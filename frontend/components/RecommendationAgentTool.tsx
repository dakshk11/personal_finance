"use client";

import {
  Bot,
  CheckCircle2,
  CircleDashed,
  Gauge,
  Loader2,
  Plus,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  X
} from "lucide-react";
import { useMemo, useState } from "react";
import {
  AIAdvisorAlpacaKeyStatus,
  AIAdvisorLunarCrushKeyStatus,
  AIAdvisorNvidiaKeyStatus,
  AIAdvisorOpenAIKeyStatus,
  AIAdvisorTipRanksKeyStatus,
  AlpacaRecommendationQuoteSession,
  RecommendationOptionRow,
  RecommendationAgentRun,
  RecommendationAgentRunRequest,
  RecommendationQuoteRow,
  apiFetch
} from "@/lib/api";

type AgentModelMode = "foundation" | "nvidia" | "ollama";

const MODEL_MODES: Array<{ id: AgentModelMode; label: string; helper: string }> = [
  { id: "foundation", label: "Foundation", helper: "Auto-selects an OpenAI model" },
  { id: "nvidia", label: "NVIDIA", helper: "Hosted open-source NIM" },
  { id: "ollama", label: "Ollama", helper: "Auto-selects a local model" },
];

const NVIDIA_MODELS = [
  "minimaxai/minimax-m2.7",
  "zhipuai/glm-5.1",
  "moonshot-ai/kimi-2.5",
  "deepseek-ai/deepseek-v4-flash",
  "nvidia/nemotron-3-ultra-550b-a55b",
];

const STAGES = ["Scanners", "Model Router", "First LLM", "TipRanks", "Final LLM"];

