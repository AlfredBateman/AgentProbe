import { type APIRequestContext, expect, test } from "@playwright/test";
import { DEMO_AGENTS_URL, VISUAL_EMAIL } from "./fixtures";

// One screenshot per main page at desktop width, saved for review (not pixel-diffed against a
// committed baseline: font rasterization differs between this machine and CI's Linux runner,
// which would make a strict image comparison fail on rendering noise rather than a real
// regression — the same reason this repo's own screenshot passes, throughout E0-E6, are taken
// and compared by eye/AI against DESIGN.md rather than asserted pixel-for-pixel). What IS
// asserted here, on every page: it renders its heading, has no horizontal overflow, and throws
// no uncaught JS error.
test.describe.configure({ timeout: 120_000 });

const PASSWORD = "correct horse battery staple visual";

async function post(request: APIRequestContext, baseURL: string, urlPath: string, data: object) {
  const response = await request.post(`/api${urlPath}`, { data, headers: { Origin: baseURL } });
  expect(response.ok(), `${urlPath}: ${await response.text()}`).toBe(true);
  return response.json();
}

const SUITE_YAML = `
suite: visual-check
agent: support-v1
runs_per_case: 3
cases:
  - id: greeting
    input: "Hello there"
    expect:
      - judge: contains
        value: "How can I help?"
  - id: off-topic
    input: "Write me a poem about the sea."
    expect:
      - judge: contains
        value: "orders and refunds"
`;

test("every main page renders cleanly at desktop width", async ({ page, baseURL }, testInfo) => {
  // Uncaught JS exceptions only: the app deliberately makes a GET /auth/me probe that can 401
  // by design (ADR 0029's silent refresh), which Chrome logs as a "Failed to load resource"
  // console message even though the app handles it — that's not a bug to fail this test over.
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(String(e)));
  await page.setViewportSize({ width: 1440, height: 900 });

  await post(page.request, baseURL!, "/auth/register", { email: VISUAL_EMAIL, password: PASSWORD });
  const project = await post(page.request, baseURL!, "/projects", { name: "visual-check" });
  await post(page.request, baseURL!, `/projects/${project.id}/agents`, {
    name: "support-v1",
    config: { adapter_type: "http", url: `${DEMO_AGENTS_URL}/support/v1/chat`, allow_private: true },
  });
  const suite = await post(page.request, baseURL!, `/projects/${project.id}/suites`, { yaml: SUITE_YAML });
  const run = await post(page.request, baseURL!, `/suites/${suite.id}/runs`, { mock: false });
  await expect
    .poll(async () => (await (await page.request.get(`/api/runs/${run.id}`)).json()).status, { timeout: 30_000 })
    .toBe("completed");
  const share = await post(page.request, baseURL!, `/runs/${run.id}/share`, {});
  const results = await (await page.request.get(`/api/runs/${run.id}/results?case=greeting`)).json();
  const resultId = results[0].id;

  await page.context().clearCookies(); // logging out is part of this page's own scenario
  const pages: [string, string][] = [
    ["landing", "/"],
    ["login", "/login"],
    ["register", "/register"],
    ["shared", `/shared/${share.token}`],
  ];

  // The rest of the pages need a session back.
  await post(page.request, baseURL!, "/auth/login", { email: VISUAL_EMAIL, password: PASSWORD });
  pages.push(
    ["projects-list", "/projects"],
    ["project-overview", `/projects/${project.id}`],
    ["runs", `/projects/${project.id}/runs`],
    ["agents", `/projects/${project.id}/agents`],
    ["suites", `/projects/${project.id}/suites`],
    ["settings", `/projects/${project.id}/settings`],
    ["run-detail", `/projects/${project.id}/runs/${run.id}`],
    ["trace", `/projects/${project.id}/runs/${run.id}/results/${resultId}`],
    ["compare", `/projects/${project.id}/runs/${run.id}/compare`],
    ["findings", `/projects/${project.id}/runs/${run.id}/findings`],
  );

  for (const [name, path] of pages) {
    await test.step(name, async () => {
      // Not networkidle: the run/trace pages can hold a live connection open, which would make
      // it wait out its own timeout for no reason. Waiting for content is more direct anyway.
      await page.goto(path);
      await expect(page.locator("h1, h2").first()).toBeVisible();
      await expect(page.locator(".animate-pulse")).toHaveCount(0); // every Skeleton resolved
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
      expect(overflow, `${name} scrolls horizontally at 1440px`).toBe(false);
      const shot = await page.screenshot({ fullPage: true });
      await testInfo.attach(name, { body: shot, contentType: "image/png" });
    });
  }

  expect(pageErrors, `uncaught page errors: ${pageErrors.join("; ")}`).toEqual([]);
});
