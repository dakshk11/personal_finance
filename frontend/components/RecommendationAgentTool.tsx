"use client";

import {
  Bot,
  CheckCircle2,
  CircleDashed,
  Gauge,
  Loader2,
  ShieldCheck,
  Sparkles,
  TrendingUp
} from "lucide-react";
import { useMemo, useState } from "react";
import {
  AIAdvisorOpenAIKeyStatus,
  RecommendationAgentRun,
  RecommendationAgentRunRequest,
  apiFetch
} from "@/lib/api";
import { OllamaConfigStrip, OllamaModelButton, effectiveModelId } from "@/components/OllamaModelPicker";

type AgentModel = "gpt-5.5" | "gpt-5.4" | "gpt-5.4-mini" | "ollama";

const OPENAI_MODELS: Array<{ id: Exclude<AgentModel, "ollama">; label: string; helper: string }> = [
  { id: "gpt-5.5", label: "Quality", helper: "gpt-5.5" },
  { id: "gpt-5.4", label: "Balanced", helper: "gpt-5.4" },
  { id: "gpt-5.4-mini", label: "Cost", helper: "gpt-5.4-mini" },
];

const STAGES = ["Scanners", "First LLM", "TipRanks", "Final LLM"];

export function RecommendationAgentTool({
  keyStatus,
  tipRanksApiKey,
  decisionContext
}: {
  keyStatus: AIAdvisorOpenAIKeyStatus | null;
  tipRanksApiKey: string;
  decisionContext: string;
}) {
  const [model, setModel] = useState<AgentModel>("gpt-5.4");
  const [ollamaModelName, setOllamaModelName] = useState("llama3");
  const [ollamaBaseUrl, setOllamaBaseUrl] = useState("http://localhost:11434");
  const [maxCandidates, setMaxCandidates] = useState(25);
  const [finalistCount, setFinalistCount] = useState(8);
  const [includeTipRanks, setIncludeTipRanks] = useState(true);
  const [currentPortfolio, setCurrentPortfolio] = useState("");
  const [result, setResult] = useState<RecommendationAgentRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const isOllama = model === "ollama";
  const activeModelId = effectiveModelId(model, ollamaModelName, false);
  const canRun = !loading && (isOllama ? Boolean(ollamaModelName.trim()) : Boolean(keyStatus?.has_key));

  const activeStages = useMemo(() => {
    if (!loading) return result ? STAGES : [];
    return STAGES;
  }, [loading, result]);

  async function runAgent() {
    if (!canRun) return;
    setLoading(true);
    setError("");
    try {
      const payload: RecommendationAgentRunRequest = {
        model: activeModelId,
        max_candidates: maxCandidates,
        finalist_count: Math.min(finalistCount, maxCandidates),
        include_tipranks: includeTipRanks,
        ...(includeTipRanks && tipRanksApiKey.trim() ? { tipranks_api_key: tipRanksApiKey.trim() } : {}),
        ...(decisionContext.trim() ? { user_context: decisionContext.trim() } : {}),
        ...(currentPortfolio.trim() ? { current_portfolio: currentPortfolio.trim() } : {}),
        ...(isOllama ? { ollama_base_url: ollamaBaseUrl.trim() || "http://localhost:11434" } : {}),
      };
      setResult(await apiFetch<RecommendationAgentRun>("/ai-advisor/recommendation-agent/run", {
        method: "POST",
        body: JSON.stringify(payload),
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not run Recommendation Agent.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="recommendation-agent">
      <section className="dashboard-panel recommendation-agent-head">
        <div>
          <p className="eyebrow">Recommendation Agent</p>
          <h2 className="recommendation-agent-title">Full Agent: multi-scanner idea ranking with optional TipRanks verification.</h2>
          <p>Wheel, Breakout, Smart Candles, and OptiTrade evidence are merged before the selected model ranks the shortlist.</p>
        </div>
        <div className="recommendation-agent-actions">
          <span className={isOllama ? "status-pill" : keyStatus?.has_key ? "status-pill" : "risk-pill"}>
            {isOllama ? `Ollama · ${ollamaModelName || "llama3"}` : keyStatus?.has_key ? "OpenAI key ready" : "OpenAI key required"}
          </span>
          <button className="primary-button" type="button" onClick={runAgent} disabled={!canRun}>
            {loading ? <Loader2 size={16} className="spin-icon" /> : <Sparkles size={16} />}
            {loading ? "Running agents" : "Run agent"}
          </button>
        </div>
      </section>

      <section className="dashboard-panel recommendation-agent-controls">
        <div className="panel-header">
          <h2>Model and scope</h2>
          <Bot size={18} />
        </div>
        <div className="stock-analysis-model-control recommendation-model-control" role="radiogroup" aria-label="Recommendation Agent AI model">
          {OPENAI_MODELS.map((item) => (
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
            useGoose={false}
            showGoose={false}
            onModelNameChange={setOllamaModelName}
            onBaseUrlChange={setOllamaBaseUrl}
            onUseGooseChange={() => undefined}
          />
        )}
        <div className="recommendation-control-grid">
          <label>
            <span>Candidate cap</span>
            <input type="number" min={5} max={60} value={maxCandidates} onChange={(event) => setMaxCandidates(clampInt(event.target.value, 5, 60))} />
          </label>
          <label>
            <span>Finalists</span>
            <input type="number" min={1} max={15} value={finalistCount} onChange={(event) => setFinalistCount(clampInt(event.target.value, 1, 15))} />
          </label>
          <label className="recommendation-toggle">
            <input type="checkbox" checked={includeTipRanks} onChange={(event) => setIncludeTipRanks(event.target.checked)} />
            <span>TipRanks enrichment</span>
          </label>
        </div>
        <label className="recommendation-portfolio-input">
          <span>Current stock portfolio</span>
          <textarea
            value={currentPortfolio}
            onChange={(event) => setCurrentPortfolio(event.target.value)}
            placeholder="NVDA:10,AVGO:5,TSM:8"
            rows={3}
          />
        </label>
        {includeTipRanks && !tipRanksApiKey.trim() && <p className="fine-print">TipRanks enrichment will use the configured backend provider if available. Add a TipRanks key in the sidebar to use the remote MCP provider for this run.</p>}
        {!isOllama && !keyStatus?.has_key && <div className="error">Save an OpenAI API key before running Recommendation Agent, or switch to Ollama.</div>}
        {error && <div className="error">{error}</div>}
      </section>

      <section className="recommendation-stage-grid">
        {STAGES.map((stage) => (
          <div className="dashboard-panel recommendation-stage" key={stage}>
            {activeStages.includes(stage) ? loading ? <Loader2 size={16} className="spin-icon" /> : <CheckCircle2 size={16} /> : <CircleDashed size={16} />}
            <span>{stage}</span>
          </div>
        ))}
      </section>

      {result && (
        <>
          <section className="dashboard-panel recommendation-summary">
            <div>
              <p className="eyebrow">Run summary</p>
              <h2>{result.ranked_ideas.length} ranked ideas</h2>
              <p className="fine-print">{result.model} · {formatDateTime(result.generated_at)}</p>
            </div>
            <div className="recommendation-summary-grid">
              {Object.entries(result.scanner_summary).map(([name, summary]) => (
                <div key={name}>
                  <span>{name}</span>
                  <strong>{String(summary.status ?? "unknown")}</strong>
                  <em>{String(summary.candidate_count ?? 0)} candidates</em>
                </div>
              ))}
            </div>
          </section>

          <section className="recommendation-results">
            {result.ranked_ideas.map((idea) => (
              <article className="dashboard-panel recommendation-card" key={`${idea.rank}-${idea.symbol}`}>
                <div className="recommendation-card-head">
                  <div>
                    <p className="eyebrow">Rank #{idea.rank}</p>
                    <h2>{idea.symbol}</h2>
                  </div>
                  <span className="status-pill"><TrendingUp size={14} /> {idea.verdict}</span>
                </div>
                <p>{idea.rationale}</p>
                <div className="recommendation-pill-row">
                  {idea.source_agents.map((agent) => <span key={agent}><ShieldCheck size={13} /> {agent}</span>)}
                  {idea.strategy_tags.slice(0, 5).map((tag) => <span key={tag}><Gauge size={13} /> {tag}</span>)}
                </div>
                <div className="recommendation-evidence">
                  {idea.evidence.slice(0, 4).map((line) => <p key={line}>{line}</p>)}
                </div>
                <div className="recommendation-context-grid">
                  {Object.entries(idea.scanner_scores).map(([key, value]) => (
                    <div key={key}><span>{labelize(key)}</span><strong>{formatNumber(value)}</strong></div>
                  ))}
                </div>
                <TipRanksBlock value={idea.tipranks} />
                {idea.warnings.length > 0 && <p className="fine-print">{idea.warnings.join(" ")}</p>}
              </article>
            ))}
          </section>

          {result.warnings.length > 0 && (
            <section className="dashboard-panel recommendation-warnings">
              <div className="panel-header">
                <h2>Warnings</h2>
                <ShieldCheck size={18} />
              </div>
              {result.warnings.map((warning) => <p key={warning}>{warning}</p>)}
            </section>
          )}
        </>
      )}

      {!result && !loading && (
        <section className="dashboard-panel empty-proposal recommendation-empty">
          <Sparkles size={34} />
          <h2>No recommendation run yet</h2>
          <p>Run the agent to consolidate scanner evidence into a ranked educational research shortlist.</p>
        </section>
      )}
    </div>
  );
}

function TipRanksBlock({ value }: { value?: Record<string, unknown> | null }) {
  if (!value) {
    return <div className="recommendation-tipranks muted">TipRanks enrichment unavailable for this idea.</div>;
  }
  const rows = Object.entries(value).slice(0, 6);
  return (
    <div className="recommendation-tipranks">
      <strong>TipRanks</strong>
      <div>
        {rows.map(([key, item]) => <span key={key}>{labelize(key)}: {String(item)}</span>)}
      </div>
    </div>
  );
}

function clampInt(value: string, min: number, max: number) {
  const parsed = Number.parseInt(value, 10);
  if (Number.isNaN(parsed)) return min;
  return Math.min(max, Math.max(min, parsed));
}

function labelize(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
}

function formatDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}
