import { render } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";
import { buttonClasses } from "@/components/ui/button";
import Home from "./page";

test("the landing page states the pitch, not the old red-team framing", () => {
  const html = renderToStaticMarkup(<Home />);
  expect(html).toContain("AgentProbe");
  expect(html).toContain("Statistically-corrected, flakiness-aware regression detection for LLM agents.");
  expect(html).not.toContain("red-team");
  expect(html).not.toContain("security scanner");
});

test("register is always the primary CTA and sign-in the secondary; at most two gradient cards", () => {
  const { container } = render(<Home />);
  const ctas = (href: string) => [...container.querySelectorAll(`a[href="${href}"]`)].map((a) => a.className);
  expect(ctas("/register").length).toBeGreaterThan(0);
  expect(ctas("/login").length).toBeGreaterThan(0);
  expect(ctas("/register").every((c) => c === buttonClasses("primary"))).toBe(true);
  expect(ctas("/login").every((c) => c === buttonClasses("secondary"))).toBe(true);
  expect(container.innerHTML.match(/background-image/g)?.length).toBeLessThanOrEqual(2);
});