export function RecommendationAgentTool({
  keyStatus,
  tipRanksKeyStatus,
  alpacaKeyStatus,
  lunarCrushKeyStatus,
  nvidiaKeyStatus,
  tipRanksApiKey,
  decisionContext
}: {
  keyStatus: AIAdvisorOpenAIKeyStatus | null;
  tipRanksKeyStatus: AIAdvisorTipRanksKeyStatus | null;
  alpacaKeyStatus: AIAdvisorAlpacaKeyStatus | null;
  lunarCrushKeyStatus: AIAdvisorLunarCrushKeyStatus | null;
  nvidiaKeyStatus: AIAdvisorNvidiaKeyStatus | null;
  tipRanksApiKey: string;
  decisionContext: string;
}) {
  const [modelMode, setModelMode] = useState<AgentModelMode>("foundation");
  const [ollamaModelOverride, setOllamaModelOverride] = useState("");
  const [nvidiaModel, setNvidiaModel] = useState(NVIDIA_MODELS[0]);
  const [maxCandidates, setMaxCandidates] = useState(25);
  const [finalistCount, setFinalistCount] = useState(8);
  const [includeTipRanks, setIncludeTipRanks] = useState(true);
  const [includeLunarCrush, setIncludeLunarCrush] = useState(true);
  const [currentPortfolio, setCurrentPortfolio] = useState("");
  const [result, setResult] = useState<RecommendationAgentRun | null>(null);
  const [quoteViewOpen, setQuoteViewOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const isOllama = modelMode === "ollama";
  const isNvidia = modelMode === "nvidia";
  const canRun = !loading && (isOllama || (isNvidia ? Boolean(nvidiaKeyStatus?.has_key) : Boolean(keyStatus?.has_key)));

  const activeStages = useMemo(() => {
    if (!loading) return result ? STAGES : [];
    return STAGES;
  }, [loading, result]);

  async function runAgent() {
    if (!canRun) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const payload: RecommendationAgentRunRequest = {
        ...recommendationAgentModelPayload(modelMode, ollamaModelOverride, nvidiaModel),
        max_candidates: maxCandidates,
        finalist_count: Math.min(finalistCount, maxCandidates),
        include_tipranks: includeTipRanks,
        include_lunarcrush: includeLunarCrush,
        ...(includeTipRanks && tipRanksApiKey.trim() ? { tipranks_api_key: tipRanksApiKey.trim() } : {}),
        ...(decisionContext.trim() ? { user_context: decisionContext.trim() } : {}),
        ...(currentPortfolio.trim() ? { current_portfolio: currentPortfolio.trim() } : {}),
      };
      setResult(await apiFetch<RecommendationAgentRun>("/ai-advisor/recommendation-agent/run", {
        method: "POST",
        body: JSON.stringify(payload),
      }));
      setQuoteViewOpen(false);
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
          <span className={isOllama ? "status-pill" : (isNvidia ? nvidiaKeyStatus?.has_key : keyStatus?.has_key) ? "status-pill" : "risk-pill"}>
            {isOllama ? "Ollama router" : isNvidia ? (nvidiaKeyStatus?.has_key ? "NVIDIA key ready" : "NVIDIA key required") : keyStatus?.has_key ? "Foundation key ready" : "Foundation key required"}
          </span>
          <button className="primary-button" type="button" onClick={runAgent} disabled={!canRun}>
            {loading ? <Loader2 size={16} className="spin-icon" /> : <Sparkles size={16} />}
            {loading ? "Running agents" : "Run agent"}
          </button>
        </div>
      </section>

      <section className="dashboard-panel recommendation-agent-controls">
        <div className="panel-header">
          <h2>Provider and scope</h2>
          <Bot size={18} />
        </div>
        <div className="stock-analysis-model-control recommendation-model-control" role="radiogroup" aria-label="Recommendation Agent AI model">
          {MODEL_MODES.map((item) => (
            <button type="button" key={item.id} className={modelMode === item.id ? "active" : ""} onClick={() => setModelMode(item.id)}>
              <strong>{item.label}</strong>
              <span>{item.helper}</span>
            </button>
          ))}
        </div>
        {isOllama && (
          <label className="stock-analysis-override-input">
            <span>Local model override</span>
            <input
              value={ollamaModelOverride}
              onChange={(event) => setOllamaModelOverride(event.target.value)}
              placeholder="llama3.1:8b or qwen2.5:7b"
            />
            <small>Leave blank for auto routing. Use this to avoid slower models like deepseek-r1:7b.</small>
          </label>
        )}
        {isNvidia && (
          <label className="stock-analysis-override-input">
            <span>NVIDIA hosted model</span>
            <select value={nvidiaModel} onChange={(event) => setNvidiaModel(event.target.value)}>
              {NVIDIA_MODELS.map((item) => (
                <option value={item} key={item}>{item}</option>
              ))}
            </select>
            <small>Defaults to the first hosted open-source model and stays within the approved NVIDIA NIM list.</small>
          </label>
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
          <label className="recommendation-toggle">
            <input type="checkbox" checked={includeLunarCrush} onChange={(event) => setIncludeLunarCrush(event.target.checked)} />
            <span>LunarCrush enrichment</span>
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
        {includeTipRanks && !tipRanksApiKey.trim() && !tipRanksKeyStatus?.has_key && <p className="fine-print">TipRanks enrichment will use the configured backend provider if available. Save a TipRanks key in the sidebar to use the remote MCP provider automatically.</p>}
        {includeTipRanks && !tipRanksApiKey.trim() && tipRanksKeyStatus?.has_key && <p className="fine-print">TipRanks enrichment will use the encrypted key saved in the local database.</p>}
        {includeLunarCrush && !lunarCrushKeyStatus?.has_key && <p className="fine-print">Save a LunarCrush key in the sidebar to add social sentiment and market-intelligence enrichment.</p>}
        {includeLunarCrush && lunarCrushKeyStatus?.has_key && <p className="fine-print">LunarCrush enrichment will use the encrypted key saved in the local database.</p>}
        {!isOllama && !isNvidia && !keyStatus?.has_key && <div className="error">Save an OpenAI API key before running Recommendation Agent, or switch to Ollama.</div>}
        {isNvidia && !nvidiaKeyStatus?.has_key && <div className="error">Save an NVIDIA API key before running Recommendation Agent with hosted NVIDIA models, or switch provider.</div>}
        {error && <div className="error">{error}</div>}
      </section>

      <section className="recommendation-stage-grid">
        {STAGES.map((stage) => (
          <div className="dashboard-panel recommendation-stage" key={stage}>
            {activeStages.includes(stage) ? loading ? <Loader2 size={16} className="spin-icon" /> : <CheckCircle2 size={16} /> : <CircleDashed size={16} />}
            <span>
              {stage}
              {stage === "Model Router" && <em>{routerStageDetail(result, modelMode, loading)}</em>}
            </span>
          </div>
        ))}
      </section>

      {result && (
        <>
          <section className="dashboard-panel recommendation-summary">
            <div>
              <p className="eyebrow">Run summary</p>
              <h2>{result.ranked_ideas.length} ranked ideas</h2>
              <p className="fine-print">{modelLabel(result)} · {formatDateTime(result.generated_at)}</p>
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
            <button className="primary-button" type="button" onClick={() => setQuoteViewOpen(true)} disabled={!alpacaKeyStatus?.has_key}>
              <TrendingUp size={16} />
              Open quote pull
            </button>
          </section>

          {quoteViewOpen && (
            <RecommendationQuotesView
              seedSymbols={result.ranked_ideas.map((idea) => idea.symbol)}
              alpacaReady={Boolean(alpacaKeyStatus?.has_key)}
              onBack={() => setQuoteViewOpen(false)}
            />
          )}

          {!quoteViewOpen && <section className="recommendation-results">
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
                <LunarCrushBlock value={idea.lunarcrush} />
                {idea.warnings.length > 0 && <p className="fine-print">{idea.warnings.join(" ")}</p>}
              </article>
            ))}
          </section>}

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

function RecommendationQuotesView({
  seedSymbols,
  alpacaReady,
  onBack
}: {
  seedSymbols: string[];
  alpacaReady: boolean;
  onBack: () => void;
}) {
  const [symbols, setSymbols] = useState(() => normalizeSymbols(seedSymbols).slice(0, 30));
  const [input, setInput] = useState("");
  const [session, setSession] = useState<AlpacaRecommendationQuoteSession | null>(null);
  const [quotes, setQuotes] = useState<Record<string, RecommendationQuoteRow>>({});
  const [optionChains, setOptionChains] = useState<AlpacaRecommendationQuoteSession["option_chains"]>({});
  const [optionOverlay, setOptionOverlay] = useState<Record<string, Partial<RecommendationOptionRow> & { timestamp?: string | null }>>({});
  const [statusLines, setStatusLines] = useState<string[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function pullQuotes(nextSymbols = symbols) {
    if (!alpacaReady) {
      setError("Save an Alpaca API key and secret in the left rail before pulling quotes.");
      return;
    }
    const normalized = normalizeSymbols(nextSymbols).slice(0, 30);
    if (normalized.length === 0) {
      setError("Add at least one stock symbol.");
      return;
    }
    setLoading(true);
    setError("");
    setStatusLines(["Pulling Alpaca quotes and option snapshot..."]);
    try {
      const created = await apiFetch<AlpacaRecommendationQuoteSession>("/alpaca/recommendation-quotes/snapshot", {
        method: "POST",
        body: JSON.stringify({ symbols: normalized, include_options: true, stream_options: false })
      });
      setSession(created);
      setSymbols(created.symbols);
      setQuotes(Object.fromEntries(created.quotes.map((quote) => [quote.symbol, quote])));
      setOptionChains(created.option_chains);
      setOptionOverlay({});
      setStatusLines([
        `Pulled: ${created.symbols.length}/${created.max_symbols} stocks, ${created.option_contracts.length}/${created.max_option_quotes} option quotes.`
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not pull Alpaca quotes.");
    } finally {
      setLoading(false);
    }
  }

  function addSymbol() {
    const next = normalizeSymbols([...symbols, ...input.split(/[\s,]+/)]);
    if (next.length > 30) {
      setError("Alpaca quote pull is capped at 30 symbols per request.");
      return;
    }
    setSymbols(next);
    setInput("");
    setError("");
  }

  function removeSymbol(symbol: string) {
    setSymbols((current) => current.filter((item) => item !== symbol));
  }

  const rows = symbols.map((symbol) => quotes[symbol] ?? { symbol, signals: [] });
  const selectedOptions = selectedSymbol ? optionChains[selectedSymbol] : null;

  return (
    <section className="dashboard-panel recommendation-quotes">
      <div className="recommendation-quotes-head">
        <div>
          <p className="eyebrow">Alpaca quote pull</p>
          <h2>Recommendation watchlist</h2>
          <p className="fine-print">{symbols.length} / 30 equities · best put/call option quotes are refreshed on demand.</p>
        </div>
        <div className="recommendation-agent-actions">
          <button className="ghost-button" type="button" onClick={onBack}><X size={16} /> Back to results</button>
          <button className="primary-button" type="button" onClick={() => pullQuotes()} disabled={loading || !alpacaReady}>
            {loading ? <Loader2 size={16} className="spin-icon" /> : <RefreshCw size={16} />}
            {session ? "Refresh quotes" : "Pull quotes"}
          </button>
        </div>
      </div>
      {!alpacaReady && <div className="error">Save an Alpaca API key and secret in the left rail before pulling quotes.</div>}
      {error && <div className="error">{error}</div>}
      <div className="recommendation-symbol-editor">
        <input value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") addSymbol(); }} placeholder="Add symbols: AAPL, MSFT" />
        <button className="secondary-button" type="button" onClick={addSymbol} disabled={symbols.length >= 30}><Plus size={16} /> Add</button>
      </div>
      <div className="recommendation-symbol-chip-row">
        {symbols.map((symbol) => (
          <button type="button" key={symbol} onClick={() => removeSymbol(symbol)}>
            {symbol} <X size={13} />
          </button>
        ))}
      </div>
      {statusLines.length > 0 && <div className="recommendation-stream-status">{statusLines.map((line) => <p key={line}>{line}</p>)}</div>}
      <div className="recommendation-quotes-table-wrap">
        <table className="recommendation-quotes-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Bid / Ask</th>
              <th>Size</th>
              <th>IV</th>
              <th>CSP 30d</th>
              <th>CC 30d</th>
              <th>Best put</th>
              <th>Best call</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((quote) => (
              <tr key={quote.symbol}>
                <td><strong>{quote.symbol}</strong><span>{quote.stage === "pulled" ? "Pulled" : quote.stage === "live" ? "Live" : "Snapshot"}</span></td>
                <td>{money(quote.bid)} / {money(quote.ask)}</td>
                <td>{fmt(quote.bid_size)} / {fmt(quote.ask_size)}</td>
                <td>{fmtPct(quote.iv_rank)}</td>
                <td>{fmtPct(quote.csp_30d)}</td>
                <td>{fmtPct(quote.cc_30d)}</td>
                <td><OptionMini option={quote.best_put} overlay={quote.best_put ? optionOverlay[quote.best_put.occ_symbol] : undefined} /></td>
                <td><OptionMini option={quote.best_call} overlay={quote.best_call ? optionOverlay[quote.best_call.occ_symbol] : undefined} /></td>
                <td>{quote.timestamp ? formatDateTime(quote.timestamp) : "N/A"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="recommendation-option-card-grid">
        {rows.map((quote) => (
          <article key={`${quote.symbol}-options`} className="recommendation-option-card">
            <div>
              <strong>{quote.symbol}</strong>
              <span>{(quote.signals ?? []).slice(0, 3).join(" · ") || "No option signal yet"}</span>
            </div>
            <OptionMini option={quote.best_put} overlay={quote.best_put ? optionOverlay[quote.best_put.occ_symbol] : undefined} label="Best CSP" />
            <OptionMini option={quote.best_call} overlay={quote.best_call ? optionOverlay[quote.best_call.occ_symbol] : undefined} label="Best CC" />
            <button className="ghost-button" type="button" onClick={() => setSelectedSymbol(quote.symbol)}>Option chain</button>
          </article>
        ))}
      </div>
      {selectedSymbol && selectedOptions && (
        <OptionChainModal
          symbol={selectedSymbol}
          data={selectedOptions}
          overlays={optionOverlay}
          onClose={() => setSelectedSymbol(null)}
        />
      )}
    </section>
  );
}

function OptionMini({ option, overlay, label }: { option?: RecommendationOptionRow | null; overlay?: Partial<RecommendationOptionRow>; label?: string }) {
  if (!option) return <span className="fine-print">{label ? `${label}: N/A` : "N/A"}</span>;
  const bid = overlay?.bid ?? option.bid;
  const ask = overlay?.ask ?? option.ask;
  return (
    <span className="option-mini">
      {label && <em>{label}</em>}
      <strong>{option.option_type}{option.strike} · {option.dte}d</strong>
      <span>{money(bid)} / {money(ask)} · Δ {fmt(option.delta)}</span>
      <span>{fmtPct(option.annualized_yield)} ann. · {fmtPct(option.pct_away)} away</span>
    </span>
  );
}

function OptionChainModal({
  symbol,
  data,
  overlays,
  onClose
}: {
  symbol: string;
  data: { puts: RecommendationOptionRow[]; calls: RecommendationOptionRow[] };
  overlays: Record<string, Partial<RecommendationOptionRow> & { timestamp?: string | null }>;
  onClose: () => void;
}) {
  const rows = [...data.puts, ...data.calls].sort((a, b) => a.expiry.localeCompare(b.expiry) || a.strike - b.strike).slice(0, 160);
  return (
    <div className="recommendation-option-modal" role="dialog" aria-modal="true">
      <div className="recommendation-option-modal-panel">
        <div className="panel-header">
          <h2>{symbol} option chain</h2>
          <button className="ghost-button" type="button" onClick={onClose}><X size={16} /> Close</button>
        </div>
        <div className="recommendation-quotes-table-wrap">
          <table className="recommendation-quotes-table">
            <thead>
              <tr>
                <th>Expiry</th><th>DTE</th><th>Type</th><th>Strike</th><th>Bid</th><th>Ask</th><th>Mid</th><th>Delta</th><th>IV</th><th>Ann yield</th><th>Away</th><th>POP</th><th>OI</th><th>Vol</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const overlay = overlays[row.occ_symbol];
                const bid = overlay?.bid ?? row.bid;
                const ask = overlay?.ask ?? row.ask;
                return (
                  <tr key={row.occ_symbol}>
                    <td>{row.expiry}</td><td>{row.dte}</td><td>{row.option_type}</td><td>{money(row.strike)}</td>
                    <td>{money(bid)}</td><td>{money(ask)}</td><td>{money(overlay?.mid ?? row.mid)}</td><td>{fmt(row.delta)}</td>
                    <td>{fmtPct(row.iv)}</td><td>{fmtPct(row.annualized_yield)}</td><td>{fmtPct(row.pct_away)}</td><td>{fmtPct(row.pop)}</td>
                    <td>{fmt(row.open_interest)}</td><td>{fmt(row.volume)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
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

function LunarCrushBlock({ value }: { value?: Record<string, unknown> | null }) {
  if (!value) {
    return <div className="recommendation-tipranks muted">LunarCrush enrichment unavailable for this idea.</div>;
  }
  const rows = Object.entries(value).slice(0, 8);
  return (
    <div className="recommendation-tipranks">
      <strong>LunarCrush</strong>
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

function normalizeSymbols(values: string[]) {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    const symbol = value.trim().toUpperCase();
    if (!symbol || seen.has(symbol) || !/^[A-Z0-9.-]{1,12}$/.test(symbol)) continue;
    seen.add(symbol);
    out.push(symbol);
  }
  return out;
}

function recommendationAgentModelPayload(modelMode: AgentModelMode, ollamaModelOverride: string, nvidiaModel: string) {
  const override = normalizeOllamaOverride(ollamaModelOverride);
  if (modelMode === "ollama" && override) {
    return {
      model: `ollama:${override}`
    };
  }
  if (modelMode === "nvidia") {
    const model = NVIDIA_MODELS.includes(nvidiaModel) ? nvidiaModel : NVIDIA_MODELS[0];
    return {
      model: `nvidia:${model}`,
      model_mode: "nvidia" as const
    };
  }
  return {
    model: "auto",
    model_mode: modelMode
  };
}

function normalizeOllamaOverride(value: string) {
  return value.trim().replace(/^ollama:/i, "");
}

function money(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "N/A";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: value >= 100 ? 2 : 4 }).format(value);
}

function fmt(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "N/A";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
}

function fmtPct(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "N/A";
  return `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value)}%`;
}

function modelLabel(result: RecommendationAgentRun) {
  const displayName = result.model_routing?.display_name;
  const mode = result.model_routing?.mode;
  if (typeof displayName === "string" && typeof mode === "string") {
    return `${displayName} · ${mode}`;
  }
  return result.model;
}

function routerStageDetail(result: RecommendationAgentRun | null, modelMode: AgentModelMode, loading: boolean) {
  if (loading) {
    if (modelMode === "ollama") return "Choosing local model";
    if (modelMode === "nvidia") return "Using NVIDIA hosted model";
    return "Choosing foundation model";
  }
  const displayName = result?.model_routing?.display_name;
  const model = result?.model_routing?.model ?? result?.model;
  if (typeof displayName === "string" && typeof model === "string") {
    return `${displayName} (${model})`;
  }
  return typeof model === "string" ? model : "";
}

function formatDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}
