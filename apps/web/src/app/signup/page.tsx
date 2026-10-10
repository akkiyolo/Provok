import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthPage } from "@/components/auth-pages";

export const metadata: Metadata = { title: "Join Provok", description: "Create a free account. Your first 3 AI debates are on us." };

export default function SignupPage() {
  return <Suspense><AuthPage mode="signup" /></Suspense>;
}
