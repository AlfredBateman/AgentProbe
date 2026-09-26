"""Shared template-selection helper for the attack generators."""

import random


def pick(rng: random.Random, n_templates: int, count: int) -> list[int]:
    """`count` template indices, cycling through a shuffled order of all `n_templates` so a
    request for more variants than there are templates repeats rather than raising, and the
    same `rng` state always produces the same sequence.
    """
    count = max(1, count)
    order = list(range(n_templates))
    rng.shuffle(order)
    repeats = count // n_templates + 1
    return (order * repeats)[:count]
