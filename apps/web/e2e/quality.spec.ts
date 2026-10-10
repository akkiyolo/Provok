import { expect, test } from "./fixtures";

const PAGES = ["/", "/challenges", "/leaderboard", "/leaderboard?type=model", "/login", "/signup", "/about", "/terms",
  "/privacy", "/refunds", "/search?q=cars", "/does-not-exist"];

test.describe("quality bar", () => {
  test.use({ viewport: { width: 360, height: 740 } });

  for (const path of PAGES) {
    test(`360px, no horizontal scroll, no page errors: ${path}`, async ({ page }) => {
      await page.goto(path);
      await page.waitForTimeout(800);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, "horizontal overflow in px").toBeLessThanOrEqual(0);
    });
  }
});

test("security headers are set on pages", async ({ request }) => {
  const res = await request.get("/");
  const h = res.headers();
  expect(h["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(h["x-content-type-options"]).toBe("nosniff");
  expect(h["x-frame-options"]).toBe("DENY");
});

test("debate pages publish share metadata", async ({ request, page }) => {
  const feed = await (await request.get("/api/v1/debates/feed?tab=recent&limit=1")).json();
  test.skip(!feed.items?.length, "no debates yet");
  const id = feed.items[0].id;
  await page.goto(`/d/${id}`);
  await expect(page.locator('meta[property="og:image"]')).toHaveAttribute("content", new RegExp(`/d/${id}/opengraph-image`));
  const img = await request.get(`/d/${id}/opengraph-image`);
  expect(img.headers()["content-type"]).toContain("image/png");
  expect((await img.body()).byteLength).toBeLessThan(300_000); // WhatsApp preview limit
});
