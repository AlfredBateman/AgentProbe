import { expect, test } from "@playwright/test";
import { AgentsPage } from "./pages/agents-page";
import { ProjectsPage } from "./pages/projects-page";
import { RegisterPage } from "./pages/register-page";
import { SSRF_EMAIL } from "./fixtures";

const PASSWORD = "correct horse battery staple ssrf";

test("an agent URL the SSRF guard blocks shows a clear error on Test connection", async ({ page }) => {
  const register = new RegisterPage(page);
  await register.goto();
  await register.register(SSRF_EMAIL, PASSWORD);
  await expect(page).toHaveURL("/projects");

  const projects = new ProjectsPage(page);
  const projectId = await projects.createProject("e2e-ssrf");

  const agents = new AgentsPage(page, projectId);
  await agents.goto();
  await agents.openNew();
  await agents.fillName("blocked");
  // Cloud metadata: blocked regardless of allow_private (ADR 0012's SSRF guard).
  await agents.fillUrl("http://169.254.169.254/latest/meta-data/");
  const message = await agents.testConnection();
  expect(message).toContain("reserved or internal address");
  expect(message).not.toMatch(/169\.254\.169\.254 resolves to \d/); // never a resolved-address detail leak

  // A private address without the opt-in is blocked too, with its own distinct message.
  await agents.fillUrl("http://127.0.0.1:1/nope");
  await agents.allowPrivate(false);
  const privateMessage = await agents.testConnection();
  expect(privateMessage).toContain("127.0.0.1 resolves to a private address. Private targets need allow_private");
});
