import {
  Activity,
  Bot,
  CandlestickChart,
  FolderArchive,
  Gauge,
  LineChart,
  Newspaper,
  PieChart,
  Search,
  Sparkles,
  TrendingUp,
  WalletCards
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type StudioToolSlug =
  | "recommendation-agent"
  | "retirement-plan"
  | "personal-cfo"
  | "research-prompts"
  | "wheel-strategy"
  | "portfolio-sync"
  | "simulated-portfolio"
  | "rsi-playbook"
  | "breakout-scanner"
  | "smart-candles"
  | "composite-signal"
  | "optitrade-lab"
  | "equity-research"
  | "earnings-agent"
  | "wheel-scanner"
  | "sector-rotation";

export type StudioTool = {
  slug: StudioToolSlug;
  label: string;
  Icon: LucideIcon;
};

/** The Recommendation Agent is first because it is also the Studio index route. */
export const STUDIO_TOOLS: StudioTool[] = [
  { slug: "recommendation-agent", label: "Recommendation Agent", Icon: Sparkles },
  { slug: "retirement-plan", label: "AI Planner", Icon: Bot },
  { slug: "personal-cfo", label: "Personal CFO", Icon: FolderArchive },
  { slug: "research-prompts", label: "Research Prompts", Icon: Search },
  { slug: "wheel-strategy", label: "Wheel Strategy", Icon: TrendingUp },
  { slug: "portfolio-sync", label: "Portfolio Sync", Icon: WalletCards },
  { slug: "simulated-portfolio", label: "Simulated Portfolio", Icon: PieChart },
  { slug: "rsi-playbook", label: "RSI Playbook", Icon: Gauge },
  { slug: "breakout-scanner", label: "Breakout Scanner", Icon: CandlestickChart },
  { slug: "smart-candles", label: "Smart Candles", Icon: CandlestickChart },
  { slug: "composite-signal", label: "Composite Signal Algorithm", Icon: Activity },
  { slug: "optitrade-lab", label: "OptiTrade Lab", Icon: CandlestickChart },
  { slug: "equity-research", label: "Equity Research", Icon: LineChart },
  { slug: "earnings-agent", label: "Earnings Agent", Icon: Newspaper },
  { slug: "wheel-scanner", label: "Wheel Scanner", Icon: TrendingUp },
  { slug: "sector-rotation", label: "Sector Rotation", Icon: Gauge }
];

export const DEFAULT_STUDIO_TOOL: StudioToolSlug = "recommendation-agent";

const SLUGS = new Set<string>(STUDIO_TOOLS.map((tool) => tool.slug));

export function isStudioToolSlug(value: string): value is StudioToolSlug {
  return SLUGS.has(value);
}

export function studioToolLabel(slug: StudioToolSlug): string {
  return STUDIO_TOOLS.find((tool) => tool.slug === slug)?.label ?? "Studio";
}
