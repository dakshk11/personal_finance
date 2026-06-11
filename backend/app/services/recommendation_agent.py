from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.schemas.common import RecommendationAgentRunRequest
from app.services.ai_advisor import generate_text, response_usage
from app.services.ai_advisor import NVIDIA_RECOMMENDATION_MODELS, is_nvidia_model, nvidia_model_name
from app.services.breakout_scanner import run_breakout_scan
from app.services.recommendation_model_router import RecommendationModelRouter
from app.services.smart_candles import run_smart_candle_scan
from app.services.stock_analysis import EQUITY_RESEARCH_JSON_SCHEMA_AND_RULES


RECOMMENDATION_AGENT_INSTRUCTIONS = (
    "You are FinanceOS Recommendation Agent, an educational market-research assistant. "
    "Use only the supplied scanner and enrichment data. Do not provide personalized "
    "investment advice, trade instructions, allocations, guarantees, or brokerage orders."
)
RECOMMENDATION_AGENT_OLLAMA_TIMEOUT_SECONDS = 420

RECOMMENDATION_MULTI_AGENT_RUBRIC = """
Multi-agent evaluation rubric:
- Director lens: develop a concise market thesis for each candidate, including market position, expected trend, technical and fundamental drivers, key opportunities, and key challenges.
- Quant lens: evaluate the supplied technical indicators, moving-average structure, RSI, Bollinger/volatility context, trend strength, momentum, volume participation, and probability/confidence-style evidence.
- Sentiment lens: when supplied data contains news, social, analyst, institutional, earnings, or narrative context, summarize sentiment direction, intensity, key themes, critical events, trend changes, and possible contrarian implications.
- Risk lens: assess drawdown risk, volatility, liquidity, market correlation, concentration overlap with the current portfolio, valuation/extension risk, and red flags that could weaken the idea.
- Execution-planning lens: discuss educational trade-parameter context only, such as possible entry/exit review zones, stop/target considerations, time horizon, and conditions that would invalidate the thesis. Do not generate brokerage orders, order types, share quantities, personalized position sizing, or buy/sell/hold instructions.
Use these lenses as internal decision criteria for ranking; the final answer must still follow the Recommendation Agent ranked_ideas schema.
""".strip()


@dataclass
class CandidateIdea:
    symbol: str
    source_agents: list[str] = field(default_factory=list)
    strategy_tags: list[str] = field(default_factory=list)
    scanner_scores: dict[str, float] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    tipranks: dict[str, Any] | None = None
    lunarcrush: dict[str, Any] | None = None

    def score(self) -> float:
        base = sum(self.scanner_scores.values())
        breadth_bonus = 12 * max(0, len(set(self.source_agents)) - 1)
        tag_bonus = min(10, len(set(self.strategy_tags)) * 2)
        return round(base + breadth_bonus + tag_bonus, 4)

    def merge(self, other: "CandidateIdea") -> None:
        self.source_agents = _unique([*self.source_agents, *other.source_agents])
        self.strategy_tags = _unique([*self.strategy_tags, *other.strategy_tags])
        self.evidence = _unique([*self.evidence, *other.evidence])[:12]
        self.warnings = _unique([*self.warnings, *other.warnings])[:8]
        self.scanner_scores.update(other.scanner_scores)
        self.context = {**self.context, **{k: v for k, v in other.context.items() if v is not None}}

    def as_payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "source_agents": self.source_agents,
            "strategy_tags": self.strategy_tags,
            "scanner_scores": self.scanner_scores,
            "aggregate_score": self.score(),
            "context": self.context,
            "evidence": self.evidence,
            "tipranks": self.tipranks,
            "lunarcrush": self.lunarcrush,
            "warnings": self.warnings,
        }


