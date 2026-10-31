"use client";

import { Activity, AlertTriangle, CandlestickChart, Gauge, Loader2, Pause, Play, RefreshCw, Search, ShieldCheck, Target } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

const IBKR_API = process.env.NEXT_PUBLIC_IBKR_API_URL ?? "http://localhost:8002";
const REFRESH_MS = 15 * 60_000;
const MAX_CHECKS = 13;

type BreakawayStock = {
  symbol: string;
  name: string;
  sector: string;
  as_of: string;
  price: number;
  change: number;
  change_pct: number | null;
  score: number;
  prev_score: number | null;
  fresh: boolean;
  tier: string;
  rank: number;
  sector_rank: number;
  sector_size: number;
  checks_firing: number;
  checks: string[];
  trend: string;
  above_200d: boolean;
  rel_volume: number | null;
  range_pct: number | null;
  gap_pct: number | null;
  new_high: boolean;
  pct_from_high: number | null;
  atr_pct: number | null;
  ret_1d: number | null;
  ret_1w: number | null;
  ret_1m: number | null;
  ret_3m: number | null;
  ret_6m: number | null;
  ret_12m: number | null;
  strength_vs_market: number | null;
  sparkline: number[];
  live: boolean;
};

type BreakawaySector = {
  rank: number;
  sector: string;
  members: number;
  avg_score: number;
  pct_trending_up: number;
  pct_above_200d: number;
  avg_ret_1d: number | null;
  avg_ret_1w: number | null;
  avg_ret_1m: number | null;
  avg_ret_3m: number | null;
  top: Array<{ symbol: string; score: number }>;
};

type ListKey = "fresh" | "gainers" | "losers" | "unusual_volume" | "new_highs" | "most_volatile" | "gap_ups" | "squeeze";

type BreakawayScan = {
  generated_at: string;
  market_date: string | null;
  ibkr_connected: boolean;
  live_quotes: number;
  universe_count: number;
  scored_count: number;
  market: {
    benchmark: string;
    ret_1d: number | null;
    ret_1w: number | null;
    ret_1m: number | null;
    ret_3m: number | null;
    pct_trending_up: number | null;
    pct_above_200d: number | null;
    tiers: Record<string, number>;
  };
  stocks: BreakawayStock[];
  lists: Record<ListKey, string[]>;
  sectors: BreakawaySector[];
  warnings: string[];
};

type ChartPoint = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema21: number | null;
  sma50: number | null;
  sma200: number | null;
  bb_upper: number | null;
  bb_lower: number | null;
  rs: number | null;
  score: number | null;
};

type BreakawayDetail = BreakawayStock & {
  breakdown: Array<{ component: string; points: number | null; range: string; detail: string; scored: boolean }>;
  check_details: Array<{ key: string; label: string; group: string; description: string; fired: boolean; count_60d: number }>;
  score_history: Array<{ date: string; score: number }>;
  chart: ChartPoint[];
  peers: Array<{ symbol: string; name: string; score: number; tier: string; change_pct: number | null; sector_rank: number; trend: string }>;
  trade_plan: { entry: number; stop: number; target: number; atr: number };
};

type View = "ranked" | ListKey | "sectors";

const VIEWS: Array<{ id: View; label: string }> = [
  { id: "ranked", label: "Ranked" },
  { id: "fresh", label: "Fresh" },
  { id: "gainers", label: "Gainers" },
  { id: "losers", label: "Losers" },
  { id: "unusual_volume", label: "Unusual volume" },
  { id: "new_highs", label: "New highs" },
  { id: "most_volatile", label: "Most volatile" },
  { id: "gap_ups", label: "Gap ups" },
  { id: "squeeze", label: "Squeeze setups" },
  { id: "sectors", label: "Industries" }
];

const TIERS = ["Exceptional", "Excellent", "Above average", "Average", "Below average", "Poor"];

