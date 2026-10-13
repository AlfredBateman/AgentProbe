import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import ComponentsPage from "./page.dev";

test("the catalogue shows every status, and the hostile output is text, not markup", () => {
  const { container } = render(<ComponentsPage />);
  for (const status of ["Pass", "Fail", "Flaky", "Error", "Stable", "Running", "Queued", "Quarantined"]) {
    expect(screen.getAllByText(status).length, status).toBeGreaterThan(0);
  }
  expect(container.querySelector("img, script")).toBeNull();
  expect(container.textContent).toContain('<img src=x onerror="alert(1)">');
});

test("a lime fill is only ever a button, a link styled as one, or the one hero panel", () => {
  const { container } = render(<ComponentsPage />);
  for (const el of container.querySelectorAll(".bg-accent")) expect(["BUTTON", "A"]).toContain(el.tagName);
});

test("every control in the catalogue has an accessible name", () => {
  render(<ComponentsPage />);
  for (const role of ["button", "textbox", "combobox", "checkbox", "switch", "tab"] as const) {
    for (const el of screen.getAllByRole(role, { hidden: true })) {
      expect(el.getAttribute("aria-label") || el.textContent || (el as HTMLInputElement).labels?.length || el.getAttribute("aria-labelledby"), `${role} ${el.outerHTML.slice(0, 80)}`).toBeTruthy();
    }
  }
});
