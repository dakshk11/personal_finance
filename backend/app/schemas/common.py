from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: int
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class RetirementAnalyzerStateIn(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class RetirementAnalyzerStateOut(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = None


class AIAdvisorOpenAIKeyIn(BaseModel):
    api_key: str = Field(min_length=20, max_length=512)


class AIAdvisorOpenAIKeyOut(BaseModel):
    has_key: bool
    key_fingerprint: str | None = None
    validated_at: datetime | None = None
    updated_at: datetime | None = None


class AIAdvisorTipRanksKeyIn(BaseModel):
    api_key: str = Field(min_length=8, max_length=512)


class AIAdvisorTipRanksKeyOut(BaseModel):
    has_key: bool
    key_fingerprint: str | None = None
    validated_at: datetime | None = None
    updated_at: datetime | None = None


class AIAdvisorLunarCrushKeyIn(BaseModel):
    api_key: str = Field(min_length=8, max_length=512)


class AIAdvisorLunarCrushKeyOut(BaseModel):
    has_key: bool
    key_fingerprint: str | None = None
    validated_at: datetime | None = None
    updated_at: datetime | None = None


class AIAdvisorNvidiaKeyIn(BaseModel):
    api_key: str = Field(min_length=8, max_length=512)


class AIAdvisorNvidiaKeyOut(BaseModel):
    has_key: bool
    key_fingerprint: str | None = None
    validated_at: datetime | None = None
    updated_at: datetime | None = None


class AIAdvisorAlpacaKeyIn(BaseModel):
    api_key: str = Field(min_length=8, max_length=512)
    api_secret: str = Field(min_length=8, max_length=512)


class AIAdvisorAlpacaKeyOut(BaseModel):
    has_key: bool
    key_fingerprint: str | None = None
    validated_at: datetime | None = None
    updated_at: datetime | None = None


class AIAdvisorRetirementRunRequest(BaseModel):
    module_id: str = Field(min_length=1, max_length=80)
    model: str = Field(default="gpt-5.4", min_length=1, max_length=200)
    inputs: dict[str, Any] = Field(default_factory=dict)
    ollama_base_url: str | None = Field(default=None, max_length=200)


class AIAdvisorReportSummaryOut(BaseModel):
    id: int
    module_id: str
    module_title: str
    model: str
    created_at: datetime


class AIAdvisorReportOut(AIAdvisorReportSummaryOut):
    input_snapshot: dict[str, Any]
    prompt_text: str
    response_text: str
    usage: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None


class AIAdvisorResearchPromptRunRequest(BaseModel):
    template_id: str = Field(min_length=1, max_length=80)
    provider: Literal["openai_web", "goose"] = "openai_web"
    model: str = Field(default="gpt-5.4", min_length=1, max_length=200)
    inputs: dict[str, Any] = Field(default_factory=dict)
    ollama_base_url: str | None = Field(default=None, max_length=200)


class AIAdvisorResearchPromptSourceOut(BaseModel):
    title: str | None = None
    url: str
    source_type: str | None = None


class AIAdvisorResearchPromptRunSummaryOut(BaseModel):
    id: int
    template_id: str
    template_title: str
    provider: str
    model: str
    created_at: datetime


class AIAdvisorResearchPromptRunOut(AIAdvisorResearchPromptRunSummaryOut):
    inputs: dict[str, Any] = Field(default_factory=dict)
    prompt_text: str
    response_text: str
    sources: list[AIAdvisorResearchPromptSourceOut] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class RecommendationAgentRunRequest(BaseModel):
    model: str = Field(default="gpt-5.4", min_length=1, max_length=200)
    model_mode: Literal["ollama", "foundation", "nvidia"] | None = None
    ollama_base_url: str | None = Field(default=None, max_length=200)
    max_candidates: int = Field(default=25, ge=5, le=60)
    finalist_count: int = Field(default=8, ge=1, le=15)
    include_tipranks: bool = True
    tipranks_api_key: str | None = Field(default=None, max_length=512)
    include_lunarcrush: bool = True
    lunarcrush_api_key: str | None = Field(default=None, max_length=512)
    user_context: str | None = Field(default=None, max_length=4000)
    current_portfolio: str | None = Field(default=None, max_length=4000)


class RecommendationAgentIdeaOut(BaseModel):
    rank: int
    symbol: str
    verdict: str = ""
    rationale: str = ""
    source_agents: list[str] = Field(default_factory=list)
    strategy_tags: list[str] = Field(default_factory=list)
    scanner_scores: dict[str, float] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    tipranks: dict[str, Any] | None = None
    lunarcrush: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)


class RecommendationAgentRunOut(BaseModel):
    generated_at: datetime
    model: str
    model_routing: dict[str, Any] = Field(default_factory=dict)
    ranked_ideas: list[RecommendationAgentIdeaOut]
    scanner_summary: dict[str, Any] = Field(default_factory=dict)
    tipranks_status: dict[str, Any] = Field(default_factory=dict)
    lunarcrush_status: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    raw_llm_markdown: str = ""
    usage: dict[str, Any] = Field(default_factory=dict)


class WheelScannerChatMessageIn(BaseModel):
    role: Literal["user", "assistant"] | str
    content: str = Field(min_length=1, max_length=4000)


class WheelScannerChatQuoteIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    price: float | None = None
    change_pct: float | None = None
    stage: int | None = None
    sata_score: float | None = None
    mansfield_rs: float | None = None
    rsi: float | None = None
    bb_pct: float | None = None
    iv_rank: float | None = None
    csp_30d: float | None = None
    cc_30d: float | None = None
    volume: float | None = None
    signals: list[str] = Field(default_factory=list)
    source: str | None = None


class WheelScannerChatOptionSummaryIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    puts_count: int = Field(default=0, ge=0)
    calls_count: int = Field(default=0, ge=0)
    best_put: dict[str, Any] | None = None
    best_call: dict[str, Any] | None = None


class WheelScannerChatContextIn(BaseModel):
    status: dict[str, Any] | None = None
    active_tab: str = Field(default="watchlist", max_length=40)
    filters: dict[str, Any] = Field(default_factory=dict)
    custom_symbols: list[str] = Field(default_factory=list)
    selected_quotes: list[WheelScannerChatQuoteIn] = Field(min_length=1, max_length=25)
    selected_options_summary: WheelScannerChatOptionSummaryIn | None = None
    recent_messages: list[WheelScannerChatMessageIn] = Field(default_factory=list, max_length=8)


class WheelScannerChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    model: str = Field(default="gpt-5.4", min_length=1, max_length=200)
    ollama_base_url: str | None = Field(default=None, max_length=200)
    context: WheelScannerChatContextIn


class WheelScannerChatOut(BaseModel):
    response_text: str
    model: str
    usage: dict[str, Any] = Field(default_factory=dict)


class EarningsAgentRunRequest(BaseModel):
    query: str = Field(min_length=1, max_length=160)
    model: str = Field(default="gpt-5.4", min_length=1, max_length=200)
    ollama_base_url: str | None = Field(default=None, max_length=200)


class EarningsAgentSourceOut(BaseModel):
    source_type: Literal["sec", "motley"] | str
    title: str
    status: Literal["found", "missing", "partial"] | str
    url: str | None = None
    document_type: str | None = None
    filing_date: date | None = None
    excerpt: str | None = None
    warning: str | None = None


class EarningsAgentMetricOut(BaseModel):
    name: str
    value: str
    context: str | None = None


class EarningsAgentDigestOut(BaseModel):
    executive_summary: str = ""
    top_takeaways: list[str] = Field(default_factory=list)
    financial_metrics: list[EarningsAgentMetricOut] = Field(default_factory=list)
    management_tone: str = ""
    risks: list[str] = Field(default_factory=list)
    deep_dive_questions: list[str] = Field(default_factory=list)
    source_notes: list[str] = Field(default_factory=list)
    raw_markdown: str | None = None


class EarningsAgentRunSummaryOut(BaseModel):
    id: int
    ticker: str
    company_name: str
    created_at: datetime
    source_status: str


class EarningsAgentRunOut(EarningsAgentRunSummaryOut):
    query: str
    cik: str | None = None
    model: str
    sources: list[EarningsAgentSourceOut] = Field(default_factory=list)
    digest: EarningsAgentDigestOut
    warnings: list[str] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)


