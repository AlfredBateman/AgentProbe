import { LabelBadge } from "@/components/run/labels";
import { Stat } from "@/components/ui/stat";
import facts from "./facts.json";
import { CountUp, Reveal } from "./motion";
import { ScrubValue } from "./proof-scrub";
import { REPO } from "./site";

const { detection, falseAlarms, regression } = facts;

/** The bundled demo's regression, as the compare view reports it. Every figure is from facts.json. */
export function Proof() {
  return (
    <section id="proof" aria-labelledby="proof-title" className="border-b border-hairline-strong px-16 py-48 tablet:px-32 tablet:py-96">
      <div className="flex flex-wrap items-end justify-between gap-16">
        <h2 id="proof-title" className="type-display-xl">
          Proof
        </h2>
        <p className="type-micro text-ink-muted">
          Measured {detection.measured} {"///"} mock mode
        </p>
      </div>
      <Reveal as="article" aria-label="Demo regression" className="crosshair mt-32 border border-hairline-strong">
        <header className="flex flex-wrap items-center justify-between gap-12 border-b border-hairline bg-surface-1 px-16 py-10">
          <p className="type-code text-ink-muted">
            {regression.baseline} {"->"} {regression.candidate}
          </p>
          <span className="border border-fail bg-fail px-8 py-3 type-label whitespace-nowrap text-on-fail">Regression</span>
        </header>
        <div className="flex flex-wrap items-center gap-x-24 gap-y-12 border-b border-hairline px-16 py-16">
          <code className="type-code">{regression.caseId}</code>
          <span className="type-data whitespace-nowrap">
            {regression.baselinePasses} {"->"} <ScrubValue from={regression.baselinePasses} to={regression.candidatePasses} /> passed
          </span>
          <LabelBadge label={regression.label} />
        </div>
        <div className="grid-lines grid-cols-1 border-b border-hairline tablet:grid-cols-2 desktop:grid-cols-4">
          <Stat label="P-value" value={<span className="normal-case">{regression.p}</span>} tone="fail" note={`Threshold ${regression.threshold} /// Fisher exact`} />
          <Stat label="Pass rate" value={<ScrubValue from={regression.passRateBefore} to={regression.passRateAfter} />} note={`Was ${regression.passRateBefore} /// CI unmeasured`} />
          <Stat label="False alarms" value={<CountUp value={falseAlarms.shipped} />} note={`95% CI ${falseAlarms.interval} /// naive ${falseAlarms.naive}`} />
          <Stat
            label="Planted flaws detected"
            value={<CountUp value={`${detection.detected} / ${detection.planted}`} />}
            note={`${detection.agents} demo agents /// controls ${detection.controlsPassed} of ${detection.controls}`}
          />
        </div>
        <p className="max-w-720 px-16 py-12 type-body-sm text-ink-muted">
          Mock mode: the demo agents are deterministic rule engines, so this proves the pipeline end to end, not detection on live
          models. The false-alarm rate is a seeded simulation of unchanged flaky agents ({falseAlarms.scenario}).{" "}
          <a href={`${REPO}/blob/main/docs/metrics.md`}>How each number was measured</a>
        </p>
      </Reveal>
    </section>
  );
}
