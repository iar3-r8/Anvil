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

import concurrent.futures
import dataclasses
import json
import math
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from anvilkit.health import ChatOutcome, GatewayStatus

# The fixed prompt every stress request carries. Trivially cheap to answer, so
# the measurement is the gateway's plumbing under load, not the model's
# creativity.
DEFAULT_PROMPT = "Reply with the single word: pong"


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
    ``error=None`` and no trailing sleep. ``attempts`` counts every ``send``
    call and ``elapsed_seconds`` is the full wall-clock span from the start
    of the first attempt to the end of the last, measured by the injected
    clock.

    An attempt may start only while the elapsed time is strictly less than
    the ``timeout`` budget. The first attempt is never gated by the budget,
    so at least one attempt is always made even with ``timeout == 0.0``;
    only the start of the *next* attempt is what the budget decides, and
    since that start is one ``retry_interval`` past the last failure, the
    decision can be made before sleeping -- which is also what keeps the
    trailing sleep off the final failed attempt. On an exhausted budget the
    result is returned, never raised, with the last failure's error text
    verbatim so the caller can tell the user why the model never came up.

    ``sleep`` and ``now`` are injected rather than read from the process,
    which is what lets the elapsed time be exercised by an instant test.

    Args:
        send: one chat completion; returns an outcome, never raises.
        timeout: the total warm-up budget, in seconds.
        retry_interval: the wall-clock pause between attempts, in seconds.
        sleep: the injected sleep.
        now: the injected monotonic clock.

    Returns:
        A ``WarmUpResult``. Never raises; an intermediate failure within the
        budget is a queued attempt, not an error.
    """
    start = now()
    attempts = 0
    last_error: Optional[str] = None
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
        last_error = outcome.error
        # The next attempt would start one interval past this failure; an
        # attempt may start only while elapsed is strictly less than the
        # budget, so refuse to sleep -- and therefore to start it -- when
        # the start would land at or past the budget.
        if now() - start + retry_interval >= timeout:
            return WarmUpResult(
                ok=False,
                attempts=attempts,
                elapsed_seconds=now() - start,
                error=last_error,
            )
        sleep(retry_interval)


@dataclasses.dataclass
class ModelAvailability:
    """The verdict on whether a named model can be stressed right now.

    Three verdicts, not a bool, because the two failures are different
    problems for the caller: ``unknown_model`` is the user's typo and is
    answerable by listing the registry, while ``unreachable`` is the
    gateway's fault and is reported with the gateway's own error text
    verbatim. ``available`` is the registered ids, ascending, so the
    caller can offer corrections; it is empty when the ids are not
    known.
    """

    verdict: str
    available: List[str]
    reason: Optional[str]


def check_model_available(
    gateway: GatewayStatus, model_id: str
) -> ModelAvailability:
    """Decide whether ``model_id`` can be stressed, over an already-fetched status.

    A pure decision: no I/O, no network, never raises. The caller does the
    probing and hands in the result. The verdict rules are evaluated in
    order, and the order is load-bearing -- a set ``registry_error``
    outranks membership, because when the ``/v1/models`` payload was
    unusable, ``check_gateway`` returns an empty ``models`` list, and the
    naive reading (empty registry, therefore the user's typo) would blame
    the user for the gateway's malformed payload. The remaining two cases
    only differ in whether ``model_id`` is an exact member of the
    registered ids -- prefix and suffix never match -- and in which of
    them the ids are reported; a genuinely empty registry is
    ``unknown_model`` with no ids, not ``unreachable``.

    Args:
        gateway: the probe outcome, as returned by
            ``health.check_gateway()``.
        model_id: the model id the user named.

    Returns:
        A ``ModelAvailability``. ``reason`` carries the gateway's own
        error text verbatim on ``unreachable`` and is ``None`` otherwise.
    """
    if not gateway.online:
        return ModelAvailability(
            verdict="unreachable", available=[], reason=gateway.error
        )
    if gateway.registry_error is not None:
        # Outranks membership: see the docstring -- an empty ``models``
        # list caused by an unusable payload is not a typo.
        return ModelAvailability(
            verdict="unreachable", available=[], reason=gateway.registry_error
        )
    available = sorted(model.id for model in gateway.models)
    if model_id in available:
        return ModelAvailability(verdict="ok", available=available, reason=None)
    return ModelAvailability(
        verdict="unknown_model", available=available, reason=None
    )


def run_level(
    send: Callable[[], ChatOutcome],
    concurrency: int,
    request_count: int,
) -> List[ChatOutcome]:
    """Run one concurrency level and return every request's outcome.

    Dispatches ``request_count`` calls to ``send`` through a
    ``ThreadPoolExecutor(max_workers=concurrency)``, so at most
    ``concurrency`` are in flight at once -- concurrency 1 is genuinely
    serial. The pool is sized to ``concurrency`` even when
    ``concurrency > request_count``; only ``request_count`` requests are
    submitted, so the level returns exactly ``request_count`` outcomes.

    A ``send`` that raises is caught and converted into a failed outcome
    (``ok=False`` with a non-empty ``error``), so one raising thread never
    aborts the level and the full count is still returned. Results are
    returned in submission order: ``executor.map`` over the request
    indices, which is deterministic and keeps the Nth result paired with
    the Nth submitted request. The executor is used as a context manager
    so it is always shut down.
    """

    def _one(_index: int) -> ChatOutcome:
        try:
            return send()
        except Exception as exc:
            return ChatOutcome(
                ok=False,
                latency_seconds=0.0,
                error="send raised: {}: {}".format(type(exc).__name__, exc),
            )

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=concurrency
    ) as executor:
        return list(executor.map(_one, range(request_count)))


# ``errors`` shows the actual raw messages, but a level can fail hundreds of
# times with the same text, so distinct messages are capped -- the *counts*
# are never capped.
_MAX_SHOWN_ERRORS = 5


@dataclasses.dataclass
class LevelSummary:
    """The aggregated statistics of one concurrency level.

    Every latency figure is drawn from successful outcomes only: a request
    that fails quickly because the worker died would otherwise drag the mean
    down and make an overloaded configuration look faster than a healthy
    one. ``None`` means "not measurable" -- a level with no successes has no
    latencies, and a zero wall time makes the rates undefined -- never a
    fabricated ``0.0``. An all-failed level reports ``0.0`` for both rates
    instead, which is a true statement (nothing got through), distinct from
    "unmeasurable".
    """

    concurrency: int
    requests: int
    succeeded: int
    failed: int
    latency_mean: Optional[float]
    latency_p50: Optional[float]
    latency_p95: Optional[float]
    latency_p99: Optional[float]
    latency_min: Optional[float]
    latency_max: Optional[float]
    requests_per_second: Optional[float]
    tokens_per_second: Optional[float]
    error_counts: Dict[str, int]
    errors: List[str]


def summarise_level(
    level: int, outcomes: List[ChatOutcome], wall_seconds: float
) -> LevelSummary:
    """Aggregate one level's outcomes into its statistics.

    A pure aggregation over data already collected: no I/O, never raises.
    Latency figures come from successful outcomes only (see
    :class:`LevelSummary`); the rates use the level's wall-clock duration;
    ``error_counts`` buckets the failures via :func:`classify_error`, and
    ``errors`` keeps the distinct raw error strings, first-seen order,
    capped at the first five so the report shows real messages without
    growing without bound.

    Args:
        level: the concurrency of this level.
        outcomes: every request's outcome, in submission order.
        wall_seconds: the wall-clock duration of the level.

    Returns:
        A ``LevelSummary``.
    """
    successful = [o for o in outcomes if o.ok]
    failed = [o for o in outcomes if not o.ok]
    succeeded = len(successful)

    latencies = [o.latency_seconds for o in successful]
    if latencies:
        latency_mean = sum(latencies) / len(latencies)
        latency_p50 = percentile(latencies, 50)
        latency_p95 = percentile(latencies, 95)
        latency_p99 = percentile(latencies, 99)
        latency_min = min(latencies)
        latency_max = max(latencies)
    else:
        latency_mean = latency_p50 = latency_p95 = None
        latency_p99 = latency_min = latency_max = None

    if succeeded == 0:
        # Nothing got through: 0.0 is a true statement, and it sidesteps
        # 0/0 when the wall time is also zero.
        requests_per_second: Optional[float] = 0.0
        tokens_per_second: Optional[float] = 0.0
    else:
        requests_per_second = (
            succeeded / wall_seconds if wall_seconds > 0 else None
        )
        # ``None`` completion tokens mean "no usage reported", which is
        # distinct from a genuine 0, so only counts that were reported are
        # summed. No successful outcome reporting usage makes the
        # throughput unmeasurable, not zero.
        reported = [
            o.completion_tokens
            for o in successful
            if o.completion_tokens is not None
        ]
        if not reported:
            tokens_per_second = None
        else:
            tokens_per_second = (
                sum(reported) / wall_seconds if wall_seconds > 0 else None
            )

    error_counts: Dict[str, int] = {}
    errors: List[str] = []
    for outcome in failed:
        # ``error`` is Optional on ChatOutcome; a failed outcome in
        # practice always carries text, and "" classifies as "unknown".
        category = classify_error(outcome.error or "", outcome.http_status)
        error_counts[category] = error_counts.get(category, 0) + 1
        raw = outcome.error or ""
        # Only the *shown* messages are capped; the counting above runs
        # over every failure regardless.
        if len(errors) < _MAX_SHOWN_ERRORS and raw and raw not in errors:
            errors.append(raw)

    return LevelSummary(
        concurrency=level,
        requests=len(outcomes),
        succeeded=succeeded,
        failed=len(failed),
        latency_mean=latency_mean,
        latency_p50=latency_p50,
        latency_p95=latency_p95,
        latency_p99=latency_p99,
        latency_min=latency_min,
        latency_max=latency_max,
        requests_per_second=requests_per_second,
        tokens_per_second=tokens_per_second,
        error_counts=error_counts,
        errors=errors,
    )


@dataclasses.dataclass
class StressReport:
    """The outcome of a whole stress run, one level summary per level.

    ``warm_up`` is the exact ``WarmUpResult`` the run was handed, so its cost
    is reported but never mixed into the per-level statistics. ``completed``
    means the run reached the end of the level list; it is ``True`` even when
    a level (or every level) failed, because a run that finished is one whose
    findings -- including "dies at 4" -- can be read. A propagated
    ``KeyboardInterrupt`` is the only way the run does not complete.

    The metadata fields (``started_at``, ``prompt``, ``max_tokens``,
    ``requests_per_level``, ``max_clean_concurrency``) are appended with
    defaults so the run's own construction -- which knows none of them --
    stays untouched: the CLI stamps them in once it has the values.
    ``max_clean_concurrency`` is the highest concurrency that completed with
    zero failures, ``None`` when even level 1 failed.
    """

    model_id: str
    port: int
    warm_up: WarmUpResult
    levels: List[LevelSummary]
    completed: bool
    started_at: str = ""
    prompt: str = ""
    max_tokens: int = 0
    requests_per_level: int = 0
    max_clean_concurrency: Optional[int] = None


def run_stress(
    send: Callable[[], ChatOutcome],
    levels: Sequence[int],
    request_count: int,
    warm_up_result: WarmUpResult,
    model_id: str,
    port: int,
) -> StressReport:
    """Assemble the whole run: every level, in ascending order, no early stop.

    Each level runs via :func:`run_level` with its wall time measured by
    ``time.monotonic`` and aggregated via :func:`summarise_level`; the report
    carries one ``LevelSummary`` per input level, in the order the levels ran.

    A level that fails completely is *recorded*, not a reason to stop: the
    run continues so the report reads as the full progression. Only a
    ``KeyboardInterrupt`` abandons the run, and it is deliberately not
    caught, so a long run can be interrupted and the CLI maps it to its
    own exit code.

    Args:
        send: one chat completion; may return a failed outcome or raise
            (``run_level`` converts a raise into a failed outcome).
        levels: the concurrency levels, in ascending order.
        request_count: how many requests each level issues.
        warm_up_result: the warm-up phase's outcome, carried through
            unchanged.
        model_id: the model id being stressed, for the report header.
        port: the gateway port, for the report header.

    Returns:
        A ``StressReport`` with ``completed=True``, because reaching the end
        of the level list is completion even when a level failed.
    """
    summaries: List[LevelSummary] = []
    for level in levels:
        start = time.monotonic()
        outcomes = run_level(send, level, request_count)
        wall = time.monotonic() - start
        summaries.append(summarise_level(level, outcomes, wall))
    return StressReport(
        model_id=model_id,
        port=port,
        warm_up=warm_up_result,
        levels=summaries,
        completed=True,
    )


# ANSI codes, mirroring ``anvilkit.health``'s convention; applied only while
# ``use_color`` is set, so colourless output stays byte-identical to the
# plain text.
_GREEN = "\033[32m"
_RED = "\033[31m"
_RESET = "\033[0m"


def _paint(text: str, code: str, use_color: bool) -> str:
    """Wrap ``text`` in ``code``/reset, or return it untouched.

    The single seam that keeps ``use_color=False`` free of every escape:
    every coloured fragment in the report goes through here.
    """
    if not use_color:
        return text
    return "{}{}{}".format(code, text, _RESET)


def _fmt_figure(value: Optional[float]) -> str:
    """One numeric table cell: ``-`` when unmeasurable, two decimals otherwise.

    ``None`` means "not measurable" (no successes, no wall time) and must
    never be rendered as a fabricated ``0.00``; a genuine ``0.0`` (an
    all-failed level's true zero rate) renders as ``0.00``.
    """
    if value is None:
        return "-"
    return "{:.2f}".format(value)


def _format_warm_up_line(warm_up: WarmUpResult, use_color: bool) -> str:
    if warm_up.ok:
        text = "Warm-up: ok after {} attempt(s), {:.1f}s".format(
            warm_up.attempts, warm_up.elapsed_seconds
        )
        return _paint(text, _GREEN, use_color)
    # The failure's error text goes in verbatim: it is the *why* the model
    # never came up, and paraphrasing would lose it.
    text = "Warm-up: FAILED after {} attempt(s), {:.1f}s: {}".format(
        warm_up.attempts, warm_up.elapsed_seconds, warm_up.error or ""
    )
    return _paint(text, _RED, use_color)


def _format_level_failures(level: LevelSummary) -> List[str]:
    """The failure block beneath a level that had failures.

    Categories with their counts (insertion order, i.e. first-seen), then
    the distinct raw messages. The block is indented under its row and the
    level is named "level N", never "concurrency N", so the closing
    summary's "highest clean concurrency" reading stays unambiguous.
    """
    lines = ["  Failures at level {}:".format(level.concurrency)]
    for category, count in level.error_counts.items():
        lines.append("    {}: {}".format(category, count))
    for message in level.errors:
        lines.append("    - {}".format(message))
    return lines


def _format_level_table(
    levels: Sequence[LevelSummary], use_color: bool
) -> List[str]:
    lines: List[str] = []
    labels = (
        "concurrency",
        "ok/fail",
        "mean",
        "p50",
        "p95",
        "p99",
        "req/s",
        "tok/s",
    )
    figure_fields = (
        "latency_mean",
        "latency_p50",
        "latency_p95",
        "latency_p99",
        "requests_per_second",
        "tokens_per_second",
    )

    rows: List[List[str]] = []
    for level in levels:
        cells = [str(level.concurrency),
                 "{}/{}".format(level.succeeded, level.failed)]
        for name in figure_fields:
            cells.append(_fmt_figure(getattr(level, name)))
        rows.append(cells)

    # Column widths from the widest cell, header labels included: the
    # ok/fail column therefore starts at the same offset in every row no
    # matter how long the figures grow (the model id lives in the header
    # and can never enter a row).
    widths = [len(label) for label in labels]
    for row in rows:
        for index, cell in enumerate(row):
            if len(cell) > widths[index]:
                widths[index] = len(cell)

    def render(cells: List[str], is_header: bool) -> str:
        parts = [cell.rjust(widths[index]) for index, cell in enumerate(cells)]
        if not is_header:
            # Colour the ok/fail cell: green when the level had no failures.
            parts[1] = _paint(
                parts[1],
                _GREEN if parts[1].strip().split("/")[-1] == "0" else _RED,
                use_color,
            )
        return " | ".join(parts)

    lines.append(render(list(labels), True))
    for level, row in zip(levels, rows):
        lines.append(render(row, False))
        if level.failed:
            lines.extend(_format_level_failures(level))
    return lines


def _format_closing_line(
    max_clean_concurrency: Optional[int], use_color: bool
) -> str:
    if max_clean_concurrency is not None:
        text = "Highest clean concurrency: {}".format(
            max_clean_concurrency
        )
        return _paint(text, _GREEN, use_color)
    return _paint(
        "No clean concurrency (every level failed)", _RED, use_color
    )


def format_report(report: StressReport, use_color: bool = True) -> str:
    """Render a finished ``StressReport`` as human-readable text.

    Pure rendering: never raises, never reads the clock (the timestamp
    shown is the report's own ``started_at``, stamped when the run began,
    so the text is identical however late it is printed) and emits no
    ANSI escapes at all when ``use_color`` is false, matching
    ``health.format_status``. An empty level list, a failed warm-up and
    all-``None`` figures all render, because each is a finding, not an
    error.
    """
    lines: List[str] = []
    lines.append("Stress test: {}".format(report.model_id))
    lines.append("Port: {}".format(report.port))
    if report.started_at:
        lines.append("Started: {}".format(report.started_at))
    lines.append("Requests per level: {}".format(report.requests_per_level))
    lines.append(_format_warm_up_line(report.warm_up, use_color))

    if report.levels:
        lines.extend(_format_level_table(report.levels, use_color))
    else:
        lines.append("No levels ran.")

    lines.append(_format_closing_line(report.max_clean_concurrency, use_color))
    return "\n".join(lines)


def format_report_json(report: StressReport) -> str:
    """Render a finished ``StressReport`` as a machine-readable JSON document.

    The document is built as a ``dict`` and emitted with ``json.dumps`` --
    never by string substitution -- so the output is valid JSON by
    construction and round-trips through ``json.loads``. The key names follow
    the plan's JSON block, which differs from the dataclass in two places:
    ``model_id`` is serialised as ``"model"``, and the six flat
    ``latency_*`` fields nest under ``"latency"``.

    ``None`` figures stay ``None`` so they serialise as JSON ``null`` -- the
    text report maps them to ``-``, but a machine reader must be able to tell
    "not measurable" apart from a genuine ``0``.

    Pure rendering: never raises.
    """
    return json.dumps(
        {
            "model": report.model_id,
            "port": report.port,
            "started_at": report.started_at,
            "prompt": report.prompt,
            "max_tokens": report.max_tokens,
            "requests_per_level": report.requests_per_level,
            "warm_up": {
                "ok": report.warm_up.ok,
                "attempts": report.warm_up.attempts,
                "elapsed_seconds": report.warm_up.elapsed_seconds,
                "error": report.warm_up.error,
            },
            "levels": [
                {
                    "concurrency": level.concurrency,
                    "requests": level.requests,
                    "succeeded": level.succeeded,
                    "failed": level.failed,
                    "latency": {
                        "mean": level.latency_mean,
                        "p50": level.latency_p50,
                        "p95": level.latency_p95,
                        "p99": level.latency_p99,
                        "min": level.latency_min,
                        "max": level.latency_max,
                    },
                    "requests_per_second": level.requests_per_second,
                    "tokens_per_second": level.tokens_per_second,
                    "error_counts": level.error_counts,
                    "errors": level.errors,
                }
                for level in report.levels
            ],
            "completed": report.completed,
            "max_clean_concurrency": report.max_clean_concurrency,
        },
        indent=2,
    )


def write_log(path: Path, text_report: str, json_report: str) -> None:
    """Persist a finished run's report to ``path``; the log's only job.

    One artefact, two destinations: the terminal already showed ``text_report``
    and ``json_report``, so the log carries the same two, verbatim -- the text
    report, then a separator line, then the JSON block. Re-rendering or
    trimming here would make the log disagree with what the user just read,
    which is worse than useless. The file therefore ends exactly with
    ``json_report``, so a machine reader can take the block from the text to
    the end of the file.

    The parent directory is created if absent, at any depth under the run
    root, and an existing file is overwritten: the derived path carries a
    second-resolution timestamp, so a collision means the same path was
    deliberately reused, and the new report must be the whole file.

    Args:
        path: the target file, e.g. as derived by :func:`log_path`.
        text_report: the human-readable report, written verbatim.
        json_report: the machine-readable report, written verbatim.

    Raises:
        StressError: the directory could not be created or the file could not
            be written; the message names ``path`` so the caller can point
            the user at the artefact that was not produced.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            text_report + "\n" + ("=" * 70) + "\n" + json_report,
            encoding="utf-8",
        )
    except OSError as exc:
        raise StressError("could not write log {}: {}".format(path, exc))
