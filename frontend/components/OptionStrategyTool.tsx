"use client";

import {
  Activity,
  AlertTriangle,
  Bell,
  CheckCircle2,
  CircleDollarSign,
  Gauge,
  LineChart as LineChartIcon,
  Loader2,
  Play,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
  Target,
  XCircle
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Area,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import {
  MarketHistory,
  MarketPriceBar,
  OptionStrategyAlertEvent,
  OptionStrategyConfig,
  OptionStrategyScanResult,
  OptionStrategySignalCandidate,
  OptionStrategyUniverse,
  OptionStrategyUniverseItem,
  OptionStrategyWheelPosition,
  apiFetch,
  currency,
  optionStrategyFetch,
  percent
} from "@/lib/api";

const fallbackUniverse: OptionStrategyUniverseItem[] = [
  { symbol: "NVDA", name: "NVIDIA Corp", sector: "Information Technology", group: "S&P 500 top 30" },
  { symbol: "AAPL", name: "Apple Inc", sector: "Information Technology", group: "S&P 500 top 30" },
  { symbol: "MSFT", name: "Microsoft Corp", sector: "Information Technology", group: "S&P 500 top 30" },
  { symbol: "AMZN", name: "Amazon.com Inc", sector: "Consumer Discretionary", group: "S&P 500 top 30" },
  { symbol: "GOOGL", name: "Alphabet Inc", sector: "Communication Services", group: "S&P 500 top 30" },
  { symbol: "AVGO", name: "Broadcom Inc", sector: "Information Technology", group: "S&P 500 top 30" },
  { symbol: "META", name: "Meta Platforms Inc", sector: "Communication Services", group: "S&P 500 top 30" },
  { symbol: "TSLA", name: "Tesla Inc", sector: "Consumer Discretionary", group: "S&P 500 top 30" },
  { symbol: "QQQ", name: "Invesco QQQ Trust", sector: "ETF", group: "Core ETFs" },
  { symbol: "SPY", name: "SPDR S&P 500 ETF Trust", sector: "ETF", group: "Core ETFs" },
  { symbol: "SMH", name: "VanEck Semiconductor ETF", sector: "ETF", group: "Core ETFs" },
  { symbol: "XLE", name: "Energy Select Sector SPDR Fund", sector: "ETF", group: "Core ETFs" },
  { symbol: "XLI", name: "Industrial Select Sector SPDR Fund", sector: "ETF", group: "Core ETFs" },
  { symbol: "UPRO", name: "ProShares UltraPro S&P500", sector: "Leveraged ETF", group: "Leveraged ETFs" },
  { symbol: "TQQQ", name: "ProShares UltraPro QQQ", sector: "Leveraged ETF", group: "Leveraged ETFs" },
  { symbol: "SOXL", name: "Direxion Daily Semiconductor Bull 3X Shares", sector: "Leveraged ETF", group: "Leveraged ETFs" }
];

const demoConfig: OptionStrategyConfig = {
  tickers: fallbackUniverse.map((item) => item.symbol),
  universe_groups: ["sp500_top_30", "nasdaq_top_30", "core_etfs", "leveraged_etfs"],
  scan_cadence: "daily",
  account_value: 500000,
  exposure_cap: 0.3,
  dte_min: 30,
  dte_max: 45,
  rsi_period: 14,
  rsi_max: 65,
  ema_periods: [8, 21, 34, 55],
  min_iv: 0.15,
  min_iv_rank: 0.4,
  min_premium_yield: 0.05,
  target_delta_min: 0.2,
  target_delta_max: 0.35,
  bb_percent_max: 0.75,
  earnings_exclusion_days: 7,
  min_open_interest: 100,
  max_spread_pct: 0.15,
  profit_take_pct: 0.5,
  single_name_cap: 0.1,
  sector_cap: 0.25,
  webhook_url: null,
  updated_at: new Date().toISOString()
};

const marketHistoryCache = new Map<string, Promise<MarketHistory>>();

type ChartRow = {
  date: string;
  close: number;
  ema8: number | null;
  ema21: number | null;
  ema34: number | null;
  ema55: number | null;
  rsi: number | null;
  signal: number | null;
  emaGreen: boolean;
};

type RegimeArea = {
  start: string;
  end: string;
  green: boolean;
};

type OpportunityRow = {
  id: string;
  symbol: string;
  dte: number;
  premium_yield: number;
  iv: number;
  delta: number;
  bid: number;
  ask: number;
  mid: number;
  open_interest: number;
  status: string;
  strike: number;
  expiration: string;
};

export function OptionStrategyTool() {
  const bootstrappedRef = useRef(false);
  const [selectedSymbol, setSelectedSymbol] = useState("SPY");
  const [universe, setUniverse] = useState<OptionStrategyUniverseItem[]>(fallbackUniverse);
  const [histories, setHistories] = useState<Record<string, MarketHistory>>({});
  const [config, setConfig] = useState<OptionStrategyConfig>(demoConfig);
  const [signals, setSignals] = useState<OptionStrategySignalCandidate[]>(() => buildDemoSignals({}));
  const [positions, setPositions] = useState<OptionStrategyWheelPosition[]>(() => buildDemoPositions());
  const [alerts, setAlerts] = useState<OptionStrategyAlertEvent[]>(() => buildDemoAlerts());
  const [selectedSignalId, setSelectedSignalId] = useState<string | null>(null);
  const [apiAvailable, setApiAvailable] = useState(false);
  const [lastScanAt, setLastScanAt] = useState<string>(new Date().toISOString());
  const [loading, setLoading] = useState("");
  const [statusMessage, setStatusMessage] = useState("");

  useEffect(() => {
    if (bootstrappedRef.current) return;
    bootstrappedRef.current = true;
    void loadWorkspace(false);
  }, []);

  useEffect(() => {
    if (!selectedSymbol || histories[selectedSymbol]) return;
    void loadSymbolHistory(selectedSymbol, false);
  }, [histories, selectedSymbol]);

  useEffect(() => {
    const current = signals.find((signal) => signalKey(signal) === selectedSignalId);
    if (current?.symbol === selectedSymbol) return;
    const next = signals.find((signal) => signal.symbol === selectedSymbol) ?? signals[0] ?? null;
    setSelectedSignalId(next ? signalKey(next) : null);
  }, [selectedSignalId, selectedSymbol, signals]);

  const selectedSignal = useMemo(
    () => signals.find((signal) => signalKey(signal) === selectedSignalId) ?? signals.find((signal) => signal.symbol === selectedSymbol) ?? signals[0] ?? null,
    [selectedSignalId, selectedSymbol, signals]
  );

  const chartRows = useMemo(() => buildChartRows(histories[selectedSymbol], selectedSymbol, selectedSignal), [histories, selectedSignal, selectedSymbol]);
  const latestRow = chartRows.at(-1) ?? null;
  const priorRow = chartRows.at(-2) ?? null;
  const regimeAreas = useMemo(() => buildRegimeAreas(chartRows), [chartRows]);
  const opportunityRows = useMemo(() => buildOpportunityRows(selectedSymbol, signals, apiAvailable), [apiAvailable, selectedSymbol, signals]);
  const approvedSignals = signals.filter((signal) => isApproved(signal.status));
  const deepDiveSignals = signals
    .filter((signal) => signal.deep_dive_rank != null)
    .sort((a, b) => Number(a.deep_dive_rank ?? 999) - Number(b.deep_dive_rank ?? 999))
    .slice(0, 5);
  const selectedTickerSignals = signals.filter((signal) => signal.symbol === selectedSymbol);
  const selectedUniverseItem = universe.find((item) => item.symbol === selectedSymbol);
  const latestRsi = latestRow?.rsi ?? 0;
  const latestClose = latestRow?.close ?? selectedSignal?.underlying_price ?? 0;
  const isRedDay = Boolean(latestRow && priorRow && latestRow.close < priorRow.close);
  const exposureUsage = selectedSignal?.exposure_usage ?? (selectedSignal && config.account_value > 0 ? selectedSignal.collateral / config.account_value : 0);
  const windowReturn = chartRows.length > 1 && chartRows[0].close > 0 ? (latestClose / chartRows[0].close) - 1 : 0;
  const maxDrawdownValue = maxDrawdown(chartRows.map((row) => row.close));
  const selectedProvider = selectedSignal?.provider?.toLowerCase() ?? "";
  const providerLabel = !apiAvailable
    ? "Fallback data"
    : selectedProvider.includes("yfinance") && !selectedProvider.includes("fallback")
      ? "Live option-chain scan"
      : selectedProvider
        ? "Fallback/estimated scan"
        : "Saved scan";

  async function loadWorkspace(runScan: boolean, refreshHistory = false) {
    setLoading(refreshHistory ? "history" : runScan ? "scan" : "bootstrap");
    setStatusMessage("");
    const apiData = await fetchOptionStrategyData(runScan);
    if (apiData.ok) {
      const nextSelectedSymbol = apiData.signals[0]?.symbol ?? selectedSymbol;
      setApiAvailable(true);
      setConfig(apiData.config);
      setSignals(apiData.signals);
      setPositions(apiData.positions);
      setAlerts(apiData.alerts);
      setUniverse(apiData.universe.items.length ? apiData.universe.items : fallbackUniverse);
      setSelectedSymbol(nextSelectedSymbol);
      setLastScanAt(apiData.scannedAt);
      await loadSymbolHistory(nextSelectedSymbol, refreshHistory);
      setStatusMessage(refreshHistory ? "Historical price history refreshed." : runScan ? "Daily wheel scan complete." : "");
    } else {
      const nextHistory = await fetchCachedMarketHistory(selectedSymbol, marketStartDate(), marketEndDate(), refreshHistory);
      setApiAvailable(false);
      setConfig(demoConfig);
      setUniverse(fallbackUniverse);
      setSignals(buildDemoSignals({ [selectedSymbol]: nextHistory }));
      setPositions(buildDemoPositions());
      setAlerts(buildDemoAlerts());
      setLastScanAt(new Date().toISOString());
      setStatusMessage(refreshHistory ? "Historical price data refreshed. Demo signals remain active until the Wheel Strategy backend is connected." : apiData.message);
      setHistories((current) => ({ ...current, [selectedSymbol]: nextHistory }));
    }
    setLoading("");
  }

  async function loadSymbolHistory(symbol: string, forceRefresh: boolean) {
    const history = await fetchCachedMarketHistory(symbol, marketStartDate(), marketEndDate(), forceRefresh);
    setHistories((current) => ({ ...current, [symbol]: history }));
  }

  async function recordSelectedSignal() {
    if (!apiAvailable || !selectedSignal) return;
    setLoading("position");
    setStatusMessage("");
    try {
      await optionStrategyFetch<OptionStrategyWheelPosition>("/positions", {
        method: "POST",
        body: JSON.stringify({ event: "accepted_put", signal_candidate_id: selectedSignal.id, candidate: selectedSignal })
      });
      await loadWorkspace(false);
      setStatusMessage("Accepted trade recorded.");
    } catch (err) {
      setStatusMessage(err instanceof Error ? err.message : "Could not record accepted trade.");
      setLoading("");
    }
  }

  async function markAssigned(position: OptionStrategyWheelPosition) {
    if (!apiAvailable) return;
    setLoading(`assign-${position.id ?? position.symbol}`);
    setStatusMessage("");
    try {
      await optionStrategyFetch<OptionStrategyWheelPosition>("/positions", {
        method: "POST",
        body: JSON.stringify({ event: "assigned", position_id: position.id, position })
      });
      await loadWorkspace(false);
      setStatusMessage("Assignment recorded.");
    } catch (err) {
      setStatusMessage(err instanceof Error ? err.message : "Could not mark assignment.");
      setLoading("");
    }
  }

  return (
    <>
      <section className="dashboard-panel option-strategy-head">
        <div>
          <p className="eyebrow">Wheel Strategy</p>
          <h2>Daily wheel strategy cockpit.</h2>
          <div className="option-strategy-meta-line">
            <span>{selectedSymbol} · {selectedUniverseItem?.name ?? "Research candidate"}</span>
            <span>{providerLabel}</span>
            <span>Last scan {formatDateTime(lastScanAt)}</span>
            <span>{config.dte_min}-{config.dte_max} DTE</span>
            <span>{universe.length} symbols</span>
          </div>
        </div>
        <div className="option-strategy-actions">
          <button className="secondary-button" type="button" onClick={() => loadWorkspace(false, true)} disabled={loading === "history"}>
            {loading === "history" ? <Loader2 size={16} className="spin-icon" /> : <RefreshCw size={16} />}
            Refresh 1Y data
          </button>
          <button className="primary-button" type="button" onClick={() => loadWorkspace(true)} disabled={loading === "scan"}>
            {loading === "scan" ? <Loader2 size={16} className="spin-icon" /> : <Play size={16} />}
            Run daily scan
          </button>
        </div>
      </section>

      {!apiAvailable && (
        <section className="dashboard-panel option-demo-banner">
          <AlertTriangle size={18} />
          <div>
            <strong>Demo mode: simulated wheel signals</strong>
            <p>Signals, positions, and alerts are sample data until the `/option-strategy` backend responds. Live mode uses yfinance option chains; fallback estimates are clearly labeled for manual review.</p>
          </div>
        </section>
      )}

      {statusMessage && (
        <section className="dashboard-panel option-strategy-notice">
          <ShieldCheck size={18} />
          <p>{statusMessage}</p>
        </section>
      )}

      <section className="dashboard-panel option-strategy-controls">
        <div className="option-ticker-strip" role="tablist" aria-label="Option strategy tickers">
          {universe.map((item) => (
            <button
              key={item.symbol}
              type="button"
              className={selectedSymbol === item.symbol ? "active" : ""}
              onClick={() => setSelectedSymbol(item.symbol)}
            >
              <strong>{item.symbol}</strong>
              <span>{item.group}</span>
            </button>
          ))}
        </div>
      </section>

      <div className="stat-grid option-strategy-stat-grid">
        <article className="stat-panel"><CheckCircle2 size={20} /><h3>Approved</h3><strong>{approvedSignals.length}</strong><p>{signals.length} contracts scanned.</p></article>
        <article className="stat-panel"><LineChartIcon size={20} /><h3>Latest close</h3><strong>{currencyCents(latestClose)}</strong><p>{isRedDay ? "Red daily candle" : "Green daily candle"}.</p></article>
        <article className="stat-panel"><Gauge size={20} /><h3>RSI 14</h3><strong>{latestRsi ? latestRsi.toFixed(1) : "N/A"}</strong><p>{latestRsi && latestRsi < config.rsi_max ? "Below entry ceiling." : "Above entry ceiling."}</p></article>
        <article className="stat-panel"><Activity size={20} /><h3>EMA cloud</h3><strong>{latestRow?.emaGreen ? "Green" : "Red"}</strong><p>8/21 and 34/55 trend check.</p></article>
        <article className="stat-panel"><CircleDollarSign size={20} /><h3>Candidate yield</h3><strong>{selectedSignal ? percent(selectedSignal.premium_yield) : "N/A"}</strong><p>{selectedSignal ? `${selectedSignal.dte} DTE ${formatAction(selectedSignal.action)}` : "No candidate selected"}.</p></article>
        <article className="stat-panel"><Target size={20} /><h3>50% alert</h3><strong>{selectedSignal ? currencyCents(selectedSignal.alert_target_price) : "N/A"}</strong><p>{percent(exposureUsage)} exposure usage.</p></article>
      </div>

      <section className="dashboard-panel option-deep-dive-panel">
        <div className="panel-header">
          <div>
            <h2>Deep Dive Summary</h2>
            <p className="fine-print">Research priorities only. Verify business quality, earnings, liquidity, and assignment comfort before any decision.</p>
          </div>
          <span className="status-pill">{deepDiveSignals.length || 0} {deepDiveSignals.length === 1 ? "priority" : "priorities"}</span>
        </div>
        <div className="option-deep-dive-grid">
          {deepDiveSignals.length ? deepDiveSignals.map((signal) => (
            <button
              type="button"
              className={`option-deep-dive-card ${selectedSignal && signalKey(selectedSignal) === signalKey(signal) ? "active" : ""}`}
              key={`deep-${signalKey(signal)}`}
              onClick={() => {
                setSelectedSymbol(signal.symbol);
                setSelectedSignalId(signalKey(signal));
              }}
            >
              <span>#{signal.deep_dive_rank ?? "-"} · {signal.sector ?? "Unknown"}</span>
              <strong>{signal.symbol}</strong>
              <p>{signal.deep_dive_summary ?? "Review the candidate checklist and option-chain liquidity before acting."}</p>
              <div>
                <small>{percent(signal.premium_yield)} yield</small>
                <small>{signal.iv_rank != null ? `${percent(signal.iv_rank)} IV rank` : "IV rank N/A"}</small>
                <small>{currencyCents(signal.if_assigned_basis ?? signal.strike)} basis</small>
              </div>
            </button>
          )) : <p className="fine-print">Run the daily scan to populate research priorities.</p>}
        </div>
      </section>

      <section className="dashboard-panel option-terminal-panel">
        <div className="option-terminal-head">
          <div>
            <span>{apiAvailable ? "Provider history" : "Cached provider history with demo signals"}</span>
            <h2>{selectedSymbol} adjusted close with EMA cloud</h2>
            <strong>{chartRows[0] ? `${formatDate(chartRows[0].date)} - ${formatDate(chartRows.at(-1)?.date ?? "")}` : "No chart data"}</strong>
          </div>
          <div className={`option-terminal-return ${windowReturn >= 0 ? "positive" : "negative"}`}>
            <span>Window return</span>
            <strong>{percent(windowReturn)}</strong>
          </div>
        </div>
        {!apiAvailable && <div className="option-demo-watermark">DEMO SIGNALS</div>}
        <div className="option-terminal-stats">
          <div><span>Bars</span><strong>{chartRows.length.toLocaleString()}</strong></div>
          <div><span>Max drawdown</span><strong>{percent(maxDrawdownValue)}</strong></div>
          <div><span>Red day</span><strong>{isRedDay ? "Yes" : "No"}</strong></div>
          <div><span>Signals</span><strong>{selectedTickerSignals.length}</strong></div>
        </div>
        <ResponsiveContainer width="100%" height={430}>
          <ComposedChart data={chartRows} margin={{ left: 4, right: 18, top: 12, bottom: 8 }}>
            <defs>
              <linearGradient id={`optionClose-${selectedSymbol}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6ee7b7" stopOpacity={0.42} />
                <stop offset="95%" stopColor="#6ee7b7" stopOpacity={0.03} />
              </linearGradient>
            </defs>
            {regimeAreas.map((area) => (
              <ReferenceArea
                key={`${area.start}-${area.end}-${area.green ? "green" : "red"}`}
                x1={area.start}
                x2={area.end}
                fill={area.green ? "#064e3b" : "#7f1d1d"}
                fillOpacity={0.13}
                ifOverflow="extendDomain"
              />
            ))}
            <CartesianGrid stroke="#19352d" strokeDasharray="3 3" />
            <XAxis
              dataKey="date"
              minTickGap={42}
              tickFormatter={formatMonthDay}
              tick={{ fontSize: 11, fill: "#8da99e" }}
              axisLine={{ stroke: "#24463c" }}
              tickLine={{ stroke: "#24463c" }}
            />
            <YAxis
              width={66}
              tickFormatter={(value) => compactCurrency(Number(value))}
              tick={{ fontSize: 11, fill: "#8da99e" }}
              axisLine={{ stroke: "#24463c" }}
              tickLine={{ stroke: "#24463c" }}
            />
            <Tooltip content={<OptionChartTooltip signalStatus={selectedSignal?.status ?? "none"} />} />
            <Legend wrapperStyle={{ color: "#b6d9cb", fontSize: 12 }} />
            <Area type="monotone" dataKey="close" name="close" stroke="#6ee7b7" fill={`url(#optionClose-${selectedSymbol})`} fillOpacity={1} strokeWidth={2.8} dot={false} activeDot={{ r: 4, fill: "#d8fff1" }} />
            <Line type="monotone" dataKey="ema8" name="ema8" stroke="#38bdf8" strokeWidth={1.55} dot={false} connectNulls />
            <Line type="monotone" dataKey="ema21" name="ema21" stroke="#60a5fa" strokeWidth={1.55} dot={false} connectNulls />
            <Line type="monotone" dataKey="ema34" name="ema34" stroke="#f59e0b" strokeWidth={1.55} dot={false} connectNulls />
            <Line type="monotone" dataKey="ema55" name="ema55" stroke="#c084fc" strokeWidth={1.55} dot={false} connectNulls />
            <Line type="monotone" dataKey="signal" name="signal" stroke="transparent" strokeWidth={0} dot={{ r: 5, fill: "#f8fafc", stroke: "#22c55e", strokeWidth: 2 }} activeDot={{ r: 7 }} />
          </ComposedChart>
        </ResponsiveContainer>
      </section>

      <div className="option-chart-grid">
        <section className="dashboard-panel option-mini-chart">
          <div className="panel-header">
            <h2>RSI 14</h2>
            <Gauge size={18} />
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={chartRows} margin={{ left: 2, right: 14, top: 8, bottom: 4 }}>
              <CartesianGrid stroke="#d7e2dc" strokeDasharray="3 3" />
              <XAxis dataKey="date" minTickGap={42} tickFormatter={formatMonthDay} tick={{ fontSize: 11, fill: "#51645b" }} />
              <YAxis width={44} domain={[0, 100]} tick={{ fontSize: 11, fill: "#51645b" }} />
              <ReferenceLine y={30} stroke="#22c55e" strokeDasharray="4 4" />
              <ReferenceLine y={50} stroke="#f59e0b" strokeDasharray="4 4" />
              <ReferenceLine y={70} stroke="#fb7185" strokeDasharray="4 4" />
              <Tooltip formatter={(value) => [Number(value).toFixed(1), "RSI"]} labelFormatter={(label) => formatDate(String(label))} contentStyle={{ border: "1px solid #d7e2dc", borderRadius: 8 }} />
              <Line type="monotone" dataKey="rsi" stroke="#0f766e" strokeWidth={2.4} dot={false} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        </section>

        <section className="dashboard-panel option-mini-chart">
          <div className="panel-header">
            <h2>Options opportunity</h2>
            <SlidersHorizontal size={18} />
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <ScatterChart margin={{ left: 2, right: 18, top: 10, bottom: 8 }}>
              <CartesianGrid stroke="#d7e2dc" strokeDasharray="3 3" />
              <XAxis type="number" dataKey="dte" name="DTE" domain={[24, 36]} tick={{ fontSize: 11, fill: "#51645b" }} />
              <YAxis type="number" dataKey="premium_yield" name="Yield" tickFormatter={(value) => percent(Number(value))} tick={{ fontSize: 11, fill: "#51645b" }} />
              <Tooltip content={<OpportunityTooltip />} cursor={{ stroke: "#94a3b8", strokeDasharray: "3 3" }} />
              <Scatter data={opportunityRows} name="Contracts">
                {opportunityRows.map((row) => (
                  <Cell key={row.id} fill={isApproved(row.status) ? "#0f766e" : "#e11d48"} />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </section>
      </div>

      <section className="dashboard-panel option-signal-table-panel">
        <div className="panel-header">
          <h2>Signal candidates</h2>
          <span className={apiAvailable ? "status-pill" : "risk-pill"}>{apiAvailable ? "API data" : "Demo signals"}</span>
        </div>
        <div className="option-signal-table">
          <div className="option-signal-row option-signal-header">
            <span>Symbol</span>
            <span>Status</span>
            <span>Strike</span>
            <span>DTE</span>
            <span>Delta</span>
            <span>IV rank</span>
            <span>Yield</span>
            <span>Score</span>
            <span>50% target</span>
            <span>Review notes</span>
          </div>
          {signals.map((signal) => (
            <button
              type="button"
              key={signalKey(signal)}
              className={`option-signal-row ${selectedSignal && signalKey(selectedSignal) === signalKey(signal) ? "active" : ""}`}
              onClick={() => {
                setSelectedSymbol(signal.symbol);
                setSelectedSignalId(signalKey(signal));
              }}
            >
              <span><strong>{signal.symbol}</strong><small>{signal.sector ?? formatAction(signal.action)}</small></span>
              <span className={`option-status ${isApproved(signal.status) ? "approved" : "blocked"}`}>{signal.status}</span>
              <span>{currencyCents(signal.strike)}</span>
              <span>{signal.dte}</span>
              <span>{signal.delta.toFixed(2)}</span>
              <span>{signal.iv_rank != null ? percent(signal.iv_rank) : percent(signal.iv)}</span>
              <span>{percent(signal.premium_yield)}</span>
              <span>{signal.score?.toFixed(1) ?? "N/A"}</span>
              <span>{currencyCents(signal.alert_target_price)}</span>
              <span>{signal.blocked_reasons.length ? signal.blocked_reasons.join(", ") : signal.deep_dive_summary ?? "Review candidate manually"}</span>
            </button>
          ))}
        </div>
      </section>

      <div className="option-detail-grid">
        <section className="dashboard-panel option-checklist-panel">
          <div className="panel-header">
            <h2>{selectedSignal ? `${selectedSignal.symbol} checklist` : "Checklist"}</h2>
            {selectedSignal ? <span className={`option-status ${isApproved(selectedSignal.status) ? "approved" : "blocked"}`}>{selectedSignal.status}</span> : <AlertTriangle size={18} />}
          </div>
          {selectedSignal ? (
            <>
              <div className="option-checklist">
                {selectedSignal.checklist.map((item) => (
                  <div className={`option-check-row ${item.passed ? "passed" : "failed"}`} key={item.id}>
                    {item.passed ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
                    <div>
                      <strong>{item.label}</strong>
                      <span>{item.detail ?? `${String(item.actual ?? "N/A")} / ${String(item.expected ?? "N/A")}`}</span>
                    </div>
                  </div>
                ))}
              </div>
              {selectedSignal.blocked_reasons.length > 0 && (
                <div className="option-blocked-reasons">
                  {selectedSignal.blocked_reasons.map((reason) => <span key={reason}>{reason}</span>)}
                </div>
              )}
              {apiAvailable && isApproved(selectedSignal.status) && (
                <button className="secondary-button" type="button" onClick={recordSelectedSignal} disabled={loading === "position"}>
                  {loading === "position" ? <Loader2 size={16} className="spin-icon" /> : <CheckCircle2 size={16} />}
                  Record accepted trade
                </button>
              )}
            </>
          ) : <p className="fine-print">No signal selected.</p>}
        </section>

        <section className="dashboard-panel option-lifecycle-panel">
          <div className="panel-header">
            <h2>Positions and alerts</h2>
            <Bell size={18} />
          </div>
          <div className="option-lifecycle-grid">
            <div className="option-lifecycle-list">
              <h3>Active wheel positions</h3>
              {positions.length ? positions.map((position) => (
                <article className="option-lifecycle-card" key={`${position.id ?? position.symbol}-${position.status}`}>
                  <div>
                    <strong>{position.symbol} {formatOptionType(position.option_type)}</strong>
                    <span>{position.status.replaceAll("_", " ")} · {position.contracts} contract{position.contracts === 1 ? "" : "s"}</span>
                  </div>
                  <div>
                    <span>{currencyCents(position.strike)} · {position.expiration}</span>
                    <strong>{position.current_price != null ? currencyCents(position.current_price) : "N/A"}</strong>
                  </div>
                  {apiAvailable && position.status === "put_open" && (
                    <button className="ghost-button" type="button" onClick={() => markAssigned(position)} disabled={loading === `assign-${position.id ?? position.symbol}`}>
                      Mark assigned
                    </button>
                  )}
                </article>
              )) : <p className="fine-print">No active wheel positions.</p>}
            </div>
            <div className="option-lifecycle-list">
              <h3>Alerts</h3>
              {alerts.length ? alerts.map((alert) => (
                <article className="option-alert-card" key={`${alert.id ?? alert.symbol}-${alert.created_at}`}>
                  <Bell size={16} />
                  <div>
                    <strong>{alert.symbol} · {alert.kind.replaceAll("_", " ")}</strong>
                    <span>{alert.message}</span>
                  </div>
                  <small>{formatDateTime(alert.created_at)}</small>
                </article>
              )) : <p className="fine-print">No alerts generated.</p>}
            </div>
          </div>
        </section>
      </div>
    </>
  );
}

function OptionChartTooltip({
  active,
  payload,
  label,
  signalStatus
}: {
  active?: boolean;
  payload?: Array<{ payload?: ChartRow }>;
  label?: string | number;
  signalStatus: string;
}) {
  if (!active) return null;
  const row = payload?.[0]?.payload;
  if (!row) return null;
  return (
    <div className="option-chart-tooltip">
      <strong>{formatDate(String(label ?? row.date))}</strong>
      <span>Close {currencyCents(row.close)}</span>
      <span>EMA 8 / 21 {formatNullableCurrency(row.ema8)} / {formatNullableCurrency(row.ema21)}</span>
      <span>EMA 34 / 55 {formatNullableCurrency(row.ema34)} / {formatNullableCurrency(row.ema55)}</span>
      <span>RSI {row.rsi == null ? "N/A" : row.rsi.toFixed(1)}</span>
      <span>Signal {signalStatus}</span>
    </div>
  );
}

function OpportunityTooltip({
  active,
  payload
}: {
  active?: boolean;
  payload?: Array<{ payload?: OpportunityRow }>;
}) {
  if (!active) return null;
  const row = payload?.[0]?.payload;
  if (!row) return null;
  return (
    <div className="option-opportunity-tooltip">
      <strong>{row.symbol} {currencyCents(row.strike)} · {row.expiration}</strong>
      <span>{row.status} · {row.dte} DTE</span>
      <span>Yield {percent(row.premium_yield)} · IV {percent(row.iv)}</span>
      <span>Delta {row.delta.toFixed(2)} · OI {row.open_interest.toLocaleString()}</span>
      <span>Bid / ask {currencyCents(row.bid)} / {currencyCents(row.ask)}</span>
    </div>
  );
}

function marketEndDate() {
  const endDate = toIsoDate(new Date());
  return endDate;
}

function marketStartDate() {
  return toIsoDate(addDays(new Date(), -370));
}

function fetchCachedMarketHistory(symbol: string, startDate: string, endDate: string, forceRefresh: boolean) {
  const cacheKey = `${symbol}:${startDate}:${endDate}`;
  if (!forceRefresh && marketHistoryCache.has(cacheKey)) {
    return marketHistoryCache.get(cacheKey) as Promise<MarketHistory>;
  }
  const params = new URLSearchParams({ symbol, start_date: startDate, end_date: endDate });
  if (forceRefresh) params.set("force_refresh", "true");
  const request = apiFetch<MarketHistory>(`/market-data/history?${params.toString()}`).catch(() => emptyHistory(symbol, startDate, endDate));
  marketHistoryCache.set(cacheKey, request);
  return request;
}

async function fetchOptionStrategyData(runScan: boolean): Promise<{
  ok: true;
  config: OptionStrategyConfig;
  universe: OptionStrategyUniverse;
  signals: OptionStrategySignalCandidate[];
  positions: OptionStrategyWheelPosition[];
  alerts: OptionStrategyAlertEvent[];
  scannedAt: string;
} | { ok: false; message: string }> {
  try {
    const scanResult = runScan ? await optionStrategyFetch<OptionStrategyScanResult>("/scan?force=true", { method: "POST" }) : null;
    const [configPayload, universePayload, signalsPayload, positionsPayload, alertsPayload] = await Promise.all([
      optionStrategyFetch<OptionStrategyConfig>("/config"),
      optionStrategyFetch<OptionStrategyUniverse>("/universe"),
      optionStrategyFetch<unknown>("/signals"),
      optionStrategyFetch<unknown>("/positions"),
      optionStrategyFetch<unknown>("/alerts")
    ]);
    const rawSignals = scanResult?.signals?.length ? scanResult.signals : normalizeSignals(signalsPayload);
    const universeSymbols = new Set(universePayload.items.map((item) => item.symbol));
    const signals = universeSymbols.size ? rawSignals.filter((signal) => universeSymbols.has(signal.symbol)) : rawSignals;
    return {
      ok: true,
      config: configPayload,
      universe: universePayload,
      signals,
      positions: normalizeArray<OptionStrategyWheelPosition>(positionsPayload, "positions"),
      alerts: normalizeArray<OptionStrategyAlertEvent>(alertsPayload, "alerts"),
      scannedAt: scanResult?.scanned_at ?? new Date().toISOString()
    };
  } catch (err) {
    const message = err instanceof Error ? err.message : "";
    const unavailable = message === "Not Found" || message === "Request failed with 404";
    return {
      ok: false,
      message: message && !unavailable
        ? `Option strategy backend unavailable: ${message}`
        : "Option strategy backend unavailable; showing demo data."
    };
  }
}

function normalizeSignals(payload: unknown): OptionStrategySignalCandidate[] {
  if (Array.isArray(payload)) return payload as OptionStrategySignalCandidate[];
  if (payload && typeof payload === "object") {
    const value = payload as { signals?: unknown; candidates?: unknown; results?: unknown };
    if (Array.isArray(value.signals)) return value.signals as OptionStrategySignalCandidate[];
    if (Array.isArray(value.candidates)) return value.candidates as OptionStrategySignalCandidate[];
    if (Array.isArray(value.results)) return value.results as OptionStrategySignalCandidate[];
  }
  return [];
}

function normalizeArray<T>(payload: unknown, key: string): T[] {
  if (Array.isArray(payload)) return payload as T[];
  if (payload && typeof payload === "object") {
    const value = payload as Record<string, unknown>;
    if (Array.isArray(value[key])) return value[key] as T[];
  }
  return [];
}

function buildChartRows(history: MarketHistory | undefined, symbol: string, selectedSignal: OptionStrategySignalCandidate | null): ChartRow[] {
  const bars = history ? history.bars : syntheticHistory(symbol).bars;
  if (!bars.length) return [];
  const values = bars.map((bar) => normalizedClose(bar));
  const ema8 = ema(values, 8);
  const ema21 = ema(values, 21);
  const ema34 = ema(values, 34);
  const ema55 = ema(values, 55);
  const rsi = rsiSeries(values, 14);
  const rows = bars.map((bar, index) => ({
    date: bar.date,
    close: round(values[index]),
    ema8: nullableRound(ema8[index]),
    ema21: nullableRound(ema21[index]),
    ema34: nullableRound(ema34[index]),
    ema55: nullableRound(ema55[index]),
    rsi: nullableRound(rsi[index]),
    signal: null as number | null,
    emaGreen: Boolean(ema8[index] && ema21[index] && ema34[index] && ema55[index] && ema8[index] > ema21[index] && ema34[index] > ema55[index])
  }));
  const latest = rows.at(-1);
  const oneYearStart = latest ? toIsoDate(addDays(parseIsoDate(latest.date), -365)) : "";
  let displayRows = oneYearStart ? rows.filter((row) => row.date >= oneYearStart) : rows;
  if (displayRows.length < 252 && rows.length > displayRows.length) {
    displayRows = rows.slice(-Math.min(rows.length, 252));
  }
  if (selectedSignal && displayRows.length) {
    displayRows = displayRows.map((row, index) => index === displayRows.length - 1 ? { ...row, signal: row.close } : row);
  }
  return displayRows;
}

function buildRegimeAreas(rows: ChartRow[]): RegimeArea[] {
  if (!rows.length) return [];
  const areas: RegimeArea[] = [];
  let start = rows[0].date;
  let green = rows[0].emaGreen;
  for (let index = 1; index < rows.length; index += 1) {
    if (rows[index].emaGreen !== green) {
      areas.push({ start, end: rows[index - 1].date, green });
      start = rows[index].date;
      green = rows[index].emaGreen;
    }
  }
  areas.push({ start, end: rows.at(-1)?.date ?? start, green });
  return areas;
}

function buildOpportunityRows(symbol: string, signals: OptionStrategySignalCandidate[], apiAvailable: boolean): OpportunityRow[] {
  const apiRows = signals.filter((signal) => signal.symbol === symbol).map((signal) => ({
    id: signalKey(signal),
    symbol: signal.symbol,
    dte: signal.dte,
    premium_yield: signal.premium_yield,
    iv: signal.iv,
    delta: signal.delta,
    bid: signal.bid,
    ask: signal.ask,
    mid: signal.mid,
    open_interest: signal.open_interest,
    status: signal.status,
    strike: signal.strike,
    expiration: signal.expiration
  }));
  if (apiAvailable || apiRows.length > 4) return apiRows;
  const anchor = apiRows[0] ?? buildDemoSignals({})[0];
  return Array.from({ length: 9 }, (_, index) => {
    const dte = 25 + index;
    const premiumYield = Math.max(0.025, anchor.premium_yield + (index - 4) * 0.004);
    const delta = -0.18 - index * 0.025;
    const status = index >= 2 && index <= 6 && premiumYield >= 0.05 && Math.abs(delta) <= 0.35 ? "approved" : "blocked";
    return {
      ...anchor,
      id: `${symbol}-chain-${index}`,
      symbol,
      dte,
      premium_yield: premiumYield,
      iv: Math.max(0.34, anchor.iv + (index - 4) * 0.018),
      delta,
      bid: Math.max(0.45, anchor.bid + (index - 4) * 0.16),
      ask: Math.max(0.55, anchor.ask + (index - 4) * 0.17),
      mid: Math.max(0.5, anchor.mid + (index - 4) * 0.165),
      open_interest: Math.max(20, anchor.open_interest + index * 43),
      status,
      strike: Math.max(5, anchor.strike - (4 - index) * 2),
      expiration: toIsoDate(nextFriday(addDays(new Date(), dte)))
    };
  });
}

function buildDemoSignals(histories: Record<string, MarketHistory>): OptionStrategySignalCandidate[] {
  const profiles: Array<{ symbol: string; approved: boolean; yield: number; iv: number; reasons: string[]; sector: string }> = [
    { symbol: "NVDA", approved: true, yield: 0.058, iv: 0.66, reasons: [], sector: "Information Technology" },
    { symbol: "AMD", approved: true, yield: 0.054, iv: 0.61, reasons: [], sector: "Information Technology" },
    { symbol: "QQQ", approved: true, yield: 0.051, iv: 0.46, reasons: [], sector: "ETF" },
    { symbol: "SMH", approved: true, yield: 0.053, iv: 0.57, reasons: [], sector: "ETF" },
    { symbol: "TQQQ", approved: true, yield: 0.056, iv: 0.68, reasons: [], sector: "Leveraged ETF" },
    { symbol: "SOXL", approved: true, yield: 0.062, iv: 0.74, reasons: [], sector: "Leveraged ETF" },
    { symbol: "UPRO", approved: false, yield: 0.043, iv: 0.54, reasons: ["Premium yield below 5%"], sector: "Leveraged ETF" },
    { symbol: "SPY", approved: false, yield: 0.032, iv: 0.31, reasons: ["Premium yield below 5%"], sector: "ETF" }
  ];
  return profiles.map((profile, index) => {
    const price = latestPrice(histories[profile.symbol], profile.symbol);
    const strike = roundToNearest(price * (profile.symbol === "SPY" || profile.symbol === "QQQ" ? 0.95 : 0.88), 1);
    const mid = round(strike * profile.yield);
    const expiration = toIsoDate(nextFriday(addDays(new Date(), 28 + (index % 4) * 2)));
    const dte = Math.max(25, daysBetween(toIsoDate(new Date()), expiration));
    return {
      id: `demo-${profile.symbol}`,
      symbol: profile.symbol,
      action: "sell_put",
      status: profile.approved ? "approved" : "blocked",
      sector: profile.sector,
      underlying_price: round(price),
      strike,
      expiration,
      dte,
      delta: -round(0.22 + (index % 4) * 0.035),
      iv: profile.iv,
      iv_rank: Math.min(0.95, profile.iv),
      bb_percent: 0.42 + index * 0.05,
      earnings_date: null,
      earnings_days: null,
      spread_pct: 0.08,
      bid: round(mid * 0.97),
      ask: round(mid * 1.03),
      mid,
      open_interest: 420 + index * 185,
      premium_yield: profile.yield,
      collateral: strike * 100,
      alert_target_price: round(mid / 2),
      exposure_usage: Math.min(0.34, (strike * 100) / demoConfig.account_value + index * 0.018),
      score: round(78 - index * 4),
      deep_dive_rank: index + 1,
      deep_dive_summary: `Research priority ${index + 1}: ${profile.symbol} is a wheel candidate to review for liquidity, assignment comfort, and upcoming events.`,
      if_expires_return: profile.yield,
      if_assigned_basis: round(strike - mid),
      provider: "demo fallback",
      checklist: buildDemoChecklist(profile.approved, profile.yield, profile.iv, profile.reasons),
      blocked_reasons: profile.reasons,
      created_at: new Date().toISOString()
    };
  });
}

function buildDemoChecklist(approved: boolean, premiumYield: number, iv: number, reasons: string[]) {
  return [
    { id: "ema_cloud", label: "EMA cloud", passed: approved || !reasons.includes("EMA cloud is red"), actual: "8 > 21 and 34 > 55", expected: "Green cloud", detail: approved ? "Trend cloud supports selling puts." : "Trend check reviewed." },
    { id: "rsi", label: "RSI 14", passed: approved || !reasons.includes("RSI above 50"), actual: 46.2, expected: "< 50", detail: "RSI is below the entry ceiling." },
    { id: "iv", label: "Contract IV", passed: iv >= 0.5, actual: percent(iv), expected: ">= 50%", detail: `${percent(iv)} implied volatility.` },
    { id: "red_day", label: "Underlying red", passed: approved, actual: approved ? "Red" : "Mixed", expected: "Red daily candle", detail: approved ? "Underlying is down on the day." : "Underlying candle is not ideal." },
    { id: "exposure", label: "Ticker exposure", passed: !reasons.includes("Exposure cap would exceed 30%"), actual: "Under cap", expected: "< 30%", detail: reasons.includes("Exposure cap would exceed 30%") ? "New collateral would exceed the configured cap." : "Collateral fits within exposure cap." },
    { id: "yield", label: "Premium yield", passed: premiumYield >= 0.05, actual: percent(premiumYield), expected: ">= 5%", detail: `${percent(premiumYield)} premium over strike collateral.` },
    { id: "liquidity", label: "DTE / delta / liquidity", passed: approved, actual: "25-35 DTE, liquid chain", expected: "0.20-0.35 delta", detail: approved ? "DTE, delta, spread, and open interest are in range." : "One or more liquidity filters blocks this contract." }
  ];
}

function buildDemoPositions(): OptionStrategyWheelPosition[] {
  return [
    {
      id: "demo-position-qqq",
      symbol: "QQQ",
      status: "put_open",
      option_type: "put",
      strike: 445,
      expiration: toIsoDate(nextFriday(addDays(new Date(), 24))),
      contracts: 1,
      entry_premium: 9.8,
      current_price: 5.2,
      alert_target_price: 4.9,
      collateral: 44500,
      created_at: toIsoDate(addDays(new Date(), -8)),
      updated_at: new Date().toISOString()
    },
    {
      id: "demo-position-smh",
      symbol: "SMH",
      status: "assigned",
      option_type: "put",
      strike: 245,
      expiration: toIsoDate(addDays(new Date(), -5)),
      contracts: 1,
      entry_premium: 7.4,
      current_price: null,
      alert_target_price: null,
      collateral: 24500,
      created_at: toIsoDate(addDays(new Date(), -39)),
      updated_at: new Date().toISOString()
    }
  ];
}

function buildDemoAlerts(): OptionStrategyAlertEvent[] {
  return [
    {
      id: "demo-alert-profit",
      symbol: "QQQ",
      kind: "profit_50",
      status: "open",
      message: "Close alert when option value reaches 50% of entry premium.",
      target_price: 4.9,
      current_price: 5.2,
      created_at: new Date().toISOString()
    },
    {
      id: "demo-alert-call",
      symbol: "SMH",
      kind: "covered_call_candidate",
      status: "open",
      message: "Assigned shares are ready for covered-call candidate review.",
      target_price: null,
      current_price: null,
      created_at: toIsoDate(addDays(new Date(), -1))
    }
  ];
}

function syntheticHistory(symbol: string): MarketHistory {
  const endDate = new Date();
  const bars: MarketPriceBar[] = [];
  const base = ({ NVDA: 132, AMD: 168, QQQ: 452, SPY: 526, SMH: 248, XLE: 92, XLI: 128, UPRO: 82, TQQQ: 78, SOXL: 44 } as Record<string, number>)[symbol] ?? 120;
  let price = base * (0.82 + (hashString(symbol) % 9) / 100);
  let cursor = addDays(endDate, -420);
  while (bars.length < 285) {
    cursor = addDays(cursor, 1);
    if (cursor.getDay() === 0 || cursor.getDay() === 6) continue;
    const index = bars.length;
    const wave = Math.sin(index / 11 + hashString(symbol)) * 0.012;
    const pulse = Math.cos(index / 29) * 0.008;
    const drift = symbol.length <= 3 ? 0.00075 : 0.0011;
    price = Math.max(4, price * (1 + drift + wave + pulse));
    bars.push({
      date: toIsoDate(cursor),
      close: round(price),
      adjusted_close: round(price),
      dividend: 0,
      source: "demo"
    });
  }
  return {
    symbol,
    name: symbol,
    benchmark: symbol,
    category: "option-strategy",
    requested_start_date: bars[0]?.date ?? toIsoDate(endDate),
    requested_end_date: bars.at(-1)?.date ?? toIsoDate(endDate),
    start_date: bars[0]?.date ?? null,
    end_date: bars.at(-1)?.date ?? null,
    bars,
    warnings: []
  };
}

function ema(values: number[], period: number): Array<number | null> {
  if (!values.length) return [];
  const smoothing = 2 / (period + 1);
  let previous = values[0];
  return values.map((value, index) => {
    if (index === 0) {
      previous = value;
      return previous;
    }
    previous = value * smoothing + previous * (1 - smoothing);
    return previous;
  });
}

function rsiSeries(values: number[], period: number): Array<number | null> {
  const output: Array<number | null> = Array(values.length).fill(null);
  if (values.length <= period) return output;
  let gains = 0;
  let losses = 0;
  for (let index = 1; index <= period; index += 1) {
    const change = values[index] - values[index - 1];
    if (change >= 0) gains += change;
    else losses -= change;
  }
  let averageGain = gains / period;
  let averageLoss = losses / period;
  output[period] = averageLoss === 0 ? 100 : 100 - (100 / (1 + averageGain / averageLoss));
  for (let index = period + 1; index < values.length; index += 1) {
    const change = values[index] - values[index - 1];
    averageGain = ((averageGain * (period - 1)) + Math.max(change, 0)) / period;
    averageLoss = ((averageLoss * (period - 1)) + Math.max(-change, 0)) / period;
    output[index] = averageLoss === 0 ? 100 : 100 - (100 / (1 + averageGain / averageLoss));
  }
  return output;
}

function normalizedClose(bar: MarketPriceBar) {
  return bar.adjusted_close || bar.close;
}

function emptyHistory(symbol: string, startDate: string, endDate: string): MarketHistory {
  return {
    symbol,
    name: `${symbol} market history`,
    benchmark: symbol,
    category: "Option strategy universe",
    requested_start_date: startDate,
    requested_end_date: endDate,
    start_date: null,
    end_date: null,
    bars: [],
    warnings: ["Market history request failed. Refresh again after confirming the backend provider is available."]
  };
}

function latestPrice(history: MarketHistory | undefined, symbol: string) {
  const historyPrice = history?.bars.at(-1);
  if (historyPrice) return normalizedClose(historyPrice);
  return normalizedClose(syntheticHistory(symbol).bars.at(-1) as MarketPriceBar);
}

function signalKey(signal: OptionStrategySignalCandidate) {
  return String(signal.id ?? `${signal.symbol}-${signal.action}-${signal.strike}-${signal.expiration}-${signal.status}`);
}

function isApproved(status: string) {
  return status.toLowerCase() === "approved";
}

function formatAction(value: string) {
  return value.replaceAll("_", " ");
}

function formatOptionType(value: string) {
  return value.toLowerCase() === "put" ? "put" : value.toLowerCase() === "call" ? "call" : value;
}

function chartSeriesLabel(name: string) {
  if (name === "close") return "Adjusted close";
  if (name === "ema8") return "EMA 8";
  if (name === "ema21") return "EMA 21";
  if (name === "ema34") return "EMA 34";
  if (name === "ema55") return "EMA 55";
  if (name === "signal") return "Signal marker";
  return name;
}

function chartTooltipValue(value: number, name: string) {
  if (name === "rsi") return value.toFixed(1);
  return currencyCents(value);
}

function opportunitySeriesLabel(name: string) {
  if (name === "dte") return "DTE";
  if (name === "premium_yield") return "Premium yield";
  if (name === "iv") return "IV";
  if (name === "delta") return "Delta";
  return name;
}

function opportunityTooltipValue(value: number, name: string) {
  if (name === "premium_yield" || name === "iv") return percent(value);
  if (name === "bid" || name === "ask" || name === "mid" || name === "strike") return currencyCents(value);
  if (name === "delta") return value.toFixed(2);
  return value.toLocaleString();
}

function maxDrawdown(values: number[]) {
  let peak = values[0] ?? 0;
  let drawdown = 0;
  for (const value of values) {
    peak = Math.max(peak, value);
    if (peak > 0) drawdown = Math.min(drawdown, (value / peak) - 1);
  }
  return drawdown;
}

function round(value: number) {
  return Math.round(value * 100) / 100;
}

function nullableRound(value: number | null | undefined) {
  return value == null ? null : round(value);
}

function roundToNearest(value: number, step: number) {
  return Math.round(value / step) * step;
}

function compactCurrency(value: number) {
  return new Intl.NumberFormat("en-US", { notation: "compact", style: "currency", currency: "USD", maximumFractionDigits: 1 }).format(value);
}

function currencyCents(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value);
}

function formatNullableCurrency(value: number | null) {
  return value == null ? "N/A" : currencyCents(value);
}

function formatDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function formatDate(value: string) {
  const parsed = parseIsoDate(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function formatMonthDay(value: string) {
  const parsed = parseIsoDate(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function toIsoDate(value: Date) {
  return value.toISOString().slice(0, 10);
}

function parseIsoDate(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year || 1970, (month || 1) - 1, day || 1);
}

function addDays(value: Date, days: number) {
  const next = new Date(value);
  next.setDate(next.getDate() + days);
  return next;
}

function daysBetween(start: string, end: string) {
  return Math.round((parseIsoDate(end).getTime() - parseIsoDate(start).getTime()) / 86400000);
}

function nextFriday(value: Date) {
  const next = new Date(value);
  while (next.getDay() !== 5) {
    next.setDate(next.getDate() + 1);
  }
  return next;
}

function hashString(value: string) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash;
}
