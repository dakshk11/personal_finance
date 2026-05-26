from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html import unescape
from io import BytesIO
import json
import re
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urljoin
from urllib.request import Request, urlopen

import certifi
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import EarningsAgentRun, utc_now
from app.services.ai_advisor import create_openai_response, response_usage
from app.services.index_data import INDEX_DEFINITIONS


SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
FOOL_TRANSCRIPTS_BASE = "https://www.fool.com/earnings-call-transcripts/"
YOUTUBE_SEARCH_BASE = "https://www.youtube.com/results"
MAX_SOURCE_CHARS = 55_000
MAX_PROMPT_SOURCE_CHARS = 24_000
MAX_EXCERPT_CHARS = 900
MAX_COMPANY_IR_SOURCES = 2

KNOWN_IR_URLS = {
    "AAPL": "https://investor.apple.com/",
    "MSFT": "https://www.microsoft.com/en-us/Investor",
    "NVDA": "https://investor.nvidia.com/",
    "AMZN": "https://ir.aboutamazon.com/",
    "GOOGL": "https://abc.xyz/investor/",
    "GOOG": "https://abc.xyz/investor/",
    "META": "https://investor.atmeta.com/",
    "TSLA": "https://ir.tesla.com/",
    "AVGO": "https://investors.broadcom.com/",
    "CSCO": "https://investor.cisco.com/",
}


class EarningsAgentSourceError(RuntimeError):
    pass


class EarningsAgentLookupError(RuntimeError):
    pass


@dataclass(frozen=True)
class EarningsCompany:
    ticker: str
    company_name: str
    cik: str | None = None


@dataclass
class EarningsSource:
    source_type: str
    title: str
    status: str
    url: str | None = None
    document_type: str | None = None
    filing_date: date | None = None
    excerpt: str | None = None
    warning: str | None = None
    text: str = ""

    def public_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "title": self.title,
            "status": self.status,
            "url": self.url,
            "document_type": self.document_type,
            "filing_date": self.filing_date.isoformat() if self.filing_date else None,
            "excerpt": self.excerpt,
            "warning": self.warning,
        }


