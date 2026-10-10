import type { Metadata } from "next";
import { Suspense } from "react";

import { SearchView } from "@/components/discover";

export const metadata: Metadata = { title: "Search", robots: { index: false } };

export default function SearchPage() {
  return <Suspense><SearchView /></Suspense>;
}