class StockAnalysisRunRequest(BaseModel):
    query: str = Field(min_length=1, max_length=160)
    model: str = Field(default="gpt-5.4", min_length=1, max_length=200)
    model_mode: Literal["ollama", "foundation"] | None = None
    ollama_base_url: str | None = Field(default=None, max_length=200)


class StockAnalysisSourceOut(BaseModel):
    source_type: str
    title: str
    status: str
    url: str | None = None
    document_type: str | None = None
    excerpt: str | None = None
    warning: str | None = None


class StockAnalysisFinancialRowOut(BaseModel):
    year: int
    revenue: float | None = None
    revenue_growth: float | None = None
    net_income: float | None = None
    free_cash_flow: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    profit_margin: float | None = None
    debt: float | None = None
    roe: float | None = None


class StockAnalysisPeerOut(BaseModel):
    symbol: str
    company_name: str
    sector: str | None = None
    industry: str | None = None
    forward_pe: float | None = None
    trailing_pe: float | None = None
    price_to_sales: float | None = None
    profit_margin: float | None = None


class StockAnalysisDCFOut(BaseModel):
    fair_value_per_share: float | None = None
    upside_downside_pct: float | None = None
    base_free_cash_flow: float | None = None
    growth_rate: float | None = None
    discount_rate: float = 0.10
    terminal_growth_rate: float = 0.03
    warning: str | None = None


class StockAnalysisValuationOut(BaseModel):
    current_price: float | None = None
    market_cap: float | None = None
    trailing_pe: float | None = None
    forward_pe: float | None = None
    price_to_sales: float | None = None
    enterprise_to_ebitda: float | None = None
    industry_average_forward_pe: float | None = None
    peer_average_forward_pe: float | None = None
    dcf: StockAnalysisDCFOut
    peers: list[StockAnalysisPeerOut] = Field(default_factory=list)


class StockAnalysisRiskOut(BaseModel):
    rank: int
    title: str
    detail: str
    severity: str | None = None


class StockAnalysisScenarioOut(BaseModel):
    case: Literal["bull", "base", "bear"] | str
    summary: str
    key_drivers: list[str] = Field(default_factory=list)


class StockAnalysisDigestOut(BaseModel):
    executive_summary: str = ""
    business_model: str = ""
    moat_summary: str = ""
    moat_score: int | None = None
    competitor_comparison: list[str] = Field(default_factory=list)
    industry_trends: list[str] = Field(default_factory=list)
    financial_health: str = ""
    valuation_summary: str = ""
    risks: list[StockAnalysisRiskOut] = Field(default_factory=list)
    growth_potential: str = ""
    institutional_perspective: str = ""
    scenarios: list[StockAnalysisScenarioOut] = Field(default_factory=list)
    bull_bear_debate: list[str] = Field(default_factory=list)
    latest_earnings: str = ""
    outlook_12_24_months: str = ""
    research_stance: str = "Neutral / monitor"
    deep_dive_questions: list[str] = Field(default_factory=list)
    source_notes: list[str] = Field(default_factory=list)
    raw_markdown: str | None = None


class StockAnalysisRunSummaryOut(BaseModel):
    id: int
    ticker: str
    company_name: str
    created_at: datetime
    source_status: str
    research_stance: str


class StockAnalysisRunOut(StockAnalysisRunSummaryOut):
    query: str
    sector: str | None = None
    industry: str | None = None
    model: str
    model_routing: dict[str, Any] = Field(default_factory=dict)
    reused_from_cache: bool = False
    cache_message: str | None = None
    sources: list[StockAnalysisSourceOut] = Field(default_factory=list)
    financials: list[StockAnalysisFinancialRowOut] = Field(default_factory=list)
    valuation: StockAnalysisValuationOut
    digest: StockAnalysisDigestOut
    warnings: list[str] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)


BreakoutDetectorLiteral = Literal["ceiling_breakout", "momentum_breakout", "near_breakout"]


class BreakoutScannerConfigIn(BaseModel):
    detectors: list[BreakoutDetectorLiteral] = Field(default_factory=lambda: ["ceiling_breakout", "momentum_breakout", "near_breakout"])
    custom_symbols: list[str] = Field(default_factory=list)
    lookback_days: int = Field(default=420, ge=120, le=1600)
    min_relative_volume: float = Field(default=1.5, ge=0.1, le=10)
    ideal_relative_volume: float = Field(default=2.0, ge=0.1, le=20)
    min_ceiling_touches: int = Field(default=3, ge=1, le=12)
    ceiling_tolerance_pct: float = Field(default=0.025, ge=0.001, le=0.15)
    breakout_clearance_pct: float = Field(default=0.01, ge=0, le=0.2)
    near_breakout_pct: float = Field(default=0.03, ge=0.001, le=0.2)
    min_avg_dollar_volume: float = Field(default=25_000_000, ge=0, le=5_000_000_000)
    require_above_sma200: bool = True
    max_symbols: int = Field(default=120, ge=1, le=505)


