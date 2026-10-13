import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import DesignBoards from "./page.dev";

test("the five boards render, with a specimen for every type tier in DESIGN.md", () => {
  const { container } = render(<DesignBoards />);
  expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(5);
  // One row per tier in DESIGN.md; a tier added there without a specimen leaves its row empty.
  expect(container.querySelectorAll("[data-tier]").length).toBeGreaterThan(0);
  expect(container.querySelectorAll("[data-tier] p:empty")).toHaveLength(0);
});
