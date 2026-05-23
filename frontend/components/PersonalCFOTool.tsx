"use client";

import {
  BarChart3,
  Bot,
  CheckCircle2,
  CircleDollarSign,
  Download,
  FileText,
  FolderArchive,
  KeyRound,
  Loader2,
  MessageSquareText,
  Save,
  Send,
  ShieldCheck,
  Upload
} from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import { Area, CartesianGrid, ComposedChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  AIAdvisorOpenAIKeyStatus,
  PersonalCFODashboard,
  PersonalCFOFile,
  PersonalCFOModel,
  PersonalCFOProject,
  apiFetch,
  apiUrl
} from "@/lib/api";

const personalCfoModels: Array<{ id: PersonalCFOModel; label: string; helper: string }> = [
  { id: "gpt-5.5", label: "Quality", helper: "gpt-5.5" },
  { id: "gpt-5.4", label: "Balanced", helper: "gpt-5.4" },
  { id: "gpt-5.4-mini", label: "Cost", helper: "gpt-5.4-mini" }
];

const personalCfoPhases = [
  "Situation & Constraints",
  "Capital & Horizon",
  "Philosophy & Mindset",
  "Behavioural Nuance",
  "Preferences & Anti-Preferences",
  "Goals",
  "Stress Tests"
];

