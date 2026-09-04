"use client";

import Link from "next/link";
import { ReactNode, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { LegalDisclaimer } from "@/components/LegalDisclaimer";
import { StudioProvider, useStudio } from "./StudioContext";
import { StudioSidebar } from "./StudioSidebar";
import { StudioTabs } from "./StudioTabs";

export function StudioShell({ children }: { children: ReactNode }) {
  return (
    <StudioProvider>
      <StudioChrome>{children}</StudioChrome>
    </StudioProvider>
  );
}

function StudioChrome({ children }: { children: ReactNode }) {
  const { keyStatus } = useStudio();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <main className="dashboard-shell ai-advisor-shell">
      <AppHeader
        title="FinanceOS Studio"
        actions={
          <>
            <span className={keyStatus?.has_key ? "status-pill" : "risk-pill"}>
              {keyStatus?.has_key ? "OpenAI key saved" : "Key required"}
            </span>
            <Link className="ghost-button" href="/portfolio">Portfolio</Link>
            <Link className="ghost-button" href="/investing">Calculators</Link>
            <Link className="ghost-button" href="/retirement-analyzer">Plan</Link>
            <Link className="secondary-button" href="/dashboard">Portfolio dashboard</Link>
          </>
        }
      />

      <div className="dashboard-disclaimer">
        <LegalDisclaimer compact />
      </div>

      <StudioTabs />

      <div className={`ai-advisor-layout${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
        <StudioSidebar collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed((v) => !v)} />
        <section className="ai-advisor-workspace">{children}</section>
      </div>
    </main>
  );
}
