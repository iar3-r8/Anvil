"""Tests for anvilkit.piguard - GitHub ruleset guard checks (behaviours 1-3).

Written before the implementation (TDD RED step for behaviour 1 of
plans/pi-guard-verification.md: the history-rewrite guard).

``check_history_rewrite`` takes the JSON array returned by
``GET /repos/{owner}/{repo}/rules/branches/{branch}`` and returns one finding
per rule type it checks - ``non_fast_forward`` and ``deletion``. A rule present
yields a ``passed`` finding naming the rule's API type and its
``ruleset_source``; a rule absent yields a ``warn`` finding naming the danger
(history rewritten unrecoverably) and the fix. An empty array warns on both.

No test performs real network I/O: the input is a recorded response fixture
(a plain list of dicts in the shape the endpoint documents).
"""

import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import piguard  # noqa: E402


def _field(finding: Any, name: str) -> Any:
    """Read a finding attribute whether it is a dict or a plain object."""
    if isinstance(finding, dict):
        return finding.get(name)
    return getattr(finding, name, None)


def rule(rule_type: str, ruleset_source: str) -> Dict[str, Any]:
    """One element of the rules/branches response, per the documented shape."""
    return {
        "type": rule_type,
        "ruleset_source_type": "repository",
        "ruleset_source": ruleset_source,
        "ruleset_id": 1,
        "parameters": {},
    }


class CheckHistoryRewriteTests(unittest.TestCase):
    """Behaviour 1: history-rewrite guard reported from a rules response."""

    def test_both_rules_present_yields_one_passed_finding_per_rule(self):
        findings = piguard.check_history_rewrite(
            [rule("non_fast_forward", "main-protected"), rule("deletion", "main-protected")]
        )

        self.assertEqual(len(findings), 2)
        for expected_type in ("non_fast_forward", "deletion"):
            matching = [
                f for f in findings if _field(f, "rule") == expected_type
            ]
            self.assertEqual(
                len(matching),
                1,
                "expected exactly one finding for rule {!r}".format(expected_type),
            )
            finding = matching[0]
            self.assertEqual(_field(finding, "status"), "passed")
            self.assertEqual(_field(finding, "check"), "history_rewrite")
            self.assertEqual(
                _field(finding, "rule"), expected_type,
                "finding must name the rule's API type",
            )
            self.assertEqual(
                _field(finding, "source"),
                "main-protected",
                "finding must name the rule's ruleset_source",
            )
            self.assertTrue(
                _field(finding, "remedy"),
                "every finding carries a non-empty remedy",
            )

    def test_one_rule_absent_yields_passed_for_the_other_and_warn_for_the_missing(self):
        findings = piguard.check_history_rewrite(
            [rule("non_fast_forward", "main-protected")]
        )

        self.assertEqual(len(findings), 2)

        passed = [f for f in findings if _field(f, "status") == "passed"]
        warns = [f for f in findings if _field(f, "status") == "warn"]
        self.assertEqual(len(passed), 1)
        self.assertEqual(len(warns), 1)

        self.assertEqual(_field(passed[0], "rule"), "non_fast_forward")

        warn = warns[0]
        self.assertEqual(_field(warn, "rule"), "deletion")
        self.assertEqual(_field(warn, "check"), "history_rewrite")
        self.assertTrue(
            _field(warn, "danger"),
            "warn finding must name the danger (history rewritten unrecoverably)",
        )
        self.assertTrue(
            "doc/external/github" in (_field(warn, "remedy") or ""),
            "warn finding must name a fix, e.g. a doc path under doc/external/github/",
        )

    def test_empty_rules_array_warns_on_both_rule_types_without_raising(self):
        findings = piguard.check_history_rewrite([])

        self.assertEqual(len(findings), 2)
        for expected_type in ("non_fast_forward", "deletion"):
            matching = [f for f in findings if _field(f, "rule") == expected_type]
            self.assertEqual(len(matching), 1)
            finding = matching[0]
            self.assertEqual(_field(finding, "status"), "warn")
            self.assertEqual(_field(finding, "check"), "history_rewrite")
            self.assertTrue(_field(finding, "danger"))
            self.assertTrue(_field(finding, "remedy"))

        self.assertEqual(
            [f for f in findings if _field(f, "status") == "passed"],
            [],
            "an empty rules array must yield no passed findings",
        )


