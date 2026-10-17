"use client";

import { api, get } from "@/lib/api";

/**
 * Web push on this device. The browser keeps the subscription; the server keeps a copy per signed-in user.
 * Signing out forgets this device (server + browser), so the next person to sign in here starts with push off.
 */

export type PushState = "unsupported" | "needs-install" | "unavailable" | "blocked" | "off" | "on";

interface PushConfig {
  enabled: boolean;
  public_key: string | null;
}

let configPromise: Promise<PushConfig> | null = null;
function pushConfig(): Promise<PushConfig> {
  configPromise ??= get<PushConfig>("/push/config").catch((e) => {
    configPromise = null;
    throw e;
  });
  return configPromise;
}

function supported(): boolean {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window
    && "Notification" in window;
}

/** iPhone/iPad Safari only offers push to sites added to the Home Screen. */
function needsInstall(): boolean {
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  return ios && !window.matchMedia("(display-mode: standalone)").matches;
}

function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const b64 = (base64url + "=".repeat((4 - (base64url.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

function sameKey(sub: PushSubscription, publicKey: string): boolean {
  const current = sub.options.applicationServerKey;
  if (!current) return true;
  const a = new Uint8Array(current);
  const b = keyBytes(publicKey);
  return a.length === b.length && a.every((v, i) => v === b[i]);
}

async function existing(): Promise<PushSubscription | null> {
  const reg = await navigator.serviceWorker.getRegistration("/");
  return (await reg?.pushManager.getSubscription()) ?? null;
}

async function send(sub: PushSubscription): Promise<void> {
  const json = sub.toJSON();
  await api("/me/push-subscriptions", {
    method: "POST",
    body: { endpoint: json.endpoint, keys: { p256dh: json.keys?.p256dh, auth: json.keys?.auth } },
  });
}

export async function pushState(): Promise<PushState> {
  if (!supported()) return typeof window !== "undefined" && needsInstall() ? "needs-install" : "unsupported";
  const cfg = await pushConfig();
  if (!cfg.enabled) return "unavailable";
  if (Notification.permission === "denied") return "blocked";
  return Notification.permission === "granted" && (await existing()) ? "on" : "off";
}

/** Must run from a click: browsers only show the permission prompt for a user gesture. */
export async function enablePush(): Promise<PushState> {
  const cfg = await pushConfig();
  if (!cfg.enabled || !cfg.public_key) return "unavailable";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return permission === "denied" ? "blocked" : "off";
  const reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
  await navigator.serviceWorker.ready;
  let sub = await reg.pushManager.getSubscription();
  if (sub && !sameKey(sub, cfg.public_key)) {
    await sub.unsubscribe();
    sub = null;
  }
  sub ??= await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(cfg.public_key) });
  await send(sub);
  return "on";
}

export async function disablePush(): Promise<PushState> {
  const sub = await existing();
  if (sub) {
    await api("/me/push-subscriptions", { method: "DELETE", body: { endpoint: sub.endpoint } }).catch(() => undefined);
    await sub.unsubscribe();
  }
  return "off";
}

/**
 * On sign-in/page load: re-send this device's subscription (the server drops them on "sign out everywhere"
 * and when a browser rotates its endpoint), and move to a new key if the server's VAPID key changed.
 */
export async function syncPush(): Promise<void> {
  if (!supported() || Notification.permission !== "granted") return;
  const sub = await existing();
  if (!sub) return;
  const cfg = await pushConfig();
  if (!cfg.enabled || !cfg.public_key) return;
  if (!sameKey(sub, cfg.public_key)) {
    await sub.unsubscribe();
    await enablePush();
    return;
  }
  await send(sub);
}

/** Before signing out: this device stops getting the account's notifications. */
export async function forgetPushDevice(): Promise<void> {
  if (!supported()) return;
  await disablePush();
}
