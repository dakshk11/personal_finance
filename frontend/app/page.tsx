import { ArrowRight, BarChart3, BookOpen, Bot, LineChart, LockKeyhole, Scale, ShieldCheck, TrendingUp, WalletCards } from "lucide-react";
import Link from "next/link";
import { AppHeader } from "@/components/AppHeader";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { PRODUCT_NAME } from "@/lib/brand";

const modules = [
  {
    href: "/retirement-analyzer",
    label: "Plan",
    title: "Retirement, Roth, sequencing",
    body: "Model income, taxes, spending guardrails, and withdrawal order before real-world decisions.",
    Icon: WalletCards
  },
  {
    href: "/portfolio",
    label: "Portfolio",
    title: "Manual and synced holdings",
    body: "Review cost basis, weights, sector mix, concentration, and synced brokerage snapshots.",
    Icon: BarChart3
  },
  {
    href: "/ai-advisor",
    label: "Studio",
    title: "AI planning and market playbooks",
    body: "Generate planning artifacts, Personal CFO summaries, Wheel Strategy scans, and RSI reviews.",
    Icon: Bot
  },
  {
    href: "/research",
    label: "Research",
    title: "13F and methodology library",
    body: "Inspect manager filings, tax-loss harvesting logic, and direct-indexing references.",
    Icon: BookOpen
  },
  {
    href: "/advisor",
    label: "Advisor",
    title: "Transition proposals",
    body: "Build reviewable transition plans with tax impact, drift, active share, and audit snapshots.",
    Icon: LineChart
  }
];

export default function Home() {
  return (
    <main className="site-shell">
      <AppHeader variant="site" />

      <section className="hero financeos-hero">
        <div className="hero-copy-block">
          <p className="eyebrow">Simulation-only household finance workspace</p>
          <h1>{PRODUCT_NAME}</h1>
          <p className="hero-copy">
            Plan retirement income, sync brokerage holdings, analyze portfolios, review tax-aware transitions, and run educational market playbooks in one simulation-only workspace.
          </p>
          <div className="hero-actions" style={{ marginTop: 28 }}>
            <Link className="primary-button" href="/dashboard">Open dashboard <ArrowRight size={16} /></Link>
            <Link className="secondary-button" href="/retirement-analyzer">Plan retirement</Link>
            <Link className="secondary-button" href="/portfolio">Analyze portfolio</Link>
            <Link className="secondary-button" href="/ai-advisor">Open Studio</Link>
            <Link className="ghost-button" href="/research">Research methodology</Link>
          </div>
          <div className="trust-row">
            <div><strong>Command center</strong><span>planning, portfolio, market playbooks, advisor workflows</span></div>
            <div><strong>Read-only sync</strong><span>brokerage snapshots, cost-basis review, concentration warnings</span></div>
            <div><strong>Simulation-first</strong><span>hypothetical outputs with explicit review guardrails</span></div>
          </div>
        </div>

        <div className="financeos-cockpit" aria-label="FinanceOS module cockpit">
          <div className="cockpit-topline">
            <div>
              <strong>Household command center</strong>
              <span>One workspace for planning, portfolios, markets, and research</span>
            </div>
            <span className="status-pill"><ShieldCheck size={14} /> Simulated</span>
          </div>
          <div className="cockpit-grid">
            {modules.map(({ Icon, ...module }) => (
              <Link className="cockpit-module" href={module.href} key={module.href}>
                <div className="module-kicker">
                  <span>{module.label}</span>
                  <Icon size={18} />
                </div>
                <strong>{module.title}</strong>
                <p>{module.body}</p>
              </Link>
            ))}
          </div>
          <div className="cockpit-rail">
            <div><TrendingUp size={18} /><span>Wheel Strategy and RSI Playbook stay educational research, not trading instructions.</span></div>
            <div><Scale size={18} /><span>Tax-aware transition output remains reviewable and documented.</span></div>
            <div><LockKeyhole size={18} /><span>Provider secrets are encrypted and never returned to the browser.</span></div>
          </div>
        </div>
      </section>

      <section className="section-band legal-section">
        <LegalDisclaimer />
      </section>

      <section className="section-band">
        <div className="section-title">
          <h2>Modules that work together.</h2>
          <p>FinanceOS connects retirement cash flow, synced holdings, portfolio analysis, direct-indexing research, and educational market workbenches while keeping each output in a review-first lane.</p>
        </div>
        <div className="feature-grid">
          <article className="feature-card"><LockKeyhole size={24} /><h3>Local workspace</h3><p>Inputs and saved planning artifacts reload against a shared local demo account while login is disabled.</p></article>
          <article className="feature-card"><WalletCards size={24} /><h3>Household planning</h3><p>Account mix, state taxes, Natural Retirement Spending Smile, Roth conversions, and withdrawal sequencing stay visible.</p></article>
          <article className="feature-card"><BookOpen size={24} /><h3>Investor playbooks</h3><p>Wheel Strategy, RSI Playbook, sector ETF TLH, asset location, TIPS ladders, charitable giving, buckets, and rebalance bands stay organized.</p></article>
          <article className="feature-card"><BarChart3 size={24} /><h3>Advisor proposals</h3><p>Transition plans show tax impact, drift, active share, assumptions, and frozen audit snapshots.</p></article>
        </div>
      </section>

      <section className="section-band">
        <div className="section-title">
          <h2>Every output stays reviewable.</h2>
          <p>Portfolio transitions, Roth conversion amounts, retirement shortfalls, bucket guidance, and investor ideas are framed as review artifacts, not instructions to act.</p>
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
