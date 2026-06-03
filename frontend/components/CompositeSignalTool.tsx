"use client";

import { Activity, AlertTriangle, Bell, CheckCircle2, Loader2, RefreshCw, ShieldCheck, TrendingDown, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const IBKR_API = process.env.NEXT_PUBLIC_IBKR_API_URL ?? "http://localhost:8002";
const TRACKING_STORAGE_KEY = "financeos_composite_signal_positions";
const TRADE_STORAGE_KEY = "financeos_composite_signal_trades";
const NOTIFIED_STORAGE_KEY = "financeos_composite_signal_notifications";

type CompositeComponents = {
  sma10: boolean;
  momentum12: boolean;
  rsi6: boolean;
};

type CompositeSignalRow = {
  symbol: string;
  underlying: string;
  signal: "BUY" | "SELL" | string;
  score: number;
  price: number;
  as_of_date: string;
  sma10: number;
  momentum_12m_pct: number;
  rsi6: number;
  components: CompositeComponents;
  history: CompositeHistoryPoint[];
  month_count: number;
  execution_note: string;
};

type CompositeHistoryPoint = {
  date: string;
  price: number;
  sma10: number;
  momentum_12m_pct: number;
  rsi6: number;
  score: number;
  signal: "BUY" | "SELL" | string;
  components: CompositeComponents;
};

type CompositeSignalResponse = {
  generated_at: string;
  data_source: string;
  signals: CompositeSignalRow[];
  warnings: string[];
};

type TrackedPosition = {
  symbol: string;
  underlying: string;
  accepted_signal: string;
  accepted_score: number;
  accepted_at: string;
  shares: string;
  purchase_price: string;
  purchase_date: string;
  account_type: "taxable" | "tax_deferred";
};

type QuoteRow = {
  symbol: string;
  price?: number | null;
  source?: string | null;
};

type TradeEntry = {
  id: string;
  symbol: string;
  underlying: string;
  trade_date: string;
  shares: string;
  price: string;
  account_type: "taxable" | "tax_deferred";
};

type PositionSummary = {
  symbol: string;
  underlying: string;
  shares: number;
  averagePrice: number;
  cost: number;
  currentPrice: number;
  value: number;
  gain: number;
  gainPct: number;
  tradeCount: number;
};

type CompositeView = "signals" | "positions" | "trades";

export function CompositeSignalTool() {
  const [result, setResult] = useState<CompositeSignalResponse | null>(null);
  const [selectedChartSymbol, setSelectedChartSymbol] = useState("SOXL");
  const [trackedPositions, setTrackedPositions] = useState<TrackedPosition[]>(loadStoredTrackedPositions);
  const [tradeEntries, setTradeEntries] = useState<TradeEntry[]>(loadStoredTradeEntries);
  const [view, setView] = useState<CompositeView>("signals");
  const [quotes, setQuotes] = useState<Record<string, QuoteRow>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notificationMessage, setNotificationMessage] = useState("");

  const buyCount = useMemo(() => result?.signals.filter((row) => row.signal === "BUY").length ?? 0, [result]);
  const tradeSharesBySymbol = useMemo(() => {
    const shares: Record<string, number> = {};
    tradeEntries.forEach((trade) => {
      shares[trade.symbol] = (shares[trade.symbol] ?? 0) + numericInput(trade.shares);
    });
    return shares;
  }, [tradeEntries]);
  const tradePositions = useMemo(() => buildTradePositions(tradeEntries, quotes), [quotes, tradeEntries]);
  const positionSummary = useMemo(
    () => tradePositions.reduce(
      (summary, position) => {
        return {
          cost: summary.cost + position.cost,
          value: summary.value + position.value,
          gain: summary.gain + position.gain,
        };
      },
      { cost: 0, value: 0, gain: 0 }
    ),
    [tradePositions]
  );
  const selectedChart = useMemo(
    () => result?.signals.find((row) => row.symbol === selectedChartSymbol) ?? result?.signals[0] ?? null,
    [result, selectedChartSymbol]
  );

  useEffect(() => {
    void loadSignals();
  }, []);

  useEffect(() => {
    window.localStorage.setItem(TRACKING_STORAGE_KEY, JSON.stringify(trackedPositions));
  }, [trackedPositions]);

  useEffect(() => {
    window.localStorage.setItem(TRADE_STORAGE_KEY, JSON.stringify(tradeEntries));
  }, [tradeEntries]);

  useEffect(() => {
    const symbols = new Set([
      ...trackedPositions.map((position) => position.symbol),
      ...tradeEntries.map((trade) => trade.symbol),
    ]);
    if (symbols.size) void loadQuotes([...symbols]);
  }, [trackedPositions, tradeEntries]);

  useEffect(() => {
    if (!result || !trackedPositions.length) return;
    maybeNotifySignalChanges(result, trackedPositions);
  }, [result, trackedPositions, tradeSharesBySymbol]);

  async function loadSignals() {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${IBKR_API}/api/composite-signal`, { cache: "no-store" });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(detail?.detail ?? `Composite signal request failed (${response.status})`);
      }
      const data = await response.json() as CompositeSignalResponse;
      setResult(data);
      setSelectedChartSymbol((current) => data.signals.some((row) => row.symbol === current) ? current : data.signals[0]?.symbol ?? "SOXL");
      void loadQuotes(data.signals.map((row) => row.symbol));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load composite signals from IBKR.");
    } finally {
      setLoading(false);
    }
  }

  async function loadQuotes(symbols: string[]) {
    try {
      const response = await fetch(`${IBKR_API}/api/quotes?symbols=${symbols.join(",")}`, { cache: "no-store" });
      if (!response.ok) return;
      const data = await response.json() as { tickers: QuoteRow[] };
      setQuotes(Object.fromEntries(data.tickers.map((row) => [row.symbol, row])));
    } catch {
      setQuotes({});
    }
  }

  function acceptSignal(row: CompositeSignalRow) {
    setTrackedPositions((current) => {
      if (current.some((item) => item.symbol === row.symbol)) return current;
      return [
        ...current,
        {
          symbol: row.symbol,
          underlying: row.underlying,
          accepted_signal: row.signal,
          accepted_score: row.score,
          accepted_at: row.as_of_date,
          shares: "",
          purchase_price: "",
          purchase_date: todayISO(),
          account_type: "tax_deferred",
        },
      ];
    });
    setView("positions");
  }

  function updateTrackedPosition(symbol: string, field: keyof TrackedPosition, value: string) {
    setTrackedPositions((current) => current.map((position) => (
      position.symbol === symbol ? { ...position, [field]: value } : position
    )));
  }

  function removeTrackedPosition(symbol: string) {
    setTrackedPositions((current) => current.filter((position) => position.symbol !== symbol));
  }

  function addTrade(position: TrackedPosition) {
    const shares = numericInput(position.shares);
    const price = numericInput(position.purchase_price);
    if (shares <= 0 || price <= 0) return;
    setTradeEntries((current) => [
      ...current,
      {
        id: `${position.symbol}-${Date.now()}`,
        symbol: position.symbol,
        underlying: position.underlying,
        trade_date: position.purchase_date || todayISO(),
        shares: position.shares,
        price: position.purchase_price,
        account_type: position.account_type,
      },
    ]);
    setTrackedPositions((current) => current.map((item) => (
      item.symbol === position.symbol ? { ...item, shares: "", purchase_price: "", purchase_date: todayISO() } : item
    )));
    setView("trades");
  }

  function removeTrade(id: string) {
    setTradeEntries((current) => current.filter((trade) => trade.id !== id));
  }

  async function requestNotifications() {
    if (typeof window === "undefined" || !("Notification" in window)) {
      setNotificationMessage("Browser notifications are not available in this environment.");
      return;
    }
    const permission = await Notification.requestPermission();
    setNotificationMessage(permission === "granted" ? "Notifications enabled for signal changes." : "Notifications were not enabled.");
  }

  function maybeNotifySignalChanges(nextResult: CompositeSignalResponse, positions: TrackedPosition[]) {
    if (typeof window === "undefined" || !("Notification" in window) || Notification.permission !== "granted") return;
    const sent = new Set(JSON.parse(window.localStorage.getItem(NOTIFIED_STORAGE_KEY) || "[]") as string[]);
    const nextSent = new Set(sent);
    const bySymbol = Object.fromEntries(nextResult.signals.map((row) => [row.symbol, row]));

    positions.forEach((position) => {
      const latest = bySymbol[position.symbol];
      const shares = (tradeSharesBySymbol[position.symbol] ?? 0) + numericInput(position.shares);
      if (!latest || shares <= 0) return;
      const notifyKey = `${position.symbol}-${latest.as_of_date}-${latest.signal}`;
      if (sent.has(notifyKey)) return;
      if (latest.signal !== position.accepted_signal || latest.signal === "SELL") {
        new Notification(`${position.symbol} composite signal: ${latest.signal}`, {
          body: `Latest score ${latest.score}/3 from ${latest.underlying}. Execute at next month's open if this changes your position plan.`,
        });
        nextSent.add(notifyKey);
      }
    });

    window.localStorage.setItem(NOTIFIED_STORAGE_KEY, JSON.stringify(Array.from(nextSent).slice(-50)));
  }

  return (
    <div className="composite-signal-tool">
      <section className="dashboard-panel composite-signal-head">
        <div>
          <p className="eyebrow">Composite Signal Algorithm</p>
          <h2>Monthly trend signal for SOXL, TQQQ, and UPRO.</h2>
          <p>
            Uses IBKR historical bars for SOXX, QQQ, and SPY, then evaluates 10-month SMA,
            12-month momentum, and RSI(6) hysteresis at month-end.
          </p>
        </div>
        <div className="composite-actions">
          <span className={error ? "risk-pill" : "status-pill"}>
            <Activity size={14} /> {result ? `${buyCount}/${result.signals.length} buy` : "IBKR monthly bars"}
          </span>
          <button className="primary-button" type="button" onClick={loadSignals} disabled={loading}>
            {loading ? <Loader2 size={16} className="spin-icon" /> : <RefreshCw size={16} />}
            Refresh
          </button>
        </div>
      </section>

      <section className="dashboard-panel composite-rule-panel">
        <div className="composite-rule-grid">
          <RuleCard title="10-Month SMA" accent="blue" detail="Bullish when index close is at or above its rolling 10-month average." />
          <RuleCard title="12M Momentum" accent="pink" detail="Bullish when the latest close is above the close 12 months earlier." />
          <RuleCard title="RSI(6)" accent="orange" detail="Bullish above 52, bearish below 42, and holds prior state inside the band." />
          <RuleCard title="Composite" accent="green" detail="Score 2 or 3 is BUY; score 0 or 1 is SELL or stay in cash equivalents." />
        </div>
      </section>

      {error && (
        <section className="dashboard-panel composite-warning">
          <AlertTriangle size={18} />
          <p>{error}</p>
        </section>
      )}

      <section className="dashboard-panel composite-view-panel">
        <div className="composite-view-tabs">
          <button type="button" className={view === "signals" ? "active" : ""} onClick={() => setView("signals")}>
            Current Signals
            <span>{result?.signals.length ?? 0}</span>
          </button>
          <button type="button" className={view === "positions" ? "active" : ""} onClick={() => setView("positions")}>
            Accepted Positions
            <span>{trackedPositions.length}</span>
          </button>
          <button type="button" className={view === "trades" ? "active" : ""} onClick={() => setView("trades")}>
            Trades
            <span>{tradeEntries.length}</span>
          </button>
        </div>
      </section>

      {view === "signals" && (
      <>
      <section className="dashboard-panel composite-signal-table-panel">
        <div className="panel-header">
          <div>
            <h2>Current Signals</h2>
            <p className="fine-print">
              {result ? `${formatDateTime(result.generated_at)} · ${result.data_source}` : "Loading IBKR composite signal data"}
            </p>
          </div>
        </div>

        {loading && !result ? (
          <div className="composite-loading"><Loader2 size={20} className="spin-icon" /> Loading composite signals</div>
        ) : result?.signals.length ? (
          <div className="composite-signal-grid">
            {result.signals.map((row) => <SignalCard row={row} key={row.symbol} onAccept={acceptSignal} tracked={trackedPositions.some((position) => position.symbol === row.symbol)} />)}
          </div>
        ) : (
          <div className="composite-loading">No composite signal data loaded yet.</div>
        )}
      </section>

      {selectedChart && (
        <section className="dashboard-panel composite-chart-panel">
          <div className="panel-header">
            <div>
              <h2>Monthly Signal Chart</h2>
              <p className="fine-print">{selectedChart.underlying} month-end close, SMA10, and composite score.</p>
            </div>
            <div className="composite-chart-tabs">
              {result?.signals.map((row) => (
                <button
                  type="button"
                  className={row.symbol === selectedChart.symbol ? "active" : ""}
                  key={row.symbol}
                  onClick={() => setSelectedChartSymbol(row.symbol)}
                >
                  {row.symbol}
                </button>
              ))}
            </div>
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={selectedChart.history.map((point) => ({ ...point, label: formatMonth(point.date) }))} margin={{ top: 10, right: 18, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="price" tick={{ fontSize: 11 }} width={64} />
              <YAxis yAxisId="score" orientation="right" domain={[0, 3]} ticks={[0, 1, 2, 3]} tick={{ fontSize: 11 }} width={34} />
              <Tooltip formatter={(value: number, name: string) => [name === "score" ? value.toFixed(0) : value.toFixed(2), name]} />
              <Bar yAxisId="score" dataKey="score" name="score" fill="#8b5cf6" radius={[3, 3, 0, 0]} />
              <Line yAxisId="price" type="monotone" dataKey="price" name="close" stroke="#0f766e" strokeWidth={2} dot={false} />
              <Line yAxisId="price" type="monotone" dataKey="sma10" name="SMA10" stroke="#2563eb" strokeWidth={1.6} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </section>
      )}
      </>
      )}

      {view === "positions" && (
      <section className="dashboard-panel composite-tracking-panel">
        <div className="panel-header">
          <div>
            <h2>Accepted Positions</h2>
            <p className="fine-print">Enter shares and buy price, then add a trade. Trades roll up in the Trades tab.</p>
          </div>
          <button className="secondary-button" type="button" onClick={requestNotifications}>
            <Bell size={16} /> Enable notifications
          </button>
        </div>
        {notificationMessage && <p className="fine-print">{notificationMessage}</p>}
        {trackedPositions.length ? (
          <div className="composite-tracking-table">
            <div className="composite-tracking-row header">
              <span>Symbol</span><span>Accepted</span><span>Latest</span><span>Shares</span><span>Buy Price</span><span>Buy Date</span><span>Account</span><span>Current</span><span>Status</span><span>Actions</span>
            </div>
            {trackedPositions.map((position) => {
              const latest = result?.signals.find((row) => row.symbol === position.symbol);
              const quote = quotes[position.symbol];
              const shares = numericInput(position.shares);
              const buyPrice = numericInput(position.purchase_price);
              const currentPrice = quote?.price ?? 0;
              const heldShares = (tradeSharesBySymbol[position.symbol] ?? 0) + shares;
              const status = latest?.signal === "SELL" && heldShares > 0 ? "Exit next open" : latest?.signal === "BUY" ? "Aligned" : "Review";
              const canAddTrade = shares > 0 && buyPrice > 0;

              return (
                <div className="composite-tracking-row" key={position.symbol}>
                  <strong>{position.symbol}<small>{position.underlying}</small></strong>
                  <span>{position.accepted_signal} {position.accepted_score}/3<small>{formatDate(position.accepted_at)}</small></span>
                  <span>{latest ? `${latest.signal} ${latest.score}/3` : position.accepted_signal}</span>
                  <input aria-label={`${position.symbol} shares`} placeholder="Shares" value={position.shares} inputMode="decimal" onChange={(event) => updateTrackedPosition(position.symbol, "shares", event.target.value)} />
                  <input aria-label={`${position.symbol} buy price`} placeholder="Buy price" value={position.purchase_price} inputMode="decimal" onChange={(event) => updateTrackedPosition(position.symbol, "purchase_price", event.target.value)} />
                  <input aria-label={`${position.symbol} buy date`} type="date" value={position.purchase_date} onChange={(event) => updateTrackedPosition(position.symbol, "purchase_date", event.target.value)} />
                  <select value={position.account_type} onChange={(event) => updateTrackedPosition(position.symbol, "account_type", event.target.value)}>
                    <option value="tax_deferred">Tax-deferred</option>
                    <option value="taxable">Taxable</option>
                  </select>
                  <span>{currentPrice ? currency(currentPrice) : "Quote pending"}</span>
                  <span className={status === "Aligned" ? "aligned" : "review"}>{status}</span>
                  <span className="composite-row-actions">
                    <button type="button" disabled={!canAddTrade} onClick={() => addTrade(position)}>Add trade</button>
                    <button type="button" onClick={() => removeTrackedPosition(position.symbol)}>Remove</button>
                  </span>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="composite-loading">No accepted positions yet. Use Accept signal on a card above.</div>
        )}
      </section>
      )}

      {view === "trades" && (
      <section className="dashboard-panel composite-tracking-panel">
        <div className="panel-header">
          <div>
            <h2>Trades</h2>
            <p className="fine-print">All composite trades, grouped into positions with total shares, average price, and gain or loss.</p>
          </div>
        </div>
        {tradeEntries.length ? (
          <>
            <div className="composite-position-summary">
              <span>Cost <strong>{currency(positionSummary.cost)}</strong></span>
              <span>Value <strong>{currency(positionSummary.value)}</strong></span>
              <span className={positionSummary.gain >= 0 ? "aligned" : "review"}>
                Gain / loss <strong>{currency(positionSummary.gain)}</strong>
              </span>
            </div>

            <div className="composite-position-table">
              <div className="composite-position-row header">
                <span>Position</span><span>Total shares</span><span>Average price</span><span>Current price</span><span>Market value</span><span>Gain / Loss</span><span>Trades</span>
              </div>
              {tradePositions.map((position) => (
                <div className="composite-position-row" key={position.symbol}>
                  <strong>{position.symbol}<small>{position.underlying}</small></strong>
                  <span>{formatShares(position.shares)}</span>
                  <span>{currency(position.averagePrice)}</span>
                  <span>{position.currentPrice ? currency(position.currentPrice) : "Quote pending"}</span>
                  <span>{currency(position.value)}</span>
                  <span className={position.gain >= 0 ? "aligned" : "review"}>{currency(position.gain)} ({percent(position.gainPct)})</span>
                  <span>{position.tradeCount}</span>
                </div>
              ))}
            </div>

            <div className="composite-trade-entry-table">
              <div className="composite-trade-entry-row header">
                <span>Date</span><span>Symbol</span><span>Shares</span><span>Price</span><span>Cost</span><span>Account</span><span />
              </div>
              {tradeEntries.map((trade) => {
                const shares = numericInput(trade.shares);
                const price = numericInput(trade.price);
                return (
                  <div className="composite-trade-entry-row" key={trade.id}>
                    <span>{formatDate(trade.trade_date)}</span>
                    <strong>{trade.symbol}<small>{trade.underlying}</small></strong>
                    <span>{formatShares(shares)}</span>
                    <span>{currency(price)}</span>
                    <span>{currency(shares * price)}</span>
                    <span>{trade.account_type === "tax_deferred" ? "Tax-deferred" : "Taxable"}</span>
                    <button type="button" onClick={() => removeTrade(trade.id)}>Remove</button>
                  </div>
                );
              })}
            </div>
          </>
        ) : (
          <div className="composite-loading">No trades recorded yet. Add shares and buy price from Accepted Positions.</div>
        )}
      </section>
      )}

      <section className="dashboard-panel composite-note-panel">
        <ShieldCheck size={18} />
        <p>
          Signal timing follows the source algorithm: evaluate at month-end close and execute at the following month&apos;s opening price.
          This is educational research only, not trading advice.
        </p>
      </section>

      {result?.warnings.length ? (
        <section className="dashboard-panel composite-warning">
          <AlertTriangle size={18} />
          <div>
            {result.warnings.map((warning) => <p key={warning}>{warning}</p>)}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function RuleCard({ title, detail, accent }: { title: string; detail: string; accent: "blue" | "pink" | "orange" | "green" }) {
  return (
    <article className={`composite-rule-card ${accent}`}>
      <strong>{title}</strong>
      <span>{detail}</span>
    </article>
  );
}

function SignalCard({ row, onAccept, tracked }: { row: CompositeSignalRow; onAccept: (row: CompositeSignalRow) => void; tracked: boolean }) {
  const isBuy = row.signal === "BUY";
  return (
    <article className={`composite-signal-card ${isBuy ? "buy" : "sell"}`}>
      <div className="composite-card-head">
        <div>
          <span>{row.underlying} signal for</span>
          <h2>{row.symbol}</h2>
        </div>
        <strong>{isBuy ? <TrendingUp size={18} /> : <TrendingDown size={18} />}{row.signal}</strong>
      </div>

      <div className="composite-score-ring">
        <span>Score</span>
        <strong>{row.score}/3</strong>
      </div>

      <div className="composite-component-list">
        <Component label="SMA10" active={row.components.sma10} value={`Close ${currency(row.price)} vs SMA ${currency(row.sma10)}`} />
        <Component label="MOM12" active={row.components.momentum12} value={`${percent(row.momentum_12m_pct)} over 12 months`} />
        <Component label="RSI6" active={row.components.rsi6} value={`RSI ${row.rsi6.toFixed(1)}`} />
      </div>

      <p className="fine-print">As of {formatDate(row.as_of_date)} · {row.month_count} monthly closes</p>
      <button className={tracked ? "secondary-button" : "primary-button"} type="button" onClick={() => onAccept(row)} disabled={tracked}>
        <CheckCircle2 size={16} /> {tracked ? "Tracking" : "Accept signal"}
      </button>
    </article>
  );
}

function Component({ label, active, value }: { label: string; active: boolean; value: string }) {
  return (
    <div className={active ? "active" : ""}>
      {active ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function currency(value: number) {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`;
}

function percent(value: number) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function formatShares(value: number) {
  return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function formatDate(value: string) {
  const parsed = new Date(`${value}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function formatMonth(value: string) {
  const parsed = new Date(`${value}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function numericInput(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function loadStoredTrackedPositions() {
  if (typeof window === "undefined") return [];
  const saved = window.localStorage.getItem(TRACKING_STORAGE_KEY);
  if (!saved) return [];
  try {
    return JSON.parse(saved) as TrackedPosition[];
  } catch {
    window.localStorage.removeItem(TRACKING_STORAGE_KEY);
    return [];
  }
}

function loadStoredTradeEntries() {
  if (typeof window === "undefined") return [];
  const saved = window.localStorage.getItem(TRADE_STORAGE_KEY);
  if (!saved) return [];
  try {
    return JSON.parse(saved) as TradeEntry[];
  } catch {
    window.localStorage.removeItem(TRADE_STORAGE_KEY);
    return [];
  }
}

function buildTradePositions(trades: TradeEntry[], quotes: Record<string, QuoteRow>): PositionSummary[] {
  const grouped = new Map<string, PositionSummary>();

  trades.forEach((trade) => {
    const shares = numericInput(trade.shares);
    const price = numericInput(trade.price);
    if (shares <= 0 || price <= 0) return;
    const existing = grouped.get(trade.symbol) ?? {
      symbol: trade.symbol,
      underlying: trade.underlying,
      shares: 0,
      averagePrice: 0,
      cost: 0,
      currentPrice: quotes[trade.symbol]?.price ?? 0,
      value: 0,
      gain: 0,
      gainPct: 0,
      tradeCount: 0,
    };
    existing.shares += shares;
    existing.cost += shares * price;
    existing.tradeCount += 1;
    grouped.set(trade.symbol, existing);
  });

  return [...grouped.values()].map((position) => {
    const currentPrice = quotes[position.symbol]?.price ?? 0;
    const value = position.shares * currentPrice;
    const gain = currentPrice > 0 ? value - position.cost : 0;
    return {
      ...position,
      averagePrice: position.shares > 0 ? position.cost / position.shares : 0,
      currentPrice,
      value,
      gain,
      gainPct: position.cost > 0 ? gain / position.cost * 100 : 0,
    };
  });
}

function formatDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}