class WheelScannerAdapter:
    name = "Wheel Scanner"

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def scan(self, limit: int) -> tuple[list[CandidateIdea], dict[str, Any], list[str]]:
        warnings: list[str] = []
        candidates: dict[str, CandidateIdea] = {}
        try:
            watchlist = _json_get(f"{self.base_url}/api/watchlist")
            rows = watchlist.get("tickers", []) if isinstance(watchlist, dict) else []
            for row in rows:
                idea = _wheel_watchlist_idea(row)
                if idea:
                    _merge_candidate(candidates, idea)
        except Exception as exc:
            warnings.append(f"Wheel Scanner watchlist unavailable: {exc}")

        for path, tag in (("/api/scanner/csp", "cash secured put"), ("/api/scanner/cc", "covered call")):
            try:
                scan = _json_get(f"{self.base_url}{path}?{urlencode({'limit': limit})}")
                for row in scan.get("results", []) if isinstance(scan, dict) else []:
                    idea = _wheel_option_idea(row, tag)
                    if idea:
                        _merge_candidate(candidates, idea)
            except Exception as exc:
                warnings.append(f"Wheel Scanner {tag} scan unavailable: {exc}")

        ordered = sorted(candidates.values(), key=lambda item: (-item.score(), item.symbol))[:limit]
        return ordered, {"candidate_count": len(ordered)}, warnings


class BreakoutScannerAdapter:
    name = "Breakout Scanner"

    def scan(self, db: Session, user_id: int, limit: int) -> tuple[list[CandidateIdea], dict[str, Any], list[str]]:
        result = run_breakout_scan(db, user_id, {"max_symbols": 120})
        ideas = [_breakout_idea(row) for row in result.get("signals", [])[:limit]]
        return [item for item in ideas if item], {
            "candidate_count": len(ideas),
            "scanned_symbols": result.get("scanned_symbols", 0),
            "data_source": result.get("data_source"),
        }, list(result.get("warnings", []))


class SmartCandlesAdapter:
    name = "Smart Candles"

    def scan(self, db: Session, limit: int) -> tuple[list[CandidateIdea], dict[str, Any], list[str]]:
        result = run_smart_candle_scan(db, {"max_symbols": 120, "include_neutral": False})
        ideas = [_smart_candle_idea(row) for row in result.get("signals", [])[:limit]]
        return [item for item in ideas if item], {
            "candidate_count": len(ideas),
            "scanned_symbols": result.get("scanned_symbols", 0),
            "data_source": result.get("data_source"),
        }, list(result.get("warnings", []))


class OptiTradeLabAdapter:
    name = "OptiTrade Lab"

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def scan(self, limit: int) -> tuple[list[CandidateIdea], dict[str, Any], list[str]]:
        data = _json_get(f"{self.base_url}/api/optitrade-lab/signals")
        rows = data.get("signals", []) if isinstance(data, dict) else []
        ideas = [_optitrade_idea(row) for row in rows[:limit]]
        return [item for item in ideas if item], {
            "candidate_count": len(ideas),
            "data_source": data.get("data_source") if isinstance(data, dict) else None,
        }, list(data.get("warnings", [])) if isinstance(data, dict) else []


class TipRanksEnricher:
    def __init__(self, api_url: str = "") -> None:
        self.api_url = api_url.strip().rstrip("/")

    def enrich(self, symbols: list[str]) -> tuple[dict[str, dict[str, Any]], dict[str, Any], list[str]]:
        if not self.api_url:
            return {}, {"status": "unavailable", "checked_symbols": [], "provider": "not_configured"}, [
                "TipRanks enrichment skipped because no TipRanks provider is configured."
            ]
        enriched: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        for symbol in symbols:
            try:
                url = self.api_url.format(symbol=quote(symbol)) if "{symbol}" in self.api_url else f"{self.api_url}/stocks/{quote(symbol)}"
                data = _json_get(url)
                enriched[symbol] = _compact_tipranks_payload(data)
            except Exception as exc:
                warnings.append(f"TipRanks unavailable for {symbol}: {exc}")
        return enriched, {
            "status": "partial" if warnings else "available",
            "checked_symbols": symbols,
            "enriched_count": len(enriched),
        }, warnings


