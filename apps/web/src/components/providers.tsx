"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LazyMotion, MotionConfig } from "motion/react";
import { useState } from "react";

import { AuthGateSheet } from "@/components/auth-forms";
import { ToastProvider } from "@/components/toast";
import { ApiError } from "@/lib/api";
import { AuthProvider } from "@/lib/auth";

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
