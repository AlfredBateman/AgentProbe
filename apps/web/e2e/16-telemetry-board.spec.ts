import path from "node:path";
import { type APIRequestContext, expect, type Page, test } from "@playwright/test";
import { DEMO_AGENTS_URL, TELEMETRY_EMAIL } from "./fixtures";

// The rebuilt overview, agents and suites pages on real data: a v1 baseline, a v2 run that
// regresses one case, one flaky case, an HTTP and an MCP agent, and an invalid suite edit. The
// last test writes docs/screenshots/app/* (SCREENSHOTS=1), against the same data.
test.describe.configure({ timeout: 240_000, mode: "serial" });

const PASSWORD = "correct horse battery staple telemetry";
const SCREENSHOT_DIR = path.resolve(__dirname, "../../../docs/screenshots/app");

// 10 attempts per case, as in the main flow: order-status's seeded 0.5 flakiness then almost
// certainly shows both outcomes, and refund-outside-window's v1 to v2 drop reaches significance.
const SUITE_YAML = `suite: telemetry-check
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
      - judge: tool_args_match
        tool: lookup_order
        args: {order_id: "1042"}
  - id: refund-outside-window
    input: "Can I get a refund after 45 days?"
    expect:
      - judge: contains_any
        values: ["30 days", "not eligible"]
      - judge: tool_not_called
        tool: issue_refund
`;

let projectId = "";
let suiteId = "";

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

// Each test has its own browser context, so each signs in again; the account exists after set-up.
test.beforeEach(async ({ page, baseURL }, testInfo) => {
  if (!projectId || testInfo.title.startsWith("set up")) return;
  await post(page.request, baseURL!, "/auth/login", { email: TELEMETRY_EMAIL, password: PASSWORD });
});

test("set up: two agents, a suite, a v1 baseline and a v2 run", async ({ page, baseURL }) => {
  await post(page.request, baseURL!, "/auth/register", { email: TELEMETRY_EMAIL, password: PASSWORD });
  projectId = (await post(page.request, baseURL!, "/projects", { name: "e2e-telemetry" })).id;
  const v1 = `${DEMO_AGENTS_URL}/support/v1/chat`;
  const agent = await post(page.request, baseURL!, `/projects/${projectId}/agents`, {
    name: "support-v1",
    // The mapping the agent form defaults to: without `tool_calls` the tool judges cannot run.
    config: {
      adapter_type: "http",
      url: v1,
      allow_private: true,
      response: { output: "$.output", tool_calls: "$.tool_calls", tool_name: "$.tool", tool_arguments: "$.arguments", total_tokens: "$.usage.total_tokens" },
    },
  });
  await post(page.request, baseURL!, `/projects/${projectId}/agents`, {
    name: "mcp-tools",
    config: { adapter_type: "mcp", transport: "http", url: `${DEMO_AGENTS_URL}/mcp-tools/mcp`, allow_private: true },
  });
  suiteId = (await post(page.request, baseURL!, `/projects/${projectId}/suites`, { yaml: SUITE_YAML })).id;

  const first = await post(page.request, baseURL!, `/suites/${suiteId}/runs`, {});
  await waitForRun(page.request, first.id);
  await post(page.request, baseURL!, `/projects/${projectId}/baseline`, { branch: "main", run_id: first.id });

  const put = await page.request.put(`/api/agents/${agent.id}`, {
    data: { config: { ...agent.config, adapter_type: "http", url: `${DEMO_AGENTS_URL}/support/v2/chat` } },
    headers: { Origin: baseURL! },
  });
  expect(put.ok(), await put.text()).toBe(true);
  const second = await post(page.request, baseURL!, `/suites/${suiteId}/runs`, {});
  await waitForRun(page.request, second.id);
});

