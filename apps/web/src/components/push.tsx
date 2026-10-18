"use client";

import { useEffect, useState } from "react";

import { useToast } from "@/components/toast";
import { Button } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { disablePush, enablePush, pushState, type PushState } from "@/lib/push";

function usePushState() {
  const [state, setState] = useState<PushState | null>(null);
  useEffect(() => {
    let live = true;
    pushState().then((s) => live && setState(s)).catch(() => live && setState("unavailable"));
    return () => {
      live = false;
    };
  }, []);
  return [state, setState] as const;
}

const HINT: Record<PushState, string> = {
  unsupported: "This browser can't show push notifications.",
  "needs-install": "On iPhone and iPad: tap Share → Add to Home Screen, open Provok from there, then turn this on.",
  unavailable: "",
  blocked: "Notifications are blocked for Provok. Allow them in your browser's site settings, then come back.",
  off: "Your turn, challenges, verdicts, replies and messages, even when Provok is closed.",
  on: "Your turn, challenges, verdicts, replies and messages, even when Provok is closed.",
};

/** The Settings row: a switch for push on this device. Hidden when the server has push turned off. */
export function PushSetting() {
  const toast = useToast();
  const [state, setState] = usePushState();
  const [busy, setBusy] = useState(false);
  if (state === null || state === "unavailable") return null;
  const on = state === "on";
  const canToggle = state === "on" || state === "off";
  const toggle = async () => {
    setBusy(true);
    try {
      const next = on ? await disablePush() : await enablePush();
      setState(next);
      if (next === "on") toast("Push notifications on for this device.", "success");
      else if (on) toast("Push notifications off for this device.", "success");
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <label className="mt-5 flex cursor-pointer items-start justify-between gap-4 border-t border-line pt-5">
      <span className="flex flex-col gap-1">
        <span className="text-[15px] font-medium">Push notifications on this device</span>
        <span className="text-[13px] text-dim">{HINT[state]}</span>
      </span>
      {canToggle && (
        <button type="button" role="switch" aria-checked={on} disabled={busy} onClick={() => void toggle()}
          className={`relative mt-0.5 h-7 w-12 shrink-0 rounded-full border transition-colors disabled:opacity-60 ${
            on ? "border-text bg-text" : "border-line bg-surface"}`}>
          <span className={`absolute left-0 top-0.5 size-[22px] rounded-full transition-transform ${
            on ? "translate-x-[22px] bg-surface" : "translate-x-0.5 bg-dim"}`} />
        </button>
      )}
    </label>
  );
}

const DISMISSED = "provok:push-prompt-dismissed";

/** A card on the Notifications page for people who haven't decided yet. Dismissal is remembered on this device. */
export function PushPrompt() {
  const toast = useToast();
  const [state, setState] = usePushState();
  const [dismissed, setDismissed] = useState(true);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    try {
      setTimeout(() => setDismissed(localStorage.getItem(DISMISSED) === "1"), 0);
    } catch {
      /* storage blocked: keep it hidden */
    }
  }, []);
  if (dismissed || state !== "off" || typeof Notification === "undefined" || Notification.permission !== "default") {
    return null;
  }
  const dismiss = () => {
    setDismissed(true);
    try {
      localStorage.setItem(DISMISSED, "1");
    } catch {
      /* private mode */
    }
  };
  return (
    <div className="mb-4 flex flex-col gap-3 rounded-2xl border border-line bg-surface px-4 py-4 sm:flex-row sm:items-center">
      <span className="flex-1">
        <span className="block font-semibold">Don&rsquo;t miss your turn.</span>
        <span className="block text-sm text-dim">Get a notification when it&rsquo;s your move, someone challenges you, or the verdict is in.</span>
      </span>
      <span className="flex shrink-0 gap-2">
        <Button size="sm" variant="outline" onClick={dismiss}>Not now</Button>
        <Button size="sm" loading={busy} onClick={async () => {
          setBusy(true);
          try {
            const next = await enablePush();
            setState(next);
            if (next === "on") toast("You'll get a ping when it matters.", "success");
            else dismiss();
          } catch (e) {
            toast(errorMessage(e), "error");
          } finally {
            setBusy(false);
          }
        }}>Turn on</Button>
      </span>
    </div>
  );
}
