"""Tests for anvilkit.stress.

Written before the implementation (TDD).

Current scope: behaviours 1-3 and 6-11 of plans/stress-test.md --
``concurrency_levels(max_concurrency)`` derives the level series from a single
maximum: 1, then each power of two up to the maximum, then the maximum itself
if it is not already a power of two; ``percentile(values, p)`` is the
nearest-rank percentile (no interpolation): sort ascending, take index
``ceil(p/100 * n) - 1`` clamped to ``[0, n-1]``; ``log_path(root, model_id,
when)`` derives the log file name under ``root/logs`` from a sanitised model
id and an injected UTC timestamp; ``classify_error`` buckets a failure's
text, best-effort; ``warm_up(send, timeout, retry_interval, sleep, now)``
returns ``WarmUpResult(ok=True, attempts=1, elapsed_seconds=<measured>,
error=None)`` when ``send`` answers on the very first call -- ``send`` runs
exactly once and ``sleep`` never runs -- and gives up when the budget is
exhausted: a ``send`` that always fails ends in
``WarmUpResult(ok=False, attempts=<n>, elapsed_seconds≈budget,
error=<last failure verbatim>)``, makes at least one attempt even with a
zero budget, and never starts an attempt once the elapsed time has reached
the budget; ``check_model_available(gateway, model_id)`` is a pure verdict
over an already-fetched ``GatewayStatus`` (no I/O, no network) returning a
``ModelAvailability(verdict, available, reason)`` -- an offline gateway, or
an online gateway whose ``registry_error`` is set, is ``unreachable`` with
the gateway's own error text verbatim as ``reason``; a named model that is
an exact member of the registered ids is ``ok`` with ``reason=None``;
otherwise it is ``unknown_model`` with ``available`` set to the registered
ids (ascending); ``run_level(send, concurrency, request_count)``
dispatches ``request_count`` requests through a pool bounded to
``concurrency`` workers and returns exactly ``request_count``
``ChatOutcome``s -- at most ``concurrency`` are in flight at once,
concurrency 1 is genuinely serial, and a ``send`` that raises is caught
and converted into a failed outcome rather than aborting the level;
``summarise_level(level, outcomes, wall_seconds)`` aggregates one level's
outcomes into a ``LevelSummary`` -- latency figures are computed from
successful outcomes only, ``requests_per_second`` is ``succeeded /
wall_seconds`` and ``tokens_per_second`` the total completion tokens over
the wall time, ``error_counts`` buckets the failed outcomes via
``classify_error`` (a clean level has an empty mapping) and ``errors``
carries the distinct raw error strings in first-seen order, capped at five;
a level where every request failed reports ``None`` for all latency figures
and ``0.0`` for both rates, and a zero wall time with successes yields
``None`` rates rather than an exception.

Behaviours 14 (``format_report``), 15 (``format_report_json``) and
16 (``write_log``) are covered below. Behaviours 4 and 5 land in this
same file in later cycles.

The module is a pure-function module for these behaviours: no network, no
real clock, no I/O. The warm-up tests inject ``send``, ``sleep`` and the
clock as spies and fakes, and the level tests inject ``send`` as a
thread-safe spy; assertions are on returned data structures only.
"""

import dataclasses
import json
import sys
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock, TestCase

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import stress  # noqa: E402
from anvilkit.health import ChatOutcome, GatewayStatus, ModelStatus  # noqa: E402
from anvilkit.stress import (  # noqa: E402
    classify_error,
    log_path,
    percentile,
    warm_up,
)

# Behaviour 10 (TDD red): these do not exist yet, so the import is guarded.
# The new test classes turn the missing import into a clear, named failure
# instead of an import-time crash that would error every test in this module.
_check_model_available_import_error = None
try:  # noqa: E402
    from anvilkit.stress import (
        ModelAvailability,
        check_model_available,
    )
except ImportError as _err:
    # ``except ... as`` deletes the exception variable when the block ends,
    # so the message is copied out into a module-level name first.
    _check_model_available_import_error = str(_err)
    ModelAvailability = None
    check_model_available = None

# Behaviour 11 (TDD red): this does not exist yet, so the import is guarded.
# The new test classes turn the missing import into a clear, named failure
# instead of an import-time crash that would error every test in this module.
_run_level_import_error = None
try:  # noqa: E402
    from anvilkit.stress import run_level
except ImportError as _err:
    _run_level_import_error = str(_err)
    run_level = None

# Behaviour 12 (TDD red): these do not exist yet, so the import is guarded.
# The new test classes turn the missing import into a clear, named failure
# instead of an import-time crash that would error every test in this module.
_summarise_level_import_error = None
try:  # noqa: E402
    from anvilkit.stress import (  # noqa: E402
        LevelSummary,
        summarise_level,
    )
except ImportError as _err:
    # ``except ... as`` deletes the exception variable when the block ends,
    # so the message is copied out into a module-level name first.
    _summarise_level_import_error = str(_err)
    LevelSummary = None
    summarise_level = None

# Behaviour 13 (TDD red): these do not exist yet, so the import is guarded.
# The new test classes turn the missing import into a clear, named failure
# instead of an import-time crash that would error every test in this module.
_run_stress_import_error = None
try:  # noqa: E402
    from anvilkit.stress import (  # noqa: E402
        StressReport,
        run_stress,
    )
except ImportError as _err:
    # ``except ... as`` deletes the exception variable when the block ends,
    # so the message is copied out into a module-level name first.
    _run_stress_import_error = str(_err)
    StressReport = None
    run_stress = None

# Behaviour 14 (TDD red): this does not exist yet, so the import is guarded.
# The new test classes turn the missing import into a clear, named failure
# instead of an import-time crash that would error every test in this module.
_format_report_import_error = None
try:  # noqa: E402
    from anvilkit.stress import format_report
except ImportError as _err:
    # ``except ... as`` deletes the exception variable when the block ends,
    # so the message is copied out into a module-level name first.
    _format_report_import_error = str(_err)
    format_report = None

# Behaviour 15 (TDD red): this does not exist yet, so the import is guarded.
# The new test classes turn the missing import into a clear, named failure
# instead of an import-time crash that would error every test in this module.
_format_report_json_import_error = None
try:  # noqa: E402
    from anvilkit.stress import format_report_json
except ImportError as _err:
    # ``except ... as`` deletes the exception variable when the block ends,
    # so the message is copied out into a module-level name first.
    _format_report_json_import_error = str(_err)
    format_report_json = None

# Behaviour 16 (TDD red): this does not exist yet, so the import is guarded.
# The new test classes turn the missing import into a clear, named failure
# instead of an import-time crash that would error every test in this module.
_write_log_import_error = None
try:  # noqa: E402
    from anvilkit.stress import write_log
except ImportError as _err:
    # ``except ... as`` deletes the exception variable when the block ends,
    # so the message is copied out into a module-level name first.
    _write_log_import_error = str(_err)
    write_log = None


class TestConcurrencyLevelsTable(unittest.TestCase):
    """The level series for a given maximum, straight from the plan's table."""

    def test_power_of_two_maximum_yields_doubling_series(self):
        cases = [
            (1, [1]),
            (2, [1, 2]),
            (4, [1, 2, 4]),
            (8, [1, 2, 4, 8]),
            (16, [1, 2, 4, 8, 16]),
        ]
        for maximum, expected in cases:
            with self.subTest(maximum=maximum):
                self.assertEqual(stress.concurrency_levels(maximum), expected)

    def test_non_power_of_two_maximum_yields_series_plus_ceiling(self):
        cases = [
            (3, [1, 2, 3]),
            (5, [1, 2, 4, 5]),
            (10, [1, 2, 4, 8, 10]),
            (12, [1, 2, 4, 8, 12]),
        ]
        for maximum, expected in cases:
            with self.subTest(maximum=maximum):
                self.assertEqual(stress.concurrency_levels(maximum), expected)


class TestConcurrencyLevelsEdges(unittest.TestCase):
    """Edge cases called out in behaviour 1 of the plan."""

    def test_maximum_of_one_yields_single_level_not_empty(self):
        self.assertEqual(stress.concurrency_levels(1), [1])

    def test_levels_are_strictly_ascending_without_duplicates(self):
        for maximum in (1, 2, 3, 4, 5, 8, 10, 12, 16):
            with self.subTest(maximum=maximum):
                levels = stress.concurrency_levels(maximum)
                self.assertEqual(levels, sorted(set(levels)))
                self.assertGreater(len(levels), 0)

    def test_non_power_of_two_maximum_is_always_final_level(self):
        for maximum in (3, 5, 10, 12):
            with self.subTest(maximum=maximum):
                self.assertEqual(stress.concurrency_levels(maximum)[-1], maximum)

    def test_power_of_two_maximum_appears_exactly_once(self):
        self.assertEqual(stress.concurrency_levels(16).count(16), 1)


class TestConcurrencyLevelsErrors(unittest.TestCase):
    """Error behaviour: max_concurrency < 1 raises StressError naming the value."""

    def test_maximum_below_one_raises_stress_error_naming_value(self):
        for bad in (0, -1):
            with self.subTest(maximum=bad):
                with self.assertRaises(stress.StressError) as ctx:
                    stress.concurrency_levels(bad)
                self.assertIn(str(bad), str(ctx.exception))


class TestPercentileTable(unittest.TestCase):
    """The percentile values straight from behaviour 2's table in the plan."""

    def test_plan_table_values(self):
        cases = [
            (list(range(1, 11)), 50, 5),
            (list(range(1, 11)), 95, 10),
            (list(range(1, 11)), 99, 10),
            ([5], 99, 5),
            ([3, 1, 2], 50, 2),
        ]
        for values, p, expected in cases:
            with self.subTest(values=values, p=p):
                self.assertEqual(percentile(values, p), expected)

    def test_input_order_does_not_change_result(self):
        for values in ([3, 1, 2], [1, 2, 3], [2, 3, 1]):
            with self.subTest(values=values):
                self.assertEqual(percentile(values, 50), 2)

    def test_result_is_always_a_value_that_occurred(self):
        # Nearest-rank, not interpolation: every reported figure is a
        # latency that actually occurred.
        for values in ([1, 2, 3], [7.5, 3.25, 9.0, 1.1], [4, 4, 2, 9]):
            for p in (0, 25, 50, 75, 95, 99, 100):
                with self.subTest(values=values, p=p):
                    self.assertIn(percentile(values, p), values)


class TestPercentileEdges(unittest.TestCase):
    """Edge cases called out in behaviour 2 of the plan."""

    def test_single_value_returns_itself_for_every_percentile(self):
        for p in (0, 1, 25, 50, 75, 95, 99, 100):
            with self.subTest(p=p):
                self.assertEqual(percentile([5], p), 5)

    def test_p_zero_returns_minimum(self):
        for values in ([1, 2, 3], [3, 1, 2], [4.25]):
            with self.subTest(values=values):
                self.assertEqual(percentile(values, 0), min(values))

    def test_p_100_returns_maximum(self):
        for values in ([1, 2, 3], [3, 1, 2], [9.5]):
            with self.subTest(values=values):
                self.assertEqual(percentile(values, 100), max(values))


class TestPercentileErrors(unittest.TestCase):
    """Error behaviour: an empty sequence raises StressError."""

    def test_empty_sequence_raises_stress_error(self):
        with self.assertRaises(stress.StressError):
            percentile([], 50)