def pull_request_rule(ruleset_source: str, count: int) -> Dict[str, Any]:
    """A ``pull_request`` element carrying an approving-review count."""
    return {
        "type": "pull_request",
        "ruleset_source_type": "repository",
        "ruleset_source": ruleset_source,
        "ruleset_id": 1,
        "parameters": {"required_approving_review_count": count},
    }


class CheckReviewGuardTests(unittest.TestCase):
    """Behaviour 2: review guard reported from a rules response."""

    def test_pull_request_present_passes_naming_check_and_ruleset_source(self):
        findings = piguard.check_review(
            [
                pull_request_rule("main-protected", 1),
                rule("non_fast_forward", "main-protected"),
            ]
        )

        passed = [
            f
            for f in findings
            if _field(f, "status") == "passed" and _field(f, "check") == "review"
        ]
        self.assertEqual(
            len(passed),
            1,
            "one passed review finding expected when pull_request is active",
        )
        finding = passed[0]
        self.assertEqual(_field(finding, "rule"), "pull_request")
        self.assertEqual(
            _field(finding, "source"),
            "main-protected",
            "finding must name the rule's ruleset_source",
        )
        self.assertEqual(
            _field(finding, "required_approving_review_count"),
            1,
            "finding must record the required approving review count",
        )
        self.assertTrue(
            _field(finding, "remedy"),
            "every finding carries a non-empty remedy",
        )

    def test_pull_request_absent_warns_naming_danger_and_remedy(self):
        for label, rules in (
            (
                "only non_fast_forward active",
                [rule("non_fast_forward", "main-protected")],
            ),
            ("empty array", []),
        ):
            with self.subTest(absent=label):
                findings = piguard.check_review(rules)

                warns = [
                    f
                    for f in findings
                    if _field(f, "status") == "warn" and _field(f, "check") == "review"
                ]
                self.assertEqual(
                    len(warns),
                    1,
                    "one warn review finding expected when pull_request is absent",
                )
                warn = warns[0]
                self.assertEqual(_field(warn, "rule"), "pull_request")
                self.assertTrue(
                    _field(warn, "danger"),
                    "warn finding must name the danger (change lands unreviewed)",
                )
                self.assertTrue(
                    "doc/external/github" in (_field(warn, "remedy") or ""),
                    "warn finding must name a concrete fix, e.g. a doc path "
                    "under doc/external/github/",
                )
                self.assertEqual(
                    [
                        f
                        for f in findings
                        if _field(f, "status") == "passed"
                        and _field(f, "check") == "review"
                    ],
                    [],
                    "no passed review finding when pull_request is absent",
                )

    def test_zero_required_approvals_passes_but_records_zero_count(self):
        findings = piguard.check_review([pull_request_rule("main-protected", 0)])

        passed = [
            f
            for f in findings
            if _field(f, "status") == "passed" and _field(f, "check") == "review"
        ]
        self.assertEqual(
            len(passed),
            1,
            "a pull_request rule with zero required approvals still passes",
        )
        self.assertEqual(
            _field(passed[0], "required_approving_review_count"),
            0,
            "zero approvals is a weaker guard than the name suggests; "
            "the count must be visible on the finding",
        )
        self.assertTrue(
            _field(passed[0], "remedy"),
            "every finding carries a non-empty remedy",
        )


