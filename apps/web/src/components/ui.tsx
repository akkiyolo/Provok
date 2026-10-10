"use client";

import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { forwardRef, useEffect, useId, useRef } from "react";

import { cx, sideLabel } from "@/lib/format";
import type { ModelRef, Position, PublicUser } from "@/lib/types";

// ── Buttons ────────────────────────────────────────────────────────────────

type Variant = "primary" | "for" | "against" | "ghost" | "outline" | "danger" | "win";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-text text-bg hover:opacity-90",
  for: "bg-for text-[#0a0a0b] hover:brightness-110 shadow-[0_0_24px_var(--for-glow)]",
  against: "bg-against text-white hover:brightness-110 shadow-[0_0_24px_var(--against-glow)]",
  ghost: "bg-transparent text-text hover:bg-surface-2",
  outline: "border border-line-strong text-text hover:bg-surface-2",
  danger: "bg-danger text-white hover:brightness-110",
  win: "bg-win text-[#0a0a0b] hover:brightness-105",
};
const SIZES = { sm: "h-8 px-3 text-[13px]", md: "h-10 px-4 text-sm", lg: "h-12 px-6 text-[15px]" };

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: keyof typeof SIZES;
  loading?: boolean;
  href?: string;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading, className, children, disabled, href, ...rest }, ref,
) {
  const cls = cx(
    "inline-flex items-center justify-center gap-2 rounded-full font-semibold tracking-tight transition",
    "disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98] select-none whitespace-nowrap",
    VARIANTS[variant], SIZES[size], className,
  );
  if (href) {
    return <Link href={href} className={cls}>{children}</Link>;
  }
  return (
    <button ref={ref} className={cls} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading && <Spinner className="size-4" />}
      {children}
    </button>
  );
});

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={cx("animate-spin", className)} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

// ── Form fields ────────────────────────────────────────────────────────────

interface FieldProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
  error?: string | null;
}

export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field({ label, hint, error, id, className, ...rest }, ref) {
  const auto = useId();
  const fid = id ?? auto;
  return (
    <div className={cx("flex flex-col gap-1.5", className)}>
      <label htmlFor={fid} className="text-[13px] font-medium text-dim">{label}</label>
      <input
        ref={ref}
        id={fid}
        aria-invalid={error ? true : undefined}
        aria-describedby={error || hint ? `${fid}-msg` : undefined}
        className={cx(
          "h-11 rounded-xl border bg-surface px-3.5 text-[15px] text-text placeholder:text-faint outline-none transition",
          "focus:border-text/60 focus:ring-2 focus:ring-text/10",
          error ? "border-danger" : "border-line",
        )}
        {...rest}
      />
      {(error || hint) && (
        <p id={`${fid}-msg`} className={cx("text-[12.5px]", error ? "text-danger" : "text-faint")}>{error ?? hint}</p>
      )}
    </div>
  );
});

// ── Identity ───────────────────────────────────────────────────────────────

export function Avatar({ user, size = 32, ring }: { user: Pick<PublicUser, "display_name" | "avatar_url"> | null; size?: number; ring?: Position }) {
  const initial = (user?.display_name ?? "?").trim().charAt(0).toUpperCase();
  const ringCls = ring === "for" ? "ring-2 ring-for" : ring === "against" ? "ring-2 ring-against" : "";
  return (
    <span
      className={cx("relative inline-grid shrink-0 place-items-center overflow-hidden rounded-full bg-surface-3 font-semibold text-dim", ringCls)}
      style={{ width: size, height: size, fontSize: size * 0.42 }}
      aria-hidden
    >
      {user?.avatar_url ? (
        // eslint-disable-next-line @next/next/no-img-element -- user-uploaded avatars from arbitrary CDNs
        <img src={user.avatar_url} alt="" className="size-full object-cover" loading="lazy" referrerPolicy="no-referrer" />
      ) : (
        initial
      )}
    </span>
  );
}

export function ModelBadge({ model, position }: { model: ModelRef | null; position?: Position }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-md border px-1.5 py-0.5 font-mono text-[10.5px] font-semibold uppercase tracking-[0.08em]",
        position === "for" ? "border-for/40 text-for" : position === "against" ? "border-against/50 text-against" : "border-line-strong text-dim",
      )}
    >
      <svg viewBox="0 0 16 16" className="size-3" fill="currentColor" aria-hidden>
        <path d="M8 1l1.6 4.4L14 7l-4.4 1.6L8 13l-1.6-4.4L2 7l4.4-1.6z" />
      </svg>
      {model?.display_name ?? "AI"}
    </span>
  );
}

/** Side colour is never the only signal: always paired with the FOR/AGAINST word. */
export function SideTag({ position, className }: { position: Position; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1.5 font-mono text-[11px] font-bold tracking-[0.14em]", position === "for" ? "text-for" : "text-against", className)}>
      <span className={cx("size-1.5 rounded-full", position === "for" ? "bg-for" : "bg-against")} aria-hidden />
      {sideLabel(position)}
    </span>
  );
}

