import { expect, newUserPage, signUp, test, uniqueName } from "./fixtures";

test("invite link: banner names the inviter, sign-up is attributed to them", async ({ browser, page }) => {
  const { page: alice, username: aliceName } = await newUserPage(browser, "inv");
  await alice.goto("/invite");
  await expect(alice.getByRole("heading", { name: "Bring a sparring partner." })).toBeVisible();
  const link = (await alice.getByText(/\/r\/[a-z0-9]{8}$/).textContent()) ?? "";
  const path = new URL(link).pathname;
  expect(path).toMatch(/^\/r\/[a-z0-9]{8}$/);

  // A newcomer opens the link: lands on the home page with the inviter's banner.
  await page.goto(path);
  await expect(page).toHaveURL((u) => u.pathname === "/");
  await expect(page.getByRole("status").filter({ hasText: "invited you to Provok" })).toContainText(aliceName);

  const friend = await signUp(page, uniqueName("fr"));
  await expect(page.getByText("invited you to Provok")).toHaveCount(0); // signed in: banner gone

  await alice.reload();
  const row = alice.getByRole("listitem").filter({ hasText: friend });
  await expect(row).toContainText("Waiting for email");
  await alice.context().close();
});
