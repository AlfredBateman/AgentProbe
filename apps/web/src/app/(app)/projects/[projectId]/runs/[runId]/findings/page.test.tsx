import { render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import FindingsPage from "./page";

// A finding's label, summary and fix are a model's words about agent output: text only.
const HOSTILE = `<img src=x onerror="alert(1)"><script>alert(2)</script>**bold**`;

const result = (id: string, caseId: string, attempt: number, output = `out ${HOSTILE}`) => ({
  id,
  case: caseId,
  attempt,
  status: "failed",
  score: 0,
  output,
  error_kind: null,
  judgments: [{ judge: "contains", status: "fail", reason: `reason ${HOSTILE}` }],
});

vi.mock("next/navigation", () => ({ useParams: () => ({ projectId: "p1", runId: "run00000-0000" }) }));
vi.mock("@/lib/api/client", () => ({
  api: {
    GET: async (path: string) => {
      if (path === "/runs/{run_id}/findings")
        return {
          data: [
            { id: "f1", cluster_label: `leaks ${HOSTILE}`, summary: `summary ${HOSTILE}`, suggested_fix: `fix ${HOSTILE}`, member_result_ids: ["r1", "r2", "r3"] },
            { id: "f2", cluster_label: "wrong window", summary: "quotes 45 days", suggested_fix: null, member_result_ids: ["r4"] },
          ],
        };
      return { data: [result("r1", "api-key-leak", 0), result("r2", "api-key-leak", 1), result("r3", "prompt-leak", 0, "a different reply"), result("r4", "refund", 0)] };
    },
  },
}));

test("findings total their failing attempts, chart them as bars with a table, and render model text literally", async () => {
  const { container } = render(<FindingsPage />);
  await screen.findByRole("heading", { level: 1, name: "Findings" });

  expect(await screen.findByText("4 failing attempts → 2 findings")).toBeTruthy();
  const tile = (label: string) => [...container.querySelectorAll("dt")].find((dt) => dt.textContent === label)!.closest("dl")!;
  expect(tile("Failing attempts").textContent).toContain("4");
  expect(tile("Cases affected").textContent).toContain("3"); // api-key-leak, prompt-leak, refund

  const chart = screen.getByText("Failing attempts per finding").closest("figure")!;
  const widths = [...chart.querySelectorAll<HTMLElement>("li span[style]")].map((s) => parseFloat(s.style.width));
  expect(widths[0]).toBe(100);
  expect(widths[1]).toBeCloseTo(33.33, 1); // 3 and 1, on one scale
  const rows = [...chart.querySelectorAll("tbody tr")].map((r) => [...r.children].map((c) => c.textContent));
  expect(rows).toEqual([
    ["F-01", `leaks ${HOSTILE}`, "3", "75.0%"],
    ["F-02", "wrong window", "1", "25.0%"],
  ]);

  const first = screen.getByRole("article", { name: /^F-01/ });
  expect(first.textContent).toContain(`summary ${HOSTILE}`);
  expect(first.textContent).toContain(`fix ${HOSTILE}`);
  expect(first.textContent).toContain("3 failing attempts");
  expect(container.querySelector("img, script, strong, b, a[href^='javascript']")).toBeNull();
  // Members start collapsed, the first finding's too, behind a count.
  expect([...container.querySelectorAll("details")].every((d) => !d.open)).toBe(true);
  expect(within(first).getByText("Show 3 members")).toBeTruthy();
  // Attempts with the same output fold into one row that opens to the attempts; the rest
  // keep the run page's attempt detail: the case, its output and every judge's reason.
  const members = within(first).getByRole("list", { name: /^Members of leaks/ });
  expect(members.children).toHaveLength(2);
  const folded = members.children[0] as HTMLElement;
  expect(within(folded).getByText("2 attempts, identical output")).toBeTruthy();
  expect(within(folded).getByText("Show the 2 attempts")).toBeTruthy();
  expect(within(folded).getByRole("list", { name: "2 attempts with identical output" }).children).toHaveLength(2);
  expect(members.textContent).toContain("api-key-leak");
  expect(members.textContent).toContain("a different reply");
  expect(members.textContent).toContain(`reason ${HOSTILE}`);
});