export function LiveBadge({ label = "LIVE" }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-live/15 px-2 py-0.5 font-mono text-[10.5px] font-bold tracking-[0.14em] text-live">
      <span className="size-1.5 rounded-full bg-live animate-live-dot" aria-hidden />
      {label}
    </span>
  );
}

export function Pill({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 text-[11.5px] text-dim", className)}>
      {children}
    </span>
  );
}

// ── Overlays ───────────────────────────────────────────────────────────────

/** Bottom sheet on mobile, centred dialog on desktop. Focus-trapped, Esc to close. */
export function Sheet({ open, onClose, title, children, wide }: {
  open: boolean; onClose: () => void; title?: string; children: React.ReactNode; wide?: boolean;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab" && panel.current) {
        const f = panel.current.querySelectorAll<HTMLElement>("button, [href], input, textarea, select, [tabindex]:not([tabindex='-1'])");
        if (!f.length) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { last.focus(); e.preventDefault(); }
        else if (!e.shiftKey && document.activeElement === last) { first.focus(); e.preventDefault(); }
      }
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    setTimeout(() => panel.current?.querySelector<HTMLElement>("input, textarea, button")?.focus(), 30);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      prev?.focus?.();
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[80] flex items-end justify-center sm:items-center" role="presentation">
          <motion.div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose}
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
          <motion.div
            ref={panel}
            role="dialog" aria-modal="true" aria-labelledby={title ? titleId : undefined}
            className={cx("relative z-10 max-h-[92dvh] w-full overflow-y-auto rounded-t-3xl border border-line bg-surface p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] sm:rounded-3xl sm:p-7",
              wide ? "sm:max-w-2xl" : "sm:max-w-md")}
            initial={{ y: 40, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 40, opacity: 0 }}
            transition={{ type: "spring", stiffness: 380, damping: 34 }}
          >
            <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-line-strong sm:hidden" aria-hidden />
            {title && <h2 id={titleId} className="font-display mb-4 text-2xl font-bold">{title}</h2>}
            <button onClick={onClose} aria-label="Close" className="absolute right-4 top-4 grid size-9 place-items-center rounded-full text-dim hover:bg-surface-2">
              <svg viewBox="0 0 20 20" className="size-4" fill="currentColor"><path d="M5.3 4.3 10 9l4.7-4.7 1 1L11 10l4.7 4.7-1 1L10 11l-4.7 4.7-1-1L9 10 4.3 5.3z" /></svg>
            </button>
            {children}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}

// ── Tabs (segmented) ───────────────────────────────────────────────────────

export function Tabs<T extends string>({ value, onChange, items, className }: {
  value: T; onChange: (v: T) => void; items: { value: T; label: React.ReactNode }[]; className?: string;
}) {
  return (
    <div role="tablist" className={cx("no-scrollbar flex gap-1 overflow-x-auto rounded-full border border-line bg-surface p-1", className)}>
      {items.map((it) => {
        const active = it.value === value;
        return (
          <button key={it.value} role="tab" aria-selected={active} onClick={() => onChange(it.value)}
            className={cx("relative shrink-0 rounded-full px-3.5 py-1.5 text-[13px] font-semibold transition", active ? "text-bg" : "text-dim hover:text-text")}>
            {active && <motion.span layoutId={`tab-${items.map((i) => i.value).join("")}`} className="absolute inset-0 rounded-full bg-text" transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
            <span className="relative">{it.label}</span>
          </button>
        );
      })}
    </div>
  );
}

// ── Empty / error states that push action ──────────────────────────────────

export function Empty({ title, body, action }: { title: string; body?: string; action?: React.ReactNode }) {
  return (
    <div className="stage grain flex flex-col items-center gap-3 rounded-3xl border border-dashed border-line px-6 py-14 text-center">
      <p className="font-display text-2xl font-bold">{title}</p>
      {body && <p className="max-w-sm text-sm text-dim">{body}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorBlock({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-3 rounded-3xl border border-line bg-surface px-6 py-10 text-center">
      <p className="font-display text-xl font-bold">That didn&apos;t load.</p>
      <p className="max-w-sm text-sm text-dim">{message}</p>
      {retry && <Button variant="outline" size="sm" onClick={retry}>Try again</Button>}
    </div>
  );
}

export function PageTitle({ eyebrow, title, children }: { eyebrow?: string; title: string; children?: React.ReactNode }) {
  return (
    <header className="mb-6 flex flex-col gap-2 sm:mb-8">
      {eyebrow && <p className="font-mono text-[11px] font-bold tracking-[0.18em] text-faint">{eyebrow}</p>}
      <h1 className="font-display text-[clamp(2rem,5vw,3.25rem)] font-extrabold leading-[0.95]">{title}</h1>
      {children}
    </header>
  );
}
