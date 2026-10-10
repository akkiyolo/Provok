import type { Metadata } from "next";
import { Suspense } from "react";

import { CreateWizard } from "@/components/create";

export const metadata: Metadata = { title: "Start a debate", robots: { index: false } };

export default function NewDebatePage() {
  return (
    // Reserve the wizard's height so the footer doesn't jump when it renders (layout shift).
    <Suspense fallback={<div className="min-h-[85dvh]" aria-busy="true" />}>
      <CreateWizard />
    </Suspense>
  );
}
