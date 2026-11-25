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


class PrFieldsForTestCase(unittest.TestCase):
    """Behaviour 4: title-and-body-derived-from-the-issue.

    ``pr_fields_for(payload)`` returns ``{"title": <issue title>,
    "body": <issue body>}``; a missing, null, or empty (whitespace-only)
    title yields ``(no title provided)`` and a missing, null, or empty body
    yields ``(no body provided)`` — a stated placeholder, never the string
    ``"None"``. A payload that is not a dict is treated the same as missing
    fields: placeholders, no exception.

    The derivation is pure: no opener, no mock and no fixture is needed.
    """

    def _payload(self, **overrides):
        payload = {
            "title": "Fix the gateway port fallback",
            "body": "The fallback port is never honoured.",
            "labels": ["bug"],
            "number": 114,
        }
        payload.update(overrides)
        return payload

    def test_title_and_body_present_returned_verbatim(self):
        self.assertEqual(
            pirun.pr_fields_for(self._payload()),
            {
                "title": "Fix the gateway port fallback",
                "body": "The fallback port is never honoured.",
            },
        )

    def test_title_missing_key_yields_placeholder_and_body_still_derived(self):
        payload = self._payload()
        del payload["title"]

        self.assertEqual(
            pirun.pr_fields_for(payload),
            {
                "title": "(no title provided)",
                "body": "The fallback port is never honoured.",
            },
        )

    def test_title_null_yields_placeholder_and_body_still_derived(self):
        self.assertEqual(
            pirun.pr_fields_for(self._payload(title=None)),
            {
                "title": "(no title provided)",
                "body": "The fallback port is never honoured.",
            },
        )

    def test_title_whitespace_only_yields_placeholder_and_body_still_derived(self):
        self.assertEqual(
            pirun.pr_fields_for(self._payload(title="   \t\n  ")),
            {
                "title": "(no title provided)",
                "body": "The fallback port is never honoured.",
            },
        )

    def test_body_missing_key_yields_placeholder_and_title_still_derived(self):
        payload = self._payload()
        del payload["body"]

        self.assertEqual(
            pirun.pr_fields_for(payload),
            {
                "title": "Fix the gateway port fallback",
                "body": "(no body provided)",
            },
        )

    def test_body_null_yields_placeholder_and_title_still_derived(self):
        self.assertEqual(
            pirun.pr_fields_for(self._payload(body=None)),
            {
                "title": "Fix the gateway port fallback",
                "body": "(no body provided)",
            },
        )

    def test_body_whitespace_only_yields_placeholder_and_title_still_derived(self):
        self.assertEqual(
            pirun.pr_fields_for(self._payload(body="  \n\t ")),
            {
                "title": "Fix the gateway port fallback",
                "body": "(no body provided)",
            },
        )

    def test_non_dict_payload_yields_both_placeholders_without_raising(self):
        self.assertEqual(
            pirun.pr_fields_for(None),
            {
                "title": "(no title provided)",
                "body": "(no body provided)",
            },
        )


class KindForTestCase(unittest.TestCase):
    """Behaviour 5: kind-derived-from-the-labels.

    ``kind_for(payload)`` returns ``"bugfix"`` iff some label's ``"name"`` is
    exactly ``"bug"`` (case-sensitive); everything else returns ``"feature"``.
    Absent, null, or malformed labels — not a list, entries not dicts, missing
    or non-string ``"name"`` — give ``"feature"``; the derivation never raises
    and never returns anything but the two words ``"feature"`` / ``"bugfix"``.

    The derivation is pure: no opener, no mock and no fixture is needed.
    """

    def test_payload_with_bug_label_among_others_returns_bugfix(self):
        payload = {
            "labels": [
                {"name": "enhancement"},
                {"name": "bug"},
                {"name": "backend"},
            ],
        }

        self.assertEqual(pirun.kind_for(payload), "bugfix")

    def test_payload_with_only_non_bug_labels_returns_feature(self):
        payload = {
            "labels": [
                {"name": "enhancement"},
                {"name": "backend"},
            ],
        }

        self.assertEqual(pirun.kind_for(payload), "feature")

    def test_payload_without_labels_key_returns_feature(self):
        self.assertEqual(pirun.kind_for({}), "feature")

    def test_payload_with_null_labels_returns_feature(self):
        self.assertEqual(pirun.kind_for({"labels": None}), "feature")

    def test_payload_with_labels_as_string_returns_feature_without_raising(self):
        self.assertEqual(pirun.kind_for({"labels": "bug"}), "feature")

    def test_payload_with_labels_as_dict_returns_feature_without_raising(self):
        self.assertEqual(pirun.kind_for({"labels": {"name": "bug"}}), "feature")

    def test_labels_list_with_non_dict_entries_and_bug_dict_returns_bugfix(self):
        payload = {"labels": ["bug", {"name": "bug"}]}

        self.assertEqual(pirun.kind_for(payload), "bugfix")

    def test_labels_list_with_only_non_dict_entries_returns_feature(self):
        self.assertEqual(pirun.kind_for({"labels": ["bug", 42]}), "feature")

    def test_label_dict_missing_name_returns_feature(self):
        self.assertEqual(pirun.kind_for({"labels": [{"area": "backend"}]}), "feature")

    def test_label_dict_with_non_string_name_returns_feature(self):
        self.assertEqual(pirun.kind_for({"labels": [{"name": 42}]}), "feature")

    def test_label_with_wrong_case_name_returns_feature(self):
        self.assertEqual(pirun.kind_for({"labels": [{"name": "Bug"}]}), "feature")


if __name__ == "__main__":
    unittest.main()
