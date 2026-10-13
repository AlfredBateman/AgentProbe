import { expect, test } from "@playwright/test";

// No account needed: the landing page is public. Playwright's Chromium ships without H.264, so
// playback itself isn't asserted here; that the video and poster are served from this origin,
// and that the CSP lets the page ask for them, is.
test("the landing hero loads, both CTAs navigate, and the CSP blocks nothing", async ({ page, baseURL }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(String(e)));
  // Anything the Content-Security-Policy blocked (ADR 0039): Chrome reports each as a console error.
  const cspViolations: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" && m.text().includes("Content Security Policy")) cspViolations.push(m.text());
  });

  const response = await page.goto("/");
  expect(response!.headers()["content-security-policy"]).toContain("media-src 'self'");
  await expect(page.getByRole("heading", { level: 1, name: "Measure, regression, proven" })).toBeVisible();
  await expect(page.getByText("Regression detection for LLM agents.", { exact: true })).toBeVisible();
  for (const service of ["Repeat every case", "Judge traces and tool calls", "Gate the pull request"]) {
    await expect(page.getByRole("listitem").filter({ hasText: service })).toBeVisible();
  }
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  expect(overflow, "the hero scrolls horizontally").toBe(false);

  // Self-hosted media: same origin, the right types, and a muted video with its poster.
  const video = page.locator("video");
  await expect(video).toHaveJSProperty("muted", true);
  expect(await video.getAttribute("autoplay")).toBeNull();
  for (const [attribute, type] of [
    ["src", "video/mp4"],
    ["poster", "image/webp"],
  ]) {
    const url = new URL((await video.getAttribute(attribute))!, baseURL);
    expect(url.origin).toBe(new URL(baseURL!).origin);
    const asset = await page.request.get(url.href);
    expect(asset.status(), url.pathname).toBe(200);
    expect(asset.headers()["content-type"]).toBe(type);
  }

  await page.getByRole("link", { name: "Get started" }).click();
  await expect(page).toHaveURL("/register");
  await expect(page.getByRole("heading", { name: "Create an account" })).toBeVisible();
  await page.goto("/");
  await page.getByRole("link", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/login");
  // The login page asks the API for a session before it shows its form, so this wait is the API's.
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible({ timeout: 15_000 });

  expect(pageErrors, `uncaught page errors: ${pageErrors.join("; ")}`).toEqual([]);
  expect(cspViolations, `CSP violations: ${cspViolations.join("; ")}`).toEqual([]);
});

test("the hero's release and repository links point at GitHub", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "GitHub" })).toHaveAttribute("href", "https://github.com/AlfredBateman/AgentProbe");
  await expect(page.getByRole("link", { name: "v0.1.0" })).toHaveAttribute(
    "href",
    "https://github.com/AlfredBateman/AgentProbe/releases/tag/v0.1.0",
  );
});
