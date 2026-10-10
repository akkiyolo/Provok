import { ImageResponse } from "next/og";

import { ogFonts } from "@/lib/og-font";
import { fetchDebatePublic } from "@/lib/server";
import type { DebateView, Position } from "@/lib/types";

export const alt = "A live debate on Provok";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const FOR = "#FF5A1F";
const AGAINST = "#4C6FFF";
const BONE = "#F2EFE9";
const WIN = "#E8C547";

function name(d: DebateView, p: Position): string {
  const s = d.sides.find((x) => x.position === p);
  if (!s?.participant_type) return "Open seat";
  return s.participant_type === "swarm" ? (s.model?.display_name ?? "AI").toUpperCase() : s.user?.display_name ?? "Debater";
}

export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [d, fonts] = await Promise.all([fetchDebatePublic(id), ogFonts()]);
  const question = d?.question ?? "Ask anything. Pick your corners.";
  const voted = !!d?.momentum && d.momentum.votes_weight > 0;
  const share = voted ? d!.momentum!.for_share : 0.5;
  const winner = d?.verdict?.winner_position ?? null;
  const status = !d ? "PROVOK" : d.status === "completed" ? (winner ? `VERDICT: ${winner.toUpperCase()} WINS` : "VERDICT: TOO CLOSE TO CALL")
    : ["opening", "rebuttal", "cross_exam", "closing"].includes(d.status) ? `LIVE · ${d.status.replace("_", "-").toUpperCase()}`
      : d.status === "waiting_for_opponent" ? "OPEN CHALLENGE — TAKE A SIDE" : d.status.replace(/_/g, " ").toUpperCase();
  const qSize = question.length > 110 ? 50 : question.length > 70 ? 60 : 72;

  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", padding: "56px 64px", background: "#0A0A0B", color: BONE, fontFamily: fonts.length ? "Bricolage" : undefined,
        backgroundImage: `radial-gradient(circle at 0% 0%, rgba(255,90,31,0.28), transparent 45%), radial-gradient(circle at 100% 0%, rgba(76,111,255,0.28), transparent 45%)` }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", fontSize: 34, fontWeight: 800, letterSpacing: -2 }}>
            PROV<span style={{ color: FOR }}>O</span>K
          </div>
          <div style={{ display: "flex", fontSize: 22, fontWeight: 700, letterSpacing: 3, color: winner ? WIN : status.startsWith("LIVE") ? "#FF2E4D" : "#9A978F" }}>
            {status}
          </div>
        </div>
        <div style={{ display: "flex", flex: 1, alignItems: "center", fontSize: qSize, fontWeight: 800, lineHeight: 1.02, letterSpacing: -2.5 }}>
          {question}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 22 }}>
          {(["for", "against"] as Position[]).map((p) => (
            <div key={p} style={{ display: "flex", flexDirection: "column", alignItems: p === "for" ? "flex-start" : "flex-end" }}>
              <div style={{ display: "flex", fontSize: 20, fontWeight: 800, letterSpacing: 4, color: p === "for" ? FOR : AGAINST }}>
                {p === "for" ? "FOR" : "AGAINST"}{winner === p ? " · WINNER" : ""}
              </div>
              <div style={{ display: "flex", fontSize: 34, fontWeight: 700, color: winner === p ? WIN : BONE }}>{d ? name(d, p) : ""}</div>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", height: 18, borderRadius: 9, overflow: "hidden", background: AGAINST }}>
          <div style={{ width: `${Math.round(share * 100)}%`, background: FOR, display: "flex" }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 10, fontSize: 20, color: "#9A978F" }}>
          <span>{voted ? `${Math.round(share * 100)}% of the crowd` : "The crowd votes every round"}</span>
          <span>{voted ? `${100 - Math.round(share * 100)}% of the crowd` : "Watch · vote · share"}</span>
        </div>
      </div>
    ),
    { ...size, fonts },
  );
}
