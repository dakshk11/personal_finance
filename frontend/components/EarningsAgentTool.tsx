"use client";

import {
  AlertTriangle,
  Building2,
  ExternalLink,
  FileSearch,
  History,
  Loader2,
  Newspaper,
  Search,
  ShieldCheck,
  Sparkles
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  AIAdvisorOpenAIKeyStatus,
  EarningsAgentMetric,
  EarningsAgentModel,
  EarningsAgentRun,
  EarningsAgentRunSummary,
  EarningsAgentSource,
  apiFetch
} from "@/lib/api";
import { OllamaConfigStrip, OllamaModelButton, effectiveModelId } from "@/components/OllamaModelPicker";

type ModelPicker = EarningsAgentModel | "ollama";

const openAIModels: Array<{ id: EarningsAgentModel; label: string; helper: string }> = [
  { id: "gpt-5.5", label: "Quality", helper: "gpt-5.5" },
  { id: "gpt-5.4", label: "Balanced", helper: "gpt-5.4" },
  { id: "gpt-5.4-mini", label: "Cost", helper: "gpt-5.4-mini" }
];

export function EarningsAgentTool({ keyStatus }: { keyStatus: AIAdvisorOpenAIKeyStatus | null }) {
  const [query, setQuery] = useState("");
  const [model, setModel] = useState<ModelPicker>("gpt-5.4");
  const [ollamaModelName, setOllamaModelName] = useState("llama3");
  const [ollamaBaseUrl, setOllamaBaseUrl] = useState("http://127.0.0.1:11434");
  const [useGoose, setUseGoose] = useState(false);
  const isOllama = model === "ollama";
  const [activeRun, setActiveRun] = useState<EarningsAgentRun | null>(null);
  const [history, setHistory] = useState<EarningsAgentRunSummary[]>([]);
  const [loading, setLoading] = useState("history");
  const [error, setError] = useState("");
  const hasKey = isOllama || Boolean(keyStatus?.has_key);

  useEffect(() => {
    void loadHistory();
  }, []);

  const sources = activeRun?.sources ?? [];
  const sourceStatus = useMemo(() => {
    if (!activeRun) return "Waiting";
    if (activeRun.source_status === "complete") return "SEC + transcript";
    if (activeRun.source_status === "partial") return "Partial sources";
    return "No source text";
  }, [activeRun]);

  async function loadHistory() {
    setLoading((current) => (current ? current : "history"));
    setError("");
    try {
      setHistory(await apiFetch<EarningsAgentRunSummary[]>("/earnings-agent/runs"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load Earnings Agent history.");
    } finally {
      setLoading("");
    }
  }

  async function openRun(runId: number) {
    setLoading(`run-${runId}`);
    setError("");
    try {
      setActiveRun(await apiFetch<EarningsAgentRun>(`/earnings-agent/runs/${runId}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open saved earnings digest.");
    } finally {
      setLoading("");
    }
  }

  async function runDigest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanQuery = query.trim();
    if (!cleanQuery) {
      setError("Enter a ticker or company name.");
      return;
    }
    if (!hasKey) {
      setError("Save an OpenAI API key before generating an earnings digest.");
      return;
    }
    setLoading("run");
    setError("");
    try {
      const result = await apiFetch<EarningsAgentRun>("/earnings-agent/run", {
        method: "POST",
        body: JSON.stringify({
          query: cleanQuery,
          model: effectiveModelId(model, ollamaModelName, useGoose),
          ...(isOllama ? { ollama_base_url: ollamaBaseUrl.trim() || "http://127.0.0.1:11434" } : {})
        })
      });
      setActiveRun(result);
      setHistory((current) => [result, ...current.filter((item) => item.id !== result.id)].slice(0, 30));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate earnings digest.");
    } finally {
      setLoading("");
    }
  }

  return (
    <>
      <section className="dashboard-panel earnings-agent-head">
        <div>
          <p className="eyebrow">Earnings Agent</p>
          <h2>SEC exhibits and earnings transcripts distilled into an educational research digest.</h2>
          <div className="earnings-agent-source-line">
            <span><FileSearch size={14} /> SEC Exhibit 99.1 / 99.2</span>
            <span><Newspaper size={14} /> Motley + company IR</span>
            <span><FileSearch size={14} /> YouTube / Quartr status</span>
            <span><ShieldCheck size={14} /> No advice language</span>
          </div>
        </div>
        <div className="earnings-agent-status">
          <span className={hasKey ? "status-pill" : "risk-pill"}>{isOllama ? (useGoose ? "Goose + tools" : "Ollama (local)") : hasKey ? "OpenAI key ready" : "Key required"}</span>
          <span className="status-pill">{sourceStatus}</span>
        </div>
      </section>

      <form className="dashboard-panel earnings-agent-form" onSubmit={runDigest}>
        <div className="field">
          <label htmlFor="earnings-query">Ticker or company</label>
          <div className="earnings-search-box">
            <Search size={16} />
            <input
              id="earnings-query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="AAPL or Apple"
              autoComplete="off"
            />
          </div>
        </div>
        <div className="earnings-model-control" role="radiogroup" aria-label="AI model">
          {openAIModels.map((item) => (
            <button type="button" key={item.id} className={model === item.id ? "active" : ""} onClick={() => setModel(item.id)}>
              <strong>{item.label}</strong>
              <span>{item.helper}</span>
            </button>
          ))}
          <OllamaModelButton active={isOllama} onClick={() => setModel("ollama")} />
        </div>
        {isOllama && (
          <OllamaConfigStrip
            modelName={ollamaModelName}
            baseUrl={ollamaBaseUrl}
            useGoose={useGoose}
            onModelNameChange={setOllamaModelName}
            onBaseUrlChange={setOllamaBaseUrl}
            onUseGooseChange={setUseGoose}
          />
        )}
        <button className="primary-button earnings-run-button" type="submit" disabled={loading === "run" || !hasKey}>
          {loading === "run" ? <Loader2 size={16} className="spin-icon" /> : <Sparkles size={16} />}
          {loading === "run" ? "Digesting earnings" : "Generate digest"}
        </button>
      </form>

      {!hasKey && (
        <section className="dashboard-panel earnings-agent-notice">
          <AlertTriangle size={18} />
          <p>Save an encrypted OpenAI key in the left rail to generate earnings digests. Source history can still be opened after a digest has been saved.</p>
        </section>
      )}

      {error && <div className="error">{error}</div>}

      {activeRun ? (
        <div className="earnings-agent-layout">
          <section className="dashboard-panel earnings-digest-panel">
            <div className="earnings-digest-head">
              <div>
                <span>{activeRun.model} | {formatDateTime(activeRun.created_at)}</span>
                <h2>{activeRun.ticker} earnings digest</h2>
                <p>{activeRun.company_name}{activeRun.cik ? ` | CIK ${activeRun.cik}` : ""}</p>
              </div>
              <div className={`earnings-source-radar ${activeRun.source_status}`}>
                <span>Sources</span>
                <strong>{activeRun.source_status}</strong>
              </div>
            </div>

            <div className="earnings-digest-grid">
              <DigestCard title="Executive Summary" text={activeRun.digest.executive_summary} />
              <ListCard title="Top Takeaways" items={activeRun.digest.top_takeaways} />
              <MetricsCard metrics={activeRun.digest.financial_metrics} />
              <DigestCard title="Management Tone" text={activeRun.digest.management_tone} />
              <ListCard title="Risks" items={activeRun.digest.risks} tone="risk" />
              <ListCard title="Deep Dive Next" items={activeRun.digest.deep_dive_questions} />
              <ListCard title="Source Notes" items={activeRun.digest.source_notes} />
            </div>

            {activeRun.digest.raw_markdown && (
              <section className="earnings-raw-markdown">
                <h3>Raw response</h3>
                <p>{activeRun.digest.raw_markdown}</p>
              </section>
            )}
          </section>

          <aside className="earnings-agent-rail">
            <section className="dashboard-panel earnings-source-panel">
              <div className="panel-header">
                <h2>Sources</h2>
                <FileSearch size={18} />
              </div>
              <div className="earnings-source-grid">
                {sources.map((source) => <SourceCard source={source} key={`${source.source_type}-${source.title}`} />)}
              </div>
            </section>

            {activeRun.warnings.length ? (
              <section className="dashboard-panel earnings-warning-panel">
                <div className="panel-header">
                  <h2>Warnings</h2>
                  <AlertTriangle size={18} />
                </div>
                {activeRun.warnings.slice(0, 6).map((warning) => <p key={warning}>{warning}</p>)}
              </section>
            ) : null}

            <HistoryPanel history={history} activeId={activeRun.id} loading={loading} onOpen={openRun} />
          </aside>
        </div>
      ) : (
        <div className="earnings-agent-layout">
          <section className="dashboard-panel earnings-empty">
            <Building2 size={36} />
            <h2>No earnings digest selected</h2>
            <p>Enter a ticker to fetch recent SEC earnings exhibits and matching transcript coverage, then generate an educational digest.</p>
          </section>
          <aside className="earnings-agent-rail">
            <HistoryPanel history={history} activeId={null} loading={loading} onOpen={openRun} />
          </aside>
        </div>
      )}
    </>
  );
}

function SourceCard({ source }: { source: EarningsAgentSource }) {
  return (
    <article className={`earnings-source-card ${source.status}`}>
      <div>
        <span className={source.status === "found" ? "status-pill" : "risk-pill"}>{source.status}</span>
        <h3>{sourceLabel(source.source_type)}</h3>
        <p>{source.title}</p>
      </div>
      <dl>
        <div><dt>Type</dt><dd>{source.document_type ?? "N/A"}</dd></div>
        <div><dt>Date</dt><dd>{formatShortDate(source.filing_date)}</dd></div>
      </dl>
      {source.excerpt && <p className="earnings-source-excerpt">{source.excerpt}</p>}
      {source.warning && <p className="earnings-source-warning">{source.warning}</p>}
      {source.url && (
        <a className="ghost-button" href={source.url} target="_blank" rel="noreferrer">
          <ExternalLink size={15} /> Open source
        </a>
      )}
    </article>
  );
}

function sourceLabel(sourceType: string) {
  if (sourceType === "sec") return "SEC EDGAR";
  if (sourceType === "sec_presentation") return "SEC Presentation";
  if (sourceType === "company_ir") return "Company IR";
  if (sourceType === "motley") return "Earnings Transcript";
  if (sourceType === "youtube") return "YouTube";
  if (sourceType === "quartr") return "Quartr";
  return "Source";
}

function DigestCard({ title, text }: { title: string; text: string }) {
  return (
    <article className="earnings-digest-card">
      <h3>{title}</h3>
      <p>{text || "Not available in the provided source materials."}</p>
    </article>
  );
}

function ListCard({ title, items, tone }: { title: string; items: string[]; tone?: "risk" }) {
  return (
    <article className={`earnings-digest-card ${tone ?? ""}`}>
      <h3>{title}</h3>
      {items.length ? (
        <ul>
          {items.map((item) => <li key={item}>{item}</li>)}
        </ul>
      ) : (
        <p>Not available in the provided source materials.</p>
      )}
    </article>
  );
}

function MetricsCard({ metrics }: { metrics: EarningsAgentMetric[] }) {
  return (
    <article className="earnings-digest-card earnings-metrics-card">
      <h3>Financial Metrics</h3>
      {metrics.length ? (
        <div className="earnings-metric-list">
          {metrics.map((metric) => (
            <div key={`${metric.name}-${metric.value}`}>
              <span>{metric.name}</span>
              <strong>{metric.value}</strong>
              {metric.context && <p>{metric.context}</p>}
            </div>
          ))}
        </div>
      ) : (
        <p>Not available in the provided source materials.</p>
      )}
    </article>
  );
}

function HistoryPanel({
  history,
  activeId,
  loading,
  onOpen
}: {
  history: EarningsAgentRunSummary[];
  activeId: number | null;
  loading: string;
  onOpen: (runId: number) => void;
}) {
  return (
    <section className="dashboard-panel earnings-history-panel">
      <div className="panel-header">
        <h2>Run History</h2>
        <History size={18} />
      </div>
      <div className="earnings-history-list">
        {history.length ? history.map((run) => (
          <button type="button" key={run.id} className={activeId === run.id ? "active" : ""} onClick={() => onOpen(run.id)}>
            <strong>{run.ticker} <small>{run.source_status}</small></strong>
            <span>{run.company_name}</span>
            <em>{loading === `run-${run.id}` ? "Opening" : formatDateTime(run.created_at)}</em>
          </button>
        )) : (
          <p className="fine-print">{loading === "history" ? "Loading history..." : "No earnings digests saved yet."}</p>
        )}
      </div>
    </section>
  );
}

function formatDateTime(value?: string | null) {
  if (!value) return "N/A";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}

function formatShortDate(value?: string | null) {
  if (!value) return "N/A";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
