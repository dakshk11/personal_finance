"use client";

import { Activity, AlertTriangle, CandlestickChart, Download, Layers, Loader2, Pause, Play, RefreshCw, Search, ShieldCheck, Target } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

const IBKR_API = process.env.NEXT_PUBLIC_IBKR_API_URL ?? "http://localhost:8002";
const REFRESH_MS = 15 * 60_000;
const STAGES = [1, 2, 3, 4] as const;
const STAGE_NAMES: Record<number, string> = { 1: "Basing", 2: "Advancing", 3: "Topping", 4: "Declining" };

type StageStock = {
  symbol: string;
  name: string;
  sector: string;
  as_of: string;
  price: number;
  change_pct: number | null;
  stage: number;
  stage_name: string;
  prev_stage: number | null;
  new_stage: boolean;
  weeks: number;
  weeks_capped: boolean;
  score: number;
  score_delta: number | null;
  checks: string[];
  mansfield: number | null;
  ma30_slope: number | null;
  pct_from_ma30: number | null;
  pct_from_high: number | null;
  ret_1w: number | null;
  ret_13w: number | null;
  ret_26w: number | null;
  rel_13w: number | null;
  rs_pct: number | null;
  ind_pct: number | null;
  ind_rank: number;
  atr: number | null;
  atr_pct: number | null;
  atr_ext: number | null;
  tags: string[];
};

type Industry = {
  rank: number;
  industry: string;
  members: number;
  ind_pct: number | null;
  rel_13w: number | null;
  avg_score: number;
  avg_mansfield: number | null;
  ret_1w: number | null;
  ret_13w: number | null;
  stage_counts: Record<string, number>;
  pct_stage2: number;
  leaders: Array<{ symbol: string; stage: number; rs_pct: number | null }>;
};

type StageScan = {
  generated_at: string;
  market_date: string | null;
  ibkr_connected: boolean;
  live_quotes: number;
  universe_count: number;
  scored_count: number;
  max_score: number;
  market: {
    benchmark: string;
    stage: number | null;
    stage_label: string;
    weeks: number | null;
    ret_1d: number | null;
    ret_1w: number | null;
    ret_1m: number | null;
    ret_3m: number | null;
    stage_counts: Record<string, number>;
  };
  stocks: StageStock[];
  industries: Industry[];
  warnings: string[];
};

type WeeklyPoint = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ma10: number | null;
  ma30: number | null;
  mansfield: number | null;
  stage: number | null;
};

type StageDetail = StageStock & {
  check_details: Array<{ key: string; label: string; description: string; passed: boolean }>;
  stage_history: Array<{ stage: number; name: string; start: string; end: string; weeks: number }>;
  chart: WeeklyPoint[];
  peers: Array<{ symbol: string; name: string; stage: number; weeks: number; score: number; rs_pct: number | null; change_pct: number | null }>;
};

type View = "overview" | "stages" | "industries";
type Filters = { industry: string; indPct: number; score: number; stage: string; weeks: number; atrExt: string };
type SortKey = "score" | "score_delta" | "ind_pct" | "rs_pct" | "weeks" | "atr_ext" | "atr_pct" | "rel_13w" | "symbol" | "change_pct";

/** The Overview screen: early Stage 2, strong trend, leading industry, not stretched. */
const OVERVIEW: Filters = { industry: "All", indPct: 0, score: 7, stage: "2", weeks: 10, atrExt: "le4" };
const CLEAR: Filters = { industry: "All", indPct: 0, score: 0, stage: "All", weeks: 0, atrExt: "All" };

