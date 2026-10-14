import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import facts from "./facts.json";
import { Proof } from "./proof";

const { regression } = facts;
const pair = /^(\S+) -> (\S+)( passed)?$/;

/** `10/10` and `98.9%` as numbers, so they can be compared whatever their format. */
const figure = (text: string) => {
  const [a, b] = text.split("/");
  return b === undefined ? Number.parseFloat(a) : Number(a) / Number(b);
};

test("the facts describe a regression: the candidate is worse than the baseline", () => {
  expect(regression.label).toBe("stable-fail");
  expect(regression.baselinePasses).not.toBe(regression.candidatePasses);
  expect(figure(regression.candidatePasses)).toBeLessThan(figure(regression.baselinePasses));
  expect(figure(regression.passRateAfter)).toBeLessThan(figure(regression.passRateBefore));
  // A stable fail passed none of its attempts.
  expect(regression.candidatePasses).toMatch(/^0\//);
});

/** Makes `(prefers-reduced-motion: no-preference)` match, as it does for most visitors. */
function allowMotion() {
  window.matchMedia = ((query: string) => ({
    matches: query.includes("no-preference"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
  })) as unknown as typeof window.matchMedia;
}

const defaultMatchMedia = window.matchMedia;
afterEach(() => {
  window.matchMedia = defaultMatchMedia;
});

// With motion on, anything that animates a figure from its baseline starts at the baseline's
// text. The card is read at that first paint, before any scroll, which is where an equal
// before/after once showed (a scrubbed value resting on its baseline).
describe.each([
  ["motion off", () => {}],
  ["motion on, before any scroll", allowMotion],
])("%s", (_, setup) => {
  test("a Regression verdict never sits beside equal before and after values", () => {
    setup();
    renderCard();
  });
});

function renderCard() {
  render(<Proof />);
  const card = screen.getByRole("article", { name: "Demo regression" });
  expect(within(card).getByText("Regression")).toBeTruthy();

  // Every element whose whole text is "before -> after", the verdict header included.
  const pairs = [...card.querySelectorAll("*")]
    .map((el) => pair.exec(el.textContent ?? ""))
    .filter((m) => m !== null)
    .map((m) => [m[1], m[2]]);
  expect(pairs.length).toBeGreaterThanOrEqual(2);
  for (const [before, after] of pairs) expect(before, `${before} -> ${after}`).not.toBe(after);

  // The case line says what the case did...
  expect(within(card).getByText(`${regression.baselinePasses} -> ${regression.candidatePasses} passed`)).toBeTruthy();
  // ...and the pass-rate tile is the candidate's rate, next to the baseline's.
  const tile = within(card).getByText("Pass rate").closest("dl")!;
  const value = tile.querySelector("dd span")!.textContent;
  expect(value).toBe(regression.passRateAfter);
  expect(tile.textContent).toContain(`Was ${regression.passRateBefore}`);
  expect(value).not.toBe(regression.passRateBefore);
}
