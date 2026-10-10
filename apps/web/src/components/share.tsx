"use client";

import { useToast } from "@/components/toast";
import { Button } from "@/components/ui";
import { track } from "@/lib/analytics";

export function shareUrl(path: string): string {
  const origin = typeof window !== "undefined" ? window.location.origin : process.env.NEXT_PUBLIC_SITE_URL ?? "";
  const sep = path.includes("?") ? "&" : "?";
  return `${origin}${path}${sep}ref=share`;
}

export function useShare() {
  const toast = useToast();
  return async (opts: { title: string; text: string; path: string; debateId?: string; kind?: string }) => {
    const url = shareUrl(opts.path);
    track("share_clicked", { kind: opts.kind ?? "debate" }, opts.debateId);
    try {
      if (navigator.share) {
        await navigator.share({ title: opts.title, text: opts.text, url });
        track("share_completed", { kind: opts.kind ?? "debate", via: "native" }, opts.debateId);
        return;
      }
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
    }
    try {
      await navigator.clipboard.writeText(`${opts.text} ${url}`);
      toast("Link copied. Paste it anywhere.", "success");
      track("share_completed", { kind: opts.kind ?? "debate", via: "clipboard" }, opts.debateId);
    } catch {
      toast(url, "info");
    }
  };
}

export function ShareButtons({ title, text, path, debateId, kind }: { title: string; text: string; path: string; debateId?: string; kind?: string }) {
  const share = useShare();
  const url = encodeURIComponent(shareUrl(path));
  const msg = encodeURIComponent(text);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button size="sm" variant="primary" onClick={() => share({ title, text, path, debateId, kind })}>Share</Button>
      <a className="inline-flex h-8 items-center rounded-full border border-line-strong px-3 text-[13px] font-semibold hover:bg-surface-2"
        href={`https://wa.me/?text=${msg}%20${url}`} target="_blank" rel="noopener noreferrer"
        onClick={() => track("share_clicked", { kind: kind ?? "debate", via: "whatsapp" }, debateId)}>
        WhatsApp
      </a>
      <a className="inline-flex h-8 items-center rounded-full border border-line-strong px-3 text-[13px] font-semibold hover:bg-surface-2"
        href={`https://twitter.com/intent/tweet?text=${msg}&url=${url}`} target="_blank" rel="noopener noreferrer"
        onClick={() => track("share_clicked", { kind: kind ?? "debate", via: "x" }, debateId)}>
        Post on X
      </a>
    </div>
  );
}
