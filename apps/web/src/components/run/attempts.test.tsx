import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { AttemptList } from "./attempts";

// Output and judge reasons quote an agent that may have been attacked: all of it is text.
const HOSTILE = `<img src=x onerror="alert(1)"><script>alert(2)</script><a href="javascript:alert(3)">x</a>**bold**`;

test("hostile output, judge names and reasons render as literal text; control characters are visible", () => {
  const { container } = render(
    <AttemptList
      label="Attempts of c"
      items={[
        {
          key: "1",
          title: `case ${HOSTILE}`,
          attempt: 0,
          status: "failed",
          score: 0,
          output: `out ${HOSTILE}\u001b[31mred‮`,
          judgments: [{ judge: `judge ${HOSTILE}`, status: "fail", reason: `reason ${HOSTILE}` }],
        },
      ]}
    />,
  );
  expect(container.querySelector("img, script, iframe, a, strong, b")).toBeNull();
  expect(container.textContent).toContain(`case ${HOSTILE}`);
  expect(container.textContent).toContain(`judge ${HOSTILE}`);
  expect(container.textContent).toContain(`reason ${HOSTILE}`);
  expect(container.textContent).toContain("␛[31mred⟨U+202E⟩"); // ESC and the bidi override, made visible
  expect(container.textContent).not.toContain("\u001b");
});

test("a failed attempt carries a red edge, its word and a trace link; a snapshot has no link", () => {
  const { rerender } = render(
    <AttemptList
      label="Attempts of refund"
      items={[
        { key: "a", attempt: 0, status: "failed", score: 0, latencyMs: 420, cost: 0.0004, judgments: [], traceHref: "/projects/p/runs/r/results/a" },
        { key: "b", attempt: 1, status: "passed", score: 1, latencyMs: null, cost: null, judgments: [] },
      ]}
    />,
  );
  const [failed, passed] = [...screen.getByRole("list", { name: "Attempts of refund" }).children];
  expect(failed.classList.contains("border-l-fail")).toBe(true);
  expect(failed.textContent).toContain("Attempt 1");
  expect(failed.textContent).toContain("Failed");
  expect(failed.textContent).toContain("420 ms");
  expect(screen.getByRole("link", { name: "View trace" }).getAttribute("href")).toBe("/projects/p/runs/r/results/a");
  expect(passed.classList.contains("border-l-fail")).toBe(false);
  expect(passed.textContent).toContain("—"); // unknown latency and cost are a dash, never 0

  rerender(<AttemptList label="Attempts of refund" items={[{ key: "a", attempt: 0, status: "failed", score: 0, judgments: [] }]} />);
  expect(screen.queryByRole("link")).toBeNull();
  expect(screen.queryByText("Latency")).toBeNull(); // not part of a public snapshot
});
