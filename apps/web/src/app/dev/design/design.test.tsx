import { readFileSync } from "node:fs";
import { join } from "node:path";
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

test("REV marks show the package version, never a typed one", () => {
  const { version } = JSON.parse(readFileSync(join(process.cwd(), "package.json"), "utf8"));
  const { container } = render(<DesignBoards />);
  const revs = [...(container.textContent ?? "").matchAll(/REV\s+(\d[\d.]*\d)/g)].map((m) => m[1]);
  expect(revs.length).toBeGreaterThan(0);
  expect(new Set(revs)).toEqual(new Set([version]));
});

// An element's own words: its text plus any descendants that do not set their own type tier.
function ownText(node: Node): string {
  return [...node.childNodes]
    .map((child) => (child.nodeType === 3 ? child.textContent : child instanceof Element && !/\btype-/.test(child.className) ? ownText(child) : ""))
    .join(" ");
}

test("mono uppercase is for labels: no label, micro or data text runs past 8 words", () => {
  const { container } = render(<DesignBoards />);
  for (const el of container.querySelectorAll(".type-label, .type-micro, .type-data, .type-button")) {
    // A word is letters on their own; "28px" and "0.04em" are data, not words.
    const words = ownText(el).match(/(?<![\p{L}\p{N}])\p{L}{2,}(?![\p{L}\p{N}])/gu) ?? [];
    expect(words.length, ownText(el)).toBeLessThanOrEqual(8);
  }
});

test("a status has a shape cue, and lime is only ever a fill on an action or a hero panel", () => {
  const { container } = render(<DesignBoards />);
  const chip = (label: string) => [...container.querySelectorAll("#board-run span.border")].find((el) => el.textContent === label);
  expect(chip("Fail")?.querySelector(".mark-fail")).not.toBeNull();
  expect(chip("Error")?.querySelector(".mark-error")).not.toBeNull();
  // Verdict chips are spans; only buttons and the hero's emphasised panel (an anchor) may fill.
  for (const el of container.querySelectorAll(".bg-accent")) expect(["BUTTON", "A"]).toContain(el.tagName);
  expect(chip("Improvement")?.className).not.toContain("bg-accent");
});
