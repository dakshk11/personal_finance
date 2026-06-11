from types import SimpleNamespace
import json
import unittest
from unittest.mock import patch

import pandas as pd
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.stock_analysis import get_run, run_analysis
from app.db.session import Base
from app.models.entities import AIAdvisorOpenAIKey, StockAnalysisRun, User, utc_now
from app.schemas.common import StockAnalysisRunRequest
from app.services.ai_advisor import encrypt_api_key
from app.services.stock_analysis import (
    StockAnalysisCompany,
    StockAnalysisSource,
    build_dcf_estimate,
    collect_stock_analysis_context,
    fetch_sec_companyfacts_snapshot,
    normalize_financial_statements,
    normalize_sec_companyfacts,
    normalize_research_stance,
    parse_stock_analysis_response,
    peer_symbols_for_sector,
    run_stock_analysis,
)


SECRET = "stock-analysis-test-secret-at-least-32-chars"
PLAINTEXT_KEY = "sess-test-valid-openai-key-value"


def _context() -> dict[str, object]:
    source_text = "Earnings presentation text " + ("context " * 60) + "DO_NOT_STORE_FULL_SOURCE"
    return {
        "profile": {
            "company_name": "Apple Inc.",
            "sector": "Information Technology",
            "industry": "Consumer Electronics",
            "current_price": 100.0,
            "forward_pe": 20.0,
        },
        "financials": [
            {"year": 2022, "revenue": 1000.0, "free_cash_flow": 180.0, "net_income": 150.0},
            {"year": 2023, "revenue": 1100.0, "free_cash_flow": 200.0, "net_income": 160.0},
            {"year": 2024, "revenue": 1210.0, "free_cash_flow": 220.0, "net_income": 175.0},
        ],
        "valuation": {
            "current_price": 100.0,
            "market_cap": 1_000_000.0,
            "trailing_pe": 22.0,
            "forward_pe": 20.0,
            "price_to_sales": 6.0,
            "enterprise_to_ebitda": 15.0,
            "industry_average_forward_pe": 19.0,
            "peer_average_forward_pe": 19.0,
            "dcf": {
                "fair_value_per_share": 112.0,
                "upside_downside_pct": 0.12,
                "base_free_cash_flow": 220.0,
                "growth_rate": 0.08,
                "discount_rate": 0.10,
                "terminal_growth_rate": 0.03,
                "warning": None,
            },
            "peers": [{"symbol": "MSFT", "company_name": "Microsoft Corp", "forward_pe": 25.0}],
        },
        "sources": [
            StockAnalysisSource(
                source_type="sec",
                title="AAPL SEC earnings release",
                status="found",
                url="https://sec.test/aapl",
                document_type="8-K EX-99.1",
                excerpt="Earnings presentation text",
                text=source_text,
            )
        ],
        "snapshot": {
            "profile": {"company_name": "Apple Inc.", "sector": "Information Technology", "industry": "Consumer Electronics", "current_price": 100.0},
            "financials": [
                {"year": 2022, "revenue": 1000.0, "free_cash_flow": 180.0, "net_income": 150.0},
                {"year": 2023, "revenue": 1100.0, "free_cash_flow": 200.0, "net_income": 160.0},
                {"year": 2024, "revenue": 1210.0, "free_cash_flow": 220.0, "net_income": 175.0},
            ],
            "valuation": {
                "current_price": 100.0,
                "market_cap": 1_000_000.0,
                "trailing_pe": 22.0,
                "forward_pe": 20.0,
                "price_to_sales": 6.0,
                "enterprise_to_ebitda": 15.0,
                "industry_average_forward_pe": 19.0,
                "peer_average_forward_pe": 19.0,
                "dcf": {
                    "fair_value_per_share": 112.0,
                    "upside_downside_pct": 0.12,
                    "base_free_cash_flow": 220.0,
                    "growth_rate": 0.08,
                    "discount_rate": 0.10,
                    "terminal_growth_rate": 0.03,
                    "warning": None,
                },
                "peers": [{"symbol": "MSFT", "company_name": "Microsoft Corp", "forward_pe": 25.0}],
            },
            "as_of_date": "2026-05-25",
        },
        "warnings": [],
    }


def _fact(year: int, value: float) -> dict[str, object]:
    return {
        "start": f"{year}-01-01",
        "end": f"{year}-12-31",
        "val": value,
        "fy": year,
        "fp": "FY",
        "form": "10-K",
        "filed": f"{year + 1}-02-01",
        "frame": f"CY{year}",
    }


