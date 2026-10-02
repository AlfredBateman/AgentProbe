import fs from "node:fs";
import path from "node:path";
import { type APIRequestContext, expect, test } from "@playwright/test";
import { cleanupE2eAccount } from "./cleanup";
import { DEMO_AGENTS_URL, E2E_EMAIL, E2E_PASSWORD } from "./fixtures";

// Setup goes through the API; what's under test is the public /shared/[token] page: it works
// in a logged-out browser context, and shows the revoked state once the owner revokes it.
test.describe.configure({ timeout: 180_000 });
test.afterAll(() => cleanupE2eAccount());

const SMOKE_YAML = fs.readFileSync(path.resolve(__dirname, "../../../suites/examples/smoke.yaml"), "utf8");
const SUPPORT_RESPONSE = { output: "$.output", tool_calls: "$.tool_calls", total_tokens: "$.usage.total_tokens" };

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

test("a share link works in a logged-out browser context; after revoking, it shows the revoked state", async ({ page, browser, baseURL }) => {
  await test.step("register and produce a completed run", async () => {
    await post(page.request, baseURL!, "/auth/register", { email: E2E_EMAIL, password: E2E_PASSWORD });
  });
  const project = await post(page.request, baseURL!, "/projects", { name: "e2e-share" });
  await post(page.request, baseURL!, `/projects/${project.id}/agents`, {
    name: "support-v1",
    config: { adapter_type: "http", url: `${DEMO_AGENTS_URL}/support/v1/chat`, allow_private: true, response: SUPPORT_RESPONSE },
  });
  const suite = await post(page.request, baseURL!, `/projects/${project.id}/suites`, { yaml: SMOKE_YAML });
  const run = await post(page.request, baseURL!, `/suites/${suite.id}/runs`, { runs_per_case: 5 }); // a finished run is all this needs
  await waitForRun(page.request, run.id);

  await page.goto(`/projects/${project.id}/runs/${run.id}`);
  await page.getByRole("button", { name: "Share" }).click();
  await page.getByRole("button", { name: "Create link" }).click();
  const link = await page.getByLabel(/Copy it now/).inputValue();
  // The dialog shows the server's own PUBLIC_WEB_URL when set (a fake domain in dev, per
  // docs/PROGRESS.md's Known issues); only the token is real, so navigate to it locally.
  const token = link.split("/shared/").pop();

  await test.step("logged out, the link shows the sanitized read-only view", async () => {
    const anon = await browser.newContext();
    const anonPage = await anon.newPage();
    await anonPage.goto(`/shared/${token}`);
    await expect(anonPage.getByText("Shared run · read-only")).toBeVisible();
    await expect(anonPage.getByRole("heading", { name: "smoke" })).toBeVisible();
    await anon.close();
  });

  await test.step("revoking it shows the revoked state to a logged-out visitor", async () => {
    await page.getByRole("button", { name: "Revoke link" }).click();
    await expect(page.getByText("Share link revoked")).toBeVisible();

    const anon = await browser.newContext();
    const anonPage = await anon.newPage();
    await anonPage.goto(`/shared/${token}`);
    await expect(anonPage.getByText("This link doesn't work")).toBeVisible();
    await anon.close();
  });
});
