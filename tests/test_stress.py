"""Tests for anvilkit.stress.

Written before the implementation (TDD).

Current scope: behaviours 1 and 2 of plans/stress-test.md --
``concurrency_levels(max_concurrency)`` derives the level series from a single
maximum: 1, then each power of two up to the maximum, then the maximum itself
if it is not already a power of two; ``percentile(values, p)`` is the
nearest-rank percentile (no interpolation): sort ascending, take index
``ceil(p/100 * n) - 1`` clamped to ``[0, n-1]``.

Behaviours 3 and 6-16 land in this same file in later cycles.

The module is a pure-function module for these behaviours: no mocks, no I/O,
assertions on returned data structures only.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import stress  # noqa: E402
from anvilkit.stress import percentile  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
