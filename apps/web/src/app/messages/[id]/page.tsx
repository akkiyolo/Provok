import type { Metadata } from "next";
import { Suspense } from "react";

import { ThreadView } from "@/components/messages";

export const metadata: Metadata = { title: "Messages", robots: { index: false } };

async function ThreadRoute({ params }: { params: PageProps<"/messages/[id]">["params"] }) {
  const { id } = await params;
  return <ThreadView id={id} />;
}

export default function ThreadPage({ params }: PageProps<"/messages/[id]">) {
  return (
    <Suspense>
      <ThreadRoute params={params} />
    </Suspense>
  );
}
