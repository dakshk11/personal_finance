"use client";

import {
  Activity,
  AlertTriangle,
  CandlestickChart,
  Gauge,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Target,
  WalletCards
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { RSIPlaybookScan, RSIPlaybookSignal, apiFetch, percent } from "@/lib/api";

type FilterKey = "all" | "cash" | "puts" | "stock" | "leap" | "watch";

const ruleCards = [
  { level: "RSI 70+", action: "Go to cash", tone: "cash" },
  { level: "RSI 55-65", action: "Sell puts far OTM", tone: "puts_far_otm" },
  { level: "RSI 45-55", action: "Sell puts ATM", tone: "puts_atm" },
  { level: "RSI 30-45", action: "Buy the stock", tone: "stock" },
  { level: "RSI 30 and below", action: "Buy LEAP aggressively", tone: "leap" }
];

export function RSIPlaybookTool() {
  const [scan, setScan] = useState<RSIPlaybookScan | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [loading, setLoading] = useState("initial");
  const [error, setError] = useState("");

  useEffect(() => {
    void loadScan(false);
  }, []);

  useEffect(() => {
    if (!scan?.signals.length) return;
    if (selectedSymbol && scan.signals.some((signal) => signal.symbol === selectedSymbol)) return;
    setSelectedSymbol(scan.signals[0].symbol);
  }, [scan, selectedSymbol]);

  const signals = scan?.signals ?? [];
  const selected = signals.find((signal) => signal.symbol === selectedSymbol) ?? signals[0] ?? null;
  const filteredSignals = useMemo(() => {
    if (filter === "all") return signals;
    if (filter === "puts") return signals.filter((signal) => signal.action_tone === "puts_far_otm" || signal.action_tone === "puts_atm");
    return signals.filter((signal) => signal.action_tone === filter);
  }, [filter, signals]);
  const counts = useMemo(() => ({
    cash: signals.filter((signal) => signal.action_tone === "cash").length,
    puts: signals.filter((signal) => signal.action_tone === "puts_far_otm" || signal.action_tone === "puts_atm").length,
    stock: signals.filter((signal) => signal.action_tone === "stock").length,
    leap: signals.filter((signal) => signal.action_tone === "leap").length,
    watch: signals.filter((signal) => signal.action_tone === "watch").length
  }), [signals]);

  async function loadScan(force: boolean) {
    setLoading(force ? "refresh" : "initial");
    setError("");
    try {
      const result = await apiFetch<RSIPlaybookScan>(`/rsi-playbook/scan${force ? "?force=true" : ""}`);
      setScan(result);
      if (result.signals[0]) setSelectedSymbol(result.signals[0].symbol);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load RSI playbook.");
    } finally {
      setLoading("");
    }
  }

  return (
    <>
      <section className="dashboard-panel rsi-playbook-head">
        <div>
          <p className="eyebrow">RSI Playbook</p>
          <h2>Wheel Strategy and Portfolio Sync symbols mapped to RSI action zones.</h2>
          <div className="rsi-source-line">
            <span><Gauge size={14} /> RSI 14</span>
            <span><Activity size={14} /> EMA 8 / 21 / 55</span>
            <span><WalletCards size={14} /> Wheel + Portfolio Sync</span>
          </div>
        </div>
        <div className="rsi-actions">
          <span className="status-pill">{scan ? `${scan.universe_count} symbols` : "Loading"}</span>
          <button className="ghost-button" type="button" onClick={() => loadScan(false)} disabled={Boolean(loading)}>
            {loading === "initial" ? <Loader2 size={16} className="spin-icon" /> : <RefreshCw size={16} />}
            Refresh
          </button>
          <button className="primary-button" type="button" onClick={() => loadScan(true)} disabled={loading === "refresh"}>
            {loading === "refresh" ? <Loader2 size={16} className="spin-icon" /> : <RefreshCw size={16} />}
            Force refresh
          </button>
        </div>
      </section>

      <section className="dashboard-panel rsi-playbook-notice">
        <ShieldCheck size={18} />
        <p>Educational playbook output only. The action labels follow the requested RSI rules and still require manual verification of news, earnings, liquidity, tax impact, and position sizing.</p>
      </section>

      {error && <div className="error">{error}</div>}

      <section className="rsi-stat-grid stat-grid">
        <Stat label="Go to cash" value={counts.cash} tone="cash" />
        <Stat label="Sell puts" value={counts.puts} tone="puts" />
        <Stat label="Buy stock" value={counts.stock} tone="stock" />
        <Stat label="Buy LEAP" value={counts.leap} tone="leap" />
        <Stat label="Watch gap" value={counts.watch} tone="watch" />
      </section>

      <section className="dashboard-panel rsi-rule-panel">
        <div className="panel-header">
          <h2>RSI rules</h2>
          <Target size={18} />
        </div>
        <div className="rsi-rule-grid">
          {ruleCards.map((rule) => (
            <article className={`rsi-rule-card ${rule.tone}`} key={rule.level}>
              <span>{rule.level}</span>
              <strong>{rule.action}</strong>
            </article>
          ))}
        </div>
      </section>

      <div className="rsi-workbench-grid">
        <section className="dashboard-panel rsi-summary-panel">
          <div className="panel-header">
            <div>
              <h2>Per-stock playbook summary</h2>
              <p className="fine-print">{scan ? `${scan.wheel_symbol_count} Wheel symbols and ${scan.portfolio_symbol_count} Portfolio Sync symbols` : "Loading combined universe"}</p>
            </div>
            <div className="rsi-filter-tabs">
              {(["all", "cash", "puts", "stock", "leap", "watch"] as FilterKey[]).map((item) => (
                <button className={filter === item ? "active" : ""} type="button" key={item} onClick={() => setFilter(item)}>
                  {filterLabel(item)}
                </button>
              ))}
            </div>
          </div>
          <div className="rsi-table">
            <div className="rsi-row rsi-row-header">
              <span>Symbol</span>
              <span>RSI level</span>
              <span>Action / context</span>
            </div>
            {loading === "initial" && !signals.length ? (
              <div className="rsi-loading-row"><Loader2 size={18} className="spin-icon" /> Loading RSI playbook</div>
            ) : filteredSignals.map((signal) => (
              <button
                className={`rsi-row ${selected?.symbol === signal.symbol ? "active" : ""}`}
                type="button"
                key={signal.symbol}
                onClick={() => setSelectedSymbol(signal.symbol)}
              >
                <strong>{signal.symbol}<small>{signal.sector}</small></strong>
                <span>{signal.level}<small>{signal.rsi == null ? "RSI N/A" : `${signal.rsi.toFixed(1)} | ${signal.trend}`}</small></span>
                <span>
                  <i className={`rsi-action-dot ${signal.action_tone}`} />{signal.action}
                  <small>{signal.window_return_3m == null ? "3M N/A" : `${percent(signal.window_return_3m)} 3M`} | {signal.sources.join(" + ")}</small>
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="dashboard-panel rsi-detail-panel">
          {selected ? <SignalDetails signal={selected} /> : <EmptyDetails />}
        </section>
      </div>

      {scan?.warnings?.length ? (
        <section className="dashboard-panel rsi-warning-panel">
          <div className="panel-header">
            <h2>Data notes</h2>
            <AlertTriangle size={18} />
          </div>
          <div className="rsi-warning-list">
            {scan.warnings.slice(0, 8).map((warning) => <p key={warning}>{warning}</p>)}
          </div>
        </section>
      ) : null}
    </>
  );
}

function SignalDetails({ signal }: { signal: RSIPlaybookSignal }) {
  const latest = signal.chart.at(-1);
  return (
    <>
      <div className="rsi-detail-head">
        <div>
          <span>{signal.sources.join(" + ")}</span>
          <h2>{signal.symbol} {signal.action}</h2>
          <p>{signal.summary}</p>
        </div>
        <div className={`rsi-radar ${signal.action_tone}`}>
          <span>{signal.level}</span>
          <strong>{signal.rsi == null ? "N/A" : signal.rsi.toFixed(1)}</strong>
        </div>
      </div>
      <div className="rsi-detail-stats">
        <div><span>Price</span><strong>{currencyCents(signal.price)}</strong></div>
        <div><span>EMA 21</span><strong>{signal.ema21 == null ? "N/A" : currencyCents(signal.ema21)}</strong></div>
        <div><span>EMA 55</span><strong>{signal.ema55 == null ? "N/A" : currencyCents(signal.ema55)}</strong></div>
        <div><span>As of</span><strong>{formatShortDate(signal.as_of_date ?? latest?.date)}</strong></div>
      </div>
      <div className="rsi-chart-stack">
        <div className="rsi-price-chart">
          <ResponsiveContainer width="100%" height={360}>
            <ComposedChart data={signal.chart} margin={{ left: 4, right: 14, top: 10, bottom: 8 }}>
              <defs>
                <linearGradient id={`rsiClose-${signal.symbol}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#5eead4" stopOpacity={0.44} />
                  <stop offset="95%" stopColor="#5eead4" stopOpacity={0.04} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#17352d" strokeDasharray="3 3" />
              <XAxis dataKey="date" minTickGap={42} tickFormatter={formatMonthDay} tick={{ fontSize: 11, fill: "#8da99e" }} axisLine={{ stroke: "#24463c" }} tickLine={{ stroke: "#24463c" }} />
              <YAxis width={64} tickFormatter={(value) => compactCurrency(Number(value))} tick={{ fontSize: 11, fill: "#8da99e" }} axisLine={{ stroke: "#24463c" }} tickLine={{ stroke: "#24463c" }} />
              <Tooltip content={<RSIChartTooltip />} />
              <Legend wrapperStyle={{ color: "#b6d9cb", fontSize: 12 }} />
              <Area type="monotone" dataKey="close" name="Close" stroke="#5eead4" fill={`url(#rsiClose-${signal.symbol})`} fillOpacity={1} strokeWidth={2.6} dot={false} activeDot={{ r: 4, fill: "#f8fffd" }} />
              <Line type="monotone" dataKey="ema8" name="EMA 8" stroke="#38bdf8" strokeWidth={1.5} dot={false} connectNulls />
              <Line type="monotone" dataKey="ema21" name="EMA 21" stroke="#f59e0b" strokeWidth={1.7} dot={false} connectNulls />
              <Line type="monotone" dataKey="ema55" name="EMA 55" stroke="#c084fc" strokeWidth={1.7} dot={false} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="rsi-oscillator-chart">
          <ResponsiveContainer width="100%" height={190}>
            <ComposedChart data={signal.chart} margin={{ left: 4, right: 14, top: 6, bottom: 4 }}>
              <CartesianGrid stroke="#d7e2dc" strokeDasharray="3 3" />
              <XAxis dataKey="date" minTickGap={42} tickFormatter={formatMonthDay} tick={{ fontSize: 11, fill: "#51645b" }} />
              <YAxis width={42} domain={[0, 100]} tick={{ fontSize: 11, fill: "#51645b" }} />
              <ReferenceLine y={30} stroke="#0f766e" strokeDasharray="4 4" />
              <ReferenceLine y={45} stroke="#65a30d" strokeDasharray="4 4" />
              <ReferenceLine y={55} stroke="#f59e0b" strokeDasharray="4 4" />
              <ReferenceLine y={65} stroke="#f97316" strokeDasharray="4 4" />
              <ReferenceLine y={70} stroke="#e11d48" strokeDasharray="4 4" />
              <Tooltip formatter={(value) => [Number(value).toFixed(1), "RSI"]} labelFormatter={(label) => formatShortDate(String(label))} contentStyle={{ border: "1px solid #d7e2dc", borderRadius: 8 }} />
              <Line type="monotone" dataKey="rsi" stroke="#0f766e" strokeWidth={2.4} dot={false} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    </>
  );
}

function EmptyDetails() {
  return (
    <div className="rsi-empty-detail">
      <CandlestickChart size={32} />
      <h2>Select a stock</h2>
      <p>RSI action details and the price/EMA chart appear here.</p>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <article className={`stat-panel rsi-stat-${tone}`}>
      <h3>{label}</h3>
      <strong>{value}</strong>
      <p>Current universe</p>
    </article>
  );
}

function RSIChartTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ name: string; value: number; color?: string }>; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="option-chart-tooltip">
      <strong>{formatShortDate(label)}</strong>
      {payload.filter((item) => item.value != null).map((item) => (
        <span key={item.name} style={{ color: item.color }}>{item.name}: {currencyCents(Number(item.value))}</span>
      ))}
    </div>
  );
}

function filterLabel(value: FilterKey) {
  if (value === "all") return "All";
  if (value === "cash") return "Cash";
  if (value === "puts") return "Puts";
  if (value === "stock") return "Stock";
  if (value === "leap") return "LEAP";
  return "Watch";
}

function currencyCents(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function compactCurrency(value: number) {
  if (Math.abs(value) >= 1000) return `$${Math.round(value / 1000)}k`;
  return `$${Math.round(value)}`;
}

function formatMonthDay(value: string) {
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatShortDate(value?: string | null) {
  if (!value) return "N/A";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
