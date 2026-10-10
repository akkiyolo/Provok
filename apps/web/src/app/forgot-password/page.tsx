import type { Metadata } from "next";

import { ForgotPassword } from "@/components/auth-pages";

export const metadata: Metadata = { title: "Reset your password", robots: { index: false } };

export default function ForgotPasswordPage() {
  return <ForgotPassword />;
}
