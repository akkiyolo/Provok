import type { Instrumentation } from "next";

import { SENTRY_DSN, SENTRY_OPTIONS } from "@/lib/monitoring";

export async function register() {
  if (!SENTRY_DSN) return;
  const Sentry = await import("@sentry/nextjs");
  Sentry.init(SENTRY_OPTIONS);
}

export const onRequestError: Instrumentation.onRequestError = async (...args) => {
  if (!SENTRY_DSN) return;
  const Sentry = await import("@sentry/nextjs");
  Sentry.captureRequestError(...args);
};
