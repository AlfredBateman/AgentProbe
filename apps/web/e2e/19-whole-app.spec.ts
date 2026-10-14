import AxeBuilder from "@axe-core/playwright";
import { type APIRequestContext, type Browser, expect, type Page, test } from "@playwright/test";
import { A11Y_EMAIL, DEMO_AGENTS_URL } from "./fixtures";

// Every route at 1440, 810 and 390px on real data: no horizontal overflow, no clipped header or
// heading, no serious or critical axe finding, and (on a touch screen at 390px) no tap target
// under 44px. Then keyboard-only use of the shell, a dialog, a sortable table and the trace
// viewer, with the focus ring checked on everything focused along the way.
test.describe.configure({ timeout: 300_000, mode: "serial" });

const PASSWORD = "correct horse battery staple a11y";
const WIDTHS = [
  { width: 1440, height: 900, touch: false },
  { width: 810, height: 1000, touch: false },
  { width: 390, height: 844, touch: true },
];
const LIME = "rgb(202, 255, 0)";

const SUITE_YAML = `suite: a11y-check
agent: support-v1
runs_per_case: 5
cases:
  - id: greeting
    input: "Hello there"
    expect:
      - judge: contains
        value: "How can I help?"
  - id: order-status
    input: "What's the status of order 1042?"
    expect:
      - judge: contains
        value: "shipped"
  - id: refund-outside-window
    input: "Can I get a refund after 45 days?"
    expect:
      - judge: contains_any
        values: ["30 days", "not eligible"]
      - judge: tool_not_called
        tool: issue_refund
`;

const ids = { project: "", suite: "", v1: "", v2: "", result: "", token: "" };

async function post(request: APIRequestContext, baseURL: string, urlPath: string, data: object) {
  const response = await request.post(`/api${urlPath}`, { data, headers: { Origin: baseURL } });
  expect(response.ok(), `${urlPath}: ${await response.text()}`).toBe(true);
  return response.json();
}

async function waitForRun(request: APIRequestContext, runId: string) {
  await expect
    .poll(async () => (await (await request.get(`/api/runs/${runId}`)).json()).status, { timeout: 120_000, intervals: [1_000] })
    .toBe("completed");
}

type Route = { name: string; path: () => string; ready: (page: Page) => Promise<void>; signedIn: boolean };

const h1 = (name: string | RegExp) => async (page: Page) => {
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
};

const ROUTES: Route[] = [
  { name: "landing", path: () => "/", ready: async (p) => expect(p.locator("h1").first()).toBeVisible(), signedIn: false },
  { name: "login", path: () => "/login", ready: async (p) => expect(p.getByRole("button", { name: "Sign in" })).toBeVisible(), signedIn: false },
  { name: "register", path: () => "/register", ready: async (p) => expect(p.getByRole("button", { name: "Create account" })).toBeVisible(), signedIn: false },
  { name: "shared", path: () => `/shared/${ids.token}`, ready: async (p) => expect(p.getByText("Read-only snapshot")).toBeVisible(), signedIn: false },
  { name: "projects", path: () => "/projects", ready: h1("Projects"), signedIn: true },
  { name: "overview", path: () => `/projects/${ids.project}`, ready: h1("Overview"), signedIn: true },
  { name: "agents", path: () => `/projects/${ids.project}/agents`, ready: h1("Agents"), signedIn: true },
  { name: "suites", path: () => `/projects/${ids.project}/suites`, ready: h1("Suites"), signedIn: true },
  { name: "suite", path: () => `/projects/${ids.project}/suites/${ids.suite}`, ready: h1("a11y-check"), signedIn: true },
  { name: "runs", path: () => `/projects/${ids.project}/runs`, ready: h1("Runs"), signedIn: true },
  {
    name: "run",
    path: () => `/projects/${ids.project}/runs/${ids.v2}`,
    ready: async (p) => expect(p.getByRole("region", { name: "Per-case tests" }).or(p.getByLabel("Per-case tests")).first()).toBeVisible(),
    signedIn: true,
  },
  { name: "compare", path: () => `/projects/${ids.project}/runs/${ids.v2}/compare`, ready: async (p) => expect(p.getByRole("heading", { name: "Verdict" })).toBeVisible(), signedIn: true },
  { name: "findings", path: () => `/projects/${ids.project}/runs/${ids.v2}/findings`, ready: async (p) => expect(p.getByRole("article").first()).toBeVisible(), signedIn: true },
  { name: "trace", path: () => `/projects/${ids.project}/runs/${ids.v2}/results/${ids.result}`, ready: async (p) => expect(p.getByText("Judge verdicts").first()).toBeVisible(), signedIn: true },
  { name: "settings", path: () => `/projects/${ids.project}/settings`, ready: h1("Settings"), signedIn: true },
  { name: "not-found", path: () => "/projects/00000000-0000-0000-0000-000000000000/nope", ready: async (p) => expect(p.locator("h1").first()).toBeVisible(), signedIn: true },
];

