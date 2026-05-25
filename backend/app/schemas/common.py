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


class AIAdvisorRetirementRunRequest(BaseModel):
    module_id: str = Field(min_length=1, max_length=80)
    model: Literal["gpt-5.5", "gpt-5.4", "gpt-5.4-mini"] = "gpt-5.4"
    inputs: dict[str, Any] = Field(default_factory=dict)


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


class EarningsAgentRunRequest(BaseModel):
    query: str = Field(min_length=1, max_length=160)
    model: Literal["gpt-5.5", "gpt-5.4", "gpt-5.4-mini"] = "gpt-5.4"


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
    model: Literal["gpt-5.5", "gpt-5.4", "gpt-5.4-mini"] = "gpt-5.4"


class PersonalCFOGenerateRequest(BaseModel):
    model: Literal["gpt-5.5", "gpt-5.4", "gpt-5.4-mini"] = "gpt-5.4"


class PersonalCFORefineRequest(BaseModel):
    feedback: str = Field(min_length=1, max_length=6000)
    model: Literal["gpt-5.5", "gpt-5.4", "gpt-5.4-mini"] = "gpt-5.4"


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
