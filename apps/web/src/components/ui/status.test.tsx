import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Badge, type Status, StatusDot } from "./status";

const statuses: Status[] = ["pass", "fail", "flaky", "error", "stable", "running", "queued", "quarantined"];

test.each(statuses)("%s badge always carries a text label", (status) => {
  const { container } = render(<Badge status={status} />);
  expect(container.textContent).toMatch(/^[A-Z][a-z]+$/);
  expect(container.firstElementChild!.className).toContain("bg-canvas"); // never a coloured surface
});

test("red is only fail, and no status is told by a green or amber hue", () => {
  const { container } = render(
    <>
      {statuses.map((s) => (
        <Badge key={s} status={s} />
      ))}
    </>,
  );
  const colours = new Map(statuses.map((s, i) => [s, container.children[i].className]));
  for (const [status, className] of colours) {
    expect(className.includes("text-fail"), status).toBe(status === "fail");
    expect(className).not.toMatch(/green|amber|lime|accent/);
  }
});

test("each status has a distinct shape, not just a colour", () => {
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

test("the marks are 10px", () => {
  const { container } = render(
    <>
      {statuses.map((s) => (
        <StatusDot key={s} status={s} decorative />
      ))}
    </>,
  );
  for (const dot of container.children) expect(dot.className).toMatch(/\bw-10\b|\bsize-10\b/);
});

test("a flaky chip has a dashed border", () => {
  const { container } = render(<Badge status="flaky" />);
  expect(container.firstElementChild!.className).toContain("border-dashed");
});

test("a standalone dot is a labelled image; inside a badge it is hidden", () => {
  render(<StatusDot status="fail" label="Run failed" />);
  expect(screen.getByRole("img", { name: "Run failed" })).toBeTruthy();
  const { container } = render(<Badge status="pass" />);
  expect(container.querySelector("[aria-hidden]")).toBeTruthy();
  expect(container.querySelector("[role=img]")).toBeNull();
});
