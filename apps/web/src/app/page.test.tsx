import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";
import Home from "./page";

test("the landing page states the pitch, not the old red-team framing", () => {
  const html = renderToStaticMarkup(<Home />);
  expect(html).toContain("AgentProbe");
  expect(html).toContain("Statistically-corrected, flakiness-aware regression detection for LLM agents.");
  expect(html).not.toContain("red-team");
  expect(html).not.toContain("security scanner");
});

test("has one primary and one secondary CTA, and at most two gradient cards", () => {
  const html = renderToStaticMarkup(<Home />);
  expect(html.match(/href="\/register"/g)?.length).toBeGreaterThanOrEqual(1);
  expect(html.match(/href="\/login"/g)?.length).toBeGreaterThanOrEqual(1);
  expect(html.match(/background-image/g)?.length).toBeLessThanOrEqual(2);
});
