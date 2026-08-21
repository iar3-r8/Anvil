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

Behaviours 4, 5 and 13-16 land in this same file in later cycles.

The module is a pure-function module for these behaviours: no network, no
real clock, no I/O. The warm-up tests inject ``send``, ``sleep`` and the
clock as spies and fakes, and the level tests inject ``send`` as a
thread-safe spy; assertions are on returned data structures only.
"""

import dataclasses
import sys
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
