export function apiUrl() {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return "http://127.0.0.1:8000";
}

export type IndexDefinition = {
  symbol: string;
  name: string;
  provider: string;
  benchmark: string;
  inception_date: string;
  holdings_count: number;
  source_url: string;
};

export type Portfolio = {
  id: number;
  name: string;
  index_symbol: string;
  starting_value: number;
  cash: number;
  exclusions: string[];
};

export type Trade = {
  id?: number | null;
  trade_date: string;
  action: string;
  symbol: string;
  shares: number;
  price: number;
  notional: number;
  reason: string;
  harvested_loss: number;
  realized_gain_loss: number;
  tracking_impact: number;
  wash_sale_status: string;
  notes?: string | null;
};

export type TradeGeneration = {
  tlh_mode: string;
  direct_index_model: string;
  trades: Trade[];
  tracking_score: number;
  tracking_difference: number;
  cap_used: number;
  cap_remaining: number;
  dropped_tlh_candidates: number;
  skipped_tax_loss_value: number;
  warnings: string[];
};

export type BacktestResult = {
  index_symbol: string;
  year: number;
  tlh_mode: string;
  direct_index_model: string;
  starting_value: number;
  ending_value: number;
  benchmark_value: number;
  portfolio_profit: number;
  portfolio_return: number;
  benchmark_profit: number;
  benchmark_return: number;
  excess_profit: number;
  tracking_difference: number;
  tracking_error: number;
  harvested_losses: number;
  realized_gains: number;
  realized_losses: number;
  net_realized_gain_loss: number;
  estimated_tax_rate: number;
  estimated_tax_savings: number;
  estimated_tax_liability: number;
  estimated_net_tax_impact: number;
  tax_adjusted_ending_value: number;
  tax_adjusted_profit: number;
  tax_adjusted_excess_profit: number;
  is_profitable: boolean;
  is_tax_adjusted_profitable: boolean;
  beats_benchmark_after_tax: boolean;
  profitability_summary: string;
  trade_count: number;
  tlh_trade_count: number;
  cap_used: number;
  cap_remaining: number;
  dropped_tlh_candidates: number;
  skipped_tax_loss_value: number;
  coverage_label: string;
  warnings: string[];
  trades: Trade[];
};

export type DirectIndexModel = {
  id: string;
  label: string;
  rank: number;
  executable: boolean;
  summary: string;
  best_for: string;
  source_support: string[];
};

export type ModelComparisonRow = {
  direct_index_model: string;
  model_label: string;
  year: number;
  available: boolean;
  coverage_label: string;
  harvested_losses: number;
  tracking_difference: number;
  tracking_error: number;
  trade_count: number;
  cap_used: number;
  cap_remaining: number;
  tax_adjusted_profit: number;
  warnings: string[];
};

export type ModelComparison = {
  index_symbol: string;
  models: DirectIndexModel[];
  rows: ModelComparisonRow[];
  recommended_model: string | null;
  recommended_model_label: string | null;
  recommendation: string;
};

export type PortfolioInitialization = {
  portfolio: Portfolio;
  as_of_date: string;
  seeded_positions: number;
  invested_value: number;
  warnings: string[];
};

export type PortfolioImportHoldingInput = {
  symbol: string;
  name?: string;
  sector?: string | null;
  shares: number;
  price: number;
  market_value?: number;
  as_of_date?: string;
};

export type PortfolioImportTaxLotInput = {
  symbol: string;
  acquisition_date: string;
  shares: number;
  cost_basis_per_share: number;
};

export type PortfolioImportPayload = {
  name: string;
  index_symbol: string;
  cash: number;
  holdings: PortfolioImportHoldingInput[];
  tax_lots: PortfolioImportTaxLotInput[];
};

export type PortfolioImportResult = {
  portfolio: Portfolio;
  imported_positions: number;
  imported_tax_lots: number;
  imported_value: number;
  warnings: string[];
};

export type PortfolioAnalyzerHoldingInput = {
  symbol: string;
  shares: number;
  cost_basis_per_share: number;
};

