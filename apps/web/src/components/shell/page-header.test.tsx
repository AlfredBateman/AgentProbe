import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { PageHeader } from "./page-header";

test("a header has the eyebrow, one h1, the actions and a metadata line", () => {
  render(
    <PageHeader eyebrow="[ Project ]" title="Agents" actions={<button>New agent</button>}>
      <p>2 agents</p>
    </PageHeader>,
  );
  expect(screen.getByRole("heading", { level: 1, name: "Agents" })).toBeTruthy();
  expect(screen.getByText("[ Project ]")).toBeTruthy();
  expect(screen.getByRole("button", { name: "New agent" })).toBeTruthy();
  expect(screen.getByText("2 agents")).toBeTruthy();
});

test("a title the user wrote keeps its case; the interface's own titles are display caps", () => {
  const { rerender } = render(<PageHeader eyebrow="x" title="Overview" />);
  expect(screen.getByRole("heading").className).not.toContain("normal-case");
  rerender(<PageHeader eyebrow="x" title="e3-check" verbatim />);
  expect(screen.getByRole("heading").className).toContain("normal-case");
});
