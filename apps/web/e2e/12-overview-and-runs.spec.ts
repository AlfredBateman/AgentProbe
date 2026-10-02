import { type APIRequestContext, expect, test } from "@playwright/test";
import { DEMO_AGENTS_URL, OVERVIEW_EMAIL } from "./fixtures";

// E2: the project overview (trends, baseline indicator, latest runs, "Run a suite") and the Runs
// page the nav links to. Setup goes through the API; the first run is started from the UI.
test.describe.configure({ timeout: 120_000 });

const PASSWORD = "correct horse battery staple overview";
const SUITE_YAML = `
suite: overview-check
agent: support-v1
runs_per_case: 3
cases:
  - id: greeting
    input: "Hello there"
    expect:
      - judge: contains
        value: "How can I help?"
  - id: refund-outside-window
    input: "Can I get a refund after 45 days?"
    expect:
      - judge: contains_any
        values: ["30 days", "not eligible"]
`;

async function post(request: APIRequestContext, baseURL: string, urlPath: string, data: object) {
  const response = await request.post(`/api${urlPath}`, { data, headers: { Origin: baseURL } });
  expect(response.ok(), `${urlPath}: ${await response.text()}`).toBe(true);
  return response.json();
}

async function waitForRun(request: APIRequestContext, runId: string) {
  await expect
    .poll(async () => (await (await request.get(`/api/runs/${runId}`)).json()).status, { timeout: 60_000, intervals: [500] })
    .toBe("completed");
}

test("the overview shows trends, the baseline and latest runs; the Runs page lists and filters them", async ({ page, baseURL }) => {
  await post(page.request, baseURL!, "/auth/register", { email: OVERVIEW_EMAIL, password: PASSWORD });
  const project = await post(page.request, baseURL!, "/projects", { name: "e2e-overview" });
  await post(page.request, baseURL!, `/projects/${project.id}/agents`, {
    name: "support-v1",
    config: { adapter_type: "http", url: `${DEMO_AGENTS_URL}/support/v1/chat`, allow_private: true },
  });
  await post(page.request, baseURL!, `/projects/${project.id}/suites`, { yaml: SUITE_YAML });

  let firstRun = "";
  await test.step("an empty project offers to run a suite, and the dialog starts one", async () => {
    await page.goto(`/projects/${project.id}`);
    await expect(page.getByText("No runs yet")).toBeVisible();
    await page.getByTestId("run-a-suite").click();
    const dialog = page.getByRole("dialog", { name: "Run a suite" });
    await expect(dialog.getByLabel("Suite")).toHaveValue(/.+/);
    await dialog.getByLabel("Attempts per case").fill("0");
    await expect(dialog.getByText("A whole number from 1 to 20.")).toBeVisible();
    await expect(dialog.getByTestId("start-run")).toBeDisabled();
    await dialog.getByLabel("Attempts per case").fill("2");
    await dialog.getByTestId("start-run").click();
    await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+$/);
    firstRun = page.url().split("/").pop()!;
    await waitForRun(page.request, firstRun);
    const run = await (await page.request.get(`/api/runs/${firstRun}`)).json();
    expect([run.runs_per_case, run.mock_mode]).toEqual([2, true]);
  });

  await post(page.request, baseURL!, `/projects/${project.id}/baseline`, { branch: "main", run_id: firstRun });
  const suites = await (await page.request.get(`/api/projects/${project.id}/suites`)).json();
  const second = await post(page.request, baseURL!, `/suites/${suites[0].id}/runs`, { branch: "feature/x" });
  await waitForRun(page.request, second.id);

  await test.step("the overview: tiles, three trend charts, the baseline and the latest runs", async () => {
    await page.goto(`/projects/${project.id}`);
    await expect(page.getByTestId("overview-suite")).toHaveValue(suites[0].id);
    await expect(page.getByText("2 completed runs")).toBeVisible();
    await expect(page.getByTestId("overview-baseline")).toContainText("main baseline");
    for (const title of ["Pass rate", "Cost per run", "Mean latency"]) {
      await expect(page.getByRole("figure", { name: new RegExp(`^${title}`) })).toBeVisible();
    }
    // Two plotted charts (pass rate, latency); the mock run has no cost to plot, and says so.
    await expect(page.locator(".recharts-surface")).toHaveCount(2);
    await expect(page.getByText(/^Baseline \(main\)/)).toBeVisible();
    await expect(page.getByText(/^No cost recorded/)).toBeVisible();
    const latest = page.getByRole("table", { name: "Latest runs, all suites" });
    await expect(latest.locator("tbody tr")).toHaveCount(2);
    await expect(latest.getByText("Baseline · main")).toHaveCount(1);
    await expect(latest.getByText("feature/x")).toBeVisible();
  });

  await test.step("the nav's Runs link lists every run, filters by suite, and links each run", async () => {
    await page.getByRole("navigation", { name: "Project sections" }).getByRole("link", { name: "Runs" }).click();
    await expect(page).toHaveURL(`/projects/${project.id}/runs`);
    await expect(page.getByRole("heading", { level: 1, name: "Runs" })).toBeVisible();
    const table = page.getByRole("table", { name: "Runs" });
    await expect(table.locator("tbody tr")).toHaveCount(2);
    await page.getByTestId("runs-suite").selectOption(suites[0].id);
    await expect(table.locator("tbody tr")).toHaveCount(2);

    await table.getByRole("link", { name: "overview-check" }).first().click();
    await expect(page).toHaveURL(new RegExp(`/runs/${second.id}$`));
    // The run page's breadcrumb, not the nav link of the same name.
    await page.getByRole("main").getByRole("link", { name: "Runs", exact: true }).click();
    await expect(page).toHaveURL(`/projects/${project.id}/runs`);
  });
});
