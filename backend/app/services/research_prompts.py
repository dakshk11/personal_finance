from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import re
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.models.entities import AIAdvisorResearchPromptRun
from app.services.ai_advisor import (
    AIAdvisorConfigurationError,
    AIAdvisorProviderError,
    create_openai_web_search_response,
    generate_text,
    response_usage,
)


ResearchPromptProvider = Literal["openai_web", "goose"]


@dataclass(frozen=True)
class ResearchPromptField:
    id: str
    label: str
    required: bool = False


@dataclass(frozen=True)
class ResearchPromptTemplate:
    id: str
    title: str
    prompt: str
    output_requirements: tuple[str, ...]
    fields: tuple[ResearchPromptField, ...] = ()


RESEARCH_PROMPT_TEMPLATES: tuple[ResearchPromptTemplate, ...] = (
    ResearchPromptTemplate(
        id="hedge-designer",
        title="Hedge Designer",
        prompt=(
            "My portfolio is exposed to {sector_market}. Using current options data and available inverse ETFs, "
            "design an efficient hedge: recommended instrument, hedge size (% of portfolio), annualized cost, "
            "scenario to activate it, and sources for volatility data."
        ),
        output_requirements=(
            "instrument or ETF/option structure",
            "hedge size percent of portfolio with assumptions",
            "annualized cost estimate",
            "activation scenario",
            "sources for volatility and options data",
        ),
        fields=(ResearchPromptField("sector_market", "Sector or market exposure", required=True),),
    ),
    ResearchPromptTemplate(
        id="hedge-fund-13f",
        title="Top Hedge Fund 13F Moves",
        prompt=(
            "Using recent 13F data from WhaleWisdom, Dataroma, SEC filings, and news, tell me which sectors/stocks "
            "the top 10 hedge funds are accumulating this quarter vs. the previous quarter. Present new entries, "
            "full exits, and increased positions, including the fund name and sources. Optional focus: {focus}."
        ),
        output_requirements=(
            "fund name",
            "ticker or sector",
            "new entries, full exits, and increased positions",
            "quarter comparison",
            "sources",
        ),
        fields=(ResearchPromptField("focus", "Optional fund, sector, or quarter focus"),),
    ),
    ResearchPromptTemplate(
        id="correlation-anomalies",
        title="Macro Correlation Anomalies",
        prompt=(
            "In the current macro environment, search for assets showing unusual correlations, such as gold and "
            "equities rising together, or bonds and stocks falling simultaneously. Explain what each anomaly has "
            "historically signaled, include 3 trades that would benefit from normalization, and provide sources. "
            "Optional asset focus: {asset_focus}."
        ),
        output_requirements=(
            "current anomaly",
            "historical signal",
            "normalization trade idea",
            "risk",
            "sources",
        ),
        fields=(ResearchPromptField("asset_focus", "Optional asset focus"),),
    ),
    ResearchPromptTemplate(
        id="dividend-trap-screen",
        title="Dividend Trap Screen",
        prompt=(
            "Search for 5 companies with an apparently attractive dividend yield above 5% but with warning signs "
            "such as high payout ratio, negative free cash flow, or rising debt. For each include ticker, current "
            "yield, probability of a cut, safer alternatives in the same sector, and sources. Optional sector focus: {sector_focus}."
        ),
        output_requirements=(
            "ticker",
            "yield",
            "warning signs",
            "cut probability",
            "safer sector alternative",
            "sources",
        ),
        fields=(ResearchPromptField("sector_focus", "Optional sector focus"),),
    ),
    ResearchPromptTemplate(
        id="short-squeeze-screen",
        title="Short Squeeze Candidates",
        prompt=(
            "Using web data from Finviz, Shortquote, exchange data, broker borrow data where available, and news, "
            "find 5 stocks with high short interest above 20% of float, elevated borrow rate, and an upcoming catalyst. "
            "For each ticker include percent short float, days to cover, catalyst, entry strategy, risk of a failed squeeze, "
            "and sources. Optional watchlist or sector: {watchlist_or_sector}."
        ),
        output_requirements=(
            "short float",
            "days to cover",
            "borrow or cost signal when available",
            "catalyst",
            "educational entry framework",
            "failed-squeeze risk",
            "sources",
        ),
        fields=(ResearchPromptField("watchlist_or_sector", "Optional watchlist or sector"),),
    ),
    ResearchPromptTemplate(
        id="macro-playbook",
        title="Macro Environment Playbook",
        prompt=(
            "Search the web from Fed, ECB, BEA, BLS, latest macro data, and market sources for the current macroeconomic "
            "context: inflation, interest rates, GDP, employment. Tell me which sectors/assets historically outperform "
            "in this exact environment, with 3 comparable historical examples, expected timeframe, and 3 sources. "
            "Optional region: {region}."
        ),
        output_requirements=(
            "inflation, rates, GDP, and employment snapshot",
            "historical analogs",
            "outperforming assets or sectors",
            "expected timeframe",
            "sources",
        ),
        fields=(ResearchPromptField("region", "Optional region"),),
    ),
    ResearchPromptTemplate(
        id="sentiment-fundamental-divergence",
        title="Sentiment/Fundamentals Divergence",
        prompt=(
            "Search for stocks where market sentiment from negative news or bearish social media tone clearly diverges "
            "from strong underlying fundamentals. Return 6 ideas including ticker, reason for negative sentiment, why "
            "the fundamentals contradict that narrative, technical entry level, and sources. Optional sector or watchlist: {sector_or_watchlist}."
        ),
        output_requirements=(
            "ticker",
            "negative narrative",
            "contradicting fundamentals",
            "technical level",
            "sources",
        ),
        fields=(ResearchPromptField("sector_or_watchlist", "Optional sector or watchlist"),),
    ),
    ResearchPromptTemplate(
        id="best-entry-point",
        title="Best Entry Point",
        prompt=(
            "I want to buy {tickers}, but I want to enter at the best possible price. "
            "For each ticker, analyze its current valuation, recent price action, and key support levels "
            "to tell me if I should buy now, wait for a pullback, or set a target entry price. "
            "Include: current price vs. fair value estimate, nearest strong support level, "
            "recommended entry price or zone, stop-loss level, and a one-line rationale."
        ),
        output_requirements=(
            "ticker and current price",
            "valuation: current price vs. fair value or analyst consensus",
            "recent price action summary",
            "key support levels with specific prices",
            "recommendation: buy now / wait for pullback / set limit — with target entry price or zone",
            "stop-loss level",
            "one-line rationale",
        ),
        fields=(
            ResearchPromptField("tickers", "Stock ticker(s)", required=True),
        ),
    ),
    ResearchPromptTemplate(
        id="trading-plan-architect",
        title="Trading Plan Architect",
        prompt=(
            "You are a high-level trading mentor. Create my personalized trading plan.\n\n"
            "My profile:\n"
            "— Experience: {level}\n"
            "— Available capital: {amount}\n"
            "— Daily time available: {time_available}\n"
            "— Markets: {markets}\n"
            "— Preferred style: {style}\n"
            "— 12-month goal: {goal}\n"
            "— Main identified weakness: {weakness}\n\n"
            "Build a complete plan with:\n"
            "1. Strategy tailored to my profile (with justification)\n"
            "2. Sample daily routine: before, during, and after the session\n"
            "3. The 5 non-negotiable rules of MY trading\n"
            "4. Tracking system and weekly KPIs\n"
            "5. Realistic roadmap at 3 / 6 / 12 months with concrete milestones\n"
            "6. The 3 most likely mistakes I will make and how to prevent them"
        ),
        output_requirements=(
            "strategy recommendation with justification tied to the stated profile",
            "sample daily routine: pre-session, during session, post-session",
            "5 non-negotiable personal trading rules",
            "tracking system and weekly KPIs",
            "3 / 6 / 12 month roadmap with concrete milestones",
            "3 most likely mistakes and specific prevention tactics",
        ),
        fields=(
            ResearchPromptField("level", "Experience level", required=True),
            ResearchPromptField("amount", "Available capital", required=True),
            ResearchPromptField("time_available", "Daily time available", required=True),
            ResearchPromptField("markets", "Markets", required=True),
            ResearchPromptField("style", "Preferred style", required=True),
            ResearchPromptField("goal", "12-month goal", required=True),
            ResearchPromptField("weakness", "Main identified weakness", required=True),
        ),
    ),
    ResearchPromptTemplate(
        id="institutional-flow-decoder",
        title="Institutional Flow Decoder",
        prompt=(
            "You are an expert in order flow, market microstructure, and institutional analysis.\n\n"
            "Current context in {asset}:\n"
            "— Open Interest: {oi_data}\n"
            "— Funding rate: {funding}\n"
            "— Volume Delta 24h: {delta}\n"
            "— Recent liquidations: {liquidations}\n"
            "— CVD (Cumulative Volume Delta): {cvd_trend}\n\n"
            "Analyze:\n"
            "1. Who controls the market: institutional buyers or sellers?\n"
            "2. Is there silent accumulation, distribution, or liquidity manipulation?\n"
            "3. Main liquidity zones above and below (probable stop hunts)\n"
            "4. 'Smart money' favorite scenario according to this data\n"
            "5. Alert signal: What change in these metrics would invalidate your analysis?"
        ),
        output_requirements=(
            "institutional control: buyers or sellers, with supporting data from the inputs",
            "accumulation / distribution / manipulation read with reasoning",
            "liquidity zones above and below with probable stop-hunt levels",
            "smart money preferred scenario with entry rationale",
            "invalidation alert: specific metric change that flips the thesis",
        ),
        fields=(
            ResearchPromptField("asset", "Asset", required=True),
            ResearchPromptField("oi_data", "Open Interest", required=True),
            ResearchPromptField("funding", "Funding rate", required=True),
            ResearchPromptField("delta", "Volume Delta 24h", required=True),
            ResearchPromptField("liquidations", "Recent liquidations", required=True),
            ResearchPromptField("cvd_trend", "CVD trend", required=True),
        ),
    ),
    ResearchPromptTemplate(
        id="weekly-macro-radar",
        title="Weekly Macro Radar",
        prompt=(
            "You are a senior macro strategist at a hedge fund. I mainly trade {markets}.\n\n"
            "For the week of {date}, build my macro briefing:\n\n"
            "1. Risk map: Top 3 macro events, including estimated probability and likely market direction.\n"
            "2. Key correlations to monitor (DXY, 10-year yields, VIX, oil, etc.).\n"
            "3. Current market sentiment: Is it risk-on or risk-off? Support your view with data.\n"
            "4. Potential impact on each of my markets.\n"
            "5. Macro trade of the week: Thesis in 3 lines, catalyst, timing, and invalidation level.\n\n"
            "My current bias is {bias}. Challenge it using the macro data and tell me whether I should reconsider it."
        ),
        output_requirements=(
            "risk map: top 3 macro events with probability estimate and likely market direction",
            "key correlations to monitor this week (DXY, yields, VIX, oil, etc.)",
            "risk-on / risk-off sentiment call with supporting data",
            "impact assessment for each specified market",
            "macro trade of the week: thesis, catalyst, timing, and invalidation level",
            "bias challenge: whether the stated bias holds or should be reconsidered given macro data",
            "sources",
        ),
        fields=(
            ResearchPromptField("markets", "Markets you trade", required=True),
            ResearchPromptField("date", "Week of (date)", required=True),
            ResearchPromptField("bias", "Your current bias", required=True),
        ),
    ),
    ResearchPromptTemplate(
        id="setup-scanner",
        title="Setup Scanner",
        prompt=(
            "You are a senior technical analyst specialized in {strategy}.\n\n"
            "Analyze the recent price action of {asset} on the {timeframe} timeframe.\n\n"
            "Provide:\n"
            "1. Precise market structure (HH/HL, LL/LH, range)\n"
            "2. Key support and resistance zones with strength rating (1-10)\n"
            "3. Most probable long and short setups for the next 48 hours\n"
            "4. Exact invalidation level for each scenario\n"
            "5. Overall confluence score for the best setup (with justification)\n\n"
            "Be precise, use specific price levels. No generalizations."
        ),
        output_requirements=(
            "market structure label (HH/HL, LL/LH, or range) with current key swing levels",
            "support and resistance zones with specific price levels and strength rating 1-10",
            "most probable long setup: entry zone, target, invalidation level",
            "most probable short setup: entry zone, target, invalidation level",
            "confluence score for best setup with justification",
        ),
        fields=(
            ResearchPromptField("strategy", "Analysis strategy", required=True),
            ResearchPromptField("asset", "Asset / ticker", required=True),
            ResearchPromptField("timeframe", "Timeframe", required=True),
        ),
    ),
)

