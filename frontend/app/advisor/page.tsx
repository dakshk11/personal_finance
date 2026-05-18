"use client";

import { CheckCircle2, Download, FileText, Play, ShieldCheck, Upload, Users } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import {
  AccountImportPayload,
  AdvisorClient,
  ClientConstraintPayload,
  ImportedAccount,
  TransitionPlan,
  apiFetch,
  apiUrl,
  currency,
  percent
} from "@/lib/api";

const sampleRows = `AAPL,Apple Inc,Information Technology,120,180,90,2021-01-04
MSFT,Microsoft Corp,Information Technology,60,420,460,2024-08-01
TSLA,Tesla Inc,Consumer Discretionary,80,150,260,2025-01-02
JPM,JPMorgan Chase,Financials,75,210,170,2022-03-15
XOM,Exxon Mobil,Energy,95,115,130,2023-09-20`;

type Objective = "transition_gradually" | "minimize_gains" | "harvest_losses";

export default function AdvisorPage() {
  const router = useRouter();
  const [clients, setClients] = useState<AdvisorClient[]>([]);
  const [clientName, setClientName] = useState("Legacy Equity Client");
  const [clientEmail, setClientEmail] = useState("client@example.com");
  const [householdNotes, setHouseholdNotes] = useState("Outside accounts need advisor confirmation before implementation.");
  const [csvRows, setCsvRows] = useState(sampleRows);
  const [targetIndex, setTargetIndex] = useState("XLG");
  const [annualGainsBudget, setAnnualGainsBudget] = useState(1000);
  const [maxTrackingError, setMaxTrackingError] = useState(4);
  const [maxActiveShare, setMaxActiveShare] = useState(12);
  const [estimatedTaxRate, setEstimatedTaxRate] = useState(35);
  const [excludedSymbols, setExcludedSymbols] = useState("TSLA");
  const [excludedSectors, setExcludedSectors] = useState("");
  const [outsideAccountsComplete, setOutsideAccountsComplete] = useState(false);
  const [disclaimerAccepted, setDisclaimerAccepted] = useState(false);
  const [objective, setObjective] = useState<Objective>("transition_gradually");
  const [account, setAccount] = useState<ImportedAccount | null>(null);
  const [plan, setPlan] = useState<TransitionPlan | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState("");

  useEffect(() => {
    void bootstrap();
  }, []);

  async function bootstrap() {
    try {
      await apiFetch("/auth/me");
      const rows = await apiFetch<AdvisorClient[]>("/advisor/clients");
      setClients(rows);
    } catch {
      router.push("/login");
    }
  }

  const parsed = useMemo(() => parseRows(csvRows), [csvRows]);
  const exportUrl = plan ? `${apiUrl()}/transition-plans/${plan.id}/export.csv` : "";

  async function generateProposal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading("proposal");
    try {
      if (!parsed.holdings.length || !parsed.tax_lots.length) {
        throw new Error("Add at least one valid holding row with symbol, shares, price, cost basis, and acquisition date.");
      }
      if (!disclaimerAccepted) {
        throw new Error("Acknowledge the legal disclaimer before generating a proposal.");
      }
      const client = await apiFetch<AdvisorClient>("/advisor/clients", {
        method: "POST",
        body: JSON.stringify({ name: clientName, email: clientEmail, household_notes: householdNotes })
      });
      const imported = await apiFetch<ImportedAccount>(`/clients/${client.id}/accounts/import`, {
        method: "POST",
        body: JSON.stringify({
          account_name: "Taxable legacy account",
          account_type: "taxable",
          taxable: true,
          custodian: "Advisor import",
          holdings: parsed.holdings,
          tax_lots: parsed.tax_lots
        } satisfies AccountImportPayload)
      });
      const constraints: ClientConstraintPayload = {
        target_index: targetIndex,
        annual_gains_budget: annualGainsBudget,
        max_tracking_error: maxTrackingError / 100,
        max_active_share: maxActiveShare / 100,
        estimated_tax_rate: estimatedTaxRate / 100,
        excluded_symbols: splitList(excludedSymbols),
        excluded_sectors: splitList(excludedSectors),
        household_wash_sale_notes: householdNotes,
        outside_accounts_complete: outsideAccountsComplete,
        equivalent_groups: [{ name: "Alphabet share classes", symbols: ["GOOG", "GOOGL"] }]
      };
      await apiFetch(`/clients/${client.id}/constraints`, { method: "POST", body: JSON.stringify(constraints) });
      const created = await apiFetch<TransitionPlan>(`/clients/${client.id}/transition-plans`, {
        method: "POST",
        body: JSON.stringify({ account_id: imported.id, objective, title: `${client.name} transition proposal` })
      });
      setClients((current) => [client, ...current]);
      setAccount(imported);
      setPlan(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate proposal");
    } finally {
      setLoading("");
    }
  }

  async function approvePlan() {
    if (!plan) return;
    setLoading("approve");
    setError("");
    try {
      const approved = await apiFetch<TransitionPlan>(`/transition-plans/${plan.id}/approve`, { method: "POST" });
      setPlan(approved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not approve proposal");
    } finally {
      setLoading("");
    }
  }

  return (
    <main className="dashboard-shell">
      <header className="dashboard-header">
        <div>
          <Link href="/" className="brand"><span className="brand-mark">D</span><span>DirectIndex</span></Link>
          <h1>Advisor planning workspace</h1>
        </div>
        <div className="dashboard-actions">
          <Link className="ghost-button" href="/research">Research</Link>
          <Link className="ghost-button" href="/ideas">Ideas</Link>
          <Link className="ghost-button" href="/retirement-analyzer">Retirement analyzer</Link>
          <Link className="secondary-button" href="/dashboard">Portfolio dashboard</Link>
        </div>
      </header>

      <div className="dashboard-disclaimer">
        <LegalDisclaimer compact />
      </div>

      <div className="advisor-layout">
        <aside className="advisor-sidebar">
          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Proposal inputs</h2>
              <Users size={18} />
            </div>
            <form className="form-stack" onSubmit={generateProposal}>
              <div className="field">
                <label htmlFor="client-name">Client</label>
                <input id="client-name" value={clientName} onChange={(event) => setClientName(event.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="client-email">Email</label>
                <input id="client-email" type="email" value={clientEmail} onChange={(event) => setClientEmail(event.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="target-index">Target index</label>
                <select id="target-index" value={targetIndex} onChange={(event) => setTargetIndex(event.target.value)}>
                  <option value="XLG">XLG · S&P 500 Top 50</option>
                  <option value="SPY">SPY · S&P 500</option>
                  <option value="TOPT">TOPT · Top 20 US Stocks</option>
                  <option value="QTOP">QTOP · Nasdaq Top 30</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="objective">Optimization mode</label>
                <select id="objective" value={objective} onChange={(event) => setObjective(event.target.value as Objective)}>
                  <option value="transition_gradually">Transition gradually</option>
                  <option value="minimize_gains">Minimize gains</option>
                  <option value="harvest_losses">Harvest losses</option>
                </select>
              </div>
              <div className="advisor-control-grid">
                <label className="inline-field" htmlFor="gains-budget"><span>Gain budget</span><input id="gains-budget" type="number" min="0" step="250" value={annualGainsBudget} onChange={(event) => setAnnualGainsBudget(Number(event.target.value))} /></label>
                <label className="inline-field" htmlFor="tax-rate-advisor"><span>Tax rate</span><input id="tax-rate-advisor" type="number" min="0" max="60" value={estimatedTaxRate} onChange={(event) => setEstimatedTaxRate(Number(event.target.value))} /></label>
                <label className="inline-field" htmlFor="tracking-budget"><span>Track max %</span><input id="tracking-budget" type="number" min="0" max="100" value={maxTrackingError} onChange={(event) => setMaxTrackingError(Number(event.target.value))} /></label>
                <label className="inline-field" htmlFor="active-budget"><span>Active max %</span><input id="active-budget" type="number" min="0" max="100" value={maxActiveShare} onChange={(event) => setMaxActiveShare(Number(event.target.value))} /></label>
              </div>
              <div className="field">
                <label htmlFor="excluded-symbols">Excluded tickers</label>
                <input id="excluded-symbols" value={excludedSymbols} onChange={(event) => setExcludedSymbols(event.target.value.toUpperCase())} placeholder="TSLA, XOM" />
              </div>
              <div className="field">
                <label htmlFor="excluded-sectors">Excluded sectors</label>
                <input id="excluded-sectors" value={excludedSectors} onChange={(event) => setExcludedSectors(event.target.value)} placeholder="Energy" />
              </div>
              <label className="check-row">
                <input type="checkbox" checked={outsideAccountsComplete} onChange={(event) => setOutsideAccountsComplete(event.target.checked)} />
                <span>Outside accounts confirmed for wash-sale review</span>
              </label>
              <label className="check-row compliance-check">
                <input type="checkbox" checked={disclaimerAccepted} onChange={(event) => setDisclaimerAccepted(event.target.checked)} required />
                <span>I understand DirectIndex is not providing tax, legal, accounting, investment, fiduciary, brokerage, or trading advice, and I will not act on any output without qualified professional review.</span>
              </label>
              <div className="field">
                <label htmlFor="notes">Household wash-sale notes</label>
                <textarea id="notes" value={householdNotes} onChange={(event) => setHouseholdNotes(event.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="holdings">Holdings and tax lots CSV</label>
                <textarea id="holdings" className="csv-input" value={csvRows} onChange={(event) => setCsvRows(event.target.value)} />
              </div>
              {error ? <div className="error">{error}</div> : null}
              <button className="primary-button" type="submit" disabled={loading === "proposal" || !disclaimerAccepted}><Play size={16} /> {loading === "proposal" ? "Generating" : "Generate advisor proposal"}</button>
            </form>
          </section>

          <section className="dashboard-panel">
            <div className="panel-header">
              <h2>Advisor clients</h2>
              <ShieldCheck size={18} />
            </div>
            {clients.length ? (
              <div className="client-list">
                {clients.slice(0, 5).map((client) => <span key={client.id}>{client.name}</span>)}
              </div>
            ) : <p className="fine-print">No clients yet. Generate a proposal to create the first workspace.</p>}
          </section>
        </aside>

        <section className="workspace">
          <div className="stat-grid">
            <article className="stat-panel"><FileText size={20} /><h3>Proposal status</h3><strong>{plan?.status ?? "draft"}</strong><p>Advisor-reviewed planning output only.</p></article>
            <article className="stat-panel"><Upload size={20} /><h3>Imported value</h3><strong>{currency(plan?.portfolio_value ?? parsed.totalValue)}</strong><p>{account?.holdings.length ?? parsed.holdings.length} holdings and {account?.tax_lots.length ?? parsed.tax_lots.length} tax lots.</p></article>
            <article className="stat-panel"><ShieldCheck size={20} /><h3>Tax impact</h3><strong>{currency(plan?.estimated_tax_impact ?? 0)}</strong><p>Estimated from realized gains/losses.</p></article>
            <article className="stat-panel"><CheckCircle2 size={20} /><h3>Tracking risk</h3><strong>{plan ? percent(plan.active_share) : "0.00%"}</strong><p>Post-plan active share estimate.</p></article>
          </div>

          {plan ? (
            <>
              <LegalDisclaimer compact />

              <section className="dashboard-panel">
                <div className="panel-header">
                  <h2>Current portfolio</h2>
                  <span className="reason-pill">{account?.name ?? plan.account_name}</span>
                </div>
                <div className="metric-strip">
                  <div className="metric"><span>Client</span><strong>{plan.client_name}</strong></div>
                  <div className="metric"><span>Value</span><strong>{currency(plan.portfolio_value)}</strong></div>
                  <div className="metric"><span>Algorithm</span><strong>{plan.algorithm_version}</strong></div>
                </div>
                <p className="outcome-note">{plan.data_source_summary}</p>
              </section>

              <section className="dashboard-panel">
                <div className="panel-header">
                  <h2>Target index</h2>
                  <span className="status-pill">{plan.target_index}</span>
                </div>
                <div className="metric-strip">
                  <div className="metric"><span>Target value</span><strong>{currency(plan.target_value)}</strong></div>
                  <div className="metric"><span>Turnover</span><strong>{percent(plan.turnover)}</strong></div>
                  <div className="metric"><span>Skipped</span><strong>{plan.skipped_trade_count}</strong></div>
                </div>
              </section>

              <section className="dashboard-panel">
                <div className="table-header" style={{ marginBottom: 14 }}>
                  <h2>Transition plan</h2>
                  <span className="reason-pill">{plan.recommendations.length} recommendations</span>
                </div>
                <div className="table-wrap">
                  <div className="advisor-trade-table">
                    <div className="advisor-trade-row header"><span>Stage</span><span>Action</span><span>Symbol</span><span>Notional</span><span>Gain/loss</span><span>Tax impact</span><span>Reason</span></div>
                    {plan.recommendations.map((row, index) => (
                      <div className="advisor-trade-row" key={`${row.action}-${row.symbol}-${index}`}>
                        <span>{row.stage}</span>
                        <span className={row.action === "BUY" ? "buy" : "sell"}>{row.action}</span>
                        <strong>{row.symbol}</strong>
                        <span>{currency(row.notional)}</span>
                        <span>{currency(row.realized_gain_loss)}</span>
                        <span>{currency(row.estimated_tax_impact)}</span>
                        <span>{row.reason.replaceAll("_", " ")}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </section>

              <section className="proposal-grid">
                <article className="dashboard-panel">
                  <h2>Tax impact</h2>
                  <div className="metric-strip stacked">
                    <div className="metric"><span>Realized gains</span><strong>{currency(plan.realized_gains)}</strong></div>
                    <div className="metric"><span>Realized losses</span><strong>{currency(plan.realized_losses)}</strong></div>
                    <div className="metric"><span>Net realized gain</span><strong>{currency(plan.net_realized_gain)}</strong></div>
                  </div>
                </article>
                <article className="dashboard-panel">
                  <h2>Tracking risk</h2>
                  <div className="metric-strip stacked">
                    <div className="metric"><span>Tracking drift</span><strong>{percent(plan.tracking_drift)}</strong></div>
                    <div className="metric"><span>Active share</span><strong>{percent(plan.active_share)}</strong></div>
                    <div className="metric"><span>Mode</span><strong>{plan.objective.replaceAll("_", " ")}</strong></div>
                  </div>
                </article>
              </section>

              <section className="dashboard-panel">
                <div className="panel-header">
                  <h2>Assumptions and disclosures</h2>
                  <div className="dashboard-actions">
                    <a className="secondary-button" href={exportUrl}><Download size={16} /> Export CSV</a>
                    <button className="primary-button" onClick={approvePlan} disabled={plan.status === "approved" || loading === "approve"}><CheckCircle2 size={16} /> {plan.status === "approved" ? "Approved" : "Approve"}</button>
                  </div>
                </div>
                <WarningList warnings={plan.warnings} />
                <p className="outcome-note">Input snapshot is frozen on approval and includes objective, target index, tax budget, source labels, equivalent-security groups, and algorithm version.</p>
              </section>
            </>
          ) : (
            <section className="dashboard-panel empty-proposal">
              <FileText size={34} />
              <h2>Create an advisor-ready transition proposal</h2>
              <p>Use the sample taxable account or paste rows in the same format: symbol, name, sector, shares, current price, cost basis, acquisition date.</p>
              <span className="risk-pill">Planning only · no brokerage connection · no live orders</span>
            </section>
          )}
        </section>
      </div>
    </main>
  );
}

function splitList(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function parseRows(value: string) {
  const rows = value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.split(",").map((part) => part.trim()));
  const holdings = rows.flatMap((row) => {
    const [symbol, name, sector, shares, price] = row;
    const parsedShares = Number(shares);
    const parsedPrice = Number(price);
    if (!symbol || !Number.isFinite(parsedShares) || !Number.isFinite(parsedPrice) || parsedShares <= 0 || parsedPrice <= 0) return [];
    return [{ symbol: symbol.toUpperCase(), name, sector, shares: parsedShares, price: parsedPrice, market_value: parsedShares * parsedPrice, as_of_date: new Date().toISOString().slice(0, 10) }];
  });
  const tax_lots = rows.flatMap((row) => {
    const [symbol, , , shares, , costBasis, acquisitionDate] = row;
    const parsedShares = Number(shares);
    const parsedBasis = Number(costBasis);
    if (!symbol || !acquisitionDate || !Number.isFinite(parsedShares) || !Number.isFinite(parsedBasis) || parsedShares <= 0 || parsedBasis <= 0) return [];
    return [{ symbol: symbol.toUpperCase(), acquisition_date: acquisitionDate, shares: parsedShares, cost_basis_per_share: parsedBasis }];
  });
  return {
    holdings,
    tax_lots,
    totalValue: holdings.reduce((total, row) => total + (row.market_value ?? 0), 0)
  };
}

function WarningList({ warnings }: { warnings: string[] }) {
  return (
    <ul className="warning-list">
      {warnings.map((warning) => <li key={warning}>{warning}</li>)}
    </ul>
  );
}
