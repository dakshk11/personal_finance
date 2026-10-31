"use client";

import dynamic from "next/dynamic";
import { Loader2 } from "lucide-react";
import type { StudioToolSlug } from "@/lib/studio-tools";
import { useStudio } from "./StudioContext";

function ToolLoading() {
  return (
    <section className="dashboard-panel empty-proposal">
      <Loader2 size={30} className="spin-icon" />
      <h2>Loading tool</h2>
    </section>
  );
}

/**
 * Each tool is loaded on demand so a Studio route only ships the tool it renders.
 * Previously all sixteen were static imports in one page component.
 */
const AIPlannerTool = dynamic(() => import("@/components/AIPlannerTool").then((m) => m.AIPlannerTool), { loading: ToolLoading });
const BreakawayTool = dynamic(() => import("@/components/BreakawayTool").then((m) => m.BreakawayTool), { loading: ToolLoading });
const BreakoutScannerTool = dynamic(() => import("@/components/BreakoutScannerTool").then((m) => m.BreakoutScannerTool), { loading: ToolLoading });
const CompositeSignalTool = dynamic(() => import("@/components/CompositeSignalTool").then((m) => m.CompositeSignalTool), { loading: ToolLoading });
const EarningsAgentTool = dynamic(() => import("@/components/EarningsAgentTool").then((m) => m.EarningsAgentTool), { loading: ToolLoading });
const OptionStrategyTool = dynamic(() => import("@/components/OptionStrategyTool").then((m) => m.OptionStrategyTool), { loading: ToolLoading });
const OptiTradeLabTool = dynamic(() => import("@/components/OptiTradeLabTool").then((m) => m.OptiTradeLabTool), { loading: ToolLoading });
const PersonalCFOTool = dynamic(() => import("@/components/PersonalCFOTool").then((m) => m.PersonalCFOTool), { loading: ToolLoading });
const PortfolioSyncTool = dynamic(() => import("@/components/PortfolioSyncTool").then((m) => m.PortfolioSyncTool), { loading: ToolLoading });
const RecommendationAgentTool = dynamic(() => import("@/components/RecommendationAgentTool").then((m) => m.RecommendationAgentTool), { loading: ToolLoading });
const ResearchPromptsTool = dynamic(() => import("@/components/ResearchPromptsTool").then((m) => m.ResearchPromptsTool), { loading: ToolLoading });
const RSIPlaybookTool = dynamic(() => import("@/components/RSIPlaybookTool").then((m) => m.RSIPlaybookTool), { loading: ToolLoading });
const SectorRotationTool = dynamic(() => import("@/components/SectorRotationTool").then((m) => m.SectorRotationTool), { loading: ToolLoading });
const SimulatedPortfolioTool = dynamic(() => import("@/components/SimulatedPortfolioTool").then((m) => m.SimulatedPortfolioTool), { loading: ToolLoading });
const StageDeskTool = dynamic(() => import("@/components/StageDeskTool").then((m) => m.StageDeskTool), { loading: ToolLoading });
const SmartCandleTool = dynamic(() => import("@/components/SmartCandleTool").then((m) => m.SmartCandleTool), { loading: ToolLoading });
const StockAnalysisTool = dynamic(() => import("@/components/StockAnalysisTool").then((m) => m.StockAnalysisTool), { loading: ToolLoading });
const WheelScannerTool = dynamic(() => import("@/components/WheelScannerTool").then((m) => m.WheelScannerTool), { loading: ToolLoading });

export function StudioToolHost({ slug }: { slug: StudioToolSlug }) {
  const studio = useStudio();

  switch (slug) {
    case "recommendation-agent":
      return (
        <RecommendationAgentTool
          keyStatus={studio.keyStatus}
          tipRanksKeyStatus={studio.tipRanksKeyStatus}
          alpacaKeyStatus={studio.alpacaKeyStatus}
          lunarCrushKeyStatus={studio.lunarCrushKeyStatus}
          nvidiaKeyStatus={studio.nvidiaKeyStatus}
          tipRanksApiKey={studio.tipRanksApiKey}
          decisionContext={studio.recommendationContext}
        />
      );
    case "retirement-plan":
      return <AIPlannerTool />;
    case "personal-cfo":
      return <PersonalCFOTool keyStatus={studio.keyStatus} />;
    case "research-prompts":
      return <ResearchPromptsTool keyStatus={studio.keyStatus} />;
    case "wheel-strategy":
      return <OptionStrategyTool />;
    case "portfolio-sync":
      return <PortfolioSyncTool />;
    case "simulated-portfolio":
      return <SimulatedPortfolioTool />;
    case "rsi-playbook":
      return <RSIPlaybookTool />;
    case "breakout-scanner":
      return <BreakoutScannerTool />;
    case "breakaway":
      return <BreakawayTool />;
    case "stage-desk":
      return <StageDeskTool />;
    case "smart-candles":
      return <SmartCandleTool />;
    case "composite-signal":
      return <CompositeSignalTool />;
    case "optitrade-lab":
      return <OptiTradeLabTool alpacaKeyStatus={studio.alpacaKeyStatus} />;
    case "equity-research":
      return <StockAnalysisTool keyStatus={studio.keyStatus} />;
    case "earnings-agent":
      return <EarningsAgentTool keyStatus={studio.keyStatus} />;
    case "wheel-scanner":
      return (
        <WheelScannerTool
          keyStatus={studio.keyStatus}
          nvidiaKeyStatus={studio.nvidiaKeyStatus}
          alpacaKeyStatus={studio.alpacaKeyStatus}
          isActive
        />
      );
    case "sector-rotation":
      return <SectorRotationTool />;
  }
}