class BreakoutScannerBacktestRequest(BreakoutScannerConfigIn):
    detector: BreakoutDetectorLiteral = "ceiling_breakout"
    years: int = Field(default=5, ge=1, le=10)


class BreakoutUniverseItemOut(BaseModel):
    symbol: str
    company_name: str
    sector: str
    source: str
    source_url: str


class BreakoutUniverseOut(BaseModel):
    items: list[BreakoutUniverseItemOut]
    count: int
    source: str
    source_url: str
    cache_status: str
    retrieved_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)


class BreakoutChartPointOut(BaseModel):
    date: date
    close: float
    volume: float
    sma20: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    resistance: float | None = None


class BreakoutSignalOut(BaseModel):
    symbol: str
    company_name: str
    sector: str
    detector_type: str
    setup_label: str
    score: float
    rank: int
    price: float
    as_of_date: date | None = None
    resistance_level: float | None = None
    breakout_pct: float | None = None
    proximity_pct: float | None = None
    touch_count: int = 0
    relative_volume: float | None = None
    avg_volume_50d: float | None = None
    sma20: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    trend_label: str
    summary: str
    data_source: str
    warnings: list[str] = Field(default_factory=list)
    chart: list[BreakoutChartPointOut] = Field(default_factory=list)


class BreakoutScanOut(BaseModel):
    scan_run_id: int | str | None = None
    scanned_at: datetime
    market_date: date
    data_source: str
    universe_count: int
    scanned_symbols: int
    config: dict[str, Any]
    signals: list[BreakoutSignalOut]
    warnings: list[str] = Field(default_factory=list)


class BreakoutBacktestHorizonOut(BaseModel):
    horizon_days: int
    signal_count: int
    win_rate: float | None = None
    average_return: float | None = None
    median_return: float | None = None
    p10_return: float | None = None
    p90_return: float | None = None


class BreakoutBacktestOut(BaseModel):
    detector: str
    evaluated_years: int
    signal_count: int
    config: dict[str, Any]
    horizons: list[BreakoutBacktestHorizonOut]
    warnings: list[str] = Field(default_factory=list)


SmartCandleColorLiteral = Literal["blue", "pink", "red", "neutral"]
SmartCandleTradeActionLiteral = Literal["buy", "sell"]


class SmartCandleScanRequest(BaseModel):
    custom_symbols: list[str] = Field(default_factory=list)
    lookback_days: int = Field(default=420, ge=120, le=1600)
    min_relative_volume: float = Field(default=1.1, ge=0.1, le=10)
    min_avg_dollar_volume: float = Field(default=25_000_000, ge=0, le=5_000_000_000)
    max_symbols: int = Field(default=120, ge=1, le=505)
    include_neutral: bool = False
    trend_filter: Literal["all", "above_sma200", "below_sma200"] = "all"


class SmartCandleComponentOut(BaseModel):
    label: str
    passed: bool
    value: str


class SmartCandleChartPointOut(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    sma20: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    candle_color: SmartCandleColorLiteral | None = None


class SmartCandleSignalOut(BaseModel):
    symbol: str
    company_name: str
    sector: str
    candle_color: SmartCandleColorLiteral
    signal_label: str
    score: float
    rank: int
    price: float
    as_of_date: date | None = None
    open: float
    high: float
    low: float
    close: float
    body_pct: float | None = None
    body_to_range: float | None = None
    close_location: float | None = None
    upper_wick_pct: float | None = None
    lower_wick_pct: float | None = None
    relative_volume: float | None = None
    avg_volume_50d: float | None = None
    avg_dollar_volume: float | None = None
    rsi14: float | None = None
    return_5d: float | None = None
    return_20d: float | None = None
    sma20: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    trend_label: str
    summary: str
    components: list[SmartCandleComponentOut] = Field(default_factory=list)
    data_source: str
    warnings: list[str] = Field(default_factory=list)
    chart: list[SmartCandleChartPointOut] = Field(default_factory=list)


class SmartCandleScanOut(BaseModel):
    scanned_at: datetime
    market_date: date
    data_source: str
    universe_count: int
    scanned_symbols: int
    config: dict[str, Any]
    signals: list[SmartCandleSignalOut]
    warnings: list[str] = Field(default_factory=list)


class SmartCandleBacktestRequest(SmartCandleScanRequest):
    candle_color: SmartCandleColorLiteral = "blue"
    years: int = Field(default=5, ge=1, le=10)
    min_signal_score: float = Field(default=0, ge=0, le=100)
    trade_action: SmartCandleTradeActionLiteral = "buy"


class SmartCandleBacktestHorizonOut(BaseModel):
    candle_color: SmartCandleColorLiteral
    horizon_days: int
    signal_count: int
    win_rate: float | None = None
    average_return: float | None = None
    median_return: float | None = None
    p10_return: float | None = None
    p90_return: float | None = None


class SmartCandleBacktestOut(BaseModel):
    candle_color: SmartCandleColorLiteral
    trade_action: SmartCandleTradeActionLiteral
    evaluated_years: int
    signal_count: int
    config: dict[str, Any]
    horizons: list[SmartCandleBacktestHorizonOut]
    warnings: list[str] = Field(default_factory=list)


class PersonalCFOProjectCreate(BaseModel):
    name: str = Field(default="Investment Folder", min_length=1, max_length=160)


class PersonalCFOMessageOut(BaseModel):
    id: int
    role: str
    content: str
    phase: int | None = None
    created_at: datetime


class PersonalCFOFileOut(BaseModel):
    id: int
    path: str
    kind: str
    content: str
    created_at: datetime
    updated_at: datetime


class PersonalCFOUploadOut(BaseModel):
    id: int
    file_name: str
    file_type: str
    row_count: int
    created_at: datetime


class PersonalCFOProjectOut(BaseModel):
    id: int
    name: str
    status: str
    current_phase: int
    phase_progress: dict[str, Any] = Field(default_factory=dict)
    phase_complete: bool = False
    can_generate_one_pager: bool = False
    one_pager_generated: bool = False
    refinement_used: bool = False
    last_exported_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[PersonalCFOMessageOut] = Field(default_factory=list)
    files: list[PersonalCFOFileOut] = Field(default_factory=list)
    uploads: list[PersonalCFOUploadOut] = Field(default_factory=list)


class PersonalCFOMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=6000)
    model: str = Field(default="gpt-5.4", min_length=1, max_length=200)
    ollama_base_url: str | None = Field(default=None, max_length=200)


class PersonalCFOGenerateRequest(BaseModel):
    model: str = Field(default="gpt-5.4", min_length=1, max_length=200)
    ollama_base_url: str | None = Field(default=None, max_length=200)


