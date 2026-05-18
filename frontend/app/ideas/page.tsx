"use client";

import {
  ArrowRight,
  CalendarCheck,
  CheckCircle2,
  Gift,
  Landmark,
  Layers3,
  MapPinned,
  RotateCcw,
  Scale,
  ShieldCheck,
  SlidersHorizontal,
  WalletCards
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";

type IdeaMetric = {
  label: string;
  value: string;
  note: string;
};

type InvestorIdea = {
  id: string;
  label: string;
  title: string;
  badge: string;
  icon: LucideIcon;
  summary: string;
  metrics: IdeaMetric[];
  cadence: {
    scan: string;
    review: string;
    output: string;
  };
  rules: string[];
  review: string[];
  sources?: {
    label: string;
    url: string;
  }[];
};

const sectorReplacementRows = [
  ["Technology", "XLK", "VGT / IYW"],
  ["Financials", "XLF", "VFH / IYF"],
  ["Consumer discretionary", "XLY", "VCR / IYC"],
  ["Communication services", "XLC", "VOX / FCOM"],
  ["Industrials", "XLI", "VIS / IYJ"],
  ["Health care", "XLV", "VHT / IYH"],
  ["Staples", "XLP", "VDC / IYK"],
  ["Energy", "XLE", "VDE / IYE"],
  ["Utilities", "XLU", "VPU / IDU"],
  ["Materials", "XLB", "VAW / IYM"],
  ["Real estate", "XLRE", "VNQ / USRT"]
];

const investorIdeas: InvestorIdea[] = [
  {
    id: "sector-etf-tlh",
    label: "Sector ETF TLH",
    title: "11-sector ETF tax-loss-harvesting sleeve",
    badge: "Shared idea",
    icon: RotateCcw,
    summary:
      "Use the S&P 500 sector ETFs as a taxable sleeve, scan weekly for loss lots, move into similar replacement ETFs during the wash-sale window, and rebalance mainly with cash, dividends, or monthly drift checks.",
    metrics: [
      { label: "Universe", value: "11 sectors", note: "Sector ETF exposure" },
      { label: "TLH scan", value: "Weekly", note: "Harvest only meaningful losses" },
      { label: "Rebalance", value: "Monthly", note: "Quarterly full review" },
      { label: "Wash-sale guard", value: "31+ days", note: "Block sold tickers" }
    ],
    cadence: {
      scan: "Weekly",
      review: "Monthly",
      output: "Wash-sale list"
    },
    rules: [
      "Set a dollar loss threshold before selling so small losses do not create unnecessary trades.",
      "After selling a sector ETF at a loss, buy a similar replacement ETF and block the sold ticker for at least 31 days.",
      "Turn off automatic dividend reinvestment for the sleeve so cash does not accidentally rebuy a blocked ETF.",
      "Avoid forced weekly winner sales; use weekly checks for TLH and monthly reviews for drift."
    ],
    review: [
      "Compare the sleeve against SPY or the chosen benchmark after tax, not only before tax.",
      "Track harvested loss, realized gain, wash-sale blocks, replacement ETF, and return to primary ETF date.",
      "Keep the sleeve sized so tracking drift does not dominate the rest of the portfolio."
    ],
    sources: [
      {
        label: "Open shared idea",
        url: "https://chatgpt.com/share/6a0a7ab1-e2ec-83e8-9c2f-44cf40c2cfa1"
      }
    ]
  },
  {
    id: "core-satellite",
    label: "Core + TLH sleeve",
    title: "Core index plus taxable harvesting sleeve",
    badge: "Self-managed default",
    icon: Layers3,
    summary:
      "Keep the majority of equity exposure in low-cost core ETFs, then reserve a smaller sleeve for sector ETFs, direct-index simulation, or concentrated tax-lot work where harvesting and tracking can be reviewed separately.",
    metrics: [
      { label: "Core", value: "60-80%", note: "Low-maintenance exposure" },
      { label: "TLH sleeve", value: "20-40%", note: "Rules-based tax work" },
      { label: "Cash use", value: "Dividends", note: "Rebalance without selling" },
      { label: "Review", value: "Monthly", note: "Check drift and taxes" }
    ],
    cadence: {
      scan: "Monthly",
      review: "Quarterly",
      output: "Drift notes"
    },
    rules: [
      "Separate core holdings from the active tax sleeve so every trade has a clear purpose.",
      "Use new deposits, dividends, and cash first before selling appreciated winners.",
      "Do not measure success by harvested losses alone; include tracking error and realized gains.",
      "Keep an equivalent-security list so ETF pairs and peer baskets do not create hidden wash-sale risk."
    ],
    review: [
      "Portfolio value, tax lots, gains budget, replacement exposure, and index drift.",
      "Whether the TLH sleeve still earns its complexity after taxes and trading effort.",
      "Whether the core ETF overlaps with any replacement used inside the wash-sale window."
    ],
    sources: [
      {
        label: "Vanguard asset location research",
        url: "https://corporate.vanguard.com/content/corporatesite/us/en/corp/articles/greater-tax-efficiency-through-equity-asset-location.html"
      }
    ]
  },
  {
    id: "asset-location",
    label: "Asset location",
    title: "Asset location heat map across accounts",
    badge: "Tax placement",
    icon: MapPinned,
    summary:
      "Coordinate taxable, tax-deferred, Roth, and HSA-style accounts so tax-efficient holdings sit where they create the least drag, while high-income or high-turnover assets are reviewed for tax-advantaged placement.",
    metrics: [
      { label: "Taxable", value: "Equity ETFs", note: "Usually tax-efficient" },
      { label: "Tax-deferred", value: "Income assets", note: "Bonds, REITs, active funds" },
      { label: "Roth", value: "Growth", note: "Long runway assets" },
      { label: "Review", value: "Yearly", note: "Before rebalancing" }
    ],
    cadence: {
      scan: "Yearly",
      review: "Tax season",
      output: "Placement map"
    },
    rules: [
      "Start with total household asset allocation first, then decide which account should hold each exposure.",
      "Prefer broad equity ETFs, individual stocks, and low-turnover funds in taxable accounts when gains can receive favorable tax treatment.",
      "Review bonds, REITs, high-dividend funds, and high-turnover active funds for tax-deferred or tax-free accounts.",
      "Avoid creating large taxable gains just to perfect account placement; transition with new contributions, dividends, and rebalancing cash."
    ],
    review: [
      "Expected return, yield, turnover, and tax rate for each holding.",
      "Whether taxable capital gains from moving assets would erase future tax-location benefits.",
      "Whether Roth space should be reserved for highest-conviction long-term growth exposure."
    ],
    sources: [
      {
        label: "Vanguard: equity asset location",
        url: "https://corporate.vanguard.com/content/corporatesite/us/en/corp/articles/greater-tax-efficiency-through-equity-asset-location.html"
      },
      {
        label: "Bogleheads: tax-efficient placement",
        url: "https://www.bogleheads.org/wiki/Tax-efficient_fund_placement"
      }
    ]
  },
  {
    id: "retirement-buckets",
    label: "Retirement buckets",
    title: "Cash, bond, and growth buckets for market stress",
    badge: "Volatility plan",
    icon: WalletCards,
    summary:
      "Hold enough cash and high-quality bonds to cover planned withdrawals during bear markets, while leaving the long-term growth bucket invested so a retiree is not forced to sell stocks during deep drawdowns.",
    metrics: [
      { label: "Cash/T-bills", value: "1-2 yrs", note: "Near-term spending" },
      { label: "Bonds", value: "3-7 yrs", note: "Stability reserve" },
      { label: "Growth", value: "Long term", note: "Stocks and equity ETFs" },
      { label: "Review", value: "Annual", note: "Refill after gains" }
    ],
    cadence: {
      scan: "Annual",
      review: "After rallies",
      output: "Refill plan"
    },
    rules: [
      "Fund near-term withdrawals from cash/T-bills before selling volatile assets.",
      "Use high-quality bonds as the middle bucket, not as a return-chasing substitute for stocks.",
      "Refill cash from bonds or stock gains after strong markets, not during forced drawdowns.",
      "Tie bucket size to essential spending, pension/Social Security, taxes, and planned retirement age."
    ],
    review: [
      "Years of essential spending covered without selling growth assets.",
      "Bond duration and credit quality before increasing equity exposure.",
      "Whether the retirement analyzer shows shortfalls in the first retirement window."
    ],
    sources: [
      {
        label: "Schwab bucket drawdown strategy",
        url: "https://www.schwab.com/learn/story/phasing-retirement-with-bucket-drawdown-strategy"
      },
      {
        label: "Schwab retirement portfolio",
        url: "https://www.schwab.com/retirement-portfolio"
      }
    ]
  },
  {
    id: "tips-ladder",
    label: "TIPS ladder",
    title: "Inflation-linked income floor",
    badge: "Income floor",
    icon: Landmark,
    summary:
      "Build a ladder of Treasury Inflation-Protected Securities or high-quality bond rungs around essential spending so a retiree has scheduled maturities that are less dependent on stock-market timing.",
    metrics: [
      { label: "Floor target", value: "Essentials", note: "Must-pay spending" },
      { label: "Rungs", value: "1-10 yrs", note: "Stagger maturities" },
      { label: "Inflation", value: "TIPS", note: "Principal adjusts with CPI" },
      { label: "Review", value: "Annual", note: "Refill or extend" }
    ],
    cadence: {
      scan: "Annual",
      review: "After spending update",
      output: "Maturity ladder"
    },
    rules: [
      "Define the essential spending gap after Social Security, pension, annuity income, and cash reserves.",
      "Match ladder maturities to years where the portfolio should not depend on selling stocks.",
      "Use TIPS when inflation protection matters more than nominal yield certainty.",
      "Keep liquidity outside the ladder for emergencies so individual bonds do not need to be sold before maturity."
    ],
    review: [
      "Essential spending by year and the income already covered by stable sources.",
      "Treasury maturity dates, real yields, account location, and state-tax treatment.",
      "How the ladder interacts with Roth conversions, RMD timing, and the growth bucket."
    ],
    sources: [
      {
        label: "TreasuryDirect: TIPS",
        url: "https://www.treasurydirect.gov/indiv/products/prod_tips_glance.htm"
      },
      {
        label: "Schwab: bond laddering in retirement",
        url: "https://www.schwab.com/retirement-portfolio"
      }
    ]
  },
  {
    id: "giving-stack",
    label: "Giving stack",
    title: "DAF and QCD charitable tax stack",
    badge: "Charitable planning",
    icon: Gift,
    summary:
      "For charitably inclined households, coordinate appreciated-stock donations, donor-advised funds, deduction bunching, and later-life qualified charitable distributions with the portfolio and tax plan.",
    metrics: [
      { label: "Appreciated stock", value: "Donate", note: "Avoid selling first" },
      { label: "DAF", value: "Bundle", note: "Grant over time" },
      { label: "QCD age", value: "70.5+", note: "IRA to charity" },
      { label: "Review", value: "Year-end", note: "Before distributions" }
    ],
    cadence: {
      scan: "Year-end",
      review: "High-income years",
      output: "Giving lot list"
    },
    rules: [
      "Identify highly appreciated taxable lots before selling or rebalancing winners.",
      "Use a donor-advised fund when bunching several years of gifts into one high-income tax year makes itemizing more useful.",
      "For older IRA owners, evaluate QCDs separately because they can satisfy charitable intent without first increasing adjusted gross income.",
      "Do not combine DAF and QCD assumptions incorrectly: QCDs must go directly from the IRA trustee to an eligible charity."
    ],
    review: [
      "Which lots have the largest embedded gains and longest holding periods.",
      "Whether itemizing, standard deduction, AGI limits, state rules, or AMT change the value of a gift.",
      "Whether the donation plan conflicts with cash needs, legacy reserve, or Roth conversion taxes."
    ],
    sources: [
      {
        label: "Fidelity Charitable: donor-advised funds",
        url: "https://www.fidelitycharitable.org/guidance/philanthropy/what-is-a-donor-advised-fund.html"
      },
      {
        label: "IRS Publication 526: QCD",
        url: "https://www.irs.gov/publications/p526"
      },
      {
        label: "Fidelity: QCD overview",
        url: "https://www.fidelity.com/retirement-ira/required-minimum-distributions-qcds"
      }
    ]
  },
  {
    id: "roth-window",
    label: "Roth window",
    title: "Partial Roth conversion decision window",
    badge: "Tax-aware planning",
    icon: Scale,
    summary:
      "Evaluate conversions from tax-deferred accounts when bracket capacity, state taxes, portfolio size, and brokerage cash make the tax tradeoff attractive without creating avoidable liquidity pressure.",
    metrics: [
      { label: "Start age", value: "User-set", note: "Often after 59.5" },
      { label: "Conversion", value: "Partial", note: "Use bracket capacity" },
      { label: "Tax source", value: "Brokerage", note: "Avoid IRA withholding" },
      { label: "Review", value: "Yearly", note: "Before RMD pressure" }
    ],
    cadence: {
      scan: "Yearly",
      review: "Tax planning",
      output: "Conversion cap"
    },
    rules: [
      "Base the opportunity on tax-deferred balance, expected RMD pressure, current income, state tax, and future filing status.",
      "Prefer partial conversions when the next dollar still fits inside the target tax bracket.",
      "Estimate how much brokerage cash is needed to pay federal and state tax on the conversion.",
      "Stop when the conversion crowds out liquidity, emergency reserves, or near-term spending needs."
    ],
    review: [
      "Current marginal rate versus expected retirement and RMD-era marginal rate.",
      "Brokerage cash needed for taxes without selling growth assets at a bad time.",
      "Whether projected heirs, estate goals, or legacy reserve targets change the answer."
    ],
    sources: [
      {
        label: "Morningstar withdrawal sequencing",
        url: "https://www.morningstar.com/retirement/retirement-withdrawal-sequencing-rules-road"
      }
    ]
  },
  {
    id: "rebalance-bands",
    label: "Rebalance bands",
    title: "Threshold-based rebalancing playbook",
    badge: "Drift control",
    icon: SlidersHorizontal,
    summary:
      "Use tolerance bands instead of calendar-only trades, so rebalancing happens when allocation drift is meaningful enough to justify taxes, spreads, and trading effort.",
    metrics: [
      { label: "Primary check", value: "Bands", note: "Trigger on drift" },
      { label: "Cash first", value: "Yes", note: "Contributions and dividends" },
      { label: "Tax budget", value: "Required", note: "Avoid surprise gains" },
      { label: "Review", value: "Monthly", note: "Quarterly deeper check" }
    ],
    cadence: {
      scan: "Monthly",
      review: "Quarterly",
      output: "Trade/no-trade"
    },
    rules: [
      "Set target weights and tolerance bands before markets move, then follow the rule consistently.",
      "Use new cash, dividends, and withdrawals to bring allocations back toward target before taxable selling.",
      "When taxable sales are required, compare drift reduction against realized gains and current tax bracket.",
      "Coordinate bands with TLH replacement tickers so rebalancing does not buy a security still inside a wash-sale block."
    ],
    review: [
      "Current allocation versus target, drift amount, and which accounts can rebalance without taxable sales.",
      "Realized gains budget, available loss carryforwards, and state tax impact.",
      "Whether the rebalance reduces risk enough to justify the trading and tax cost."
    ],
    sources: [
      {
        label: "Vanguard threshold rebalancing research",
        url: "https://corporate.vanguard.com/content/dam/corp/research/pdf/the_rebalancing_edge_optimizing_target_date_fund_rebalancing_through_threshold_based_strategies.pdf"
      }
    ]
  }
];

export default function IdeasPage() {
  const [activeIdeaId, setActiveIdeaId] = useState(investorIdeas[0].id);
  const activeIdea = investorIdeas.find((idea) => idea.id === activeIdeaId) ?? investorIdeas[0];
  const ActiveIcon = activeIdea.icon;

  return (
    <main className="site-shell">
      <header className="topbar">
        <Link href="/" className="brand">
          <span className="brand-mark">D</span>
          <span>DirectIndex</span>
        </Link>
        <nav className="nav-actions">
          <Link className="link-button" href="/">Home</Link>
          <Link className="link-button" href="/research">Research</Link>
          <Link className="link-button" href="/retirement-analyzer">Retirement analyzer</Link>
          <Link className="link-button" href="/advisor">Advisor workspace</Link>
          <Link className="link-button" href="/login">Log in</Link>
          <Link className="primary-button" href="/signup">Get started <ArrowRight size={16} /></Link>
        </nav>
      </header>

      <section className="research-hero idea-hero">
        <div>
          <p className="eyebrow">Self-managed investor ideas</p>
          <h1>Rules before trades.</h1>
          <p className="hero-copy">
            Practical planning concepts for taxable accounts, retirement withdrawals, Roth conversions, and portfolio resilience, framed as reviewable playbooks instead of one-off trade tips.
          </p>
        </div>
        <div className="method-card">
          <ShieldCheck size={24} />
          <h2>Built as planning tabs</h2>
          <p>
            Each idea shows fit, cadence, guardrails, and review items so a self-managed investor can evaluate the workflow before considering any real transaction.
          </p>
          <div className="inline-actions">
            <span className="status-pill">Simulation first</span>
            <span className="reason-pill">Tax-aware</span>
            <span className="risk-pill">Not advice</span>
          </div>
        </div>
      </section>

      <section className="section-band legal-section">
        <LegalDisclaimer />
      </section>

      <section className="section-band">
        <div className="section-title">
          <h2>Ideas workspace.</h2>
          <p>Switch between planning playbooks and review the operating rules, cadence, and risk checks for each investor workflow.</p>
        </div>

        <div className="idea-workspace">
          <nav className="tab-list idea-tab-list" aria-label="Self-managed investor ideas">
            {investorIdeas.map((idea) => {
              const IdeaIcon = idea.icon;
              return (
                <button
                  className={idea.id === activeIdea.id ? "active" : ""}
                  key={idea.id}
                  type="button"
                  onClick={() => setActiveIdeaId(idea.id)}
                >
                  <IdeaIcon size={16} />
                  <span>{idea.label}</span>
                </button>
              );
            })}
          </nav>

          <div className="idea-layout">
            <article className="idea-primary">
              <div className="idea-heading">
                <ActiveIcon size={28} />
                <div>
                  <span className="reason-pill">{activeIdea.badge}</span>
                  <h2>{activeIdea.title}</h2>
                  <p>{activeIdea.summary}</p>
                </div>
              </div>

              <div className="idea-metric-grid">
                {activeIdea.metrics.map((metric) => (
                  <div className="idea-metric" key={metric.label}>
                    <span>{metric.label}</span>
                    <strong>{metric.value}</strong>
                    <small>{metric.note}</small>
                  </div>
                ))}
              </div>

              <div className="idea-columns">
                <section className="idea-check-panel">
                  <CalendarCheck size={20} />
                  <h3>Operating rules</h3>
                  <ul className="idea-list">
                    {activeIdea.rules.map((rule) => <li key={rule}>{rule}</li>)}
                  </ul>
                </section>

                <section className="idea-check-panel">
                  <CheckCircle2 size={20} />
                  <h3>Review before acting</h3>
                  <ul className="idea-list">
                    {activeIdea.review.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                </section>
              </div>

              {activeIdea.id === "sector-etf-tlh" ? (
                <section className="idea-replacement-section">
                  <div className="panel-header">
                    <div>
                      <h3>Sector ETF replacement map</h3>
                      <p>Replacement examples keep sector exposure while the sold ETF stays blocked during the wash-sale window.</p>
                    </div>
                    <span className="status-pill">Example pairs</span>
                  </div>
                  <div className="replacement-table">
                    <div className="replacement-row replacement-header">
                      <span>Sector</span>
                      <span>Primary</span>
                      <span>Replacement examples</span>
                    </div>
                    {sectorReplacementRows.map(([sector, primary, replacements]) => (
                      <div className="replacement-row" key={sector}>
                        <span>{sector}</span>
                        <strong>{primary}</strong>
                        <span>{replacements}</span>
                      </div>
                    ))}
                  </div>
                </section>
              ) : null}
            </article>

            <aside className="idea-side">
              <section className="idea-side-panel">
                <h3>Cadence</h3>
                <div className="cadence-list">
                  <div><span>Scan</span><strong>{activeIdea.cadence.scan}</strong></div>
                  <div><span>Review</span><strong>{activeIdea.cadence.review}</strong></div>
                  <div><span>Output</span><strong>{activeIdea.cadence.output}</strong></div>
                </div>
              </section>

              <section className="idea-side-panel">
                <h3>Connect this idea</h3>
                <p>
                  Use the portfolio dashboard for simulated trades and the retirement analyzer for tax-aware cash-flow context before moving from idea to implementation.
                </p>
                <div className="idea-actions">
                  <Link className="secondary-button" href="/dashboard">Dashboard</Link>
                  <Link className="ghost-button" href="/retirement-analyzer">Retirement analyzer</Link>
                </div>
              </section>

              {activeIdea.sources?.length ? (
                <section className="idea-side-panel">
                  <h3>References</h3>
                  <div className="source-link-list">
                    {activeIdea.sources.map((source) => (
                      <a href={source.url} target="_blank" rel="noreferrer" className="text-link" key={source.url}>
                        {source.label} <ArrowRight size={15} />
                      </a>
                    ))}
                  </div>
                </section>
              ) : null}
            </aside>
          </div>
        </div>
      </section>
    </main>
  );
}
