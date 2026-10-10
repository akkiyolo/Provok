import type { Metadata } from "next";
import { Suspense } from "react";

import { ChallengesView } from "@/components/discover";
import { CardSkeleton } from "@/components/debate-card";

export const metadata: Metadata = {
  title: "Open challenges",
  description: "Questions waiting for someone brave enough to take the other side.",
};

export default function ChallengesPage() {
  return (
    <Suspense fallback={<div className="mx-auto grid max-w-7xl gap-5 px-4 pt-8 sm:px-6 lg:grid-cols-3"><CardSkeleton /><CardSkeleton /><CardSkeleton /></div>}>
      <ChallengesView />
    </Suspense>
  );
}
