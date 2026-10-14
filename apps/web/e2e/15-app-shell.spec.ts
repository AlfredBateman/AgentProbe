import path from "node:path";
import { type APIRequestContext, expect, type Page, test } from "@playwright/test";
import { SHELL_1440_EMAIL, SHELL_390_EMAIL, SHELL_404_EMAIL, SHELL_COLD_EMAIL, SHELL_SHOTS_EMAIL } from "./fixtures";

// The rebuilt shell and the pages on it (login, register, projects, settings), through the real
// UI: register, sign in, create a project, create an API key, at a desktop and a phone width.
// Each run also fails on an uncaught page error, a CSP violation, or horizontal overflow.
const PASSWORD = "correct horse battery staple shell";
const SCREENSHOT_DIR = path.resolve(__dirname, "../../../docs/screenshots/app");

const VIEWPORTS = [
  { width: 1440, height: 900, email: SHELL_1440_EMAIL },
  { width: 390, height: 844, email: SHELL_390_EMAIL },
];

function watch(page: Page) {
  const problems: string[] = [];
  page.on("pageerror", (e) => problems.push(`page error: ${e}`));
  page.on("console", (m) => {
    if (m.type() === "error" && m.text().includes("Content Security Policy")) problems.push(`CSP: ${m.text()}`);
  });
  return problems;
}

async function noOverflow(page: Page, where: string) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  expect(overflow, `${where} scrolls horizontally`).toBe(false);
}

/** The shell's API chip. Its title tells it from the waking notice, which is also a status. */
const chip = (page: Page, text: string) => page.getByTitle(/^API status/).filter({ hasText: text }).first();

/** The rail on a desktop; the menu below 810px. */
async function openSection(page: Page, name: string, mobile: boolean) {
  if (mobile) {
    await page.getByRole("button", { name: "Open menu" }).click();
    await page.getByRole("navigation", { name: "Project menu" }).getByRole("link", { name, exact: true }).click();
  } else {
    await page.getByRole("navigation", { name: "Project sections" }).getByRole("link", { name, exact: true }).click();
  }
}

