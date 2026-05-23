import io
import unittest
from unittest.mock import patch
import zipfile

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.personal_cfo import get_project
from app.db.session import Base
from app.models.entities import User
from app.services import personal_cfo as cfo


class PersonalCFOTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def _seed_user(self, email: str = "cfo@example.com") -> tuple[object, User]:
        db = self.Session()
        user = User(email=email, password_hash="hash")
        db.add(user)
        db.commit()
        db.refresh(user)
        return db, user

    def test_first_interview_response_uses_exact_opening_line(self) -> None:
        db, user = self._seed_user()

        project = cfo.create_project(db, user.id, "Investment Folder")

        self.assertEqual(project.messages[0].content, cfo.OPENING_MESSAGE)
        self.assertEqual(project.messages[0].role, "assistant")
        self.assertEqual({file_row.path for file_row in project.files}, {
            "investor-one-pager.md",
            "instructions.md",
            "memory.md",
            "investor-strategy-system-prompt.md",
        })

    def test_user_cannot_access_another_users_project(self) -> None:
        db = self.Session()
        user_one = User(email="one@example.com", password_hash="hash")
        user_two = User(email="two@example.com", password_hash="hash")
        db.add_all([user_one, user_two])
        db.commit()
        db.refresh(user_one)
        db.refresh(user_two)
        project = cfo.create_project(db, user_one.id, "Owner Project")

        with self.assertRaises(HTTPException) as raised:
            get_project(project.id, user_two, db)

        self.assertEqual(raised.exception.status_code, 404)

    def test_one_pager_generation_rejected_before_all_phases_complete(self) -> None:
        db, user = self._seed_user()
        project = cfo.create_project(db, user.id, "Early Project")

        with self.assertRaises(cfo.PersonalCFOStateError) as raised:
            cfo.generate_one_pager(db, project, "sk-test", "gpt-5.4")

        self.assertIn("Complete all seven", str(raised.exception))

    def test_generic_answer_pushback_is_preserved_without_advancing(self) -> None:
        db, user = self._seed_user()
        project = cfo.create_project(db, user.id, "Generic Project")

        updated = cfo.submit_interview_message(db, project, "sk-test", "gpt-5.4", "buy and hold quality companies")

        self.assertEqual(updated.current_phase, 1)
        self.assertEqual(updated.messages[-1].content, cfo.GENERIC_PUSHBACK)

    def test_interview_uses_system_prompt_and_one_question(self) -> None:
        db, user = self._seed_user()
        project = cfo.create_project(db, user.id, "Interview Project")

        with patch(
            "app.services.personal_cfo.create_openai_response",
            return_value=("What constraint would force you to change the framework? Also what is the next goal?", {}),
        ) as create_response:
            updated = cfo.submit_interview_message(
                db,
                project,
                "sk-test",
                "gpt-5.4-mini",
                "I live in California, earn W2 income, and the portfolio is long-term optionality capital.",
            )

        self.assertEqual(updated.current_phase, 2)
        self.assertEqual(updated.messages[-1].content, "What constraint would force you to change the framework?")
        self.assertIn("Investor Strategy Architect", create_response.call_args.kwargs["instructions"])
        self.assertIn("Do not produce the investor one-pager", create_response.call_args.args[2])

    def test_one_pager_generation_and_single_refinement(self) -> None:
        db, user = self._seed_user()
        project = cfo.create_project(db, user.id, "Visha")
        project.current_phase = 8
        project.status = "ready_for_one_pager"
        db.commit()

        one_pager = """# Investor One-Pager - Visha

**Last updated:** 23 May 2026
**Operating base:** California, US resident, US tax regime

---

## North Star
Optionality first.

---

## Core Philosophy
- **Rules before impulse.** Stress does not rewrite the framework.

---

## Time Horizon
Tactical and core capital are separate.

---

## Mindset Rules
1. State the rule first.

---

## Personal Nuances
- Time budget is constrained.

---

## Anti-Portfolio
- Won't buy social-pressure deals.

---

*This document is reviewed every quarter. Material changes require a 48-hour cooldown period before execution.*"""

        with patch("app.services.personal_cfo.create_openai_response", return_value=(one_pager, {})):
            generated = cfo.generate_one_pager(db, project, "sk-test", "gpt-5.4")

        one_pager_file = next(file_row for file_row in generated.files if file_row.path == "investor-one-pager.md")
        self.assertIn("# Investor One-Pager - Visha", one_pager_file.content)
        self.assertTrue(generated.one_pager_generated)
        self.assertEqual(generated.messages[-1].content, cfo.REFINEMENT_QUESTION)

        with patch("app.services.personal_cfo.create_openai_response", return_value=(one_pager.replace("Optionality first.", "Optionality with a hard cash floor."), {})):
            refined = cfo.refine_one_pager(db, generated, "sk-test", "gpt-5.4", "Make the cash floor sharper.")

        self.assertTrue(refined.refinement_used)
        with self.assertRaises(cfo.PersonalCFOStateError):
            cfo.refine_one_pager(db, refined, "sk-test", "gpt-5.4", "Second pass.")

    def test_zip_export_contains_expected_entries(self) -> None:
        db, user = self._seed_user()
        project = cfo.create_project(db, user.id, "Zip Project")

        archive = cfo.export_project_zip(db, project)
        with zipfile.ZipFile(io.BytesIO(archive), "r") as zipped:
            names = set(zipped.namelist())

        self.assertIn("investor-one-pager.md", names)
        self.assertIn("instructions.md", names)
        self.assertIn("memory.md", names)
        self.assertIn("investor-strategy-system-prompt.md", names)
        self.assertIn("Financials/", names)

    def test_csv_upload_persists_and_feeds_dashboard(self) -> None:
        db, user = self._seed_user()
        project = cfo.create_project(db, user.id, "Dashboard Project")
        content = "date,cash,pnl,symbol,market_value\n2026-05-01,10000,250,AAPL,6000\n2026-05-15,12500,-50,MSFT,4000\n"

        upload = cfo.create_upload(db, project, "positions.csv", content)
        summary = cfo.dashboard_summary(project)

        self.assertEqual(cfo.upload_row_count(upload), 2)
        self.assertEqual(summary["pnl_summary"]["total_pnl"], 200)
        self.assertEqual(len(summary["cash_trend"]), 2)
        self.assertEqual(summary["exposures"][0]["label"], "AAPL")


if __name__ == "__main__":
    unittest.main()
