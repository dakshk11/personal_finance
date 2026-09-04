import { permanentRedirect } from "next/navigation";
import { isStudioToolSlug } from "@/lib/studio-tools";

type PageProps = { searchParams: Promise<{ tab?: string }> };

/** The Studio moved to /studio/[tool]. Old links, including ?tab= deep links, keep working. */
export default async function AIAdvisorRedirect({ searchParams }: PageProps) {
  const { tab } = await searchParams;
  if (tab && isStudioToolSlug(tab)) permanentRedirect(`/studio/${tab}`);
  permanentRedirect("/studio");
}
