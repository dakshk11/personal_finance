"use client";

import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Download,
  KeyRound,
  Loader2,
  LockKeyhole,
  PieChart,
  Play,
  RefreshCw,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  XCircle
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { AppHeader } from "@/components/AppHeader";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import {
  ConcentrationAnalysisOut,
  ConcentrationHoldingIn,
  CurrentHoldingIn,
  DiversifyBacktestOut,
  DiversifyRecommendationsOut,
  DiversifyYearResultOut,
  RecommendTradeOut,
  apiFetch,
  currency,
  percent
} from "@/lib/api";

// ── Helpers ───────────────────────────────────────────────────────────────────

const SAMPLE_HOLDINGS = "TSLA,Tesla,Consumer Discretionary,100,250";

function parseHoldings(csv: string): ConcentrationHoldingIn[] {
  return csv
    .trim()
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .flatMap((line) => {
      const parts = line.split(",").map((p) => p.trim());
      const symbol = parts[0];
      const name   = parts[1] || symbol;
      const sector = parts[2] || undefined;
      const shares = parseFloat(parts[3]);
      const price  = parseFloat(parts[4]);
      if (!symbol || isNaN(shares) || isNaN(price)) return [];
      return [{ symbol, name, sector, shares, price }];
    });
}

function scoreColor(score: number): string {
  if (score >= 70) return "#0f766e";
  if (score >= 40) return "#d97706";
  return "#dc2626";
}

function scoreLabel(score: number): string {
  if (score >= 70) return "Well Diversified";
  if (score >= 40) return "Moderately Concentrated";
  return "Highly Concentrated";
}

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({
  label, value, sub, highlight
}: { label: string; value: string; sub?: string; highlight?: "green" | "red" | "amber" }) {
  const cls = highlight === "green" ? "stat-panel diversify-stat-green"
    : highlight === "red" ? "stat-panel diversify-stat-red"
    : highlight === "amber" ? "stat-panel diversify-stat-amber"
    : "stat-panel";
  return (
    <article className={cls}>
      <h3>{label}</h3>
      <strong>{value}</strong>
      {sub && <p>{sub}</p>}
    </article>
  );
}

// ── Trade row ─────────────────────────────────────────────────────────────────

