import { expect, test } from "@playwright/test";
import { cleanupE2eAccount } from "./cleanup";
import { E2E_EMAIL, E2E_PASSWORD } from "./fixtures";

test.afterAll(() => cleanupE2eAccount());

test("a fully expired session lands on /login with `next` preserved, and returns there after signing in", async ({
  page,
  context,
}) => {
  const registered = await context.request.post("/api/auth/register", {
    data: { email: E2E_EMAIL, password: E2E_PASSWORD },
    headers: { origin: "http://localhost:3000" },
  });
  expect(registered.ok()).toBe(true);
  await context.clearCookies(); // both cookies gone: a fully signed-out browser

  await page.goto("/projects");
  await page.waitForURL(/\/login\?next=%2Fprojects/); // proxy.ts's redirect: a real navigation

  await page.getByLabel("Email").fill(E2E_EMAIL);
  await page.getByLabel("Password").fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();

  // toHaveURL polls page.url() directly; waitForURL's default waitUntil:'load' never resolves
  // for the login page's client-side (History API) redirect after a successful sign-in.
  await expect(page).toHaveURL("/projects");
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
});
