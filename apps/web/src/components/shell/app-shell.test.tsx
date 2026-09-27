import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { AppShell } from "./app-shell";

const projects = [
  { id: "p1", name: "support-bot" },
  { id: "p2", name: "rag-bot" },
];

function renderShell(pathname = "/projects/p1/runs/r9") {
  const onProjectChange = vi.fn();
  const onSignOut = vi.fn();
  render(
    <AppShell
      projects={projects}
      projectId="p1"
      email="dev@example.com"
      pathname={pathname}
      onProjectChange={onProjectChange}
      onSignOut={onSignOut}
    >
      <p>page</p>
    </AppShell>,
  );
  return { onProjectChange, onSignOut };
}

test("links point into the current project and mark the active section", () => {
  renderShell();
  const nav = screen.getByRole("navigation", { name: "Project sections" });
  const links = within(nav).getAllByRole("link");
  expect(links.map((l) => l.getAttribute("href"))).toEqual([
    "/projects/p1",
    "/projects/p1/agents",
    "/projects/p1/suites",
    "/projects/p1/runs",
    "/projects/p1/settings",
  ]);
  // A nested run page highlights Runs, not Overview.
  expect(links.filter((l) => l.getAttribute("aria-current") === "page").map((l) => l.textContent)).toEqual(["Runs"]);
});

test("Overview is current only on the project root", () => {
  renderShell("/projects/p1");
  const nav = screen.getByRole("navigation", { name: "Project sections" });
  expect(within(nav).getByRole("link", { current: "page" }).textContent).toBe("Overview");
});

test("the switcher changes project", () => {
  const { onProjectChange } = renderShell();
  fireEvent.change(screen.getByRole("combobox", { name: "Project" }), { target: { value: "p2" } });
  expect(onProjectChange).toHaveBeenCalledWith("p2");
});

test("the menu toggles, closes on Escape, and signs out", () => {
  const { onSignOut } = renderShell();
  const toggle = screen.getByRole("button", { name: "Open menu" });
  expect(toggle.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(toggle);
  expect(toggle.getAttribute("aria-expanded")).toBe("true");
  const menu = screen.getByRole("navigation", { name: "Project menu" });
  expect(within(menu).getAllByRole("link")).toHaveLength(5);
  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.queryByRole("navigation", { name: "Project menu" })).toBeNull();
  fireEvent.click(screen.getAllByRole("button", { name: "Sign out" })[0]);
  expect(onSignOut).toHaveBeenCalledOnce();
});
