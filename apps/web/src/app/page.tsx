import { Suspense } from "react";

import { CardSkeleton } from "@/components/debate-card";
import { Feed, HomeHero } from "@/components/feed";

export default function HomePage() {
  return (
    <div className="mx-auto max-w-7xl px-4 pt-2 sm:px-6 sm:pt-6">
      <Suspense>
        <HomeHero />
      </Suspense>
      <Suspense fallback={<div className="grid gap-5 lg:grid-cols-3"><CardSkeleton variant="hero" /><CardSkeleton /><CardSkeleton /></div>}>
        <Feed />
      </Suspense>
    </div>
  );
}