class TipRanksRemoteMcpEnricher:
    def __init__(self, api_key: str) -> None:
        self.endpoint = f"https://mcp.tipranks.com/mcp/?apikey={quote(api_key.strip())}"

    def enrich(self, symbols: list[str]) -> tuple[dict[str, dict[str, Any]], dict[str, Any], list[str]]:
        if not symbols:
            return {}, {"status": "skipped", "checked_symbols": [], "provider": "tipranks_remote_mcp"}, []

        warnings: list[str] = []
        enriched: dict[str, dict[str, Any]] = {}
        try:
            trending = self._call_tool(
                "get_trending_stocks",
                {"num": max(20, min(60, len(symbols) * 5)), "filter": "both", "daysAgo": 30, "trendingType": "best-rated", "country": "US"},
            )
            rows = _tipranks_rows(trending)
            for row in rows:
                symbol = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
                if symbol in symbols:
                    enriched[symbol] = _compact_tipranks_payload(row)
        except Exception as exc:
            warnings.append(f"TipRanks remote MCP enrichment unavailable: {exc}")

        missing = [symbol for symbol in symbols if symbol not in enriched]
        if missing and not warnings:
            warnings.append(f"TipRanks remote MCP did not return matching finalist data for: {', '.join(missing)}.")

        return enriched, {
            "status": "partial" if warnings else "available",
            "checked_symbols": symbols,
            "enriched_count": len(enriched),
            "provider": "tipranks_remote_mcp",
        }, warnings

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        return _json_post(self.endpoint, payload)


class LunarCrushEnricher:
    base_url = "https://lunarcrush.com/api4"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key.strip()

    def enrich(self, symbols: list[str]) -> tuple[dict[str, dict[str, Any]], dict[str, Any], list[str]]:
        if not self.api_key:
            return {}, {"status": "skipped", "checked_symbols": [], "provider": "lunarcrush"}, []
        if not symbols:
            return {}, {"status": "skipped", "checked_symbols": [], "provider": "lunarcrush"}, []

        enriched: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        for symbol in symbols:
            try:
                data = _json_get(f"{self.base_url}/public/stocks/{quote(symbol)}/v1", headers={"Authorization": f"Bearer {self.api_key}"})
                compacted = _compact_lunarcrush_payload(data)
                if compacted:
                    enriched[symbol] = compacted
            except Exception as exc:
                warnings.append(f"LunarCrush unavailable for {symbol}: {exc}")
        return enriched, {
            "status": "partial" if warnings else "available",
            "checked_symbols": symbols,
            "enriched_count": len(enriched),
            "provider": "lunarcrush",
        }, warnings


