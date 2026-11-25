"""Tests for anvilkit.pi.pirun — derivation for the ``pi run`` command.

Written before the implementation (TDD, ``plans/pi-phase14-run-command.md``).
This file covers behaviour 3 ("branch-derived-from-kind-and-issue"):
``branch_for(kind, issue_number)`` returns ``feature/issue-<n>`` or
``bugfix/issue-<n>`` derived from the kind and the issue number, and raises
``RunError`` naming the number for a non-positive issue number.
``anvilkit.pi.pirun`` exists with a deliberately wrong
``branch_for`` placeholder (``return ""``), so these tests fail on the
assertions, not on import.

The later behaviours of the plan (PR title, PR body, kind, outcome-to-exit-
code) get their own cycles and will be added here as separate test classes.

No test performs real I/O: ``branch_for`` is pure derivation, so no opener,
no mock and no fixture is needed.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit.pi import pirun  # noqa: E402


class BranchForTestCase(unittest.TestCase):
    """Behaviour 3: branch-derived-from-kind-and-issue."""

    def test_branch_for_feature_kind_returns_feature_issue_branch(self):
        self.assertEqual(
            pirun.branch_for("feature", 114),
            "feature/issue-114",
        )

    def test_branch_for_bugfix_kind_returns_bugfix_issue_branch(self):
        self.assertEqual(
            pirun.branch_for("bugfix", 114),
            "bugfix/issue-114",
        )

    def test_branch_for_zero_issue_number_raises_run_error_naming_it(self):
        with self.assertRaises(pirun.RunError) as ctx:
            pirun.branch_for("feature", 0)

        message = str(ctx.exception)
        self.assertTrue(
            message,
            "the RunError must carry a non-empty message",
        )
        self.assertIn(
            "0",
            message,
            "the RunError must name the issue number 0 (got: {!r})".format(
                message
            ),
        )

    def test_branch_for_negative_issue_number_raises_run_error_naming_it(self):
        with self.assertRaises(pirun.RunError) as ctx:
            pirun.branch_for("bugfix", -7)

        message = str(ctx.exception)
        self.assertTrue(
            message,
            "the RunError must carry a non-empty message",
        )
        self.assertIn(
            "-7",
            message,
            "the RunError must name the issue number -7 (got: {!r})".format(
                message
            ),
        )


if __name__ == "__main__":
    unittest.main()
