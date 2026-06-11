from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.research_prompts import get_run, list_runs, run_prompt
from app.db.session import Base
from app.models.entities import AIAdvisorOpenAIKey, AIAdvisorResearchPromptRun, User
from app.schemas.common import AIAdvisorResearchPromptRunRequest
from app.services.ai_advisor import create_openai_web_search_response, encrypt_api_key
from app.services.research_prompts import build_research_prompt, run_research_prompt


SECRET = "test-secret-for-research-prompts-key"
OPENAI_KEY = "sess-test-valid-openai-key-value"


class ResearchPromptTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def _seed_user(self, email: str = "research@example.com") -> tuple[object, User]:
        db = self.Session()
        user = User(email=email, password_hash="hash")
        db.add(user)
        db.commit()
        db.refresh(user)
        return db, user

    def test_prompt_builder_includes_constraints_and_template_requirements(self) -> None:
        _, inputs, prompt = build_research_prompt("hedge-designer", {"sector_market": "semiconductors"})

        self.assertEqual(inputs["sector_market"], "semiconductors")
        self.assertIn("semiconductors", prompt)
        self.assertIn("annualized cost", prompt)
        self.assertIn("source list with URLs", prompt)
        self.assertIn("date-sensitive caveat", prompt)
        self.assertIn("educational-only disclaimer", prompt)
        self.assertIn("Do not provide personalized investment advice", prompt)

    def test_missing_required_template_input_returns_422(self) -> None:
        db, user = self._seed_user()

        with self.assertRaises(HTTPException) as raised:
            run_prompt(
                AIAdvisorResearchPromptRunRequest(template_id="hedge-designer", provider="goose", model="llama3.1:8b", inputs={}),
                user,
                db,
            )

        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("Sector or market exposure", str(raised.exception.detail))

    def test_openai_web_search_helper_uses_responses_web_search_tool(self) -> None:
        with patch("app.services.ai_advisor._openai_json_request", return_value={"output_text": "answer"}) as request:
            text, _ = create_openai_web_search_response(OPENAI_KEY, "gpt-5.4", "Find current sources")

        self.assertEqual(text, "answer")
        payload = request.call_args.kwargs["payload"]
        self.assertEqual(request.call_args.args[0], "https://api.openai.com/v1/responses")
        self.assertEqual(payload["tools"], [{"type": "web_search"}])
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertIn("web_search_call.action.sources", payload["include"])

    def test_goose_provider_uses_local_model_and_does_not_require_openai_key(self) -> None:
        db, user = self._seed_user()
        with patch(
            "app.services.research_prompts.generate_text",
            return_value=("Answer with https://example.com/source", {"usage": {"provider": "goose"}}),
        ) as generate:
            run = run_research_prompt(
                db,
                user_id=user.id,
                template_id="macro-playbook",
                provider="goose",
                model="llama3.1:8b",
                inputs={},
                ollama_base_url="http://127.0.0.1:11434",
            )

        generate.assert_called_once()
        self.assertEqual(generate.call_args.args[0], "goose:llama3.1:8b")
        self.assertEqual(run.model, "goose:llama3.1:8b")
        self.assertIn("https://example.com/source", run.sources_json)
        self.assertIn("Goose source quality depends", run.warnings_json)

    def test_openai_run_decrypts_key_saves_sources_and_is_user_scoped(self) -> None:
        db, user_one = self._seed_user("one@example.com")
        _, user_two = self._seed_user("two@example.com")
        db.add(
            AIAdvisorOpenAIKey(
                user_id=user_one.id,
                encrypted_api_key=encrypt_api_key(OPENAI_KEY, SECRET),
                key_fingerprint="sha256:test",
            )
        )
        db.commit()

        response_payload = {
            "output_text": "Answer",
            "output": [{"content": [{"annotations": [{"type": "url_citation", "url": "https://example.com", "title": "Example"}]}]}],
            "usage": {"input_tokens": 10},
        }
        with patch("app.api.research_prompts.get_settings", return_value=SimpleNamespace(ai_advisor_key_encryption_secret=SECRET)), patch(
            "app.services.research_prompts.create_openai_web_search_response",
            return_value=("Answer", response_payload),
        ) as openai:
            result = run_prompt(
                AIAdvisorResearchPromptRunRequest(template_id="macro-playbook", provider="openai_web", model="gpt-5.4", inputs={}),
                user_one,
                db,
            )

        openai.assert_called_once()
        self.assertEqual(openai.call_args.args[0], OPENAI_KEY)
        self.assertEqual(result.sources[0].url, "https://example.com")
        self.assertEqual(len(list_runs(user_one, db)), 1)

        with self.assertRaises(HTTPException) as raised:
            get_run(result.id, user_two, db)
        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(db.query(AIAdvisorResearchPromptRun).count(), 1)


if __name__ == "__main__":
    unittest.main()
