import { expect, type Page } from "@playwright/test";

/** A run's detail page: live progress, the case table, trace links, and the share dialog. */
export class RunPage {
  constructor(
    private readonly page: Page,
    private readonly projectId: string,
    readonly runId: string,
  ) {}

  async goto() {
    await this.page.goto(`/projects/${this.projectId}/runs/${this.runId}`);
  }

  async waitForCompletion(timeout = 60_000) {
    await expect(this.page.getByText("Completed", { exact: true }).first()).toBeVisible({ timeout });
  }

  /** Expands `caseId`'s row and opens the trace of its first failed or errored attempt. */
  async openFailingTrace(caseId: string) {
    await this.page.getByRole("button", { name: `Show attempts of ${caseId}` }).click();
    const attempts = this.page.getByRole("list", { name: `Attempts of ${caseId}` });
    const failing = attempts.locator("li").filter({ hasText: /Failed|Error/ }).first();
    await failing.getByRole("link", { name: "View trace" }).click();
  }

  async goToCompare() {
    await this.page.getByRole("link", { name: "Compare" }).click();
    // Not waitForURL: its default waitUntil:'load' never fires after a client-side (History
    // API) route change like this Link's — there's no real navigation event to wait for.
    await expect(this.page).toHaveURL(/\/compare$/);
  }

  async openShareDialog() {
    await this.page.getByRole("button", { name: "Share", exact: true }).click();
  }

  /** Assumes the share dialog is already open; returns the created link's URL. */
  async createShareLink(): Promise<string> {
    await this.page.getByRole("button", { name: "Create link" }).click();
    return this.page.getByLabel(/Copy it now/).inputValue();
  }

  async revokeShareLink() {
    await this.page.getByRole("button", { name: "Revoke link" }).click();
  }
}