export type PortfolioAnalyzerHolding = {
  symbol: string;
  shares: number;
  price: number;
  market_value: number;
  weight: number;
  cost_basis_per_share: number;
  cost_basis: number;
  unrealized_gain_loss: number;
  unrealized_gain_loss_pct: number;
  forward_pe?: number | null;
  forward_pe_5y_avg?: number | null;
  forward_pe_10y_avg?: number | null;
  valuation_signal: "below_10y_average" | "below_5y_average" | "at_or_above_average" | "unknown";
  valuation_signal_label: string;
  data_source: string;
  warning?: string | null;
};

export type PortfolioAnalyzerResult = {
  as_of_date: string;
  min_weight_percent: number;
  total_market_value: number;
  total_cost_basis: number;
  unrealized_gain_loss: number;
  unrealized_gain_loss_pct: number;
  analyzed_holding_count: number;
  hidden_holding_count: number;
  holdings: PortfolioAnalyzerHolding[];
  warnings: string[];
};

export type PortfolioSyncStatus = {
  provider: "snaptrade" | string;
  configured: boolean;
  connected: boolean;
  account_count: number;
  holding_count: number;
  last_synced_at?: string | null;
  warnings: string[];
};

export type PortfolioSyncProviderCredentialStatus = {
  provider: "snaptrade" | string;
  configured: boolean;
  source: "environment" | "database" | "none" | string;
  client_id?: string | null;
  consumer_key_fingerprint?: string | null;
  updated_at?: string | null;
  warnings: string[];
};

export type PortfolioSyncProviderCredentialPayload = {
  client_id: string;
  consumer_key: string;
};

export type PortfolioSyncConnect = {
  provider: "snaptrade" | string;
  configured: boolean;
  connected: boolean;
  redirect_url?: string | null;
  provider_user_id?: string | null;
  warnings: string[];
};

export type PortfolioSyncAccount = {
  account_id: string;
  account_name: string;
  brokerage_name: string;
  authorization_id?: string | null;
  account_type?: string | null;
  status?: string | null;
  raw: Record<string, unknown>;
};

export type PortfolioSyncHolding = {
  symbol: string;
  shares: number;
  price: number;
  market_value: number;
  weight: number;
  cost_basis_per_share: number;
  cost_basis: number;
  unrealized_gain_loss: number;
  unrealized_gain_loss_pct: number;
  account_id?: string | null;
  account_name: string;
  brokerage_name: string;
  sector?: string | null;
  data_source: string;
  provider_symbol_id?: string | null;
  provider_updated_at?: string | null;
  warning?: string | null;
};

export type PortfolioSyncSectorExposure = {
  sector: string;
  market_value: number;
  weight: number;
  holding_count: number;
};

export type PortfolioSyncSummary = {
  status: PortfolioSyncStatus;
  synced_at?: string | null;
  total_market_value: number;
  total_cost_basis: number;
  unrealized_gain_loss: number;
  unrealized_gain_loss_pct: number;
  account_count: number;
  holding_count: number;
  accounts: PortfolioSyncAccount[];
  holdings: PortfolioSyncHolding[];
  top_holdings: PortfolioSyncHolding[];
  sector_exposures: PortfolioSyncSectorExposure[];
  concentration_warnings: string[];
  warnings: string[];
};

export type RSIPlaybookChartPoint = {
  date: string;
  close: number;
  ema8?: number | null;
  ema21?: number | null;
  ema55?: number | null;
  rsi?: number | null;
};

export type RSIPlaybookSignal = {
  symbol: string;
  name: string;
  sector: string;
  sources: string[];
  group: string;
  price: number;
  as_of_date?: string | null;
  rsi?: number | null;
  level: string;
  action: string;
  action_tone: "cash" | "puts_far_otm" | "puts_atm" | "stock" | "leap" | "watch" | string;
  summary: string;
  trend: string;
  ema8?: number | null;
  ema21?: number | null;
  ema55?: number | null;
  distance_to_ema21?: number | null;
  window_return_3m?: number | null;
  portfolio_weight?: number | null;
  data_source: string;
  warnings: string[];
  chart: RSIPlaybookChartPoint[];
};

export type RSIPlaybookScan = {
  scanned_at: string;
  source_summary: string;
  universe_count: number;
  portfolio_symbol_count: number;
  wheel_symbol_count: number;
  signals: RSIPlaybookSignal[];
  warnings: string[];
};

export type EarningsAgentModel = AIAdvisorRetirementRunRequest["model"];

