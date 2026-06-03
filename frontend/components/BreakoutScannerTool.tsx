"use client";

import {
  Activity,
  AlertTriangle,
  CandlestickChart,
  Gauge,
  Loader2,
  Plus,
  RefreshCw,
  ShieldCheck,
  Target,
  TrendingUp,
  X
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  BreakoutBacktest,
  BreakoutChartPoint,
  BreakoutDetectorType,
  BreakoutScan,
  BreakoutScannerConfig,
  BreakoutSignal,
  BreakoutUniverse,
  IbkrBreakoutStatus,
  apiFetch,
  percent
} from "@/lib/api";

const IBKR_API = process.env.NEXT_PUBLIC_IBKR_API_URL ?? "http://localhost:8002";

const detectorCards: Array<{ id: BreakoutDetectorType; title: string; summary: string }> = [
  { id: "ceiling_breakout", title: "Ceiling Breakouts", summary: "Multi-touch resistance cleared with volume confirmation." },
  { id: "momentum_breakout", title: "Momentum Breakouts", summary: "Recent highs, strong trend, and broad price follow-through." },
  { id: "near_breakout", title: "Near-Breakout Watch", summary: "Stocks coiled just below a tested ceiling for review." }
];

const defaultConfig: BreakoutScannerConfig = {
  detectors: ["ceiling_breakout", "momentum_breakout", "near_breakout"],
  custom_symbols: [],
  lookback_days: 420,
  min_relative_volume: 1.5,
  ideal_relative_volume: 2,
  min_ceiling_touches: 3,
  ceiling_tolerance_pct: 0.025,
  breakout_clearance_pct: 0.01,
  near_breakout_pct: 0.03,
  min_avg_dollar_volume: 25_000_000,
  require_above_sma200: true,
  max_symbols: 120
};

