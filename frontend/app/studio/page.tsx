import type { Metadata } from "next";
import { StudioToolHost } from "@/components/studio/StudioToolHost";
import { DEFAULT_STUDIO_TOOL, studioToolLabel } from "@/lib/studio-tools";

export const metadata: Metadata = {
  title: `${studioToolLabel(DEFAULT_STUDIO_TOOL)} · FinanceOS Studio`
};

export default function StudioIndexPage() {
  return <StudioToolHost slug={DEFAULT_STUDIO_TOOL} />;
}
