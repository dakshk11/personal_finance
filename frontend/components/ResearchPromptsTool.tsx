"use client";

import { CheckCircle2, ExternalLink, Loader2, Play, Search, ShieldCheck } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  AIAdvisorOpenAIKeyStatus,
  AIAdvisorResearchPromptProvider,
  AIAdvisorResearchPromptRun,
  AIAdvisorResearchPromptRunRequest,
  AIAdvisorResearchPromptRunSummary,
  apiFetch
} from "@/lib/api";

type ResearchField = {
  id: string;
  label: string;
  placeholder?: string;
  required?: boolean;
};

type ResearchTemplate = {
  id: string;
  title: string;
  summary: string;
  fields: ResearchField[];
};

const templates: ResearchTemplate[] = [
  {
    id: "hedge-designer",
    title: "Hedge Designer",
    summary: "Design an efficient hedge using options data and inverse ETFs.",
    fields: [{ id: "sector_market", label: "Sector or market exposure", placeholder: "Technology, Nasdaq 100, semiconductors", required: true }]
  },
  {
    id: "hedge-fund-13f",
    title: "Top Hedge Fund 13F Moves",
    summary: "Compare recent top hedge fund accumulation, exits, and sector shifts.",
    fields: [{ id: "focus", label: "Optional focus", placeholder: "AI stocks, energy, Q1 2026" }]
  },
  {
    id: "correlation-anomalies",
    title: "Correlation Anomalies",
    summary: "Find unusual asset correlations and normalization trade setups.",
    fields: [{ id: "asset_focus", label: "Optional asset focus", placeholder: "Gold, long bonds, equities, dollar" }]
  },
  {
    id: "dividend-trap-screen",
    title: "Dividend Trap Screen",
    summary: "Screen high yields for payout, cash-flow, and balance-sheet warning signs.",
    fields: [{ id: "sector_focus", label: "Optional sector focus", placeholder: "REITs, utilities, telecom" }]
  },
  {
    id: "short-squeeze-screen",
    title: "Short Squeeze Candidates",
    summary: "Find high short-interest stocks with borrow pressure and catalysts.",
    fields: [{ id: "watchlist_or_sector", label: "Optional watchlist or sector", placeholder: "EVs, biotech, retail" }]
  },
  {
    id: "macro-playbook",
    title: "Macro Playbook",
    summary: "Map inflation, rates, GDP, and jobs data to historical sector playbooks.",
    fields: [{ id: "region", label: "Optional region", placeholder: "US, global, Europe" }]
  },
  {
    id: "sentiment-fundamental-divergence",
    title: "Sentiment/Fundamental Divergence",
    summary: "Find negative sentiment where fundamentals appear stronger than the narrative.",
    fields: [{ id: "sector_or_watchlist", label: "Optional sector or watchlist", placeholder: "Software, banks, AAPL MSFT NVDA" }]
  }
];

const openAIModels = ["gpt-5.4", "gpt-5.4-mini", "gpt-5.5"];

