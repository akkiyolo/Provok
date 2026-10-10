import type { Metadata } from "next";
import { Suspense } from "react";

import { VerifyEmail } from "@/components/auth-pages";

export const metadata: Metadata = { title: "Confirm your email", robots: { index: false } };

export default function VerifyEmailPage() {
  return <Suspense><VerifyEmail /></Suspense>;
}
