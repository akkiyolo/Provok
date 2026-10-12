import type { Metadata } from "next";
import { Suspense } from "react";

import { TagFeed } from "@/components/posts/feeds";

export async function generateMetadata({ params }: PageProps<"/tag/[tag]">): Promise<Metadata> {
  const { tag } = await params;
  const t = decodeURIComponent(tag).toLowerCase();
  return { title: `#${t}`, description: `Posts tagged #${t} on Provok.`, alternates: { canonical: `/tag/${encodeURIComponent(t)}` } };
}

async function TagRoute({ params }: { params: PageProps<"/tag/[tag]">["params"] }) {
  const { tag } = await params;
  return <TagFeed tag={decodeURIComponent(tag).toLowerCase()} />;
}

export default function TagPage({ params }: PageProps<"/tag/[tag]">) {
  return (
    <Suspense>
      <TagRoute params={params} />
    </Suspense>
  );
}
