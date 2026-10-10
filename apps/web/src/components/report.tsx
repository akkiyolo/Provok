"use client";

import { useState } from "react";

import { useToast } from "@/components/toast";
import { Button, Sheet } from "@/components/ui";
import { errorMessage, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cx } from "@/lib/format";

const REASONS: { value: string; label: string }[] = [
  { value: "harassment", label: "Harassment or personal attack" },
  { value: "hate", label: "Hate speech" },
  { value: "misinformation", label: "Deliberate misinformation" },
  { value: "spam", label: "Spam" },
  { value: "sexual", label: "Sexual content" },
  { value: "violence", label: "Violence or threats" },
  { value: "cheating", label: "Cheating / prompt injection" },
  { value: "other", label: "Something else" },
];

export function ReportButton({ targetType, targetId, label }: { targetType: "debate" | "turn" | "user"; targetId: string; label?: string }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [details, setDetails] = useState("");
  const [busy, setBusy] = useState(false);
  const { requireAuth } = useAuth();
  const toast = useToast();

  const submit = async () => {
    setBusy(true);
    try {
      await post("/reports", { target_type: targetType, target_id: targetId, reason, details: details || null });
      toast("Thanks — our moderators will take a look.", "success");
      setOpen(false);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button type="button" onClick={() => requireAuth("Sign in to report content.") && setOpen(true)}
        className="inline-flex items-center gap-1 text-[11px] text-faint hover:text-danger" aria-label={`Report this ${targetType}`}>
        <svg viewBox="0 0 16 16" className="size-3" fill="currentColor" aria-hidden><path d="M3 1h1v14H3zm2 1h8l-2 3 2 3H5z" /></svg>
        {label ?? "Report"}
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} title="Report">
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-sm text-dim">What&apos;s wrong with this {targetType}?</legend>
          {REASONS.map((r) => (
            <label key={r.value} className={cx("flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-2.5 text-sm",
              reason === r.value ? "border-text bg-surface-2" : "border-line hover:bg-surface-2")}>
              <input type="radio" name="reason" value={r.value} checked={reason === r.value} onChange={() => setReason(r.value)} className="accent-[var(--for)]" />
              {r.label}
            </label>
          ))}
        </fieldset>
        <textarea value={details} onChange={(e) => setDetails(e.target.value)} maxLength={1000} rows={3}
          placeholder="Anything else we should know? (optional)"
          className="mt-3 w-full rounded-xl border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-text/60" />
        <Button className="mt-4 w-full" variant="danger" disabled={!reason} loading={busy} onClick={submit}>Send report</Button>
      </Sheet>
    </>
  );
}