TEMPLATE_BY_ID = {template.id: template for template in RESEARCH_PROMPT_TEMPLATES}

RESEARCH_PROMPT_SYSTEM_INSTRUCTIONS = (
    "You are an educational public-market research analyst. Use current, source-backed information where available. "
    "Do not provide personalized investment advice, position sizing for a user's real account, buy/sell/hold instructions, "
    "or brokerage/order execution instructions. Trade ideas, entries, exits, stops, and hedge sizing must be framed as "
    "educational scenario analysis for further review. Always include source URLs and note that date-sensitive market data "
    "can change quickly."
)


def get_research_prompt_template(template_id: str) -> ResearchPromptTemplate | None:
    return TEMPLATE_BY_ID.get(template_id)


def build_research_prompt(template_id: str, inputs: dict[str, Any]) -> tuple[ResearchPromptTemplate, dict[str, str], str]:
    template = get_research_prompt_template(template_id)
    if not template:
        raise ValueError("Unknown research prompt template.")

    clean_inputs = _clean_inputs(template, inputs)
    missing = [field.label for field in template.fields if field.required and not clean_inputs.get(field.id)]
    if missing:
        raise ValueError(f"Missing required inputs: {', '.join(missing)}")

    filled_prompt = template.prompt.format_map(_DefaultInputs(clean_inputs))
    today = datetime.now(UTC).date().isoformat()
    requirements = "\n".join(f"- {item}" for item in template.output_requirements)
    prompt = f"""{RESEARCH_PROMPT_SYSTEM_INSTRUCTIONS}

Current date: {today}

Research task:
{filled_prompt}

Required output:
- Start with a concise answer-first summary.
- Include a table or clearly structured sections matching this template.
{requirements}
- Include an explicit source list with URLs.
- Include a date-sensitive caveat for current data.
- Include an educational-only disclaimer.

Return concise Markdown. Prefer primary or reputable sources for current market, macro, 13F, short-interest, options, and fundamental data."""
    return template, clean_inputs, prompt


