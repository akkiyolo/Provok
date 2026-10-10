import type { Metadata } from "next";
import { Suspense } from "react";

import { Arena, ArenaSkeleton } from "@/components/arena/arena";
import { fetchDebatePublic } from "@/lib/server";

export async function generateMetadata({ params }: PageProps<"/d/[id]">): Promise<Metadata> {
  const { id } = await params;
  const d = await fetchDebatePublic(id);
  if (!d) return { title: "Debate", robots: { index: false } };
  const forSide = d.sides.find((s) => s.position === "for");
  const againstSide = d.sides.find((s) => s.position === "against");
  const name = (s: typeof forSide) =>
    s?.participant_type === "swarm" ? s.model?.display_name ?? "AI" : s?.user?.display_name ?? "an open seat";
  const description = d.status === "completed"
    ? `The verdict is in: ${name(forSide)} (FOR) vs ${name(againstSide)} (AGAINST). See who won and why.`
    : `${name(forSide)} (FOR) vs ${name(againstSide)} (AGAINST). Watch live and vote every round on Provok.`;
  return {
    title: d.question,
    description,
    alternates: { canonical: `/d/${d.id}` },
    openGraph: { title: d.question, description, type: "article", url: `/d/${d.id}` },
    twitter: { card: "summary_large_image", title: d.question, description },
  };
}

async function ArenaRoute({ params }: { params: PageProps<"/d/[id]">["params"] }) {
  const { id } = await params;
  return <Arena id={id} />;
}

export default function DebatePage({ params }: PageProps<"/d/[id]">) {
  return (
    <Suspense fallback={<ArenaSkeleton />}>
      <ArenaRoute params={params} />
    </Suspense>
  );
}
