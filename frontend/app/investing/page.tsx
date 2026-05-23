"use client";

import {
  ArrowLeft,
  BarChart3,
  CalendarDays,
  Calculator,
  CheckCircle2,
  CircleDollarSign,
  LineChart as LineChartIcon,
  RefreshCcw,
  ShieldCheck,
  SlidersHorizontal,
  TrendingDown,
  TrendingUp
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { HighYieldFund, MajorIndex, MarketHistory, MarketPriceBar, apiFetch } from "@/lib/api";

type ToolId = "etf-dma" | "stock-dma" | "etf-return" | "high-yield";
type AssetKind = "etf" | "stock";
type DividendMode = "reinvest" | "cash" | "ignore";
type ContributionFrequency = "none" | "monthly" | "quarterly" | "annually";

type MovingAverageInput = {
  symbol: string;
  startDate: string;
  endDate: string;
  fastPeriod: number;
  slowPeriod: number;
};

type ReturnInput = {
  symbol: string;
  startDate: string;
  endDate: string;
  initialInvestment: number;
  periodicInvestment: number;
  contributionFrequency: ContributionFrequency;
  dividendMode: DividendMode;
  annualExpenseRatio: number;
};

type PricePoint = {
  date: string;
  close: number;
  maFast: number | null;
  maSlow: number | null;
};

type Crossover = {
  date: string;
  type: "Bullish" | "Bearish";
  close: number;
  fast: number;
  slow: number;
  priorTrendDays: number;
};

type ReturnEvent = {
  date: string;
  label: string;
  amount: number;
};

const tools: Array<{
  id: ToolId;
  label: string;
  title: string;
  summary: string;
  sourceLabel: string;
  sourceUrl: string;
}> = [
  {
    id: "etf-dma",
    label: "ETF moving average",
    title: "ETF daily moving average lab",
    summary: "Review ETF price trend, fast and slow moving averages, crossover dates, and distance from the trend line.",
    sourceLabel: "DQYDJ ETF daily moving average calculator",
    sourceUrl: "https://dqydj.com/etf-daily-moving-average-calculator/"
  },
  {
    id: "stock-dma",
    label: "Stock moving average",
    title: "Stock daily moving average lab",
    summary: "Stress-test single-stock trend readings with a wider volatility model and explicit crossover review.",
    sourceLabel: "DQYDJ stock daily moving average calculator",
    sourceUrl: "https://dqydj.com/stock-daily-moving-average-calculator/"
  },
  {
    id: "etf-return",
    label: "ETF return",
    title: "ETF return and reinvestment calculator",
    summary: "Compare an ETF investment path with dividend reinvestment, cash dividends, periodic contributions, and expense drag.",
    sourceLabel: "DQYDJ ETF return calculator",
    sourceUrl: "https://dqydj.com/etf-return-calculator/"
  },
  {
    id: "high-yield",
    label: "High Yield Investing",
    title: "High-yield income ETF buy/add monitor",
    summary: "Review option-income funds, cached price history, weekly DCA pullback signals, and total-return context.",
    sourceLabel: "Official issuer fund pages",
    sourceUrl: "https://neosfunds.com/"
  }
];

const defaultStartDate = "2024-01-02";
const defaultReturnStartDate = "2021-01-04";
const highYieldStartDate = "2023-01-03";
const defaultEndDate = "2026-05-22";

const defaultEtfInput: MovingAverageInput = {
  symbol: "SPY",
  startDate: defaultStartDate,
  endDate: defaultEndDate,
  fastPeriod: 50,
  slowPeriod: 200
};

const defaultStockInput: MovingAverageInput = {
  symbol: "AAPL",
  startDate: defaultStartDate,
  endDate: defaultEndDate,
  fastPeriod: 20,
  slowPeriod: 100
};

const defaultReturnInput: ReturnInput = {
  symbol: "VTI",
  startDate: defaultReturnStartDate,
  endDate: defaultEndDate,
  initialInvestment: 10000,
  periodicInvestment: 500,
  contributionFrequency: "monthly",
  dividendMode: "reinvest",
  annualExpenseRatio: 0.03
};

export default function InvestingPage() {
  const [activeTool, setActiveTool] = useState<ToolId>("etf-dma");
  const [etfInput, setEtfInput] = useState(defaultEtfInput);
  const [stockInput, setStockInput] = useState(defaultStockInput);
  const [returnInput, setReturnInput] = useState(defaultReturnInput);
  const [majorIndexes, setMajorIndexes] = useState<MajorIndex[]>([]);
  const [marketHistory, setMarketHistory] = useState<MarketHistory | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [cacheStatus, setCacheStatus] = useState("");
  const [highYieldFunds, setHighYieldFunds] = useState<HighYieldFund[]>([]);
  const [highYieldHistories, setHighYieldHistories] = useState<Record<string, MarketHistory>>({});
  const [highYieldLoading, setHighYieldLoading] = useState(false);
  const [highYieldError, setHighYieldError] = useState("");
  const [highYieldCacheStatus, setHighYieldCacheStatus] = useState("");

  const activeMeta = tools.find((tool) => tool.id === activeTool) ?? tools[0];
  const historyRequest = useMemo(() => marketHistoryRequest(activeTool, etfInput, stockInput, returnInput), [activeTool, etfInput, returnInput, stockInput]);
  const activeBars = marketHistory?.symbol === cleanTicker(historyRequest.symbol) ? marketHistory.bars : [];

  useEffect(() => {
    let active = true;
    async function loadMajorIndexes() {
      try {
        const rows = await apiFetch<MajorIndex[]>("/market-data/major-indexes");
        if (active) setMajorIndexes(rows);
      } catch {
        if (active) setMajorIndexes([]);
      }
    }
    void loadMajorIndexes();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (activeTool === "high-yield") {
      setHistoryLoading(false);
      setHistoryError("");
      setMarketHistory(null);
      return;
    }
    let active = true;
    const timeout = window.setTimeout(async () => {
      setHistoryLoading(true);
      setHistoryError("");
      try {
        const params = new URLSearchParams({
          symbol: historyRequest.symbol,
          start_date: historyRequest.startDate,
          end_date: historyRequest.endDate
        });
        const history = await apiFetch<MarketHistory>(`/market-data/history?${params.toString()}`);
        if (active) setMarketHistory(history);
      } catch (err) {
        if (active) {
          setMarketHistory(null);
          setHistoryError(err instanceof Error ? err.message : "Could not load market history.");
        }
      } finally {
        if (active) setHistoryLoading(false);
      }
    }, 300);
    return () => {
      active = false;
      window.clearTimeout(timeout);
    };
  }, [activeTool, historyRequest]);

  useEffect(() => {
    if (activeTool !== "high-yield") return;
    let active = true;
    async function loadHighYieldFunds() {
      setHighYieldLoading(true);
      setHighYieldError("");
      try {
        const params = highYieldParams(false);
        const funds = await apiFetch<HighYieldFund[]>(`/market-data/high-yield-funds?${params.toString()}`);
        const histories = await fetchHighYieldHistories(funds);
        if (active) {
          setHighYieldFunds(funds);
          setHighYieldHistories(histories);
        }
      } catch (err) {
        if (active) {
          setHighYieldError(err instanceof Error ? err.message : "Could not load high-yield fund data.");
        }
      } finally {
        if (active) setHighYieldLoading(false);
      }
    }
    void loadHighYieldFunds();
    return () => {
      active = false;
    };
  }, [activeTool]);

  async function refreshMajorIndexCache() {
    setCacheStatus("Caching major indexes");
    setHistoryError("");
    try {
      const params = new URLSearchParams({
        start_date: historyRequest.startDate,
        end_date: historyRequest.endDate,
        force_refresh: "true"
      });
      const histories = await apiFetch<MarketHistory[]>(`/market-data/major-indexes/cache?${params.toString()}`, { method: "POST" });
      const barCount = histories.reduce((total, history) => total + history.bars.length, 0);
      setCacheStatus(`Cached ${barCount.toLocaleString()} daily bars across ${histories.length} major index ETFs.`);
      const refreshed = histories.find((history) => history.symbol === cleanTicker(historyRequest.symbol));
      if (refreshed) setMarketHistory(refreshed);
    } catch (err) {
      setCacheStatus("");
      setHistoryError(err instanceof Error ? err.message : "Could not refresh the major index cache.");
    }
  }

  async function refreshHighYieldCache() {
    setHighYieldCacheStatus("Caching high-yield funds");
    setHighYieldError("");
    try {
      const params = highYieldParams(true);
      const funds = await apiFetch<HighYieldFund[]>(`/market-data/high-yield-funds/cache?${params.toString()}`, { method: "POST" });
      const histories = await fetchHighYieldHistories(funds);
      setHighYieldFunds(funds);
      setHighYieldHistories(histories);
      const barCount = Object.values(histories).reduce((total, history) => total + history.bars.length, 0);
      setHighYieldCacheStatus(`Cached ${barCount.toLocaleString()} daily bars across ${funds.length} high-yield funds.`);
    } catch (err) {
      setHighYieldCacheStatus("");
      setHighYieldError(err instanceof Error ? err.message : "Could not refresh high-yield fund data.");
    }
  }

  return (
    <main className="dashboard-shell investing-shell">
      <header className="dashboard-header">
        <div>
          <Link href="/" className="brand"><span className="brand-mark">D</span><span>DirectIndex</span></Link>
          <h1>Investing calculators</h1>
        </div>
        <div className="dashboard-actions">
          <Link className="ghost-button" href="/"><ArrowLeft size={16} /> Home</Link>
          <Link className="ghost-button" href="/portfolio">Portfolio</Link>
          <Link className="ghost-button" href="/ideas">Ideas</Link>
          <Link className="ghost-button" href="/research">Research</Link>
          <Link className="secondary-button" href="/dashboard">Direct-index dashboard</Link>
        </div>
      </header>

      <div className="dashboard-disclaimer">
        <LegalDisclaimer compact />
      </div>

      <section className="investing-hero">
        <div>
          <p className="eyebrow">Investing research workspace</p>
          <h2>Daily trend and return calculators for review work.</h2>
          <p>
            Use the calculator tabs to examine moving-average trend signals, crossover dates, dividend handling,
            and contribution-driven return paths before moving an idea into the portfolio or advisor workflow.
          </p>
        </div>
        <div className="investing-hero-panel">
          <div className="investing-hero-metric">
            <LineChartIcon size={20} />
            <span>Trend tools</span>
            <strong>ETF + stock</strong>
          </div>
          <div className="investing-hero-metric">
            <CircleDollarSign size={20} />
            <span>Return path</span>
            <strong>Dividends</strong>
          </div>
          <div className="investing-hero-metric">
            <ShieldCheck size={20} />
            <span>Output type</span>
            <strong>Simulation</strong>
          </div>
        </div>
      </section>

      <section className="investing-page-layout">
        <aside className="investing-sidebar">
          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Investing tabs</h2>
              <SlidersHorizontal size={18} />
            </div>
            <div className="investing-tool-list" role="tablist" aria-label="Investing calculator tabs">
              {tools.map((tool) => (
                <button
                  className={`investing-tool-button ${activeTool === tool.id ? "active" : ""}`}
                  key={tool.id}
                  type="button"
                  role="tab"
                  aria-selected={activeTool === tool.id}
                  onClick={() => setActiveTool(tool.id)}
                >
                  <span>{tool.label}</span>
                  <small>{tool.summary}</small>
                </button>
              ))}
            </div>
          </section>

          <section className="dashboard-panel investing-source-card">
            <div className="panel-header">
              <h2>Reference basis</h2>
              <Calculator size={18} />
            </div>
            <p>
              This page adapts the calculator concepts into the DirectIndex visual system with original explanatory copy,
              interactive controls, and explicit simulation guardrails.
            </p>
            <a className="text-link" href={activeMeta.sourceUrl} target="_blank" rel="noreferrer">
              Open {activeMeta.sourceLabel}
            </a>
          </section>

          <section className="dashboard-panel investing-source-card">
            <div className="panel-header">
              <h2>Market data cache</h2>
              <RefreshCcw size={18} />
            </div>
            {activeTool === "high-yield" ? (
              <>
                <p>
                  High-yield charts and signals use cached adjusted-close bars for QQQI, SPYI, CHPY, IAUI, OVL, and GIAX.
                </p>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={refreshHighYieldCache}
                  disabled={highYieldLoading || highYieldCacheStatus === "Caching high-yield funds"}
                >
                  <RefreshCcw size={16} /> {highYieldCacheStatus === "Caching high-yield funds" ? "Caching" : "Refresh high-yield cache"}
                </button>
                {highYieldCacheStatus && highYieldCacheStatus !== "Caching high-yield funds" && <p className="fine-print">{highYieldCacheStatus}</p>}
                {highYieldError && <p className="error">{highYieldError}</p>}
              </>
            ) : (
              <>
                <p>
                  Charts use cached provider history from the backend `price_bars` table. Refreshing caches the main index ETF proxies for this date window.
                </p>
                <button className="secondary-button" type="button" onClick={refreshMajorIndexCache} disabled={historyLoading || cacheStatus === "Caching major indexes"}>
                  <RefreshCcw size={16} /> {cacheStatus === "Caching major indexes" ? "Caching" : "Refresh index cache"}
                </button>
                {cacheStatus && cacheStatus !== "Caching major indexes" && <p className="fine-print">{cacheStatus}</p>}
                {historyError && <p className="error">{historyError}</p>}
              </>
            )}
          </section>

          <section className="dashboard-panel investing-warning">
            <ShieldCheck size={18} />
            <p>
              Real provider bars can still be delayed, incomplete, or unavailable for a requested date. Outputs remain research artifacts,
              not live trading, tax filing, or brokerage instructions.
            </p>
          </section>
        </aside>

        <section className="investing-workspace">
          {activeTool === "etf-dma" && (
            <MovingAverageTool
              assetKind="etf"
              input={etfInput}
              onChange={setEtfInput}
              majorIndexes={majorIndexes}
              marketHistory={marketHistory}
              marketBars={activeBars}
              loading={historyLoading}
              sourceUrl={activeMeta.sourceUrl}
              title={activeMeta.title}
            />
          )}

          {activeTool === "stock-dma" && (
            <MovingAverageTool
              assetKind="stock"
              input={stockInput}
              onChange={setStockInput}
              majorIndexes={majorIndexes}
              marketHistory={marketHistory}
              marketBars={activeBars}
              loading={historyLoading}
              sourceUrl={activeMeta.sourceUrl}
              title={activeMeta.title}
            />
          )}

          {activeTool === "etf-return" && (
            <EtfReturnTool
              input={returnInput}
              onChange={setReturnInput}
              majorIndexes={majorIndexes}
              marketHistory={marketHistory}
              marketBars={activeBars}
              loading={historyLoading}
              sourceUrl={activeMeta.sourceUrl}
              title={activeMeta.title}
            />
          )}

          {activeTool === "high-yield" && (
            <HighYieldInvestingTool
              funds={highYieldFunds}
              histories={highYieldHistories}
              loading={highYieldLoading}
              error={highYieldError}
              cacheStatus={highYieldCacheStatus}
              onRefresh={refreshHighYieldCache}
            />
          )}
        </section>
      </section>
    </main>
  );
}

function HighYieldInvestingTool({
  funds,
  histories,
  loading,
  error,
  cacheStatus,
  onRefresh
}: {
  funds: HighYieldFund[];
  histories: Record<string, MarketHistory>;
  loading: boolean;
  error: string;
  cacheStatus: string;
  onRefresh: () => void;
}) {
  const buyCount = funds.filter((fund) => fund.signal.action === "BUY").length;
  const holdCount = funds.filter((fund) => fund.signal.action === "HOLD").length;
  const latestCacheAt = latestDateTime(funds.map((fund) => fund.cached_at).filter(Boolean) as string[]);
  const dataSource = funds.find((fund) => fund.data_source)?.data_source ?? "Cached provider adjusted close";

  return (
    <>
      <section className="dashboard-panel investing-workspace-head high-yield-head">
        <div>
          <p className="eyebrow">High-yield income ETF monitor</p>
          <h2>Weekly DCA signals for option-income funds.</h2>
          <p>
            These signals are designed for long-term buy-and-hold accumulation: BUY means add a scheduled tranche, while HOLD means keep existing shares and skip the new add.
          </p>
          <div className="investing-data-line">
            <span>{loading ? "Loading high-yield data" : `${funds.length} funds tracked`}</span>
            <span>{dataSource}</span>
            {latestCacheAt && <span>Cached {formatDateTime(latestCacheAt)}</span>}
          </div>
        </div>
        <button className="secondary-button" type="button" onClick={onRefresh} disabled={loading || cacheStatus === "Caching high-yield funds"}>
          <RefreshCcw size={16} /> {cacheStatus === "Caching high-yield funds" ? "Caching" : "Refresh"}
        </button>
      </section>

      <div className="stat-grid high-yield-summary-grid">
        <article className="stat-panel"><TrendingUp size={20} /><h3>BUY this week</h3><strong>{buyCount}</strong><p>New-tranche signals from the weekly model.</p></article>
        <article className="stat-panel"><ShieldCheck size={20} /><h3>HOLD this week</h3><strong>{holdCount}</strong><p>Keep existing shares; skip the new add.</p></article>
        <article className="stat-panel"><CalendarDays size={20} /><h3>Last cache</h3><strong>{latestCacheAt ? formatShortDateTime(latestCacheAt) : "N/A"}</strong><p>Most recent stored provider refresh.</p></article>
        <article className="stat-panel"><BarChart3 size={20} /><h3>Source</h3><strong>Adjusted close</strong><p>Signals use daily cached total-return proxy bars.</p></article>
      </div>

      {error && <section className="dashboard-panel investing-warning"><ShieldCheck size={18} /><p>{error}</p></section>}
      {loading && !funds.length && <section className="dashboard-panel"><p className="fine-print">Loading high-yield fund data and cached histories.</p></section>}

      <section className="high-yield-fund-grid" aria-label="High-yield fund signal cards">
        {funds.map((fund) => {
          const chart = buildHighYieldChart(histories[fund.symbol], fund);
          const signal = fund.signal;
          const isBuy = signal.action === "BUY";
          return (
            <article className="dashboard-panel high-yield-card" key={fund.symbol}>
              <div className="high-yield-info-stack">
                <div className="high-yield-card-head">
                  <div>
                    <p className="eyebrow">{fund.issuer}</p>
                    <h3>{fund.symbol}</h3>
                    <strong>{fund.name}</strong>
                  </div>
                  <span className={`high-yield-signal ${isBuy ? "buy" : "hold"}`}>{signal.action}</span>
                </div>

                <p className="high-yield-strategy">{fund.strategy}</p>

                <div className="high-yield-meta-grid">
                  <div><span>Exposure</span><strong>{fund.exposure}</strong></div>
                  <div><span>Distribution</span><strong>{fund.distribution_frequency}</strong></div>
                  <div><span>Last close</span><strong>{signal.last_close ? currencyCents(signal.last_close) : "N/A"}</strong></div>
                  <div><span>Signal date</span><strong>{signal.signal_date ? formatDate(signal.signal_date) : "N/A"}</strong></div>
                </div>

                <div className="high-yield-reason">
                  <CheckCircle2 size={16} />
                  <p>{signal.reason}</p>
                </div>

                <div className="high-yield-pill-row">
                  <span className="reason-pill">{signal.risk_state}</span>
                  <span className="reason-pill">{percent(signal.confidence)} confidence</span>
                  {signal.backtest.hit_rate_4w !== null && signal.backtest.hit_rate_4w !== undefined && (
                    <span className="reason-pill">{percent(signal.backtest.hit_rate_4w)} 4W hit rate</span>
                  )}
                </div>

                <div className="high-yield-footer">
                  <p>{fund.risk_note}</p>
                  <a className="text-link" href={fund.source_url} target="_blank" rel="noreferrer">Issuer page</a>
                </div>

                {(signal.limited_history || fund.warnings.length > 0) && (
                  <div className="high-yield-warning">
                    <ShieldCheck size={15} />
                    <span>{fund.warnings[0] || "Limited cached history; HOLD is shown until more provider data is available."}</span>
                  </div>
                )}
              </div>

              <div className="high-yield-trade-panel">
                <div className="high-yield-trade-head">
                  <div>
                    <span>{chart.windowLabel}</span>
                    <strong>{chart.rangeLabel}</strong>
                  </div>
                  <div className={`high-yield-window-return ${chart.windowReturn >= 0 ? "positive" : "negative"}`}>
                    <span>Window return</span>
                    <strong>{chart.rows.length ? percent(chart.windowReturn) : "N/A"}</strong>
                  </div>
                </div>

                <div className="high-yield-terminal-stats">
                  <div><span>Bars</span><strong>{chart.rows.length.toLocaleString()}</strong></div>
                  <div><span>Max drawdown</span><strong>{chart.rows.length ? percent(chart.maxDrawdown) : "N/A"}</strong></div>
                  <div><span>Last model buy</span><strong>{signal.backtest.last_buy_date ? formatDate(signal.backtest.last_buy_date) : "N/A"}</strong></div>
                </div>

                <div className="high-yield-chart">
                  {chart.rows.length ? (
                  <ResponsiveContainer width="100%" height={318}>
                    <ComposedChart data={chart.rows} margin={{ left: 2, right: 12, top: 10, bottom: 4 }}>
                      <defs>
                        <linearGradient id={`highYieldClose-${fund.symbol}`} x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#6ee7b7" stopOpacity={0.42} />
                          <stop offset="95%" stopColor="#6ee7b7" stopOpacity={0.03} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="#19352d" strokeDasharray="3 3" />
                      <XAxis
                        dataKey="label"
                        minTickGap={42}
                        tick={{ fontSize: 11, fill: "#8da99e" }}
                        axisLine={{ stroke: "#24463c" }}
                        tickLine={{ stroke: "#24463c" }}
                      />
                      <YAxis
                        width={58}
                        tickFormatter={(value) => compactCurrency(Number(value))}
                        tick={{ fontSize: 11, fill: "#8da99e" }}
                        axisLine={{ stroke: "#24463c" }}
                        tickLine={{ stroke: "#24463c" }}
                      />
                      <Tooltip
                        formatter={(value, name) => [currencyCents(Number(value)), highYieldSeriesLabel(String(name))]}
                        labelFormatter={(_, payload) => formatDate(String(payload?.[0]?.payload?.date ?? ""))}
                        contentStyle={{ background: "#08110f", border: "1px solid #24463c", borderRadius: 8, color: "#d8f5ea" }}
                        labelStyle={{ color: "#9be7cb" }}
                      />
                      <Legend wrapperStyle={{ color: "#b6d9cb", fontSize: 12 }} />
                      <Area type="monotone" dataKey="close" name="Close" stroke="#6ee7b7" fill={`url(#highYieldClose-${fund.symbol})`} fillOpacity={1} strokeWidth={2.8} dot={false} activeDot={{ r: 4, fill: "#d8fff1" }} />
                      <Line type="monotone" dataKey="ma20" name="20D" stroke="#38bdf8" strokeWidth={1.7} dot={false} connectNulls />
                      <Line type="monotone" dataKey="ma50" name="50D" stroke="#f59e0b" strokeWidth={1.7} dot={false} connectNulls />
                      <Line type="monotone" dataKey="ma200" name="200D" stroke="#c084fc" strokeWidth={1.7} dot={false} connectNulls />
                      <Line type="monotone" dataKey="buy" name="Buy marker" stroke="transparent" strokeWidth={0} dot={{ r: 4.5, fill: "#22c55e", stroke: "#ecfdf5", strokeWidth: 1.5 }} activeDot={{ r: 6 }} />
                    </ComposedChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="high-yield-empty-chart">No cached daily chart history is available yet.</div>
                )}
                </div>
              </div>
            </article>
          );
        })}
      </section>
    </>
  );
}

function MovingAverageTool({
  assetKind,
  input,
  onChange,
  majorIndexes,
  marketHistory,
  marketBars,
  loading,
  sourceUrl,
  title
}: {
  assetKind: AssetKind;
  input: MovingAverageInput;
  onChange: (next: MovingAverageInput) => void;
  majorIndexes: MajorIndex[];
  marketHistory: MarketHistory | null;
  marketBars: MarketPriceBar[];
  loading: boolean;
  sourceUrl: string;
  title: string;
}) {
  const analysis = useMemo(() => analyzeMovingAverage(input, assetKind, marketBars), [assetKind, input, marketBars]);
  const latest = analysis.rows.at(-1);
  const fastLabel = `${analysis.fastPeriod}D avg`;
  const slowLabel = `${analysis.slowPeriod}D avg`;
  const trendPositive = analysis.trend === "Above slow average";
  const providerSource = marketHistory?.bars[0]?.source ?? "Synthetic fallback";

  function update<K extends keyof MovingAverageInput>(key: K, value: MovingAverageInput[K]) {
    onChange({ ...input, [key]: value });
  }

  return (
    <>
      <section className="dashboard-panel investing-workspace-head">
        <div>
          <p className="eyebrow">{assetKind === "etf" ? "ETF trend model" : "Stock trend model"}</p>
          <h2>{title}</h2>
          <p>
            Enter a ticker, date window, and two rolling periods to compare price behavior against fast and slow daily moving averages.
          </p>
          <div className="investing-data-line">
            <span>{loading ? "Loading provider history" : `${analysis.rows.length.toLocaleString()} daily bars`}</span>
            <span>{providerSource}</span>
            {marketHistory?.end_date && <span>Through {formatDate(marketHistory.end_date)}</span>}
          </div>
        </div>
        <span className={`status-pill ${trendPositive ? "" : "investing-bearish"}`}>
          {trendPositive ? <TrendingUp size={14} /> : <TrendingDown size={14} />} {analysis.trend}
        </span>
      </section>

      <section className="dashboard-panel">
        <div className="panel-header">
          <h2>Calculator inputs</h2>
          <CalendarDays size={18} />
        </div>
        <div className="investing-control-grid">
          <div className="field">
            <label htmlFor={`${assetKind}-symbol`}>Ticker</label>
            {assetKind === "etf" ? (
              <select id={`${assetKind}-symbol`} value={input.symbol} onChange={(event) => update("symbol", cleanTicker(event.target.value))}>
                {majorIndexes.length ? majorIndexes.map((item) => (
                  <option value={item.symbol} key={item.symbol}>{item.symbol} - {item.benchmark}</option>
                )) : (
                  <option value={input.symbol}>{input.symbol}</option>
                )}
              </select>
            ) : (
              <input
                id={`${assetKind}-symbol`}
                value={input.symbol}
                onChange={(event) => update("symbol", cleanTicker(event.target.value))}
                placeholder="AAPL"
              />
            )}
          </div>
          <div className="field">
            <label htmlFor={`${assetKind}-start`}>Start date</label>
            <input id={`${assetKind}-start`} type="date" value={input.startDate} onChange={(event) => update("startDate", event.target.value)} />
          </div>
          <div className="field">
            <label htmlFor={`${assetKind}-end`}>End date</label>
            <input id={`${assetKind}-end`} type="date" value={input.endDate} onChange={(event) => update("endDate", event.target.value)} />
          </div>
          <div className="field">
            <label htmlFor={`${assetKind}-fast`}>Fast period</label>
            <input
              id={`${assetKind}-fast`}
              type="number"
              min="2"
              max="260"
              step="1"
              value={input.fastPeriod}
              onChange={(event) => update("fastPeriod", Number(event.target.value))}
            />
          </div>
          <div className="field">
            <label htmlFor={`${assetKind}-slow`}>Slow period</label>
            <input
              id={`${assetKind}-slow`}
              type="number"
              min="5"
              max="300"
              step="1"
              value={input.slowPeriod}
              onChange={(event) => update("slowPeriod", Number(event.target.value))}
            />
          </div>
        </div>
      </section>

      <div className="stat-grid investing-stat-grid">
        <article className="stat-panel"><BarChart3 size={20} /><h3>Latest close</h3><strong>{currencyCents(latest?.close ?? 0)}</strong><p>{formatDate(latest?.date ?? analysis.endDate)} close in the demo series.</p></article>
        <article className="stat-panel"><LineChartIcon size={20} /><h3>{fastLabel}</h3><strong>{currencyCents(latest?.maFast ?? 0)}</strong><p>Fast trend line for recent price action.</p></article>
        <article className="stat-panel"><RefreshCcw size={20} /><h3>{slowLabel}</h3><strong>{currencyCents(latest?.maSlow ?? 0)}</strong><p>Slow trend line for baseline review.</p></article>
        <article className="stat-panel"><TrendingUp size={20} /><h3>Distance to slow</h3><strong>{percent(analysis.distanceToSlow)}</strong><p>{analysis.crossoverCount} crossover events in range.</p></article>
      </div>

      <section className="dashboard-panel chart-panel investing-chart-panel investing-trade-chart-panel">
        <div className="investing-terminal-head">
          <div>
            <span>{analysis.realData ? "Cached provider adjusted close" : "Synthetic fallback"}</span>
            <h2>Daily close versus moving averages</h2>
            <strong>{formatDate(analysis.startDate)} - {formatDate(analysis.endDate)}</strong>
          </div>
          <div className={`investing-terminal-return ${analysis.distanceToSlow >= 0 ? "positive" : "negative"}`}>
            <span>Distance to slow</span>
            <strong>{percent(analysis.distanceToSlow)}</strong>
          </div>
        </div>
        <div className="investing-terminal-stats">
          <div><span>Bars</span><strong>{analysis.rows.length.toLocaleString()}</strong></div>
          <div><span>Max drawdown</span><strong>{percent(analysis.maxDrawdown)}</strong></div>
          <div><span>{fastLabel} spread</span><strong>{percent(analysis.movingAverageSpread)}</strong></div>
        </div>
        <ResponsiveContainer width="100%" height={420}>
          <ComposedChart data={analysis.chartRows} margin={{ left: 4, right: 18, top: 12, bottom: 8 }}>
            <defs>
              <linearGradient id={`trendClose-${assetKind}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6ee7b7" stopOpacity={0.42} />
                <stop offset="95%" stopColor="#6ee7b7" stopOpacity={0.03} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#19352d" strokeDasharray="3 3" />
            <XAxis
              dataKey="label"
              minTickGap={44}
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
            <Tooltip
              formatter={(value, name) => [currencyCents(Number(value)), seriesLabel(String(name), fastLabel, slowLabel)]}
              labelFormatter={(_, payload) => formatDate(String(payload?.[0]?.payload?.date ?? ""))}
              contentStyle={{ background: "#08110f", border: "1px solid #24463c", borderRadius: 8, color: "#d8f5ea" }}
              labelStyle={{ color: "#9be7cb" }}
            />
            <Legend wrapperStyle={{ color: "#b6d9cb", fontSize: 12 }} />
            <Area type="monotone" dataKey="close" name="Close" stroke="#6ee7b7" fill={`url(#trendClose-${assetKind})`} fillOpacity={1} strokeWidth={2.8} dot={false} activeDot={{ r: 4, fill: "#d8fff1" }} />
            <Line type="monotone" dataKey="fast" name="Fast" stroke="#38bdf8" strokeWidth={1.9} dot={false} connectNulls />
            <Line type="monotone" dataKey="slow" name="Slow" stroke="#f59e0b" strokeWidth={1.9} dot={false} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </section>

      <div className="investing-two-column">
        <section className="dashboard-panel">
          <div className="panel-header">
            <h2>Crossover review</h2>
            <CheckCircle2 size={18} />
          </div>
          <div className="investing-table">
            <div className="investing-row investing-row-header">
              <span>Date</span>
              <span>Signal</span>
              <span>Close</span>
              <span>Prior trend</span>
            </div>
            {analysis.crossovers.length ? analysis.crossovers.slice(-8).map((item) => (
              <div className="investing-row" key={`${item.date}-${item.type}`}>
                <span>{formatDate(item.date)}</span>
                <strong className={item.type === "Bullish" ? "buy" : "sell"}>{item.type}</strong>
                <span>{currencyCents(item.close)}</span>
                <span>{item.priorTrendDays} days</span>
              </div>
            )) : (
              <div className="investing-row investing-empty-row">
                <span>No fast/slow crossover occurred inside this date range.</span>
              </div>
            )}
          </div>
        </section>

        <section className="dashboard-panel investing-method-panel">
          <div className="panel-header">
            <h2>How to read it</h2>
            <Calculator size={18} />
          </div>
          <ul className="idea-list">
            <li>The moving average is a rolling mean of daily closes over the selected lookback window.</li>
            <li>A bullish crossover appears when the fast average moves above the slow average.</li>
            <li>A bearish crossover appears when the fast average moves below the slow average.</li>
            <li>Review the signal with volatility, taxes, position size, and portfolio context before acting.</li>
          </ul>
          <a className="text-link" href={sourceUrl} target="_blank" rel="noreferrer">Reference calculator concept</a>
        </section>
      </div>
    </>
  );
}

function EtfReturnTool({
  input,
  onChange,
  majorIndexes,
  marketHistory,
  marketBars,
  loading,
  sourceUrl,
  title
}: {
  input: ReturnInput;
  onChange: (next: ReturnInput) => void;
  majorIndexes: MajorIndex[];
  marketHistory: MarketHistory | null;
  marketBars: MarketPriceBar[];
  loading: boolean;
  sourceUrl: string;
  title: string;
}) {
  const analysis = useMemo(() => analyzeEtfReturn(input, marketBars), [input, marketBars]);
  const providerSource = marketHistory?.bars[0]?.source ?? "Synthetic fallback";

  function update<K extends keyof ReturnInput>(key: K, value: ReturnInput[K]) {
    onChange({ ...input, [key]: value });
  }

  return (
    <>
      <section className="dashboard-panel investing-workspace-head">
        <div>
          <p className="eyebrow">ETF performance model</p>
          <h2>{title}</h2>
          <p>
            Model a starting investment, optional periodic buys, dividends, and expense drag across a selected ETF date range.
          </p>
          <div className="investing-data-line">
            <span>{loading ? "Loading provider history" : `${analysis.chartRows.length.toLocaleString()} daily bars`}</span>
            <span>{providerSource}</span>
            {marketHistory?.end_date && <span>Through {formatDate(marketHistory.end_date)}</span>}
          </div>
        </div>
        <span className={`status-pill ${analysis.gainLoss >= 0 ? "" : "investing-bearish"}`}>
          {analysis.gainLoss >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />} {percent(analysis.totalReturn)}
        </span>
      </section>

      <section className="dashboard-panel">
        <div className="panel-header">
          <h2>Calculator inputs</h2>
          <CalendarDays size={18} />
        </div>
        <div className="investing-control-grid investing-return-grid">
          <div className="field">
            <label htmlFor="return-symbol">ETF ticker</label>
            <select id="return-symbol" value={input.symbol} onChange={(event) => update("symbol", cleanTicker(event.target.value))}>
              {majorIndexes.length ? majorIndexes.map((item) => (
                <option value={item.symbol} key={item.symbol}>{item.symbol} - {item.benchmark}</option>
              )) : (
                <option value={input.symbol}>{input.symbol}</option>
              )}
            </select>
          </div>
          <div className="field">
            <label htmlFor="return-start">Start date</label>
            <input id="return-start" type="date" value={input.startDate} onChange={(event) => update("startDate", event.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="return-end">End date</label>
            <input id="return-end" type="date" value={input.endDate} onChange={(event) => update("endDate", event.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="initial-investment">Initial investment</label>
            <input
              id="initial-investment"
              type="number"
              min="0"
              step="100"
              value={input.initialInvestment}
              onChange={(event) => update("initialInvestment", Number(event.target.value))}
            />
          </div>
          <div className="field">
            <label htmlFor="periodic-investment">Periodic investment</label>
            <input
              id="periodic-investment"
              type="number"
              min="0"
              step="50"
              value={input.periodicInvestment}
              onChange={(event) => update("periodicInvestment", Number(event.target.value))}
            />
          </div>
          <div className="field">
            <label htmlFor="contribution-frequency">Contribution frequency</label>
            <select
              id="contribution-frequency"
              value={input.contributionFrequency}
              onChange={(event) => update("contributionFrequency", event.target.value as ContributionFrequency)}
            >
              <option value="none">None</option>
              <option value="monthly">Monthly</option>
              <option value="quarterly">Quarterly</option>
              <option value="annually">Annually</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="dividend-mode">Dividend treatment</label>
            <select id="dividend-mode" value={input.dividendMode} onChange={(event) => update("dividendMode", event.target.value as DividendMode)}>
              <option value="reinvest">Reinvest dividends</option>
              <option value="cash">Hold dividends as cash</option>
              <option value="ignore">Ignore dividends</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="expense-ratio">Expense ratio %</label>
            <input
              id="expense-ratio"
              type="number"
              min="0"
              max="2"
              step="0.01"
              value={input.annualExpenseRatio}
              onChange={(event) => update("annualExpenseRatio", Number(event.target.value))}
            />
          </div>
        </div>
      </section>

      <div className="stat-grid investing-return-stat-grid">
        <article className="stat-panel"><CircleDollarSign size={20} /><h3>Ending value</h3><strong>{currency(analysis.endingValue)}</strong><p>Portfolio value on {formatDate(analysis.endDate)}.</p></article>
        <article className="stat-panel"><TrendingUp size={20} /><h3>Total return</h3><strong>{percent(analysis.totalReturn)}</strong><p>{currency(analysis.gainLoss)} over contributed capital.</p></article>
        <article className="stat-panel"><BarChart3 size={20} /><h3>Annualized</h3><strong>{percent(analysis.annualizedReturn)}</strong><p>Calendar-time annualized estimate.</p></article>
        <article className="stat-panel"><RefreshCcw size={20} /><h3>Dividends</h3><strong>{currency(analysis.dividends)}</strong><p>{dividendModeLabel(input.dividendMode)}.</p></article>
        <article className="stat-panel"><Calculator size={20} /><h3>Contributed</h3><strong>{currency(analysis.contributed)}</strong><p>Initial plus periodic investments.</p></article>
      </div>

      <section className="dashboard-panel chart-panel investing-chart-panel investing-trade-chart-panel">
        <div className="investing-terminal-head">
          <div>
            <span>{analysis.realData ? "Cached provider total return model" : "Synthetic fallback"}</span>
            <h2>Investment value path</h2>
            <strong>{formatDate(analysis.startDate)} - {formatDate(analysis.endDate)}</strong>
          </div>
          <div className={`investing-terminal-return ${analysis.totalReturn >= 0 ? "positive" : "negative"}`}>
            <span>Total return</span>
            <strong>{percent(analysis.totalReturn)}</strong>
          </div>
        </div>
        <div className="investing-terminal-stats">
          <div><span>Bars</span><strong>{analysis.chartRows.length.toLocaleString()}</strong></div>
          <div><span>Max drawdown</span><strong>{percent(analysis.maxDrawdown)}</strong></div>
          <div><span>Cash-flow events</span><strong>{analysis.events.length.toLocaleString()}</strong></div>
        </div>
        <ResponsiveContainer width="100%" height={430}>
          <ComposedChart data={analysis.chartRows} margin={{ left: 4, right: 18, top: 12, bottom: 8 }}>
            <defs>
              <linearGradient id="returnValueGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6ee7b7" stopOpacity={0.42} />
                <stop offset="95%" stopColor="#6ee7b7" stopOpacity={0.03} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#19352d" strokeDasharray="3 3" />
            <XAxis
              dataKey="label"
              minTickGap={44}
              tick={{ fontSize: 11, fill: "#8da99e" }}
              axisLine={{ stroke: "#24463c" }}
              tickLine={{ stroke: "#24463c" }}
            />
            <YAxis
              width={76}
              tickFormatter={(value) => compactCurrency(Number(value))}
              tick={{ fontSize: 11, fill: "#8da99e" }}
              axisLine={{ stroke: "#24463c" }}
              tickLine={{ stroke: "#24463c" }}
            />
            <Tooltip
              formatter={(value, name) => [currency(Number(value)), returnSeriesLabel(String(name))]}
              labelFormatter={(_, payload) => formatDate(String(payload?.[0]?.payload?.date ?? ""))}
              contentStyle={{ background: "#08110f", border: "1px solid #24463c", borderRadius: 8, color: "#d8f5ea" }}
              labelStyle={{ color: "#9be7cb" }}
            />
            <Legend wrapperStyle={{ color: "#b6d9cb", fontSize: 12 }} />
            <Area type="monotone" dataKey="value" name="Value" stroke="#6ee7b7" fill="url(#returnValueGradient)" fillOpacity={1} strokeWidth={2.8} activeDot={{ r: 4, fill: "#d8fff1" }} />
            <Line type="monotone" dataKey="contributed" name="Contributed" stroke="#38bdf8" strokeWidth={2} dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </section>

      <div className="investing-two-column">
        <section className="dashboard-panel">
          <div className="panel-header">
            <h2>Recent cash-flow events</h2>
            <CheckCircle2 size={18} />
          </div>
          <div className="investing-table">
            <div className="investing-row investing-row-header investing-return-header">
              <span>Date</span>
              <span>Event</span>
              <span>Amount</span>
            </div>
            {analysis.events.length ? analysis.events.slice(-8).map((event) => (
              <div className="investing-row investing-return-row" key={`${event.date}-${event.label}-${event.amount}`}>
                <span>{formatDate(event.date)}</span>
                <strong>{event.label}</strong>
                <span>{currency(event.amount)}</span>
              </div>
            )) : (
              <div className="investing-row investing-empty-row">
                <span>No contribution or dividend events occurred inside this date range.</span>
              </div>
            )}
          </div>
        </section>

        <section className="dashboard-panel investing-method-panel">
          <div className="panel-header">
            <h2>How to read it</h2>
            <Calculator size={18} />
          </div>
          <ul className="idea-list">
            <li>Ending value includes price movement, selected dividend treatment, recurring contributions, and expense drag.</li>
            <li>Total return compares ending value against contributed capital, not only the first purchase.</li>
            <li>Annualized return is a simplified calendar-time estimate and is not a full money-weighted IRR.</li>
            <li>Use real provider data before making any decision that depends on exact historical returns.</li>
          </ul>
          <a className="text-link" href={sourceUrl} target="_blank" rel="noreferrer">Reference calculator concept</a>
        </section>
      </div>
    </>
  );
}

function highYieldParams(forceRefresh: boolean) {
  const params = new URLSearchParams({
    start_date: highYieldStartDate,
    end_date: defaultEndDate
  });
  if (forceRefresh) params.set("force_refresh", "true");
  return params;
}

async function fetchHighYieldHistories(funds: HighYieldFund[]) {
  const entries = await Promise.all(
    funds.map(async (fund) => {
      const params = new URLSearchParams({
        symbol: fund.symbol,
        start_date: highYieldStartDate,
        end_date: defaultEndDate
      });
      try {
        const history = await apiFetch<MarketHistory>(`/market-data/history?${params.toString()}`);
        return [fund.symbol, history] as const;
      } catch {
        return null;
      }
    })
  );
  return Object.fromEntries(entries.filter(Boolean) as Array<readonly [string, MarketHistory]>);
}

function buildHighYieldChart(history: MarketHistory | undefined, fund: HighYieldFund) {
  const series = history ? barsToPriceSeries(history.bars) : [];
  const buyDates = new Set(fund.signal.backtest.recent_buy_dates);
  const closes: number[] = [];
  const rows = series.map((point) => {
    closes.push(point.close);
    const ma20 = closes.length >= 20 ? average(closes.slice(-20)) : null;
    const ma50 = closes.length >= 50 ? average(closes.slice(-50)) : null;
    const ma200 = closes.length >= 200 ? average(closes.slice(-200)) : null;
    return {
      date: point.date,
      label: formatMonthDay(point.date),
      close: point.close,
      ma20: ma20 ? round(ma20) : null,
      ma50: ma50 ? round(ma50) : null,
      ma200: ma200 ? round(ma200) : null,
      buy: buyDates.has(point.date) ? point.close : null
    };
  });
  const latest = rows.at(-1);
  const oneYearStart = latest ? toIsoDate(addDays(parseIsoDate(latest.date), -365)) : "";
  let displayRows = oneYearStart ? rows.filter((row) => row.date >= oneYearStart) : rows;
  if (displayRows.length < 252 && rows.length > displayRows.length) {
    displayRows = rows.slice(-Math.min(rows.length, 252));
  }
  const first = displayRows[0];
  const last = displayRows.at(-1);
  const windowReturn = first && last && first.close > 0 ? (last.close / first.close) - 1 : 0;
  let peak = first?.close ?? 0;
  let maxDrawdown = 0;
  for (const row of displayRows) {
    peak = Math.max(peak, row.close);
    if (peak > 0) maxDrawdown = Math.min(maxDrawdown, (row.close / peak) - 1);
  }
  const windowDays = first && last ? daysBetween(first.date, last.date) : 0;
  return {
    maxDrawdown,
    rangeLabel: first && last ? `${formatDate(first.date)} - ${formatDate(last.date)}` : "No chart data",
    rows: displayRows,
    windowLabel: windowDays >= 360 ? "1Y adjusted-close chart" : "Available adjusted-close chart",
    windowReturn
  };
}

function highYieldSeriesLabel(name: string) {
  if (name === "close") return "Adjusted close";
  if (name === "ma20") return "20-day average";
  if (name === "ma50") return "50-day average";
  if (name === "ma200") return "200-day average";
  if (name === "buy") return "Buy marker";
  return name;
}

function analyzeMovingAverage(input: MovingAverageInput, assetKind: AssetKind, marketBars: MarketPriceBar[]) {
  const symbol = cleanTicker(input.symbol) || (assetKind === "etf" ? "SPY" : "AAPL");
  const { startDate, endDate } = normalizeRange(input.startDate, input.endDate);
  const fastPeriod = clampInteger(input.fastPeriod, 2, 260, assetKind === "etf" ? 50 : 20);
  const slowPeriod = clampInteger(input.slowPeriod, 5, 300, assetKind === "etf" ? 200 : 100);
  const fast = Math.min(fastPeriod, slowPeriod);
  const slow = Math.max(fastPeriod, slowPeriod);
  const history = marketBars.length ? barsToPriceSeries(marketBars) : generatePriceSeries(symbol, startDate, endDate, assetKind, slow + 35);
  const rows = applyMovingAverages(history, startDate, fast, slow);
  const crossovers = findCrossovers(rows);
  const latest = rows.at(-1);
  const distanceToSlow = latest?.maSlow ? (latest.close / latest.maSlow) - 1 : 0;
  const movingAverageSpread = latest?.maFast && latest?.maSlow ? (latest.maFast / latest.maSlow) - 1 : 0;
  const trend = latest?.maFast && latest?.maSlow && latest.maFast >= latest.maSlow ? "Above slow average" : "Below slow average";

  return {
    chartRows: rows.map((row) => ({
      date: row.date,
      label: formatMonthDay(row.date),
      close: round(row.close),
      fast: row.maFast ? round(row.maFast) : null,
      slow: row.maSlow ? round(row.maSlow) : null
    })),
    crossoverCount: crossovers.length,
    crossovers,
    distanceToSlow,
    endDate,
    fastPeriod: fast,
    maxDrawdown: maxDrawdown(rows.map((row) => row.close)),
    movingAverageSpread,
    rows,
    slowPeriod: slow,
    startDate,
    trend,
    realData: marketBars.length > 0
  };
}

function analyzeEtfReturn(input: ReturnInput, marketBars: MarketPriceBar[]) {
  const symbol = cleanTicker(input.symbol) || "VTI";
  const { startDate, endDate } = normalizeRange(input.startDate, input.endDate);
  const initialInvestment = clampNumber(input.initialInvestment, 0, 100000000, 10000);
  const periodicInvestment = clampNumber(input.periodicInvestment, 0, 10000000, 0);
  const expenseRatio = clampNumber(input.annualExpenseRatio, 0, 3, 0.03) / 100;
  const series = marketBars.length ? barsToPriceSeries(marketBars).filter((bar) => bar.date >= startDate && bar.date <= endDate) : generatePriceSeries(symbol, startDate, endDate, "etf", 0);
  const annualYield = 0.012 + (hashTicker(symbol) % 260) / 10000;
  const firstPrice = series[0]?.close ?? 1;
  let shares = firstPrice > 0 ? initialInvestment / firstPrice : 0;
  let contributed = initialInvestment;
  let cashDividends = 0;
  let dividends = 0;
  let lastContributionKey = contributionPeriodKey(parseIsoDate(series[0]?.date ?? startDate), input.contributionFrequency);
  let lastDividendQuarter = dividendQuarterKey(parseIsoDate(series[0]?.date ?? startDate));
  const events: ReturnEvent[] = [];

  const chartRows = series.map((row, index) => {
    const date = parseIsoDate(row.date);
    const contributionKey = contributionPeriodKey(date, input.contributionFrequency);
    if (index > 0 && input.contributionFrequency !== "none" && periodicInvestment > 0 && contributionKey && contributionKey !== lastContributionKey) {
      shares += periodicInvestment / row.close;
      contributed += periodicInvestment;
      events.push({ date: row.date, label: "Contribution", amount: periodicInvestment });
      lastContributionKey = contributionKey;
    }

    const sourceDividend = marketBars.length ? marketBars.find((bar) => bar.date === row.date)?.dividend ?? 0 : 0;
    const dividendQuarter = dividendQuarterKey(date);
    if (index > 0 && ((sourceDividend > 0) || (!marketBars.length && dividendQuarter && dividendQuarter !== lastDividendQuarter))) {
      const dividendAmount = sourceDividend > 0 ? shares * sourceDividend : shares * row.close * (annualYield / 4);
      dividends += dividendAmount;
      if (input.dividendMode === "reinvest") {
        shares += dividendAmount / row.close;
      } else if (input.dividendMode === "cash") {
        cashDividends += dividendAmount;
      }
      if (input.dividendMode !== "ignore") {
        events.push({ date: row.date, label: input.dividendMode === "reinvest" ? "Dividend reinvested" : "Dividend cash", amount: dividendAmount });
      }
      lastDividendQuarter = dividendQuarter || lastDividendQuarter;
    }

    const dailyExpense = expenseRatio / 252;
    if (dailyExpense > 0 && shares > 0) {
      shares = Math.max(0, shares * (1 - dailyExpense));
    }

    const value = shares * row.close + cashDividends;
    return {
      date: row.date,
      label: formatMonthDay(row.date),
      value: round(value),
      contributed: round(contributed)
    };
  });

  const endingValue = chartRows.at(-1)?.value ?? 0;
  const gainLoss = endingValue - contributed;
  const totalReturn = contributed > 0 ? gainLoss / contributed : 0;
  const years = Math.max(1 / 365, daysBetween(startDate, endDate) / 365.25);
  const annualizedReturn = contributed > 0 && endingValue > 0 ? Math.pow(endingValue / contributed, 1 / years) - 1 : 0;

  return {
    annualizedReturn,
    chartRows,
    contributed,
    dividends,
    endingValue,
    endDate,
    events,
    gainLoss,
    maxDrawdown: maxDrawdown(chartRows.map((row) => row.value)),
    realData: marketBars.length > 0,
    startDate,
    totalReturn
  };
}

function generatePriceSeries(symbol: string, startDate: string, endDate: string, assetKind: AssetKind, warmupTradingDays: number) {
  const seed = hashTicker(symbol);
  const start = parseIsoDate(startDate);
  const warmupStart = addDays(start, -Math.ceil(warmupTradingDays * 1.65 + 8));
  const dates = tradingDays(toIsoDate(warmupStart), endDate);
  const base = assetKind === "etf" ? 70 + (seed % 220) : 25 + (seed % 420);
  const drift = assetKind === "etf" ? 0.00022 + ((seed % 17) - 7) / 100000 : 0.00028 + ((seed % 23) - 10) / 85000;
  const volatility = assetKind === "etf" ? 0.009 + (seed % 35) / 10000 : 0.014 + (seed % 85) / 10000;
  let close = base;

  return dates.map((date, index) => {
    const wave = Math.sin((index + (seed % 29)) / 9) * 0.46;
    const cycle = Math.cos((index * 1.7 + (seed % 41)) / 17) * 0.34;
    const shock = Math.sin((index + seed) / 37) * 0.2;
    const dailyReturn = drift + volatility * (wave + cycle + shock) / 3;
    close = Math.max(3, close * (1 + dailyReturn));
    return { date, close: round(close) };
  });
}

function barsToPriceSeries(bars: MarketPriceBar[]) {
  return bars
    .map((bar) => ({ date: bar.date, close: round(bar.adjusted_close || bar.close) }))
    .filter((bar) => isValidDate(bar.date) && bar.close > 0)
    .sort((left, right) => left.date.localeCompare(right.date));
}

function applyMovingAverages(
  generated: Array<{ date: string; close: number }>,
  displayStart: string,
  fastPeriod: number,
  slowPeriod: number
): PricePoint[] {
  const closes: number[] = [];
  return generated.map((point) => {
    closes.push(point.close);
    const maFast = closes.length >= fastPeriod ? average(closes.slice(-fastPeriod)) : null;
    const maSlow = closes.length >= slowPeriod ? average(closes.slice(-slowPeriod)) : null;
    return {
      date: point.date,
      close: point.close,
      maFast: maFast ? round(maFast) : null,
      maSlow: maSlow ? round(maSlow) : null
    };
  }).filter((point) => point.date >= displayStart);
}

function findCrossovers(rows: PricePoint[]): Crossover[] {
  const crossovers: Crossover[] = [];
  let lastTrendIndex = 0;
  for (let index = 1; index < rows.length; index += 1) {
    const previous = rows[index - 1];
    const current = rows[index];
    if (!previous.maFast || !previous.maSlow || !current.maFast || !current.maSlow) continue;
    const previousDiff = previous.maFast - previous.maSlow;
    const currentDiff = current.maFast - current.maSlow;
    if (previousDiff <= 0 && currentDiff > 0) {
      crossovers.push({
        date: current.date,
        type: "Bullish",
        close: current.close,
        fast: current.maFast,
        slow: current.maSlow,
        priorTrendDays: Math.max(1, index - lastTrendIndex)
      });
      lastTrendIndex = index;
    }
    if (previousDiff >= 0 && currentDiff < 0) {
      crossovers.push({
        date: current.date,
        type: "Bearish",
        close: current.close,
        fast: current.maFast,
        slow: current.maSlow,
        priorTrendDays: Math.max(1, index - lastTrendIndex)
      });
      lastTrendIndex = index;
    }
  }
  return crossovers;
}

function marketHistoryRequest(activeTool: ToolId, etfInput: MovingAverageInput, stockInput: MovingAverageInput, returnInput: ReturnInput) {
  if (activeTool === "stock-dma") {
    const { startDate, endDate } = normalizeRange(stockInput.startDate, stockInput.endDate);
    const warmupDays = Math.ceil(Math.max(stockInput.fastPeriod, stockInput.slowPeriod, 100) * 1.65 + 12);
    return {
      symbol: cleanTicker(stockInput.symbol) || "AAPL",
      startDate: toIsoDate(addDays(parseIsoDate(startDate), -warmupDays)),
      endDate
    };
  }
  if (activeTool === "etf-return") {
    const { startDate, endDate } = normalizeRange(returnInput.startDate, returnInput.endDate);
    return {
      symbol: cleanTicker(returnInput.symbol) || "VTI",
      startDate,
      endDate
    };
  }
  const { startDate, endDate } = normalizeRange(etfInput.startDate, etfInput.endDate);
  const warmupDays = Math.ceil(Math.max(etfInput.fastPeriod, etfInput.slowPeriod, 200) * 1.65 + 12);
  return {
    symbol: cleanTicker(etfInput.symbol) || "SPY",
    startDate: toIsoDate(addDays(parseIsoDate(startDate), -warmupDays)),
    endDate
  };
}

function contributionPeriodKey(date: Date, frequency: ContributionFrequency) {
  const year = date.getUTCFullYear();
  const month = date.getUTCMonth();
  if (frequency === "monthly") return `${year}-${month}`;
  if (frequency === "quarterly") return `${year}-Q${Math.floor(month / 3)}`;
  if (frequency === "annually") return `${year}`;
  return "";
}

function dividendQuarterKey(date: Date) {
  const month = date.getUTCMonth();
  const day = date.getUTCDate();
  if (![2, 5, 8, 11].includes(month) || day < 14) return "";
  return `${date.getUTCFullYear()}-Q${Math.floor(month / 3)}`;
}

function dividendModeLabel(mode: DividendMode) {
  if (mode === "reinvest") return "Reinvested into shares";
  if (mode === "cash") return "Held as cash";
  return "Excluded from return";
}

function returnSeriesLabel(name: string) {
  if (name === "value") return "Portfolio value";
  if (name === "contributed") return "Contributed capital";
  return name;
}

function seriesLabel(name: string, fastLabel: string, slowLabel: string) {
  if (name === "close") return "Close";
  if (name === "fast") return fastLabel;
  if (name === "slow") return slowLabel;
  return name;
}

function normalizeRange(startDate: string, endDate: string) {
  const start = isValidDate(startDate) ? startDate : defaultStartDate;
  const end = isValidDate(endDate) ? endDate : defaultEndDate;
  return start <= end ? { startDate: start, endDate: end } : { startDate: end, endDate: start };
}

function tradingDays(startDate: string, endDate: string) {
  const days: string[] = [];
  let current = parseIsoDate(startDate);
  const end = parseIsoDate(endDate);
  while (current <= end) {
    const weekday = current.getUTCDay();
    if (weekday !== 0 && weekday !== 6) days.push(toIsoDate(current));
    current = addDays(current, 1);
  }
  return days.length ? days : [startDate];
}

function average(values: number[]) {
  return values.reduce((total, value) => total + value, 0) / Math.max(1, values.length);
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

function hashTicker(symbol: string) {
  let hash = 2166136261;
  for (let index = 0; index < symbol.length; index += 1) {
    hash ^= symbol.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash);
}

function cleanTicker(value: string) {
  return value.toUpperCase().replace(/[^A-Z0-9.-]/g, "").slice(0, 10);
}

function parseIsoDate(value: string) {
  return new Date(`${value}T12:00:00.000Z`);
}

function toIsoDate(value: Date) {
  return value.toISOString().slice(0, 10);
}

function addDays(value: Date, days: number) {
  const next = new Date(value);
  next.setUTCDate(next.getUTCDate() + days);
  return next;
}

function daysBetween(startDate: string, endDate: string) {
  return Math.max(1, Math.round((parseIsoDate(endDate).getTime() - parseIsoDate(startDate).getTime()) / 86400000));
}

function isValidDate(value: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(parseIsoDate(value).getTime());
}

function clampInteger(value: number, min: number, max: number, fallback: number) {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, Math.round(value)));
}

function clampNumber(value: number, min: number, max: number, fallback: number) {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, value));
}

function round(value: number) {
  return Math.round(value * 100) / 100;
}

function currency(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

function currencyCents(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function compactCurrency(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function percent(value: number) {
  return new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 2 }).format(value);
}

function latestDateTime(values: string[]) {
  return values.sort((left, right) => right.localeCompare(left))[0] ?? "";
}

function formatDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}

function formatShortDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatDate(value: string) {
  if (!value || !isValidDate(value)) return "N/A";
  return parseIsoDate(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

function formatMonthDay(value: string) {
  if (!value || !isValidDate(value)) return "";
  return parseIsoDate(value).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}