export function BreakawayTool() {
  const [scan, setScan] = useState<BreakawayScan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [view, setView] = useState<View>("ranked");
  const [query, setQuery] = useState("");
  const [tierFilter, setTierFilter] = useState("All");
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<BreakawayDetail | null>(null);
  const [detailError, setDetailError] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`${IBKR_API}/api/breakaway/scan`, { cache: "no-store" });
      if (!response.ok) throw new Error(`IBKR backend returned ${response.status}`);
      const next = (await response.json()) as BreakawayScan;
      setScan(next);
      setError("");
      setSelected((current) => current || next.stocks[0]?.symbol || "");
    } catch (err) {
      setError(err instanceof Error ? `Could not load Breakaway scan: ${err.message}` : "Could not load Breakaway scan");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, REFRESH_MS);
    return () => window.clearInterval(id);
  }, [autoRefresh, load]);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    fetch(`${IBKR_API}/api/breakaway/stock/${encodeURIComponent(selected)}`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error(`IBKR backend returned ${response.status}`);
        return (await response.json()) as BreakawayDetail;
      })
      .then((next) => {
        if (cancelled) return;
        setDetail(next);
        setDetailError("");
      })
      .catch((err) => {
        if (!cancelled) setDetailError(err instanceof Error ? err.message : "Could not load stock detail");
      });
    return () => {
      cancelled = true;
    };
  }, [selected, scan?.generated_at]);

  const bySymbol = useMemo(() => new Map((scan?.stocks ?? []).map((stock) => [stock.symbol, stock])), [scan]);

  const visible = useMemo(() => {
    if (!scan) return [];
    const needle = query.trim().toUpperCase();
    let rows: BreakawayStock[];
    if (needle) {
      rows = scan.stocks.filter((stock) => stock.symbol.includes(needle) || stock.name.toUpperCase().includes(needle));
    } else if (view === "ranked" || view === "sectors") {
      rows = scan.stocks;
    } else {
      rows = scan.lists[view].map((symbol) => bySymbol.get(symbol)).filter((stock): stock is BreakawayStock => Boolean(stock));
    }
    return tierFilter === "All" ? rows : rows.filter((stock) => stock.tier === tierFilter);
  }, [bySymbol, query, scan, tierFilter, view]);

  const showSectors = view === "sectors" && !query.trim();

  return (
    <>
      <section className="dashboard-panel breakout-head">
        <div>
          <p className="eyebrow">Breakaway · Nasdaq-100 + SOXL / TQQQ / UPRO</p>
          <h2>Every Nasdaq-100 stock plus SOXL, TQQQ and UPRO ranked by one Quality Score, refreshed every 15 minutes.</h2>
          <div className="breakout-source-line">
            <span><Activity size={14} /> IBKR cached daily bars + live quotes</span>
            <span><Gauge size={14} /> 14 chart checks · trend · run-up · persistence</span>
            <span><Target size={14} /> Shared with Breakout Scanner — no extra IBKR calls</span>
          </div>
        </div>
        <div className="breakout-actions">
          {scan && (
            <span className={scan.ibkr_connected ? "status-pill" : "risk-pill"}>
              {scan.ibkr_connected ? "IBKR live" : "IBKR offline"} · {scan.live_quotes}/{scan.scored_count} live quotes
            </span>
          )}
          <span className="status-pill">{scan ? `Updated ${formatTime(scan.generated_at)}` : "Loading"}</span>
          <button className="ghost-button" type="button" onClick={() => setAutoRefresh((value) => !value)}>
            {autoRefresh ? <Pause size={16} /> : <Play size={16} />}
            {autoRefresh ? "Auto 15m" : "Paused"}
          </button>
          <button className="ghost-button" type="button" onClick={() => void load()} disabled={loading}>
            {loading ? <Loader2 size={16} className="spin-icon" /> : <RefreshCw size={16} />}
            Refresh
          </button>
        </div>
      </section>

      {error && <div className="error">{error}</div>}

      {scan && <MarketPanel scan={scan} />}

      <section className="dashboard-panel bk-controls">
        <div className="bk-tabs" role="tablist">
          {VIEWS.map((item) => {
            const count = item.id === "ranked" ? scan?.stocks.length : item.id === "sectors" ? scan?.sectors.length : scan?.lists[item.id].length;
            return (
              <button key={item.id} type="button" role="tab" aria-selected={view === item.id} className={view === item.id ? "active" : ""} onClick={() => setView(item.id)}>
                {item.label}
                {count != null && <small>{count}</small>}
              </button>
            );
          })}
        </div>
        <div className="bk-filter-row">
          <label className="bk-search">
            <Search size={15} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search Nasdaq-100, SOXL, TQQQ, UPRO" aria-label="Search stocks" />
          </label>
          <div className="bk-tier-chips">
            {["All", ...TIERS].map((label) => (
              <button key={label} type="button" className={tierFilter === label ? "active" : ""} onClick={() => setTierFilter(label)}>
                {label}
                {label !== "All" && scan?.market.tiers[label] ? <small>{scan.market.tiers[label]}</small> : null}
              </button>
            ))}
          </div>
        </div>
      </section>

      <div className="bk-workbench">
        <section className="bk-list">
          {!scan && loading ? (
            <div className="dashboard-panel breakout-loading-row"><Loader2 size={18} className="spin-icon" /> Scoring Nasdaq-100 from IBKR cache</div>
          ) : showSectors ? (
            <SectorTable sectors={scan?.sectors ?? []} onPick={(symbol) => setSelected(symbol)} />
          ) : visible.length ? (
            <div className="bk-card-grid">
              {visible.map((stock) => (
                <StockCard key={stock.symbol} stock={stock} active={stock.symbol === selected} onClick={() => setSelected(stock.symbol)} />
              ))}
            </div>
          ) : (
            <div className="dashboard-panel breakout-loading-row">No stocks match this list right now.</div>
          )}
        </section>

        <section className="dashboard-panel bk-detail">
          {detailError && <div className="error">{detailError}</div>}
          {detail && detail.symbol === selected ? (
            <StockDetail detail={detail} onPick={(symbol) => setSelected(symbol)} />
          ) : selected ? (
            <div className="breakout-empty-detail"><Loader2 size={24} className="spin-icon" /><p>Loading {selected}</p></div>
          ) : (
            <div className="breakout-empty-detail"><CandlestickChart size={32} /><h2>Select a stock</h2></div>
          )}
        </section>
      </div>

      <section className="dashboard-panel breakout-notice">
        <ShieldCheck size={18} />
        <p>Educational research only. Quality Scores are not buy or sell instructions; verify earnings, news, liquidity and portfolio fit before acting.</p>
      </section>

      {scan?.warnings.length ? (
        <section className="dashboard-panel breakout-warning-panel">
          <div className="panel-header">
            <h2>Data notes</h2>
            <AlertTriangle size={18} />
          </div>
          <div className="breakout-warning-list">
            {scan.warnings.map((warning) => <p key={warning}>{warning}</p>)}
          </div>
        </section>
      ) : null}
    </>
  );
}

