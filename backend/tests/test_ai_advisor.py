from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.ai_advisor import get_openai_key_status, get_report, run_retirement_plan, save_openai_key
from app.db.session import Base
from app.models.entities import AIAdvisorOpenAIKey, AIAdvisorReport, User
from app.schemas.common import AIAdvisorOpenAIKeyIn, AIAdvisorRetirementRunRequest
from app.services.ai_advisor import (
    RETIREMENT_PROMPT_MODULE_BY_ID,
    decrypt_api_key,
    encrypt_api_key,
    required_field_ids,
    validate_openai_api_key,
)


SECRET = "test-secret-for-ai-advisor-key-encryption"
PLAINTEXT_KEY = "sess-test-valid-openai-key-value"


class AIAdvisorTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def _seed_user(self, email: str = "ai@example.com") -> tuple[object, User]:
        db = self.Session()
        user = User(email=email, password_hash="hash")
        db.add(user)
        db.commit()
        db.refresh(user)
        return db, user

    def test_key_save_rejects_missing_or_invalid_encryption_secret(self) -> None:
        db, user = self._seed_user()

        with patch(
            "app.api.ai_advisor.get_settings",
            return_value=SimpleNamespace(ai_advisor_key_encryption_secret="short"),
        ):
            with self.assertRaises(HTTPException) as raised:
                save_openai_key(AIAdvisorOpenAIKeyIn(api_key=PLAINTEXT_KEY), user, db)

        self.assertEqual(raised.exception.status_code, 500)
        self.assertEqual(db.scalar(select(func.count(AIAdvisorOpenAIKey.id))), 0)

    def test_key_save_rejects_invalid_key_format_before_database_write(self) -> None:
        db, user = self._seed_user()

        with patch("app.api.ai_advisor.get_settings", return_value=SimpleNamespace(ai_advisor_key_encryption_secret=SECRET)):
            with self.assertRaises(HTTPException) as raised:
                save_openai_key(AIAdvisorOpenAIKeyIn(api_key="not-a-real-openai-key"), user, db)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(db.scalar(select(func.count(AIAdvisorOpenAIKey.id))), 0)

    def test_stored_key_ciphertext_does_not_contain_plaintext(self) -> None:
        ciphertext = encrypt_api_key(PLAINTEXT_KEY, SECRET)

        self.assertNotIn(PLAINTEXT_KEY, ciphertext)
        self.assertEqual(decrypt_api_key(ciphertext, SECRET), PLAINTEXT_KEY)

    def test_key_validation_uses_responses_api(self) -> None:
        with patch("app.services.ai_advisor._openai_json_request", return_value={}) as request:
            validate_openai_api_key(PLAINTEXT_KEY)

        request.assert_called_once()
        self.assertEqual(request.call_args.args[0], "https://api.openai.com/v1/responses")
        self.assertEqual(request.call_args.kwargs["method"], "POST")
        self.assertEqual(request.call_args.kwargs["payload"]["model"], "gpt-5.4-mini")

    def test_retirement_run_rejects_missing_required_fields(self) -> None:
        db, user = self._seed_user()

        with self.assertRaises(HTTPException) as raised:
            run_retirement_plan(
                AIAdvisorRetirementRunRequest(module_id="full-retirement-blueprint", model="gpt-5.4", inputs={}),
                user,
                db,
            )

        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("age", str(raised.exception.detail))

    def test_retirement_run_decrypts_key_calls_openai_and_saves_report(self) -> None:
        db, user = self._seed_user()
        with patch(
            "app.api.ai_advisor.get_settings",
            return_value=SimpleNamespace(ai_advisor_key_encryption_secret=SECRET),
        ):
            save_openai_key(AIAdvisorOpenAIKeyIn(api_key=PLAINTEXT_KEY), user, db)

        module = RETIREMENT_PROMPT_MODULE_BY_ID["portfolio-strategy"]
        inputs = {field_id: "test value" for field_id in required_field_ids(module)}

        with patch("app.api.ai_advisor.get_settings", return_value=SimpleNamespace(ai_advisor_key_encryption_secret=SECRET)), patch(
            "app.api.ai_advisor.create_openai_response",
            return_value=("Report body", {"usage": {"input_tokens": 12, "output_tokens": 34}}),
        ) as create_response:
            result = run_retirement_plan(
                AIAdvisorRetirementRunRequest(module_id=module.id, model="gpt-5.4-mini", inputs=inputs),
                user,
                db,
            )

        self.assertEqual(result.response_text, "Report body")
        self.assertEqual(result.model, "gpt-5.4-mini")
        self.assertEqual(db.scalar(select(func.count(AIAdvisorReport.id))), 1)
        create_response.assert_called_once()
        self.assertEqual(create_response.call_args.args[0], PLAINTEXT_KEY)
        self.assertNotIn("[amount]", result.prompt_text)

    def test_users_cannot_read_other_users_key_or_report(self) -> None:
        db = self.Session()
        user_one = User(email="one@example.com", password_hash="hash")
        user_two = User(email="two@example.com", password_hash="hash")
        db.add_all([user_one, user_two])
        db.commit()
        db.refresh(user_one)
        db.refresh(user_two)
        db.add(
            AIAdvisorOpenAIKey(
                user_id=user_one.id,
                encrypted_api_key=encrypt_api_key(PLAINTEXT_KEY, SECRET),
                key_fingerprint="sha256:test",
            )
        )
        report = AIAdvisorReport(
            user_id=user_one.id,
            module_id="portfolio-strategy",
            module_title="Portfolio Strategy",
            model="gpt-5.4",
            input_snapshot_json="{}",
            prompt_text="Prompt",
            response_text="Report",
            usage_json="{}",
        )
        db.add(report)
        db.commit()
        db.refresh(report)

        self.assertFalse(get_openai_key_status(user_two, db).has_key)
        with self.assertRaises(HTTPException) as raised:
            get_report(report.id, user_two, db)
        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