class TestLogPathTable(unittest.TestCase):
    """The derived log paths straight from behaviour 3 of the plan."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.when = datetime(2026, 8, 21, 14, 30, 0)

    def test_plan_example_and_separator_replacement(self):
        cases = [
            (
                "Qwen/Qwen3-Coder-30B",
                "stress-Qwen-Qwen3-Coder-30B-20260821-143000.log",
            ),
            ("llama-8b", "stress-llama-8b-20260821-143000.log"),
            ("my model v2", "stress-my-model-v2-20260821-143000.log"),
            ("org/sub/model", "stress-org-sub-model-20260821-143000.log"),
            (
                "org\\sub\\model",
                "stress-org-sub-model-20260821-143000.log",
            ),
            ("model:v2", "stress-model-v2-20260821-143000.log"),
        ]
        for model_id, expected_name in cases:
            with self.subTest(model_id=model_id):
                self.assertEqual(
                    log_path(self.root, model_id, self.when),
                    self.root / "logs" / expected_name,
                )

    def test_timestamp_is_rendered_as_utc_yyyymmdd_hhmmss(self):
        cases = [
            (datetime(2026, 8, 21, 14, 30, 0), "20260821-143000"),
            (datetime(2026, 1, 2, 3, 4, 5), "20260102-030405"),
            (datetime(2025, 12, 31, 23, 59, 59), "20251231-235959"),
        ]
        for when, stamp in cases:
            with self.subTest(when=when):
                path = log_path(self.root, "model", when)
                self.assertEqual(path.name, "stress-model-{}.log".format(stamp))
                self.assertEqual(path.parent, self.root / "logs")


class TestLogPathEdges(unittest.TestCase):
    """Edge cases called out in behaviour 3 of the plan."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.when = datetime(2026, 8, 21, 14, 30, 0)

    def test_slash_does_not_create_nested_directories(self):
        # The common HuggingFace case: a slash in the id must land in the
        # file name, never in the directory tree.
        for model_id in ("Qwen/Qwen3-Coder-30B", "a/b/c/d"):
            with self.subTest(model_id=model_id):
                path = log_path(self.root, model_id, self.when)
                self.assertEqual(path.parent, self.root / "logs")

    def test_id_cannot_escape_logs_directory(self):
        for model_id in ("a/../../evil", "../escape", "..\\..\\evil"):
            with self.subTest(model_id=model_id):
                path = log_path(self.root, model_id, self.when)
                self.assertEqual(path.parent, self.root / "logs")
                self.assertEqual(Path(path.name).parts, (path.name,))

    def test_leading_separator_collapses_without_leading_dash(self):
        cases = [
            "/model-x",
            "\\model-x",
            ":model-x",
            " model-x",
        ]
        for model_id in cases:
            with self.subTest(model_id=model_id):
                path = log_path(self.root, model_id, self.when)
                self.assertEqual(
                    path.name, "stress-model-x-20260821-143000.log"
                )

    def test_trailing_separator_collapses_without_dangling_dash(self):
        cases = [
            "model-x/",
            "model-x\\",
            "model-x:",
            "model-x ",
        ]
        for model_id in cases:
            with self.subTest(model_id=model_id):
                path = log_path(self.root, model_id, self.when)
                self.assertEqual(
                    path.name, "stress-model-x-20260821-143000.log"
                )


class TestClassifyErrorTable(unittest.TestCase):
    """One row per category, straight from behaviour 6's table in the plan."""

    def test_oom_substrings(self):
        cases = [
            "out of memory",
            "outofmemoryerror",
            "enginedeaderror",
            "enginecore encountered an issue",
            "no available memory",
            "kv cache",
        ]
        for error in cases:
            with self.subTest(error=error):
                self.assertEqual(classify_error(error, None), "oom")

    def test_timeout_substring(self):
        for error in ("timed out", "the request timed out after 120.0s"):
            with self.subTest(error=error):
                self.assertEqual(classify_error(error, None), "timeout")

    def test_connection_substrings(self):
        for error in (
            "connection refused",
            "connection reset by peer",
            "broken pipe",
        ):
            with self.subTest(error=error):
                self.assertEqual(classify_error(error, None), "connection")

    def test_protocol_substrings(self):
        for error in (
            "the response did not return json",
            "non-object payload",
            "malformed response",
            "no choices",
        ):
            with self.subTest(error=error):
                self.assertEqual(classify_error(error, None), "protocol")

    def test_unknown_for_unrecognised_text(self):
        for error in ("the model was rude", "a totally novel error"):
            with self.subTest(error=error):
                self.assertEqual(classify_error(error, None), "unknown")


class TestClassifyErrorHttp(unittest.TestCase):
    """The ``http`` bucket and the precedence of text matches over it."""

    def test_unrecognised_text_with_status_is_http(self):
        for status in (400, 404, 500, 502, 503):
            with self.subTest(status=status):
                self.assertEqual(
                    classify_error("the model was rude", status), "http"
                )

    def test_oom_wins_over_http(self):
        # The plan's load-bearing rule: an OOM arriving as HTTP 500 is
        # classified as oom, not http.
        for error in (
            "CUDA out of memory",
            "out of memory",
            "no available memory",
        ):
            with self.subTest(error=error):
                self.assertEqual(classify_error(error, 500), "oom")

    def test_text_matches_win_over_http_in_declared_order(self):
        self.assertEqual(classify_error("timed out", 504), "timeout")
        self.assertEqual(classify_error("connection refused", 502), "connection")
        # http sits before protocol in the table: a protocol-shaped message
        # that also carries a status classifies as http.
        self.assertEqual(classify_error("did not return json", 500), "http")


class TestClassifyErrorEdges(unittest.TestCase):
    """Edge cases called out in behaviour 6 of the plan."""

    def test_empty_error_without_status_is_unknown(self):
        self.assertEqual(classify_error("", None), "unknown")

    def test_empty_error_with_status_is_http(self):
        self.assertEqual(classify_error("", 500), "http")

    def test_matching_is_case_insensitive(self):
        cases = [
            ("CUda oUt Of mEmOrY", None, "oom"),
            ("TIMED OUT", None, "timeout"),
            ("CONNECTION RESET BY PEER", None, "connection"),
            ("MALFORMED", None, "protocol"),
        ]
        for error, status, expected in cases:
            with self.subTest(error=error):
                self.assertEqual(classify_error(error, status), expected)

    def test_never_raises_and_always_returns_a_known_category(self):
        known = {"oom", "timeout", "http", "connection", "protocol", "unknown"}
        for error, status in (("", None), ("", 500), ("???", 0), ("kv cache", 500)):
            with self.subTest(error=error, status=status):
                self.assertIn(classify_error(error, status), known)


class _FakeClock:
    """A hand-advanced stand-in for the injected monotonic clock.

    ``warm_up`` must never read a real clock; tests advance this by hand so
    every elapsed figure is deterministic. Shared by behaviours 7-9.
    """

    def __init__(self, start=0.0):
        self._value = float(start)

    def now(self):
        return self._value

    def advance(self, seconds):
        self._value += float(seconds)


class _SendSpy:
    """Records calls to the injected ``send`` and returns queued outcomes.

    ``on_call`` runs once per call, just before the outcome is returned, so a
    test can advance the fake clock by the request's in-flight time.
    """

    def __init__(self, outcomes, on_call=None):
        self._outcomes = list(outcomes)
        self._queued = len(self._outcomes)
        self._on_call = on_call
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if not self._outcomes:
            raise AssertionError(
                "send called {} times but only {} outcomes were queued".format(
                    self.calls, self._queued
                )
            )
        outcome = self._outcomes.pop(0)
        if self._on_call is not None:
            self._on_call()
        return outcome


class _SleepSpy:
    """Records every call to the injected ``sleep`` with its interval."""

    def __init__(self):
        self.intervals = []

    def __call__(self, seconds):
        self.intervals.append(seconds)


class TestWarmUpFirstTrySuccess(unittest.TestCase):
    """Behaviour 7: ``send`` answers on the very first call.

    Only the first-try-success path is covered here; the retry path
    (behaviour 8) and budget exhaustion (behaviour 9) land in later cycles.
    """

    BUDGET = 600.0
    RETRY_INTERVAL = 5.0

    def setUp(self):
        self.clock = _FakeClock(start=100.0)
        self.sleep_spy = _SleepSpy()

    def _run_warm_up(self, in_flight_seconds):
        # A canned success, built from the real ChatOutcome type. The clock
        # advances by the in-flight time inside the send call, which is the
        # only time that may pass between warm_up's own now() readings.
        success = ChatOutcome(
            ok=True,
            latency_seconds=float(in_flight_seconds),
            prompt_tokens=7,
            completion_tokens=128,
        )
        send = _SendSpy(
            [success],
            on_call=lambda: self.clock.advance(in_flight_seconds),
        )
        result = warm_up(
            send,
            self.BUDGET,
            self.RETRY_INTERVAL,
            self.sleep_spy,
            self.clock.now,
        )
        return result, send

    def test_warm_up_first_try_success_returns_ok_result(self):
        result, _send = self._run_warm_up(32.5)
        self.assertTrue(result.ok)
        self.assertEqual(result.attempts, 1)
        self.assertIsNone(result.error)

    def test_warm_up_first_try_success_elapsed_measured_via_injected_clock(self):
        # Elapsed comes from the injected now(), not from the outcome's own
        # latency field and not from any real clock.
        for in_flight in (0.0, 0.25, 32.5, 120.0):
            with self.subTest(in_flight=in_flight):
                result, _send = self._run_warm_up(in_flight)
                self.assertIsInstance(result.elapsed_seconds, float)
                self.assertEqual(result.elapsed_seconds, in_flight)

    def test_warm_up_first_try_success_send_called_exactly_once(self):
        _result, send = self._run_warm_up(32.5)
        self.assertEqual(send.calls, 1)

    def test_warm_up_first_try_success_sleep_never_called(self):
        # There is no retry on this path, so sleep must never run at all.
        _result, _send = self._run_warm_up(32.5)
        self.assertEqual(self.sleep_spy.intervals, [])


class TestWarmUpRetriesUntilSuccess(unittest.TestCase):
    """Behaviour 8: a cold model that fails before it answers.

    A scripted ``send`` fails twice and then succeeds; ``warm_up`` must keep
    trying and report the successful outcome. Intermediate failures are not
    errors; only budget exhaustion (behaviour 9) is, and this cycle's script
    always succeeds long before the 600 s budget matters.
    """

    BUDGET = 600.0
    RETRY_INTERVAL = 5.0

    def _run_warm_up(self, failure_latencies, success_latency):
        # Two canned failures with distinct texts, then one canned success.
        # The clock advances by each request's in-flight time inside the send
        # call and by the interval whenever warm_up sleeps, so the full
        # wall-clock span is deterministic. Fresh fakes per call so subTests
        # cannot leak into one another.
        outcomes = [
            ChatOutcome(
                ok=False,
                latency_seconds=float(latency),
                error="connection refused",
            )
            for latency in failure_latencies
        ] + [
            ChatOutcome(
                ok=True,
                latency_seconds=float(success_latency),
                prompt_tokens=7,
                completion_tokens=128,
            )
        ]

        clock = _FakeClock(start=100.0)
        sleep_spy = _SleepSpy()
        in_flight = list(failure_latencies) + [success_latency]
        call_index = [0]

        def on_call():
            clock.advance(in_flight[call_index[0]])
            call_index[0] += 1

        def sleeping(seconds):
            # The retry interval is wall-clock time between attempts.
            sleep_spy(seconds)
            clock.advance(seconds)

        send = _SendSpy(outcomes, on_call=on_call)
        result = warm_up(
            send, self.BUDGET, self.RETRY_INTERVAL, sleeping, clock.now
        )
        return result, send, sleep_spy

    def test_warm_up_retries_until_success_returns_ok_result(self):
        result, send, _sleep_spy = self._run_warm_up([40.0, 60.0], 32.5)
        self.assertTrue(result.ok)
        self.assertEqual(result.attempts, 3)
        self.assertIsNone(result.error)
        self.assertEqual(send.calls, 3)

    def test_warm_up_retries_sleeps_interval_after_each_failure_not_after_success(
        self
    ):
        # One sleep per intermediate failure; the success ends the loop, so
        # there is no trailing sleep.
        _result, _send, sleep_spy = self._run_warm_up([40.0, 60.0], 32.5)
        self.assertEqual(
            sleep_spy.intervals, [self.RETRY_INTERVAL, self.RETRY_INTERVAL]
        )

    def test_warm_up_retries_elapsed_is_full_wall_clock_span(self):
        # Elapsed must cover every failed request's in-flight time, both
        # retry intervals and the final request -- not just the first attempt.
        for failure_latencies, success_latency in (
            ([40.0, 60.0], 32.5),
            ([0.0, 0.0], 120.0),
            ([12.25, 3.5], 0.0),
        ):
            with self.subTest(
                failure_latencies=failure_latencies,
                success_latency=success_latency,
            ):
                result, _send, _sleep_spy = self._run_warm_up(
                    failure_latencies, success_latency
                )
                expected = (
                    sum(failure_latencies)
                    + success_latency
                    + 2 * self.RETRY_INTERVAL
                )
                self.assertIsInstance(result.elapsed_seconds, float)
                self.assertEqual(result.elapsed_seconds, expected)


