"""Statistics (SPEC.md §4.6-4.7, ADR 0006, ADR 0014): per-case pass rates, labels and Wilson
intervals; the suite pass rate with a case-level bootstrap CI; and regression detection
between a baseline and a candidate run.

Thresholds come from `StatisticsConfig` (the suite YAML's `statistics:` block, overridable by
CLI flags through `StatisticsConfig.override`). Per-case tests are one-sided Fisher exact
tests with a Tarone-Holm step-down, so unchanged deterministic cases don't dilute the
correction: one case going 5/5 -> 0/5 is flagged at any suite size. Known limit: a case
that only turns flaky (5/5 -> 3/5) is weak evidence at 5 attempts; more attempts per case,
or several cases moving together (the suite-level test), are what catch it.
"""

from agentprobe_core.stats.regression import (
    CaseComparison,
    MetricDelta,
    RegressionReport,
    SuiteComparison,
    Verdict,
    compare_cases,
    compare_runs,
)
from agentprobe_core.stats.significance import (
    FisherResult,
    SignFlipResult,
    StepDownDecision,
    fisher_exact,
    sign_flip_test,
    tarone_holm,
)
from agentprobe_core.stats.summary import (
    DEFAULT_CONFIDENCE,
    DEFAULT_SEED,
    CaseSummary,
    Interval,
    Label,
    SuiteStats,
    suite_stats,
    wilson_interval,
)

__all__ = [
    "DEFAULT_CONFIDENCE",
    "DEFAULT_SEED",
    "CaseComparison",
    "CaseSummary",
    "FisherResult",
    "Interval",
    "Label",
    "MetricDelta",
    "RegressionReport",
    "SignFlipResult",
    "StepDownDecision",
    "SuiteComparison",
    "SuiteStats",
    "Verdict",
    "compare_cases",
    "compare_runs",
    "fisher_exact",
    "sign_flip_test",
    "suite_stats",
    "tarone_holm",
    "wilson_interval",
]
