import type { MetadataRoute } from "next";

const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/api/", "/admin", "/settings", "/wallet", "/notifications", "/new", "/auth/", "/bookmarks", "/messages"] }],
    sitemap: `${SITE}/sitemap.xml`,
    host: SITE,
  };
}