async function signedInContext(browser: Browser, baseURL: string, size: (typeof WIDTHS)[number]) {
  const context = await browser.newContext({ baseURL, viewport: { width: size.width, height: size.height }, hasTouch: size.touch });
  const page = await context.newPage();
  await post(page.request, baseURL, "/auth/login", { email: A11Y_EMAIL, password: PASSWORD });
  return { context, page };
}

/** Everything the page shows that a person could need and can't see: text pushed past the
 * viewport, and headers, headings and controls whose own box cuts their text off. A truncated
 * id with its full text in `title` is deliberate and is skipped. */
async function layoutProblems(page: Page) {
  return page.evaluate(() => {
    const problems: string[] = [];
    if (document.documentElement.scrollWidth > window.innerWidth + 1) problems.push(`page scrolls sideways (${document.documentElement.scrollWidth}px)`);
    const describe = (el: Element) => `${el.tagName.toLowerCase()} "${(el.textContent ?? "").trim().slice(0, 40)}"`;
    for (const el of document.querySelectorAll("th, h1, h2, h3, label, button, a, summary, [role=tab]")) {
      const box = el.getBoundingClientRect();
      if (!box.width || !box.height || el.closest("[aria-hidden=true], .sr-only, details:not([open]) > :not(summary)")) continue;
      if (el.hasAttribute("title")) continue;
      const style = getComputedStyle(el);
      const clips = style.overflowX !== "visible" || style.textOverflow === "ellipsis";
      if (clips && el.scrollWidth > el.clientWidth + 1) problems.push(`clipped: ${describe(el)}`);
    }
    return problems;
  });
}

/** Tap targets under 44px on a touch screen. An inline link inside a sentence is exempt (WCAG
 * 2.5.8's inline exception), as is a control inside a closed <details>. */
async function smallTargets(page: Page) {
  return page.evaluate(() => {
    const small: string[] = [];
    const targets = document.querySelectorAll("a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [tabindex='0']");
    for (const el of targets) {
      const box = el.getBoundingClientRect();
      if (!box.width || !box.height || el.closest("[aria-hidden=true], details:not([open]) > :not(summary)") || (el as HTMLButtonElement).disabled) continue;
      const style = getComputedStyle(el);
      if (style.visibility === "hidden" || style.pointerEvents === "none") continue;
      // Visually hidden until focused (the skip link): not a tap target.
      if (box.width <= 1 && box.height <= 1) continue;
      // A stretched link's ::after covers its panel, and that is what a finger hits.
      const after = getComputedStyle(el, "::after");
      const stretched = after.position === "absolute" && after.content !== "none" && el.parentElement?.closest("[class*=relative]");
      // A checkbox or radio is tapped through its label.
      const label = (el as HTMLInputElement).labels?.[0];
      const hit = stretched
        ? stretched.getBoundingClientRect()
        : /^(checkbox|radio)$/.test((el as HTMLInputElement).type ?? "") && label
          ? label.getBoundingClientRect()
          : box;
      if (el.tagName === "A" && el.parentElement) {
        const own = (el.textContent ?? "").trim();
        const around = (el.parentElement.textContent ?? "").trim();
        if (getComputedStyle(el).display === "inline" && around.length > own.length + 20) continue;
      }
      // A scroll region is a focus stop for the keyboard, not a tap target.
      if (el.getAttribute("role") === "region") continue;
      if (hit.width < 43.5 || hit.height < 43.5) {
        small.push(`${el.tagName.toLowerCase()} "${((el as HTMLElement).innerText || el.getAttribute("aria-label") || "").trim().slice(0, 30)}" ${Math.round(hit.width)}x${Math.round(hit.height)}`);
      }
    }
    return small;
  });
}