test("the overview board reads the latest run: flaky and regressed cases, the baseline, quick actions", async ({ page }) => {
  const problems = watch(page);
  await page.goto(`/projects/${projectId}`);
  await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();

  await test.step("the tiles hold the latest run's real figures", async () => {
    const baseline = page.getByTestId("overview-baseline");
    await expect(baseline).toContainText("main baseline");
    await expect(baseline).toContainText(/\d+\.\d%/); // the v1 run's pass rate, counted up
    const regressed = page.getByRole("term").filter({ hasText: "Regressed cases" }).locator("xpath=..");
    await expect(regressed).toContainText("against the main baseline");
    await expect(regressed.locator("dd").first()).toHaveText("1"); // refund-outside-window
    const flaky = page.getByRole("term").filter({ hasText: "Flaky cases" }).locator("xpath=..");
    await expect(flaky).toContainText("of 3 cases");
  });

  await test.step("the flakiness panel names the flaky case and its attempts", async () => {
    const panel = page.getByRole("region", { name: "Flakiness" });
    await expect(panel.getByRole("link", { name: "order-status" })).toBeVisible();
    await expect(panel.getByText(/^\d+\/10$/)).toBeVisible();
    await expect(panel.getByText("Flaky", { exact: true })).toBeVisible(); // the word, not only the mark
  });

  await test.step("the regression panel carries the verdict and the case that fired", async () => {
    const panel = page.getByRole("region", { name: "Regression" });
    await expect(panel.locator("span").filter({ hasText: /^Regression$/ })).toBeVisible(); // the badge, not the title
    await expect(panel).toContainText("refund-outside-window");
    await panel.getByRole("link", { name: "Open the comparison" }).click();
    await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+\/compare$/);
  });

  await test.step("quick actions go where they say", async () => {
    await page.goto(`/projects/${projectId}`);
    const actions = page.getByRole("region", { name: "Quick actions" });
    await actions.getByRole("link", { name: "Add an agent" }).click();
    await expect(page).toHaveURL(`/projects/${projectId}/agents`);
    await page.goBack();
    await page.getByRole("region", { name: "Quick actions" }).getByRole("button", { name: "Run a suite" }).click();
    await expect(page.getByRole("dialog", { name: "Run a suite" })).toBeVisible();
    await page.keyboard.press("Escape");
  });

  await noOverflow(page, "overview");
  expect(problems, problems.join("\n")).toEqual([]);
});

test("agents: adapter chips, with MCP marked CLI only", async ({ page }) => {
  const problems = watch(page);
  await page.goto(`/projects/${projectId}/agents`);
  await expect(page.getByRole("heading", { level: 1, name: "Agents" })).toBeVisible();

  const types = page.getByRole("list", { name: "Adapter types in this project" });
  await expect(types.getByRole("listitem")).toHaveCount(2);
  await expect(types.getByRole("listitem").filter({ hasText: "HTTP" })).toContainText("1");
  await expect(types.getByRole("listitem").filter({ hasText: "MCP" })).toContainText("CLI only");

  const table = page.getByRole("table", { name: "Agents" });
  await expect(table.locator("tr").filter({ hasText: "mcp-tools" })).toContainText("CLI only");
  await expect(table.locator("tr").filter({ hasText: "support-v1" })).not.toContainText("CLI only");

  // Choosing MCP in the dialog says it too, and keeps the verbatim name as typed.
  await page.getByTestId("new-agent").click();
  const dialog = page.getByRole("dialog", { name: "New agent" });
  await dialog.getByTestId("agent-adapter").selectOption("mcp");
  await expect(dialog).toContainText("run MCP suites with the CLI");
  await expect(dialog.getByText("CLI only")).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();

  await noOverflow(page, "agents");
  expect(problems, problems.join("\n")).toEqual([]);
});

test("suites: the list, the editor with inline problems, the cases table", async ({ page }) => {
  const problems = watch(page);
  await page.goto(`/projects/${projectId}/suites`);
  const list = page.getByRole("table", { name: "Suites" });
  await expect(list.locator("tbody tr")).toHaveCount(1);
  await expect(page.getByTestId("run-suite-telemetry-check")).toBeEnabled();
  await list.getByRole("link", { name: "telemetry-check" }).click();

  // The title is data: it keeps the case the user wrote.
  const title = page.getByRole("heading", { level: 1, name: "telemetry-check" });
  await expect(title).toBeVisible();
  expect(await title.evaluate((el) => getComputedStyle(el).textTransform)).toBe("none");

  await test.step("a bad edit marks its line in the gutter and lists the problem in the frame", async () => {
    const editor = page.getByTestId("suite-editor");
    await editor.fill(SUITE_YAML.replace("runs_per_case: 10", "runs_per_case: 99"));
    const issues = page.getByTestId("suite-issues");
    await expect(issues).toContainText("Line 3: runs_per_case");
    await expect(page.locator("figure").filter({ has: issues })).toContainText("suite.yaml");
    await expect(page.getByTestId("save-suite")).toBeDisabled();
    await issues.getByRole("button").first().click();
    await expect(editor).toBeFocused();
    expect(await editor.evaluate((el: HTMLTextAreaElement) => el.value.slice(el.selectionStart, el.selectionEnd))).toBe("runs_per_case: 99");
    await page.getByRole("button", { name: "Discard" }).click();
    await expect(page.getByTestId("suite-validation")).toHaveText("Valid · 3 cases");
  });

  await test.step("the cases tab is a dense table", async () => {
    await page.getByRole("tab", { name: "Cases" }).click();
    const cases = page.getByRole("table", { name: "Cases in version 1" });
    await expect(cases.locator("tbody tr")).toHaveCount(3);
    await expect(cases.getByRole("cell", { name: "order-status", exact: true })).toBeVisible();
  });

  await noOverflow(page, "suite");
  expect(problems, problems.join("\n")).toEqual([]);
});

