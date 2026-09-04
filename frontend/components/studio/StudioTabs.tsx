"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { DEFAULT_STUDIO_TOOL, STUDIO_TOOLS } from "@/lib/studio-tools";

export function StudioTabs() {
  const pathname = usePathname();
  const segment = pathname === "/studio" ? DEFAULT_STUDIO_TOOL : pathname.replace(/^\/studio\//, "");

  return (
    <div className="ai-tabbar" role="tablist" aria-label="FinanceOS Studio tabs">
      {STUDIO_TOOLS.map(({ slug, label, Icon }) => {
        const active = segment === slug;
        return (
          <Link
            key={slug}
            href={slug === DEFAULT_STUDIO_TOOL ? "/studio" : `/studio/${slug}`}
            role="tab"
            aria-selected={active}
            className={`${slug === DEFAULT_STUDIO_TOOL ? "recommendation-agent-tab " : ""}${active ? "active" : ""}`}
          >
            <Icon size={16} /> {label}
          </Link>
        );
      })}
    </div>
  );
}
