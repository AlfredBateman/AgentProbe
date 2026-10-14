import { expect, type Page, test } from "@playwright/test";

// The landing page's motion and its one 3D piece. three marks the window when its module runs
// (`__THREE__`), so its absence proves the fallback paths never loaded it.

/** Every console error, uncaught exception and CSP violation on the page. */
function watchErrors(page: Page) {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(String(e)));
  return errors;
}

/** The page's layout shifts so far, summed as CLS sums them (no input-driven ones). */
const layoutShift = (page: Page) =>
  page.evaluate(
    () =>
      new Promise<number>((resolve) => {
        let total = 0;
        new PerformanceObserver((list) => {
          for (const e of list.getEntries() as unknown as { value: number; hadRecentInput: boolean }[]) if (!e.hadRecentInput) total += e.value;
        }).observe({ type: "layout-shift", buffered: true });
        setTimeout(() => resolve(total), 100);
      }),
  );

const threeLoaded = (page: Page) => page.evaluate(() => "__THREE__" in window);

/** Scrolls to the bottom in steps, as a reader would, so scroll-driven code sees every position. */
async function scrollThrough(page: Page) {
  const height = await page.evaluate(() => document.documentElement.scrollHeight);
  for (let y = 0; y <= height; y += 200) {
    await page.mouse.wheel(0, 200);
    await page.waitForTimeout(30);
  }
}

test("desktop: the 3D grid renders, the proof card reads the regression at rest, nothing errors or shifts", async ({ page }) => {
  const errors = watchErrors(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/Regressions\s*not\s*noise/i);
  const canvas = page.getByTestId("hero-3d").locator("canvas");
  await expect(canvas).toBeVisible();
  expect(await threeLoaded(page)).toBe(true);
  // The canvas covers the box exactly, at no more than 2 device pixels per CSS pixel.
  const box = await page.getByTestId("hero-3d").boundingBox();
  const size = await canvas.evaluate((c: HTMLCanvasElement) => ({ w: c.width, h: c.height, cw: c.clientWidth }));
  expect(size.cw).toBeCloseTo(box!.width, 0);
  expect(size.w / size.cw).toBeLessThanOrEqual(2);
  await expect(page.getByTestId("hero-3d").locator("..").getByText("Illustrative", { exact: true })).toBeVisible();

  // The card is the same at every scroll position: the candidate's figures beside a Regression
  // verdict, never the baseline's in their place.
  const passRate = page.getByRole("article", { name: "Demo regression" }).locator("dl").nth(1).locator("dd").first();
  await expect(passRate).toHaveText("86.7%");
  await expect(page.getByText(/^10\/10 -> 0\/10 passed$/)).toBeAttached();
  await scrollThrough(page);
  await expect(passRate).toHaveText("86.7%");
  await expect(page.getByText(/^10\/10 -> 0\/10 passed$/)).toBeVisible();

  expect(await layoutShift(page)).toBeLessThan(0.1);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);
  expect(errors, errors.join("\n")).toEqual([]);
});

test.describe("reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("the static figure stays, three never loads, and every figure is final at once", async ({ page }) => {
    const errors = watchErrors(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    const figure = page.getByTestId("hero-3d").locator("..");
    await expect(figure.locator("svg")).toBeVisible();
    await expect(figure.getByText("Illustrative", { exact: true })).toBeVisible();
    await expect(page.getByTestId("hero-3d").locator("canvas")).toHaveCount(0);
    await expect(page.getByText(/^10\/10 -> 0\/10 passed$/)).toBeAttached();
    await expect(page.locator("[data-motion]")).toHaveCount(0);
    await page.waitForLoadState("load");
    expect(await threeLoaded(page)).toBe(false);
    expect(errors, errors.join("\n")).toEqual([]);
  });
});

test("a 390px phone gets the static figure and no three", async ({ page }) => {
  const errors = watchErrors(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByTestId("hero-3d").locator("..").locator("svg")).toBeVisible();
  await page.waitForLoadState("load");
  await expect(page.getByTestId("hero-3d").locator("canvas")).toHaveCount(0);
  expect(await threeLoaded(page)).toBe(false);
  expect(errors, errors.join("\n")).toEqual([]);
});

for (const [width, height] of [
  [1440, 900],
  [810, 1000],
  [390, 844],
] as const) {
  test(`the install block wraps at ${width}px and copies the whole command`, async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.setViewportSize({ width, height });
    await page.goto("/");
    const block = page.locator("#install figure");
    await block.scrollIntoViewIfNeeded();
    const pre = block.locator("pre");
    // Nothing is cut off: the text wraps inside the block, so it has no sideways overflow.
    const fits = await pre.evaluate((el) => el.scrollWidth <= el.clientWidth + 1);
    expect(fits, "the install command overflows its block").toBe(true);
    const shown = (await pre.locator("code").textContent()) ?? "";
    await block.getByRole("button", { name: "Copy" }).click();
    // A Windows clipboard hands lines back CRLF; the text is otherwise the whole block, unbroken.
    const copied = (await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, "\n");
    expect(copied).toBe(shown);
    expect(shown).toContain("pip install");
    expect(shown.split(String.fromCharCode(10))[0].length).toBeGreaterThan(100); // the long line this test is about
  });
}

test("the footer shows the license package.json names", async ({ page }) => {
  await page.goto("/");
  const footer = page.getByRole("contentinfo");
  await expect(footer.getByText("MIT", { exact: true })).toBeVisible();
  await expect(footer).not.toContainText("NOT SET");
});
