import type { Metadata } from "next";
import { Suspense } from "react";

import { LeaderboardView } from "@/components/discover";

export const metadata: Metadata = {
  title: "Leaderboard — who argues best?",
  description: "Top human debaters by Elo, and which AI model wins the most debates — overall and by topic.",
};

export default function LeaderboardPage() {
  return <Suspense><LeaderboardView /></Suspense>;
}
