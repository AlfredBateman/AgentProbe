import fs from "node:fs";
import path from "node:path";
import { type APIRequestContext, expect, test } from "@playwright/test";
import { cleanupE2eAccount } from "./cleanup";
import { DEMO_AGENTS_URL, E2E_EMAIL, E2E_PASSWORD } from "./fixtures";

// Setup goes through the API (via the same /api rewrite the app uses); what's under test is
// the compare page: the verdict banner's plain-language statistics and the click-through to
// a side-by-side trace.
test.describe.configure({ timeout: 180_000 });
test.afterAll(() => cleanupE2eAccount());

// The real suite (5 runs/case): a per-case regression can only ever reach significance at 5+
// runs (ADR 0014's power limit), and this is the suite the golden tests and docs/metrics.md
// already use for the v1/v2 refund regression.
const SMOKE_YAML = fs.readFileSync(path.resolve(__dirname, "../../../suites/examples/smoke.yaml"), "utf8");

const SUPPORT_RESPONSE = { output: "$.output", tool_calls: "$.tool_calls", total_tokens: "$.usage.total_tokens" };

async function post(request: APIRequestContext, baseURL: string, urlPath: string, data: object) {
  const response = await request.post(`/api${urlPath}`, { data, headers: { Origin: baseURL } });
  expect(response.ok(), `${urlPath}: ${await response.text()}`).toBe(true);
  return response.json();
}

async function put(request: APIRequestContext, baseURL: string, urlPath: string, data: object) {
  const response = await request.put(`/api${urlPath}`, { data, headers: { Origin: baseURL } });
  expect(response.ok(), `${urlPath}: ${await response.text()}`).toBe(true);
  return response.json();
}

async function waitForRun(request: APIRequestContext, runId: string) {
  await expect
    .poll(async () => (await (await request.get(`/api/runs/${runId}`)).json()).status, { timeout: 60_000, intervals: [500] })
    .toBe("completed");
}

test("comparing /support/v1 with /support/v2 shows a regression, with the refund case newly failing and its trace reachable", async ({
  page,
  baseURL,
}) => {
  await test.step("register and run the smoke suite against v1, then v2", async () => {
    await post(page.request, baseURL!, "/auth/register", { email: E2E_EMAIL, password: E2E_PASSWORD });
  });

  const project = await post(page.request, baseURL!, "/projects", { name: "e2e-compare" });
  // smoke.yaml's `agent:` field names it support-v1; the suite's own agent name must match.
  const agent = await post(page.request, baseURL!, `/projects/${project.id}/agents`, {
    name: "support-v1",
    config: { adapter_type: "http", url: `${DEMO_AGENTS_URL}/support/v1/chat`, allow_private: true, response: SUPPORT_RESPONSE },
  });
  const suite = await post(page.request, baseURL!, `/projects/${project.id}/suites`, { yaml: SMOKE_YAML });

  const v1Run = await post(page.request, baseURL!, `/suites/${suite.id}/runs`, {});
  await waitForRun(page.request, v1Run.id);

  await put(page.request, baseURL!, `/agents/${agent.id}`, {
    config: { adapter_type: "http", url: `${DEMO_AGENTS_URL}/support/v2/chat`, allow_private: true, response: SUPPORT_RESPONSE },
  });
  const v2Run = await post(page.request, baseURL!, `/suites/${suite.id}/runs`, {});
  await waitForRun(page.request, v2Run.id);

  await test.step("the compare page names the verdict, its statistics, and the newly-failing case", async () => {
    await page.goto(`/projects/${project.id}/runs/${v2Run.id}/compare`);
    await page.getByLabel("Baseline").selectOption(v1Run.id);

    await expect(page.getByRole("heading", { name: "Verdict" })).toBeVisible();
    await expect(page.getByText("Regression", { exact: true })).toBeVisible();
    // Plain-language statistics: significance, effect size and N, not just the verdict word.
    await expect(page.getByText(/dropped significantly/)).toBeVisible();
    await expect(page.getByText(/α_cases/)).toBeVisible();
    await expect(page.getByRole("heading", { name: "Newly failing (1)" })).toBeVisible();
  });

  await test.step("clicking the case opens a side-by-side trace of both runs", async () => {
    await page.getByRole("button", { name: "refund-outside-window" }).first().click();
    await expect(page).toHaveURL(/\/results\/[0-9a-f-]+\?compare=/);
    await expect(page.getByRole("heading", { name: /^A ·/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: /^B ·/ })).toBeVisible();
  });
});
