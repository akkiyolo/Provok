import { ImageResponse } from "next/og";

export const size = { width: 512, height: 512 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: "#0A0A0B", borderRadius: 112 }}>
        <div style={{ display: "flex", width: 300, height: 300, borderRadius: 999, overflow: "hidden" }}>
          <div style={{ width: "50%", background: "#FF5A1F", display: "flex" }} />
          <div style={{ width: "50%", background: "#4C6FFF", display: "flex" }} />
        </div>
        <div style={{ position: "absolute", width: 22, height: 360, background: "#0A0A0B", display: "flex" }} />
      </div>
    ),
    { ...size },
  );
}