class PersonalCFORefineRequest(BaseModel):
    feedback: str = Field(min_length=1, max_length=6000)
    model: str = Field(default="gpt-5.4", min_length=1, max_length=200)
    ollama_base_url: str | None = Field(default=None, max_length=200)


class PersonalCFOFileUpdate(BaseModel):
    content: str = Field(max_length=200000)


class PersonalCFOUploadIn(BaseModel):
    file_name: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=500000)


class PersonalCFODashboardOut(BaseModel):
    project_id: int
    files_count: int
    uploads_count: int
    message_count: int
    cash_trend: list[dict[str, Any]] = Field(default_factory=list)
    pnl_summary: dict[str, Any] = Field(default_factory=dict)
    exposures: list[dict[str, Any]] = Field(default_factory=list)
    memory_timeline: list[str] = Field(default_factory=list)
    open_flags: list[str] = Field(default_factory=list)


class IndexOut(BaseModel):
    symbol: str
    name: str
    provider: str
    benchmark: str
    inception_date: date
    holdings_count: int
    source_url: str


class PortfolioCreate(BaseModel):
    name: str = Field(default="Direct Index Portfolio", min_length=1, max_length=120)
    index_symbol: str = Field(default="XLG", min_length=1, max_length=16)
    starting_value: float = Field(default=100_000, gt=0)


class PortfolioOut(BaseModel):
    id: int
    name: str
    index_symbol: str
    starting_value: float
    cash: float
    exclusions: list[str]


class ExclusionIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    reason: str | None = Field(default=None, max_length=255)


class GenerateTradesRequest(BaseModel):
    as_of_date: date | None = None
    enable_tlh: bool = True
    tlh_mode: Literal["conservative", "moderate", "aggressive"] = "aggressive"
    direct_index_model: Literal["risk_score", "threshold_throttle", "peer_basket", "completion_etf"] = "risk_score"


class TradeOut(BaseModel):
    id: int | None = None
    trade_date: date
    action: str
    symbol: str
    shares: float
    price: float
    notional: float
    reason: str
    harvested_loss: float = 0
    realized_gain_loss: float = 0
    tracking_impact: float = 0
    wash_sale_status: str = "cleared"
    notes: str | None = None

    model_config = {"from_attributes": True}


class TradeGenerationOut(BaseModel):
    tlh_mode: str
    direct_index_model: str
    trades: list[TradeOut]
    tracking_score: float
    tracking_difference: float
    cap_used: int
    cap_remaining: int
    dropped_tlh_candidates: int
    skipped_tax_loss_value: float
    warnings: list[str]


class BacktestRequest(BaseModel):
    index_symbol: str = Field(default="XLG", min_length=1, max_length=16)
    year: int = Field(ge=2023, le=2026)
    starting_value: float = Field(default=100_000, gt=0)
    exclusions: list[str] = Field(default_factory=list)
    estimated_tax_rate: float = Field(default=0.35, ge=0, le=0.60)
    tlh_mode: Literal["conservative", "moderate", "aggressive"] = "aggressive"
    direct_index_model: Literal["risk_score", "threshold_throttle", "peer_basket", "completion_etf"] = "risk_score"


class BacktestOut(BaseModel):
    index_symbol: str
    year: int
    tlh_mode: str
    direct_index_model: str
    starting_value: float
    ending_value: float
    benchmark_value: float
    portfolio_profit: float
    portfolio_return: float
    benchmark_profit: float
    benchmark_return: float
    excess_profit: float
    tracking_difference: float
    tracking_error: float
    harvested_losses: float
    realized_gains: float
    realized_losses: float
    net_realized_gain_loss: float
    estimated_tax_rate: float
    estimated_tax_savings: float
    estimated_tax_liability: float
    estimated_net_tax_impact: float
    tax_adjusted_ending_value: float
    tax_adjusted_profit: float
    tax_adjusted_excess_profit: float
    is_profitable: bool
    is_tax_adjusted_profitable: bool
    beats_benchmark_after_tax: bool
    profitability_summary: str
    trade_count: int
    tlh_trade_count: int
    cap_used: int
    cap_remaining: int
    dropped_tlh_candidates: int
    skipped_tax_loss_value: float
    coverage_label: str
    warnings: list[str]
    trades: list[TradeOut]


class DirectIndexModelOut(BaseModel):
    id: str
    label: str
    rank: int
    executable: bool
    summary: str
    best_for: str
    source_support: list[str]


class ModelComparisonRequest(BaseModel):
    index_symbol: str = Field(default="XLG", min_length=1, max_length=16)
    years: list[int] = Field(default_factory=lambda: [2023, 2024, 2025])
    starting_value: float = Field(default=100_000, gt=0)
    exclusions: list[str] = Field(default_factory=list)
    estimated_tax_rate: float = Field(default=0.35, ge=0, le=0.60)
    tlh_mode: Literal["conservative", "moderate", "aggressive"] = "aggressive"


class ModelComparisonRow(BaseModel):
    direct_index_model: str
    model_label: str
    year: int
    available: bool
    coverage_label: str
    harvested_losses: float
    tracking_difference: float
    tracking_error: float
    trade_count: int
    cap_used: int
    cap_remaining: int
    tax_adjusted_profit: float
    warnings: list[str]


class ModelComparisonOut(BaseModel):
    index_symbol: str
    models: list[DirectIndexModelOut]
    rows: list[ModelComparisonRow]
    recommended_model: str | None = None
    recommended_model_label: str | None = None
    recommendation: str


class PortfolioInitializationRequest(BaseModel):
    as_of_date: date | None = None


class PortfolioInitializationOut(BaseModel):
    portfolio: PortfolioOut
    as_of_date: date
    seeded_positions: int
    invested_value: float
    warnings: list[str]


class PortfolioImportHoldingIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    name: str = Field(default="", max_length=255)
    sector: str | None = Field(default=None, max_length=100)
    shares: float = Field(gt=0)
    price: float = Field(gt=0)
    market_value: float | None = Field(default=None, gt=0)
    as_of_date: date | None = None


class PortfolioImportTaxLotIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    acquisition_date: date
    shares: float = Field(gt=0)
    cost_basis_per_share: float = Field(gt=0)


class PortfolioImportRequest(BaseModel):
    name: str = Field(default="Imported portfolio", min_length=1, max_length=120)
    index_symbol: str = Field(default="XLG", min_length=1, max_length=16)
    cash: float = Field(default=0, ge=0)
    holdings: list[PortfolioImportHoldingIn] = Field(default_factory=list)
    tax_lots: list[PortfolioImportTaxLotIn] = Field(default_factory=list)


