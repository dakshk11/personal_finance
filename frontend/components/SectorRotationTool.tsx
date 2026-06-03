"use client";

import {
  Activity,
  AlertCircle,
  BarChart2,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  DollarSign,
  Loader2,
  Play,
  RefreshCw,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiFetch } from "@/lib/api";

// ── Types ──────────────────────────────────────────────────────────────────

type PeriodSnapshot = {
  year: number;
  sectors_held: string[];
  sector_weights: Record<string, number>;
  period_return_pct: number;
  cumulative_value: number;
  taxes_paid_period: number;
  taxes_paid_cumulative: number;
  post_liquidation_value: number;
  embedded_tax_liability: number;
};

type ScenarioMetrics = {
  cagr_pretax_pct: number;
  cagr_posttax_pct: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  total_taxes_paid: number;
  tax_drag_annualized_pct: number;
  alpha_vs_spy_pretax_pct: number;
  alpha_vs_spy_posttax_pct: number;
  total_return_pct: number;
  win_rate_vs_benchmark: number;
  post_liquidation_value: number;
  final_pretax_value: number;
  best_year_return_pct: number;
  worst_year_return_pct: number;
};

type ScenarioResult = {
  id: string;
  name: string;
  metrics: ScenarioMetrics;
  period_snapshots: PeriodSnapshot[];
};

type BacktestResult = {
  starting_capital: number;
  weighting_method: WeightingMethod;
  tax_rates: Record<string, number>;
  scenarios: ScenarioResult[];
  comparison: {
    final_pretax_values: Record<string, number>;
    final_posttax_values: Record<string, number>;
    winner: string;
    tax_saved_annual_vs_quarterly: number;
    alpha_vs_spy_posttax_pct: number;
  };
};

type Allocation = {
  ticker: string;
  sector_name: string;
  weight: number;
  dollar_amount: number;
  trailing_eps_beat: number;
  forward_eps_beat: number;
  composite_score: number;
};

type LiveAllocationResult = {
  as_of_year: number;
  time_frame: string;
  weighting_method: WeightingMethod;
  allocations: Allocation[];
  sp500_signals: Record<string, number | string>;
  rebalance_guidance: string;
};

type AccountType = "taxable" | "tax_deferred";
type WeightingMethod = "equal" | "market_weight";
type RebalanceStatus = "planned" | "completed" | "partial" | "skipped";

type AcceptedPosition = {
  ticker: string;
  sector_name: string;
  target_weight: number;
  target_amount: number;
  shares: string;
  cost_basis: string;
  current_price: string;
  purchase_date: string;
};

type SavedAcceptedTrade = {
  id: number;
  ticker: string;
  sector_name: string;
  target_weight: number;
  target_amount: number;
  shares: number;
  cost_basis_per_share: number;
  current_price: number;
  purchase_date: string;
  market_value: number;
  cost_basis: number;
  gain_loss: number;
};

type SavedAcceptedAllocation = {
  id: number;
  account_type: AccountType;
  time_frame: string;
  weighting_method: WeightingMethod;
  cash_amount: number;
  as_of_year: number;
  rebalance_date?: string | null;
  rebalance_status: RebalanceStatus;
  rebalance_notes?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
  trades: SavedAcceptedTrade[];
};

type SelectionHistoryRow = {
  year: number;
  selected_sectors: string[];
  sector_weights: Record<string, number>;
  algo_return_pct: number;
  spy_return_pct: number;
  delta_pct: number;
  key_signal: string;
  weighting_method: WeightingMethod;
};

// ── Constants ──────────────────────────────────────────────────────────────

const SCENARIO_COLORS: Record<string, string> = {
  SPY_BUY_HOLD: "#2563eb",
  ALGO_ANNUAL_LTCG: "#0f766e",
  ALGO_QUARTERLY_STCG: "#d97706",
  ALGO_NO_REBALANCE: "#7c3aed",
  EW_NO_REBALANCE: "#dc2626",
};

const SCENARIO_SHORT: Record<string, string> = {
  SPY_BUY_HOLD: "SPY B&H",
  ALGO_ANNUAL_LTCG: "Algo Annual",
  ALGO_QUARTERLY_STCG: "Algo Quarterly",
  ALGO_NO_REBALANCE: "Algo No-Rebal",
  EW_NO_REBALANCE: "EW No-Rebal",
};

const SECTOR_COLORS = [
  "#0f766e", "#2563eb", "#d97706", "#7c3aed", "#dc2626",
  "#0891b2", "#65a30d", "#9f1239", "#92400e", "#1d4ed8", "#6d28d9",
];

const ALL_SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLB", "XLRE", "XLU", "XLC"];
const REBALANCE_STATUS_LABELS: Record<RebalanceStatus, string> = {
  planned: "Planned",
  completed: "Completed",
  partial: "Partial",
  skipped: "Skipped",
};

function fmt$(n: number) {
  return "$" + Math.round(n).toLocaleString();
}
function fmtPct(n: number, decimals = 1) {
  const sign = n > 0 ? "+" : "";
  return sign + n.toFixed(decimals) + "%";
}
function todayISO() {
  return new Date().toISOString().slice(0, 10);
}
function formatDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}
function yearsSince(dateValue: string) {
  const start = new Date(dateValue);
  if (Number.isNaN(start.getTime())) return 0;
  return Math.max((Date.now() - start.getTime()) / (365.25 * 24 * 60 * 60 * 1000), 0);
}
function numericInput(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}
function effectiveCurrentPrice(currentPrice: string, costBasis: string) {
  return numericInput(currentPrice) || numericInput(costBasis);
}
function cagr(startValue: number, endValue: number, years: number) {
  if (startValue <= 0 || endValue <= 0 || years <= 0) return 0;
  return (Math.pow(endValue / startValue, 1 / years) - 1) * 100;
}
function weightingLabel(method: WeightingMethod) {
  return method === "market_weight" ? "Market Weight" : "Equal Weight";
}
function allocationTaxRate(allocation: SavedAcceptedAllocation) {
  if (allocation.account_type === "tax_deferred") return 0;
  return allocation.time_frame === "quarterly" ? 0.541 : 0.371;
}
function savedAllocationStats(allocation: SavedAcceptedAllocation) {
  const basis = allocation.trades.reduce((sum, trade) => sum + trade.cost_basis, 0);
  const value = allocation.trades.reduce((sum, trade) => sum + trade.market_value, 0);
  const gain = value - basis;
  const taxImpact = gain > 0 ? gain * allocationTaxRate(allocation) : 0;
  const afterTaxValue = value - taxImpact;
  const weightedYears = allocation.trades.reduce((sum, trade) => (
    sum + yearsSince(trade.purchase_date) * trade.market_value
  ), 0);
  const avgHoldingYears = value > 0 ? weightedYears / value : 0;
  const displayCagr = avgHoldingYears >= 30 / 365.25
    ? fmtPct(cagr(basis, allocation.account_type === "tax_deferred" ? value : afterTaxValue, avgHoldingYears))
    : "N/A";
  return { basis, value, gain, taxImpact, afterTaxValue, avgHoldingYears, displayCagr };
}

// ── Sub-tabs ───────────────────────────────────────────────────────────────

type SubTab = "backtest" | "live-advisor" | "trades" | "history";

// ── Main component ─────────────────────────────────────────────────────────