export function StageDeskTool() {
  const [scan, setScan] = useState<StageScan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [view, setView] = useState<View>("overview");
  const [filters, setFilters] = useState<Filters>(OVERVIEW);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "score", desc: true });
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<StageDetail | null>(null);
  const [detailError, setDetailError] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`${IBKR_API}/api/stage-desk/scan`, { cache: "no-store" });
      if (!response.ok) throw new Error(`IBKR backend returned ${response.status}`);
      const next = (await response.json()) as StageScan;
      setScan(next);
      setError("");
      setSelected((current) => current || next.stocks[0]?.symbol || "");
    } catch (err) {
      setError(err instanceof Error ? `Could not load Stage Desk: ${err.message}` : "Could not load Stage Desk");
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
    fetch(`${IBKR_API}/api/stage-desk/stock/${encodeURIComponent(selected)}`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error(`IBKR backend returned ${response.status}`);
        return (await response.json()) as StageDetail;
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

  const industries = useMemo(() => [...new Set((scan?.stocks ?? []).map((s) => s.sector))].sort(), [scan]);

  const rows = useMemo(() => {
    if (!scan) return [];
    const needle = query.trim().toUpperCase();
    const filtered = needle
      ? scan.stocks.filter((s) => s.symbol.includes(needle) || s.name.toUpperCase().includes(needle))
      : scan.stocks.filter((s) => passes(s, filters));
    const dir = sort.desc ? -1 : 1;
    return [...filtered].sort((a, b) => {
      const av = a[sort.key], bv = b[sort.key];
      if (typeof av === "string" || typeof bv === "string") return String(av).localeCompare(String(bv)) * dir;
      return ((av ?? -Infinity) - (bv ?? -Infinity)) * dir || a.symbol.localeCompare(b.symbol);
    });
  }, [filters, query, scan, sort]);

  const isOverview = JSON.stringify(filters) === JSON.stringify(OVERVIEW);
  const setFilter = <K extends keyof Filters>(key: K, value: Filters[K]) => setFilters((cur) => ({ ...cur, [key]: value }));
  const toggleSort = (key: SortKey) => setSort((cur) => ({ key, desc: cur.key === key ? !cur.desc : key !== "symbol" && key !== "atr_ext" && key !== "weeks" }));

  return (
    <>
      <section className="dashboard-panel breakout-head">
        <div>
          <p className="eyebrow">Stage Desk · Nasdaq-100</p>
          <h2>A short daily list of Nasdaq-100 stocks early in a Stage 2 uptrend, before they get stretched.</h2>
          <div className="breakout-source-line">
            <span><Activity size={14} /> IBKR cached daily bars + live quotes</span>
            <span><Layers size={14} /> Weinstein stages · trend score · industry RS · ATR extension</span>
            <span><Target size={14} /> Shared with Breakout Scanner and Breakaway — no extra IBKR calls</span>
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
          {([["overview", "Overview screen"], ["stages", "Stage analysis"], ["industries", "Industries"]] as Array<[View, string]>).map(([id, label]) => (
            <button key={id} type="button" role="tab" aria-selected={view === id} className={view === id ? "active" : ""} onClick={() => setView(id)}>
              {label}
              {id === "overview" && scan && <small>{rows.length}</small>}
              {id === "industries" && scan && <small>{scan.industries.length}</small>}
            </button>
          ))}
        </div>
        {view === "overview" && (
          <div className="sd-filters">
            <label className="bk-search">
              <Search size={15} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search Nasdaq-100" aria-label="Search stocks" />
            </label>
            <Select label="Industry" value={filters.industry} onChange={(v) => setFilter("industry", v)} options={[["All", "All industries"], ...industries.map((i) => [i, i] as [string, string])]} />
            <Select label="Ind %ile" value={String(filters.indPct)} onChange={(v) => setFilter("indPct", Number(v))} options={[["0", "All ind %ile"], ["50", "Ind ≥ 50"], ["70", "Ind ≥ 70"], ["90", "Ind ≥ 90"]]} />
            <Select label="Score" value={String(filters.score)} onChange={(v) => setFilter("score", Number(v))} options={[["0", "All scores"], ["5", "Score ≥ 5"], ["7", "Score ≥ 7"], ["9", "Score ≥ 9"]]} />
            <Select label="Stage" value={filters.stage} onChange={(v) => setFilter("stage", v)} options={[["All", "All stages"], ["new2", "New Stage 2"], ...STAGES.map((s) => [String(s), `Stage ${s} · ${STAGE_NAMES[s]}`] as [string, string])]} />
            <Select label="Weeks" value={String(filters.weeks)} onChange={(v) => setFilter("weeks", Number(v))} options={[["0", "All weeks"], ["4", "≤ 4 weeks"], ["10", "≤ 10 weeks"], ["20", "≤ 20 weeks"]]} />
            <Select label="ATR Ext" value={filters.atrExt} onChange={(v) => setFilter("atrExt", v)} options={[["All", "All ATR ext"], ["le2", "≤ 2 ATR"], ["le4", "≤ 4 ATR"], ["gt4", "> 4 ATR (stretched)"]]} />
            <button className="ghost-button" type="button" onClick={() => setFilters(OVERVIEW)} disabled={isOverview}>Overview defaults</button>
            <button className="ghost-button" type="button" onClick={() => setFilters(CLEAR)}>Clear</button>
            <button className="ghost-button" type="button" onClick={() => exportCsv(rows)} disabled={!rows.length}><Download size={15} /> Export CSV</button>
          </div>
        )}
      </section>

      <div className="sd-workbench">
        <section className="sd-main">
          {!scan && loading ? (
            <div className="dashboard-panel breakout-loading-row"><Loader2 size={18} className="spin-icon" /> Staging Nasdaq-100 from IBKR cache</div>
          ) : !scan ? null : view === "industries" ? (
            <IndustryTable industries={scan.industries} onPick={setSelected} />
          ) : view === "stages" ? (
            <StageBoard stocks={scan.stocks} selected={selected} onPick={setSelected} />
          ) : (
            <ScreenTable rows={rows} total={scan.scored_count} selected={selected} sort={sort} onSort={toggleSort} onPick={setSelected} marketDate={scan.market_date} />
          )}
        </section>

        <section className="dashboard-panel bk-detail">
          {detailError && <div className="error">{detailError}</div>}
          {detail && detail.symbol === selected ? (
            <StockDetail detail={detail} maxScore={scan?.max_score ?? 10} onPick={setSelected} />
          ) : selected ? (
            <div className="breakout-empty-detail"><Loader2 size={24} className="spin-icon" /><p>Loading {selected}</p></div>
          ) : (
            <div className="breakout-empty-detail"><CandlestickChart size={32} /><h2>Select a stock</h2></div>
          )}
        </section>
      </div>

      <section className="dashboard-panel breakout-notice">
        <ShieldCheck size={18} />
        <p>Educational research only. Stages and scores are not buy or sell instructions; verify earnings, news, liquidity and portfolio fit before acting.</p>
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

function passes(s: StageStock, f: Filters) {
  if (f.industry !== "All" && s.sector !== f.industry) return false;
  if (f.indPct && (s.ind_pct ?? 0) < f.indPct) return false;
  if (f.score && s.score < f.score) return false;
  if (f.stage === "new2" ? !(s.stage === 2 && s.new_stage) : f.stage !== "All" && s.stage !== Number(f.stage)) return false;
  if (f.weeks && s.weeks > f.weeks) return false;
  const ext = s.atr_ext ?? 0;
  if (f.atrExt === "le2" && ext > 2) return false;
  if (f.atrExt === "le4" && ext > 4) return false;
  if (f.atrExt === "gt4" && ext <= 4) return false;
  return true;
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: Array<[string, string]> }) {
  return (
    <select className={`sd-select${value !== "All" && value !== "0" ? " set" : ""}`} aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map(([v, text]) => <option key={v} value={v}>{text}</option>)}
    </select>
  );
}

function MarketPanel({ scan }: { scan: StageScan }) {
  const m = scan.market;
  const total = Object.values(m.stage_counts).reduce((sum, v) => sum + v, 0) || 1;
  return (
    <section className="dashboard-panel bk-market">
      <div className="bk-market-stats">
        <div>
          <span>{m.benchmark}</span>
          <strong>{m.stage ? <StagePill stage={m.stage} /> : "N/A"} {m.weeks ? <small className="sd-muted">{m.weeks}w</small> : null}</strong>
        </div>
        <MarketStat label="1D" value={signedPct(m.ret_1d)} tone={m.ret_1d} />
        <MarketStat label="1W" value={signedPct(m.ret_1w)} tone={m.ret_1w} />
        <MarketStat label="1M" value={signedPct(m.ret_1m)} tone={m.ret_1m} />
        <MarketStat label="3M" value={signedPct(m.ret_3m)} tone={m.ret_3m} />
        <MarketStat label="In Stage 2" value={pct((m.stage_counts["2"] ?? 0) / total, 0)} />
      </div>
      <div className="bk-tier-bar" aria-label="Stage distribution">
        {STAGES.map((s) => m.stage_counts[s] ? (
          <span key={s} className={`sd-stage-${s}`} style={{ width: `${(m.stage_counts[s] / total) * 100}%` }} title={`Stage ${s} ${STAGE_NAMES[s]}: ${m.stage_counts[s]}`}>
            S{s} · {m.stage_counts[s]}
          </span>
        ) : null)}
      </div>
      <p className="fine-print">{scan.scored_count} of {scan.universe_count} Nasdaq-100 stocks staged · closing data as of {scan.market_date ?? "N/A"}</p>
    </section>
  );
}

function MarketStat({ label, value, tone: t }: { label: string; value: string; tone?: number | null }) {
  return (
    <div>
      <span>{label}</span>
      <strong className={tone(t)}>{value}</strong>
    </div>
  );
}

function StagePill({ stage, weeks, capped }: { stage: number; weeks?: number; capped?: boolean }) {
  return (
    <span className={`sd-stage sd-stage-${stage}`} title={`Stage ${stage} · ${STAGE_NAMES[stage]}`}>
      {stage}{weeks != null && <small>{weeks}{capped ? "+" : ""}w</small>}
    </span>
  );
}

function Heat({ value, max = 100, suffix = "" }: { value: number | null; max?: number; suffix?: string }) {
  if (value == null) return <span className="sd-heat">—</span>;
  const r = value / max;
  return <span className={`sd-heat ${r >= 0.7 ? "hi" : r >= 0.4 ? "mid" : "lo"}`}>{value}{suffix}</span>;
}

function SortTh({ label, k, sort, onSort, title }: { label: string; k: SortKey; sort: { key: SortKey; desc: boolean }; onSort: (k: SortKey) => void; title?: string }) {
  return (
    <th title={title} className={`sd-sort${sort.key === k ? " active" : ""}`} onClick={() => onSort(k)}>
      {label}{sort.key === k ? (sort.desc ? " ↓" : " ↑") : ""}
    </th>
  );
}

function ScreenTable({ rows, total, selected, sort, onSort, onPick, marketDate }: {
  rows: StageStock[];
  total: number;
  selected: string;
  sort: { key: SortKey; desc: boolean };
  onSort: (k: SortKey) => void;
  onPick: (symbol: string) => void;
  marketDate: string | null;
}) {
  return (
    <div className="dashboard-panel sd-table-panel">
      <div className="panel-header">
        <h2>Showing {rows.length} of {total} stocks</h2>
        <p className="fine-print">Closing data as of {marketDate ?? "N/A"} · click a column to sort</p>
      </div>
      <div className="bk-table-scroll">
        <table className="bk-table sd-table">
          <thead>
            <tr>
              <SortTh label="Ticker" k="symbol" sort={sort} onSort={onSort} />
              <th>Industry</th>
              <SortTh label="Ind %ile" k="ind_pct" sort={sort} onSort={onSort} title="Industry relative-strength percentile (13-week return vs Nasdaq-100 EW)" />
              <SortTh label="Score" k="score" sort={sort} onSort={onSort} title="Trend score 0–10" />
              <SortTh label="Δ" k="score_delta" sort={sort} onSort={onSort} title="Score change vs last week" />
              <SortTh label="Stage" k="weeks" sort={sort} onSort={onSort} title="Weinstein stage · weeks in stage" />
              <SortTh label="ATR Ext" k="atr_ext" sort={sort} onSort={onSort} title="(Close − 50-day SMA) / 14-day ATR" />
              <SortTh label="ATR %" k="atr_pct" sort={sort} onSort={onSort} title="14-day ATR as % of price" />
              <SortTh label="RS %ile" k="rs_pct" sort={sort} onSort={onSort} title="Stock RS percentile within the Nasdaq-100" />
              <SortTh label="1D" k="change_pct" sort={sort} onSort={onSort} />
              <th>Tags</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.symbol} className={`sd-row${s.symbol === selected ? " current" : ""}`} onClick={() => onPick(s.symbol)}>
                <td><strong>{s.symbol}</strong><small>{s.name}</small></td>
                <td><span className="sd-industry">{s.sector}</span></td>
                <td><Heat value={s.ind_pct} /></td>
                <td><Heat value={s.score} max={10} /></td>
                <td className={tone(s.score_delta)}>{s.score_delta == null ? "—" : s.score_delta > 0 ? `+${s.score_delta}` : s.score_delta}</td>
                <td><StagePill stage={s.stage} weeks={s.weeks} capped={s.weeks_capped} /></td>
                <td><span className={`sd-ext ${extClass(s.atr_ext)}`}>{s.atr_ext == null ? "—" : s.atr_ext.toFixed(1)}</span></td>
                <td>{pct(s.atr_pct)}</td>
                <td><Heat value={s.rs_pct} /></td>
                <td className={tone(s.change_pct)}>{signedPct(s.change_pct)}</td>
                <td><div className="sd-tags">{s.tags.map((t) => <span key={t}>{t}</span>)}</div></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && <p className="breakout-loading-row">No Nasdaq-100 stocks pass this screen right now. Try Clear or loosen a filter.</p>}
      </div>
    </div>
  );
}

