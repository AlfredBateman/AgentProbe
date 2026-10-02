import { describe, expect, it } from "vitest";
import { lineDiff, MAX_CELLS } from "./line-diff";

describe("lineDiff", () => {
  it("marks kept, removed and added lines in order", () => {
    expect(lineDiff("a\nb\nc", "a\nB\nc\nd")).toEqual([
      { kind: "same", text: "a" },
      { kind: "del", text: "b" },
      { kind: "add", text: "B" },
      { kind: "same", text: "c" },
      { kind: "add", text: "d" },
    ]);
  });

  it("is all `same` for identical text and handles empty sides", () => {
    expect(lineDiff("x\ny", "x\ny")?.every((l) => l.kind === "same")).toBe(true);
    expect(lineDiff("", "z")).toEqual([
      { kind: "del", text: "" },
      { kind: "add", text: "z" },
    ]);
  });

  it("rebuilds both texts from its output", () => {
    const before = "suite: s\ncases:\n  - id: a\n  - id: b\n";
    const after = "suite: s\nruns_per_case: 10\ncases:\n  - id: b\n  - id: c\n";
    const diff = lineDiff(before, after)!;
    expect(diff.filter((l) => l.kind !== "add").map((l) => l.text).join("\n")).toBe(before);
    expect(diff.filter((l) => l.kind !== "del").map((l) => l.text).join("\n")).toBe(after);
  });

  it("declines texts too large for its table", () => {
    const big = "x\n".repeat(Math.ceil(Math.sqrt(MAX_CELLS)) + 1);
    expect(lineDiff(big, big)).toBeNull();
  });
});
