from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import math
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import StockAnalysisRun, utc_now
from app.services.ai_advisor import generate_text, response_usage
from app.services.earnings_agent import (
    EarningsAgentSourceError,
    EarningsAgentLookupError,
    EarningsCompany,
    EarningsSource,
    _fetch_json,
    _json_from_response,
    fetch_company_ir_sources,
    fetch_sec_earnings_sources,
    resolve_company,
)
from app.services.index_data import INDEX_DEFINITIONS
from app.services.market_data import get_latest_security_snapshots, normalize_symbol


MAX_PROMPT_CONTEXT_CHARS = 42_000
MAX_EARNINGS_SOURCE_CHARS = 8_000
SEC_COMPANYFACTS_BASE = "https://data.sec.gov/api/xbrl/companyfacts"

SEC_FACT_CONCEPTS = {
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet"),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets",
    ),
    "debt": ("DebtCurrent", "LongTermDebtCurrent", "LongTermDebt", "LongTermDebtNoncurrent"),
    "equity": ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    "cash": ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
}


class StockAnalysisLookupError(RuntimeError):
    pass


@dataclass(frozen=True)
class StockAnalysisCompany:
    ticker: str
    company_name: str
    cik: str | None = None


@dataclass
class StockAnalysisSource:
    source_type: str
    title: str
    status: str
    url: str | None = None
    document_type: str | None = None
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
            "excerpt": self.excerpt,
            "warning": self.warning,
        }