function StageBoard({ stocks, selected, onPick }: { stocks: StageStock[]; selected: string; onPick: (symbol: string) => void }) {
  const changed = stocks.filter((s) => s.new_stage);
  return (
    <div className="sd-stage-panel">
      {changed.length > 0 && (
        <div className="dashboard-panel">
          <div className="panel-header"><h2>Changed stage this week</h2><p className="fine-print">{changed.length} stocks</p></div>
          <div className="sd-chip-row">
            {changed.map((s) => (
              <button key={s.symbol} type="button" className="sd-chip" onClick={() => onPick(s.symbol)}>
                <strong>{s.symbol}</strong> <StagePill stage={s.prev_stage ?? s.stage} /> → <StagePill stage={s.stage} />
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="sd-board">
        {STAGES.map((stage) => {
          const members = stocks.filter((s) => s.stage === stage).sort((a, b) => a.weeks - b.weeks || b.score - a.score);
          return (
            <div key={stage} className="dashboard-panel sd-board-col">
              <div className={`sd-board-head sd-stage-${stage}`}>Stage {stage} · {STAGE_NAMES[stage]} <b>{members.length}</b></div>
              {members.map((s) => (
                <button key={s.symbol} type="button" className={`sd-board-item${s.symbol === selected ? " active" : ""}`} onClick={() => onPick(s.symbol)}>
                  <strong>{s.symbol}</strong>
                  <small>{s.weeks}{s.weeks_capped ? "+" : ""}w · score {s.score}</small>
                  <span className={tone(s.change_pct)}>{signedPct(s.change_pct)}</span>
                </button>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function IndustryTable({ industries, onPick }: { industries: Industry[]; onPick: (symbol: string) => void }) {
  return (
    <div className="dashboard-panel sd-table-panel">
      <div className="panel-header">
        <h2>Industries ranked by relative strength</h2>
        <p className="fine-print">Average 13-week return vs the Nasdaq-100 equal-weight composite. Leaders come from leading groups.</p>
      </div>
      <div className="bk-table-scroll">
        <table className="bk-table sd-table">
          <thead>
            <tr><th>#</th><th>Industry</th><th>Ind %ile</th><th>13W vs NDX</th><th>Avg score</th><th>Stages 1 · 2 · 3 · 4</th><th>1W</th><th>13W</th><th>RS leaders</th></tr>
          </thead>
          <tbody>
            {industries.map((ind) => (
              <tr key={ind.industry}>
                <td>{ind.rank}</td>
                <td><strong>{ind.industry}</strong><small>{ind.members} names</small></td>
                <td><Heat value={ind.ind_pct} /></td>
                <td className={tone(ind.rel_13w)}>{signedPct(ind.rel_13w)}</td>
                <td>{ind.avg_score.toFixed(1)}</td>
                <td>
                  <div className="sd-mini-bar">
                    {STAGES.map((s) => ind.stage_counts[s] ? <span key={s} className={`sd-stage-${s}`} style={{ flex: ind.stage_counts[s] }} title={`Stage ${s}: ${ind.stage_counts[s]}`}>{ind.stage_counts[s]}</span> : null)}
                  </div>
                </td>
                <td className={tone(ind.ret_1w)}>{signedPct(ind.ret_1w)}</td>
                <td className={tone(ind.ret_13w)}>{signedPct(ind.ret_13w)}</td>
                <td>
                  <div className="bk-top-chips">
                    {ind.leaders.map((l) => <button type="button" key={l.symbol} onClick={() => onPick(l.symbol)}>{l.symbol} <b>S{l.stage}</b></button>)}
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

function StockDetail({ detail, maxScore, onPick }: { detail: StageDetail; maxScore: number; onPick: (symbol: string) => void }) {
  return (
    <div className="bk-detail-body">
      <div className="bk-detail-head">
        <div>
          <span className="eyebrow">{detail.sector} · industry #{detail.ind_rank} · as of {detail.as_of}</span>
          <h2>{detail.symbol} <small>{detail.name}</small></h2>
          <p>
            <strong>{money(detail.price)}</strong>{" "}
            <span className={tone(detail.change_pct)}>{signedPct(detail.change_pct)}</span>
          </p>
        </div>
        <div className="sd-detail-badge">
          <StagePill stage={detail.stage} weeks={detail.weeks} capped={detail.weeks_capped} />
          <small>{detail.stage_name}</small>
        </div>
      </div>

      <div className="breakout-detail-stats sd-detail-stats">
        <div><span>Trend score</span><strong>{detail.score}/{maxScore} {detail.score_delta ? <small className={tone(detail.score_delta)}>{detail.score_delta > 0 ? "+" : ""}{detail.score_delta}</small> : null}</strong></div>
        <div><span>Mansfield RS</span><strong className={tone(detail.mansfield)}>{detail.mansfield == null ? "N/A" : detail.mansfield.toFixed(1)}</strong></div>
        <div><span>RS / Ind %ile</span><strong>{detail.rs_pct ?? "—"} / {detail.ind_pct ?? "—"}</strong></div>
        <div><span>ATR Ext</span><strong className={`sd-ext ${extClass(detail.atr_ext)}`}>{detail.atr_ext == null ? "N/A" : `${detail.atr_ext.toFixed(1)}×`}</strong></div>
        <div><span>From 30W / 52W hi</span><strong>{signedPct(detail.pct_from_ma30, 0)} / {signedPct(detail.pct_from_high, 0)}</strong></div>
        <div><span>13W vs NDX</span><strong className={tone(detail.rel_13w)}>{signedPct(detail.rel_13w)}</strong></div>
      </div>

      <WeeklyChart points={detail.chart} symbol={detail.symbol} />

      <div>
        <h3>Stage history</h3>
        <div className="sd-timeline">
          {detail.stage_history.map((seg) => (
            <span key={seg.start} className={`sd-stage-${seg.stage}`} style={{ flex: seg.weeks }} title={`Stage ${seg.stage} ${seg.name}: ${seg.start} → ${seg.end} (${seg.weeks}w)`}>
              {seg.weeks >= 2 ? `S${seg.stage}` : ""}
            </span>
          ))}
        </div>
        <p className="fine-print">{detail.stage_history[0]?.start ?? ""} → {detail.as_of}. Limited by the ~1 year of cached daily bars (30-week warm-up).</p>
      </div>

      <div>
        <h3>Trend checks · {detail.score} of {maxScore}</h3>
        <div className="sd-checks">
          {detail.check_details.map((c) => (
            <div key={c.key} className={`bk-check${c.passed ? " fired" : ""}`} title={c.description}>
              <strong>{c.label}</strong>
              <small>{c.description}</small>
            </div>
          ))}
        </div>
      </div>

      {detail.tags.length > 0 && <div className="sd-tags">{detail.tags.map((t) => <span key={t}>{t}</span>)}</div>}

      <div>
        <h3>Peers in {detail.sector}</h3>
        <table className="bk-table bk-peers">
          <tbody>
            {detail.peers.map((p) => (
              <tr key={p.symbol} className={p.symbol === detail.symbol ? "current" : ""} onClick={() => onPick(p.symbol)}>
                <td><strong>{p.symbol}</strong><small>{p.name}</small></td>
                <td><StagePill stage={p.stage} weeks={p.weeks} /></td>
                <td><Heat value={p.score} max={10} /></td>
                <td>RS {p.rs_pct ?? "—"}</td>
                <td className={tone(p.change_pct)}>{signedPct(p.change_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const STAGE_FILL: Record<number, string> = { 1: "rgba(96, 165, 250, 0.10)", 2: "rgba(45, 212, 191, 0.12)", 3: "rgba(251, 191, 36, 0.12)", 4: "rgba(251, 113, 133, 0.12)" };

function WeeklyChart({ points, symbol }: { points: WeeklyPoint[]; symbol: string }) {
  if (points.length < 2) return <div className="breakout-empty-detail">No weekly bars cached.</div>;
  const width = 760, height = 340, left = 8, right = 58, top = 12, priceBottom = 232, lowerTop = 254, lowerBottom = 316;
  const plotWidth = width - left - right;
  const step = plotWidth / Math.max(points.length - 1, 1);
  const candleWidth = Math.max(3, Math.min(10, step * 0.6));
  const values = points.flatMap((p) => [p.high, p.low, p.ma10, p.ma30].filter(isNumber));
  const min = Math.min(...values), max = Math.max(...values);
  const pad = (max - min) * 0.05 || max * 0.01;
  const lo = min - pad, hi = max + pad;
  const x = (i: number) => left + i * step;
  const y = (v: number) => top + ((hi - v) / (hi - lo)) * (priceBottom - top);
  const rs = points.map((p) => p.mansfield);
  const rsNums = rs.filter(isNumber);
  const rMax = Math.max(...rsNums.map(Math.abs), 1);
  const ry = (v: number) => (lowerTop + lowerBottom) / 2 - (v / rMax) * ((lowerBottom - lowerTop) / 2);
  const ticks = [0, 0.5, 1].map((r) => hi - (hi - lo) * r);

  return (
    <div className="bk-chart">
      <div className="sd-legend">
        <span><i style={{ background: "#38bdf8" }} />10W SMA</span>
        <span><i style={{ background: "#f59e0b" }} />30W SMA</span>
        {STAGES.map((s) => <span key={s}><i style={{ background: STAGE_FILL[s].replace(/0\.1\d\)/, "0.6)") }} />S{s}</span>)}
      </div>
      <svg className="breakout-candle-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${symbol} weekly stage chart`}>
        <rect x={left} y={top} width={plotWidth} height={priceBottom - top} rx="8" fill="rgba(9, 24, 21, 0.72)" stroke="#17352d" />
        {points.map((p, i) => p.stage ? (
          <rect key={`s-${i}`} x={x(i) - step / 2} y={top} width={step} height={priceBottom - top} fill={STAGE_FILL[p.stage]} />
        ) : null)}
        <rect x={left} y={lowerTop} width={plotWidth} height={lowerBottom - lowerTop} rx="8" fill="rgba(9, 24, 21, 0.72)" stroke="#17352d" />
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={left} x2={left + plotWidth} y1={y(tick)} y2={y(tick)} stroke="#17352d" strokeDasharray="3 4" />
            <text x={width - 4} y={y(tick) + 4} textAnchor="end" className="breakout-candle-axis-text">{money(tick)}</text>
          </g>
        ))}
        {[0, Math.floor((points.length - 1) / 2), points.length - 1].map((i) => (
          <text key={i} x={x(i)} y={height - 6} textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"} className="breakout-candle-axis-text">{shortDate(points[i].date)}</text>
        ))}
        {points.map((p, i) => {
          const up = p.close >= p.open;
          const color = up ? "#2dd4bf" : "#fb7185";
          return (
            <g key={p.date}>
              <title>{`Week of ${p.date} O ${money(p.open)} H ${money(p.high)} L ${money(p.low)} C ${money(p.close)}${p.stage ? ` · Stage ${p.stage}` : ""}`}</title>
              <line x1={x(i)} x2={x(i)} y1={y(p.high)} y2={y(p.low)} stroke={color} strokeWidth="1.1" />
              <rect x={x(i) - candleWidth / 2} y={Math.min(y(p.open), y(p.close))} width={candleWidth} height={Math.max(1.5, Math.abs(y(p.open) - y(p.close)))} fill={color} rx="1" />
            </g>
          );
        })}
        <path d={line(points.map((p) => p.ma10), x, y)} fill="none" stroke="#38bdf8" strokeWidth="1.4" />
        <path d={line(points.map((p) => p.ma30), x, y)} fill="none" stroke="#f59e0b" strokeWidth="1.8" />
        <line x1={left} x2={left + plotWidth} y1={ry(0)} y2={ry(0)} stroke="#2f5a4f" strokeDasharray="3 3" />
        <path d={line(rs, x, ry)} fill="none" stroke="#facc15" strokeWidth="1.5" />
        <text x={left + 8} y={lowerTop + 14} className="breakout-candle-axis-text">Mansfield RS vs Nasdaq-100 EW</text>
      </svg>
    </div>
  );
}

function line(values: Array<number | null>, x: (i: number) => number, y: (v: number) => number) {
  let d = "";
  let drawing = false;
  values.forEach((v, i) => {
    if (!isNumber(v)) {
      drawing = false;
      return;
    }
    d += `${drawing ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)} `;
    drawing = true;
  });
  return d.trim();
}

function exportCsv(rows: StageStock[]) {
  const header = ["Ticker", "Name", "Industry", "Ind %ile", "Score", "Score Δ", "Stage", "Weeks", "ATR Ext", "ATR %", "RS %ile", "Mansfield RS", "13W vs NDX", "Price", "1D", "Tags"];
  const body = rows.map((s) => [
    s.symbol, s.name, s.sector, s.ind_pct, s.score, s.score_delta, s.stage, s.weeks, s.atr_ext?.toFixed(2), s.atr_pct?.toFixed(4),
    s.rs_pct, s.mansfield?.toFixed(2), s.rel_13w?.toFixed(4), s.price, s.change_pct?.toFixed(4), s.tags.join("; ")
  ]);
  const csv = [header, ...body].map((r) => r.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `stage-desk-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function extClass(ext: number | null) {
  if (ext == null) return "";
  return ext > 4 ? "hot" : ext > 2 ? "warm" : "cool";
}

function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function tone(value: number | null | undefined) {
  if (value == null) return "";
  return value >= 0 ? "bk-up" : "bk-down";
}

function money(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
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
