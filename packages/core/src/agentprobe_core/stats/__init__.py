"""Statistics (SPEC.md §4.6-4.7, ADR 0006, ADR 0014): per-case pass rates, labels and Wilson
intervals; the suite pass rate with a case-level bootstrap CI; and regression detection
between a baseline and a candidate run.

Thresholds come from `StatisticsConfig` (the suite YAML's `statistics:` block, overridable by
CLI flags through `StatisticsConfig.override`). Known limit: at 5 attempts per case a single
case is only flagged on a large drop (5/5 -> 0/5 or 1/5), and not at all once 13+ cases
are compared; smaller or more widespread drops are caught by the suite-level test.
"""

from agentprobe_core.stats.regression import (
    CaseComparison,
    MetricDelta,
    RegressionReport,
    SuiteComparison,
    Verdict,
    compare_runs,
)
from agentprobe_core.stats.significance import SignFlipResult, fisher_exact, holm, sign_flip_test
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
    "Interval",
    "Label",
    "MetricDelta",
    "RegressionReport",
    "SignFlipResult",
    "SuiteComparison",
    "SuiteStats",
    "Verdict",
    "compare_runs",
    "fisher_exact",
    "holm",
    "sign_flip_test",
    "suite_stats",
    "wilson_interval",
]