export function PersonalCFOTool({
  keyStatus,
  onAuthExpired
}: {
  keyStatus: AIAdvisorOpenAIKeyStatus | null;
  onAuthExpired?: () => void;
}) {
  const bootstrappedRef = useRef(false);
  const [projects, setProjects] = useState<PersonalCFOProject[]>([]);
  const [project, setProject] = useState<PersonalCFOProject | null>(null);
  const [dashboard, setDashboard] = useState<PersonalCFODashboard | null>(null);
  const [model, setModel] = useState<PersonalCFOModel>("gpt-5.4");
  const [messageInput, setMessageInput] = useState("");
  const [refineInput, setRefineInput] = useState("");
  const [activeFileId, setActiveFileId] = useState<number | null>(null);
  const [fileDraft, setFileDraft] = useState("");
  const [uploadName, setUploadName] = useState("");
  const [uploadContent, setUploadContent] = useState("");
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");

  const activeFile = project?.files.find((file) => file.id === activeFileId) ?? project?.files[0] ?? null;
  const currentPhaseIndex = project ? Math.min(Math.max(project.current_phase, 1), personalCfoPhases.length) - 1 : 0;
  const totalPnlRaw = dashboard?.pnl_summary["total_pnl"];
  const totalPnl = typeof totalPnlRaw === "number" ? totalPnlRaw : 0;
  const canGenerate = Boolean(project?.can_generate_one_pager && keyStatus?.has_key && loading !== "generate");

  useEffect(() => {
    if (bootstrappedRef.current) return;
    bootstrappedRef.current = true;
    void bootstrap();
  }, []);

  useEffect(() => {
    if (!activeFile) {
      setFileDraft("");
      return;
    }
    setFileDraft(activeFile.content);
  }, [activeFile?.id, activeFile?.content]);

  async function bootstrap() {
    setLoading("bootstrap");
    setError("");
    try {
      await apiFetch("/auth/me");
      const rows = await apiFetch<PersonalCFOProject[]>("/ai-advisor/personal-cfo/projects");
      setProjects(rows);
      const initial = rows[0] ?? await apiFetch<PersonalCFOProject>("/ai-advisor/personal-cfo/projects", {
        method: "POST",
        body: JSON.stringify({ name: "Investment Folder" })
      });
      await loadProject(initial.id, false);
    } catch {
      onAuthExpired?.();
    } finally {
      setLoading("");
    }
  }

  async function loadProject(projectId: number, clearError = true) {
    if (clearError) setError("");
    const [detail, summary] = await Promise.all([
      apiFetch<PersonalCFOProject>(`/ai-advisor/personal-cfo/projects/${projectId}`),
      apiFetch<PersonalCFODashboard>(`/ai-advisor/personal-cfo/projects/${projectId}/dashboard`)
    ]);
    setProject(detail);
    setDashboard(summary);
    setProjects((current) => [detail, ...current.filter((item) => item.id !== detail.id)]);
    setActiveFileId((current) => detail.files.some((file) => file.id === current) ? current : detail.files[0]?.id ?? null);
  }

  async function createProject() {
    setLoading("create");
    setError("");
    try {
      const created = await apiFetch<PersonalCFOProject>("/ai-advisor/personal-cfo/projects", {
        method: "POST",
        body: JSON.stringify({ name: `Investment Folder ${projects.length + 1}` })
      });
      setProjects((current) => [created, ...current]);
      await loadProject(created.id);
      setMessageInput("");
      setRefineInput("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create Personal CFO project.");
    } finally {
      setLoading("");
    }
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!project || !messageInput.trim() || !keyStatus?.has_key) return;
    setLoading("message");
    setError("");
    try {
      const updated = await apiFetch<PersonalCFOProject>(`/ai-advisor/personal-cfo/projects/${project.id}/messages`, {
        method: "POST",
        body: JSON.stringify({ content: messageInput.trim(), model })
      });
      setProject(updated);
      setMessageInput("");
      await loadDashboard(updated.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit interview answer.");
    } finally {
      setLoading("");
    }
  }

  async function generateOnePager() {
    if (!project || !canGenerate) return;
    setLoading("generate");
    setError("");
    try {
      const updated = await apiFetch<PersonalCFOProject>(`/ai-advisor/personal-cfo/projects/${project.id}/one-pager`, {
        method: "POST",
        body: JSON.stringify({ model })
      });
      setProject(updated);
      setActiveFileId(updated.files.find((file) => file.path === "investor-one-pager.md")?.id ?? updated.files[0]?.id ?? null);
      await loadDashboard(updated.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate investor one-pager.");
    } finally {
      setLoading("");
    }
  }

  async function refineOnePager(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!project || !refineInput.trim() || !project.one_pager_generated || project.refinement_used || !keyStatus?.has_key) return;
    setLoading("refine");
    setError("");
    try {
      const updated = await apiFetch<PersonalCFOProject>(`/ai-advisor/personal-cfo/projects/${project.id}/one-pager/refine`, {
        method: "POST",
        body: JSON.stringify({ feedback: refineInput.trim(), model })
      });
      setProject(updated);
      setRefineInput("");
      setActiveFileId(updated.files.find((file) => file.path === "investor-one-pager.md")?.id ?? updated.files[0]?.id ?? null);
      await loadDashboard(updated.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not refine investor one-pager.");
    } finally {
      setLoading("");
    }
  }

  async function saveActiveFile() {
    if (!project || !activeFile) return;
    setLoading("file");
    setError("");
    try {
      const saved = await apiFetch<PersonalCFOFile>(`/ai-advisor/personal-cfo/projects/${project.id}/files/${activeFile.id}`, {
        method: "PUT",
        body: JSON.stringify({ content: fileDraft })
      });
      setProject({ ...project, files: project.files.map((file) => file.id === saved.id ? saved : file) });
      await loadDashboard(project.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save project file.");
    } finally {
      setLoading("");
    }
  }

  async function uploadFinancialFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!project || !uploadName.trim() || !uploadContent.trim()) return;
    setLoading("upload");
    setError("");
    try {
      await apiFetch(`/ai-advisor/personal-cfo/projects/${project.id}/uploads`, {
        method: "POST",
        body: JSON.stringify({ file_name: uploadName.trim(), content: uploadContent })
      });
      setUploadName("");
      setUploadContent("");
      await loadProject(project.id, false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not upload financial file.");
    } finally {
      setLoading("");
    }
  }

  async function handleFileSelect(file: File | null) {
    if (!file) return;
    setUploadName(file.name);
    setUploadContent(await file.text());
  }

  async function loadDashboard(projectId: number) {
    setDashboard(await apiFetch<PersonalCFODashboard>(`/ai-advisor/personal-cfo/projects/${projectId}/dashboard`));
  }

  async function downloadZip() {
    if (!project) return;
    setLoading("export");
    setError("");
    try {
      const response = await fetch(`${apiUrl()}/ai-advisor/personal-cfo/projects/${project.id}/export`, {
        credentials: "include"
      });
      if (!response.ok) throw new Error(`Export failed with ${response.status}`);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "Investment Folder.zip";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
      await loadDashboard(project.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not export Investment Folder ZIP.");
    } finally {
      setLoading("");
    }
  }

  return (
    <>
      <section className="dashboard-panel ai-advisor-head personal-cfo-head">
        <div>
          <p className="eyebrow">Personal CFO</p>
          <h2>Build an investor one-pager and portable Investment Folder.</h2>
          <p>
            Run the strategy architect interview one answer at a time, keep the generated markdown files in sync,
            upload CSV or markdown financial context, and export the project as a ZIP.
          </p>
          <div className="investing-data-line">
            <span>{project ? `Project ${project.id}` : "Loading project"}</span>
            <span>{project?.one_pager_generated ? "One-pager generated" : project?.status.replaceAll("_", " ") ?? "Interview"}</span>
            <span>{keyStatus?.has_key ? `Key ${keyStatus.key_fingerprint ?? "saved"}` : "OpenAI key required"}</span>
          </div>
        </div>
        <button className="secondary-button" type="button" onClick={downloadZip} disabled={!project || loading === "export"}>
          {loading === "export" ? <Loader2 size={16} className="spin-icon" /> : <Download size={16} />} Export ZIP
        </button>
      </section>

      {error && <section className="dashboard-panel investing-warning"><ShieldCheck size={18} /><p>{error}</p></section>}
      {!keyStatus?.has_key && (
        <section className="dashboard-panel investing-warning">
          <KeyRound size={18} />
          <p>Personal CFO uses the encrypted OpenAI API key saved in AI Advisor. Save a validated key before sending interview answers or generating the one-pager.</p>
        </section>
      )}

      <div className="personal-cfo-grid">
        <section className="dashboard-panel personal-cfo-projects">
          <div className="panel-header">
            <h2>Projects</h2>
            <FolderArchive size={18} />
          </div>
          <button className="secondary-button" type="button" onClick={createProject} disabled={loading === "create"}>
            {loading === "create" ? <Loader2 size={16} className="spin-icon" /> : <FolderArchive size={16} />} New project
          </button>
          <div className="personal-cfo-project-list">
            {projects.map((item) => (
              <button key={item.id} type="button" className={project?.id === item.id ? "active" : ""} onClick={() => loadProject(item.id)}>
                <strong>{item.name}</strong>
                <span>{item.status.replaceAll("_", " ")} · {formatDateTime(item.updated_at)}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="dashboard-panel personal-cfo-interview">
          <div className="panel-header">
            <div>
              <h2>Interview</h2>
              <p className="fine-print">
                {project?.phase_complete ? "All seven phases complete" : `Phase ${project?.current_phase ?? 1}: ${personalCfoPhases[currentPhaseIndex]}`}
              </p>
            </div>
            <div className="ai-model-control personal-cfo-models" role="radiogroup" aria-label="Personal CFO OpenAI model">
              {personalCfoModels.map((item) => (
                <button type="button" key={item.id} className={model === item.id ? "active" : ""} onClick={() => setModel(item.id)}>
                  <strong>{item.label}</strong>
                  <span>{item.helper}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="personal-cfo-phase-strip">
            {personalCfoPhases.map((phase, index) => (
              <span key={phase} className={project && project.current_phase > index + 1 ? "complete" : project?.current_phase === index + 1 ? "active" : ""}>
                {index + 1}
              </span>
            ))}
          </div>

          <div className="personal-cfo-chat" aria-live="polite">
            {project?.messages.map((message) => (
              <div className={`personal-cfo-message ${message.role === "user" ? "user" : "assistant"}`} key={message.id}>
                <span>{message.role === "user" ? "You" : "Architect"}</span>
                <p>{message.content}</p>
              </div>
            )) ?? <p className="fine-print">Loading interview.</p>}
          </div>

          <form className="personal-cfo-chat-form" onSubmit={sendMessage}>
            <textarea
              value={messageInput}
              onChange={(event) => setMessageInput(event.target.value)}
              placeholder={keyStatus?.has_key ? "Answer the current question directly." : "Draft your answer here, then save an OpenAI key before sending."}
              disabled={!project || project.one_pager_generated}
            />
            <button className="primary-button" type="submit" disabled={!messageInput.trim() || !keyStatus?.has_key || loading === "message" || !project || project.one_pager_generated}>
              {loading === "message" ? <Loader2 size={16} className="spin-icon" /> : <Send size={16} />} Send
            </button>
          </form>
        </section>
      </div>

      <section className="dashboard-panel personal-cfo-actions">
        <div>
          <p className="eyebrow">Investor one-pager</p>
          <h2>{project?.one_pager_generated ? "Generated markdown is saved in project files." : "Generate only after all seven phases are complete."}</h2>
          <p className="fine-print">
            {project?.can_generate_one_pager ? "The backend has marked the interview complete." : "The generate action remains blocked until phase completion."}
          </p>
        </div>
        <button className="primary-button" type="button" onClick={generateOnePager} disabled={!canGenerate}>
          {loading === "generate" ? <Loader2 size={16} className="spin-icon" /> : <Bot size={16} />}
          {loading === "generate" ? "Generating" : "Generate one-pager"}
        </button>
      </section>

      {project?.one_pager_generated && (
        <form className="dashboard-panel personal-cfo-refine" onSubmit={refineOnePager}>
          <div className="panel-header">
            <div>
              <h2>One refinement round</h2>
              <p className="fine-print">{project.refinement_used ? "Refinement already used" : "Anything in here that doesn't sound like you?"}</p>
            </div>
            <CheckCircle2 size={18} />
          </div>
          <textarea
            value={refineInput}
            onChange={(event) => setRefineInput(event.target.value)}
            disabled={project.refinement_used || loading === "refine"}
            placeholder="Give one concise refinement pass."
          />
          <button className="secondary-button" type="submit" disabled={!refineInput.trim() || project.refinement_used || loading === "refine"}>
            {loading === "refine" ? <Loader2 size={16} className="spin-icon" /> : <MessageSquareText size={16} />} Incorporate refinement
          </button>
        </form>
      )}

      <div className="personal-cfo-grid personal-cfo-files-grid">
        <section className="dashboard-panel personal-cfo-files">
          <div className="panel-header">
            <h2>Project files</h2>
            <FileText size={18} />
          </div>
          <div className="personal-cfo-file-tabs">
            {project?.files.map((file) => (
              <button key={file.id} type="button" className={activeFile?.id === file.id ? "active" : ""} onClick={() => setActiveFileId(file.id)}>
                {file.path}
              </button>
            ))}
          </div>
          {activeFile ? (
            <>
              <textarea className="personal-cfo-file-editor" value={fileDraft} onChange={(event) => setFileDraft(event.target.value)} />
              <button className="secondary-button" type="button" onClick={saveActiveFile} disabled={loading === "file"}>
                {loading === "file" ? <Loader2 size={16} className="spin-icon" /> : <Save size={16} />} Save file
              </button>
            </>
          ) : <p className="fine-print">No project file selected.</p>}
        </section>

        <section className="dashboard-panel personal-cfo-preview">
          <div className="panel-header">
            <h2>Markdown preview</h2>
            <FileText size={18} />
          </div>
          {activeFile ? <MarkdownText value={fileDraft} /> : <p className="fine-print">Select a file to preview.</p>}
        </section>
      </div>

      <div className="personal-cfo-grid">
        <form className="dashboard-panel personal-cfo-upload" onSubmit={uploadFinancialFile}>
          <div className="panel-header">
            <h2>Financial uploads</h2>
            <Upload size={18} />
          </div>
          <div className="field">
            <label htmlFor="personal-cfo-file">Markdown or CSV file</label>
            <input id="personal-cfo-file" type="file" accept=".md,.markdown,.csv,text/markdown,text/csv,text/plain" onChange={(event) => void handleFileSelect(event.target.files?.[0] ?? null)} />
          </div>
          <div className="field">
            <label htmlFor="personal-cfo-upload-name">Stored file name</label>
            <input id="personal-cfo-upload-name" value={uploadName} onChange={(event) => setUploadName(event.target.value)} placeholder="positions-may-2026.csv" />
          </div>
          <div className="field">
            <label htmlFor="personal-cfo-upload-content">Content</label>
            <textarea id="personal-cfo-upload-content" value={uploadContent} onChange={(event) => setUploadContent(event.target.value)} />
          </div>
          <button className="secondary-button" type="submit" disabled={!project || !uploadName.trim() || !uploadContent.trim() || loading === "upload"}>
            {loading === "upload" ? <Loader2 size={16} className="spin-icon" /> : <Upload size={16} />} Upload to Financials
          </button>
          <div className="personal-cfo-upload-list">
            {project?.uploads.length ? project.uploads.map((upload) => (
              <span key={upload.id}>{upload.file_name} · {upload.row_count} rows</span>
            )) : <p className="fine-print">No markdown or CSV uploads yet.</p>}
          </div>
        </form>

        <section className="dashboard-panel personal-cfo-dashboard">
          <div className="panel-header">
            <h2>Folder-derived dashboard</h2>
            <BarChart3 size={18} />
          </div>
          <div className="stat-grid personal-cfo-stat-grid">
            <article className="stat-panel"><FileText size={20} /><h3>Files</h3><strong>{dashboard?.files_count ?? 0}</strong><p>Markdown files in the project.</p></article>
            <article className="stat-panel"><Upload size={20} /><h3>Uploads</h3><strong>{dashboard?.uploads_count ?? 0}</strong><p>Financials folder items.</p></article>
            <article className="stat-panel"><MessageSquareText size={20} /><h3>Messages</h3><strong>{dashboard?.message_count ?? 0}</strong><p>Interview transcript entries.</p></article>
            <article className="stat-panel"><CircleDollarSign size={20} /><h3>P&L</h3><strong>{currency(totalPnl)}</strong><p>Parsed from CSV rows when present.</p></article>
          </div>

          <div className="personal-cfo-dashboard-grid">
            <div className="personal-cfo-chart-box">
              <h3>Cash trend</h3>
              {dashboard?.cash_trend.length ? (
                <ResponsiveContainer width="100%" height={220}>
                  <ComposedChart data={dashboard.cash_trend} margin={{ left: 4, right: 12, top: 12, bottom: 4 }}>
                    <CartesianGrid stroke="#d9e6df" strokeDasharray="3 3" />
                    <XAxis dataKey="date" minTickGap={28} tick={{ fontSize: 11, fill: "#51645b" }} />
                    <YAxis width={72} tickFormatter={(value) => compactCurrency(Number(value))} tick={{ fontSize: 11, fill: "#51645b" }} />
                    <Tooltip formatter={(value) => [currency(Number(value)), "Cash"]} contentStyle={{ border: "1px solid #d7e2dc", borderRadius: 8 }} />
                    <Area type="monotone" dataKey="value" stroke="#0f766e" fill="#d6f4ea" strokeWidth={2.5} />
                  </ComposedChart>
                </ResponsiveContainer>
              ) : <div className="personal-cfo-empty-visual">Upload CSV rows with date and cash columns.</div>}
            </div>

            <div className="personal-cfo-chart-box">
              <h3>Exposure</h3>
              {dashboard?.exposures.length ? dashboard.exposures.slice(0, 8).map((item) => (
                <div className="personal-cfo-exposure-row" key={item.label}>
                  <span>{item.label}</span>
                  <div><i style={{ width: `${Math.max(item.weight * 100, 4)}%` }} /></div>
                  <strong>{currency(item.value)}</strong>
                </div>
              )) : <div className="personal-cfo-empty-visual">Upload CSV rows with symbol and market_value columns.</div>}
            </div>
          </div>

          <div className="personal-cfo-dashboard-grid">
            <div className="personal-cfo-timeline">
              <h3>Memory timeline</h3>
              {dashboard?.memory_timeline.length ? dashboard.memory_timeline.map((item) => <p key={item}>{item}</p>) : <p className="fine-print">Memory entries appear as project events occur.</p>}
            </div>
            <div className="personal-cfo-timeline">
              <h3>Rules and flags</h3>
              {dashboard?.open_flags.length ? dashboard.open_flags.map((item) => <p key={item}>{item}</p>) : <p className="fine-print">Generated one-pager rules and contradictions appear here.</p>}
            </div>
          </div>
        </section>
      </div>
    </>
  );
}

function MarkdownText({ value }: { value: string }) {
  const lines = value.split("\n").map((line) => line.trim()).filter(Boolean);
  if (!lines.length) return <p className="fine-print">This file is empty.</p>;
  return (
    <div className="ai-report-markdown personal-cfo-markdown">
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

function currency(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

function compactCurrency(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function formatDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}
