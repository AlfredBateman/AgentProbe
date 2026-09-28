import { expect, type Page } from "@playwright/test";

/** The public /shared/[token] page, as a logged-out visitor sees it. */
export class SharedPage {
  constructor(private readonly page: Page) {}

  async goto(url: string) {
    await this.page.goto(url);
  }

  async expectReadOnlyView(suiteName: string) {
    await expect(this.page.getByText("Shared run · read-only")).toBeVisible();
    await expect(this.page.getByRole("heading", { name: suiteName })).toBeVisible();
  }

  async expectRevokedOrMissing() {
    await expect(this.page.getByText("This link doesn't work")).toBeVisible();
  }
}
