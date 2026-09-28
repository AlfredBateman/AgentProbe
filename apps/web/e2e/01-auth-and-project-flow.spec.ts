import { expect, test } from "@playwright/test";
import { cleanupE2eAccount } from "./cleanup";
import { E2E_EMAIL, E2E_PASSWORD } from "./fixtures";

test.afterAll(() => cleanupE2eAccount());

test("register -> sign out -> sign in -> create project -> create and revoke an API key", async ({ page }) => {
  await test.step("register", async () => {
    await page.goto("/register");
    await page.getByLabel("Email").fill(E2E_EMAIL);
    await page.getByLabel("Password").fill(E2E_PASSWORD);
    await page.getByRole("button", { name: "Create account" }).click();
    // toHaveURL polls page.url() directly; waitForURL's default waitUntil:'load' never
    // resolves for a client-side (History API) route change like router.replace().
    await expect(page).toHaveURL("/projects");
    await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  });

  await test.step("sign out", async () => {
    await page.getByRole("button", { name: /Sign out/ }).click();
    await expect(page).toHaveURL("/login");
  });

  await test.step("sign in", async () => {
    await page.getByLabel("Email").fill(E2E_EMAIL);
    await page.getByLabel("Password").fill(E2E_PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL("/projects");
    await expect(page.getByText("No projects yet")).toBeVisible();
  });

  await test.step("create a project", async () => {
    await page.getByRole("button", { name: "New project" }).click();
    await page.getByLabel("Name").fill("e2e-test-project");
    await page.getByRole("button", { name: "Create project" }).click();
    await expect(page).toHaveURL(/\/projects\/[^/]+$/);
    await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  });

  await test.step("go to settings", async () => {
    await page.getByRole("link", { name: "Settings" }).click();
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
    await expect(page.getByText("No API keys yet")).toBeVisible();
  });

  await test.step("create an API key, shown once", async () => {
    await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.getByRole("button", { name: "Create key" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Label").fill("e2e-ci");
    await dialog.getByRole("button", { name: "Create key" }).click();
    const code = page.locator("pre code");
    await expect(code).toHaveText(/^ap_/);
    await page.getByRole("button", { name: "Copy" }).click();
    await expect(page.getByRole("button", { name: "Copied" })).toBeVisible();
    const clipboard = await page.evaluate(() => navigator.clipboard.readText());
    expect(clipboard).toMatch(/^ap_/);
    await page.getByRole("button", { name: "Done" }).click();
    await expect(page.getByRole("cell", { name: "e2e-ci" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "Active" })).toBeVisible();
  });

  await test.step("revoke it", async () => {
    await page.getByRole("button", { name: "Revoke" }).click();
    await expect(page.getByText('Revoked "e2e-ci"')).toBeVisible();
    await expect(page.getByRole("cell", { name: "Revoked" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Revoke" })).toHaveCount(0);
  });
});
