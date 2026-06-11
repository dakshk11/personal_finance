"use client";

import {
  Activity,
  AlertTriangle,
  Bell,
  Bot,
  CheckCircle2,
  Gauge,
  Loader2,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
  TrendingDown,
  TrendingUp,
  Zap
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  AIAdvisorAlpacaKeyStatus,
  apiFetch
} from "@/lib/api";

const IBKR_API = process.env.NEXT_PUBLIC_IBKR_API_URL ?? "http://localhost:8002";
const SETTINGS_KEY = "financeos_optitrade_lab_settings";
const DEFAULT_SYMBOLS = [
  "TQQQ", "SOXL", "UPRO",
  "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "AVGO", "GOOG", "META", "TSLA", "MU",
  "LLY", "BRK.B", "AMD", "JPM", "XOM", "JNJ", "V", "INTC", "WMT", "CSCO"
];

type OptiTradeView = "signals" | "backtest" | "risk" | "automation";
type TpMode = "single" | "multi" | "always_in";
type StopModel = "atr" | "swing";
type StrategyFocus = "flip" | "dynamic" | "multi" | "chop";
type DataSource = "ibkr" | "alpaca";

type OptiTradeSettings = {
  accountSize: string;
  riskPct: string;
  atrMultiplier: string;
  tpMode: TpMode;
  stopModel: StopModel;
  maxDrawdownGuard: string;
};

type OptiTradeBacktest = {
  period: string;
  win_rate: number;
  profit_factor: number;
  max_drawdown: number;
  total_trades: number;
  avg_trade: number;
  trades: OptiTradeBacktestTrade[];
};

type OptiTradeBacktestTrade = {
  direction: "BUY" | "SELL" | string;
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  return_pct: number;
  exit_reason: string;
  bars_held: number;
};

type OptiTradeChartPoint = {
  date: string;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close: number;
  volume?: number | null;
  ema21: number | null;
  ema55: number | null;
  entry: number;
  stop_loss: number;
  tp1: number;
  tp2: number;
  tp3: number;
  tp4: number;
  marker?: "BUY" | "SELL";
};

type OptiTradeSignal = {
  symbol: string;
  underlying: string;
  as_of_date: string;
  price: number;
  signal: "BUY" | "SELL" | "HOLD" | string;
  trend_state: string;
  anti_chop_state: string;
  anti_chop_pass: boolean;
  entry: number;
  stop_loss: number;
  take_profits: number[];
  risk_reward: number | null;
  atr: number;
  momentum_score: number;
  volume_score: number;
  rsi: number;
  chart: OptiTradeChartPoint[];
  backtest: OptiTradeBacktest;
};

type OptiTradeResponse = {
  generated_at: string;
  data_source: string;
  signals: OptiTradeSignal[];
  warnings: string[];
  rate_limit?: {
    limit_per_minute: number;
    remaining: number;
    pagination_note: string;
  };
};

type OptiTradeBacktestResponse = {
  generated_at: string;
  data_source: string;
  symbol: string;
  underlying: string;
  backtest: OptiTradeBacktest;
  rate_limit?: {
    limit_per_minute: number;
    remaining: number;
    pagination_note: string;
  };
};

