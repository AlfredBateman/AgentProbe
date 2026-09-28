import { expect, test } from "@playwright/test";
import { cleanupE2eAccount } from "./cleanup";
import { E2E_EMAIL, E2E_PASSWORD } from "./fixtures";

test.afterAll(() => cleanupE2eAccount());

test("an expired access cookie is silently refreshed on a direct visit to a protected page", async ({ page, context }) => {
  // Registering through the API (not the UI — that's 01's job) sets both cookies in this
  // browser context, since context.request shares its cookie jar with page.
  const registered = await context.request.post("/api/auth/register", {
    data: { email: E2E_EMAIL, password: E2E_PASSWORD },
    headers: { origin: "http://localhost:3000" },
  });
  expect(registered.ok()).toBe(true);

  // Drop only the access cookie, simulating its 15-minute expiry; the refresh cookie survives.
  await context.clearCookies({ name: "access_token" });

  await page.goto("/projects");
  await expect(page).toHaveURL("/projects"); // never bounced through /login
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();

  const cookies = await context.cookies();
  expect(cookies.find((c) => c.name === "access_token")).toBeDefined(); // the silent refresh reissued it
});
