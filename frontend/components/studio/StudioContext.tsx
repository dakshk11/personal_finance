"use client";

import { FormEvent, ReactNode, createContext, useContext, useEffect, useState } from "react";
import {
  AIAdvisorAlpacaKeyStatus,
  AIAdvisorLunarCrushKeyStatus,
  AIAdvisorNvidiaKeyStatus,
  AIAdvisorOpenAIKeyStatus,
  AIAdvisorReport,
  AIAdvisorReportSummary,
  AIAdvisorTipRanksKeyStatus,
  apiFetch
} from "@/lib/api";

export function formatDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "N/A";
  return parsed.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}

type StudioContextValue = {
  keyStatus: AIAdvisorOpenAIKeyStatus | null;
  tipRanksKeyStatus: AIAdvisorTipRanksKeyStatus | null;
  alpacaKeyStatus: AIAdvisorAlpacaKeyStatus | null;
  lunarCrushKeyStatus: AIAdvisorLunarCrushKeyStatus | null;
  nvidiaKeyStatus: AIAdvisorNvidiaKeyStatus | null;

  apiKey: string;
  setApiKey: (value: string) => void;
  tipRanksApiKey: string;
  setTipRanksApiKey: (value: string) => void;
  lunarCrushApiKey: string;
  setLunarCrushApiKey: (value: string) => void;
  nvidiaApiKey: string;
  setNvidiaApiKey: (value: string) => void;
  alpacaApiKey: string;
  setAlpacaApiKey: (value: string) => void;
  alpacaApiSecret: string;
  setAlpacaApiSecret: (value: string) => void;

  keyMessage: string;
  tipRanksKeyMessage: string;
  lunarCrushKeyMessage: string;
  nvidiaKeyMessage: string;
  alpacaKeyMessage: string;

  saveKey: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  deleteKey: () => Promise<void>;
  saveTipRanksKey: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  deleteTipRanksKey: () => Promise<void>;
  saveLunarCrushKey: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  deleteLunarCrushKey: () => Promise<void>;
  saveNvidiaKey: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  deleteNvidiaKey: () => Promise<void>;
  saveAlpacaKey: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  deleteAlpacaKey: () => Promise<void>;

  recommendationContext: string;
  setRecommendationContext: (value: string) => void;

  reports: AIAdvisorReportSummary[];
  setReports: (updater: (current: AIAdvisorReportSummary[]) => AIAdvisorReportSummary[]) => void;
  activeReport: AIAdvisorReport | null;
  setActiveReport: (value: AIAdvisorReport | null) => void;
  openReport: (reportId: number) => Promise<void>;

  loading: string;
  setLoading: (value: string) => void;
  error: string;
  setError: (value: string) => void;
};

const StudioContext = createContext<StudioContextValue | null>(null);

export function useStudio() {
  const value = useContext(StudioContext);
  if (!value) throw new Error("useStudio must be used inside StudioProvider");
  return value;
}

