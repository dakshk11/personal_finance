import { BarChart3, BookOpen, Bot, LineChart, LockKeyhole, PieChart, ShieldCheck, WalletCards } from "lucide-react";
import Link from "next/link";
import { AppHeader } from "@/components/AppHeader";
import { LaneDoors } from "@/components/LaneDoors";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { PRODUCT_NAME } from "@/lib/brand";

const pipeline = [
  { group: "Scanners", steps: ["Wheel", "Breakout", "Smart Candles", "OptiTrade"] },
  { group: "Routing", steps: ["Model router", "First LLM"] },
  { group: "Enrichment", steps: ["TipRanks", "LunarCrush", "Market context"] },
  { group: "Ranking", steps: ["Final LLM", "Ranked ideas"] }
];

const guardrails = [
  { Icon: ShieldCheck, title: "Simulation-first", body: "Every output is a hypothetical planning artifact with explicit review guardrails, not an instruction to act." },
  { Icon: LockKeyhole, title: "Secrets stay server-side", body: "Provider keys are encrypted in the database and never returned to the browser." },
  { Icon: BarChart3, title: "Assumptions stay visible", body: "Tax impact, drift, wash-sale blocks, spending floors and rebalance bands are shown alongside every result." }
];

const modules = [
  { href: "/retirement-analyzer", label: "Plan", title: "Retirement, Roth, sequencing", body: "Model income, taxes, spending guardrails, and withdrawal order before real-world decisions.", Icon: WalletCards },
  { href: "/portfolio", label: "Portfolio", title: "Manual and synced holdings", body: "Review cost basis, weights, sector mix, concentration, and synced brokerage snapshots.", Icon: BarChart3 },
  { href: "/studio", label: "Studio", title: "Recommendation Agent and market playbooks", body: "Rank scanner evidence into a shortlist, then drill into wheel income, breakouts, and options structures.", Icon: Bot },
  { href: "/research", label: "Research", title: "13F and methodology library", body: "Inspect manager filings, tax-loss harvesting logic, and direct-indexing references.", Icon: BookOpen },
  { href: "/diversify", label: "Diversify", title: "Concentration → SCHD diversification", body: "Simulate TLH-funded diversification of a concentrated stock into SCHD, with backtested returns and monthly trades.", Icon: PieChart },
  { href: "/advisor", label: "Advisor", title: "Transition proposals", body: "Build reviewable transition plans with tax impact, drift, active share, and audit snapshots.", Icon: LineChart },
  { href: "/investing", label: "Calculators", title: "Trend and return calculators", body: "Moving-average trend models, return paths with dividends, and the high-yield income ETF monitor.", Icon: LineChart },
  { href: "/ideas", label: "Ideas", title: "Rules before trades", body: "Written playbooks and planning rules kept separate from any execution workflow.", Icon: BookOpen }
];

export default function Home() {
  return (
    <main className="site-shell">
      <AppHeader variant="site" />

      <section className="lane-hero">
        <p className="eyebrow">Simulation-only household finance workspace</p>
        <h1>{PRODUCT_NAME}</h1>
        <p className="lane-hero-copy">
          Scanners, options data and two LLM passes resolved into a ranked shortlist — alongside the retirement, portfolio and tax-aware planning tools that sit behind it.
        </p>
        <span className="status-pill lane-hero-pill"><ShieldCheck size={14} /> Simulated output only</span>
      </section>

      <LaneDoors />

      <section className="section-band">
        <div className="section-title">
          <h2>How the Recommendation Agent works.</h2>
          <p>One run merges four scanners, enriches the finalists, and asks the model twice — once to shortlist, once to rank. Every stage reports its own progress and warnings.</p>
        </div>
        <div className="pipeline">
          {pipeline.map((phase) => (
            <div className="pipeline-phase" key={phase.group}>
              <span className="pipeline-group">{phase.group}</span>
              <div className="pipeline-steps">
                {phase.steps.map((step) => <span key={step}>{step}</span>)}
              </div>
            </div>
          ))}
        </div>
        <p className="pipeline-foot">
          <Link className="primary-button" href="/studio">Open the agent</Link>
        </p>
      </section>

      <section className="section-band legal-section">
        <LegalDisclaimer />
      </section>

      <section className="section-band">
        <div className="section-title">
          <h2>Every output stays reviewable.</h2>
        </div>
        <div className="feature-grid">
          {guardrails.map(({ Icon, title, body }) => (
            <article className="feature-card" key={title}>
              <Icon size={24} />
              <h3>{title}</h3>
              <p>{body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section-band">
        <div className="section-title">
          <h2>All modules.</h2>
          <p>Everything in the workspace, for when you already know where you are going.</p>
        </div>
        <div className="module-grid">
          {modules.map(({ Icon, ...module }) => (
            <Link className="module-card" href={module.href} key={module.href}>
              <div className="module-kicker">
                <span>{module.label}</span>
                <Icon size={18} />
              </div>
              <strong>{module.title}</strong>
              <p>{module.body}</p>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
