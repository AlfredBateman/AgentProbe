import path from "node:path";
import { type APIRequestContext, expect, type Page, test } from "@playwright/test";
import { COMPARE_EMAIL, DEMO_AGENTS_URL } from "./fixtures";

// The rebuilt compare view, findings, public snapshot and HTML export on real data: a v1 run as
// the baseline and a v2 run that regresses one case. With SCREENSHOTS=1 the last test writes
// docs/screenshots/app/{compare,findings,shared,shared-attempts,export}-*.
test.describe.configure({ timeout: 240_000, mode: "serial" });

const PASSWORD = "correct horse battery staple compare";
const SCREENSHOT_DIR = path.resolve(__dirname, "../../../docs/screenshots/app");
const SIZES = [
  { width: 1440, height: 900 },
  { width: 810, height: 1000 },
  { width: 390, height: 844 },
];

// 10 attempts per case, so refund-outside-window's v1 to v2 drop (10/10 to 0/10) is significant
// and order-status's seeded 0.5 flakiness shows both outcomes.
const SUITE_YAML = `suite: compare-check
agent: support-v1
runs_per_case: 10
cases:
  - id: greeting
    input: "Hello there"
    expect:
      - judge: contains
        value: "How can I help?"
  - id: order-status
    input: "What's the status of order 1042?"
    expect:
      - judge: contains
        value: "shipped"
  - id: refund-outside-window
    input: "Can I get a refund after 45 days?"
    expect:
      - judge: contains_any
        values: ["30 days", "not eligible"]
      - judge: tool_not_called
        tool: issue_refund
`;

let projectId = "";
let v1Run = "";
let v2Run = "";
let token = "";

async function post(request: APIRequestContext, baseURL: string, urlPath: string, data: object) {
  const response = await request.post(`/api${urlPath}`, { data, headers: { Origin: baseURL } });
  expect(response.ok(), `${urlPath}: ${await response.text()}`).toBe(true);
  return response.json();
}

async function waitForRun(request: APIRequestContext, runId: string) {
  await expect
    .poll(async () => (await (await request.get(`/api/runs/${runId}`)).json()).status, { timeout: 120_000, intervals: [1_000] })
    .toBe("completed");
}

function watch(page: Page) {
  const problems: string[] = [];
  page.on("pageerror", (e) => problems.push(`page error: ${e}`));
  page.on("console", (m) => {
    if (m.type() === "error" && m.text().includes("Content Security Policy")) problems.push(`CSP: ${m.text()}`);
  });
  return problems;
}

async function noOverflow(page: Page, where: string) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1), `${where} scrolls horizontally`).toBe(false);
}