def run_stock_analysis(db: Session, user_id: int, query: str, model: str, api_key: str | None, ollama_base_url: str | None = None) -> StockAnalysisRun:
    company = resolve_stock_company(query)
    context = collect_stock_analysis_context(db, company)
    prompt_text = build_stock_analysis_prompt(company, context)
    response_text, response_payload = generate_text(
        model,
        prompt_text,
        api_key=api_key,
        ollama_base_url=ollama_base_url,
        instructions=(
            "You are an educational equity research assistant. Return strict JSON only. "
            "Do not provide personalized investment advice, buy/sell/hold recommendations, price targets, trade instructions, or allocation instructions."
        ),
    )
    digest = parse_stock_analysis_response(response_text)
    digest["research_stance"] = normalize_research_stance(digest.get("research_stance"))
    source_status = _source_status(context)
    run = StockAnalysisRun(
        user_id=user_id,
        query=query.strip(),
        ticker=company.ticker,
        company_name=str(context["profile"].get("company_name") or company.company_name),
        sector=_optional_str(context["profile"].get("sector")),
        industry=_optional_str(context["profile"].get("industry")),
        model=model,
        source_status=source_status,
        source_json=json.dumps([source.public_dict() for source in context["sources"]], separators=(",", ":"), sort_keys=True),
        financial_snapshot_json=json.dumps(context["snapshot"], separators=(",", ":"), sort_keys=True),
        digest_json=json.dumps(digest, separators=(",", ":"), sort_keys=True),
        warnings_json=json.dumps(_unique(context["warnings"]), separators=(",", ":"), sort_keys=True),
        prompt_text=build_stored_prompt_snapshot(company, context),
        response_text=response_text,
        usage_json=json.dumps(response_usage(response_payload), separators=(",", ":"), sort_keys=True),
        created_at=utc_now(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def resolve_stock_company(query: str) -> StockAnalysisCompany:
    try:
        company = resolve_company(query)
        return StockAnalysisCompany(company.ticker, company.company_name, company.cik)
    except EarningsAgentLookupError as exc:
        cleaned = " ".join(query.strip().split())
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9.\-]{0,9}", cleaned):
            ticker = cleaned.upper().replace("-", ".")
            return StockAnalysisCompany(ticker, ticker)
        raise StockAnalysisLookupError(str(exc)) from exc


def collect_stock_analysis_context(db: Session, company: StockAnalysisCompany) -> dict[str, Any]:
    warnings: list[str] = []
    info = _fetch_yfinance_info(company.ticker)
    if not info:
        warnings.append(f"yfinance profile data was unavailable for {company.ticker}.")

    market_snapshot = _market_snapshot(db, company.ticker, warnings)
    financial_warnings: list[str] = []
    financials = fetch_yfinance_financials(company.ticker, financial_warnings)
    sec_snapshot = fetch_sec_companyfacts_snapshot(company.cik, warnings) if company.cik else {"financials": [], "profile_metrics": {}}
    if not financials and sec_snapshot["financials"]:
        financials = sec_snapshot["financials"]
        warnings.append("Financial rows were sourced from SEC Company Facts because yfinance annual statements were unavailable.")
    elif financial_warnings:
        warnings.extend(financial_warnings)
    sec_profile_metrics = sec_snapshot["profile_metrics"] if isinstance(sec_snapshot["profile_metrics"], dict) else {}

    company_name = _info_str(info, "longName", "shortName") or company.company_name
    sector = _info_str(info, "sector") or _reference_field(company.ticker, "sector")
    industry = _info_str(info, "industry")
    current_price = _info_number(info, "currentPrice", "regularMarketPrice", "previousClose")
    if current_price is None and market_snapshot:
        current_price = market_snapshot.price
    shares_outstanding = _info_number(info, "sharesOutstanding", "impliedSharesOutstanding") or _safe_number(sec_profile_metrics.get("shares_outstanding"))
    market_cap = _info_number(info, "marketCap")
    if market_cap is None and current_price and shares_outstanding:
        market_cap = current_price * shares_outstanding

    peers = build_peer_comparisons(company.ticker, sector, industry, warnings, allow_live_profile=bool(info))
    profile = {
        "ticker": company.ticker,
        "company_name": company_name,
        "sector": sector,
        "industry": industry,
        "business_summary": _info_str(info, "longBusinessSummary"),
        "market_cap": market_cap,
        "current_price": current_price,
        "currency": _info_str(info, "currency") or "USD",
        "trailing_pe": _info_number(info, "trailingPE"),
        "forward_pe": _info_number(info, "forwardPE") or (market_snapshot.forward_pe if market_snapshot else None),
        "price_to_sales": _info_number(info, "priceToSalesTrailing12Months"),
        "enterprise_to_ebitda": _info_number(info, "enterpriseToEbitda"),
        "beta": _info_number(info, "beta"),
        "revenue_growth": _info_number(info, "revenueGrowth"),
        "gross_margin": _info_number(info, "grossMargins"),
        "operating_margin": _info_number(info, "operatingMargins"),
        "profit_margin": _info_number(info, "profitMargins"),
        "return_on_equity": _info_number(info, "returnOnEquity"),
        "total_debt": _info_number(info, "totalDebt") or _safe_number(sec_profile_metrics.get("total_debt")),
        "total_cash": _info_number(info, "totalCash") or _safe_number(sec_profile_metrics.get("total_cash")),
        "shares_outstanding": shares_outstanding,
        "data_source": "yfinance profile + FinanceOS market cache",
    }
    valuation = build_valuation_snapshot(profile, financials, peers, warnings)
    sources = fetch_stock_earnings_sources(company, warnings)
    snapshot = {
        "profile": profile,
        "financials": financials,
        "valuation": valuation,
        "as_of_date": date.today().isoformat(),
    }
    return {
        "profile": profile,
        "financials": financials,
        "valuation": valuation,
        "sources": sources,
        "snapshot": snapshot,
        "warnings": warnings,
    }


def fetch_yfinance_financials(symbol: str, warnings: list[str] | None = None) -> list[dict[str, Any]]:
    warnings = warnings if warnings is not None else []
    try:
        import yfinance as yf
    except Exception:
        warnings.append("yfinance is not installed; five-year financials could not be fetched.")
        return []

    try:
        ticker = yf.Ticker(_provider_symbol(symbol))
        income = _first_statement(getattr(ticker, "income_stmt", None), getattr(ticker, "financials", None))
        cashflow = _first_statement(getattr(ticker, "cashflow", None))
        balance = _first_statement(getattr(ticker, "balance_sheet", None))
    except Exception as exc:
        warnings.append(f"yfinance financial statements could not be fetched for {symbol}: {exc}")
        return []

    rows = normalize_financial_statements(income, cashflow, balance)
    if not rows:
        warnings.append(f"No annual financial statement rows were available for {symbol}.")
    elif len(rows) < 5:
        warnings.append(f"Only {len(rows)} annual financial statement row(s) were available for {symbol}.")
    return rows


def fetch_sec_companyfacts_snapshot(cik: str | None, warnings: list[str] | None = None) -> dict[str, Any]:
    warnings = warnings if warnings is not None else []
    if not cik:
        return {"financials": [], "profile_metrics": {}}
    url = f"{SEC_COMPANYFACTS_BASE}/CIK{str(cik).zfill(10)}.json"
    try:
        payload = _fetch_json(url, sec=True)
    except EarningsAgentSourceError as exc:
        warnings.append(f"SEC Company Facts fallback was unavailable: {exc}")
        return {"financials": [], "profile_metrics": {}}
    financials = normalize_sec_companyfacts(payload)
    if not financials:
        warnings.append("SEC Company Facts did not include enough annual facts to build financial rows.")
    return {
        "financials": financials,
        "profile_metrics": {
            "shares_outstanding": _latest_sec_fact_value(payload, ("EntityCommonStockSharesOutstanding",), taxonomy="dei", unit="shares"),
            "total_cash": _latest_sec_fact_value(payload, SEC_FACT_CONCEPTS["cash"], taxonomy="us-gaap", unit="USD"),
            "total_debt": _latest_sec_total_debt(payload),
        },
    }


def normalize_sec_companyfacts(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    year_map: dict[int, dict[str, float | int | None]] = {}
    for metric, concepts in SEC_FACT_CONCEPTS.items():
        if metric in {"debt", "cash"}:
            continue
        values = _sec_metric_values(payload, concepts, unit="USD")
        for year, value in values.items():
            year_map.setdefault(year, {"year": year})[metric] = value
    debt_values = _sec_total_debt_by_year(payload)
    equity_values = _sec_metric_values(payload, SEC_FACT_CONCEPTS["equity"], unit="USD")
    for year, value in debt_values.items():
        year_map.setdefault(year, {"year": year})["debt"] = value
    for year, value in equity_values.items():
        year_map.setdefault(year, {"year": year})["equity"] = value

    recent_years = sorted(year_map.keys(), reverse=True)[:5]
    rows: list[dict[str, Any]] = []
    previous_revenue: float | None = None
    for year in sorted(recent_years):
        item = year_map[year]
        revenue = _safe_number(item.get("revenue"))
        gross_profit = _safe_number(item.get("gross_profit"))
        operating_income = _safe_number(item.get("operating_income"))
        net_income = _safe_number(item.get("net_income"))
        operating_cash_flow = _safe_number(item.get("operating_cash_flow"))
        capex = _safe_number(item.get("capex"))
        free_cash_flow = None
        if operating_cash_flow is not None and capex is not None:
            free_cash_flow = operating_cash_flow - abs(capex)
        equity = _safe_number(item.get("equity"))
        revenue_growth = None
        if revenue is not None and previous_revenue and previous_revenue > 0:
            revenue_growth = (revenue / previous_revenue) - 1
        row = {
            "year": year,
            "revenue": revenue,
            "revenue_growth": revenue_growth,
            "net_income": net_income,
            "free_cash_flow": free_cash_flow,
            "gross_margin": _ratio(gross_profit, revenue),
            "operating_margin": _ratio(operating_income, revenue),
            "profit_margin": _ratio(net_income, revenue),
            "debt": _safe_number(item.get("debt")),
            "roe": _ratio(net_income, equity),
        }
        if any(value is not None for key, value in row.items() if key != "year"):
            rows.append(row)
        if revenue is not None:
            previous_revenue = revenue
    return rows


def normalize_financial_statements(income: object, cashflow: object, balance: object) -> list[dict[str, Any]]:
    year_columns = _year_columns(income) | _year_columns(cashflow) | _year_columns(balance)
    recent_years = sorted(year_columns.keys(), reverse=True)[:5]
    rows: list[dict[str, Any]] = []
    previous_revenue: float | None = None
    for year in sorted(recent_years):
        revenue = _statement_value(income, year, ["Total Revenue", "Operating Revenue", "Revenue"])
        gross_profit = _statement_value(income, year, ["Gross Profit"])
        operating_income = _statement_value(income, year, ["Operating Income", "Operating Income Or Loss"])
        net_income = _statement_value(income, year, ["Net Income", "Net Income Common Stockholders"])
        operating_cash_flow = _statement_value(cashflow, year, ["Operating Cash Flow", "Total Cash From Operating Activities"])
        capital_expenditure = _statement_value(cashflow, year, ["Capital Expenditure", "Capital Expenditures"])
        free_cash_flow = _statement_value(cashflow, year, ["Free Cash Flow"])
        if free_cash_flow is None and operating_cash_flow is not None and capital_expenditure is not None:
            free_cash_flow = operating_cash_flow + capital_expenditure
        debt = _statement_value(balance, year, ["Total Debt"])
        if debt is None:
            long_debt = _statement_value(balance, year, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"]) or 0
            current_debt = _statement_value(balance, year, ["Current Debt", "Current Debt And Capital Lease Obligation"]) or 0
            debt = long_debt + current_debt if long_debt or current_debt else None
        equity = _statement_value(balance, year, ["Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"])
        revenue_growth = None
        if revenue is not None and previous_revenue and previous_revenue > 0:
            revenue_growth = (revenue / previous_revenue) - 1
        row = {
            "year": year,
            "revenue": revenue,
            "revenue_growth": revenue_growth,
            "net_income": net_income,
            "free_cash_flow": free_cash_flow,
            "gross_margin": _ratio(gross_profit, revenue),
            "operating_margin": _ratio(operating_income, revenue),
            "profit_margin": _ratio(net_income, revenue),
            "debt": debt,
            "roe": _ratio(net_income, equity),
        }
        if any(value is not None for key, value in row.items() if key != "year"):
            rows.append(row)
        if revenue is not None:
            previous_revenue = revenue
    return rows


def build_peer_comparisons(
    symbol: str,
    sector: str | None,
    industry: str | None,
    warnings: list[str] | None = None,
    *,
    allow_live_profile: bool = True,
) -> list[dict[str, Any]]:
    del industry
    warnings = warnings if warnings is not None else []
    peer_symbols = peer_symbols_for_sector(symbol, sector)
    peers: list[dict[str, Any]] = []
    for peer_symbol in peer_symbols:
        info = _fetch_yfinance_info(peer_symbol) if allow_live_profile else {}
        reference_name = _reference_field(peer_symbol, "name") or peer_symbol
        peers.append(
            {
                "symbol": peer_symbol,
                "company_name": _info_str(info, "shortName", "longName") or reference_name,
                "sector": _info_str(info, "sector") or _reference_field(peer_symbol, "sector"),
                "industry": _info_str(info, "industry"),
                "forward_pe": _info_number(info, "forwardPE"),
                "trailing_pe": _info_number(info, "trailingPE"),
                "price_to_sales": _info_number(info, "priceToSalesTrailing12Months"),
                "profit_margin": _info_number(info, "profitMargins"),
            }
        )
    if not peers:
        warnings.append("Peer comparison was limited because FinanceOS could not identify same-sector index peers.")
    return peers


def peer_symbols_for_sector(symbol: str, sector: str | None, limit: int = 5) -> list[str]:
    normalized = normalize_symbol(symbol)
    effective_sector = sector or _reference_field(normalized, "sector")
    candidates: list[tuple[float, str]] = []
    seen: set[str] = set()
    for definition in INDEX_DEFINITIONS.values():
        for holding in definition.holdings:
            peer_symbol = normalize_symbol(str(holding.get("symbol", "")))
            if not peer_symbol or peer_symbol == normalized or peer_symbol in seen:
                continue
            if effective_sector and str(holding.get("sector") or "") != effective_sector:
                continue
            seen.add(peer_symbol)
            candidates.append((float(holding.get("weight") or 0), peer_symbol))
    candidates.sort(reverse=True)
    return [candidate[1] for candidate in candidates[:limit]]


def build_valuation_snapshot(
    profile: dict[str, Any],
    financials: list[dict[str, Any]],
    peers: list[dict[str, Any]],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    warnings = warnings if warnings is not None else []
    peer_forward_pes = [float(peer["forward_pe"]) for peer in peers if _safe_number(peer.get("forward_pe"))]
    peer_average_forward_pe = round(sum(peer_forward_pes) / len(peer_forward_pes), 2) if peer_forward_pes else None
    dcf = build_dcf_estimate(profile, financials)
    if dcf.get("warning"):
        warnings.append(str(dcf["warning"]))
    return {
        "current_price": profile.get("current_price"),
        "market_cap": profile.get("market_cap"),
        "trailing_pe": profile.get("trailing_pe"),
        "forward_pe": profile.get("forward_pe"),
        "price_to_sales": profile.get("price_to_sales"),
        "enterprise_to_ebitda": profile.get("enterprise_to_ebitda"),
        "industry_average_forward_pe": peer_average_forward_pe,
        "peer_average_forward_pe": peer_average_forward_pe,
        "dcf": dcf,
        "peers": peers,
    }


def build_dcf_estimate(profile: dict[str, Any], financials: list[dict[str, Any]]) -> dict[str, Any]:
    discount_rate = 0.10
    terminal_growth_rate = 0.03
    base_fcf = next((row.get("free_cash_flow") for row in reversed(financials) if _safe_number(row.get("free_cash_flow"))), None)
    shares = _safe_number(profile.get("shares_outstanding"))
    if not _safe_number(base_fcf) or not shares or shares <= 0:
        return {
            "fair_value_per_share": None,
            "upside_downside_pct": None,
            "base_free_cash_flow": _safe_number(base_fcf),
            "growth_rate": None,
            "discount_rate": discount_rate,
            "terminal_growth_rate": terminal_growth_rate,
            "warning": "DCF estimate requires free cash flow and shares outstanding; one or both were unavailable.",
        }
    revenue_cagr = _revenue_cagr(financials)
    growth_rate = revenue_cagr if revenue_cagr is not None else _safe_number(profile.get("revenue_growth"))
    growth_rate = _clamp(growth_rate if growth_rate is not None else 0.03, -0.02, 0.12)
    projected_fcf = float(base_fcf)
    present_value = 0.0
    for year in range(1, 6):
        projected_fcf *= 1 + growth_rate
        present_value += projected_fcf / ((1 + discount_rate) ** year)
    terminal_value = projected_fcf * (1 + terminal_growth_rate) / (discount_rate - terminal_growth_rate)
    present_value += terminal_value / ((1 + discount_rate) ** 5)
    total_cash = _safe_number(profile.get("total_cash")) or 0
    total_debt = _safe_number(profile.get("total_debt"))
    if total_debt is None:
        total_debt = next((row.get("debt") for row in reversed(financials) if _safe_number(row.get("debt"))), 0) or 0
    equity_value = present_value + total_cash - float(total_debt)
    fair_value = equity_value / shares
    current_price = _safe_number(profile.get("current_price"))
    upside = (fair_value / current_price - 1) if current_price and current_price > 0 else None
    return {
        "fair_value_per_share": round(fair_value, 2) if math.isfinite(fair_value) and fair_value > 0 else None,
        "upside_downside_pct": round(upside, 4) if upside is not None and math.isfinite(upside) else None,
        "base_free_cash_flow": round(float(base_fcf), 2),
        "growth_rate": round(growth_rate, 4),
        "discount_rate": discount_rate,
        "terminal_growth_rate": terminal_growth_rate,
        "warning": None,
    }


def fetch_stock_earnings_sources(company: StockAnalysisCompany, warnings: list[str] | None = None) -> list[StockAnalysisSource]:
    warnings = warnings if warnings is not None else []
    earnings_company = EarningsCompany(company.ticker, company.company_name, company.cik)
    sources: list[EarningsSource] = []
    try:
        sources.extend(fetch_sec_earnings_sources(earnings_company))
    except Exception as exc:
        warnings.append(f"SEC earnings context was unavailable: {exc}")
    existing_urls = {source.url for source in sources if source.url}
    try:
        sources.extend(fetch_company_ir_sources(earnings_company, existing_urls=existing_urls))
    except Exception as exc:
        warnings.append(f"Company investor-relations context was unavailable: {exc}")
    return [
        StockAnalysisSource(
            source_type=source.source_type,
            title=source.title,
            status=source.status,
            url=source.url,
            document_type=source.document_type,
            excerpt=source.excerpt,
            warning=source.warning,
            text=source.text,
        )
        for source in sources[:5]
    ]


def build_stock_analysis_prompt(company: StockAnalysisCompany, context: dict[str, Any]) -> str:
    source_blocks = []
    for source in context["sources"]:
        if not source.text.strip():
            continue
        source_blocks.append(
            "\n".join(
                [
                    f"Source: {source.source_type.upper()} | {source.title}",
                    f"Document type: {source.document_type or 'unknown'}",
                    f"URL: {source.url or 'unavailable'}",
                    "Text:",
                    source.text[:MAX_EARNINGS_SOURCE_CHARS],
                ]
            )
        )
    source_text = "\n\n---\n\n".join(source_blocks) or "No recent earnings source text was available; use only structured financial data for earnings-related sections and state gaps."
    structured_context = json.dumps(context["snapshot"], indent=2, sort_keys=True)
    prompt = f"""Create an educational Wall Street-style equity research analysis for {company.company_name} ({company.ticker}).

Use the structured FinanceOS data and source text below. If a metric or section is not supported by the supplied data, say it is unavailable instead of fabricating it.

Return strict JSON with exactly these keys:
{{
  "executive_summary": "3-5 sentence neutral summary",
  "business_model": "Business model and revenue streams",
  "moat_summary": "Competitive advantage assessment",
  "moat_score": 1,
  "competitor_comparison": ["comparison point"],
  "industry_trends": ["trend 1", "trend 2"],
  "financial_health": "5-year financial health read, including strengthening or weakening",
  "valuation_summary": "P/E, DCF, peer comparison, and valuation conclusion using research language only",
  "risks": [{{"rank": 1, "title": "Risk", "detail": "why it matters", "severity": "high"}}],
  "growth_potential": "5-10 year growth potential with drivers and constraints",
  "institutional_perspective": "Why institutions might research it further or avoid it",
  "scenarios": [{{"case": "bull", "summary": "scenario", "key_drivers": ["driver"]}}, {{"case": "base", "summary": "scenario", "key_drivers": ["driver"]}}, {{"case": "bear", "summary": "scenario", "key_drivers": ["driver"]}}],
  "bull_bear_debate": ["Bull analyst: data-backed argument", "Bear analyst: data-backed argument", "Balanced conclusion"],
  "latest_earnings": "Latest earnings breakdown from supplied data/source text, including gaps",
  "outlook_12_24_months": "12-24 month educational outlook",
  "research_stance": "Attractive for research | Neutral / monitor | Avoid-for-now for research",
  "deep_dive_questions": ["question 1", "question 2"],
  "source_notes": ["data sources and caveats"]
}}

Rules:
- Educational research only.
- Do not use buy, sell, hold, price target, rating, trade, or allocation instructions.
- The final stance must be one of: Attractive for research, Neutral / monitor, Avoid-for-now for research.
- Use the DCF as a model estimate, not as a price target.
- Rank risks from most dangerous to least dangerous.
- Prefer concrete metrics from FinanceOS data over generic commentary.

FinanceOS structured data:
{structured_context}

Latest earnings/source text:
{source_text}
"""
    return prompt[:MAX_PROMPT_CONTEXT_CHARS]


def build_stored_prompt_snapshot(company: StockAnalysisCompany, context: dict[str, Any]) -> str:
    sources = []
    for source in context["sources"]:
        sources.append(
            {
                "source_type": source.source_type,
                "title": source.title,
                "status": source.status,
                "url": source.url,
                "document_type": source.document_type,
                "excerpt": source.excerpt,
                "warning": source.warning,
            }
        )
    return (
        f"Equity Research prompt snapshot for {company.company_name} ({company.ticker}).\n\n"
        "Full source text was sent transiently to the LLM when available. This stored snapshot keeps structured market data, "
        "financial metrics, source metadata, and short provenance excerpts.\n\n"
        f"{json.dumps({'snapshot': context['snapshot'], 'sources': sources}, indent=2, sort_keys=True)}"
    )


def parse_stock_analysis_response(response_text: str) -> dict[str, Any]:
    payload = _json_from_response(response_text)
    if not isinstance(payload, dict):
        return {
            "executive_summary": response_text.strip(),
            "business_model": "",
            "moat_summary": "",
            "moat_score": None,
            "competitor_comparison": [],
            "industry_trends": [],
            "financial_health": "",
            "valuation_summary": "",
            "risks": [],
            "growth_potential": "",
            "institutional_perspective": "",
            "scenarios": [],
            "bull_bear_debate": [],
            "latest_earnings": "",
            "outlook_12_24_months": "",
            "research_stance": "Neutral / monitor",
            "deep_dive_questions": [],
            "source_notes": ["LLM response was not valid JSON; showing the raw response as markdown."],
            "raw_markdown": response_text.strip(),
        }
    return {
        "executive_summary": _clean_text(payload.get("executive_summary")),
        "business_model": _clean_text(payload.get("business_model")),
        "moat_summary": _clean_text(payload.get("moat_summary")),
        "moat_score": _moat_score(payload.get("moat_score")),
        "competitor_comparison": _string_list(payload.get("competitor_comparison")),
        "industry_trends": _string_list(payload.get("industry_trends")),
        "financial_health": _clean_text(payload.get("financial_health")),
        "valuation_summary": _clean_text(payload.get("valuation_summary")),
        "risks": _risk_list(payload.get("risks")),
        "growth_potential": _clean_text(payload.get("growth_potential")),
        "institutional_perspective": _clean_text(payload.get("institutional_perspective")),
        "scenarios": _scenario_list(payload.get("scenarios")),
        "bull_bear_debate": _string_list(payload.get("bull_bear_debate")),
        "latest_earnings": _clean_text(payload.get("latest_earnings")),
        "outlook_12_24_months": _clean_text(payload.get("outlook_12_24_months")),
        "research_stance": normalize_research_stance(payload.get("research_stance")),
        "deep_dive_questions": _string_list(payload.get("deep_dive_questions")),
        "source_notes": _string_list(payload.get("source_notes")),
        "raw_markdown": None,
    }


def normalize_research_stance(value: object) -> str:
    text = str(value or "").strip().lower()
    if any(token in text for token in ("avoid", "sell", "weaken", "unattractive")):
        return "Avoid-for-now for research"
    if any(token in text for token in ("attractive", "positive", "bull", "outperform", "buy")):
        return "Attractive for research"
    return "Neutral / monitor"


def _fetch_yfinance_info(symbol: str) -> dict[str, Any]:
    try:
        import yfinance as yf
    except Exception:
        return {}
    try:
        info = yf.Ticker(_provider_symbol(symbol)).get_info()
        return info if isinstance(info, dict) else {}
    except Exception:
        return {}


def _market_snapshot(db: Session, symbol: str, warnings: list[str]) -> Any:
    try:
        snapshot = get_latest_security_snapshots(db, [symbol], date.today()).get(normalize_symbol(symbol))
    except Exception as exc:
        warnings.append(f"FinanceOS market snapshot was unavailable for {symbol}: {exc}")
        return None
    if snapshot and snapshot.warning:
        warnings.append(snapshot.warning)
    return snapshot


def _source_status(context: dict[str, Any]) -> str:
    has_financials = len(context["financials"]) >= 3
    has_profile = bool(context["profile"].get("company_name")) and bool(context["profile"].get("current_price"))
    has_source = any(source.status == "found" and source.text.strip() for source in context["sources"])
    if has_financials and has_profile and has_source:
        return "complete"
    if has_financials or has_profile or has_source:
        return "partial"
    return "missing"


def _provider_symbol(symbol: str) -> str:
    return normalize_symbol(symbol).replace(".", "-")


def _first_statement(*statements: object) -> object | None:
    for statement in statements:
        if statement is not None and not getattr(statement, "empty", False):
            return statement
    return None


def _year_columns(statement: object) -> dict[int, object]:
    if statement is None:
        return {}
    columns = getattr(statement, "columns", [])
    result: dict[int, object] = {}
    for column in columns:
        year = _column_year(column)
        if year and year not in result:
            result[year] = column
    return result


def _column_year(column: object) -> int | None:
    year = getattr(column, "year", None)
    if isinstance(year, int):
        return year
    match = re.search(r"(20\d{2}|19\d{2})", str(column))
    return int(match.group(1)) if match else None


def _statement_value(statement: object, year: int, names: list[str]) -> float | None:
    if statement is None:
        return None
    columns = _year_columns(statement)
    column = columns.get(year)
    if column is None:
        return None
    index = [str(item) for item in getattr(statement, "index", [])]
    lower_index = {item.lower(): item for item in index}
    for name in names:
        row_name = name if name in index else lower_index.get(name.lower())
        if not row_name:
            continue
        try:
            return _safe_number(statement.loc[row_name, column])
        except Exception:
            continue
    return None


def _sec_metric_values(payload: dict[str, Any], concepts: tuple[str, ...], *, unit: str) -> dict[int, float]:
    values: dict[int, tuple[str, float]] = {}
    for concept in concepts:
        for item in _sec_fact_items(payload, concept, taxonomy="us-gaap", unit=unit):
            year = _sec_fact_year(item)
            value = _safe_number(item.get("val"))
            filed = str(item.get("filed") or "")
            if year is None or value is None:
                continue
            existing = values.get(year)
            if existing is None or filed >= existing[0]:
                values[year] = (filed, value)
    return {year: value for year, (_, value) in values.items()}


def _sec_total_debt_by_year(payload: dict[str, Any]) -> dict[int, float]:
    total_debt = _sec_metric_values(payload, ("DebtCurrent", "LongTermDebtCurrent", "LongTermDebt", "LongTermDebtNoncurrent"), unit="USD")
    current = _sec_metric_values(payload, ("DebtCurrent", "LongTermDebtCurrent"), unit="USD")
    noncurrent = _sec_metric_values(payload, ("LongTermDebt", "LongTermDebtNoncurrent"), unit="USD")
    years = set(total_debt) | set(current) | set(noncurrent)
    output: dict[int, float] = {}
    for year in years:
        if current.get(year) is not None or noncurrent.get(year) is not None:
            output[year] = float(current.get(year) or 0) + float(noncurrent.get(year) or 0)
        elif total_debt.get(year) is not None:
            output[year] = total_debt[year]
    return output


def _latest_sec_total_debt(payload: dict[str, Any]) -> float | None:
    values = _sec_total_debt_by_year(payload)
    if not values:
        return None
    return values[max(values)]


def _latest_sec_fact_value(
    payload: dict[str, Any],
    concepts: tuple[str, ...],
    *,
    taxonomy: str,
    unit: str,
) -> float | None:
    values: list[tuple[str, int, float]] = []
    for concept in concepts:
        for item in _sec_fact_items(payload, concept, taxonomy=taxonomy, unit=unit):
            year = _sec_fact_year(item)
            value = _safe_number(item.get("val"))
            filed = str(item.get("filed") or "")
            if year is not None and value is not None:
                values.append((filed, year, value))
    if not values:
        return None
    values.sort(key=lambda item: (item[1], item[0]))
    return values[-1][2]


def _sec_fact_items(payload: dict[str, Any], concept: str, *, taxonomy: str, unit: str) -> list[dict[str, Any]]:
    fact = ((payload.get("facts") or {}).get(taxonomy) or {}).get(concept)
    if not isinstance(fact, dict):
        return []
    unit_values = (fact.get("units") or {}).get(unit) or []
    if not isinstance(unit_values, list):
        return []
    return [
        item
        for item in unit_values
        if isinstance(item, dict)
        and str(item.get("form") or "").upper() in {"10-K", "10-K/A"}
        and str(item.get("fp") or "").upper() == "FY"
    ]


def _sec_fact_year(item: dict[str, Any]) -> int | None:
    frame = str(item.get("frame") or "")
    frame_match = re.search(r"CY(\d{4})", frame)
    if frame_match:
        return int(frame_match.group(1))
    end = str(item.get("end") or "")
    end_match = re.match(r"(\d{4})-", end)
    if end_match:
        return int(end_match.group(1))
    fy = item.get("fy")
    if isinstance(fy, int):
        return fy
    if isinstance(fy, str) and fy.isdigit():
        return int(fy)
    return None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(numerator / denominator, 6)


def _safe_number(value: object) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _info_number(info: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        number = _safe_number(info.get(key))
        if number is not None:
            return number
    return None


def _info_str(info: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = info.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _optional_str(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _reference_field(symbol: str, field: str) -> str | None:
    normalized = normalize_symbol(symbol)
    for definition in INDEX_DEFINITIONS.values():
        for holding in definition.holdings:
            if normalize_symbol(str(holding.get("symbol", ""))) == normalized:
                value = holding.get(field)
                return str(value) if value else None
    return None


def _revenue_cagr(financials: list[dict[str, Any]]) -> float | None:
    revenue_rows = [row for row in financials if _safe_number(row.get("revenue")) and row.get("revenue", 0) > 0]
    if len(revenue_rows) < 2:
        return None
    first = float(revenue_rows[0]["revenue"])
    last = float(revenue_rows[-1]["revenue"])
    periods = max(1, len(revenue_rows) - 1)
    return (last / first) ** (1 / periods) - 1


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        raw = value
    elif value in (None, ""):
        raw = []
    else:
        raw = [value]
    return [str(item).strip() for item in raw if str(item).strip()][:12]


def _moat_score(value: object) -> int | None:
    number = _safe_number(value)
    if number is None:
        return None
    return int(_clamp(round(number), 1, 10))


def _risk_list(value: object) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else []
    risks: list[dict[str, Any]] = []
    for index, item in enumerate(items[:10], start=1):
        if isinstance(item, dict):
            risks.append(
                {
                    "rank": int(_safe_number(item.get("rank")) or index),
                    "title": _clean_text(item.get("title")) or f"Risk {index}",
                    "detail": _clean_text(item.get("detail")),
                    "severity": _clean_text(item.get("severity")) or None,
                }
            )
        elif item:
            risks.append({"rank": index, "title": f"Risk {index}", "detail": str(item), "severity": None})
    return risks


def _scenario_list(value: object) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else []
    scenarios: list[dict[str, Any]] = []
    for item in items[:3]:
        if isinstance(item, dict):
            scenarios.append(
                {
                    "case": _clean_text(item.get("case")) or "base",
                    "summary": _clean_text(item.get("summary")),
                    "key_drivers": _string_list(item.get("key_drivers")),
                }
            )
    return scenarios


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
