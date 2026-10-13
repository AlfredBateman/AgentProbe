import { render } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";
import Home from "./page";

test("the landing page states the pitch, not the old red-team framing", () => {
  const html = renderToStaticMarkup(<Home />);
  expect(html).toContain("AgentProbe");
  expect(html).toContain("Regression detection for LLM agents.");
  expect(html).toContain("Statistically corrected,");
  expect(html).not.toContain("red-team");
  expect(html).not.toContain("security scanner");
});

test("the hero leads the page with its only h1 and both CTAs; at most two gradient cards", () => {
  const { container } = render(<Home />);
  const main = container.querySelector("main")!;
  expect(main.firstElementChild!.querySelector("h1")).not.toBeNull();
  expect(container.querySelectorAll("h1")).toHaveLength(1);
  const texts = (href: string) => [...container.querySelectorAll(`a[href="${href}"]`)].map((a) => a.textContent);
  expect(texts("/register")).toEqual(["Get started"]);
  expect(texts("/login")).toEqual(["Sign in"]);
  // The sections under the hero are still there.
  expect([...container.querySelectorAll("h2")].map((h) => h.textContent)).toEqual([
    "How it works",
    "Run it from the CLI",
    "agentprobe / regression-check",
  ]);
  expect(container.innerHTML.match(/background-image/g)?.length).toBeLessThanOrEqual(2);
});
