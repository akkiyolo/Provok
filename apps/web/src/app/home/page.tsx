import type { Metadata } from "next";
import { Suspense } from "react";

import { HomeFeed } from "@/components/posts/feeds";

export const metadata: Metadata = { title: "Home", description: "Takes, replies and debates from people you follow and across Provok." };

export default function HomePage() {
  return (
    <div className="pt-0 sm:pt-6">
      <Suspense>
        <HomeFeed />
      </Suspense>
    </div>
  );
}
