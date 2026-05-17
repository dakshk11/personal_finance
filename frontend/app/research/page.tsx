import { ArrowRight, BookOpen, Calculator, CheckCircle2, FileText, GitBranch, LineChart, Scale, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";

const sourcePapers = [
  {
    title: "IRS Publication 550: Wash Sales",
    source: "Internal Revenue Service",
    year: "2025",
    url: "https://www.irs.gov/publications/p550",
    usedFor: "The 30-day wash-sale window, substantially identical security checks, and why the app flags replacement similarity risk.",
    plainEnglish: "A harvested loss can be disallowed if the investor buys the same or substantially identical security too close to the sale."
  },
  {
    title: "Wealthfront Tax-Loss Harvesting White Paper",
    source: "Wealthfront Research",
    year: "2026",
    url: "https://research.wealthfront.com/whitepapers/tax-loss-harvesting/",
    usedFor: "Daily loss scanning, highly correlated replacements, harvesting yield, and the distinction between tax deferral and tax avoidance.",
    plainEnglish: "Tax-loss harvesting sells losing lots, buys a similar replacement, and measures value by how losses offset current or future taxable gains."
  },
  {
    title: "Wealthfront US Direct Indexing White Paper",
    source: "Wealthfront Research",
    year: "2025",
    url: "https://research.wealthfront.com/whitepapers/stock-level-tax-loss-harvesting/",
    usedFor: "Stock-level harvesting, completion ETF sleeves, and why individual holdings create more harvesting opportunities than ETF-only portfolios.",
    plainEnglish: "Owning stocks directly can keep broad market exposure while creating more separate tax lots to review for harvestable losses."
  },
  {
    title: "Direct Indexing for Tax Loss Harvesting",
    source: "Journal of Financial Planning",
    year: "2022",
    url: "https://www.financialplanningassociation.org/learning/publications/journal/OCT22-direct-indexing-tax-loss-harvesting-OPEN",
    usedFor: "Benchmark-relative portfolio construction, peer replacements, and backtesting factor, size, sector, and tracking exposure before swaps.",
    plainEnglish: "Start from a benchmark, own the same holdings at similar weights, then use rules and peer replacements to limit drift."
  },
  {
    title: "Beyond Direct Indexing: Dynamic Direct Long-Short Investing",
    source: "AQR / Journal of Beta Investment Strategies",
    year: "2023",
    url: "https://www.aqr.com/Insights/Research/Journal-Article/Beyond-Direct-Indexing-Dynamic-Direct-Long-Short-Investing",
    usedFor: "Research-only context for long-short direct indexing and why the app keeps leveraged long-short models out of the default workflow.",
    plainEnglish: "More complex long-short approaches may harvest more losses, but they add leverage, shorting, and materially higher model risk."
  },
  {
    title: "Long Short Direct Indexing White Paper",
    source: "Frec",
    year: "2025",
    url: "https://freccom.blog/2025/07/17/white-paper-long-short-direct-indexing/",
    usedFor: "The constrained-optimization framing: trade off tracking error, tax-loss opportunity, and transaction cost.",
    plainEnglish: "A direct-indexing engine should not chase losses blindly; it should compare tax value against tracking and trading costs."
  }
];

const algorithmSteps = [
  {
    icon: LineChart,
    title: "Track the benchmark first",
    body: "The app normalizes index holdings, applies exclusions, then calculates target dollar weights so the simulated portfolio starts from the benchmark instead of a hand-picked stock list."
  },
  {
    icon: Calculator,
    title: "Scan tax lots for real losses",
    body: "Lots qualify only when the current value is below cost basis by enough dollars and percent. Conservative, moderate, and aggressive modes simply change those thresholds and scan cadence."
  },
  {
    icon: Scale,
    title: "Reject wash-sale conflicts",
    body: "The engine blocks prior buys inside the 30-day window and rejects equivalent replacement groups before showing a candidate as wash-sale clear."
  },
  {
    icon: GitBranch,
    title: "Choose replacement exposure",
    body: "Executable models either use same-sector peer baskets or a completion ETF sleeve, then monthly rebalancing pulls the account back toward target weights."
  },
  {
    icon: ShieldCheck,
    title: "Control operational risk",
    body: "The annual tax-loss-harvesting cap is 1,000 trade rows. If there are too many candidates, lower-impact trades are dropped and the skipped loss value stays visible."
  },
  {
    icon: CheckCircle2,
    title: "Show the evidence",
    body: "Backtests compare portfolio value, benchmark value, tracking difference, harvested losses, tax-adjusted result, cap usage, and warnings for review."
  }
];

const modelNotes = [
  {
    name: "Risk-score optimizer",
    status: "Executable",
    explanation: "Ranks harvest value against tracking drift, turnover, and wash-sale controls. This is the default when index discipline matters most."
  },
  {
    name: "Threshold throttle",
    status: "Executable",
    explanation: "Harvests only larger losses, scans less aggressively, and keeps a tighter tracking budget for lower-turnover accounts."
  },
  {
    name: "Peer basket",
    status: "Executable",
    explanation: "Sells the losing stock and buys similar same-sector peers, keeping exposure stock-based while avoiding the exact sold ticker."
  },
  {
    name: "Completion ETF sleeve",
    status: "Executable",
    explanation: "Uses the selected ETF or index sleeve as temporary exposure during the wash-sale lockout, reducing replacement trade count."
  },
  {
    name: "Long-short direct indexing",
    status: "Research only",
    explanation: "Displayed for education, but not enabled for trade generation because leverage and shorting add complexity beyond this simulation."
  }
];

export default function ResearchPage() {
  return (
    <main className="site-shell">
      <header className="topbar">
        <Link href="/" className="brand">
          <span className="brand-mark">D</span>
          <span>DirectIndex</span>
        </Link>
        <nav className="nav-actions">
          <Link className="link-button" href="/">Home</Link>
          <Link className="link-button" href="/retirement-analyzer">Retirement analyzer</Link>
          <Link className="link-button" href="/advisor">Advisor workspace</Link>
          <Link className="link-button" href="/login">Log in</Link>
          <Link className="primary-button" href="/signup">Get started <ArrowRight size={16} /></Link>
        </nav>
      </header>

      <section className="research-hero">
        <div>
          <p className="eyebrow">Research and algorithm notes</p>
          <h1>How the direct-indexing simulation decides.</h1>
          <p className="hero-copy">
            This page explains the papers, white papers, and tax rules behind the app in plain language, then maps them to the exact models exposed in the dashboard.
          </p>
        </div>
        <div className="method-card">
          <BookOpen size={24} />
          <h2>What users should understand</h2>
          <p>
            DirectIndex is simulation-only. It shows how tax-loss harvesting candidates are found, filtered, replaced, and backtested before a user talks with a qualified advisor.
          </p>
          <div className="inline-actions">
            <span className="status-pill">Research backed</span>
            <span className="reason-pill">No live trading</span>
            <span className="risk-pill">Not tax advice</span>
          </div>
        </div>
      </section>

      <section className="section-band legal-section">
        <LegalDisclaimer />
      </section>

      <section className="section-band">
        <div className="section-title">
          <h2>Source library.</h2>
          <p>Each source is listed with the specific implementation idea it supports, so the methodology is easy to audit.</p>
        </div>
        <div className="paper-grid">
          {sourcePapers.map((paper) => (
            <article className="paper-card" key={paper.title}>
              <div className="paper-meta">
                <span className="reason-pill">{paper.source}</span>
                <span>{paper.year}</span>
              </div>
              <h3>{paper.title}</h3>
              <p>{paper.plainEnglish}</p>
              <div className="source-use">
                <strong>Used in DirectIndex for</strong>
                <span>{paper.usedFor}</span>
              </div>
              <a href={paper.url} target="_blank" rel="noreferrer" className="text-link">
                Open source <ArrowRight size={15} />
              </a>
            </article>
          ))}
        </div>
      </section>

      <section className="section-band">
        <div className="section-title">
          <h2>Algorithm, without jargon.</h2>
          <p>The trading engine is a sequence of guardrails, not a black box. Every candidate must pass these checks before it appears in the dashboard.</p>
        </div>
        <div className="algorithm-grid">
          {algorithmSteps.map((step) => {
            const Icon = step.icon;
            return (
              <article className="algorithm-step" key={step.title}>
                <Icon size={22} />
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </article>
            );
          })}
        </div>
      </section>

      <section className="section-band">
        <div className="section-title">
          <h2>Model map.</h2>
          <p>The dashboard labels match the backend model names, so users can connect what they read here to what they run in backtests.</p>
        </div>
        <div className="model-note-list">
          {modelNotes.map((model) => (
            <article className="model-note" key={model.name}>
              <div>
                <h3>{model.name}</h3>
                <p>{model.explanation}</p>
              </div>
              <span className={model.status === "Executable" ? "status-pill" : "risk-pill"}>{model.status}</span>
            </article>
          ))}
        </div>
      </section>

      <section className="section-band">
        <div className="confidence-panel">
          <FileText size={24} />
          <div>
            <h2>Why this should build confidence</h2>
            <p>
              The website now separates methodology from marketing: users can see source material, understand the simplified algorithm, and verify that risky ideas such as long-short direct indexing are labeled research-only.
            </p>
          </div>
          <Link className="primary-button" href="/signup">Try the simulation <ArrowRight size={16} /></Link>
        </div>
      </section>
    </main>
  );
}