class RenderFindingTests(unittest.TestCase):
    """Behaviour 3: a rendered finding states the bypass-visibility caveat.

    GitHub returns ``bypass_actors`` only to users with write access to the
    ruleset (doc/external/github/rest-api-endpoints-for-rules.md), so a
    passed rule finding rendered on a read-only token must never claim the
    branch is simply "protected": it must say the rule is present and that
    the bypass list is not visible. An unseen ``bypass_actors`` entry is an
    unmeasured hole.

    ``render_finding(finding)`` is expected to take one finding dict (the
    shape the check functions return) and return the human-readable line
    for it; no network is involved. Skipped-finding rendering is deferred to
    behaviour 4's tests, since the module emits no ``skipped`` status yet.
    """

    def _render_finding(self):
        """Fetch ``anvilkit.piguard.render_finding``, failing clearly if absent."""
        renderer = getattr(piguard, "render_finding", None)
        self.assertTrue(
            callable(renderer),
            "anvilkit.piguard.render_finding is not callable; the finding "
            "renderer has not been implemented yet",
        )
        return renderer

    def test_passed_history_rewrite_findings_state_rule_type_and_bypass_invisibility(self):
        render = self._render_finding()
        findings = piguard.check_history_rewrite(
            [
                rule("non_fast_forward", "main-guard"),
                rule("deletion", "main-guard"),
            ]
        )

        self.assertEqual(
            [_field(f, "status") for f in findings],
            ["passed", "passed"],
            "fixture sanity: both rules active means two passed findings",
        )
        for finding in findings:
            with self.subTest(rule=_field(finding, "rule")):
                line = render(finding)
                self.assertIsInstance(line, str)
                self.assertIn(
                    _field(finding, "rule"),
                    line,
                    "the rendered line must name the rule's API type",
                )
                self.assertIn(
                    "bypass",
                    line.lower(),
                    "a passed finding must say the bypass list is not visible "
                    "on a read-only token",
                )
                self.assertNotIn(
                    "protected",
                    line.lower(),
                    "a passed finding on a read-only token must never claim "
                    "the branch is simply 'protected' - an unseen "
                    "bypass_actors entry is an unmeasured hole",
                )

    def test_passed_review_finding_states_caveat_and_keeps_review_count_visible(self):
        render = self._render_finding()
        for count in (0, 2):
            with self.subTest(count=count):
                findings = piguard.check_review(
                    [pull_request_rule("main-guard", count)]
                )
                self.assertEqual(
                    [_field(f, "status") for f in findings],
                    ["passed"],
                    "fixture sanity: pull_request active means one passed finding",
                )
                line = render(findings[0])
                self.assertIn(
                    "bypass",
                    line.lower(),
                    "the caveat must survive on a passed review finding",
                )
                self.assertNotIn(
                    "protected",
                    line.lower(),
                    "no bare 'protected' claim on a read-only token",
                )
                self.assertRegex(
                    line,
                    r"\b{}\b".format(count),
                    "the recorded required-approving-review count of {} must "
                    "stay visible in the rendered line - a zero count must "
                    "not be hidden by the caveat".format(count),
                )

    def test_warn_finding_lines_name_danger_and_remedy(self):
        render = self._render_finding()
        for label, findings in (
            (
                "history_rewrite warn",
                piguard.check_history_rewrite(
                    [rule("non_fast_forward", "main-guard")]
                ),
            ),
            (
                "review warn",
                piguard.check_review(
                    [rule("non_fast_forward", "main-guard")]
                ),
            ),
        ):
            with self.subTest(warn=label):
                warns = [f for f in findings if _field(f, "status") == "warn"]
                self.assertEqual(
                    len(warns),
                    1,
                    "fixture sanity: one warn finding expected",
                )
                warn = warns[0]
                line = render(warn)
                self.assertIn(
                    _field(warn, "danger"),
                    line,
                    "the rendered warn line must name the danger",
                )
                self.assertIn(
                    "doc/external/github",
                    line,
                    "the rendered warn line must name the concrete fix, e.g. "
                    "a doc path under doc/external/github/",
                )


if __name__ == "__main__":
    unittest.main()
