from types import SimpleNamespace
import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.earnings_agent import get_run, run_digest
from app.db.session import Base
from app.models.entities import AIAdvisorOpenAIKey, EarningsAgentRun, User, utc_now
from app.schemas.common import EarningsAgentRunRequest
from app.services.ai_advisor import encrypt_api_key
from app.services.earnings_agent import (
    EarningsCompany,
    EarningsSource,
    best_company_ir_links,
    best_sec_exhibit,
    extract_sec_document_text,
    fetch_company_ir_sources,
    fetch_motley_transcript_source,
    fetch_youtube_discovery_source,
    parse_digest_response,
    parse_sec_submission_documents,
    resolve_company,
    run_earnings_agent,
)


SECRET = "earnings-agent-test-secret-at-least-32-chars"
PLAINTEXT_KEY = "sess-test-valid-openai-key-value"


class EarningsAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def _seed_user(self, email: str = "earnings@example.com") -> tuple[object, User]:
        db = self.Session()
        user = User(email=email, password_hash="hash")
        db.add(user)
        db.commit()
        db.refresh(user)
        return db, user

    def test_resolves_company_by_ticker_and_name(self) -> None:
        records = [
            {"ticker": "AAPL", "title": "Apple Inc.", "cik_str": 320193},
            {"ticker": "MSFT", "title": "Microsoft Corp", "cik_str": 789019},
        ]
        with patch("app.services.earnings_agent._company_ticker_records", return_value=records):
            by_ticker = resolve_company("aapl")
            by_name = resolve_company("Microsoft")

        self.assertEqual(by_ticker.ticker, "AAPL")
        self.assertEqual(by_ticker.cik, "0000320193")
        self.assertEqual(by_name.ticker, "MSFT")

    def test_sec_submission_parser_prefers_ex_99_1_earnings_release(self) -> None:
        submission = """
        <DOCUMENT>
        <TYPE>EX-99.2
        <FILENAME>presentation.htm
        <DESCRIPTION>Investor presentation
        <TEXT><html><body>Presentation deck text</body></html></TEXT>
        </DOCUMENT>
        <DOCUMENT>
        <TYPE>EX-99.1
        <FILENAME>earnings-release.htm
        <DESCRIPTION>Earnings press release
        <TEXT><html><body>Revenue grew and operating margin expanded.</body></html></TEXT>
        </DOCUMENT>
        """
        documents = parse_sec_submission_documents(submission, "https://www.sec.gov/Archives/edgar/data/1/2")
        best = best_sec_exhibit(documents)

        self.assertIsNotNone(best)
        assert best is not None
        self.assertEqual(best["filename"], "earnings-release.htm")
        text, warning = extract_sec_document_text(best)
        self.assertIsNone(warning)
        self.assertIn("Revenue grew", text)

    def test_sec_multi_source_returns_release_and_presentation(self) -> None:
        submission = """
        <DOCUMENT>
        <TYPE>EX-99.1
        <FILENAME>release.htm
        <DESCRIPTION>Earnings press release
        <TEXT><html><body>Revenue grew and operating margin expanded.</body></html></TEXT>
        </DOCUMENT>
        <DOCUMENT>
        <TYPE>EX-99.2
        <FILENAME>presentation.htm
        <DESCRIPTION>Investor presentation
        <TEXT><html><body>Presentation with ARR, revenue, and guidance.</body></html></TEXT>
        </DOCUMENT>
        """
        submissions_json = {
            "filings": {
                "recent": {
                    "form": ["8-K"],
                    "accessionNumber": ["0000320193-26-000001"],
                    "filingDate": ["2026-04-30"],
                }
            }
        }
        with patch("app.services.earnings_agent._fetch_json", return_value=submissions_json), patch(
            "app.services.earnings_agent._fetch_sec_submission_text",
            return_value=(submission, "https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/0000320193-26-000001.txt"),
        ):
            from app.services.earnings_agent import fetch_sec_earnings_sources

            sources = fetch_sec_earnings_sources(EarningsCompany("AAPL", "Apple Inc.", "0000320193"))

        self.assertEqual({source.source_type for source in sources}, {"sec", "sec_presentation"})
        self.assertTrue(any("Presentation" in (source.excerpt or "") for source in sources))

    def test_sec_submission_text_fetch_tries_hyphenated_filename_first(self) -> None:
        from app.services.earnings_agent import _fetch_sec_submission_text

        calls: list[str] = []

        def fake_fetch(url: str, *, sec: bool, max_bytes: int) -> str:
            del sec, max_bytes
            calls.append(url)
            if url.endswith("000032019326000001.txt"):
                raise AssertionError("Should use the hyphenated SEC submission filename before no-dash fallback.")
            return "submission"

        with patch("app.services.earnings_agent._fetch_text", side_effect=fake_fetch):
            text, url = _fetch_sec_submission_text(
                "https://www.sec.gov/Archives/edgar/data/320193/000032019326000001",
                "0000320193-26-000001",
            )

        self.assertEqual(text, "submission")
        self.assertTrue(url.endswith("0000320193-26-000001.txt"))
        self.assertEqual(len(calls), 1)

    def test_sec_pdf_extraction_path_uses_pypdf_helper(self) -> None:
        document = {
            "type": "EX-99.2",
            "filename": "presentation.pdf",
            "description": "Investor presentation",
            "url": "https://www.sec.gov/presentation.pdf",
            "text": "",
        }
        with patch("app.services.earnings_agent._fetch_bytes", return_value=b"%PDF"), patch(
            "app.services.earnings_agent._extract_pdf_text",
            return_value="Parsed PDF text",
        ) as parser:
            text, warning = extract_sec_document_text(document)

        self.assertEqual(text, "Parsed PDF text")
        self.assertIsNone(warning)
        parser.assert_called_once()

    def test_missing_motley_transcript_returns_warning(self) -> None:
        with patch("app.services.earnings_agent._fetch_text", return_value="<html><a href='/not-this'>Other</a></html>"):
            source = fetch_motley_transcript_source(EarningsCompany("AAPL", "Apple Inc.", "0000320193"))

        self.assertEqual(source.status, "missing")
        self.assertIn("No matching Motley Fool", source.warning or "")

    def test_company_ir_fallback_extracts_presentation_link(self) -> None:
        html = """
        <html><body>
        <a href="/files/q2-2026-earnings-presentation.pdf">Q2 2026 Earnings Presentation</a>
        </body></html>
        """
        links = best_company_ir_links(html, "https://investor.example.com/", EarningsCompany("TEST", "Test Corp", "1"))
        self.assertEqual(links[0]["url"], "https://investor.example.com/files/q2-2026-earnings-presentation.pdf")

        with patch("app.services.earnings_agent.company_ir_candidate_pages", return_value=["https://investor.example.com/"]), patch(
            "app.services.earnings_agent._fetch_text",
            return_value=html,
        ), patch(
            "app.services.earnings_agent.extract_public_document_url",
            return_value=("Revenue and EPS presentation text", None),
        ):
            sources = fetch_company_ir_sources(EarningsCompany("TEST", "Test Corp", "1"))

        self.assertEqual(sources[0].source_type, "company_ir")
        self.assertEqual(sources[0].status, "found")
        self.assertIn("Revenue", sources[0].text)

    def test_youtube_discovery_is_manual_review_only(self) -> None:
        source = fetch_youtube_discovery_source(EarningsCompany("AAPL", "Apple Inc.", "0000320193"))

        self.assertEqual(source.source_type, "youtube")
        self.assertEqual(source.status, "partial")
        self.assertIn("youtube.com/results", source.url or "")
        self.assertIn("manual review", source.warning or "")

    def test_digest_json_parse_and_markdown_fallback(self) -> None:
        parsed = parse_digest_response(
            '{"executive_summary":"Summary","top_takeaways":["One"],"financial_metrics":[{"name":"Revenue","value":"up","context":"demand"}],"management_tone":"Measured","risks":["Margin"],"deep_dive_questions":["Capex?"],"source_notes":["SEC only"]}'
        )
        fallback = parse_digest_response("### Earnings notes\nNot JSON")

        self.assertEqual(parsed["executive_summary"], "Summary")
        self.assertEqual(parsed["financial_metrics"][0]["name"], "Revenue")
        self.assertEqual(fallback["raw_markdown"], "### Earnings notes\nNot JSON")

    def test_missing_openai_key_returns_clear_error(self) -> None:
        db, user = self._seed_user()

        with self.assertRaises(HTTPException) as raised:
            run_digest(EarningsAgentRunRequest(query="AAPL", model="gpt-5.4"), user, db)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("OpenAI API key", str(raised.exception.detail))

    def test_run_persists_digest_without_full_transcript_text(self) -> None:
        db, user = self._seed_user()
        company = EarningsCompany("AAPL", "Apple Inc.", "0000320193")
        transcript_text = "Management discussed services growth. " + ("context " * 150) + "DO_NOT_STORE_FULL_TRANSCRIPT"
        with (
            patch("app.services.earnings_agent.resolve_company", return_value=company),
            patch(
                "app.services.earnings_agent.fetch_sec_earnings_sources",
                return_value=[
                    EarningsSource(
                        source_type="sec",
                        title="AAPL SEC earnings release",
                        status="found",
                        url="https://sec.test/aapl",
                        document_type="8-K EX-99.1",
                        text="Revenue increased and gross margin improved.",
                        excerpt="Revenue increased and gross margin improved.",
                    )
                ],
            ),
            patch(
                "app.services.earnings_agent.fetch_motley_transcript_source",
                return_value=EarningsSource(
                    source_type="motley",
                    title="AAPL earnings call transcript",
                    status="found",
                    url="https://fool.test/aapl",
                    document_type="earnings call transcript",
                    text=transcript_text,
                    excerpt=transcript_text[:120],
                ),
            ),
            patch("app.services.earnings_agent.fetch_company_ir_sources", return_value=[]),
            patch(
                "app.services.earnings_agent.create_openai_response",
                return_value=(
                    json.dumps(
                        {
                            "executive_summary": "Apple reported a durable quarter.",
                            "top_takeaways": ["Services remained a key driver."],
                            "financial_metrics": [{"name": "Revenue", "value": "increased", "context": "demand"}],
                            "management_tone": "Confident but measured.",
                            "risks": ["FX and margin pressure."],
                            "deep_dive_questions": ["How durable is services growth?"],
                            "source_notes": ["SEC and transcript used."],
                        }
                    ),
                    {"usage": {"input_tokens": 10, "output_tokens": 20}},
                ),
            ),
        ):
            run = run_earnings_agent(db, user.id, "AAPL", "gpt-5.4", PLAINTEXT_KEY)

        stored = db.get(EarningsAgentRun, run.id)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.source_status, "complete")
        self.assertEqual(db.scalar(select(func.count(EarningsAgentRun.id))), 1)
        self.assertNotIn("DO_NOT_STORE_FULL_TRANSCRIPT", stored.transcript_source_json)
        self.assertNotIn("DO_NOT_STORE_FULL_TRANSCRIPT", stored.prompt_text)
        self.assertIn("Full source text was sent transiently", stored.prompt_text)
        self.assertIn("services", stored.transcript_source_json)
        self.assertTrue(stored.sec_source_json.startswith("["))

    def test_get_run_is_scoped_to_current_user(self) -> None:
        db, user_one = self._seed_user("one@example.com")
        user_two = User(email="two@example.com", password_hash="hash")
        db.add(user_two)
        db.commit()
        db.refresh(user_two)
        run = EarningsAgentRun(
            user_id=user_one.id,
            query="AAPL",
            ticker="AAPL",
            company_name="Apple Inc.",
            cik="0000320193",
            model="gpt-5.4",
            source_status="partial",
            sec_source_json="{}",
            transcript_source_json="{}",
            digest_json='{"executive_summary":"Summary"}',
            warnings_json="[]",
            prompt_text="Prompt",
            response_text="{}",
            usage_json="{}",
        )
        db.add(run)
        db.add(
            AIAdvisorOpenAIKey(
                user_id=user_one.id,
                encrypted_api_key=encrypt_api_key(PLAINTEXT_KEY, SECRET),
                key_fingerprint="sha256:test",
            )
        )
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
        with patch("app.api.earnings_agent.get_settings", return_value=SimpleNamespace(ai_advisor_key_encryption_secret=SECRET)), patch(
            "app.api.earnings_agent.run_earnings_agent",
        ) as service:
            service.side_effect = lambda db_arg, user_id, query, model, api_key: EarningsAgentRun(
                id=7,
                user_id=user_id,
                query=query,
                ticker="AAPL",
                company_name="Apple Inc.",
                cik="0000320193",
                model=model,
                source_status="partial",
                sec_source_json='{"source_type":"sec","title":"SEC","status":"found"}',
                transcript_source_json='{"source_type":"motley","title":"Transcript","status":"missing"}',
                digest_json='{"executive_summary":"Summary"}',
                warnings_json="[]",
                prompt_text="Prompt",
                response_text="{}",
                usage_json="{}",
                created_at=utc_now(),
            )

            result = run_digest(EarningsAgentRunRequest(query="AAPL", model="gpt-5.4-mini"), user, db)

        self.assertEqual(result.ticker, "AAPL")
        self.assertEqual(service.call_args.args[4], PLAINTEXT_KEY)


if __name__ == "__main__":
    unittest.main()
