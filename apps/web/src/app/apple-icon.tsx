import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: "#0A0A0B", borderRadius: 40 }}>
        <div style={{ display: "flex", width: 106, height: 106, borderRadius: 999, overflow: "hidden" }}>
          <div style={{ width: "50%", background: "#FF5A1F", display: "flex" }} />
          <div style={{ width: "50%", background: "#4C6FFF", display: "flex" }} />
        </div>
        <div style={{ position: "absolute", width: 8, height: 128, background: "#0A0A0B", display: "flex" }} />
      </div>
    ),
    { ...size },
  );
}