class TestWarmUpBudgetExhaustion(unittest.TestCase):
    """Behaviour 9: a ``send`` that never answers ends in a failed result.

    The budget is checked before each attempt after the first, so no attempt
    may start once the elapsed time has reached the budget; at least one
    attempt is always made, even with a budget of zero; and the last
    failure's text is carried through verbatim so the caller can tell the
    user *why* the model never came up. The result is returned, never
    raised.
    """

    BUDGET = 600.0
    RETRY_INTERVAL = 5.0

    def _run_warm_up(self, budget, in_flight_seconds, n_attempts):
        # A ``send`` that always fails. The per-attempt error text varies
        # (``attempt <k>: connection refused``) so a verbatim assertion on
        # the *last* failure cannot pass by coincidence of identical texts.
        # The clock advances by the in-flight time inside each send call and
        # by the interval whenever warm_up sleeps, so every attempt-start
        # time is deterministic.
        def make_failure(k):
            return ChatOutcome(
                ok=False,
                latency_seconds=float(in_flight_seconds),
                error="attempt {}: connection refused".format(k),
            )

        clock = _FakeClock(start=100.0)
        sleep_spy = _SleepSpy()
        call_index = [0]

        def on_call():
            call_index[0] += 1
            clock.advance(in_flight_seconds)

        def sleeping(seconds):
            sleep_spy(seconds)
            clock.advance(seconds)

        # Queue exactly the maximum number of attempts a correct
        # implementation can make; if warm_up ever checks the budget too
        # late (or not at all) the spy exhausts and the test fails fast
        # with a clear message instead of hanging.
        send = _SendSpy([make_failure(i) for i in range(1, n_attempts + 1)],
                        on_call=on_call)
        result = warm_up(
            send, budget, self.RETRY_INTERVAL, sleeping, clock.now
        )
        return result, send, sleep_spy, clock

    def test_budget_exhaustion_returns_failed_result_not_raises(self):
        # The contract is a failed WarmUpResult, not an exception: the
        # caller (a later behaviour) turns it into exit code 7.
        result, _send, _sleep_spy, _clock = self._run_warm_up(
            self.BUDGET, 1.0, 100
        )
        self.assertIsInstance(result, stress.WarmUpResult)
        self.assertFalse(result.ok)

    def test_budget_exhaustion_at_least_one_attempt_even_with_zero_budget(
        self
    ):
        # Reporting "never tried" would be useless: the first attempt is
        # always made, then the budget check stops any further attempts.
        result, send, sleep_spy, _clock = self._run_warm_up(0.0, 1.0, 1)
        self.assertFalse(result.ok)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(send.calls, 1)
        # No second attempt happens, so there is nothing to sleep before.
        self.assertEqual(sleep_spy.intervals, [])

    def test_budget_exhaustion_exact_count_for_scripted_timing(self):
        # In-flight 1.0 s per attempt, interval 5.0 s, so attempt k starts
        # at elapsed (k-1) * 6.0 s. Attempt 100 starts at 594.0 < 600.0
        # and attempt 101 would start exactly at the budget, so it must
        # not be made: exactly 100 attempts.
        result, send, _sleep_spy, _clock = self._run_warm_up(
            self.BUDGET, 1.0, 100
        )
        self.assertEqual(result.attempts, 100)
        self.assertEqual(send.calls, 100)
        # Elapsed is the full span to the end of the last attempt:
        # 99 intervals of 5.0 plus 100 in-flight seconds of 1.0.
        self.assertEqual(result.elapsed_seconds, 594.0 + 1.0)

    def test_budget_exhaustion_no_attempt_starts_at_or_after_budget(self):
        # The invariant behind the exact count: with the scripted timing,
        # the last attempt that *may* start does so at 594.0, strictly
        # before the 600.0 budget, and the one that would follow is
        # refused. A weaker bound (no attempt *past* the budget) would
        # still allow overshooting by a whole request timeout.
        in_flight = 1.0
        step = in_flight + self.RETRY_INTERVAL
        last_start = (100 - 1) * step
        next_start = 100 * step
        self.assertLess(last_start, self.BUDGET)
        self.assertGreaterEqual(next_start, self.BUDGET)
        result, send, _sleep_spy, _clock = self._run_warm_up(
            self.BUDGET, in_flight, 100
        )
        self.assertEqual(result.attempts, 100)
        self.assertEqual(send.calls, 100)
        self.assertLessEqual(result.elapsed_seconds, self.BUDGET + in_flight)

    def test_budget_exhaustion_last_error_preserved_verbatim(self):
        # The user must see WHY the model never came up, and it must be
        # the *last* failure's text, not the first: the texts vary per
        # attempt, so asserting on the final one is meaningful.
        result, _send, _sleep_spy, _clock = self._run_warm_up(
            self.BUDGET, 1.0, 100
        )
        self.assertEqual(
            result.error, "attempt 100: connection refused"
        )
        self.assertNotEqual(result.error, "attempt 1: connection refused")

    def test_budget_exhaustion_sleeps_only_between_attempts(self):
        # One interval per gap between consecutive attempts; a failed last
        # attempt does not get a trailing sleep after it.
        result, send, sleep_spy, _clock = self._run_warm_up(
            self.BUDGET, 1.0, 100
        )
        self.assertEqual(len(sleep_spy.intervals), result.attempts - 1)
        self.assertTrue(
            all(interval == self.RETRY_INTERVAL for interval in
                sleep_spy.intervals)
        )


class TestCheckModelAvailableTable(unittest.TestCase):
    """Behaviour 10: one row per case in the plan's verdict table.

    A pure decision over hand-built ``GatewayStatus`` objects: no mocks,
    no CLI, no network. The verdict ordering is load-bearing -- both
    flavours of unreachability (offline gateway, unusable registry
    payload) outrank membership, and a genuinely empty registry is
    ``unknown_model``, not ``unreachable``.
    """

    def _decide(self, gateway, model_id):
        if check_model_available is None:
            self.fail(
                "anvilkit.stress.check_model_available is not implemented "
                "yet: {}".format(_check_model_available_import_error)
            )
        result = check_model_available(gateway, model_id)
        if ModelAvailability is not None:
            self.assertIsInstance(result, ModelAvailability)
        return result

    def _gateway(self, online, models=(), error=None, registry_error=None):
        return GatewayStatus(
            port=8080,
            online=online,
            models=[ModelStatus(mid, False) for mid in models],
            error=error,
            registry_error=registry_error,
        )

    def test_plan_table_rows(self):
        cases = [
            (
                "registered model on an online gateway",
                self._gateway(True, models=("a", "b")),
                "a",
                "ok",
                ["a", "b"],
                None,
            ),
            (
                "unknown model on a non-empty registry",
                self._gateway(True, models=("a", "b")),
                "c",
                "unknown_model",
                ["a", "b"],
                None,
            ),
            (
                "offline gateway",
                self._gateway(False, error="connection refused"),
                "a",
                "unreachable",
                [],
                "connection refused",
            ),
            (
                "unusable registry payload",
                self._gateway(
                    True, registry_error="/v1/models did not return JSON"
                ),
                "a",
                "unreachable",
                [],
                "/v1/models did not return JSON",
            ),
            (
                "genuinely empty registry",
                self._gateway(True),
                "a",
                "unknown_model",
                [],
                None,
            ),
        ]
        for description, gateway, model_id, verdict, available, reason in cases:
            with self.subTest(description=description):
                result = self._decide(gateway, model_id)
                self.assertEqual(result.verdict, verdict)
                self.assertEqual(result.available, available)
                self.assertEqual(result.reason, reason)

    def test_registry_error_outranks_a_positive_membership(self):
        # The ordering point: the gateway answered and the handed-in status
        # even lists the named model, but the payload was flagged unusable,
        # so the verdict must be unreachable, not ok.
        gateway = self._gateway(
            True, models=("a",), registry_error="/v1/models did not return JSON"
        )
        result = self._decide(gateway, "a")
        self.assertEqual(result.verdict, "unreachable")
        self.assertEqual(result.reason, "/v1/models did not return JSON")

    def test_unreachable_carries_the_gateways_error_verbatim(self):
        for error in (
            "connection refused",
            "timed out after 2.0s contacting /v1/models",
        ):
            with self.subTest(error=error):
                result = self._decide(self._gateway(False, error=error), "a")
                self.assertEqual(result.verdict, "unreachable")
                self.assertEqual(result.reason, error)
                self.assertEqual(result.available, [])

    def test_exact_set_membership_never_prefix_or_suffix_matches(self):
        for registered, requested in (
            ("vendor/model-a-instruct", "vendor/model-a"),
            ("vendor/model-a", "vendor/model-a-instruct"),
            ("vendor/model-a", "vendor/model-a2"),
        ):
            with self.subTest(registered=registered, requested=requested):
                result = self._decide(
                    self._gateway(True, models=(registered,)), requested
                )
                self.assertEqual(result.verdict, "unknown_model")
                self.assertEqual(result.available, [registered])

    def test_available_ids_are_ascending(self):
        # The plan's field contract: "the registered ids, ascending".
        result = self._decide(self._gateway(True, models=("b", "a")), "a")
        self.assertEqual(result.verdict, "ok")
        self.assertEqual(result.available, ["a", "b"])


class TestCheckModelAvailableEdges(unittest.TestCase):
    """Edge cases called out in behaviour 10 of the plan."""

    def _decide(self, gateway, model_id):
        if check_model_available is None:
            self.fail(
                "anvilkit.stress.check_model_available is not implemented "
                "yet: {}".format(_check_model_available_import_error)
            )
        return check_model_available(gateway, model_id)

    def _gateway(self, online, models=(), error=None, registry_error=None):
        return GatewayStatus(
            port=8080,
            online=online,
            models=[ModelStatus(mid, False) for mid in models],
            error=error,
            registry_error=registry_error,
        )

    def test_never_raises_for_any_combination_of_status_fields(self):
        # The error behaviour is "never raises": it is a pure verdict over
        # data already in hand, and the verdict is always one of the three.
        gateways = [
            self._gateway(False, error="connection refused"),
            self._gateway(True, registry_error="bad payload"),
            self._gateway(True),
            self._gateway(True, models=("a",)),
            self._gateway(True, models=("a",), registry_error="bad payload"),
        ]
        for index, gateway in enumerate(gateways):
            for model_id in ("a", "b", ""):
                with self.subTest(gateway=index, model_id=model_id):
                    result = self._decide(gateway, model_id)
                    self.assertIn(
                        result.verdict, {"ok", "unknown_model", "unreachable"}
                    )

    def test_hot_cold_state_does_not_change_the_verdict(self):
        # The verdict is about registration, not load state: a model that
        # is registered but swapped out is still stressable.
        gateway = GatewayStatus(
            port=8080,
            online=True,
            models=[ModelStatus("a", hot=True), ModelStatus("b", hot=False)],
        )
        for model_id in ("a", "b"):
            with self.subTest(model_id=model_id):
                if check_model_available is None:
                    self.fail(
                        "anvilkit.stress.check_model_available is not "
                        "implemented yet: {}".format(
                            _check_model_available_import_error
                        )
                    )
                result = check_model_available(gateway, model_id)
                self.assertEqual(result.verdict, "ok")


class TestCheckModelAvailableResultType(unittest.TestCase):
    """The result type contract from behaviour 10 of the plan."""

    def test_model_availability_is_a_dataclass(self):
        if ModelAvailability is None:
            self.fail(
                "anvilkit.stress.ModelAvailability is not implemented yet: "
                "{}".format(_check_model_available_import_error)
            )
        self.assertTrue(dataclasses.is_dataclass(ModelAvailability))


def _success_outcome():
    """A canned successful ``ChatOutcome`` for level tests."""
    return ChatOutcome(
        ok=True,
        latency_seconds=0.01,
        prompt_tokens=7,
        completion_tokens=128,
    )


class _InFlightTracker:
    """A thread-safe fake ``send`` that records its observed peak in-flight.

    Increments the in-flight count on entry, records the peak, and
    decrements on exit, all under a lock so the observation is exact even
    though the worker threads interleave. Returns the outcome queued for
    its call number, so the test knows ``send`` ran the expected times.
    """

    def __init__(self, outcomes):
        self._lock = threading.Lock()
        self._outcomes = list(outcomes)
        self._calls = 0
        self._in_flight = 0
        self.peak = 0

    def __call__(self, *args, **kwargs):
        with self._lock:
            self._calls += 1
            call_index = self._calls
            self._in_flight += 1
            if self._in_flight > self.peak:
                self.peak = self._in_flight
        try:
            return self._outcomes[call_index - 1]
        finally:
            with self._lock:
                self._in_flight -= 1

    @property
    def calls(self):
        with self._lock:
            return self._calls


class _RaisingSend:
    """A thread-safe fake ``send`` whose first N calls raise, the rest return.

    Call order across the worker threads is not pinned, so the raise set
    is over the call *sequence* rather than any request identity: exactly
    ``raise_count`` of the calls raise, whichever requests they are.
    """

    def __init__(self, outcomes, raise_count):
        self._lock = threading.Lock()
        self._outcomes = list(outcomes)
        self._raise_count = raise_count
        self._calls = 0
        self.raised = 0

    def __call__(self, *args, **kwargs):
        with self._lock:
            self._calls += 1
            call_index = self._calls
            should_raise = call_index <= self._raise_count
            if should_raise:
                self.raised += 1
            outcome = self._outcomes[call_index - 1]
        if should_raise:
            raise RuntimeError(
                "injected failure: call {}".format(call_index)
            )
        return outcome

    @property
    def calls(self):
        with self._lock:
            return self._calls


