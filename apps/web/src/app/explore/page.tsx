import type { Metadata } from "next";

import { ExploreView } from "@/components/explore";

export const metadata: Metadata = { title: "Explore", description: "Today's debate, trending topics, live debates and people to follow on Provok." };

export default function ExplorePage() {
  return <ExploreView />;
}
