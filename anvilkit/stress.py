"""Stress testing against the llama-swap gateway.

The gateway is registered-and-loaded by design: nothing about the registry says
whether a model can actually sustain concurrent load. This module answers that
with a controlled ramp of chat completions.

It derives the concurrency ramp from a single maximum instead of a hand-listed
sequence, so the caller states one intent ("up to N in parallel") and the
levels are the doubling series that makes each level a step up from the
previous. Later behaviours add percentiles, warm-up, execution and reporting
here; this module never prompts, never reads configuration and never calls
``sys.exit()`` -- those stay with the CLI.
"""

import math
from typing import List, Sequence


class StressError(Exception):
    """Any failure of a stress run.

    A single exception type covers invalid input, a request failure and a
    report-writing failure, so callers need only one ``except`` clause.
    """


def concurrency_levels(max_concurrency: int) -> List[int]:
    """Derive the concurrency ramp from a single maximum.

    The series is 1, then each power of two up to the maximum, then the
    maximum itself if it is not already a power of two. Ascending, no
    duplicates: a power-of-two maximum appears exactly once, and a
    non-power-of-two maximum is always the final level.

    Args:
        max_concurrency: the largest concurrency to test; must be >= 1.

    Raises:
        StressError: ``max_concurrency`` is less than 1.
    """
    if max_concurrency < 1:
        raise StressError(
            "max_concurrency must be >= 1, got {}".format(max_concurrency)
        )

    levels = []
    level = 1
    while level <= max_concurrency:
        levels.append(level)
        level *= 2
    if levels[-1] != max_concurrency:
        levels.append(max_concurrency)
    return levels


def percentile(values: Sequence[float], p: float) -> float:
    """Return the nearest-rank percentile of ``values`` for ``p`` (0-100).

    Sorts ascending and takes the element at index ``ceil(p / 100 * n) - 1``,
    clamped to ``[0, n - 1]`` so ``p == 0`` yields the minimum and
    ``p == 100`` the maximum. Nearest-rank rather than interpolation is
    deliberate: every reported figure is a latency that actually occurred,
    which is what someone sizing hardware needs.

    Args:
        values: the latencies, in any order; must not be empty.
        p: the percentile, 0-100.

    Raises:
        StressError: ``values`` is empty.
    """
    if not values:
        raise StressError("values must not be empty")

    ordered = sorted(values)
    # The clamp handles p == 0 (rank 0 would index -1) and any rounding that
    # pushes the rank past the last element.
    rank = math.ceil(p / 100 * len(ordered)) - 1
    index = max(0, min(len(ordered) - 1, rank))
    return ordered[index]
