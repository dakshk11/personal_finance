"use client";

import {
  AlertTriangle,
  Building2,
  CircleDollarSign,
  DatabaseZap,
  ExternalLink,
  Gauge,
  KeyRound,
  Loader2,
  PieChart,
  RefreshCw,
  Save,
  ShieldCheck,
  Trash2,
  WalletCards
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  PortfolioSyncConnect,
  PortfolioSyncHolding,
  PortfolioSyncProviderCredentialPayload,
  PortfolioSyncProviderCredentialStatus,
  PortfolioSyncStatus,
  PortfolioSyncSummary,
  apiFetch,
  currency,
  percent
} from "@/lib/api";

export function PortfolioSyncTool() {
  const [status, setStatus] = useState<PortfolioSyncStatus | null>(null);
  const [summary, setSummary] = useState<PortfolioSyncSummary | null>(null);
  const [providerCredential, setProviderCredential] = useState<PortfolioSyncProviderCredentialStatus | null>(null);
  const [snaptradeClientId, setSnaptradeClientId] = useState("");
  const [snaptradeConsumerKey, setSnaptradeConsumerKey] = useState("");
  const [credentialMessage, setCredentialMessage] = useState("");
  const [loading, setLoading] = useState("initial");
  const [error, setError] = useState("");

  const effectiveStatus = summary?.status ?? status;
  const configured = Boolean(effectiveStatus?.configured);
  const connected = Boolean(effectiveStatus?.connected);
  const hasSnapshot = Boolean(summary?.synced_at && summary.holdings.length);
  const warnings = useMemo(() => {
    const values = [...(summary?.warnings ?? []), ...(effectiveStatus?.warnings ?? [])];
    return Array.from(new Set(values)).slice(0, 8);
  }, [effectiveStatus?.warnings, summary?.warnings]);

  useEffect(() => {
    void loadPortfolioSync();
  }, []);

  async function loadPortfolioSync() {
    setLoading("initial");
    setError("");
    try {
      const [nextProviderCredential, nextStatus, nextSummary] = await Promise.all([
        apiFetch<PortfolioSyncProviderCredentialStatus>("/portfolio-sync/provider-credentials"),
        apiFetch<PortfolioSyncStatus>("/portfolio-sync/status"),
        apiFetch<PortfolioSyncSummary>("/portfolio-sync/summary")
      ]);
      setProviderCredential(nextProviderCredential);
      setSnaptradeClientId(nextProviderCredential.client_id ?? "");
      setStatus(nextSummary.status ?? nextStatus);
      setSummary(nextSummary);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load portfolio sync.");
    } finally {
      setLoading("");
    }
  }

  async function saveProviderCredentials(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    setLoading("credentials");
    setError("");
    setCredentialMessage("");
    try {
      const payload: PortfolioSyncProviderCredentialPayload = {
        client_id: snaptradeClientId.trim(),
        consumer_key: snaptradeConsumerKey.trim()
      };
      const saved = await apiFetch<PortfolioSyncProviderCredentialStatus>("/portfolio-sync/provider-credentials", {
        method: "PUT",
        body: JSON.stringify(payload)
      });
      const [nextStatus, nextSummary] = await Promise.all([
        apiFetch<PortfolioSyncStatus>("/portfolio-sync/status"),
        apiFetch<PortfolioSyncSummary>("/portfolio-sync/summary")
      ]);
      setProviderCredential(saved);
      setSnaptradeClientId(saved.client_id ?? payload.client_id);
      setSnaptradeConsumerKey("");
      setStatus(nextSummary.status ?? nextStatus);
      setSummary(nextSummary);
      setCredentialMessage("SnapTrade credentials saved encrypted in the backend. Connect brokerage when ready.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save SnapTrade credentials.");
    } finally {
      setLoading("");
    }
  }

  async function removeProviderCredentials() {
    setLoading("credentials");
    setError("");
    setCredentialMessage("");
    try {
      const removed = await apiFetch<PortfolioSyncProviderCredentialStatus>("/portfolio-sync/provider-credentials", { method: "DELETE" });
      const [nextStatus, nextSummary] = await Promise.all([
        apiFetch<PortfolioSyncStatus>("/portfolio-sync/status"),
        apiFetch<PortfolioSyncSummary>("/portfolio-sync/summary")
      ]);
      setProviderCredential(removed);
      setSnaptradeClientId(removed.client_id ?? "");
      setSnaptradeConsumerKey("");
      setStatus(nextSummary.status ?? nextStatus);
      setSummary(nextSummary);
      setCredentialMessage(removed.configured ? "Stored credentials removed; backend environment credentials are active." : "Stored SnapTrade credentials removed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove stored SnapTrade credentials.");
    } finally {
      setLoading("");
    }
  }

  async function connectBrokerage() {
    setLoading("connect");
    setError("");
    try {
      const connection = await apiFetch<PortfolioSyncConnect>("/portfolio-sync/connect", { method: "POST" });
      if (connection.redirect_url) {
        window.location.assign(connection.redirect_url);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start brokerage connection.");
    } finally {
      setLoading("");
    }
  }

  async function syncNow() {
    setLoading("sync");
    setError("");
    try {
      const nextSummary = await apiFetch<PortfolioSyncSummary>("/portfolio-sync/sync", { method: "POST" });
      setSummary(nextSummary);
      setStatus(nextSummary.status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sync brokerage holdings.");
    } finally {
      setLoading("");
    }
  }

  return (
    <>
      <section className="dashboard-panel portfolio-sync-head">
        <div>
          <p className="eyebrow">Portfolio Sync</p>
          <h2>Read-only brokerage sync with exposure, cost basis, and concentration review.</h2>
          <div className="portfolio-sync-meta-line">
            <span><ShieldCheck size={14} /> Read-only</span>
            <span><DatabaseZap size={14} /> SnapTrade</span>
            <span><Gauge size={14} /> Portfolio analyzer pricing</span>
          </div>
        </div>
        <div className="portfolio-sync-actions">
          <span className={configured ? "status-pill" : "risk-pill"}>{configured ? "Provider configured" : "Setup required"}</span>
          <button className="ghost-button" type="button" onClick={loadPortfolioSync} disabled={Boolean(loading)}>
            {loading === "initial" ? <Loader2 size={16} className="spin-icon" /> : <RefreshCw size={16} />}
            Refresh
          </button>
          {configured && !connected && (
            <button className="primary-button" type="button" onClick={connectBrokerage} disabled={loading === "connect"}>
              {loading === "connect" ? <Loader2 size={16} className="spin-icon" /> : <ExternalLink size={16} />}
              Connect brokerage
            </button>
          )}
          {configured && connected && (
            <button className="primary-button" type="button" onClick={syncNow} disabled={loading === "sync"}>
              {loading === "sync" ? <Loader2 size={16} className="spin-icon" /> : <RefreshCw size={16} />}
              Sync now
            </button>
          )}
        </div>
      </section>

      {error && <div className="error">{error}</div>}

      {!configured ? (
        <SetupRequired
          warnings={warnings}
          providerCredential={providerCredential}
          clientId={snaptradeClientId}
          consumerKey={snaptradeConsumerKey}
          loading={loading === "credentials"}
          message={credentialMessage}
          onClientIdChange={setSnaptradeClientId}
          onConsumerKeyChange={setSnaptradeConsumerKey}
          onSave={saveProviderCredentials}
        />
      ) : !connected ? (
        <NotConnected
          onConnect={connectBrokerage}
          loading={loading === "connect"}
          providerCredential={providerCredential}
          clientId={snaptradeClientId}
          consumerKey={snaptradeConsumerKey}
          credentialLoading={loading === "credentials"}
          credentialMessage={credentialMessage}
          onClientIdChange={setSnaptradeClientId}
          onConsumerKeyChange={setSnaptradeConsumerKey}
          onSave={saveProviderCredentials}
          onRemove={removeProviderCredentials}
        />
      ) : !hasSnapshot ? (
        <ReadyToSync onSync={syncNow} loading={loading === "sync"} status={effectiveStatus} />
      ) : summary ? (
        <SyncedPortfolio summary={summary} warnings={warnings} />
      ) : (
        <section className="dashboard-panel empty-proposal portfolio-sync-empty">
          <Loader2 size={28} className="spin-icon" />
          <h2>Loading portfolio sync</h2>
          <p>Preparing the latest read-only brokerage snapshot.</p>
        </section>
      )}
    </>
  );
}

type CredentialFormProps = {
  providerCredential?: PortfolioSyncProviderCredentialStatus | null;
  clientId: string;
  consumerKey: string;
  loading: boolean;
  message?: string;
  onClientIdChange: (value: string) => void;
  onConsumerKeyChange: (value: string) => void;
  onSave: (event?: FormEvent<HTMLFormElement>) => void;
  onRemove?: () => void;
};

function SetupRequired({
  warnings,
  providerCredential,
  clientId,
  consumerKey,
  loading,
  message,
  onClientIdChange,
  onConsumerKeyChange,
  onSave
}: CredentialFormProps & { warnings: string[] }) {
  return (
    <section className="dashboard-panel portfolio-sync-setup">
      <div>
        <AlertTriangle size={24} />
        <h2>SnapTrade credentials are not configured.</h2>
        <p>Paste your SnapTrade app client id and consumer key here. FinanceOS stores the consumer key encrypted in the backend database and never returns the plaintext value to the browser.</p>
      </div>
      <CredentialForm
        providerCredential={providerCredential}
        clientId={clientId}
        consumerKey={consumerKey}
        loading={loading}
        message={message}
        onClientIdChange={onClientIdChange}
        onConsumerKeyChange={onConsumerKeyChange}
        onSave={onSave}
      />
      <div className="portfolio-sync-credential-grid">
        <article>
          <strong>SnapTrade client id</strong>
          <code>Entered in browser</code>
          <span>Public app identifier from the SnapTrade dashboard.</span>
        </article>
        <article>
          <strong>SnapTrade consumer key</strong>
          <code>Encrypted in backend</code>
          <span>Secret app key. Plaintext is used only for the save request.</span>
        </article>
        <article>
          <strong>Local encryption secret</strong>
          <code>BROKER_SYNC_ENCRYPTION_SECRET</code>
          <span>Backend secret used to encrypt SnapTrade provider and user secrets.</span>
        </article>
      </div>
      <div className="portfolio-sync-env-snippet" aria-label="Portfolio Sync environment snippet">
        <span>Hosted deployments can still use backend env vars instead of browser setup.</span>
        <code>SNAPTRADE_CLIENT_ID</code>
        <code>SNAPTRADE_CONSUMER_KEY</code>
        <code>BROKER_SYNC_ENCRYPTION_SECRET</code>
      </div>
      {warnings.length > 0 && (
        <div className="portfolio-sync-warning-list compact">
          {warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </div>
      )}
      <div className="portfolio-sync-setup-actions">
        <a href="https://docs.snaptrade.com/" target="_blank" rel="noreferrer" className="ghost-button">Open SnapTrade docs</a>
        <Link href="/portfolio" className="secondary-button">Open manual Portfolio Analyzer</Link>
      </div>
    </section>
  );
}

function CredentialForm({
  providerCredential,
  clientId,
  consumerKey,
  loading,
  message,
  onClientIdChange,
  onConsumerKeyChange,
  onSave,
  onRemove
}: CredentialFormProps) {
  const storedInBackend = providerCredential?.source === "database";
  return (
    <form className="portfolio-sync-credential-form" onSubmit={onSave}>
      <div className="portfolio-sync-credential-status">
        <span><KeyRound size={15} /> {providerCredential?.configured ? `Provider source: ${providerCredential.source}` : "Provider source: not configured"}</span>
        {providerCredential?.consumer_key_fingerprint && <code>{providerCredential.consumer_key_fingerprint}</code>}
      </div>
      <div className="portfolio-sync-credential-fields">
        <label>
          <span>SnapTrade client id</span>
          <input
            value={clientId}
            onChange={(event) => onClientIdChange(event.target.value)}
            placeholder="Enter SnapTrade client id"
            autoComplete="off"
          />
        </label>
        <label>
          <span>SnapTrade consumer key</span>
          <input
            value={consumerKey}
            onChange={(event) => onConsumerKeyChange(event.target.value)}
            placeholder={storedInBackend ? "Enter a new key to replace the stored key" : "Enter SnapTrade consumer key"}
            type="password"
            autoComplete="off"
          />
        </label>
      </div>
      <div className="portfolio-sync-credential-actions">
        <button className="primary-button" type="submit" disabled={loading || !clientId.trim() || !consumerKey.trim()}>
          {loading ? <Loader2 size={16} className="spin-icon" /> : <Save size={16} />}
          Save SnapTrade credentials
        </button>
        {storedInBackend && onRemove && (
          <button className="ghost-button" type="button" onClick={onRemove} disabled={loading}>
            <Trash2 size={16} />
            Remove stored credentials
          </button>
        )}
        {providerCredential?.updated_at && <span>Updated {formatDateTime(providerCredential.updated_at)}</span>}
      </div>
      {message && <p className="portfolio-sync-credential-message">{message}</p>}
    </form>
  );
}

function NotConnected({
  onConnect,
  loading,
  providerCredential,
  clientId,
  consumerKey,
  credentialLoading,
  credentialMessage,
  onClientIdChange,
  onConsumerKeyChange,
  onSave,
  onRemove
}: {
  onConnect: () => void;
  loading: boolean;
  providerCredential?: PortfolioSyncProviderCredentialStatus | null;
  clientId: string;
  consumerKey: string;
  credentialLoading: boolean;
  credentialMessage?: string;
  onClientIdChange: (value: string) => void;
  onConsumerKeyChange: (value: string) => void;
  onSave: (event?: FormEvent<HTMLFormElement>) => void;
  onRemove: () => void;
}) {
  return (
    <>
      <section className="dashboard-panel portfolio-sync-connect">
        <div>
          <WalletCards size={30} />
          <h2>No brokerage connection yet.</h2>
          <p>Start a SnapTrade redirect to connect accounts read-only, then return here to sync holdings.</p>
        </div>
        <button className="primary-button" type="button" onClick={onConnect} disabled={loading}>
          {loading ? <Loader2 size={16} className="spin-icon" /> : <ExternalLink size={16} />}
          Connect brokerage
        </button>
      </section>
      <section className="dashboard-panel portfolio-sync-provider-panel">
        <div className="panel-header">
          <div>
            <h2>SnapTrade app credentials</h2>
            <p className="fine-print">Update local provider credentials here; saving clears the old SnapTrade user secret so the next connection uses the new app keys.</p>
          </div>
          <KeyRound size={18} />
        </div>
        <CredentialForm
          providerCredential={providerCredential}
          clientId={clientId}
          consumerKey={consumerKey}
          loading={credentialLoading}
          message={credentialMessage}
          onClientIdChange={onClientIdChange}
          onConsumerKeyChange={onConsumerKeyChange}
          onSave={onSave}
          onRemove={onRemove}
        />
      </section>
    </>
  );
}

function ReadyToSync({ onSync, loading, status }: { onSync: () => void; loading: boolean; status?: PortfolioSyncStatus | null }) {
  return (
    <section className="dashboard-panel portfolio-sync-connect">
      <div>
        <DatabaseZap size={30} />
        <h2>Brokerage connected. Run the first holdings sync.</h2>
        <p>{status?.account_count ? `${status.account_count} account${status.account_count === 1 ? "" : "s"} ready for refresh.` : "SnapTrade connection is registered and ready for holdings refresh."}</p>
      </div>
      <button className="primary-button" type="button" onClick={onSync} disabled={loading}>
        {loading ? <Loader2 size={16} className="spin-icon" /> : <RefreshCw size={16} />}
        Sync now
      </button>
    </section>
  );
}

function SyncedPortfolio({ summary, warnings }: { summary: PortfolioSyncSummary; warnings: string[] }) {
  return (
    <>
      <section className="portfolio-sync-stat-grid stat-grid">
        <Stat label="Market value" value={currency(summary.total_market_value)} tone="strong" />
        <Stat label="Cost basis" value={currency(summary.total_cost_basis)} />
        <Stat label="Unrealized P/L" value={signedCurrency(summary.unrealized_gain_loss)} tone={summary.unrealized_gain_loss >= 0 ? "positive" : "negative"} />
        <Stat label="Return" value={percent(summary.unrealized_gain_loss_pct)} tone={summary.unrealized_gain_loss >= 0 ? "positive" : "negative"} />
        <Stat label="Accounts" value={String(summary.account_count)} />
        <Stat label="Holdings" value={String(summary.holding_count)} />
      </section>

      <section className="dashboard-panel portfolio-sync-account-panel">
        <div className="panel-header">
          <h2>Connected accounts</h2>
          <Building2 size={18} />
        </div>
        <div className="portfolio-sync-account-grid">
          {summary.accounts.map((account) => (
            <article className="portfolio-sync-account-card" key={account.account_id}>
              <span>{account.brokerage_name}</span>
              <strong>{account.account_name}</strong>
              <small>{account.account_type || account.status || "Synced account"}</small>
            </article>
          ))}
        </div>
      </section>

      <div className="portfolio-sync-dashboard-grid">
        <section className="dashboard-panel portfolio-sync-sector-panel">
          <div className="panel-header">
            <h2>Sector mix</h2>
            <PieChart size={18} />
          </div>
          <div className="portfolio-sync-sector-list">
            {summary.sector_exposures.slice(0, 8).map((sector) => (
              <div className="portfolio-sync-sector-row" key={sector.sector}>
                <span>{sector.sector}</span>
                <div aria-hidden="true"><i style={{ width: `${Math.min(100, sector.weight * 100)}%` }} /></div>
                <strong>{percent(sector.weight)}</strong>
              </div>
            ))}
          </div>
        </section>

        <section className="dashboard-panel portfolio-sync-holdings-panel">
          <div className="panel-header">
            <h2>Top holdings P/L</h2>
            <CircleDollarSign size={18} />
          </div>
          <div className="portfolio-sync-top-list">
            {summary.top_holdings.slice(0, 6).map((holding) => (
              <HoldingPill holding={holding} key={`${holding.account_id}-${holding.symbol}`} />
            ))}
          </div>
        </section>
      </div>

      {warnings.length > 0 && <WarningList warnings={warnings} />}

      <section className="dashboard-panel portfolio-sync-table-panel">
        <div className="panel-header">
          <div>
            <h2>Synced holdings</h2>
            <p className="fine-print">Last sync {formatDateTime(summary.synced_at)}</p>
          </div>
          <span className="status-pill">Read-only snapshot</span>
        </div>
        <div className="portfolio-sync-table">
          <div className="portfolio-sync-row portfolio-sync-row-header">
            <span>Symbol</span>
            <span>Broker / account</span>
            <span>Shares</span>
            <span>Price</span>
            <span>Value</span>
            <span>Weight</span>
            <span>Basis</span>
            <span>P/L</span>
            <span>Source</span>
          </div>
          {summary.holdings.map((holding) => (
            <div className="portfolio-sync-row" key={`${holding.account_id}-${holding.symbol}-${holding.shares}`}>
              <strong>{holding.symbol}<small>{holding.sector || "Unknown"}</small></strong>
              <span>{holding.brokerage_name}<small>{holding.account_name}</small></span>
              <span>{formatShares(holding.shares)}</span>
              <span>{currencyPrecise(holding.price)}</span>
              <span>{currency(holding.market_value)}</span>
              <span>{percent(holding.weight)}</span>
              <span>{currency(holding.cost_basis)}</span>
              <span className={holding.unrealized_gain_loss >= 0 ? "positive-text" : "negative-text"}>{signedCurrency(holding.unrealized_gain_loss)}<small>{percent(holding.unrealized_gain_loss_pct)}</small></span>
              <span>{holding.warning ? "Review" : "Synced"}<small>{holding.data_source}</small></span>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "strong" | "positive" | "negative" }) {
  return (
    <article className={`stat-panel ${tone ? `portfolio-sync-stat-${tone}` : ""}`}>
      <h3>{label}</h3>
      <strong>{value}</strong>
      <p>Synced snapshot</p>
    </article>
  );
}

function HoldingPill({ holding }: { holding: PortfolioSyncHolding }) {
  return (
    <div className="portfolio-sync-top-row">
      <strong>{holding.symbol}<small>{percent(holding.weight)}</small></strong>
      <span>{currency(holding.market_value)}</span>
      <span className={holding.unrealized_gain_loss >= 0 ? "positive-text" : "negative-text"}>{signedCurrency(holding.unrealized_gain_loss)}</span>
    </div>
  );
}

function WarningList({ warnings }: { warnings: string[] }) {
  return (
    <section className="dashboard-panel portfolio-sync-warning-panel">
      <div className="panel-header">
        <h2>Review flags</h2>
        <AlertTriangle size={18} />
      </div>
      <div className="portfolio-sync-warning-list">
        {warnings.map((warning) => <p key={warning}>{warning}</p>)}
      </div>
    </section>
  );
}

function signedCurrency(value: number) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${currency(value)}`;
}

function currencyPrecise(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function formatShares(value: number) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 }).format(value);
}

function formatDateTime(value?: string | null) {
  if (!value) return "not synced";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "not synced";
  return parsed.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}