class TestRunLevelOutcomeCount(unittest.TestCase):
    """Behaviour 11: exactly ``request_count`` outcomes, one per request."""

    def _run(self, send, concurrency, request_count):
        if run_level is None:
            self.fail(
                "anvilkit.stress.run_level is not implemented yet: "
                "{}".format(_run_level_import_error)
            )
        return run_level(send, concurrency, request_count)

    def test_returns_exactly_request_count_outcomes(self):
        cases = [
            (1, 1),
            (1, 5),
            (2, 10),
            (3, 10),
            (4, 20),
            (16, 20),
        ]
        for concurrency, request_count in cases:
            with self.subTest(
                concurrency=concurrency, request_count=request_count
            ):
                send = _InFlightTracker(
                    [_success_outcome() for _ in range(request_count)]
                )
                outcomes = self._run(send, concurrency, request_count)
                self.assertEqual(len(outcomes), request_count)
                self.assertEqual(send.calls, request_count)
                for outcome in outcomes:
                    self.assertIsInstance(outcome, ChatOutcome)

    def test_concurrency_above_request_count_still_returns_full_count(
        self
    ):
        # The pool is sized to ``concurrency`` but only ``request_count``
        # requests are submitted: the level returns 3 outcomes, not 8. The
        # "not reached its nominal concurrency" annotation belongs to the
        # later reporting behaviour; this behaviour's contract is the count.
        for concurrency, request_count in ((8, 3), (16, 1)):
            with self.subTest(
                concurrency=concurrency, request_count=request_count
            ):
                send = _InFlightTracker(
                    [_success_outcome() for _ in range(request_count)]
                )
                outcomes = self._run(send, concurrency, request_count)
                self.assertEqual(len(outcomes), request_count)
                self.assertEqual(send.calls, request_count)
                for outcome in outcomes:
                    self.assertIsInstance(outcome, ChatOutcome)

    def test_failure_outcomes_do_not_shrink_the_count(self):
        # Returned failures are collected results, not short-circuits: one
        # outcome per request, ok or not.
        request_count = 10
        outcomes_in = [
            ChatOutcome(
                ok=(index % 3 != 0),
                latency_seconds=0.01,
                error=None
                if index % 3 != 0
                else "connection refused",
            )
            for index in range(request_count)
        ]
        send = _InFlightTracker(outcomes_in)
        outcomes = self._run(send, 2, request_count)
        self.assertEqual(len(outcomes), request_count)
        # Assert as a multiset on the ok flag, not on any ordering.
        self.assertEqual(
            sorted(o.ok for o in outcomes),
            sorted(o.ok for o in outcomes_in),
        )


class TestRunLevelInFlightBound(unittest.TestCase):
    """Behaviour 11: at most ``concurrency`` requests in flight at once."""

    def _run(self, send, concurrency, request_count):
        if run_level is None:
            self.fail(
                "anvilkit.stress.run_level is not implemented yet: "
                "{}".format(_run_level_import_error)
            )
        return run_level(send, concurrency, request_count)

    def test_concurrency_one_is_genuinely_serial(self):
        # With one worker, the observed in-flight count can never exceed 1,
        # and because every one of the 8 requests actually runs, the peak
        # is exactly 1.
        request_count = 8
        send = _InFlightTracker(
            [_success_outcome() for _ in range(request_count)]
        )
        self._run(send, 1, request_count)
        self.assertEqual(send.calls, request_count)
        self.assertEqual(send.peak, 1)

    def test_peak_in_flight_never_exceeds_concurrency(self):
        # The plan pins the bound, not the achieved concurrency: the peak
        # must never exceed the level, whether or not the scheduler ever
        # fills the pool.
        for concurrency, request_count in ((2, 10), (3, 10), (4, 20)):
            with self.subTest(
                concurrency=concurrency, request_count=request_count
            ):
                send = _InFlightTracker(
                    [_success_outcome() for _ in range(request_count)]
                )
                self._run(send, concurrency, request_count)
                self.assertEqual(send.calls, request_count)
                self.assertLessEqual(send.peak, concurrency)


class TestRunLevelRaisingSend(unittest.TestCase):
    """Behaviour 11: a ``send`` that raises is converted into a failure.

    One thread must never abort the level: the exception is caught, the
    request it was servicing comes back as a failed ``ChatOutcome``, and
    the level still returns the full count.
    """

    def _run(self, send, concurrency, request_count):
        if run_level is None:
            self.fail(
                "anvilkit.stress.run_level is not implemented yet: "
                "{}".format(_run_level_import_error)
            )
        return run_level(send, concurrency, request_count)

    def test_raising_send_is_converted_to_a_failed_outcome(self):
        request_count = 6
        send = _RaisingSend(
            [_success_outcome() for _ in range(request_count)],
            raise_count=1,
        )
        outcomes = self._run(send, 2, request_count)
        self.assertEqual(len(outcomes), request_count)
        self.assertEqual(send.raised, 1)
        failed = [outcome for outcome in outcomes if not outcome.ok]
        succeeded = [outcome for outcome in outcomes if outcome.ok]
        self.assertEqual(len(failed), 1)
        self.assertEqual(len(succeeded), request_count - 1)
        self.assertIsInstance(failed[0].error, str)
        self.assertTrue(failed[0].error)

    def test_send_that_always_raises_does_not_abort_the_level(self):
        # The strongest form: every request raises, yet the level returns
        # the full count, all failed, none of them an exception.
        request_count = 5
        send = _RaisingSend(
            [_success_outcome() for _ in range(request_count)],
            raise_count=request_count,
        )
        outcomes = self._run(send, 3, request_count)
        self.assertEqual(len(outcomes), request_count)
        self.assertEqual(send.raised, request_count)
        for outcome in outcomes:
            self.assertFalse(outcome.ok)
            self.assertIsInstance(outcome.error, str)
            self.assertTrue(outcome.error)


def _ok_outcome(latency, completion_tokens=None, prompt_tokens=None):
    """A canned successful ``ChatOutcome`` with the given latency."""
    return ChatOutcome(
        ok=True,
        latency_seconds=latency,
        completion_tokens=completion_tokens,
        prompt_tokens=prompt_tokens,
    )


def _failed_outcome(error, latency=0.0, http_status=None):
    """A canned failed ``ChatOutcome`` with the given raw error text."""
    return ChatOutcome(
        ok=False,
        latency_seconds=latency,
        error=error,
        http_status=http_status,
    )


class TestSummariseLevelAllSuccess(unittest.TestCase):
    """Behaviour 12: a level where every request succeeded."""

    def _summarise(self, level, outcomes, wall_seconds):
        if summarise_level is None:
            self.fail(
                "anvilkit.stress.summarise_level is not implemented yet: "
                "{}".format(_summarise_level_import_error)
            )
        return summarise_level(level, outcomes, wall_seconds)

    def test_reports_counts_and_clean_error_fields(self):
        outcomes = [
            _ok_outcome(1.0, completion_tokens=128),
            _ok_outcome(2.0, completion_tokens=256),
            _ok_outcome(3.0, completion_tokens=64),
            _ok_outcome(4.0, completion_tokens=192),
        ]
        summary = self._summarise(4, outcomes, 10.0)
        self.assertEqual(summary.concurrency, 4)
        self.assertEqual(summary.requests, 4)
        self.assertEqual(summary.succeeded, 4)
        self.assertEqual(summary.failed, 0)
        # A clean level has an empty error mapping and no raw errors.
        self.assertEqual(summary.error_counts, {})
        self.assertEqual(summary.errors, [])

    def test_latency_figures(self):
        # Nearest-rank on [1, 2, 3, 4]: p50 is index ceil(0.5*4)-1 = 1 ->
        # 2.0; p95 and p99 both reach the last element.
        outcomes = [
            _ok_outcome(1.0),
            _ok_outcome(2.0),
            _ok_outcome(3.0),
            _ok_outcome(4.0),
        ]
        summary = self._summarise(2, outcomes, 10.0)
        self.assertAlmostEqual(summary.latency_mean, 2.5)
        self.assertAlmostEqual(summary.latency_p50, 2.0)
        self.assertAlmostEqual(summary.latency_p95, 4.0)
        self.assertAlmostEqual(summary.latency_p99, 4.0)
        self.assertAlmostEqual(summary.latency_min, 1.0)
        self.assertAlmostEqual(summary.latency_max, 4.0)

    def test_single_success_reports_it_for_every_figure(self):
        outcome = _ok_outcome(1.5, completion_tokens=100)
        summary = self._summarise(1, [outcome], 3.0)
        self.assertEqual(summary.requests, 1)
        self.assertEqual(summary.succeeded, 1)
        self.assertAlmostEqual(summary.latency_mean, 1.5)
        self.assertAlmostEqual(summary.latency_p50, 1.5)
        self.assertAlmostEqual(summary.latency_p95, 1.5)
        self.assertAlmostEqual(summary.latency_p99, 1.5)
        self.assertAlmostEqual(summary.latency_min, 1.5)
        self.assertAlmostEqual(summary.latency_max, 1.5)
        self.assertAlmostEqual(summary.requests_per_second, 1.0 / 3.0)
        self.assertAlmostEqual(summary.tokens_per_second, 100.0 / 3.0)

    def test_rates(self):
        outcomes = [
            _ok_outcome(1.0, completion_tokens=128),
            _ok_outcome(2.0, completion_tokens=256),
            _ok_outcome(3.0, completion_tokens=64),
            _ok_outcome(4.0, completion_tokens=192),
        ]
        summary = self._summarise(4, outcomes, 10.0)
        self.assertAlmostEqual(summary.requests_per_second, 4.0 / 10.0)
        # 128 + 256 + 64 + 192 = 640 completion tokens over 10 seconds.
        self.assertAlmostEqual(summary.tokens_per_second, 64.0)


class TestSummariseLevelMixed(unittest.TestCase):
    """Behaviour 12: successes and failures at the same level.

    The load-bearing rule: latency figures come from successful outcomes
    only, so a fast failure must not drag the mean down.
    """

    def _summarise(self, level, outcomes, wall_seconds):
        if summarise_level is None:
            self.fail(
                "anvilkit.stress.summarise_level is not implemented yet: "
                "{}".format(_summarise_level_import_error)
            )
        return summarise_level(level, outcomes, wall_seconds)

    def test_latency_figures_exclude_failures(self):
        # Two slow successes and two fast failures: the 0.1/0.2 s failures
        # must not appear in any latency figure.
        outcomes = [
            _ok_outcome(3.0, completion_tokens=128),
            _failed_outcome("CUDA out of memory", latency=0.2, http_status=500),
            _ok_outcome(4.0, completion_tokens=256),
            _failed_outcome("request timed out", latency=0.1),
        ]
        summary = self._summarise(8, outcomes, 20.0)
        self.assertAlmostEqual(summary.latency_mean, 3.5)
        # Nearest-rank on [3, 4]: p50 is index 0, p95/p99 reach index 1.
        self.assertAlmostEqual(summary.latency_p50, 3.0)
        self.assertAlmostEqual(summary.latency_p95, 4.0)
        self.assertAlmostEqual(summary.latency_p99, 4.0)
        self.assertAlmostEqual(summary.latency_min, 3.0)
        self.assertAlmostEqual(summary.latency_max, 4.0)

    def test_counts(self):
        outcomes = [
            _ok_outcome(3.0, completion_tokens=128),
            _failed_outcome("CUDA out of memory", http_status=500),
            _ok_outcome(4.0, completion_tokens=256),
            _failed_outcome("request timed out"),
        ]
        summary = self._summarise(8, outcomes, 20.0)
        self.assertEqual(summary.concurrency, 8)
        self.assertEqual(summary.requests, 4)
        self.assertEqual(summary.succeeded, 2)
        self.assertEqual(summary.failed, 2)

    def test_rates_and_throughput(self):
        outcomes = [
            _ok_outcome(3.0, completion_tokens=128),
            _failed_outcome("CUDA out of memory", http_status=500),
            _ok_outcome(4.0, completion_tokens=256),
            _failed_outcome("request timed out"),
        ]
        summary = self._summarise(8, outcomes, 20.0)
        self.assertAlmostEqual(summary.requests_per_second, 2.0 / 20.0)
        # Only the successful token counts contribute: 128 + 256 over 20 s.
        self.assertAlmostEqual(summary.tokens_per_second, 19.2)

    def test_error_counts_and_raw_errors(self):
        outcomes = [
            _ok_outcome(3.0, completion_tokens=128),
            _failed_outcome("CUDA out of memory", http_status=500),
            _ok_outcome(4.0, completion_tokens=256),
            _failed_outcome("request timed out"),
        ]
        summary = self._summarise(8, outcomes, 20.0)
        # The OOM arrives as an HTTP 500 but must bucket as oom, not http.
        self.assertEqual(
            summary.error_counts, {"oom": 1, "timeout": 1}
        )
        self.assertEqual(
            summary.errors,
            ["CUDA out of memory", "request timed out"],
        )


