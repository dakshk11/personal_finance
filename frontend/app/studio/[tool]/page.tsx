import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { StudioToolHost } from "@/components/studio/StudioToolHost";
import { DEFAULT_STUDIO_TOOL, STUDIO_TOOLS, isStudioToolSlug, studioToolLabel } from "@/lib/studio-tools";

type PageProps = { params: Promise<{ tool: string }> };

export function generateStaticParams() {
  return STUDIO_TOOLS.filter((tool) => tool.slug !== DEFAULT_STUDIO_TOOL).map((tool) => ({ tool: tool.slug }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { tool } = await params;
  if (!isStudioToolSlug(tool)) return { title: "FinanceOS Studio" };
  return { title: `${studioToolLabel(tool)} · FinanceOS Studio` };
}

export default async function StudioToolPage({ params }: PageProps) {
  const { tool } = await params;
  if (tool === DEFAULT_STUDIO_TOOL) redirect("/studio");
  if (!isStudioToolSlug(tool)) notFound();
  return <StudioToolHost slug={tool} />;
}