class PortfolioImportOut(BaseModel):
    portfolio: PortfolioOut
    imported_positions: int
    imported_tax_lots: int
    imported_value: float
    warnings: list[str]


class PortfolioAnalyzerHoldingIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    shares: float = Field(gt=0)
    cost_basis_per_share: float = Field(ge=0)


class PortfolioAnalyzerRequest(BaseModel):
    holdings: list[PortfolioAnalyzerHoldingIn] = Field(default_factory=list)
    min_weight_percent: float = Field(default=1, ge=0, le=100)
    as_of_date: date | None = None


class PortfolioAnalyzerHoldingOut(BaseModel):
    symbol: str
    shares: float
    price: float
    market_value: float
    weight: float
    cost_basis_per_share: float
    cost_basis: float
    unrealized_gain_loss: float
    unrealized_gain_loss_pct: float
    forward_pe: float | None = None
    forward_pe_5y_avg: float | None = None
    forward_pe_10y_avg: float | None = None
    valuation_signal: str
    valuation_signal_label: str
    data_source: str
    warning: str | None = None


class PortfolioAnalyzerOut(BaseModel):
    as_of_date: date
    min_weight_percent: float
    total_market_value: float
    total_cost_basis: float
    unrealized_gain_loss: float
    unrealized_gain_loss_pct: float
    analyzed_holding_count: int
    hidden_holding_count: int
    holdings: list[PortfolioAnalyzerHoldingOut]
    warnings: list[str]


class PortfolioSyncStatusOut(BaseModel):
    provider: str = "snaptrade"
    configured: bool
    connected: bool
    account_count: int = 0
    holding_count: int = 0
    last_synced_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)


class PortfolioSyncProviderCredentialIn(BaseModel):
    client_id: str = Field(min_length=1, max_length=160)
    consumer_key: str = Field(min_length=1, max_length=2048)


class PortfolioSyncProviderCredentialOut(BaseModel):
    provider: str = "snaptrade"
    configured: bool
    source: str = "none"
    client_id: str | None = None
    consumer_key_fingerprint: str | None = None
    updated_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)


class PortfolioSyncConnectOut(BaseModel):
    provider: str = "snaptrade"
    configured: bool
    connected: bool
    redirect_url: str | None = None
    provider_user_id: str | None = None
    warnings: list[str] = Field(default_factory=list)


class PortfolioSyncAccountOut(BaseModel):
    account_id: str
    account_name: str
    brokerage_name: str
    authorization_id: str | None = None
    account_type: str | None = None
    status: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class PortfolioSyncHoldingOut(BaseModel):
    symbol: str
    shares: float
    price: float
    market_value: float
    weight: float = 0
    cost_basis_per_share: float
    cost_basis: float
    unrealized_gain_loss: float
    unrealized_gain_loss_pct: float = 0
    account_id: str | None = None
    account_name: str
    brokerage_name: str
    sector: str | None = None
    data_source: str = "snaptrade"
    provider_symbol_id: str | None = None
    provider_updated_at: datetime | None = None
    warning: str | None = None


class PortfolioSyncSectorExposureOut(BaseModel):
    sector: str
    market_value: float
    weight: float
    holding_count: int


class PortfolioSyncSummaryOut(BaseModel):
    status: PortfolioSyncStatusOut
    synced_at: datetime | None = None
    total_market_value: float = 0
    total_cost_basis: float = 0
    unrealized_gain_loss: float = 0
    unrealized_gain_loss_pct: float = 0
    account_count: int = 0
    holding_count: int = 0
    accounts: list[PortfolioSyncAccountOut] = Field(default_factory=list)
    holdings: list[PortfolioSyncHoldingOut] = Field(default_factory=list)
    top_holdings: list[PortfolioSyncHoldingOut] = Field(default_factory=list)
    sector_exposures: list[PortfolioSyncSectorExposureOut] = Field(default_factory=list)
    concentration_warnings: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RSIPlaybookChartPointOut(BaseModel):
    date: date
    close: float
    ema8: float | None = None
    ema21: float | None = None
    ema55: float | None = None
    rsi: float | None = None


class RSIPlaybookSignalOut(BaseModel):
    symbol: str
    name: str
    sector: str
    sources: list[str]
    group: str
    price: float
    as_of_date: date | None = None
    rsi: float | None = None
    level: str
    action: str
    action_tone: str
    summary: str
    trend: str
    ema8: float | None = None
    ema21: float | None = None
    ema55: float | None = None
    distance_to_ema21: float | None = None
    window_return_3m: float | None = None
    portfolio_weight: float | None = None
    data_source: str
    warnings: list[str] = Field(default_factory=list)
    chart: list[RSIPlaybookChartPointOut] = Field(default_factory=list)


class RSIPlaybookScanOut(BaseModel):
    scanned_at: datetime
    source_summary: str
    universe_count: int
    portfolio_symbol_count: int
    wheel_symbol_count: int
    signals: list[RSIPlaybookSignalOut]
    warnings: list[str] = Field(default_factory=list)


class DataSyncOut(BaseModel):
    status: str
    synced_indices: list[str]
    warning: str | None = None


class MajorIndexOut(BaseModel):
    symbol: str
    name: str
    benchmark: str
    category: str


class HighYieldBacktestOut(BaseModel):
    evaluated_weeks: int
    buy_signals: int
    hit_rate_4w: float | None = None
    average_forward_return_4w: float | None = None
    last_buy_date: date | None = None
    recent_buy_dates: list[date]


class HighYieldSignalOut(BaseModel):
    action: Literal["BUY", "HOLD"]
    signal_date: date | None = None
    last_close: float | None = None
    reason: str
    reasons: list[str]
    risk_state: str
    confidence: float
    limited_history: bool
    data_points: int
    backtest: HighYieldBacktestOut


class HighYieldFundOut(BaseModel):
    symbol: str
    name: str
    issuer: str
    exposure: str
    strategy: str
    distribution_frequency: str
    source_url: str
    risk_note: str
    data_source: str
    last_price_date: date | None = None
    cached_at: datetime | None = None
    warnings: list[str]
    signal: HighYieldSignalOut


class MarketPriceBarOut(BaseModel):
    date: date
    close: float
    adjusted_close: float
    dividend: float = 0
    source: str


class MarketHistoryOut(BaseModel):
    symbol: str
    name: str
    benchmark: str
    category: str
    requested_start_date: date
    requested_end_date: date
    start_date: date | None = None
    end_date: date | None = None
    bars: list[MarketPriceBarOut]
    warnings: list[str]


