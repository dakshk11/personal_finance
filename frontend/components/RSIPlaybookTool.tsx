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
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { RSIPlaybookScan, RSIPlaybookSignal, apiFetch, percent } from "@/lib/api";

type FilterKey = "all" | "sell_puts" | "sell_puts_otm" | "sell_puts_itm" | "wait" | "watch";

const ruleCards = [
  { level: "Rule 1", action: "Only sell puts when RSI is under 50", tone: "sell_puts" },
  { level: "Rule 2", action: "Moving averages must confirm a bullish trend", tone: "wait" },
  { level: "Rule 3", action: "Target 5% return in 30 days", tone: "watch" },
  { level: "Exit", action: "Close at 50% profit, usually 5-7 days", tone: "watch" }
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
    if (filter === "sell_puts_otm") return signals.filter(isOtmPutCandidate);
    if (filter === "sell_puts_itm") return signals.filter(isItmPutCandidate);
    return signals.filter((signal) => signal.action_tone === filter);
  }, [filter, signals]);
  const counts = useMemo(() => ({
    sellPuts: signals.filter((signal) => signal.action_tone === "sell_puts").length,
    otmPuts: signals.filter(isOtmPutCandidate).length,
    itmPuts: signals.filter(isItmPutCandidate).length,
    wait: signals.filter((signal) => signal.action_tone === "wait").length,
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
          <h2>RSI entry timing plus moving-average trend confirmation.</h2>
          <div className="rsi-source-line">
            <span><Gauge size={14} /> RSI 14</span>
            <span><Activity size={14} /> Bullish EMA trend</span>
            <span><WalletCards size={14} /> Wheel + Portfolio Sync</span>
          </div>
        </div>
        <div className="rsi-actions">
          <span className="status-pill">{scan ? `${scan.universe_count} symbols` : "Loading"}</span>
          <button className="ghost-button rsi-refresh-button" type="button" onClick={() => loadScan(false)} disabled={Boolean(loading)}>
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
        <p>Educational playbook output only. Sell-put setups require both conditions: RSI under 50 and a bullish moving-average trend. Target/exit notes are planning rules, not guaranteed outcomes.</p>
      </section>

      {error && <div className="error">{error}</div>}

      <section className="rsi-stat-grid stat-grid">
        <Stat label="Sell puts" value={counts.sellPuts} tone="puts" />
        <Stat label="OTM puts" value={counts.otmPuts} tone="puts" />
        <Stat label="ITM puts" value={counts.itmPuts} tone="puts" />
        <Stat label="Wait" value={counts.wait} tone="watch" />
        <Stat label="Data watch" value={counts.watch} tone="watch" />
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
              {(["all", "sell_puts", "sell_puts_otm", "sell_puts_itm", "wait", "watch"] as FilterKey[]).map((item) => (
                <button className={filter === item ? "active" : ""} type="button" key={item} onClick={() => setFilter(item)} data-tooltip={filterTooltip(item)}>
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
                  <small>{putFilterContext(signal, filter)}{signal.window_return_3m == null ? "3M N/A" : `${percent(signal.window_return_3m)} 3M`} | {signal.sources.join(" + ")}</small>
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
          <CandlestickPriceChart signal={signal} />
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

function CandlestickPriceChart({ signal }: { signal: RSIPlaybookSignal }) {
  const width = 920;
  const height = 360;
  const padding = { top: 18, right: 58, bottom: 34, left: 12 };
  const rows = signal.chart;
  if (!rows.length) {
    return <div className="rsi-empty-chart">No price history available.</div>;
  }

  const candles = rows.map((row, index) => {
    const open = index > 0 ? rows[index - 1].close : row.close;
    const high = Math.max(open, row.close);
    const low = Math.min(open, row.close);
    return { ...row, open, high, low };
  });
  const values = candles.flatMap((row) => [row.high, row.low, row.ema8, row.ema21, row.ema55].filter((value): value is number => typeof value === "number"));
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const pad = Math.max((maxValue - minValue) * 0.08, maxValue * 0.01);
  const domainMin = minValue - pad;
  const domainMax = maxValue + pad;
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const xFor = (index: number) => padding.left + (rows.length <= 1 ? chartWidth / 2 : (index / (rows.length - 1)) * chartWidth);
  const yFor = (value: number) => padding.top + ((domainMax - value) / (domainMax - domainMin)) * chartHeight;
  const candleWidth = Math.max(2, Math.min(9, (chartWidth / Math.max(rows.length, 1)) * 0.58));
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => domainMin + (domainMax - domainMin) * ratio);
  const xTickIndexes = Array.from(new Set([0, 0.25, 0.5, 0.75, 1].map((ratio) => Math.round((rows.length - 1) * ratio))));
  const emaLine = (key: "ema8" | "ema21" | "ema55") =>
    rows
      .map((row, index) => (typeof row[key] === "number" ? `${xFor(index)},${yFor(row[key])}` : ""))
      .filter(Boolean)
      .join(" ");

  return (
    <svg className="rsi-candlestick-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${signal.symbol} candlestick chart with EMA overlays`}>
      <rect className="rsi-candle-bg" x="0" y="0" width={width} height={height} rx="12" />
      {yTicks.map((tick) => {
        const y = yFor(tick);
        return (
          <g key={tick}>
            <line className="rsi-candle-grid" x1={padding.left} x2={width - padding.right} y1={y} y2={y} />
            <text className="rsi-candle-axis" x={width - padding.right + 10} y={y + 4}>{compactCurrency(tick)}</text>
          </g>
        );
      })}
      {xTickIndexes.map((index) => (
        <text className="rsi-candle-axis" key={index} x={xFor(index)} y={height - 9} textAnchor={index === 0 ? "start" : index === rows.length - 1 ? "end" : "middle"}>
          {formatMonthDay(rows[index].date)}
        </text>
      ))}
      {candles.map((row, index) => {
        const x = xFor(index);
        const openY = yFor(row.open);
        const closeY = yFor(row.close);
        const highY = yFor(row.high);
        const lowY = yFor(row.low);
        const up = row.close >= row.open;
        return (
          <g className={up ? "rsi-candle up" : "rsi-candle down"} key={row.date}>
            <line x1={x} x2={x} y1={highY} y2={lowY} />
            <rect x={x - candleWidth / 2} y={Math.min(openY, closeY)} width={candleWidth} height={Math.max(2, Math.abs(closeY - openY))} rx="1.5" />
          </g>
        );
      })}
      <polyline className="rsi-ema-line ema8" points={emaLine("ema8")} />
      <polyline className="rsi-ema-line ema21" points={emaLine("ema21")} />
      <polyline className="rsi-ema-line ema55" points={emaLine("ema55")} />
      <g className="rsi-candle-legend">
        <text x={padding.left} y="16">Candles</text>
        <text x={padding.left + 82} y="16">EMA 8</text>
        <text x={padding.left + 142} y="16">EMA 21</text>
        <text x={padding.left + 214} y="16">EMA 55</text>
      </g>
    </svg>
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
  if (value === "sell_puts") return "Sell puts";
  if (value === "sell_puts_otm") return "OTM puts";
  if (value === "sell_puts_itm") return "ITM puts";
  if (value === "wait") return "Wait";
  return "Data watch";
}

function filterTooltip(value: FilterKey) {
  if (value === "sell_puts") {
    return "Rule 1: Only sell puts on red days (RSI <50)\nRule 2: Target 5% return in 30 days\nRule 3: Close at 50% profit (5-7 days)";
  }
  if (value === "sell_puts_otm") return "OTM put filter only: RSI <50 red-day candidates. Does not require the bullish-trend rule.";
  if (value === "sell_puts_itm") return "ITM put filter only: RSI <40 deeper-red candidates. Does not require the bullish-trend rule.";
  return undefined;
}

function isOtmPutCandidate(signal: RSIPlaybookSignal) {
  return typeof signal.rsi === "number" && signal.rsi < 50;
}

function isItmPutCandidate(signal: RSIPlaybookSignal) {
  return typeof signal.rsi === "number" && signal.rsi < 40;
}

function putFilterContext(signal: RSIPlaybookSignal, filter: FilterKey) {
  if (filter === "sell_puts_otm" && isOtmPutCandidate(signal)) return "OTM put filter: RSI <50, trend not required | ";
  if (filter === "sell_puts_itm" && isItmPutCandidate(signal)) return "ITM put filter: RSI <40, trend not required | ";
  return "";
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
