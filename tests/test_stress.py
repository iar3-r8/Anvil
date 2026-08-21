"""Tests for anvilkit.stress.

Written before the implementation (TDD).

Current scope: behaviours 1-3 of plans/stress-test.md --
``concurrency_levels(max_concurrency)`` derives the level series from a single
maximum: 1, then each power of two up to the maximum, then the maximum itself
if it is not already a power of two; ``percentile(values, p)`` is the
nearest-rank percentile (no interpolation): sort ascending, take index
``ceil(p/100 * n) - 1`` clamped to ``[0, n-1]``; ``log_path(root, model_id,
when)`` derives the log file name under ``root/logs`` from a sanitised model
id and an injected UTC timestamp.

Behaviours 4, 5 and 6-16 land in this same file in later cycles.

The module is a pure-function module for these behaviours: no mocks, no I/O,
assertions on returned data structures only.
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
from anvilkit.stress import log_path, percentile  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
