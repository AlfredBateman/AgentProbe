import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { components } from "@/lib/api/schema";
import SharedRunPage from "./page";

// XSS regression: a share link is public, and everything on it came from the agent, its judges
// or a suite author. It must all render as literal text.
const XSS = `<img src=x onerror="alert(1)"><script>alert(2)</script><a href="javascript:alert(3)">x</a>**bold**`;

const shared: components["schemas"]["SharedRunOut"] = {
  suite: `suite ${XSS}`,
  agent: `agent ${XSS}`,
  status: "completed",
  runs_per_case: 1,
  pass_rate: 0,
  ci_lower: 0,
  ci_upper: 0.5,
  created_at: "2026-10-03T10:00:00Z",
  started_at: "2026-10-03T10:00:00Z",
  finished_at: "2026-10-03T10:00:01Z",
  cases: [{ case: `case ${XSS}`, label: "stable-fail", pass_rate: 0, passes: 0, attempts: 1 }],
  results: [
    {
      case: `case ${XSS}`,
      attempt: 0,
      status: "failed",
      output: `output ${XSS}`,
      score: 0,
      error_kind: null,
      judgments: [{ judge: `judge ${XSS}`, status: "fail", reason: `reason ${XSS}` }],
    },
  ],
};

vi.mock("next/navigation", () => ({ useParams: () => ({ token: "t0ken" }) }));
vi.mock("@/lib/api/wake", () => ({ awakeFetch: async () => Response.json(shared) }));

test("XSS: every untrusted field on the public share page renders as literal text", async () => {
  const { container } = render(<SharedRunPage />);
  fireEvent.click(await screen.findByRole("button", { name: `Show attempts of case ${XSS}` }));
  await screen.findByText(`reason ${XSS}`);
  // The only links are the page's own: the logo and "Try AgentProbe".
  expect([...container.querySelectorAll("a")].map((a) => a.getAttribute("href"))).toEqual(["/", "/register"]);
  expect(container.querySelector("img, script, iframe, strong, b")).toBeNull();
  for (const field of ["suite", "agent", "output", "judge", "reason"]) {
    expect(container.textContent).toContain(`${field} ${XSS}`);
  }
});
