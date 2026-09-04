"use client";

import { ArrowRight, LineChart, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Lane, readStoredLane, storeLane } from "@/lib/brand";

const DOORS: Array<{
  lane: Lane;
  href: string;
  kicker: string;
  title: string;
  body: string;
  links: Array<{ href: string; label: string }>;
  Icon: typeof Sparkles;
}> = [
  {
    lane: "trade",
    href: "/studio",
    kicker: "Short horizon",
    title: "Trade and income today",
    body: "Run the Recommendation Agent: wheel premium, breakouts and options structures, ranked from merged scanner evidence.",
    links: [
      { href: "/studio/wheel-scanner", label: "Wheel scanner" },
      { href: "/studio/breakout-scanner", label: "Breakout scanner" },
      { href: "/studio/optitrade-lab", label: "OptiTrade Lab" }
    ],
    Icon: Sparkles
  },
  {
    lane: "invest",
    href: "/dashboard",
    kicker: "Long horizon",
    title: "Build long-term wealth",
    body: "Retirement income, synced holdings, concentration review and tax-loss funded diversification.",
    links: [
      { href: "/retirement-analyzer", label: "Retirement plan" },
      { href: "/portfolio", label: "Portfolio analysis" },
      { href: "/diversify", label: "Diversify" }
    ],
    Icon: LineChart
  }
];

export function LaneDoors() {
  const [lane, setLane] = useState<Lane | null>(null);

  useEffect(() => {
    setLane(readStoredLane());
  }, []);

  return (
    <div className="lane-doors">
      {DOORS.map((door) => {
        const remembered = lane === door.lane;
        return (
          <section className={`lane-door lane-${door.lane}${remembered ? " remembered" : ""}`} key={door.lane}>
            <div className="lane-door-kicker">
              <span>{door.kicker}</span>
              {remembered && <em>Your lane</em>}
            </div>
            <Link className="lane-door-main" href={door.href} onClick={() => storeLane(door.lane)}>
              <door.Icon size={22} />
              <strong>{door.title}</strong>
              <span>{door.body}</span>
              <span className="lane-door-cta">Open <ArrowRight size={15} /></span>
            </Link>
            <div className="lane-door-links">
              {door.links.map((link) => (
                <Link href={link.href} key={link.href} onClick={() => storeLane(door.lane)}>
                  {link.label}
                </Link>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
