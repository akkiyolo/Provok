import type { MetadataRoute } from "next";

const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
const API = (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/$/, "");

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  "use cache";
  const now = new Date();
  const fixed: MetadataRoute.Sitemap = ["", "/home", "/challenges", "/leaderboard", "/about", "/terms", "/privacy", "/refunds", "/contact"]
    .map((p) => ({ url: `${SITE}${p}`, lastModified: now, changeFrequency: p ? "weekly" : "hourly", priority: p ? 0.5 : 1 }));
  try {
    const res = await fetch(`${API}/api/v1/debates/feed?tab=completed&limit=50`, { signal: AbortSignal.timeout(4000) });
    const data = (await res.json()) as { items: { id: string; completed_at: string | null; created_at: string }[] };
    return [
      ...fixed,
      ...data.items.map((d) => ({
        url: `${SITE}/d/${d.id}`, lastModified: new Date(d.completed_at ?? d.created_at), changeFrequency: "monthly" as const, priority: 0.7,
      })),
    ];
  } catch {
    return fixed;
  }
}
