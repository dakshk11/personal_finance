import { ArrowRight, BarChart3, BookOpen, LockKeyhole, Scale, ShieldCheck, TrendingUp, WalletCards } from "lucide-react";
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
          <Link className="link-button" href="/ideas">Ideas</Link>
          <Link className="link-button" href="/retirement-analyzer">Retirement analyzer</Link>
          <Link className="link-button" href="/advisor">Advisor workspace</Link>
          <Link className="link-button" href="/login">Log in</Link>
          <Link className="primary-button" href="/signup">Get started <ArrowRight size={16} /></Link>
        </nav>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">Simulation-only tax-aware planning</p>
          <h1>Tax-aware planning simulator.</h1>
          <p className="hero-copy">
            Model portfolio transitions, retirement income, Roth conversion windows, self-managed investor playbooks, and direct-index tax workflows before any real-world decision.
          </p>
          <div className="hero-actions" style={{ marginTop: 28 }}>
            <Link className="primary-button" href="/signup">Create account <ArrowRight size={16} /></Link>
            <Link className="secondary-button" href="/research">Review methodology</Link>
            <Link className="secondary-button" href="/ideas">Investor ideas</Link>
            <Link className="secondary-button" href="/retirement-analyzer">Retirement analyzer</Link>
            <Link className="ghost-button" href="/advisor">Open advisor workspace</Link>
          </div>
          <div className="trust-row">
            <div><strong>6 modules</strong><span>portfolio, retirement, ideas, advisor, research, 13F</span></div>
            <div><strong>8 playbooks</strong><span>self-managed investor ideas</span></div>
            <div><strong>Saved inputs</strong><span>retirement analyzer state after login</span></div>
          </div>
        </div>

        <div className="product-preview" aria-label="Planning simulator preview">
          <div className="preview-header">
            <div>
              <strong>Planning command center</strong>
              <div style={{ color: "var(--muted)", fontSize: ".9rem", marginTop: 3 }}>Portfolio, retirement, Roth, and investor idea review</div>
            </div>
            <span className="status-pill"><ShieldCheck size={14} /> Simulated</span>
          </div>
          <div className="metric-strip">
            <div className="metric"><span>Retirement confidence</span><strong>98%</strong></div>
            <div className="metric"><span>Roth window</span><strong>Partial</strong></div>
            <div className="metric"><span>Ideas library</span><strong>8 tabs</strong></div>
          </div>
          <div className="preview-chart">
            {bars.map((height, index) => <i key={index} style={{ height }} />)}
          </div>
          <div className="preview-table">
            <div className="preview-row"><strong>PLAN</strong><span>Tax-aware withdrawals</span><span>Funding mix</span><span className="status-pill">Modeled</span></div>
            <div className="preview-row"><strong>REVIEW</strong><span>Roth conversion</span><span>Brokerage tax funding</span><span className="reason-pill">Explainable</span></div>
          </div>
        </div>
      </section>

      <section className="section-band legal-section">
        <LegalDisclaimer />
      </section>

      <section className="section-band">
        <div className="section-title">
          <h2>Built for tax-aware planning decisions.</h2>
          <p>Portfolio construction, retirement cash flow, advisor transition proposals, investor ideas, methodology, and daily data caching live behind secure authentication and a modular backend.</p>
        </div>
        <div className="feature-grid">
          <article className="feature-card"><LockKeyhole size={24} /><h3>Secure user workspace</h3><p>Passwords are hashed with Argon2id, sessions use HTTP-only cookies, and retirement inputs can reload after login.</p></article>
          <article className="feature-card"><WalletCards size={24} /><h3>Retirement cash flow</h3><p>Account mix, state taxes, Natural Retirement Spending Smile, Roth conversions, and withdrawal sequencing stay visible.</p></article>
          <article className="feature-card"><BookOpen size={24} /><h3>Investor playbooks</h3><p>Ideas tabs organize sector ETF TLH, asset location, TIPS ladders, charitable giving, buckets, and rebalance bands.</p></article>
          <article className="feature-card"><BarChart3 size={24} /><h3>Advisor proposals</h3><p>Transition plans show tax impact, drift, active share, assumptions, and frozen audit snapshots.</p></article>
        </div>
      </section>

      <section className="section-band">
        <div className="section-title">
          <h2>Every output stays reviewable.</h2>
          <p>Direct-index trades, Roth conversion amounts, retirement shortfalls, bucket guidance, and investor ideas are framed as review artifacts, not instructions to act.</p>
        </div>
        <div className="feature-grid">
          <article className="feature-card"><TrendingUp size={24} /><h3>Tax impact explained</h3><p>TLH output, taxable transitions, Roth conversion taxes, and charitable giving ideas show the assumptions behind the result.</p></article>
          <article className="feature-card"><Scale size={24} /><h3>Guardrails stay explicit</h3><p>Wash-sale blocks, spending floors, legacy reserves, withdrawal gaps, and rebalance bands stay visible for review.</p></article>
          <article className="feature-card"><ShieldCheck size={24} /><h3>Simulation-first language</h3><p>Legal disclaimers and warnings reinforce that outputs are hypothetical planning artifacts, not tax or investment advice.</p></article>
        </div>
      </section>
    </main>
  );
}