export type EarningsAgentSource = {
  source_type: "sec" | "motley" | string;
  title: string;
  status: "found" | "missing" | "partial" | string;
  url?: string | null;
  document_type?: string | null;
  filing_date?: string | null;
  excerpt?: string | null;
  warning?: string | null;
};

export type EarningsAgentMetric = {
  name: string;
  value: string;
  context?: string | null;
};

export type EarningsAgentDigest = {
  executive_summary: string;
  top_takeaways: string[];
  financial_metrics: EarningsAgentMetric[];
  management_tone: string;
  risks: string[];
  deep_dive_questions: string[];
  source_notes: string[];
  raw_markdown?: string | null;
};

export type EarningsAgentRunSummary = {
  id: number;
  ticker: string;
  company_name: string;
  created_at: string;
  source_status: string;
};

export type EarningsAgentRun = EarningsAgentRunSummary & {
  query: string;
  cik?: string | null;
  model: EarningsAgentModel | string;
  sources: EarningsAgentSource[];
  digest: EarningsAgentDigest;
  warnings: string[];
  usage: Record<string, unknown>;
};

export type MajorIndex = {
  symbol: string;
  name: string;
  benchmark: string;
  category: string;
};

export type MarketPriceBar = {
  date: string;
  close: number;
  adjusted_close: number;
  dividend: number;
  source: string;
};

export type MarketHistory = {
  symbol: string;
  name: string;
  benchmark: string;
  category: string;
  requested_start_date: string;
  requested_end_date: string;
  start_date?: string | null;
  end_date?: string | null;
  bars: MarketPriceBar[];
  warnings: string[];
};

export type HighYieldBacktest = {
  evaluated_weeks: number;
  buy_signals: number;
  hit_rate_4w?: number | null;
  average_forward_return_4w?: number | null;
  last_buy_date?: string | null;
  recent_buy_dates: string[];
};

export type HighYieldSignal = {
  action: "BUY" | "HOLD";
  signal_date?: string | null;
  last_close?: number | null;
  reason: string;
  reasons: string[];
  risk_state: string;
  confidence: number;
  limited_history: boolean;
  data_points: number;
  backtest: HighYieldBacktest;
};

export type HighYieldFund = {
  symbol: string;
  name: string;
  issuer: string;
  exposure: string;
  strategy: string;
  distribution_frequency: string;
  source_url: string;
  risk_note: string;
  data_source: string;
  last_price_date?: string | null;
  cached_at?: string | null;
  warnings: string[];
  signal: HighYieldSignal;
};

export type ThirteenFManagerCandidate = {
  cik: string;
  manager_name: string;
  match_source: string;
  latest_filing_date?: string | null;
  latest_report_period?: string | null;
};

export type ThirteenFSearchResult = {
  query: string;
  candidates: ThirteenFManagerCandidate[];
  warning?: string | null;
};

export type ThirteenFWatch = {
  id: number;
  query: string;
  manager_name: string;
  cik: string;
  status: string;
  latest_form?: string | null;
  latest_accession_number?: string | null;
  latest_filing_date?: string | null;
  latest_report_period?: string | null;
  latest_primary_document_url?: string | null;
  latest_info_table_url?: string | null;
  last_checked_at?: string | null;
  next_check_at?: string | null;
  last_downloaded_at?: string | null;
  warning?: string | null;
  download_url?: string | null;
};

export type ThirteenFHolding = {
  symbol?: string | null;
  issuer_name: string;
  value: number;
  shares: number;
  weight: number;
};

export type ThirteenFPerformancePeriod = {
  report_period: string;
  filing_date: string;
  start_date: string;
  end_date: string;
  starting_value: number;
  ending_value: number;
  return_pct: number;
  benchmark_return_pct: number;
  holdings_count: number;
  priced_holdings_count: number;
  top_holdings: ThirteenFHolding[];
};

export type ThirteenFPerformance = {
  watch_id: number;
  manager_name: string;
  cik: string;
  years: number;
  starting_value: number;
  ending_value: number;
  total_return: number;
  annualized_return: number;
  benchmark_symbol: string;
  benchmark_ending_value: number;
  benchmark_total_return: number;
  cached_filings: number;
  cached_holdings: number;
  priced_holdings: number;
  periods: ThirteenFPerformancePeriod[];
  warnings: string[];
};

export type AdvisorClient = {
  id: number;
  name: string;
  email?: string | null;
  household_notes?: string | null;
  created_at: string;
};