export function BreakoutScannerTool() {
  const bootstrapped = useRef(false);
  const [dataSource, setDataSource] = useState<"ibkr" | "yfinance">("ibkr");
  const [ibkrStatus, setIbkrStatus] = useState<IbkrBreakoutStatus | null>(null);
  const [config, setConfig] = useState<BreakoutScannerConfig>(defaultConfig);
  const [universe, setUniverse] = useState<BreakoutUniverse | null>(null);
  const [scan, setScan] = useState<BreakoutScan | null>(null);
  const [selectedKey, setSelectedKey] = useState("");
  const [watchlistInput, setWatchlistInput] = useState("");
  const [backtestDetector, setBacktestDetector] = useState<BreakoutDetectorType>("ceiling_breakout");
  const [backtestYears, setBacktestYears] = useState(5);
  const [backtest, setBacktest] = useState<BreakoutBacktest | null>(null);
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;
    void bootstrap();
  }, []);

  const visibleSignals = useMemo(() => {
    const activeDetectors = new Set(config.detectors);
    return (scan?.signals ?? []).filter((signal) => activeDetectors.has(signal.detector_type as BreakoutDetectorType));
  }, [config.detectors, scan]);
  const selected = useMemo(() => visibleSignals.find((signal) => signalKey(signal) === selectedKey) ?? visibleSignals[0] ?? null, [selectedKey, visibleSignals]);

  useEffect(() => {
    if (!visibleSignals.length) {
      setSelectedKey("");
      return;
    }
    if (selectedKey && visibleSignals.some((signal) => signalKey(signal) === selectedKey)) return;
    setSelectedKey(signalKey(visibleSignals[0]));
  }, [selectedKey, visibleSignals]);
  const counts = useMemo(() => {
    const signals = scan?.signals ?? [];
    return {
      ceiling: signals.filter((signal) => signal.detector_type === "ceiling_breakout").length,
      momentum: signals.filter((signal) => signal.detector_type === "momentum_breakout").length,
      near: signals.filter((signal) => signal.detector_type === "near_breakout").length
    };
  }, [scan]);

  async function bootstrap() {
    fetch(`${IBKR_API}/api/breakout/status`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((s: IbkrBreakoutStatus | null) => { if (s) setIbkrStatus(s); })
      .catch(() => {});

    apiFetch<BreakoutUniverse>("/breakout-scanner/universe")
      .then(setUniverse)
      .catch(() => {});

    await loadIbkrScan();
  }

  async function loadIbkrScan(extraSymbols = config.custom_symbols) {
    setLoading("scan");
    setError("");
    try {
      const params = new URLSearchParams({ source: "ibkr", index: "ndx100" });
      if (extraSymbols.length) params.set("extra", extraSymbols.join(","));
      const res = await fetch(`${IBKR_API}/api/breakout/scan?${params.toString()}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`IBKR breakout scan failed (${res.status})`);
      const result = await res.json() as BreakoutScan;
      setScan(result);
      setBacktest(null);
      if (result.signals[0]) setSelectedKey(signalKey(result.signals[0]));
      // Refresh status after scan
      fetch(`${IBKR_API}/api/breakout/status`, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((s: IbkrBreakoutStatus | null) => { if (s) setIbkrStatus(s); })
        .catch(() => {});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cannot reach IBKR backend (http://localhost:8002). Is it running?");
    } finally {
      setLoading("");
    }
  }

  async function loadScan(force: boolean) {
    if (dataSource === "ibkr") {
      return loadIbkrScan();
    }
    return loadYfinanceScan(force);
  }

  async function loadYfinanceScan(force: boolean, nextConfig = config) {
    setLoading(force ? "refresh" : "scan");
    setError("");
    try {
      const result = await apiFetch<BreakoutScan>(`/breakout-scanner/scan${force ? "?force=true" : ""}`, {
        method: "POST",
        body: JSON.stringify(nextConfig)
      });
      setScan(result);
      setBacktest(null);
      if (result.signals[0]) setSelectedKey(signalKey(result.signals[0]));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not run Breakout Scanner.");
    } finally {
      setLoading("");
    }
  }

  async function runBacktest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading("backtest");
    setError("");
    try {
      setBacktest(await apiFetch<BreakoutBacktest>("/breakout-scanner/backtest", {
        method: "POST",
        body: JSON.stringify({ ...config, detector: backtestDetector, years: backtestYears })
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not run Breakout Backtest Lab.");
    } finally {
      setLoading("");
    }
  }

  function updateNumber(key: keyof BreakoutScannerConfig, value: string) {
    const parsed = Number(value);
    if (Number.isNaN(parsed)) return;
    setConfig((current) => ({ ...current, [key]: parsed }));
  }

  function toggleDetector(detector: BreakoutDetectorType) {
    setConfig((current) => {
      const exists = current.detectors.includes(detector);
      const next = exists ? current.detectors.filter((item) => item !== detector) : [...current.detectors, detector];
      return { ...current, detectors: next.length ? next : [detector] };
    });
  }

  function appendWatchlistSymbols() {
    const symbols = watchlistInput
      .split(/[\s,]+/)
      .map((value) => value.trim().toUpperCase().replace(/[^A-Z0-9.-]/g, ""))
      .filter(Boolean)
      .slice(0, 10);
    if (!symbols.length) return;
    const nextSymbols = Array.from(new Set([...config.custom_symbols, ...symbols])).slice(0, 25);
    const nextConfig = { ...config, custom_symbols: nextSymbols };
    setConfig(nextConfig);
    setWatchlistInput("");
    setError("");
    void (dataSource === "ibkr" ? loadIbkrScan(nextSymbols) : loadYfinanceScan(false, nextConfig));
  }

  function removeWatchlistSymbol(symbol: string) {
    const nextConfig = { ...config, custom_symbols: config.custom_symbols.filter((item) => item !== symbol) };
    setConfig(nextConfig);
    void (dataSource === "ibkr" ? loadIbkrScan(nextConfig.custom_symbols) : loadYfinanceScan(false, nextConfig));
  }

  return (
    <>
      <section className="dashboard-panel breakout-head">
        <div>
          <p className="eyebrow">Breakout Scanner</p>
          <h2>
            {dataSource === "ibkr"
              ? "Nasdaq-100 breakout research using IBKR live data — ceiling, momentum, and near-breakout setups."
              : "S&P 500 breakout research across ceiling, momentum, and near-breakout setups."}
          </h2>
          <div className="breakout-source-line">
            {dataSource === "ibkr"
              ? <><span><Activity size={14} /> IBKR live / cached bars</span><span><Gauge size={14} /> SMA 20 / 50 / 200</span></>
              : <><span><Target size={14} /> S&P 500 only</span><span><Activity size={14} /> Relative volume</span><span><Gauge size={14} /> SMA 20 / 50 / 200</span></>
            }
          </div>
          {/* Source toggle */}
          <div className="breakout-source-toggle">
            <button
              type="button"
              className={dataSource === "ibkr" ? "active" : ""}
              onClick={() => {
                setDataSource("ibkr");
                setScan(null);
                setError("");
                void loadIbkrScan();
              }}
            >
              IBKR Live · Nasdaq-100
            </button>
            <button
              type="button"
              className={dataSource === "yfinance" ? "active" : ""}
              onClick={() => {
                setDataSource("yfinance");
                setScan(null);
                setError("");
                void loadYfinanceScan(false);
              }}
            >
              Yahoo Finance · S&P 500
            </button>
          </div>
        </div>
        <div className="breakout-actions">
          {dataSource === "ibkr" && ibkrStatus && (
            <span className={ibkrStatus.ibkr_connected ? "status-pill" : "risk-pill"}>
              {ibkrStatus.ibkr_connected ? "IBKR live" : "IBKR offline"} · {ibkrStatus.fresh_today}/{ibkrStatus.ndx100_count} cached
            </span>
          )}
          <span className="status-pill">{scan ? `${visibleSignals.length}/${scan.signals.length} setups` : "No scan yet"}</span>
          <button className="ghost-button" type="button" onClick={() => loadScan(false)} disabled={Boolean(loading)}>
            {loading === "scan" || loading === "initial" ? <Loader2 size={16} className="spin-icon" /> : <RefreshCw size={16} />}
            Run scan
          </button>
          {dataSource === "yfinance" && (
            <button className="primary-button" type="button" onClick={() => loadScan(true)} disabled={loading === "refresh"}>
              {loading === "refresh" ? <Loader2 size={16} className="spin-icon" /> : <RefreshCw size={16} />}
              Force refresh
            </button>
          )}
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
            placeholder="NVDA, SMCI, ARM"
            aria-label="Add watchlist symbols"
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

      <section className="dashboard-panel breakout-notice">
        <ShieldCheck size={18} />
        <p>Educational research only. Setups are not buy or sell instructions; manually verify earnings, news, liquidity, risk, and portfolio fit before making decisions.</p>
      </section>

      {error && <div className="error">{error}</div>}

      <section className="breakout-stat-grid stat-grid">
        <Stat
          label={dataSource === "ibkr" ? "Nasdaq-100 universe" : "S&P 500 universe"}
          value={dataSource === "ibkr" ? (scan?.universe_count ?? ibkrStatus?.ndx100_count ?? 0) : (universe?.count ?? scan?.universe_count ?? 0)}
          helper={dataSource === "ibkr" ? (ibkrStatus ? `${ibkrStatus.fresh_today} cached today` : "loading") : (universe?.cache_status ?? "loading")}
        />
        <Stat label="Scanned symbols" value={scan?.scanned_symbols ?? 0} helper={scan?.data_source ?? "waiting"} />
        <Stat label="Ceiling" value={counts.ceiling} helper="breakout setups" />
        <Stat label="Momentum" value={counts.momentum} helper="breakout setups" />
        <Stat label="Watch" value={counts.near} helper="near-breakout setups" />
      </section>

      <section className="dashboard-panel breakout-detector-panel">
        <div className="panel-header">
          <h2>Detectors</h2>
          <CandlestickChart size={18} />
        </div>
        <div className="breakout-detector-grid">
          {detectorCards.map((detector) => (
            <button
              className={config.detectors.includes(detector.id) ? "active" : ""}
              type="button"
              key={detector.id}
              onClick={() => toggleDetector(detector.id)}
            >
              <strong>{detector.title}</strong>
              <span>{detector.summary}</span>
            </button>
          ))}
        </div>
      </section>

      {dataSource === "yfinance" && <section className="dashboard-panel breakout-config-panel">
        <div className="panel-header">
          <h2>Scanner parameters</h2>
          <TrendingUp size={18} />
        </div>
        <div className="breakout-config-grid">
          <NumberField label="Lookback days" value={config.lookback_days} min={120} max={1600} step={30} onChange={(value) => updateNumber("lookback_days", value)} />
          <NumberField label="Max symbols" value={config.max_symbols} min={1} max={505} step={10} onChange={(value) => updateNumber("max_symbols", value)} />
          <NumberField label="Min rel volume" value={config.min_relative_volume} min={0.1} max={10} step={0.1} onChange={(value) => updateNumber("min_relative_volume", value)} />
          <NumberField label="Ideal rel volume" value={config.ideal_relative_volume} min={0.1} max={20} step={0.1} onChange={(value) => updateNumber("ideal_relative_volume", value)} />
          <NumberField label="Min touches" value={config.min_ceiling_touches} min={1} max={12} step={1} onChange={(value) => updateNumber("min_ceiling_touches", value)} />
          <NumberField label="Ceiling tolerance" value={config.ceiling_tolerance_pct} min={0.001} max={0.15} step={0.001} display="percent" onChange={(value) => updateNumber("ceiling_tolerance_pct", value)} />
          <NumberField label="Breakout clearance" value={config.breakout_clearance_pct} min={0} max={0.2} step={0.001} display="percent" onChange={(value) => updateNumber("breakout_clearance_pct", value)} />
          <NumberField label="Near-breakout band" value={config.near_breakout_pct} min={0.001} max={0.2} step={0.001} display="percent" onChange={(value) => updateNumber("near_breakout_pct", value)} />
          <NumberField label="Min dollar volume" value={config.min_avg_dollar_volume} min={0} max={5_000_000_000} step={5_000_000} onChange={(value) => updateNumber("min_avg_dollar_volume", value)} />
          <label className="breakout-toggle">
            <input type="checkbox" checked={config.require_above_sma200} onChange={(event) => setConfig((current) => ({ ...current, require_above_sma200: event.target.checked }))} />
            <span>Require price above SMA 200</span>
          </label>
        </div>
      </section>}

      <div className="breakout-workbench-grid">
        <section className="dashboard-panel breakout-table-panel">
          <div className="panel-header">
            <div>
              <h2>Ranked setups</h2>
              <p className="fine-print">{scan ? `${visibleSignals.length} shown from ${scan.signals.length} setups · ${formatDateTime(scan.scanned_at)} · ${scan.data_source}` : "Run a scan to populate ranked setups"}</p>
            </div>
          </div>
          <div className="breakout-table">
            <div className="breakout-row breakout-row-header">
              <span>Symbol</span>
              <span>Setup</span>
              <span>Score</span>
              <span>Rel vol</span>
              <span>Resistance</span>
            </div>
            {loading === "initial" && !scan ? (
              <div className="breakout-loading-row"><Loader2 size={18} className="spin-icon" /> Loading breakout scan</div>
            ) : visibleSignals.length ? visibleSignals.map((signal) => (
              <button
                className={`breakout-row ${selected && signalKey(selected) === signalKey(signal) ? "active" : ""}`}
                type="button"
                key={`${signal.symbol}-${signal.detector_type}-${signal.rank}`}
                onClick={() => setSelectedKey(signalKey(signal))}
              >
                <strong>{signal.symbol}<small>{signal.sector}</small></strong>
                <span>{detectorLabel(signal.detector_type)}<small>{signal.trend_label}</small></span>
                <span>{signal.score.toFixed(0)}<small>rank #{signal.rank}</small></span>
                <span>{signal.relative_volume == null ? "N/A" : `${signal.relative_volume.toFixed(2)}x`}<small>{compactNumber(signal.avg_volume_50d ?? 0)} avg vol</small></span>
                <span>{signal.resistance_level == null ? "N/A" : currencyCents(signal.resistance_level)}<small>{breakoutContext(signal)}</small></span>
              </button>
            )) : (
              <div className="breakout-loading-row">{scan?.signals.length ? "No setups match the selected detector filters." : "No current setups match these parameters."}</div>
            )}
          </div>
        </section>

        <section className="dashboard-panel breakout-detail-panel">
          {selected ? <BreakoutDetails signal={selected} /> : <EmptyDetails />}
        </section>
      </div>

      {dataSource === "yfinance" && <section className="dashboard-panel breakout-backtest-panel">
        <div className="panel-header">
          <div>
            <h2>Backtest Lab</h2>
            <p className="fine-print">Runs the selected detector against cached historical OHLCV and summarizes forward-return distributions.</p>
          </div>
        </div>
        <form className="breakout-backtest-form" onSubmit={runBacktest}>
          <label>
            <span>Detector</span>
            <select value={backtestDetector} onChange={(event) => setBacktestDetector(event.target.value as BreakoutDetectorType)}>
              {detectorCards.map((detector) => <option value={detector.id} key={detector.id}>{detector.title}</option>)}
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
          <div className="breakout-backtest-grid">
            <article className="breakout-backtest-summary">
              <span>{detectorLabel(backtest.detector)}</span>
              <strong>{backtest.signal_count}</strong>
              <p>signals over {backtest.evaluated_years} year{backtest.evaluated_years === 1 ? "" : "s"}</p>
            </article>
            {backtest.horizons.map((row) => (
              <article className="breakout-horizon-card" key={row.horizon_days}>
                <span>{row.horizon_days}D forward</span>
                <strong>{row.win_rate == null ? "N/A" : percent(row.win_rate)}</strong>
                <p>Avg {row.average_return == null ? "N/A" : percent(row.average_return)} · P10/P90 {row.p10_return == null ? "N/A" : percent(row.p10_return)} / {row.p90_return == null ? "N/A" : percent(row.p90_return)}</p>
              </article>
            ))}
          </div>
        ) : null}
      </section>}

      {(scan?.warnings.length || universe?.warnings.length || backtest?.warnings.length) ? (
        <section className="dashboard-panel breakout-warning-panel">
          <div className="panel-header">
            <h2>Data notes</h2>
            <AlertTriangle size={18} />
          </div>
          <div className="breakout-warning-list">
            {[...(scan?.warnings ?? []), ...(universe?.warnings ?? []), ...(backtest?.warnings ?? [])].slice(0, 8).map((warning) => <p key={warning}>{warning}</p>)}
          </div>
        </section>
      ) : null}
    </>
  );
}

function BreakoutDetails({ signal }: { signal: BreakoutSignal }) {
  return (
    <>
      <div className="breakout-detail-head">
        <div>
          <span>{detectorLabel(signal.detector_type)}</span>
          <h2>{signal.symbol} {signal.setup_label}</h2>
          <p>{signal.summary}</p>
        </div>
        <div className="breakout-score">
          <span>Score</span>
          <strong>{signal.score.toFixed(0)}</strong>
        </div>
      </div>
      <div className="breakout-detail-stats">
        <div><span>Price</span><strong>{currencyCents(signal.price)}</strong></div>
        <div><span>Resistance</span><strong>{signal.resistance_level == null ? "N/A" : currencyCents(signal.resistance_level)}</strong></div>
        <div><span>Rel volume</span><strong>{signal.relative_volume == null ? "N/A" : `${signal.relative_volume.toFixed(2)}x`}</strong></div>
        <div><span>Touches</span><strong>{signal.touch_count}</strong></div>
      </div>
      <BreakoutCandlestickChart signal={signal} />
    </>
  );
}

function BreakoutCandlestickChart({ signal }: { signal: BreakoutSignal }) {
  const rows = normalizeBreakoutCandles(signal.chart).slice(-84);
  if (!rows.length) {
    return <div className="breakout-empty-detail">No chart bars available for this setup.</div>;
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
  const resistance = signal.resistance_level;
  const priceValues = rows.flatMap((row) => [row.high, row.low, row.sma20, row.sma50, row.sma200, resistance].filter(isNumber));
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
    return volumeBottom - (value / maxVolume) * (volumeBottom - volumeTop);
  }

  return (
    <div className="breakout-chart-panel">
      <div className="breakout-chart-legend">
        <span style={{ color: "#2dd4bf" }}>Up candle</span>
        <span style={{ color: "#fb7185" }}>Down candle</span>
        <span style={{ color: "#38bdf8" }}>SMA 20</span>
        <span style={{ color: "#f59e0b" }}>SMA 50</span>
        <span style={{ color: "#c084fc" }}>SMA 200</span>
        {isNumber(resistance) && <span style={{ color: "#facc15" }}>Resistance</span>}
      </div>
      <div className="breakout-candle-chart-shell">
        <div className="breakout-candle-chart-topline">
          <div>
            <strong>{signal.symbol} daily breakout chart</strong>
            <span>{formatMonthDay(rows[0].date)} to {formatMonthDay(latest.date)} · volume shown below candles</span>
          </div>
          <b>{detectorLabel(signal.detector_type)}</b>
        </div>
        <svg className="breakout-candle-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${signal.symbol} breakout candlestick chart with volume`}>
          <rect x={left} y={top} width={plotWidth} height={priceBottom - top} rx="8" fill="rgba(9, 24, 21, 0.72)" stroke="#17352d" />
          <rect x={left} y={volumeTop} width={plotWidth} height={volumeBottom - volumeTop} rx="8" fill="rgba(9, 24, 21, 0.72)" stroke="#17352d" />

          {priceTicks.map((tick) => (
            <g key={tick}>
              <line x1={left} x2={left + plotWidth} y1={y(tick)} y2={y(tick)} stroke="#17352d" strokeDasharray="3 4" />
              <text x={width - 8} y={y(tick) + 4} textAnchor="end" className="breakout-candle-axis-text">{compactCurrency(tick)}</text>
            </g>
          ))}

          {dateTickIndexes.map((index) => (
            <text key={`${rows[index].date}-${index}`} x={x(index)} y={height - 9} textAnchor={index === 0 ? "start" : index === rows.length - 1 ? "end" : "middle"} className="breakout-candle-axis-text">
              {formatMonthDay(rows[index].date)}
            </text>
          ))}

          <text x={left - 12} y={volumeTop + 14} textAnchor="end" className="breakout-candle-axis-text">Vol</text>
          <text x={width - 8} y={volumeTop + 14} textAnchor="end" className="breakout-candle-axis-text">{compactNumber(maxVolume)}</text>

          {rows.map((row, index) => {
            const up = row.close >= row.open;
            const fill = up ? "#2dd4bf" : "#fb7185";
            const center = x(index);
            const openY = y(row.open);
            const closeY = y(row.close);
            const bodyTop = Math.min(openY, closeY);
            const bodyHeight = Math.max(2, Math.abs(openY - closeY));
            const volumeTopY = volumeY(row.volume);
            return (
              <g key={`${row.date}-${index}`}>
                <title>{`${row.date} O ${currencyCents(row.open)} H ${currencyCents(row.high)} L ${currencyCents(row.low)} C ${currencyCents(row.close)} Vol ${compactNumber(row.volume)}`}</title>
                <rect x={center - candleWidth / 2} y={volumeTopY} width={Math.max(2, candleWidth)} height={Math.max(1, volumeBottom - volumeTopY)} fill={fill} opacity="0.34" rx="1.5" />
                <line x1={center} x2={center} y1={y(row.high)} y2={y(row.low)} stroke={fill} strokeWidth="1.2" />
                <rect x={center - candleWidth / 2} y={bodyTop} width={candleWidth} height={bodyHeight} fill={fill} stroke={fill} strokeWidth="0.8" rx="1.5" />
              </g>
            );
          })}

          <path d={linePath(rows, "sma20", x, y)} fill="none" stroke="#38bdf8" strokeWidth="1.4" />
          <path d={linePath(rows, "sma50", x, y)} fill="none" stroke="#f59e0b" strokeWidth="1.4" />
          <path d={linePath(rows, "sma200", x, y)} fill="none" stroke="#c084fc" strokeWidth="1.4" />

          {isNumber(resistance) && (
            <g>
              <line x1={left} x2={left + plotWidth} y1={y(resistance)} y2={y(resistance)} stroke="#facc15" strokeDasharray="5 4" strokeWidth="1.5" />
              <text x={width - 8} y={y(resistance) - 6} textAnchor="end" fill="#facc15" fontSize="11" fontWeight="760">R {currencyCents(resistance)}</text>
            </g>
          )}
        </svg>
      </div>
    </div>
  );
}

function EmptyDetails() {
  return (
    <div className="breakout-empty-detail">
      <CandlestickChart size={32} />
      <h2>Select a setup</h2>
      <p>Price, volume, moving averages, and resistance context appear here.</p>
    </div>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  step,
  display,
  onChange
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  display?: "percent";
  onChange: (value: string) => void;
}) {
  return (
    <label>
      <span>{label}</span>
      <input type="number" min={min} max={max} step={step} value={value} onChange={(event) => onChange(event.target.value)} />
      {display === "percent" && <small>{percent(value)}</small>}
    </label>
  );
}

function Stat({ label, value, helper }: { label: string; value: number; helper: string }) {
  return (
    <article className="stat-panel breakout-stat-panel">
      <h3>{label}</h3>
      <strong>{value}</strong>
      <p>{helper}</p>
    </article>
  );
}

function detectorLabel(value: string) {
  if (value === "ceiling_breakout") return "Ceiling";
  if (value === "momentum_breakout") return "Momentum";
  if (value === "near_breakout") return "Near breakout";
  return value;
}

function signalKey(signal: BreakoutSignal) {
  return `${signal.symbol}:${signal.detector_type}:${signal.rank}`;
}

function breakoutContext(signal: BreakoutSignal) {
  if (signal.detector_type === "near_breakout") return signal.proximity_pct == null ? "near band N/A" : `${percent(signal.proximity_pct)} below`;
  return signal.breakout_pct == null ? "breakout N/A" : `${percent(signal.breakout_pct)} clear`;
}

function currencyCents(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function compactCurrency(value: number) {
  if (Math.abs(value) >= 1000) return `$${Math.round(value / 1000)}k`;
  return `$${Math.round(value)}`;
}

function compactNumber(value: number) {
  if (!Number.isFinite(value)) return "N/A";
  if (Math.abs(value) >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`;
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return `${Math.round(value)}`;
}

type BreakoutCandlePoint = BreakoutChartPoint & {
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

function normalizeBreakoutCandles(points: BreakoutChartPoint[]): BreakoutCandlePoint[] {
  return points.map((point) => {
    const close = numberOr(point.close, 0);
    const open = numberOr(point.open, close);
    const high = Math.max(numberOr(point.high, Math.max(open, close)), open, close);
    const low = Math.min(numberOr(point.low, Math.min(open, close)), open, close);
    return { ...point, open, high, low, close, volume: Math.max(0, numberOr(point.volume, 0)) };
  }).filter((point) => point.close > 0);
}

function linePath(rows: BreakoutCandlePoint[], key: "sma20" | "sma50" | "sma200", x: (index: number) => number, y: (value: number) => number) {
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

function numberOr(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
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

function formatDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
