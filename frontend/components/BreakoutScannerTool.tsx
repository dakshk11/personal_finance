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
  TrendingUp
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  Bar,
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
import {
  BreakoutBacktest,
  BreakoutDetectorType,
  BreakoutScan,
  BreakoutScannerConfig,
  BreakoutSignal,
  BreakoutUniverse,
  apiFetch,
  percent
} from "@/lib/api";

const detectorCards: Array<{ id: BreakoutDetectorType; title: string; summary: string }> = [
  { id: "ceiling_breakout", title: "Ceiling Breakouts", summary: "Multi-touch resistance cleared with volume confirmation." },
  { id: "momentum_breakout", title: "Momentum Breakouts", summary: "Recent highs, strong trend, and broad price follow-through." },
  { id: "near_breakout", title: "Near-Breakout Watch", summary: "Stocks coiled just below a tested ceiling for review." }
];

const defaultConfig: BreakoutScannerConfig = {
  detectors: ["ceiling_breakout", "momentum_breakout", "near_breakout"],
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
  const [config, setConfig] = useState<BreakoutScannerConfig>(defaultConfig);
  const [universe, setUniverse] = useState<BreakoutUniverse | null>(null);
  const [scan, setScan] = useState<BreakoutScan | null>(null);
  const [selectedKey, setSelectedKey] = useState("");
  const [backtestDetector, setBacktestDetector] = useState<BreakoutDetectorType>("ceiling_breakout");
  const [backtestYears, setBacktestYears] = useState(5);
  const [backtest, setBacktest] = useState<BreakoutBacktest | null>(null);
  const [loading, setLoading] = useState("initial");
  const [error, setError] = useState("");

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;
    void bootstrap();
  }, []);

  useEffect(() => {
    if (!scan?.signals.length) return;
    if (selectedKey && scan.signals.some((signal) => signalKey(signal) === selectedKey)) return;
    setSelectedKey(signalKey(scan.signals[0]));
  }, [scan, selectedKey]);

  const selected = useMemo(() => scan?.signals.find((signal) => signalKey(signal) === selectedKey) ?? scan?.signals[0] ?? null, [scan, selectedKey]);
  const counts = useMemo(() => {
    const signals = scan?.signals ?? [];
    return {
      ceiling: signals.filter((signal) => signal.detector_type === "ceiling_breakout").length,
      momentum: signals.filter((signal) => signal.detector_type === "momentum_breakout").length,
      near: signals.filter((signal) => signal.detector_type === "near_breakout").length
    };
  }, [scan]);

  async function bootstrap() {
    setLoading("initial");
    setError("");
    try {
      const [universeResult, scanResult] = await Promise.all([
        apiFetch<BreakoutUniverse>("/breakout-scanner/universe"),
        apiFetch<BreakoutScan>("/breakout-scanner/scan", {
          method: "POST",
          body: JSON.stringify(defaultConfig)
        })
      ]);
      setUniverse(universeResult);
      setScan(scanResult);
      if (scanResult.signals[0]) setSelectedKey(signalKey(scanResult.signals[0]));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load Breakout Scanner.");
    } finally {
      setLoading("");
    }
  }

  async function loadScan(force: boolean) {
    setLoading(force ? "refresh" : "scan");
    setError("");
    try {
      const result = await apiFetch<BreakoutScan>(`/breakout-scanner/scan${force ? "?force=true" : ""}`, {
        method: "POST",
        body: JSON.stringify(config)
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

  return (
    <>
      <section className="dashboard-panel breakout-head">
        <div>
          <p className="eyebrow">Breakout Scanner</p>
          <h2>S&P 500 breakout research across ceiling, momentum, and near-breakout setups.</h2>
          <div className="breakout-source-line">
            <span><Target size={14} /> S&P 500 only</span>
            <span><Activity size={14} /> Relative volume</span>
            <span><Gauge size={14} /> SMA 20 / 50 / 200</span>
          </div>
        </div>
        <div className="breakout-actions">
          <span className="status-pill">{scan ? `${scan.signals.length} setups` : "Loading"}</span>
          <button className="ghost-button" type="button" onClick={() => loadScan(false)} disabled={Boolean(loading)}>
            {loading === "scan" || loading === "initial" ? <Loader2 size={16} className="spin-icon" /> : <RefreshCw size={16} />}
            Run scan
          </button>
          <button className="primary-button" type="button" onClick={() => loadScan(true)} disabled={loading === "refresh"}>
            {loading === "refresh" ? <Loader2 size={16} className="spin-icon" /> : <RefreshCw size={16} />}
            Force refresh
          </button>
        </div>
      </section>

      <section className="dashboard-panel breakout-notice">
        <ShieldCheck size={18} />
        <p>Educational research only. Setups are not buy or sell instructions; manually verify earnings, news, liquidity, risk, and portfolio fit before making decisions.</p>
      </section>

      {error && <div className="error">{error}</div>}

      <section className="breakout-stat-grid stat-grid">
        <Stat label="S&P 500 universe" value={universe?.count ?? scan?.universe_count ?? 0} helper={universe?.cache_status ?? "loading"} />
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

      <section className="dashboard-panel breakout-config-panel">
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
      </section>

      <div className="breakout-workbench-grid">
        <section className="dashboard-panel breakout-table-panel">
          <div className="panel-header">
            <div>
              <h2>Ranked setups</h2>
              <p className="fine-print">{scan ? `${formatDateTime(scan.scanned_at)} · ${scan.data_source}` : "Run a scan to populate ranked setups"}</p>
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
            ) : scan?.signals.length ? scan.signals.map((signal) => (
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
              <div className="breakout-loading-row">No current setups match these parameters.</div>
            )}
          </div>
        </section>

        <section className="dashboard-panel breakout-detail-panel">
          {selected ? <BreakoutDetails signal={selected} /> : <EmptyDetails />}
        </section>
      </div>

      <section className="dashboard-panel breakout-backtest-panel">
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
      </section>

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
      <div className="breakout-chart-panel">
        <ResponsiveContainer width="100%" height={430}>
          <ComposedChart data={signal.chart} margin={{ left: 4, right: 18, top: 10, bottom: 8 }}>
            <CartesianGrid stroke="#17352d" strokeDasharray="3 3" />
            <XAxis dataKey="date" minTickGap={42} tickFormatter={formatMonthDay} tick={{ fontSize: 11, fill: "#8da99e" }} axisLine={{ stroke: "#24463c" }} tickLine={{ stroke: "#24463c" }} />
            <YAxis yAxisId="price" width={64} tickFormatter={(value) => compactCurrency(Number(value))} tick={{ fontSize: 11, fill: "#8da99e" }} axisLine={{ stroke: "#24463c" }} tickLine={{ stroke: "#24463c" }} />
            <YAxis yAxisId="volume" orientation="right" width={58} tickFormatter={(value) => compactNumber(Number(value))} tick={{ fontSize: 11, fill: "#8da99e" }} axisLine={{ stroke: "#24463c" }} tickLine={{ stroke: "#24463c" }} />
            <Tooltip content={<BreakoutTooltip />} />
            <Legend wrapperStyle={{ color: "#b6d9cb", fontSize: 12 }} />
            <Bar yAxisId="volume" dataKey="volume" name="Volume" fill="#164e63" opacity={0.35} />
            <Line yAxisId="price" type="monotone" dataKey="close" name="Close" stroke="#5eead4" strokeWidth={2.5} dot={false} />
            <Line yAxisId="price" type="monotone" dataKey="sma20" name="SMA 20" stroke="#38bdf8" strokeWidth={1.4} dot={false} connectNulls />
            <Line yAxisId="price" type="monotone" dataKey="sma50" name="SMA 50" stroke="#f59e0b" strokeWidth={1.5} dot={false} connectNulls />
            <Line yAxisId="price" type="monotone" dataKey="sma200" name="SMA 200" stroke="#c084fc" strokeWidth={1.5} dot={false} connectNulls />
            {signal.resistance_level != null && <ReferenceLine yAxisId="price" y={signal.resistance_level} stroke="#fb7185" strokeDasharray="5 5" label={{ value: "Resistance", fill: "#fb7185", fontSize: 11 }} />}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </>
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

function BreakoutTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ name: string; value: number; color?: string }>; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="option-chart-tooltip">
      <strong>{formatShortDate(label)}</strong>
      {payload.filter((item) => item.value != null).map((item) => (
        <span key={item.name} style={{ color: item.color }}>
          {item.name}: {item.name === "Volume" ? compactNumber(Number(item.value)) : currencyCents(Number(item.value))}
        </span>
      ))}
    </div>
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
