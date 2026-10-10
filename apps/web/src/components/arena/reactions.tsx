"use client";

import { AnimatePresence, motion } from "motion/react";

import type { Reaction } from "@/lib/realtime";
import type { Position } from "@/lib/types";

export const REACTIONS = ["🔥", "🎯", "🤯", "👏", "😂", "🚩"] as const;

export function ReactionDock({ onReact, side }: { onReact: (emoji: string, position: Position | null) => void; side: Position | null }) {
  return (
    <div className="flex items-center gap-1 rounded-full border border-line bg-surface/90 p-1 shadow-xl backdrop-blur" role="toolbar" aria-label="Send a reaction">
      {REACTIONS.map((e) => (
        <button key={e} onClick={() => onReact(e, side)} aria-label={`React ${e}`}
          className="grid size-9 place-items-center rounded-full text-lg transition hover:scale-125 hover:bg-surface-2 active:scale-95">
          {e}
        </button>
      ))}
    </div>
  );
}

export function FloatingReactions({ items }: { items: Reaction[] }) {
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-28 z-30 h-0" aria-hidden>
      <AnimatePresence>
        {items.map((r) => {
          const x = r.position === "for" ? 18 + (r.id % 5) * 4 : r.position === "against" ? 62 + (r.id % 5) * 4 : 30 + (r.id % 9) * 5;
          return (
            <motion.span key={r.id} className="absolute text-3xl" style={{ left: `${x}%` }}
              initial={{ y: 0, opacity: 0, scale: 0.6 }}
              animate={{ y: -260 - (r.id % 4) * 30, opacity: [0, 1, 1, 0], scale: [0.6, 1.2, 1, 0.9], x: [0, (r.id % 2 ? 14 : -14), 0] }}
              exit={{ opacity: 0 }} transition={{ duration: 2.4, ease: "easeOut" }}>
              {r.emoji}
            </motion.span>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
