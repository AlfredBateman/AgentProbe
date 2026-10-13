import Link from "next/link";
import { buttonClasses } from "@/components/ui/button";
import facts from "./facts.json";
import { demoUrl } from "./site";

const { detection, falseAlarms, runsPerCase } = facts;

// Value, what it counts, and the condition it was measured under (docs/metrics.md).
const CALLOUTS = [
  [`${detection.detected} / ${detection.planted}`, "Planted flaws caught", "mock mode"],
  [falseAlarms.shipped, "False alarms", "simulation"],
  [runsPerCase, "Attempts per case", "demo suite"],
];

export function Hero() {
  const demo = demoUrl();
  return (
    <section aria-labelledby="hero-title" className="border-b border-hairline-strong">
      <div className="overflow-hidden px-16 pt-24 pb-32 tablet:px-32 tablet:pt-48 tablet:pb-48">
        {/* An @container: the headline, the visual box and their offsets are all in cqi, so the
            composition keeps its proportions at every width and cannot overflow. */}
        <div className="@container grid grid-cols-[minmax(0,1fr)]">
          <div className="col-start-1 row-start-1 grid py-24 tablet:py-48">
            {/* The box the 3D piece will take over. Its size is fixed by aspect ratio, so swapping
                the content moves nothing. Squares, not round dots: the system has no radius. */}
            <div
              aria-hidden
              className="scanlines col-start-1 row-start-1 ml-[22cqi] aspect-4/3 w-[40cqi] self-end border border-hairline-strong bg-surface-1 text-hairline-strong"
            >
              <svg viewBox="0 0 320 240" className="block size-full">
                <defs>
                  <pattern id="hero-dots" width="16" height="16" patternUnits="userSpaceOnUse">
                    <rect x="7" y="7" width="2" height="2" fill="currentColor" />
                  </pattern>
                </defs>
                <rect width="320" height="240" fill="url(#hero-dots)" />
              </svg>
            </div>
            <h1 id="hero-title" className="relative col-start-1 row-start-1 self-end type-display-xxl">
              <span className="block text-accent">Regressions</span>
              <span className="block">not</span>
              <span className="ml-[27cqi] block text-outline text-accent">noise</span>
            </h1>
          </div>
          <p aria-hidden className="col-start-1 row-start-2 border-t border-hairline pt-8 type-micro text-ink-muted">
            Fig. 01 {"///"} Dot grid {"///"} Illustrative
          </p>
          {/* Beside the last two lines on desktop, with leader lines back to them; a row under
              the caption otherwise. */}
          <dl className="col-start-1 row-start-3 mt-24 grid gap-16 tablet:grid-cols-3 desktop:row-start-1 desktop:mt-0 desktop:mb-48 desktop:w-[30%] desktop:grid-cols-1 desktop:self-end desktop:justify-self-end">
            {CALLOUTS.map(([value, label, condition]) => (
              <div key={label} className="flex items-center gap-12">
                <span aria-hidden className="hidden h-px min-w-24 flex-1 bg-ink-muted desktop:block" />
                {/* One width, so the three leader lines end on the same vertical. */}
                <div className="desktop:w-240 desktop:shrink-0">
                  <dd className="type-display-md tabular-nums">{value}</dd>
                  <dt className="mt-4 type-micro text-ink-muted">
                    {label} {"///"} {condition}
                  </dt>
                </div>
              </div>
            ))}
          </dl>
        </div>
        <div className="mt-32 flex flex-wrap items-end justify-between gap-24">
          <p className="max-w-640 type-body-lg text-ink-muted">
            Regression detection for LLM agents. Statistically corrected. Flakiness-aware.
          </p>
          <div className="flex flex-col gap-8 desktop:items-end">
            <div className="flex flex-wrap gap-12">
              <Link href="/register" className={buttonClasses("primary")}>
                <span aria-hidden>{">>>"}</span>
                Get started
              </Link>
              {demo && (
                <a href={demo} className={buttonClasses("secondary")}>
                  Try the demo
                </a>
              )}
            </div>
            {demo && (
              <p className="type-micro text-ink-muted">
                <span aria-hidden>{"/// "}</span>
                Demo servers take about 30 s to wake
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