class TestSummariseLevelAllFailed(unittest.TestCase):
    """Behaviour 12: a level where every request failed.

    All latency figures are ``None`` -- never a fabricated ``0.0`` -- and
    both rates are ``0.0``, never a ``ZeroDivisionError``.
    """

    def _summarise(self, level, outcomes, wall_seconds):
        if summarise_level is None:
            self.fail(
                "anvilkit.stress.summarise_level is not implemented yet: "
                "{}".format(_summarise_level_import_error)
            )
        return summarise_level(level, outcomes, wall_seconds)

    def test_latency_figures_are_none(self):
        outcomes = [
            _failed_outcome("CUDA out of memory", latency=0.2, http_status=500),
            _failed_outcome("request timed out", latency=0.1),
        ]
        summary = self._summarise(4, outcomes, 10.0)
        self.assertEqual(summary.requests, 2)
        self.assertEqual(summary.succeeded, 0)
        self.assertEqual(summary.failed, 2)
        self.assertIsNone(summary.latency_mean)
        self.assertIsNone(summary.latency_p50)
        self.assertIsNone(summary.latency_p95)
        self.assertIsNone(summary.latency_p99)
        self.assertIsNone(summary.latency_min)
        self.assertIsNone(summary.latency_max)

    def test_rates_are_zero_not_an_exception(self):
        outcomes = [
            _failed_outcome("CUDA out of memory", latency=0.2, http_status=500),
            _failed_outcome("request timed out", latency=0.1),
        ]
        summary = self._summarise(4, outcomes, 10.0)
        self.assertEqual(summary.requests_per_second, 0.0)
        self.assertEqual(summary.tokens_per_second, 0.0)

    def test_all_failed_with_zero_wall_still_reports_zero_rates(self):
        # The plan's all-failure rule is unconditional on wall time: an
        # all-failed level reports 0.0 rates even when the wall time is
        # zero -- 0/0 must not raise.
        outcomes = [
            _failed_outcome("CUDA out of memory", http_status=500),
        ]
        summary = self._summarise(1, outcomes, 0.0)
        self.assertEqual(summary.requests_per_second, 0.0)
        self.assertEqual(summary.tokens_per_second, 0.0)
        self.assertIsNone(summary.latency_mean)

    def test_error_counts_cover_every_category_over_failures_only(self):
        outcomes = [
            _failed_outcome("CUDA out of memory", http_status=500),
            _failed_outcome("request timed out"),
            _failed_outcome("connection refused"),
            _failed_outcome("internal error", http_status=500),
            _failed_outcome("server did not return json"),
            _failed_outcome("???"),
        ]
        summary = self._summarise(6, outcomes, 10.0)
        self.assertEqual(
            summary.error_counts,
            {"oom": 1, "timeout": 1, "connection": 1, "http": 1, "protocol": 1, "unknown": 1},
        )
        self.assertEqual(
            summary.errors,
            [
                "CUDA out of memory",
                "request timed out",
                "connection refused",
                "internal error",
                "server did not return json",
            ],
        )


class TestSummariseLevelZeroWall(unittest.TestCase):
    """Behaviour 12: a zero wall time must not raise.

    With successes the rates are ``None`` rather than an exception; the
    latency figures are unaffected, since they do not use the wall time.
    """

    def _summarise(self, level, outcomes, wall_seconds):
        if summarise_level is None:
            self.fail(
                "anvilkit.stress.summarise_level is not implemented yet: "
                "{}".format(_summarise_level_import_error)
            )
        return summarise_level(level, outcomes, wall_seconds)

    def test_rates_are_none_when_there_are_successes(self):
        outcomes = [
            _ok_outcome(1.0, completion_tokens=128),
            _ok_outcome(2.0, completion_tokens=256),
        ]
        summary = self._summarise(2, outcomes, 0.0)
        self.assertIsNone(summary.requests_per_second)
        self.assertIsNone(summary.tokens_per_second)

    def test_latency_figures_still_computed(self):
        outcomes = [
            _ok_outcome(1.0, completion_tokens=128),
            _ok_outcome(2.0, completion_tokens=256),
        ]
        summary = self._summarise(2, outcomes, 0.0)
        self.assertAlmostEqual(summary.latency_mean, 1.5)
        self.assertAlmostEqual(summary.latency_min, 1.0)
        self.assertAlmostEqual(summary.latency_max, 2.0)


class TestSummariseLevelTokenThroughput(unittest.TestCase):
    """Behaviour 12: token throughput versus missing usage counters.

    ``None`` token counts mean "the response reported no usage", which is
    distinct from a genuine zero and must yield ``None`` throughput.
    """

    def _summarise(self, level, outcomes, wall_seconds):
        if summarise_level is None:
            self.fail(
                "anvilkit.stress.summarise_level is not implemented yet: "
                "{}".format(_summarise_level_import_error)
            )
        return summarise_level(level, outcomes, wall_seconds)

    def test_no_usage_reported_is_none_not_zero(self):
        outcomes = [
            _ok_outcome(1.0),
            _ok_outcome(2.0),
        ]
        summary = self._summarise(2, outcomes, 10.0)
        self.assertIsNone(summary.tokens_per_second)
        # The request rate does not depend on usage counters.
        self.assertAlmostEqual(summary.requests_per_second, 0.2)

    def test_genuine_zero_tokens_is_zero_not_none(self):
        outcomes = [
            _ok_outcome(1.0, completion_tokens=0),
            _ok_outcome(2.0, completion_tokens=0),
        ]
        summary = self._summarise(2, outcomes, 10.0)
        self.assertEqual(summary.tokens_per_second, 0.0)

    def test_partial_usage_sums_only_reported_counts(self):
        outcomes = [
            _ok_outcome(1.0, completion_tokens=128),
            _ok_outcome(2.0),
            _ok_outcome(3.0, completion_tokens=256),
        ]
        summary = self._summarise(3, outcomes, 10.0)
        self.assertAlmostEqual(summary.tokens_per_second, 38.4)


class TestSummariseLevelErrorsList(unittest.TestCase):
    """Behaviour 12: ``errors`` is distinct raw strings, first five.

    Duplicates collapse; first-seen order is pinned here as the contract;
    the list is capped at the first five distinct errors, so the report
    shows actual messages without growing without bound.
    """

    def _summarise(self, level, outcomes, wall_seconds):
        if summarise_level is None:
            self.fail(
                "anvilkit.stress.summarise_level is not implemented yet: "
                "{}".format(_summarise_level_import_error)
            )
        return summarise_level(level, outcomes, wall_seconds)

    def test_duplicates_collapse_in_first_seen_order(self):
        outcomes = [
            _failed_outcome("boom-a"),
            _failed_outcome("boom-b"),
            _failed_outcome("boom-a"),
            _failed_outcome("boom-c"),
        ]
        summary = self._summarise(4, outcomes, 10.0)
        self.assertEqual(
            summary.errors, ["boom-a", "boom-b", "boom-c"]
        )

    def test_capped_at_first_five_distinct_errors(self):
        outcomes = [
            _failed_outcome("boom-a"),
            _failed_outcome("boom-b"),
            _failed_outcome("boom-c"),
            _failed_outcome("boom-a"),
            _failed_outcome("boom-d"),
            _failed_outcome("boom-e"),
            _failed_outcome("boom-f"),
        ]
        summary = self._summarise(6, outcomes, 10.0)
        self.assertEqual(
            summary.errors,
            ["boom-a", "boom-b", "boom-c", "boom-d", "boom-e"],
        )
        # The count of failures is not capped: only the shown messages are.
        self.assertEqual(summary.failed, 7)


class TestSummariseLevelResultType(unittest.TestCase):
    """The result type contract from behaviour 12 of the plan."""

    def test_level_summary_is_a_dataclass(self):
        if LevelSummary is None:
            self.fail(
                "anvilkit.stress.LevelSummary is not implemented yet: "
                "{}".format(_summarise_level_import_error)
            )
        self.assertTrue(dataclasses.is_dataclass(LevelSummary))


class _LevelSend:
    """A fake ``send`` that serves one scripted outcome list per level.

    ``run_stress`` runs the levels one after another and calls ``send``
    ``request_count`` times per level, so call ``k`` belongs to level
    ``(k - 1) // request_count`` and to slot ``(k - 1) % request_count``
    within that level. Within one level the worker threads interleave, so
    which task receives which scripted outcome is not pinned: the per-level
    list is meaningful as a multiset, and every assertion is on the
    aggregated counts and the figures that follow from per-level latency
    values, never on the arrival order of individual outcomes.
    """

    def __init__(self, level_outcomes, request_count):
        self._levels = [list(outcomes) for outcomes in level_outcomes]
        self._request_count = request_count
        self._lock = threading.Lock()
        self._calls = 0

    def __call__(self, *args, **kwargs):
        with self._lock:
            self._calls += 1
            call_index = self._calls
        zero = call_index - 1
        level_index = zero // self._request_count
        if level_index >= len(self._levels):
            raise AssertionError(
                "send called {} times but only {} levels were scripted".format(
                    call_index, len(self._levels)
                )
            )
        return self._levels[level_index][zero % self._request_count]

    @property
    def calls(self):
        with self._lock:
            return self._calls


class TestRunStressCleanRun(unittest.TestCase):
    """Behaviour 13: a run where every request at every level succeeded.

    ``run_stress(send, levels, request_count, warm_up_result, model_id,
    port)`` returns a ``StressReport`` carrying the run's identifying
    metadata, the warm-up result it was handed, and one ``LevelSummary``
    per input level in input order. The per-level wall time comes from
    ``time.monotonic`` inside the implementation and is not injectable, so
    the rates (``requests_per_second`` / ``tokens_per_second``) are NOT
    pinned here; the latency figures are, because they derive from the
    canned ``latency_seconds`` only.
    """

    def _run(self, send, levels, request_count, warm_up_result, model_id, port):
        if run_stress is None:
            self.fail(
                "anvilkit.stress.run_stress is not implemented yet: "
                "{}".format(_run_stress_import_error)
            )
        return run_stress(
            send, levels, request_count, warm_up_result, model_id, port
        )

    def test_metadata_and_warm_up_pass_through(self):
        levels = [1, 2, 4]
        request_count = 3
        warm = stress.WarmUpResult(
            ok=True, attempts=1, elapsed_seconds=42.1, error=None
        )
        send = _LevelSend(
            [[_ok_outcome(0.5) for _ in range(request_count)] for _ in levels],
            request_count,
        )
        report = self._run(
            send, levels, request_count, warm, "Qwen/Qwen3-Coder-30B", 8080
        )
        if StressReport is not None:
            self.assertIsInstance(report, StressReport)
        self.assertEqual(report.model_id, "Qwen/Qwen3-Coder-30B")
        self.assertEqual(report.port, 8080)
        # The report carries the very WarmUpResult it was handed, not a copy.
        self.assertIs(report.warm_up, warm)

    def test_one_summary_per_input_level_in_input_order(self):
        levels = [1, 2, 4]
        request_count = 3
        warm = stress.WarmUpResult(
            ok=True, attempts=1, elapsed_seconds=42.1, error=None
        )
        send = _LevelSend(
            [[_ok_outcome(0.5) for _ in range(request_count)] for _ in levels],
            request_count,
        )
        report = self._run(send, levels, request_count, warm, "model", 11434)
        self.assertEqual(len(report.levels), len(levels))
        self.assertEqual(
            [summary.concurrency for summary in report.levels], levels
        )
        for summary in report.levels:
            self.assertIsInstance(summary, LevelSummary)

    def test_clean_level_summaries(self):
        # Distinct per-level latencies so a level that got the wrong
        # outcomes would show up in its latency figures.
        per_level = {1: 0.5, 2: 1.0, 4: 2.0}
        levels = [1, 2, 4]
        request_count = 3
        warm = stress.WarmUpResult(
            ok=True, attempts=1, elapsed_seconds=42.1, error=None
        )
        send = _LevelSend(
            [
                [_ok_outcome(per_level[level]) for _ in range(request_count)]
                for level in levels
            ],
            request_count,
        )
        report = self._run(send, levels, request_count, warm, "model", 11434)
        for summary in report.levels:
            with self.subTest(concurrency=summary.concurrency):
                expected = per_level[summary.concurrency]
                self.assertEqual(summary.requests, request_count)
                self.assertEqual(summary.succeeded, request_count)
                self.assertEqual(summary.failed, 0)
                # Clean level: empty buckets, no raw messages.
                self.assertEqual(summary.error_counts, {})
                self.assertEqual(summary.errors, [])
                # Every figure collapses to the single canned latency.
                self.assertAlmostEqual(summary.latency_mean, expected)
                self.assertAlmostEqual(summary.latency_p50, expected)
                self.assertAlmostEqual(summary.latency_p95, expected)
                self.assertAlmostEqual(summary.latency_p99, expected)
                self.assertAlmostEqual(summary.latency_min, expected)
                self.assertAlmostEqual(summary.latency_max, expected)

    def test_completed_is_true_for_a_clean_run(self):
        levels = [1, 2]
        request_count = 2
        warm = stress.WarmUpResult(
            ok=True, attempts=1, elapsed_seconds=10.0, error=None
        )
        send = _LevelSend(
            [[_ok_outcome(0.5) for _ in range(request_count)] for _ in levels],
            request_count,
        )
        report = self._run(send, levels, request_count, warm, "model", 8080)
        self.assertTrue(report.completed)

    def test_send_called_request_count_times_per_level(self):
        levels = [1, 2, 4]
        request_count = 3
        warm = stress.WarmUpResult(
            ok=True, attempts=1, elapsed_seconds=10.0, error=None
        )
        send = _LevelSend(
            [[_ok_outcome(0.5) for _ in range(request_count)] for _ in levels],
            request_count,
        )
        self._run(send, levels, request_count, warm, "model", 8080)
        self.assertEqual(send.calls, len(levels) * request_count)


