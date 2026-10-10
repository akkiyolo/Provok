"use client";

import { AnimatePresence, m } from "motion/react";
import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { cx } from "@/lib/format";

type Tone = "info" | "success" | "error" | "for" | "against";
interface Toast {
  id: number;
  message: string;
  tone: Tone;
  action?: { label: string; onClick: () => void };
}

const ToastContext = createContext<((message: string, tone?: Tone, action?: Toast["action"]) => void) | null>(null);
let nextId = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((message: string, tone: Tone = "info", action?: Toast["action"]) => {
    const id = ++nextId;
    setToasts((t) => [...t.slice(-3), { id, message, tone, action }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), action ? 7000 : 4200);
  }, []);
  const value = useMemo(() => push, [push]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-[calc(76px+env(safe-area-inset-bottom))] z-[90] flex flex-col items-center gap-2 px-4 sm:bottom-6">
        <AnimatePresence>
          {toasts.map((t) => (
            <m.div key={t.id} layout initial={{ y: 16, opacity: 0, scale: 0.96 }} animate={{ y: 0, opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
              className={cx(
                "pointer-events-auto flex max-w-md items-center gap-3 rounded-2xl border bg-surface-2 px-4 py-3 text-sm shadow-2xl",
                t.tone === "error" ? "border-danger/50" : t.tone === "success" ? "border-ok/40" :
                  t.tone === "for" ? "border-for/50" : t.tone === "against" ? "border-against/50" : "border-line",
              )}>
              <span className="flex-1">{t.message}</span>
              {t.action && (
                <button className="font-semibold underline underline-offset-4" onClick={t.action.onClick}>{t.action.label}</button>
              )}
            </m.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
