"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui";
import { reportError } from "@/lib/monitoring";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
    void reportError(error);
  }, [error]);
  return (
    <div className="stage grain flex min-h-[70dvh] flex-col items-center justify-center gap-4 px-6 text-center">
      <p className="font-mono text-[12px] font-bold tracking-[0.2em] text-faint">TECHNICAL TIMEOUT</p>
      <h1 className="font-display text-[clamp(2.2rem,7vw,4rem)] font-extrabold leading-[0.9]">Something broke on our side.</h1>
      <p className="max-w-md text-dim">It&apos;s been logged. Try again — debates are saved server-side, so you haven&apos;t lost anything.</p>
      {error.digest && <p className="font-mono text-[11px] text-faint">ref {error.digest}</p>}
      <div className="mt-2 flex gap-3">
        <Button onClick={reset}>Try again</Button>
        <Button href="/" variant="outline">Home</Button>
      </div>
    </div>
  );
}
