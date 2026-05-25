"use client";

import { Activity, BarChart3, Bell, Clock3, DownloadCloud, FileDown, LogOut, Play, Plus, RefreshCw, Search, ShieldCheck, SlidersHorizontal, Trash2, Upload } from "lucide-react";
import Link from "next/link";
import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AppHeader } from "@/components/AppHeader";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { BacktestResult, DirectIndexModel, IndexDefinition, ModelComparison, Portfolio, PortfolioImportHoldingInput, PortfolioImportPayload, PortfolioImportResult, PortfolioImportTaxLotInput, PortfolioInitialization, ThirteenFManagerCandidate, ThirteenFPerformance, ThirteenFSearchResult, ThirteenFWatch, Trade, TradeGeneration, apiFetch, apiUrl, currency, percent } from "@/lib/api";

const years = [2025, 2024, 2023];
const portfolioSampleRows = `AAPL,Apple Inc,Information Technology,120,180,90,2021-01-04
MSFT,Microsoft Corp,Information Technology,60,420,460,2024-08-01
JPM,JPMorgan Chase,Financials,75,210,170,2022-03-15`;
const tlhModes = [
  { value: "conservative", label: "Conservative" },
  { value: "moderate", label: "Moderate" },
  { value: "aggressive", label: "Aggressive" }
] as const;
const directIndexModels = [
  { value: "risk_score", label: "Risk score" },
  { value: "threshold_throttle", label: "Threshold" },
  { value: "peer_basket", label: "Peer basket" },
  { value: "completion_etf", label: "ETF sleeve" }
] as const;
const fallbackModels: DirectIndexModel[] = [
  { id: "risk_score", label: "Risk-score optimizer", rank: 1, executable: true, summary: "Scores tax-loss value against tracking drift, turnover, and wash-sale constraints.", best_for: "Default model when tracking discipline dominates tax value.", source_support: ["Frec", "Wealthfront", "IRS"] },
  { id: "threshold_throttle", label: "Threshold throttle", rank: 2, executable: true, summary: "Harvests only losses that clear a threshold and throttles active risk.", best_for: "Lower-turnover accounts.", source_support: ["Israelov/Lu", "IRS"] },
  { id: "peer_basket", label: "Peer basket", rank: 3, executable: true, summary: "Replaces harvested names with same-sector peer baskets.", best_for: "Stock-only replacement exposure.", source_support: ["Frec", "Wealthfront"] },
  { id: "completion_etf", label: "Completion ETF sleeve", rank: 4, executable: true, summary: "Uses the selected ETF/index sleeve as temporary replacement exposure.", best_for: "Lower replacement trade count.", source_support: ["Wealthfront", "ETF TLH baseline"] },
  { id: "etf_pair_tlh", label: "ETF-pair TLH baseline", rank: 5, executable: false, summary: "Swaps broad ETFs with correlated alternatives.", best_for: "Baseline comparison only.", source_support: ["Wealthfront", "Israelov/Lu"] },
  { id: "full_replication", label: "Full replication direct indexing", rank: 6, executable: false, summary: "Owns every constituent when account size supports it.", best_for: "Large accounts with fractional shares.", source_support: ["Provider literature", "Frec"] },
  { id: "tax_aware_reinvestment", label: "Tax-aware reinvestment", rank: 7, executable: false, summary: "Models quarterly reinvestment of realized tax savings.", best_for: "High-tax investors with external gains.", source_support: ["Frec", "Sosner/Gromis/Krasner"] },
  { id: "long_short_direct_indexing", label: "Long-short direct indexing", rank: 8, executable: false, summary: "Uses long-short extensions and leverage to generate larger tax assets.", best_for: "Research-only high-net-worth simulation.", source_support: ["AQR"] }
];

type TlhMode = (typeof tlhModes)[number]["value"];
type DirectIndexModelId = (typeof directIndexModels)[number]["value"];
type DashboardTab = "backtests" | "models" | "current" | "portfolio";

