import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import facts from "@/components/landing/facts.json";
import { demoUrl, INSTALL, TAG } from "@/components/landing/site";
import { buttonClasses } from "@/components/ui/button";
import { resetWake } from "@/lib/api/wake";
import Home from "./page";

// Vitest runs in apps/web.
const { version } = JSON.parse(readFileSync(join(process.cwd(), "package.json"), "utf8"));
const readme = readFileSync(join(process.cwd(), "../../README.md"), "utf8");

beforeEach(() => {
  resetWake();
  vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 200 })));
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

test("one h1 in three lines, a real h2 for every section, and the tagline", () => {
  render(<Home />);
  const h1 = screen.getByRole("heading", { level: 1 });
  expect([...h1.children].map((line) => line.textContent)).toEqual(["Regressions", "not", "noise"]);
  expect(h1.querySelectorAll(".text-outline")).toHaveLength(1);
  expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
    "Repeat every case",
    "Judge traces and tool calls",
    "Gate the pull request",
    "Proof",
    "Install",
  ]);
  expect(screen.getByText("Regression detection for LLM agents. Statistically corrected. Flakiness-aware.")).toBeTruthy();
  // The hero figure is not live data: the box itself and its caption both say so.
  expect(screen.getByText("Illustrative").closest("[aria-hidden]")?.querySelector("svg")).not.toBeNull();
  expect(screen.getByText(/^Fig\. 01 .* Illustrative$/)).toBeTruthy();
});

test("every link goes somewhere, and lime fills only the register action", () => {
  const { container } = render(<Home />);
  for (const a of container.querySelectorAll("a")) expect(a.getAttribute("href"), a.textContent ?? "").toMatch(/^(\/|#\w|https:\/\/)/);
  const register = [...container.querySelectorAll('a[href="/register"]')];
  expect(register.filter((a) => a.className.startsWith(buttonClasses("primary")))).toHaveLength(2); // top bar and hero
  for (const el of container.querySelectorAll(".bg-accent")) expect(el.getAttribute("href")).toBe("/register");
  expect(container.querySelector('a[href="/login"]')).not.toBeNull();
  expect(container.innerHTML).not.toContain("background-image");
});

test("the version is the package version and the install lines are the README's", () => {
  const { container } = render(<Home />);
  expect(TAG).toBe(`v${version}`);
  expect(container.textContent).toContain(`REV ${TAG}`);
  const lines = INSTALL.split("\n");
  expect(lines).toHaveLength(3);
  expect(container.querySelector("pre")?.textContent).toBe(INSTALL);
  // The pip requirements and the Action line, as the README publishes them at this tag.
  for (const requirement of lines[0].match(/"[^"]+"/g)!) expect(readme).toContain(requirement);
  expect(readme).toContain(lines[2]);
  expect(readme).toContain(lines[1].split(" ").slice(0, 2).join(" "));
});

test("every figure on the page is one facts.json holds", () => {
  const { container } = render(<Home />);
  const { detection, regression, falseAlarms, runsPerCase } = facts;
  const text = container.textContent ?? "";
  for (const figure of [
    `${detection.detected} / ${detection.planted}`,
    detection.measured,
    regression.caseId,
    regression.p,
    regression.threshold,
    regression.passRateBefore,
    regression.passRateAfter,
    `${regression.baselinePasses} -> ${regression.candidatePasses}`,
    falseAlarms.shipped,
    falseAlarms.naive,
    falseAlarms.interval,
    falseAlarms.scenario,
  ]) {
    expect(text).toContain(figure);
  }
  // Nothing else on the page is a number: every numeric token is one a fact, the version or
  // the year holds, or a mark that is drawing (card indexes, FIG and UNIT, "95% CI").
  const tokens = (s: string) => s.match(/\d+(?:\.\d+)?(?:e-\d+)?%?/g) ?? [];
  const known = [...Object.values(detection), ...Object.values(regression), ...Object.values(falseAlarms), runsPerCase, TAG, INSTALL, String(new Date().getFullYear())];
  const allowed = new Set([...known.flatMap(tokens), "01", "02", "03", "95%"]);
  // Text nodes apart, so "9 / 9" beside "4 demo agents" is not read as 94.
  const spaced = [...container.querySelectorAll("*")].flatMap((el) => [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent)).join(" ");
  expect(tokens(spaced).filter((token) => !allowed.has(token))).toEqual([]);
});

// An element's own words: its text plus any descendants that do not set their own type tier.
function ownText(node: Node): string {
  return [...node.childNodes]
    .map((child) => (child.nodeType === 3 ? child.textContent : child instanceof Element && !/\btype-/.test(child.className) ? ownText(child) : ""))
    .join(" ");
}

test("mono uppercase is for labels: no label, micro or data text runs past 8 words", () => {
  vi.stubEnv("NEXT_PUBLIC_DEMO_URL", "/shared/sample");
  const { container } = render(<Home />);
  for (const el of container.querySelectorAll(".type-label, .type-micro, .type-data, .type-button")) {
    if (el.matches("nav, dl")) continue; // a list of labels, not one label
    const words = ownText(el).match(/(?<![\p{L}\p{N}])\p{L}{2,}(?![\p{L}\p{N}])/gu) ?? [];
    expect(words.length, ownText(el)).toBeLessThanOrEqual(8);
  }
});

test("the demo link shows only for a usable NEXT_PUBLIC_DEMO_URL", () => {
  expect(demoUrl("/shared/abc")).toBe("/shared/abc");
  expect(demoUrl(" https://example.com/shared/abc ")).toBe("https://example.com/shared/abc");
  for (const bad of [undefined, "", "javascript:alert(1)", "//evil.example", "http://example.com"]) expect(demoUrl(bad)).toBeUndefined();

  const none = render(<Home />);
  expect(none.container.textContent).not.toContain("Try the demo");
  none.unmount();

  vi.stubEnv("NEXT_PUBLIC_DEMO_URL", "/shared/sample");
  render(<Home />);
  const demo = screen.getByRole("link", { name: "Try the demo" });
  expect(demo.getAttribute("href")).toBe("/shared/sample");
  expect(demo.className).toBe(buttonClasses("secondary"));
  expect(screen.getByText(/Demo servers take about 30 s to wake/)).toBeTruthy();
});