function MarketPanel({ scan }: { scan: BreakawayScan }) {
  const m = scan.market;
  const total = Object.values(m.tiers).reduce((sum, value) => sum + value, 0) || 1;
  return (
    <section className="dashboard-panel bk-market">
      <div className="bk-market-stats">
        <MarketStat label={`${m.benchmark} · 1D`} value={pct(m.ret_1d)} tone={m.ret_1d} />
        <MarketStat label="1W" value={pct(m.ret_1w)} tone={m.ret_1w} />
        <MarketStat label="1M" value={pct(m.ret_1m)} tone={m.ret_1m} />
        <MarketStat label="3M" value={pct(m.ret_3m)} tone={m.ret_3m} />
        <MarketStat label="Trending up" value={pct(m.pct_trending_up, 0)} />
        <MarketStat label="Above 200-day" value={pct(m.pct_above_200d, 0)} />
      </div>
      <div className="bk-tier-bar" aria-label="Quality Score tier distribution">
        {TIERS.map((label) => m.tiers[label] ? (
          <span key={label} className={`tier-${tierSlug(label)}`} style={{ width: `${(m.tiers[label] / total) * 100}%` }} title={`${label}: ${m.tiers[label]}`}>
            {m.tiers[label]}
          </span>
        ) : null)}
      </div>
      <p className="fine-print">{scan.scored_count} of {scan.universe_count} symbols scored · bars as of {scan.market_date ?? "N/A"}</p>
    </section>
  );
}

function MarketStat({ label, value, tone }: { label: string; value: string; tone?: number | null }) {
  return (
    <div>
      <span>{label}</span>
      <strong className={tone == null ? "" : tone >= 0 ? "bk-up" : "bk-down"}>{value}</strong>
    </div>
  );
}