export default function DashboardPage() {
  const [indices, setIndices] = useState<IndexDefinition[]>([]);
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<number | null>(null);
  const [selectedIndex, setSelectedIndex] = useState("XLG");
  const [startingValue, setStartingValue] = useState(100000);
  const [estimatedTaxRate, setEstimatedTaxRate] = useState(35);
  const [tlhMode, setTlhMode] = useState<TlhMode>("aggressive");
  const [directIndexModel, setDirectIndexModel] = useState<DirectIndexModelId>("peer_basket");
  const [modelLabIndex, setModelLabIndex] = useState("XLG");
  const [exclusion, setExclusion] = useState("");
  const [syncWarning, setSyncWarning] = useState("");
  const [tradeResult, setTradeResult] = useState<TradeGeneration | null>(null);
  const [backtest, setBacktest] = useState<BacktestResult | null>(null);
  const [modelComparison, setModelComparison] = useState<ModelComparison | null>(null);
  const [portfolioInitialization, setPortfolioInitialization] = useState<PortfolioInitialization | null>(null);
  const [importPortfolioName, setImportPortfolioName] = useState("Imported taxable account");
  const [importIndex, setImportIndex] = useState("SPY");
  const [importCash, setImportCash] = useState(0);
  const [portfolioCsvRows, setPortfolioCsvRows] = useState(portfolioSampleRows);
  const [portfolioImportResult, setPortfolioImportResult] = useState<PortfolioImportResult | null>(null);
  const [managerQuery, setManagerQuery] = useState("Warren Buffett");
  const [filingCandidates, setFilingCandidates] = useState<ThirteenFManagerCandidate[]>([]);
  const [selectedFilingCandidate, setSelectedFilingCandidate] = useState<ThirteenFManagerCandidate | null>(null);
  const [thirteenFWatches, setThirteenFWatches] = useState<ThirteenFWatch[]>([]);
  const [thirteenFPerformance, setThirteenFPerformance] = useState<ThirteenFPerformance | null>(null);
  const [filingWarning, setFilingWarning] = useState("");
  const [backtestYear, setBacktestYear] = useState(2025);
  const [activeTab, setActiveTab] = useState<DashboardTab>("backtests");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState("");

  const selectedPortfolio = useMemo(
    () => portfolios.find((portfolio) => portfolio.id === selectedPortfolioId) ?? portfolios[0],
    [portfolios, selectedPortfolioId]
  );
  const parsedPortfolioImport = useMemo(() => parsePortfolioImportRows(portfolioCsvRows), [portfolioCsvRows]);

  useEffect(() => {
    void bootstrap();
  }, []);

  async function bootstrap() {
    setError("");
    try {
      const [indexRows, portfolioRows, filingWatches] = await Promise.all([
        apiFetch<IndexDefinition[]>("/indices"),
        apiFetch<Portfolio[]>("/portfolios"),
        apiFetch<ThirteenFWatch[]>("/filings/13f/watches")
      ]);
      setIndices(indexRows);
      setPortfolios(portfolioRows);
      setThirteenFWatches(filingWatches);
      if (portfolioRows[0]) {
        setSelectedPortfolioId(portfolioRows[0].id);
        setSelectedIndex(portfolioRows[0].index_symbol);
        setStartingValue(portfolioRows[0].starting_value);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load dashboard");
    }
  }

  async function logout() {
    await apiFetch("/auth/logout", { method: "POST" });
  }

  async function createPortfolio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading("portfolio");
    setError("");
    try {
      const created = await apiFetch<Portfolio>("/portfolios", {
        method: "POST",
        body: JSON.stringify({
          name: `${selectedIndex} direct index`,
          index_symbol: selectedIndex,
          starting_value: startingValue
        })
      });
      setPortfolios((current) => [created, ...current]);
      setSelectedPortfolioId(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create portfolio");
    } finally {
      setLoading("");
    }
  }

  function handlePortfolioImportFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setPortfolioCsvRows(String(reader.result ?? ""));
    reader.readAsText(file);
  }

  async function importPortfolio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading("portfolio-import");
    setError("");
    setSyncWarning("");
    try {
      if (!parsedPortfolioImport.holdings.length && !parsedPortfolioImport.tax_lots.length) {
        throw new Error("Add at least one valid portfolio row before importing.");
      }
      const result = await apiFetch<PortfolioImportResult>("/portfolios/import", {
        method: "POST",
        body: JSON.stringify({
          name: importPortfolioName,
          index_symbol: importIndex,
          cash: importCash,
          holdings: parsedPortfolioImport.holdings,
          tax_lots: parsedPortfolioImport.tax_lots
        } satisfies PortfolioImportPayload)
      });
      setPortfolios((current) => [result.portfolio, ...current.filter((item) => item.id !== result.portfolio.id)]);
      setSelectedPortfolioId(result.portfolio.id);
      setSelectedIndex(result.portfolio.index_symbol);
      setStartingValue(result.portfolio.starting_value);
      setPortfolioImportResult(result);
      setSyncWarning(`Imported ${result.imported_tax_lots} tax lots into ${result.portfolio.name}.`);
      setActiveTab("portfolio");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Portfolio import failed");
    } finally {
      setLoading("");
    }
  }

  async function syncData() {
    setLoading("sync");
    setError("");
    try {
      const result = await apiFetch<{ status: string; synced_indices: string[]; warning?: string | null }>("/data/sync", { method: "POST" });
      setSyncWarning(result.warning ?? "Data sync completed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Data sync failed");
    } finally {
      setLoading("");
    }
  }

  async function addExclusion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedPortfolio || !exclusion.trim()) return;
    setLoading("exclusion");
    setError("");
    try {
      const updated = await apiFetch<Portfolio>(`/portfolios/${selectedPortfolio.id}/exclusions`, {
        method: "POST",
        body: JSON.stringify({ symbol: exclusion.trim(), reason: "User requested exclusion" })
      });
      setPortfolios((current) => current.map((item) => item.id === updated.id ? updated : item));
      setExclusion("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add exclusion");
    } finally {
      setLoading("");
    }
  }

  async function removeExclusion(symbol: string) {
    if (!selectedPortfolio) return;
    const updated = await apiFetch<Portfolio>(`/portfolios/${selectedPortfolio.id}/exclusions/${symbol}`, { method: "DELETE" });
    setPortfolios((current) => current.map((item) => item.id === updated.id ? updated : item));
  }

  async function generateTrades() {
    if (!selectedPortfolio) return;
    setLoading("trades");
    setError("");
    try {
      const result = await apiFetch<TradeGeneration>(`/portfolios/${selectedPortfolio.id}/trades/generate`, {
        method: "POST",
        body: JSON.stringify({ enable_tlh: true, tlh_mode: tlhMode, direct_index_model: directIndexModel })
      });
      setTradeResult(result);
      setActiveTab("current");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Trade generation failed");
    } finally {
      setLoading("");
    }
  }

  async function previewTrades() {
    if (!selectedPortfolio) return;
    setLoading("preview");
    setError("");
    try {
      const result = await apiFetch<TradeGeneration>(`/portfolios/${selectedPortfolio.id}/trades/preview`, {
        method: "POST",
        body: JSON.stringify({ enable_tlh: true, tlh_mode: tlhMode, direct_index_model: directIndexModel })
      });
      setTradeResult(result);
      setActiveTab("current");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Trade preview failed");
    } finally {
      setLoading("");
    }
  }

  async function initializeCurrentPortfolio() {
    if (!selectedPortfolio) return;
    setLoading("initialize");
    setError("");
    try {
      const result = await apiFetch<PortfolioInitialization>(`/portfolios/${selectedPortfolio.id}/initialize-current`, {
        method: "POST",
        body: JSON.stringify({})
      });
      setPortfolioInitialization(result);
      setSyncWarning(`Current portfolio seeded as of ${result.as_of_date} with ${result.seeded_positions} positions.`);
      setPortfolios((current) => current.map((item) => item.id === result.portfolio.id ? result.portfolio : item));
      setActiveTab("current");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not set portfolio current");
    } finally {
      setLoading("");
    }
  }

  async function runBacktest() {
    const index = selectedPortfolio?.index_symbol ?? selectedIndex;
    const exclusions = selectedPortfolio?.exclusions ?? [];
    setLoading("backtest");
    setError("");
    try {
      const result = await apiFetch<BacktestResult>("/backtests", {
        method: "POST",
        body: JSON.stringify({
          index_symbol: index,
          year: backtestYear,
          starting_value: startingValue,
          exclusions,
          estimated_tax_rate: estimatedTaxRate / 100,
          tlh_mode: tlhMode,
          direct_index_model: directIndexModel
        })
      });
      setBacktest(result);
      setActiveTab("backtests");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backtest failed");
    } finally {
      setLoading("");
    }
  }

  async function runModelComparison() {
    const exclusions = selectedPortfolio?.exclusions ?? [];
    setLoading("models");
    setError("");
    try {
      const result = await apiFetch<ModelComparison>("/backtests/model-comparison", {
        method: "POST",
        body: JSON.stringify({
          index_symbol: modelLabIndex,
          years,
          starting_value: startingValue,
          exclusions,
          estimated_tax_rate: estimatedTaxRate / 100,
          tlh_mode: tlhMode
        })
      });
      setModelComparison(result);
      if (isDirectIndexModelId(result.recommended_model)) {
        setDirectIndexModel(result.recommended_model);
        setSyncWarning(`${result.recommended_model_label ?? modelLabel(result.recommended_model)} is now the current-year default from the ${result.index_symbol} model lab.`);
      }
      setActiveTab("models");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Model comparison failed");
    } finally {
      setLoading("");
    }
  }

  async function search13FManagers(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!managerQuery.trim()) return;
    setLoading("13f-search");
    setError("");
    setFilingWarning("");
    try {
      const result = await apiFetch<ThirteenFSearchResult>("/filings/13f/search", {
        method: "POST",
        body: JSON.stringify({ query: managerQuery.trim() })
      });
      setFilingCandidates(result.candidates);
      setSelectedFilingCandidate(result.candidates[0] ?? null);
      setFilingWarning(result.warning ?? (result.candidates.length ? `${result.candidates.length} manager match${result.candidates.length === 1 ? "" : "es"} found.` : "No 13F manager matches found."));
      setActiveTab("portfolio");
    } catch (err) {
      setError(err instanceof Error ? err.message : "13F manager search failed");
    } finally {
      setLoading("");
    }
  }

  async function watch13FManager(candidate?: ThirteenFManagerCandidate | null) {
    const selectedCandidate = candidate ?? selectedFilingCandidate;
    if (!managerQuery.trim() && !selectedCandidate) return;
    setLoading("13f-watch");
    setError("");
    setFilingWarning("");
    try {
      const watch = await apiFetch<ThirteenFWatch>("/filings/13f/watches", {
        method: "POST",
        body: JSON.stringify({
          query: managerQuery.trim() || selectedCandidate?.manager_name,
          cik: selectedCandidate?.cik,
          manager_name: selectedCandidate?.manager_name
        })
      });
      setThirteenFWatches((current) => [watch, ...current.filter((item) => item.id !== watch.id)]);
      setSelectedFilingCandidate(selectedCandidate ?? {
        cik: watch.cik,
        manager_name: watch.manager_name,
        match_source: "watch"
      });
      setFilingWarning(watch.warning ?? `${watch.manager_name} is being checked during 13F filing windows.`);
      setActiveTab("portfolio");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create 13F watch");
    } finally {
      setLoading("");
    }
  }

  async function refresh13FWatch(watchId: number) {
    setLoading(`13f-refresh-${watchId}`);
    setError("");
    setFilingWarning("");
    try {
      const watch = await apiFetch<ThirteenFWatch>(`/filings/13f/watches/${watchId}/refresh`, { method: "POST" });
      setThirteenFWatches((current) => current.map((item) => item.id === watch.id ? watch : item));
      setFilingWarning(watch.warning ?? `${watch.manager_name} checked for the latest 13F filing.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "13F refresh failed");
    } finally {
      setLoading("");
    }
  }

  async function analyze13FPerformance(watchId: number) {
    setLoading(`13f-performance-${watchId}`);
    setError("");
    setFilingWarning("");
    try {
      const result = await apiFetch<ThirteenFPerformance>(`/filings/13f/watches/${watchId}/performance?years=4&starting_value=100000&benchmark_symbol=SPY`);
      setThirteenFPerformance(result);
      setFilingWarning(`${result.manager_name} local 13F cache now covers ${result.cached_filings} filings and ${result.cached_holdings} holdings.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "13F performance analysis failed");
    } finally {
      setLoading("");
    }
  }

  async function delete13FWatch(watchId: number) {
    setLoading(`13f-delete-${watchId}`);
    setError("");
    try {
      await apiFetch(`/filings/13f/watches/${watchId}`, { method: "DELETE" });
      setThirteenFWatches((current) => current.filter((item) => item.id !== watchId));
      setThirteenFPerformance((current) => current?.watch_id === watchId ? null : current);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove 13F watch");
    } finally {
      setLoading("");
    }
  }

  const activeTrades = activeTab === "current" ? tradeResult?.trades ?? [] : backtest?.trades ?? [];
  const displayedCapUsed = activeTab === "backtests" ? backtest?.cap_used ?? 0 : tradeResult?.cap_used ?? 0;
  const displayedCapRemaining = activeTab === "backtests" ? backtest?.cap_remaining ?? 1000 : tradeResult?.cap_remaining ?? 1000;
  const displayedDroppedCandidates = activeTab === "backtests" ? backtest?.dropped_tlh_candidates ?? 0 : tradeResult?.dropped_tlh_candidates ?? 0;
  const displayedSkippedLossValue = activeTab === "backtests" ? backtest?.skipped_tax_loss_value ?? 0 : tradeResult?.skipped_tax_loss_value ?? 0;
  const displayedHarvestedLosses = activeTab === "backtests" ? backtest?.harvested_losses ?? 0 : sumHarvested(activeTrades);
  const chartData = activeTab === "backtests" && backtest
    ? [
      { name: "Portfolio", value: backtest.ending_value },
      { name: "Benchmark", value: backtest.benchmark_value },
      { name: "Tax adj.", value: backtest.tax_adjusted_ending_value },
      { name: "Harvested", value: backtest.harvested_losses }
    ]
    : [
      { name: "Tracking", value: tradeResult?.tracking_score ?? 0 },
      { name: "Cap used", value: tradeResult?.cap_used ?? 0 },
      { name: "Dropped", value: tradeResult?.dropped_tlh_candidates ?? 0 }
    ];

  return (
    <main className="dashboard-shell">
      <AppHeader
        title="Portfolio dashboard"
        actions={
          <>
          <Link className="ghost-button" href="/research">Research</Link>
          <Link className="ghost-button" href="/portfolio">Portfolio analyzer</Link>
          <Link className="ghost-button" href="/ideas">Ideas</Link>
          <Link className="ghost-button" href="/advisor">Advisor</Link>
          <Link className="ghost-button" href="/retirement-analyzer">Plan</Link>
          <button className="secondary-button" onClick={syncData} disabled={loading === "sync"}><DownloadCloud size={16} /> {loading === "sync" ? "Syncing" : "Sync data"}</button>
          <button className="ghost-button" onClick={logout}><LogOut size={16} /> Log out</button>
          </>
        }
      />

      <div className="dashboard-disclaimer">
        <LegalDisclaimer compact />
      </div>

      <div className="dashboard-grid">
        <aside className="sidebar">
          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Portfolio</h2>
              <SlidersHorizontal size={18} />
            </div>
            <form className="form-stack" onSubmit={createPortfolio}>
              <div className="field">
                <label htmlFor="index">Index</label>
                <select id="index" value={selectedIndex} onChange={(event) => setSelectedIndex(event.target.value)}>
                  {indices.map((index) => <option key={index.symbol} value={index.symbol}>{index.symbol} · {index.benchmark}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="value">Starting value</label>
                <input id="value" type="number" min="1000" step="1000" value={startingValue} onChange={(event) => setStartingValue(Number(event.target.value))} />
              </div>
              <button className="primary-button" type="submit" disabled={loading === "portfolio"}><Plus size={16} /> Create portfolio</button>
            </form>
          </section>

          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Active account</h2>
              <span className="status-pill"><ShieldCheck size={14} /> Secure</span>
            </div>
            {selectedPortfolio ? (
              <div className="form-stack">
                <div className="field">
                  <label htmlFor="portfolio-select">Portfolio</label>
                  <select
                    id="portfolio-select"
                    value={selectedPortfolio.id}
                    onChange={(event) => {
                      const id = Number(event.target.value);
                      const next = portfolios.find((portfolio) => portfolio.id === id);
                      setSelectedPortfolioId(id);
                      if (next) {
                        setSelectedIndex(next.index_symbol);
                        setStartingValue(next.starting_value);
                      }
                    }}
                  >
                    {portfolios.map((portfolio) => <option key={portfolio.id} value={portfolio.id}>{portfolio.name}</option>)}
                  </select>
                </div>
                <p className="fine-print">{selectedPortfolio.index_symbol} · {currency(selectedPortfolio.starting_value)} · {selectedPortfolio.exclusions.length} exclusions</p>
              </div>
            ) : <p className="fine-print">Create a portfolio to generate trades.</p>}
          </section>

          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Exclusions</h2>
              <Trash2 size={18} />
            </div>
            <form className="form-stack" onSubmit={addExclusion}>
              <div className="field">
                <label htmlFor="exclude">Ticker</label>
                <input id="exclude" value={exclusion} onChange={(event) => setExclusion(event.target.value.toUpperCase())} placeholder="TSLA" />
              </div>
              <button className="secondary-button" type="submit" disabled={!selectedPortfolio || loading === "exclusion"}>Add exclusion</button>
            </form>
            <div className="inline-actions" style={{ marginTop: 14 }}>
              {selectedPortfolio?.exclusions.map((symbol) => (
                <button className="ghost-button" key={symbol} onClick={() => removeExclusion(symbol)}>{symbol} <Trash2 size={14} /></button>
              ))}
            </div>
          </section>
        </aside>

        <section className="workspace">
          {error ? <div className="error">{error}</div> : null}
          {syncWarning ? <ul className="warning-list"><li>{syncWarning}</li></ul> : null}

          <div className="stat-grid">
            <article className="stat-panel"><Activity size={20} /><h3>Tracking score</h3><strong>{tradeResult ? tradeResult.tracking_score.toFixed(1) : "0.0"}</strong><p>Higher is closer to target weights.</p></article>
            <article className="stat-panel"><RefreshCw size={20} /><h3>TLH cap used</h3><strong>{displayedCapUsed}</strong><p>{displayedCapRemaining} trades remaining this year.</p></article>
            <article className="stat-panel"><BarChart3 size={20} /><h3>Harvested losses</h3><strong>{currency(displayedHarvestedLosses)}</strong><p>Simulated tax-loss value before tax-rate assumptions.</p></article>
            <article className="stat-panel"><ShieldCheck size={20} /><h3>Dropped candidates</h3><strong>{displayedDroppedCandidates}</strong><p>{currency(displayedSkippedLossValue)} skipped by cap.</p></article>
          </div>

          <nav className="tab-list" aria-label="Dashboard sections">
            <button className={activeTab === "backtests" ? "active" : ""} onClick={() => setActiveTab("backtests")}>Backtests</button>
            <button className={activeTab === "models" ? "active" : ""} onClick={() => setActiveTab("models")}>Model Lab</button>
            <button className={activeTab === "current" ? "active" : ""} onClick={() => setActiveTab("current")}>Current Year Trades</button>
            <button className={activeTab === "portfolio" ? "active" : ""} onClick={() => setActiveTab("portfolio")}>Portfolio</button>
          </nav>

          {activeTab === "backtests" ? (
            <>
              <section className="dashboard-panel chart-panel">
                <div className="panel-header">
                  <h2>Backtests</h2>
                  <div className="dashboard-actions">
                    <select value={backtestYear} onChange={(event) => setBacktestYear(Number(event.target.value))}>
                      {years.map((year) => <option key={year} value={year}>{year}</option>)}
                    </select>
                    <select value={directIndexModel} onChange={(event) => setDirectIndexModel(event.target.value as DirectIndexModelId)}>
                      {directIndexModels.map((model) => <option key={model.value} value={model.value}>{model.label}</option>)}
                    </select>
                    <label className="inline-field" htmlFor="tax-rate">
                      <span>Tax rate</span>
                      <input id="tax-rate" type="number" min="0" max="60" step="1" value={estimatedTaxRate} onChange={(event) => setEstimatedTaxRate(Number(event.target.value))} />
                    </label>
                    <TlhModeControl tlhMode={tlhMode} setTlhMode={setTlhMode} />
                    <button className="secondary-button" onClick={runBacktest} disabled={loading === "backtest"}><Play size={16} /> {loading === "backtest" ? "Running" : "Run backtest"}</button>
                  </div>
                </div>
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={chartData}>
                    <CartesianGrid stroke="#dfe7e3" vertical={false} />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip formatter={(value) => typeof value === "number" && value > 1000 ? currency(value) : value} />
                    <Bar dataKey="value" fill="#143d2a" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </section>

              {backtest?.warnings.length ? <WarningList warnings={backtest.warnings} /> : null}
              {backtest ? <BacktestSummary backtest={backtest} /> : null}
              <TradeList title="Backtest trades" trades={activeTrades} />
            </>
          ) : null}

          {activeTab === "models" ? (
            <>
              <section className="dashboard-panel">
                <div className="panel-header">
                  <h2>Direct indexing model lab</h2>
                  <div className="dashboard-actions">
                    <select value={modelLabIndex} onChange={(event) => setModelLabIndex(event.target.value)}>
                      {indices.map((index) => <option key={index.symbol} value={index.symbol}>{index.symbol}</option>)}
                    </select>
                    <TlhModeControl tlhMode={tlhMode} setTlhMode={setTlhMode} />
                    <button className="secondary-button" onClick={runModelComparison} disabled={loading === "models"}><BarChart3 size={16} /> {loading === "models" ? "Testing" : `Test ${modelLabIndex} models`}</button>
                  </div>
                </div>
                <p className="outcome-note">{modelComparison?.recommendation ?? "Executable models are tested against XLG by default for full 2023, 2024, and 2025 history. The winner becomes the current-year default model."}</p>
              </section>
              <ModelCards models={modelComparison?.models ?? fallbackModels} recommendedModel={modelComparison?.recommended_model} />
              <ModelComparisonTable comparison={modelComparison} />
            </>
          ) : null}

          {activeTab === "current" ? (
            <>
              <section className="dashboard-panel chart-panel">
                <div className="panel-header">
                  <h2>Current year trades</h2>
                  <div className="dashboard-actions">
                    <select value={directIndexModel} onChange={(event) => setDirectIndexModel(event.target.value as DirectIndexModelId)}>
                      {directIndexModels.map((model) => <option key={model.value} value={model.value}>{model.label}</option>)}
                    </select>
                    <span className="reason-pill">Default {modelLabel(directIndexModel)}</span>
                    <TlhModeControl tlhMode={tlhMode} setTlhMode={setTlhMode} />
                    <button className="secondary-button" onClick={initializeCurrentPortfolio} disabled={!selectedPortfolio || loading === "initialize"}><ShieldCheck size={16} /> {loading === "initialize" ? "Setting" : "Set portfolio current"}</button>
                    <button className="secondary-button" onClick={previewTrades} disabled={!selectedPortfolio || loading === "preview"}><RefreshCw size={16} /> {loading === "preview" ? "Previewing" : "Preview trades"}</button>
                    <button className="primary-button" onClick={generateTrades} disabled={!selectedPortfolio || loading === "trades"}><RefreshCw size={16} /> {loading === "trades" ? "Generating" : "Generate trades"}</button>
                  </div>
                </div>
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={chartData}>
                    <CartesianGrid stroke="#dfe7e3" vertical={false} />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip formatter={(value) => typeof value === "number" && value > 1000 ? currency(value) : value} />
                    <Bar dataKey="value" fill="#143d2a" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </section>
              {portfolioInitialization ? (
                <section className="dashboard-panel">
                  <div className="metric-strip">
                    <div className="metric"><span>As of</span><strong>{portfolioInitialization.as_of_date}</strong></div>
                    <div className="metric"><span>Seeded positions</span><strong>{portfolioInitialization.seeded_positions}</strong></div>
                    <div className="metric"><span>Invested</span><strong>{currency(portfolioInitialization.invested_value)}</strong></div>
                  </div>
                </section>
              ) : null}
              {tradeResult?.warnings.length ? <WarningList warnings={tradeResult.warnings} /> : null}
              <TradeList title="Current-year trade recommendations" trades={activeTrades} />
            </>
          ) : null}

          {activeTab === "portfolio" ? (
            <>
              <section className="dashboard-panel">
                <div className="panel-header">
                  <h2>Import portfolio</h2>
                  <span className="reason-pill"><Upload size={14} /> CSV</span>
                </div>
                <form className="form-stack" onSubmit={importPortfolio}>
                  <div className="portfolio-import-grid">
                    <div className="field">
                      <label htmlFor="import-name">Portfolio name</label>
                      <input id="import-name" value={importPortfolioName} onChange={(event) => setImportPortfolioName(event.target.value)} />
                    </div>
                    <div className="field">
                      <label htmlFor="import-index">Target index</label>
                      <select id="import-index" value={importIndex} onChange={(event) => setImportIndex(event.target.value)}>
                        {indices.map((index) => <option key={index.symbol} value={index.symbol}>{index.symbol} · {index.benchmark}</option>)}
                      </select>
                    </div>
                    <div className="field">
                      <label htmlFor="import-cash">Cash</label>
                      <input id="import-cash" type="number" min="0" step="100" value={importCash} onChange={(event) => setImportCash(Number(event.target.value))} />
                    </div>
                    <div className="field">
                      <label htmlFor="portfolio-import-file">CSV file</label>
                      <input id="portfolio-import-file" type="file" accept=".csv,text/csv" onChange={handlePortfolioImportFile} />
                    </div>
                  </div>
                  <div className="field">
                    <label htmlFor="portfolio-csv">Portfolio rows</label>
                    <textarea id="portfolio-csv" className="csv-input" value={portfolioCsvRows} onChange={(event) => setPortfolioCsvRows(event.target.value)} />
                  </div>
                  <div className="metric-strip import-summary">
                    <div className="metric"><span>Positions</span><strong>{parsedPortfolioImport.holdings.length}</strong></div>
                    <div className="metric"><span>Tax lots</span><strong>{parsedPortfolioImport.tax_lots.length}</strong></div>
                    <div className="metric"><span>Market value</span><strong>{currency(parsedPortfolioImport.totalValue + importCash)}</strong></div>
                  </div>
                  <button className="primary-button" type="submit" disabled={loading === "portfolio-import"}>
                    <Upload size={16} /> {loading === "portfolio-import" ? "Importing" : "Import portfolio"}
                  </button>
                </form>
                {portfolioImportResult ? (
                  <p className="outcome-note">
                    {portfolioImportResult.portfolio.name} is now selected with {portfolioImportResult.imported_tax_lots} open tax lots.
                  </p>
                ) : null}
                {portfolioImportResult?.warnings.length ? <WarningList warnings={portfolioImportResult.warnings} /> : null}
              </section>

              <section className="dashboard-panel">
                <div className="panel-header">
                  <h2>13F filing downloads</h2>
                  <span className="reason-pill"><Bell size={14} /> 2-hour filing-window checks</span>
                </div>
                <form className="filing-search" onSubmit={search13FManagers}>
                  <div className="field">
                    <label htmlFor="manager-query">Hedge fund or manager</label>
                    <input
                      id="manager-query"
                      value={managerQuery}
                      onChange={(event) => setManagerQuery(event.target.value)}
                      placeholder="Warren Buffett, Berkshire Hathaway, Citadel"
                    />
                  </div>
                  <button className="secondary-button" type="submit" disabled={loading === "13f-search"}>
                    <Search size={16} /> {loading === "13f-search" ? "Searching" : "Search SEC"}
                  </button>
                  <button className="primary-button" type="button" onClick={() => watch13FManager()} disabled={loading === "13f-watch" || (!selectedFilingCandidate && !managerQuery.trim())}>
                    <Bell size={16} /> {loading === "13f-watch" ? "Watching" : "Watch and fetch"}
                  </button>
                </form>
                {filingWarning ? <p className="outcome-note">{filingWarning}</p> : null}
              </section>

              {filingCandidates.length ? (
                <section className="filing-candidate-grid">
                  {filingCandidates.map((candidate) => (
                    <article className={selectedFilingCandidate?.cik === candidate.cik ? "dashboard-panel filing-card selected" : "dashboard-panel filing-card"} key={candidate.cik}>
                      <div className="panel-header">
                        <h2>{candidate.manager_name}</h2>
                        <span className="reason-pill">{candidate.match_source.replaceAll("-", " ")}</span>
                      </div>
                      <div className="metric-strip stacked">
                        <div className="metric"><span>CIK</span><strong>{candidate.cik}</strong></div>
                        <div className="metric"><span>Latest report</span><strong>{formatOptionalDate(candidate.latest_report_period)}</strong></div>
                      </div>
                      <div className="inline-actions">
                        <button className="secondary-button" onClick={() => setSelectedFilingCandidate(candidate)}>Select</button>
                        <button className="primary-button" onClick={() => watch13FManager(candidate)} disabled={loading === "13f-watch"}><Bell size={16} /> Watch</button>
                      </div>
                    </article>
                  ))}
                </section>
              ) : null}

              <section className="dashboard-panel">
                <div className="table-header" style={{ marginBottom: 14 }}>
                  <h2>Watched 13F managers</h2>
                  <span className="reason-pill">{thirteenFWatches.length} active</span>
                </div>
                <ThirteenFWatchTable watches={thirteenFWatches} loading={loading} onRefresh={refresh13FWatch} onAnalyze={analyze13FPerformance} onDelete={delete13FWatch} />
              </section>
              {thirteenFPerformance ? <ThirteenFPerformancePanel performance={thirteenFPerformance} /> : null}
            </>
          ) : null}
        </section>
      </div>
    </main>
  );
}

function sumHarvested(trades: Trade[]) {
  return trades.reduce((total, trade) => total + (trade.harvested_loss ?? 0), 0);
}

function parsePortfolioImportRows(value: string): {
  holdings: PortfolioImportHoldingInput[];
  tax_lots: PortfolioImportTaxLotInput[];
  totalValue: number;
} {
  const today = new Date().toISOString().slice(0, 10);
  const rows = value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.split(",").map((part) => part.trim()))
    .filter((row) => row[0]?.toLowerCase() !== "symbol");

  const holdings = rows.flatMap((row) => {
    const fullRow = row.length >= 7;
    const symbol = row[0];
    const name = fullRow ? row[1] : "";
    const sector = fullRow ? row[2] : "";
    const shares = Number(fullRow ? row[3] : row[1]);
    const price = Number(fullRow ? row[4] : row[2]);
    if (!symbol || !Number.isFinite(shares) || !Number.isFinite(price) || shares <= 0 || price <= 0) return [];
    return [{
      symbol: symbol.toUpperCase(),
      name,
      sector,
      shares,
      price,
      market_value: shares * price,
      as_of_date: today
    }];
  });

  const tax_lots = rows.flatMap((row) => {
    const fullRow = row.length >= 7;
    const symbol = row[0];
    const shares = Number(fullRow ? row[3] : row[1]);
    const costBasis = Number(fullRow ? row[5] : row[3]);
    const acquisitionDate = fullRow ? row[6] : row[4];
    if (!symbol || !acquisitionDate || !Number.isFinite(shares) || !Number.isFinite(costBasis) || shares <= 0 || costBasis <= 0) return [];
    return [{
      symbol: symbol.toUpperCase(),
      acquisition_date: acquisitionDate,
      shares,
      cost_basis_per_share: costBasis
    }];
  });

  return {
    holdings,
    tax_lots,
    totalValue: holdings.reduce((total, row) => total + (row.market_value ?? 0), 0)
  };
}

