import { expect, type Page } from "@playwright/test";

/** The Agents page: add/edit an HTTP agent and test its connection before saving. */
export class AgentsPage {
  constructor(
    private readonly page: Page,
    private readonly projectId: string,
  ) {}

  async goto() {
    await this.page.goto(`/projects/${this.projectId}/agents`);
  }

  async openNew() {
    await this.page.getByTestId("new-agent").click();
  }

  async openEdit(name: string) {
    await this.page
      .locator("tr")
      .filter({ hasText: name })
      .getByRole("button", { name: "Edit" })
      .click();
  }

  async fillUrl(url: string) {
    await this.page.getByTestId("agent-url").fill(url);
  }

  async fillName(name: string) {
    await this.page.getByTestId("agent-name").fill(name);
  }

  async allowPrivate(allow: boolean) {
    const checkbox = this.page.getByLabel(/Allow private targets/);
    if (allow) await checkbox.check();
    else await checkbox.uncheck();
  }

  /** Clicks Test connection and returns the result message shown in the dialog. Waits for the
   * text to change (not just for the element to exist), since a re-test replaces the same
   * data-testid and a stale read could otherwise catch the previous result. */
  async testConnection(): Promise<string> {
    const result = this.page.getByTestId("test-connection-result");
    const before = (await result.count()) ? await result.textContent() : null;
    await this.page.getByTestId("test-connection").click();
    await expect
      .poll(async () => ((await result.count()) ? await result.textContent() : null))
      .not.toBe(before);
    return (await result.textContent()) ?? "";
  }

  async save() {
    await this.page.getByRole("button", { name: "Save" }).click();
  }

  async cancel() {
    await this.page.getByRole("button", { name: "Cancel" }).click();
  }
}
