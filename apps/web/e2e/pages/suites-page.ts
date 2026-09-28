import { expect, type Page } from "@playwright/test";

/** The Suites page: create a suite from YAML and start a run from it. */
export class SuitesPage {
  constructor(
    private readonly page: Page,
    private readonly projectId: string,
  ) {}

  async goto() {
    await this.page.goto(`/projects/${this.projectId}/suites`);
  }

  async openNew() {
    await this.page.getByTestId("new-suite").click();
  }

  async pasteYaml(yaml: string) {
    await this.page.getByTestId("suite-yaml").fill(yaml);
  }

  async create() {
    await this.page.getByRole("button", { name: "Create suite" }).click();
  }

  async cancel() {
    await this.page.getByRole("button", { name: "Cancel" }).click();
  }

  async validationIssues(): Promise<string> {
    const issues = this.page.getByTestId("suite-yaml-issues");
    await issues.waitFor();
    return (await issues.textContent()) ?? "";
  }

  /** Clicks Run for the named suite and returns the new run's id, parsed off the redirect. */
  async run(suiteName: string): Promise<string> {
    await this.page.getByTestId(`run-suite-${suiteName}`).click();
    // Not waitForURL: it lands via router.push, which fires no 'load' event.
    await expect(this.page).toHaveURL(/\/runs\/[^/]+$/);
    const match = /\/runs\/([^/]+)$/.exec(this.page.url());
    if (!match) throw new Error(`unexpected URL after starting a run: ${this.page.url()}`);
    return match[1];
  }
}
