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

import dataclasses
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from anvilkit.health import ChatOutcome


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


def log_path(root: Path, model_id: str, when: datetime) -> Path:
    """Derive the log file path for a stress run, without touching the disk.

    Returns ``root / "logs" / "stress-<safe-model>-<YYYYmmdd-HHMMSS>.log"``.
    The model id is sanitised so it can never leave ``root/logs``: ``/``,
    ``\\``, ``:`` and any whitespace become ``-``, so a HuggingFace-style id
    (``org/sub/model``) and a traversal attempt (``a/../../evil``) both end
    up as a flat file name. Leading/trailing separators collapse so the id
    never contributes a doubled, leading or dangling dash. ``when`` is a
    naive ``datetime`` already in UTC and is rendered directly; reading the
    clock would make the result untestable.
    """
    safe = re.sub(r"[/\\:\s]", "-", model_id).strip("-")
    stamp = when.strftime("%Y%m%d-%H%M%S")
    return root / "logs" / "stress-{}-{}.log".format(safe, stamp)


# Substrings, grouped by category, in the order they must be checked. ``http``
# has no text: it is the fallback for anything carrying a status that no text
# rule claimed first, so it is not a list here -- it is a slot between the
# text rules.
_OOM_SUBSTRINGS = (
    # ``cuda out of memory`` is a superstring of ``out of memory``; the first
    # entry already catches it, but the explicit entry documents the case.
    "out of memory",
    "cuda out of memory",
    "outofmemoryerror",
    "enginedeaderror",
    "enginecore encountered an issue",
    "no available memory",
    "kv cache",
)
_TIMEOUT_SUBSTRINGS = ("timed out",)
_CONNECTION_SUBSTRINGS = (
    "connection refused",
    "connection reset",
    "broken pipe",
)
_PROTOCOL_SUBSTRINGS = (
    "did not return json",
    "non-object payload",
    "malformed",
    "no choices",
)


def classify_error(error: str, http_status: Optional[int]) -> str:
    """Classify a failed request, best-effort, without discarding the raw text.

    Returns one of ``"oom"``, ``"timeout"``, ``"http"``, ``"connection"``,
    ``"protocol"``, ``"unknown"``. Matching is case-insensitive substring,
    evaluated in the order the rules appear here: ``oom``, ``timeout``,
    ``connection``, then ``http`` (any remaining failure that carries an
    ``http_status``), then ``protocol``, then ``unknown``. The order is
    load-bearing: an OOM that arrives as an HTTP 500 must classify as
    ``oom``, not ``http``; a protocol-shaped message that also carries a
    status classifies as ``http`` because ``http`` precedes ``protocol``.

    This is explicitly best-effort. vLLM publishes no stable
    machine-readable OOM identifier -- no reserved ``error.type`` value, no
    dedicated HTTP status, no error code (see
    ``doc/external/vllm/troubleshooting.md``). The substrings below are drawn
    from that page's own transcripts; they are a heuristic, not a
    specification, and a misclassification must be expected. The caller
    therefore keeps the raw error string alongside the category so nothing
    is lost when a guess is wrong.

    Args:
        error: the error text from a failed chat completion.
        http_status: the HTTP status of the failure, if any; ``None`` when
            the request failed without an HTTP response (e.g. the
            connection dropped).

    Returns:
        One of the six category strings. Never raises; ``"unknown"`` is the
        safe default.
    """
    text = error.lower()

    if any(needle in text for needle in _OOM_SUBSTRINGS):
        return "oom"
    if any(needle in text for needle in _TIMEOUT_SUBSTRINGS):
        return "timeout"
    if any(needle in text for needle in _CONNECTION_SUBSTRINGS):
        return "connection"
    if http_status is not None:
        return "http"
    if any(needle in text for needle in _PROTOCOL_SUBSTRINGS):
        return "protocol"
    return "unknown"


@dataclasses.dataclass
class WarmUpResult:
    """The outcome of the warm-up phase, reported but never measured.

    Warm-up exists so the model is loaded before measurement starts; its cost
    is shown to the user but never enters the statistics. On an exhausted
    budget, ``error`` carries the last failure's text verbatim, so the user
    sees *why* the model never came up rather than a bare "gave up".
    """

    ok: bool
    attempts: int
    elapsed_seconds: float
    error: Optional[str]


def warm_up(
    send: Callable[[], "ChatOutcome"],
    timeout: float,
    retry_interval: float,
    sleep: Callable[[float], None],
    now: Callable[[], float],
) -> "WarmUpResult":
    """Retry a cold model until it answers, and report the outcome.

    ``send`` is called, and while it keeps failing, ``sleep(retry_interval)``
    is called exactly once between each pair of attempts and another attempt
    is made. The first success ends the loop with ``ok=True`` and
    ``error=None`` and no trailing sleep; a failure never raises, it only
    queues another attempt (giving up on an exhausted budget is a later
    behaviour). ``attempts`` counts every ``send`` call and
    ``elapsed_seconds`` is the full wall-clock span from the start of the
    first attempt to the end of the last, measured by the injected clock.

    ``sleep`` and ``now`` are injected rather than read from the process,
    which is what lets the elapsed time be exercised by an instant test.

    Args:
        send: one chat completion; returns an outcome, never raises.
        timeout: the total warm-up budget, in seconds (used by later
            behaviours; accepted here for signature stability).
        retry_interval: the wall-clock pause between attempts, in seconds.
        sleep: the injected sleep.
        now: the injected monotonic clock.

    Returns:
        A ``WarmUpResult``. Never raises; an intermediate failure is a
        queued attempt, not an error.
    """
    start = now()
    attempts = 0
    while True:
        attempts += 1
        outcome = send()
        if outcome.ok:
            return WarmUpResult(
                ok=True,
                attempts=attempts,
                elapsed_seconds=now() - start,
                error=None,
            )
        sleep(retry_interval)