export type ImportedHoldingInput = {
  symbol: string;
  name?: string;
  sector?: string | null;
  shares: number;
  price: number;
  market_value?: number;
  as_of_date?: string;
};

export type ImportedTaxLotInput = {
  symbol: string;
  acquisition_date: string;
  shares: number;
  cost_basis_per_share: number;
};

export type AccountImportPayload = {
  account_name: string;
  account_type: string;
  taxable: boolean;
  custodian?: string | null;
  holdings: ImportedHoldingInput[];
  tax_lots: ImportedTaxLotInput[];
};

export type ImportedAccount = {
  id: number;
  client_id: number;
  name: string;
  account_type: string;
  taxable: boolean;
  custodian?: string | null;
  imported_at: string;
  holdings: Array<ImportedHoldingInput & { market_value: number; as_of_date: string }>;
  tax_lots: ImportedTaxLotInput[];
};

export type ClientConstraintPayload = {
  target_index: string;
  annual_gains_budget: number;
  max_tracking_error: number;
  max_active_share: number;
  estimated_tax_rate: number;
  excluded_symbols: string[];
  excluded_sectors: string[];
  household_wash_sale_notes?: string | null;
  outside_accounts_complete: boolean;
  equivalent_groups: { name: string; symbols: string[] }[];
};

export type TransitionRecommendation = {
  stage: string;
  action: string;
  symbol: string;
  shares: number;
  price: number;
  notional: number;
  realized_gain_loss: number;
  estimated_tax_impact: number;
  reason: string;
  wash_sale_status: string;
  notes: string;
};

export type TransitionPlan = {
  id: number;
  proposal_id: number;
  client_id: number;
  client_name: string;
  account_id?: number | null;
  account_name?: string | null;
  title: string;
  status: string;
  objective: string;
  algorithm_version: string;
  target_index: string;
  data_source_summary: string;
  portfolio_value: number;
  target_value: number;
  realized_gains: number;
  realized_losses: number;
  net_realized_gain: number;
  estimated_tax_impact: number;
  tracking_drift: number;
  active_share: number;
  turnover: number;
  skipped_trade_count: number;
  warnings: string[];
  recommendations: TransitionRecommendation[];
  input_snapshot: Record<string, unknown>;
  created_at: string;
};

export type AIAdvisorOpenAIKeyStatus = {
  has_key: boolean;
  key_fingerprint?: string | null;
  validated_at?: string | null;
  updated_at?: string | null;
};

export type AIAdvisorReportSummary = {
  id: number;
  module_id: string;
  module_title: string;
  model: string;
  created_at: string;
};

export type AIAdvisorReport = AIAdvisorReportSummary & {
  input_snapshot: Record<string, unknown>;
  prompt_text: string;
  response_text: string;
  usage: Record<string, unknown>;
  error?: Record<string, unknown> | null;
};

export type AIAdvisorRetirementRunRequest = {
  module_id: string;
  model: "gpt-5.5" | "gpt-5.4" | "gpt-5.4-mini";
  inputs: Record<string, string>;
};

export type PersonalCFOModel = AIAdvisorRetirementRunRequest["model"];

export type PersonalCFOMessage = {
  id: number;
  role: "assistant" | "user" | string;
  content: string;
  phase?: number | null;
  created_at: string;
};

export type PersonalCFOFile = {
  id: number;
  path: string;
  kind: string;
  content: string;
  created_at: string;
  updated_at: string;
};

export type PersonalCFOUpload = {
  id: number;
  file_name: string;
  file_type: string;
  row_count: number;
  created_at: string;
};

export type PersonalCFOProject = {
  id: number;
  name: string;
  status: string;
  current_phase: number;
  phase_progress: Record<string, unknown>;
  phase_complete: boolean;
  can_generate_one_pager: boolean;
  one_pager_generated: boolean;
  refinement_used: boolean;
  last_exported_at?: string | null;
  created_at: string;
  updated_at: string;
  messages: PersonalCFOMessage[];
  files: PersonalCFOFile[];
  uploads: PersonalCFOUpload[];
};

export type PersonalCFODashboard = {
  project_id: number;
  files_count: number;
  uploads_count: number;
  message_count: number;
  cash_trend: Array<{ date: string; value: number }>;
  pnl_summary: Record<string, number | string>;
  exposures: Array<{ label: string; value: number; weight: number }>;
  memory_timeline: string[];
  open_flags: string[];
};

