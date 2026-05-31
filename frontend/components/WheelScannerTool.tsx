"use client";

import {
  ChevronDown,
  ChevronRight,
  ChevronUp,
  ExternalLink,
  RefreshCw,
  RotateCcw,
  Settings,
  Star,
  TrendingDown,
  TrendingUp,
  Wifi,
  WifiOff,
  X
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

// ── Types ────────────────────────────────────────────────────────────────────

interface WheelQuote {
  symbol: string;
  price: number | null;
  bid: number | null;
  ask: number | null;
  last: number | null;
  close: number | null;
  change: number | null;
  change_pct: number | null;
  volume: number | null;
  iv_rank: number | null;
  hv30: number | null;
  rsi: number | null;
  bb_pct: number | null;
  csp_30d: number | null;
  cc_30d: number | null;
  signals: string[];
  source?: string;
  // Stage Analysis (Weinstein)
  stage: number | null;          // 1=Basing 2=Advancing 3=Topping 4=Declining
  sata_score: number | null;     // 0–10
  mansfield_rs: number | null;
  ma150: number | null;
  ma200: number | null;
  sata_attributes: Record<string, boolean>;
}

interface WheelOptionRow {
  symbol: string;
  occ_symbol: string;
  option_type: "P" | "C";
  expiry: string;
  dte: number;
  strike: number;
  bid: number;
  ask: number;
  mid: number;
  last: number | null;
  iv: number | null;
  delta: number | null;
  open_interest: number;
  volume: number;
  raw_yield: number | null;
  annualized_yield: number | null;
  pct_away: number | null;
  pop: number | null;
  stock_price: number | null;
  capital_required: number | null;
  upside_pct?: number | null;
}

interface WheelStatus {
  ibkr_connected: boolean;
  watchlist_count: number;
  quotes_cached: number;
  cboe_prices_cached: number;
  price_source: "ibkr" | "cboe_delayed" | "none";
}

type SortDir = "asc" | "desc";
type SubTab = "watchlist" | "wheel-hub";
type HubFilter = "all" | "csp" | "cc" | "leap";
type OptionsTab = "P" | "C";

// ── Constants ─────────────────────────────────────────────────────────────────

const WHEEL_API = process.env.NEXT_PUBLIC_IBKR_API_URL ?? "http://localhost:8002";

const DTE_PRESETS = [
  { label: "7–14d",  min: 7,  max: 14  },
  { label: "15–30d", min: 15, max: 30  },
  { label: "30–45d", min: 30, max: 45  },
  { label: "All",    min: 0,  max: 999 },
];

const WHEEL_STAGES = [
  {
    num: 1, icon: TrendingDown, title: "Sell CSP",
    color: "#3b82f6", border: "#3b82f6",
    desc: "Sell 30Δ put · DTE 30–45",
    pathA: "Expires OTM → keep premium → repeat",
    pathB: "Expires ITM → assigned at strike (→ Stage 3)",
  },
  {
    num: 2, icon: Settings, title: "Manage",
    color: "#f59e0b", border: "#f59e0b",
    desc: "While CSP is open",
    pathA: "Close at 50% profit — keep the easy theta",
    pathB: "Going ITM? Roll down-and-out for net credit",
  },
  {
    num: 3, icon: TrendingUp, title: "Sell CC",
    color: "#22c55e", border: "#22c55e",
    desc: "30Δ call on 100 assigned shares",
    pathA: "Expires OTM → collect premium → repeat CC",
    pathB: "Called away at strike (→ Stage 4)",
  },
  {
    num: 4, icon: RotateCcw, title: "Exit & Repeat",
    color: "var(--forest)", border: "var(--forest)",
    desc: "Stock sold at target price",
    pathA: "Profit taken → redeploy capital → Stage 1",
    pathB: "Review journal — was timing / strike right?",
  },
];

const HUB_FILTERS: { key: HubFilter; label: string }[] = [
  { key: "all",  label: "All Candidates" },
  { key: "csp",  label: "CSP Ready"      },
  { key: "cc",   label: "CC Ready"       },
  { key: "leap", label: "LEAP Setup"     },
];

const WATCHLIST_COLS = [
  { key: "rank",        label: "#",         right: false },
  { key: "symbol",      label: "Symbol",    right: false },
  { key: "price",       label: "Price",     right: true  },
  { key: "change_pct",  label: "1D Chg",   right: true  },
  { key: "stage",       label: "Stage",     right: false, title: "Weinstein Stage 1=Basing 2=Advancing 3=Topping 4=Declining" },
  { key: "sata_score",  label: "SATA",      right: true,  title: "Stage Analysis Technical Attributes score 0–10 (8–10=S2 bullish, 0–3=S4 bearish)" },
  { key: "mansfield_rs",label: "Mans RS",   right: true,  title: "Mansfield Relative Strength vs SPX — above 0 = outperforming" },
  { key: "rsi",         label: "RSI",       right: true  },
  { key: "bb_pct",      label: "BB %",      right: true  },
  { key: "iv_rank",     label: "IV %",      right: true  },
  { key: "csp_30d",     label: "30Δ CSP %", right: true  },
  { key: "cc_30d",      label: "30Δ CC %",  right: true  },
  { key: "volume",      label: "Volume",    right: true  },
  { key: "signals",     label: "Signals",   right: false },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

async function wheelGet<T>(path: string): Promise<T> {
  const res = await fetch(`${WHEEL_API}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Wheel API ${res.status}: ${path}`);
  return res.json() as Promise<T>;
}

function fmtNum(v: number | null | undefined, d = 2): string {
  return v == null ? "—" : v.toFixed(d);
}

function fmtPrice(v: number | null | undefined): string {
  if (v == null) return "—";
  return `$${v.toFixed(2)}`;
}

function fmtVol(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return String(v);
}

function rsiClass(v: number | null): string {
  if (v == null) return "wheel-muted";
  if (v <= 40) return "wheel-green";
  if (v >= 70) return "wheel-red";
  return "wheel-dim";
}

function yieldClass(v: number | null, threshold = 5): string {
  if (v == null) return "wheel-muted";
  if (v > threshold) return "wheel-green";
  if (v > threshold * 0.6) return "wheel-amber";
  return "wheel-dim";
}

function changeClass(v: number | null): string {
  if (v == null) return "wheel-muted";
  if (v > 0) return "wheel-green";
  if (v < 0) return "wheel-red";
  return "wheel-dim";
}

// Score option by proximity to 30Δ at 30 DTE
function optionScore(o: WheelOptionRow): number {
  const dteDist = Math.abs(o.dte - 30) / 30;
  const deltaAbs = Math.abs(o.delta ?? 0);
  const deltaDist = Math.abs(deltaAbs - 0.3) * 2;
  return dteDist + deltaDist;
}

function findRecommendedOcc(options: WheelOptionRow[]): string | null {
  const valid = options.filter(
    (o) => o.delta != null && o.dte >= 20 && o.dte <= 50 && o.annualized_yield != null && o.bid > 0.05
  );
  if (!valid.length) return null;
  return valid.reduce((best, cur) => (optionScore(cur) < optionScore(best) ? cur : best)).occ_symbol;
}

// ── Stage Badge ───────────────────────────────────────────────────────────────

const STAGE_META: Record<number, { label: string; cls: string; title: string }> = {
  1: { label: "S1 Basing",    cls: "wheel-badge-stage1", title: "Stage 1 — Basing / Accumulation: price sideways around flattening 150d MA" },
  2: { label: "S2 Advancing", cls: "wheel-badge-stage2", title: "Stage 2 — Advancing: price above rising 150d MA, SATA 7–10" },
  3: { label: "S3 Topping",   cls: "wheel-badge-stage3", title: "Stage 3 — Topping / Distribution: MA flattening after uptrend, SATA 4–6" },
  4: { label: "S4 Declining", cls: "wheel-badge-stage4", title: "Stage 4 — Declining: price below falling 150d MA, SATA 0–3" },
};

function StageBadge({ stage }: { stage: number | null }) {
  if (!stage || !STAGE_META[stage]) return <span className="wheel-muted">—</span>;
  const m = STAGE_META[stage];
  return <span className={`wheel-badge ${m.cls}`} title={m.title}>{m.label}</span>;
}

function SataScore({ score, attrs }: { score: number | null; attrs?: Record<string, boolean> }) {
  if (score == null) return <span className="wheel-muted">—</span>;
  const cls = score >= 7 ? "wheel-green" : score <= 3 ? "wheel-red" : "wheel-amber";
  const attrList = attrs
    ? Object.entries(attrs)
        .map(([k, v]) => `${v ? "✓" : "✗"} ${k.replace(/_/g, " ")}`)
        .join("\n")
    : "";
  return (
    <span className={`${cls} wheel-sata-score`} title={attrList ? `SATA attributes:\n${attrList}` : ""}>
      {score}<span className="wheel-sata-denom">/10</span>
    </span>
  );
}

// ── Signal Badges ─────────────────────────────────────────────────────────────

function SignalBadges({ signals }: { signals: string[] }) {
  if (!signals?.length) return <span className="wheel-muted">—</span>;
  return (
    <div className="wheel-signals">
      {signals.map((s) => (
        <span key={s} className={`wheel-badge wheel-badge-${s.toLowerCase()}`}>{s}</span>
      ))}
    </div>
  );
}

// ── Options Panel ─────────────────────────────────────────────────────────────

function OptionsPanel({
  symbol,
  data,
  loading,
  onClose,
}: {
  symbol: string;
  data: { puts: WheelOptionRow[]; calls: WheelOptionRow[] } | null;
  loading: boolean;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<OptionsTab>("P");
  const [preset, setPreset] = useState(DTE_PRESETS[2]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const allOptions = tab === "P" ? (data?.puts ?? []) : (data?.calls ?? []);
  const recommendedOcc = useMemo(() => findRecommendedOcc(allOptions), [allOptions]);
  const recommended = allOptions.find((o) => o.occ_symbol === recommendedOcc);

  const filtered = useMemo(
    () =>
      allOptions
        .filter((o) => o.dte >= preset.min && o.dte <= preset.max)
        .sort((a, b) => {
          if (a.dte !== b.dte) return a.dte - b.dte;
          return Math.abs(Math.abs(a.delta ?? 0) - 0.3) - Math.abs(Math.abs(b.delta ?? 0) - 0.3);
        }),
    [allOptions, preset]
  );

  return (
    <>
      <div className="wheel-options-backdrop" onClick={onClose} />
      <div className="wheel-options-panel">
        {/* Header */}
        <div className="wheel-options-header">
          <span className="wheel-options-title">{symbol} — Options Chain</span>
          <div className="wheel-options-tabs">
            <button
              type="button"
              className={tab === "P" ? "active blue" : ""}
              onClick={() => setTab("P")}
            >
              Puts (CSP)
            </button>
            <button
              type="button"
              className={tab === "C" ? "active green" : ""}
              onClick={() => setTab("C")}
            >
              Calls (CC)
            </button>
          </div>
          <div className="wheel-dte-presets">
            {DTE_PRESETS.map((p) => (
              <button
                key={p.label}
                type="button"
                className={preset.label === p.label ? "active" : ""}
                onClick={() => setPreset(p)}
              >
                {p.label}
              </button>
            ))}
          </div>
          <button type="button" className="wheel-close-btn" onClick={onClose}><X size={16} /></button>
        </div>

        {/* Algorithm Pick */}
        {recommended && (
          <div className="wheel-algo-pick">
            <div className="wheel-algo-pick-header">
              <Star size={13} /> Algorithm Pick
              <span className="wheel-algo-pick-sub">
                {tab === "P" ? "Best CSP — nearest 30Δ put at ~30 DTE" : "Best CC — nearest 30Δ call at ~30 DTE"}
              </span>
            </div>
            <div className="wheel-algo-metrics">
              {[
                { label: "Strike",     value: `$${recommended.strike.toFixed(0)}` },
                { label: "DTE",        value: `${recommended.dte}d` },
                { label: "Delta",      value: Math.abs(recommended.delta ?? 0).toFixed(2) },
                { label: "Mid",        value: `$${recommended.mid.toFixed(2)}`,  green: true },
                { label: "IV",         value: recommended.iv != null ? `${recommended.iv.toFixed(1)}%` : "—" },
                { label: "Ann. Yield", value: recommended.annualized_yield != null ? `${recommended.annualized_yield.toFixed(1)}%` : "—", green: true },
                { label: "OI",         value: recommended.open_interest.toLocaleString() },
              ].map(({ label, value, green }) => (
                <div key={label} className="wheel-algo-metric">
                  <strong className={green ? "wheel-green" : ""}>{value}</strong>
                  <span>{label}</span>
                </div>
              ))}
            </div>
            <p className="wheel-algo-expiry fine-print">
              Expiry {recommended.expiry} · Bid ${recommended.bid.toFixed(2)} / Ask ${recommended.ask.toFixed(2)}
              {recommended.pct_away != null ? ` · ${recommended.pct_away.toFixed(1)}% OTM` : ""}
            </p>
          </div>
        )}

        {/* Options table */}
        <div className="wheel-options-body">
          {loading ? (
            <p className="fine-print" style={{ padding: "24px", textAlign: "center" }}>Loading options chain…</p>
          ) : (
            <div className="table-wrap">
              <table className="wheel-table">
                <thead>
                  <tr>
                    <th>Expiry</th>
                    <th className="right">Strike</th>
                    <th className="right">% OTM</th>
                    <th className="right">DTE</th>
                    <th className="right">Bid</th>
                    <th className="right">Ask</th>
                    <th className="right">Mid</th>
                    <th className="right">Delta</th>
                    <th className="right">IV %</th>
                    <th className="right">OI</th>
                    <th className="right">Ann.Yield</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((o) => {
                    const isRec = o.occ_symbol === recommendedOcc;
                    return (
                      <tr key={o.occ_symbol} className={isRec ? "wheel-row-pick" : ""}>
                        <td>
                          {o.expiry}
                          {isRec && <span className="wheel-pick-star"> ★ Pick</span>}
                        </td>
                        <td className="right">${o.strike.toFixed(0)}</td>
                        <td className={`right ${o.pct_away != null && o.pct_away < 0 ? "wheel-red" : "wheel-dim"}`}>
                          {o.pct_away != null ? `${o.pct_away.toFixed(1)}%` : "—"}
                        </td>
                        <td className="right wheel-dim">{o.dte}</td>
                        <td className="right wheel-dim">${fmtNum(o.bid)}</td>
                        <td className="right wheel-dim">${fmtNum(o.ask)}</td>
                        <td className={`right ${isRec ? "wheel-green" : ""}`}>${fmtNum(o.mid)}</td>
                        <td className="right wheel-dim">
                          {o.delta != null ? Math.abs(o.delta).toFixed(2) : "—"}
                        </td>
                        <td className="right wheel-dim">
                          {o.iv != null ? `${o.iv.toFixed(1)}%` : "—"}
                        </td>
                        <td className="right wheel-dim">{o.open_interest.toLocaleString()}</td>
                        <td className={`right ${o.annualized_yield != null && o.annualized_yield > 5 ? "wheel-green" : "wheel-dim"}`}>
                          {o.annualized_yield != null ? `${o.annualized_yield.toFixed(1)}%` : "—"}
                        </td>
                      </tr>
                    );
                  })}
                  {filtered.length === 0 && !loading && (
                    <tr>
                      <td colSpan={11} className="wheel-empty-row">No options in this DTE range — try &quot;All&quot;</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

// ── TradingView Modal ─────────────────────────────────────────────────────────

function ChartModal({ symbol, quote, onClose }: { symbol: string; quote: WheelQuote | undefined; onClose: () => void }) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const tvUrl = `https://www.tradingview.com/chart/?symbol=NASDAQ%3A${symbol}&interval=D`;
  const chg = quote?.change_pct;

  return (
    <div className="wheel-modal-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="wheel-modal">
        <div className="wheel-modal-header">
          <div className="wheel-modal-symbol">
            <strong>{symbol}</strong>
            <span className="fine-print">NASDAQ · Daily</span>
          </div>
          {quote?.price != null && (
            <div className="wheel-modal-price">
              <strong>{fmtPrice(quote.price)}</strong>
              {chg != null && (
                <span className={`fine-print ${changeClass(chg)}`}>
                  {chg >= 0 ? "+" : ""}{chg.toFixed(2)}%
                </span>
              )}
            </div>
          )}
          <button type="button" className="wheel-close-btn" onClick={onClose}><X size={16} /></button>
        </div>
        {/* Stage + SATA row */}
        {(quote?.stage || quote?.sata_score != null) && (
          <div className="wheel-modal-stage-row">
            <StageBadge stage={quote?.stage ?? null} />
            {quote?.sata_score != null && (
              <span className="fine-print">
                SATA <SataScore score={quote.sata_score} attrs={quote.sata_attributes} />
              </span>
            )}
            {quote?.mansfield_rs != null && (
              <span className={`fine-print ${quote.mansfield_rs > 0 ? "wheel-green" : "wheel-red"}`}>
                Mansfield RS {quote.mansfield_rs > 0 ? "+" : ""}{quote.mansfield_rs.toFixed(1)}
              </span>
            )}
            {quote?.ma150 != null && quote?.price != null && (
              <span className="fine-print wheel-dim">
                150d MA ${quote.ma150.toFixed(2)} ({quote.price > quote.ma150 ? "▲ above" : "▼ below"})
              </span>
            )}
          </div>
        )}
        <div className="wheel-modal-metrics">
          {[
            { label: "RSI (14)", value: quote?.rsi != null ? quote.rsi.toFixed(1) : "—", cls: rsiClass(quote?.rsi ?? null) },
            { label: "BB %",     value: quote?.bb_pct != null ? `${quote.bb_pct.toFixed(1)}%` : "—", cls: quote?.bb_pct != null ? (quote.bb_pct <= 20 ? "wheel-green" : quote.bb_pct >= 80 ? "wheel-red" : "") : "" },
            { label: "IV %",     value: quote?.iv_rank != null ? `${quote.iv_rank.toFixed(1)}%` : "—", cls: "" },
            { label: "30Δ CSP %", value: quote?.csp_30d != null ? `${quote.csp_30d.toFixed(2)}%` : "—", cls: yieldClass(quote?.csp_30d ?? null) },
            { label: "30Δ CC %",  value: quote?.cc_30d != null ? `${quote.cc_30d.toFixed(2)}%` : "—",  cls: yieldClass(quote?.cc_30d ?? null) },
            { label: "Volume",    value: fmtVol(quote?.volume), cls: "" },
          ].map(({ label, value, cls }) => (
            <div key={label} className="wheel-metric-box">
              <span className="wheel-metric-label">{label}</span>
              <strong className={cls}>{value}</strong>
            </div>
          ))}
        </div>
        {quote?.signals?.length ? (
          <div className="wheel-modal-signals">
            <span className="fine-print">Signals:</span>
            <SignalBadges signals={quote.signals} />
          </div>
        ) : null}
        <div className="wheel-modal-footer">
          <a href={tvUrl} target="_blank" rel="noopener noreferrer" className="primary-button" style={{ display: "flex", alignItems: "center", gap: "8px", textDecoration: "none", justifyContent: "center" }}>
            <ExternalLink size={15} /> Open {symbol} in TradingView
          </a>
          <p className="fine-print" style={{ marginTop: "6px", textAlign: "center" }}>
            Opens Daily chart · Indicators button → RSI(14), Volume, SMA 50/200
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export function WheelScannerTool() {
  const [status, setStatus]         = useState<WheelStatus | null>(null);
  const [quotes, setQuotes]         = useState<WheelQuote[]>([]);
  const [subTab, setSubTab]         = useState<SubTab>("watchlist");
  const [hubFilter, setHubFilter]   = useState<HubFilter>("all");
  const [sort, setSort]             = useState<{ key: string; dir: SortDir }>({ key: "symbol", dir: "asc" });
  const [search, setSearch]         = useState("");
  const [customSymbols, setCustomSymbols] = useState<Set<string>>(new Set());
  const [customInput, setCustomInput]     = useState("");
  const [optionsSymbol, setOptionsSymbol] = useState<string | null>(null);
  const [optionsData, setOptionsData]     = useState<{ puts: WheelOptionRow[]; calls: WheelOptionRow[] } | null>(null);
  const [loadingOptions, setLoadingOptions] = useState(false);
  const [chartSymbol, setChartSymbol]     = useState<string | null>(null);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState("");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const wsRef         = useRef<WebSocket | null>(null);
  const reconnectRef  = useRef<ReturnType<typeof setTimeout> | null>(null);
  const quotesMapRef  = useRef<Record<string, WheelQuote>>({});

  // ── Custom symbols (localStorage) ──────────────────────────────────────────

  useEffect(() => {
    try {
      const saved = localStorage.getItem("wheelscan_custom_symbols");
      if (saved) setCustomSymbols(new Set(JSON.parse(saved) as string[]));
    } catch { /* ignore */ }
  }, []);

  function saveCustomSymbols(syms: Set<string>) {
    setCustomSymbols(syms);
    localStorage.setItem("wheelscan_custom_symbols", JSON.stringify([...syms]));
  }

  function addCustomSymbols() {
    if (!customInput.trim()) return;
    const symbols = customInput.toUpperCase().split(/[\s,]+/).filter(Boolean);
    const next = new Set([...customSymbols, ...symbols]);
    saveCustomSymbols(next);
    setCustomInput("");
    void fetchCustom(symbols);
  }

  function removeCustomSymbol(sym: string) {
    const next = new Set(customSymbols);
    next.delete(sym);
    saveCustomSymbols(next);
    setQuotes((prev) => prev.filter((q) => !next.has(q.symbol) || q.symbol !== sym ? true : false));
  }

  // ── Data fetching ──────────────────────────────────────────────────────────

  const loadWatchlist = useCallback(async () => {
    try {
      const [statusData, watchlistData] = await Promise.all([
        wheelGet<WheelStatus>("/api/status"),
        wheelGet<{ tickers: WheelQuote[] }>("/api/watchlist"),
      ]);
      setStatus(statusData);
      const map: Record<string, WheelQuote> = {};
      for (const q of watchlistData.tickers) map[q.symbol] = q;
      quotesMapRef.current = { ...quotesMapRef.current, ...map };
      setQuotes(Object.values(quotesMapRef.current));
      setLastUpdated(new Date());
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cannot reach Wheel Scanner backend (http://localhost:8002)");
    } finally {
      setLoading(false);
    }
  }, []);

  async function fetchCustom(symbols: string[]) {
    if (!symbols.length) return;
    try {
      const data = await wheelGet<{ tickers: WheelQuote[] }>(`/api/quotes?symbols=${symbols.join(",")}`);
      for (const q of data.tickers) quotesMapRef.current[q.symbol] = q;
      setQuotes(Object.values(quotesMapRef.current));
    } catch { /* silently ignore custom fetch errors */ }
  }

  // ── Options fetch ──────────────────────────────────────────────────────────

  async function openOptions(symbol: string) {
    setOptionsSymbol(symbol);
    setOptionsData(null);
    setLoadingOptions(true);
    try {
      const data = await wheelGet<{ puts: WheelOptionRow[]; calls: WheelOptionRow[] }>(`/api/options/${symbol}`);
      setOptionsData(data);
    } catch { /* error handled by loading state */ } finally {
      setLoadingOptions(false);
    }
  }

  // ── WebSocket for live quotes ──────────────────────────────────────────────

  const connectWs = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    try {
      const wsBase = WHEEL_API.replace(/^http/, "ws");
      const ws = new WebSocket(`${wsBase}/ws/quotes`);
      wsRef.current = ws;

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data as string) as { type: string; data: Record<string, WheelQuote> };
          if (msg.type === "snapshot" || msg.type === "update") {
            for (const [sym, q] of Object.entries(msg.data)) {
              quotesMapRef.current[sym] = { ...(quotesMapRef.current[sym] ?? {}), ...q };
            }
            setQuotes(Object.values(quotesMapRef.current));
            setLastUpdated(new Date());
          }
        } catch { /* ignore malformed frames */ }
      };

      ws.onerror = () => ws.close();
      ws.onclose = () => {
        wsRef.current = null;
        reconnectRef.current = setTimeout(connectWs, 5000);
      };
    } catch { /* WS not available, HTTP polling covers it */ }
  }, []);

  // ── Lifecycle ──────────────────────────────────────────────────────────────

  useEffect(() => {
    void loadWatchlist();
    if (customSymbols.size) void fetchCustom([...customSymbols]);
    connectWs();
    const pollId = setInterval(() => { void loadWatchlist(); }, 30_000);
    return () => {
      clearInterval(pollId);
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Sorted + filtered quotes ───────────────────────────────────────────────

  const filteredWatchlist = useMemo(() => {
    let rows = quotes;
    if (search.trim()) {
      const q = search.toUpperCase();
      rows = rows.filter((r) => r.symbol.includes(q));
    }
    return [...rows].sort((a, b) => {
      const ak = (a as unknown as Record<string, unknown>)[sort.key] ?? "";
      const bk = (b as unknown as Record<string, unknown>)[sort.key] ?? "";
      if (ak === "" || ak == null) return 1;
      if (bk === "" || bk == null) return -1;
      return sort.dir === "asc"
        ? ak < bk ? -1 : ak > bk ? 1 : 0
        : ak > bk ? -1 : ak < bk ? 1 : 0;
    });
  }, [quotes, search, sort]);

  const hubCandidates = useMemo(() => {
    let rows = quotes.filter((q) => q.price != null);
    if (hubFilter === "csp")  rows = rows.filter((q) => q.signals?.includes("CSP"));
    if (hubFilter === "cc")   rows = rows.filter((q) => q.signals?.includes("CC"));
    if (hubFilter === "leap") rows = rows.filter((q) => q.signals?.includes("LEAP"));
    return rows.sort((a, b) => ((b.csp_30d ?? 0) + (b.cc_30d ?? 0)) - ((a.csp_30d ?? 0) + (a.cc_30d ?? 0)));
  }, [quotes, hubFilter]);

  function toggleSort(key: string) {
    setSort((s) => ({ key, dir: s.key === key && s.dir === "asc" ? "desc" : "asc" }));
  }

  function SortIcon({ col }: { col: string }) {
    if (sort.key !== col) return <span className="wheel-sort-neutral">⇅</span>;
    return sort.dir === "asc"
      ? <ChevronUp size={12} style={{ display: "inline", marginLeft: "2px", color: "var(--forest)" }} />
      : <ChevronDown size={12} style={{ display: "inline", marginLeft: "2px", color: "var(--forest)" }} />;
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="wheel-scanner">

      {/* Status bar */}
      <div className="wheel-status-bar">
        <div className="wheel-status-left">
          {status ? (
            <>
              <span className={`wheel-conn ${status.ibkr_connected ? "connected" : ""}`}>
                {status.ibkr_connected ? <Wifi size={13} /> : <WifiOff size={13} />}
                {status.ibkr_connected ? "IBKR Live" : "IBKR Offline"}
              </span>
              <span className="fine-print">
                Source: {status.price_source === "ibkr" ? "IBKR real-time" : status.price_source === "cboe_delayed" ? "CBOE 15-min delayed" : "—"}
              </span>
              <span className="fine-print">·</span>
              <span className="fine-print">{status.quotes_cached} quotes cached</span>
            </>
          ) : (
            <span className="fine-print wheel-muted">{error || "Connecting to backend…"}</span>
          )}
        </div>
        <div className="wheel-status-right">
          {lastUpdated && <span className="fine-print">Updated {lastUpdated.toLocaleTimeString()}</span>}
          <button
            type="button"
            className="ghost-button"
            style={{ padding: "4px 10px", fontSize: "0.82rem" }}
            onClick={() => void loadWatchlist()}
            disabled={loading}
          >
            <RefreshCw size={12} style={{ marginRight: "4px" }} />
            Refresh
          </button>
        </div>
      </div>

      {/* Sub-tabs */}
      <div className="wheel-subtabs">
        <button
          type="button"
          className={subTab === "watchlist" ? "active" : ""}
          onClick={() => setSubTab("watchlist")}
        >
          Watchlist
          <span className="wheel-subtab-count">{filteredWatchlist.length}</span>
        </button>
        <button
          type="button"
          className={subTab === "wheel-hub" ? "active" : ""}
          onClick={() => setSubTab("wheel-hub")}
        >
          Wheel Hub
          <span className="wheel-subtab-count">{hubCandidates.length}</span>
        </button>
      </div>

      {error && !quotes.length && (
        <div className="error" style={{ margin: "0 0 12px" }}>{error}</div>
      )}

      {/* ── Watchlist tab ── */}
      {subTab === "watchlist" && (
        <div className="wheel-content">
          <div className="wheel-toolbar">
            <input
              type="text"
              className="wheel-search"
              placeholder="Search symbol…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <input
              type="text"
              className="wheel-search"
              placeholder="Add symbols (AAPL, TSLA…)"
              value={customInput}
              onChange={(e) => setCustomInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") addCustomSymbols(); }}
            />
            <button type="button" className="ghost-button" onClick={addCustomSymbols} style={{ padding: "6px 12px" }}>Add</button>
          </div>

          {loading && !quotes.length ? (
            <p className="fine-print" style={{ padding: "32px 0", textAlign: "center" }}>Loading watchlist from Wheel Scanner backend…</p>
          ) : (
            <div className="table-wrap">
              <table className="wheel-table">
                <thead>
                  <tr>
                    {WATCHLIST_COLS.map((c) => (
                      <th
                        key={c.key}
                        className={c.right ? "right sortable" : "sortable"}
                        onClick={() => toggleSort(c.key)}
                      >
                        {c.label} <SortIcon col={c.key} />
                      </th>
                    ))}
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredWatchlist.map((q, i) => {
                    const isCustom = customSymbols.has(q.symbol);
                    return (
                      <tr
                        key={q.symbol}
                        className="wheel-data-row"
                        onClick={() => setChartSymbol(q.symbol)}
                        title={`Click to view ${q.symbol} chart`}
                      >
                        <td className="wheel-muted" style={{ fontSize: "0.8rem" }}>{i + 1}</td>
                        <td>
                          <div className="wheel-symbol-cell">
                            <strong>{q.symbol}</strong>
                            {isCustom && <span className="wheel-badge wheel-badge-custom">custom</span>}
                            {isCustom && (
                              <button
                                type="button"
                                className="wheel-remove-btn"
                                onClick={(e) => { e.stopPropagation(); removeCustomSymbol(q.symbol); }}
                                title={`Remove ${q.symbol}`}
                              >
                                <X size={10} />
                              </button>
                            )}
                          </div>
                        </td>
                        <td className="right">{fmtPrice(q.price)}</td>
                        <td className={`right ${changeClass(q.change_pct)}`}>
                          {q.change_pct != null ? `${q.change_pct >= 0 ? "+" : ""}${q.change_pct.toFixed(2)}%` : "—"}
                        </td>
                        <td><StageBadge stage={q.stage} /></td>
                        <td className="right"><SataScore score={q.sata_score} attrs={q.sata_attributes} /></td>
                        <td className={`right ${q.mansfield_rs != null ? (q.mansfield_rs > 0 ? "wheel-green" : "wheel-red") : "wheel-muted"}`}>
                          {q.mansfield_rs != null ? `${q.mansfield_rs > 0 ? "+" : ""}${q.mansfield_rs.toFixed(1)}` : "—"}
                        </td>
                        <td className={`right ${rsiClass(q.rsi)}`}>{fmtNum(q.rsi, 1)}</td>
                        <td className={`right ${q.bb_pct != null ? (q.bb_pct <= 20 ? "wheel-green" : q.bb_pct >= 80 ? "wheel-red" : "wheel-dim") : "wheel-muted"}`}>
                          {q.bb_pct != null ? `${q.bb_pct.toFixed(1)}%` : "—"}
                        </td>
                        <td className="right wheel-dim">{q.iv_rank != null ? `${q.iv_rank.toFixed(1)}%` : "—"}</td>
                        <td className={`right ${yieldClass(q.csp_30d)}`}>{q.csp_30d != null ? `${q.csp_30d.toFixed(2)}%` : "—"}</td>
                        <td className={`right ${yieldClass(q.cc_30d)}`}>{q.cc_30d != null ? `${q.cc_30d.toFixed(2)}%` : "—"}</td>
                        <td className="right wheel-dim">{fmtVol(q.volume)}</td>
                        <td><SignalBadges signals={q.signals ?? []} /></td>
                        <td>
                          <button
                            type="button"
                            className="wheel-options-btn"
                            onClick={(e) => { e.stopPropagation(); void openOptions(q.symbol); }}
                          >
                            Options ›
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Wheel Hub tab ── */}
      {subTab === "wheel-hub" && (
        <div className="wheel-content">
          {/* Cycle visual */}
          <div className="wheel-cycle-grid">
            {WHEEL_STAGES.map((stage, idx) => (
              <div key={stage.num} className="wheel-cycle-row">
                <div className="wheel-cycle-card" style={{ borderColor: `${stage.color}40`, background: `${stage.color}0d` }}>
                  <div className="wheel-cycle-card-header">
                    <span className="wheel-cycle-num" style={{ color: stage.color, borderColor: `${stage.color}40`, background: `${stage.color}10` }}>
                      {stage.num}
                    </span>
                    <stage.icon size={14} style={{ color: stage.color }} />
                    <strong style={{ color: stage.color, fontSize: "0.85rem" }}>{stage.title}</strong>
                  </div>
                  <p className="wheel-cycle-desc">{stage.desc}</p>
                  <div className="wheel-cycle-paths">
                    <div><span className="wheel-path-a">A</span> {stage.pathA}</div>
                    <div><span className="wheel-path-b">B</span> {stage.pathB}</div>
                  </div>
                </div>
                {idx < WHEEL_STAGES.length - 1 && (
                  <ChevronRight size={16} style={{ color: "var(--muted)", flexShrink: 0 }} />
                )}
              </div>
            ))}
          </div>

          {/* Filter bar */}
          <div className="wheel-filter-bar">
            <div className="tab-list" style={{ gridTemplateColumns: `repeat(${HUB_FILTERS.length}, minmax(0, 1fr))` }}>
              {HUB_FILTERS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  className={hubFilter === f.key ? "active" : ""}
                  onClick={() => setHubFilter(f.key)}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <span className="fine-print">{hubCandidates.length} candidates · click row for chart</span>
          </div>

          {/* Hub table */}
          <div className="table-wrap">
            <table className="wheel-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Symbol</th>
                  <th className="right">Price</th>
                  <th className="right">1D Chg</th>
                  <th title="Weinstein Stage">Stage</th>
                  <th className="right" title="SATA 0–10">SATA</th>
                  <th className="right">RSI</th>
                  <th className="right">BB %</th>
                  <th className="right">IV %</th>
                  <th className="right">30Δ CSP %</th>
                  <th className="right">30Δ CC %</th>
                  <th>Signals</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {hubCandidates.map((q, i) => (
                  <tr
                    key={q.symbol}
                    className="wheel-data-row"
                    onClick={() => setChartSymbol(q.symbol)}
                    title={`Click to view ${q.symbol} chart`}
                  >
                    <td className="wheel-muted" style={{ fontSize: "0.8rem" }}>{i + 1}</td>
                    <td><strong>{q.symbol}</strong></td>
                    <td className="right">{fmtPrice(q.price)}</td>
                    <td className={`right ${changeClass(q.change_pct)}`}>
                      {q.change_pct != null ? `${q.change_pct >= 0 ? "+" : ""}${q.change_pct.toFixed(2)}%` : "—"}
                    </td>
                    <td><StageBadge stage={q.stage} /></td>
                    <td className="right"><SataScore score={q.sata_score} attrs={q.sata_attributes} /></td>
                    <td className={`right ${rsiClass(q.rsi)}`}>{fmtNum(q.rsi, 1)}</td>
                    <td className={`right ${q.bb_pct != null ? (q.bb_pct <= 20 ? "wheel-green" : q.bb_pct >= 80 ? "wheel-red" : "wheel-dim") : "wheel-muted"}`}>
                      {q.bb_pct != null ? `${q.bb_pct.toFixed(1)}%` : "—"}
                    </td>
                    <td className="right wheel-dim">{q.iv_rank != null ? `${q.iv_rank.toFixed(1)}%` : "—"}</td>
                    <td className={`right ${yieldClass(q.csp_30d)}`}>{q.csp_30d != null ? `${q.csp_30d.toFixed(2)}%` : "—"}</td>
                    <td className={`right ${yieldClass(q.cc_30d)}`}>{q.cc_30d != null ? `${q.cc_30d.toFixed(2)}%` : "—"}</td>
                    <td><SignalBadges signals={q.signals ?? []} /></td>
                    <td>
                      <button
                        type="button"
                        className="wheel-options-btn"
                        onClick={(e) => { e.stopPropagation(); void openOptions(q.symbol); }}
                      >
                        Options ›
                      </button>
                    </td>
                  </tr>
                ))}
                {hubCandidates.length === 0 && (
                  <tr>
                    <td colSpan={11} className="wheel-empty-row">
                      No candidates match this filter. Try &quot;All Candidates&quot;.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Options panel */}
      {optionsSymbol && (
        <OptionsPanel
          symbol={optionsSymbol}
          data={optionsData}
          loading={loadingOptions}
          onClose={() => { setOptionsSymbol(null); setOptionsData(null); }}
        />
      )}

      {/* Chart modal */}
      {chartSymbol && (
        <ChartModal
          symbol={chartSymbol}
          quote={quotes.find((q) => q.symbol === chartSymbol)}
          onClose={() => setChartSymbol(null)}
        />
      )}
    </div>
  );
}
