import { Badge, type Status } from "@/components/ui/status";

// Run, case-label and verdict vocabularies as badges. Every badge carries its text (ADR 0028).
const RUN: Record<string, [Status, string]> = {
  queued: ["stable", "Queued"],
  running: ["stable", "Running"],
  completed: ["pass", "Completed"],
  failed: ["fail", "Failed"],
  cancelled: ["error", "Cancelled"],
};
const LABEL: Record<string, [Status, string]> = {
  "stable-pass": ["pass", "Stable pass"],
  "stable-fail": ["fail", "Stable fail"],
  flaky: ["flaky", "Flaky"],
};
const VERDICT: Record<string, [Status, string]> = {
  regression: ["fail", "Regression"],
  improvement: ["pass", "Improvement"],
  no_change: ["stable", "No change"],
};
const ATTEMPT: Record<string, [Status, string]> = {
  passed: ["pass", "Passed"],
  failed: ["fail", "Failed"],
  error: ["error", "Error"],
};
const JUDGMENT: Record<string, [Status, string]> = {
  pass: ["pass", "Pass"],
  fail: ["fail", "Fail"],
  error: ["error", "Error"],
};

function badge(map: Record<string, [Status, string]>, value: string) {
  const [status, text] = map[value] ?? ["error", value];
  return <Badge status={status}>{text}</Badge>;
}

export const RunStatusBadge = ({ status }: { status: string }) => badge(RUN, status);
export const LabelBadge = ({ label }: { label: string }) => badge(LABEL, label);
export const VerdictBadge = ({ verdict }: { verdict: string }) => badge(VERDICT, verdict);
export const AttemptBadge = ({ status }: { status: string }) => badge(ATTEMPT, status);
export const JudgmentBadge = ({ status }: { status: string }) => badge(JUDGMENT, status);

export const LABELS = Object.entries(LABEL).map(([value, [, text]]) => ({ value, text }));
