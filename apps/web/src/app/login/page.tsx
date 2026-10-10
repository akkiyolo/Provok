import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthPage } from "@/components/auth-pages";

export const metadata: Metadata = { title: "Sign in", robots: { index: false } };

export default function LoginPage() {
  return <Suspense><AuthPage mode="login" /></Suspense>;
}