async function axeProblems(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.impact} ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 4).join(" | ")}`);
}

test.beforeAll(async ({ browser, baseURL }) => {
  const page = await browser.newPage({ baseURL });
  await post(page.request, baseURL!, "/auth/register", { email: A11Y_EMAIL, password: PASSWORD });
  ids.project = (await post(page.request, baseURL!, "/projects", { name: "e2e-whole-app" })).id;
  const response = { output: "$.output", tool_calls: "$.tool_calls", total_tokens: "$.usage.total_tokens" };
  const agent = await post(page.request, baseURL!, `/projects/${ids.project}/agents`, {
    name: "support-v1",
    config: { adapter_type: "http", url: `${DEMO_AGENTS_URL}/support/v1/chat`, allow_private: true, response },
  });
  ids.suite = (await post(page.request, baseURL!, `/projects/${ids.project}/suites`, { yaml: SUITE_YAML })).id;
  ids.v1 = (await post(page.request, baseURL!, `/suites/${ids.suite}/runs`, {})).id;
  await waitForRun(page.request, ids.v1);
  await post(page.request, baseURL!, `/projects/${ids.project}/baseline`, { branch: "main", run_id: ids.v1 });
  const put = await page.request.put(`/api/agents/${agent.id}`, {
    data: { config: { ...agent.config, adapter_type: "http", url: `${DEMO_AGENTS_URL}/support/v2/chat` } },
    headers: { Origin: baseURL! },
  });
  expect(put.ok(), await put.text()).toBe(true);
  ids.v2 = (await post(page.request, baseURL!, `/suites/${ids.suite}/runs`, {})).id;
  await waitForRun(page.request, ids.v2);
  const failed = await (await page.request.get(`/api/runs/${ids.v2}/results?status=failed`)).json();
  ids.result = failed[0].id;
  ids.token = (await post(page.request, baseURL!, `/runs/${ids.v2}/share`, {})).token;
  await page.close();
});

test("every route at 1440, 810 and 390px: no overflow, nothing clipped, no serious axe finding, 44px targets on touch", async ({ browser, baseURL }) => {
  for (const size of WIDTHS) {
    const signedIn = await signedInContext(browser, baseURL!, size);
    const anon = await browser.newContext({ baseURL, viewport: { width: size.width, height: size.height }, hasTouch: size.touch });
    const anonPage = await anon.newPage();
    const found: string[] = [];
    for (const route of ROUTES) {
      const page = route.signedIn ? signedIn.page : anonPage;
      await page.goto(route.path());
      await route.ready(page);
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(500); // reveals and draw-ins have finished
      if (size.touch) expect(await page.evaluate(() => matchMedia("(pointer: coarse)").matches), "a touch context has a coarse pointer").toBe(true);
      for (const p of await layoutProblems(page)) found.push(`${route.name}: ${p}`);
      for (const p of await axeProblems(page)) found.push(`${route.name}: axe ${p}`);
      if (size.touch) for (const p of await smallTargets(page)) found.push(`${route.name}: target ${p}`);
    }
    await signedIn.context.close();
    await anon.close();
    // Soft, so one run reports every width.
    expect.soft(found, [`at ${size.width}px:`, ...found].join("\n")).toEqual([]);
  }
});

/** Tabs `count` times and returns what got focus, failing on any focused element without the
 * 2px lime ring. */
async function tabThrough(page: Page, count: number) {
  const seen: string[] = [];
  for (let i = 0; i < count; i++) {
    await page.keyboard.press("Tab");
    const focus = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || el === document.body) return null;
      const s = getComputedStyle(el);
      return { name: (el.innerText || el.getAttribute("aria-label") || el.tagName).trim().slice(0, 40), width: s.outlineWidth, style: s.outlineStyle, color: s.outlineColor };
    });
    if (!focus) continue;
    expect(focus.style, `focus ring on "${focus.name}"`).toBe("solid");
    expect(focus.width, `focus ring on "${focus.name}"`).toBe("2px");
    expect(focus.color, `focus ring on "${focus.name}"`).toBe(LIME);
    seen.push(focus.name);
  }
  return seen;
}

test("keyboard: the shell's skip link comes first and moves focus to the content; every stop has the lime ring", async ({ browser, baseURL }) => {
  const { context, page } = await signedInContext(browser, baseURL!, WIDTHS[0]);
  await page.goto(`/projects/${ids.project}`);
  await h1("Overview")(page);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: /skip to/i })).toBeFocused();
  await page.keyboard.press("Enter");
  expect(await page.evaluate(() => document.activeElement?.closest("main") !== null || document.activeElement?.tagName === "MAIN")).toBe(true);
  const seen = await tabThrough(page, 20);
  expect(seen.length).toBeGreaterThan(5);
  await context.close();
});

test("keyboard: a dialog takes focus, keeps it, closes on Escape and hands it back", async ({ browser, baseURL }) => {
  const { context, page } = await signedInContext(browser, baseURL!, WIDTHS[0]);
  await page.goto(`/projects/${ids.project}`);
  const trigger = page.getByTestId("run-a-suite");
  await expect(trigger).toBeEnabled(); // disabled, with its reason, until the project loads
  await trigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Run a suite" });
  await expect(dialog).toBeVisible();
  // A native modal makes the page behind it inert: Tab past the last control goes to the
  // browser's own UI (document.body here) and then back in, never to the page underneath.
  let inside = 0;
  for (let i = 0; i < 15; i++) {
    await page.keyboard.press("Tab");
    const where = await dialog.evaluate((d) => (d.contains(document.activeElement) ? "dialog" : document.activeElement === document.body ? "browser" : "page"));
    expect(where, "focus never reaches the page behind the dialog").not.toBe("page");
    if (where === "dialog") inside++;
  }
  expect(inside).toBeGreaterThan(10);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
  await context.close();
});

test("keyboard: a sortable table header sorts with Enter and says so", async ({ browser, baseURL }) => {
  const { context, page } = await signedInContext(browser, baseURL!, WIDTHS[0]);
  await page.goto(`/projects/${ids.project}/runs`);
  const table = page.getByRole("table", { name: "Runs" });
  await expect(table.locator("tbody tr")).toHaveCount(2);
  const header = table.getByRole("columnheader", { name: /Pass rate/ });
  await header.getByRole("button").focus();
  await page.keyboard.press("Enter");
  await expect(header).toHaveAttribute("aria-sort", /ascending|descending/);
  await context.close();
});

test("keyboard: the trace viewer's controls, steps and verdict links are reachable, each with the ring", async ({ browser, baseURL }) => {
  const { context, page } = await signedInContext(browser, baseURL!, WIDTHS[0]);
  await page.goto(`/projects/${ids.project}/runs/${ids.v2}/results/${ids.result}`);
  await expect(page.getByText("Judge verdicts").first()).toBeVisible();
  await page.locator("main").focus();
  const seen = await tabThrough(page, 30);
  expect(seen.some((s) => /copy/i.test(s)), `a copy button among ${seen.join(", ")}`).toBe(true);
  expect(seen.some((s) => /compact|expanded/i.test(s)), `the view toggle among ${seen.join(", ")}`).toBe(true);
  await context.close();
});