function StockCard({ stock, active, onClick }: { stock: BreakawayStock; active: boolean; onClick: () => void }) {
  return (
    <button type="button" className={`bk-card${active ? " active" : ""}`} onClick={onClick}>
      <div className="bk-card-top">
        <span className="bk-rank">#{stock.rank}</span>
        <div className="bk-card-name">
          <strong>{stock.symbol}</strong>
          <small>{stock.name}</small>
        </div>
        <ScoreBadge score={stock.score} tier={stock.tier} />
      </div>
      <div className="bk-card-price">
        <strong>{money(stock.price)}</strong>
        <span className={(stock.change_pct ?? 0) >= 0 ? "bk-up" : "bk-down"}>{signedPct(stock.change_pct)}</span>
        {stock.live && <em>live</em>}
        {stock.fresh && <em className="bk-fresh">{stock.prev_score != null && stock.score > stock.prev_score ? "▲" : "▼"} fresh</em>}
      </div>
      <Sparkline values={stock.sparkline} />
      <CheckBar firing={stock.checks_firing} />
      <div className="bk-card-meta">
        <span>#{stock.sector_rank} of {stock.sector_size} · {stock.sector}</span>
        <span className={trendClass(stock.trend)}>{stock.trend}</span>
      </div>
    </button>
  );
}

function ScoreBadge({ score, tier, large }: { score: number; tier: string; large?: boolean }) {
  return (
    <span className={`bk-score tier-${tierSlug(tier)}${large ? " large" : ""}`} title={tier}>
      Q{score}
      {large && <small>{tier}</small>}
    </span>
  );
}