function TradeRow({ trade }: { trade: RecommendTradeOut }) {
  return (
    <div className={`diversify-trade-row ${trade.action === "SELL" ? "diversify-trade-sell" : "diversify-trade-buy"}`}>
      <span className="diversify-trade-badge">{trade.action}</span>
      <div className="diversify-trade-detail">
        <strong>{trade.symbol}</strong>
        <span className="fine-print">{trade.name}</span>
      </div>
      <div className="diversify-trade-numbers">
        <span>{trade.shares.toFixed(2)} sh @ {currency(trade.estimated_price)}</span>
        <span className="fine-print">{currency(trade.notional)}</span>
      </div>
      <p className="fine-print diversify-trade-reason">{trade.reason}</p>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function DiversifyPage() {
  // ── Alpha Vantage key (persisted in localStorage) ─────────────────────────
  const [avKey, setAvKey]           = useState("");
  const [avKeyInput, setAvKeyInput] = useState("");
  const [avKeySaved, setAvKeySaved] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("diversify_av_key") ?? "";
    setAvKey(saved);
    setAvKeySaved(!!saved);
  }, []);

  function saveAvKey() {
    const trimmed = avKeyInput.trim();
    if (!trimmed) return;
    localStorage.setItem("diversify_av_key", trimmed);
    setAvKey(trimmed);
    setAvKeySaved(true);
    setAvKeyInput("");
  }

  function removeAvKey() {
    localStorage.removeItem("diversify_av_key");
    setAvKey("");
    setAvKeySaved(false);
  }

  // ── Form state ────────────────────────────────────────────────────────────
  const [holdingsCsv, setHoldingsCsv]         = useState(SAMPLE_HOLDINGS);
  const [concentratedSymbol, setConcentratedSymbol] = useState("TSLA");
  const [concentratedShares, setConcentratedShares] = useState(100);
  const [avgCostBasis, setAvgCostBasis]        = useState(200);
  const [startingCash, setStartingCash]        = useState(50000);
  const [taxRate, setTaxRate]                  = useState(35);
  const [harvestThreshold, setHarvestThreshold] = useState(3);
  const [years, setYears]                       = useState<number[]>([2022, 2023, 2024]);
  const [schdHoldingsCsv, setSchdHoldingsCsv] = useState(
    "QCOM,200,250\nTXN,150,180\nUNH,80,520"
  );

  // ── Result state ──────────────────────────────────────────────────────────
  const [concentration, setConcentration] = useState<ConcentrationAnalysisOut | null>(null);
  const [backtest, setBacktest]           = useState<DiversifyBacktestOut | null>(null);
  const [recommendations, setRecommendations] = useState<DiversifyRecommendationsOut | null>(null);
  const [loading, setLoading]             = useState("");
  const [error, setError]                 = useState("");

  // ── Actions ───────────────────────────────────────────────────────────────

  async function analyzeConcentration(event: FormEvent) {
    event.preventDefault();
    const holdings = parseHoldings(holdingsCsv);
    if (!holdings.length) { setError("Enter at least one holding."); return; }
    setLoading("analyze"); setError("");
    try {
      const result = await apiFetch<ConcentrationAnalysisOut>("/diversify/analyze", {
        method: "POST",
        body: JSON.stringify({ holdings, index_symbol: "SCHD" })
      });
      setConcentration(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Concentration analysis failed.");
    } finally {
      setLoading("");
    }
  }

  async function runBacktest(event: FormEvent) {
    event.preventDefault();
    if (!concentratedSymbol.trim()) { setError("Enter the concentrated stock symbol."); return; }
    setLoading("backtest"); setError("");
    try {
      const result = await apiFetch<DiversifyBacktestOut>("/diversify/backtest", {
        method: "POST",
        body: JSON.stringify({
          concentrated_symbol: concentratedSymbol.toUpperCase(),
          concentrated_shares: concentratedShares,
          avg_cost_basis: avgCostBasis,
          starting_cash: startingCash,
          years,
          estimated_tax_rate: taxRate / 100,
          harvest_threshold: harvestThreshold / 100,
          alpha_vantage_key: avKey || null,
        })
      });
      setBacktest(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backtest failed. Check the symbol and try again.");
    } finally {
      setLoading("");
    }
  }

  async function getRecommendations(event: FormEvent) {
    event.preventDefault();
    setLoading("recommend"); setError("");
    const currentHoldings: CurrentHoldingIn[] = schdHoldingsCsv
      .trim().split("\n")
      .map((l) => l.trim()).filter(Boolean)
      .flatMap((l) => {
        const [sym, sharesStr, costStr] = l.split(",").map((s) => s.trim());
        const shares = parseFloat(sharesStr), avgCost = parseFloat(costStr);
        if (!sym || isNaN(shares) || isNaN(avgCost)) return [];
        return [{ symbol: sym, shares, avg_cost: avgCost }];
      });
    try {
      const result = await apiFetch<DiversifyRecommendationsOut>("/diversify/recommendations", {
        method: "POST",
        body: JSON.stringify({
          concentrated_symbol: concentratedSymbol.toUpperCase(),
          concentrated_shares: concentratedShares,
          avg_cost_basis: avgCostBasis,
          current_schd_holdings: currentHoldings,
          estimated_tax_rate: taxRate / 100,
          harvest_threshold: harvestThreshold / 100,
        })
      });
      setRecommendations(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not fetch recommendations.");
    } finally {
      setLoading("");
    }
  }

  function downloadTradesCsv() {
    if (!recommendations) return;
    const allTrades = [
      ...recommendations.harvest_trades,
      ...recommendations.replacement_trades,
      ...(recommendations.concentrated_sell ? [recommendations.concentrated_sell] : [])
    ];
    const header = "Action,Symbol,Name,Shares,Est Price,Notional,Reason";
    const rows = allTrades.map(
      (t) => `${t.action},${t.symbol},"${t.name}",${t.shares},${t.estimated_price},${t.notional},"${t.reason}"`
    );
    const csv = [header, ...rows].join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = `diversify_trades_${recommendations.as_of_date}.csv`;
    a.click();
  }

  function toggleYear(y: number) {
    setYears((prev) => prev.includes(y) ? prev.filter((x) => x !== y) : [...prev, y].sort());
  }

  // ── Chart data ────────────────────────────────────────────────────────────

  const chartData = backtest?.years.map((yr) => ({
    year: yr.year.toString(),
    harvested: Math.round(yr.harvested_losses),
    saved: Math.round(yr.tax_savings),
    concentration: Math.round(yr.concentration_pct * 100),
  })) ?? [];

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <main className="dashboard-shell">
      <AppHeader
        title="Portfolio Diversification"
        actions={
          <>
            <Link className="ghost-button" href="/dashboard">Dashboard</Link>
            <Link className="ghost-button" href="/portfolio">Portfolio</Link>
          </>
        }
      />
      <div className="dashboard-disclaimer">
        <LegalDisclaimer compact />
      </div>

      {/* ── Hero banner ── */}
      <div className="diversify-hero">
        <div className="diversify-hero-text">
          <p className="eyebrow">SCHD Diversification Tool</p>
          <h2>Gradually move a concentrated stock into SCHD using Tax-Loss Harvesting</h2>
          <p>
            Inspired by Frec&apos;s Diversify methodology and the Malkin et al. (2025) academic research.
            Harvest losses from your SCHD basket to offset gains from selling your concentrated position —
            reducing taxes while diversifying into 103 dividend-quality stocks.
          </p>
        </div>
        <div className="diversify-hero-stats">
          <div><strong>SCHD</strong><span>103 dividend stocks</span></div>
          <div><strong>TLH</strong><span>funds diversification</span></div>
          <div><strong>yfinance</strong><span>real historical data</span></div>
        </div>
      </div>

      {error && <div className="error" style={{ margin: "0 clamp(16px,4vw,36px) 12px" }}>{error}</div>}

      <div className="diversify-layout">

        {/* ── LEFT: Configuration ── */}
        <div className="diversify-config">

          {/* Alpha Vantage Key */}
          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Alpha Vantage API Key</h2>
              <KeyRound size={18} />
            </div>
            <p className="fine-print" style={{ marginBottom: "10px" }}>
              Used to fetch real monthly price history for the backtest.
              Free at{" "}
              <a href="https://www.alphavantage.co/support/#api-key" target="_blank" rel="noopener noreferrer">
                alphavantage.co
              </a>{" "}
              · 25 calls/day · full history per call · cached after first use.
            </p>
            {avKeySaved ? (
              <div className="diversify-av-saved">
                <span className="status-pill"><LockKeyhole size={13} /> Key saved</span>
                <span className="fine-print">Stored in browser only · never sent to our servers</span>
                <button className="ghost-button danger-button" type="button" onClick={removeAvKey} style={{ padding: "4px 10px", fontSize: "0.82rem" }}>
                  Remove
                </button>
              </div>
            ) : (
              <div className="diversify-av-input">
                <input
                  type="password"
                  autoComplete="off"
                  placeholder="Enter your Alpha Vantage API key…"
                  value={avKeyInput}
                  onChange={(e) => setAvKeyInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") saveAvKey(); }}
                />
                <button className="primary-button" type="button" onClick={saveAvKey} disabled={!avKeyInput.trim()} style={{ padding: "7px 14px" }}>
                  <LockKeyhole size={14} /> Save
                </button>
              </div>
            )}
          </section>

          {/* Concentration Analysis */}
          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Step 1 — Analyze Concentration</h2>
              <PieChart size={18} />
            </div>
            <form className="form-stack" onSubmit={analyzeConcentration}>
              <div className="field">
                <label htmlFor="holdings-csv">
                  Current holdings <span className="fine-print">(symbol, name, sector, shares, price — one per line)</span>
                </label>
                <textarea
                  id="holdings-csv"
                  rows={4}
                  value={holdingsCsv}
                  onChange={(e) => setHoldingsCsv(e.target.value)}
                  placeholder={SAMPLE_HOLDINGS}
                />
              </div>
              <button className="primary-button" type="submit" disabled={loading === "analyze"}>
                {loading === "analyze" ? <Loader2 size={16} className="spin-icon" /> : <PieChart size={16} />}
                Analyze Concentration
              </button>
            </form>
          </section>

          {/* Backtest Config */}
          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Step 2 — Backtest Diversification</h2>
              <Play size={18} />
            </div>
            <form className="form-stack" onSubmit={runBacktest}>
              <div className="diversify-form-grid">
                <div className="field">
                  <label>Concentrated symbol</label>
                  <input value={concentratedSymbol} onChange={(e) => setConcentratedSymbol(e.target.value.toUpperCase())} placeholder="TSLA" />
                </div>
                <div className="field">
                  <label>Shares held</label>
                  <input type="number" min={1} value={concentratedShares} onChange={(e) => setConcentratedShares(Number(e.target.value))} />
                </div>
                <div className="field">
                  <label>Avg cost / share ($)</label>
                  <input type="number" min={0.01} step={0.01} value={avgCostBasis} onChange={(e) => setAvgCostBasis(Number(e.target.value))} />
                </div>
                <div className="field">
                  <label>Additional cash to invest ($)</label>
                  <input type="number" min={0} value={startingCash} onChange={(e) => setStartingCash(Number(e.target.value))} />
                </div>
                <div className="field">
                  <label>Tax rate (%)</label>
                  <input type="number" min={0} max={60} step={1} value={taxRate} onChange={(e) => setTaxRate(Number(e.target.value))} />
                </div>
                <div className="field">
                  <label>Harvest threshold (%)</label>
                  <input type="number" min={0.5} max={30} step={0.5} value={harvestThreshold} onChange={(e) => setHarvestThreshold(Number(e.target.value))} />
                </div>
              </div>
              <div className="field">
                <label>Simulation years</label>
                <div className="diversify-year-toggles">
                  {[2020, 2021, 2022, 2023, 2024].map((y) => (
                    <button
                      key={y} type="button"
                      className={years.includes(y) ? "active" : ""}
                      onClick={() => toggleYear(y)}
                    >
                      {y}
                    </button>
                  ))}
                </div>
              </div>
              {!avKey && (
                <p className="fine-print" style={{ color: "#b45309" }}>
                  <AlertTriangle size={12} style={{ display: "inline", marginRight: "4px" }} />
                  Save an Alpha Vantage key above to fetch real price data.
                  Without it, only cached symbols will be used.
                </p>
              )}
              <button className="primary-button" type="submit" disabled={loading === "backtest" || !years.length}>
                {loading === "backtest" ? <Loader2 size={16} className="spin-icon" /> : <Play size={16} />}
                Run Backtest
              </button>
            </form>
          </section>

          {/* Self-Diversify */}
          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Step 3 — Self-Diversify (This Month)</h2>
              <RefreshCw size={18} />
            </div>
            <form className="form-stack" onSubmit={getRecommendations}>
              <div className="field">
                <label htmlFor="schd-holdings">
                  Your current SCHD basket <span className="fine-print">(symbol, shares, avg cost — one per line)</span>
                </label>
                <textarea
                  id="schd-holdings"
                  rows={4}
                  value={schdHoldingsCsv}
                  onChange={(e) => setSchdHoldingsCsv(e.target.value)}
                  placeholder={"QCOM,200,250\nKO,100,62"}
                />
              </div>
              <button className="primary-button" type="submit" disabled={loading === "recommend"}>
                {loading === "recommend" ? <Loader2 size={16} className="spin-icon" /> : <RefreshCw size={16} />}
                Get Trade Recommendations
              </button>
            </form>
          </section>
        </div>

        {/* ── RIGHT: Results ── */}
        <div className="diversify-results">

          {/* Concentration Result */}
          {concentration && (
            <section className="dashboard-panel">
              <div className="panel-header">
                <h2>Concentration Analysis</h2>
                <span
                  className={concentration.diversification_score >= 70 ? "status-pill" : "risk-pill"}
                >
                  {scoreLabel(concentration.diversification_score)}
                </span>
              </div>

              {/* Score gauge */}
              <div className="diversify-score-row">
                <div className="diversify-score-gauge">
                  <div
                    className="diversify-score-fill"
                    style={{
                      width: `${concentration.diversification_score}%`,
                      background: scoreColor(concentration.diversification_score)
                    }}
                  />
                </div>
                <div className="diversify-score-label">
                  <strong style={{ color: scoreColor(concentration.diversification_score) }}>
                    {concentration.diversification_score}
                  </strong>
                  <span className="fine-print">/ 100</span>
                </div>
              </div>

              {/* Key metrics */}
              <div className="stat-grid" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))", marginBottom: "14px" }}>
                <StatCard label="HHI" value={concentration.hhi.toFixed(3)}
                  sub="< 0.15 = diversified"
                  highlight={concentration.hhi < 0.15 ? "green" : concentration.hhi < 0.35 ? "amber" : "red"} />
                <StatCard label="Top Holding" value={`${concentration.top_holding} ${percent(concentration.top_holding_weight)}`}
                  highlight={concentration.top_holding_weight > 0.25 ? "red" : undefined} />
                <StatCard label="Active Share" value={percent(concentration.active_share)}
                  sub="vs SCHD top-25" />
              </div>

              {/* Sector gap table */}
              <div className="table-wrap">
                <table className="wheel-table">
                  <thead>
                    <tr>
                      <th>Sector</th>
                      <th className="right">Portfolio</th>
                      <th className="right">SCHD</th>
                      <th className="right">Gap</th>
                    </tr>
                  </thead>
                  <tbody>
                    {concentration.sector_vs_index.slice(0, 8).map((row) => (
                      <tr key={row.sector}>
                        <td>{row.sector}</td>
                        <td className="right">{percent(row.portfolio_weight)}</td>
                        <td className="right">{percent(row.index_weight)}</td>
                        <td className={`right ${row.gap > 0.1 ? "wheel-red" : row.gap < -0.1 ? "wheel-amber" : "wheel-dim"}`}>
                          {row.gap > 0 ? "+" : ""}{percent(row.gap)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Warnings */}
              {concentration.concentration_warnings.length > 0 && (
                <div className="diversify-warnings">
                  {concentration.concentration_warnings.map((w) => (
                    <p key={w}><AlertTriangle size={13} /> {w}</p>
                  ))}
                </div>
              )}
            </section>
          )}

          {/* Backtest Result */}
          {backtest && (
            <section className="dashboard-panel">
              <div className="panel-header">
                <h2>Backtest Results</h2>
                <span className={backtest.tlh_wins ? "status-pill" : "risk-pill"}>
                  {backtest.tlh_wins ? <><CheckCircle2 size={13} /> TLH Wins</> : <><XCircle size={13} /> Sell Now Cheaper</>}
                </span>
              </div>

              {/* Savings summary */}
              <div className="stat-grid" style={{ marginBottom: "14px" }}>
                <StatCard
                  label="Total TLH Tax Savings"
                  value={currency(backtest.total_tax_savings)}
                  sub={`from ${currency(backtest.total_harvested_losses)} harvested losses`}
                  highlight="green"
                />
                <StatCard
                  label="Immediate Sell Tax Cost"
                  value={currency(backtest.immediate_sell_tax_cost)}
                  sub="if you sold everything today"
                  highlight="red"
                />
                <StatCard
                  label="Net TLH Benefit"
                  value={currency(backtest.net_tlh_benefit)}
                  sub="after estimated tracking cost"
                  highlight={backtest.net_tlh_benefit > 0 ? "green" : "red"}
                />
                <StatCard
                  label="TLH vs Immediate Sell"
                  value={currency(Math.abs(backtest.savings_vs_immediate_sell))}
                  sub={backtest.tlh_wins ? "you save more with TLH" : "selling now is cheaper"}
                  highlight={backtest.tlh_wins ? "green" : "amber"}
                />
              </div>

              {/* Concentration progress */}
              <div className="diversify-progress-row">
                <div>
                  <span className="fine-print">Concentration start</span>
                  <strong>{percent(backtest.concentration_start_pct)}</strong>
                </div>
                <ArrowRight size={16} style={{ color: "var(--muted)" }} />
                <div>
                  <span className="fine-print">Concentration end</span>
                  <strong style={{ color: "#0f766e" }}>{percent(backtest.concentration_end_pct)}</strong>
                </div>
              </div>

              {/* Harvested losses bar chart */}
              {chartData.length > 0 && (
                <div style={{ marginTop: "12px" }}>
                  <p className="fine-print" style={{ marginBottom: "6px" }}>Harvested losses by year</p>
                  <ResponsiveContainer width="100%" height={180}>
                    <BarChart data={chartData} margin={{ left: 0, right: 8, top: 4, bottom: 0 }}>
                      <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="year" tick={{ fontSize: 11, fill: "#6b7280" }} axisLine={false} tickLine={false} />
                      <YAxis tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11, fill: "#6b7280" }} axisLine={false} tickLine={false} width={48} />
                      <Tooltip formatter={(v: number, name: string) => [currency(v), name === "harvested" ? "Harvested Losses" : "Tax Savings"]} />
                      <Bar dataKey="harvested" name="harvested" fill="#0f766e" radius={[3, 3, 0, 0]} />
                      <Bar dataKey="saved" name="saved" fill="#ccfbf1" radius={[3, 3, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Per-year table */}
              <div className="table-wrap" style={{ marginTop: "12px" }}>
                <table className="wheel-table">
                  <thead>
                    <tr>
                      <th>Year</th>
                      <th className="right">Harvested</th>
                      <th className="right">Tax Saved</th>
                      <th className="right">Concentration</th>
                      <th className="right">Trades</th>
                    </tr>
                  </thead>
                  <tbody>
                    {backtest.years.map((yr) => (
                      <tr key={yr.year}>
                        <td>{yr.year}</td>
                        <td className="right">{currency(yr.harvested_losses)}</td>
                        <td className="right wheel-green">{currency(yr.tax_savings)}</td>
                        <td className="right">{percent(yr.concentration_pct)}</td>
                        <td className="right wheel-dim">{yr.trade_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {backtest.warnings.map((w) => (
                <p key={w} className="fine-print" style={{ marginTop: "8px", color: "#6b7280" }}>
                  <AlertTriangle size={12} style={{ display: "inline", marginRight: "4px" }} />{w}
                </p>
              ))}
            </section>
          )}

          {/* Self-Diversify Recommendations */}
          {recommendations && (
            <section className="dashboard-panel">
              <div className="panel-header">
                <div>
                  <h2>This Month&apos;s Trade Recommendations</h2>
                  <p className="fine-print">As of {recommendations.as_of_date} · live prices from Yahoo Finance</p>
                </div>
                <button className="ghost-button" onClick={downloadTradesCsv}>
                  <Download size={14} /> CSV
                </button>
              </div>

              {/* Concentration change */}
              <div className="diversify-progress-row" style={{ marginBottom: "12px" }}>
                <div><span className="fine-print">Before</span><strong>{percent(recommendations.concentration_before_pct)}</strong></div>
                <ArrowRight size={16} style={{ color: "var(--muted)" }} />
                <div><span className="fine-print">After</span><strong style={{ color: "#0f766e" }}>{percent(recommendations.concentration_after_pct)}</strong></div>
                <div><span className="fine-print">Tax cost</span><strong>{currency(recommendations.net_tax_cost)}</strong></div>
              </div>

              {/* Trades */}
              {recommendations.harvest_trades.length === 0 && !recommendations.concentrated_sell ? (
                <p className="fine-print" style={{ padding: "16px 0" }}>
                  {recommendations.warnings[0] ?? "No harvestable losses found this month. Check back when market conditions create losses in your SCHD basket."}
                </p>
              ) : (
                <div className="diversify-trades-list">
                  {recommendations.harvest_trades.map((t) => <TradeRow key={`sell-${t.symbol}`} trade={t} />)}
                  {recommendations.replacement_trades.map((t) => <TradeRow key={`buy-${t.symbol}`} trade={t} />)}
                  {recommendations.concentrated_sell && <TradeRow trade={recommendations.concentrated_sell} />}
                </div>
              )}

              {recommendations.warnings.map((w) => (
                <p key={w} className="fine-print" style={{ marginTop: "8px", color: "#6b7280" }}>
                  <AlertTriangle size={12} style={{ display: "inline", marginRight: "4px" }} />{w}
                </p>
              ))}

              <p className="fine-print" style={{ marginTop: "10px", color: "#9ca3af" }}>
                <ShieldCheck size={12} style={{ display: "inline", marginRight: "4px" }} />
                These are educational planning recommendations, not investment advice. Verify wash-sale dates,
                lot selection, and tax impact with a qualified tax professional before executing trades.
              </p>
            </section>
          )}

          {/* Empty state */}
          {!concentration && !backtest && !recommendations && (
            <section className="dashboard-panel empty-proposal">
              <PieChart size={34} />
              <h2>Start with Step 1</h2>
              <p>Enter your current holdings to see your concentration score and sector gaps vs SCHD.</p>
              <p className="fine-print" style={{ marginTop: "8px" }}>
                The backtest uses real Yahoo Finance historical prices. The self-diversify recommendations use today&apos;s live prices.
              </p>
            </section>
          )}
        </div>
      </div>
    </main>
  );
}