class TestRunStressContinuesAfterFailedLevel(unittest.TestCase):
    """Behaviour 13: the load-bearing rule.

    Every level runs even if an earlier one failed completely: "fine at 1
    and 2, dies at 4" is the finding, not a reason to stop. A level that
    fails entirely is recorded -- with ``None`` latency figures and its
    error buckets filled -- and the run continues to the next level.
    """

    def _run(self, send, levels, request_count, warm_up_result, model_id, port):
        if run_stress is None:
            self.fail(
                "anvilkit.stress.run_stress is not implemented yet: "
                "{}".format(_run_stress_import_error)
            )
        return run_stress(
            send, levels, request_count, warm_up_result, model_id, port
        )

    def test_plan_script_succeed_at_1_and_2_fail_at_4(self):
        # The plan's own scripted case: succeed at levels 1 and 2, fail
        # every request at level 4, and all three summaries are present,
        # in order 1, 2, 4.
        levels = [1, 2, 4]
        request_count = 3
        warm = stress.WarmUpResult(
            ok=True, attempts=1, elapsed_seconds=42.1, error=None
        )
        send = _LevelSend(
            [
                [_ok_outcome(0.5) for _ in range(request_count)],
                [_ok_outcome(1.0) for _ in range(request_count)],
                [
                    _failed_outcome(
                        "CUDA out of memory", http_status=500
                    )
                    for _ in range(request_count)
                ],
            ],
            request_count,
        )
        report = self._run(send, levels, request_count, warm, "model", 8080)
        self.assertEqual(
            [summary.concurrency for summary in report.levels], levels
        )
        by_level = {summary.concurrency: summary for summary in report.levels}
        # The healthy levels are untouched by the dying one.
        for level in (1, 2):
            with self.subTest(concurrency=level):
                self.assertEqual(by_level[level].succeeded, request_count)
                self.assertEqual(by_level[level].failed, 0)
                self.assertEqual(by_level[level].error_counts, {})
                self.assertEqual(by_level[level].errors, [])
        # The dying level is recorded, not hidden: no successes, every
        # latency figure None, the OOM bucketed and the raw text kept.
        dying = by_level[4]
        self.assertEqual(dying.succeeded, 0)
        self.assertEqual(dying.failed, request_count)
        self.assertIsNone(dying.latency_mean)
        self.assertIsNone(dying.latency_p50)
        self.assertIsNone(dying.latency_p95)
        self.assertIsNone(dying.latency_p99)
        self.assertIsNone(dying.latency_min)
        self.assertIsNone(dying.latency_max)
        self.assertEqual(dying.error_counts, {"oom": request_count})
        self.assertEqual(dying.errors, ["CUDA out of memory"])
        # Reaching the end IS completion, even with failures: this is the
        # run that earns exit 8 downstream, not a run that was abandoned.
        self.assertTrue(report.completed)
        # All three levels really ran: the full request budget was spent.
        self.assertEqual(send.calls, len(levels) * request_count)

    def test_later_levels_still_run_after_earlier_level_failed_completely(
        self
    ):
        # The edge-case wording in the plan: an EARLIER level failing
        # completely must not stop the ramp -- level 1 dies and levels 2
        # and 4 must still run and be recorded.
        levels = [1, 2, 4]
        request_count = 2
        warm = stress.WarmUpResult(
            ok=True, attempts=1, elapsed_seconds=42.1, error=None
        )
        send = _LevelSend(
            [
                [
                    _failed_outcome(
                        "CUDA out of memory", http_status=500
                    )
                    for _ in range(request_count)
                ],
                [_ok_outcome(1.0) for _ in range(request_count)],
                [_ok_outcome(2.0) for _ in range(request_count)],
            ],
            request_count,
        )
        report = self._run(send, levels, request_count, warm, "model", 8080)
        self.assertEqual(
            [summary.concurrency for summary in report.levels], levels
        )
        by_level = {summary.concurrency: summary for summary in report.levels}
        self.assertEqual(by_level[1].succeeded, 0)
        self.assertEqual(by_level[1].failed, request_count)
        self.assertEqual(by_level[1].error_counts, {"oom": request_count})
        self.assertEqual(by_level[2].succeeded, request_count)
        self.assertEqual(by_level[2].failed, 0)
        self.assertAlmostEqual(by_level[2].latency_mean, 1.0)
        self.assertEqual(by_level[4].succeeded, request_count)
        self.assertEqual(by_level[4].failed, 0)
        self.assertAlmostEqual(by_level[4].latency_mean, 2.0)
        self.assertTrue(report.completed)
        self.assertEqual(send.calls, len(levels) * request_count)

    def test_every_level_failing_still_yields_the_full_report(self):
        # The strongest form: total failure at every level. The run still
        # reaches the end and reports all levels -- learning that nothing
        # worked is itself the finding.
        levels = [1, 2]
        request_count = 2
        warm = stress.WarmUpResult(
            ok=True, attempts=1, elapsed_seconds=42.1, error=None
        )
        send = _LevelSend(
            [
                [
                    _failed_outcome("connection refused")
                    for _ in range(request_count)
                ]
                for _ in levels
            ],
            request_count,
        )
        report = self._run(send, levels, request_count, warm, "model", 8080)
        self.assertEqual(
            [summary.concurrency for summary in report.levels], levels
        )
        for summary in report.levels:
            with self.subTest(concurrency=summary.concurrency):
                self.assertEqual(summary.requests, request_count)
                self.assertEqual(summary.succeeded, 0)
                self.assertEqual(summary.failed, request_count)
                self.assertIsNone(summary.latency_mean)
                self.assertEqual(
                    summary.error_counts, {"connection": request_count}
                )
        self.assertTrue(report.completed)
        self.assertEqual(send.calls, len(levels) * request_count)


class TestRunStressLevelOrder(unittest.TestCase):
    """Behaviour 13: levels execute in ascending order, as a progression."""

    def _run(self, send, levels, request_count, warm_up_result, model_id, port):
        if run_stress is None:
            self.fail(
                "anvilkit.stress.run_stress is not implemented yet: "
                "{}".format(_run_stress_import_error)
            )
        return run_stress(
            send, levels, request_count, warm_up_result, model_id, port
        )

    def test_report_reads_as_the_ascending_progression(self):
        # Distinct per-level latencies prove that each summary is the
        # summary of its own level, in the order the levels ran.
        per_level = {1: 0.25, 2: 0.5, 4: 1.0, 8: 2.0}
        levels = [1, 2, 4, 8]
        request_count = 2
        warm = stress.WarmUpResult(
            ok=True, attempts=1, elapsed_seconds=42.1, error=None
        )
        send = _LevelSend(
            [
                [_ok_outcome(per_level[level]) for _ in range(request_count)]
                for level in levels
            ],
            request_count,
        )
        report = self._run(send, levels, request_count, warm, "model", 8080)
        self.assertEqual(
            [summary.concurrency for summary in report.levels], levels
        )
        for summary in report.levels:
            with self.subTest(concurrency=summary.concurrency):
                self.assertAlmostEqual(
                    summary.latency_mean, per_level[summary.concurrency]
                )


class TestRunStressReportType(unittest.TestCase):
    """The result type contract from behaviour 13 of the plan."""

    def test_stress_report_is_a_dataclass(self):
        if StressReport is None:
            self.fail(
                "anvilkit.stress.StressReport is not implemented yet: "
                "{}".format(_run_stress_import_error)
            )
        self.assertTrue(dataclasses.is_dataclass(StressReport))


# ---------------------------------------------------------------------------
# Behaviour 14: format_report renders the human report.
#
# The report is hand-built from the plan §15 shape: StressReport carries
# ``model_id``, ``port``, ``started_at``, ``prompt``, ``max_tokens``,
# ``requests_per_level``, ``warm_up``, ``levels``, ``completed`` and a
# ``max_clean_concurrency`` figure (highest concurrency with zero failures,
# ``None`` when even level 1 failed). The current dataclass does not have the
# new fields yet; constructing with them is an acceptable named red for this
# step.
# ---------------------------------------------------------------------------

_FORMAT_REPORT_FIELDS = (
    "started_at",
    "prompt",
    "max_tokens",
    "requests_per_level",
    "max_clean_concurrency",
)


def _fr_summary(
    concurrency,
    succeeded=None,
    failed=None,
    latency_mean=1.1,
    latency_p50=1.0,
    latency_p95=1.4,
    latency_p99=1.5,
    latency_min=0.9,
    latency_max=1.5,
    requests_per_second=0.9,
    tokens_per_second=115.2,
    error_counts=None,
    errors=None,
):
    """A hand-built ``LevelSummary`` with chosen fields.

    Defaults are a clean level's figures, so callers pin exactly what they
    need to vary.
    """
    if succeeded is None:
        succeeded = 20 - (failed or 0)
    return stress.LevelSummary(
        concurrency=concurrency,
        requests=succeeded + (failed or 0),
        succeeded=succeeded,
        failed=failed or 0,
        latency_mean=latency_mean,
        latency_p50=latency_p50,
        latency_p95=latency_p95,
        latency_p99=latency_p99,
        latency_min=latency_min,
        latency_max=latency_max,
        requests_per_second=requests_per_second,
        tokens_per_second=tokens_per_second,
        error_counts=error_counts or {},
        errors=errors or [],
    )


def _fr_report(model_id="model-a", port=8080, levels=None, **overrides):
    """A hand-built ``StressReport`` in the plan §15 shape.

    ``overrides`` supplies any field the current dataclass lacks (a named
    red); once the dataclass is extended it also lets cases vary them.
    """
    warm = stress.WarmUpResult(
        ok=True, attempts=1, elapsed_seconds=42.1, error=None
    )
    fields = {
        "model_id": model_id,
        "port": port,
        "started_at": "2026-08-21T14:30:00Z",
        "prompt": "count to ten",
        "max_tokens": 128,
        "requests_per_level": 20,
        "warm_up": warm,
        "levels": levels if levels is not None else [_fr_summary(1)],
        "completed": True,
        "max_clean_concurrency": None,
    }
    fields.update(overrides)
    return stress.StressReport(**fields)


def _fr_render(report, use_color=True):
    if format_report is None:
        raise AssertionError(
            "anvilkit.stress.format_report is not implemented yet: "
            + (_format_report_import_error or "missing")
        )
    return format_report(report, use_color=use_color)


def _row_for(text, concurrency, okfail="20/0"):
    """The table row that carries the level's figures for ``concurrency``.

    The row is identified by its concurrency and its ok/fail split, so a
    call for one level cannot be answered by another level's row.
    """
    for line in text.splitlines():
        if str(concurrency) in line and okfail in line:
            return line
    return None


