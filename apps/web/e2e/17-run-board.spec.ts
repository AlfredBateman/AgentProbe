import path from "node:path";
import { type APIRequestContext, expect, type Page, test } from "@playwright/test";
import { DEMO_AGENTS_URL, RUN_BOARD_EMAIL } from "./fixtures";
import { gatedAgent } from "./gated-agent";

// The runs list, the live run board and the trace viewer, on full runs against the demo agents
// in mock mode: a held v1 run watched live (cells change state and flash), a v2 run against it
// as the baseline (the verdict with its statistics, the failure clusters, reduced motion), a
// hostile case's trace (text only, nothing executes), and the runs list's filters, sort and
// pages. With SCREENSHOTS=1 it also writes docs/screenshots/app/{runs,run-live,run-complete,trace}-*.
test.describe.configure({ timeout: 300_000, mode: "serial" });

const PASSWORD = "correct horse battery staple run board";
const SCREENSHOT_DIR = path.resolve(__dirname, "../../../docs/screenshots/app");

// The hostile input: markup with handlers, markdown, an ANSI colour, an OSC 8 hyperlink and a
// bidi override. YAML's double quotes turn \e and ‮ into the real characters.
const HOSTILE =
  String.raw`<img src=x onerror=\"window.__pwned=1\"><script>window.__pwned=2</script> **bold** [x](javascript:alert(1)) ` +
  String.raw`\e[31mRED\e[0m \e]8;;https://evil.example\aclick\e]8;;\a invoice‮fdp.exe`;

// 10 attempts per case: order-status's seeded 0.5 flakiness shows both outcomes, and
// refund-outside-window's v1 -> v2 drop (10/10 -> 0/10) reaches significance.
const SUITE_YAML = `suite: board-check
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
  - id: hostile-input
    input: "${HOSTILE}"
    expect:
      - judge: not_contains
        values: ["AP-CANARY"]
`;

const CASES = ["greeting", "order-status", "refund-outside-window", "hostile-input"];
const SIZES = [
  { width: 1440, height: 900 },
  { width: 810, height: 1000 },
  { width: 390, height: 844 },
];

let projectId = "";
let suiteId = "";
let agentId = "";
let v1Run = "";
let v2Run = "";
let cancelledRun = "";
const gates = { v1: null as Awaited<ReturnType<typeof gatedAgent>> | null, v2: null as Awaited<ReturnType<typeof gatedAgent>> | null };

async function post(request: APIRequestContext, baseURL: string, urlPath: string, data: object) {
  const response = await request.post(`/api${urlPath}`, { data, headers: { Origin: baseURL } });
  expect(response.ok(), `${urlPath}: ${await response.text()}`).toBe(true);
  return response.json();
}

async function pointAgentAt(page: Page, baseURL: string, url: string) {
  const put = await page.request.put(`/api/agents/${agentId}`, {
    data: { config: { adapter_type: "http", url, allow_private: true, response: { tool_calls: "$.tool_calls", total_tokens: "$.usage.total_tokens" } } },
    headers: { Origin: baseURL },
  });
  expect(put.ok(), await put.text()).toBe(true);
}

function watch(page: Page) {
  const problems: string[] = [];
  page.on("pageerror", (e) => problems.push(`page error: ${e}`));
  page.on("dialog", (d) => {
    problems.push(`dialog: ${d.message()}`);
    void d.dismiss();
  });
  page.on("console", (m) => {
    if (m.type() === "error" && m.text().includes("Content Security Policy")) problems.push(`CSP: ${m.text()}`);
  });
  return problems;
}

async function noOverflow(page: Page, where: string) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1), `${where} scrolls horizontally`).toBe(false);
}

/** Counts inline-style writes on the board's flash marks: each flash writes its clip. */
async function countFlashes(page: Page) {
  await page.evaluate(() => {
    const w = window as unknown as { __flashes: number };
    w.__flashes = 0;
    new MutationObserver((records) => {
      w.__flashes += records.filter((r) => (r.target as Element).hasAttribute("data-flash")).length;
    }).observe(document.querySelector("ol[aria-label='Case board']")!, { attributes: true, attributeFilter: ["style"], subtree: true });
  });
  return () => page.evaluate(() => (window as unknown as { __flashes: number }).__flashes);
}

