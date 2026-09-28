import { expect, type Page } from "@playwright/test";

export class ProjectsPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/projects");
  }

  /** Creates a project and returns its id, parsed off the redirect URL. */
  async createProject(name: string): Promise<string> {
    await this.page.getByRole("button", { name: "New project" }).click();
    await this.page.getByLabel("Name").fill(name);
    await this.page.getByRole("button", { name: "Create project" }).click();
    // Not waitForURL: it lands via router.push (a client-side route change), which never fires
    // a 'load' event for waitForURL's default waitUntil to resolve on.
    await expect(this.page).toHaveURL(/\/projects\/[^/]+$/);
    const match = /\/projects\/([^/]+)$/.exec(this.page.url());
    if (!match) throw new Error(`unexpected URL after creating a project: ${this.page.url()}`);
    return match[1];
  }
}
