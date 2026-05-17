import { ArrowRight, BarChart3, LockKeyhole, RefreshCw, Scale, ShieldCheck, TrendingUp } from "lucide-react";
import Link from "next/link";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";

const bars = [35, 44, 38, 52, 61, 57, 69, 64, 76, 72, 82, 79, 88, 84, 96, 92, 104, 100, 114, 110, 124, 119, 132, 128];

export default function Home() {
  return (
    <main className="site-shell">
      <header className="topbar">
        <Link href="/" className="brand">
          <span className="brand-mark">D</span>
          <span>DirectIndex</span>
        </Link>
        <nav className="nav-actions">
          <Link className="link-button" href="/research">Research</Link>
          <Link className="link-button" href="/retirement-analyzer">Retirement analyzer</Link>
          <Link className="link-button" href="/advisor">Advisor workspace</Link>
          <Link className="link-button" href="/login">Log in</Link>
          <Link className="primary-button" href="/signup">Get started <ArrowRight size={16} /></Link>
        </nav>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">Simulation-only direct indexing</p>
          <h1>Tax-aware index tracking.</h1>
          <p className="hero-copy">
            Build simulated direct-index portfolios for XLG, SPY, TOPT, and QTOP, track drift against the index, and review tax-loss harvesting trades before any real-world decision.
          </p>
          <div className="hero-actions" style={{ marginTop: 28 }}>
            <Link className="primary-button" href="/signup">Create account <ArrowRight size={16} /></Link>
            <Link className="secondary-button" href="/research">Review methodology</Link>
            <Link className="secondary-button" href="/retirement-analyzer">Retirement analyzer</Link>
            <Link className="ghost-button" href="/advisor">Open advisor workspace</Link>
          </div>
          <div className="trust-row">
            <div><strong>1,000</strong><span>annual TLH trade cap</span></div>
            <div><strong>4 indices</strong><span>XLG, SPY, TOPT, QTOP</span></div>
            <div><strong>2024/2025</strong><span>actual-history backtests</span></div>
          </div>
        </div>

        <div className="product-preview" aria-label="Dashboard preview">
          <div className="preview-header">
            <div>
              <strong>XLG direct index</strong>
              <div style={{ color: "var(--muted)", fontSize: ".9rem", marginTop: 3 }}>Tracking and tax-loss harvest review</div>
            </div>
            <span className="status-pill"><ShieldCheck size={14} /> Simulated</span>
          </div>
          <div className="metric-strip">
            <div className="metric"><span>Tracking score</span><strong>98.4</strong></div>
            <div className="metric"><span>Harvested losses</span><strong>$8,920</strong></div>
            <div className="metric"><span>Trade cap left</span><strong>714</strong></div>
          </div>
          <div className="preview-chart">
            {bars.map((height, index) => <i key={index} style={{ height }} />)}
          </div>
          <div className="preview-table">
            <div className="preview-row"><strong>SELL</strong><span>NVDA</span><span>$1,240 loss</span><span className="risk-pill">Wash clear</span></div>
            <div className="preview-row"><strong>BUY</strong><span>AVGO</span><span>Replacement</span><span className="reason-pill">Tracking</span></div>
          </div>
        </div>
      </section>

      <section className="section-band legal-section">
        <LegalDisclaimer />
      </section>

      <section className="section-band">
        <div className="section-title">
          <h2>Built for index tracking discipline.</h2>
          <p>Advisor proposals, portfolio construction, trade review, tax-lot accounting, and daily data caching live behind secure authentication and a modular backend.</p>
        </div>
        <div className="feature-grid">
          <article className="feature-card"><LockKeyhole size={24} /><h3>Backend-only credentials</h3><p>Passwords are hashed with Argon2id and sessions use HTTP-only cookies.</p></article>
          <article className="feature-card"><RefreshCw size={24} /><h3>Daily cached data</h3><p>Holdings and prices are cached with source dates and coverage warnings.</p></article>
          <article className="feature-card"><Scale size={24} /><h3>Wash-sale controls</h3><p>Exact tickers and user-defined equivalent groups are blocked inside the 30-day window.</p></article>
          <article className="feature-card"><BarChart3 size={24} /><h3>Advisor proposals</h3><p>Transition plans show tax impact, drift, active share, assumptions, and frozen audit snapshots.</p></article>
        </div>
      </section>

      <section className="section-band">
        <div className="section-title">
          <h2>Trade lists stay reviewable.</h2>
          <p>Tax-loss harvesting output is capped at 1,000 trades per calendar year per portfolio, keeping recommendations operationally manageable.</p>
        </div>
        <div className="feature-grid">
          <article className="feature-card"><TrendingUp size={24} /><h3>Prioritized by tax impact</h3><p>When candidates exceed the cap, the app keeps the strongest tax-loss opportunities first.</p></article>
          <article className="feature-card"><ShieldCheck size={24} /><h3>Warnings stay visible</h3><p>Dropped trades, skipped loss value, and ambiguous replacement notes are shown in the dashboard.</p></article>
        </div>
      </section>
    </main>
  );
}
