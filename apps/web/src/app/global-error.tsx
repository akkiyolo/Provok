"use client";

import { useEffect } from "react";

import { reportError } from "@/lib/monitoring";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    void reportError(error);
  }, [error]);
  return (
    <html lang="en">
      <body style={{ margin: 0, background: "#0a0a0b", color: "#f2efe9", fontFamily: "system-ui, sans-serif", minHeight: "100dvh", display: "grid", placeItems: "center", textAlign: "center", padding: 24 }}>
        <div>
          <h1 style={{ fontSize: 40, margin: 0, letterSpacing: -1 }}>Provok hit a snag.</h1>
          <p style={{ color: "#9a978f" }}>Please reload the page. If it keeps happening, we&apos;re already on it.</p>
          <button onClick={reset} style={{ marginTop: 12, padding: "12px 22px", borderRadius: 999, border: 0, background: "#f2efe9", color: "#0a0a0b", fontWeight: 700, cursor: "pointer" }}>
            Reload
          </button>
        </div>
      </body>
    </html>
  );
}