def run_recommendation_agent(
    db: Session,
    user_id: int,
    payload: RecommendationAgentRunRequest,
    *,
    api_key: str | None = None,
    settings: Settings | None = None,
    tipranks_enricher: TipRanksEnricher | None = None,
    lunarcrush_enricher: LunarCrushEnricher | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    warnings: list[str] = [
        "Educational research only. Recommendations are scanner-ranked ideas for review, not investment advice or trade instructions."
    ]
    scanner_summary: dict[str, Any] = {}
    candidates: dict[str, CandidateIdea] = {}
    per_adapter_limit = max(payload.max_candidates, payload.finalist_count)

    wheel = WheelScannerAdapter(settings.ibkr_research_api_url)
    for idea in _safe_scan(lambda: wheel.scan(per_adapter_limit), wheel.name, scanner_summary, warnings):
        _merge_candidate(candidates, idea)

    breakout = BreakoutScannerAdapter()
    for idea in _safe_scan(lambda: breakout.scan(db, user_id, per_adapter_limit), breakout.name, scanner_summary, warnings):
        _merge_candidate(candidates, idea)

    smart = SmartCandlesAdapter()
    for idea in _safe_scan(lambda: smart.scan(db, per_adapter_limit), smart.name, scanner_summary, warnings):
        _merge_candidate(candidates, idea)

    optitrade = OptiTradeLabAdapter(settings.ibkr_research_api_url)
    for idea in _safe_scan(lambda: optitrade.scan(per_adapter_limit), optitrade.name, scanner_summary, warnings):
        _merge_candidate(candidates, idea)

    ordered_candidates = sorted(candidates.values(), key=lambda item: (-item.score(), item.symbol))[: payload.max_candidates]
    if not ordered_candidates:
        raise ValueError("No scanner candidates could be loaded from the configured research agents.")

    candidate_payload = [item.as_payload() for item in ordered_candidates]
    portfolio_payload = _parse_portfolio_input(payload.current_portfolio)
    pass_one_prompt = _ranking_prompt(candidate_payload, payload.finalist_count, phase="first-pass", user_context=payload.user_context, portfolio=portfolio_payload)
    model = payload.model
    model_routing: dict[str, Any] = {}
    if payload.model_mode == "nvidia":
        requested_model = nvidia_model_name(payload.model) if is_nvidia_model(payload.model) else NVIDIA_RECOMMENDATION_MODELS[0]
        model = f"nvidia:{requested_model}"
        model_routing = {
            "mode": "nvidia",
            "model": model,
            "display_name": requested_model,
            "reason": "Selected hosted NVIDIA NIM model for Recommendation Agent.",
            "provider": "nvidia",
            "base_url": "https://integrate.api.nvidia.com/v1",
            "available_models": list(NVIDIA_RECOMMENDATION_MODELS),
        }
    elif payload.model_mode:
        decision = RecommendationModelRouter().route(pass_one_prompt, payload.model_mode, payload.ollama_base_url)
        model = decision.model
        model_routing = {
            "mode": decision.mode,
            "model": decision.model,
            "display_name": decision.display_name,
            "reason": decision.reason,
            **decision.metadata,
        }

    pass_one_text, pass_one_payload = generate_text(
        model,
        pass_one_prompt,
        api_key=api_key,
        ollama_base_url=payload.ollama_base_url,
        instructions=RECOMMENDATION_AGENT_INSTRUCTIONS,
        ollama_timeout_seconds=RECOMMENDATION_AGENT_OLLAMA_TIMEOUT_SECONDS,
    )
    finalist_symbols = _finalist_symbols(pass_one_text, ordered_candidates, payload.finalist_count)

    tipranks_status: dict[str, Any] = {"status": "skipped", "checked_symbols": []}
    if payload.include_tipranks:
        if tipranks_enricher is None and payload.tipranks_api_key and payload.tipranks_api_key.strip():
            tipranks_enricher = TipRanksRemoteMcpEnricher(payload.tipranks_api_key)
        tipranks_enricher = tipranks_enricher or TipRanksEnricher(settings.tipranks_api_url)
        enriched, tipranks_status, tipranks_warnings = tipranks_enricher.enrich(finalist_symbols)
        warnings.extend(tipranks_warnings)
        for symbol, data in enriched.items():
            if symbol in candidates:
                candidates[symbol].tipranks = data

    lunarcrush_status: dict[str, Any] = {"status": "skipped", "checked_symbols": []}
    if payload.include_lunarcrush:
        if lunarcrush_enricher is None and payload.lunarcrush_api_key and payload.lunarcrush_api_key.strip():
            lunarcrush_enricher = LunarCrushEnricher(payload.lunarcrush_api_key)
        if lunarcrush_enricher is None:
            lunarcrush_status = {"status": "unavailable", "checked_symbols": finalist_symbols, "provider": "lunarcrush"}
            warnings.append("LunarCrush enrichment skipped because no LunarCrush API key is saved or supplied.")
        else:
            enriched, lunarcrush_status, lunarcrush_warnings = lunarcrush_enricher.enrich(finalist_symbols)
            warnings.extend(lunarcrush_warnings)
            for symbol, data in enriched.items():
                if symbol in candidates:
                    candidates[symbol].lunarcrush = data

    finalist_payload = [candidates[symbol].as_payload() for symbol in finalist_symbols if symbol in candidates]
    final_text, final_payload = generate_text(
        model,
        _ranking_prompt(finalist_payload, payload.finalist_count, phase="final-pass", user_context=payload.user_context, portfolio=portfolio_payload),
        api_key=api_key,
        ollama_base_url=payload.ollama_base_url,
        instructions=RECOMMENDATION_AGENT_INSTRUCTIONS,
        ollama_timeout_seconds=RECOMMENDATION_AGENT_OLLAMA_TIMEOUT_SECONDS,
    )

    ranked_ideas = _ranked_ideas_from_llm(final_text, [candidates[s] for s in finalist_symbols if s in candidates])
    return {
        "generated_at": datetime.now(timezone.utc),
        "model": model,
        "model_routing": model_routing,
        "ranked_ideas": ranked_ideas,
        "scanner_summary": scanner_summary,
        "tipranks_status": tipranks_status,
        "lunarcrush_status": lunarcrush_status,
        "warnings": _unique(warnings),
        "raw_llm_markdown": final_text,
        "usage": {
            "model_routing": model_routing,
            "first_pass": response_usage(pass_one_payload),
            "final_pass": response_usage(final_payload),
        },
    }


def _safe_scan(call: Any, name: str, scanner_summary: dict[str, Any], warnings: list[str]) -> list[CandidateIdea]:
    try:
        ideas, summary, adapter_warnings = call()
    except Exception as exc:
        scanner_summary[name] = {"status": "unavailable", "candidate_count": 0}
        warnings.append(f"{name} unavailable: {exc}")
        return []
    scanner_summary[name] = {"status": "ok", **summary}
    warnings.extend(adapter_warnings)
    return ideas


def _ranking_prompt(
    candidates: list[dict[str, Any]],
    finalist_count: int,
    *,
    phase: str,
    user_context: str | None = None,
    portfolio: list[dict[str, Any]] | None = None,
) -> str:
    context = (user_context or "").strip()
    portfolio_rows = portfolio or []
    return "\n".join([
        f"Recommendation Agent {phase}.",
        "Use the same educational Wall Street-style research discipline as FinanceOS Equity Research.",
        "Apply the equity research rubric below as decision criteria, but return the Recommendation Agent ranked_ideas schema requested after it.",
        "Also review the user's current stock portfolio, when supplied, for concentration, valuation, momentum-extension, and red-flag context that may affect new-money decisions.",
        "Use this extension rule for high-growth AI/semiconductor holdings: 15% above the 40-DMA is caution, 20% above the 40-DMA is dangerous, and 30% above the 40-DMA is very dangerous / partial trim zone.",
        "A dangerous area usually requires price 20%+ above the 40-DMA, RSI above 70, and climax-type/news-driven volume. This does not mean short it; it means do not chase new money and consider trimming or waiting for a pullback to the 20-day/40-day MA.",
        "",
        "Recommendation multi-agent rubric:",
        RECOMMENDATION_MULTI_AGENT_RUBRIC,
        "",
        "Equity Research rubric reused for this agent:",
        EQUITY_RESEARCH_JSON_SCHEMA_AND_RULES,
        "",
        "User decision context:",
        context or "No additional user context supplied.",
        "",
        "Current stock portfolio supplied by user:",
        json.dumps(portfolio_rows, indent=2, sort_keys=True, default=str) if portfolio_rows else "No current portfolio supplied.",
        "",
        f"Rank up to {finalist_count} educational research ideas from the supplied JSON.",
        "Prefer candidates with multiple independent scanner confirmations, strong evidence, and fewer unresolved warnings.",
        "When LunarCrush enrichment is supplied, use sentiment, interactions, social_dominance, and galaxy_score as final-analysis evidence for the Sentiment lens and mention meaningful extremes or contradictions versus scanner evidence.",
        "When a ranked idea overlaps with or materially adds to the current portfolio, point out portfolio-level red flags in rationale, especially concentration, valuation/extension risk, RSI > 70, climax volume, and whether new money should wait for a pullback.",
        "Return concise Markdown plus a JSON object with key 'ranked_ideas'.",
        "Each ranked idea should include: rank, symbol, verdict, rationale.",
        "Make the rationale visibly reflect the multi-agent rubric. For each ranked_ideas item, write rationale as compact labeled clauses: Director: ... Quant: ... Sentiment: ... Risk: ... Execution-planning: ...",
        "If a lens lacks supplied evidence, say 'Sentiment: no supplied sentiment evidence' or the equivalent rather than inventing outside facts.",
        "Do not include buy/sell/hold instructions or position sizing.",
        "",
        "Candidate JSON:",
        json.dumps(candidates, indent=2, sort_keys=True, default=str),
    ])


def _ranked_ideas_from_llm(text: str, finalists: list[CandidateIdea]) -> list[dict[str, Any]]:
    parsed = _extract_json_object(text)
    by_symbol = {item.symbol: item for item in finalists}
    ranked: list[dict[str, Any]] = []
    rows = parsed.get("ranked_ideas", []) if isinstance(parsed, dict) else []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol", "")).strip().upper()
            if symbol not in by_symbol:
                continue
            ranked.append(_ranked_idea_out(
                by_symbol[symbol],
                len(ranked) + 1,
                verdict=str(row.get("verdict", "")).strip(),
                rationale=str(row.get("rationale", "")).strip(),
            ))
    used = {row["symbol"] for row in ranked}
    for idea in finalists:
        if idea.symbol not in used:
            ranked.append(_ranked_idea_out(idea, len(ranked) + 1))
    return ranked


def _ranked_idea_out(idea: CandidateIdea, rank: int, *, verdict: str = "", rationale: str = "") -> dict[str, Any]:
    return {
        "rank": rank,
        "symbol": idea.symbol,
        "verdict": verdict or _default_verdict(idea),
        "rationale": rationale or "; ".join(idea.evidence[:3]),
        "source_agents": idea.source_agents,
        "strategy_tags": idea.strategy_tags,
        "scanner_scores": idea.scanner_scores,
        "context": idea.context,
        "evidence": idea.evidence,
        "tipranks": idea.tipranks,
        "lunarcrush": idea.lunarcrush,
        "warnings": idea.warnings,
    }


def _default_verdict(idea: CandidateIdea) -> str:
    if len(idea.source_agents) >= 2:
        return "Multi-agent research candidate"
    return f"{idea.source_agents[0] if idea.source_agents else 'Scanner'} research candidate"


def _finalist_symbols(text: str, candidates: list[CandidateIdea], count: int) -> list[str]:
    symbols = [item.symbol for item in candidates]
    parsed = _extract_json_object(text)
    llm_symbols: list[str] = []
    rows = parsed.get("ranked_ideas", []) if isinstance(parsed, dict) else []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                symbol = str(row.get("symbol", "")).strip().upper()
                if symbol in symbols and symbol not in llm_symbols:
                    llm_symbols.append(symbol)
    return [*llm_symbols, *[symbol for symbol in symbols if symbol not in llm_symbols]][:count]


def _extract_json_object(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start:end + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            continue
    return {}


def _parse_portfolio_input(value: str | None) -> list[dict[str, Any]]:
    if not value:
        return []
    holdings: list[dict[str, Any]] = []
    for part in value.split(","):
        if ":" not in part:
            continue
        symbol_raw, shares_raw = part.split(":", 1)
        symbol = symbol_raw.strip().upper()
        shares = _float(shares_raw.strip())
        if not symbol or shares is None:
            continue
        holdings.append({"symbol": symbol, "shares": shares})
    return holdings[:100]


def _wheel_watchlist_idea(row: Any) -> CandidateIdea | None:
    if not isinstance(row, dict):
        return None
    symbol = _symbol(row)
    if not symbol:
        return None
    signals = [str(item) for item in row.get("signals", []) if str(item).strip()]
    if not signals and not any(row.get(key) is not None for key in ("csp_30d", "cc_30d", "iv_rank", "rsi")):
        return None
    score = sum(_float(row.get(key)) or 0 for key in ("csp_30d", "cc_30d")) + ((_float(row.get("iv_rank")) or 0) / 4)
    return CandidateIdea(
        symbol=symbol,
        source_agents=["Wheel Scanner"],
        strategy_tags=_unique([item.lower() for item in signals] or ["wheel"]),
        scanner_scores={"wheel": round(score, 4)},
        context=_compact(row, ["price", "change_pct", "stage", "sata_score", "mansfield_rs", "rsi", "bb_pct", "iv_rank", "csp_30d", "cc_30d", "source"]),
        evidence=[f"Wheel context: {', '.join(signals) if signals else 'watchlist metrics available'}."],
        warnings=_extension_warnings(row),
    )


def _wheel_option_idea(row: Any, tag: str) -> CandidateIdea | None:
    if not isinstance(row, dict):
        return None
    symbol = _symbol(row)
    if not symbol:
        return None
    score = (_float(row.get("annualized_yield")) or _float(row.get("raw_yield")) or 0) + ((_float(row.get("open_interest")) or 0) / 1000)
    return CandidateIdea(
        symbol=symbol,
        source_agents=["Wheel Scanner"],
        strategy_tags=[tag],
        scanner_scores={f"wheel_{tag.replace(' ', '_')}": round(score, 4)},
        context=_compact(row, ["stock_price", "strike", "expiry", "dte", "delta", "annualized_yield", "open_interest", "volume", "bid", "ask"]),
        evidence=[f"Wheel {tag} candidate from option scan."],
    )


def _breakout_idea(row: Any) -> CandidateIdea | None:
    if not isinstance(row, dict):
        return None
    symbol = _symbol(row)
    if not symbol:
        return None
    return CandidateIdea(
        symbol=symbol,
        source_agents=["Breakout Scanner"],
        strategy_tags=[str(row.get("detector_type") or "breakout").replace("_", " ")],
        scanner_scores={"breakout": _float(row.get("score")) or 0},
        context=_compact(row, ["company_name", "sector", "price", "as_of_date", "resistance_level", "breakout_pct", "proximity_pct", "relative_volume", "rsi14", "sma20", "sma40", "sma50", "trend_label"]),
        evidence=[str(row.get("summary") or row.get("setup_label") or "Breakout setup detected.")],
        warnings=_unique([*[str(item) for item in row.get("warnings", [])], *_extension_warnings(row)]),
    )


def _smart_candle_idea(row: Any) -> CandidateIdea | None:
    if not isinstance(row, dict):
        return None
    symbol = _symbol(row)
    if not symbol:
        return None
    return CandidateIdea(
        symbol=symbol,
        source_agents=["Smart Candles"],
        strategy_tags=[f"smart candle {row.get('candle_color', 'signal')}"],
        scanner_scores={"smart_candles": _float(row.get("score")) or 0},
        context=_compact(row, ["company_name", "sector", "price", "as_of_date", "candle_color", "relative_volume", "rsi14", "return_5d", "return_20d", "sma20", "sma40", "sma50", "trend_label"]),
        evidence=[str(row.get("summary") or row.get("signal_label") or "Smart Candle signal detected.")],
        warnings=_unique([*[str(item) for item in row.get("warnings", [])], *_extension_warnings(row)]),
    )


def _optitrade_idea(row: Any) -> CandidateIdea | None:
    if not isinstance(row, dict):
        return None
    symbol = _symbol(row)
    signal = str(row.get("signal") or "").upper()
    if not symbol or signal not in {"BUY", "SELL", "HOLD"}:
        return None
    score = (_float(row.get("momentum_score")) or 0) + (_float(row.get("volume_score")) or 0) + (10 if signal == "BUY" else 0)
    return CandidateIdea(
        symbol=symbol,
        source_agents=["OptiTrade Lab"],
        strategy_tags=[f"optitrade {signal.lower()}", str(row.get("trend_state") or "trend")],
        scanner_scores={"optitrade": round(score, 4)},
        context=_compact(row, ["underlying", "as_of_date", "price", "signal", "trend_state", "anti_chop_state", "risk_reward", "atr", "momentum_score", "volume_score", "rsi", "sma40"]),
        evidence=[f"OptiTrade Lab signal is {signal} with trend state {row.get('trend_state', 'unknown')}."],
        warnings=_extension_warnings(row),
    )


def _compact_tipranks_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"raw": data}
    allowed = {
        "ticker", "symbol", "smartScore", "smart_score", "analystConsensus", "analyst_consensus",
        "priceTarget", "price_target", "buy", "hold", "sell", "hedgeFundTrend", "bloggerSentiment",
    }
    compact = {key: value for key, value in data.items() if key in allowed and value is not None}
    return compact or {"raw": data}


def _compact_lunarcrush_payload(data: Any) -> dict[str, Any]:
    row = _lunarcrush_row(data)
    if not row:
        return {}
    allowed = {
        "symbol", "ticker", "name", "title", "topic", "topic_rank", "market_cap_rank",
        "price", "volume_24h", "market_cap", "percent_change_24h", "galaxy_score",
        "alt_rank", "sentiment", "social_dominance", "num_posts", "num_contributors",
        "interactions", "interactions_24h", "interactions_per_post", "categories",
    }
    compact = {key: value for key, value in row.items() if key in allowed and value is not None}
    return compact or {"raw": row}


def _lunarcrush_row(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        return next((item for item in data if isinstance(item, dict)), {})
    if not isinstance(data, dict):
        return {}
    for key in ("data", "result", "stock", "topic"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            row = next((item for item in value if isinstance(item, dict)), None)
            if row:
                return row
    return data


def _tipranks_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    result = data.get("result")
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            rows: list[dict[str, Any]] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parsed = _json_loads(text)
                        rows.extend(_tipranks_rows(parsed))
                    elif isinstance(item.get("json"), (dict, list)):
                        rows.extend(_tipranks_rows(item["json"]))
            if rows:
                return rows
        structured = result.get("structuredContent") or result.get("data")
        rows = _tipranks_rows(structured)
        if rows:
            return rows
    for key in ("stocks", "data", "items", "results"):
        rows = _tipranks_rows(data.get(key))
        if rows:
            return rows
    return [data] if data.get("ticker") or data.get("symbol") else []


def _json_loads(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return []


def _json_get(url: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req_headers = {"Accept": "application/json", **(headers or {})}
    req = Request(url, method="GET", headers=req_headers)
    try:
        with urlopen(req, timeout=45) as response:
            return json.loads(response.read().decode("utf-8", errors="ignore") or "{}")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:160]
        raise RuntimeError(f"HTTP {exc.code}{': ' + detail if detail else ''}") from exc
    except (URLError, OSError) as exc:
        raise RuntimeError(str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("provider returned unreadable JSON") from exc


def _json_post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, method="POST", headers={"Accept": "application/json", "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=45) as response:
            return json.loads(response.read().decode("utf-8", errors="ignore") or "{}")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:160]
        raise RuntimeError(f"HTTP {exc.code}{': ' + detail if detail else ''}") from exc
    except (URLError, OSError) as exc:
        raise RuntimeError(str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("provider returned unreadable JSON") from exc


def _merge_candidate(candidates: dict[str, CandidateIdea], idea: CandidateIdea) -> None:
    existing = candidates.get(idea.symbol)
    if existing:
        existing.merge(idea)
    else:
        candidates[idea.symbol] = idea


def _symbol(row: dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").strip().upper()


def _float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _extension_warnings(row: dict[str, Any]) -> list[str]:
    price = _first_float(row, ["price", "close", "last", "stock_price"])
    ma40 = _first_float(row, ["sma40", "ma40", "dma40", "ma_40", "moving_average_40"])
    if not price or not ma40 or ma40 <= 0:
        return []

    extension_pct = ((price / ma40) - 1) * 100
    if extension_pct < 15:
        return []

    rsi = _first_float(row, ["rsi", "rsi14"])
    relative_volume = _first_float(row, ["relative_volume"])
    volume_score = _first_float(row, ["volume_score"])
    climax_volume = bool(
        (relative_volume is not None and relative_volume >= 2.0)
        or (volume_score is not None and volume_score >= 80)
    )
    overbought = bool(rsi is not None and rsi > 70)
    detail = f"price is {extension_pct:.1f}% above the 40-DMA"

    if extension_pct >= 30:
        zone = "Very dangerous / partial trim zone"
        action = "do not chase new money; consider partial trims or wait for a pullback toward the 20-day/40-day MA."
    elif extension_pct >= 20:
        zone = "Dangerous extension zone"
        action = "do not chase new money; consider waiting for a pullback toward the 20-day/40-day MA."
    else:
        zone = "Caution extension zone"
        action = "avoid chasing new money unless the setup resets closer to trend support."

    if extension_pct >= 20 and overbought and climax_volume:
        return [f"{zone}: {detail}, RSI is above 70, and volume is climax-type/news-driven; {action}"]
    if extension_pct >= 20 and overbought:
        return [f"{zone}: {detail} and RSI is above 70; {action}"]
    if extension_pct >= 20 and climax_volume:
        return [f"{zone}: {detail} with climax-type/news-driven volume; {action}"]
    return [f"{zone}: {detail}; {action}"]


def _first_float(row: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        value = _float(row.get(key))
        if value is not None:
            return value
    return None


def _compact(row: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: row.get(key) for key in keys if row.get(key) is not None}


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        cleaned = str(value).strip()
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result