export function SectorRotationTool() {
  const [subTab, setSubTab] = useState<SubTab>("backtest");

  return (
    <div className="sector-rotation-tool">
      <section className="dashboard-panel ai-advisor-head">
        <div>
          <p className="eyebrow">Sector Rotation Algorithm</p>
          <h2>Earnings-Based Sector Rotation Backtest &amp; Live Advisor</h2>
          <p>
            Rotates among S&amp;P 500 sector ETFs using FactSet trailing EPS growth and forward NTM estimates.
            Full after-tax modeling under California&apos;s tax regime (LTCG 37.1%, STCG 54.1%).
          </p>
        </div>
        <span className="status-pill">
          <Activity size={14} /> 2015–2025 Backtest
        </span>
      </section>

      <div className="ai-tabbar" style={{ marginBottom: 0 }}>
        <button
          type="button"
          role="tab"
          className={subTab === "backtest" ? "active" : ""}
          onClick={() => setSubTab("backtest")}
        >
          <BarChart2 size={15} /> Backtest (5 Scenarios)
        </button>
        <button
          type="button"
          role="tab"
          className={subTab === "live-advisor" ? "active" : ""}
          onClick={() => setSubTab("live-advisor")}
        >
          <DollarSign size={15} /> Live Advisor
        </button>
        <button
          type="button"
          role="tab"
          className={subTab === "history" ? "active" : ""}
          onClick={() => setSubTab("history")}
        >
          <Clock size={15} /> Historical Selections
        </button>
        <button
          type="button"
          role="tab"
          className={subTab === "trades" ? "active" : ""}
          onClick={() => setSubTab("trades")}
        >
          <RefreshCw size={15} /> Trades
        </button>
      </div>

      {subTab === "backtest" && <BacktestTab />}
      {subTab === "live-advisor" && <LiveAdvisorTab />}
      {subTab === "trades" && <AcceptedTradesTab />}
      {subTab === "history" && <HistoryTab />}
    </div>
  );
}

function WeightingSelector({ value, onChange }: { value: WeightingMethod; onChange: (value: WeightingMethod) => void }) {
  return (
    <div className="sector-weight-toggle">
      <span className="fine-print">Weighting</span>
      <button
        type="button"
        className={value === "equal" ? "active" : ""}
        onClick={() => onChange("equal")}
      >
        Equal Weight
      </button>
      <button
        type="button"
        className={value === "market_weight" ? "active" : ""}
        onClick={() => onChange("market_weight")}
      >
        Market Weight
      </button>
    </div>
  );
}

// ── Backtest Tab ───────────────────────────────────────────────────────────