export type OptionStrategyChecklistItem = {
  id: string;
  label: string;
  passed: boolean;
  actual?: string | number | null;
  expected?: string | number | null;
  detail?: string | null;
};

export type OptionStrategySignalCandidate = {
  id?: number | string;
  symbol: string;
  action: "sell_put" | "covered_call" | string;
  status: "approved" | "blocked" | string;
  sector?: string | null;
  underlying_price: number;
  strike: number;
  expiration: string;
  dte: number;
  delta: number;
  iv: number;
  iv_rank?: number | null;
  bb_percent?: number | null;
  earnings_date?: string | null;
  earnings_days?: number | null;
  spread_pct?: number | null;
  bid: number;
  ask: number;
  mid: number;
  open_interest: number;
  premium_yield: number;
  collateral: number;
  alert_target_price: number;
  exposure_usage?: number | null;
  score?: number | null;
  deep_dive_rank?: number | null;
  deep_dive_summary?: string | null;
  if_expires_return?: number | null;
  if_assigned_basis?: number | null;
  provider?: string | null;
  checklist: OptionStrategyChecklistItem[];
  blocked_reasons: string[];
  created_at: string;
};

export type OptionStrategyConfig = {
  tickers: string[];
  universe_groups?: string[];
  scan_cadence?: string;
  account_value: number;
  exposure_cap: number;
  dte_min: number;
  dte_max: number;
  rsi_period: number;
  rsi_max: number;
  ema_periods: number[];
  min_iv: number;
  min_iv_rank?: number;
  min_premium_yield: number;
  target_delta_min?: number;
  target_delta_max?: number;
  bb_percent_max?: number;
  earnings_exclusion_days?: number;
  min_open_interest?: number;
  max_spread_pct?: number;
  profit_take_pct?: number;
  single_name_cap?: number;
  sector_cap?: number;
  webhook_url?: string | null;
  updated_at?: string | null;
};

export type OptionStrategyUniverseItem = {
  symbol: string;
  name: string;
  sector: string;
  group: string;
};

export type OptionStrategyUniverse = {
  items: OptionStrategyUniverseItem[];
  groups: string[];
  count: number;
};

export type OptionStrategyWheelPosition = {
  id?: number | string;
  symbol: string;
  status: "put_open" | "assigned" | "covered_call_open" | "closed" | string;
  option_type: "put" | "call" | string;
  strike: number;
  expiration: string;
  contracts: number;
  entry_premium: number;
  current_price?: number | null;
  alert_target_price?: number | null;
  collateral?: number | null;
  created_at: string;
  updated_at?: string | null;
};

export type OptionStrategyAlertEvent = {
  id?: number | string;
  symbol: string;
  kind: "profit_50" | "covered_call_candidate" | string;
  status: "open" | "sent" | "acknowledged" | string;
  message: string;
  target_price?: number | null;
  current_price?: number | null;
  created_at: string;
};

export type OptionStrategyScanResult = {
  scan_run_id?: number | string | null;
  scanned_at: string;
  data_source?: string | null;
  signals: OptionStrategySignalCandidate[];
  warnings?: string[];
};

export function optionStrategyApiUrl(path = "") {
  const base = process.env.NEXT_PUBLIC_OPTION_STRATEGY_API_URL || `${apiUrl()}/option-strategy`;
  const normalizedBase = base.replace(/\/$/, "");
  if (!path) return normalizedBase;
  return `${normalizedBase}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function optionStrategyFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(optionStrategyApiUrl(path), {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {})
    }
  });
  if (!response.ok) {
    let message = `Request failed with ${response.status}`;
    try {
      const body = await response.json();
      message = typeof body.detail === "string" ? body.detail : body.detail ? JSON.stringify(body.detail) : message;
    } catch {
      // Keep default message.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${apiUrl()}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {})
    }
  });
  if (!response.ok) {
    let message = `Request failed with ${response.status}`;
    try {
      const body = await response.json();
      message = typeof body.detail === "string" ? body.detail : body.detail ? JSON.stringify(body.detail) : message;
    } catch {
      // Keep default message.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export function currency(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

export function percent(value: number) {
  return new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 2 }).format(value);
}
