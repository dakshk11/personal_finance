"use client";

import { BarChart3, DownloadCloud, LineChart, Plus, ShieldCheck, Trash2, Upload, WalletCards } from "lucide-react";
import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { PortfolioAnalyzerHoldingInput, PortfolioAnalyzerResult, apiFetch, currency, percent } from "@/lib/api";

type EditableHolding = {
  id: string;
  symbol: string;
  shares: number;
  costBasisPerShare: number;
};

const storageKey = "directindex.portfolioAnalyzer.holdings";
const thresholdStorageKey = "directindex.portfolioAnalyzer.minWeight";
const sampleBulkRows = `AAPL,120,90
MSFT,60,260
JPM,75,170
XOM,95,80`;

const defaultHoldings: EditableHolding[] = [
  { id: "aapl", symbol: "AAPL", shares: 120, costBasisPerShare: 90 },
  { id: "msft", symbol: "MSFT", shares: 60, costBasisPerShare: 260 },
  { id: "jpm", symbol: "JPM", shares: 75, costBasisPerShare: 170 },
  { id: "xom", symbol: "XOM", shares: 95, costBasisPerShare: 80 }
];

export default function PortfolioAnalyzerPage() {
  const [holdings, setHoldings] = useState<EditableHolding[]>(defaultHoldings);
  const [bulkRows, setBulkRows] = useState(sampleBulkRows);
  const [minWeightPercent, setMinWeightPercent] = useState(1);
  const [result, setResult] = useState<PortfolioAnalyzerResult | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    async function bootstrap() {
      try {
        const savedHoldings = window.localStorage.getItem(storageKey);
        const savedThreshold = window.localStorage.getItem(thresholdStorageKey);
        if (savedHoldings) {
          const parsed = JSON.parse(savedHoldings) as EditableHolding[];
          if (Array.isArray(parsed) && parsed.length) setHoldings(parsed);
        }
        if (savedThreshold) setMinWeightPercent(Number(savedThreshold));
      } catch {
        // Local storage is a convenience cache only.
      } finally {
        setLoaded(true);
      }
    }
    void bootstrap();
  }, []);

  useEffect(() => {
    if (!loaded) return;
    window.localStorage.setItem(storageKey, JSON.stringify(holdings));
    window.localStorage.setItem(thresholdStorageKey, String(minWeightPercent));
  }, [holdings, loaded, minWeightPercent]);

  const validHoldings = useMemo<PortfolioAnalyzerHoldingInput[]>(
    () => holdings
      .map((holding) => ({
        symbol: holding.symbol.trim().toUpperCase(),
        shares: Number(holding.shares),
        cost_basis_per_share: Number(holding.costBasisPerShare)
      }))
      .filter((holding) => holding.symbol && holding.shares > 0 && holding.cost_basis_per_share >= 0),
    [holdings]
  );
  const localCostBasis = validHoldings.reduce((total, holding) => total + holding.shares * holding.cost_basis_per_share, 0);

  function updateHolding(id: string, field: keyof Omit<EditableHolding, "id">, value: string) {
    setHoldings((current) => current.map((holding) => {
      if (holding.id !== id) return holding;
      if (field === "symbol") return { ...holding, symbol: value.toUpperCase() };
      return { ...holding, [field]: Number(value) };
    }));
  }

  function addHolding() {
    setHoldings((current) => [...current, { id: crypto.randomUUID(), symbol: "", shares: 0, costBasisPerShare: 0 }]);
  }

  function removeHolding(id: string) {
    setHoldings((current) => current.filter((holding) => holding.id !== id));
  }

  function loadBulkRows() {
    const rows = bulkRows
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line, index) => {
        const [symbol, shares, costBasis] = line.split(",").map((part) => part.trim());
        return {
          id: `${symbol || "row"}-${index}-${Date.now()}`,
          symbol: symbol?.toUpperCase() ?? "",
          shares: Number(shares),
          costBasisPerShare: Number(costBasis)
        };
      })
      .filter((row) => row.symbol && row.shares > 0 && row.costBasisPerShare >= 0);
    if (rows.length) setHoldings(rows);
  }

  async function analyzePortfolio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading("analyze");
    try {
      if (!validHoldings.length) {
        throw new Error("Add at least one holding with ticker, shares, and cost basis.");
      }
      const analyzed = await apiFetch<PortfolioAnalyzerResult>("/portfolio-analysis/analyze", {
        method: "POST",
        body: JSON.stringify({
          holdings: validHoldings,
          min_weight_percent: minWeightPercent
        })
      });
      setResult(analyzed);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not analyze portfolio");
    } finally {
      setLoading("");
    }
  }

  return (
    <main className="dashboard-shell">
      <AppHeader
        title="Portfolio analyzer"
        actions={
          <>
          <Link className="ghost-button" href="/research">Research</Link>
          <Link className="ghost-button" href="/ideas">Ideas</Link>
          <Link className="ghost-button" href="/retirement-analyzer">Plan</Link>
          <Link className="ghost-button" href="/advisor">Advisor</Link>
          <Link className="secondary-button" href="/dashboard">Direct-index dashboard</Link>
          </>
        }
      />

      <div className="dashboard-disclaimer">
        <LegalDisclaimer compact />
      </div>

      <div className="portfolio-analyzer-layout">
        <aside className="portfolio-analyzer-sidebar">
          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Holdings over 1%</h2>
              <WalletCards size={18} />
            </div>
            <form className="form-stack" onSubmit={analyzePortfolio}>
              <div className="holding-editor-list">
                {holdings.map((holding) => (
                  <div className="holding-editor-row" key={holding.id}>
                    <div className="field">
                      <label htmlFor={`${holding.id}-symbol`}>Ticker</label>
                      <input id={`${holding.id}-symbol`} value={holding.symbol} onChange={(event) => updateHolding(holding.id, "symbol", event.target.value)} placeholder="AAPL" />
                    </div>
                    <div className="field">
                      <label htmlFor={`${holding.id}-shares`}>Shares</label>
                      <input id={`${holding.id}-shares`} type="number" min="0" step="0.0001" value={holding.shares} onChange={(event) => updateHolding(holding.id, "shares", event.target.value)} />
                    </div>
                    <div className="field">
                      <label htmlFor={`${holding.id}-basis`}>Cost basis / sh.</label>
                      <input id={`${holding.id}-basis`} type="number" min="0" step="0.01" value={holding.costBasisPerShare} onChange={(event) => updateHolding(holding.id, "costBasisPerShare", event.target.value)} />
                    </div>
                    <button className="ghost-button icon-button" type="button" aria-label={`Remove ${holding.symbol || "holding"}`} onClick={() => removeHolding(holding.id)}>
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
              </div>
              <div className="inline-actions">
                <button className="secondary-button" type="button" onClick={addHolding}><Plus size={16} /> Add holding</button>
                <label className="inline-field" htmlFor="min-weight">
                  <span>Focus %</span>
                  <input id="min-weight" type="number" min="0" max="100" step="0.1" value={minWeightPercent} onChange={(event) => setMinWeightPercent(Number(event.target.value))} />
                </label>
              </div>
              <button className="primary-button" type="submit" disabled={loading === "analyze"}>
                <DownloadCloud size={16} /> {loading === "analyze" ? "Analyzing" : "Analyze portfolio"}
              </button>
            </form>
            <p className="fine-print">
              Enter the positions you care about, especially holdings above 1% of the account. Cost basis is used for unrealized gain/loss review.
            </p>
          </section>

          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Paste rows</h2>
              <Upload size={18} />
            </div>
            <div className="form-stack">
              <div className="field">
                <label htmlFor="bulk-holdings">Ticker, shares, cost basis/share</label>
                <textarea id="bulk-holdings" className="csv-input" value={bulkRows} onChange={(event) => setBulkRows(event.target.value)} />
              </div>
              <button className="secondary-button" type="button" onClick={loadBulkRows}><Upload size={16} /> Load rows</button>
            </div>
          </section>
        </aside>

        <section className="portfolio-analyzer-workspace">
          {error ? <div className="error">{error}</div> : null}

          <div className="stat-grid portfolio-stat-grid">
            <article className="stat-panel"><WalletCards size={20} /><h3>Entered holdings</h3><strong>{validHoldings.length}</strong><p>{currency(localCostBasis)} entered cost basis.</p></article>
            <article className="stat-panel"><BarChart3 size={20} /><h3>Market value</h3><strong>{result ? currency(result.total_market_value) : "Pending"}</strong><p>Daily price cache by symbol.</p></article>
            <article className="stat-panel"><LineChart size={20} /><h3>Unrealized G/L</h3><strong>{result ? currency(result.unrealized_gain_loss) : "Pending"}</strong><p>{result ? percent(result.unrealized_gain_loss_pct) : "Run analysis"} total.</p></article>
            <article className="stat-panel"><ShieldCheck size={20} /><h3>Focus table</h3><strong>{result ? result.analyzed_holding_count : 0}</strong><p>{result ? `${result.hidden_holding_count} below threshold` : "Holdings at/above threshold."}</p></article>
          </div>

          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Valuation dashboard</h2>
              <div className="inline-actions">
                <span className="reason-pill">Fwd P/E</span>
                <span className="valuation-legend ten-year">Below 10Y avg</span>
                <span className="valuation-legend five-year">Below 5Y avg</span>
              </div>
            </div>
            {result ? (
              <>
                <div className="table-wrap">
                  <div className="portfolio-valuation-table">
                    <div className="portfolio-valuation-row header">
                      <span>Ticker</span><span>Weight</span><span>Shares</span><span>Price</span><span>Value</span><span>Basis/sh.</span><span>Cost basis</span><span>Gain/Loss</span><span>Fwd P/E</span><span>5Y avg</span><span>10Y avg</span><span>Signal</span><span>Source</span>
                    </div>
                    {result.holdings.map((holding) => (
                      <div className={`portfolio-valuation-row ${signalClass(holding.valuation_signal)}`} key={holding.symbol}>
                        <strong>{holding.symbol}</strong>
                        <span>{percent(holding.weight)}</span>
                        <span>{formatShares(holding.shares)}</span>
                        <span>{currencyCents(holding.price)}</span>
                        <strong>{currency(holding.market_value)}</strong>
                        <span>{currencyCents(holding.cost_basis_per_share)}</span>
                        <span>{currency(holding.cost_basis)}</span>
                        <span className={holding.unrealized_gain_loss >= 0 ? "positive-money" : "negative-money"}>{currency(holding.unrealized_gain_loss)} / {percent(holding.unrealized_gain_loss_pct)}</span>
                        <span>{formatPe(holding.forward_pe)}</span>
                        <span>{formatPe(holding.forward_pe_5y_avg)}</span>
                        <span>{formatPe(holding.forward_pe_10y_avg)}</span>
                        <span className={`valuation-chip ${signalClass(holding.valuation_signal)}`}>{holding.valuation_signal_label}</span>
                        <span className={holding.data_source.includes("fallback") ? "source-chip fallback" : "source-chip"}>{formatDataSource(holding.data_source)}</span>
                      </div>
                    ))}
                  </div>
                </div>
                {result.warnings.length ? <WarningList warnings={result.warnings} /> : null}
                <p className="outcome-note">
                  As of {result.as_of_date}. Rows below {result.min_weight_percent}% are hidden from the focus table, but still count toward total portfolio value. Forward P/E averages use the daily local valuation cache and fall back to estimates when provider history is unavailable.
                </p>
              </>
            ) : (
              <p className="fine-print">Run analysis to download/cache daily market data and compare each stock’s forward P/E with its 5-year and 10-year averages.</p>
            )}
          </section>
        </section>
      </div>
    </main>
  );
}

function WarningList({ warnings }: { warnings: string[] }) {
  return (
    <ul className="warning-list">
      {warnings.map((warning) => <li key={warning}>{warning}</li>)}
    </ul>
  );
}

function signalClass(signal: PortfolioAnalyzerResult["holdings"][number]["valuation_signal"]) {
  if (signal === "below_10y_average") return "below-10y";
  if (signal === "below_5y_average") return "below-5y";
  if (signal === "unknown") return "unknown";
  return "neutral";
}

function formatPe(value?: number | null) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(1) : "N/A";
}

function currencyCents(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function formatShares(value: number) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 }).format(value);
}

function formatDataSource(value: string) {
  if (value.includes("stooq") && value.includes("deterministic")) return "Stooq close / fallback P/E";
  if (value.includes("yfinance") && value.includes("deterministic")) return "Yahoo price / fallback P/E";
  if (value.includes("stooq")) return "Stooq close cache";
  if (value.includes("yfinance")) return "Yahoo cache";
  if (value.includes("deterministic")) return "Fallback cache";
  return "Cached";
}
