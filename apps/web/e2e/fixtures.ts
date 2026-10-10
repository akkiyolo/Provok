import { type Browser, expect, type Page, test as base } from "@playwright/test";

/** Every test fails on uncaught page errors (incl. React hydration mismatches). */
export const test = base.extend<{ page: Page }>({
  page: async ({ page }, use) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await use(page);
    expect(errors, `uncaught page errors:\n${errors.join("\n")}`).toEqual([]);
  },
});
export { expect };

export const PASSWORD = "arena-launch-2026!";

export function uniqueName(prefix: string): string {
  return `${prefix}${Date.now().toString(36).slice(-5)}${Math.floor(Math.random() * 90 + 10)}`;
}

export async function signUp(page: Page, username = uniqueName("u")): Promise<string> {
  await page.goto("/signup");
  await page.getByLabel("Email").fill(`${username}@example.com`);
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL((u) => u.pathname === "/");
  return username;
}

export async function newUserPage(browser: Browser, prefix: string): Promise<{ page: Page; username: string }> {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const username = await signUp(page, uniqueName(prefix));
  return { page, username };
}

export const ARG =
  "Cars dominate space that could be parks, buses and bike lanes. Cities that pedestrianised their cores saw " +
  "footfall rise, cleaner air and safer streets. The burden of proof is on those defending the status quo.";
