"use client";

import {
  Bot,
  CheckCircle2,
  FileText,
  FolderArchive,
  Gauge,
  KeyRound,
  Loader2,
  LockKeyhole,
  MessageSquareText,
  Play,
  ShieldCheck,
  TrendingUp,
  Trash2,
  WalletCards
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { OptionStrategyTool } from "@/components/OptionStrategyTool";
import { PersonalCFOTool } from "@/components/PersonalCFOTool";
import { PortfolioSyncTool } from "@/components/PortfolioSyncTool";
import { RSIPlaybookTool } from "@/components/RSIPlaybookTool";
import {
  AIAdvisorOpenAIKeyStatus,
  AIAdvisorReport,
  AIAdvisorReportSummary,
  AIAdvisorRetirementRunRequest,
  apiFetch
} from "@/lib/api";

type AIModel = AIAdvisorRetirementRunRequest["model"];
type AdvisorTab = "retirement-plan" | "personal-cfo" | "wheel-strategy" | "portfolio-sync" | "rsi-playbook";

type RetirementField = {
  id: string;
  label: string;
  kind?: "short" | "long" | "select";
  options?: string[];
};

type RetirementModule = {
  id: string;
  title: string;
  summary: string;
  fields: RetirementField[];
};

const models: Array<{ id: AIModel; label: string; helper: string }> = [
  { id: "gpt-5.5", label: "Quality", helper: "gpt-5.5" },
  { id: "gpt-5.4", label: "Balanced", helper: "gpt-5.4" },
  { id: "gpt-5.4-mini", label: "Cost", helper: "gpt-5.4-mini" }
];

const modules: RetirementModule[] = [
  {
    id: "full-retirement-blueprint",
    title: "Full Retirement Blueprint",
    summary: "Savings rate, account priority, Social Security timing, inflation, and decade-by-decade portfolio path.",
    fields: [
      { id: "age", label: "Current age" },
      { id: "income", label: "Annual income" },
      { id: "current_savings", label: "Current savings" },
      { id: "retirement_age", label: "Retirement age" },
      { id: "target_monthly_income", label: "Target monthly retirement income" },
      { id: "account_list", label: "Current accounts", kind: "long" },
      { id: "account_balances", label: "Account balances", kind: "long" },
      { id: "employer_match_percent", label: "Employer 401k match percent" },
      { id: "employer_match_limit", label: "Employer match limit" },
      { id: "dependents", label: "Number of dependents" },
      { id: "monthly_expenses", label: "Monthly expenses" }
    ]
  },
  {
    id: "tax-optimization",
    title: "Tax Optimization",
    summary: "Traditional versus Roth, conversion ladder, backdoor Roth, withdrawal sequencing, and missing tax-advantaged strategies.",
    fields: [
      { id: "gross_income", label: "Gross annual income" },
      { id: "income_source", label: "Income source", kind: "select", options: ["salary", "freelance", "business", "investments", "mixed"] },
      { id: "tax_bracket", label: "Current tax bracket" },
      { id: "k401_contribution", label: "401k contribution" },
      { id: "ira_contribution", label: "IRA contribution" },
      { id: "other_accounts_assets", label: "Other accounts or assets", kind: "long" },
      { id: "state", label: "State of residence" },
      { id: "age", label: "Current age" },
      { id: "retirement_age", label: "Retirement age" }
    ]
  },
  {
    id: "portfolio-strategy",
    title: "Portfolio Strategy",
    summary: "Allocation critique, target allocation, five-year glide path, ETFs, expense ratios, and rebalance process.",
    fields: [
      { id: "age", label: "Current age" },
      { id: "retirement_age", label: "Retirement age" },
      { id: "holdings_allocation", label: "Current holdings and percentages", kind: "long" },
      { id: "investable_assets", label: "Total investable assets" },
      { id: "risk_tolerance", label: "Risk tolerance", kind: "select", options: ["conservative", "moderate", "aggressive"] },
      { id: "risk_explanation", label: "Comfort with volatility", kind: "long" },
      { id: "monthly_contribution", label: "Monthly contribution" }
    ]
  },
  {
    id: "risk-stress-test",
    title: "Retirement Risk Stress Test",
    summary: "Sequence risk, withdrawal rate, good/average/bad markets, inflation, guardrails, buffers, and income floors.",
    fields: [
      { id: "retirement_age", label: "Retirement age" },
      { id: "portfolio_amount", label: "Portfolio amount" },
      { id: "monthly_withdrawal", label: "Monthly withdrawal" },
      { id: "retirement_years", label: "Expected retirement years" },
      { id: "allocation_breakdown", label: "Allocation breakdown", kind: "long" },
      { id: "social_security_age", label: "Social Security start age" },
      { id: "social_security_monthly", label: "Monthly Social Security" }
    ]
  },
  {
    id: "social-security-optimization",
    title: "Social Security Optimization",
    summary: "Claiming break-evens, married-couple claiming strategies, spousal benefit review, and portfolio-withdrawal fit.",
    fields: [
      { id: "age", label: "Current age" },
      { id: "spouse_age", label: "Spouse age" },
      { id: "benefit_62", label: "Your benefit at 62" },
      { id: "fra_age", label: "Your full retirement age" },
      { id: "benefit_fra", label: "Your benefit at FRA" },
      { id: "benefit_70", label: "Your benefit at 70" },
      { id: "spouse_benefit_62", label: "Spouse benefit at 62" },
      { id: "spouse_benefit_fra", label: "Spouse benefit at FRA" },
      { id: "spouse_benefit_70", label: "Spouse benefit at 70" },
      { id: "health", label: "Current health", kind: "select", options: ["good", "average", "below average"] },
      { id: "longevity_history", label: "Family longevity history", kind: "long" },
      { id: "portfolio_amount", label: "Portfolio amount saved" },
      { id: "retirement_age", label: "Retirement age" },
      { id: "other_income", label: "Other income sources", kind: "long" }
    ]
  }
];

export default function AIAdvisorPage() {
  const [keyStatus, setKeyStatus] = useState<AIAdvisorOpenAIKeyStatus | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [keyMessage, setKeyMessage] = useState("");
  const [activeModuleId, setActiveModuleId] = useState(modules[0].id);
  const [activeTab, setActiveTab] = useState<AdvisorTab>("retirement-plan");
  const [model, setModel] = useState<AIModel>("gpt-5.4");
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [reports, setReports] = useState<AIAdvisorReportSummary[]>([]);
  const [activeReport, setActiveReport] = useState<AIAdvisorReport | null>(null);
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");

  const activeModule = useMemo(() => modules.find((item) => item.id === activeModuleId) ?? modules[0], [activeModuleId]);
  const missingFields = activeModule.fields.filter((field) => !inputs[field.id]?.trim());
  const canGenerate = Boolean(keyStatus?.has_key) && missingFields.length === 0 && loading !== "report";

  useEffect(() => {
    void bootstrap();
  }, []);

  async function bootstrap() {
    try {
      const [key, history] = await Promise.all([
        apiFetch<AIAdvisorOpenAIKeyStatus>("/ai-advisor/openai-key"),
        apiFetch<AIAdvisorReportSummary[]>("/ai-advisor/reports")
      ]);
      setKeyStatus(key);
      setReports(history);
      setKeyMessage(key.has_key ? `Saved key ${key.key_fingerprint ?? ""}` : "No OpenAI key saved");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load FinanceOS Studio");
    }
  }

  async function saveKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setKeyMessage("");
    if (!apiKey.trim()) {
      setKeyMessage("Enter an OpenAI API key before saving.");
      return;
    }
    setLoading("key");
    try {
      const saved = await apiFetch<AIAdvisorOpenAIKeyStatus>("/ai-advisor/openai-key", {
        method: "PUT",
        body: JSON.stringify({ api_key: apiKey.trim() })
      });
      setApiKey("");
      setKeyStatus(saved);
      setKeyMessage(`Saved ${saved.key_fingerprint ?? "OpenAI key"}`);
    } catch (err) {
      setKeyMessage(err instanceof Error ? err.message : "Could not validate OpenAI key.");
    } finally {
      setLoading("");
    }
  }

  async function deleteKey() {
    setLoading("delete-key");
    setError("");
    try {
      const deleted = await apiFetch<AIAdvisorOpenAIKeyStatus>("/ai-advisor/openai-key", { method: "DELETE" });
      setKeyStatus(deleted);
      setKeyMessage("OpenAI key removed.");
    } catch (err) {
      setKeyMessage(err instanceof Error ? err.message : "Could not remove OpenAI key.");
    } finally {
      setLoading("");
    }
  }

  async function generateReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canGenerate) return;
    setLoading("report");
    setError("");
    try {
      const payload: AIAdvisorRetirementRunRequest = {
        module_id: activeModule.id,
        model,
        inputs: Object.fromEntries(activeModule.fields.map((field) => [field.id, inputs[field.id]?.trim() ?? ""]))
      };
      const report = await apiFetch<AIAdvisorReport>("/ai-advisor/retirement-plan/run", {
        method: "POST",
        body: JSON.stringify(payload)
      });
      setActiveReport(report);
      setReports((current) => [report, ...current.filter((item) => item.id !== report.id)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate retirement report.");
    } finally {
      setLoading("");
    }
  }

  async function openReport(reportId: number) {
    setLoading(`report-${reportId}`);
    setError("");
    try {
      setActiveReport(await apiFetch<AIAdvisorReport>(`/ai-advisor/reports/${reportId}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open saved report.");
    } finally {
      setLoading("");
    }
  }

  function updateInput(fieldId: string, value: string) {
    setInputs((current) => ({ ...current, [fieldId]: value }));
  }

  return (
    <main className="dashboard-shell ai-advisor-shell">
      <AppHeader
        title="FinanceOS Studio"
        actions={
          <>
          <span className={keyStatus?.has_key ? "status-pill" : "risk-pill"}>{keyStatus?.has_key ? "OpenAI key saved" : "Key required"}</span>
          <Link className="ghost-button" href="/portfolio">Portfolio</Link>
          <Link className="ghost-button" href="/investing">Calculators</Link>
          <Link className="ghost-button" href="/retirement-analyzer">Plan</Link>
          <Link className="secondary-button" href="/dashboard">Portfolio dashboard</Link>
          </>
        }
      />

      <div className="dashboard-disclaimer">
        <LegalDisclaimer compact />
      </div>

      <div className="ai-tabbar" role="tablist" aria-label="FinanceOS Studio tabs">
        <button
          className={activeTab === "retirement-plan" ? "active" : ""}
          type="button"
          role="tab"
          aria-selected={activeTab === "retirement-plan"}
          onClick={() => setActiveTab("retirement-plan")}
        >
          <Bot size={16} /> AI Planner
        </button>
        <button
          className={activeTab === "personal-cfo" ? "active" : ""}
          type="button"
          role="tab"
          aria-selected={activeTab === "personal-cfo"}
          onClick={() => setActiveTab("personal-cfo")}
        >
          <FolderArchive size={16} /> Personal CFO
        </button>
        <button
          className={activeTab === "wheel-strategy" ? "active" : ""}
          type="button"
          role="tab"
          aria-selected={activeTab === "wheel-strategy"}
          onClick={() => setActiveTab("wheel-strategy")}
        >
          <TrendingUp size={16} /> Wheel Strategy
        </button>
        <button
          className={activeTab === "portfolio-sync" ? "active" : ""}
          type="button"
          role="tab"
          aria-selected={activeTab === "portfolio-sync"}
          onClick={() => setActiveTab("portfolio-sync")}
        >
          <WalletCards size={16} /> Portfolio Sync
        </button>
        <button
          className={activeTab === "rsi-playbook" ? "active" : ""}
          type="button"
          role="tab"
          aria-selected={activeTab === "rsi-playbook"}
          onClick={() => setActiveTab("rsi-playbook")}
        >
          <Gauge size={16} /> RSI Playbook
        </button>
      </div>

      <div className="ai-advisor-layout">
        <aside className="ai-advisor-sidebar">
          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>OpenAI key</h2>
              <KeyRound size={18} />
            </div>
            <form className="form-stack" onSubmit={saveKey}>
              <div className="field">
                <label htmlFor="openai-key">API key</label>
                <input
                  id="openai-key"
                  type="password"
                  autoComplete="off"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder="sk-..."
                />
              </div>
              <button className="primary-button" type="submit" disabled={loading === "key"}>
                {loading === "key" ? <Loader2 size={16} className="spin-icon" /> : <LockKeyhole size={16} />}
                {keyStatus?.has_key ? "Update key" : "Save key"}
              </button>
              {keyStatus?.has_key && (
                <button className="ghost-button danger-button" type="button" onClick={deleteKey} disabled={loading === "delete-key"}>
                  <Trash2 size={16} /> Remove key
                </button>
              )}
            </form>
            <p className="fine-print">{keyMessage || "Keys are encrypted in the database and never shown again after save."}</p>
            {keyStatus?.validated_at && <p className="fine-print">Saved {formatDateTime(keyStatus.validated_at)}</p>}
          </section>

          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Reports</h2>
              <FileText size={18} />
            </div>
            <div className="ai-report-list">
              {reports.length ? reports.slice(0, 12).map((report) => (
                <button type="button" key={report.id} onClick={() => openReport(report.id)} className={activeReport?.id === report.id ? "active" : ""}>
                  <strong>{report.module_title}</strong>
                  <span>{report.model} · {formatDateTime(report.created_at)}</span>
                </button>
              )) : <p className="fine-print">No AI retirement reports generated yet.</p>}
            </div>
          </section>
        </aside>

        <section className="ai-advisor-workspace">
          {activeTab === "retirement-plan" ? (
            <>
              <section className="dashboard-panel ai-advisor-head">
                <div>
                  <p className="eyebrow">AI Planner</p>
                  <h2>Generate a saved AI retirement report from complete client inputs.</h2>
                  <p>Choose one planning module, complete every required field, select a model, and generate a database-saved report using your saved OpenAI key.</p>
                </div>
                <span className="status-pill"><ShieldCheck size={14} /> Saved history</span>
              </section>

              <section className="dashboard-panel">
                <div className="panel-header">
                  <h2>Planning module</h2>
                  <MessageSquareText size={18} />
                </div>
                <div className="ai-module-grid">
                  {modules.map((module) => (
                    <button
                      type="button"
                      key={module.id}
                      className={module.id === activeModule.id ? "active" : ""}
                      onClick={() => setActiveModuleId(module.id)}
                    >
                      <strong>{module.title}</strong>
                      <span>{module.summary}</span>
                    </button>
                  ))}
                </div>
              </section>

              <form className="dashboard-panel ai-retirement-form" onSubmit={generateReport}>
                <div className="panel-header">
                  <div>
                    <h2>{activeModule.title}</h2>
                    <p className="fine-print">{missingFields.length ? `${missingFields.length} required input${missingFields.length === 1 ? "" : "s"} remaining` : "All required inputs complete"}</p>
                  </div>
                  <div className="ai-model-control" role="radiogroup" aria-label="OpenAI model">
                    {models.map((item) => (
                      <button type="button" key={item.id} className={model === item.id ? "active" : ""} onClick={() => setModel(item.id)}>
                        <strong>{item.label}</strong>
                        <span>{item.helper}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="ai-field-grid">
                  {activeModule.fields.map((field) => (
                    <div className={`field ${field.kind === "long" ? "wide-field" : ""}`} key={`${activeModule.id}-${field.id}`}>
                      <label htmlFor={`${activeModule.id}-${field.id}`}>{field.label}</label>
                      {field.kind === "long" ? (
                        <textarea
                          id={`${activeModule.id}-${field.id}`}
                          value={inputs[field.id] ?? ""}
                          onChange={(event) => updateInput(field.id, event.target.value)}
                        />
                      ) : field.kind === "select" ? (
                        <select id={`${activeModule.id}-${field.id}`} value={inputs[field.id] ?? ""} onChange={(event) => updateInput(field.id, event.target.value)}>
                          <option value="">Select</option>
                          {field.options?.map((option) => <option value={option} key={option}>{option}</option>)}
                        </select>
                      ) : (
                        <input
                          id={`${activeModule.id}-${field.id}`}
                          value={inputs[field.id] ?? ""}
                          onChange={(event) => updateInput(field.id, event.target.value)}
                        />
                      )}
                    </div>
                  ))}
                </div>

                {error && <div className="error">{error}</div>}
                {!keyStatus?.has_key && <div className="error">Save an OpenAI API key before generating a report.</div>}
                <button className="primary-button ai-generate-button" type="submit" disabled={!canGenerate}>
                  {loading === "report" ? <Loader2 size={16} className="spin-icon" /> : <Play size={16} />}
                  {loading === "report" ? "Generating report" : "Generate retirement report"}
                </button>
              </form>

              {activeReport ? (
                <section className="dashboard-panel ai-report-output">
                  <div className="panel-header">
                    <div>
                      <h2>{activeReport.module_title}</h2>
                      <p className="fine-print">{activeReport.model} · {formatDateTime(activeReport.created_at)}</p>
                    </div>
                    <span className="status-pill"><CheckCircle2 size={14} /> Saved</span>
                  </div>
                  <ReportText value={activeReport.response_text} />
                </section>
              ) : (
                <section className="dashboard-panel empty-proposal ai-empty-report">
                  <Bot size={34} />
                  <h2>No AI retirement report selected</h2>
                  <p>Generated reports appear here and remain available in the report history.</p>
                </section>
              )}
            </>
          ) : activeTab === "personal-cfo" ? (
            <PersonalCFOTool keyStatus={keyStatus} />
          ) : activeTab === "wheel-strategy" ? (
            <OptionStrategyTool />
          ) : activeTab === "portfolio-sync" ? (
            <PortfolioSyncTool />
          ) : (
            <RSIPlaybookTool />
          )}
        </section>
      </div>
    </main>
  );
}

function ReportText({ value }: { value: string }) {
  const lines = value.split("\n").map((line) => line.trim()).filter(Boolean);
  return (
    <div className="ai-report-markdown">
      {lines.map((line, index) => {
        if (line.startsWith("### ")) return <h4 key={`${line}-${index}`}>{line.replace(/^###\s+/, "")}</h4>;
        if (line.startsWith("## ")) return <h3 key={`${line}-${index}`}>{line.replace(/^##\s+/, "")}</h3>;
        if (line.startsWith("# ")) return <h2 key={`${line}-${index}`}>{line.replace(/^#\s+/, "")}</h2>;
        if (/^[-*]\s+/.test(line)) return <p className="ai-report-bullet" key={`${line}-${index}`}>{line.replace(/^[-*]\s+/, "")}</p>;
        if (/^\d+\.\s+/.test(line)) return <p className="ai-report-bullet" key={`${line}-${index}`}>{line}</p>;
        return <p key={`${line}-${index}`}>{line}</p>;
      })}
    </div>
  );
}

function formatDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}
