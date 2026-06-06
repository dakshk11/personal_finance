from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.recommendation_agent import run as run_endpoint
from app.db.session import Base
from app.models.entities import AIAdvisorOpenAIKey, User
from app.schemas.common import RecommendationAgentRunRequest
from app.services.ai_advisor import encrypt_api_key
from app.services.recommendation_agent import CandidateIdea, TipRanksEnricher, _breakout_idea, _extension_warnings, _parse_portfolio_input, _ranking_prompt, run_recommendation_agent


SECRET = "test-secret-for-recommendation-agent-key"
PLAINTEXT_KEY = "sess-test-valid-openai-key-value"
TIPRANKS_TEST_KEY = "test-tipranks-placeholder"


class FailingTipRanks(TipRanksEnricher):
    def enrich(self, symbols: list[str]):
        return {}, {"status": "unavailable", "checked_symbols": symbols}, ["TipRanks test failure."]


class CapturingTipRanks(TipRanksEnricher):
    captured_key = ""

    def __init__(self, api_key: str) -> None:
        self.captured_key = api_key
        CapturingTipRanks.captured_key = api_key

    def enrich(self, symbols: list[str]):
        return {symbols[0]: {"ticker": symbols[0], "smartScore": 9}} if symbols else {}, {
            "status": "available",
            "checked_symbols": symbols,
            "provider": "tipranks_remote_mcp",
        }, []


class RecommendationAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def _seed_user(self) -> tuple[object, User]:
        db = self.Session()
        user = User(email="recommendation@example.com", password_hash="hash")
        db.add(user)
        db.commit()
        db.refresh(user)
        return db, user

    def test_merges_duplicate_symbols_and_returns_ranked_ideas(self) -> None:
        db, user = self._seed_user()
        wheel_idea = CandidateIdea(
            symbol="AAPL",
            source_agents=["Wheel Scanner"],
            strategy_tags=["cash secured put"],
            scanner_scores={"wheel": 18},
            evidence=["Wheel evidence"],
        )
        breakout_idea = CandidateIdea(
            symbol="AAPL",
            source_agents=["Breakout Scanner"],
            strategy_tags=["momentum breakout"],
            scanner_scores={"breakout": 91},
            evidence=["Breakout evidence"],
        )
        smart_idea = CandidateIdea(
            symbol="MSFT",
            source_agents=["Smart Candles"],
            strategy_tags=["smart candle blue"],
            scanner_scores={"smart_candles": 82},
            evidence=["Smart candle evidence"],
        )

        with self._patched_scanners(wheel=[wheel_idea], breakout=[breakout_idea], smart=[smart_idea]), patch(
            "app.services.recommendation_agent.generate_text",
            side_effect=[
                ('{"ranked_ideas":[{"rank":1,"symbol":"AAPL","verdict":"First pass","rationale":"merged"}]}', {"usage": {"input_tokens": 10}}),
                ('{"ranked_ideas":[{"rank":1,"symbol":"AAPL","verdict":"Best merged idea","rationale":"Two scanners agree."}]}', {"usage": {"output_tokens": 10}}),
            ],
        ) as generate:
            result = run_recommendation_agent(
                db,
                user.id,
                RecommendationAgentRunRequest(model="ollama:llama3", include_tipranks=False, current_portfolio="AAPL:12,NVDA:3"),
                settings=SimpleNamespace(ibkr_research_api_url="http://test", tipranks_api_url=""),
            )

        self.assertEqual(result["ranked_ideas"][0]["symbol"], "AAPL")
        self.assertIn("Wheel Scanner", result["ranked_ideas"][0]["source_agents"])
        self.assertIn("Breakout Scanner", result["ranked_ideas"][0]["source_agents"])
        self.assertEqual(result["scanner_summary"]["Wheel Scanner"]["status"], "ok")
        self.assertIn('"symbol": "NVDA"', generate.call_args_list[0].args[1])

    def test_ollama_endpoint_does_not_require_openai_key(self) -> None:
        db, user = self._seed_user()
        with patch("app.api.recommendation_agent.run_recommendation_agent", return_value=self._empty_result("ollama:llama3")) as service:
            result = run_endpoint(RecommendationAgentRunRequest(model="ollama:llama3"), user, db)

        self.assertEqual(result.model, "ollama:llama3")
        self.assertIsNone(service.call_args.kwargs.get("api_key"))

    def test_openai_endpoint_requires_saved_key(self) -> None:
        db, user = self._seed_user()
        with self.assertRaises(HTTPException) as raised:
            run_endpoint(RecommendationAgentRunRequest(model="gpt-5.4"), user, db)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("OpenAI API key", str(raised.exception.detail))

    def test_openai_endpoint_decrypts_saved_key(self) -> None:
        db, user = self._seed_user()
        db.add(
            AIAdvisorOpenAIKey(
                user_id=user.id,
                encrypted_api_key=encrypt_api_key(PLAINTEXT_KEY, SECRET),
                key_fingerprint="sha256:test",
            )
        )
        db.commit()

        with patch("app.api.recommendation_agent.get_settings", return_value=SimpleNamespace(ai_advisor_key_encryption_secret=SECRET)), patch(
            "app.api.recommendation_agent.run_recommendation_agent",
            return_value=self._empty_result("gpt-5.4-mini"),
        ) as service:
            run_endpoint(RecommendationAgentRunRequest(model="gpt-5.4-mini"), user, db)

        self.assertEqual(service.call_args.kwargs.get("api_key"), PLAINTEXT_KEY)

    def test_tipranks_failure_does_not_fail_run(self) -> None:
        db, user = self._seed_user()
        idea = CandidateIdea(
            symbol="NVDA",
            source_agents=["OptiTrade Lab"],
            strategy_tags=["optitrade buy"],
            scanner_scores={"optitrade": 73},
            evidence=["OptiTrade evidence"],
        )

        with self._patched_scanners(opti=[idea]), patch(
            "app.services.recommendation_agent.generate_text",
            side_effect=[
                ('{"ranked_ideas":[{"rank":1,"symbol":"NVDA"}]}', {}),
                ('{"ranked_ideas":[{"rank":1,"symbol":"NVDA"}]}', {}),
            ],
        ):
            result = run_recommendation_agent(
                db,
                user.id,
                RecommendationAgentRunRequest(model="ollama:llama3", include_tipranks=True),
                settings=SimpleNamespace(ibkr_research_api_url="http://test", tipranks_api_url="http://test"),
                tipranks_enricher=FailingTipRanks(),
            )

        self.assertEqual(result["ranked_ideas"][0]["symbol"], "NVDA")
        self.assertIn("TipRanks test failure.", result["warnings"])
        self.assertEqual(result["tipranks_status"]["status"], "unavailable")

    def test_per_run_tipranks_key_is_not_returned(self) -> None:
        db, user = self._seed_user()
        idea = CandidateIdea(
            symbol="NVDA",
            source_agents=["OptiTrade Lab"],
            strategy_tags=["optitrade buy"],
            scanner_scores={"optitrade": 73},
            evidence=["OptiTrade evidence"],
        )

        with self._patched_scanners(opti=[idea]), patch(
            "app.services.recommendation_agent.TipRanksRemoteMcpEnricher",
            CapturingTipRanks,
        ), patch(
            "app.services.recommendation_agent.generate_text",
            side_effect=[
                ('{"ranked_ideas":[{"rank":1,"symbol":"NVDA"}]}', {}),
                ('{"ranked_ideas":[{"rank":1,"symbol":"NVDA"}]}', {}),
            ],
        ):
            result = run_recommendation_agent(
                db,
                user.id,
                RecommendationAgentRunRequest(model="ollama:llama3", include_tipranks=True, tipranks_api_key=TIPRANKS_TEST_KEY),
                settings=SimpleNamespace(ibkr_research_api_url="http://test", tipranks_api_url=""),
            )

        self.assertEqual(CapturingTipRanks.captured_key, TIPRANKS_TEST_KEY)
        serialized = str(result)
        self.assertNotIn(TIPRANKS_TEST_KEY, serialized)
        self.assertEqual(result["ranked_ideas"][0]["tipranks"]["smartScore"], 9)

    def test_ranking_prompt_reuses_equity_research_rubric_and_user_context(self) -> None:
        prompt = _ranking_prompt(
            [{"symbol": "AAPL", "evidence": ["scanner evidence"]}],
            3,
            phase="final-pass",
            user_context="Prefer durable cash flow and avoid earnings binary risk.",
            portfolio=[{"symbol": "NVDA", "shares": 10}],
        )

        self.assertIn("Wall Street-style research discipline", prompt)
        self.assertIn("research_stance", prompt)
        self.assertIn("Prefer durable cash flow", prompt)
        self.assertIn("NVDA", prompt)
        self.assertIn("40-DMA", prompt)
        self.assertIn("do not chase new money", prompt)
        self.assertIn("ranked_ideas", prompt)

    def test_portfolio_input_parser_accepts_symbol_share_pairs(self) -> None:
        self.assertEqual(
            _parse_portfolio_input("nvda:10, AVGO:5.5, bad, cash:nope"),
            [{"symbol": "NVDA", "shares": 10.0}, {"symbol": "AVGO", "shares": 5.5}],
        )

    def test_extension_warning_bands_use_price_above_40dma(self) -> None:
        self.assertIn("Caution", _extension_warnings({"price": 116, "sma40": 100})[0])
        self.assertIn("Dangerous", _extension_warnings({"price": 121, "sma40": 100})[0])
        self.assertIn("Very dangerous", _extension_warnings({"price": 131, "sma40": 100})[0])

    def test_dangerous_extension_warning_mentions_rsi_volume_and_no_chase(self) -> None:
        warnings = _extension_warnings({"price": 125, "sma40": 100, "rsi14": 72, "relative_volume": 2.4})

        self.assertEqual(len(warnings), 1)
        self.assertIn("RSI is above 70", warnings[0])
        self.assertIn("climax-type", warnings[0])
        self.assertIn("do not chase new money", warnings[0])
        self.assertIn("20-day/40-day MA", warnings[0])

    def test_breakout_candidate_carries_extension_warning(self) -> None:
        idea = _breakout_idea({
            "symbol": "NVDA",
            "score": 88,
            "price": 125,
            "sma40": 100,
            "rsi14": 73,
            "relative_volume": 2.1,
            "summary": "Breakout detected.",
        })

        self.assertIsNotNone(idea)
        self.assertTrue(any("Dangerous" in warning for warning in idea.warnings))

    def _patched_scanners(self, wheel=None, breakout=None, smart=None, opti=None):
        return patch.multiple(
            "app.services.recommendation_agent",
            WheelScannerAdapter=FakeAdapter.factory(wheel or []),
            BreakoutScannerAdapter=FakeDbAdapter.factory(breakout or [], "Breakout Scanner"),
            SmartCandlesAdapter=FakeDbOnlyAdapter.factory(smart or [], "Smart Candles"),
            OptiTradeLabAdapter=FakeAdapter.factory(opti or [], "OptiTrade Lab"),
        )

    def _empty_result(self, model: str) -> dict:
        from datetime import datetime, timezone

        return {
            "generated_at": datetime.now(timezone.utc),
            "model": model,
            "ranked_ideas": [],
            "scanner_summary": {},
            "tipranks_status": {"status": "skipped"},
            "warnings": [],
            "raw_llm_markdown": "",
            "usage": {},
        }


