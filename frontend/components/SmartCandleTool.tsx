"use client";

import {
  Activity,
  AlertTriangle,
  CandlestickChart,
  CheckCircle2,
  Gauge,
  Loader2,
  Plus,
  RefreshCw,
  ShieldCheck,
  Target,
  X
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  SmartCandleBacktest,
  SmartCandleChartPoint,
  SmartCandleColor,
  SmartCandleScan,
  SmartCandleScanRequest,
  SmartCandleSignal,
  apiFetch,
  percent
} from "@/lib/api";

const defaultConfig: SmartCandleScanRequest = {
  custom_symbols: [],
  lookback_days: 420,
  min_relative_volume: 1.1,
  min_avg_dollar_volume: 25_000_000,
  max_symbols: 120,
  include_neutral: false,
  trend_filter: "all",
};

const ruleCards: Array<{ color: SmartCandleColor; title: string; detail: string }> = [
  { color: "blue", title: "Blue", detail: "Bullish accumulation or reversal: strong body, high close, volume, and constructive trend context." },
  { color: "pink", title: "Pink", detail: "Caution or distribution: weak close, elevated volume, and trend weakening before full breakdown." },
  { color: "red", title: "Red", detail: "Breakdown risk: bearish body, weak close, moving-average damage, or weak RSI/returns." },
  { color: "neutral", title: "Neutral", detail: "No strong edge under the visible FinanceOS OHLCV rules." },
];

