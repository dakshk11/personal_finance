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


class DataSyncOut(BaseModel):
    status: str
    synced_indices: list[str]
    warning: str | None = None


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