class OptionStrategyChecklistItemOut(BaseModel):
    id: str
    label: str
    passed: bool
    actual: str | float | int | None = None
    expected: str | float | int | None = None
    detail: str | None = None


class OptionStrategySignalCandidateOut(BaseModel):
    id: int | str | None = None
    symbol: str
    action: str
    status: str
    sector: str | None = None
    underlying_price: float
    strike: float
    expiration: date
    dte: int
    delta: float
    iv: float
    iv_rank: float | None = None
    bb_percent: float | None = None
    earnings_date: date | None = None
    earnings_days: int | None = None
    spread_pct: float | None = None
    bid: float
    ask: float
    mid: float
    open_interest: int
    premium_yield: float
    collateral: float
    alert_target_price: float
    exposure_usage: float | None = None
    score: float | None = None
    deep_dive_rank: int | None = None
    deep_dive_summary: str | None = None
    if_expires_return: float | None = None
    if_assigned_basis: float | None = None
    provider: str | None = None
    checklist: list[OptionStrategyChecklistItemOut] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    created_at: datetime


class OptionStrategyConfigOut(BaseModel):
    tickers: list[str]
    universe_groups: list[str] = Field(default_factory=list)
    scan_cadence: str = "daily"
    account_value: float
    exposure_cap: float
    dte_min: int
    dte_max: int
    rsi_period: int
    rsi_max: float
    ema_periods: list[int]
    min_iv: float
    min_iv_rank: float = 0.40
    min_premium_yield: float
    target_delta_min: float = 0.20
    target_delta_max: float = 0.35
    bb_percent_max: float = 0.75
    earnings_exclusion_days: int = 7
    min_open_interest: int = 100
    max_spread_pct: float = 0.15
    profit_take_pct: float = 0.50
    single_name_cap: float = 0.10
    sector_cap: float = 0.25
    webhook_url: str | None = None
    updated_at: datetime | None = None


class OptionStrategyConfigUpdate(BaseModel):
    tickers: list[str] | None = None
    account_value: float | None = Field(default=None, gt=0)
    exposure_cap: float | None = Field(default=None, gt=0, le=1)
    dte_min: int | None = Field(default=None, ge=1, le=365)
    dte_max: int | None = Field(default=None, ge=1, le=365)
    rsi_period: int | None = Field(default=None, ge=2, le=100)
    rsi_max: float | None = Field(default=None, ge=1, le=100)
    ema_periods: list[int] | None = None
    min_iv: float | None = Field(default=None, ge=0, le=5)
    min_premium_yield: float | None = Field(default=None, ge=0, le=1)
    webhook_url: str | None = Field(default=None, max_length=512)


class OptionStrategyWheelPositionOut(BaseModel):
    id: int | str | None = None
    symbol: str
    status: str
    option_type: str
    strike: float
    expiration: date
    contracts: int
    entry_premium: float
    current_price: float | None = None
    alert_target_price: float | None = None
    collateral: float | None = None
    created_at: datetime
    updated_at: datetime | None = None


class OptionStrategyAlertEventOut(BaseModel):
    id: int | str | None = None
    symbol: str
    kind: str
    status: str
    message: str
    target_price: float | None = None
    current_price: float | None = None
    created_at: datetime


class OptionStrategyScanResultOut(BaseModel):
    scan_run_id: int | str | None = None
    scanned_at: datetime
    data_source: str | None = None
    signals: list[OptionStrategySignalCandidateOut]
    warnings: list[str] = Field(default_factory=list)


class OptionStrategyUniverseItemOut(BaseModel):
    symbol: str
    name: str
    sector: str
    group: str


class OptionStrategyUniverseOut(BaseModel):
    items: list[OptionStrategyUniverseItemOut]
    groups: list[str]
    count: int


class OptionStrategyPositionEventIn(BaseModel):
    event: Literal["accepted_put", "assigned", "closed"] | str
    signal_candidate_id: int | str | None = None
    candidate: dict[str, Any] | None = None
    position_id: int | str | None = None
    position: dict[str, Any] | None = None


class ThirteenFSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=160)


class ThirteenFWatchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=160)
    cik: str | None = Field(default=None, min_length=1, max_length=10)
    manager_name: str | None = Field(default=None, max_length=255)


class ThirteenFManagerCandidateOut(BaseModel):
    cik: str
    manager_name: str
    match_source: str
    latest_filing_date: date | None = None
    latest_report_period: date | None = None


class ThirteenFSearchOut(BaseModel):
    query: str
    candidates: list[ThirteenFManagerCandidateOut]
    warning: str | None = None


class ThirteenFWatchOut(BaseModel):
    id: int
    query: str
    manager_name: str
    cik: str
    status: str
    latest_form: str | None = None
    latest_accession_number: str | None = None
    latest_filing_date: date | None = None
    latest_report_period: date | None = None
    latest_primary_document_url: str | None = None
    latest_info_table_url: str | None = None
    last_checked_at: datetime | None = None
    next_check_at: datetime | None = None
    last_downloaded_at: datetime | None = None
    warning: str | None = None
    download_url: str | None = None

    model_config = {"from_attributes": True}


class ThirteenFCacheOut(BaseModel):
    watch_id: int
    years: int
    cached_filings: int
    cached_holdings: int
    priced_holdings: int
    warnings: list[str]


class ThirteenFHoldingOut(BaseModel):
    symbol: str | None = None
    issuer_name: str
    value: float
    shares: float
    weight: float


class ThirteenFPerformancePeriodOut(BaseModel):
    report_period: date
    filing_date: date
    start_date: date
    end_date: date
    starting_value: float
    ending_value: float
    return_pct: float
    benchmark_return_pct: float
    holdings_count: int
    priced_holdings_count: int
    top_holdings: list[ThirteenFHoldingOut]


class ThirteenFPerformanceOut(BaseModel):
    watch_id: int
    manager_name: str
    cik: str
    years: int
    starting_value: float
    ending_value: float
    total_return: float
    annualized_return: float
    benchmark_symbol: str
    benchmark_ending_value: float
    benchmark_total_return: float
    cached_filings: int
    cached_holdings: int
    priced_holdings: int
    periods: list[ThirteenFPerformancePeriodOut]
    warnings: list[str]


class AdvisorClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=320)
    household_notes: str | None = Field(default=None, max_length=2000)


class AdvisorClientOut(BaseModel):
    id: int
    name: str
    email: str | None = None
    household_notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ImportedHoldingIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    name: str = Field(default="", max_length=255)
    sector: str | None = Field(default=None, max_length=100)
    shares: float = Field(gt=0)
    price: float = Field(gt=0)
    market_value: float | None = Field(default=None, gt=0)
    as_of_date: date | None = None


class ImportedTaxLotIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    acquisition_date: date
    shares: float = Field(gt=0)
    cost_basis_per_share: float = Field(gt=0)


class AccountImportRequest(BaseModel):
    account_name: str = Field(default="Taxable account", min_length=1, max_length=160)
    account_type: str = Field(default="taxable", min_length=1, max_length=80)
    taxable: bool = True
    custodian: str | None = Field(default=None, max_length=120)
    holdings: list[ImportedHoldingIn] = Field(default_factory=list)
    tax_lots: list[ImportedTaxLotIn] = Field(default_factory=list)


class ImportedHoldingOut(BaseModel):
    symbol: str
    name: str
    sector: str | None = None
    shares: float
    price: float
    market_value: float
    as_of_date: date


class ImportedTaxLotOut(BaseModel):
    symbol: str
    acquisition_date: date
    shares: float
    cost_basis_per_share: float


class AccountOut(BaseModel):
    id: int
    client_id: int
    name: str
    account_type: str
    taxable: bool
    custodian: str | None = None
    imported_at: datetime
    holdings: list[ImportedHoldingOut]
    tax_lots: list[ImportedTaxLotOut]


class EquivalentSecurityGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    symbols: list[str] = Field(min_length=2, max_length=20)


class ClientConstraintIn(BaseModel):
    target_index: str = Field(default="XLG", min_length=1, max_length=16)
    annual_gains_budget: float = Field(default=0, ge=0)
    max_tracking_error: float = Field(default=0.05, ge=0, le=1)
    max_active_share: float = Field(default=0.20, ge=0, le=1)
    estimated_tax_rate: float = Field(default=0.35, ge=0, le=0.60)
    excluded_symbols: list[str] = Field(default_factory=list)
    excluded_sectors: list[str] = Field(default_factory=list)
    household_wash_sale_notes: str | None = Field(default=None, max_length=2000)
    outside_accounts_complete: bool = False
    equivalent_groups: list[EquivalentSecurityGroupIn] = Field(default_factory=list)


class ClientConstraintOut(BaseModel):
    id: int
    target_index: str
    annual_gains_budget: float
    max_tracking_error: float
    max_active_share: float
    estimated_tax_rate: float
    excluded_symbols: list[str]
    excluded_sectors: list[str]
    household_wash_sale_notes: str | None = None
    outside_accounts_complete: bool
    equivalent_groups: list[EquivalentSecurityGroupIn]
    created_at: datetime


class TransitionPlanRequest(BaseModel):
    account_id: int | None = None
    objective: Literal["transition_gradually", "minimize_gains", "harvest_losses"] = "transition_gradually"
    title: str | None = Field(default=None, max_length=180)


class TransitionRecommendationOut(BaseModel):
    stage: str
    action: str
    symbol: str
    shares: float
    price: float
    notional: float
    realized_gain_loss: float
    estimated_tax_impact: float
    reason: str
    wash_sale_status: str
    notes: str


class TransitionPlanOut(BaseModel):
    id: int
    proposal_id: int
    client_id: int
    client_name: str
    account_id: int | None = None
    account_name: str | None = None
    title: str
    status: str
    objective: str
    algorithm_version: str
    target_index: str
    data_source_summary: str
    portfolio_value: float
    target_value: float
    realized_gains: float
    realized_losses: float
    net_realized_gain: float
    estimated_tax_impact: float
    tracking_drift: float
    active_share: float
    turnover: float
    skipped_trade_count: int
    warnings: list[str]
    recommendations: list[TransitionRecommendationOut]
    input_snapshot: dict
    created_at: datetime


# ── Portfolio Diversification ─────────────────────────────────────────────────

class ConcentrationHoldingIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    name: str = Field(default="", max_length=255)
    sector: str | None = Field(default=None, max_length=100)
    shares: float = Field(gt=0)
    price: float = Field(gt=0)


class ConcentrationAnalysisRequest(BaseModel):
    holdings: list[ConcentrationHoldingIn]
    index_symbol: str = Field(default="SCHD", max_length=16)


class SectorGapOut(BaseModel):
    sector: str
    portfolio_weight: float
    index_weight: float
    gap: float


class ConcentrationAnalysisOut(BaseModel):
    hhi: float
    diversification_score: int
    top_holding: str
    top_holding_weight: float
    sector_weights: dict[str, float]
    sector_vs_index: list[SectorGapOut]
    active_share: float
    concentration_warnings: list[str]


class DiversifyBacktestRequest(BaseModel):
    concentrated_symbol: str = Field(min_length=1, max_length=16)
    concentrated_shares: float = Field(gt=0)
    avg_cost_basis: float = Field(gt=0)
    starting_cash: float = Field(default=0.0, ge=0)
    years: list[int] = Field(default_factory=lambda: [2023, 2024, 2025])
    estimated_tax_rate: float = Field(default=0.35, ge=0, le=0.60)
    harvest_threshold: float = Field(default=0.03, ge=0.005, le=0.30)
    alpha_vantage_key: str | None = Field(default=None, description="Alpha Vantage API key for price history")


class DiversifyYearResultOut(BaseModel):
    year: int
    harvested_losses: float
    tax_savings: float
    concentration_pct: float
    hhi: float
    schd_value: float
    concentrated_value: float
    trade_count: int
    data_source: str
    warnings: list[str]


class DiversifyBacktestOut(BaseModel):
    years: list[DiversifyYearResultOut]
    total_harvested_losses: float
    total_tax_savings: float
    immediate_sell_tax_cost: float
    net_tlh_benefit: float
    savings_vs_immediate_sell: float
    tlh_wins: bool
    concentration_start_pct: float
    concentration_end_pct: float
    warnings: list[str]


class CurrentHoldingIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    shares: float = Field(gt=0)
    avg_cost: float = Field(gt=0)
    last_sold_date: date | None = None


class DiversifyRecommendationsRequest(BaseModel):
    concentrated_symbol: str = Field(min_length=1, max_length=16)
    concentrated_shares: float = Field(gt=0)
    avg_cost_basis: float = Field(gt=0)
    current_schd_holdings: list[CurrentHoldingIn] = Field(default_factory=list)
    estimated_tax_rate: float = Field(default=0.35, ge=0, le=0.60)
    harvest_threshold: float = Field(default=0.03, ge=0.005, le=0.30)


class RecommendTradeOut(BaseModel):
    action: str
    symbol: str
    name: str
    shares: float
    estimated_price: float
    notional: float
    reason: str
    harvested_loss: float | None = None


