import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.wheel_scanner_chat import build_wheel_scanner_chat_prompt, chat
from app.db.session import Base
from app.models.entities import User
from app.schemas.common import WheelScannerChatRequest


class WheelScannerChatTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.SessionLocal = sessionmaker(bind=engine)

    def _payload(self, model: str = "ollama:llama3") -> WheelScannerChatRequest:
        return WheelScannerChatRequest(
            query="Compare these wheel setups.",
            model=model,
            context={
                "active_tab": "watchlist",
                "filters": {"search": "NVDA", "hub_filter": "all"},
                "custom_symbols": ["COHR"],
                "selected_quotes": [
                    {
                        "symbol": "NVDA",
                        "price": 140.5,
                        "stage": 2,
                        "sata_score": 8,
                        "mansfield_rs": 4.1,
                        "rsi": 55,
                        "bb_pct": 42,
                        "iv_rank": 33,
                        "csp_30d": 2.4,
                        "cc_30d": 1.7,
                        "signals": ["CSP"],
                    }
                ],
                "recent_messages": [
                    {"role": "user", "content": "Focus on CSP risk."},
                    {"role": "assistant", "content": "I will compare premium and downside risk."},
                ],
            },
        )

    def test_prompt_includes_symbols_and_recent_messages(self) -> None:
        prompt = build_wheel_scanner_chat_prompt(self._payload())

        self.assertIn("NVDA", prompt)
        self.assertIn("Focus on CSP risk.", prompt)
        self.assertIn("selected_quotes", prompt)
        self.assertIn("Compare these wheel setups.", prompt)

    def test_empty_selected_rows_rejected(self) -> None:
        with self.assertRaises(ValueError):
            WheelScannerChatRequest(
                query="Anything?",
                model="ollama:llama3",
                context={"selected_quotes": []},
            )

    def test_openai_requires_saved_key(self) -> None:
        db = self.SessionLocal()
        try:
            user = User(email="wheel-chat@example.com", password_hash="test")
            db.add(user)
            db.commit()
            db.refresh(user)

            with self.assertRaises(HTTPException) as caught:
                chat(self._payload("gpt-5.4"), user, db)
            self.assertEqual(caught.exception.status_code, 400)
        finally:
            db.close()

    def test_ollama_routes_to_generate_text(self) -> None:
        db = self.SessionLocal()
        try:
            user = User(email="wheel-chat-ollama@example.com", password_hash="test")
            db.add(user)
            db.commit()
            db.refresh(user)

            with patch("app.api.wheel_scanner_chat.generate_text", return_value=("Answer", {"usage": {"provider": "ollama"}})) as mocked:
                result = chat(self._payload("ollama:llama3"), user, db)

            self.assertEqual(result.response_text, "Answer")
            mocked.assert_called_once()
            self.assertEqual(mocked.call_args.args[0], "ollama:llama3")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
