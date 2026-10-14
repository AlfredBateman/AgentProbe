import { readFileSync } from "node:fs";
import path from "node:path";
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { AttemptStrip, Bars, ChartFigure, ChartTable, RateWhiskers, RunTrend } from "./telemetry";

const styled = (root: ParentNode, selector = "span[style]") => [...root.querySelectorAll<HTMLElement>(selector)];

test("a figure carries its own table view and draws in", () => {
  const { container } = render(
    <ChartFigure title="Pass rate" table={<ChartTable caption="Pass rate by run" head={["Run", "Rate"]} rows={[["a1b2", "90.0%"]]} />}>
      <p>plot</p>
    </ChartFigure>,
  );
  expect(container.querySelector(".draw-in")?.textContent).toBe("plot");
  // The table is real text inside a native <details>: reachable by keyboard, no script.
  const details = container.querySelector("details")!;
  expect(details.querySelector("summary")?.textContent).toBe("Table view");
  expect(details.querySelector("table")?.textContent).toContain("90.0%");
  expect(details.querySelector("caption")?.textContent).toBe("Pass rate by run");
});

test("the draw-in is a stepped clip that reduced motion and the dev switch both turn off", () => {
  const css = readFileSync(path.join(__dirname, "../../app/globals.css"), "utf8");
  const utility = css.slice(css.indexOf("@utility draw-in"));
  expect(utility).toContain("prefers-reduced-motion: no-preference");
  expect(utility).toContain(":not([data-reduce-motion])");
  expect(utility).toContain("steps(6, end)");
  expect(css).toMatch(/@keyframes draw-in\s*{\s*from\s*{\s*clip-path: inset\(0 100% 0 0\)/);
});

test("whiskers sit at the value and span the interval on a fixed 0 to 100% ruler", () => {
  const { container } = render(
    <RateWhiskers
      rows={[
        { label: "Baseline", tone: "baseline", value: 0.9, lower: 0.7, upper: 0.97 },
        { label: "Candidate", tone: "candidate", value: 0.4, lower: null, upper: null },
      ]}
    />,
  );
  const [baseline, candidate] = [...container.querySelectorAll("li")];
  expect(baseline.classList.contains("text-ink")).toBe(true);
  expect(candidate.classList.contains("text-accent")).toBe(true); // lime marks the candidate
  const whisker = styled(baseline).find((b) => b.style.width)!;
  expect(whisker.style.left).toBe("70%");
  expect(parseFloat(whisker.style.width)).toBeCloseTo(27, 5);
  expect(styled(baseline).some((b) => b.style.left === "90%" && b.classList.contains("size-10"))).toBe(true);
  // A run without an interval shows its point and no whisker.
  expect(styled(candidate).some((b) => b.style.width)).toBe(false);
  expect(styled(candidate).some((b) => b.style.left === "40%" && b.classList.contains("size-10"))).toBe(true);
  expect(container.textContent).toContain("0%");
  expect(container.textContent).toContain("100%");
});

test("an attempt strip has one shape per attempt: pass, failure cross, error", () => {
  const { container } = render(<AttemptStrip passes={2} attempts={6} errors={1} tone="candidate" />);
  const marks = [...container.querySelectorAll("span > span")];
  expect(marks).toHaveLength(6);
  const count = (cls: string) => marks.filter((m) => m.classList.contains(cls));
  expect(count("bg-current")).toHaveLength(2);
  expect(count("mark-fail")).toHaveLength(3); // 6 attempts - 2 passes - 1 error
  expect(count("mark-error")).toHaveLength(1);
  expect(count("mark-fail").every((m) => m.classList.contains("text-fail"))).toBe(true);
  expect(count("bg-current").every((m) => m.classList.contains("text-accent"))).toBe(true);
});

test("bars share one scale; red only for failure, hatch for flaky, and every row names its value", () => {
  const { container } = render(
    <Bars
      rows={[
        { key: "a", label: "refund-flow", value: 8, tone: "fail" },
        { key: "b", label: "order-status", value: 2, tone: "flaky", note: "20%" },
        { key: "c", label: "none", value: 0, tone: "candidate" },
      ]}
    />,
  );
  const fills = styled(container, "li span[style]");
  expect(fills.map((f) => f.style.width)).toEqual(["100%", "25%", "0%"]);
  expect(fills[0].classList.contains("bg-fail")).toBe(true);
  expect(fills[1].classList.contains("hatch")).toBe(true);
  expect(fills[2].classList.contains("bg-accent")).toBe(true);
  expect(screen.getByText("refund-flow").classList.contains("type-code")).toBe(true); // a case id is never recased
  expect(container.textContent).toContain("2 20%");
});

test("the trend marks the baseline and the candidate in place, and leaves a run without a rate out", () => {
  const { container } = render(
    <RunTrend
      points={[
        { id: "1", rate: 0.9, role: "baseline" },
        { id: "2", rate: null },
        { id: "3", rate: 0.5 },
        { id: "4", rate: 0.2, role: "candidate" },
      ]}
    />,
  );
  expect(container.textContent).toContain("Baseline");
  expect(container.textContent).toContain("Candidate");
  const markers = styled(container).filter((s) => [...s.classList].some((c) => c.startsWith("size-")));
  expect(markers).toHaveLength(3); // the null run has no marker
  expect(markers[0].style.left).toBe("0%");
  expect(markers[2].style.left).toBe("100%");
  expect(markers[2].style.top).toBe("80%"); // 20% sits near the bottom
  expect(markers[2].classList.contains("bg-accent")).toBe(true);
  // 1px line, drawn at any width.
  const line = container.querySelector("polyline")!;
  expect(line.getAttribute("vector-effect")).toBe("non-scaling-stroke");
  expect(line.getAttribute("stroke-width")).toBe("1");
});
