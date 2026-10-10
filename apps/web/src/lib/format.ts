import type { DebateCard, DebateView, Position, SideView, Status } from "./types";

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  if (s < 604800) return `${Math.round(s / 86400)}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.ceil(totalSeconds));
  if (s >= 3600) {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return h >= 24 ? `${Math.floor(h / 24)}d ${h % 24}h` : `${h}h ${String(m).padStart(2, "0")}m`;
  }
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function compact(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}k`;
  return `${(n / 1_000_000).toFixed(1)}M`;
}

export const sideLabel = (p: Position) => (p === "for" ? "FOR" : "AGAINST");

export function sideName(side: SideView | undefined): string {
  if (!side) return "—";
  if (side.participant_type === "swarm") return side.model?.display_name ?? "AI Swarm";
  if (side.user) return side.user.display_name;
  if (side.invited) return `@${side.invited.username} (invited)`;
  if (side.invite_link) return "Invite only";
  return "Open seat";
}

export function sideOf(d: Pick<DebateView | DebateCard, "sides">, p: Position): SideView | undefined {
  return d.sides.find((s) => s.position === p);
}

export const LIVE_STATUSES: Status[] = ["lobby", "opening", "rebuttal", "cross_exam", "closing", "judging"];
export const isLive = (s: Status) => LIVE_STATUSES.includes(s);
export const isRound = (s: Status) => ["opening", "rebuttal", "cross_exam", "closing"].includes(s);

export function statusText(s: Status): string {
  return (
    {
      waiting_for_opponent: "Open challenge",
      swarm_fallback_offered: "Awaiting opponent",
      lobby: "Pre-show",
      opening: "Opening",
      rebuttal: "Rebuttal",
      cross_exam: "Cross-examination",
      closing: "Closing",
      judging: "Judge deliberating",
      completed: "Verdict in",
      paused: "Paused",
      abandoned: "Abandoned",
      cancelled: "Cancelled",
    } as Record<Status, string>
  )[s];
}

export function modeText(m: string): string {
  return m === "hvh" ? "Human vs Human" : m === "hva" ? "Human vs AI" : "AI vs AI";
}

export function wordCount(text: string): number {
  const t = text.trim();
  return t ? t.split(/\s+/).length : 0;
}

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

export const PERSONA_LABEL: Record<string, string> = {
  data_driven: "Data-driven",
  moral_framing: "Moral framing",
  economic: "Economist",
  contrarian: "Contrarian",
};
