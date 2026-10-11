"use client";

import { useSyncExternalStore } from "react";

/**
 * Are we running inside the Provok Android app (a Trusted Web Activity)?
 *
 * Google Play doesn't allow selling digital goods through an outside payment provider inside an app, or pointing
 * users to buy elsewhere, so the app hides credit purchases. The app's launch URL carries ?app=android, and Chrome
 * sets document.referrer to android-app://<package> when the app opens a page (including links opened in the app).
 * The answer is kept in sessionStorage: it belongs to the app's own session, so it never leaks into the user's
 * normal Chrome tabs, which share localStorage and cookies with the app.
 */
const KEY = "provok:android-app";

function detect(): boolean {
  try {
    if (sessionStorage.getItem(KEY) === "1") return true;
    const fromApp = new URLSearchParams(window.location.search).get("app") === "android"
      || document.referrer.startsWith("android-app://");
    if (fromApp) sessionStorage.setItem(KEY, "1");
    return fromApp;
  } catch {
    return document.referrer.startsWith("android-app://");
  }
}

/** Shown instead of the server's "Top up" message inside the app (no pointers to buying elsewhere). */
export const IN_APP_NO_CREDITS = "Not enough credits for this AI debate. Debates against people are always free.";

let cached: boolean | null = null;
const noSubscribe = () => () => {};

export function isAndroidApp(): boolean {
  if (typeof window === "undefined") return false;
  cached ??= detect();
  return cached;
}

/** False during SSR and hydration, then the real answer, so server and first client render always match. */
export function useIsAndroidApp(): boolean {
  return useSyncExternalStore(noSubscribe, isAndroidApp, () => false);
}
