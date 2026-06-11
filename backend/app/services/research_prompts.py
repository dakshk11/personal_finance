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
