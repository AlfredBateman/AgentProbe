import Link from "next/link";
import { buttonClasses } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { CodeBlock } from "@/components/ui/code";
import { GradientCard } from "@/components/ui/gradient-card";
import { Badge } from "@/components/ui/status";

const STEPS = [
  {
    title: "Point it at your agent",
    body: "HTTP, MCP, or a CLI-only Python adapter. No SDK to install inside the agent itself.",
  },
  {
    title: "Run every case, many times",
    body: "Multi-run execution catches the flakiness a single pass would miss, and labels every case pass / fail / flaky.",
  },
  {
    title: "Gate the PR on a real regression",
    body: "A one-sided Fisher exact test per case and a paired sign-flip test at suite level decide — not a raw score delta.",
  },
];

const CLI_EXAMPLE = `$ agentprobe run suites/regression.yaml \\
    --push --branch "$GITHUB_HEAD_REF" --baseline-branch main

  refund-outside-window   0/5  FAIL    (p = 0.0040)
  order-status-lookup     4/5  FLAKY
  27 more cases            —   PASS

  verdict: regression — blocking merge`;

export default function Home() {
  return (
    <main className="flex flex-1 flex-col">
      <header className="mx-auto flex h-56 w-full max-w-1440 shrink-0 items-center justify-between px-16 tablet:px-30">
        <span className="font-display text-[20px] font-medium tracking-[-0.6px] text-ink">AgentProbe</span>
        <div className="flex items-center gap-8">
          <Link href="/login" className={buttonClasses("secondary")}>
            Sign in
          </Link>
          <Link href="/register" className={buttonClasses("primary")}>
            Get started
          </Link>
        </div>
      </header>

      <section className="mx-auto flex w-full max-w-1440 flex-col items-start gap-20 px-16 py-40 tablet:px-30 tablet:py-96">
        <h1 className="font-display max-w-900 text-display-md tablet:text-display-lg desktop:text-display-xxl">
          Statistically-corrected, flakiness-aware regression detection for LLM agents.
        </h1>
        <p className="max-w-640 text-body-lg text-ink-muted">
          AgentProbe runs every case in your suite many times, judges traces and tool calls — not just final text —
          and fails a pull request only when a drop is statistically meaningful. Not when a flaky case happened to
          fail this time.
        </p>
        <div className="flex flex-wrap items-center gap-12">
          <Link href="/register" className={buttonClasses("primary")}>
            Get started
          </Link>
          <Link href="/login" className={buttonClasses("secondary")}>
            Sign in
          </Link>
        </div>
      </section>

      <section className="mx-auto w-full max-w-1440 px-16 py-40 tablet:px-30">
        <h2 className="font-display text-display-md">How it works</h2>
        <div className="mt-30 grid grid-cols-1 gap-15 tablet:grid-cols-3">
          {STEPS.map((step, i) => (
            <Card key={step.title}>
              <span className="text-caption text-ink-muted">{String(i + 1).padStart(2, "0")}</span>
              <h3 className="mt-8 font-display text-dash-heading">{step.title}</h3>
              <p className="mt-8 text-body-sm text-ink-muted">{step.body}</p>
            </Card>
          ))}
        </div>
      </section>

      <section className="mx-auto w-full max-w-1440 px-16 py-40 tablet:px-30">
        <div className="grid grid-cols-1 gap-20 tablet:grid-cols-2">
          <div>
            <h2 className="font-display text-display-md">Run it from the CLI</h2>
            <p className="mt-12 text-body text-ink-muted">
              Every run — local or CI — executes through the same engine, so the check that blocks your PR is the
              one you can reproduce on your own machine.
            </p>
            <CodeBlock code={CLI_EXAMPLE} label="terminal" className="mt-20" />
          </div>
          <Card title="agentprobe / regression-check">
            <p className="text-body-sm text-ink-muted">PR #482 · support-bot v2 vs. v1 baseline</p>
            <ul className="mt-15 flex flex-col gap-8">
              <li className="flex items-center justify-between gap-8">
                <span className="text-body-sm">refund-outside-window</span>
                <Badge status="fail">5/5 → 0/5</Badge>
              </li>
              <li className="flex items-center justify-between gap-8">
                <span className="text-body-sm">order-status-lookup</span>
                <Badge status="flaky">4/5</Badge>
              </li>
              <li className="flex items-center justify-between gap-8">
                <span className="text-body-sm">unauthorized-delete</span>
                <Badge status="pass" />
              </li>
              <li className="flex items-center justify-between gap-8">
                <span className="text-body-sm">+26 more cases</span>
                <Badge status="pass" />
              </li>
            </ul>
            <p className="mt-15 text-body-sm text-fail">1 case regressed at p = 0.0040 — blocking merge.</p>
          </Card>
        </div>
      </section>

      <section className="mx-auto w-full max-w-1440 px-16 py-40 tablet:px-30">
        <GradientCard>
          <p className="font-display text-display-md">From PR to verdict, in one gate.</p>
          <p className="mt-12 max-w-560 text-body-lg text-ink/90">
            Most agent test tools threshold a raw score. AgentProbe blocks a merge only on a statistically
            significant drop, corrected for testing many cases across many runs — so a flaky case never costs you a
            green check.
          </p>
        </GradientCard>
      </section>

      <footer className="mx-auto w-full max-w-1440 px-16 py-40 text-caption text-ink-muted tablet:px-30">
        AgentProbe — statistically-corrected, flakiness-aware regression detection for LLM agents.
      </footer>
    </main>
  );
}
