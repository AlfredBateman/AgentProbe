import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Panel } from "./panel";

test("a panel is a bordered canvas compartment; lifted steps up one surface", () => {
  const { container, rerender } = render(<Panel>body</Panel>);
  const el = () => container.firstElementChild!;
  expect(el().tagName).toBe("SECTION");
  expect(el().className).toContain("border-hairline");
  expect(el().className).toContain("bg-canvas");
  rerender(<Panel lifted>body</Panel>);
  expect(el().className).toContain("bg-surface-1");
  expect(el().className).toContain("border-hairline-strong");
});

test("a title makes a header strip with the actions beside it", () => {
  render(
    <Panel title="Latest runs" actions={<button>View all</button>}>
      body
    </Panel>,
  );
  const heading = screen.getByRole("heading", { level: 2, name: "Latest runs" });
  expect(heading.className).toContain("type-headline");
  expect(heading.parentElement!.tagName).toBe("HEADER");
  expect(heading.parentElement!.className).toContain("border-b");
  expect(screen.getByRole("button", { name: "View all" })).toBeTruthy();
});

test("the title can be set in label type", () => {
  render(<Panel title="Cases" titleStyle="label" />);
  expect(screen.getByRole("heading", { name: "Cases" }).className).toContain("type-label");
});

test("with an href the title is the one link and the corner arrow is hidden from assistive technology", () => {
  const { container } = render(
    <Panel title="Support bot" href="/projects/1">
      body
    </Panel>,
  );
  const link = screen.getByRole("link", { name: "Support bot" });
  expect(link.getAttribute("href")).toBe("/projects/1");
  expect(screen.getAllByRole("link")).toHaveLength(1);
  expect(link.className).toContain("after:inset-0"); // stretched over the whole panel
  expect(container.querySelector("svg")!.getAttribute("aria-hidden")).toBe("true");
});

test("a panel without an href has no link and no arrow", () => {
  const { container } = render(<Panel title="Plain">body</Panel>);
  expect(screen.queryByRole("link")).toBeNull();
  expect(container.querySelector("svg")).toBeNull();
});

test("crosshair marks are opt-in", () => {
  const { container, rerender } = render(<Panel>body</Panel>);
  expect(container.firstElementChild!.className).not.toContain("crosshair");
  rerender(<Panel crosshair>body</Panel>);
  expect(container.firstElementChild!.className).toContain("crosshair");
});
