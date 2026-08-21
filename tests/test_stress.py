"""Tests for anvilkit.stress.

Written before the implementation (TDD).

Current scope: behaviour 1 of plans/stress-test.md only --
``concurrency_levels(max_concurrency)`` derives the level series from a single
maximum: 1, then each power of two up to the maximum, then the maximum itself
if it is not already a power of two.

Behaviours 2-3 and 6-16 land in this same file in later cycles.

The module is a pure-function module for this behaviour: no mocks, no I/O,
assertions on returned data structures only.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import stress  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