function modeLabel(value: string) {
  return tlhModes.find((mode) => mode.value === value)?.label ?? value;
}

function modelLabel(value: string) {
  return directIndexModels.find((model) => model.value === value)?.label ?? value.replaceAll("_", " ");
}

function isDirectIndexModelId(value: string | null | undefined): value is DirectIndexModelId {
  return directIndexModels.some((model) => model.value === value);
}

function TlhModeControl({ tlhMode, setTlhMode }: { tlhMode: TlhMode; setTlhMode: (mode: TlhMode) => void }) {
  return (
    <div className="mode-control" role="group" aria-label="Tax-loss harvesting mode">
      {tlhModes.map((mode) => (
        <button
          key={mode.value}
          type="button"
          className={tlhMode === mode.value ? "active" : ""}
          onClick={() => setTlhMode(mode.value)}
        >
          {mode.label}
        </button>
      ))}
    </div>
  );
}

function WarningList({ warnings }: { warnings: string[] }) {
  return (
    <ul className="warning-list">
      {warnings.map((warning) => <li key={warning}>{warning}</li>)}
    </ul>
  );
}

function ThirteenFWatchTable({
  watches,
  loading,
  onRefresh,
  onAnalyze,
  onDelete
}: {
  watches: ThirteenFWatch[];
  loading: string;
  onRefresh: (watchId: number) => void;
  onAnalyze: (watchId: number) => void;
  onDelete: (watchId: number) => void;
}) {
  if (!watches.length) {
    return <p className="fine-print">No 13F managers watched yet.</p>;
  }
  return (
    <div className="table-wrap">
      <div className="filing-watch-table">
        <div className="filing-watch-row header">
          <span>Manager</span><span>Latest filing</span><span>Report period</span><span>Last check</span><span>Next check</span><span>Actions</span>
        </div>
        {watches.map((watch) => (
          <div className="filing-watch-row" key={watch.id}>
            <div>
              <strong>{watch.manager_name}</strong>
              <span className="table-subtext">CIK {watch.cik}</span>
              {watch.warning ? <span className="table-warning">{watch.warning}</span> : null}
            </div>
            <span>{formatOptionalDate(watch.latest_filing_date)}{watch.latest_form ? ` · ${watch.latest_form}` : ""}</span>
            <span>{formatOptionalDate(watch.latest_report_period)}</span>
            <span>{formatOptionalDateTime(watch.last_checked_at)}</span>
            <span><Clock3 size={14} /> {formatOptionalDateTime(watch.next_check_at)}</span>
            <div className="inline-actions filing-actions">
              <button className="ghost-button" aria-label="Check latest 13F" title="Check latest 13F" onClick={() => onRefresh(watch.id)} disabled={loading === `13f-refresh-${watch.id}`}>
                <RefreshCw size={16} />
              </button>
              {watch.download_url ? (
                <a className="secondary-button" href={`${apiUrl()}${watch.download_url}`}>
                  <FileDown size={16} /> Download
                </a>
              ) : (
                <span className="risk-pill">No file</span>
              )}
              <button className="secondary-button" onClick={() => onAnalyze(watch.id)} disabled={loading === `13f-performance-${watch.id}`}>
                <BarChart3 size={16} /> {loading === `13f-performance-${watch.id}` ? "Analyzing" : "Analyze"}
              </button>
              <button className="ghost-button" aria-label="Remove 13F watch" title="Remove 13F watch" onClick={() => onDelete(watch.id)} disabled={loading === `13f-delete-${watch.id}`}>
                <Trash2 size={16} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ThirteenFPerformancePanel({ performance }: { performance: ThirteenFPerformance }) {
  const latestPeriod = performance.periods[performance.periods.length - 1];
  return (
    <section className="dashboard-panel">
      <div className="panel-header">
        <h2>{performance.manager_name} copycat performance</h2>
        <div className="inline-actions">
          <span className="reason-pill">4Y local cache</span>
          <span className="reason-pill">{performance.cached_filings} filings</span>
          <span className="reason-pill">{performance.priced_holdings} priced holdings</span>
        </div>
      </div>
      <div className="metric-strip">
        <div className="metric"><span>Copycat value</span><strong>{currency(performance.ending_value)}</strong></div>
        <div className="metric"><span>Total return</span><strong>{percent(performance.total_return)}</strong></div>
        <div className="metric"><span>Annualized</span><strong>{percent(performance.annualized_return)}</strong></div>
        <div className="metric"><span>{performance.benchmark_symbol} value</span><strong>{currency(performance.benchmark_ending_value)}</strong></div>
        <div className="metric"><span>{performance.benchmark_symbol} return</span><strong>{percent(performance.benchmark_total_return)}</strong></div>
        <div className="metric"><span>Last rebalance</span><strong>{latestPeriod ? formatOptionalDate(latestPeriod.start_date) : "Pending"}</strong></div>
      </div>
      <p className="outcome-note">
        Simulation buys each disclosed long-equity 13F portfolio after the filing date, rebalances at the next filing, and compares it with {performance.benchmark_symbol}. Unresolved tickers and options rows are excluded.
      </p>
      {performance.warnings.length ? <WarningList warnings={performance.warnings} /> : null}
      <div className="table-wrap performance-table-wrap">
        <div className="performance-table">
          <div className="performance-row header">
            <span>Report</span><span>Held</span><span>Portfolio</span><span>Benchmark</span><span>Coverage</span><span>Top disclosed names</span>
          </div>
          {performance.periods.map((period) => (
            <div className="performance-row" key={`${period.report_period}-${period.start_date}`}>
              <span>{period.report_period}</span>
              <span>{period.start_date} to {period.end_date}</span>
              <strong>{percent(period.return_pct)}</strong>
              <span>{percent(period.benchmark_return_pct)}</span>
              <span>{period.priced_holdings_count} / {period.holdings_count}</span>
              <span>{period.top_holdings.map((holding) => holding.symbol ?? holding.issuer_name).join(", ")}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function formatOptionalDate(value?: string | null) {
  if (!value) return "Pending";
  return value.slice(0, 10);
}

function formatOptionalDateTime(value?: string | null) {
  if (!value) return "Pending";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function BacktestSummary({ backtest }: { backtest: BacktestResult }) {
  return (
    <section className="dashboard-panel">
      <div className="panel-header">
        <h2>{backtest.index_symbol} {backtest.year} backtest</h2>
        <div className="inline-actions">
          <span className={backtest.beats_benchmark_after_tax ? "status-pill" : backtest.is_tax_adjusted_profitable ? "reason-pill" : "risk-pill"}>
            {backtest.beats_benchmark_after_tax ? "Beats benchmark" : backtest.is_tax_adjusted_profitable ? "Profitable" : "Not profitable"}
          </span>
          <span className="reason-pill">{modeLabel(backtest.tlh_mode)} TLH</span>
          <span className="reason-pill">{modelLabel(backtest.direct_index_model)}</span>
          <span className="risk-pill">{backtest.coverage_label}</span>
        </div>
      </div>
      <div className="metric-strip">
        <div className="metric"><span>Ending value</span><strong>{currency(backtest.ending_value)}</strong></div>
        <div className="metric"><span>Benchmark</span><strong>{currency(backtest.benchmark_value)}</strong></div>
        <div className="metric"><span>Tax-adjusted value</span><strong>{currency(backtest.tax_adjusted_ending_value)}</strong></div>
        <div className="metric"><span>Buyer profit</span><strong>{currency(backtest.tax_adjusted_profit)}</strong></div>
        <div className="metric"><span>Tax-adjusted alpha</span><strong>{currency(backtest.tax_adjusted_excess_profit)}</strong></div>
        <div className="metric"><span>Tracking diff</span><strong>{percent(backtest.tracking_difference)}</strong></div>
      </div>
      <p className="outcome-note">
        {backtest.profitability_summary} Estimated tax impact is {currency(backtest.estimated_net_tax_impact)} at {percent(backtest.estimated_tax_rate)} using realized gains of {currency(backtest.realized_gains)} and realized losses of {currency(backtest.realized_losses)}.
      </p>
    </section>
  );
}

function TradeList({ title, trades }: { title: string; trades: Trade[] }) {
  return (
    <section className="dashboard-panel">
      <div className="table-header" style={{ marginBottom: 14 }}>
        <h2>{title}</h2>
        <span className="reason-pill">{trades.length} rows</span>
      </div>
      <TradeTable trades={trades} />
    </section>
  );
}

function ModelCards({ models, recommendedModel }: { models: DirectIndexModel[]; recommendedModel?: string | null }) {
  return (
    <section className="model-grid">
      {models.map((model) => (
        <article className="dashboard-panel model-card" key={model.id}>
          <div className="panel-header">
            <h2>{model.rank}. {model.label}</h2>
            <span className={model.id === recommendedModel ? "status-pill" : model.executable ? "reason-pill" : "risk-pill"}>{model.id === recommendedModel ? "Current default" : model.executable ? "Executable" : "Research only"}</span>
          </div>
          <p>{model.summary}</p>
          <p className="fine-print">{model.best_for}</p>
          <div className="inline-actions">
            {model.source_support.map((source) => <span className="reason-pill" key={`${model.id}-${source}`}>{source}</span>)}
          </div>
        </article>
      ))}
    </section>
  );
}

function ModelComparisonTable({ comparison }: { comparison: ModelComparison | null }) {
  const rows = comparison?.rows ?? [];
  if (!rows.length) {
    return (
      <section className="dashboard-panel">
        <p className="fine-print">Run the XLG model test to compare 2023, 2024, and 2025 results.</p>
      </section>
    );
  }
  return (
    <section className="dashboard-panel">
      <div className="table-header" style={{ marginBottom: 14 }}>
        <h2>{comparison?.index_symbol ?? "XLG"} model comparison</h2>
        <span className="reason-pill">{rows.length} runs</span>
      </div>
      <div className="table-wrap">
        <div className="comparison-table">
          <div className="comparison-row header">
            <span>Model</span><span>Year</span><span>Coverage</span><span>Harvested</span><span>Tracking</span><span>Trades</span><span>Tax profit</span>
          </div>
          {rows.map((row) => (
            <div className={row.direct_index_model === comparison?.recommended_model ? "comparison-row recommended" : "comparison-row"} key={`${row.direct_index_model}-${row.year}`}>
              <strong>{row.model_label}</strong>
              <span>{row.year}</span>
              <span className={row.available ? "status-pill" : "risk-pill"}>{row.coverage_label}</span>
              <span>{currency(row.harvested_losses)}</span>
              <span>{percent(row.tracking_difference)}</span>
              <span>{row.trade_count} / cap {row.cap_used}</span>
              <span>{currency(row.tax_adjusted_profit)}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function TradeTable({ trades }: { trades: Trade[] }) {
  if (!trades.length) {
    return <p className="fine-print">No trades generated yet.</p>;
  }
  return (
    <div className="table-wrap">
      <div className="trade-table">
        <div className="trade-row header">
          <span>Date</span><span>Action</span><span>Symbol</span><span>Reason</span><span>Notional</span><span>Harvested</span><span>Wash sale</span>
        </div>
        {trades.map((trade, index) => (
          <div className="trade-row" key={`${trade.trade_date}-${trade.symbol}-${trade.action}-${index}`}>
            <span>{trade.trade_date}</span>
            <span className={trade.action === "BUY" ? "buy" : "sell"}>{trade.action}</span>
            <strong>{trade.symbol}</strong>
            <span>{trade.reason.replaceAll("_", " ")}</span>
            <span>{currency(trade.notional)}</span>
            <span>{currency(trade.harvested_loss ?? 0)}</span>
            <span>{trade.wash_sale_status}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
