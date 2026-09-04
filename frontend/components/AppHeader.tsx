"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Lane, PRIMARY_NAV_ITEMS, PRODUCT_MARK, PRODUCT_NAME, orderNavForLane, readStoredLane } from "@/lib/brand";

type AppHeaderProps = {
  actions?: ReactNode;
  showPrimaryNav?: boolean;
  title?: string;
  variant?: "site" | "dashboard";
};

export function BrandLink() {
  return (
    <Link href="/" className="brand">
      <span className="brand-mark">{PRODUCT_MARK}</span>
      <span>{PRODUCT_NAME}</span>
    </Link>
  );
}

export function AppHeader({ actions, showPrimaryNav = true, title, variant = "dashboard" }: AppHeaderProps) {
  const [lane, setLane] = useState<Lane | null>(null);

  useEffect(() => {
    setLane(readStoredLane());
  }, []);

  const navItems = useMemo(() => orderNavForLane(PRIMARY_NAV_ITEMS, lane), [lane]);

  if (variant === "site") {
    return (
      <header className="topbar">
        <BrandLink />
        <nav className="nav-actions" aria-label="Primary navigation">
          {showPrimaryNav && navItems.map((item) => (
            <Link className="link-button" href={item.href} key={item.href}>
              {item.label}
            </Link>
          ))}
          {actions}
        </nav>
      </header>
    );
  }

  return (
    <header className="dashboard-header">
      <div>
        <BrandLink />
        {title ? <h1>{title}</h1> : null}
      </div>
      {actions ? <div className="dashboard-actions">{actions}</div> : null}
    </header>
  );
}