def run_research_prompt(
    db: Session,
    *,
    user_id: int,
    template_id: str,
    provider: ResearchPromptProvider,
    model: str,
    inputs: dict[str, Any],
    openai_api_key: str | None = None,
    ollama_base_url: str | None = None,
) -> AIAdvisorResearchPromptRun:
    template, clean_inputs, prompt_text = build_research_prompt(template_id, inputs)
    normalized_model = model.strip()
    if not normalized_model:
        raise AIAdvisorProviderError("Select a model before running the research prompt.", status_code=422)

    warnings: list[str] = []
    try:
        if provider == "openai_web":
            if not openai_api_key:
                raise AIAdvisorProviderError("Save an OpenAI API key before running OpenAI Web Search.", status_code=400)
            response_text, response_payload = create_openai_web_search_response(
                openai_api_key,
                normalized_model,
                prompt_text,
                instructions=RESEARCH_PROMPT_SYSTEM_INSTRUCTIONS,
            )
        elif provider == "goose":
            goose_model = normalized_model if normalized_model.startswith("goose:") else f"goose:{normalized_model}"
            response_text, response_payload = generate_text(
                goose_model,
                prompt_text,
                ollama_base_url=ollama_base_url,
                ollama_timeout_seconds=240,
            )
            normalized_model = goose_model
            warnings.append("Goose source quality depends on your local Goose tools and model configuration.")
        else:
            raise AIAdvisorProviderError("Unsupported research provider.", status_code=400)
    except AIAdvisorConfigurationError:
        raise

    sources = extract_sources(response_payload, response_text)
    if not sources:
        warnings.append("No structured sources were extracted. Check the response text for cited URLs.")

    run = AIAdvisorResearchPromptRun(
        user_id=user_id,
        template_id=template.id,
        template_title=template.title,
        provider=provider,
        model=normalized_model,
        input_json=json.dumps(clean_inputs, separators=(",", ":"), sort_keys=True),
        prompt_text=prompt_text,
        response_text=response_text,
        sources_json=json.dumps(sources, separators=(",", ":"), sort_keys=True),
        usage_json=json.dumps(response_usage(response_payload), separators=(",", ":"), sort_keys=True),
        warnings_json=json.dumps(warnings, separators=(",", ":"), sort_keys=True),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def extract_sources(response_payload: dict[str, Any], response_text: str) -> list[dict[str, str | None]]:
    sources: list[dict[str, str | None]] = []
    seen: set[str] = set()

    def add_source(url: Any, title: Any = None, source_type: Any = None) -> None:
        if not isinstance(url, str):
            return
        cleaned = url.strip().rstrip(".,;)")
        if not cleaned.startswith(("http://", "https://")) or cleaned in seen:
            return
        seen.add(cleaned)
        sources.append({
            "title": title.strip() if isinstance(title, str) and title.strip() else None,
            "url": cleaned,
            "source_type": source_type.strip() if isinstance(source_type, str) and source_type.strip() else None,
        })

    _walk_openai_sources(response_payload, add_source)
    for match in re.findall(r"https?://[^\s<>)\]]+", response_text or ""):
        add_source(match, source_type="text")
    return sources[:80]


def _walk_openai_sources(value: Any, add_source: Any) -> None:
    if isinstance(value, dict):
        source_type = value.get("type")
        if isinstance(value.get("url"), str):
            add_source(value.get("url"), value.get("title") or value.get("name"), source_type)
        if isinstance(value.get("uri"), str):
            add_source(value.get("uri"), value.get("title") or value.get("name"), source_type)
        for key in ("sources", "annotations", "content", "output", "action", "results"):
            if key in value:
                _walk_openai_sources(value[key], add_source)
    elif isinstance(value, list):
        for item in value:
            _walk_openai_sources(item, add_source)


def _clean_inputs(template: ResearchPromptTemplate, inputs: dict[str, Any]) -> dict[str, str]:
    allowed = {field.id for field in template.fields}
    clean: dict[str, str] = {}
    for field_id in allowed:
        value = inputs.get(field_id, "")
        clean[field_id] = str(value).strip()[:2000] if value is not None else ""
    return clean


class _DefaultInputs(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "none"
