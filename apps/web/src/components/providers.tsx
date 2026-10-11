"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LazyMotion, MotionConfig } from "motion/react";
import { useEffect, useState } from "react";

import { AuthGateSheet } from "@/components/auth-forms";
import { ToastProvider } from "@/components/toast";
import { ApiError } from "@/lib/api";
import { AuthProvider } from "@/lib/auth";
import { isAndroidApp } from "@/lib/platform";

const loadMotionFeatures = () => import("@/lib/motion-features").then((mod) => mod.default);

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            refetchOnWindowFocus: false,
            retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 2,
          },
        },
      }),
  );
  // Record "inside the Android app" on whichever page the app opens, so later pages (which no longer carry
  // ?app=android or the android-app:// referrer) still know.
  useEffect(() => void isAndroidApp(), []);
  return (
    <QueryClientProvider client={client}>
      <LazyMotion features={loadMotionFeatures} strict>
        <MotionConfig reducedMotion="user">
          <ToastProvider>
            <AuthProvider>
              {children}
              <AuthGateSheet />
            </AuthProvider>
          </ToastProvider>
        </MotionConfig>
      </LazyMotion>
    </QueryClientProvider>
  );
}
