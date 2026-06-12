from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from io import BytesIO

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.ai_advisor import delete_alpaca_key, delete_lunarcrush_key, delete_nvidia_key, delete_tipranks_key, get_alpaca_key_status, get_lunarcrush_key_status, get_nvidia_key_status, get_openai_key_status, get_report, get_tipranks_key_status, run_retirement_plan, save_alpaca_key, save_lunarcrush_key, save_nvidia_key, save_openai_key, save_tipranks_key
from app.db.session import Base
from app.models.entities import AIAdvisorAlpacaKey, AIAdvisorLunarCrushKey, AIAdvisorNvidiaKey, AIAdvisorOpenAIKey, AIAdvisorReport, AIAdvisorTipRanksKey, User
from app.schemas.common import AIAdvisorAlpacaKeyIn, AIAdvisorLunarCrushKeyIn, AIAdvisorNvidiaKeyIn, AIAdvisorOpenAIKeyIn, AIAdvisorRetirementRunRequest, AIAdvisorTipRanksKeyIn
from app.services.ai_advisor import (
    RETIREMENT_PROMPT_MODULE_BY_ID,
    create_nvidia_response,
    decrypt_api_key,
    encrypt_api_key,
    required_field_ids,
    validate_openai_api_key,
    _provider_error_message,
)