function BacktestTab() {
  const [startingCapital, setStartingCapital] = useState("100000");
  const [weightingMethod, setWeightingMethod] = useState<WeightingMethod>("equal");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [expandedScenario, setExpandedScenario] = useState<string | null>(null);

  useEffect(() => {
    setResult(null);
    setExpandedScenario(null);
  }, [weightingMethod]);

  async function runBacktest() {
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<BacktestResult>("/sector-rotation/backtest", {
        method: "POST",
        body: JSON.stringify({
          starting_capital: parseFloat(startingCapital) || 100000,
          weighting_method: weightingMethod,
        }),
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backtest failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="form-stack">
      {/* Config */}
      <section className="dashboard-panel">
        <div className="panel-header">
          <h2>Backtest Configuration</h2>
          <BarChart2 size={18} />
        </div>
        <div className="ai-field-grid" style={{ gridTemplateColumns: "1fr 1fr auto" }}>
          <div className="field">
            <label>Starting Capital</label>
            <input
              type="number"
              value={startingCapital}
              onChange={(e) => setStartingCapital(e.target.value)}
              min={1000}
              step={1000}
            />
          </div>
          <div className="field">
            <label>Backtest Window</label>
            <input type="text" value="Jan 2015 – Dec 2025 (11 years)" disabled readOnly />
          </div>
          <div style={{ display: "flex", alignItems: "flex-end" }}>
            <button
              type="button"
              className="primary-button"
              onClick={runBacktest}
              disabled={loading}
              style={{ whiteSpace: "nowrap" }}
            >
              {loading ? <Loader2 size={16} className="spin-icon" /> : <Play size={16} />}
              Run Backtest
            </button>
          </div>
        </div>
        <div style={{ marginTop: 8 }} className="fine-print">
          California investor · Single filer · $1.8M income · LTCG 37.1% · STCG 54.1% (NIIT included)
        </div>
        <WeightingSelector value={weightingMethod} onChange={setWeightingMethod} />
        {error && (
          <div className="error-message" style={{ marginTop: 8 }}>
            <AlertCircle size={14} /> {error}
          </div>
        )}
      </section>

      {result && (
        <>
          {/* Scenario comparison table */}
          <ScenarioComparisonTable result={result} />

          {/* Growth curves chart */}
          <GrowthCurvesChart result={result} />

          {/* Annual returns vs SPY */}
          <AnnualReturnsChart result={result} />

          {/* Tax waterfall */}
          <TaxWaterfallChart result={result} />

          {/* Sector drift (no-rebalance) */}
          <SectorDriftChart result={result} />

          {/* Selection heatmap */}
          <SelectionHeatmap result={result} />

          {/* Expandable period-by-period details */}
          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Period-by-Period Details</h2>
              <Calendar size={18} />
            </div>
            <div className="form-stack">
              {result.scenarios.map((scenario) => (
                <div key={scenario.id} style={{ border: "1px solid var(--line)", borderRadius: 8 }}>
                  <button
                    type="button"
                    style={{
                      width: "100%",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "10px 14px",
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                      fontWeight: 600,
                      color: SCENARIO_COLORS[scenario.id] ?? "var(--ink)",
                    }}
                    onClick={() => setExpandedScenario(expandedScenario === scenario.id ? null : scenario.id)}
                  >
                    <span>{scenario.name}</span>
                    {expandedScenario === scenario.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>
                  {expandedScenario === scenario.id && (
                    <div style={{ overflowX: "auto", padding: "0 14px 14px" }}>
                      <table className="allocation-table">
                        <thead>
                          <tr>
                            <th>Year</th>
                            <th>Sectors Held</th>
                            <th>Return</th>
                            <th>Cumul. Value (Pre-Tax)</th>
                            <th>Post-Liq. Value</th>
                            <th>Taxes Paid</th>
                          </tr>
                        </thead>
                        <tbody>
                          {scenario.period_snapshots.map((snap) => (
                            <tr key={snap.year}>
                              <td>{snap.year}</td>
                              <td style={{ fontSize: 12 }}>{snap.sectors_held.join(", ")}</td>
                              <td style={{ color: snap.period_return_pct >= 0 ? "var(--forest)" : "var(--rose)" }}>
                                {fmtPct(snap.period_return_pct)}
                              </td>
                              <td>{fmt$(snap.cumulative_value)}</td>
                              <td>{fmt$(snap.post_liquidation_value)}</td>
                              <td style={{ color: snap.taxes_paid_period > 0 ? "var(--rose)" : undefined }}>
                                {snap.taxes_paid_period > 0 ? fmt$(snap.taxes_paid_period) : "—"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

// ── Scenario comparison table ──────────────────────────────────────────────

function ScenarioComparisonTable({ result }: { result: BacktestResult }) {
  const winner = result.comparison.winner;
  return (
    <section className="dashboard-panel">
      <div className="panel-header">
        <h2>Scenario Comparison</h2>
        <CheckCircle2 size={18} />
      </div>

      {/* Winner callout */}
      <div
        style={{
          background: "var(--mint)",
          border: "1px solid var(--forest)",
          borderRadius: 8,
          padding: "10px 14px",
          marginBottom: 16,
          display: "flex",
          gap: 8,
          alignItems: "center",
          fontSize: 14,
        }}
      >
        <TrendingUp size={16} color="var(--forest)" />
        <strong style={{ color: "var(--forest)" }}>Winner (post-tax):</strong>
        <span>{result.scenarios.find((s) => s.id === winner)?.name}</span>
        <span style={{ marginLeft: "auto", color: "var(--forest)", fontWeight: 600 }}>
          {fmt$(result.comparison.final_posttax_values[winner])} after tax
        </span>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table className="allocation-table">
          <thead>
            <tr>
              <th>Scenario</th>
              <th>Pre-Tax CAGR</th>
              <th>Post-Tax CAGR</th>
              <th>Final (Pre-Tax)</th>
              <th>Final (Post-Tax)</th>
              <th>Total Taxes</th>
              <th>Tax Drag</th>
              <th>Alpha vs SPY</th>
              <th>Sharpe</th>
              <th>Max DD</th>
              <th>Win Rate</th>
            </tr>
          </thead>
          <tbody>
            {result.scenarios.map((s) => {
              const m = s.metrics;
              const isWinner = s.id === winner;
              return (
                <tr key={s.id} style={isWinner ? { background: "#f0fdf4" } : undefined}>
                  <td>
                    <span
                      style={{
                        display: "inline-block",
                        width: 10,
                        height: 10,
                        borderRadius: "50%",
                        background: SCENARIO_COLORS[s.id] ?? "#888",
                        marginRight: 6,
                      }}
                    />
                    <strong>{SCENARIO_SHORT[s.id] ?? s.name}</strong>
                    {isWinner && (
                      <span
                        style={{
                          marginLeft: 6,
                          fontSize: 10,
                          background: "var(--forest)",
                          color: "#fff",
                          borderRadius: 4,
                          padding: "1px 5px",
                        }}
                      >
                        WINNER
                      </span>
                    )}
                  </td>
                  <td style={{ color: "var(--forest)", fontWeight: 600 }}>{fmtPct(m.cagr_pretax_pct)}</td>
                  <td>{fmtPct(m.cagr_posttax_pct)}</td>
                  <td>{fmt$(m.final_pretax_value)}</td>
                  <td style={{ fontWeight: 600 }}>{fmt$(m.post_liquidation_value)}</td>
                  <td style={{ color: m.total_taxes_paid > 0 ? "var(--rose)" : undefined }}>
                    {fmt$(m.total_taxes_paid)}
                  </td>
                  <td style={{ color: "var(--amber)" }}>
                    {m.tax_drag_annualized_pct > 0 ? `-${m.tax_drag_annualized_pct.toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ color: m.alpha_vs_spy_posttax_pct >= 0 ? "var(--forest)" : "var(--rose)" }}>
                    {fmtPct(m.alpha_vs_spy_posttax_pct)}
                  </td>
                  <td>{m.sharpe_ratio.toFixed(2)}</td>
                  <td style={{ color: "var(--rose)" }}>{m.max_drawdown_pct.toFixed(1)}%</td>
                  <td>{m.win_rate_vs_benchmark.toFixed(0)}%</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 12,
          marginTop: 16,
          fontSize: 13,
        }}
      >
        <div className="dashboard-panel" style={{ padding: "10px 14px" }}>
          <div className="fine-print" style={{ marginBottom: 4 }}>Tax saved (Annual vs Quarterly)</div>
          <strong style={{ fontSize: 18, color: "var(--forest)" }}>
            {fmt$(result.comparison.tax_saved_annual_vs_quarterly)}
          </strong>
        </div>
        <div className="dashboard-panel" style={{ padding: "10px 14px" }}>
          <div className="fine-print" style={{ marginBottom: 4 }}>Algo Alpha vs SPY (post-tax)</div>
          <strong
            style={{
              fontSize: 18,
              color: result.comparison.alpha_vs_spy_posttax_pct >= 0 ? "var(--forest)" : "var(--rose)",
            }}
          >
            {fmtPct(result.comparison.alpha_vs_spy_posttax_pct)} CAGR
          </strong>
        </div>
      </div>
    </section>
  );
}

// ── Growth curves chart ────────────────────────────────────────────────────

function GrowthCurvesChart({ result }: { result: BacktestResult }) {
  const years = result.scenarios[0].period_snapshots.map((s) => s.year);

  const chartData = years.map((year) => {
    const row: Record<string, number | string> = { year };
    for (const scenario of result.scenarios) {
      const snap = scenario.period_snapshots.find((s) => s.year === year);
      if (snap) {
        row[scenario.id] = snap.cumulative_value;
        row[`${scenario.id}_posttax`] = snap.post_liquidation_value;
      }
    }
    return row;
  });

  return (
    <section className="dashboard-panel">
      <div className="panel-header">
        <h2>Portfolio Growth (Pre-Tax)</h2>
        <TrendingUp size={18} />
      </div>
      <p className="fine-print">Solid lines = gross pre-tax compound value. Post-tax values shown in comparison table.</p>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={chartData} margin={{ top: 10, right: 30, left: 20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
          <XAxis dataKey="year" tick={{ fontSize: 12 }} />
          <YAxis tickFormatter={(v) => "$" + Math.round(v / 1000) + "K"} tick={{ fontSize: 11 }} width={60} />
          <Tooltip
            formatter={(value: number, name: string) => {
              const scenario = result.scenarios.find((s) => s.id === name);
              return [fmt$(value), scenario?.name ?? name];
            }}
          />
          <Legend formatter={(value) => SCENARIO_SHORT[value] ?? value} />
          {result.scenarios.map((s) => (
            <Line
              key={s.id}
              type="monotone"
              dataKey={s.id}
              stroke={SCENARIO_COLORS[s.id] ?? "#888"}
              strokeWidth={2}
              dot={false}
              name={s.id}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </section>
  );
}

// ── Annual returns vs SPY ──────────────────────────────────────────────────

function AnnualReturnsChart({ result }: { result: BacktestResult }) {
  const algoAnnual = result.scenarios.find((s) => s.id === "ALGO_ANNUAL_LTCG");
  const spy = result.scenarios.find((s) => s.id === "SPY_BUY_HOLD");
  if (!algoAnnual || !spy) return null;

  const chartData = algoAnnual.period_snapshots.map((snap, i) => ({
    year: snap.year,
    algo: snap.period_return_pct,
    spy: spy.period_snapshots[i]?.period_return_pct ?? 0,
    delta: snap.period_return_pct - (spy.period_snapshots[i]?.period_return_pct ?? 0),
  }));

  return (
    <section className="dashboard-panel">
      <div className="panel-header">
        <h2>Algo Annual Returns vs SPY</h2>
        <BarChart2 size={18} />
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
          <XAxis dataKey="year" tick={{ fontSize: 12 }} />
          <YAxis tickFormatter={(v) => v + "%"} tick={{ fontSize: 11 }} />
          <Tooltip
            formatter={(value: number, name: string) => [value.toFixed(1) + "%", name === "algo" ? "Algo Annual" : name === "spy" ? "SPY" : "Delta"]}
          />
          <Legend />
          <Bar dataKey="algo" name="Algo Annual" radius={[3, 3, 0, 0]}>
            {chartData.map((entry) => (
              <Cell key={entry.year} fill={entry.algo >= entry.spy ? "#0f766e" : "#dc2626"} />
            ))}
          </Bar>
          <Line type="monotone" dataKey="spy" name="SPY" stroke="#2563eb" strokeWidth={2} dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="fine-print">Green bars = outperformed SPY · Red bars = underperformed SPY</p>
    </section>
  );
}

// ── Tax waterfall chart ────────────────────────────────────────────────────

function TaxWaterfallChart({ result }: { result: BacktestResult }) {
  const ltcg = result.scenarios.find((s) => s.id === "ALGO_ANNUAL_LTCG");
  const stcg = result.scenarios.find((s) => s.id === "ALGO_QUARTERLY_STCG");
  if (!ltcg || !stcg) return null;

  const chartData = ltcg.period_snapshots.map((snap, i) => ({
    year: snap.year,
    ltcg: snap.taxes_paid_period,
    stcg: stcg.period_snapshots[i]?.taxes_paid_period ?? 0,
  }));

  return (
    <section className="dashboard-panel">
      <div className="panel-header">
        <h2>Annual Tax Burden Comparison</h2>
        <Activity size={18} />
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
          <XAxis dataKey="year" tick={{ fontSize: 12 }} />
          <YAxis tickFormatter={(v) => "$" + Math.round(v / 1000) + "K"} tick={{ fontSize: 11 }} width={50} />
          <Tooltip formatter={(v: number) => fmt$(v)} />
          <Legend />
          <Bar dataKey="ltcg" name="LTCG (Annual)" fill="#0f766e" radius={[3, 3, 0, 0]} />
          <Bar dataKey="stcg" name="STCG (Quarterly)" fill="#dc2626" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
      <div className="fine-print">
        LTCG rate: {((result.tax_rates.ltcg_effective ?? 0.371) * 100).toFixed(1)}% ·
        STCG rate: {((result.tax_rates.stcg_effective ?? 0.541) * 100).toFixed(1)}%
      </div>
    </section>
  );
}

// ── Sector drift chart ─────────────────────────────────────────────────────

function SectorDriftChart({ result }: { result: BacktestResult }) {
  const noRebalance = result.scenarios.find((s) => s.id === "ALGO_NO_REBALANCE");
  if (!noRebalance) return null;

  const sectors = Array.from(
    new Set(noRebalance.period_snapshots.flatMap((s) => s.sectors_held))
  );

  const chartData = noRebalance.period_snapshots.map((snap) => {
    const row: Record<string, number | string> = { year: snap.year };
    for (const sector of sectors) {
      row[sector] = Math.round((snap.sector_weights[sector] ?? 0) * 100);
    }
    return row;
  });

  return (
    <section className="dashboard-panel">
      <div className="panel-header">
        <h2>Sector Weight Drift — Algo No-Rebalance</h2>
        <RefreshCw size={18} />
      </div>
      <p className="fine-print">Shows how sector weights shift without rebalancing. Tech dominates due to compounding returns.</p>
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
          <XAxis dataKey="year" tick={{ fontSize: 12 }} />
          <YAxis tickFormatter={(v) => v + "%"} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v: number) => v + "%"} />
          <Legend />
          {sectors.map((sector, i) => (
            <Area
              key={sector}
              type="monotone"
              dataKey={sector}
              stackId="1"
              fill={SECTOR_COLORS[i % SECTOR_COLORS.length]}
              stroke={SECTOR_COLORS[i % SECTOR_COLORS.length]}
              fillOpacity={0.8}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </section>
  );
}

// ── Selection heatmap ──────────────────────────────────────────────────────

function SelectionHeatmap({ result }: { result: BacktestResult }) {
  const algoAnnual = result.scenarios.find((s) => s.id === "ALGO_ANNUAL_LTCG");
  if (!algoAnnual) return null;

  const years = algoAnnual.period_snapshots.map((s) => s.year);
  const selectedMap: Record<number, string[]> = {};
  for (const snap of algoAnnual.period_snapshots) {
    selectedMap[snap.year] = snap.sectors_held;
  }

  return (
    <section className="dashboard-panel">
      <div className="panel-header">
        <h2>Sector Selection Heatmap — Algo Annual</h2>
        <Calendar size={18} />
      </div>
      <div style={{ overflowX: "auto" }}>
        <div className="sector-heatmap-grid" style={{ minWidth: 720 }}>
          {/* Header row */}
          <div className="sector-heatmap-cell sector-heatmap-header" />
          {years.map((y) => (
            <div key={y} className="sector-heatmap-cell sector-heatmap-header">
              {y}
            </div>
          ))}
          {/* Sector rows */}
          {ALL_SECTORS.map((sector) => (
            <div key={sector} style={{ display: "contents" }}>
              <div className="sector-heatmap-cell sector-heatmap-label">{sector}</div>
              {years.map((year) => {
                const selected = selectedMap[year]?.includes(sector);
                return (
                  <div
                    key={year}
                    className={`sector-heatmap-cell${selected ? " sector-heatmap-selected" : ""}`}
                    title={selected ? `${sector} selected in ${year}` : `${sector} not selected in ${year}`}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>
      <div style={{ display: "flex", gap: 16, marginTop: 8, fontSize: 12, color: "var(--muted)" }}>
        <span>
          <span
            style={{
              display: "inline-block",
              width: 12,
              height: 12,
              background: "var(--forest)",
              borderRadius: 2,
              marginRight: 4,
            }}
          />
          Selected
        </span>
        <span>
          <span
            style={{
              display: "inline-block",
              width: 12,
              height: 12,
              background: "var(--line)",
              borderRadius: 2,
              marginRight: 4,
            }}
          />
          Not selected
        </span>
      </div>
    </section>
  );
}

// ── Live Advisor Tab ───────────────────────────────────────────────────────

function LiveAdvisorTab() {
  const [cashAmount, setCashAmount] = useState("100000");
  const [timeFrame, setTimeFrame] = useState("annual");
  const [weightingMethod, setWeightingMethod] = useState<WeightingMethod>("equal");
  const [accountType, setAccountType] = useState<AccountType>("taxable");
  const [acceptedPositions, setAcceptedPositions] = useState<AcceptedPosition[]>([]);
  const [savedAllocations, setSavedAllocations] = useState<SavedAcceptedAllocation[]>([]);
  const [loading, setLoading] = useState(false);
  const [savingAccepted, setSavingAccepted] = useState(false);
  const [error, setError] = useState("");
  const [saveMessage, setSaveMessage] = useState("");
  const [result, setResult] = useState<LiveAllocationResult | null>(null);

  useEffect(() => {
    setResult(null);
    setAcceptedPositions([]);
  }, [weightingMethod]);

  useEffect(() => {
    void loadAcceptedAllocations();
  }, []);

  async function loadAcceptedAllocations() {
    try {
      setSavedAllocations(await apiFetch<SavedAcceptedAllocation[]>("/sector-rotation/accepted-allocations"));
    } catch {
      setSavedAllocations([]);
    }
  }

  async function getAllocation() {
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<LiveAllocationResult>("/sector-rotation/live-allocation", {
        method: "POST",
        body: JSON.stringify({
          cash_amount: parseFloat(cashAmount) || 100000,
          time_frame: timeFrame,
          weighting_method: weightingMethod,
        }),
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to get allocation");
    } finally {
      setLoading(false);
    }
  }

  function acceptAllocation() {
    if (!result) return;
    setAcceptedPositions(result.allocations.map((alloc) => ({
      ticker: alloc.ticker,
      sector_name: alloc.sector_name,
      target_weight: alloc.weight,
      target_amount: alloc.dollar_amount,
      shares: "",
      cost_basis: "",
      current_price: "",
      purchase_date: todayISO(),
    })));
  }

  function updateAcceptedPosition(ticker: string, field: keyof AcceptedPosition, value: string) {
    setAcceptedPositions((rows) => rows.map((row) => (
      row.ticker === ticker ? { ...row, [field]: value } : row
    )));
    setSaveMessage("");
  }

  async function saveAcceptedTrades() {
    if (!result) return;
    const trades = acceptedPositions
      .map((row) => {
        const shares = numericInput(row.shares);
        const cost = numericInput(row.cost_basis);
        const currentPrice = effectiveCurrentPrice(row.current_price, row.cost_basis);
        return {
          ticker: row.ticker,
          sector_name: row.sector_name,
          target_weight: row.target_weight,
          target_amount: row.target_amount,
          shares,
          cost_basis_per_share: cost,
          current_price: currentPrice,
          purchase_date: row.purchase_date || todayISO(),
        };
      })
      .filter((row) => row.shares > 0 && row.cost_basis_per_share > 0 && row.current_price > 0);

    if (!trades.length) {
      setSaveMessage("Enter shares and cost per share for at least one ETF before saving.");
      return;
    }

    setSavingAccepted(true);
    setSaveMessage("");
    try {
      const saved = await apiFetch<SavedAcceptedAllocation>("/sector-rotation/accepted-allocations", {
        method: "POST",
        body: JSON.stringify({
          account_type: accountType,
          time_frame: timeFrame,
          weighting_method: result.weighting_method,
          cash_amount: parseFloat(cashAmount) || 0,
          as_of_year: result.as_of_year,
          rebalance_date: trades[0]?.purchase_date ?? todayISO(),
          rebalance_status: "planned",
          trades,
        }),
      });
      setSavedAllocations((rows) => [saved, ...rows]);
      setSaveMessage(`Saved ${saved.trades.length} accepted trade${saved.trades.length === 1 ? "" : "s"} to database.`);
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : "Could not save accepted trades.");
    } finally {
      setSavingAccepted(false);
    }
  }

  const taxableRate = timeFrame === "quarterly" ? 0.541 : 0.371;
  const taxRateLabel = accountType === "tax_deferred"
    ? "0.0% tax-deferred"
    : timeFrame === "quarterly" ? "54.1% STCG" : "37.1% LTCG";
  const accountGuidance = result && accountType === "tax_deferred"
    ? result.rebalance_guidance.replace(
      /California effective tax rate: [^.]+\./,
      "Tax-deferred account: no current tax drag modeled."
    )
    : result?.rebalance_guidance;
  const nextRebalance =
    timeFrame === "annual"
      ? "First Monday of February (annually)"
      : timeFrame === "quarterly"
      ? "First Monday of Feb / May / Aug / Nov"
      : "One-time — no future rebalancing";
  const portfolioStats = acceptedPositions.reduce((stats, row) => {
    const shares = numericInput(row.shares);
    const cost = numericInput(row.cost_basis);
    const price = effectiveCurrentPrice(row.current_price, row.cost_basis);
    const basis = shares * cost;
    const value = shares * price;
    const gain = value - basis;
    const taxImpact = accountType === "taxable" && gain > 0 ? gain * taxableRate : 0;
    const heldYears = yearsSince(row.purchase_date);
    const weightedYears = value > 0 ? heldYears * value : 0;
    return {
      basis: stats.basis + basis,
      value: stats.value + value,
      gain: stats.gain + gain,
      taxImpact: stats.taxImpact + taxImpact,
      weightedYears: stats.weightedYears + weightedYears,
    };
  }, { basis: 0, value: 0, gain: 0, taxImpact: 0, weightedYears: 0 });
  const afterTaxValue = portfolioStats.value - portfolioStats.taxImpact;
  const avgHoldingYears = portfolioStats.value > 0 ? portfolioStats.weightedYears / portfolioStats.value : 0;
  const preTaxCagr = cagr(portfolioStats.basis, portfolioStats.value, avgHoldingYears);
  const afterTaxCagr = cagr(portfolioStats.basis, afterTaxValue, avgHoldingYears);
  const displayCagr = avgHoldingYears >= 30 / 365.25
    ? fmtPct(accountType === "tax_deferred" ? preTaxCagr : afterTaxCagr)
    : "N/A";
  const totalTargetAmount = acceptedPositions.reduce((sum, row) => sum + row.target_amount, 0);

  return (
    <div className="form-stack">
      <section className="dashboard-panel">
        <div className="panel-header">
          <h2>Live Allocation Advisor</h2>
          <DollarSign size={18} />
        </div>
        <p style={{ marginBottom: 16, color: "var(--muted)", fontSize: 14 }}>
          Enter your available cash to get sector allocation targets based on the latest EPS signals.
          The algorithm uses prior-year Q4 FactSet data (as available in February for the annual rebalance).
        </p>

        <div className="ai-field-grid" style={{ gridTemplateColumns: "1fr 1fr auto" }}>
          <div className="field">
            <label>Available Cash</label>
            <input
              type="number"
              value={cashAmount}
              onChange={(e) => setCashAmount(e.target.value)}
              min={0}
              step={1000}
              placeholder="100000"
            />
          </div>
          <div className="field">
            <label>Rebalancing Time Frame</label>
            <select value={timeFrame} onChange={(e) => setTimeFrame(e.target.value)}>
              <option value="annual">Annual — LTCG (37.1%)</option>
              <option value="quarterly">Quarterly — STCG (54.1%)</option>
              <option value="one_time">One-Time — No future rebalancing</option>
            </select>
          </div>
          <div style={{ display: "flex", alignItems: "flex-end" }}>
            <button
              type="button"
              className="primary-button"
              onClick={getAllocation}
              disabled={loading}
              style={{ whiteSpace: "nowrap" }}
            >
              {loading ? <Loader2 size={16} className="spin-icon" /> : <TrendingUp size={16} />}
              Get Allocation
            </button>
          </div>
        </div>
        <WeightingSelector value={weightingMethod} onChange={setWeightingMethod} />

        <div
          style={{
            marginTop: 12,
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 8,
            fontSize: 13,
          }}
        >
          <div style={{ background: "var(--paper)", borderRadius: 6, padding: "8px 12px" }}>
            <div className="fine-print">Effective Tax Rate</div>
            <strong style={{ color: timeFrame === "quarterly" ? "var(--rose)" : "var(--forest)" }}>
              {taxRateLabel}
            </strong>
          </div>
          <div style={{ background: "var(--paper)", borderRadius: 6, padding: "8px 12px" }}>
            <div className="fine-print">Next Rebalance Date</div>
            <strong>{nextRebalance}</strong>
          </div>
        </div>

        <div className="sector-account-toggle">
          <span className="fine-print">Account Type</span>
          <button
            type="button"
            className={accountType === "taxable" ? "active" : ""}
            onClick={() => setAccountType("taxable")}
          >
            Taxable
          </button>
          <button
            type="button"
            className={accountType === "tax_deferred" ? "active" : ""}
            onClick={() => setAccountType("tax_deferred")}
          >
            Tax-deferred
          </button>
        </div>

        {error && (
          <div className="error-message" style={{ marginTop: 8 }}>
            <AlertCircle size={14} /> {error}
          </div>
        )}
      </section>

      {result && (
        <>
          {/* Guidance banner */}
          <section className="dashboard-panel" style={{ background: "var(--mint)", border: "1px solid var(--forest)" }}>
            <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
              <CheckCircle2 size={20} color="var(--forest)" style={{ flexShrink: 0, marginTop: 2 }} />
              <div>
                <strong style={{ color: "var(--forest)", display: "block", marginBottom: 4 }}>
                  Algorithm Recommendation — {result.as_of_year}
                </strong>
                <div className="fine-print" style={{ marginBottom: 4 }}>
                  {weightingLabel(result.weighting_method)} allocation
                </div>
                <p style={{ margin: 0, fontSize: 14 }}>{accountGuidance}</p>
              </div>
            </div>
          </section>

          {/* Allocation table + chart side by side */}
          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Sector Allocation</h2>
              <DollarSign size={18} />
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 280px",
                gap: 24,
                alignItems: "start",
              }}
            >
              <div style={{ overflowX: "auto" }}>
                <table className="allocation-table">
                  <thead>
                    <tr>
                      <th>ETF</th>
                      <th>Sector</th>
                      <th>Weight</th>
                      <th>Dollar Amount</th>
                      <th>Trailing EPS Beat</th>
                      <th>Forward EPS Beat</th>
                      <th>Composite Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.allocations.map((alloc, i) => (
                      <tr key={alloc.ticker}>
                        <td>
                          <strong style={{ color: SECTOR_COLORS[i % SECTOR_COLORS.length] }}>
                            {alloc.ticker}
                          </strong>
                        </td>
                        <td>{alloc.sector_name}</td>
                        <td>{(alloc.weight * 100).toFixed(1)}%</td>
                        <td>
                          <strong>{fmt$(alloc.dollar_amount)}</strong>
                        </td>
                        <td style={{ color: alloc.trailing_eps_beat >= 0 ? "var(--forest)" : "var(--rose)" }}>
                          {fmtPct(alloc.trailing_eps_beat, 1)} pp
                        </td>
                        <td style={{ color: alloc.forward_eps_beat >= 0 ? "var(--forest)" : "var(--rose)" }}>
                          {fmtPct(alloc.forward_eps_beat, 1)} pp
                        </td>
                        <td>{alloc.composite_score.toFixed(1)}</td>
                      </tr>
                    ))}
                    <tr style={{ borderTop: "2px solid var(--line)", fontWeight: 700 }}>
                      <td colSpan={2}>Total</td>
                      <td>
                        {(result.allocations.reduce((sum, a) => sum + a.weight, 0) * 100).toFixed(0)}%
                      </td>
                      <td>{fmt$(result.allocations.reduce((sum, a) => sum + a.dollar_amount, 0))}</td>
                      <td colSpan={3} />
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* Mini allocation bar chart */}
              <div>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart
                    data={result.allocations.map((a, i) => ({
                      ticker: a.ticker,
                      weight: Math.round(a.weight * 100),
                      color: SECTOR_COLORS[i % SECTOR_COLORS.length],
                    }))}
                    layout="vertical"
                    margin={{ left: 10, right: 20, top: 0, bottom: 0 }}
                  >
                    <XAxis type="number" tickFormatter={(v) => v + "%"} tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="ticker" tick={{ fontSize: 12 }} width={36} />
                    <Tooltip formatter={(v: number) => v + "%"} />
                    <Bar dataKey="weight" radius={[0, 4, 4, 0]}>
                      {result.allocations.map((a, i) => (
                        <Cell key={a.ticker} fill={SECTOR_COLORS[i % SECTOR_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div style={{ marginTop: 16, display: "flex", justifyContent: "flex-end" }}>
              <button type="button" className="primary-button" onClick={acceptAllocation}>
                <CheckCircle2 size={16} /> Accept allocation
              </button>
            </div>
          </section>

          {acceptedPositions.length > 0 && (
            <section className="dashboard-panel">
              <div className="panel-header">
                <h2>Accepted Position Performance</h2>
                <TrendingUp size={18} />
              </div>
              <p className="fine-print" style={{ marginTop: -6 }}>
                Tracking against accepted {weightingLabel(result.weighting_method)} targets.
              </p>
              <div className="sector-performance-summary">
                <article>
                  <span>Market Value</span>
                  <strong>{fmt$(portfolioStats.value)}</strong>
                  <small>Entered positions</small>
                </article>
                <article>
                  <span>Gain / Loss</span>
                  <strong style={{ color: portfolioStats.gain >= 0 ? "var(--forest)" : "var(--rose)" }}>
                    {fmt$(portfolioStats.gain)}
                  </strong>
                  <small>{portfolioStats.basis > 0 ? fmtPct((portfolioStats.gain / portfolioStats.basis) * 100) : "0.0%"}</small>
                </article>
                <article>
                  <span>After-Tax Value</span>
                  <strong>{fmt$(afterTaxValue)}</strong>
                  <small>{accountType === "tax_deferred" ? "No current tax drag" : `${fmt$(portfolioStats.taxImpact)} estimated tax`}</small>
                </article>
                <article>
                  <span>CAGR</span>
                  <strong>{displayCagr}</strong>
                  <small>{displayCagr === "N/A" ? "needs 30+ days held" : accountType === "tax_deferred" ? "pre-tax compounding" : "after estimated taxes"}</small>
                </article>
              </div>

              <div style={{ overflowX: "auto" }}>
                <table className="allocation-table sector-position-table">
                  <thead>
                    <tr>
                      <th>ETF</th>
                      <th>Target</th>
                      <th>Shares</th>
                      <th>Cost / Sh.</th>
                      <th>Current / Sh.</th>
                      <th>Purchase Date</th>
                      <th>Value</th>
                      <th>Return</th>
                      <th>Drift</th>
                    </tr>
                  </thead>
                  <tbody>
                    {acceptedPositions.map((row) => {
                      const shares = numericInput(row.shares);
                      const cost = numericInput(row.cost_basis);
                      const price = effectiveCurrentPrice(row.current_price, row.cost_basis);
                      const basis = shares * cost;
                      const value = shares * price;
                      const gainPct = basis > 0 ? ((value / basis) - 1) * 100 : 0;
                      const actualWeight = portfolioStats.value > 0 ? value / portfolioStats.value : 0;
                      const targetWeight = totalTargetAmount > 0 ? row.target_amount / totalTargetAmount : row.target_weight;
                      const drift = (actualWeight - targetWeight) * 100;

                      return (
                        <tr key={row.ticker}>
                          <td>
                            <strong>{row.ticker}</strong>
                            <div className="fine-print">{row.sector_name}</div>
                          </td>
                          <td>{(targetWeight * 100).toFixed(1)}%</td>
                          <td>
                            <input
                              type="number"
                              min={0}
                              step="0.0001"
                              value={row.shares}
                              onChange={(e) => updateAcceptedPosition(row.ticker, "shares", e.target.value)}
                            />
                          </td>
                          <td>
                            <input
                              type="number"
                              min={0}
                              step="0.01"
                              value={row.cost_basis}
                              onChange={(e) => updateAcceptedPosition(row.ticker, "cost_basis", e.target.value)}
                            />
                          </td>
                          <td>
                            <input
                              type="number"
                              min={0}
                              step="0.01"
                              placeholder="defaults to cost"
                              value={row.current_price}
                              onChange={(e) => updateAcceptedPosition(row.ticker, "current_price", e.target.value)}
                            />
                          </td>
                          <td>
                            <input
                              type="text"
                              inputMode="numeric"
                              pattern="\\d{4}-\\d{2}-\\d{2}"
                              placeholder="YYYY-MM-DD"
                              value={row.purchase_date}
                              onChange={(e) => updateAcceptedPosition(row.ticker, "purchase_date", e.target.value)}
                            />
                          </td>
                          <td>{fmt$(value)}</td>
                          <td style={{ color: gainPct >= 0 ? "var(--forest)" : "var(--rose)" }}>{fmtPct(gainPct)}</td>
                          <td style={{ color: Math.abs(drift) <= 2 ? "var(--forest)" : "var(--amber)" }}>
                            {fmtPct(drift)} pts
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="fine-print" style={{ marginTop: 10 }}>
                Taxable estimates apply the selected rebalance tax rate to unrealized gains only. Tax-deferred accounts show performance before current tax drag, which can lift displayed CAGR.
              </p>
              <div style={{ marginTop: 12, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                <p className="fine-print" style={{ margin: 0 }}>
                  Saving creates a new accepted allocation batch, so multiple accepted allocations can be tracked over time.
                </p>
                <button type="button" className="primary-button" onClick={saveAcceptedTrades} disabled={savingAccepted}>
                  {savingAccepted ? <Loader2 size={16} className="spin-icon" /> : <CheckCircle2 size={16} />}
                  Save accepted trades
                </button>
              </div>
              {saveMessage && (
                <div className="fine-print" style={{ marginTop: 8, color: saveMessage.startsWith("Saved") ? "var(--forest)" : "var(--rose)" }}>
                  {saveMessage}
                </div>
              )}
            </section>
          )}

          {savedAllocations.length > 0 && (
            <SavedAcceptedAllocations allocations={savedAllocations} />
          )}

          {/* EPS signal strength */}
          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>EPS Signal Strength vs S&amp;P 500</h2>
              <Activity size={18} />
            </div>
            <p className="fine-print">
              Signal year: {result.sp500_signals.signal_year} · S&amp;P 500 trailing EPS:{" "}
              {result.sp500_signals.trailing_eps_growth}% · Forward NTM: {result.sp500_signals.forward_eps_growth}%
            </p>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={result.allocations.map((a, i) => ({
                  ticker: a.ticker,
                  trailing_beat: a.trailing_eps_beat,
                  forward_beat: a.forward_eps_beat,
                  color: SECTOR_COLORS[i % SECTOR_COLORS.length],
                }))}
                margin={{ top: 10, right: 20, left: 10, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
                <XAxis dataKey="ticker" tick={{ fontSize: 12 }} />
                <YAxis tickFormatter={(v) => v + " pp"} tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v: number) => v.toFixed(1) + " pp above S&P 500"} />
                <Legend />
                <Bar dataKey="trailing_beat" name="Trailing EPS Beat" fill="#0f766e" radius={[3, 3, 0, 0]} />
                <Bar dataKey="forward_beat" name="Forward EPS Beat" fill="#2563eb" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </section>

          {/* Rebalancing action guide */}
          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Rebalancing Action Guide</h2>
              <RefreshCw size={18} />
            </div>
            <div style={{ display: "grid", gap: 10 }}>
              <div
                style={{
                  background: "var(--paper)",
                  borderRadius: 8,
                  padding: "12px 16px",
                  fontSize: 13,
                }}
              >
                <strong>Step 1 — Liquidate non-selected positions</strong>
                <p style={{ margin: "4px 0 0", color: "var(--muted)" }}>
                  Sell any sector ETFs not in the current selection.{" "}
                  {accountType === "tax_deferred" ? (
                    <>No current tax drag is modeled for tax-deferred accounts.</>
                  ) : (
                    <>Gains are taxed at <strong>{taxRateLabel}</strong>. Losses create carryforward.</>
                  )}
                </p>
              </div>
              {result.allocations.map((alloc, i) => (
                <div
                  key={alloc.ticker}
                  style={{
                    background: "var(--paper)",
                    borderRadius: 8,
                    padding: "12px 16px",
                    borderLeft: `3px solid ${SECTOR_COLORS[i % SECTOR_COLORS.length]}`,
                    fontSize: 13,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <strong>
                      Buy {alloc.ticker} — {alloc.sector_name}
                    </strong>
                    <span style={{ color: SECTOR_COLORS[i % SECTOR_COLORS.length], fontWeight: 700 }}>
                      {fmt$(alloc.dollar_amount)} ({(alloc.weight * 100).toFixed(1)}%)
                    </span>
                  </div>
                  <p style={{ margin: "4px 0 0", color: "var(--muted)" }}>
                    Trailing EPS {fmtPct(alloc.trailing_eps_beat)} vs S&amp;P · Forward EPS{" "}
                    {fmtPct(alloc.forward_eps_beat)} vs S&amp;P
                  </p>
                </div>
              ))}
              <div
                style={{
                  background: "#fef3c7",
                  borderRadius: 8,
                  padding: "12px 16px",
                  fontSize: 13,
                  border: "1px solid var(--amber)",
                }}
              >
                <strong>Next rebalance date</strong>
                <p style={{ margin: "4px 0 0", color: "var(--muted)" }}>{nextRebalance}</p>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function AcceptedTradesTab() {
  const [allocations, setAllocations] = useState<SavedAcceptedAllocation[]>([]);
  const [drafts, setDrafts] = useState<Record<number, { rebalance_date: string; rebalance_status: RebalanceStatus; rebalance_notes: string }>>({});
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    void loadTrades();
  }, []);

  async function loadTrades() {
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<SavedAcceptedAllocation[]>("/sector-rotation/accepted-allocations");
      setAllocations(data);
      setDrafts(Object.fromEntries(data.map((allocation) => [allocation.id, {
        rebalance_date: allocation.rebalance_date ?? "",
        rebalance_status: allocation.rebalance_status,
        rebalance_notes: allocation.rebalance_notes ?? "",
      }])));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load accepted trades.");
    } finally {
      setLoading(false);
    }
  }

  function updateDraft(id: number, field: "rebalance_date" | "rebalance_status" | "rebalance_notes", value: string) {
    setDrafts((rows) => ({
      ...rows,
      [id]: {
        rebalance_date: rows[id]?.rebalance_date ?? "",
        rebalance_status: rows[id]?.rebalance_status ?? "planned",
        rebalance_notes: rows[id]?.rebalance_notes ?? "",
        [field]: value,
      },
    }));
    setMessage("");
  }

  async function saveRebalance(allocation: SavedAcceptedAllocation) {
    const draft = drafts[allocation.id];
    if (!draft) return;

    setSavingId(allocation.id);
    setMessage("");
    try {
      const saved = await apiFetch<SavedAcceptedAllocation>(`/sector-rotation/accepted-allocations/${allocation.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          rebalance_date: draft.rebalance_date || null,
          rebalance_status: draft.rebalance_status,
          rebalance_notes: draft.rebalance_notes || null,
        }),
      });
      setAllocations((rows) => rows.map((row) => (row.id === saved.id ? saved : row)));
      setMessage(`Updated ${formatDateTime(saved.updated_at)}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update rebalance status.");
    } finally {
      setSavingId(null);
    }
  }

  if (loading) {
    return (
      <section className="dashboard-panel" style={{ textAlign: "center", padding: 40 }}>
        <Loader2 size={24} className="spin-icon" />
        <p style={{ marginTop: 8, color: "var(--muted)" }}>Loading accepted trades…</p>
      </section>
    );
  }

  return (
    <div className="form-stack">
      <section className="dashboard-panel">
        <div className="panel-header">
          <h2>Accepted Trades</h2>
          <RefreshCw size={18} />
        </div>
        <p className="fine-print">
          Review saved allocation batches, track the account and weighting method used, and record whether the rebalance was completed or changed.
        </p>
        {error && (
          <div className="error-message" style={{ marginTop: 8 }}>
            <AlertCircle size={14} /> {error}
          </div>
        )}
        {message && (
          <div className="fine-print" style={{ marginTop: 8, color: "var(--forest)" }}>{message}</div>
        )}
      </section>

      {allocations.length === 0 ? (
        <section className="dashboard-panel">
          <p style={{ margin: 0, color: "var(--muted)" }}>
            No accepted trades saved yet. Use Live Advisor, accept an allocation, enter shares and cost, then save accepted trades.
          </p>
        </section>
      ) : (
        allocations.map((allocation) => {
          const stats = savedAllocationStats(allocation);
          const draft = drafts[allocation.id] ?? {
            rebalance_date: allocation.rebalance_date ?? "",
            rebalance_status: allocation.rebalance_status,
            rebalance_notes: allocation.rebalance_notes ?? "",
          };

          return (
            <section className="dashboard-panel sector-trade-card" key={allocation.id}>
              <div className="sector-trade-card-head">
                <div>
                  <p className="eyebrow">Portfolio Entry #{allocation.id}</p>
                  <h2>{formatDateTime(allocation.created_at)}</h2>
                  <span>
                    {allocation.account_type === "tax_deferred" ? "Tax-deferred" : "Taxable"} · {weightingLabel(allocation.weighting_method)} · {allocation.time_frame}
                  </span>
                </div>
                <div className={`sector-rebalance-status ${draft.rebalance_status}`}>
                  {REBALANCE_STATUS_LABELS[draft.rebalance_status]}
                </div>
              </div>

              <div className="sector-performance-summary">
                <article>
                  <span>Market Value</span>
                  <strong>{fmt$(stats.value)}</strong>
                  <small>{allocation.trades.length} ETF entries</small>
                </article>
                <article>
                  <span>Gain / Loss</span>
                  <strong style={{ color: stats.gain >= 0 ? "var(--forest)" : "var(--rose)" }}>{fmt$(stats.gain)}</strong>
                  <small>{stats.basis > 0 ? fmtPct((stats.gain / stats.basis) * 100) : "0.0%"}</small>
                </article>
                <article>
                  <span>After-Tax Value</span>
                  <strong>{fmt$(stats.afterTaxValue)}</strong>
                  <small>{allocation.account_type === "tax_deferred" ? "No current tax drag" : `${fmt$(stats.taxImpact)} estimated tax`}</small>
                </article>
                <article>
                  <span>CAGR</span>
                  <strong>{stats.displayCagr}</strong>
                  <small>{stats.displayCagr === "N/A" ? "needs 30+ days held" : allocation.account_type === "tax_deferred" ? "pre-tax CAGR" : "after estimated taxes"}</small>
                </article>
              </div>

              <div className="sector-trade-meta-grid">
                <div className="field">
                  <label>Rebalance Date</label>
                  <input
                    type="text"
                    inputMode="numeric"
                    pattern="\\d{4}-\\d{2}-\\d{2}"
                    placeholder="YYYY-MM-DD"
                    value={draft.rebalance_date}
                    onChange={(e) => updateDraft(allocation.id, "rebalance_date", e.target.value)}
                  />
                </div>
                <div className="field">
                  <label>Rebalance Status</label>
                  <select
                    value={draft.rebalance_status}
                    onChange={(e) => updateDraft(allocation.id, "rebalance_status", e.target.value)}
                  >
                    <option value="planned">Planned</option>
                    <option value="completed">Completed</option>
                    <option value="partial">Partial / changed</option>
                    <option value="skipped">Skipped</option>
                  </select>
                </div>
                <div className="field">
                  <label>Changes Done / Notes</label>
                  <input
                    type="text"
                    value={draft.rebalance_notes}
                    onChange={(e) => updateDraft(allocation.id, "rebalance_notes", e.target.value)}
                    placeholder="Example: bought all except XLE, added cash later"
                  />
                </div>
                <button
                  type="button"
                  className="primary-button"
                  onClick={() => saveRebalance(allocation)}
                  disabled={savingId === allocation.id}
                >
                  {savingId === allocation.id ? <Loader2 size={16} className="spin-icon" /> : <CheckCircle2 size={16} />}
                  Save
                </button>
              </div>

              <div style={{ overflowX: "auto" }}>
                <table className="allocation-table">
                  <thead>
                    <tr>
                      <th>ETF</th>
                      <th>Sector</th>
                      <th>Target</th>
                      <th>Shares</th>
                      <th>Cost / Sh.</th>
                      <th>Current / Sh.</th>
                      <th>Purchase Date</th>
                      <th>Value</th>
                      <th>Gain / Loss</th>
                    </tr>
                  </thead>
                  <tbody>
                    {allocation.trades.map((trade) => (
                      <tr key={trade.id}>
                        <td><strong>{trade.ticker}</strong></td>
                        <td>{trade.sector_name}</td>
                        <td>{(trade.target_weight * 100).toFixed(1)}%</td>
                        <td>{trade.shares.toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
                        <td>{fmt$(trade.cost_basis_per_share)}</td>
                        <td>{fmt$(trade.current_price)}</td>
                        <td>{trade.purchase_date}</td>
                        <td>{fmt$(trade.market_value)}</td>
                        <td style={{ color: trade.gain_loss >= 0 ? "var(--forest)" : "var(--rose)" }}>
                          {fmt$(trade.gain_loss)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          );
        })
      )}
    </div>
  );
}

function SavedAcceptedAllocations({ allocations }: { allocations: SavedAcceptedAllocation[] }) {
  return (
    <section className="dashboard-panel">
      <div className="panel-header">
        <h2>Accepted Trades History</h2>
        <Clock size={18} />
      </div>
      <div className="sector-accepted-history">
        {allocations.map((allocation) => {
          const stats = savedAllocationStats(allocation);
          return (
            <article key={allocation.id}>
              <div className="sector-accepted-history-head">
                <div>
                  <strong>{formatDateTime(allocation.created_at)}</strong>
                  <span>{weightingLabel(allocation.weighting_method)} · {allocation.account_type === "tax_deferred" ? "Tax-deferred" : "Taxable"} · {REBALANCE_STATUS_LABELS[allocation.rebalance_status]}</span>
                </div>
                <div>
                  <strong>{fmt$(stats.value)}</strong>
                  <span style={{ color: stats.gain >= 0 ? "var(--forest)" : "var(--rose)" }}>{fmt$(stats.gain)} · {stats.displayCagr}</span>
                </div>
              </div>
              <div className="sector-accepted-trade-grid">
                {allocation.trades.map((trade) => (
                  <div key={trade.id}>
                    <strong>{trade.ticker}</strong>
                    <span>{trade.shares.toLocaleString(undefined, { maximumFractionDigits: 4 })} sh · {fmt$(trade.current_price)} / sh</span>
                    <span>{fmt$(trade.market_value)} · {(trade.target_weight * 100).toFixed(1)}% target</span>
                  </div>
                ))}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

// ── History Tab ────────────────────────────────────────────────────────────

function HistoryTab() {
  const [rows, setRows] = useState<SelectionHistoryRow[]>([]);
  const [weightingMethod, setWeightingMethod] = useState<WeightingMethod>("equal");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      setLoading(true);
      setError("");
      try {
        const data = await apiFetch<SelectionHistoryRow[]>(`/sector-rotation/selection-history?weighting_method=${weightingMethod}`);
        setRows(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load history");
      } finally {
        setLoading(false);
      }
    })();
  }, [weightingMethod]);

  if (loading) {
    return (
      <section className="dashboard-panel" style={{ textAlign: "center", padding: 40 }}>
        <Loader2 size={24} className="spin-icon" />
        <p style={{ marginTop: 8, color: "var(--muted)" }}>Loading selection history…</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="dashboard-panel">
        <div className="error-message">
          <AlertCircle size={14} /> {error}
        </div>
      </section>
    );
  }

  const totalAlphaYears = rows.filter((r) => r.delta_pct > 0).length;
  const avgAlpha = rows.reduce((sum, r) => sum + r.delta_pct, 0) / rows.length;

  return (
    <div className="form-stack">
      {/* Summary stats */}
      <section className="dashboard-panel">
        <div className="panel-header">
          <h2>Historical Algorithm Selections (2015–2025)</h2>
          <Clock size={18} />
        </div>
        <WeightingSelector value={weightingMethod} onChange={setWeightingMethod} />
        <p className="fine-print" style={{ marginTop: 8, marginBottom: 12 }}>
          Showing {weightingLabel(weightingMethod)} historical returns.
        </p>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 12,
            marginBottom: 20,
          }}
        >
          <div style={{ background: "var(--paper)", borderRadius: 8, padding: "12px 14px" }}>
            <div className="fine-print">Outperformed SPY</div>
            <strong style={{ fontSize: 22, color: "var(--forest)" }}>
              {totalAlphaYears}/{rows.length}
            </strong>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>years</div>
          </div>
          <div style={{ background: "var(--paper)", borderRadius: 8, padding: "12px 14px" }}>
            <div className="fine-print">Avg Annual Alpha</div>
            <strong
              style={{
                fontSize: 22,
                color: avgAlpha >= 0 ? "var(--forest)" : "var(--rose)",
              }}
            >
              {fmtPct(avgAlpha, 1)}
            </strong>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>vs SPY</div>
          </div>
          <div style={{ background: "var(--paper)", borderRadius: 8, padding: "12px 14px" }}>
            <div className="fine-print">Best Year (Alpha)</div>
            <strong style={{ fontSize: 22, color: "var(--forest)" }}>
              {fmtPct(Math.max(...rows.map((r) => r.delta_pct)), 1)}
            </strong>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>
              {rows.find((r) => r.delta_pct === Math.max(...rows.map((r2) => r2.delta_pct)))?.year}
            </div>
          </div>
        </div>

        {/* Alpha bar chart */}
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
            <XAxis dataKey="year" tick={{ fontSize: 11 }} />
            <YAxis tickFormatter={(v) => v + "%"} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v: number) => v.toFixed(1) + "%"} />
            <Bar dataKey="delta_pct" name="Alpha vs SPY" radius={[3, 3, 0, 0]}>
              {rows.map((row) => (
                <Cell key={row.year} fill={row.delta_pct >= 0 ? "#0f766e" : "#dc2626"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <p className="fine-print">Green = outperformed SPY · Red = underperformed SPY</p>
      </section>

      {/* Year-by-year table */}
      <section className="dashboard-panel">
        <div className="panel-header">
          <h2>Year-by-Year Selections</h2>
          <Calendar size={18} />
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="allocation-table">
            <thead>
              <tr>
                <th>Year</th>
                <th>Selected Sectors</th>
                <th>Weights</th>
                <th>Algo Return</th>
                <th>SPY Return</th>
                <th>Alpha</th>
                <th>Key Signal</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.year}
                  style={{
                    background: row.delta_pct >= 0 ? "#f0fdf4" : "#fff1f2",
                  }}
                >
                  <td>
                    <strong>{row.year}</strong>
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      {row.selected_sectors.map((s) => (
                        <span
                          key={s}
                          style={{
                            background: "var(--mint)",
                            color: "var(--forest)",
                            border: "1px solid var(--forest)",
                            borderRadius: 4,
                            padding: "1px 6px",
                            fontSize: 12,
                            fontWeight: 600,
                          }}
                        >
                          {s}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td style={{ fontSize: 12 }}>
                    {row.selected_sectors.map((sector) => (
                      <span key={sector} style={{ display: "block", whiteSpace: "nowrap" }}>
                        {sector}: {((row.sector_weights[sector] ?? 0) * 100).toFixed(1)}%
                      </span>
                    ))}
                  </td>
                  <td style={{ color: row.algo_return_pct >= 0 ? "var(--forest)" : "var(--rose)", fontWeight: 600 }}>
                    {fmtPct(row.algo_return_pct)}
                  </td>
                  <td>{fmtPct(row.spy_return_pct)}</td>
                  <td>
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 4,
                        fontWeight: 700,
                        color: row.delta_pct >= 0 ? "var(--forest)" : "var(--rose)",
                      }}
                    >
                      {row.delta_pct >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                      {fmtPct(row.delta_pct)}
                    </span>
                  </td>
                  <td style={{ fontSize: 12, color: "var(--muted)" }}>{row.key_signal}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