async function shoot(page: Page, name: string) {
  for (const size of SIZES) {
    await page.setViewportSize(size);
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(600); // the header's reveal and the charts' draw-in have played
    // The image first, so a failed overflow check leaves what it saw.
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${name}-${size.width}.png`), fullPage: true });
    await noOverflow(page, `${name} at ${size.width}px`);
  }
  await page.setViewportSize(SIZES[0]);
}

test.beforeEach(async ({ page, baseURL }, testInfo) => {
  await page.setViewportSize(SIZES[0]);
  if (testInfo.title.startsWith("set up")) return;
  await post(page.request, baseURL!, "/auth/login", { email: COMPARE_EMAIL, password: PASSWORD });
});

test("set up: a v1 baseline, a v2 run that regresses one case, and a share link", async ({ page, baseURL }) => {
  await post(page.request, baseURL!, "/auth/register", { email: COMPARE_EMAIL, password: PASSWORD });
  projectId = (await post(page.request, baseURL!, "/projects", { name: "e2e-compare-views" })).id;
  const response = { output: "$.output", tool_calls: "$.tool_calls", tool_name: "$.tool", tool_arguments: "$.arguments", total_tokens: "$.usage.total_tokens" };
  const agent = await post(page.request, baseURL!, `/projects/${projectId}/agents`, {
    name: "support-v1",
    config: { adapter_type: "http", url: `${DEMO_AGENTS_URL}/support/v1/chat`, allow_private: true, response },
  });
  const suite = await post(page.request, baseURL!, `/projects/${projectId}/suites`, { yaml: SUITE_YAML });

  v1Run = (await post(page.request, baseURL!, `/suites/${suite.id}/runs`, {})).id;
  await waitForRun(page.request, v1Run);
  await post(page.request, baseURL!, `/projects/${projectId}/baseline`, { branch: "main", run_id: v1Run });

  const put = await page.request.put(`/api/agents/${agent.id}`, {
    data: { config: { ...agent.config, adapter_type: "http", url: `${DEMO_AGENTS_URL}/support/v2/chat` } },
    headers: { Origin: baseURL! },
  });
  expect(put.ok(), await put.text()).toBe(true);
  v2Run = (await post(page.request, baseURL!, `/suites/${suite.id}/runs`, {})).id;
  await waitForRun(page.request, v2Run);
  token = (await post(page.request, baseURL!, `/runs/${v2Run}/share`, {})).token;
});

test("compare: one bordered sentence of the report's real values, over the figures and the cases", async ({ page }) => {
  const problems = watch(page);
  await page.goto(`/projects/${projectId}/runs/${v2Run}/compare`);

  const verdict = page.locator("section").filter({ has: page.getByRole("heading", { name: "Verdict" }) });
  const sentence = verdict.locator("p").first();
  await expect(sentence).toHaveText(/^Regression: refund-outside-window, p=(\d\.\d{4}|\d\.\de-\d+), corrected threshold=\d\.\d{4}/);
  expect(await sentence.evaluate((el) => getComputedStyle(el).borderTopColor)).toBe("rgb(255, 42, 42)"); // red: a failure
  expect(await sentence.evaluate((el) => getComputedStyle(el).borderTopWidth)).toBe("1px");
  await expect(page.getByText("Regression", { exact: true })).toHaveCount(1);

  await test.step("the run's pass rates are on one 0 to 100% ruler, each row labelled, with a table view", async () => {
    const figure = page.locator("figure").filter({ hasText: "Run pass rate, 95% interval" });
    await expect(figure).toBeVisible();
    const plot = figure.locator("ul"); // the rows are labelled in place; the table view repeats them as text
    await expect(plot.getByText("Baseline", { exact: true })).toBeVisible();
    await expect(plot.getByText("Candidate", { exact: true })).toBeVisible();
    await figure.getByText("Table view").click();
    const table = figure.getByRole("table");
    await expect(table.getByRole("row")).toHaveCount(3); // header, baseline, candidate
    await expect(table).toContainText(/Baseline\s*\d+\.\d%/);
  });

  await test.step("the trend names the baseline and the candidate in place", async () => {
    const plot = page.locator("figure").filter({ hasText: "Pass rate by run" }).locator("[aria-hidden]").first();
    await expect(plot.getByText("Candidate", { exact: true })).toBeVisible();
    await expect(plot.getByText("Baseline", { exact: true })).toBeVisible();
  });

  await test.step("the cases table has the counts, a mark per attempt and the corrected threshold", async () => {
    const row = page.getByRole("table", { name: "Case-by-case comparison" }).locator("tr").filter({ hasText: "refund-outside-window" });
    await expect(row).toContainText("10/10");
    await expect(row).toContainText("0/10");
    await expect(row.locator(".mark-fail")).toHaveCount(11); // ten failed attempts, and the Regressed badge's own mark
    await expect(row).toContainText(/0\.\d{4}/);
  });

  await noOverflow(page, "compare");
  expect(problems, problems.join("\n")).toEqual([]);
});

test("compare: the charts draw in, in steps, and not at all under reduced motion", async ({ page }) => {
  const animation = () => page.locator("figure .draw-in").first().evaluate((el) => getComputedStyle(el).animationName);
  await page.goto(`/projects/${projectId}/runs/${v2Run}/compare`);
  await expect(page.locator("figure .draw-in").first()).toBeVisible();
  expect(await animation()).toBe("draw-in");
  // `steps(6, end)` is what the stylesheet says; the browser may serialize it as `steps(6)`.
  expect(await page.locator("figure .draw-in").first().evaluate((el) => getComputedStyle(el).animationTimingFunction)).toMatch(/^steps\(6(, end)?\)$/);

  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.reload();
  await expect(page.locator("figure .draw-in").first()).toBeVisible();
  expect(await animation()).toBe("none");
});

test("findings: totals, a bar per finding with a table, and each finding's members with their judges", async ({ page }) => {
  const problems = watch(page);
  await page.goto(`/projects/${projectId}/runs/${v2Run}/findings`);
  await expect(page.getByRole("heading", { level: 1, name: "Findings" })).toBeVisible();
  await expect(page.getByText(/^\d+ failing attempts? → \d+ findings?$/)).toBeVisible();

  const chart = page.locator("figure").filter({ hasText: "Failing attempts per finding" });
  await expect(chart).toBeVisible();
  await chart.getByText("Table view").click();
  await expect(chart.getByRole("table")).toContainText("F-01");

  const first = page.getByRole("article").first();
  await first.getByText(/^Show \d+ members$/).click();
  const members = first.getByRole("list", { name: /^Members of / });
  await expect(members.getByRole("listitem").first()).toContainText(/Attempt \d+/);
  await members.getByRole("link", { name: "View trace" }).first().click();
  await expect(page).toHaveURL(/\/results\/[0-9a-f-]+$/);
  expect(problems, problems.join("\n")).toEqual([]);
});

test("shared: a logged-out visitor sees a complete read-only snapshot, and nothing of the agent's config", async ({ browser, baseURL }) => {
  const anon = await browser.newContext({ baseURL });
  const page = await anon.newPage();
  const problems = watch(page);
  await page.goto(`/shared/${token}`);

  await expect(page.getByText("Read-only snapshot")).toBeVisible();
  await expect(page.getByText("Captured")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1, name: "compare-check" })).toBeVisible();
  await expect(page.locator("figure").filter({ hasText: "Cases by stability" })).toBeVisible();
  await expect(page.locator("figure").filter({ hasText: "Pass rate, 95% interval" })).toBeVisible();

  await page.getByRole("button", { name: "Show attempts of refund-outside-window" }).click();
  const attempts = page.getByRole("list", { name: "Attempts of refund-outside-window" });
  await expect(attempts.getByRole("listitem").first()).toContainText("Failed");
  await expect(attempts.getByRole("list", { name: "Judgments" }).first()).toBeVisible();

  const body = await page.locator("body").innerText();
  expect(body).not.toContain(DEMO_AGENTS_URL); // the agent's address is config, not part of a snapshot
  expect(body).not.toContain("Latency"); // no raw trace figures
  const links = await page.locator("a[href]").evaluateAll((as) => as.map((a) => a.getAttribute("href")));
  expect(links.sort()).toEqual(["/", "/register"]);

  await noOverflow(page, "shared");
  expect(problems, problems.join("\n")).toEqual([]);
  await anon.close();
});

test("export: the HTML file is one self-contained document, under a CSP that allows nothing but its own styles", async ({ page }) => {
  const exportUrl = `/api/runs/${v2Run}/export?format=html`;
  const response = await page.request.get(exportUrl);
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("text/html");
  expect(response.headers()["content-security-policy"]).toContain("default-src 'none'");
  const html = await response.text();
  expect(html).toContain("[ Run report ]");
  expect(html).not.toMatch(/<script|<img|<svg|<link|<form|https?:\/\/|url\(|@import|src=/);

  // Opened in the browser: nothing else is requested, nothing is blocked, and it fits the screen.
  const requests: string[] = [];
  page.on("request", (r) => requests.push(r.url()));
  const problems = watch(page);
  await page.goto(exportUrl);
  await expect(page.getByRole("heading", { level: 1, name: "compare-check" })).toBeVisible();
  expect(requests.map((u) => new URL(u).pathname)).toEqual([new URL(exportUrl, "http://x").pathname]);
  await noOverflow(page, "export");
  expect(problems, problems.join("\n")).toEqual([]);
});

// Writes docs/screenshots/app/*: SCREENSHOTS=1 pnpm e2e. Off by default, so an ordinary run does
// not rewrite the images with this machine's font rasterization.
test("screenshots at 1440, 810 and 390px", async ({ page, browser, baseURL }) => {
  test.skip(!process.env.SCREENSHOTS, "set SCREENSHOTS=1 to write docs/screenshots/app");
  test.setTimeout(180_000);

  await page.goto(`/projects/${projectId}/runs/${v2Run}/compare`);
  await expect(page.getByRole("heading", { name: "Verdict" })).toBeVisible();
  await shoot(page, "compare");

  await page.goto(`/projects/${projectId}/runs/${v2Run}/findings`);
  await expect(page.getByRole("article").first()).toBeVisible();
  await page.getByRole("article").first().getByText(/^Show \d+ members$/).click();
  await shoot(page, "findings");

  const anon = await browser.newContext({ baseURL });
  const shared = await anon.newPage();
  await shared.goto(`/shared/${token}`);
  await expect(shared.getByText("Read-only snapshot")).toBeVisible();
  await shoot(shared, "shared");
  await shared.getByRole("button", { name: "Show attempts of refund-outside-window" }).click();
  await shoot(shared, "shared-attempts");
  await anon.close();

  await page.goto(`/api/runs/${v2Run}/export?format=html`);
  await expect(page.getByRole("heading", { level: 1, name: "compare-check" })).toBeVisible();
  await shoot(page, "export");
});
