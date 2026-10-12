import { ARG, expect, newUserPage, PASSWORD, signUp, test, uniqueName } from "./fixtures";

test("anonymous visitor sees the arena and is prompted to sign in at the moment of action", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Ask anything/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Live" })).toBeVisible();
  await page.getByRole("button", { name: /Debate an AI now/ }).click();
  await expect(page.getByRole("dialog")).toContainText("Join the arena");
});

test("first debate vs AI: create → argue → verdict reveal", async ({ page }) => {
  await signUp(page);
  await page.goto("/new?quick=1");
  await page.getByLabel("Debate question").fill("Should cities ban private cars from their centres?");
  await expect(page.getByText(/Good to go/)).toBeVisible();
  await page.getByRole("button", { name: "Fight an AI now" }).click();
  await expect(page.getByText(/Free · 3 free AI debates left/)).toBeVisible(); // never a paywall for a new user
  await page.getByRole("button", { name: /Start the debate/ }).click();
  await page.waitForURL(/\/d\/[0-9a-f-]{36}$/);

  for (let turn = 0; turn < 5; turn++) {
    const composer = page.locator("#composer");
    await expect(composer).toBeVisible({ timeout: 45_000 });
    const turnKey = await composer.getAttribute("data-turn");
    await composer.fill(`${ARG} (${turn + 1})`);
    await page.getByRole("button", { name: /^Submit/ }).click();
    // The composer for this turn must go away before the next one appears.
    await expect(page.locator(`#composer[data-turn="${turnKey}"]`)).toHaveCount(0);
  }
  await expect(page.getByRole("link", { name: /Reveal the verdict/ }).first()).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: /Claim Board/ }).click();
  await expect(page.getByRole("dialog")).toContainText("C1");
  await page.keyboard.press("Escape");

  await page.getByRole("link", { name: /Reveal the verdict/ }).first().click();
  await expect(page.getByText("THE VERDICT").first()).toBeVisible();
  await page.getByRole("button", { name: "Skip" }).click().catch(() => undefined);
  await expect(page.getByRole("heading", { name: "Why" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Scorecard" })).toBeVisible();
});

test("human vs human: open challenge → join → turns → spectator votes", async ({ browser }) => {
  const alice = await newUserPage(browser, "al");
  await alice.page.goto("/new");
  await alice.page.getByLabel("Debate question").fill("Is remote work better than the office for juniors?");
  await alice.page.getByRole("button", { name: "Pick the corners →" }).click();
  await alice.page.getByRole("button", { name: /Open challenge/ }).last().click();
  await alice.page.getByRole("button", { name: "Choose the format →" }).click();
  await alice.page.getByRole("button", { name: "Review →" }).click();
  await expect(alice.page.getByText("Free", { exact: true })).toBeVisible();
  await alice.page.getByRole("button", { name: /Start the debate/ }).click();
  await alice.page.waitForURL(/\/d\//);
  const url = alice.page.url();
  await expect(alice.page.getByText("Waiting for a challenger")).toBeVisible();

  const bob = await newUserPage(browser, "bo");
  await bob.page.goto("/challenges");
  await bob.page.getByRole("link", { name: /remote work/ }).first().click();
  await bob.page.getByRole("button", { name: /Take the AGAINST side/ }).click();
  await expect(bob.page.getByText("ON THE CLOCK")).toBeVisible();

  await alice.page.reload();
  await alice.page.locator("#composer").fill(ARG);
  await alice.page.getByRole("button", { name: /^Submit/ }).click();
  await bob.page.reload();
  await bob.page.locator("#composer").fill(ARG);
  await bob.page.getByRole("button", { name: /^Submit/ }).click();

  const carol = await newUserPage(browser, "ca");
  await carol.page.goto(url);
  await expect(carol.page.getByText("Who won the Opening?")).toBeVisible();
  await carol.page.getByRole("button", { name: /^AGAINST/ }).click();
  await expect(carol.page.getByText(/Vote locked for AGAINST/)).toBeVisible();
  // Debaters can't vote in their own debate.
  await alice.page.reload();
  await expect(alice.page.getByText(/The crowd is voting/)).toBeVisible();
});

test("wrong password shows a clear error and no account enumeration", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email or username").fill("nobody-here");
  await page.getByLabel("Password").fill("not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText(/password don.t match/)).toBeVisible();
});

test("private invite link: only the link admits, and a brand-new user can sign up and join", async ({ browser }) => {
  const alice = await newUserPage(browser, "al");
  // Capture what "Send on WhatsApp" would open instead of leaving the app.
  await alice.page.addInitScript(() => {
    const w = window as unknown as { __opened?: string[] };
    window.open = ((url?: string | URL) => {
      w.__opened = [...(w.__opened ?? []), String(url)];
      return null;
    }) as typeof window.open;
  });
  await alice.page.goto("/new");
  await alice.page.getByLabel("Debate question").fill("Should homework be banned in primary schools?");
  await alice.page.getByRole("button", { name: "Pick the corners →" }).click();
  await alice.page.getByRole("button", { name: /Invite link/ }).last().click();
  await alice.page.getByRole("button", { name: "Choose the format →" }).click();
  await alice.page.getByRole("button", { name: "Review →" }).click();
  await alice.page.getByRole("button", { name: /Start the debate/ }).click();
  await alice.page.waitForURL(/\/d\//);
  const debatePath = new URL(alice.page.url()).pathname;
  await alice.page.getByRole("button", { name: "Send on WhatsApp" }).click();
  const opened = await alice.page.evaluate(() => (window as unknown as { __opened: string[] }).__opened[0]);
  const inviteUrl = new URL(new URL(opened).searchParams.get("text")!.split(" ").pop()!);
  expect(inviteUrl.pathname).toBe(debatePath);
  expect(inviteUrl.searchParams.get("invite")).toBeTruthy();

  // Without the link: no way in, and it isn't listed publicly.
  const nosy = await newUserPage(browser, "no");
  await nosy.page.goto(debatePath);
  await expect(nosy.page.getByText("This is a private challenge.")).toBeVisible();
  await expect(nosy.page.getByRole("button", { name: /Take the AGAINST side/ })).toHaveCount(0);
  await nosy.page.goto("/challenges");
  await expect(nosy.page.getByRole("link", { name: /homework/ })).toHaveCount(0);

  // With the link: an anonymous friend signs up right there and takes the seat.
  const bob = await (await browser.newContext()).newPage();
  await bob.goto(inviteUrl.pathname + inviteUrl.search);
  await expect(bob.getByText("You've been challenged.")).toBeVisible();
  await bob.getByRole("button", { name: /Take the AGAINST side/ }).click();
  const bobName = uniqueName("bo");
  await bob.getByLabel("Email").fill(`${bobName}@example.com`);
  await bob.getByLabel("Username").fill(bobName);
  await bob.getByLabel("Password").fill(PASSWORD);
  await bob.getByRole("button", { name: "Create account" }).click();
  await bob.getByRole("button", { name: /Take the AGAINST side/ }).click();
  await expect(bob.getByText("ON THE CLOCK")).toBeVisible();
  await alice.page.reload();
  await expect(alice.page.getByText(bobName).first()).toBeVisible();
});

test("inside the Android app the wallet shows balance and history but no purchases", async ({ page }) => {
  await signUp(page);
  await page.goto("/wallet");
  await expect(page.getByRole("heading", { name: "Top up" })).toBeVisible();

  // The app's launch URL carries ?app=android; the flag holds for the rest of the app session.
  await page.goto("/?app=android");
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem("provok:android-app"))).toBe("1");
  await page.goto("/wallet");
  await expect(page.getByRole("heading", { name: "History" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Top up" })).toHaveCount(0);
  await expect(page.getByText(/Razorpay/)).toHaveCount(0);
});

test("social: post, follow, like, reply, and the author is notified", async ({ browser }) => {
  const alice = await newUserPage(browser, "al");
  const bob = await newUserPage(browser, "bo");
  const take = `Chai beats coffee, every single morning ${Date.now() % 10000} #chai`;

  await alice.page.goto("/home");
  const home = alice.page.locator("section[aria-labelledby='home-heading']");
  await home.getByLabel("Write a post").fill(take);
  await home.getByRole("button", { name: "Post", exact: true }).click();
  await expect(home.getByText(take)).toBeVisible();

  await bob.page.goto(`/u/${alice.username}`);
  await bob.page.getByRole("button", { name: "Follow", exact: true }).click();
  await expect(bob.page.getByRole("button", { name: "Following" })).toBeVisible();
  await bob.page.goto("/home?tab=following");
  const card = bob.page.locator("article", { hasText: take });
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Like", exact: true }).click();
  await expect(card.getByRole("button", { name: "Unlike" })).toBeVisible();
  await card.getByRole("button", { name: "Reply", exact: true }).click();
  const dialog = bob.page.getByRole("dialog");
  await dialog.getByLabel("Write your reply").fill("Filter coffee says hello");
  await dialog.getByRole("button", { name: "Reply", exact: true }).click();
  await expect(dialog).toBeHidden();

  await alice.page.goto("/notifications");
  await expect(alice.page.getByText(/liked your post/)).toBeVisible();
  await expect(alice.page.getByText(/replied to you/)).toBeVisible();
  await expect(alice.page.getByText(/followed you/)).toBeVisible();
  await alice.page.getByText(/replied to you/).click();
  await expect(alice.page).toHaveURL(/\/p\//);
  // Next keeps the previous page (notifications) mounted but hidden, so look inside the post itself.
  await expect(alice.page.locator("article", { hasText: "Filter coffee says hello" })).toBeVisible();

  await alice.page.goto("/tag/chai");
  await expect(alice.page.locator("article", { hasText: take })).toBeVisible();
});
