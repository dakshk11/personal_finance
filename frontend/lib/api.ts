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
      message = body.detail ?? message;
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