class DiversifyRecommendationsOut(BaseModel):
    as_of_date: str
    harvest_trades: list[RecommendTradeOut]
    replacement_trades: list[RecommendTradeOut]
    concentrated_sell: RecommendTradeOut | None
    total_harvested_loss: float
    net_tax_cost: float
    concentration_before_pct: float
    concentration_after_pct: float
    warnings: list[str]


# ── Sector Rotation Algo ──────────────────────────────────────────────────────

class SectorRotationBacktestRequest(BaseModel):
    starting_capital: float = Field(default=100_000.0, gt=0)
    weighting_method: Literal["equal", "market_weight"] = "equal"


class SectorRotationLiveRequest(BaseModel):
    cash_amount: float = Field(gt=0)
    time_frame: str = Field(default="annual")
    weighting_method: Literal["equal", "market_weight"] = "equal"


class SectorAllocationOut(BaseModel):
    ticker: str
    sector_name: str
    weight: float
    dollar_amount: float
    trailing_eps_beat: float
    forward_eps_beat: float
    composite_score: float


class SectorRotationPeriodSnapshotOut(BaseModel):
    year: int
    sectors_held: list[str]
    sector_weights: dict[str, float]
    period_return_pct: float
    cumulative_value: float
    taxes_paid_period: float
    taxes_paid_cumulative: float
    post_liquidation_value: float
    embedded_tax_liability: float


class SectorRotationScenarioMetricsOut(BaseModel):
    cagr_pretax_pct: float
    cagr_posttax_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    total_taxes_paid: float
    tax_drag_annualized_pct: float
    alpha_vs_spy_pretax_pct: float
    alpha_vs_spy_posttax_pct: float
    total_return_pct: float
    win_rate_vs_benchmark: float
    post_liquidation_value: float
    final_pretax_value: float
    best_year_return_pct: float
    worst_year_return_pct: float


class SectorRotationScenarioResultOut(BaseModel):
    id: str
    name: str
    metrics: SectorRotationScenarioMetricsOut
    period_snapshots: list[SectorRotationPeriodSnapshotOut]


class SectorRotationBacktestOut(BaseModel):
    starting_capital: float
    weighting_method: str = "equal"
    tax_rates: dict[str, float]
    scenarios: list[SectorRotationScenarioResultOut]
    comparison: dict[str, Any]


class SectorRotationLiveOut(BaseModel):
    as_of_year: int
    time_frame: str
    weighting_method: str = "equal"
    allocations: list[SectorAllocationOut]
    sp500_signals: dict[str, Any]
    rebalance_guidance: str


class SectorRotationAcceptedTradeIn(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    sector_name: str = Field(default="", max_length=120)
    target_weight: float = Field(default=0, ge=0)
    target_amount: float = Field(default=0, ge=0)
    shares: float = Field(gt=0)
    cost_basis_per_share: float = Field(gt=0)
    current_price: float = Field(gt=0)
    purchase_date: date


class SectorRotationAcceptedAllocationIn(BaseModel):
    account_type: Literal["taxable", "tax_deferred"] = "taxable"
    time_frame: str = Field(default="annual", max_length=32)
    weighting_method: Literal["equal", "market_weight"] = "equal"
    cash_amount: float = Field(default=0, ge=0)
    as_of_year: int = Field(default=0, ge=0)
    rebalance_date: date | None = None
    rebalance_status: Literal["planned", "completed", "partial", "skipped"] = "planned"
    rebalance_notes: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=1000)
    trades: list[SectorRotationAcceptedTradeIn] = Field(min_length=1)


class SectorRotationAcceptedAllocationUpdate(BaseModel):
    rebalance_date: date | None = None
    rebalance_status: Literal["planned", "completed", "partial", "skipped"] = "planned"
    rebalance_notes: str | None = Field(default=None, max_length=1000)


class SectorRotationAcceptedTradeOut(BaseModel):
    id: int
    ticker: str
    sector_name: str
    target_weight: float
    target_amount: float
    shares: float
    cost_basis_per_share: float
    current_price: float
    purchase_date: date
    market_value: float
    cost_basis: float
    gain_loss: float


class SectorRotationAcceptedAllocationOut(BaseModel):
    id: int
    account_type: str
    time_frame: str
    weighting_method: str
    cash_amount: float
    as_of_year: int
    rebalance_date: date | None = None
    rebalance_status: str = "planned"
    rebalance_notes: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    trades: list[SectorRotationAcceptedTradeOut]


class SimulatedPortfolioTradeIn(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    name: str = Field(default="", max_length=160)
    sleeve: Literal["income", "growth"] | str = Field(max_length=32)
    category: str = Field(default="", max_length=80)
    yield_pct: float = Field(default=0, ge=0)
    target_weight: float = Field(default=0, ge=0)
    target_amount: float = Field(default=0, ge=0)
    shares: float = Field(gt=0)
    cost_basis_per_share: float = Field(gt=0)
    current_price: float = Field(gt=0)
    purchase_date: date


class SimulatedPortfolioIn(BaseModel):
    name: str = Field(default="$420K Master Portfolio Plan", min_length=1, max_length=160)
    cash_amount: float = Field(gt=0)
    target_value: float = Field(default=420_000, gt=0)
    notes: str | None = Field(default=None, max_length=1000)
    trades: list[SimulatedPortfolioTradeIn] = Field(min_length=1)


class SimulatedPortfolioPriceIn(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    current_price: float = Field(gt=0)


class SimulatedPortfolioPriceUpdate(BaseModel):
    prices: list[SimulatedPortfolioPriceIn] = Field(min_length=1)


class SimulatedPortfolioTradeOut(BaseModel):
    id: int
    ticker: str
    name: str
    sleeve: str
    category: str
    yield_pct: float
    target_weight: float
    target_amount: float
    shares: float
    cost_basis_per_share: float
    current_price: float
    purchase_date: date
    market_value: float
    cost_basis: float
    gain_loss: float
    return_pct: float
    annual_income: float


class SimulatedPortfolioOut(BaseModel):
    id: int
    name: str
    cash_amount: float
    target_value: float
    cost_basis: float
    market_value: float
    gain_loss: float
    return_pct: float
    annual_income: float
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    trades: list[SimulatedPortfolioTradeOut]


class YahooQuoteOut(BaseModel):
    symbol: str
    price: float | None = None
    last: float | None = None
    close: float | None = None
    source: str
    warning: str | None = None


class YahooQuotesOut(BaseModel):
    tickers: list[YahooQuoteOut]


class SelectionHistoryRowOut(BaseModel):
    year: int
    selected_sectors: list[str]
    sector_weights: dict[str, float] = Field(default_factory=dict)
    algo_return_pct: float
    spy_return_pct: float
    delta_pct: float
    key_signal: str
    weighting_method: str = "equal"
