"use client";

import { useState } from "react";
import { AlertTriangle, ChevronDown } from "lucide-react";

export const STRONG_LEGAL_DISCLAIMER = [
  "FinanceOS is educational planning software only. It is not a registered investment adviser, broker-dealer, law firm, CPA firm, tax preparer, fiduciary, custodian, or trading system.",
  "Nothing on this website, in any proposal, export, backtest, tax-loss-harvesting output, transition plan, algorithm result, or data display is tax, legal, accounting, investment, fiduciary, brokerage, or trading advice.",
  "Do not buy, sell, hold, rebalance, harvest losses, file a tax return, claim a tax benefit, or make any financial decision based only on this website. Consult a qualified attorney, CPA or tax professional, and appropriately registered investment adviser before acting.",
  "Outputs are hypothetical, model-based, and dependent on user-provided data, assumptions, cached data, and simplified rules. They may be stale, incomplete, inaccurate, unsuitable, or inconsistent with a client's full financial, legal, tax, or regulatory facts.",
  "FinanceOS does not guarantee performance, tax savings, wash-sale treatment, tracking error, active share, data accuracy, regulatory compliance, suitability, availability, or any outcome. Users and advisors are solely responsible for independent review, documentation, supervision, and final decisions."
];

export function LegalDisclaimer({ compact = false, defaultCollapsed = compact }: { compact?: boolean; defaultCollapsed?: boolean }) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  return (
    <section className={compact ? "legal-disclaimer compact" : "legal-disclaimer"} aria-label="Important legal disclaimer">
      <div className="legal-disclaimer-heading">
        <AlertTriangle size={20} />
        <div>
          <span>Important legal disclaimer</span>
          <strong>Do not treat this website as advice.</strong>
        </div>
        <button
          className="disclaimer-toggle"
          type="button"
          aria-expanded={!collapsed}
          onClick={() => setCollapsed((current) => !current)}
        >
          {collapsed ? "Show details" : "Hide details"}
          <ChevronDown size={16} />
        </button>
      </div>
      <ul hidden={collapsed}>
        {STRONG_LEGAL_DISCLAIMER.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </section>
  );
}
