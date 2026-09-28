import { expect, test } from "@playwright/test";

// No account needed: a brand-new browser context has no session cookies at all.
test("an unauthenticated visit to a protected page redirects to login with `next` preserved", async ({ page }) => {
  const target = "/projects/00000000-0000-0000-0000-000000000000/runs/00000000-0000-0000-0000-000000000000";
  await page.goto(target);
  await page.waitForURL(`/login?next=${encodeURIComponent(target)}`);
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});

test("an unauthenticated visit to the projects list also redirects", async ({ page }) => {
  await page.goto("/projects");
  await page.waitForURL("/login?next=%2Fprojects");
});
