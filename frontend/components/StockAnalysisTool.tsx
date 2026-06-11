"use client";

import {
  AlertTriangle,
  BarChart3,
  Bot,
  Building2,
  ExternalLink,
  History,
  LineChart,
  Loader2,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import {
  AIAdvisorOpenAIKeyStatus,
  StockAnalysisFinancialRow,
  StockAnalysisRun,
  StockAnalysisRunSummary,
  StockAnalysisSource,
  apiFetch,
  percent
} from "@/lib/api";

type StockAnalysisModelMode = "foundation" | "ollama";

const modelModes: Array<{ id: StockAnalysisModelMode; label: string; helper: string }> = [
  { id: "ollama", label: "Ollama", helper: "Auto-selects a local model" },
  { id: "foundation", label: "Foundation", helper: "Auto-selects an OpenAI model" }
];

export function StockAnalysisTool({ keyStatus }: { keyStatus: AIAdvisorOpenAIKeyStatus | null }) {
  const [query, setQuery] = useState("");
  const [modelMode, setModelMode] = useState<StockAnalysisModelMode>("ollama");
  const [ollamaModelOverride, setOllamaModelOverride] = useState("");
  const [activeRun, setActiveRun] = useState<StockAnalysisRun | null>(null);
  const [history, setHistory] = useState<StockAnalysisRunSummary[]>([]);
  const [loading, setLoading] = useState("history");
  const [error, setError] = useState("");
  const [runMessage, setRunMessage] = useState("");
  const isOllama = modelMode === "ollama";
  const hasKey = isOllama || Boolean(keyStatus?.has_key);

  useEffect(() => {
    void loadHistory();
  }, []);

  const sourceStatus = useMemo(() => {
    if (!activeRun) return "Waiting";
    if (activeRun.source_status === "complete") return "Full context";
    if (activeRun.source_status === "partial") return "Partial context";
    return "Sparse context";
  }, [activeRun]);

  async function loadHistory() {
    setLoading((current) => (current ? current : "history"));
    setError("");
    try {
      setHistory(await apiFetch<StockAnalysisRunSummary[]>("/stock-analysis/runs"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load Equity Research history.");
    } finally {
      setLoading("");
    }
  }

  async function openRun(runId: number) {
    setLoading(`run-${runId}`);
    setError("");
    setRunMessage("");
    try {
      setActiveRun(await apiFetch<StockAnalysisRun>(`/stock-analysis/runs/${runId}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open saved Equity Research analysis.");
    } finally {
      setLoading("");
    }
  }

  async function runAnalysis(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanQuery = query.trim();
    if (!cleanQuery) {
      setError("Enter a ticker or company name.");
      return;
    }
    if (!hasKey) {
      setError("Save an OpenAI API key before generating an equity research analysis.");
      return;
    }
    setLoading("run");
    setError("");
    setRunMessage("");
    setActiveRun(null);
    try {
      const result = await apiFetch<StockAnalysisRun>("/stock-analysis/run", {
        method: "POST",
        body: JSON.stringify(stockAnalysisPayload(cleanQuery, modelMode, ollamaModelOverride))
      });
      setActiveRun(result);
      setHistory((current) => [result, ...current.filter((item) => item.id !== result.id)].slice(0, 30));
      setRunMessage(result.reused_from_cache ? result.cache_message ?? "Opened a saved analysis; no new OpenAI tokens were used." : "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate Equity Research analysis.");
    } finally {
      setLoading("");
    }
  }

  return (
    <>
      <section className="dashboard-panel stock-analysis-head">
        <div>
          <p className="eyebrow">Equity Research</p>
          <h2>Wall Street-style stock analysis with live financials, valuation, moat, and risk framing.</h2>
          <div className="stock-analysis-source-line">
            <span><BarChart3 size={14} /> 5Y financials</span>
            <span><Target size={14} /> DCF model</span>
            <span><TrendingUp size={14} /> Peer valuation</span>
            <span><ShieldCheck size={14} /> Research stance only</span>
          </div>
        </div>
        <div className="stock-analysis-status">
          <span className={hasKey ? "status-pill" : "risk-pill"}>{isOllama ? "Ollama router" : hasKey ? "Foundation key ready" : "Key required"}</span>
          <span className="status-pill">{sourceStatus}</span>
        </div>
      </section>

      <form className="dashboard-panel stock-analysis-form" onSubmit={runAnalysis}>
        <div className="field">
          <label htmlFor="stock-analysis-query">Ticker or company</label>
          <div className="stock-analysis-search-box">
            <Search size={16} />
            <input
              id="stock-analysis-query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="CSCO or Cisco"
              autoComplete="off"
            />
          </div>
        </div>
        <div className="stock-analysis-model-control" role="radiogroup" aria-label="AI model">
          {modelModes.map((item) => (
            <button type="button" key={item.id} className={modelMode === item.id ? "active" : ""} onClick={() => setModelMode(item.id)}>
              <strong>{item.label}</strong>
              <span>{item.helper}</span>
            </button>
          ))}
        </div>
        {isOllama && (
          <label className="stock-analysis-model-override">
            <span>Local model override</span>
            <input
              value={ollamaModelOverride}
              onChange={(event) => setOllamaModelOverride(event.target.value)}
              placeholder="Auto or llama3.1:8b"
              autoComplete="off"
            />
          </label>
        )}
        <button className="primary-button stock-analysis-run-button" type="submit" disabled={loading === "run" || !hasKey}>
          {loading === "run" ? <Loader2 size={16} className="spin-icon" /> : <Sparkles size={16} />}
          {loading === "run" ? "Building analysis" : "Generate analysis"}
        </button>
      </form>

      {(loading === "run" || activeRun?.model_routing?.model) && (
        <section className="dashboard-panel stock-analysis-router-flow">
          <Bot size={18} />
          <div>
            <span>Model Router</span>
            <strong>{stockRouterDetail(activeRun, modelMode, loading === "run")}</strong>
          </div>
        </section>
      )}

      <section className="dashboard-panel stock-analysis-notice">
        <ShieldCheck size={18} />
        <p>Educational research only. FinanceOS uses research stance language instead of buy, sell, hold, price target, order, or allocation instructions.</p>
      </section>

      {!hasKey && (
        <section className="dashboard-panel stock-analysis-warning-panel">
          <AlertTriangle size={18} />
          <p>Save an encrypted OpenAI key in the left rail to generate Equity Research analyses. Previously saved runs can still be opened from history.</p>
        </section>
      )}

      {error && <div className="error">{error}</div>}
      {runMessage && <div className="stock-analysis-cache-note">{runMessage}</div>}

      {activeRun ? (
        <div className="stock-analysis-layout">
          <section className="dashboard-panel stock-analysis-output-panel">
            <RunHeader run={activeRun} />
            <MetricStrip run={activeRun} />
            <FinancialChart rows={activeRun.financials} />
            <div className="stock-analysis-digest-grid">
              <TextCard title="Executive Summary" text={activeRun.digest.executive_summary} />
              <TextCard title="Business Model" text={activeRun.digest.business_model} />
              <TextCard title="Moat" text={activeRun.digest.moat_summary} badge={activeRun.digest.moat_score == null ? "N/A" : `${activeRun.digest.moat_score}/10`} />
              <ListCard title="Competitor Comparison" items={activeRun.digest.competitor_comparison} />
              <ListCard title="Industry Trends" items={activeRun.digest.industry_trends} />
              <TextCard title="Financial Health" text={activeRun.digest.financial_health} />
              <TextCard title="Valuation" text={activeRun.digest.valuation_summary} />
              <TextCard title="Growth Potential" text={activeRun.digest.growth_potential} />
              <TextCard title="Institutional Perspective" text={activeRun.digest.institutional_perspective} />
              <TextCard title="Latest Earnings" text={activeRun.digest.latest_earnings} />
              <TextCard title="12-24 Month Outlook" text={activeRun.digest.outlook_12_24_months} />
              <ListCard title="Bull vs Bear Debate" items={activeRun.digest.bull_bear_debate} />
            </div>
            <RiskPanel run={activeRun} />
            <ScenarioPanel run={activeRun} />
            {activeRun.digest.raw_markdown && (
              <section className="stock-analysis-raw">
                <h3>Raw response</h3>
                <p>{activeRun.digest.raw_markdown}</p>
              </section>
            )}
          </section>

          <aside className="stock-analysis-rail">
            <FinancialTable rows={activeRun.financials} />
            <PeerPanel run={activeRun} />
            <SourcePanel sources={activeRun.sources} />
            <HistoryPanel history={history} activeId={activeRun.id} loading={loading} onOpen={openRun} />
          </aside>
        </div>
      ) : (
        <div className="stock-analysis-layout">
          <section className="dashboard-panel stock-analysis-empty">
            <Building2 size={36} />
            <h2>No equity analysis selected</h2>
            <p>Enter a ticker to fetch profile, five-year statements, valuation context, recent earnings source metadata, and generate a saved educational analysis.</p>
          </section>
          <aside className="stock-analysis-rail">
            <HistoryPanel history={history} activeId={null} loading={loading} onOpen={openRun} />
          </aside>
        </div>
      )}
    </>
  );
}

function RunHeader({ run }: { run: StockAnalysisRun }) {
  return (
    <div className="stock-analysis-run-head">
      <div>
        <span>{stockModelLabel(run)} | {formatDateTime(run.created_at)}</span>
        <h2>{run.ticker} equity research</h2>
        <p>{run.company_name}{run.sector ? ` | ${run.sector}` : ""}{run.industry ? ` | ${run.industry}` : ""}</p>
      </div>
      <div className={`stock-analysis-stance ${stanceClass(run.research_stance)}`}>
        <span>Research stance</span>
        <strong>{run.research_stance}</strong>
      </div>
    </div>
  );
}

function stockAnalysisPayload(query: string, modelMode: StockAnalysisModelMode, ollamaModelOverride: string) {
  const override = normalizeOllamaOverride(ollamaModelOverride);
  if (modelMode === "ollama" && override) {
    return {
      query,
      model: `ollama:${override}`
    };
  }
  return {
    query,
    model: "auto",
    model_mode: modelMode
  };
}

function normalizeOllamaOverride(value: string) {
  return value.trim().replace(/^ollama:/i, "");
}

function stockModelLabel(run: StockAnalysisRun) {
  const displayName = run.model_routing?.display_name;
  const mode = run.model_routing?.mode;
  if (typeof displayName === "string" && typeof mode === "string") {
    return `${displayName} · ${mode}`;
  }
  return run.model;
}

function stockRouterDetail(run: StockAnalysisRun | null, modelMode: StockAnalysisModelMode, loading: boolean) {
  if (loading) {
    return modelMode === "ollama" ? "Choosing local model" : "Choosing foundation model";
  }
  const displayName = run?.model_routing?.display_name;
  const model = run?.model_routing?.model ?? run?.model;
  if (typeof displayName === "string" && typeof model === "string") {
    return `${displayName} (${model})`;
  }
  return typeof model === "string" ? model : "";
}

function MetricStrip({ run }: { run: StockAnalysisRun }) {
  const dcf = run.valuation.dcf;
  return (
    <div className="stock-analysis-metric-strip">
      <Metric label="Price" value={currencyCents(run.valuation.current_price)} />
      <Metric label="Forward P/E" value={numberLabel(run.valuation.forward_pe)} />
      <Metric label="DCF estimate" value={currencyCents(dcf.fair_value_per_share)} helper={dcf.upside_downside_pct == null ? undefined : `${percent(dcf.upside_downside_pct)} model gap`} />
      <Metric label="Moat score" value={run.digest.moat_score == null ? "N/A" : `${run.digest.moat_score}/10`} />
    </div>
  );
}

function Metric({ label, value, helper }: { label: string; value: string; helper?: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
      {helper && <em>{helper}</em>}
    </div>
  );
}

function FinancialChart({ rows }: { rows: StockAnalysisFinancialRow[] }) {
  const chartRows = rows.map((row) => ({
    year: row.year,
    revenue: row.revenue == null ? null : row.revenue / 1_000_000_000,
    net_income: row.net_income == null ? null : row.net_income / 1_000_000_000,
    free_cash_flow: row.free_cash_flow == null ? null : row.free_cash_flow / 1_000_000_000,
    profit_margin: row.profit_margin == null ? null : row.profit_margin * 100
  }));
  return (
    <section className="stock-analysis-chart-panel">
      <div className="panel-header">
        <h2>Five-year financials</h2>
        <LineChart size={18} />
      </div>
      {chartRows.length ? (
        <ResponsiveContainer width="100%" height={330}>
          <ComposedChart data={chartRows} margin={{ left: 4, right: 16, top: 8, bottom: 8 }}>
            <CartesianGrid stroke="#17352d" strokeDasharray="3 3" />
            <XAxis dataKey="year" tick={{ fontSize: 11, fill: "#8da99e" }} axisLine={{ stroke: "#24463c" }} tickLine={{ stroke: "#24463c" }} />
            <YAxis yAxisId="money" width={58} tickFormatter={(value) => `$${Number(value).toFixed(0)}B`} tick={{ fontSize: 11, fill: "#8da99e" }} axisLine={{ stroke: "#24463c" }} tickLine={{ stroke: "#24463c" }} />
            <YAxis yAxisId="margin" orientation="right" width={46} tickFormatter={(value) => `${Number(value).toFixed(0)}%`} tick={{ fontSize: 11, fill: "#8da99e" }} axisLine={{ stroke: "#24463c" }} tickLine={{ stroke: "#24463c" }} />
            <Tooltip formatter={(value, name) => [name === "Profit margin" ? `${Number(value).toFixed(1)}%` : `$${Number(value).toFixed(1)}B`, name]} contentStyle={{ border: "1px solid #17352d", borderRadius: 8, background: "#07110e", color: "#d8f5ea" }} />
            <Legend wrapperStyle={{ color: "#b6d9cb", fontSize: 12 }} />
            <Bar yAxisId="money" dataKey="revenue" name="Revenue" fill="#5eead4" radius={[4, 4, 0, 0]} />
            <Bar yAxisId="money" dataKey="free_cash_flow" name="Free cash flow" fill="#38bdf8" radius={[4, 4, 0, 0]} />
            <Line yAxisId="money" type="monotone" dataKey="net_income" name="Net income" stroke="#fbbf24" strokeWidth={2.2} dot={{ r: 3 }} connectNulls />
            <Line yAxisId="margin" type="monotone" dataKey="profit_margin" name="Profit margin" stroke="#c084fc" strokeWidth={2.2} dot={false} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      ) : (
        <p className="fine-print">Five-year financial rows were not available from the data provider.</p>
      )}
    </section>
  );
}

function TextCard({ title, text, badge }: { title: string; text: string; badge?: string }) {
  return (
    <article className="stock-analysis-digest-card">
      <div>
        <h3>{title}</h3>
        {badge && <span>{badge}</span>}
      </div>
      <p>{text || "Not available from the supplied data."}</p>
    </article>
  );
}

function ListCard({ title, items }: { title: string; items: string[] }) {
  return (
    <article className="stock-analysis-digest-card">
      <h3>{title}</h3>
      {items.length ? <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul> : <p>Not available from the supplied data.</p>}
    </article>
  );
}

function RiskPanel({ run }: { run: StockAnalysisRun }) {
  return (
    <section className="stock-analysis-section">
      <div className="panel-header">
        <h2>Ranked risks</h2>
        <AlertTriangle size={18} />
      </div>
      <div className="stock-analysis-risk-list">
        {run.digest.risks.length ? run.digest.risks.map((risk) => (
          <article key={`${risk.rank}-${risk.title}`}>
            <span>#{risk.rank}{risk.severity ? ` | ${risk.severity}` : ""}</span>
            <strong>{risk.title}</strong>
            <p>{risk.detail}</p>
          </article>
        )) : <p className="fine-print">No ranked risks returned.</p>}
      </div>
    </section>
  );
}

function ScenarioPanel({ run }: { run: StockAnalysisRun }) {
  return (
    <section className="stock-analysis-section">
      <div className="panel-header">
        <h2>Bull / base / bear</h2>
        <Target size={18} />
      </div>
      <div className="stock-analysis-scenario-grid">
        {run.digest.scenarios.length ? run.digest.scenarios.map((scenario) => (
          <article key={scenario.case} className={scenario.case.toLowerCase()}>
            <span>{scenario.case}</span>
            <p>{scenario.summary}</p>
            {scenario.key_drivers.length ? <ul>{scenario.key_drivers.map((driver) => <li key={driver}>{driver}</li>)}</ul> : null}
          </article>
        )) : <p className="fine-print">Scenarios were not available from the model output.</p>}
      </div>
    </section>
  );
}

function FinancialTable({ rows }: { rows: StockAnalysisFinancialRow[] }) {
  return (
    <section className="dashboard-panel stock-analysis-table-panel">
      <div className="panel-header">
        <h2>Financial rows</h2>
        <BarChart3 size={18} />
      </div>
      <div className="stock-analysis-table">
        <div className="stock-analysis-table-row header">
          <span>Year</span>
          <span>Revenue</span>
          <span>Net income</span>
          <span>FCF</span>
          <span>Margin</span>
          <span>Debt</span>
          <span>ROE</span>
        </div>
        {rows.length ? rows.map((row) => (
          <div className="stock-analysis-table-row" key={row.year}>
            <strong>{row.year}</strong>
            <span>{compactMoney(row.revenue)}</span>
            <span>{compactMoney(row.net_income)}</span>
            <span>{compactMoney(row.free_cash_flow)}</span>
            <span>{ratioLabel(row.profit_margin)}</span>
            <span>{compactMoney(row.debt)}</span>
            <span>{ratioLabel(row.roe)}</span>
          </div>
        )) : <p className="fine-print">No annual rows available.</p>}
      </div>
    </section>
  );
}

function PeerPanel({ run }: { run: StockAnalysisRun }) {
  return (
    <section className="dashboard-panel stock-analysis-peer-panel">
      <div className="panel-header">
        <h2>Peer valuation</h2>
        <TrendingUp size={18} />
      </div>
      <div className="stock-analysis-peer-list">
        {run.valuation.peers.length ? run.valuation.peers.map((peer) => (
          <article key={peer.symbol}>
            <strong>{peer.symbol}<small>{peer.company_name}</small></strong>
            <span>Fwd P/E {numberLabel(peer.forward_pe)}</span>
            <span>P/S {numberLabel(peer.price_to_sales)}</span>
          </article>
        )) : <p className="fine-print">Peer metrics were not available.</p>}
      </div>
    </section>
  );
}

function SourcePanel({ sources }: { sources: StockAnalysisSource[] }) {
  const workingSources = sources.filter((source) => source.status === "found");
  return (
    <section className="dashboard-panel stock-analysis-source-panel">
      <div className="panel-header">
        <h2>Sources</h2>
        <ExternalLink size={18} />
      </div>
      <div className="stock-analysis-source-grid">
        {workingSources.length ? workingSources.map((source) => (
          <article className={`stock-analysis-source-card ${source.status}`} key={`${source.source_type}-${source.title}`}>
            <span className="status-pill">{source.status}</span>
            <h3>{source.title}</h3>
            <p>{source.document_type ?? source.source_type}</p>
            {source.excerpt && <p className="stock-analysis-source-excerpt">{source.excerpt}</p>}
            {source.url && <a className="ghost-button" href={source.url} target="_blank" rel="noreferrer"><ExternalLink size={15} /> Open source</a>}
          </article>
        )) : <p className="fine-print">No working earnings source is attached to this analysis. The saved report still keeps the available market and financial data.</p>}
      </div>
    </section>
  );
}

function HistoryPanel({
  history,
  activeId,
  loading,
  onOpen
}: {
  history: StockAnalysisRunSummary[];
  activeId: number | null;
  loading: string;
  onOpen: (runId: number) => void;
}) {
  return (
    <section className="dashboard-panel stock-analysis-history-panel">
      <div className="panel-header">
        <h2>Run History</h2>
        <History size={18} />
      </div>
      <div className="stock-analysis-history-list">
        {history.length ? history.map((run) => (
          <button type="button" key={run.id} className={activeId === run.id ? "active" : ""} onClick={() => onOpen(run.id)}>
            <strong>{run.ticker} <small>{run.research_stance}</small></strong>
            <span>{run.company_name}</span>
            <em>{loading === `run-${run.id}` ? "Opening" : formatDateTime(run.created_at)}</em>
          </button>
        )) : (
          <p className="fine-print">{loading === "history" ? "Loading history..." : "No Equity Research runs saved yet."}</p>
        )}
      </div>
    </section>
  );
}

function stanceClass(value: string) {
  const lower = value.toLowerCase();
  if (lower.includes("attractive")) return "attractive";
  if (lower.includes("avoid")) return "avoid";
  return "neutral";
}

function numberLabel(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return "N/A";
  return value.toFixed(1);
}

function ratioLabel(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return "N/A";
  return percent(value);
}

function currencyCents(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return "N/A";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function compactMoney(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return "N/A";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_000_000_000_000) return `${sign}$${(abs / 1_000_000_000_000).toFixed(2)}T`;
  if (abs >= 1_000_000_000) return `${sign}$${(abs / 1_000_000_000).toFixed(2)}B`;
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(1)}M`;
  return `${sign}$${abs.toFixed(0)}`;
}

function formatDateTime(value?: string | null) {
  if (!value) return "N/A";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}