class FakeAdapter:
    def __init__(self, ideas: list[CandidateIdea]):
        self.ideas = ideas
        self.name = self.__class__.__name__.replace("Fake", "")

    @classmethod
    def factory(cls, ideas: list[CandidateIdea], name: str = "Wheel Scanner"):
        class BoundFakeAdapter(cls):
            def __init__(self, *args, **kwargs):
                super().__init__(ideas)
                self.name = name

        BoundFakeAdapter.name = name
        return BoundFakeAdapter

    def scan(self, limit: int):
        return self.ideas[:limit], {"candidate_count": len(self.ideas)}, []


class FakeDbAdapter(FakeAdapter):
    @classmethod
    def factory(cls, ideas: list[CandidateIdea], name: str):
        class BoundFakeDbAdapter(cls):
            def __init__(self, *args, **kwargs):
                super().__init__(ideas)
                self.name = name

        BoundFakeDbAdapter.name = name
        return BoundFakeDbAdapter

    def scan(self, db, user_id: int, limit: int):
        return self.ideas[:limit], {"candidate_count": len(self.ideas)}, []


class FakeDbOnlyAdapter(FakeAdapter):
    @classmethod
    def factory(cls, ideas: list[CandidateIdea], name: str):
        class BoundFakeDbOnlyAdapter(cls):
            def __init__(self, *args, **kwargs):
                super().__init__(ideas)
                self.name = name

        BoundFakeDbOnlyAdapter.name = name
        return BoundFakeDbOnlyAdapter

    def scan(self, db, limit: int):
        return self.ideas[:limit], {"candidate_count": len(self.ideas)}, []


if __name__ == "__main__":
    unittest.main()
