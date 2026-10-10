import { Suspense } from "react";

import { OAuthCallback } from "@/components/auth-pages";

export default function CallbackPage() {
  return <Suspense><OAuthCallback /></Suspense>;
}
