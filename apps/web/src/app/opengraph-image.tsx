import { ImageResponse } from "next/og";

import { ogFonts } from "@/lib/og-font";

export const alt = "Provok — Ask anything. Pick your corners.";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function OpengraphImage() {
  const fonts = await ogFonts();
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between", padding: 72, color: "#F2EFE9", fontFamily: fonts.length ? "Bricolage" : undefined,
        background: "#0A0A0B", backgroundImage: "radial-gradient(circle at 0% 0%, rgba(255,90,31,0.32), transparent 45%), radial-gradient(circle at 100% 0%, rgba(76,111,255,0.32), transparent 45%)" }}>
        <div style={{ display: "flex", fontSize: 40, fontWeight: 800, letterSpacing: -2 }}>PROV<span style={{ color: "#FF5A1F" }}>O</span>K</div>
        <div style={{ display: "flex", flexDirection: "column", fontSize: 92, fontWeight: 800, lineHeight: 0.95, letterSpacing: -4 }}>
          <span>Ask anything.</span>
          <span>Pick your <span style={{ color: "#FF5A1F", marginLeft: 22 }}>corners.</span></span>
        </div>
        <div style={{ display: "flex", fontSize: 30, color: "#9A978F" }}>Debate humans or AI · the crowd votes · an impartial AI judge decides</div>
      </div>
    ),
    { ...size, fonts },
  );
}
