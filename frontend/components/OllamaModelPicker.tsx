"use client";

import { Zap } from "lucide-react";

/**
 * Reusable Ollama + Goose configuration UI.
 *
 * Renders an "Ollama" button in the model-control row, plus an inline
 * config strip (model name, Ollama URL, and optional Goose tool-call toggle).
 *
 * Model string conventions sent to the backend:
 *   ollama:<model>   — direct Ollama call, no tool use
 *   goose:<model>    — Ollama routed through a Goose session (tool calls enabled)
 */
export function OllamaModelButton({
  active,
  onClick
}: {
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button type="button" className={active ? "active" : ""} onClick={onClick}>
      <strong>Ollama</strong>
      <span>Local model</span>
    </button>
  );
}

export function OllamaConfigStrip({
  modelName,
  baseUrl,
  useGoose,
  showGoose = true,
  onModelNameChange,
  onBaseUrlChange,
  onUseGooseChange
}: {
  modelName: string;
  baseUrl: string;
  useGoose: boolean;
  showGoose?: boolean;
  onModelNameChange: (v: string) => void;
  onBaseUrlChange: (v: string) => void;
  onUseGooseChange: (v: boolean) => void;
}) {
  return (
    <div className="ollama-config-row">
      <label className="ollama-config-field">
        <span>Model name</span>
        <input
          value={modelName}
          onChange={(e) => onModelNameChange(e.target.value)}
          placeholder="llama3"
          autoComplete="off"
        />
      </label>
      <label className="ollama-config-field">
        <span>Ollama URL</span>
        <input
          value={baseUrl}
          onChange={(e) => onBaseUrlChange(e.target.value)}
          placeholder="http://127.0.0.1:11434"
          autoComplete="off"
        />
      </label>
      {showGoose && (
        <label className="ollama-config-field ollama-goose-toggle">
          <span><Zap size={12} /> Enable tool calls</span>
          <div className="goose-toggle-row">
            <button
              type="button"
              className={`goose-toggle-btn${useGoose ? " active" : ""}`}
              onClick={() => onUseGooseChange(!useGoose)}
              title="Route through Goose for web search and real-time tool calls. Requires: goose configure"
            >
              {useGoose ? "Goose ON" : "Goose OFF"}
            </button>
            {useGoose && (
              <span className="goose-hint">
                Requires <code>goose configure</code> with Ollama provider
              </span>
            )}
          </div>
        </label>
      )}
    </div>
  );
}

/**
 * Build the model string sent to the backend.
 *   goose enabled  → "goose:<model>"
 *   goose disabled → "ollama:<model>"
 *   gpt-* picker   → raw model id
 */
export function effectiveModelId(
  modelPicker: string,
  ollamaModelName: string,
  useGoose: boolean = false
): string {
  if (modelPicker === "ollama") {
    const name = ollamaModelName.trim() || "llama3";
    return useGoose ? `goose:${name}` : `ollama:${name}`;
  }
  return modelPicker;
}
