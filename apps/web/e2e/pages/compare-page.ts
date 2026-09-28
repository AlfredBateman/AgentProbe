import { expect, type Page } from "@playwright/test";

/** The compare page: pick a baseline run and read its verdict. */
export class ComparePage {
  constructor(private readonly page: Page) {}

  async pickBaseline(runId: string) {
    await this.page.getByLabel("Baseline").selectOption(runId);
  }

  async waitForVerdict(name: "Regression" | "No change" | "Improvement", timeout = 15_000) {
    await expect(this.page.getByText(name, { exact: true })).toBeVisible({ timeout });
  }

  /** Clicks a case id button (in a transition section or the case table) to open its diff trace. */
  async openCaseDiff(caseId: string) {
    await this.page.getByRole("button", { name: caseId }).first().click();
  }
}
