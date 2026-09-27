import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Badge, type Status, StatusDot } from "./status";

const statuses: Status[] = ["pass", "fail", "flaky", "error", "stable"];

test.each(statuses)("%s badge always carries a text label", (status) => {
  const { container } = render(<Badge status={status} />);
  expect(container.textContent).toMatch(/^[A-Z][a-z]+$/);
  expect(container.firstElementChild!.className).toContain("bg-surface-2"); // never a colored surface
});

test("badge colors map to the result tokens", () => {
  const { container } = render(
    <>
      {statuses.map((s) => (
        <Badge key={s} status={s} />
      ))}
    </>,
  );
  expect([...container.children].map((c) => c.className.match(/text-(pass|fail|flaky|neutral|ink)\b/)![1])).toEqual([
    "pass",
    "fail",
    "flaky",
    "neutral",
    "ink",
  ]);
});

test("each status has a distinct shape, not just a color", () => {
  const { container } = render(
    <>
      {statuses.map((s) => (
        <StatusDot key={s} status={s} decorative />
      ))}
    </>,
  );
  const shapes = [...container.children].map((c) => c.className.replace(/text-\S+/, ""));
  expect(new Set(shapes).size).toBe(statuses.length);
});

test("a standalone dot is a labelled image; inside a badge it is hidden", () => {
  render(<StatusDot status="fail" label="Run failed" />);
  expect(screen.getByRole("img", { name: "Run failed" })).toBeTruthy();
  const { container } = render(<Badge status="pass" />);
  expect(container.querySelector("[aria-hidden]")).toBeTruthy();
});
