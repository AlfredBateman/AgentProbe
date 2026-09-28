import { expect, test } from "@playwright/test";
import { ProjectsPage } from "./pages/projects-page";
import { RegisterPage } from "./pages/register-page";
import { SuitesPage } from "./pages/suites-page";
import { INVALID_YAML_EMAIL } from "./fixtures";

const PASSWORD = "correct horse battery staple yaml";

test("an invalid suite YAML shows validation errors instead of a generic failure", async ({ page }) => {
  const register = new RegisterPage(page);
  await register.goto();
  await register.register(INVALID_YAML_EMAIL, PASSWORD);
  await expect(page).toHaveURL("/projects");

  const projects = new ProjectsPage(page);
  const projectId = await projects.createProject("e2e-invalid-yaml");

  const suites = new SuitesPage(page, projectId);
  await suites.goto();

  await test.step("a YAML syntax error names its line", async () => {
    await suites.openNew();
    await suites.pasteYaml("suite: bad\nagent: [this is not closed");
    await suites.create();
    const issues = await suites.validationIssues();
    expect(issues).toMatch(/line 2/i);
    await suites.cancel();
  });

  await test.step("a schema violation (missing required fields) is named too", async () => {
    await suites.openNew();
    await suites.pasteYaml("suite: bad\nagent: support-v1\ncases: []");
    await suites.create();
    const issues = await suites.validationIssues();
    expect(issues.length).toBeGreaterThan(0);
    await suites.cancel();
  });

  // Neither attempt created a suite.
  await expect(page.getByText("No suites yet")).toBeVisible();
});
