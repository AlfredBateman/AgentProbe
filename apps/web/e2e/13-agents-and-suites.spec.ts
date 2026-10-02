import { type APIRequestContext, expect, type Page, test } from "@playwright/test";
import { AGENTS_SUITES_EMAIL, DEMO_AGENTS_URL } from "./fixtures";
import { SuitesPage } from "./pages/suites-page";

// E3 through the UI: an HTTP agent with plain headers and an auth header, an edit that keeps
// what the form doesn't show, testing a saved agent, an MCP agent, the suite editor (validation,
// a new version), the case browser, version history with its diff, running from the suite page,
// and the delete warning.
test.describe.configure({ timeout: 150_000 });

const PASSWORD = "correct horse battery staple agents-suites";
const SUITE_YAML = `suite: e3-check
agent: support-v1
runs_per_case: 2
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

async function post(request: APIRequestContext, baseURL: string, urlPath: string, data: object) {
  const response = await request.post(`/api${urlPath}`, { data, headers: { Origin: baseURL } });
  expect(response.ok(), `${urlPath}: ${await response.text()}`).toBe(true);
  return response.json();
}

const getJson = async (page: Page, urlPath: string) => (await page.request.get(`/api${urlPath}`)).json();
const row = (page: Page, name: string) => page.getByRole("table", { name: "Agents" }).locator("tr").filter({ hasText: name });

test("agents with full config and auth headers; suites with an editor, cases and versions", async ({ page, baseURL }) => {
  await post(page.request, baseURL!, "/auth/register", { email: AGENTS_SUITES_EMAIL, password: PASSWORD });
  const project = await post(page.request, baseURL!, "/projects", { name: "e2e-agents-suites" });
  const agentsUrl = `/projects/${project.id}/agents`;

  await test.step("add an HTTP agent with a plain header and an auth header, tested before saving", async () => {
    await page.goto(agentsUrl);
    await page.getByTestId("new-agent").click();
    const dialog = page.getByRole("dialog", { name: "New agent" });
    await dialog.getByTestId("agent-name").fill("support-v1");
    await dialog.getByTestId("agent-url").fill(`${DEMO_AGENTS_URL}/support/v1/chat`);
    await dialog.getByTestId("auth-value").fill("Bearer fake-e2e-token");
    await dialog.getByText("Request and limits").click();
    await dialog.getByTestId("agent-template").fill("{not json");
    await dialog.getByTestId("test-connection").click();
    await expect(dialog.getByText("Not valid JSON.")).toBeVisible();
    await dialog.getByTestId("agent-template").fill('{"input": "{{input}}", "documents": "{{documents}}"}');
    await dialog.getByTestId("agent-headers").fill("X-Team: e2e");
    await dialog.getByTestId("test-connection").click();
    await expect(dialog.getByTestId("test-connection-result")).toHaveText("Connection succeeded");
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(row(page, "support-v1")).toContainText("Set");
  });

  const [agent] = await getJson(page, `/projects/${project.id}/agents`);
  expect(agent.config.headers).toEqual({ "X-Team": "e2e" });
  expect(agent.has_secret).toBe(true);

  await test.step("editing the URL keeps the headers, template and auth header", async () => {
    // A field the form doesn't show, set through the API: the edit must not reset it.
    const custom = { ...agent.config, adapter_type: "http", response: { ...agent.config.response, input_tokens: "$.usage.prompt" } };
    const put = await page.request.put(`/api/agents/${agent.id}`, { data: { config: custom }, headers: { Origin: baseURL! } });
    expect(put.ok()).toBe(true);
    await page.reload();
    await row(page, "support-v1").getByRole("button", { name: "Edit" }).click();
    const dialog = page.getByRole("dialog", { name: "Edit agent" });
    await expect(dialog.getByTestId("auth-state")).toHaveText("An auth header is stored.");
    await dialog.getByTestId("agent-url").fill(`${DEMO_AGENTS_URL}/support/v1/chat?edited=1`);
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(dialog).toBeHidden();
    const edited = await getJson(page, `/agents/${agent.id}`);
    expect(edited.config.url).toContain("edited=1");
    expect(edited.config.headers).toEqual({ "X-Team": "e2e" });
    expect(edited.config.request_template).toEqual(agent.config.request_template);
    expect(edited.config.response.input_tokens).toBe("$.usage.prompt");
    expect(edited.has_secret).toBe(true);
  });

  await test.step("a saved agent tests with its stored header; removing the header clears it", async () => {
    await page.getByTestId("test-agent-support-v1").click();
    await expect(page.getByText("support-v1: Connection succeeded")).toBeVisible();
    await row(page, "support-v1").getByRole("button", { name: "Edit" }).click();
    const dialog = page.getByRole("dialog", { name: "Edit agent" });
    await dialog.getByTestId("remove-auth").click();
    await expect(dialog.getByTestId("auth-state")).toHaveText("The stored auth header will be removed on save.");
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(dialog).toBeHidden();
    expect((await getJson(page, `/agents/${agent.id}`)).has_secret).toBe(false);
  });

  await test.step("add an MCP agent over HTTP", async () => {
    await page.getByTestId("new-agent").click();
    const dialog = page.getByRole("dialog", { name: "New agent" });
    await dialog.getByTestId("agent-name").fill("mcp-tools");
    await dialog.getByTestId("agent-adapter").selectOption("mcp");
    await dialog.getByTestId("agent-url").fill(`${DEMO_AGENTS_URL}/mcp-tools/mcp`);
    await dialog.getByTestId("test-connection").click();
    await expect(dialog.getByTestId("test-connection-result")).toHaveText("Connection succeeded");
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(row(page, "mcp-tools")).toContainText("mcp");
  });

  const suites = new SuitesPage(page, project.id);
  await test.step("the suite editor validates as you type and saving makes version 2", async () => {
    await suites.goto();
    await suites.openNew();
    await suites.pasteYaml(SUITE_YAML);
    await suites.create();
    await page.getByRole("link", { name: "e3-check" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "e3-check" })).toBeVisible();
    const editor = page.getByTestId("suite-editor");
    await editor.fill(SUITE_YAML.replace("runs_per_case: 2", "runs_per_case: 99"));
    await expect(page.getByTestId("suite-issues")).toContainText("Line 3: runs_per_case");
    await expect(page.getByTestId("save-suite")).toBeDisabled();
    await editor.fill(SUITE_YAML.replace("runs_per_case: 2", "runs_per_case: 3"));
    await expect(page.getByTestId("suite-validation")).toHaveText("Valid · 2 cases");
    await page.getByTestId("save-suite").click();
    await expect(page.getByText("Version 2 · 2 cases")).toBeVisible();
  });

  await test.step("the case browser and the version history with its diff", async () => {
    await page.getByRole("tab", { name: "Cases" }).click();
    const cases = page.getByRole("table", { name: "Cases in version 2" });
    await expect(cases.locator("tbody tr")).toHaveCount(2);
    await page.getByRole("button", { name: "Show case off-topic" }).click();
    await expect(page.getByText("Write me a poem about the sea.").first()).toBeVisible();

    await page.getByRole("tab", { name: "Versions (2)" }).click();
    await page.getByRole("button", { name: "Show version 2" }).click();
    const diff = page.getByTestId("yaml-diff");
    await expect(diff).toContainText("Removed: runs_per_case: 2");
    await expect(diff).toContainText("Added: runs_per_case: 3");
  });

  let runId = "";
  await test.step("run the suite from its page", async () => {
    await page.getByTestId("run-this-suite").click();
    await page.getByRole("dialog", { name: "Run a suite" }).getByTestId("start-run").click();
    await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+$/);
    runId = page.url().split("/").pop()!;
    await expect
      .poll(async () => (await getJson(page, `/runs/${runId}`)).status, { timeout: 60_000 })
      .toBe("completed");
    expect((await getJson(page, `/runs/${runId}`)).suite_version).toBe(2);
  });

  await test.step("deleting an agent warns that its runs go too", async () => {
    await page.goto(agentsUrl);
    await row(page, "support-v1").getByRole("button", { name: "Delete" }).click();
    const dialog = page.getByRole("dialog", { name: "Delete support-v1?" });
    await expect(dialog).toContainText("This also deletes its 1 run");
    await dialog.getByTestId("confirm-delete-agent").click();
    await expect(row(page, "support-v1")).toHaveCount(0);
    expect((await page.request.get(`/api/runs/${runId}`)).status()).toBe(404);
  });
});
