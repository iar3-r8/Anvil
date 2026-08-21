"""Tests for anvilkit.stress.

Written before the implementation (TDD).

Current scope: behaviours 1-3 and 6-8 of plans/stress-test.md --
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
exactly once and ``sleep`` never runs.

Behaviours 4, 5 and 9-16 land in this same file in later cycles.

The module is a pure-function module for these behaviours: no network, no
real clock, no I/O. The warm-up tests inject ``send``, ``sleep`` and the
clock as spies and fakes; assertions are on returned data structures only.
"""

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import stress  # noqa: E402
from anvilkit.health import ChatOutcome  # noqa: E402
from anvilkit.stress import (  # noqa: E402
    classify_error,
    log_path,
    percentile,
    warm_up,
)


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


if __name__ == "__main__":
    unittest.main()