async function shoot(page: Page, name: string) {
  if (!process.env.SCREENSHOTS) return;
  for (const size of SIZES) {
    await page.setViewportSize(size);
    await page.evaluate(() => document.fonts.ready);
    await expect(page.locator('[class*="skeleton-step"]')).toHaveCount(0);
    await page.waitForTimeout(500); // the header's reveal has played
    await noOverflow(page, `${name} at ${size.width}px`);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${name}-${size.width}.png`), fullPage: true });
  }
  await page.setViewportSize(SIZES[0]);
}

const cell = (page: Page, id: string) => page.locator(`[data-case="${id}"]`);

test.beforeEach(async ({ page, baseURL }, testInfo) => {
  await page.setViewportSize(SIZES[0]);
  if (testInfo.title.startsWith("set up")) return;
  await post(page.request, baseURL!, "/auth/login", { email: RUN_BOARD_EMAIL, password: PASSWORD });
});

test.afterAll(async () => {
  for (const gate of [gates.v1, gates.v2]) {
    gate?.open();
    await gate?.close();
  }
});

test("set up: an agent behind a gate and the suite", async ({ page, baseURL }) => {
  gates.v1 = await gatedAgent(`${DEMO_AGENTS_URL}/support/v1/chat`);
  gates.v2 = await gatedAgent(`${DEMO_AGENTS_URL}/support/v2/chat`);
  await post(page.request, baseURL!, "/auth/register", { email: RUN_BOARD_EMAIL, password: PASSWORD });
  projectId = (await post(page.request, baseURL!, "/projects", { name: "e2e-run-board" })).id;
  agentId = (
    await post(page.request, baseURL!, `/projects/${projectId}/agents`, {
      name: "support-v1",
      config: { adapter_type: "http", url: gates.v1.url, allow_private: true, response: { tool_calls: "$.tool_calls", total_tokens: "$.usage.total_tokens" } },
    })
  ).id;
  suiteId = (await post(page.request, baseURL!, `/projects/${projectId}/suites`, { yaml: SUITE_YAML })).id;
});

test("a live v1 run: the board fills cell by cell over SSE, then shows its statistics", async ({ page, baseURL }) => {
  const problems = watch(page);
  const gate = gates.v1!;
  gate.hold();
  v1Run = (await post(page.request, baseURL!, `/suites/${suiteId}/runs`, {})).id;
  const stream = page.waitForResponse((r) => r.url().includes(`/runs/${v1Run}/stream?token=`));
  await page.goto(`/projects/${projectId}/runs/${v1Run}`);
  await stream;

  await test.step("every case is on the board before its first attempt", async () => {
    await expect(page.getByText("Live", { exact: true })).toBeVisible();
    const bar = page.getByRole("progressbar", { name: "Attempts finished" });
    await expect(bar).toHaveAttribute("aria-valuemax", "40");
    await expect(page.getByRole("list", { name: "Case board" }).getByRole("listitem")).toHaveCount(4);
    for (const id of CASES) await expect(cell(page, id)).toHaveAttribute("data-state", "queued");
    await expect(page.getByText("Compared with the baseline when the run finishes.")).toBeVisible();
  });

  await test.step("an attempt lands: its cell changes state, with one stepped flash", async () => {
    const flashes = await countFlashes(page);
    await expect.poll(gate.held).toBeGreaterThan(0);
    gate.releaseOne();
    await expect(cell(page, "greeting")).toHaveAttribute("data-state", "running");
    await expect(page.getByRole("progressbar", { name: "Attempts finished" })).toHaveAttribute("aria-valuenow", "1");
    expect(await flashes()).toBeGreaterThan(0);
    await expect(cell(page, "order-status")).toHaveAttribute("data-state", "queued");
  });

  await test.step("part way through", async () => {
    // Attempts run in suite order, four at a time. Release whatever is waiting, in batches, until
    // the API has saved 12: greeting (10) is done and order-status is part-way (at most 16 done).
    // Batches, not one call at a time: on a slow database a call left waiting would pass the
    // adapter's 30 s attempt timeout and be retried.
    const saved = async () => (await (await page.request.get(`/api/runs/${v1Run}`)).json()).attempts_done as number;
    while ((await saved()) < 12) {
      await expect.poll(gate.held).toBeGreaterThan(0);
      gate.releaseHeld();
    }
    // The page agrees with the API's own count.
    const bar = page.getByRole("progressbar", { name: "Attempts finished" });
    await expect
      .poll(async () => Number(await bar.getAttribute("aria-valuenow")) - (await saved()), { timeout: 20_000 })
      .toBe(0);
    await expect(cell(page, "greeting")).toHaveAttribute("data-state", "pass");
    await expect(cell(page, "order-status")).toHaveAttribute("data-state", "running");
    await shoot(page, "run-live");
  });

  await test.step("the run ends: final states, the interval, no baseline yet", async () => {
    gate.open();
    await expect(page.getByText("Completed", { exact: true })).toBeVisible({ timeout: 150_000 });
    await expect(page.getByRole("progressbar")).toHaveCount(0);
    await expect(cell(page, "greeting")).toHaveAttribute("data-state", "pass");
    await expect(cell(page, "refund-outside-window")).toHaveAttribute("data-state", "pass");
    await expect(cell(page, "order-status")).toHaveAttribute("data-state", "flaky");
    await expect(cell(page, "order-status")).toContainText("Flaky"); // the word, not only the mark
    const stats = page.getByRole("region", { name: "Statistics" });
    await expect(stats).toContainText(/95% CI \d+\.\d%–\d+\.\d%/);
    await expect(stats).toContainText("no verdict and no p-value");
    await expect(stats).toContainText("1 flaky");
  });

  await test.step("set it as the baseline from the page", async () => {
    await page.getByRole("button", { name: "Set as baseline" }).click();
    await page.getByRole("dialog", { name: "Set as baseline" }).getByRole("button", { name: "Set baseline" }).click();
    // The page refetches the run, then the verdict: a few queries against the test database.
    await expect(page.getByRole("region", { name: "Statistics" })).toContainText("This run is the main baseline", { timeout: 20_000 });
  });

  await noOverflow(page, "run board");
  expect(problems, problems.join("\n")).toEqual([]);
});

test("a v2 run against the baseline: the verdict in numbers, the clusters, and no flash under reduced motion", async ({ page, baseURL }) => {
  const problems = watch(page);
  await pointAgentAt(page, baseURL!, gates.v2!.url);
  const gate = gates.v2!;
  gate.hold();
  v2Run = (await post(page.request, baseURL!, `/suites/${suiteId}/runs`, {})).id;

  await page.emulateMedia({ reducedMotion: "reduce" });
  const stream = page.waitForResponse((r) => r.url().includes(`/runs/${v2Run}/stream?token=`));
  await page.goto(`/projects/${projectId}/runs/${v2Run}`);
  await stream;
  await expect(page.getByText("Live", { exact: true })).toBeVisible();
  const flashes = await countFlashes(page);
  for (let i = 0; i < 3; i++) {
    await expect.poll(gate.held).toBeGreaterThan(0);
    gate.releaseOne();
  }
  await expect(page.getByRole("progressbar", { name: "Attempts finished" })).toHaveAttribute("aria-valuenow", "3");
  await expect(cell(page, "greeting")).toHaveAttribute("data-state", "running");
  expect(await flashes()).toBe(0);
  await page.emulateMedia({ reducedMotion: "no-preference" });

  gate.open();
  await expect(page.getByText("Completed", { exact: true })).toBeVisible({ timeout: 150_000 });

  await test.step("the statistics panel states the regression with its figures", async () => {
    const stats = page.getByRole("region", { name: "Statistics" });
    // The verdict compares two runs' summaries: several queries, slow against a remote test database.
    await expect(stats.locator("span").filter({ hasText: /^Regression$/ })).toBeVisible({ timeout: 20_000 });
    await expect(stats).toContainText("1 case (refund-outside-window) dropped significantly");
    await expect(stats).toContainText(/Effect size\s*[−+±]\d+\.\d pts/);
    const tests = page.getByRole("region", { name: "Per-case tests" });
    const refund = tests.getByRole("row").filter({ has: page.getByRole("rowheader", { name: "refund-outside-window" }) });
    await expect(refund).toContainText("10/10");
    await expect(refund).toContainText("0/10");
    await expect(refund).toContainText("Regressed");
    await expect(refund.getByRole("cell").nth(3)).toHaveText(/^\d\.\de-\d+$/); // its p-value
    await expect(refund.getByRole("cell").nth(4)).toHaveText(/^0\.\d{4}$/); // its corrected threshold
    await expect(tests).toContainText("not an adjusted p-value");
    await expect(cell(page, "refund-outside-window")).toHaveAttribute("data-state", "fail");
  });

  await test.step("the failure clusters name the refund case and open a trace", async () => {
    const clusters = page.getByRole("region", { name: "Failure clusters" });
    await expect(clusters.getByRole("list", { name: "Failure clusters" })).toBeVisible();
    await expect(clusters).toContainText("refund-outside-window");
    await expect(clusters.getByRole("link", { name: "First trace" }).first()).toHaveAttribute("href", /\/results\/[0-9a-f-]+$/);
  });

  await shoot(page, "run-complete");
  await noOverflow(page, "run board");
  expect(problems, problems.join("\n")).toEqual([]);
});

test("the hostile case's trace: every payload is inert text, steps fold, copy is safe", async ({ page, context, baseURL }) => {
  const problems = watch(page);
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: baseURL });
  await page.goto(`/projects/${projectId}/runs/${v2Run}`);
  await page.getByRole("link", { name: /^hostile-input: / }).click();
  await expect(page.getByRole("heading", { level: 1, name: "hostile-input" })).toBeVisible();
  const main = page.getByRole("main");

  await test.step("nothing in the text became markup or ran", async () => {
    const steps = page.getByRole("list", { name: "Trace steps" });
    await expect(steps).toContainText(`<img src=x onerror="window.__pwned=1"><script>window.__pwned=2</script> **bold**`);
    await expect(steps).toContainText("␛[31mRED␛[0m ␛]8;;https://evil.example␇click");
    await expect(steps).toContainText("invoice⟨U+202E⟩fdp.exe");
    await expect(main.locator("img, iframe, strong, em")).toHaveCount(0);
    await expect(main.locator("script")).toHaveCount(0);
    for (const href of await main.locator("a").evaluateAll((as) => as.map((a) => a.getAttribute("href") ?? ""))) {
      expect(href).not.toMatch(/^javascript:|evil\.example/);
    }
    expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
    // Raw escapes must never reach the page's text.
    expect(await main.evaluate((el) => /[\u001b‮]/.test(el.textContent ?? ""))).toBe(false);
  });

  await test.step("a step folds and unfolds; its copy button copies the inert text", async () => {
    const first = page.getByRole("list", { name: "Trace steps" }).locator(":scope > li").first();
    await first.getByRole("button", { name: "Copy step 1" }).click();
    const copied = await page.evaluate(() => navigator.clipboard.readText());
    expect(copied).toContain("␛[31mRED");
    expect(copied).not.toContain("\u001b");
    await first.locator("summary").click();
    await expect(first.locator("details")).not.toHaveAttribute("open");
    await first.locator("summary").click();
    await expect(first.locator("details")).toHaveAttribute("open");
  });

  await test.step("the whole trace copies as JSON with the escapes encoded, not raw", async () => {
    await page.getByRole("button", { name: "Copy the trace as JSON" }).click();
    const json = await page.evaluate(() => navigator.clipboard.readText());
    expect(json).not.toMatch(/[\u001b‮]/);
    expect(JSON.parse(json).input).toContain("\u001b[31mRED"); // the same value, losslessly
  });

  await test.step("the verdict panel lists the judges and links their step", async () => {
    const verdicts = page.getByRole("region", { name: "Judge verdicts" });
    await expect(verdicts).toContainText("not_contains");
    await expect(verdicts).toContainText(/\d of 1 passed/);
  });

  await shoot(page, "trace");
  await noOverflow(page, "trace");
  expect(problems, problems.join("\n")).toEqual([]);
});

test("the runs list: status chips, filters, sort and pages, all in the URL", async ({ page, baseURL }) => {
  const problems = watch(page);
  // A third run, cancelled while its first attempt is held.
  await pointAgentAt(page, baseURL!, gates.v1!.url);
  gates.v1!.hold();
  cancelledRun = (await post(page.request, baseURL!, `/suites/${suiteId}/runs`, {})).id;
  await expect.poll(gates.v1!.held).toBeGreaterThan(0);
  await post(page.request, baseURL!, `/runs/${cancelledRun}/cancel`, {});
  gates.v1!.open();
  await expect
    .poll(async () => (await (await page.request.get(`/api/runs/${cancelledRun}`)).json()).status, { timeout: 60_000 })
    .toBe("cancelled");

  await page.goto(`/projects/${projectId}/runs`);
  const table = page.getByRole("table", { name: "Runs" });
  const ids = async () =>
    (await table.locator("tbody tr a").evaluateAll((as) => as.map((a) => a.getAttribute("href")?.split("/").pop() ?? ""))).filter(Boolean);

  await test.step("newest first, each with its status chip", async () => {
    await expect(table.locator("tbody tr")).toHaveCount(3);
    expect(await ids()).toEqual([cancelledRun, v2Run, v1Run]);
    await expect(table.getByText("Cancelled", { exact: true })).toHaveCount(1);
    await expect(table.getByText("Completed", { exact: true })).toHaveCount(2);
    await expect(table.getByText("Baseline · main")).toHaveCount(1);
    await expect(page.getByText("1–3 of 3")).toBeVisible();
  });

  await test.step("filter by status and branch", async () => {
    await page.getByTestId("runs-status").selectOption("cancelled");
    await expect(page).toHaveURL(/\?status=cancelled$/);
    await expect(table.locator("tbody tr")).toHaveCount(1);
    expect(await ids()).toEqual([cancelledRun]);
    // A run opened from a filtered list comes Back to the same filtered list.
    await table.getByRole("link").first().click();
    await expect(page).toHaveURL(new RegExp(`/runs/${cancelledRun}$`));
    await page.goBack();
    await expect(page).toHaveURL(/\?status=cancelled$/);
    await expect(page.getByTestId("runs-status")).toHaveValue("cancelled");
    await expect(table.locator("tbody tr")).toHaveCount(1);

    await page.getByTestId("runs-status").selectOption("");
    await page.getByTestId("runs-branch").fill("no-such-branch");
    await expect(page.getByText("No runs match")).toBeVisible();
    await expect(page).toHaveURL(/branch=no-such-branch/);
    // The nav's Runs link is the default view: the box follows the URL rather than re-applying itself.
    await page.getByRole("navigation", { name: "Project sections" }).getByRole("link", { name: "Runs" }).click();
    await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/runs$`));
    await expect(page.getByTestId("runs-branch")).toHaveValue("");
    await expect(table.locator("tbody tr")).toHaveCount(3);
    await page.waitForTimeout(500); // past the box's debounce: it must not put the old branch back
    await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/runs$`));
  });

  await test.step("sort by pass rate on the server; unknown rates last", async () => {
    // The expected order from the API's own figures: a cancelled run may or may not have one.
    const rates = new Map<string, number | null>();
    for (const id of [v1Run, v2Run, cancelledRun]) rates.set(id, (await (await page.request.get(`/api/runs/${id}`)).json()).pass_rate);
    expect(rates.get(v2Run)!).toBeLessThan(rates.get(v1Run)!); // v2 lost the refund case
    const byRate = (dir: 1 | -1) =>
      [v1Run, v2Run, cancelledRun].toSorted((a, b) => {
        const [x, y] = [rates.get(a), rates.get(b)];
        return x == null ? 1 : y == null ? -1 : dir * (x - y);
      });
    await table.getByRole("button", { name: "Pass rate" }).click();
    await expect(page).toHaveURL(/sort=pass_rate&order=asc/);
    await expect.poll(ids).toEqual(byRate(1));
    await expect(table.getByRole("columnheader", { name: "Pass rate" })).toHaveAttribute("aria-sort", "ascending");
    await table.getByRole("button", { name: "Pass rate" }).click();
    await expect.poll(ids).toEqual(byRate(-1));
  });

  await test.step("pages: the API's total drives the pager, and a page is an offset", async () => {
    // Three runs fit one page; report 60 to exercise the pager without 60 real runs.
    const offsets: string[] = [];
    const runsList = (url: URL) => /^\/api\/projects\/[^/]+\/runs$/.test(url.pathname);
    await page.route(runsList, async (route) => {
      offsets.push(new URL(route.request().url()).searchParams.get("offset") ?? "");
      const response = await route.fetch();
      await route.fulfill({ response, headers: { ...response.headers(), "x-total-count": "60" } });
    });
    await page.goto(`/projects/${projectId}/runs`);
    const pager = page.getByRole("navigation", { name: "Runs pages" });
    await expect(pager.getByRole("button", { name: "Page 3" })).toBeVisible();
    await pager.getByRole("button", { name: "Page 2" }).click();
    await expect(page).toHaveURL(/\?page=2$/);
    await expect.poll(() => offsets.at(-1)).toBe("25");
    await expect(pager.getByRole("button", { name: "Page 2" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByText("No runs yet")).toBeVisible(); // page 2 of three real runs is empty
    await page.unrouteAll({ behavior: "wait" });
  });

  await page.goto(`/projects/${projectId}/runs`);
  await expect(table.locator("tbody tr")).toHaveCount(3);
  await shoot(page, "runs");
  await noOverflow(page, "runs");
  expect(problems, problems.join("\n")).toEqual([]);
});