export function SmartCandleTool() {
  const [config, setConfig] = useState<SmartCandleScanRequest>(defaultConfig);
  const [scan, setScan] = useState<SmartCandleScan | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [watchlistInput, setWatchlistInput] = useState("");
  const [backtestColor, setBacktestColor] = useState<SmartCandleColor>("blue");
  const [backtestYears, setBacktestYears] = useState(5);
  const [backtest, setBacktest] = useState<SmartCandleBacktest | null>(null);
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    void loadScan(false);
  }, []);

  const counts = useMemo(() => {
    const rows = scan?.signals ?? [];
    return {
      blue: rows.filter((row) => row.candle_color === "blue").length,
      pink: rows.filter((row) => row.candle_color === "pink").length,
      red: rows.filter((row) => row.candle_color === "red").length,
      neutral: rows.filter((row) => row.candle_color === "neutral").length,
    };
  }, [scan]);

  const selected = useMemo(
    () => scan?.signals.find((signal) => signal.symbol === selectedSymbol) ?? scan?.signals[0] ?? null,
    [scan, selectedSymbol]
  );

  useEffect(() => {
    if (!scan?.signals.length) {
      setSelectedSymbol("");
      return;
    }
    if (selectedSymbol && scan.signals.some((signal) => signal.symbol === selectedSymbol)) return;
    setSelectedSymbol(scan.signals[0].symbol);
  }, [scan, selectedSymbol]);

  async function loadScan(force: boolean) {
    await loadScanWithConfig(config, force);
  }

  async function loadScanWithConfig(nextConfig: SmartCandleScanRequest, force: boolean) {
    setLoading(force ? "refresh" : "scan");
    setError("");
    try {
      const result = await apiFetch<SmartCandleScan>(`/smart-candles/scan${force ? "?force=true" : ""}`, {
        method: "POST",
        body: JSON.stringify(nextConfig),
      });
      setScan(result);
      setBacktest(null);
      if (result.signals[0]) setSelectedSymbol(result.signals[0].symbol);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not run Smart Candle scan.";
      setError(message === "Not Found" ? "Smart Candle API is not loaded yet. Restart the backend server, then run the scan again." : message);
    } finally {
      setLoading("");
    }
  }

  async function runBacktest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading("backtest");
    setError("");
    try {
      setBacktest(await apiFetch<SmartCandleBacktest>("/smart-candles/backtest", {
        method: "POST",
        body: JSON.stringify({ ...config, candle_color: backtestColor, years: backtestYears }),
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not run Smart Candle backtest.");
    } finally {
      setLoading("");
    }
  }

  function updateNumber(key: keyof SmartCandleScanRequest, value: string) {
    const parsed = Number(value);
    if (Number.isNaN(parsed)) return;
    setConfig((current) => ({ ...current, [key]: parsed }));
  }

  function appendWatchlistSymbols() {
    const symbols = watchlistInput
      .split(/[\s,]+/)
      .map((value) => value.trim().toUpperCase().replace(/[^A-Z0-9.-]/g, ""))
      .filter(Boolean)
      .slice(0, 10);
    if (!symbols.length) return;
    const nextConfig = { ...config, custom_symbols: Array.from(new Set([...config.custom_symbols, ...symbols])).slice(0, 25) };
    setConfig(nextConfig);
    setWatchlistInput("");
    void loadScanWithConfig(nextConfig, false);
  }

  function removeWatchlistSymbol(symbol: string) {
    const nextConfig = { ...config, custom_symbols: config.custom_symbols.filter((item) => item !== symbol) };
    setConfig(nextConfig);
    void loadScanWithConfig(nextConfig, false);
  }

  return (
    <div className="smart-candle-tool">
      <section className="dashboard-panel smart-candle-head">
        <div>
          <p className="eyebrow">FinanceOS Smart Candle Signals</p>
          <h2>Blue, pink, red, and neutral candle classifications from transparent OHLCV rules.</h2>
          <p>
            It scans S&P 500 symbols plus your watchlist using cached daily market data.
            The labels are transparent OHLCV classifications for manual research.
          </p>
        </div>
        <div className="smart-candle-actions">
          <span className={error ? "risk-pill" : "status-pill"}>
            <CandlestickChart size={14} /> {scan ? `${scan.signals.length} signals` : "Ready"}
          </span>
          <button className="ghost-button" type="button" onClick={() => loadScan(false)} disabled={Boolean(loading)}>
            {loading === "scan" ? <Loader2 size={16} className="spin-icon" /> : <RefreshCw size={16} />}
            Run scan
          </button>
          <button className="primary-button" type="button" onClick={() => loadScan(true)} disabled={loading === "refresh"}>
            {loading === "refresh" ? <Loader2 size={16} className="spin-icon" /> : <RefreshCw size={16} />}
            Force refresh
          </button>
        </div>
      </section>

      <section className="dashboard-panel smart-candle-rule-panel">
        <div className="smart-candle-rule-grid">
          {ruleCards.map((card) => (
            <article className={`smart-candle-rule-card ${card.color}`} key={card.color}>
              <strong>{card.title}</strong>
              <span>{card.detail}</span>
            </article>
          ))}
        </div>
      </section>

      <section className="dashboard-panel breakout-watchlist-panel">
        <div className="panel-header">
          <h2>Watchlist Symbols</h2>
          <Target size={18} />
        </div>
        <div className="breakout-watchlist-form">
          <input
            type="text"
            value={watchlistInput}
            onChange={(event) => setWatchlistInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                appendWatchlistSymbols();
              }
            }}
            placeholder="PLTR, HIMS, RDDT"
            aria-label="Add smart candle watchlist symbols"
          />
          <button className="secondary-button" type="button" onClick={appendWatchlistSymbols}>
            <Plus size={16} /> Append
          </button>
        </div>
        {config.custom_symbols.length > 0 && (
          <div className="breakout-watchlist-pills">
            {config.custom_symbols.map((symbol) => (
              <button type="button" key={symbol} onClick={() => removeWatchlistSymbol(symbol)}>
                {symbol}
                <X size={13} />
              </button>
            ))}
          </div>
        )}
      </section>

      <section className="dashboard-panel smart-candle-config-panel">
        <div className="panel-header">
          <h2>Scanner Parameters</h2>
          <Gauge size={18} />
        </div>
        <div className="smart-candle-config-grid">
          <NumberField label="Lookback days" value={config.lookback_days} min={120} max={1600} step={30} onChange={(value) => updateNumber("lookback_days", value)} />
          <NumberField label="Max symbols" value={config.max_symbols} min={1} max={505} step={10} onChange={(value) => updateNumber("max_symbols", value)} />
          <NumberField label="Min rel volume" value={config.min_relative_volume} min={0.1} max={10} step={0.1} onChange={(value) => updateNumber("min_relative_volume", value)} />
          <NumberField label="Min dollar volume" value={config.min_avg_dollar_volume} min={0} max={5_000_000_000} step={5_000_000} onChange={(value) => updateNumber("min_avg_dollar_volume", value)} />
          <label>
            <span>Trend filter</span>
            <select value={config.trend_filter} onChange={(event) => setConfig((current) => ({ ...current, trend_filter: event.target.value as SmartCandleScanRequest["trend_filter"] }))}>
              <option value="all">All trends</option>
              <option value="above_sma200">Above SMA 200</option>
              <option value="below_sma200">Below SMA 200</option>
            </select>
          </label>
          <label className="breakout-toggle">
            <input type="checkbox" checked={config.include_neutral} onChange={(event) => setConfig((current) => ({ ...current, include_neutral: event.target.checked }))} />
            <span>Include neutral</span>
          </label>
        </div>
      </section>

      {error && (
        <section className="dashboard-panel smart-candle-warning">
          <AlertTriangle size={18} />
          <p>{error}</p>
        </section>
      )}

      <section className="smart-candle-stat-grid stat-grid">
        <Stat label="Universe" value={scan?.universe_count ?? 0} helper="S&P 500 base" />
        <Stat label="Scanned" value={scan?.scanned_symbols ?? 0} helper={scan?.data_source ?? "waiting"} />
        <Stat label="Blue" value={counts.blue} helper="accumulation" />
        <Stat label="Pink" value={counts.pink} helper="caution" />
        <Stat label="Red" value={counts.red} helper="breakdown" />
      </section>

      <div className="smart-candle-workbench-grid">
        <section className="dashboard-panel smart-candle-table-panel">
          <div className="panel-header">
            <div>
              <h2>Current Smart Candles</h2>
              <p className="fine-print">{scan ? `${formatDateTime(scan.scanned_at)} · ${scan.data_source}` : "Run a scan to classify candles"}</p>
            </div>
          </div>
          {loading === "scan" && !scan ? (
            <div className="smart-candle-loading"><Loader2 size={18} className="spin-icon" /> Loading smart candles</div>
          ) : scan?.signals.length ? (
            <div className="smart-candle-signal-grid">
              {scan.signals.map((signal) => (
                <button
                  type="button"
                  className={`smart-candle-card ${signal.candle_color} ${selected?.symbol === signal.symbol ? "active" : ""}`}
                  key={`${signal.symbol}-${signal.rank}`}
                  onClick={() => setSelectedSymbol(signal.symbol)}
                >
                  <span>{signal.signal_label}</span>
                  <strong>{signal.symbol}</strong>
                  <b>{signal.score.toFixed(0)}</b>
                  <small>{signal.trend_label} · {signal.relative_volume == null ? "N/A" : `${signal.relative_volume.toFixed(2)}x vol`}</small>
                </button>
              ))}
            </div>
          ) : (
            <div className="smart-candle-loading">No smart-candle signals match the current filters.</div>
          )}
        </section>

        <section className="dashboard-panel smart-candle-detail-panel">
          {selected ? <SmartCandleDetails signal={selected} /> : <EmptyDetails />}
        </section>
      </div>

      <section className="dashboard-panel smart-candle-backtest-panel">
        <div className="panel-header">
          <div>
            <h2>Backtest Lab</h2>
            <p className="fine-print">
              Tests the selected candle color across the configured universe: up to {config.max_symbols} S&P 500 symbols
              {config.custom_symbols.length ? ` plus ${config.custom_symbols.length} watchlist symbol${config.custom_symbols.length === 1 ? "" : "s"}` : ""}.
            </p>
          </div>
        </div>
        <form className="smart-candle-backtest-form" onSubmit={runBacktest}>
          <label>
            <span>Candle color</span>
            <select value={backtestColor} onChange={(event) => setBacktestColor(event.target.value as SmartCandleColor)}>
              <option value="blue">Blue</option>
              <option value="pink">Pink</option>
              <option value="red">Red</option>
              <option value="neutral">Neutral</option>
            </select>
          </label>
          <label>
            <span>Years</span>
            <input type="number" min={1} max={10} value={backtestYears} onChange={(event) => setBacktestYears(Number(event.target.value))} />
          </label>
          <button className="primary-button" type="submit" disabled={loading === "backtest"}>
            {loading === "backtest" ? <Loader2 size={16} className="spin-icon" /> : <Gauge size={16} />}
            Run backtest
          </button>
        </form>
        {backtest ? (
          <div className="smart-candle-backtest-grid">
            <article className={`smart-candle-backtest-summary ${backtest.candle_color}`}>
              <span>{labelForColor(backtest.candle_color)}</span>
              <strong>{backtest.signal_count}</strong>
              <p>signals over {backtest.evaluated_years} year{backtest.evaluated_years === 1 ? "" : "s"}</p>
            </article>
            {backtest.horizons.map((row) => (
              <article className="smart-candle-horizon-card" key={row.horizon_days}>
                <span>{row.horizon_days}D forward</span>
                <strong>{row.win_rate == null ? "N/A" : percent(row.win_rate)}</strong>
                <p>Avg {row.average_return == null ? "N/A" : percent(row.average_return)} · P10/P90 {row.p10_return == null ? "N/A" : percent(row.p10_return)} / {row.p90_return == null ? "N/A" : percent(row.p90_return)}</p>
              </article>
            ))}
          </div>
        ) : null}
      </section>

      <section className="dashboard-panel smart-candle-note-panel">
        <ShieldCheck size={18} />
        <p>
          These labels are transparent OHLCV classifications for education and manual research only.
        </p>
      </section>

      {(scan?.warnings.length || backtest?.warnings.length) ? (
        <section className="dashboard-panel smart-candle-warning">
          <AlertTriangle size={18} />
          <div>
            {[...(scan?.warnings ?? []), ...(backtest?.warnings ?? [])].slice(0, 8).map((warning) => <p key={warning}>{warning}</p>)}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function SmartCandleDetails({ signal }: { signal: SmartCandleSignal }) {
  return (
    <>
      <div className="smart-candle-detail-head">
        <div>
          <span>{signal.company_name}</span>
          <h2>{signal.symbol} {signal.signal_label}</h2>
          <p>{signal.summary}</p>
        </div>
        <div className={`smart-candle-score ${signal.candle_color}`}>
          <span>Score</span>
          <strong>{signal.score.toFixed(0)}</strong>
        </div>
      </div>

      <div className="smart-candle-detail-stats">
        <div><span>Price</span><strong>{currencyCents(signal.price)}</strong></div>
        <div><span>RSI 14</span><strong>{signal.rsi14 == null ? "N/A" : signal.rsi14.toFixed(1)}</strong></div>
        <div><span>Rel volume</span><strong>{signal.relative_volume == null ? "N/A" : `${signal.relative_volume.toFixed(2)}x`}</strong></div>
        <div><span>20D return</span><strong>{signal.return_20d == null ? "N/A" : percent(signal.return_20d)}</strong></div>
      </div>

      <div className="smart-candle-component-list">
        {signal.components.map((component) => (
          <div className={component.passed ? "active" : ""} key={component.label}>
            {component.passed ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
            <span>{component.label}</span>
            <strong>{component.value}</strong>
          </div>
        ))}
      </div>

      <div className="smart-candle-chart-legend">
        <span style={{ color: "#2dd4bf" }}>Up candle</span>
        <span style={{ color: "#fb7185" }}>Down candle</span>
        <span style={{ color: "#38bdf8" }}>SMA 20</span>
        <span style={{ color: "#f59e0b" }}>SMA 50</span>
        <span style={{ color: "#c084fc" }}>SMA 200</span>
        <span style={{ color: colorHex(signal.candle_color) }}>Latest candle</span>
      </div>
      <SmartCandlestickChart signal={signal} />
    </>
  );
}

function SmartCandlestickChart({ signal }: { signal: SmartCandleSignal }) {
  const rows = signal.chart.slice(-84);
  if (!rows.length) {
    return <div className="smart-candle-loading">No chart bars available for this signal.</div>;
  }

  const width = 920;
  const height = 370;
  const left = 58;
  const right = 66;
  const top = 18;
  const priceBottom = 252;
  const volumeTop = 284;
  const volumeBottom = 342;
  const plotWidth = width - left - right;
  const step = rows.length > 1 ? plotWidth / (rows.length - 1) : plotWidth;
  const candleWidth = Math.max(3, Math.min(9, step * 0.58));
  const priceValues = rows.flatMap((row) => [row.high, row.low, row.sma20, row.sma50, row.sma200].filter(isNumber));
  const rawMin = Math.min(...priceValues);
  const rawMax = Math.max(...priceValues);
  const padding = Math.max((rawMax - rawMin) * 0.08, rawMax * 0.005);
  const minPrice = rawMin - padding;
  const maxPrice = rawMax + padding;
  const maxVolume = Math.max(...rows.map((row) => row.volume), 1);
  const latest = rows[rows.length - 1];
  const priceTicks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => maxPrice - (maxPrice - minPrice) * ratio);
  const dateTickIndexes = [0, 0.25, 0.5, 0.75, 1].map((ratio) => Math.min(rows.length - 1, Math.round((rows.length - 1) * ratio)));

  function x(index: number) {
    return left + index * step;
  }

  function y(value: number) {
    const ratio = (maxPrice - value) / Math.max(maxPrice - minPrice, 0.0001);
    return top + ratio * (priceBottom - top);
  }

  function volumeY(value: number) {
    const ratio = value / maxVolume;
    return volumeBottom - ratio * (volumeBottom - volumeTop);
  }

  return (
    <div className="smart-candle-chart-shell">
      <div className="smart-candle-chart-topline">
        <div>
          <strong>{signal.symbol} daily candles</strong>
          <span>{formatShortDate(rows[0].date)} to {formatShortDate(latest.date)}</span>
        </div>
        <b className={signal.candle_color}>{labelForColor(signal.candle_color)}</b>
      </div>
      <svg className="smart-candle-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${signal.symbol} candlestick chart with volume`}>
        <rect x={left} y={top} width={plotWidth} height={priceBottom - top} rx="8" fill="rgba(9, 24, 21, 0.72)" stroke="#17352d" />
        <rect x={left} y={volumeTop} width={plotWidth} height={volumeBottom - volumeTop} rx="8" fill="rgba(9, 24, 21, 0.72)" stroke="#17352d" />

        {priceTicks.map((tick) => (
          <g key={tick}>
            <line x1={left} x2={left + plotWidth} y1={y(tick)} y2={y(tick)} stroke="#17352d" strokeDasharray="3 4" />
            <text x={width - 8} y={y(tick) + 4} textAnchor="end" className="smart-candle-axis-text">{compactCurrency(tick)}</text>
          </g>
        ))}

        {dateTickIndexes.map((index) => (
          <text key={`${rows[index].date}-${index}`} x={x(index)} y={height - 9} textAnchor={index === 0 ? "start" : index === rows.length - 1 ? "end" : "middle"} className="smart-candle-axis-text">
            {formatShortDate(rows[index].date)}
          </text>
        ))}

        <text x={left - 12} y={volumeTop + 14} textAnchor="end" className="smart-candle-axis-text">Vol</text>
        <text x={width - 8} y={volumeTop + 14} textAnchor="end" className="smart-candle-axis-text">{compactNumber(maxVolume)}</text>

        {rows.map((row, index) => {
          const isLatest = index === rows.length - 1;
          const up = row.close >= row.open;
          const fill = isLatest ? colorHex(signal.candle_color) : up ? "#2dd4bf" : "#fb7185";
          const center = x(index);
          const openY = y(row.open);
          const closeY = y(row.close);
          const bodyTop = Math.min(openY, closeY);
          const bodyHeight = Math.max(2, Math.abs(openY - closeY));
          const volumeTopY = volumeY(row.volume);
          return (
            <g key={`${row.date}-${index}`}>
              <title>{`${row.date} O ${currencyCents(row.open)} H ${currencyCents(row.high)} L ${currencyCents(row.low)} C ${currencyCents(row.close)} Vol ${compactNumber(row.volume)}`}</title>
              <rect
                x={center - candleWidth / 2}
                y={volumeTopY}
                width={Math.max(2, candleWidth)}
                height={Math.max(1, volumeBottom - volumeTopY)}
                fill={fill}
                opacity={isLatest ? 0.82 : 0.34}
                rx="1.5"
              />
              <line x1={center} x2={center} y1={y(row.high)} y2={y(row.low)} stroke={fill} strokeWidth={isLatest ? 2 : 1.2} />
              <rect
                x={center - candleWidth / 2}
                y={bodyTop}
                width={candleWidth}
                height={bodyHeight}
                fill={fill}
                stroke={isLatest ? "#fff" : fill}
                strokeWidth={isLatest ? 1.4 : 0.8}
                rx="1.5"
              />
            </g>
          );
        })}

        <path d={linePath(rows, "sma20", x, y)} fill="none" stroke="#38bdf8" strokeWidth="1.4" />
        <path d={linePath(rows, "sma50", x, y)} fill="none" stroke="#f59e0b" strokeWidth="1.4" />
        <path d={linePath(rows, "sma200", x, y)} fill="none" stroke="#c084fc" strokeWidth="1.4" />

        <line x1={x(rows.length - 1)} x2={x(rows.length - 1)} y1={top} y2={volumeBottom} stroke={colorHex(signal.candle_color)} strokeDasharray="4 4" opacity="0.72" />
      </svg>
    </div>
  );
}

function EmptyDetails() {
  return (
    <div className="smart-candle-empty-detail">
      <CandlestickChart size={34} />
      <h2>No candle selected</h2>
      <p>Run a scan, then select a smart-candle card to review its chart and rule components.</p>
    </div>
  );
}

function NumberField({ label, value, min, max, step, onChange }: { label: string; value: number; min: number; max: number; step: number; onChange: (value: string) => void }) {
  return (
    <label>
      <span>{label}</span>
      <input type="number" min={min} max={max} step={step} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function Stat({ label, value, helper }: { label: string; value: number; helper: string }) {
  return (
    <article className="dashboard-panel stat-card smart-candle-stat-panel">
      <span>{label}</span>
      <strong>{value.toLocaleString()}</strong>
      <p>{helper}</p>
    </article>
  );
}

function labelForColor(color: SmartCandleColor) {
  return {
    blue: "Blue accumulation",
    pink: "Pink caution",
    red: "Red breakdown",
    neutral: "Neutral",
  }[color];
}

function colorHex(color: SmartCandleColor) {
  return {
    blue: "#2563eb",
    pink: "#be185d",
    red: "#dc2626",
    neutral: "#64748b",
  }[color];
}

function currencyCents(value: number) {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`;
}

function compactCurrency(value: number) {
  if (Math.abs(value) >= 1000) return `$${(value / 1000).toFixed(0)}k`;
  return `$${value.toFixed(0)}`;
}

function compactNumber(value: number) {
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function linePath(rows: SmartCandleChartPoint[], key: "sma20" | "sma50" | "sma200", x: (index: number) => number, y: (value: number) => number) {
  let output = "";
  let drawing = false;
  rows.forEach((row, index) => {
    const value = row[key];
    if (!isNumber(value)) {
      drawing = false;
      return;
    }
    output += `${drawing ? "L" : "M"}${x(index).toFixed(2)} ${y(value).toFixed(2)} `;
    drawing = true;
  });
  return output.trim();
}

function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function formatDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}

function formatShortDate(value: string) {
  const parsed = new Date(`${value}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}
