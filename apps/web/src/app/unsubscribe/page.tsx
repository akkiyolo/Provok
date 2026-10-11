import type { Metadata } from "next";
import { Suspense } from "react";

import { Unsubscribe } from "@/components/auth-pages";

export const metadata: Metadata = { title: "Unsubscribe", robots: { index: false } };

export default function UnsubscribePage() {
  return <Suspense><Unsubscribe /></Suspense>;
}