function CheckBar({ firing }: { firing: number }) {
  return (
    <div className="bk-checkbar" title={`${firing} of ${MAX_CHECKS} chart checks firing`}>
      <div>
        {Array.from({ length: MAX_CHECKS }, (_, i) => <span key={i} className={i < firing ? "lit" : ""} />)}
      </div>
      <small>{firing} of {MAX_CHECKS}</small>
    </div>
  );
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const d = values.map((value, i) => `${i ? "L" : "M"}${((i / (values.length - 1)) * 100).toFixed(2)} ${(28 - ((value - min) / Math.max(max - min, 0.0001)) * 26).toFixed(2)}`).join(" ");
  const up = values[values.length - 1] >= values[0];
  return (
    <svg className="bk-spark" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">
      <path d={d} fill="none" stroke={up ? "#0f766e" : "#dc2626"} strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function SectorTable({ sectors, onPick }: { sectors: BreakawaySector[]; onPick: (symbol: string) => void }) {
  return (
    <div className="dashboard-panel bk-sector-panel">
      <div className="panel-header">
        <h2>Industries ranked by average Quality Score</h2>
        <p className="fine-print">Industries with 4+ Nasdaq-100 names.</p>
      </div>
      <div className="bk-table-scroll">
        <table className="bk-table">
          <thead>
            <tr><th>#</th><th>Industry</th><th>Avg Q</th><th>Trending up</th><th>Above 200d</th><th>1D</th><th>1W</th><th>1M</th><th>3M</th><th>Top scores</th></tr>
          </thead>
          <tbody>
            {sectors.map((sector) => (
              <tr key={sector.sector}>
                <td>{sector.rank}</td>
                <td><strong>{sector.sector}</strong><small>{sector.members} names</small></td>
                <td>{sector.avg_score.toFixed(1)}</td>
                <td>{pct(sector.pct_trending_up, 0)}</td>
                <td>{pct(sector.pct_above_200d, 0)}</td>
                <td className={tone(sector.avg_ret_1d)}>{signedPct(sector.avg_ret_1d)}</td>
                <td className={tone(sector.avg_ret_1w)}>{signedPct(sector.avg_ret_1w)}</td>
                <td className={tone(sector.avg_ret_1m)}>{signedPct(sector.avg_ret_1m)}</td>
                <td className={tone(sector.avg_ret_3m)}>{signedPct(sector.avg_ret_3m)}</td>
                <td>
                  <div className="bk-top-chips">
                    {sector.top.map((item) => <button type="button" key={item.symbol} onClick={() => onPick(item.symbol)}>{item.symbol} <b>Q{item.score}</b></button>)}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StockDetail({ detail, onPick }: { detail: BreakawayDetail; onPick: (symbol: string) => void }) {
  const groups = useMemo(() => {
    const map = new Map<string, BreakawayDetail["check_details"]>();
    detail.check_details.forEach((check) => map.set(check.group, [...(map.get(check.group) ?? []), check]));
    return [...map.entries()];
  }, [detail.check_details]);

  return (
    <div className="bk-detail-body">
      <div className="bk-detail-head">
        <div>
          <span className="eyebrow">{detail.sector} · #{detail.sector_rank} of {detail.sector_size} · rank #{detail.rank}</span>
          <h2>{detail.symbol} <small>{detail.name}</small></h2>
          <p>
            <strong>{money(detail.price)}</strong>{" "}
            <span className={(detail.change_pct ?? 0) >= 0 ? "bk-up" : "bk-down"}>{signedMoney(detail.change)} ({signedPct(detail.change_pct)})</span>{" "}
            <span className={trendClass(detail.trend)}>{detail.trend}</span>
          </p>
        </div>
        <ScoreBadge score={detail.score} tier={detail.tier} large />
      </div>

      <div className="breakout-detail-stats bk-detail-stats">
        <div><span>Strength vs market (3M)</span><strong className={tone(detail.strength_vs_market)}>{signedPct(detail.strength_vs_market)}</strong></div>
        <div><span>From 52W high</span><strong>{signedPct(detail.pct_from_high)}</strong></div>
        <div><span>Rel volume</span><strong>{detail.rel_volume == null ? "N/A" : `${detail.rel_volume.toFixed(2)}x`}</strong></div>
        <div><span>ATR %</span><strong>{pct(detail.atr_pct)}</strong></div>
        <div><span>6M / 12M</span><strong>{signedPct(detail.ret_6m, 0)} / {signedPct(detail.ret_12m, 0)}</strong></div>
      </div>

      <DetailChart points={detail.chart} symbol={detail.symbol} />

      <div className="bk-detail-grid">
        <div>
          <h3>Score, added up</h3>
          <table className="bk-table bk-breakdown">
            <tbody>
              {detail.breakdown.map((part) => (
                <tr key={part.component} className={part.scored ? "" : "unscored"}>
                  <td><strong>{part.component}</strong><small>{part.detail}</small></td>
                  <td>{part.range}</td>
                  <td className="bk-points">{part.points == null ? "—" : part.points > 0 ? `+${part.points}` : part.points}</td>
                </tr>
              ))}
              <tr className="bk-total"><td><strong>Quality Score</strong></td><td /><td className="bk-points">Q{detail.score}</td></tr>
            </tbody>
          </table>
        </div>
        <div>
          <h3>Score history</h3>
          <ScoreHistory history={detail.score_history} />
          <p className="fine-print">Limited to the ~1 year of IBKR daily bars in the cache (200-day warm-up).</p>
        </div>
      </div>

      <h3>Chart checks · {detail.checks_firing} of {MAX_CHECKS} firing</h3>
      <div className="bk-check-groups">
        {groups.map(([group, checks]) => (
          <div key={group}>
            <span className="bk-group-label">{group}</span>
            {checks.map((check) => (
              <div key={check.key} className={`bk-check${check.fired ? " fired" : ""}`} title={check.description}>
                <strong>{check.label}</strong>
                <small>{check.description}</small>
                <em>{check.count_60d}/60 sessions</em>
              </div>
            ))}
          </div>
        ))}
      </div>

      <div className="bk-detail-grid">
        <TradePlan plan={detail.trade_plan} key={detail.symbol} />
        <div>
          <h3>Peers in {detail.sector}</h3>
          <table className="bk-table bk-peers">
            <tbody>
              {detail.peers.map((peer) => (
                <tr key={peer.symbol} className={peer.symbol === detail.symbol ? "current" : ""} onClick={() => onPick(peer.symbol)}>
                  <td>{peer.sector_rank}</td>
                  <td><strong>{peer.symbol}</strong><small>{peer.name}</small></td>
                  <td><ScoreBadge score={peer.score} tier={peer.tier} /></td>
                  <td className={tone(peer.change_pct)}>{signedPct(peer.change_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

type ChartStyle = "candles" | "hollow" | "heikin" | "line";
type LowerPane = "volume" | "strength" | "score";
const RANGES: Array<{ label: string; bars: number }> = [
  { label: "1M", bars: 21 },
  { label: "3M", bars: 63 },
  { label: "6M", bars: 126 },
  { label: "1Y", bars: 252 }
];

function DetailChart({ points, symbol }: { points: ChartPoint[]; symbol: string }) {
  const [range, setRange] = useState(126);
  const [style, setStyle] = useState<ChartStyle>("candles");
  const [lower, setLower] = useState<LowerPane>("volume");
  const [overlays, setOverlays] = useState({ ema21: true, sma50: true, sma200: true, bb: false });

  const candles = useMemo(() => (style === "heikin" ? heikinAshi(points) : points), [points, style]);
  const rows = candles.slice(-range);
  if (rows.length < 2) return <div className="breakout-empty-detail">No chart bars cached.</div>;

  const width = 760, height = 360, left = 8, right = 58, top = 12, priceBottom = 240, lowerTop = 262, lowerBottom = 336;
  const plotWidth = width - left - right;
  const step = plotWidth / Math.max(rows.length - 1, 1);
  const candleWidth = Math.max(2, Math.min(9, step * 0.6));
  const priceValues = rows.flatMap((row) => [row.high, row.low, overlays.ema21 ? row.ema21 : null, overlays.sma50 ? row.sma50 : null, overlays.sma200 ? row.sma200 : null, overlays.bb ? row.bb_upper : null, overlays.bb ? row.bb_lower : null].filter(isNumber));
  const min = Math.min(...priceValues), max = Math.max(...priceValues);
  const pad = (max - min) * 0.05 || max * 0.01;
  const lo = min - pad, hi = max + pad;
  const x = (i: number) => left + i * step;
  const y = (value: number) => top + ((hi - value) / (hi - lo)) * (priceBottom - top);

  const lowerValues = rows.map((row) => (lower === "volume" ? row.volume : lower === "strength" ? row.rs : row.score));
  const lowerNums = lowerValues.filter(isNumber);
  const lMin = lower === "volume" ? 0 : Math.min(...lowerNums);
  const lMax = Math.max(...lowerNums, lMin + 0.0001);
  const ly = (value: number) => lowerBottom - ((value - lMin) / Math.max(lMax - lMin, 0.0001)) * (lowerBottom - lowerTop);
  const ticks = [0, 0.5, 1].map((r) => hi - (hi - lo) * r);

  return (
    <div className="bk-chart">
      <div className="bk-chart-controls">
        <div className="bk-seg">{RANGES.map((r) => <button key={r.label} type="button" className={range === r.bars ? "active" : ""} onClick={() => setRange(r.bars)}>{r.label}</button>)}</div>
        <div className="bk-seg">
          {(["candles", "hollow", "heikin", "line"] as ChartStyle[]).map((s) => (
            <button key={s} type="button" className={style === s ? "active" : ""} onClick={() => setStyle(s)}>{s === "heikin" ? "Heikin Ashi" : s[0].toUpperCase() + s.slice(1)}</button>
          ))}
        </div>
        <div className="bk-seg">
          {([["ema21", "21 EMA"], ["sma50", "50"], ["sma200", "200"], ["bb", "Bollinger"]] as Array<[keyof typeof overlays, string]>).map(([key, label]) => (
            <button key={key} type="button" className={overlays[key] ? "active" : ""} onClick={() => setOverlays((cur) => ({ ...cur, [key]: !cur[key] }))}>{label}</button>
          ))}
        </div>
        <div className="bk-seg">
          {([["volume", "Volume"], ["strength", "Strength vs market"], ["score", "Score"]] as Array<[LowerPane, string]>).map(([key, label]) => (
            <button key={key} type="button" className={lower === key ? "active" : ""} onClick={() => setLower(key)}>{label}</button>
          ))}
        </div>
      </div>
      <svg className="breakout-candle-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${symbol} price chart`}>
        <rect x={left} y={top} width={plotWidth} height={priceBottom - top} rx="8" fill="rgba(9, 24, 21, 0.72)" stroke="#17352d" />
        <rect x={left} y={lowerTop} width={plotWidth} height={lowerBottom - lowerTop} rx="8" fill="rgba(9, 24, 21, 0.72)" stroke="#17352d" />
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={left} x2={left + plotWidth} y1={y(tick)} y2={y(tick)} stroke="#17352d" strokeDasharray="3 4" />
            <text x={width - 4} y={y(tick) + 4} textAnchor="end" className="breakout-candle-axis-text">{money(tick)}</text>
          </g>
        ))}
        {[0, Math.floor((rows.length - 1) / 2), rows.length - 1].map((i) => (
          <text key={i} x={x(i)} y={height - 6} textAnchor={i === 0 ? "start" : i === rows.length - 1 ? "end" : "middle"} className="breakout-candle-axis-text">{shortDate(rows[i].date)}</text>
        ))}
        {overlays.bb && <path d={path(rows, "bb_upper", x, y)} fill="none" stroke="#64748b" strokeDasharray="4 3" />}
        {overlays.bb && <path d={path(rows, "bb_lower", x, y)} fill="none" stroke="#64748b" strokeDasharray="4 3" />}
        {style === "line" ? (
          <path d={path(rows, "close", x, y)} fill="none" stroke="#2dd4bf" strokeWidth="1.8" />
        ) : rows.map((row, i) => {
          const up = row.close >= row.open;
          const color = up ? "#2dd4bf" : "#fb7185";
          const hollow = style === "hollow" && up;
          const bodyTop = Math.min(y(row.open), y(row.close));
          return (
            <g key={`${row.date}-${i}`}>
              <title>{`${row.date} O ${money(row.open)} H ${money(row.high)} L ${money(row.low)} C ${money(row.close)}`}</title>
              <line x1={x(i)} x2={x(i)} y1={y(row.high)} y2={y(row.low)} stroke={color} strokeWidth="1.1" />
              <rect x={x(i) - candleWidth / 2} y={bodyTop} width={candleWidth} height={Math.max(1.5, Math.abs(y(row.open) - y(row.close)))} fill={hollow ? "#0b1417" : color} stroke={color} rx="1" />
            </g>
          );
        })}
        {overlays.ema21 && <path d={path(rows, "ema21", x, y)} fill="none" stroke="#38bdf8" strokeWidth="1.3" />}
        {overlays.sma50 && <path d={path(rows, "sma50", x, y)} fill="none" stroke="#f59e0b" strokeWidth="1.3" />}
        {overlays.sma200 && <path d={path(rows, "sma200", x, y)} fill="none" stroke="#c084fc" strokeWidth="1.3" />}
        {lower === "volume"
          ? rows.map((row, i) => <rect key={`v-${i}`} x={x(i) - candleWidth / 2} y={ly(row.volume)} width={candleWidth} height={Math.max(1, lowerBottom - ly(row.volume))} fill={row.close >= row.open ? "#2dd4bf" : "#fb7185"} opacity="0.4" />)
          : <path d={lowerValues.reduce<string>((acc, value, i) => (isNumber(value) ? `${acc}${acc && isNumber(lowerValues[i - 1]) ? "L" : "M"}${x(i).toFixed(1)} ${ly(value).toFixed(1)} ` : acc), "")} fill="none" stroke={lower === "strength" ? "#facc15" : "#2dd4bf"} strokeWidth="1.5" />}
        <text x={left + 8} y={lowerTop + 14} className="breakout-candle-axis-text">{lower === "volume" ? "Volume" : lower === "strength" ? "Strength vs Nasdaq-100 EW" : "Quality Score"}</text>
      </svg>
    </div>
  );
}

function ScoreHistory({ history }: { history: Array<{ date: string; score: number }> }) {
  if (history.length < 2) return <p className="fine-print">Not enough history yet.</p>;
  const scores = history.map((h) => h.score);
  const min = Math.min(...scores, 0), max = Math.max(...scores, 13);
  const w = 320, h = 110;
  const x = (i: number) => (i / (history.length - 1)) * w;
  const y = (v: number) => 6 + ((max - v) / Math.max(max - min, 1)) * (h - 12);
  return (
    <svg className="bk-history" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Quality Score history">
      {[20, 15, 11, 6, 0].filter((v) => v >= min && v <= max).map((v) => (
        <g key={v}><line x1={0} x2={w} y1={y(v)} y2={y(v)} stroke="var(--line)" strokeDasharray="3 3" /><text x={w - 2} y={y(v) - 2} textAnchor="end">Q{v}</text></g>
      ))}
      <path d={history.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(p.score).toFixed(1)}`).join(" ")} fill="none" stroke="var(--forest)" strokeWidth="2" />
      <text x={0} y={h - 1}>{shortDate(history[0].date)}</text>
      <text x={w} y={h - 1} textAnchor="end">{shortDate(history[history.length - 1].date)}</text>
    </svg>
  );
}

function TradePlan({ plan }: { plan: BreakawayDetail["trade_plan"] }) {
  const [entry, setEntry] = useState(plan.entry);
  const [stop, setStop] = useState(plan.stop);
  const [target, setTarget] = useState(plan.target);
  const [risk, setRisk] = useState(1000);
  const riskPerShare = entry - stop;
  const shares = riskPerShare > 0 ? Math.floor(risk / riskPerShare) : 0;
  const reward = (target - entry) * shares;
  return (
    <div className="bk-plan">
      <h3>Trade plan</h3>
      <div className="bk-plan-grid">
        <label><span>Buy price</span><input type="number" step="0.01" value={entry} onChange={(e) => setEntry(Number(e.target.value))} /></label>
        <label><span>Stop</span><input type="number" step="0.01" value={stop} onChange={(e) => setStop(Number(e.target.value))} /></label>
        <label><span>Target</span><input type="number" step="0.01" value={target} onChange={(e) => setTarget(Number(e.target.value))} /></label>
        <label><span>Risk budget $</span><input type="number" step="100" value={risk} onChange={(e) => setRisk(Number(e.target.value))} /></label>
      </div>
      <div className="breakout-detail-stats">
        <div><span>Shares</span><strong>{shares.toLocaleString()}</strong></div>
        <div><span>Position</span><strong>{money(shares * entry)}</strong></div>
        <div><span>Reward : risk</span><strong>{riskPerShare > 0 ? `${((target - entry) / riskPerShare).toFixed(2)}R` : "N/A"}</strong></div>
        <div><span>Reward $</span><strong>{money(reward)}</strong></div>
      </div>
      <p className="fine-print">Defaults: stop at the tighter of 2× ATR ({money(plan.atr)}) or the 10-session low; target at 2R.</p>
    </div>
  );
}

function heikinAshi(points: ChartPoint[]): ChartPoint[] {
  const out: ChartPoint[] = [];
  points.forEach((p, i) => {
    const close = (p.open + p.high + p.low + p.close) / 4;
    const open = i === 0 ? (p.open + p.close) / 2 : (out[i - 1].open + out[i - 1].close) / 2;
    out.push({ ...p, open, close, high: Math.max(p.high, open, close), low: Math.min(p.low, open, close) });
  });
  return out;
}

function path(rows: ChartPoint[], key: keyof ChartPoint, x: (i: number) => number, y: (v: number) => number) {
  let d = "";
  let drawing = false;
  rows.forEach((row, i) => {
    const value = row[key];
    if (!isNumber(value)) {
      drawing = false;
      return;
    }
    d += `${drawing ? "L" : "M"}${x(i).toFixed(1)} ${y(value).toFixed(1)} `;
    drawing = true;
  });
  return d.trim();
}

function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function tierSlug(tier: string) {
  return tier.toLowerCase().replace(/\s+/g, "-");
}

function trendClass(trend: string) {
  return `bk-trend ${trend === "Trending up" ? "up" : trend === "Trending down" ? "down" : "flat"}`;
}

function tone(value: number | null | undefined) {
  if (value == null) return "";
  return value >= 0 ? "bk-up" : "bk-down";
}

function money(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function signedMoney(value: number) {
  return `${value >= 0 ? "+" : "−"}${money(Math.abs(value))}`;
}

function pct(value: number | null | undefined, digits = 1) {
  return value == null ? "N/A" : `${(value * 100).toFixed(digits)}%`;
}

function signedPct(value: number | null | undefined, digits = 1) {
  return value == null ? "N/A" : `${value >= 0 ? "+" : "−"}${Math.abs(value * 100).toFixed(digits)}%`;
}

function shortDate(value: string) {
  const parsed = new Date(`${value}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatTime(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "N/A" : parsed.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit" });
}
