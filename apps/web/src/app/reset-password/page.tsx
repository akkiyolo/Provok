import type { Metadata } from "next";
import { Suspense } from "react";

import { ResetPassword } from "@/components/auth-pages";

export const metadata: Metadata = { title: "Choose a new password", robots: { index: false } };

export default function ResetPasswordPage() {
  return <Suspense><ResetPassword /></Suspense>;
}