def _instant_fact(year: int, value: float) -> dict[str, object]:
    return {
        "end": f"{year}-12-31",
        "val": value,
        "fy": year,
        "fp": "FY",
        "form": "10-K",
        "filed": f"{year + 1}-02-01",
        "frame": f"CY{year}Q4I",
    }


class StockAnalysisTests(unittest.TestCase):
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

    def test_normalizes_five_year_financial_statement_rows(self) -> None:
        columns = pd.to_datetime(["2024-12-31", "2023-12-31", "2022-12-31"])
        income = pd.DataFrame(
            [[1210.0, 1100.0, 1000.0], [605.0, 550.0, 500.0], [302.5, 275.0, 230.0], [181.5, 165.0, 140.0]],
            index=["Total Revenue", "Gross Profit", "Operating Income", "Net Income"],
            columns=columns,
        )
        cashflow = pd.DataFrame(
            [[260.0, 230.0, 200.0], [-40.0, -30.0, -20.0]],
            index=["Operating Cash Flow", "Capital Expenditure"],
            columns=columns,
        )
        balance = pd.DataFrame(
            [[400.0, 420.0, 450.0], [900.0, 850.0, 800.0]],
            index=["Total Debt", "Stockholders Equity"],
            columns=columns,
        )

        rows = normalize_financial_statements(income, cashflow, balance)

        self.assertEqual([row["year"] for row in rows], [2022, 2023, 2024])
        self.assertAlmostEqual(rows[-1]["revenue_growth"], 0.10, places=4)
        self.assertAlmostEqual(rows[-1]["free_cash_flow"], 220.0)
        self.assertAlmostEqual(rows[-1]["profit_margin"], 0.15)
        self.assertAlmostEqual(rows[-1]["roe"], 181.5 / 900.0, places=5)

    def test_dcf_estimate_is_deterministic_and_warns_on_missing_inputs(self) -> None:
        profile = {"current_price": 100.0, "shares_outstanding": 100.0, "total_cash": 0.0, "total_debt": 0.0}
        financials = [
            {"year": 2022, "revenue": 1000.0, "free_cash_flow": 100.0},
            {"year": 2023, "revenue": 1100.0, "free_cash_flow": 110.0},
            {"year": 2024, "revenue": 1210.0, "free_cash_flow": 120.0},
        ]

        first = build_dcf_estimate(profile, financials)
        second = build_dcf_estimate(profile, financials)
        missing = build_dcf_estimate({"current_price": 100.0}, [])

        self.assertEqual(first, second)
        self.assertIsNone(first["warning"])
        self.assertGreater(first["fair_value_per_share"], 0)
        self.assertIn("requires free cash flow", missing["warning"])

    def test_sec_companyfacts_fallback_builds_financial_rows_and_profile_metrics(self) -> None:
        payload = {
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [_fact(2023, 1000), _fact(2024, 1200)]}},
                    "GrossProfit": {"units": {"USD": [_fact(2023, 500), _fact(2024, 660)]}},
                    "OperatingIncomeLoss": {"units": {"USD": [_fact(2023, 200), _fact(2024, 300)]}},
                    "NetIncomeLoss": {"units": {"USD": [_fact(2023, 100), _fact(2024, 180)]}},
                    "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [_fact(2023, 250), _fact(2024, 330)]}},
                    "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [_fact(2023, 40), _fact(2024, 60)]}},
                    "LongTermDebt": {"units": {"USD": [_instant_fact(2023, 70), _instant_fact(2024, 80)]}},
                    "LongTermDebtCurrent": {"units": {"USD": [_instant_fact(2023, 10), _instant_fact(2024, 20)]}},
                    "StockholdersEquity": {"units": {"USD": [_instant_fact(2023, 500), _instant_fact(2024, 600)]}},
                    "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [_instant_fact(2024, 90)]}},
                },
                "dei": {
                    "EntityCommonStockSharesOutstanding": {"units": {"shares": [_instant_fact(2024, 10)]}},
                },
            }
        }
        warnings: list[str] = []
        with patch("app.services.stock_analysis._fetch_json", return_value=payload):
            snapshot = fetch_sec_companyfacts_snapshot("0000000001", warnings)

        rows = snapshot["financials"]
        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(rows[-1]["revenue_growth"], 0.2)
        self.assertAlmostEqual(rows[-1]["free_cash_flow"], 270)
        self.assertAlmostEqual(rows[-1]["debt"], 100)
        self.assertEqual(snapshot["profile_metrics"]["shares_outstanding"], 10)
        self.assertEqual(snapshot["profile_metrics"]["total_cash"], 90)
        self.assertEqual(warnings, [])

    def test_collect_context_uses_sec_financial_rows_when_yfinance_is_throttled(self) -> None:
        db, _ = self._seed_user()
        sec_rows = [
            {"year": 2023, "revenue": 1000.0, "free_cash_flow": 100.0, "net_income": 100.0, "debt": 0.0},
            {"year": 2024, "revenue": 1200.0, "revenue_growth": 0.2, "free_cash_flow": 150.0, "net_income": 180.0, "debt": 0.0},
        ]

        def no_yfinance_rows(symbol: str, warnings: list[str]) -> list[dict[str, object]]:
            del symbol
            warnings.append("No annual financial statement rows were available.")
            return []

        with (
            patch("app.services.stock_analysis._fetch_yfinance_info", return_value={}),
            patch("app.services.stock_analysis.fetch_yfinance_financials", side_effect=no_yfinance_rows),
            patch("app.services.stock_analysis.fetch_sec_companyfacts_snapshot", return_value={"financials": sec_rows, "profile_metrics": {"shares_outstanding": 10.0, "total_cash": 0.0, "total_debt": 0.0}}),
            patch("app.services.stock_analysis._market_snapshot", return_value=SimpleNamespace(price=100.0, forward_pe=20.0, warning=None)),
            patch("app.services.stock_analysis.fetch_stock_earnings_sources", return_value=[]),
        ):
            context = collect_stock_analysis_context(db, StockAnalysisCompany("AMD", "Advanced Micro Devices Inc", "0000002488"))

        self.assertEqual(context["financials"], sec_rows)
        self.assertEqual(context["profile"]["shares_outstanding"], 10.0)
        self.assertIsNone(context["valuation"]["dcf"]["warning"])
        self.assertIn("Financial rows were sourced from SEC Company Facts", " ".join(context["warnings"]))
        self.assertNotIn("No annual financial statement rows", " ".join(context["warnings"]))

    def test_peer_symbols_use_same_sector_fallback(self) -> None:
        peers = peer_symbols_for_sector("AAPL", "Information Technology", limit=4)

        self.assertGreater(len(peers), 0)
        self.assertNotIn("AAPL", peers)

    def test_digest_parse_and_research_stance_sanitizes_literal_advice_words(self) -> None:
        parsed = parse_stock_analysis_response(
            json.dumps(
                {
                    "executive_summary": "Summary",
                    "business_model": "Revenue streams",
                    "moat_summary": "Strong",
                    "moat_score": 8,
                    "risks": [{"rank": 1, "title": "Competition", "detail": "Pressure", "severity": "high"}],
                    "scenarios": [{"case": "bull", "summary": "Upside", "key_drivers": ["Margins"]}],
                    "research_stance": "Buy",
                }
            )
        )
        fallback = parse_stock_analysis_response("### Not JSON")

        self.assertEqual(parsed["research_stance"], "Attractive for research")
        self.assertEqual(normalize_research_stance("Hold"), "Neutral / monitor")
        self.assertEqual(parsed["risks"][0]["rank"], 1)
        self.assertEqual(fallback["raw_markdown"], "### Not JSON")

    def test_missing_openai_key_returns_clear_error(self) -> None:
        db, user = self._seed_user()

        with patch("app.api.stock_analysis.resolve_stock_company", return_value=StockAnalysisCompany("AAPL", "Apple Inc.", "0000320193")), self.assertRaises(HTTPException) as raised:
            run_analysis(StockAnalysisRunRequest(query="AAPL", model="gpt-5.4"), user, db)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("OpenAI API key", str(raised.exception.detail))

    def test_foundation_router_mode_requires_openai_key(self) -> None:
        db, user = self._seed_user()

        with patch("app.api.stock_analysis.resolve_stock_company", return_value=StockAnalysisCompany("AAPL", "Apple Inc.", "0000320193")), self.assertRaises(HTTPException) as raised:
            run_analysis(StockAnalysisRunRequest(query="AAPL", model="auto", model_mode="foundation"), user, db)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("OpenAI API key", str(raised.exception.detail))

    def test_auto_model_defaults_to_foundation_router_mode(self) -> None:
        db, user = self._seed_user()

        with patch("app.api.stock_analysis.resolve_stock_company", return_value=StockAnalysisCompany("AAPL", "Apple Inc.", "0000320193")), self.assertRaises(HTTPException) as raised:
            run_analysis(StockAnalysisRunRequest(query="AAPL", model="auto"), user, db)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("OpenAI API key", str(raised.exception.detail))

    def test_ollama_router_mode_does_not_require_openai_key(self) -> None:
        db, user = self._seed_user()

        with patch("app.api.stock_analysis.resolve_stock_company", return_value=StockAnalysisCompany("AAPL", "Apple Inc.", "0000320193")), patch(
            "app.api.stock_analysis.run_stock_analysis"
        ) as service:
            service.side_effect = lambda db_arg, user_id, query, model, api_key, ollama_base_url=None, model_mode=None: StockAnalysisRun(
                id=8,
                user_id=user_id,
                query=query,
                ticker="AAPL",
                company_name="Apple Inc.",
                sector="Information Technology",
                industry="Consumer Electronics",
                model="ollama:llama3.1:8b",
                source_status="partial",
                source_json="[]",
                financial_snapshot_json=json.dumps(_context()["snapshot"]),
                digest_json='{"research_stance":"Neutral / monitor"}',
                warnings_json="[]",
                prompt_text="Prompt",
                response_text="{}",
                usage_json='{"model_routing":{"model":"ollama:llama3.1:8b","display_name":"Llama 3.1 8B","mode":"ollama"}}',
                created_at=utc_now(),
            )

            result = run_analysis(StockAnalysisRunRequest(query="AAPL", model="auto", model_mode="ollama"), user, db)

        self.assertEqual(result.model, "ollama:llama3.1:8b")
        self.assertEqual(result.model_routing["display_name"], "Llama 3.1 8B")
        self.assertIsNone(service.call_args.args[4])
        self.assertEqual(service.call_args.kwargs["model_mode"], "ollama")

    def test_ollama_model_override_does_not_require_openai_key(self) -> None:
        db, user = self._seed_user()

        with patch("app.api.stock_analysis.resolve_stock_company", return_value=StockAnalysisCompany("AAPL", "Apple Inc.", "0000320193")), patch(
            "app.api.stock_analysis.run_stock_analysis"
        ) as service:
            service.side_effect = lambda db_arg, user_id, query, model, api_key, ollama_base_url=None, model_mode=None: StockAnalysisRun(
                id=9,
                user_id=user_id,
                query=query,
                ticker="AAPL",
                company_name="Apple Inc.",
                sector="Information Technology",
                industry="Consumer Electronics",
                model=model,
                source_status="partial",
                source_json="[]",
                financial_snapshot_json=json.dumps(_context()["snapshot"]),
                digest_json='{"research_stance":"Neutral / monitor"}',
                warnings_json="[]",
                prompt_text="Prompt",
                response_text="{}",
                usage_json="{}",
                created_at=utc_now(),
            )

            result = run_analysis(StockAnalysisRunRequest(query="AAPL", model="ollama:qwen3:8b"), user, db)

        self.assertEqual(result.model, "ollama:qwen3:8b")
        self.assertIsNone(service.call_args.args[4])
        self.assertIsNone(service.call_args.kwargs["model_mode"])

    def test_api_reuses_recent_saved_run_without_openai_key(self) -> None:
        db, user = self._seed_user()
        run = StockAnalysisRun(
            user_id=user.id,
            query="AAPL",
            ticker="AAPL",
            company_name="Apple Inc.",
            sector="Information Technology",
            industry="Consumer Electronics",
            model="gpt-5.4",
            source_status="partial",
            source_json="[]",
            financial_snapshot_json=json.dumps(_context()["snapshot"]),
            digest_json='{"research_stance":"Neutral / monitor"}',
            warnings_json='["Stored warning"]',
            prompt_text="Prompt",
            response_text="{}",
            usage_json="{}",
            created_at=utc_now(),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        with patch("app.api.stock_analysis.resolve_stock_company", return_value=StockAnalysisCompany("AAPL", "Apple Inc.", "0000320193")), patch(
            "app.api.stock_analysis.run_stock_analysis"
        ) as service:
            result = run_analysis(StockAnalysisRunRequest(query="Apple", model="gpt-5.4"), user, db)

        service.assert_not_called()
        self.assertEqual(result.id, run.id)
        self.assertTrue(result.reused_from_cache)
        self.assertIn("no new", result.cache_message or "")

    def test_run_persists_analysis_without_full_source_text(self) -> None:
        db, user = self._seed_user()
        with (
            patch("app.services.stock_analysis.resolve_stock_company", return_value=StockAnalysisCompany("AAPL", "Apple Inc.", "0000320193")),
            patch("app.services.stock_analysis.collect_stock_analysis_context", return_value=_context()),
            patch(
                "app.services.stock_analysis.generate_text",
                return_value=(
                    json.dumps(
                        {
                            "executive_summary": "Apple remains a scaled platform.",
                            "business_model": "Hardware and services.",
                            "moat_summary": "Brand, ecosystem, and switching costs.",
                            "moat_score": 8,
                            "competitor_comparison": ["Compared with Microsoft and Alphabet."],
                            "industry_trends": ["AI devices", "Services mix"],
                            "financial_health": "Financials appear resilient.",
                            "valuation_summary": "Valuation is above many peers but supported by margins.",
                            "risks": [{"rank": 1, "title": "Competition", "detail": "AI and device cycles.", "severity": "high"}],
                            "growth_potential": "Services and installed base expansion.",
                            "institutional_perspective": "Institutions may value quality and liquidity.",
                            "scenarios": [{"case": "base", "summary": "Steady growth.", "key_drivers": ["Services"]}],
                            "bull_bear_debate": ["Bull analyst: margins.", "Bear analyst: multiple.", "Balanced conclusion."],
                            "latest_earnings": "Recent source context was reviewed.",
                            "outlook_12_24_months": "Monitor product cycle and margins.",
                            "research_stance": "Neutral / monitor",
                            "deep_dive_questions": ["What drives services?"],
                            "source_notes": ["SEC source used."],
                        }
                    ),
                    {"usage": {"input_tokens": 10, "output_tokens": 20}},
                ),
            ),
        ):
            run = run_stock_analysis(db, user.id, "AAPL", "gpt-5.4", PLAINTEXT_KEY)

        stored = db.get(StockAnalysisRun, run.id)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.source_status, "complete")
        self.assertNotIn("DO_NOT_STORE_FULL_SOURCE", stored.source_json)
        self.assertNotIn("DO_NOT_STORE_FULL_SOURCE", stored.prompt_text)
        self.assertIn("Apple remains", stored.digest_json)

    def test_get_run_is_scoped_to_current_user(self) -> None:
        db, user_one = self._seed_user("one-stock@example.com")
        user_two = User(email="two-stock@example.com", password_hash="hash")
        db.add(user_two)
        db.commit()
        db.refresh(user_two)
        run = StockAnalysisRun(
            user_id=user_one.id,
            query="AAPL",
            ticker="AAPL",
            company_name="Apple Inc.",
            sector="Information Technology",
            industry="Consumer Electronics",
            model="gpt-5.4",
            source_status="partial",
            source_json="[]",
            financial_snapshot_json=json.dumps(_context()["snapshot"]),
            digest_json='{"research_stance":"Neutral / monitor"}',
            warnings_json="[]",
            prompt_text="Prompt",
            response_text="{}",
            usage_json="{}",
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        with self.assertRaises(HTTPException) as raised:
            get_run(run.id, user_two, db)

        self.assertEqual(raised.exception.status_code, 404)

    def test_api_run_decrypts_key_and_saves_result(self) -> None:
        db, user = self._seed_user()
        db.add(
            AIAdvisorOpenAIKey(
                user_id=user.id,
                encrypted_api_key=encrypt_api_key(PLAINTEXT_KEY, SECRET),
                key_fingerprint="sha256:test",
            )
        )
        db.commit()
        with (
            patch("app.api.stock_analysis.resolve_stock_company", return_value=StockAnalysisCompany("AAPL", "Apple Inc.", "0000320193")),
            patch("app.api.stock_analysis.get_settings", return_value=SimpleNamespace(ai_advisor_key_encryption_secret=SECRET)),
            patch("app.api.stock_analysis.run_stock_analysis") as service,
        ):
            service.side_effect = lambda db_arg, user_id, query, model, api_key, ollama_base_url=None, model_mode=None: StockAnalysisRun(
                id=7,
                user_id=user_id,
                query=query,
                ticker="AAPL",
                company_name="Apple Inc.",
                sector="Information Technology",
                industry="Consumer Electronics",
                model=model,
                source_status="partial",
                source_json="[]",
                financial_snapshot_json=json.dumps(_context()["snapshot"]),
                digest_json='{"research_stance":"Neutral / monitor"}',
                warnings_json="[]",
                prompt_text="Prompt",
                response_text="{}",
                usage_json="{}",
                created_at=utc_now(),
            )

            result = run_analysis(StockAnalysisRunRequest(query="AAPL", model="gpt-5.4-mini"), user, db)

        self.assertEqual(result.ticker, "AAPL")
        self.assertEqual(service.call_args.args[4], PLAINTEXT_KEY)


if __name__ == "__main__":
    unittest.main()
