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
  allocations: Allocation[];
  sp500_signals: Record<string, number | string>;
  rebalance_guidance: string;
};

type SelectionHistoryRow = {
  year: number;
  selected_sectors: string[];
  algo_return_pct: number;
  spy_return_pct: number;
  delta_pct: number;
  key_signal: string;
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

function fmt$(n: number) {
  return "$" + Math.round(n).toLocaleString();
}
function fmtPct(n: number, decimals = 1) {
  const sign = n > 0 ? "+" : "";
  return sign + n.toFixed(decimals) + "%";
}

// ── Sub-tabs ───────────────────────────────────────────────────────────────

type SubTab = "backtest" | "live-advisor" | "history";

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
      </div>

      {subTab === "backtest" && <BacktestTab />}
      {subTab === "live-advisor" && <LiveAdvisorTab />}
      {subTab === "history" && <HistoryTab />}
    </div>
  );
}

// ── Backtest Tab ───────────────────────────────────────────────────────────

function BacktestTab() {
  const [startingCapital, setStartingCapital] = useState("100000");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [expandedScenario, setExpandedScenario] = useState<string | null>(null);

  async function runBacktest() {
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<BacktestResult>("/sector-rotation/backtest", {
        method: "POST",
        body: JSON.stringify({ starting_capital: parseFloat(startingCapital) || 100000 }),
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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<LiveAllocationResult | null>(null);

  async function getAllocation() {
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<LiveAllocationResult>("/sector-rotation/live-allocation", {
        method: "POST",
        body: JSON.stringify({
          cash_amount: parseFloat(cashAmount) || 100000,
          time_frame: timeFrame,
        }),
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to get allocation");
    } finally {
      setLoading(false);
    }
  }

  const taxRateLabel = timeFrame === "quarterly" ? "54.1% STCG" : "37.1% LTCG";
  const nextRebalance =
    timeFrame === "annual"
      ? "First Monday of February (annually)"
      : timeFrame === "quarterly"
      ? "First Monday of Feb / May / Aug / Nov"
      : "One-time — no future rebalancing";

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
                <p style={{ margin: 0, fontSize: 14 }}>{result.rebalance_guidance}</p>
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
          </section>

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
                  Sell any sector ETFs not in the current selection. Gains are taxed at{" "}
                  <strong>{taxRateLabel}</strong>. Losses create carryforward.
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

// ── History Tab ────────────────────────────────────────────────────────────

function HistoryTab() {
  const [rows, setRows] = useState<SelectionHistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        const data = await apiFetch<SelectionHistoryRow[]>("/sector-rotation/selection-history");
        setRows(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load history");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

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