def run_earnings_agent(db: Session, user_id: int, query: str, model: str, api_key: str) -> EarningsAgentRun:
    company = resolve_company(query)
    sec_sources = fetch_sec_earnings_sources(company)
    transcript_source = fetch_motley_transcript_source(company)
    existing_urls = {source.url for source in [*sec_sources, transcript_source] if source.url}
    company_ir_sources = fetch_company_ir_sources(company, existing_urls=existing_urls)
    sources = [*sec_sources, transcript_source, *company_ir_sources]
    discovery_sources: list[EarningsSource] = []
    if not any("transcript" in (source.document_type or "").lower() and source.text.strip() for source in sources):
        discovery_sources.append(fetch_youtube_discovery_source(company))
        discovery_sources.append(fetch_quartr_status_source(company))
        sources.extend(discovery_sources)
    warnings = [source.warning for source in sources if source.warning]
    usable_sources = [source for source in sources if source.text.strip()]
    if not usable_sources:
        raise EarningsAgentSourceError(
            "No earnings source text was available from SEC EDGAR, company investor relations, or Motley Fool for this query. Try a public US ticker with recent earnings materials."
        )

    prompt_text = build_earnings_prompt(company, usable_sources)
    response_text, response_payload = create_openai_response(
        api_key,
        model,
        prompt_text,
        instructions=(
            "You are an educational earnings research assistant. Return strict JSON only. "
            "Do not provide buy/sell recommendations, investment advice, price targets, or order instructions."
        ),
    )
    digest = parse_digest_response(response_text)
    status = _source_status(sources)

    run = EarningsAgentRun(
        user_id=user_id,
        query=query.strip(),
        ticker=company.ticker,
        company_name=company.company_name,
        cik=company.cik,
        model=model,
        source_status=status,
        sec_source_json=json.dumps([source.public_dict() for source in [*sec_sources, *company_ir_sources]], separators=(",", ":"), sort_keys=True),
        transcript_source_json=json.dumps([source.public_dict() for source in [transcript_source, *discovery_sources]], separators=(",", ":"), sort_keys=True),
        digest_json=json.dumps(digest, separators=(",", ":"), sort_keys=True),
        warnings_json=json.dumps(_unique([warning for warning in warnings if warning]), separators=(",", ":"), sort_keys=True),
        prompt_text=build_stored_prompt_snapshot(company, sources),
        response_text=response_text,
        usage_json=json.dumps(response_usage(response_payload), separators=(",", ":"), sort_keys=True),
        created_at=utc_now(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def resolve_company(query: str) -> EarningsCompany:
    cleaned = " ".join(query.strip().split())
    if not cleaned:
        raise EarningsAgentLookupError("Enter a ticker or company name.")
    ticker_query = _ticker_token(cleaned)
    records = _company_ticker_records()
    for record in records:
        if _ticker_token(str(record.get("ticker", ""))) == ticker_query:
            return EarningsCompany(
                ticker=str(record["ticker"]).upper(),
                company_name=str(record.get("title") or record["ticker"]),
                cik=_normalize_cik(record.get("cik_str")),
            )

    query_key = _company_key(cleaned)
    best: dict[str, Any] | None = None
    for record in records:
        title_key = _company_key(str(record.get("title", "")))
        if query_key and (query_key in title_key or title_key in query_key):
            best = record
            break
    if best:
        return EarningsCompany(
            ticker=str(best["ticker"]).upper(),
            company_name=str(best.get("title") or best["ticker"]),
            cik=_normalize_cik(best.get("cik_str")),
        )

    for definition in INDEX_DEFINITIONS.values():
        for holding in definition.holdings:
            symbol = str(holding.get("symbol", "")).upper()
            name = str(holding.get("name", ""))
            if _ticker_token(symbol) == ticker_query or (query_key and query_key in _company_key(name)):
                resolved = _resolve_record_by_ticker(symbol, records)
                if resolved:
                    return resolved
                return EarningsCompany(ticker=symbol, company_name=name or symbol)

    if re.fullmatch(r"[A-Za-z][A-Za-z0-9.\-]{0,9}", cleaned):
        return EarningsCompany(ticker=cleaned.upper().replace("-", "."), company_name=cleaned.upper())
    raise EarningsAgentLookupError("Could not resolve the company. Try a public US ticker symbol.")


def fetch_sec_earnings_source(company: EarningsCompany) -> EarningsSource:
    sources = fetch_sec_earnings_sources(company)
    return sources[0]


def fetch_sec_earnings_sources(company: EarningsCompany) -> list[EarningsSource]:
    if not company.cik:
        return [
            EarningsSource(
                source_type="sec",
                title="SEC EDGAR exhibit",
                status="missing",
                document_type="8-K exhibit",
                warning=f"SEC CIK could not be resolved for {company.ticker}.",
            )
        ]
    submissions_url = f"{SEC_SUBMISSIONS_BASE}/CIK{company.cik.zfill(10)}.json"
    try:
        submissions = _fetch_json(submissions_url, sec=True)
    except EarningsAgentSourceError as exc:
        return [
            EarningsSource(
                source_type="sec",
                title="SEC EDGAR exhibit",
                status="missing",
                document_type="8-K exhibit",
                warning=f"SEC submissions could not be fetched: {exc}",
            )
        ]

    recent = (submissions.get("filings") or {}).get("recent") or {}
    forms = list(recent.get("form") or [])
    accessions = list(recent.get("accessionNumber") or [])
    filing_dates = list(recent.get("filingDate") or [])
    accession_pairs = list(zip(forms, accessions, filing_dates, strict=False))

    for form, accession, filing_date_value in accession_pairs[:80]:
        if str(form).upper() not in {"8-K", "8-K/A"}:
            continue
        accession_str = str(accession)
        filing_date = _date_from_value(filing_date_value)
        folder_url = _sec_archive_folder(company.cik, accession_str)
        try:
            submission_text, submission_text_url = _fetch_sec_submission_text(folder_url, accession_str)
        except EarningsAgentSourceError:
            continue
        documents = parse_sec_submission_documents(submission_text, folder_url)
        candidates = ranked_sec_exhibits(documents)
        if not candidates:
            continue
        sources: list[EarningsSource] = []
        seen_roles: set[str] = set()
        for _, candidate in candidates:
            role = _sec_document_role(candidate)
            if role in seen_roles:
                continue
            seen_roles.add(role)
            extracted_text, warning = extract_sec_document_text(candidate)
            public_text = _compact_text(extracted_text)
            url = str(candidate.get("url") or submission_text_url)
            document_type = str(candidate.get("type") or "EX-99")
            source_type = "sec_presentation" if role == "presentation" else "sec"
            title = _source_title(company, "SEC EDGAR", candidate.get("description"), filing_date)
            if public_text:
                sources.append(
                    EarningsSource(
                        source_type=source_type,
                        title=title,
                        status="found",
                        url=url,
                        document_type=f"{str(form).upper()} {document_type}".strip(),
                        filing_date=filing_date,
                        excerpt=_excerpt(public_text),
                        warning=warning,
                        text=public_text[:MAX_SOURCE_CHARS],
                    )
                )
            else:
                sources.append(
                    EarningsSource(
                        source_type=source_type,
                        title=title,
                        status="partial",
                        url=url,
                        document_type=f"{str(form).upper()} {document_type}".strip(),
                        filing_date=filing_date,
                        warning=warning or "SEC exhibit was found, but readable text could not be extracted.",
                    )
                )
            if len(sources) >= 3:
                break
        if sources:
            return sources

    return [
        EarningsSource(
            source_type="sec",
            title="SEC EDGAR exhibit",
            status="missing",
            document_type="8-K exhibit",
            warning=f"No recent 8-K Exhibit 99.1 or 99.2 earnings material was found for {company.ticker}.",
        )
    ]


def fetch_company_ir_sources(company: EarningsCompany, existing_urls: set[str] | None = None) -> list[EarningsSource]:
    existing_urls = existing_urls or set()
    sources: list[EarningsSource] = []
    warnings: list[str] = []
    for page_url in company_ir_candidate_pages(company):
        if len(sources) >= MAX_COMPANY_IR_SOURCES:
            break
        try:
            html = _fetch_text(page_url, sec=False, max_bytes=2_500_000)
        except EarningsAgentSourceError as exc:
            warnings.append(str(exc))
            continue
        links = best_company_ir_links(html, page_url, company)
        if not links:
            page_text = _compact_text(_html_to_text(html))
            if _looks_like_earnings_material(page_text) and page_url not in existing_urls:
                sources.append(
                    EarningsSource(
                        source_type="company_ir",
                        title=f"{company.ticker} company investor relations page",
                        status="found",
                        url=page_url,
                        document_type="company investor relations earnings page",
                        excerpt=_excerpt(page_text),
                        text=page_text[:MAX_SOURCE_CHARS],
                    )
                )
            continue
        for link in links:
            if len(sources) >= MAX_COMPANY_IR_SOURCES:
                break
            url = link["url"]
            if url in existing_urls:
                continue
            text, warning = extract_public_document_url(url)
            if text:
                sources.append(
                    EarningsSource(
                        source_type="company_ir",
                        title=link["title"],
                        status="found",
                        url=url,
                        document_type=link["document_type"],
                        excerpt=_excerpt(text),
                        warning=warning,
                        text=text[:MAX_SOURCE_CHARS],
                    )
                )
            else:
                sources.append(
                    EarningsSource(
                        source_type="company_ir",
                        title=link["title"],
                        status="partial",
                        url=url,
                        document_type=link["document_type"],
                        warning=warning or "Company investor-relations document was discovered, but text could not be extracted.",
                    )
                )
    if not sources and warnings:
        return [
            EarningsSource(
                source_type="company_ir",
                title="Company investor relations",
                status="missing",
                document_type="company earnings material",
                warning=f"Company IR fallback could not fetch source text. Last warning: {warnings[-1]}",
            )
        ]
    if not sources:
        return [
            EarningsSource(
                source_type="company_ir",
                title="Company investor relations",
                status="missing",
                document_type="company earnings material",
                warning=f"No company investor-relations earnings presentation or transcript link was discovered for {company.ticker}.",
            )
        ]
    return sources


def fetch_youtube_discovery_source(company: EarningsCompany) -> EarningsSource:
    query = f"{company.ticker} {company.company_name} earnings call transcript presentation"
    url = f"{YOUTUBE_SEARCH_BASE}?search_query={quote_plus(query)}"
    return EarningsSource(
        source_type="youtube",
        title=f"YouTube search for {company.ticker} earnings call",
        status="partial",
        url=url,
        document_type="video discovery link",
        warning="YouTube is linked for manual review only; FinanceOS does not download captions or rehost video transcripts.",
    )


def fetch_quartr_status_source(company: EarningsCompany) -> EarningsSource:
    return EarningsSource(
        source_type="quartr",
        title=f"Quartr transcripts and slides for {company.ticker}",
        status="missing",
        url="https://quartr.com/",
        document_type="transcript and slide provider",
        warning="Quartr is not configured in the FinanceOS backend. The Codex Quartr connector check requires a Quartr Pro subscription, so this run used public web sources only.",
    )


def fetch_motley_transcript_source(company: EarningsCompany) -> EarningsSource:
    pages = [
        FOOL_TRANSCRIPTS_BASE,
        f"{FOOL_TRANSCRIPTS_BASE}?q={quote_plus(company.ticker)}",
        f"{FOOL_TRANSCRIPTS_BASE}page/2/",
        f"{FOOL_TRANSCRIPTS_BASE}page/3/",
    ]
    last_warning = ""
    for page_url in pages:
        try:
            index_html = _fetch_text(page_url, sec=False, max_bytes=1_500_000)
        except EarningsAgentSourceError as exc:
            last_warning = str(exc)
            continue
        link = best_motley_link(index_html, company)
        if not link:
            continue
        transcript_url = urljoin(FOOL_TRANSCRIPTS_BASE, link["href"])
        try:
            article_html = _fetch_text(transcript_url, sec=False, max_bytes=4_000_000)
        except EarningsAgentSourceError as exc:
            last_warning = str(exc)
            continue
        text = _compact_text(_html_to_text(article_html))
        if not text:
            return EarningsSource(
                source_type="motley",
                title=link["title"],
                status="partial",
                url=transcript_url,
                document_type="earnings call transcript",
                warning="Motley Fool transcript page was found, but readable text could not be extracted.",
            )
        return EarningsSource(
            source_type="motley",
            title=link["title"],
            status="found",
            url=transcript_url,
            document_type="earnings call transcript",
            excerpt=_excerpt(text),
            text=text[:MAX_SOURCE_CHARS],
        )

    warning = f"No matching Motley Fool earnings call transcript was found for {company.ticker}."
    if last_warning:
        warning = f"{warning} Last fetch warning: {last_warning}"
    return EarningsSource(
        source_type="motley",
        title="Motley Fool earnings call transcript",
        status="missing",
        document_type="earnings call transcript",
        warning=warning,
    )


def build_earnings_prompt(company: EarningsCompany, sources: list[EarningsSource]) -> str:
    source_blocks = []
    for source in sources:
        source_blocks.append(
            "\n".join(
                [
                    f"Source: {source.source_type.upper()} | {source.title}",
                    f"Document type: {source.document_type or 'unknown'}",
                    f"URL: {source.url or 'unavailable'}",
                    f"Filing/date: {source.filing_date.isoformat() if source.filing_date else 'unavailable'}",
                    "Text:",
                    source.text[:MAX_PROMPT_SOURCE_CHARS],
                ]
            )
        )
    return f"""Create an educational earnings digest for {company.company_name} ({company.ticker}).

Use only the provided source text. If a section cannot be supported by the source text, say that it was not available in the provided materials.

Return strict JSON with exactly these keys:
{{
  "executive_summary": "3-5 sentence neutral summary",
  "top_takeaways": ["takeaway 1", "takeaway 2", "takeaway 3"],
  "financial_metrics": [{{"name": "Metric name", "value": "reported value or direction", "context": "why it matters"}}],
  "management_tone": "Neutral read of management tone and operating priorities",
  "risks": ["risk 1", "risk 2"],
  "deep_dive_questions": ["question 1", "question 2"],
  "source_notes": ["which sources were used and any gaps"]
}}

Rules:
- Educational research only.
- Do not use buy, sell, hold, price target, rating, trade, or allocation instructions.
- Prefer concrete facts from the sources over generic market commentary.
- Highlight missing SEC exhibit or transcript coverage in source_notes when relevant.

Sources:
{"\n\n---\n\n".join(source_blocks)}
"""


def build_stored_prompt_snapshot(company: EarningsCompany, sources: list[EarningsSource]) -> str:
    source_summaries = []
    for source in sources:
        source_summaries.append(
            "\n".join(
                [
                    f"Source: {source.source_type.upper()} | {source.title}",
                    f"Status: {source.status}",
                    f"Document type: {source.document_type or 'unknown'}",
                    f"URL: {source.url or 'unavailable'}",
                    f"Filing/date: {source.filing_date.isoformat() if source.filing_date else 'unavailable'}",
                    f"Excerpt: {source.excerpt or 'No excerpt stored.'}",
                ]
            )
        )
    joined = "\n\n---\n\n".join(source_summaries)
    return (
        f"Earnings Agent digest prompt snapshot for {company.company_name} ({company.ticker}).\n\n"
        "Full source text was sent transiently to the LLM but is not persisted here. "
        "This stored snapshot keeps only source metadata and short provenance excerpts.\n\n"
        f"{joined}"
    )


def parse_digest_response(response_text: str) -> dict[str, Any]:
    payload = _json_from_response(response_text)
    if not isinstance(payload, dict):
        return {
            "executive_summary": response_text.strip(),
            "top_takeaways": [],
            "financial_metrics": [],
            "management_tone": "",
            "risks": [],
            "deep_dive_questions": [],
            "source_notes": ["LLM response was not valid JSON; showing the raw response as markdown."],
            "raw_markdown": response_text.strip(),
        }
    metrics = []
    for item in _list_value(payload.get("financial_metrics")):
        if isinstance(item, dict):
            name = str(item.get("name") or "Metric").strip()
            value = str(item.get("value") or "Not specified").strip()
            context = str(item.get("context") or "").strip() or None
            metrics.append({"name": name, "value": value, "context": context})
        elif item:
            metrics.append({"name": "Metric", "value": str(item), "context": None})
    return {
        "executive_summary": str(payload.get("executive_summary") or "").strip(),
        "top_takeaways": _string_list(payload.get("top_takeaways")),
        "financial_metrics": metrics[:12],
        "management_tone": str(payload.get("management_tone") or "").strip(),
        "risks": _string_list(payload.get("risks")),
        "deep_dive_questions": _string_list(payload.get("deep_dive_questions")),
        "source_notes": _string_list(payload.get("source_notes")),
        "raw_markdown": None,
    }


def parse_sec_submission_documents(submission_text: str, folder_url: str) -> list[dict[str, str]]:
    documents: list[dict[str, str]] = []
    for block in re.findall(r"<DOCUMENT>(.*?)</DOCUMENT>", submission_text, flags=re.IGNORECASE | re.DOTALL):
        doc_type = _sec_tag(block, "TYPE")
        filename = _sec_tag(block, "FILENAME")
        description = _sec_tag(block, "DESCRIPTION")
        body = _sec_text_body(block)
        if not (doc_type or filename or body):
            continue
        url = urljoin(f"{folder_url}/", filename) if filename else folder_url
        documents.append(
            {
                "type": doc_type,
                "filename": filename,
                "description": description,
                "text": body,
                "url": url,
            }
        )
    return documents


def best_sec_exhibit(documents: list[dict[str, str]]) -> dict[str, str] | None:
    scored = ranked_sec_exhibits(documents)
    if not scored:
        return None
    return scored[0][1]


def ranked_sec_exhibits(documents: list[dict[str, str]]) -> list[tuple[int, dict[str, str]]]:
    scored: list[tuple[int, dict[str, str]]] = []
    for document in documents:
        haystack = " ".join(str(document.get(key, "")) for key in ("type", "filename", "description")).lower()
        score = 0
        if "ex-99.1" in haystack or "ex99.1" in haystack or "99.1" in haystack:
            score += 80
        if "ex-99.2" in haystack or "ex99.2" in haystack or "99.2" in haystack:
            score += 70
        for keyword in ("earnings", "financial results", "press release", "shareholder letter", "investor presentation", "presentation"):
            if keyword in haystack:
                score += 12
        if document.get("filename", "").lower().endswith((".htm", ".html", ".txt")):
            score += 3
        if document.get("filename", "").lower().endswith(".pdf"):
            score += 2
        if score >= 70:
            scored.append((score, document))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


def extract_sec_document_text(document: dict[str, str]) -> tuple[str, str | None]:
    filename = document.get("filename", "").lower()
    url = document.get("url", "")
    if filename.endswith(".pdf") or url.lower().endswith(".pdf"):
        try:
            return _extract_pdf_text(_fetch_bytes(url, sec=True, max_bytes=12_000_000)), None
        except EarningsAgentSourceError as exc:
            return "", str(exc)
    text = document.get("text", "")
    if "<html" in text.lower() or re.search(r"<[a-z][\s>/]", text, flags=re.IGNORECASE):
        return _html_to_text(text), None
    return _compact_text(text), None


def best_motley_link(index_html: str, company: EarningsCompany) -> dict[str, str] | None:
    candidates: list[tuple[int, dict[str, str]]] = []
    ticker = company.ticker.upper()
    company_tokens = [token for token in _company_key(company.company_name).split() if len(token) > 3]
    for match in re.finditer(r"<a[^>]+href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>", index_html, flags=re.IGNORECASE | re.DOTALL):
        href = unescape(match.group("href"))
        label = _compact_text(_html_to_text(match.group("label")))
        haystack = f"{href} {label}".upper()
        if "/earnings/call-transcripts/" not in href:
            continue
        score = 0
        if ticker in haystack:
            score += 80
        if "EARNINGS" in haystack and "TRANSCRIPT" in haystack:
            score += 20
        for token in company_tokens[:3]:
            if token.upper() in haystack:
                score += 10
        if score >= 80:
            candidates.append((score, {"href": href, "title": label or f"{ticker} earnings call transcript"}))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def company_ir_candidate_pages(company: EarningsCompany) -> list[str]:
    candidates: list[str] = []
    known = KNOWN_IR_URLS.get(company.ticker.upper())
    if known:
        base = known.rstrip("/")
        candidates.extend([known, f"{base}/events-and-presentations", f"{base}/financials", f"{base}/news"])
        return _unique_urls(candidates)[:8]
    website = _company_website(company.ticker)
    if website:
        base = website.rstrip("/")
        candidates.extend(
            [
                base,
                f"{base}/investor-relations",
                f"{base}/investors",
                f"{base}/investor",
                f"{base}/ir",
                f"{base}/news-and-events",
            ]
        )
    return _unique_urls(candidates)[:8]


def best_company_ir_links(html: str, base_url: str, company: EarningsCompany) -> list[dict[str, str]]:
    candidates: list[tuple[int, dict[str, str]]] = []
    company_tokens = [token for token in _company_key(company.company_name).split() if len(token) > 3]
    for match in re.finditer(r"<a[^>]+href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>", html, flags=re.IGNORECASE | re.DOTALL):
        href = unescape(match.group("href")).strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(base_url, href)
        label = _compact_text(_html_to_text(match.group("label")))
        haystack = f"{url} {label}".lower()
        score = 0
        for keyword in ("earnings", "results", "quarter", "quarterly", "q1", "q2", "q3", "q4", "fiscal"):
            if keyword in haystack:
                score += 12
        if "presentation" in haystack or "slides" in haystack or "deck" in haystack:
            score += 34
        if "transcript" in haystack or "call" in haystack:
            score += 28
        if "webcast" in haystack:
            score += 16
        if ".pdf" in haystack:
            score += 16
        for token in company_tokens[:3]:
            if token in haystack:
                score += 5
        if score < 40:
            continue
        document_type = "company earnings call transcript" if "transcript" in haystack else "company investor presentation"
        candidates.append((score, {"url": url, "title": label or f"{company.ticker} investor relations material", "document_type": document_type}))
    candidates.sort(key=lambda item: item[0], reverse=True)
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for _, item in candidates:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        deduped.append(item)
        if len(deduped) >= 5:
            break
    return deduped


def extract_public_document_url(url: str) -> tuple[str, str | None]:
    try:
        payload = _fetch_bytes(url, sec=False, max_bytes=12_000_000)
    except EarningsAgentSourceError as exc:
        return "", str(exc)
    if url.lower().split("?", 1)[0].endswith(".pdf") or payload[:5] == b"%PDF-":
        try:
            return _extract_pdf_text(payload), None
        except EarningsAgentSourceError as exc:
            return "", str(exc)
    return _compact_text(_html_to_text(payload.decode("utf-8", errors="replace"))), None


def _company_ticker_records() -> list[dict[str, Any]]:
    payload = _fetch_json(SEC_COMPANY_TICKERS_URL, sec=True)
    if isinstance(payload, dict):
        records = list(payload.values())
    elif isinstance(payload, list):
        records = payload
    else:
        records = []
    return [record for record in records if isinstance(record, dict) and record.get("ticker")]


def _resolve_record_by_ticker(symbol: str, records: list[dict[str, Any]]) -> EarningsCompany | None:
    ticker = _ticker_token(symbol)
    for record in records:
        if _ticker_token(str(record.get("ticker", ""))) == ticker:
            return EarningsCompany(
                ticker=str(record["ticker"]).upper(),
                company_name=str(record.get("title") or record["ticker"]),
                cik=_normalize_cik(record.get("cik_str")),
            )
    return None


def _source_status(sources: list[EarningsSource]) -> str:
    text_sources = [source for source in sources if source.text.strip()]
    has_filing_or_presentation = any(
        source.source_type in {"sec", "sec_presentation", "company_ir"} and (source.status == "found" or source.text.strip())
        for source in sources
    )
    has_transcript = any(
        "transcript" in (source.document_type or "").lower() and source.text.strip()
        for source in sources
    )
    if has_filing_or_presentation and has_transcript:
        return "complete"
    if text_sources or any(source.status == "found" for source in sources):
        return "partial"
    return "missing"


def _sec_document_role(document: dict[str, str]) -> str:
    haystack = " ".join(str(document.get(key, "")) for key in ("type", "filename", "description")).lower()
    if "presentation" in haystack or "slides" in haystack or "deck" in haystack:
        return "presentation"
    if "shareholder letter" in haystack or "letter" in haystack:
        return "shareholder_letter"
    if "transcript" in haystack:
        return "transcript"
    return "release"


def _looks_like_earnings_material(text: str) -> bool:
    lowered = text.lower()
    if len(lowered) < 900:
        return False
    keyword_count = sum(
        1
        for keyword in ("earnings", "quarter", "revenue", "net income", "eps", "guidance", "conference call", "financial results")
        if keyword in lowered
    )
    return keyword_count >= 3


def _company_website(symbol: str) -> str | None:
    try:
        import yfinance as yf

        info = yf.Ticker(symbol).get_info()
    except Exception:
        return None
    if not isinstance(info, dict):
        return None
    for key in ("irWebsite", "website"):
        value = str(info.get(key) or "").strip()
        if value.startswith(("http://", "https://")):
            return value
    return None


def _unique_urls(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = value.strip().rstrip("/")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(value.strip())
    return output


def _fetch_json(url: str, *, sec: bool) -> Any:
    text = _fetch_text(url, sec=sec, max_bytes=4_000_000)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise EarningsAgentSourceError(f"Invalid JSON from {url}") from exc


def _fetch_text(url: str, *, sec: bool, max_bytes: int = 2_000_000) -> str:
    return _fetch_bytes(url, sec=sec, max_bytes=max_bytes).decode("utf-8", errors="replace")


def _fetch_sec_submission_text(folder_url: str, accession: str) -> tuple[str, str]:
    urls = [
        f"{folder_url}/{accession}.txt",
        f"{folder_url}/{accession.replace('-', '')}.txt",
    ]
    last_error: EarningsAgentSourceError | None = None
    for url in urls:
        try:
            return _fetch_text(url, sec=True, max_bytes=8_000_000), url
        except EarningsAgentSourceError as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise EarningsAgentSourceError(f"SEC submission text was not available for {accession}.")


def _fetch_bytes(url: str, *, sec: bool, max_bytes: int = 2_000_000) -> bytes:
    headers = {
        "User-Agent": get_settings().sec_user_agent if sec else "FinanceOS earnings research contact@example.com",
        "Accept-Encoding": "identity",
    }
    if not sec:
        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=20, context=_ssl_context()) as response:  # noqa: S310
            return response.read(max_bytes + 1)[:max_bytes]
    except HTTPError as exc:
        raise EarningsAgentSourceError(f"{url} returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise EarningsAgentSourceError(f"{url} could not be reached") from exc
    except TimeoutError as exc:
        raise EarningsAgentSourceError(f"{url} timed out") from exc


def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


def _extract_pdf_text(payload: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise EarningsAgentSourceError("pypdf is not installed, so SEC PDF text could not be parsed.") from exc
    try:
        reader = PdfReader(BytesIO(payload))
        pages = [page.extract_text() or "" for page in reader.pages[:30]]
    except Exception as exc:  # pragma: no cover - pypdf raises library-specific errors across versions.
        raise EarningsAgentSourceError("SEC PDF text could not be parsed.") from exc
    return _compact_text("\n".join(pages))


def _sec_archive_folder(cik: str, accession: str) -> str:
    return f"{SEC_ARCHIVES_BASE}/{str(int(cik))}/{accession.replace('-', '')}"


def _normalize_cik(value: object) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    if not digits:
        return None
    return digits.zfill(10)


def _ticker_token(value: str) -> str:
    return re.sub(r"[^A-Z0-9.]", "", value.upper().replace("-", "."))


def _company_key(value: str) -> str:
    return " ".join(
        token
        for token in re.sub(r"[^a-z0-9 ]", " ", value.lower()).split()
        if token not in {"inc", "corp", "corporation", "company", "co", "class", "plc", "ltd", "the"}
    )


def _date_from_value(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _source_title(company: EarningsCompany, provider: str, description: object, filing_date: date | None) -> str:
    suffix = f" ({filing_date.isoformat()})" if filing_date else ""
    descriptor = str(description or "earnings exhibit").strip()
    return f"{company.ticker} {provider} {descriptor}{suffix}"


def _sec_tag(block: str, tag: str) -> str:
    match = re.search(rf"<{tag}>\s*([^\r\n<]*)", block, flags=re.IGNORECASE)
    return _compact_text(match.group(1)) if match else ""


def _sec_text_body(block: str) -> str:
    match = re.search(r"<TEXT>\s*(.*?)\s*</TEXT>", block, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _html_to_text(value: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", value)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|tr|h[1-6]|section|article)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return _compact_text(unescape(text))


def _compact_text(value: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.replace("\xa0", " ").splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _excerpt(value: str) -> str:
    return value[:MAX_EXCERPT_CHARS].strip()


def _json_from_response(response_text: str) -> Any:
    text = response_text.strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


def _list_value(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _string_list(value: object) -> list[str]:
    return [str(item).strip() for item in _list_value(value) if str(item).strip()][:12]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
