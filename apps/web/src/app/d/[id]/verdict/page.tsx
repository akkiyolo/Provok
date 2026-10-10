import type { Metadata } from "next";
import { Suspense } from "react";

import { Spinner } from "@/components/ui";
import { VerdictView } from "@/components/verdict";
import { fetchDebatePublic } from "@/lib/server";

export async function generateMetadata({ params }: PageProps<"/d/[id]/verdict">): Promise<Metadata> {
  const { id } = await params;
  const d = await fetchDebatePublic(id);
  if (!d) return { title: "Verdict" };
  const w = d.verdict?.winner_position;
  const title = w ? `${w.toUpperCase()} wins: ${d.question}` : `Verdict: ${d.question}`;
  return {
    title,
    description: "See the AI judge's explained verdict, round-by-round scores and whether the crowd agreed.",
    openGraph: { title, images: [`/d/${d.id}/opengraph-image`] },
    twitter: { card: "summary_large_image", title, images: [`/d/${d.id}/opengraph-image`] },
  };
}

async function Route({ params }: { params: PageProps<"/d/[id]/verdict">["params"] }) {
  const { id } = await params;
  return <VerdictView id={id} />;
}

export default function VerdictPage({ params }: PageProps<"/d/[id]/verdict">) {
  return (
    <Suspense fallback={<div className="grid min-h-dvh place-items-center"><Spinner className="size-8 text-win" /></div>}>
      <Route params={params} />
    </Suspense>
  );
}
