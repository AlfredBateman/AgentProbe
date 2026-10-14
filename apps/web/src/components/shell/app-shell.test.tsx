import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { resetWake } from "@/lib/api/wake";
import { AppShell } from "./app-shell";

const projects = [
  { id: "p1", name: "support-bot" },
  { id: "p2", name: "rag-bot" },
];

// `null` is "no project open": an undefined argument would take the default.
function renderShell(pathname = "/projects/p1/runs/r9", projectId: string | null = "p1") {
  const onProjectChange = vi.fn();
  const onSignOut = vi.fn();
  render(
    <AppShell
      projects={projects}
      projectId={projectId ?? undefined}
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

afterEach(() => resetWake());

const rail = () => screen.getByRole("navigation", { name: "Project sections" });

test("the rail links into the current project and marks the active section", () => {
  renderShell();
  const links = within(rail()).getAllByRole("link");
  expect(links.map((l) => l.getAttribute("href"))).toEqual([
    "/projects",
    "/projects/p1",
    "/projects/p1/agents",
    "/projects/p1/suites",
    "/projects/p1/runs",
    "/projects/p1/settings",
  ]);
  // A nested run page highlights Runs, and only Runs.
  expect(links.filter((l) => l.getAttribute("aria-current") === "page").map((l) => l.textContent)).toEqual(["Runs"]);
});

test("the project's name is the way to its overview, current only on the project root", () => {
  renderShell("/projects/p1");
  const current = within(rail()).getByRole("link", { current: "page" });
  expect(current.getAttribute("href")).toBe("/projects/p1");
  expect(current.textContent).toBe("support-bot"); // as written, never uppercased by the DOM
});

test("on the projects list only Projects is current, and project sections are not offered", () => {
  renderShell("/projects", null);
  const links = within(rail()).getAllByRole("link");
  expect(links.map((l) => l.getAttribute("href"))).toEqual(["/projects"]);
  expect(within(rail()).getByRole("link", { current: "page" }).textContent).toBe("Projects");
  expect(screen.getByText(/Open a project to see/)).toBeTruthy();
});

test("the switcher changes project, and on the list it asks for one", () => {
  const { onProjectChange } = renderShell();
  fireEvent.change(screen.getByRole("combobox", { name: "Project" }), { target: { value: "p2" } });
  expect(onProjectChange).toHaveBeenCalledWith("p2");
});

test("without a project the switcher shows a disabled prompt", () => {
  renderShell("/projects", null);
  const prompt = within(screen.getByRole("combobox", { name: "Project" })).getByRole("option", { name: "Select a project" }) as HTMLOptionElement;
  expect(prompt.disabled).toBe(true);
  expect(prompt.selected).toBe(true);
});

test("the skip link is the first tab stop and targets the main region", () => {
  renderShell();
  const skip = screen.getByRole("link", { name: "Skip to content" });
  expect(skip.getAttribute("href")).toBe("#main-content");
  expect(document.body.querySelector("a, button, select")).toBe(skip);
  const main = screen.getByRole("main");
  expect(main.id).toBe("main-content");
  expect(main.getAttribute("tabindex")).toBe("-1");
});

test("arrow keys, Home and End move between rail links", () => {
  renderShell("/projects/p1");
  const links = within(rail()).getAllByRole("link");
  links[0].focus();
  fireEvent.keyDown(links[0], { key: "ArrowDown" });
  expect(document.activeElement).toBe(links[1]);
  fireEvent.keyDown(links[1], { key: "End" });
  expect(document.activeElement).toBe(links.at(-1));
  fireEvent.keyDown(links.at(-1)!, { key: "ArrowDown" }); // wraps
  expect(document.activeElement).toBe(links[0]);
  fireEvent.keyDown(links[0], { key: "ArrowUp" });
  expect(document.activeElement).toBe(links.at(-1));
  fireEvent.keyDown(links.at(-1)!, { key: "Home" });
  expect(document.activeElement).toBe(links[0]);
});

test("the strip shows the environment, the version and the API status", () => {
  renderShell();
  expect(screen.getByText(/Env/).textContent).toMatch(/Env\s+Prod|Env\s+Dev/);
  expect(screen.getByText(/Rev/).textContent).toMatch(/Rev\s+v\d+\.\d+\.\d+/);
  // Nothing has answered yet in this test, so the chip is still asking.
  expect(within(screen.getAllByRole("status")[0]).getByText("Checking")).toBeTruthy();
});

test("the status chip follows the wake state", async () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
  const { awakeFetch } = await import("@/lib/api/wake");
  vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 200 })));
  renderShell();
  await act(() => awakeFetch(new Request("http://localhost/api/projects"), []));
  expect(within(screen.getAllByRole("status")[0]).getByText("Awake")).toBeTruthy();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

test("the menu toggles, closes on Escape, and signs out", () => {
  const { onSignOut } = renderShell();
  const toggle = screen.getByRole("button", { name: "Open menu" });
  expect(toggle.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(toggle);
  expect(toggle.getAttribute("aria-expanded")).toBe("true");
  const menu = screen.getByRole("navigation", { name: "Project menu" });
  expect(within(menu).getAllByRole("link")).toHaveLength(6);
  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.queryByRole("navigation", { name: "Project menu" })).toBeNull();
  fireEvent.click(screen.getAllByRole("button", { name: "Sign out" })[0]);
  expect(onSignOut).toHaveBeenCalledOnce();
});
