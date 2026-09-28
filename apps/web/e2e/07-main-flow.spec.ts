import { expect, test } from "@playwright/test";
import { AgentsPage } from "./pages/agents-page";
import { ComparePage } from "./pages/compare-page";
import { ProjectsPage } from "./pages/projects-page";
import { RegisterPage } from "./pages/register-page";
import { RunPage } from "./pages/run-page";
import { SharedPage } from "./pages/shared-page";
import { SuitesPage } from "./pages/suites-page";
import { DEMO_AGENTS_URL, MAIN_FLOW_EMAIL } from "./fixtures";

// SPEC.md §11's main flow, end to end through the real UI (no API shortcuts for setup): register
// -> create project -> add agent -> test connection -> create suite from YAML -> run -> watch
// live progress -> open a failing trace -> run against /support/v2 -> compare shows a
// regression -> create a share link -> open it logged out.
test.describe.configure({ timeout: 180_000 });

const PASSWORD = "correct horse battery staple main-flow";

// 10 runs/case: enough that order-status's seeded 0.5 flakiness (near-)certainly produces a
// failing attempt to open a trace on, and enough for refund-outside-window's v1->v2 regression
// to reach significance (ADR 0014's power limit needs 5+; this uses double that for headroom).
const MAIN_FLOW_YAML = `
suite: main-flow
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
  - id: refund-inside-window
    input: "I bought it 10 days ago, can I get a refund?"
    expect:
      - judge: tool_called
        tool: issue_refund
  - id: refund-outside-window
    input: "Can I get a refund after 45 days?"
    expect:
      - judge: contains_any
        values: ["30 days", "not eligible"]
      - judge: tool_not_called
        tool: issue_refund
`;

test("register -> project -> agent -> suite -> run -> trace -> v2 regression -> share", async ({ page, browser }) => {
  let projectId = "";
  let v1RunId = "";
  let v2RunId = "";
  let shareLink = "";

  await test.step("register", async () => {
    const register = new RegisterPage(page);
    await register.goto();
    await register.register(MAIN_FLOW_EMAIL, PASSWORD);
    await expect(page).toHaveURL("/projects");
  });

  await test.step("create a project", async () => {
    const projects = new ProjectsPage(page);
    projectId = await projects.createProject("e2e-main-flow");
  });

  await test.step("add an agent and test its connection", async () => {
    const agents = new AgentsPage(page, projectId);
    await agents.goto();
    await agents.openNew();
    await agents.fillName("support-v1");
    await agents.fillUrl(`${DEMO_AGENTS_URL}/support/v1/chat`);
    await expect(page.getByLabel(/Allow private targets/)).toBeChecked(); // default: on
    expect(await agents.testConnection()).toBe("Connection succeeded");
    await agents.save();
    await expect(page.locator("tr").filter({ hasText: "support-v1" })).toBeVisible();
  });

  await test.step("create a suite from YAML and run it", async () => {
    const suites = new SuitesPage(page, projectId);
    await suites.goto();
    await suites.openNew();
    await suites.pasteYaml(MAIN_FLOW_YAML);
    await suites.create();
    await expect(page.locator("tr").filter({ hasText: "main-flow" })).toBeVisible();
    v1RunId = await suites.run("main-flow");
  });

  await test.step("watch it run live, then open a failing trace", async () => {
    const run = new RunPage(page, projectId, v1RunId);
    // Set up before navigating: the run page opens this stream itself on mount (ADR 0031), and
    // by the time the response starts, the live panel is already in the DOM.
    const stream = page.waitForResponse((r) => r.url().includes(`/runs/${v1RunId}/stream?token=`));
    await run.goto();
    await stream;
    await expect(page.getByRole("progressbar", { name: "Attempts finished" })).toBeVisible();
    await run.waitForCompletion();
    await run.openFailingTrace("order-status");
    await expect(page.getByRole("heading", { name: "order-status" })).toBeVisible();
    await expect(page.getByText(/^(Failed|Error)$/).first()).toBeVisible();
  });

  await test.step("re-point the agent at /support/v2 and run again", async () => {
    const agents = new AgentsPage(page, projectId);
    await agents.goto();
    await agents.openEdit("support-v1");
    await agents.fillUrl(`${DEMO_AGENTS_URL}/support/v2/chat`);
    await agents.save();

    const suites = new SuitesPage(page, projectId);
    await suites.goto();
    v2RunId = await suites.run("main-flow");
    const run = new RunPage(page, projectId, v2RunId);
    await run.goto();
    await run.waitForCompletion();
  });

  await test.step("compare shows a regression on the refund case", async () => {
    const run = new RunPage(page, projectId, v2RunId);
    await run.goto();
    await run.goToCompare();
    const compare = new ComparePage(page);
    await compare.pickBaseline(v1RunId);
    await compare.waitForVerdict("Regression");
    await expect(page.getByText("refund-outside-window").first()).toBeVisible();
    await compare.openCaseDiff("refund-outside-window");
    await expect(page).toHaveURL(/\/results\/[0-9a-f-]+\?compare=/);
  });

  await test.step("create a share link and open it logged out", async () => {
    const run = new RunPage(page, projectId, v2RunId);
    await run.goto();
    await run.openShareDialog();
    shareLink = await run.createShareLink();
  });

  await test.step("the share link works without a session", async () => {
    const token = shareLink.split("/shared/").pop();
    const anon = await browser.newContext();
    const anonPage = await anon.newPage();
    const shared = new SharedPage(anonPage);
    await shared.goto(`/shared/${token}`);
    await shared.expectReadOnlyView("main-flow");
    await anon.close();
  });
});