export function StudioProvider({ children }: { children: ReactNode }) {
  const [keyStatus, setKeyStatus] = useState<AIAdvisorOpenAIKeyStatus | null>(null);
  const [tipRanksKeyStatus, setTipRanksKeyStatus] = useState<AIAdvisorTipRanksKeyStatus | null>(null);
  const [alpacaKeyStatus, setAlpacaKeyStatus] = useState<AIAdvisorAlpacaKeyStatus | null>(null);
  const [lunarCrushKeyStatus, setLunarCrushKeyStatus] = useState<AIAdvisorLunarCrushKeyStatus | null>(null);
  const [nvidiaKeyStatus, setNvidiaKeyStatus] = useState<AIAdvisorNvidiaKeyStatus | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [tipRanksApiKey, setTipRanksApiKey] = useState("");
  const [lunarCrushApiKey, setLunarCrushApiKey] = useState("");
  const [nvidiaApiKey, setNvidiaApiKey] = useState("");
  const [alpacaApiKey, setAlpacaApiKey] = useState("");
  const [alpacaApiSecret, setAlpacaApiSecret] = useState("");
  const [recommendationContext, setRecommendationContext] = useState("");
  const [keyMessage, setKeyMessage] = useState("");
  const [tipRanksKeyMessage, setTipRanksKeyMessage] = useState("");
  const [lunarCrushKeyMessage, setLunarCrushKeyMessage] = useState("");
  const [nvidiaKeyMessage, setNvidiaKeyMessage] = useState("");
  const [alpacaKeyMessage, setAlpacaKeyMessage] = useState("");
  const [reports, setReportsState] = useState<AIAdvisorReportSummary[]>([]);
  const [activeReport, setActiveReport] = useState<AIAdvisorReport | null>(null);
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    void bootstrap();
  }, []);

  async function bootstrap() {
    try {
      const [key, tipRanksKey, lunarCrushKey, nvidiaKey, alpacaKey, history] = await Promise.all([
        apiFetch<AIAdvisorOpenAIKeyStatus>("/ai-advisor/openai-key"),
        apiFetch<AIAdvisorTipRanksKeyStatus>("/ai-advisor/tipranks-key"),
        apiFetch<AIAdvisorLunarCrushKeyStatus>("/ai-advisor/lunarcrush-key"),
        apiFetch<AIAdvisorNvidiaKeyStatus>("/ai-advisor/nvidia-key"),
        apiFetch<AIAdvisorAlpacaKeyStatus>("/ai-advisor/alpaca-key"),
        apiFetch<AIAdvisorReportSummary[]>("/ai-advisor/reports")
      ]);
      setKeyStatus(key);
      setTipRanksKeyStatus(tipRanksKey);
      setLunarCrushKeyStatus(lunarCrushKey);
      setNvidiaKeyStatus(nvidiaKey);
      setAlpacaKeyStatus(alpacaKey);
      setReportsState(history);
      setKeyMessage(key.has_key ? `Saved key ${key.key_fingerprint ?? ""}` : "No OpenAI key saved");
      setTipRanksKeyMessage(tipRanksKey.has_key ? `Saved key ${tipRanksKey.key_fingerprint ?? ""}` : "No TipRanks key saved");
      setLunarCrushKeyMessage(lunarCrushKey.has_key ? `Saved key ${lunarCrushKey.key_fingerprint ?? ""}` : "No LunarCrush key saved");
      setNvidiaKeyMessage(nvidiaKey.has_key ? `Saved key ${nvidiaKey.key_fingerprint ?? ""}` : "No NVIDIA key saved");
      setAlpacaKeyMessage(alpacaKey.has_key ? `Saved key ${alpacaKey.key_fingerprint ?? ""}` : "No Alpaca key saved");
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

  async function saveTipRanksKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setTipRanksKeyMessage("");
    if (!tipRanksApiKey.trim()) {
      setTipRanksKeyMessage("Enter a TipRanks API key before saving.");
      return;
    }
    setLoading("tipranks-key");
    try {
      const saved = await apiFetch<AIAdvisorTipRanksKeyStatus>("/ai-advisor/tipranks-key", {
        method: "PUT",
        body: JSON.stringify({ api_key: tipRanksApiKey.trim() })
      });
      setTipRanksApiKey("");
      setTipRanksKeyStatus(saved);
      setTipRanksKeyMessage(`Saved ${saved.key_fingerprint ?? "TipRanks key"}`);
    } catch (err) {
      setTipRanksKeyMessage(err instanceof Error ? err.message : "Could not save TipRanks key.");
    } finally {
      setLoading("");
    }
  }

  async function deleteTipRanksKey() {
    setLoading("delete-tipranks-key");
    setError("");
    try {
      const deleted = await apiFetch<AIAdvisorTipRanksKeyStatus>("/ai-advisor/tipranks-key", { method: "DELETE" });
      setTipRanksKeyStatus(deleted);
      setTipRanksKeyMessage("TipRanks key removed.");
    } catch (err) {
      setTipRanksKeyMessage(err instanceof Error ? err.message : "Could not remove TipRanks key.");
    } finally {
      setLoading("");
    }
  }

  async function saveLunarCrushKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLunarCrushKeyMessage("");
    if (!lunarCrushApiKey.trim()) {
      setLunarCrushKeyMessage("Enter a LunarCrush API key before saving.");
      return;
    }
    setLoading("lunarcrush-key");
    try {
      const saved = await apiFetch<AIAdvisorLunarCrushKeyStatus>("/ai-advisor/lunarcrush-key", {
        method: "PUT",
        body: JSON.stringify({ api_key: lunarCrushApiKey.trim() })
      });
      setLunarCrushApiKey("");
      setLunarCrushKeyStatus(saved);
      setLunarCrushKeyMessage(`Saved ${saved.key_fingerprint ?? "LunarCrush key"}`);
    } catch (err) {
      setLunarCrushKeyMessage(err instanceof Error ? err.message : "Could not save LunarCrush key.");
    } finally {
      setLoading("");
    }
  }

  async function deleteLunarCrushKey() {
    setLoading("delete-lunarcrush-key");
    setError("");
    try {
      const deleted = await apiFetch<AIAdvisorLunarCrushKeyStatus>("/ai-advisor/lunarcrush-key", { method: "DELETE" });
      setLunarCrushKeyStatus(deleted);
      setLunarCrushKeyMessage("LunarCrush key removed.");
    } catch (err) {
      setLunarCrushKeyMessage(err instanceof Error ? err.message : "Could not remove LunarCrush key.");
    } finally {
      setLoading("");
    }
  }

  async function saveNvidiaKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNvidiaKeyMessage("");
    if (!nvidiaApiKey.trim()) {
      setNvidiaKeyMessage("Enter an NVIDIA API key before saving.");
      return;
    }
    setLoading("nvidia-key");
    try {
      const saved = await apiFetch<AIAdvisorNvidiaKeyStatus>("/ai-advisor/nvidia-key", {
        method: "PUT",
        body: JSON.stringify({ api_key: nvidiaApiKey.trim() })
      });
      setNvidiaApiKey("");
      setNvidiaKeyStatus(saved);
      setNvidiaKeyMessage(`Saved ${saved.key_fingerprint ?? "NVIDIA key"}`);
    } catch (err) {
      setNvidiaKeyMessage(err instanceof Error ? err.message : "Could not save NVIDIA key.");
    } finally {
      setLoading("");
    }
  }

  async function deleteNvidiaKey() {
    setLoading("delete-nvidia-key");
    setError("");
    try {
      const deleted = await apiFetch<AIAdvisorNvidiaKeyStatus>("/ai-advisor/nvidia-key", { method: "DELETE" });
      setNvidiaKeyStatus(deleted);
      setNvidiaKeyMessage("NVIDIA key removed.");
    } catch (err) {
      setNvidiaKeyMessage(err instanceof Error ? err.message : "Could not remove NVIDIA key.");
    } finally {
      setLoading("");
    }
  }

  async function saveAlpacaKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setAlpacaKeyMessage("");
    if (!alpacaApiKey.trim() || !alpacaApiSecret.trim()) {
      setAlpacaKeyMessage("Enter both Alpaca API key and secret before saving.");
      return;
    }
    setLoading("alpaca-key");
    try {
      const saved = await apiFetch<AIAdvisorAlpacaKeyStatus>("/ai-advisor/alpaca-key", {
        method: "PUT",
        body: JSON.stringify({ api_key: alpacaApiKey.trim(), api_secret: alpacaApiSecret.trim() })
      });
      setAlpacaApiKey("");
      setAlpacaApiSecret("");
      setAlpacaKeyStatus(saved);
      setAlpacaKeyMessage(`Saved ${saved.key_fingerprint ?? "Alpaca key"}`);
    } catch (err) {
      setAlpacaKeyMessage(err instanceof Error ? err.message : "Could not save Alpaca key.");
    } finally {
      setLoading("");
    }
  }

  async function deleteAlpacaKey() {
    setLoading("delete-alpaca-key");
    setError("");
    try {
      const deleted = await apiFetch<AIAdvisorAlpacaKeyStatus>("/ai-advisor/alpaca-key", { method: "DELETE" });
      setAlpacaKeyStatus(deleted);
      setAlpacaKeyMessage("Alpaca key removed.");
    } catch (err) {
      setAlpacaKeyMessage(err instanceof Error ? err.message : "Could not remove Alpaca key.");
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

  return (
    <StudioContext.Provider
      value={{
        keyStatus,
        tipRanksKeyStatus,
        alpacaKeyStatus,
        lunarCrushKeyStatus,
        nvidiaKeyStatus,
        apiKey,
        setApiKey,
        tipRanksApiKey,
        setTipRanksApiKey,
        lunarCrushApiKey,
        setLunarCrushApiKey,
        nvidiaApiKey,
        setNvidiaApiKey,
        alpacaApiKey,
        setAlpacaApiKey,
        alpacaApiSecret,
        setAlpacaApiSecret,
        keyMessage,
        tipRanksKeyMessage,
        lunarCrushKeyMessage,
        nvidiaKeyMessage,
        alpacaKeyMessage,
        saveKey,
        deleteKey,
        saveTipRanksKey,
        deleteTipRanksKey,
        saveLunarCrushKey,
        deleteLunarCrushKey,
        saveNvidiaKey,
        deleteNvidiaKey,
        saveAlpacaKey,
        deleteAlpacaKey,
        recommendationContext,
        setRecommendationContext,
        reports,
        setReports: setReportsState,
        activeReport,
        setActiveReport,
        openReport,
        loading,
        setLoading,
        error,
        setError
      }}
    >
      {children}
    </StudioContext.Provider>
  );
}