class TestFormatReportHeaderAndWarmUp(unittest.TestCase):
    """Behaviour 14: header (model, port, timestamp, request count) and the
    warm-up line."""

    def test_header_shows_model_port_timestamp_and_request_count(self):
        report = _fr_report(
            model_id="deepseek-ai/DeepSeek-V3.2", port=8123
        )
        text = _fr_render(report, use_color=False)
        self.assertIn("deepseek-ai/DeepSeek-V3.2", text)
        self.assertIn("8123", text)
        # The timestamp is the report's ``started_at``, not the render time.
        self.assertIn("2026-08-21T14:30:00Z", text)
        # The per-level request count from the header.
        self.assertIn("20", text)

    def test_warm_up_line_shows_attempts_and_elapsed_when_ok(self):
        report = _fr_report()
        text = _fr_render(report, use_color=False)
        self.assertIn("42.1", text)

    def test_warm_up_line_shows_the_failure_when_not_ok(self):
        report = _fr_report(
            warm_up=stress.WarmUpResult(
                ok=False,
                attempts=3,
                elapsed_seconds=120.5,
                error="connect: connection refused",
            )
        )
        text = _fr_render(report, use_color=False)
        self.assertIn("connection refused", text)


class TestFormatReportLevelTable(unittest.TestCase):
    """Behaviour 14: the per-level table, one row per level, aligned."""

    def test_each_level_row_carries_its_concurrency_and_figures(self):
        # Distinct figures per level prove each row is its own level's.
        levels = [
            _fr_summary(
                1,
                latency_mean=0.5,
                latency_p50=0.5,
                latency_p95=0.5,
                latency_p99=0.5,
                latency_min=0.5,
                latency_max=0.5,
                requests_per_second=2.0,
                tokens_per_second=256.0,
            ),
            _fr_summary(
                4,
                latency_mean=2.5,
                latency_p50=2.5,
                latency_p95=2.5,
                latency_p99=2.5,
                latency_min=2.5,
                latency_max=2.5,
                requests_per_second=0.5,
                tokens_per_second=64.0,
            ),
        ]
        report = _fr_report(levels=levels, max_clean_concurrency=4)
        text = _fr_render(report, use_color=False)
        row1 = _row_for(text, 1)
        row4 = _row_for(text, 4)
        self.assertIsNotNone(row1)
        self.assertIsNotNone(row4)
        self.assertIn("0.50", row1)
        self.assertIn("2.00", row1)
        self.assertIn("256.00", row1)
        self.assertIn("2.50", row4)
        self.assertIn("0.50", row4)
        self.assertIn("64.00", row4)
        # The all-failed column still shows the true 0.0 rates for the
        # clean levels' siblings, but each row shows its OWN ok/fail split.
        self.assertIn("20/0", row1)
        self.assertIn("20/0", row4)

    def test_unmeasurable_figures_render_dashes_never_fabricated_zeros(self):
        # A level whose figures are all ``None`` (no successes, and no
        # wall time to measure rates over): every numeric column must be
        # ``-``, and a fabricated ``0.00`` must not appear anywhere in the
        # report, because no figure is genuinely zero.
        levels = [
            _fr_summary(1),
            _fr_summary(
                4,
                succeeded=0,
                failed=20,
                latency_mean=None,
                latency_p50=None,
                latency_p95=None,
                latency_p99=None,
                latency_min=None,
                latency_max=None,
                requests_per_second=None,
                tokens_per_second=None,
                error_counts={"connection": 20},
                errors=["connection refused"],
            ),
        ]
        report = _fr_report(levels=levels, max_clean_concurrency=1)
        text = _fr_render(report, use_color=False)
        row = _row_for(text, 4, okfail="0/20")
        self.assertIsNotNone(row)
        # Every unmeasurable column renders ``-``.
        self.assertIn("-", row)
        # ...and never a fabricated ``0.00``.
        self.assertNotIn("0.00", text)

    def test_all_failed_level_shows_true_zero_rates_as_zero(self):
        # The summary contract: an all-failed level reports ``0.0`` for both
        # rates (a true statement: nothing got through) and ``None`` for the
        # latency figures. The dashes belong to the latency columns only;
        # the rates are stated as zero.
        levels = [
            _fr_summary(
                2,
                succeeded=0,
                failed=20,
                latency_mean=None,
                latency_p50=None,
                latency_p95=None,
                latency_p99=None,
                latency_min=None,
                latency_max=None,
                requests_per_second=0.0,
                tokens_per_second=0.0,
                error_counts={"oom": 20},
                errors=["CUDA out of memory"],
            ),
        ]
        report = _fr_report(levels=levels, max_clean_concurrency=None)
        text = _fr_render(report, use_color=False)
        row = _row_for(text, 2, okfail="0/20")
        self.assertIsNotNone(row)
        # The true zero rates are stated as zero in some form (0.00, 0.0
        # or 0), and the latency figures are dashes, not zeros.
        self.assertRegex(row, r"\b0(\.0+)?\b")
        self.assertIn("-", row)

    def test_failing_level_lists_error_categories_and_raw_messages(self):
        levels = [
            _fr_summary(
                2,
                succeeded=10,
                failed=10,
                latency_mean=1.5,
                latency_p50=1.4,
                latency_p95=2.2,
                latency_p99=2.4,
                latency_min=1.1,
                latency_max=2.4,
                requests_per_second=0.4,
                tokens_per_second=51.2,
                error_counts={
                    "connection": 6,
                    "oom": 3,
                    "server_error": 1,
                },
                errors=[
                    "connection refused",
                    "CUDA out of memory",
                    "internal error",
                ],
            ),
        ]
        report = _fr_report(levels=levels, max_clean_concurrency=None)
        text = _fr_render(report, use_color=False)
        # Categories with their counts.
        self.assertIn("connection", text)
        self.assertIn("6", text)
        self.assertIn("oom", text)
        self.assertIn("3", text)
        # The raw messages, verbatim.
        self.assertIn("connection refused", text)
        self.assertIn("CUDA out of memory", text)
        self.assertIn("internal error", text)

    def test_clean_level_lists_no_error_section(self):
        report = _fr_report(levels=[_fr_summary(1)], max_clean_concurrency=1)
        text = _fr_render(report, use_color=False)
        self.assertNotIn("connection refused", text)
        self.assertNotIn("error_counts", text)

    def test_long_model_id_does_not_break_table_alignment(self):
        long_id = (
            "deepseek-ai/DeepSeek-V3.2-R1-SFT-Long-Horizon-"
            "235B-A22B-Instruct-128K-vllm-awq-gptq"
        )
        report = _fr_report(
            model_id=long_id,
            levels=[_fr_summary(1), _fr_summary(2), _fr_summary(4)],
            max_clean_concurrency=4,
        )
        text = _fr_render(report, use_color=False)
        self.assertIn(long_id, text)
        rows = [
            _row_for(text, concurrency) for concurrency in (1, 2, 4)
        ]
        for row in rows:
            self.assertIsNotNone(row)
        # Every data row carries the same ok/fail split, so the split
        # column must start at the same offset in each row regardless of
        # the long model id in the header above the table.
        positions = {row.index("20/0") for row in rows}
        self.assertEqual(len(positions), 1)


class TestFormatReportColor(unittest.TestCase):
    """Behaviour 14: colour is suppressed under ``--no-color``."""

    def test_no_color_suppresses_ansi_escapes(self):
        report = _fr_report(
            levels=[
                _fr_summary(1),
                _fr_summary(
                    4,
                    succeeded=0,
                    failed=20,
                    latency_mean=None,
                    latency_p50=None,
                    latency_p95=None,
                    latency_p99=None,
                    latency_min=None,
                    latency_max=None,
                    requests_per_second=0.0,
                    tokens_per_second=0.0,
                    error_counts={"oom": 20},
                    errors=["CUDA out of memory"],
                ),
            ],
            max_clean_concurrency=1,
        )
        text = _fr_render(report, use_color=False)
        self.assertNotIn("\x1b[", text)


class TestFormatReportClosingSummary(unittest.TestCase):
    """Behaviour 14: the closing summary names the highest concurrency that
    completed with zero failures."""

    def test_closing_summary_names_highest_clean_concurrency(self):
        # Clean through 8, failing at 16: the summary must name 8.
        levels = [_fr_summary(concurrency) for concurrency in (1, 2, 4, 8)]
        levels.append(
            _fr_summary(
                16,
                succeeded=0,
                failed=20,
                latency_mean=None,
                latency_p50=None,
                latency_p95=None,
                latency_p99=None,
                latency_min=None,
                latency_max=None,
                requests_per_second=0.0,
                tokens_per_second=0.0,
                error_counts={"oom": 20},
                errors=["CUDA out of memory"],
            )
        )
        report = _fr_report(levels=levels, max_clean_concurrency=8)
        text = _fr_render(report, use_color=False)
        # The closing summary names the highest clean concurrency: 8.
        # Allow both "concurrency 8" and "concurrency: 8" spellings.
        self.assertRegex(text, r"concurrency\s*:?\s*8\b")
        # And it must not overclaim the level that failed.
        self.assertNotRegex(text, r"concurrency\s*:?\s*16\b")

    def test_closing_summary_says_so_when_even_level_1_failed(self):
        # Every level failed: there is no clean concurrency, and the
        # summary must say so rather than naming a level.
        levels = [
            _fr_summary(
                concurrency,
                succeeded=0,
                failed=20,
                latency_mean=None,
                latency_p50=None,
                latency_p95=None,
                latency_p99=None,
                latency_min=None,
                latency_max=None,
                requests_per_second=0.0,
                tokens_per_second=0.0,
                error_counts={"connection": 20},
                errors=["connection refused"],
            )
            for concurrency in (1, 2)
        ]
        report = _fr_report(levels=levels, max_clean_concurrency=None)
        text = _fr_render(report, use_color=False)
        self.assertNotRegex(text, r"concurrency\s*:?\s*1\b")
        # The plan's wording for the no-clean case: say so explicitly.
        self.assertRegex(text.lower(), r"no clean concurrency")

    def test_never_raises(self):
        # Pure rendering: an unusual but valid report must not raise.
        report = _fr_report(
            model_id="model-a",
            levels=[],
            max_clean_concurrency=None,
            warm_up=stress.WarmUpResult(
                ok=False,
                attempts=0,
                elapsed_seconds=0.0,
                error="model never came up",
            ),
        )
        # Must return a string without raising.
        self.assertIsInstance(_fr_render(report, use_color=False), str)


# ---------------------------------------------------------------------------
# Behaviour 15: format_report_json renders the machine-readable summary.
#
# The output is a JSON document built as a dict and emitted with
# ``json.dumps(..., indent=2)``. The contract is the round trip: the tests
# parse the output with ``json.loads`` and assert on the PARSED structure,
# never on the raw string. The plan's key names differ from the dataclass
# field names in two places: ``model_id`` becomes the key ``"model"``, and
# the six flat ``latency_*`` fields nest under the key ``"latency"``.
# ---------------------------------------------------------------------------


def _frj_render(report):
    if format_report_json is None:
        raise AssertionError(
            "anvilkit.stress.format_report_json is not implemented yet: "
            + (_format_report_json_import_error or "missing")
        )
    return format_report_json(report)


def _frj_parse(report):
    """Render and round-trip: the contract is that the output parses."""
    return json.loads(_frj_render(report))


