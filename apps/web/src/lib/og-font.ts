import "server-only";

// Bricolage Grotesque for share images. Fetched once per server process from Google Fonts
// (TTF via the CSS2 API); falls back to the built-in font if the network is unavailable.
let cached: Promise<ArrayBuffer | null> | null = null;

async function load(weight: number): Promise<ArrayBuffer | null> {
  try {
    const css = await fetch(`https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@${weight}`, {
      headers: { "User-Agent": "Mozilla/4.0" }, // old UA → Google serves TTF, which Satori supports
      signal: AbortSignal.timeout(3000),
    }).then((r) => r.text());
    const url = /src: url\((.+?)\)/.exec(css)?.[1];
    if (!url) return null;
    return await fetch(url, { signal: AbortSignal.timeout(3000) }).then((r) => r.arrayBuffer());
  } catch {
    return null;
  }
}

export async function ogFonts(): Promise<{ name: string; data: ArrayBuffer; weight: 800; style: "normal" }[]> {
  cached ??= load(800);
  const data = await cached;
  if (!data) {
    cached = null; // retry next time
    return [];
  }
  return [{ name: "Bricolage", data, weight: 800, style: "normal" }];
}
