"use client";

import {
  AlertTriangle,
  CheckCircle2,
  DollarSign,
  Loader2,
  PieChart as PieChartIcon,
  RefreshCw,
  TrendingUp,
  WalletCards,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiFetch, apiUrl } from "@/lib/api";

const TARGET_VALUE = 150_000;
const QUOTE_TIMEOUT_MS = 25_000;
const COLORS = ["#21c997", "#f59e0b", "#34d399", "#a78bfa", "#f472b6", "#60a5fa", "#fb923c", "#818cf8", "#14b8a6", "#22c55e", "#6366f1", "#06b6d4"];

type RecipeRow = {
  ticker: string;
  name: string;
  sleeve: "income" | "growth";
  category: string;
  yieldPct: number;
  phase2Amount: number;
};

type QuoteRow = {
  symbol: string;
  price?: number | null;
  last?: number | null;
  close?: number | null;
  bid?: number | null;
  ask?: number | null;
  source?: string | null;
};

type SimulatedTrade = {
  id: number;
  ticker: string;
  name: string;
  sleeve: string;
  category: string;
  yield_pct: number;
  target_weight: number;
  target_amount: number;
  shares: number;
  cost_basis_per_share: number;
  current_price: number;
  purchase_date: string;
  market_value: number;
  cost_basis: number;
  gain_loss: number;
  return_pct: number;
  annual_income: number;
};

type SimulatedPortfolio = {
  id: number;
  name: string;
  cash_amount: number;
  target_value: number;
  cost_basis: number;
  market_value: number;
  gain_loss: number;
  return_pct: number;
  annual_income: number;
  notes?: string | null;
  created_at: string;
  updated_at: string;
  trades: SimulatedTrade[];
};

const RECIPE: RecipeRow[] = [
  { ticker: "QQQI", name: "NEOS Nasdaq-100 High Income", sleeve: "income", category: "US Tech", yieldPct: 12.0, phase2Amount: 26_000 },
  { ticker: "SPYI", name: "NEOS S&P 500 High Income", sleeve: "income", category: "US Large Cap", yieldPct: 11.0, phase2Amount: 20_000 },
  { ticker: "IWMI", name: "NEOS Russell 2000 High Income", sleeve: "income", category: "US Small Cap", yieldPct: 14.0, phase2Amount: 16_000 },
  { ticker: "OVL", name: "Overlay Shares Large Cap", sleeve: "income", category: "Large Cap Alt", yieldPct: 7.0, phase2Amount: 14_000 },
  { ticker: "GPIQ", name: "Goldman Sachs Nasdaq-100 Premium", sleeve: "income", category: "US Tech", yieldPct: 9.0, phase2Amount: 9_000 },
  { ticker: "CHPY", name: "YieldMax Semiconductor Portfolio", sleeve: "income", category: "Satellite", yieldPct: 30.0, phase2Amount: 5_000 },
  { ticker: "VOO", name: "Vanguard S&P 500 ETF", sleeve: "growth", category: "Growth Sleeve", yieldPct: 0, phase2Amount: 25_000 },
  { ticker: "QQQ", name: "Invesco Nasdaq 100 ETF", sleeve: "growth", category: "Growth Sleeve", yieldPct: 0, phase2Amount: 20_000 },
  { ticker: "VUG", name: "Vanguard Growth ETF", sleeve: "growth", category: "Growth Sleeve", yieldPct: 0, phase2Amount: 15_000 },
];