test("after a long idle the Run button says the API is waking, then unlocks", async ({ page }) => {
  await page.goto(`/projects/${projectId}/agents`);
  await expect(page.getByRole("heading", { level: 1, name: "Agents" })).toBeVisible();
  // The platform holds /api/health until the service is up; the app's wake logic re-checks an
  // API that has been quiet for ten minutes, so make this one 15 minutes quiet.
  await page.clock.install();
  await page.route("**/api/health", async (route) => {
    await new Promise((r) => setTimeout(r, 4_000));
    await route.continue();
  });
  await page.clock.fastForward("15:00");
  await page.getByRole("navigation", { name: "Project sections" }).getByRole("link", { name: /^Project overview/ }).click();

  const run = page.getByTestId("run-a-suite");
  await expect(run).toBeDisabled();
  await expect(run).toHaveText("Waking…");
  await expect(page.getByText("Run unlocks when it answers.")).toBeAttached();
  await expect(run).toHaveText("Run", { timeout: 20_000 });
  await expect(run).toBeEnabled();
});

// Writes docs/screenshots/app/*: SCREENSHOTS=1 pnpm e2e. Off by default, so an ordinary run does
// not rewrite committed images with this machine's font rasterization.
test("screenshots at 1440, 810 and 390px", async ({ page, baseURL }) => {
  test.skip(!process.env.SCREENSHOTS, "set SCREENSHOTS=1 to write docs/screenshots/app");
  test.setTimeout(180_000);
  const sizes = [
    { width: 1440, height: 900 },
    { width: 810, height: 1000 },
    { width: 390, height: 844 },
  ];
  async function shoot(name: string) {
    for (const size of sizes) {
      await page.setViewportSize(size);
      await page.evaluate(() => document.fonts.ready);
      await expect(page.locator('[class*="skeleton-step"]')).toHaveCount(0);
      // Scroll through the page as a reader would: rows below the fold reveal when they come into view.
      const height = await page.evaluate(() => document.documentElement.scrollHeight);
      for (let y = 0; y <= height; y += size.height / 2) {
        await page.mouse.wheel(0, size.height / 2);
        await page.waitForTimeout(60);
      }
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.waitForTimeout(900); // the reveals, the count-up and the page wipe have played
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${name}-${size.width}.png`), fullPage: true });
    }
    await page.setViewportSize(sizes[0]);
  }

  // An empty project, for the overview's empty state.
  const empty = await post(page.request, baseURL!, "/projects", { name: "checkout-assistant" });
  await page.goto(`/projects/${empty.id}`);
  await expect(page.getByText("No runs yet")).toBeVisible();
  await shoot("project-overview");

  await page.goto(`/projects/${projectId}`);
  await expect(page.getByRole("region", { name: "Regression" }).locator("span").filter({ hasText: /^Regression$/ })).toBeVisible();
  await expect(page.getByRole("figure", { name: /^Pass rate/ })).toBeVisible();
  await shoot("project-overview-runs");

  await page.goto(`/projects/${projectId}/agents`);
  await expect(page.getByRole("table", { name: "Agents" })).toBeVisible();
  await shoot("agents");
  await page.getByTestId("new-agent").click();
  await page.getByRole("dialog").getByTestId("agent-adapter").selectOption("mcp");
  await shoot("agents-dialog-mcp");
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();

  await page.goto(`/projects/${projectId}/suites`);
  await expect(page.getByRole("table", { name: "Suites" })).toBeVisible();
  await shoot("suites");

  await page.getByRole("link", { name: "telemetry-check" }).click();
  await expect(page.getByTestId("suite-editor")).toBeVisible();
  await shoot("suite-editor");
  await page.getByTestId("suite-editor").fill(SUITE_YAML.replace("runs_per_case: 10", "runs_per_case: 99"));
  await expect(page.getByTestId("suite-issues")).toBeVisible();
  await page.getByTestId("suite-issues").getByRole("button").first().click(); // scrolls the marked line into view
  await shoot("suite-editor-invalid");
  await page.getByRole("button", { name: "Discard" }).click();
  await page.getByRole("tab", { name: "Cases" }).click();
  await expect(page.getByRole("table", { name: "Cases in version 1" })).toBeVisible();
  await shoot("suite-cases");
});