export function OptiTradeLabTool({ alpacaKeyStatus }: { alpacaKeyStatus: AIAdvisorAlpacaKeyStatus | null }) {
  const [result, setResult] = useState<OptiTradeResponse | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState(DEFAULT_SYMBOLS[0]);
  const [dataSource, setDataSource] = useState<DataSource>("alpaca");
  const [view, setView] = useState<OptiTradeView>("signals");
  const [strategyFocus, setStrategyFocus] = useState<StrategyFocus>("flip");
  const [settings, setSettings] = useState<OptiTradeSettings>(loadSettings);
  const [settingsBacktest, setSettingsBacktest] = useState<OptiTradeBacktestResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [backtestLoading, setBacktestLoading] = useState(false);
  const [error, setError] = useState("");
  const [backtestError, setBacktestError] = useState("");

  const selected = useMemo(
    () => result?.signals.find((row) => row.symbol === selectedSymbol) ?? result?.signals[0] ?? null,
    [result, selectedSymbol]
  );
  const counts = useMemo(() => ({
    buy: result?.signals.filter((row) => row.signal === "BUY").length ?? 0,
    sell: result?.signals.filter((row) => row.signal === "SELL").length ?? 0,
    hold: result?.signals.filter((row) => row.signal === "HOLD").length ?? 0,
  }), [result]);
  const canRefresh = !loading && (dataSource === "ibkr" || Boolean(alpacaKeyStatus?.has_key));

  useEffect(() => {
    void loadSignals();
  }, [dataSource]);

  useEffect(() => {
    window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  }, [settings]);

  useEffect(() => {
    setSettingsBacktest(null);
    setBacktestError("");
  }, [selectedSymbol, settings.atrMultiplier, settings.tpMode, settings.stopModel]);

  async function loadSignals() {
    if (dataSource === "alpaca" && !alpacaKeyStatus?.has_key) {
      setError("Save an Alpaca API key and secret in the left rail before using Alpaca OptiTrade Lab data.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await fetchOptiTradeSignals(dataSource);
      setResult(data);
      setSelectedSymbol((current) => data.signals.some((row) => row.symbol === current) ? current : data.signals[0]?.symbol ?? DEFAULT_SYMBOLS[0]);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Could not load OptiTrade Lab signals from ${dataSourceLabel(dataSource)}.`);
    } finally {
      setLoading(false);
    }
  }

  function updateSetting(field: keyof OptiTradeSettings, value: string) {
    setSettings((current) => ({ ...current, [field]: value }));
  }

  async function runSettingsBacktest() {
    if (!selected) return;
    setBacktestLoading(true);
    setBacktestError("");
    try {
      const params = new URLSearchParams({
        symbol: selected.symbol,
        atr_multiplier: String(numericInput(settings.atrMultiplier) || 2.5),
        tp_mode: settings.tpMode,
        stop_model: settings.stopModel,
      });
      setSettingsBacktest(await fetchOptiTradeBacktest(dataSource, params));
    } catch (err) {
      setBacktestError(err instanceof Error ? err.message : `Could not run settings-aware ${dataSourceLabel(dataSource)} backtest.`);
    } finally {
      setBacktestLoading(false);
    }
  }

  function selectStrategy(focus: StrategyFocus) {
    setStrategyFocus(focus);
    setView(focus === "chop" ? "automation" : "signals");
  }

  return (
    <div className="optitrade-lab">
      <section className="dashboard-panel opti-hero">
        <div>
          <h2>OptiTrade Lab</h2>
          <p>
            Leveraged ETF signal cockpit with trend regime, dynamic stops, multi-target exits,
            anti-chop filtering, and simulated automation rules.
          </p>
        </div>
        <div className="opti-hero-status">
          <div className="opti-source-toggle" role="radiogroup" aria-label="OptiTrade data source">
            <button type="button" className={dataSource === "ibkr" ? "active" : ""} onClick={() => setDataSource("ibkr")}>IBKR live</button>
            <button type="button" className={dataSource === "alpaca" ? "active" : ""} onClick={() => setDataSource("alpaca")}>Alpaca</button>
          </div>
          <span><TrendingUp size={15} /> {counts.buy} buy</span>
          <span><TrendingDown size={15} /> {counts.sell} sell</span>
          <span><Gauge size={15} /> {counts.hold} hold</span>
          <button className="primary-button" type="button" onClick={loadSignals} disabled={!canRefresh}>
            {loading ? <Loader2 size={16} className="spin-icon" /> : <RefreshCw size={16} />}
            Refresh
          </button>
        </div>
      </section>

      <section className="opti-strategy-grid">
        <StrategyCard title="Buy/Sell Flip" detail="Trend and momentum combine into clear long, exit, or wait states." icon={<Activity size={17} />} active={strategyFocus === "flip"} onClick={() => selectStrategy("flip")} />
        <StrategyCard title="Dynamic TP/SL" detail="ATR-sized risk bands define stop loss and profit objectives." icon={<SlidersHorizontal size={17} />} active={strategyFocus === "dynamic"} onClick={() => selectStrategy("dynamic")} />
        <StrategyCard title="Multi-TP" detail="TP1 through TP4 create a staged exit map for volatile ETFs." icon={<Zap size={17} />} active={strategyFocus === "multi"} onClick={() => selectStrategy("multi")} />
        <StrategyCard title="Anti-Chop" detail="Range and volatility filters suppress low-quality sideways signals." icon={<ShieldCheck size={17} />} active={strategyFocus === "chop"} onClick={() => selectStrategy("chop")} />
      </section>

      {error && (
        <section className="dashboard-panel opti-warning">
          <AlertTriangle size={18} />
          <p>{error}</p>
        </section>
      )}

      {dataSource === "alpaca" && !alpacaKeyStatus?.has_key && (
        <section className="dashboard-panel opti-warning">
          <AlertTriangle size={18} />
          <p>Save an Alpaca API key and secret in the left rail before using Alpaca OptiTrade Lab data.</p>
        </section>
      )}

      <section className="dashboard-panel opti-tabs-panel">
        <div className="opti-tabs">
          <button type="button" className={view === "signals" ? "active" : ""} onClick={() => setView("signals")}>Signals</button>
          <button type="button" className={view === "backtest" ? "active" : ""} onClick={() => setView("backtest")}>Backtest</button>
          <button type="button" className={view === "risk" ? "active" : ""} onClick={() => setView("risk")}>Risk Settings</button>
          <button type="button" className={view === "automation" ? "active" : ""} onClick={() => setView("automation")}>Automation</button>
        </div>
      </section>

      {view === "signals" && (
        <>
          <section className="opti-signal-grid">
            {loading && !result ? (
              <div className="dashboard-panel opti-loading"><Loader2 size={18} className="spin-icon" /> Loading leveraged ETF signals</div>
            ) : result?.signals.map((row) => (
              <button
                type="button"
                key={row.symbol}
                className={`opti-signal-card ${row.signal.toLowerCase()} ${selected?.symbol === row.symbol ? "active" : ""}`}
                onClick={() => setSelectedSymbol(row.symbol)}
              >
                <span>{row.underlying} engine</span>
                <strong>{row.symbol}</strong>
                <b>{row.signal}</b>
                <small>{row.trend_state} | {row.anti_chop_state}</small>
                <i>Momentum {row.momentum_score.toFixed(1)} / Volume {row.volume_score.toFixed(1)}</i>
              </button>
            ))}
          </section>

          {selected && <SignalWorkbench signal={selected} settings={settings} generatedAt={result?.generated_at} focus={strategyFocus} />}
        </>
      )}

      {view === "backtest" && (
        <section className="dashboard-panel opti-backtest-panel">
          <div className="panel-header">
            <div>
              <h2>{selected ? `${selected.symbol} Backtest` : "Backtest Snapshot"}</h2>
              <p className="fine-print">{settingsBacktest ? `${formatDateTime(settingsBacktest.generated_at)} | current settings` : result ? `${formatDateTime(result.generated_at)} | default scan settings` : `Run refresh to load ${dataSourceLabel(dataSource)} history`}</p>
            </div>
            <button className="primary-button" type="button" onClick={runSettingsBacktest} disabled={!selected || backtestLoading}>
              {backtestLoading ? <Loader2 size={16} className="spin-icon" /> : <RefreshCw size={16} />}
              Run backtest with current settings
            </button>
          </div>
          {backtestError && <p className="opti-backtest-error">{backtestError}</p>}
          <div className="opti-backtest-context">
            <span>ETF: <strong>{selected?.symbol ?? "N/A"}</strong></span>
            <span>Underlying: <strong>{selected?.underlying ?? "N/A"}</strong></span>
            <span>TP: <strong>{labelForTpMode(settings.tpMode)}</strong></span>
            <span>Stop: <strong>{labelForStopModel(settings.stopModel)}</strong></span>
            <span>ATR x: <strong>{numericInput(settings.atrMultiplier) || 2.5}</strong></span>
          </div>
          <div className="opti-backtest-grid">
            {selected && (
              <BacktestCard
                symbol={selected.symbol}
                backtest={settingsBacktest?.symbol === selected.symbol ? settingsBacktest.backtest : selected.backtest}
              />
            )}
          </div>
          {selected ? (
            <div className="opti-trade-ledger">
              <div className="opti-trade-row header">
                <span>Symbol</span><span>Side</span><span>Entry</span><span>Exit</span><span>Entry Price</span><span>Exit Price</span><span>Return</span><span>Held</span><span>Reason</span>
              </div>
              {(settingsBacktest?.symbol === selected.symbol ? settingsBacktest.backtest : selected.backtest).trades.map((trade, index) => (
                <div className="opti-trade-row" key={`${selected.symbol}-${trade.entry_date}-${trade.exit_date}-${index}`}>
                  <strong>{selected.symbol}<small>{selected.underlying}</small></strong>
                  <span className={trade.direction === "BUY" ? "aligned" : "review"}>{trade.direction}</span>
                  <span>{formatDate(trade.entry_date)}</span>
                  <span>{formatDate(trade.exit_date)}</span>
                  <span>{currency(trade.entry_price)}</span>
                  <span>{currency(trade.exit_price)}</span>
                  <span className={trade.return_pct >= 0 ? "aligned" : "review"}>{percent(trade.return_pct)}</span>
                  <span>{trade.bars_held} bars</span>
                  <span>{trade.exit_reason}</span>
                </div>
              ))}
            </div>
          ) : null}
        </section>
      )}

      {view === "risk" && (
        <RiskSettings settings={settings} selected={selected} onChange={updateSetting} />
      )}

      {view === "automation" && (
        <AutomationPanel selected={selected} settings={settings} />
      )}

      <section className="dashboard-panel opti-note">
        <ShieldCheck size={18} />
        <p>
          Educational research only. OptiTrade Lab is an original FinanceOS approximation of public indicator concepts and does not place trades. Alpaca Market Data requests are held under 200 requests per minute per saved account key; each cursor/page fetch counts as one request.
        </p>
      </section>

      {result?.rate_limit && (
        <section className="dashboard-panel opti-note">
          <Gauge size={18} />
          <p>Alpaca rate budget: {result.rate_limit.remaining} / {result.rate_limit.limit_per_minute} requests remaining in the current minute. {result.rate_limit.pagination_note}</p>
        </section>
      )}

      {result?.warnings.length ? (
        <section className="dashboard-panel opti-warning">
          <AlertTriangle size={18} />
          <div>{result.warnings.map((warning) => <p key={warning}>{warning}</p>)}</div>
        </section>
      ) : null}
    </div>
  );
}

async function fetchOptiTradeSignals(source: DataSource) {
  if (source === "alpaca") {
    return apiFetch<OptiTradeResponse>(`/alpaca/optitrade-lab/signals?symbols=${DEFAULT_SYMBOLS.join(",")}`);
  }
  const response = await fetch(`${IBKR_API}/api/optitrade-lab/signals?symbols=${DEFAULT_SYMBOLS.join(",")}`, { cache: "no-store" });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `OptiTrade Lab request failed (${response.status})`);
  }
  return response.json() as Promise<OptiTradeResponse>;
}

async function fetchOptiTradeBacktest(source: DataSource, params: URLSearchParams) {
  if (source === "alpaca") {
    return apiFetch<OptiTradeBacktestResponse>(`/alpaca/optitrade-lab/backtest?${params.toString()}`);
  }
  const response = await fetch(`${IBKR_API}/api/optitrade-lab/backtest?${params.toString()}`, { cache: "no-store" });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `Backtest request failed (${response.status})`);
  }
  return response.json() as Promise<OptiTradeBacktestResponse>;
}

function dataSourceLabel(source: DataSource) {
  return source === "alpaca" ? "Alpaca" : "IBKR live";
}

function StrategyCard({ title, detail, icon, active, onClick }: { title: string; detail: string; icon: ReactNode; active: boolean; onClick: () => void }) {
  return (
    <button type="button" className={`dashboard-panel opti-strategy-card ${active ? "active" : ""}`} onClick={onClick}>
      <span>{icon}</span>
      <strong>{title}</strong>
      <p>{detail}</p>
    </button>
  );
}

function SignalWorkbench({ signal, settings, generatedAt, focus }: { signal: OptiTradeSignal; settings: OptiTradeSettings; generatedAt?: string; focus: StrategyFocus }) {
  const adjusted = adjustedLevels(signal, settings);
  const position = suggestedPosition(signal, settings);
  return (
    <section className="opti-workbench-grid">
      <div className={`dashboard-panel opti-chart-panel ${focus === "flip" ? "focus" : ""}`}>
        <div className="panel-header">
          <div>
            <h2>{signal.symbol} Signal Map</h2>
            <p className="fine-print">{signal.underlying} trend engine | {generatedAt ? formatDateTime(generatedAt) : formatDate(signal.as_of_date)}</p>
          </div>
          <span className={`opti-signal-pill ${signal.signal.toLowerCase()}`}>{signal.signal}</span>
        </div>
        <OptiTradeCandlestickChart signal={signal} />
      </div>

      <aside className={`dashboard-panel opti-level-panel ${focus === "dynamic" || focus === "multi" ? "focus" : ""}`}>
        <h2>Execution Plan</h2>
        <div className="opti-level-list">
          <Level label="Entry" value={signal.entry} active={focus === "dynamic"} />
          <Level label="Adjusted Stop" value={adjusted.stop} danger active={focus === "dynamic"} />
          {adjusted.takeProfits.map((value, index) => <Level key={value} label={`TP${index + 1}`} value={value} active={focus === "multi"} />)}
        </div>
        <div className="opti-risk-box">
          <span>Suggested shares</span>
          <strong>{position.shares.toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong>
          <small>{currency(position.dollarsAtRisk)} planned risk at {settings.riskPct || "0"}%</small>
        </div>
      </aside>
    </section>
  );
}

type OptiTradeCandlePoint = OptiTradeChartPoint & {
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

function OptiTradeCandlestickChart({ signal }: { signal: OptiTradeSignal }) {
  const rows = normalizeOptiTradeCandles(signal.chart).slice(-96);
  if (!rows.length) {
    return <div className="opti-empty-chart">No chart bars available for this signal.</div>;
  }

  const width = 920;
  const height = 390;
  const left = 58;
  const right = 66;
  const top = 18;
  const priceBottom = 262;
  const volumeTop = 298;
  const volumeBottom = 360;
  const plotWidth = width - left - right;
  const step = rows.length > 1 ? plotWidth / (rows.length - 1) : plotWidth;
  const candleWidth = Math.max(3, Math.min(9, step * 0.58));
  const levelValues = [signal.entry, signal.stop_loss, ...signal.take_profits];
  const priceValues = rows.flatMap((row) => [row.high, row.low, row.ema21, row.ema55, ...levelValues].filter(isFiniteNumber));
  const rawMin = Math.min(...priceValues);
  const rawMax = Math.max(...priceValues);
  const padding = Math.max((rawMax - rawMin) * 0.08, rawMax * 0.005);
  const minPrice = rawMin - padding;
  const maxPrice = rawMax + padding;
  const maxVolume = Math.max(...rows.map((row) => row.volume), 1);
  const latest = rows[rows.length - 1];
  const first = rows[0];
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
    <div className="opti-candle-chart-shell">
      <div className="opti-candle-chart-topline">
        <div>
          <strong>{signal.symbol} candlestick signal map</strong>
          <span>{formatShortDate(first.date)} to {formatShortDate(latest.date)} | Volume bars shown below price</span>
        </div>
        <b className={signal.signal.toLowerCase()}>{signal.signal}</b>
      </div>
      <div className="opti-chart-legend">
        <span style={{ color: "#2dd4bf" }}>Up candle</span>
        <span style={{ color: "#fb7185" }}>Down candle</span>
        <span style={{ color: "#38bdf8" }}>EMA 21</span>
        <span style={{ color: "#94a3b8" }}>EMA 55</span>
        <span style={{ color: "#facc15" }}>Entry</span>
        <span style={{ color: "#fb7185" }}>Stop</span>
        <span style={{ color: "#22c55e" }}>Targets</span>
      </div>
      <svg className="opti-candle-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${signal.symbol} candlestick chart with volume and OptiTrade levels`}>
        <rect x={left} y={top} width={plotWidth} height={priceBottom - top} rx="8" fill="rgba(9, 24, 21, 0.72)" stroke="#17352d" />
        <rect x={left} y={volumeTop} width={plotWidth} height={volumeBottom - volumeTop} rx="8" fill="rgba(9, 24, 21, 0.72)" stroke="#17352d" />

        {priceTicks.map((tick) => (
          <g key={tick}>
            <line x1={left} x2={left + plotWidth} y1={y(tick)} y2={y(tick)} stroke="#17352d" strokeDasharray="3 4" />
            <text x={width - 8} y={y(tick) + 4} textAnchor="end" className="opti-candle-axis-text">{compactCurrency(tick)}</text>
          </g>
        ))}

        {dateTickIndexes.map((index) => (
          <text key={`${rows[index].date}-${index}`} x={x(index)} y={height - 10} textAnchor={index === 0 ? "start" : index === rows.length - 1 ? "end" : "middle"} className="opti-candle-axis-text">
            {formatShortDate(rows[index].date)}
          </text>
        ))}

        <text x={left - 12} y={volumeTop + 14} textAnchor="end" className="opti-candle-axis-text">Vol</text>
        <text x={width - 8} y={volumeTop + 14} textAnchor="end" className="opti-candle-axis-text">{compactNumber(maxVolume)}</text>

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
              <title>{`${row.date} O ${currency(row.open)} H ${currency(row.high)} L ${currency(row.low)} C ${currency(row.close)} Vol ${compactNumber(row.volume)}`}</title>
              <rect x={center - candleWidth / 2} y={volumeTopY} width={Math.max(2, candleWidth)} height={Math.max(1, volumeBottom - volumeTopY)} fill={fill} opacity="0.34" rx="1.5" />
              <line x1={center} x2={center} y1={y(row.high)} y2={y(row.low)} stroke={fill} strokeWidth="1.2" />
              <rect x={center - candleWidth / 2} y={bodyTop} width={candleWidth} height={bodyHeight} fill={fill} stroke={fill} strokeWidth="0.8" rx="1.5" />
            </g>
          );
        })}

        <path d={optiLinePath(rows, "ema55", x, y)} fill="none" stroke="#94a3b8" strokeWidth="1.4" />
        <path d={optiLinePath(rows, "ema21", x, y)} fill="none" stroke="#38bdf8" strokeWidth="1.5" />

        <g>
          <line x1={left} x2={left + plotWidth} y1={y(signal.entry)} y2={y(signal.entry)} stroke="#facc15" strokeDasharray="5 4" strokeWidth="1.4" />
          <text x={width - 8} y={y(signal.entry) - 6} textAnchor="end" fill="#facc15" fontSize="11" fontWeight="760">Entry {currency(signal.entry)}</text>
        </g>
        <g>
          <line x1={left} x2={left + plotWidth} y1={y(signal.stop_loss)} y2={y(signal.stop_loss)} stroke="#fb7185" strokeDasharray="5 4" strokeWidth="1.5" />
          <text x={width - 8} y={y(signal.stop_loss) + 14} textAnchor="end" fill="#fb7185" fontSize="11" fontWeight="760">SL {currency(signal.stop_loss)}</text>
        </g>
        {signal.take_profits.map((value, index) => (
          <g key={value}>
            <line x1={left} x2={left + plotWidth} y1={y(value)} y2={y(value)} stroke="#22c55e" strokeDasharray="4 5" strokeWidth="1.2" opacity="0.82" />
            <text x={left + 8} y={y(value) - 5} fill="#22c55e" fontSize="10" fontWeight="740">TP{index + 1}</text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function Level({ label, value, danger = false, active = false }: { label: string; value: number; danger?: boolean; active?: boolean }) {
  return <div className={`${danger ? "danger" : ""} ${active ? "active" : ""}`}><span>{label}</span><strong>{currency(value)}</strong></div>;
}

function BacktestCard({ symbol, backtest }: { symbol: string; backtest: OptiTradeBacktest }) {
  return (
    <article className="opti-backtest-card">
      <div>
        <span>{symbol}</span>
        <strong>{backtest.period}</strong>
      </div>
      <dl>
        <div><dt>Win rate</dt><dd>{backtest.win_rate.toFixed(1)}%</dd></div>
        <div><dt>Profit factor</dt><dd>{backtest.profit_factor.toFixed(2)}</dd></div>
        <div><dt>Max DD</dt><dd>{backtest.max_drawdown.toFixed(1)}%</dd></div>
        <div><dt>Trades</dt><dd>{backtest.total_trades}</dd></div>
        <div><dt>Avg trade</dt><dd>{percent(backtest.avg_trade)}</dd></div>
      </dl>
    </article>
  );
}

function RiskSettings({ settings, selected, onChange }: { settings: OptiTradeSettings; selected: OptiTradeSignal | null; onChange: (field: keyof OptiTradeSettings, value: string) => void }) {
  const position = selected ? suggestedPosition(selected, settings) : null;
  return (
    <section className="dashboard-panel opti-risk-settings">
      <div className="panel-header">
        <div>
          <h2>Risk Settings</h2>
          <p className="fine-print">Saved locally and used to size the simulated signal plan.</p>
        </div>
        <SlidersHorizontal size={18} />
      </div>
      <div className="opti-settings-grid">
        <Field label="Account size" value={settings.accountSize} onChange={(value) => onChange("accountSize", value)} prefix="$" />
        <Field label="Risk per trade" value={settings.riskPct} onChange={(value) => onChange("riskPct", value)} suffix="%" />
        <Field label="ATR multiplier" value={settings.atrMultiplier} onChange={(value) => onChange("atrMultiplier", value)} />
        <Field label="Max drawdown guard" value={settings.maxDrawdownGuard} onChange={(value) => onChange("maxDrawdownGuard", value)} suffix="%" />
        <label className="opti-field">
          <span>TP mode</span>
          <select value={settings.tpMode} onChange={(event) => onChange("tpMode", event.target.value)}>
            <option value="single">Single TP</option>
            <option value="multi">Multi TP</option>
            <option value="always_in">Always In Trade</option>
          </select>
        </label>
        <label className="opti-field">
          <span>Stop model</span>
          <select value={settings.stopModel} onChange={(event) => onChange("stopModel", event.target.value)}>
            <option value="atr">ATR Stop</option>
            <option value="swing">Swing Stop</option>
          </select>
        </label>
      </div>
      {selected && position && (
        <div className="opti-risk-preview">
          <span>Selected plan</span>
          <strong>{selected.symbol}: {position.shares.toLocaleString(undefined, { maximumFractionDigits: 2 })} shares</strong>
          <p>{currency(position.dollarsAtRisk)} risk budget using the adjusted stop model.</p>
        </div>
      )}
    </section>
  );
}

function Field({ label, value, onChange, prefix, suffix }: { label: string; value: string; onChange: (value: string) => void; prefix?: string; suffix?: string }) {
  return (
    <label className="opti-field">
      <span>{label}</span>
      <div>
        {prefix && <small>{prefix}</small>}
        <input value={value} inputMode="decimal" onChange={(event) => onChange(event.target.value)} />
        {suffix && <small>{suffix}</small>}
      </div>
    </label>
  );
}

function AutomationPanel({ selected, settings }: { selected: OptiTradeSignal | null; settings: OptiTradeSettings }) {
  return (
    <section className="dashboard-panel opti-automation-panel">
      <div className="panel-header">
        <div>
          <h2>Automation Mode</h2>
          <p className="fine-print">Alert planning only. FinanceOS does not place broker orders from this tab.</p>
        </div>
        <Bell size={18} />
      </div>
      <div className="opti-automation-grid">
        <AutomationStep title="Signal trigger" detail={selected ? `${selected.symbol} ${selected.signal} when trend and momentum agree.` : "Load a signal to populate automation rules."} active={Boolean(selected)} />
        <AutomationStep title="Risk gate" detail={`Block new alerts if drawdown exceeds ${settings.maxDrawdownGuard || "0"}%.`} active />
        <AutomationStep title="Exit routing" detail={`${settings.tpMode === "multi" ? "Stage exits across TP1-TP4." : settings.tpMode === "always_in" ? "Flip on opposite signal." : "Exit at the first active target."} ${labelForStopModel(settings.stopModel)} protects the downside.`} active />
        <AutomationStep title="Human review" detail="Send alert details for manual confirmation before any trade." active />
      </div>
    </section>
  );
}

function AutomationStep({ title, detail, active }: { title: string; detail: string; active: boolean }) {
  return (
    <article className={active ? "active" : ""}>
      {active ? <CheckCircle2 size={16} /> : <Bot size={16} />}
      <strong>{title}</strong>
      <p>{detail}</p>
    </article>
  );
}

function adjustedLevels(signal: OptiTradeSignal, settings: OptiTradeSettings) {
  const multiplier = numericInput(settings.atrMultiplier) || 2.5;
  const baseRisk = Math.abs(signal.entry - signal.stop_loss) || signal.entry * 0.03;
  const risk = baseRisk * (multiplier / 2.5);
  const direction = signal.signal === "SELL" ? -1 : 1;
  return {
    stop: signal.entry - direction * risk,
    takeProfits: [1, 2, 3, 4].map((multiple) => signal.entry + direction * risk * multiple),
  };
}

function suggestedPosition(signal: OptiTradeSignal, settings: OptiTradeSettings) {
  const account = numericInput(settings.accountSize);
  const riskPct = numericInput(settings.riskPct);
  const adjusted = adjustedLevels(signal, settings);
  const perShareRisk = Math.abs(signal.entry - adjusted.stop);
  const dollarsAtRisk = account * (riskPct / 100);
  return {
    dollarsAtRisk,
    shares: perShareRisk > 0 ? dollarsAtRisk / perShareRisk : 0,
  };
}

function loadSettings(): OptiTradeSettings {
  if (typeof window === "undefined") return defaultSettings();
  const saved = window.localStorage.getItem(SETTINGS_KEY);
  if (!saved) return defaultSettings();
  try {
    return { ...defaultSettings(), ...JSON.parse(saved) };
  } catch {
    window.localStorage.removeItem(SETTINGS_KEY);
    return defaultSettings();
  }
}

function defaultSettings(): OptiTradeSettings {
  return {
    accountSize: "100000",
    riskPct: "1",
    atrMultiplier: "2.5",
    tpMode: "multi",
    stopModel: "atr",
    maxDrawdownGuard: "12",
  };
}

function numericInput(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function normalizeOptiTradeCandles(points: OptiTradeChartPoint[]): OptiTradeCandlePoint[] {
  return points.map((point) => {
    const close = numberOr(point.close, 0);
    const open = numberOr(point.open, close);
    const high = Math.max(numberOr(point.high, Math.max(open, close)), open, close);
    const low = Math.min(numberOr(point.low, Math.min(open, close)), open, close);
    return { ...point, open, high, low, close, volume: Math.max(0, numberOr(point.volume, 0)) };
  }).filter((point) => point.close > 0);
}

function optiLinePath(rows: OptiTradeCandlePoint[], key: "ema21" | "ema55", x: (index: number) => number, y: (value: number) => number) {
  let output = "";
  let drawing = false;
  rows.forEach((row, index) => {
    const value = row[key];
    if (!isFiniteNumber(value)) {
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

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function currency(value: number) {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`;
}

function percent(value: number) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function formatDate(value: string) {
  const parsed = new Date(`${value}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function formatShortDate(value: string) {
  const parsed = new Date(`${value}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
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

function labelForTpMode(mode: TpMode) {
  if (mode === "single") return "Single TP";
  if (mode === "always_in") return "Always In Trade";
  return "Multi TP";
}

function labelForStopModel(model: StopModel) {
  return model === "swing" ? "Swing Stop" : "ATR Stop";
}
