import type { Metadata } from "next";
import { Suspense } from "react";

import { PostThread } from "@/components/posts/feeds";
import { PostSkeleton } from "@/components/posts/post-card";
import { fetchPostPublic } from "@/lib/server";

export async function generateMetadata({ params }: PageProps<"/p/[id]">): Promise<Metadata> {
  const { id } = await params;
  const p = await fetchPostPublic(id);
  if (!p) return { title: "Post", robots: { index: false } };
  const who = p.author ? `${p.author.display_name} (@${p.author.username})` : "Someone";
  const text = (p.text ?? (p.media.length ? "Shared a photo" : "")).slice(0, 200);
  const title = `${who} on Provok`;
  const image = p.media[0]?.url;
  return {
    title,
    description: text,
    alternates: { canonical: `/p/${p.id}` },
    openGraph: { title, description: text, type: "article", url: `/p/${p.id}`, ...(image ? { images: [{ url: image }] } : {}) },
    twitter: { card: image ? "summary_large_image" : "summary", title, description: text, ...(image ? { images: [image] } : {}) },
  };
}

async function ThreadRoute({ params }: { params: PageProps<"/p/[id]">["params"] }) {
  const { id } = await params;
  return <PostThread id={id} />;
}

export default function PostPage({ params }: PageProps<"/p/[id]">) {
  return (
    <Suspense fallback={<div className="mx-auto max-w-2xl sm:px-6 sm:pt-6"><PostSkeleton /></div>}>
      <ThreadRoute params={params} />
    </Suspense>
  );
}
