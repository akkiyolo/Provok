/**
 * Error reporting (Sentry). Inert unless NEXT_PUBLIC_SENTRY_DSN is set.
 *
 * In the browser the SDK (~100 KB gzipped) is only downloaded when the first error actually happens, so it costs
 * nothing on a healthy page load. Global errors are caught by our own listeners (instrumentation-client.ts), which
 * is why Sentry's GlobalHandlers integration is turned off here: it would only start after the first error anyway.
 */
export const SENTRY_DSN = process.env.NEXT_PUBLIC_SENTRY_DSN || undefined;

export const SENTRY_OPTIONS = {
  dsn: SENTRY_DSN,
  environment: process.env.NEXT_PUBLIC_SENTRY_ENV || process.env.NODE_ENV,
  release: process.env.NEXT_PUBLIC_SENTRY_RELEASE || undefined,
  tracesSampleRate: 0,
  sendDefaultPii: false,
};

type SentryModule = typeof import("@sentry/nextjs");
let loading: Promise<SentryModule> | null = null;

function loadBrowserSentry(): Promise<SentryModule> {
  loading ??= import("@sentry/nextjs").then((Sentry) => {
    Sentry.init({ ...SENTRY_OPTIONS, integrations: (defaults) => defaults.filter((i) => i.name !== "GlobalHandlers") });
    return Sentry;
  });
  return loading;
}

export async function reportError(error: unknown): Promise<void> {
  if (!SENTRY_DSN) return;
  try {
    (await loadBrowserSentry()).captureException(error);
  } catch {
    // Reporting must never break the page that is already showing an error.
  }
}
