import { reportError, SENTRY_DSN } from "@/lib/monitoring";

if (SENTRY_DSN) {
  window.addEventListener("error", (e) => void reportError(e.error ?? e.message));
  window.addEventListener("unhandledrejection", (e) => void reportError(e.reason));
}
