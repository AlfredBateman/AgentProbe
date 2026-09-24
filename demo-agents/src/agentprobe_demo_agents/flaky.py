"""Seeded, reproducible flakiness for one support-bot behavior (order lookup).

`FLAKY_RATE`/`FLAKY_SEED` come from the environment. `reset()` restarts the sequence from a
given seed, so tests can assert exact flaky/non-flaky outcomes instead of a real intermittent
bug that can't be pinned down.
"""

import os
import random

FLAKY_RATE = float(os.environ.get("FLAKY_RATE", "0.2"))
FLAKY_SEED = int(os.environ.get("FLAKY_SEED", "1337"))

_rng = random.Random(FLAKY_SEED)


def reset(seed: int = FLAKY_SEED) -> None:
    global _rng
    _rng = random.Random(seed)


def roll(rate: float | None = None) -> bool:
    return _rng.random() < (FLAKY_RATE if rate is None else rate)