export function SimulatedPortfolioTool() {
  const [cashAmount, setCashAmount] = useState("150000");
  const [quotes, setQuotes] = useState<Record<string, QuoteRow>>({});
  const [savedPortfolios, setSavedPortfolios] = useState<SimulatedPortfolio[]>([]);
  const [loadingQuotes, setLoadingQuotes] = useState(false);
  const [saving, setSaving] = useState(false);
  const [refreshingId, setRefreshingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const cash = numericInput(cashAmount);
  const allocationRows = useMemo(() => RECIPE.map((row, index) => {
    const targetWeight = row.phase2Amount / TARGET_VALUE;
    const targetAmount = cash * targetWeight;
    const price = quotePrice(quotes[row.ticker]);
    const shares = price ? targetAmount / price : 0;
    return {
      ...row,
      color: COLORS[index % COLORS.length],
      targetWeight,
      targetAmount,
      price,
      shares,
      annualIncome: targetAmount * (row.yieldPct / 100),
    };
  }), [cash, quotes]);

  const missingPrices = allocationRows.filter((row) => !row.price).map((row) => row.ticker);
  const canAccept = cash > 0 && missingPrices.length === 0 && !saving;
  const incomeTotal = allocationRows.filter((row) => row.sleeve === "income").reduce((sum, row) => sum + row.targetAmount, 0);
  const growthTotal = allocationRows.filter((row) => row.sleeve === "growth").reduce((sum, row) => sum + row.targetAmount, 0);
  const annualIncome = allocationRows.reduce((sum, row) => sum + row.annualIncome, 0);
  const latestSaved = savedPortfolios[0] ?? null;

  const sleeveChart = [
    { name: "Income sleeve", value: incomeTotal, color: "#21c997" },
    { name: "Growth sleeve", value: growthTotal, color: "#818cf8" },
  ];
  const categoryChart = aggregateBy(allocationRows, "category");
  const incomeChart = allocationRows.filter((row) => row.sleeve === "income").map((row) => ({
    ticker: row.ticker,
    income: Math.round(row.annualIncome),
    color: row.color,
  }));

  useEffect(() => {
    void loadSaved();
    void refreshQuotes();
  }, []);

  async function loadSaved() {
    try {
      setSavedPortfolios(await apiFetch<SimulatedPortfolio[]>("/simulated-portfolios"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load simulated portfolios.");
    }
  }

  async function refreshQuotes() {
    setLoadingQuotes(true);
    setError("");
    try {
      const symbols = RECIPE.map((row) => row.ticker).join(",");
      const response = await fetchWithTimeout(`${apiUrl()}/market-data/yahoo-quotes?symbols=${encodeURIComponent(symbols)}`);
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(detail?.detail ?? `Yahoo Finance quote request failed (${response.status})`);
      }
      const data = await response.json() as { tickers: QuoteRow[] };
      setQuotes(Object.fromEntries((data.tickers ?? []).map((row) => [row.symbol.toUpperCase(), row])));
      setMessage("Yahoo Finance prices refreshed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not fetch Yahoo Finance quotes.");
    } finally {
      setLoadingQuotes(false);
    }
  }

  async function acceptPortfolio() {
    if (!canAccept) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const saved = await apiFetch<SimulatedPortfolio>("/simulated-portfolios", {
        method: "POST",
        body: JSON.stringify({
          name: "$150K Master Portfolio Plan",
          cash_amount: cash,
          target_value: TARGET_VALUE,
          notes: "Scaled from the $150K Master Portfolio Plan.",
          trades: allocationRows.map((row) => ({
            ticker: row.ticker,
            name: row.name,
            sleeve: row.sleeve,
            category: row.category,
            yield_pct: row.yieldPct,
            target_weight: row.targetWeight,
            target_amount: round2(row.targetAmount),
            shares: round4(row.shares),
            cost_basis_per_share: row.price,
            current_price: row.price,
            purchase_date: todayISO(),
          })),
        }),
      });
      setSavedPortfolios((rows) => [saved, ...rows]);
      setMessage(`Accepted and saved ${saved.trades.length} simulated ETF trades.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save simulated portfolio.");
    } finally {
      setSaving(false);
    }
  }

  async function refreshSavedPrices(portfolio: SimulatedPortfolio) {
    setRefreshingId(portfolio.id);
    setError("");
    setMessage("");
    try {
      const symbols = portfolio.trades.map((trade) => trade.ticker).join(",");
      const response = await fetchWithTimeout(`${apiUrl()}/market-data/yahoo-quotes?symbols=${encodeURIComponent(symbols)}`);
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(detail?.detail ?? `Yahoo Finance quote request failed (${response.status})`);
      }
      const data = await response.json() as { tickers: QuoteRow[] };
      const prices = (data.tickers ?? [])
        .map((row) => ({ ticker: row.symbol, current_price: quotePrice(row) }))
        .filter((row): row is { ticker: string; current_price: number } => Boolean(row.current_price));
      if (!prices.length) {
        throw new Error("No live prices were available for this saved portfolio.");
      }
      const updated = await apiFetch<SimulatedPortfolio>(`/simulated-portfolios/${portfolio.id}/prices`, {
        method: "PATCH",
        body: JSON.stringify({ prices }),
      });
      setSavedPortfolios((rows) => rows.map((row) => row.id === updated.id ? updated : row));
      setMessage(`Updated ${prices.length} live price snapshot${prices.length === 1 ? "" : "s"}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not refresh saved portfolio prices.");
    } finally {
      setRefreshingId(null);
    }
  }

  return (
    <div className="sim-portfolio-tool">
      <section className="dashboard-panel sim-portfolio-hero">
        <div>
          <h2>Simulated Portfolio</h2>
          <p>$150K income plus growth plan, scaled to the cash amount you enter and priced with Yahoo Finance quotes.</p>
        </div>
        <div className="sim-portfolio-hero-actions">
          <span><WalletCards size={15} /> {fmt$(cash || 0)} planned</span>
          <button className="secondary-button" type="button" onClick={refreshQuotes} disabled={loadingQuotes}>
            {loadingQuotes ? <Loader2 size={16} className="spin-icon" /> : <RefreshCw size={16} />}
            Refresh Prices
          </button>
          <button className="primary-button" type="button" onClick={acceptPortfolio} disabled={!canAccept}>
            {saving ? <Loader2 size={16} className="spin-icon" /> : <CheckCircle2 size={16} />}
            Accept Portfolio
          </button>
        </div>
      </section>

      <section className="dashboard-panel sim-portfolio-control">
        <div className="field">
          <label htmlFor="sim-total-cash">Total cash to simulate</label>
          <input
            id="sim-total-cash"
            type="number"
            min={0}
            step={1000}
            value={cashAmount}
            onChange={(event) => setCashAmount(event.target.value)}
          />
        </div>
        <MetricCard label="Income sleeve" value={fmt$(incomeTotal)} detail={`${fmtPct(incomeTotal / (cash || 1) * 100)} target`} />
        <MetricCard label="Growth sleeve" value={fmt$(growthTotal)} detail={`${fmtPct(growthTotal / (cash || 1) * 100)} target`} />
        <MetricCard label="Annual income" value={fmt$(annualIncome)} detail={`${fmt$(annualIncome / 12)} / mo est.`} tone="green" />
      </section>

      {(error || message || missingPrices.length > 0) && (
        <section className={`dashboard-panel sim-portfolio-alert ${error || missingPrices.length ? "warning" : ""}`}>
          {error || missingPrices.length ? <AlertTriangle size={18} /> : <CheckCircle2 size={18} />}
          <p>
            {error || (missingPrices.length ? `Missing Yahoo Finance prices for ${missingPrices.join(", ")}. Accept is disabled until all ${RECIPE.length} prices are available.` : message)}
          </p>
        </section>
      )}

      <section className="sim-portfolio-summary-grid">
        <section className="dashboard-panel sim-chart-panel">
          <div className="panel-header">
            <h2>Sleeve Mix</h2>
            <PieChartIcon size={18} />
          </div>
          <ResponsiveContainer width="100%" height={230}>
            <PieChart>
              <Pie data={sleeveChart} innerRadius={58} outerRadius={88} dataKey="value" nameKey="name">
                {sleeveChart.map((row) => <Cell key={row.name} fill={row.color} />)}
              </Pie>
              <Tooltip formatter={(value: number) => fmt$(value)} />
            </PieChart>
          </ResponsiveContainer>
          <div className="sim-chart-legend">
            {sleeveChart.map((row) => <span key={row.name}><i style={{ background: row.color }} />{row.name} {fmt$(row.value)}</span>)}
          </div>
        </section>

        <section className="dashboard-panel sim-chart-panel">
          <div className="panel-header">
            <h2>Category Exposure</h2>
            <PieChartIcon size={18} />
          </div>
          <ResponsiveContainer width="100%" height={230}>
            <PieChart>
              <Pie data={categoryChart} innerRadius={48} outerRadius={88} dataKey="value" nameKey="name">
                {categoryChart.map((row) => <Cell key={row.name} fill={row.color} />)}
              </Pie>
              <Tooltip formatter={(value: number) => fmt$(value)} />
            </PieChart>
          </ResponsiveContainer>
        </section>

        <section className="dashboard-panel sim-chart-panel wide">
          <div className="panel-header">
            <h2>Estimated Income by ETF</h2>
            <DollarSign size={18} />
          </div>
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={incomeChart} margin={{ top: 8, right: 18, left: 4, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.22)" />
              <XAxis dataKey="ticker" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={(value) => `$${Math.round(Number(value) / 1000)}K`} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(value: number) => fmt$(value)} />
              <Bar dataKey="income" radius={[4, 4, 0, 0]}>
                {incomeChart.map((row) => <Cell key={row.ticker} fill={row.color} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </section>
      </section>

      <section className="dashboard-panel sim-allocation-panel">
        <div className="panel-header">
          <h2>Scaled Allocation</h2>
          <TrendingUp size={18} />
        </div>
        <div className="sim-table-scroll">
          <table className="sim-portfolio-table">
            <thead>
              <tr>
                <th>ETF</th>
                <th>Sleeve</th>
                <th>Yield</th>
                <th>Weight</th>
                <th>Dollar Allocation</th>
                <th>Live Price</th>
                <th>Shares</th>
                <th>Annual Income</th>
              </tr>
            </thead>
            <tbody>
              {allocationRows.map((row) => (
                <tr key={row.ticker}>
                  <td>
                    <strong style={{ color: row.color }}>{row.ticker}</strong>
                    <span>{row.name}</span>
                  </td>
                  <td>{row.category}</td>
                  <td>{row.yieldPct ? fmtPct(row.yieldPct) : "DRIP"}</td>
                  <td>{fmtPct(row.targetWeight * 100)}</td>
                  <td><strong>{fmt$(row.targetAmount)}</strong></td>
                  <td>{row.price ? fmt$(row.price) : <em>Missing</em>}</td>
                  <td>{row.price ? row.shares.toLocaleString(undefined, { maximumFractionDigits: 4 }) : "N/A"}</td>
                  <td>{row.annualIncome ? fmt$(row.annualIncome) : "DRIP"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {latestSaved && (
        <section className="dashboard-panel sim-saved-panel">
          <div className="panel-header">
            <div>
              <h2>Accepted Portfolio #{latestSaved.id}</h2>
              <p className="fine-print">Accepted {formatDateTime(latestSaved.created_at)} · updated {formatDateTime(latestSaved.updated_at)}</p>
            </div>
            <button className="secondary-button" type="button" onClick={() => refreshSavedPrices(latestSaved)} disabled={refreshingId === latestSaved.id}>
              {refreshingId === latestSaved.id ? <Loader2 size={16} className="spin-icon" /> : <RefreshCw size={16} />}
              Refresh Live Prices
            </button>
          </div>
          <div className="sim-saved-metrics">
            <MetricCard label="Total value" value={fmt$(latestSaved.market_value)} detail={`${latestSaved.trades.length} ETF trades`} />
            <MetricCard label="Cost basis" value={fmt$(latestSaved.cost_basis)} detail="Accepted notional" />
            <MetricCard label="Gain / loss" value={fmt$(latestSaved.gain_loss)} detail={`${fmtPct(latestSaved.return_pct)} return`} tone={latestSaved.gain_loss >= 0 ? "green" : "red"} />
            <MetricCard label="Annual income" value={fmt$(latestSaved.annual_income)} detail={`${fmt$(latestSaved.annual_income / 12)} / mo est.`} tone="green" />
          </div>
          <div className="sim-table-scroll">
            <table className="sim-portfolio-table">
              <thead>
                <tr>
                  <th>ETF</th>
                  <th>Shares</th>
                  <th>Entry</th>
                  <th>Latest</th>
                  <th>Value</th>
                  <th>Gain / Loss</th>
                  <th>Return</th>
                  <th>Accepted</th>
                </tr>
              </thead>
              <tbody>
                {latestSaved.trades.map((trade) => (
                  <tr key={trade.id}>
                    <td>
                      <strong>{trade.ticker}</strong>
                      <span>{trade.category}</span>
                    </td>
                    <td>{trade.shares.toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
                    <td>{fmt$(trade.cost_basis_per_share)}</td>
                    <td>{fmt$(trade.current_price)}</td>
                    <td>{fmt$(trade.market_value)}</td>
                    <td style={{ color: trade.gain_loss >= 0 ? "var(--forest)" : "var(--rose)" }}>{fmt$(trade.gain_loss)}</td>
                    <td style={{ color: trade.return_pct >= 0 ? "var(--forest)" : "var(--rose)" }}>{fmtPct(trade.return_pct)}</td>
                    <td>{trade.purchase_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

function MetricCard({ label, value, detail, tone }: { label: string; value: string; detail: string; tone?: "green" | "red" }) {
  return (
    <article className={`sim-metric-card ${tone ?? ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function aggregateBy(rows: Array<{ category: string; targetAmount: number; color: string }>, field: "category") {
  const colors = new Map<string, string>();
  const totals = new Map<string, number>();
  for (const row of rows) {
    const key = row[field];
    colors.set(key, colors.get(key) ?? row.color);
    totals.set(key, (totals.get(key) ?? 0) + row.targetAmount);
  }
  return Array.from(totals.entries()).map(([name, value]) => ({ name, value, color: colors.get(name) ?? "#21c997" }));
}

function quotePrice(row?: QuoteRow) {
  if (!row) return null;
  const mid = row.bid && row.ask ? (row.bid + row.ask) / 2 : null;
  return positive(row.price) ?? positive(mid) ?? positive(row.last) ?? positive(row.close);
}

async function fetchWithTimeout(url: string) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), QUOTE_TIMEOUT_MS);
  try {
    return await fetch(url, { cache: "no-store", signal: controller.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error("Yahoo Finance quote request timed out. Refresh prices again in a moment.");
    }
    throw err;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function positive(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : null;
}

function numericInput(value: string) {
  const parsed = Number(value.replace(/,/g, ""));
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function round2(value: number) {
  return Math.round(value * 100) / 100;
}

function round4(value: number) {
  return Math.round(value * 10_000) / 10_000;
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function fmt$(value: number) {
  return value.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: value >= 1000 ? 0 : 2 });
}

function fmtPct(value: number) {
  return `${value.toFixed(1)}%`;
}

function formatDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}
