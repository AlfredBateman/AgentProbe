// Generates src/components/landing/facts.json from docs/metrics.md and README.md, so no figure on
// the landing page is typed by hand. Run: pnpm --filter web gen:facts
// facts.test.ts fails when the committed file differs from a fresh generation.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (file) => readFileSync(fileURLToPath(new URL(`../../../${file}`, import.meta.url)), "utf8");
export const OUTPUT = fileURLToPath(new URL("../src/components/landing/facts.json", import.meta.url));

// A figure that is not where it is expected stops the build; it is never left blank.
function pick(text, pattern, what) {
  const match = text.match(pattern);
  if (!match) throw new Error(`gen-landing-facts: ${what} not found`);
  return match.groups;
}

export function generate(metrics = read("docs/metrics.md"), readme = read("README.md")) {
  const { block } = pick(metrics, /<!-- detection:mock:start -->(?<block>[\s\S]*?)<!-- detection:mock:end -->/, "the mock detection block");
  const detection = pick(
    block,
    /Detected (?<detected>\d+) of (?<planted>\d+) planted vulnerabilities across (?<agents>\d+) demo agents[\s\S]*?Negative controls: (?<controlsPassed>\d+) of (?<controls>\d+) passed[\s\S]*?measured (?<measured>\d{4}-\d{2}-\d{2})/,
    "the detection summary",
  );
  const row = pick(
    block,
    /\| support-v2-refund-regression \| (?<candidate>\S+) \| (?<caseId>\S+) \| (?<label>[\w-]+) \((?<candidatePasses>\d+\/\d+) passed\) \| yes \| regression against (?<baseline>\S+) \([^:]+: p = (?<p>[\d.e+-]+), threshold (?<threshold>[\d.]+)\)/,
    "the refund regression row",
  );
  const { runsPerCase } = pick(metrics, /\*\*Runs per case: (?<runsPerCase>\d+)\*\*/, "runs per case");
  const seeded = pick(
    readme,
    /pass rate fell from (?<passRateBefore>[\d.]+%) to (?<passRateAfter>[\d.]+%), and one case went from (?<baselinePasses>\d+\/\d+) to \d+\/\d+/,
    "the seeded run's pass rates in README.md",
  );
  const alarms = pick(
    metrics,
    /\((?<scenario>\d+ cases × \d+ runs per case, \d+% of cases flaky)\):\r?\n- A naive single-run pass\/fail check raised a false regression alarm on \*\*(?<naive>[\d.]+%)\*\* of runs\.\r?\n- AgentProbe's multi-run statistical check raised one on \*\*(?<shipped>[\d.]+%)\*\* of runs\.\r?\n\r?\nThat is a \*\*(?<reduction>[\d.]+%) reduction\*\*/,
    "the false-alarm result",
  );
  const { interval } = pick(metrics, /alpha split \(shipped\) \| \*\*[\d.]+% \((?<interval>[\d.]+–[\d.]+)\)\*\*/, "the shipped false-alarm interval");

  const facts = {
    detection,
    regression: { ...row, ...seeded },
    runsPerCase,
    falseAlarms: { ...alarms, interval },
  };
  return `${JSON.stringify(facts, null, 2)}\n`;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  writeFileSync(OUTPUT, generate());
  console.log(`wrote ${OUTPUT}`);
}
