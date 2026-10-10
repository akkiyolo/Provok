import type { Metadata } from "next";
import { Suspense } from "react";

import { CreateWizard } from "@/components/create";

export const metadata: Metadata = { title: "Start a debate", robots: { index: false } };

export default function NewDebatePage() {
  return (
    <Suspense>
      <CreateWizard />
    </Suspense>
  );
}
