import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { expect, test } from "vitest";
import { Tabs } from "./tabs";

const items = [
  { value: "all", label: "All" },
  { value: "failed", label: "Failed" },
  { value: "flaky", label: "Flaky" },
];

function Harness() {
  const [value, setValue] = useState("all");
  return <Tabs aria-label="Filter" items={items} value={value} onValueChange={setValue} />;
}

const selected = () => screen.getAllByRole("tab").filter((t) => t.getAttribute("aria-selected") === "true");

test("click selects a tab; selected is a surface lift", () => {
  render(<Harness />);
  fireEvent.click(screen.getByRole("tab", { name: "Failed" }));
  expect(selected().map((t) => t.textContent)).toEqual(["Failed"]);
  expect(screen.getByRole("tab", { name: "Failed" }).className).toContain("bg-surface-2");
  expect(screen.getByRole("tab", { name: "All" }).className).toContain("text-ink-muted");
});

test("arrow keys, Home and End move selection and focus, wrapping around", () => {
  render(<Harness />);
  const all = screen.getByRole("tab", { name: "All" });
  fireEvent.keyDown(all, { key: "ArrowLeft" });
  expect(selected()[0].textContent).toBe("Flaky");
  expect(document.activeElement).toBe(screen.getByRole("tab", { name: "Flaky" }));
  fireEvent.keyDown(document.activeElement!, { key: "ArrowRight" });
  expect(selected()[0].textContent).toBe("All");
  fireEvent.keyDown(document.activeElement!, { key: "End" });
  expect(selected()[0].textContent).toBe("Flaky");
  fireEvent.keyDown(document.activeElement!, { key: "Home" });
  expect(selected()[0].textContent).toBe("All");
});

test("only the selected tab is in the tab order", () => {
  render(<Harness />);
  expect(screen.getAllByRole("tab").map((t) => t.tabIndex)).toEqual([0, -1, -1]);
});