SECRET = "test-secret-for-ai-advisor-key-encryption"
PLAINTEXT_KEY = "sess-test-valid-openai-key-value"
TIPRANKS_KEY = "test-tipranks-key-value"
LUNARCRUSH_KEY = "test-lunarcrush-key-value"
NVIDIA_KEY = "test-nvidia-key-value"
ALPACA_KEY = "alpaca-test-key"
ALPACA_SECRET = "alpaca-test-secret"


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

    def test_tipranks_key_save_status_and_delete(self) -> None:
        db, user = self._seed_user()

        with patch("app.api.ai_advisor.get_settings", return_value=SimpleNamespace(ai_advisor_key_encryption_secret=SECRET)):
            saved = save_tipranks_key(AIAdvisorTipRanksKeyIn(api_key=TIPRANKS_KEY), user, db)

        self.assertTrue(saved.has_key)
        self.assertTrue(saved.key_fingerprint.startswith("sha256:"))
        row = db.scalar(select(AIAdvisorTipRanksKey).where(AIAdvisorTipRanksKey.user_id == user.id))
        self.assertIsNotNone(row)
        self.assertNotIn(TIPRANKS_KEY, row.encrypted_api_key)
        self.assertEqual(decrypt_api_key(row.encrypted_api_key, SECRET), TIPRANKS_KEY)
        self.assertTrue(get_tipranks_key_status(user, db).has_key)

        deleted = delete_tipranks_key(user, db)
        self.assertFalse(deleted.has_key)
        self.assertFalse(get_tipranks_key_status(user, db).has_key)

    def test_alpaca_key_save_status_and_delete(self) -> None:
        db, user = self._seed_user()

        with patch("app.api.ai_advisor.get_settings", return_value=SimpleNamespace(ai_advisor_key_encryption_secret=SECRET)):
            saved = save_alpaca_key(AIAdvisorAlpacaKeyIn(api_key=ALPACA_KEY, api_secret=ALPACA_SECRET), user, db)

        self.assertTrue(saved.has_key)
        self.assertTrue(saved.key_fingerprint.startswith("sha256:"))
        row = db.scalar(select(AIAdvisorAlpacaKey).where(AIAdvisorAlpacaKey.user_id == user.id))
        self.assertIsNotNone(row)
        self.assertNotIn(ALPACA_KEY, row.encrypted_api_key)
        self.assertNotIn(ALPACA_SECRET, row.encrypted_api_secret)
        self.assertEqual(decrypt_api_key(row.encrypted_api_key, SECRET), ALPACA_KEY)
        self.assertEqual(decrypt_api_key(row.encrypted_api_secret, SECRET), ALPACA_SECRET)
        self.assertTrue(get_alpaca_key_status(user, db).has_key)

        deleted = delete_alpaca_key(user, db)
        self.assertFalse(deleted.has_key)
        self.assertFalse(get_alpaca_key_status(user, db).has_key)

    def test_lunarcrush_key_save_status_and_delete(self) -> None:
        db, user = self._seed_user()

        with patch("app.api.ai_advisor.get_settings", return_value=SimpleNamespace(ai_advisor_key_encryption_secret=SECRET)):
            saved = save_lunarcrush_key(AIAdvisorLunarCrushKeyIn(api_key=LUNARCRUSH_KEY), user, db)

        self.assertTrue(saved.has_key)
        self.assertTrue(saved.key_fingerprint.startswith("sha256:"))
        row = db.scalar(select(AIAdvisorLunarCrushKey).where(AIAdvisorLunarCrushKey.user_id == user.id))
        self.assertIsNotNone(row)
        self.assertNotIn(LUNARCRUSH_KEY, row.encrypted_api_key)
        self.assertEqual(decrypt_api_key(row.encrypted_api_key, SECRET), LUNARCRUSH_KEY)
        self.assertTrue(get_lunarcrush_key_status(user, db).has_key)

        deleted = delete_lunarcrush_key(user, db)
        self.assertFalse(deleted.has_key)
        self.assertFalse(get_lunarcrush_key_status(user, db).has_key)

    def test_nvidia_key_save_status_and_delete(self) -> None:
        db, user = self._seed_user()

        with patch("app.api.ai_advisor.get_settings", return_value=SimpleNamespace(ai_advisor_key_encryption_secret=SECRET)):
            saved = save_nvidia_key(AIAdvisorNvidiaKeyIn(api_key=NVIDIA_KEY), user, db)

        self.assertTrue(saved.has_key)
        self.assertTrue(saved.key_fingerprint.startswith("sha256:"))
        row = db.scalar(select(AIAdvisorNvidiaKey).where(AIAdvisorNvidiaKey.user_id == user.id))
        self.assertIsNotNone(row)
        self.assertNotIn(NVIDIA_KEY, row.encrypted_api_key)
        self.assertEqual(decrypt_api_key(row.encrypted_api_key, SECRET, "NVIDIA API key"), NVIDIA_KEY)
        self.assertTrue(get_nvidia_key_status(user, db).has_key)

        deleted = delete_nvidia_key(user, db)
        self.assertFalse(deleted.has_key)
        self.assertFalse(get_nvidia_key_status(user, db).has_key)

    def test_key_validation_uses_responses_api(self) -> None:
        with patch("app.services.ai_advisor._openai_json_request", return_value={}) as request:
            validate_openai_api_key(PLAINTEXT_KEY)

        request.assert_called_once()
        self.assertEqual(request.call_args.args[0], "https://api.openai.com/v1/responses")
        self.assertEqual(request.call_args.kwargs["method"], "POST")
        self.assertEqual(request.call_args.kwargs["payload"]["model"], "gpt-5.4-mini")

    def test_nvidia_response_uses_openai_compatible_chat_completions(self) -> None:
        with patch(
            "app.services.ai_advisor._provider_json_request",
            return_value={"choices": [{"message": {"content": "NVIDIA answer"}}], "usage": {"total_tokens": 9}},
        ) as request:
            text, payload = create_nvidia_response(NVIDIA_KEY, "minimaxai/minimax-m2.7", "Rank these ideas.", instructions="Be concise.")

        self.assertEqual(text, "NVIDIA answer")
        self.assertEqual(payload["usage"]["provider"], "nvidia")
        self.assertEqual(request.call_args.args[0], "https://integrate.api.nvidia.com/v1/chat/completions")
        self.assertEqual(request.call_args.args[1], NVIDIA_KEY)
        self.assertEqual(request.call_args.kwargs["method"], "POST")
        self.assertEqual(request.call_args.kwargs["provider_label"], "NVIDIA NIM")
        request_payload = request.call_args.kwargs["payload"]
        self.assertEqual(request_payload["model"], "minimaxai/minimax-m2.7")
        self.assertEqual(request_payload["messages"][0]["role"], "system")
        self.assertEqual(request_payload["messages"][1]["content"], "Rank these ideas.")

    def test_nvidia_response_maps_requested_alias_to_nim_model_id(self) -> None:
        with patch(
            "app.services.ai_advisor._provider_json_request",
            return_value={"choices": [{"message": {"content": "GLM answer"}}]},
        ) as request:
            text, payload = create_nvidia_response(NVIDIA_KEY, "zhipuai/glm-5.1", "Compare setups.")

        self.assertEqual(text, "GLM answer")
        self.assertEqual(payload["usage"]["requested_model"], "zhipuai/glm-5.1")
        self.assertEqual(payload["usage"]["model"], "z-ai/glm-5.1")
        self.assertEqual(request.call_args.kwargs["payload"]["model"], "z-ai/glm-5.1")

    def test_nvidia_response_maps_kimi_alias_to_current_nim_endpoint(self) -> None:
        with patch(
            "app.services.ai_advisor._provider_json_request",
            return_value={"choices": [{"message": {"content": "Kimi answer"}}]},
        ) as request:
            text, payload = create_nvidia_response(NVIDIA_KEY, "moonshot-ai/kimi-2.5", "Compare setups.")

        self.assertEqual(text, "Kimi answer")
        self.assertEqual(payload["usage"]["requested_model"], "moonshot-ai/kimi-2.5")
        self.assertEqual(payload["usage"]["model"], "moonshotai/kimi-k2.6")
        self.assertEqual(request.call_args.kwargs["payload"]["model"], "moonshotai/kimi-k2.6")

    def test_provider_error_message_includes_detail_payload(self) -> None:
        exc = HTTPError(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            400,
            "Bad Request",
            {},
            BytesIO(b'{"detail":"model not available"}'),
        )

        self.assertEqual(_provider_error_message(exc, "NVIDIA NIM"), "model not available")

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
            "app.api.ai_advisor.generate_text",
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
        self.assertEqual(create_response.call_args.kwargs.get("api_key"), PLAINTEXT_KEY)
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