export function ResearchPromptsTool({ keyStatus }: { keyStatus: AIAdvisorOpenAIKeyStatus | null }) {
  const [activeTemplateId, setActiveTemplateId] = useState(templates[0].id);
  const [provider, setProvider] = useState<AIAdvisorResearchPromptProvider>("openai_web");
  const [openAIModel, setOpenAIModel] = useState("gpt-5.4");
  const [gooseModel, setGooseModel] = useState("llama3.1:8b");
  const [ollamaBaseUrl, setOllamaBaseUrl] = useState("http://127.0.0.1:11434");
  const [inputsByTemplate, setInputsByTemplate] = useState<Record<string, Record<string, string>>>({});
  const [runs, setRuns] = useState<AIAdvisorResearchPromptRunSummary[]>([]);
  const [activeRun, setActiveRun] = useState<AIAdvisorResearchPromptRun | null>(null);
  const [loading, setLoading] = useState<"runs" | "run" | "open" | null>(null);
  const [error, setError] = useState("");

  const activeTemplate = useMemo(() => templates.find((template) => template.id === activeTemplateId) ?? templates[0], [activeTemplateId]);
  const templateInputs = inputsByTemplate[activeTemplate.id] ?? {};
  const missingRequired = activeTemplate.fields.filter((field) => field.required && !templateInputs[field.id]?.trim());
  const selectedModel = provider === "openai_web" ? openAIModel : gooseModel.trim();
  const canRun = missingRequired.length === 0 && loading !== "run" && (provider === "goose" ? Boolean(gooseModel.trim()) : Boolean(keyStatus?.has_key));

  useEffect(() => {
    void loadRuns();
  }, []);

  async function loadRuns() {
    setLoading("runs");
    setError("");
    try {
      setRuns(await apiFetch<AIAdvisorResearchPromptRunSummary[]>("/ai-advisor/research-prompts/runs"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load research prompt history.");
    } finally {
      setLoading(null);
    }
  }

  function updateInput(fieldId: string, value: string) {
    setInputsByTemplate((current) => ({
      ...current,
      [activeTemplate.id]: {
        ...(current[activeTemplate.id] ?? {}),
        [fieldId]: value
      }
    }));
  }

  async function runPrompt(event: FormEvent) {
    event.preventDefault();
    if (!canRun) return;
    setLoading("run");
    setError("");
    try {
      const body: AIAdvisorResearchPromptRunRequest = {
        template_id: activeTemplate.id,
        provider,
        model: selectedModel,
        inputs: templateInputs,
        ollama_base_url: provider === "goose" ? ollamaBaseUrl : null
      };
      const run = await apiFetch<AIAdvisorResearchPromptRun>("/ai-advisor/research-prompts/run", {
        method: "POST",
        body: JSON.stringify(body)
      });
      setActiveRun(run);
      setRuns((current) => [run, ...current.filter((item) => item.id !== run.id)].slice(0, 50));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Research prompt failed.");
    } finally {
      setLoading(null);
    }
  }

  async function openRun(runId: number) {
    setLoading("open");
    setError("");
    try {
      setActiveRun(await apiFetch<AIAdvisorResearchPromptRun>(`/ai-advisor/research-prompts/runs/${runId}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open research prompt run.");
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="research-prompts">
      <section className="dashboard-panel research-prompts-head">
        <div>
          <p className="eyebrow">Research Prompts</p>
          <h2>Run source-backed market research templates.</h2>
          <p>Choose a template, select OpenAI Web Search or local Goose tooling, and save the resulting research run.</p>
        </div>
        <span className="status-pill"><ShieldCheck size={14} /> Saved runs</span>
      </section>

      <section className="dashboard-panel research-provider-panel">
        <div className="panel-header">
          <div>
            <h2>Research engine</h2>
            <p className="fine-print">OpenAI Web Search is the default for current data and structured source capture.</p>
          </div>
          <Search size={18} />
        </div>
        <div className="research-provider-grid">
          <button type="button" className={provider === "openai_web" ? "active" : ""} onClick={() => setProvider("openai_web")}>
            <strong>OpenAI Web Search</strong>
            <span>{keyStatus?.has_key ? "Saved key ready" : "Save an OpenAI key first"}</span>
          </button>
          <button type="button" className={provider === "goose" ? "active" : ""} onClick={() => setProvider("goose")}>
            <strong>Goose + local tools</strong>
            <span>Uses your local Goose/Ollama setup</span>
          </button>
        </div>
        <div className="research-model-row">
          {provider === "openai_web" ? (
            <div className="field">
              <label htmlFor="research-openai-model">OpenAI model</label>
              <select id="research-openai-model" value={openAIModel} onChange={(event) => setOpenAIModel(event.target.value)}>
                {openAIModels.map((model) => <option key={model} value={model}>{model}</option>)}
              </select>
            </div>
          ) : (
            <>
              <div className="field">
                <label htmlFor="research-goose-model">Local model</label>
                <input id="research-goose-model" value={gooseModel} onChange={(event) => setGooseModel(event.target.value)} placeholder="llama3.1:8b" />
              </div>
              <div className="field">
                <label htmlFor="research-ollama-base">Ollama base URL</label>
                <input id="research-ollama-base" value={ollamaBaseUrl} onChange={(event) => setOllamaBaseUrl(event.target.value)} placeholder="http://127.0.0.1:11434" />
              </div>
            </>
          )}
        </div>
        {provider === "openai_web" && !keyStatus?.has_key && <div className="error">Save an OpenAI API key before running OpenAI Web Search.</div>}
        {provider === "goose" && <p className="fine-print">Goose source reliability depends on your local Goose tools, web access, and Ollama model quality.</p>}
      </section>

      <div className="research-prompts-grid">
        <section className="dashboard-panel">
          <div className="panel-header">
            <h2>Templates</h2>
          </div>
          <div className="research-template-grid">
            {templates.map((template) => (
              <button
                type="button"
                key={template.id}
                className={activeTemplate.id === template.id ? "active" : ""}
                onClick={() => setActiveTemplateId(template.id)}
              >
                <strong>{template.title}</strong>
                <span>{template.summary}</span>
              </button>
            ))}
          </div>
        </section>

        <form className="dashboard-panel research-run-panel" onSubmit={runPrompt}>
          <div className="panel-header">
            <div>
              <h2>{activeTemplate.title}</h2>
              <p className="fine-print">{provider === "openai_web" ? "OpenAI Web Search" : "Goose + local tools"} · {selectedModel || "model required"}</p>
            </div>
            {activeRun?.template_id === activeTemplate.id && <span className="status-pill"><CheckCircle2 size={14} /> Latest run loaded</span>}
          </div>
          <div className="research-field-stack">
            {activeTemplate.fields.map((field) => (
              <div className="field" key={`${activeTemplate.id}-${field.id}`}>
                <label htmlFor={`${activeTemplate.id}-${field.id}`}>{field.label}{field.required ? " *" : ""}</label>
                <input
                  id={`${activeTemplate.id}-${field.id}`}
                  value={templateInputs[field.id] ?? ""}
                  placeholder={field.placeholder}
                  onChange={(event) => updateInput(field.id, event.target.value)}
                />
              </div>
            ))}
          </div>
          {error && <div className="error">{error}</div>}
          {missingRequired.length > 0 && <div className="error">Missing required input: {missingRequired.map((field) => field.label).join(", ")}</div>}
          <button className="primary-button ai-generate-button" type="submit" disabled={!canRun}>
            {loading === "run" ? <Loader2 size={16} className="spin-icon" /> : <Play size={16} />}
            {loading === "run" ? "Running research" : "Run research prompt"}
          </button>
        </form>
      </div>

      <div className="research-output-grid">
        <section className="dashboard-panel ai-report-output">
          <div className="panel-header">
            <div>
              <h2>{activeRun ? activeRun.template_title : "Research output"}</h2>
              <p className="fine-print">{activeRun ? `${activeRun.provider} · ${activeRun.model} · ${formatDateTime(activeRun.created_at)}` : "Run a template or open a saved history item."}</p>
            </div>
          </div>
          {activeRun ? (
            <>
              <ResearchText value={activeRun.response_text} />
              {activeRun.warnings.length > 0 && (
                <div className="research-warning-list">
                  {activeRun.warnings.map((warning) => <span key={warning}>{warning}</span>)}
                </div>
              )}
              <div className="research-source-list">
                <h3>Sources</h3>
                {activeRun.sources.length ? activeRun.sources.map((source) => (
                  <a key={source.url} href={source.url} target="_blank" rel="noreferrer">
                    <ExternalLink size={14} />
                    {source.title || source.url}
                  </a>
                )) : <p className="fine-print">No structured sources were extracted for this run.</p>}
              </div>
            </>
          ) : (
            <p className="fine-print">Saved research output will appear here with extracted source links.</p>
          )}
        </section>

        <section className="dashboard-panel">
          <div className="panel-header">
            <h2>Run history</h2>
            {loading === "runs" && <Loader2 size={16} className="spin-icon" />}
          </div>
          <div className="ai-report-list">
            {runs.length ? runs.map((run) => (
              <button type="button" key={run.id} onClick={() => openRun(run.id)} className={activeRun?.id === run.id ? "active" : ""} disabled={loading === "open"}>
                <strong>{run.template_title}</strong>
                <span>{run.provider} · {run.model} · {formatDateTime(run.created_at)}</span>
              </button>
            )) : <p className="fine-print">No research prompt runs yet.</p>}
          </div>
        </section>
      </div>
    </div>
  );
}

function ResearchText({ value }: { value: string }) {
  const lines = value.split("\n").map((line) => line.trim()).filter(Boolean);
  return (
    <div className="ai-report-markdown">
      {lines.map((line, index) => {
        if (line.startsWith("### ")) return <h4 key={`${line}-${index}`}>{line.replace(/^###\s+/, "")}</h4>;
        if (line.startsWith("## ")) return <h3 key={`${line}-${index}`}>{line.replace(/^##\s+/, "")}</h3>;
        if (line.startsWith("# ")) return <h2 key={`${line}-${index}`}>{line.replace(/^#\s+/, "")}</h2>;
        if (/^[-*]\s+/.test(line)) return <p key={`${line}-${index}`}>- {line.replace(/^[-*]\s+/, "")}</p>;
        return <p key={`${line}-${index}`}>{line}</p>;
      })}
    </div>
  );
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  }).format(new Date(value));
}