class TestFormatReportJsonShape(unittest.TestCase):
    """Behaviour 15: the document's top-level keys and values, parsed."""

    def test_top_level_keys_match_the_plan_shape(self):
        doc = _frj_parse(
            _fr_report(
                model_id="deepseek-ai/DeepSeek-V3.2",
                port=8123,
                max_clean_concurrency=8,
            )
        )
        self.assertEqual(
            sorted(doc),
            [
                "completed",
                "levels",
                "max_clean_concurrency",
                "max_tokens",
                "model",
                "port",
                "prompt",
                "requests_per_level",
                "started_at",
                "warm_up",
            ],
        )

    def test_top_level_values_pass_through(self):
        # The field name differs from the JSON key: the dataclass carries
        # ``model_id``, the document carries ``"model"``.
        report = _fr_report(
            model_id="deepseek-ai/DeepSeek-V3.2",
            port=8123,
            max_clean_concurrency=8,
        )
        doc = _frj_parse(report)
        self.assertEqual(doc["model"], "deepseek-ai/DeepSeek-V3.2")
        self.assertEqual(doc["port"], 8123)
        self.assertEqual(doc["started_at"], "2026-08-21T14:30:00Z")
        self.assertEqual(doc["prompt"], "count to ten")
        self.assertEqual(doc["max_tokens"], 128)
        self.assertEqual(doc["requests_per_level"], 20)
        self.assertIs(doc["completed"], True)
        self.assertEqual(doc["max_clean_concurrency"], 8)

    def test_warm_up_object_round_trips(self):
        report = _fr_report(
            warm_up=stress.WarmUpResult(
                ok=False,
                attempts=3,
                elapsed_seconds=61.5,
                error="model never came up",
            )
        )
        doc = _frj_parse(report)
        self.assertEqual(
            doc["warm_up"],
            {"ok": False, "attempts": 3, "elapsed_seconds": 61.5, "error": "model never came up"},
        )

    def test_warm_up_error_is_null_when_ok(self):
        doc = _frj_parse(_fr_report(max_clean_concurrency=1))
        self.assertEqual(
            doc["warm_up"],
            {"ok": True, "attempts": 1, "elapsed_seconds": 42.1, "error": None},
        )

    def test_levels_preserve_order_and_carry_full_row(self):
        # Distinct figures per level prove each object is its own level's.
        levels = [
            _fr_summary(1),
            _fr_summary(4, latency_mean=2.2, latency_p50=2.0, latency_p95=2.4,
                        latency_p99=2.5, latency_min=1.9, latency_max=2.5,
                        requests_per_second=1.8, tokens_per_second=230.4),
        ]
        doc = _frj_parse(_frj_report(levels, max_clean_concurrency=4))
        self.assertEqual(len(doc["levels"]), 2)
        self.assertEqual(
            doc["levels"][0],
            {
                "concurrency": 1,
                "requests": 20,
                "succeeded": 20,
                "failed": 0,
                "latency": {
                    "mean": 1.1, "p50": 1.0, "p95": 1.4,
                    "p99": 1.5, "min": 0.9, "max": 1.5,
                },
                "requests_per_second": 0.9,
                "tokens_per_second": 115.2,
                "error_counts": {},
                "errors": [],
            },
        )
        self.assertEqual(doc["levels"][1]["concurrency"], 4)
        self.assertEqual(
            doc["levels"][1]["latency"],
            {"mean": 2.2, "p50": 2.0, "p95": 2.4,
             "p99": 2.5, "min": 1.9, "max": 2.5},
        )
        self.assertEqual(doc["levels"][1]["requests_per_second"], 1.8)
        self.assertEqual(doc["levels"][1]["tokens_per_second"], 230.4)

    def test_level_error_fields_round_trip(self):
        levels = [
            _fr_summary(
                2,
                failed=5,
                requests_per_second=0.4,
                tokens_per_second=51.2,
                error_counts={"oom": 3, "timeout": 2},
                errors=["CUDA out of memory", "timed out"],
            )
        ]
        doc = _frj_parse(_frj_report(levels, max_clean_concurrency=None))
        row = doc["levels"][0]
        self.assertEqual(row["requests"], 20)
        self.assertEqual(row["succeeded"], 15)
        self.assertEqual(row["failed"], 5)
        self.assertEqual(row["error_counts"], {"oom": 3, "timeout": 2})
        self.assertEqual(row["errors"], ["CUDA out of memory", "timed out"])

    def test_empty_levels_round_trips_as_empty_list(self):
        doc = _frj_parse(
            _frj_report([], max_clean_concurrency=None)
        )
        self.assertEqual(doc["levels"], [])


class TestFormatReportJsonEdgeCases(unittest.TestCase):
    """Behaviour 15: the edge cases the plan pins."""

    def test_absent_latency_figures_are_null_not_zero(self):
        # An all-failed level: every latency figure is ``None`` on the
        # summary, and the document must carry ``null`` for each -- a
        # renderer that coerces ``None`` to ``0`` would fabricate latencies.
        levels = [
            _fr_summary(
                1,
                succeeded=0,
                failed=20,
                latency_mean=None,
                latency_p50=None,
                latency_p95=None,
                latency_p99=None,
                latency_min=None,
                latency_max=None,
                requests_per_second=0.0,
                tokens_per_second=0.0,
                error_counts={"connection": 20},
                errors=["connection refused"],
            )
        ]
        doc = _frj_parse(_frj_report(levels, max_clean_concurrency=None))
        row = doc["levels"][0]
        self.assertEqual(row["latency"], {
            "mean": None, "p50": None, "p95": None,
            "p99": None, "min": None, "max": None,
        })
        # The rates on an all-failed level are a TRUE zero, not absent:
        # they must survive the round trip as 0.0, distinct from the nulls.
        self.assertEqual(row["requests_per_second"], 0.0)
        self.assertEqual(row["tokens_per_second"], 0.0)

    def test_max_clean_concurrency_is_null_when_level_1_failed(self):
        # Level 1 itself had failures, so there is no clean level to anchor
        # on: ``max_clean_concurrency`` is legitimately ``None``.
        levels = [
            _fr_summary(
                1,
                succeeded=15,
                failed=5,
                error_counts={"timeout": 5},
                errors=["timed out"],
            )
        ]
        doc = _frj_parse(_frj_report(levels, max_clean_concurrency=None))
        self.assertIsNone(doc["max_clean_concurrency"])

    def test_raw_output_is_pure_json_with_no_python_repr_artifacts(self):
        # The round trip is the contract; this guards the extra case where
        # Python repr leaks into the emitted string (single quotes,
        # ``None``/``True`` literals that are not JSON).
        report = _fr_report(max_clean_concurrency=8)
        raw = _frj_render(report)
        self.assertIsInstance(raw, str)
        json.loads(raw)  # must not raise
        self.assertNotIn("None", raw)
        self.assertNotIn("'", raw)
        self.assertNotIn("True", raw)


def _frj_report(levels, **overrides):
    """A hand-built ``StressReport`` for the JSON cases.

    A thin alias over ``_fr_report`` so the JSON section reads in terms of
    its own shape without touching the behaviour-14 helpers.
    """
    return _fr_report(levels=levels, **overrides)


# ---------------------------------------------------------------------------
# Behaviour 16: write_log persists the finished report to the derived path.
#
# Contract (plans/stress-test.md, section 7, behaviour 16):
# ``write_log(path, text_report, json_report) -> None`` creates the parent
# directory if absent and writes the text report, then a separator, then the
# JSON summary block, into the file at ``path``. An existing file is
# overwritten. Both forms are written VERBATIM -- the function renders
# nothing. An unwritable directory raises ``StressError`` naming the path.
#
# The CLI concerns the plan attaches to this behaviour (``--no-log-file``
# skips the call, ``--dry-run`` announces the path and writes nothing) are
# behaviour 17's and are deliberately NOT tested here: at this level
# ``write_log`` is simply called, or not.
#
# The unwritable-directory case mocks the write seam rather than using
# ``os.chmod``: a chmod-based test silently passes for the wrong reason when
# the suite runs as root (CI containers often do). ``pathlib.Path.write_text``
# opens via a C-level path that a ``builtins.open`` patch does not intercept
# (verified on this host), so BOTH ``builtins.open`` and ``Path.write_text``
# are patched to fail -- whatever seam the implementation picks, the
# ``PermissionError`` it would hit for real is simulated.
# ---------------------------------------------------------------------------

# A multi-line text report with a trailing blank line and a non-trivial JSON
# document: the verbatim cases assert both survive intact.
_wl_text_report = (
    "stress run: deepseek-ai/DeepSeek-V3.2\n"
    "port 8123, levels 1, 2, 4, 8\n"
    "warm up: ok in 1 attempt (42.1s)\n"
    "\n"
    "concurrency  1  20/20 ok  1.10s mean  0.9 req/s\n"
    "concurrency  4  15/20 ok  2.20s mean  1.8 req/s\n"
)
_wl_json_doc = {
    "model": "deepseek-ai/DeepSeek-V3.2",
    "port": 8123,
    "completed": True,
    "max_clean_concurrency": 1,
    "levels": [
        {"concurrency": 1, "succeeded": 20, "failed": 0},
        {"concurrency": 4, "succeeded": 15, "failed": 5},
    ],
}
_wl_json_report = json.dumps(_wl_json_doc, indent=2)


def _wl_write(path, text_report, json_report):
    """Call ``write_log`` or fail with the named red for a missing symbol."""
    if write_log is None:
        raise AssertionError(
            "anvilkit.stress.write_log is not implemented yet: "
            + (_write_log_import_error or "missing")
        )
    return write_log(path, text_report, json_report)


def _wl_block_from_content(path, json_report):
    """The JSON summary block of a written file, as a string.

    The text report comes first, then a separator, then the JSON block, so
    the block is the file content from the JSON text to the end. ``rindex``
    keeps this honest even if the text report itself contained a brace.
    """
    content = path.read_text()
    return content[content.rindex(json_report):]


def _wl_block_parsed(path, json_report):
    """The written JSON block, round-tripped: the contract is it parses."""
    return json.loads(_wl_block_from_content(path, json_report))


class TestWriteLogFileCreation(TestCase):
    """Behaviour 16: the file lands at the path, parent created, no return."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_parent_directory_is_created_when_absent(self):
        # Nested, not just ``logs``: the contract is "the parent directory is
        # created if absent", at any depth under the run root.
        path = self.root / "logs" / "nested" / "deeper" / "stress-model.log"
        self.assertFalse(path.parent.exists())
        _wl_write(path, _wl_text_report, _wl_json_report)
        self.assertTrue(path.parent.is_dir())
        self.assertTrue(path.is_file())

    def test_returns_none(self):
        path = self.root / "logs" / "stress-model.log"
        self.assertIsNone(_wl_write(path, _wl_text_report, _wl_json_report))


class TestWriteLogContent(TestCase):
    """Behaviour 16: text report, separator, JSON block -- both verbatim."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.path = self.root / "logs" / "stress-model.log"

    def test_text_report_first_then_separator_then_json_block(self):
        # A literal ``\n`` sequence in the text report (backslash + n, not a
        # newline) must survive verbatim: an implementation that re-parses
        # or re-renders the report would corrupt it.
        text_report = "TEXT-REPORT-ANCHOR\\nline two\n"
        _wl_write(self.path, text_report, _wl_json_report)
        content = self.path.read_text()
        text_idx = content.index("TEXT-REPORT-ANCHOR")
        json_idx = content.index(_wl_json_report)
        self.assertLess(text_idx, json_idx)
        self.assertIn(text_report, content)

    def test_json_block_parses_and_matches_input(self):
        _wl_write(self.path, _wl_text_report, _wl_json_report)
        self.assertEqual(_wl_block_parsed(self.path, _wl_json_report), _wl_json_doc)

    def test_text_report_written_verbatim(self):
        # Multi-line, with a trailing blank line: no trimming, no
        # re-flowing, no truncation.
        _wl_write(self.path, _wl_text_report, _wl_json_report)
        self.assertIn(_wl_text_report, self.path.read_text())

    def test_json_block_written_verbatim(self):
        # The emitted block is the argument's text: a reader that re-dumps
        # with different indentation or key order writes different bytes.
        _wl_write(self.path, _wl_text_report, _wl_json_report)
        self.assertEqual(_wl_block_from_content(self.path, _wl_json_report), _wl_json_report)


class TestWriteLogOverwrite(TestCase):
    """Behaviour 16: an existing file at the path is overwritten."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "logs" / "stress-model.log"
        self.path.parent.mkdir(parents=True)

    def test_existing_file_replaced_by_new_content(self):
        first_text = "FIRST-RUN-REPORT\n"
        first_json = json.dumps({"run": 1}, indent=2)
        _wl_write(self.path, first_text, first_json)
        self.assertTrue(self.path.is_file())

        # The derived path carries a second-resolution timestamp, so real
        # collisions are practically impossible -- but when the same path IS
        # written again, the new report is the whole file: no appending.
        second_text = "SECOND-RUN-REPORT\n"
        second_json = json.dumps({"run": 2}, indent=2)
        _wl_write(self.path, second_text, second_json)

        content = self.path.read_text()
        self.assertNotIn("FIRST-RUN-REPORT", content)
        self.assertIn(second_text, content)
        self.assertEqual(_wl_block_parsed(self.path, second_json), {"run": 2})


class TestWriteLogErrors(TestCase):
    """Behaviour 16: an unwritable directory raises StressError naming the path."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.path = self.root / "logs" / "stress-model.log"

    def test_unwritable_directory_raises_stress_error_naming_the_path(self):
        # Guarded before ``assertRaises`` so the named red, not
        # "StressError not raised", is the failure while the symbol is
        # missing (the behaviour-10 error cases do the same).
        if write_log is None:
            self.fail(
                "anvilkit.stress.write_log is not implemented yet: "
                "{}".format(_write_log_import_error)
            )
        # chmod(555) would be unreliable as root -- root writes anyway -- so
        # the write seam is mocked to fail instead (see section comment).
        with mock.patch(
            "builtins.open",
            side_effect=PermissionError(13, "Permission denied"),
        ) as open_mock, mock.patch(
            "pathlib.Path.write_text",
            side_effect=PermissionError(13, "Permission denied"),
        ) as write_text_mock:
            with self.assertRaises(stress.StressError) as ctx:
                _wl_write(self.path, _wl_text_report, _wl_json_report)
        message = str(ctx.exception)
        self.assertIn(str(self.path), message)
        # The failure came from the write attempt, not from anywhere else.
        self.assertTrue(open_mock.called or write_text_mock.called)


if __name__ == "__main__":
    unittest.main()
