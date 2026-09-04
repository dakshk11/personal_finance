"use client";

import { ChevronLeft, ChevronRight, FileText, KeyRound, Loader2, LockKeyhole, MessageSquareText, Trash2 } from "lucide-react";
import { formatDateTime, useStudio } from "./StudioContext";

export function StudioSidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const studio = useStudio();

  return (
    <aside className="ai-advisor-sidebar">
      <button
        type="button"
        className="sidebar-toggle-btn"
        onClick={onToggle}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
      </button>

      <section className="dashboard-panel">
        <div className="panel-header">
          <h2>OpenAI key</h2>
          <KeyRound size={18} />
        </div>
        <form className="form-stack" onSubmit={studio.saveKey}>
          <div className="field">
            <label htmlFor="openai-key">API key</label>
            <input
              id="openai-key"
              type="password"
              autoComplete="off"
              value={studio.apiKey}
              onChange={(event) => studio.setApiKey(event.target.value)}
              placeholder="sk-..."
            />
          </div>
          <button className="primary-button" type="submit" disabled={studio.loading === "key"}>
            {studio.loading === "key" ? <Loader2 size={16} className="spin-icon" /> : <LockKeyhole size={16} />}
            {studio.keyStatus?.has_key ? "Update key" : "Save key"}
          </button>
          {studio.keyStatus?.has_key && (
            <button className="ghost-button danger-button" type="button" onClick={studio.deleteKey} disabled={studio.loading === "delete-key"}>
              <Trash2 size={16} /> Remove key
            </button>
          )}
        </form>
        <p className="fine-print">{studio.keyMessage || "Keys are encrypted in the database and never shown again after save."}</p>
        {studio.keyStatus?.validated_at && <p className="fine-print">Saved {formatDateTime(studio.keyStatus.validated_at)}</p>}
      </section>

      <section className="dashboard-panel">
        <div className="panel-header">
          <h2>TipRanks key</h2>
          <KeyRound size={18} />
        </div>
        <form className="form-stack" onSubmit={studio.saveTipRanksKey}>
          <div className="field">
            <label htmlFor="tipranks-key">API key</label>
            <input
              id="tipranks-key"
              type="password"
              autoComplete="off"
              value={studio.tipRanksApiKey}
              onChange={(event) => studio.setTipRanksApiKey(event.target.value)}
              placeholder="TipRanks API key"
            />
          </div>
          <button className="primary-button" type="submit" disabled={studio.loading === "tipranks-key"}>
            {studio.loading === "tipranks-key" ? <Loader2 size={16} className="spin-icon" /> : <LockKeyhole size={16} />}
            {studio.tipRanksKeyStatus?.has_key ? "Update key" : "Save key"}
          </button>
          {studio.tipRanksKeyStatus?.has_key && (
            <button className="ghost-button danger-button" type="button" onClick={studio.deleteTipRanksKey} disabled={studio.loading === "delete-tipranks-key"}>
              <Trash2 size={16} /> Remove key
            </button>
          )}
        </form>
        <p className="fine-print">{studio.tipRanksKeyMessage || "Keys are encrypted in the database and never shown again after save."}</p>
        {studio.tipRanksKeyStatus?.validated_at && <p className="fine-print">Saved {formatDateTime(studio.tipRanksKeyStatus.validated_at)}</p>}
      </section>

      <section className="dashboard-panel">
        <div className="panel-header">
          <h2>LunarCrush key</h2>
          <KeyRound size={18} />
        </div>
        <form className="form-stack" onSubmit={studio.saveLunarCrushKey}>
          <div className="field">
            <label htmlFor="lunarcrush-key">API key</label>
            <input
              id="lunarcrush-key"
              type="password"
              autoComplete="off"
              value={studio.lunarCrushApiKey}
              onChange={(event) => studio.setLunarCrushApiKey(event.target.value)}
              placeholder="LunarCrush API key"
            />
          </div>
          <button className="primary-button" type="submit" disabled={studio.loading === "lunarcrush-key"}>
            {studio.loading === "lunarcrush-key" ? <Loader2 size={16} className="spin-icon" /> : <LockKeyhole size={16} />}
            {studio.lunarCrushKeyStatus?.has_key ? "Update key" : "Save key"}
          </button>
          {studio.lunarCrushKeyStatus?.has_key && (
            <button className="ghost-button danger-button" type="button" onClick={studio.deleteLunarCrushKey} disabled={studio.loading === "delete-lunarcrush-key"}>
              <Trash2 size={16} /> Remove key
            </button>
          )}
        </form>
        <p className="fine-print">{studio.lunarCrushKeyMessage || "Used for LunarCrush market and social intelligence. Keys are encrypted in the database and never shown again after save."}</p>
        {studio.lunarCrushKeyStatus?.validated_at && <p className="fine-print">Saved {formatDateTime(studio.lunarCrushKeyStatus.validated_at)}</p>}
      </section>

      <section className="dashboard-panel">
        <div className="panel-header">
          <h2>NVIDIA key</h2>
          <KeyRound size={18} />
        </div>
        <form className="form-stack" onSubmit={studio.saveNvidiaKey}>
          <div className="field">
            <label htmlFor="nvidia-key">API key</label>
            <input
              id="nvidia-key"
              type="password"
              autoComplete="off"
              value={studio.nvidiaApiKey}
              onChange={(event) => studio.setNvidiaApiKey(event.target.value)}
              placeholder="NVIDIA API key"
            />
          </div>
          <button className="primary-button" type="submit" disabled={studio.loading === "nvidia-key"}>
            {studio.loading === "nvidia-key" ? <Loader2 size={16} className="spin-icon" /> : <LockKeyhole size={16} />}
            {studio.nvidiaKeyStatus?.has_key ? "Update key" : "Save key"}
          </button>
          {studio.nvidiaKeyStatus?.has_key && (
            <button className="ghost-button danger-button" type="button" onClick={studio.deleteNvidiaKey} disabled={studio.loading === "delete-nvidia-key"}>
              <Trash2 size={16} /> Remove key
            </button>
          )}
        </form>
        <p className="fine-print">{studio.nvidiaKeyMessage || "Used for hosted open-source NVIDIA NIM models in Recommendation Agent and Wheel Scanner. Keys are encrypted in the database and never shown again after save."}</p>
        {studio.nvidiaKeyStatus?.validated_at && <p className="fine-print">Saved {formatDateTime(studio.nvidiaKeyStatus.validated_at)}</p>}
      </section>

      <section className="dashboard-panel">
        <div className="panel-header">
          <h2>Alpaca key</h2>
          <KeyRound size={18} />
        </div>
        <form className="form-stack" onSubmit={studio.saveAlpacaKey}>
          <div className="field">
            <label htmlFor="alpaca-key">API key</label>
            <input
              id="alpaca-key"
              type="password"
              autoComplete="off"
              value={studio.alpacaApiKey}
              onChange={(event) => studio.setAlpacaApiKey(event.target.value)}
              placeholder="Alpaca API key"
            />
          </div>
          <div className="field">
            <label htmlFor="alpaca-secret">API secret</label>
            <input
              id="alpaca-secret"
              type="password"
              autoComplete="off"
              value={studio.alpacaApiSecret}
              onChange={(event) => studio.setAlpacaApiSecret(event.target.value)}
              placeholder="Alpaca API secret"
            />
          </div>
          <button className="primary-button" type="submit" disabled={studio.loading === "alpaca-key"}>
            {studio.loading === "alpaca-key" ? <Loader2 size={16} className="spin-icon" /> : <LockKeyhole size={16} />}
            {studio.alpacaKeyStatus?.has_key ? "Update key" : "Save key"}
          </button>
          {studio.alpacaKeyStatus?.has_key && (
            <button className="ghost-button danger-button" type="button" onClick={studio.deleteAlpacaKey} disabled={studio.loading === "delete-alpaca-key"}>
              <Trash2 size={16} /> Remove key
            </button>
          )}
        </form>
        <p className="fine-print">{studio.alpacaKeyMessage || "Used for Recommendation Agent real-time quotes. Secrets are encrypted and never shown again after save."}</p>
        {studio.alpacaKeyStatus?.validated_at && <p className="fine-print">Saved {formatDateTime(studio.alpacaKeyStatus.validated_at)}</p>}
      </section>

      <section className="dashboard-panel">
        <div className="panel-header">
          <h2>Agent context</h2>
          <MessageSquareText size={18} />
        </div>
        <div className="field">
          <label htmlFor="recommendation-context">Optional LLM context</label>
          <textarea
            id="recommendation-context"
            value={studio.recommendationContext}
            onChange={(event) => studio.setRecommendationContext(event.target.value)}
            placeholder="Add preferences, watchlist focus, risk constraints, time horizon, sectors to avoid, or what the agent should optimize for."
            rows={5}
          />
        </div>
        <p className="fine-print">Sent only with Recommendation Agent runs to help the LLM decide between scanner ideas.</p>
      </section>

      <section className="dashboard-panel">
        <div className="panel-header">
          <h2>Reports</h2>
          <FileText size={18} />
        </div>
        <div className="ai-report-list">
          {studio.reports.length ? studio.reports.slice(0, 12).map((report) => (
            <button type="button" key={report.id} onClick={() => studio.openReport(report.id)} className={studio.activeReport?.id === report.id ? "active" : ""}>
              <strong>{report.module_title}</strong>
              <span>{report.model} · {formatDateTime(report.created_at)}</span>
            </button>
          )) : <p className="fine-print">No AI retirement reports generated yet.</p>}
        </div>
      </section>
    </aside>
  );
}