async function signOut(page: Page, mobile: boolean) {
  if (mobile) await page.getByRole("button", { name: "Open menu" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL("/login");
}

for (const { width, height, email } of VIEWPORTS) {
  test(`register, sign in, create a project and an API key at ${width}px`, async ({ page }) => {
    const problems = watch(page);
    const mobile = width < 810;
    await page.setViewportSize({ width, height });

    await test.step("register", async () => {
      await page.goto("/register");
      await expect(page.getByRole("heading", { level: 1 })).toContainText(/create\s+account/i);
      // A short password is refused where it is typed, with the message tied to the field.
      await page.getByLabel("Email").fill(email);
      await page.getByLabel("Password").fill("short");
      await page.getByRole("button", { name: "Create account" }).click();
      await expect(page.getByLabel("Password")).toHaveAttribute("aria-invalid", "true");
      await expect(page.locator("#password-error")).toBeVisible();
      await noOverflow(page, "register with an error");
      await page.getByLabel("Password").fill(PASSWORD);
      await page.getByRole("button", { name: "Create account" }).click();
      await expect(page).toHaveURL("/projects");
      await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
    });

    await test.step("the shell: skip link, status chip, version and keyboard rail", async () => {
      // A fresh load, so the first Tab starts from the top of the document and not from wherever
      // the last click or the removed submit button left the focus starting point.
      await page.goto("/projects");
      await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
      await page.keyboard.press("Tab");
      await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(page.locator("#main-content")).toBeFocused();
      if (!mobile) {
        // The chip reads the app's own requests: by now /auth/me and /projects have answered.
        await expect(chip(page, "Awake")).toBeVisible();
        await expect(page.getByText(/Rev\s+v\d/)).toBeVisible();
        const rail = page.getByRole("navigation", { name: "Project sections" });
        await expect(rail.getByRole("link", { name: "Projects", exact: true })).toHaveAttribute("aria-current", "page");
      }
    });

    await test.step("sign out", async () => {
      await signOut(page, mobile);
    });

    await test.step("a wrong password is an alert, not a silent reload", async () => {
      await page.getByLabel("Email").fill(email);
      await page.getByLabel("Password").fill("not the password at all");
      await page.getByRole("button", { name: "Sign in" }).click();
      // #form-error, not the "alert" role: Next's route announcer has that role too.
      await expect(page.locator("#form-error")).toBeVisible();
      await expect(page).toHaveURL("/login");
      await noOverflow(page, "login with an error");
    });

    await test.step("sign in", async () => {
      await page.getByLabel("Password").fill(PASSWORD);
      await page.getByRole("button", { name: "Sign in" }).click();
      await expect(page).toHaveURL("/projects");
      await expect(page.getByText("No projects yet")).toBeVisible();
      await noOverflow(page, "empty projects");
    });

    await test.step("create a project", async () => {
      await page.getByRole("button", { name: "New project" }).click();
      await page.getByRole("button", { name: "Create project" }).click();
      await expect(page.locator("#project-name-error")).toBeVisible(); // required, caught before the API
      await page.getByLabel("Name").fill(`shell-${width}`);
      await page.getByRole("button", { name: "Create project" }).click();
      await expect(page).toHaveURL(/\/projects\/[^/]+$/);
      await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
      // The shell kept its place: the same session, now with the project open in the switcher.
      await expect(page.getByRole("combobox", { name: "Project" })).toHaveValue(/.+/);
      if (!mobile) {
        // Arrow keys walk the rail: Projects, then the project's own overview link.
        const rail = page.getByRole("navigation", { name: "Project sections" });
        await rail.getByRole("link", { name: "Projects", exact: true }).focus();
        await page.keyboard.press("ArrowDown");
        await expect(rail.getByRole("link", { name: /^Project overview/ })).toBeFocused();
        await expect(rail.getByRole("link", { name: /^Project overview/ })).toHaveAttribute("aria-current", "page");
      }
    });

    await test.step("the project is listed", async () => {
      await openSection(page, "Projects", mobile);
      await expect(page).toHaveURL("/projects");
      await expect(page.getByRole("cell", { name: `shell-${width}` })).toBeVisible();
      await noOverflow(page, "projects list");
    });

    await test.step("create an API key; it is shown once", async () => {
      await page.getByRole("link", { name: `shell-${width}` }).click();
      await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
      await openSection(page, "Settings", mobile);
      await expect(page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
      await expect(page.getByText("No API keys yet")).toBeVisible();
      // The page wipe must leave nothing clipped once it has played.
      await expect(page.locator("#main-content > div")).not.toHaveAttribute("style", /clip-path/);

      await page.getByRole("button", { name: "Create key" }).click();
      const dialog = page.getByRole("dialog");
      await dialog.getByRole("button", { name: "Create key" }).click();
      await expect(dialog.locator("#key-label-error")).toBeVisible();
      await dialog.getByLabel("Label").fill("e2e-shell");
      await dialog.getByRole("button", { name: "Create key" }).click();
      const code = page.locator("pre code");
      await expect(code).toHaveText(/^ap_/);
      const key = (await code.textContent()) ?? "";
      await expect(page.getByText("Shown once")).toBeVisible();
      await noOverflow(page, "settings with the key shown");

      await page.getByRole("button", { name: "Done" }).click();
      await expect(page.locator("pre code")).toHaveCount(0);
      await expect(page.getByRole("cell", { name: "e2e-shell" })).toBeVisible();
      await expect(page.getByRole("cell", { name: "Active" })).toBeVisible();

      await page.reload();
      await expect(page.getByRole("cell", { name: "e2e-shell" })).toBeVisible();
      await expect(page.getByText(key)).toHaveCount(0); // not shown again, in any form
      await noOverflow(page, "settings");
    });

    expect(problems, problems.join("\n")).toEqual([]);
  });
}

async function post(request: APIRequestContext, baseURL: string, urlPath: string, data: object) {
  const response = await request.post(`/api${urlPath}`, { data, headers: { Origin: baseURL } });
  expect(response.ok(), `${urlPath}: ${await response.text()}`).toBe(true);
  return response.json();
}

test("a sleeping API: the notice and the chip show while it wakes, then the page loads", async ({ page, baseURL }) => {
  const problems = watch(page);
  await post(page.request, baseURL!, "/auth/register", { email: SHELL_COLD_EMAIL, password: PASSWORD });
  // The platform holds /api/health until the service is up. Hold it 4 s; the notice shows at 1.5 s.
  await page.route("**/api/health", async (route) => {
    await new Promise((r) => setTimeout(r, 4_000));
    await route.continue();
  });
  await page.goto("/projects");
  await expect(page.getByText("Waking the server")).toBeVisible();
  await expect(chip(page, "Waking")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Waking the server")).toHaveCount(0);
  await expect(chip(page, "Awake")).toBeVisible();
  expect(problems, problems.join("\n")).toEqual([]);
});

test("an unknown address is the 404 page, with a way out", async ({ page, baseURL }) => {
  const problems = watch(page);
  // Signed in: the proxy sends a visitor with no session to /login before any page can 404.
  await post(page.request, baseURL!, "/auth/register", { email: SHELL_404_EMAIL, password: PASSWORD });
  const response = await page.goto("/no/such/page");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
  await page.getByRole("link", { name: "Home" }).click();
  await expect(page).toHaveURL("/");
  expect(problems, problems.join("\n")).toEqual([]);
});

// Writes docs/screenshots/app/*: SCREENSHOTS=1 pnpm e2e. Off by default, so an ordinary run does
// not rewrite committed images with this machine's font rasterization.
test("screenshots at 1440, 810 and 390px", async ({ page, baseURL }) => {
  test.skip(!process.env.SCREENSHOTS, "set SCREENSHOTS=1 to write docs/screenshots/app");
  test.setTimeout(120_000);
  const sizes = [
    { width: 1440, height: 900 },
    { width: 810, height: 1000 },
    { width: 390, height: 844 },
  ];
  async function shoot(name: string) {
    for (const size of sizes) {
      await page.setViewportSize(size);
      await page.evaluate(() => document.fonts.ready);
      // No skeleton left (a page still loading is not what the screenshot is of), and the
      // reveals and the wipe have played.
      await expect(page.locator('[class*="skeleton-step"]')).toHaveCount(0);
      await page.waitForTimeout(700);
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${name}-${size.width}.png`), fullPage: true });
    }
    await page.setViewportSize(sizes[0]);
  }

  await page.goto("/login");
  await expect(page.getByLabel("Email")).toBeVisible();
  await shoot("login");
  await page.getByLabel("Email").fill("someone@example.com");
  await page.getByLabel("Password").fill("not the password at all");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.locator("#form-error")).toBeVisible();
  await shoot("login-error");

  await page.goto("/register");
  await expect(page.getByLabel("Email")).toBeVisible();
  await shoot("register");

  await post(page.request, baseURL!, "/auth/register", { email: SHELL_SHOTS_EMAIL, password: PASSWORD });
  await page.goto("/no/such/page");
  await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
  await shoot("not-found");

  await page.goto("/projects");
  await expect(page.getByText("No projects yet")).toBeVisible();
  await shoot("projects-empty");

  const names = ["support-bot", "rag-bot", "checkout-assistant"];
  const created = [];
  for (const [i, name] of names.entries()) {
    created.push(await post(page.request, baseURL!, "/projects", { name, description: i === 0 ? "Refunds and order status, v1 and v2 prompts." : null }));
  }
  await page.goto("/projects");
  await expect(page.getByRole("cell", { name: "rag-bot" })).toBeVisible();
  await shoot("projects");

  await page.goto(`/projects/${created[0].id}/settings`);
  await expect(page.getByText("No API keys yet")).toBeVisible();
  await page.getByRole("button", { name: "Create key" }).click();
  await page.getByRole("dialog").getByLabel("Label").fill("ci");
  await page.getByRole("dialog").getByRole("button", { name: "Create key" }).click();
  await expect(page.locator("pre code")).toHaveText(/^ap_/);
  await shoot("settings-key-shown");
  await page.getByRole("button", { name: "Done" }).click();
  await shoot("settings");

  await page.goto(`/projects/${created[0].id}`);
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await shoot("project-overview");

  await page.setViewportSize(sizes[2]);
  await page.getByRole("button", { name: "Open menu" }).click();
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "menu-open-390.png"), fullPage: false });
});
