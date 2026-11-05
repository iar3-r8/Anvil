"""Tests for anvilkit.pi.piguard - GitHub ruleset guard checks (behaviours 1-7).

Written before the implementation (TDD RED step for behaviour 1 of
plans/pi-guard-verification.md: the history-rewrite guard).

``check_history_rewrite`` takes the JSON array returned by
``GET /repos/{owner}/{repo}/rules/branches/{branch}`` and returns one finding
per rule type it checks - ``non_fast_forward`` and ``deletion``. A rule present
yields a ``passed`` finding naming the rule's API type and its
``ruleset_source``; a rule absent yields a ``warn`` finding naming the danger
(history rewritten unrecoverably) and the fix. An empty array warns on both.

No test performs real network I/O: the input is a recorded response fixture
(a plain list of dicts in the shape the endpoint documents). Behaviour 4's
tests go one step further and inject a recorded *opener* (a urlopen-like
callable) so the fetch path runs over recorded responses with no live network.
"""

import json
import socket
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit.pi import piguard  # noqa: E402
from anvilkit.pi import piruleset  # noqa: E402


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


def update_rule(
    ruleset_source: str, parameters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """An ``update`` element; ``parameters=None`` omits the key entirely."""
    element: Dict[str, Any] = {
        "type": "update",
        "ruleset_source_type": "repository",
        "ruleset_source": ruleset_source,
        "ruleset_id": 1,
    }
    if parameters is not None:
        element["parameters"] = parameters
    return element


class CheckUpdateTests(unittest.TestCase):
    """Behaviour 1 of plans/verify-guards-five-rules.md: the update-restriction
    guard reported from a rules response.

    ``check_update(rules)`` takes the parsed ``/rules/branches`` array and
    reports one finding for the ``update`` rule: a rule present yields a
    ``passed`` finding under the ``update_restriction`` check, naming the
    rule's API type and its ``ruleset_source`` and recording
    ``parameters.update_allows_fetch_and_merge`` on the finding (a weak value
    passes but stays visible, the zero-approvals precedent); a rule absent
    yields a ``warn`` finding naming the danger (anyone with push access can
    push straight to the branch, with no gate) and a remedy citing both saved
    docs (doc/external/github/rest-api-endpoints-for-rules.md:134,
    doc/external/github/available-rules-for-rulesets.md:32).
    """

    def test_update_rule_present_yields_one_passed_finding_recording_parameter(self):
        findings = piguard.check_update(
            [
                update_rule("main-protected", {"update_allows_fetch_and_merge": True}),
                rule("non_fast_forward", "main-protected"),
            ]
        )

        self.assertEqual(
            len(findings),
            1,
            "check_update reports one finding for the update rule",
        )
        finding = findings[0]
        self.assertEqual(_field(finding, "status"), "passed")
        self.assertEqual(
            _field(finding, "check"),
            "update_restriction",
            "the update check runs under its own check constant",
        )
        self.assertEqual(
            _field(finding, "rule"),
            "update",
            "finding must name the rule's API type",
        )
        self.assertEqual(
            _field(finding, "source"),
            "main-protected",
            "finding must name the rule's ruleset_source",
        )
        self.assertEqual(
            _field(finding, "update_allows_fetch_and_merge"),
            True,
            "finding must record parameters.update_allows_fetch_and_merge",
        )
        self.assertTrue(
            _field(finding, "remedy"),
            "every finding carries a non-empty remedy",
        )

    def test_update_absent_warns_naming_danger_and_both_saved_docs(self):
        for label, rules in (
            (
                "only non_fast_forward active",
                [rule("non_fast_forward", "main-protected")],
            ),
            ("empty array", []),
            ("only non-dict elements", ["not a dict", 42, None]),
        ):
            with self.subTest(absent=label):
                findings = piguard.check_update(rules)

                warns = [f for f in findings if _field(f, "status") == "warn"]
                self.assertEqual(
                    len(warns),
                    1,
                    "one warn update finding expected when the update rule "
                    "is absent",
                )
                warn = warns[0]
                self.assertEqual(
                    _field(warn, "check"),
                    "update_restriction",
                    "the warn must carry the update check constant",
                )
                self.assertEqual(_field(warn, "rule"), "update")
                self.assertTrue(
                    _field(warn, "danger"),
                    "warn finding must name the danger: anyone with push "
                    "access can push straight to the branch, with no gate",
                )
                remedy = _field(warn, "remedy") or ""
                self.assertIn(
                    "doc/external/github/available-rules-for-rulesets.md",
                    remedy,
                    "the warn remedy must cite the saved rules doc, so a "
                    "reviewer can check the claim",
                )
                self.assertIn(
                    "doc/external/github/rest-api-endpoints-for-rules.md",
                    remedy,
                    "the warn remedy must cite the saved endpoint doc, so a "
                    "reviewer can check the claim",
                )
                self.assertEqual(
                    [
                        f
                        for f in findings
                        if _field(f, "status") == "passed"
                    ],
                    [],
                    "no passed update finding when the update rule is absent",
                )

    def test_missing_or_non_dict_parameters_records_none_and_never_raises(self):
        cases = (
            ("parameters key absent", update_rule("main-protected")),
            (
                "parameters is None",
                dict(update_rule("main-protected"), parameters=None),
            ),
            (
                "parameters is not a dict",
                dict(
                    update_rule("main-protected"),
                    parameters=["update_allows_fetch_and_merge"],
                ),
            ),
        )
        for label, element in cases:
            with self.subTest(parameters=label):
                findings = piguard.check_update([element])

                self.assertEqual(
                    len(findings),
                    1,
                    "an update rule whose parameters cannot be read still "
                    "yields one finding - never an exception",
                )
                finding = findings[0]
                self.assertEqual(
                    _field(finding, "status"),
                    "passed",
                    "a present update rule passes even when its parameters "
                    "are unreadable",
                )
                self.assertIsNone(
                    _field(finding, "update_allows_fetch_and_merge"),
                    "an unreadable parameters object must record None, not "
                    "raise or guess a value",
                )
                self.assertTrue(
                    _field(finding, "remedy"),
                    "every finding carries a non-empty remedy",
                )

    def test_false_allows_fetch_and_merge_passes_but_records_false(self):
        findings = piguard.check_update(
            [
                update_rule(
                    "main-protected",
                    {"update_allows_fetch_and_merge": False},
                )
            ]
        )

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "passed",
            "a present update rule with a weak value still passes - the "
            "weak value is recorded, not hidden (zero-approvals precedent)",
        )
        self.assertEqual(
            _field(finding, "update_allows_fetch_and_merge"),
            False,
            "a False value must stay visible on the finding - it means "
            "fetches and merges are the only allowed updates",
        )
        self.assertTrue(
            _field(finding, "remedy"),
            "every finding carries a non-empty remedy",
        )

    def test_source_is_unknown_when_ruleset_source_absent_or_blank(self):
        for label, element in (
            (
                "ruleset_source absent",
                dict(
                    (k, v)
                    for k, v in update_rule(
                        "main-protected",
                        {"update_allows_fetch_and_merge": True},
                    ).items()
                    if k != "ruleset_source"
                ),
            ),
            (
                "ruleset_source blank",
                update_rule("", {"update_allows_fetch_and_merge": True}),
            ),
        ):
            with self.subTest(source=label):
                findings = piguard.check_update([element])

                self.assertEqual(len(findings), 1)
                finding = findings[0]
                self.assertEqual(_field(finding, "status"), "passed")
                self.assertEqual(
                    _field(finding, "source"),
                    "unknown",
                    "an absent or blank ruleset_source must be named "
                    "'unknown' on the finding",
                )


def file_path_rule(
    ruleset_source: str, parameters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """A ``file_path_restriction`` element; ``parameters=None`` omits the key entirely."""
    element: Dict[str, Any] = {
        "type": "file_path_restriction",
        "ruleset_source_type": "repository",
        "ruleset_source": ruleset_source,
        "ruleset_id": 1,
    }
    if parameters is not None:
        element["parameters"] = parameters
    return element


class CheckFilePathsTests(unittest.TestCase):
    """Behaviour 2 of plans/verify-guards-five-rules.md: the file-path
    restriction guard reported from a rules response.

    ``check_file_paths(rules)`` takes the parsed ``/rules/branches`` array
    and reports one finding for the ``file_path_restriction`` rule: a rule
    present yields a ``passed`` finding under the ``file_paths`` check,
    naming the rule's API type and its ``ruleset_source`` and recording
    ``parameters.restricted_file_paths`` as a list on the finding (an empty
    list passes but stays visible, the zero-approvals precedent); a rule
    absent yields a ``warn`` finding naming the danger (a push can change
    ``.github/workflows/**`` - the paths the rule restricts, e.g. what CI
    runs - with no gate) and a remedy citing both saved docs
    (doc/external/github/available-rules-for-rulesets.md,
    doc/external/github/rest-api-endpoints-for-rules.md:137).
    """

    def test_file_path_rule_present_yields_one_passed_finding_recording_paths(self):
        findings = piguard.check_file_paths(
            [
                file_path_rule(
                    "main-protected",
                    {"restricted_file_paths": [".github/workflows/**"]},
                ),
                rule("non_fast_forward", "main-protected"),
            ]
        )

        self.assertEqual(
            len(findings),
            1,
            "check_file_paths reports one finding for the "
            "file_path_restriction rule",
        )
        finding = findings[0]
        self.assertEqual(_field(finding, "status"), "passed")
        self.assertEqual(
            _field(finding, "check"),
            "file_paths",
            "the file-path check runs under its own check constant",
        )
        self.assertEqual(
            _field(finding, "rule"),
            "file_path_restriction",
            "finding must name the rule's API type",
        )
        self.assertEqual(
            _field(finding, "source"),
            "main-protected",
            "finding must name the rule's ruleset_source",
        )
        self.assertEqual(
            _field(finding, "restricted_file_paths"),
            [".github/workflows/**"],
            "finding must record the exact restricted_file_paths list the "
            "rule carries - the value build_ruleset writes",
        )
        self.assertTrue(
            _field(finding, "remedy"),
            "every finding carries a non-empty remedy",
        )

    def test_file_path_absent_warns_naming_danger_and_both_saved_docs(self):
        for label, rules in (
            (
                "only non_fast_forward active",
                [rule("non_fast_forward", "main-protected")],
            ),
            ("empty array", []),
            ("only non-dict elements", ["not a dict", 42, None]),
        ):
            with self.subTest(absent=label):
                findings = piguard.check_file_paths(rules)

                warns = [f for f in findings if _field(f, "status") == "warn"]
                self.assertEqual(
                    len(warns),
                    1,
                    "one warn file-path finding expected when the "
                    "file_path_restriction rule is absent",
                )
                warn = warns[0]
                self.assertEqual(
                    _field(warn, "check"),
                    "file_paths",
                    "the warn must carry the file-path check constant",
                )
                self.assertEqual(_field(warn, "rule"), "file_path_restriction")
                self.assertTrue(
                    _field(warn, "danger"),
                    "warn finding must name the danger: a push can change "
                    ".github/workflows/** - what CI runs - with no gate",
                )
                remedy = _field(warn, "remedy") or ""
                self.assertIn(
                    "doc/external/github/available-rules-for-rulesets.md",
                    remedy,
                    "the warn remedy must cite the saved rules doc, so a "
                    "reviewer can check the claim",
                )
                self.assertIn(
                    "doc/external/github/rest-api-endpoints-for-rules.md",
                    remedy,
                    "the warn remedy must cite the saved endpoint doc, so a "
                    "reviewer can check the claim",
                )
                self.assertEqual(
                    [
                        f
                        for f in findings
                        if _field(f, "status") == "passed"
                    ],
                    [],
                    "no passed file-path finding when the rule is absent",
                )

    def test_missing_or_non_dict_parameters_records_empty_list_and_never_raises(self):
        cases = (
            ("parameters key absent", file_path_rule("main-protected")),
            (
                "parameters is None",
                dict(file_path_rule("main-protected"), parameters=None),
            ),
            (
                "parameters is not a dict",
                dict(
                    file_path_rule("main-protected"),
                    parameters=["restricted_file_paths"],
                ),
            ),
            (
                "restricted_file_paths is not a list",
                file_path_rule(
                    "main-protected",
                    {"restricted_file_paths": ".github/workflows/**"},
                ),
            ),
        )
        for label, element in cases:
            with self.subTest(parameters=label):
                findings = piguard.check_file_paths([element])

                self.assertEqual(
                    len(findings),
                    1,
                    "a file_path_restriction rule whose parameters cannot "
                    "be read still yields one finding - never an exception",
                )
                finding = findings[0]
                self.assertEqual(
                    _field(finding, "status"),
                    "passed",
                    "a present file_path_restriction rule passes even when "
                    "its parameters are unreadable",
                )
                self.assertEqual(
                    _field(finding, "restricted_file_paths"),
                    [],
                    "an unreadable parameters object must record an empty "
                    "list, not None - an empty restriction set is the "
                    "only honest value",
                )
                self.assertTrue(
                    _field(finding, "remedy"),
                    "every finding carries a non-empty remedy",
                )

    def test_empty_restricted_file_paths_passes_but_records_empty_list(self):
        findings = piguard.check_file_paths(
            [file_path_rule("main-protected", {"restricted_file_paths": []})]
        )

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "passed",
            "a present rule with an empty restriction list still passes - "
            "the weak value is recorded, not hidden (zero-approvals "
            "precedent)",
        )
        self.assertEqual(
            _field(finding, "restricted_file_paths"),
            [],
            "an empty restriction list must stay visible on the finding - "
            "it means the rule restricts nothing",
        )
        self.assertTrue(
            _field(finding, "remedy"),
            "every finding carries a non-empty remedy",
        )

    def test_duplicated_file_path_rule_elements_first_wins(self):
        findings = piguard.check_file_paths(
            [
                file_path_rule(
                    "first-ruleset",
                    {"restricted_file_paths": [".github/workflows/**"]},
                ),
                file_path_rule(
                    "second-ruleset",
                    {"restricted_file_paths": ["src/**"]},
                ),
            ]
        )

        self.assertEqual(
            len(findings),
            1,
            "a duplicated file_path_restriction rule yields one finding, "
            "as check_history_rewrite does",
        )
        finding = findings[0]
        self.assertEqual(
            _field(finding, "source"),
            "first-ruleset",
            "the first element wins when the rule type is duplicated",
        )
        self.assertEqual(
            _field(finding, "restricted_file_paths"),
            [".github/workflows/**"],
            "the first element's paths win when the rule type is "
            "duplicated",
        )

    def test_source_is_unknown_when_ruleset_source_absent_or_blank(self):
        for label, element in (
            (
                "ruleset_source absent",
                dict(
                    (k, v)
                    for k, v in file_path_rule(
                        "main-protected",
                        {"restricted_file_paths": [".github/workflows/**"]},
                    ).items()
                    if k != "ruleset_source"
                ),
            ),
            (
                "ruleset_source blank",
                file_path_rule("", {"restricted_file_paths": [".github/workflows/**"]}),
            ),
        ):
            with self.subTest(source=label):
                findings = piguard.check_file_paths([element])

                self.assertEqual(len(findings), 1)
                finding = findings[0]
                self.assertEqual(_field(finding, "status"), "passed")
                self.assertEqual(
                    _field(finding, "source"),
                    "unknown",
                    "an absent or blank ruleset_source must be named "
                    "'unknown' on the finding",
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
        """Fetch ``anvilkit.pi.piguard.render_finding``, failing clearly if absent."""
        renderer = getattr(piguard, "render_finding", None)
        self.assertTrue(
            callable(renderer),
            "anvilkit.pi.piguard.render_finding is not callable; the finding "
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

    def test_passed_update_finding_states_caveat_and_keeps_allows_fetch_and_merge_visible(self):
        render = self._render_finding()
        for value in (True, False):
            with self.subTest(value=value):
                findings = piguard.check_update(
                    [
                        update_rule(
                            "main-guard",
                            {"update_allows_fetch_and_merge": value},
                        )
                    ]
                )
                self.assertEqual(
                    [_field(f, "status") for f in findings],
                    ["passed"],
                    "fixture sanity: update rule active means one passed finding",
                )
                self.assertEqual(
                    _field(findings[0], "update_allows_fetch_and_merge"),
                    value,
                    "fixture sanity: the check records the parameter value",
                )
                line = render(findings[0])
                self.assertIsInstance(line, str)
                self.assertTrue(
                    line,
                    "a passed finding must render a non-empty line",
                )
                self.assertIn(
                    "update",
                    line,
                    "the rendered line must name the update rule's API type",
                )
                self.assertIn(
                    "bypass",
                    line.lower(),
                    "the caveat must survive on a passed update finding - "
                    "bypass_actors is only returned to users with write "
                    "access, so the line must never claim the branch is "
                    "simply 'protected'",
                )
                self.assertNotIn(
                    "protected",
                    line.lower(),
                    "no bare 'protected' claim on a read-only token",
                )
                self.assertIn(
                    "True" if value else "False",
                    line,
                    "the recorded update_allows_fetch_and_merge value of {} "
                    "must stay visible in the rendered line - a weak value "
                    "must not be hidden by the caveat".format(value),
                )

    def test_passed_update_finding_with_unreadable_parameters_renders_without_claiming_a_value(self):
        render = self._render_finding()
        for label, element in (
            ("parameters key absent", update_rule("main-guard")),
            (
                "parameters is None",
                dict(update_rule("main-guard"), parameters=None),
            ),
            (
                "parameters is not a dict",
                dict(
                    update_rule("main-guard"),
                    parameters=["update_allows_fetch_and_merge"],
                ),
            ),
        ):
            with self.subTest(parameters=label):
                findings = piguard.check_update([element])
                self.assertEqual(
                    [_field(f, "status") for f in findings],
                    ["passed"],
                    "fixture sanity: a present update rule passes even when "
                    "its parameters are unreadable",
                )
                self.assertIsNone(
                    _field(findings[0], "update_allows_fetch_and_merge"),
                    "fixture sanity: an unreadable parameters object records "
                    "None, not a guess",
                )

                line = render(findings[0])

                self.assertIsInstance(line, str)
                self.assertTrue(
                    line,
                    "a passed finding must render a non-empty line",
                )
                self.assertIn(
                    "update",
                    line,
                    "the rendered line must still name the update rule's "
                    "API type",
                )
                self.assertIn(
                    "bypass",
                    line.lower(),
                    "the caveat must survive when no value was returned",
                )
                self.assertNotIn(
                    "protected",
                    line.lower(),
                    "no bare 'protected' claim on a read-only token",
                )
                self.assertNotIn(
                    "True",
                    line,
                    "no value was returned, so the line must not claim True",
                )
                self.assertNotIn(
                    "False",
                    line,
                    "no value was returned, so the line must not claim False",
                )

    def test_passed_file_path_finding_states_caveat_and_keeps_restricted_paths_visible(self):
        render = self._render_finding()
        for paths in (
            [".github/workflows/**"],
            [".github/workflows/**", "config.yaml"],
        ):
            with self.subTest(paths=paths):
                findings = piguard.check_file_paths(
                    [
                        file_path_rule(
                            "main-guard",
                            {"restricted_file_paths": list(paths)},
                        )
                    ]
                )
                self.assertEqual(
                    [_field(f, "status") for f in findings],
                    ["passed"],
                    "fixture sanity: file_path_restriction active means one "
                    "passed finding",
                )
                self.assertEqual(
                    _field(findings[0], "restricted_file_paths"),
                    list(paths),
                    "fixture sanity: the check records the "
                    "restricted_file_paths list",
                )
                line = render(findings[0])
                self.assertIsInstance(line, str)
                self.assertTrue(
                    line,
                    "a passed finding must render a non-empty line",
                )
                self.assertIn(
                    "file_path_restriction",
                    line,
                    "the rendered line must name the rule's API type",
                )
                self.assertIn(
                    "bypass",
                    line.lower(),
                    "the caveat must survive on a passed file-path finding - "
                    "bypass_actors is only returned to users with write "
                    "access, so the line must never claim the branch is "
                    "simply 'protected'",
                )
                self.assertNotIn(
                    "protected",
                    line.lower(),
                    "no bare 'protected' claim on a read-only token",
                )
                for path in paths:
                    self.assertIn(
                        path,
                        line,
                        "every recorded restricted path ({}) must stay "
                        "visible in the rendered line - no path may be "
                        "elided or truncated, so a reader sees exactly what "
                        "is restricted".format(path),
                    )

    def test_passed_file_path_finding_with_empty_restricted_paths_renders_explicit_no_paths(self):
        render = self._render_finding()
        findings = piguard.check_file_paths(
            [file_path_rule("main-guard", {"restricted_file_paths": []})]
        )
        self.assertEqual(
            [_field(f, "status") for f in findings],
            ["passed"],
            "fixture sanity: a present rule with an empty restriction list "
            "still passes",
        )
        self.assertEqual(
            _field(findings[0], "restricted_file_paths"),
            [],
            "fixture sanity: an empty restriction list is recorded",
        )
        line = render(findings[0])
        self.assertIsInstance(line, str)
        self.assertTrue(
            line,
            "a passed finding must render a non-empty line",
        )
        self.assertIn(
            "file_path_restriction",
            line,
            "the rendered line must name the rule's API type",
        )
        self.assertIn(
            "bypass",
            line.lower(),
            "the caveat must survive on a passed file-path finding",
        )
        self.assertNotIn(
            "protected",
            line.lower(),
            "an empty restriction list must render an explicit 'no restricted "
            "paths recorded' rather than a bare 'protected'",
        )
        self.assertIn(
            "no restricted paths recorded",
            line,
            "an empty restriction list must render the explicit phrase 'no "
            "restricted paths recorded' (case-sensitive) - a weak value is "
            "recorded, not hidden (zero-approvals precedent)",
        )

    def test_passed_file_path_finding_with_unreadable_parameters_renders_without_claiming_a_path(self):
        render = self._render_finding()
        for label, element in (
            ("parameters key absent", file_path_rule("main-guard")),
            (
                "parameters is None",
                dict(file_path_rule("main-guard"), parameters=None),
            ),
            (
                "parameters is not a dict",
                dict(
                    file_path_rule("main-guard"),
                    parameters=["restricted_file_paths"],
                ),
            ),
            (
                "restricted_file_paths is not a list",
                file_path_rule(
                    "main-guard",
                    {"restricted_file_paths": ".github/workflows/**"},
                ),
            ),
        ):
            with self.subTest(parameters=label):
                findings = piguard.check_file_paths([element])
                self.assertEqual(
                    [_field(f, "status") for f in findings],
                    ["passed"],
                    "fixture sanity: a present rule passes even when its "
                    "parameters are unreadable",
                )
                self.assertEqual(
                    _field(findings[0], "restricted_file_paths"),
                    [],
                    "fixture sanity: an unreadable parameters object records "
                    "an empty list, not a guess",
                )

                line = render(findings[0])

                self.assertIsInstance(line, str)
                self.assertTrue(
                    line,
                    "a passed finding must render a non-empty line",
                )
                self.assertIn(
                    "file_path_restriction",
                    line,
                    "the rendered line must still name the rule's API type",
                )
                self.assertIn(
                    "bypass",
                    line.lower(),
                    "the caveat must survive when no paths were returned",
                )
                self.assertNotIn(
                    "protected",
                    line.lower(),
                    "no bare 'protected' claim on a read-only token",
                )
                self.assertIn(
                    "no restricted paths recorded",
                    line,
                    "no paths were returned, so the line must read 'no "
                    "restricted paths recorded' - it must not claim a path "
                    "that was not returned",
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


class _FakeResponse:
    """A minimal urlopen response: readable, statused, usable as a context manager."""

    def __init__(
        self,
        body: bytes,
        status: int = 200,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self._body = body
        self.status = status
        self.headers = dict(headers) if headers else {}

    def getcode(self) -> int:
        return self.status

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


def _opener(outcome: Any) -> Any:
    """A urlopen-like callable that plays back one recorded outcome.

    ``outcome`` is either an exception to raise on call (a recorded failure)
    or a :class:`_FakeResponse` to return (a recorded success). Accepts
    whatever argument shape the implementation hands it, so the test does
    not depend on the exact call signature.
    """

    def opener(*args: Any, **kwargs: Any) -> Any:
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return opener


class _CapturingOpener:
    """An opener that records the request it was handed, then plays back one
    recorded outcome.

    ``outcome`` follows the same contract as :func:`_opener` (an exception to
    raise or a :class:`_FakeResponse` to return). ``captured`` holds the
    request object the implementation built - the first argument of the
    opener call, recorded positionally so the test does not depend on the
    exact call signature - or ``None`` if the opener was never called.
    """

    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome
        self.captured: Any = None
        self.timeout: Any = None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.captured = args[0]
        if len(args) > 1:
            self.timeout = args[1]
        elif "timeout" in kwargs:
            self.timeout = kwargs["timeout"]
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def _request_headers(request: Any) -> Dict[str, Any]:
    """The headers the recorded request carries, keyed by canonical form.

    Reads through :meth:`urllib.request.Request.get_header`, so a missing
    header is ``None`` in the returned mapping rather than a KeyError.
    """
    if request is None:
        return {}
    keys = getattr(request, "header_items", None)
    if not callable(keys):
        return {}
    try:
        items = list(keys())
    except Exception:
        return {}
    headers = {}
    for key, value in items:
        headers[str(key).lower()] = value
    return headers


class _SkippedAssertions:
    """Mixin of shared assertions on what a failed fetch must turn into.

    Deliberately a plain mixin, not a ``unittest.TestCase``: only the
    concrete test classes inherit ``unittest.TestCase`` (with this mixin
    second, for the assertion methods), which is what the test loader
    looks for when discovering tests.

    Behaviour 4 of plans/pi-guard-verification.md: a check that cannot run
    yields a ``skipped`` finding carrying the reason - never ``passed``,
    never an exception. One skipped finding per defined check - the four
    check constants (history_rewrite, review, update_restriction,
    file_paths) - each with a non-empty reason and a non-empty remedy
    (behaviour 5 invariant: a finding that cannot say what the user can do
    to make the check runnable is a programming error).
    """

    def _assert_skipped_findings(self, findings: Any, reason: str) -> None:
        self.assertIsInstance(findings, list)
        self.assertEqual(
            len(findings),
            4,
            "one skipped finding expected per defined check: "
            "history_rewrite, review, update_restriction and file_paths",
        )
        self.assertEqual(
            [_field(f, "check") for f in findings],
            ["history_rewrite", "review", "update_restriction", "file_paths"],
            "exactly one skipped finding per check constant, in report order",
        )
        self.assertEqual(
            [_field(f, "status") for f in findings],
            ["skipped", "skipped", "skipped", "skipped"],
            "every affected check must yield a skipped finding, in a "
            "visually distinct shape from a pass",
        )
        self.assertEqual(
            [f for f in findings if _field(f, "status") == "passed"],
            [],
            "a skipped finding never counts toward a clean report",
        )
        for finding in findings:
            with self.subTest(check=_field(finding, "check")):
                carried = _field(finding, "reason") or _field(finding, "danger")
                self.assertTrue(
                    carried,
                    "each skipped finding carries a non-empty reason",
                )
                self.assertIn(
                    reason,
                    carried,
                    "the reason the fetch failed must reach the finding, so "
                    "the user sees why the check did not run",
                )
                self.assertTrue(
                    _field(finding, "remedy"),
                    "each skipped finding carries a non-empty remedy naming "
                    "what the user can do to make the check runnable",
                )


class FetchBranchRulesTests(unittest.TestCase, _SkippedAssertions):
    """Behaviour 4: an unreachable or unreadable rules endpoint is skipped, not passed.

    ``fetch_branch_rules(owner, repo, branch, token=None, opener=None,
    timeout=None)`` is expected to take an injectable opener (a urlopen-like
    callable, the same seam ``anvilkit/health.py`` uses) and to return
    ``(rules, None)`` on a 200 with a JSON array, or ``(None, reason)`` on
    any failure - never raising. A missing token is NOT an automatic skip:
    the endpoint allows unauthenticated access on public repositories
    (plans/pi-guard-verification.md, Assumptions), so a missing token means
    an unauthenticated attempt, and only actual request failure skips.
    Every test below runs over a recorded opener - no live network.
    """

    def _fetcher(self) -> Any:
        fetcher = getattr(piguard, "fetch_branch_rules", None)
        self.assertTrue(
            callable(fetcher),
            "anvilkit.pi.piguard.fetch_branch_rules is not callable; the rules "
            "endpoint fetch has not been implemented yet",
        )
        return fetcher

    def test_url_error_returns_none_and_reason_without_raising(self):
        fetch = self._fetcher()

        rules, reason = fetch(
            "owner",
            "repo",
            "main",
            opener=_opener(urllib.error.URLError("Name or service not known")),
        )

        self.assertIsNone(rules, "no rules exist when the request never lands")
        self.assertIsInstance(reason, str)
        self.assertTrue(
            reason, "a failed fetch must record the reason it failed"
        )

        self._assert_skipped_findings(piguard.skipped_findings(reason), reason)

    def test_timeout_returns_none_and_reason_without_raising(self):
        # A network timeout is a skipped, not a fail (plan Assumptions): a
        # slow GitHub must not make a provisioning command unusable.
        fetch = self._fetcher()
        for label, outcome in (
            ("bare socket.timeout", socket.timeout("timed out")),
            (
                "URLError wrapping socket.timeout",
                urllib.error.URLError(socket.timeout("timed out")),
            ),
        ):
            with self.subTest(timeout=label):
                rules, reason = fetch(
                    "owner", "repo", "main", opener=_opener(outcome)
                )

                self.assertIsNone(rules)
                self.assertIsInstance(reason, str)
                self.assertTrue(reason, "a timeout must record the reason")

                self._assert_skipped_findings(
                    piguard.skipped_findings(reason), reason
                )

    def test_http_404_returns_non_blaming_reason(self):
        # A 404 on a private repo may be a plan limit - rulesets are
        # unavailable on private repos under GitHub Free (plan Notes) - so
        # the reason must name the situation, not accuse the user.
        fetch = self._fetcher()
        url = "https://api.github.com/repos/owner/repo/rules/branches/main"

        rules, reason = fetch(
            "owner",
            "repo",
            "main",
            opener=_opener(urllib.error.HTTPError(url, 404, "Not Found", None, None)),
        )

        self.assertIsNone(rules)
        self.assertIsInstance(reason, str)
        self.assertTrue(
            reason, "a 404 must still record a non-empty reason"
        )
        self.assertNotIn(
            "you",
            reason.lower(),
            "a 404 may be a plan limit (rulesets unavailable on private "
            "repos under GitHub Free); the reason must not accuse the user",
        )

        findings = piguard.skipped_findings(reason)
        self._assert_skipped_findings(findings, reason)
        for finding in findings:
            with self.subTest(check=_field(finding, "check")):
                self.assertEqual(_field(finding, "status"), "skipped")

    def test_non_json_body_returns_none_and_reason_without_raising(self):
        fetch = self._fetcher()

        rules, reason = fetch(
            "owner",
            "repo",
            "main",
            opener=_opener(_FakeResponse(b"<html>GitHub</html>")),
        )

        self.assertIsNone(
            rules, "an unreadable body must not be reported as rules"
        )
        self.assertIsInstance(reason, str)
        self.assertTrue(
            reason, "an unreadable body must record the reason"
        )

        self._assert_skipped_findings(piguard.skipped_findings(reason), reason)

    def test_json_array_returns_rules_and_none_usable_by_checks(self):
        # Success-path regression: a working response still produces real
        # findings, and the fetched rules plug straight into the check
        # functions.
        fetch = self._fetcher()
        body = json.dumps(
            [
                rule("non_fast_forward", "main-guard"),
                rule("deletion", "main-guard"),
                pull_request_rule("main-guard", 1),
            ]
        ).encode("utf-8")

        rules, reason = fetch(
            "owner", "repo", "main", opener=_opener(_FakeResponse(body))
        )

        self.assertIsNone(reason, "a 200 with a JSON array is a success")
        self.assertIsInstance(rules, list)
        self.assertTrue(
            all(isinstance(r, dict) for r in rules),
            "each rule must be the parsed element from the response",
        )

        history = piguard.check_history_rewrite(rules)
        self.assertEqual(
            [_field(f, "status") for f in history],
            ["passed", "passed"],
            "fetched rules must flow into real findings: both history-rewrite "
            "rules active means two passed findings",
        )
        review = piguard.check_review(rules)
        self.assertEqual(
            [_field(f, "status") for f in review],
            ["passed"],
            "fetched rules must flow into real findings: pull_request active "
            "means one passed review finding",
        )
        self.assertEqual(
            _field(review[0], "required_approving_review_count"),
            1,
            "the recorded review count must survive the fetch",
        )


class FetchProbeTests(unittest.TestCase):
    """Behaviour 1 of plans/verify-guards-token.md: ``fetch_probe``.

    ``fetch_probe(url, token, opener, timeout)`` issues one read-only GET
    through an injected opener (a urlopen-like callable, the same seam
    ``fetch_branch_rules`` in this module uses) and returns a four-tuple
    ``(status, headers, body, reason)``. An ``HTTPError`` is a **successful
    observation** - its ``code`` and ``headers`` are returned with
    ``reason=None``, because a ``403`` is the compliant answer to a probe:
    a denial is the data. Only transport-level failures - ``URLError``,
    ``socket.timeout``, a bare ``OSError`` - yield ``(None, None, None,
    reason)`` with a non-empty reason string. It never raises, and a
    missing token means no ``Authorization`` header on the request.

    Every test below runs over a recorded opener - no live network. The
    version header is the one the saved endpoint docs pin for the probe
    endpoints (``doc/external/github/rest-api-endpoints-for-actions-
    permissions.md`` and ``doc/external/github/rest-api-endpoints-for-users.md``),
    cited below - consistency with the module's pinned API version, not an
    invention.
    """

    URL = "https://api.github.com/user"

    def _prober(self) -> Any:
        prober = getattr(piguard, "fetch_probe", None)
        self.assertTrue(
            callable(prober),
            "anvilkit.pi.piguard.fetch_probe is not callable; the token-scope "
            "probe fetch has not been implemented yet",
        )
        return prober

    def test_recorded_200_returns_status_headers_body_and_none(self):
        probe = self._prober()
        headers = {"X-Frame-Options": "DENY"}
        body = b'{"login": "owner"}'

        status, resp_headers, resp_body, reason = probe(
            self.URL, None, _opener(_FakeResponse(body, 200, headers)), 10.0
        )

        self.assertEqual(
            status,
            200,
            "a recorded 200 must be observed as status 200",
        )
        self.assertIsNotNone(resp_headers, "a successful observation carries headers")
        self.assertEqual(
            resp_body,
            body,
            "the recorded body must come back unchanged",
        )
        self.assertIsNone(
            reason,
            "a 200 is a successful observation - no failure reason",
        )

    def test_recorded_http_error_403_is_a_successful_observation(self):
        # The core assertion: a 403 is the compliant answer to a probe, so
        # it must be returned as data, not swallowed into a reason.
        probe = self._prober()
        headers = {"X-Frame-Options": "DENY"}

        status, resp_headers, _resp_body, reason = probe(
            self.URL,
            None,
            _opener(
                urllib.error.HTTPError(
                    self.URL, 403, "Forbidden", headers, None
                )
            ),
            10.0,
        )

        self.assertEqual(
            status,
            403,
            "an HTTPError is a successful observation - its code must be "
            "returned, because a 403 is the compliant answer",
        )
        self.assertIsInstance(
            resp_headers,
            dict,
            "the observation must carry the recorded headers",
        )
        self.assertEqual(
            resp_headers.get("X-Frame-Options"),
            "DENY",
            "the recorded 403 headers must be returned, not discarded",
        )
        self.assertIsNone(
            reason,
            "a 403 is data, not a failure - it must not produce a reason",
        )

    def test_recorded_http_error_404_is_a_successful_observation(self):
        probe = self._prober()

        status, _resp_headers, _resp_body, reason = probe(
            self.URL,
            None,
            _opener(
                urllib.error.HTTPError(self.URL, 404, "Not Found", None, None)
            ),
            10.0,
        )

        self.assertEqual(
            status,
            404,
            "a 404 is data, not a failure - its code must be returned",
        )
        self.assertIsNone(
            reason,
            "a 404 must not produce a failure reason - it is a successful "
            "observation",
        )

    def test_url_error_returns_none_triple_and_nonempty_reason(self):
        probe = self._prober()

        status, headers, body, reason = probe(
            self.URL,
            None,
            _opener(urllib.error.URLError("Name or service not known")),
            10.0,
        )

        self.assertIsNone(status)
        self.assertIsNone(headers)
        self.assertIsNone(body)
        self.assertIsInstance(reason, str)
        self.assertTrue(
            reason, "a transport failure must record a non-empty reason"
        )

    def test_socket_timeout_returns_none_triple_and_nonempty_reason(self):
        probe = self._prober()

        status, headers, body, reason = probe(
            self.URL, None, _opener(socket.timeout("timed out")), 10.0
        )

        self.assertIsNone(status)
        self.assertIsNone(headers)
        self.assertIsNone(body)
        self.assertIsInstance(reason, str)
        self.assertTrue(
            reason, "a timeout must record a non-empty reason"
        )

    def test_bare_oserror_returns_none_triple_and_nonempty_reason(self):
        probe = self._prober()

        status, headers, body, reason = probe(
            self.URL, None, _opener(OSError("Network is unreachable")), 10.0
        )

        self.assertIsNone(status)
        self.assertIsNone(headers)
        self.assertIsNone(body)
        self.assertIsInstance(reason, str)
        self.assertTrue(
            reason, "a bare OSError must record a non-empty reason"
        )

    def test_no_token_request_carries_no_authorization_header(self):
        probe = self._prober()
        opener = _CapturingOpener(
            _FakeResponse(b'{"login": "owner"}', 200)
        )

        probe(self.URL, None, opener, 10.0)

        request = opener.captured
        self.assertIsNotNone(
            request,
            "fetch_probe must hand its opener a request to open",
        )
        self.assertNotIn(
            "authorization",
            _request_headers(request),
            "no token means no Authorization header on the request",
        )

    def test_token_request_carries_bearer_authorization_header(self):
        # Same header shape fetch_branch_rules builds
        # (anvilkit/pi/piguard.py: Authorization: Bearer {token}).
        probe = self._prober()
        opener = _CapturingOpener(
            _FakeResponse(b'{"login": "owner"}', 200)
        )

        probe(self.URL, "ghp_recordedtoken", opener, 10.0)

        request = opener.captured
        self.assertIsNotNone(request, "fetch_probe must hand its opener a request")
        headers = _request_headers(request)
        self.assertEqual(
            headers.get("authorization"),
            "Bearer ghp_recordedtoken",
            "a token must produce the same Authorization: Bearer <token> "
            "header shape fetch_branch_rules uses",
        )

    def test_request_headers_match_pinned_api_version(self):
        # Cited: doc/external/github/rest-api-endpoints-for-actions-
        # permissions.md and doc/external/github/rest-api-endpoints-for-
        # users.md pin X-GitHub-Api-Version: 2026-03-10 for the probe
        # endpoints; Accept: application/vnd.github+json is the module's
        # existing header for api.github.com requests.
        probe = self._prober()
        opener = _CapturingOpener(
            _FakeResponse(b'{"login": "owner"}', 200)
        )

        probe(self.URL, None, opener, 10.0)

        request = opener.captured
        self.assertIsNotNone(request, "fetch_probe must hand its opener a request")
        headers = _request_headers(request)
        self.assertEqual(
            headers.get("accept"),
            "application/vnd.github+json",
            "the probe must send the same Accept header the module already "
            "uses for api.github.com requests",
        )
        self.assertEqual(
            headers.get("x-github-api-version"),
            "2026-03-10",
            "the probe must pin the API version the saved endpoint docs use "
            "for the probe endpoints",
        )

    def test_timeout_is_passed_through_to_the_opener(self):
        probe = self._prober()
        opener = _CapturingOpener(_FakeResponse(b'{"login": "owner"}', 200))

        probe(self.URL, None, opener, 12.5)

        self.assertIs(
            opener.timeout,
            12.5,
            "fetch_probe must pass its timeout through to the opener",
        )

    def test_never_raises_across_every_recorded_failure_mode(self):
        probe = self._prober()
        for label, outcome in (
            ("URLError", urllib.error.URLError("Name or service not known")),
            ("socket.timeout", socket.timeout("timed out")),
            ("bare OSError", OSError("Network is unreachable")),
            (
                "HTTPError 403",
                urllib.error.HTTPError(self.URL, 403, "Forbidden", None, None),
            ),
            (
                "HTTPError 404",
                urllib.error.HTTPError(self.URL, 404, "Not Found", None, None),
            ),
        ):
            with self.subTest(failure=label):
                try:
                    status, headers, body, reason = probe(
                        self.URL, None, _opener(outcome), 10.0
                    )
                except Exception as exc:
                    self.fail(
                        "fetch_probe raised {} for the recorded {}; every "
                        "recorded failure mode must be returned, not "
                        "thrown".format(type(exc).__name__, label)
                    )
                if isinstance(outcome, urllib.error.HTTPError):
                    self.assertIsNone(
                        reason,
                        "an HTTPError is a successful observation - no "
                        "reason",
                    )
                    self.assertEqual(status, outcome.code)
                else:
                    self.assertEqual(
                        (status, headers, body),
                        (None, None, None),
                        "a transport failure must return the none-triple",
                    )
                    self.assertIsInstance(reason, str)
                    self.assertTrue(reason, "a transport failure must record a reason")


class SkippedFindingsTests(unittest.TestCase, _SkippedAssertions):
    """Behaviour 4 (rendering half): a skipped finding is visually distinct from a pass.

    ``skipped_findings(reason)`` yields one ``skipped`` finding per defined
    check - the four check constants (history_rewrite, review,
    update_restriction, file_paths) - each carrying the reason and a remedy
    naming what the user can do to make the check runnable.
    ``render_finding`` already carries the reason for a skipped finding; the
    rendered line must say the check could not run - never a passed-style
    ``ok:`` prefix.
    """

    def _skipped_findings(self) -> Any:
        producer = getattr(piguard, "skipped_findings", None)
        self.assertTrue(
            callable(producer),
            "anvilkit.pi.piguard.skipped_findings is not callable; the "
            "skipped-finding producer has not been implemented yet",
        )
        return producer

    def test_one_skipped_finding_per_check_carries_reason_and_remedy(self):
        reason = "GitHub was unreachable: connection refused"

        findings = self._skipped_findings()(reason)

        self._assert_skipped_findings(findings, reason)

    def test_rendered_skipped_finding_is_visually_distinct_from_a_pass(self):
        reason = "GitHub was unreachable: connection refused"
        findings = self._skipped_findings()(reason)
        passed_line = piguard.render_finding(
            piguard.check_history_rewrite(
                [rule("non_fast_forward", "main-guard")]
            )[0]
        )

        for finding in findings:
            with self.subTest(check=_field(finding, "check")):
                line = piguard.render_finding(finding)
                self.assertIn(
                    "skipped",
                    line.lower(),
                    "the rendered skipped line must say the check was skipped",
                )
                self.assertIn(
                    reason,
                    line,
                    "the rendered skipped line must carry the reason",
                )
                self.assertNotIn(
                    "ok:",
                    line,
                    "a skipped finding must never carry a passed-style "
                    "'ok:' prefix",
                )
                self.assertNotEqual(
                    line,
                    passed_line,
                    "a skipped finding is visually distinct from a pass",
                )

    def test_skipped_finding_per_check_carries_check_specific_danger(self):
        # A skipped finding must stand on its own rather than leaning on the
        # renderer: the danger text names the unmeasured hole of its own
        # check, so the four findings cannot all carry one shared danger -
        # the history_rewrite one differs from the review one, and the
        # update_restriction and file_paths findings name the update and
        # file-path holes rather than copying the first two.
        reason = "GitHub was unreachable: connection refused"

        findings = self._skipped_findings()(reason)

        self.assertEqual(
            len(findings),
            4,
            "one skipped finding expected per defined check: "
            "history_rewrite, review, update_restriction and file_paths",
        )
        texts: List[Tuple[str, str]] = []
        for finding in findings:
            with self.subTest(check=_field(finding, "check")):
                text = (
                    _field(finding, "danger")
                    or _field(finding, "reason")
                    or ""
                )
                self.assertTrue(
                    text,
                    "each skipped finding must carry a non-empty danger or "
                    "reason naming the unmeasured hole of its own check",
                )
                texts.append((_field(finding, "check") or "", text))
        distinct = {text for _check, text in texts}
        self.assertGreaterEqual(
            len(distinct),
            3,
            "the four skipped findings' danger texts must be specific to "
            "their check, not one shared copy: the two original checks "
            "already differ, so at least three distinct texts are expected "
            "across four findings",
        )


class FindingInvariantsTests(unittest.TestCase):
    """Behaviour 5: findings carry danger and remedy - a boundary pin.

    A finding with an empty remedy is a programming error, so this class
    sweeps EVERY finding the module can emit as of today - every documented
    rules-array shape through all four check functions
    (``check_history_rewrite``, ``check_review``, ``check_update`` and
    ``check_file_paths``), and the skipped findings for every fetch failure
    mode - and pins the invariants: a known status, a non-empty string
    remedy on every finding, a non-empty danger on every non-passing
    finding, and a renderable non-empty line. The sweep exercises
    the module as it is and may already pass; its job is to break on future
    drift, so a finding that later drops its remedy or its danger must fail
    these tests, and the assertions must never be weakened to get back to
    green.
    """

    _KNOWN_STATUSES = ("passed", "warn", "skipped", "fail")

    def _rule_shapes(self) -> List[Tuple[str, List[Dict[str, Any]]]]:
        """Every rules-array shape the check functions can be asked about today."""
        return [
            ("empty array", []),
            (
                "non_fast_forward alone",
                [rule("non_fast_forward", "main-guard")],
            ),
            ("deletion alone", [rule("deletion", "main-guard")]),
            (
                "pull_request alone, zero approvals",
                [pull_request_rule("main-guard", 0)],
            ),
            (
                "pull_request alone, one approval",
                [pull_request_rule("main-guard", 1)],
            ),
            (
                "all three rules, zero approvals",
                [
                    rule("non_fast_forward", "main-guard"),
                    rule("deletion", "main-guard"),
                    pull_request_rule("main-guard", 0),
                ],
            ),
            (
                "all three rules, one approval",
                [
                    rule("non_fast_forward", "main-guard"),
                    rule("deletion", "main-guard"),
                    pull_request_rule("main-guard", 1),
                ],
            ),
            (
                "update alone",
                [
                    update_rule(
                        "main-guard",
                        {"update_allows_fetch_and_merge": True},
                    )
                ],
            ),
            (
                "file_path_restriction alone",
                [
                    file_path_rule(
                        "main-guard",
                        {"restricted_file_paths": [".github/workflows/**"]},
                    )
                ],
            ),
            (
                "all five rules",
                [
                    rule("non_fast_forward", "main-guard"),
                    rule("deletion", "main-guard"),
                    pull_request_rule("main-guard", 1),
                    update_rule(
                        "main-guard",
                        {"update_allows_fetch_and_merge": True},
                    ),
                    file_path_rule(
                        "main-guard",
                        {"restricted_file_paths": [".github/workflows/**"]},
                    ),
                ],
            ),
            (
                "all five rules, weak parameters",
                [
                    rule("non_fast_forward", "main-guard"),
                    rule("deletion", "main-guard"),
                    pull_request_rule("main-guard", 0),
                    update_rule(
                        "main-guard",
                        {"update_allows_fetch_and_merge": False},
                    ),
                    file_path_rule(
                        "main-guard",
                        {"restricted_file_paths": []},
                    ),
                ],
            ),
        ]

    def _skip_reasons(self) -> List[Tuple[str, str]]:
        """(label, reason) for every fetch failure mode, over recorded openers."""
        url = "https://api.github.com/repos/owner/repo/rules/branches/main"
        pairs: List[Tuple[str, str]] = []
        for label, outcome in (
            ("no network", urllib.error.URLError("Name or service not known")),
            ("timeout", socket.timeout("timed out")),
            (
                "http 404",
                urllib.error.HTTPError(url, 404, "Not Found", None, None),
            ),
            ("non-JSON body", _FakeResponse(b"<html>GitHub</html>")),
        ):
            with self.subTest(skip_reason=label):
                rules, reason = piguard.fetch_branch_rules(
                    "owner", "repo", "main", opener=_opener(outcome)
                )
                self.assertIsNone(
                    rules,
                    "a failed fetch must not be reported as rules",
                )
                self.assertIsInstance(
                    reason,
                    str,
                    "a failed fetch must record a string reason",
                )
                self.assertTrue(
                    reason,
                    "a failed fetch must record a non-empty reason",
                )
            pairs.append((label, reason))
        return pairs

    def _every_finding(self) -> List[Tuple[str, Dict[str, Any]]]:
        """Every finding the module can emit as of today, with a label.

        Adding a rule type, a check, a status or a fetch failure mode to the
        module without adding it here would silently un-pin the invariant:
        keep the module's emitters and this sweep in sync.
        """
        findings: List[Tuple[str, Dict[str, Any]]] = []
        for label, rules in self._rule_shapes():
            for check in (
                piguard.check_history_rewrite,
                piguard.check_review,
                piguard.check_update,
                piguard.check_file_paths,
            ):
                for finding in check(rules):
                    findings.append(
                        (
                            "{}/{}: {} on rule {!r}".format(
                                label,
                                check.__name__,
                                _field(finding, "status"),
                                _field(finding, "rule"),
                            ),
                            finding,
                        )
                    )
        for label, reason in self._skip_reasons():
            for finding in piguard.skipped_findings(reason):
                findings.append(
                    (
                        "fetch({})/{}/{}".format(
                            label,
                            _field(finding, "check"),
                            _field(finding, "rule"),
                        ),
                        finding,
                    )
                )
        return findings

    def test_every_finding_the_module_can_emit_carries_danger_and_remedy(self):
        findings = self._every_finding()
        self.assertGreater(
            len(findings),
            0,
            "the sweep produced no findings; the input shapes must exercise "
            "the module's real output",
        )

        for label, finding in findings:
            with self.subTest(finding=label):
                status = _field(finding, "status")
                self.assertIn(
                    status,
                    self._KNOWN_STATUSES,
                    "finding status {!r} is not one of the four known "
                    "statuses; the report cannot interpret it".format(status),
                )
                remedy = _field(finding, "remedy")
                self.assertIsInstance(
                    remedy,
                    str,
                    "remedy must be a string, not {!r}".format(
                        type(remedy).__name__
                    ),
                )
                self.assertTrue(
                    remedy,
                    "a finding with an empty remedy is a programming error: "
                    "it cannot name the concrete fix",
                )
                if status != "passed":
                    danger = _field(finding, "danger")
                    self.assertIsInstance(
                        danger,
                        str,
                        "danger must be a string, not {!r}".format(
                            type(danger).__name__
                        ),
                    )
                    self.assertTrue(
                        danger,
                        "a non-passing finding ({}) must name what an agent "
                        "could do; its danger is empty".format(status),
                    )
                line = piguard.render_finding(finding)
                self.assertIsInstance(line, str)
                self.assertTrue(
                    line,
                    "render_finding must produce a non-empty line",
                )

    def test_non_passing_findings_name_a_doc_path_under_doc_external_github(self):
        checked = 0
        for label, finding in self._every_finding():
            status = _field(finding, "status")
            if status not in ("warn", "skipped"):
                continue
            checked += 1
            with self.subTest(finding=label):
                remedy = _field(finding, "remedy") or ""
                self.assertIn(
                    "doc/external/github/",
                    remedy,
                    "the {} finding on rule {!r} must name a doc path under "
                    "doc/external/github/ in its remedy, so a reviewer can "
                    "check the claim against the saved documentation".format(
                        status, _field(finding, "rule")
                    ),
                )
        self.assertGreater(
            checked,
            0,
            "the sweep produced no warn or skipped findings; the input shapes "
            "must produce some",
        )


class ParseGithubRemoteTests(unittest.TestCase):
    """Behaviour 6: owner/repo parsed from a GitHub remote URL.

    ``parse_github_remote(url)`` is expected to be a pure parser: the HTTPS
    and SSH forms of a GitHub remote yield the same ``(owner, repo)`` pair
    with any ``.git`` suffix stripped, and anything else - a non-GitHub
    host, an unparsable string, an empty owner or repo - yields a falsy
    return. It must never guess and never raise: a URL it cannot account
    for is a skip, not a guess (plans/pi-guard-verification.md, behaviour 6).
    """

    HTTPS_WITH = "https://github.com/owner/repo.git"
    HTTPS_BARE = "https://github.com/owner/repo"
    SSH_WITH = "git@github.com:owner/repo.git"
    SSH_BARE = "git@github.com:owner/repo"
    # HTTPS remotes with a userinfo component - the form git leaves behind
    # after a clone with an embedded token (plans/pi-guard-verification.md,
    # behaviour 6: a resolvable GitHub remote must never be a false skip).
    HTTPS_USERINFO = "https://user:token@github.com/owner/repo.git"
    HTTPS_USERINFO_BARE = "https://user@github.com/owner/repo"

    def _parser(self) -> Any:
        parser = getattr(piguard, "parse_github_remote", None)
        self.assertTrue(
            callable(parser),
            "anvilkit.pi.piguard.parse_github_remote is not callable; the "
            "GitHub remote parser has not been implemented yet",
        )
        return parser

    def test_https_remote_with_git_suffix_returns_owner_repo(self):
        parse = self._parser()

        self.assertEqual(parse(self.HTTPS_WITH), ("owner", "repo"))

    def test_https_remote_without_git_suffix_matches_git_form(self):
        parse = self._parser()

        self.assertEqual(
            parse(self.HTTPS_BARE),
            parse(self.HTTPS_WITH),
            "the .git suffix must not change the answer",
        )
        self.assertEqual(parse(self.HTTPS_BARE), ("owner", "repo"))

    def test_ssh_remote_forms_match_https_form(self):
        parse = self._parser()

        self.assertEqual(
            parse(self.SSH_WITH),
            parse(self.SSH_BARE),
            "the .git suffix must not change the answer on an SSH remote",
        )
        self.assertEqual(
            parse(self.SSH_WITH),
            parse(self.HTTPS_WITH),
            "HTTPS and SSH forms of the same remote must give the same answer",
        )
        self.assertEqual(parse(self.SSH_BARE), ("owner", "repo"))

    def test_https_remote_with_user_token_credentials_matches_clean_form(self):
        parse = self._parser()

        self.assertEqual(
            parse(self.HTTPS_USERINFO),
            ("owner", "repo"),
            "an HTTPS remote with embedded credentials is a resolvable "
            "GitHub remote - it must parse to the same (owner, repo) as "
            "the clean form, never a false skip",
        )
        self.assertEqual(
            parse(self.HTTPS_USERINFO),
            parse(self.HTTPS_WITH),
            "credentials in the URL must not change the answer",
        )

    def test_https_remote_with_username_only_userinfo_matches_clean_form(self):
        parse = self._parser()

        self.assertEqual(
            parse(self.HTTPS_USERINFO_BARE),
            ("owner", "repo"),
            "a username-only userinfo component must not change the answer",
        )
        self.assertEqual(
            parse(self.HTTPS_USERINFO_BARE),
            parse(self.HTTPS_BARE),
        )

    def test_parsed_credential_remote_returns_no_credential(self):
        parse = self._parser()
        for url in (self.HTTPS_USERINFO, self.HTTPS_USERINFO_BARE):
            with self.subTest(url=url):
                result = parse(url)

                self.assertIsNotNone(
                    result,
                    "a credentialed GitHub remote must parse, not skip",
                )
                self.assertNotIn(
                    "token",
                    result,
                    "the credential must never appear in a returned value",
                )
                self.assertNotIn(
                    "user",
                    result,
                    "the username must never appear in a returned value",
                )
                self.assertEqual(
                    result,
                    ("owner", "repo"),
                    "the returned tuple must be byte-equal to the "
                    "clean-form tuple: owner and repo are the only "
                    "things a parse can return",
                )

    def test_non_github_credential_remotes_do_not_parse(self):
        parse = self._parser()
        for url in (
            "https://user:token@bitbucket.org/owner/repo.git",
            "https://user@gitlab.com/owner/repo",
        ):
            with self.subTest(url=url):
                self.assertIsNone(
                    parse(url),
                    "credentials on a non-GitHub host must not make the "
                    "host parse - never a guess",
                )

    def test_non_github_remotes_do_not_parse(self):
        parse = self._parser()
        for url in (
            "https://bitbucket.org/owner/repo.git",
            "git@bitbucket.org:owner/repo.git",
            "https://gitlab.com/owner/repo.git",
        ):
            with self.subTest(url=url):
                self.assertIsNone(
                    parse(url),
                    "a non-GitHub remote must not parse - never a guess",
                )

    def test_unparsable_urls_return_none_without_raising(self):
        parse = self._parser()
        for url in (
            "https://github.com/owner",
            "not a url at all",
            "",
        ):
            with self.subTest(url=url):
                self.assertIsNone(
                    parse(url),
                    "an unparsable remote must not parse - never an exception",
                )


class ResolveRepositoryTests(unittest.TestCase):
    """Behaviour 6: owner/repo resolved from the target directory's origin.

    ``resolve_repository(path, runner=None)`` is expected to resolve the
    target repository's ``origin`` remote through an injectable runner - a
    callable that returns the origin URL, or returns empty / raises when
    there is no remote - and feed it to the pure parser. The suite runs
    offline: a GitHub origin in either form gives the parsed pair, a missing
    or non-GitHub origin gives a falsy return, so every network check
    becomes a skip rather than a guess.
    """

    def _resolver(self) -> Any:
        resolver = getattr(piguard, "resolve_repository", None)
        self.assertTrue(
            callable(resolver),
            "anvilkit.pi.piguard.resolve_repository is not callable; the "
            "repository-identity resolver has not been implemented yet",
        )
        return resolver

    def _fake_runner(self, url: Optional[str], exc: Any = None) -> Any:
        """A runner that plays back one recorded origin outcome.

        Accepts whatever argument shape the implementation hands it, so the
        test does not depend on the exact call signature (same seam
        discipline as ``_opener`` above).
        """

        def runner(*args: Any, **kwargs: Any) -> str:
            if exc is not None:
                raise exc
            if url is None:
                return ""
            return url

        return runner

    def test_origin_https_github_returns_pair(self):
        resolve = self._resolver()

        with tempfile.TemporaryDirectory() as path:
            result = resolve(
                path,
                runner=self._fake_runner("https://github.com/owner/repo.git"),
            )

        self.assertEqual(result, ("owner", "repo"))

    def test_origin_ssh_github_returns_same_pair(self):
        resolve = self._resolver()

        with tempfile.TemporaryDirectory() as path:
            https = resolve(
                path,
                runner=self._fake_runner("https://github.com/owner/repo"),
            )
            ssh = resolve(
                path,
                runner=self._fake_runner("git@github.com:owner/repo.git"),
            )

        self.assertEqual(
            ssh,
            https,
            "HTTPS and SSH origin remotes must give the same answer",
        )
        self.assertEqual(ssh, ("owner", "repo"))

    def test_origin_https_github_with_credentials_returns_same_pair(self):
        resolve = self._resolver()

        with tempfile.TemporaryDirectory() as path:
            credentialed = resolve(
                path,
                runner=self._fake_runner(
                    "https://user:token@github.com/owner/repo.git"
                ),
            )
            clean = resolve(
                path,
                runner=self._fake_runner("https://github.com/owner/repo.git"),
            )

        self.assertEqual(
            credentialed,
            clean,
            "a credentialed origin and the clean origin of the same "
            "repository must give the same answer - a resolvable GitHub "
            "remote must never be a false skip",
        )
        self.assertEqual(credentialed, ("owner", "repo"))

    def test_no_origin_returns_none(self):
        resolve = self._resolver()
        for label, runner in (
            ("empty output", self._fake_runner(None)),
            ("raises", self._fake_runner(None, exc=RuntimeError("no remote origin"))),
        ):
            with self.subTest(no_remote=label):
                with tempfile.TemporaryDirectory() as path:
                    self.assertIsNone(
                        resolve(path, runner=runner),
                        "no origin remote must yield no repository identity "
                        "- never a guess",
                    )

    def test_non_github_credential_origin_returns_none(self):
        resolve = self._resolver()
        for url in (
            "https://user:token@bitbucket.org/owner/repo.git",
            "https://user@gitlab.com/owner/repo",
        ):
            with self.subTest(url=url):
                with tempfile.TemporaryDirectory() as path:
                    self.assertIsNone(
                        resolve(path, runner=self._fake_runner(url)),
                        "credentials on a non-GitHub origin must not make "
                        "the origin resolvable - never a guess",
                    )

    def test_non_github_origin_returns_none(self):
        resolve = self._resolver()
        for url in (
            "https://bitbucket.org/owner/repo.git",
            "https://gitlab.com/owner/repo.git",
        ):
            with self.subTest(url=url):
                with tempfile.TemporaryDirectory() as path:
                    self.assertIsNone(
                        resolve(path, runner=self._fake_runner(url)),
                        "a non-GitHub origin must yield no repository "
                        "identity - never a guess",
                    )


class SummarizeTests(unittest.TestCase):
    """Behaviour 7: the exit-status seam - ``summarize(findings)``.

    The ``verify-guards`` command interprets its findings to decide its exit
    status. That interpretation is a pure function of the findings, so it is
    testable with no typer and no network: 0 when nothing failed, non-zero
    (1) when any finding has status ``fail``. ``warn`` and ``skipped`` alone
    yield 0: a warning or an unrunnable check is reported, not a failure.
    This slice emits no ``fail`` finding, but the contract is what the
    follow-up slice's fail findings will drive, so it is pinned now.
    """

    def _summarizer(self) -> Any:
        summarizer = getattr(piguard, "summarize", None)
        self.assertTrue(
            callable(summarizer),
            "anvilkit.pi.piguard.summarize is not callable; the exit-status "
            "seam has not been implemented yet",
        )
        return summarizer

    def _fail_finding(self) -> Dict[str, Any]:
        """One ``fail`` finding in the module's own finding shape."""
        return {
            "status": "fail",
            "check": "history_rewrite",
            "rule": "non_fast_forward",
            "danger": "branch history can be rewritten by a force push",
            "source": "main-protected",
            "remedy": "add a 'non_fast_forward' rule; see "
            + "doc/external/github/available-rules-for-rulesets.md",
        }

    def test_passed_warn_and_skipped_findings_alone_yield_zero(self):
        summarize = self._summarizer()
        findings = (
            piguard.check_history_rewrite([rule("non_fast_forward", "main-guard")])
            + piguard.check_review([rule("non_fast_forward", "main-guard")])
            + piguard.skipped_findings("GitHub was unreachable")
        )

        self.assertEqual(
            [f for f in findings if _field(f, "status") == "fail"],
            [],
            "fixture sanity: this slice emits no fail finding",
        )
        self.assertIn(
            _field(findings[0], "status"),
            ("passed", "warn", "skipped"),
            "fixture sanity: the findings are drawn from the three "
            "non-failing statuses",
        )

        self.assertEqual(
            summarize(findings),
            0,
            "warn and skipped alone must exit 0 - only a fail finding "
            "exits non-zero",
        )

    def test_exactly_one_fail_finding_yields_one(self):
        summarize = self._summarizer()
        findings = (
            piguard.check_history_rewrite(
                [
                    rule("non_fast_forward", "main-guard"),
                    rule("deletion", "main-guard"),
                ]
            )
            + piguard.check_review(
                [
                    rule("non_fast_forward", "main-guard"),
                    rule("deletion", "main-guard"),
                ]
            )
            + piguard.skipped_findings("GitHub was unreachable")
            + [self._fail_finding()]
        )
        self.assertEqual(
            [f for f in findings if _field(f, "status") == "fail"],
            [self._fail_finding()],
            "fixture sanity: exactly one fail finding among the passes, "
            "warns and skips",
        )

        self.assertEqual(
            summarize(findings),
            1,
            "a single fail finding among passes, warns and skips must "
            "yield the non-zero exit status 1",
        )

    def test_empty_findings_yield_zero(self):
        summarize = self._summarizer()

        self.assertEqual(
            summarize([]),
            0,
            "no findings at all means nothing failed",
        )


class RenderReportTests(unittest.TestCase):
    """Behaviour 7: the report seam - ``render_report(findings)``.

    The report always prints - including on failure - so it must contain one
    line per finding, in order, delegating each line to
    ``render_finding``: passed, warn, skipped and fail alike, nothing
    dropped. A pure function over the findings, so it is testable with no
    typer and no network.
    """

    def _report_renderer(self) -> Any:
        renderer = getattr(piguard, "render_report", None)
        self.assertTrue(
            callable(renderer),
            "anvilkit.pi.piguard.render_report is not callable; the report "
            "renderer has not been implemented yet",
        )
        return renderer

    def test_mixed_findings_render_one_line_each_in_order(self):
        render = self._report_renderer()
        passed = piguard.check_history_rewrite(
            [rule("non_fast_forward", "main-guard")]
        )[0]
        warn = piguard.check_review(
            [rule("non_fast_forward", "main-guard")]
        )[0]
        skipped = piguard.skipped_findings("GitHub was unreachable")[0]
        fail = {
            "status": "fail",
            "check": "history_rewrite",
            "rule": "non_fast_forward",
            "danger": "branch history can be rewritten by a force push",
            "source": "main-protected",
            "remedy": "add a 'non_fast_forward' rule; see "
            + "doc/external/github/available-rules-for-rulesets.md",
        }
        findings = [passed, warn, skipped, fail]
        self.assertEqual(
            [_field(f, "status") for f in findings],
            ["passed", "warn", "skipped", "fail"],
            "fixture sanity: one finding of each status",
        )

        lines = render(findings)

        self.assertIsInstance(lines, list)
        self.assertEqual(
            len(lines),
            4,
            "one line per finding - a report that drops a finding hides "
            "what happened, including on failure",
        )
        for finding, line in zip(findings, lines):
            with self.subTest(status=_field(finding, "status")):
                self.assertEqual(
                    line,
                    piguard.render_finding(finding),
                    "each report line must be render_finding of that "
                    "finding, so the report and the single-finding renderer "
                    "can never drift apart",
                )

    def test_empty_findings_render_empty_report(self):
        render = self._report_renderer()

        self.assertEqual(
            render([]),
            [],
            "no findings means no report lines",
        )


class RulesetWriteLockstepTests(unittest.TestCase):
    """Behaviour 9 of plans/verify-guards-five-rules.md: the ruleset-write /
    verify-guards lockstep - a boundary pin.

    ``build_ruleset()`` (anvilkit/pi/piruleset.py) is the writer side: the five
    rules Anvil provisions. ``check_all`` (anvilkit/pi/piguard.py) is the reader
    side: what verify-guards measures. A rule added to ``build_ruleset``
    without a matching check fails this test - which is its purpose. The
    fixture translates ``build_ruleset()["rules"]`` into the
    ``/rules/branches`` element shape (each element gains
    ``ruleset_source_type``, ``ruleset_source`` and ``ruleset_id``; the
    element's ``type`` and ``parameters`` are copied through unchanged into
    fresh dicts, so the ``build_ruleset()`` result is never mutated) and runs
    ``check_all`` over it with no live import: the live GitHub import stays a
    reader's step, never a suite step.
    """

    EXPECTED_REPORT_ORDER = (
        "non_fast_forward",
        "deletion",
        "pull_request",
        "update",
        "file_path_restriction",
    )

    def _check_all(self) -> Any:
        check_all = getattr(piguard, "check_all", None)
        self.assertTrue(
            callable(check_all),
            "anvilkit.pi.piguard.check_all is not callable; the check_all "
            "seam has not been implemented yet",
        )
        return check_all

    def _fixture(self) -> List[Dict[str, Any]]:
        """build_ruleset() rules translated into the /rules/branches shape.

        Fresh dicts throughout: the build_ruleset() result is copied, never
        mutated, so a check that misbehaves cannot poison the writer side.
        """
        fixture: List[Dict[str, Any]] = []
        for element in piruleset.build_ruleset()["rules"]:
            fresh: Dict[str, Any] = {
                "type": element["type"],
                "ruleset_source_type": "repository",
                "ruleset_source": "main-protected",
                "ruleset_id": 1,
            }
            if "parameters" in element:
                fresh["parameters"] = dict(element["parameters"])
            fixture.append(fresh)
        return fixture

    def test_check_all_over_build_ruleset_fixture_yields_five_passed_findings_one_per_rule(self):
        check_all = self._check_all()
        fixture = self._fixture()

        findings = check_all(fixture)

        self.assertEqual(
            len(findings),
            5,
            "one finding per rule build_ruleset writes - exactly five",
        )
        self.assertEqual(
            [_field(f, "status") for f in findings],
            ["passed"] * 5,
            "every rule build_ruleset writes must measure as passed - a "
            "rule the writer side provisions that the reader side cannot "
            "pass is a hole in the guard",
        )
        self.assertEqual(
            [_field(f, "rule") for f in findings],
            list(self.EXPECTED_REPORT_ORDER),
            "findings must report one per rule type, in the planned report "
            "order: non_fast_forward, deletion, pull_request, update, "
            "file_path_restriction",
        )
        by_rule = {_field(f, "rule"): f for f in findings}
        self.assertEqual(
            _field(by_rule["pull_request"], "required_approving_review_count"),
            1,
            "the review finding must record the count build_ruleset writes "
            "(required_approving_review_count: 1)",
        )
        self.assertIs(
            _field(by_rule["update"], "update_allows_fetch_and_merge"),
            True,
            "the update finding must record the value build_ruleset writes "
            "(update_allows_fetch_and_merge: True)",
        )
        self.assertEqual(
            _field(by_rule["file_path_restriction"], "restricted_file_paths"),
            [".github/workflows/**"],
            "the file-path finding must record the paths build_ruleset "
            "writes (restricted_file_paths: ['.github/workflows/**'])",
        )

    def test_check_all_covers_every_rule_build_ruleset_writes(self):
        """Lockstep: the rule types check_all reports must equal the rule
        types build_ruleset writes, and the count must stay exactly five.

        A rule added to build_ruleset without a matching check breaks the
        set equality and the count assertion - which is this test's purpose.
        The live GitHub import stays a reader's step, never a suite step.
        """
        check_all = self._check_all()
        fixture = self._fixture()

        findings = check_all(fixture)

        self.assertEqual(
            len(findings),
            5,
            "exactly five findings: build_ruleset writes five rules, so a "
            "sixth rule type on either side must break this test",
        )
        fixture_types = {element["type"] for element in fixture}
        finding_types = {_field(f, "rule") for f in findings}
        self.assertEqual(
            fixture_types,
            finding_types,
            "check_all must report exactly the rule types build_ruleset "
            "writes - a rule added to the writer side without a matching "
            "check (or a finding for a rule it does not write) is the hole "
            "this test exists to catch",
        )


class ProbeTargetAccessTests(unittest.TestCase):
    """Behaviour 2 of plans/verify-guards-token.md: ``probe_target_access``.

    ``probe_target_access(owner, repo, token, opener=None, timeout=None)``
    runs the first token-scope probe: a recorded
    ``GET /repos/{owner}/{repo}`` through :func:`anvilkit.pi.piguard.fetch_probe`
    (behaviour 1, already green), so the probe is only the interpretation of
    the observation, not a second fetch seam.

    The probe answers whether the token reaches the target repository at all:

    - ``200``  -> one ``passed`` finding: the target is reachable, so the
      later probes' denials are interpretable as withholdings.
    - ``404``  -> one ``warn`` finding: the token cannot reach the target
      repo at all, so no other probe's denial can be read as a withholding.
      The warn remedy must name a saved page under ``doc/external/github/``
      (behaviour 10's invariant: a doc path in every non-passing remedy).
    - ``401`` or any other status -> one ``skipped`` finding whose reason
      carries the status.
    - transport failure -> one ``skipped`` finding whose reason is non-empty.
    - ``token=None`` -> one ``skipped`` finding (behaviour 7), and no request
      may be attempted at all: a token-scope probe with no token establishes
      no fact about any token, and a probe must never issue an
      unauthenticated request and read its status as a token property.

    The finding dict shape is the one ``render_finding`` already consumes:
    ``status``, ``check``, ``rule``, ``danger``, ``source`` and ``remedy``
    (plus ``reason`` on a skip). Every test below runs over a recorded opener
    - no live network.
    """

    TOKEN = "ghp_recordedtoken"
    REPO_PATH = "/repos/owner/repo"

    def _prober(self) -> Any:
        prober = getattr(piguard, "probe_target_access", None)
        self.assertTrue(
            callable(prober),
            "anvilkit.pi.piguard.probe_target_access is not callable; the "
            "target-access token-scope probe has not been implemented yet",
        )
        return prober

    def test_recorded_200_yields_exactly_one_passed_finding(self):
        probe = self._prober()
        opener = _CapturingOpener(
            _FakeResponse(b'{"full_name": "owner/repo"}', 200)
        )

        findings = probe(
            "owner", "repo", self.TOKEN, opener=opener, timeout=10.0
        )

        self.assertIsInstance(findings, list)
        self.assertEqual(
            len(findings),
            1,
            "the target-access probe yields exactly one finding",
        )
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "passed",
            "a 200 means the target is reachable, so the later probes' "
            "denials are interpretable: the probe passes",
        )
        self.assertIsInstance(_field(finding, "remedy"), str)
        self.assertTrue(
            _field(finding, "remedy"),
            "every finding carries a non-empty remedy",
        )

    def test_recorded_404_yields_warn_naming_no_access_and_doc_path(self):
        # The 404 is the louder, different finding: the token cannot reach
        # the target repo at all, so no other probe's denial can be read as
        # a withholding. It is an HTTPError played back through the opener,
        # exactly as fetch_probe records it.
        probe = self._prober()
        url = "https://api.github.com" + self.REPO_PATH

        findings = probe(
            "owner",
            "repo",
            self.TOKEN,
            opener=_opener(
                urllib.error.HTTPError(url, 404, "Not Found", None, None)
            ),
            timeout=10.0,
        )

        self.assertIsInstance(findings, list)
        self.assertEqual(
            len(findings),
            1,
            "the target-access probe yields exactly one finding",
        )
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "warn",
            "a 404 on the target repo means the token cannot reach the "
            "target at all - a warn, because no other probe's denial can "
            "be read as a withholding",
        )
        self.assertIsInstance(_field(finding, "danger"), str)
        self.assertTrue(
            _field(finding, "danger"),
            "the warn must name the danger: the token reaches no target, so "
            "the other probes' denials are unreadable",
        )
        remedy = _field(finding, "remedy") or ""
        self.assertIn(
            "doc/external/github/",
            remedy,
            "the warn remedy must name a saved page under "
            "doc/external/github/, so a reviewer can check the claim "
            "against the saved documentation",
        )

    def test_recorded_401_yields_skipped_with_status_in_reason(self):
        probe = self._prober()
        url = "https://api.github.com" + self.REPO_PATH

        findings = probe(
            "owner",
            "repo",
            self.TOKEN,
            opener=_opener(
                urllib.error.HTTPError(url, 401, "Unauthorized", None, None)
            ),
            timeout=10.0,
        )

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "skipped",
            "a 401 on the target repo is not a scope answer the probe can "
            "interpret: it skips",
        )
        reason = _field(finding, "reason") or _field(finding, "danger") or ""
        self.assertIn(
            "401",
            reason,
            "the skipped finding's reason must carry the status 401, so "
            "the report shows why the probe did not run",
        )
        self.assertTrue(
            _field(finding, "remedy"),
            "every finding carries a non-empty remedy",
        )

    def test_recorded_other_status_yields_skipped_with_status_in_reason(self):
        probe = self._prober()
        url = "https://api.github.com" + self.REPO_PATH

        for status, phrase in (
            (500, "Internal Server Error"),
            (403, "Forbidden"),
            (503, "Service Unavailable"),
        ):
            with self.subTest(status=status):
                findings = probe(
                    "owner",
                    "repo",
                    self.TOKEN,
                    opener=_opener(
                        urllib.error.HTTPError(url, status, phrase, None, None)
                    ),
                    timeout=10.0,
                )

                self.assertEqual(len(findings), 1)
                finding = findings[0]
                self.assertEqual(
                    _field(finding, "status"),
                    "skipped",
                    "any status other than 200 or 404 is not a scope "
                    "answer the probe can interpret: it skips",
                )
                reason = (
                    _field(finding, "reason")
                    or _field(finding, "danger")
                    or ""
                )
                self.assertIn(
                    str(status),
                    reason,
                    "the skipped finding's reason must carry the status "
                    "{}, so the report shows why the probe did not "
                    "run".format(status),
                )
                self.assertTrue(
                    _field(finding, "remedy"),
                    "every finding carries a non-empty remedy",
                )

    def test_transport_failure_yields_skipped_with_nonempty_reason(self):
        probe = self._prober()
        for label, outcome in (
            ("URLError", urllib.error.URLError("Name or service not known")),
            ("socket.timeout", socket.timeout("timed out")),
            ("bare OSError", OSError("Network is unreachable")),
        ):
            with self.subTest(transport=label):
                findings = probe(
                    "owner",
                    "repo",
                    self.TOKEN,
                    opener=_opener(outcome),
                    timeout=10.0,
                )

                self.assertIsInstance(findings, list)
                self.assertEqual(
                    len(findings),
                    1,
                    "a transport failure yields one skipped finding, not "
                    "an exception",
                )
                finding = findings[0]
                self.assertEqual(
                    _field(finding, "status"),
                    "skipped",
                    "a transport failure is a skipped, not a pass or a "
                    "fail: a slow GitHub must not read as a scope answer",
                )
                reason = (
                    _field(finding, "reason")
                    or _field(finding, "danger")
                    or ""
                )
                self.assertIsInstance(reason, str)
                self.assertTrue(
                    reason,
                    "the skipped finding must carry a non-empty reason "
                    "naming the transport failure",
                )
                self.assertTrue(
                    _field(finding, "remedy"),
                    "every finding carries a non-empty remedy",
                )

    def test_no_token_yields_skipped_without_attempting_a_request(self):
        # Behaviour 7, this probe's share: a token-scope probe with no token
        # establishes no fact about any token, and no probe may issue an
        # unauthenticated request and read its status as a token property.
        probe = self._prober()
        opener = _CapturingOpener(
            _FakeResponse(b'{"full_name": "owner/repo"}', 200)
        )

        findings = probe(
            "owner", "repo", None, opener=opener, timeout=10.0
        )

        self.assertIsNone(
            opener.captured,
            "with no token the probe must not attempt a request at all: "
            "a token-scope probe reads a token property, and an "
            "unauthenticated request establishes no fact about any token",
        )
        self.assertIsInstance(findings, list)
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "skipped",
            "no token means the probe skips - never a pass or a warn",
        )
        reason = (
            _field(finding, "reason")
            or _field(finding, "danger")
            or ""
        )
        self.assertTrue(
            reason,
            "the skipped finding must carry a non-empty reason stating "
            "that a token-scope probe with no token establishes no fact "
            "about any token",
        )
        self.assertTrue(
            _field(finding, "remedy"),
            "every finding carries a non-empty remedy",
        )

    def test_request_targets_the_repos_owner_repo_endpoint(self):
        # The probe is GET /repos/{owner}/{repo}: the recorded request it
        # builds must carry that path, so the probe cannot be pointed at a
        # different endpoint later without a test change.
        probe = self._prober()
        opener = _CapturingOpener(_FakeResponse(b'{"full_name": "owner/repo"}', 200))

        probe("owner", "repo", self.TOKEN, opener=opener, timeout=10.0)

        request = opener.captured
        self.assertIsNotNone(
            request,
            "the probe must hand its opener a request to open",
        )
        url = getattr(request, "full_url", None) or getattr(request, "url", "")
        parsed = urllib.parse.urlparse(url)
        self.assertEqual(
            parsed.path,
            self.REPO_PATH,
            "the probe must issue GET /repos/{owner}/{repo} - the "
            "target-access endpoint - not any other path",
        )

    def test_findings_carry_the_module_finding_shape_and_render(self):
        # The finding dicts must match what render_finding already consumes:
        # a passed finding renders without a danger, a warn carries a
        # non-empty danger and remedy that survive rendering, and a skipped
        # finding renders with its reason. A shape mismatch here would make
        # render_finding fall through to the "unknown: ..." line and hide
        # the probe's result.
        probe = self._prober()
        url = "https://api.github.com" + self.REPO_PATH
        cases = [
            (
                "passed",
                _FakeResponse(b'{"full_name": "owner/repo"}', 200),
            ),
            (
                "warn",
                urllib.error.HTTPError(url, 404, "Not Found", None, None),
            ),
            (
                "skipped (401)",
                urllib.error.HTTPError(url, 401, "Unauthorized", None, None),
            ),
        ]

        for label, outcome in cases:
            with self.subTest(label=label):
                findings = probe(
                    "owner",
                    "repo",
                    self.TOKEN,
                    opener=_opener(outcome),
                    timeout=10.0,
                )
                self.assertEqual(len(findings), 1)
                finding = findings[0]
                self.assertIn(
                    _field(finding, "status"),
                    ("passed", "warn", "skipped", "fail"),
                    "finding status must be one of the four known statuses",
                )
                self.assertTrue(
                    _field(finding, "check"),
                    "every finding carries a non-empty check name",
                )
                self.assertIsInstance(_field(finding, "remedy"), str)
                self.assertTrue(
                    _field(finding, "remedy"),
                    "every finding carries a non-empty remedy",
                )
                line = piguard.render_finding(finding)
                self.assertIsInstance(line, str)
                self.assertTrue(
                    line,
                    "render_finding must produce a non-empty line for the "
                    "probe's finding",
                )
                self.assertNotIn(
                    "unknown:",
                    line,
                    "the probe's finding must render through the known "
                    "branches, not fall through to 'unknown:' - a shape "
                    "mismatch would hide the probe's result",
                )
                if _field(finding, "status") == "warn":
                    self.assertIn(
                        _field(finding, "danger"),
                        line,
                        "the rendered warn line must name the danger",
                    )
                    self.assertIn(
                        _field(finding, "remedy"),
                        line,
                        "the rendered warn line must name the remedy",
                    )
                if _field(finding, "status") == "passed":
                    self.assertNotIn(
                        "warn:",
                        line,
                        "a passed finding must not render as a warn",
                    )
                if _field(finding, "status") == "skipped":
                    reason = (
                        _field(finding, "reason")
                        or _field(finding, "danger")
                        or ""
                    )
                    self.assertIn(
                        reason,
                        line,
                        "the rendered skipped line must carry the reason",
                    )

    def test_never_raises_across_every_recorded_mode(self):
        probe = self._prober()
        url = "https://api.github.com" + self.REPO_PATH
        modes = [
            ("200", _FakeResponse(b'{"full_name": "owner/repo"}', 200)),
            (
                "404",
                urllib.error.HTTPError(url, 404, "Not Found", None, None),
            ),
            (
                "401",
                urllib.error.HTTPError(url, 401, "Unauthorized", None, None),
            ),
            (
                "500",
                urllib.error.HTTPError(url, 500, "Internal Server Error", None, None),
            ),
            (
                "URLError",
                urllib.error.URLError("Name or service not known"),
            ),
            ("socket.timeout", socket.timeout("timed out")),
            ("bare OSError", OSError("Network is unreachable")),
        ]
        for label, outcome in modes + [("no token", None)]:
            with self.subTest(mode=label):
                try:
                    if outcome is None:
                        findings = probe(
                            "owner", "repo", None,
                            opener=_CapturingOpener(_FakeResponse(b"{}", 200)),
                            timeout=10.0,
                        )
                    else:
                        findings = probe(
                            "owner",
                            "repo",
                            self.TOKEN,
                            opener=_opener(outcome),
                            timeout=10.0,
                        )
                except Exception as exc:
                    self.fail(
                        "probe_target_access raised {} for the recorded {}; "
                        "every recorded mode must return a finding list, "
                        "not an exception".format(type(exc).__name__, label)
                    )
                self.assertIsInstance(
                    findings,
                    list,
                    "every recorded mode returns a finding list",
                )
                self.assertEqual(
                    len(findings),
                    1,
                    "the target-access probe yields exactly one finding",
                )


class ProbeAdministrationTests(unittest.TestCase):
    """Behaviour 3 of plans/verify-guards-token.md: ``probe_administration``.

    ``probe_administration(owner, repo, token, opener=None, timeout=None)``
    runs the administration probe: a recorded
    ``GET /repos/{owner}/{repo}/actions/permissions`` through
    :func:`anvilkit.pi.piguard.fetch_probe` (behaviour 1, already green) -
    the endpoint the saved page
    ``doc/external/github/rest-api-endpoints-for-actions-permissions.md``
    documents as gated on "Administration" repository permissions (read), so
    a denial is the compliant answer and a ``200`` is the dangerous one.

    The probe answers whether the token holds Administration on the target:

    - ``403``  -> one ``passed`` finding: administration is withheld.
    - ``200``  -> one ``fail`` finding - the first emittable ``fail`` in the
      module: the token can delete or reconfigure the repo and raise the
      default ``GITHUB_TOKEN`` to write. The fail finding carries both a
      non-empty danger (the consequence) and a non-empty remedy naming a
      saved page under ``doc/external/github/`` (behaviour 10's invariants).
      Its rendering is behaviour 9's job, so these tests assert the finding
      dict fields directly.
    - ``404``  -> one ``warn`` finding: the page documents only ``200``, so a
      404 is ambiguous between "administration withheld" and "no access at
      all" - the warn names behaviour 2's target-access finding as the
      disambiguator.
    - ``401`` or any other status -> one ``skipped`` finding whose reason
      carries the status.
    - transport failure -> one ``skipped`` finding whose reason is non-empty.
    - ``token=None`` -> one ``skipped`` finding (behaviour 7), and no request
      may be attempted at all: a token-scope probe with no token establishes
      no fact about any token.

    The finding dict shape is the one ``render_finding`` already consumes:
    ``status``, ``check``, ``rule``, ``danger``, ``source`` and ``remedy``
    (plus ``reason`` on a skip). Every test below runs over a recorded opener
    - no live network.
    """

    TOKEN = "ghp_recordedtoken"
    REPO_PATH = "/repos/owner/repo/actions/permissions"
    _200_BODY = (
        b'{"enabled": true, "allowed_actions": "selected", '
        b'"sha_pinning_required": true}'
    )

    def _prober(self) -> Any:
        prober = getattr(piguard, "probe_administration", None)
        self.assertTrue(
            callable(prober),
            "anvilkit.pi.piguard.probe_administration is not callable; the "
            "administration token-scope probe has not been implemented yet",
        )
        return prober

    def test_recorded_403_yields_exactly_one_passed_finding(self):
        # A 403 is the compliant answer to this probe - the endpoint is
        # gated on Administration read, so a denial is the data, not a
        # failure (doc/external/github/rest-api-endpoints-for-actions-
        # permissions.md). It is an HTTPError played back through the
        # opener, exactly as fetch_probe records it.
        probe = self._prober()
        url = "https://api.github.com" + self.REPO_PATH

        findings = probe(
            "owner",
            "repo",
            self.TOKEN,
            opener=_opener(
                urllib.error.HTTPError(url, 403, "Forbidden", None, None)
            ),
            timeout=10.0,
        )

        self.assertIsInstance(findings, list)
        self.assertEqual(
            len(findings),
            1,
            "the administration probe yields exactly one finding",
        )
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "passed",
            "a 403 means administration is withheld - the compliant "
            "answer: the probe passes",
        )
        self.assertIsInstance(_field(finding, "remedy"), str)
        self.assertTrue(
            _field(finding, "remedy"),
            "every finding carries a non-empty remedy",
        )

    def test_recorded_200_yields_exactly_one_fail_finding_with_danger_and_remedy(self):
        # The first emittable fail in the module. A 200 means the token
        # holds Administration on the target: it can delete or reconfigure
        # the repo and raise the default GITHUB_TOKEN to write
        # (doc/external/github/rest-api-endpoints-for-actions-permissions.md,
        # "What administration: write would let an agent do"). The fail
        # finding must carry BOTH a non-empty danger stating the
        # consequence and a non-empty remedy (behaviour 10's invariants).
        # render_finding has no fail branch yet - behaviour 9 owns its
        # rendering - so this test asserts the finding dict fields directly.
        probe = self._prober()
        opener = _CapturingOpener(_FakeResponse(self._200_BODY, 200))

        findings = probe(
            "owner", "repo", self.TOKEN, opener=opener, timeout=10.0
        )

        self.assertIsInstance(findings, list)
        self.assertEqual(
            len(findings),
            1,
            "the administration probe yields exactly one finding",
        )
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "fail",
            "a 200 means the token holds Administration on the target - "
            "the probe fails; this is the first emittable fail finding in "
            "the module",
        )
        danger = _field(finding, "danger")
        self.assertIsInstance(danger, str)
        self.assertTrue(
            danger,
            "the fail finding must carry a non-empty danger stating the "
            "consequence - a fail that cannot say what the token can do "
            "is a programming error (behaviour 10)",
        )
        self.assertIn(
            "deleted",
            danger,
            "the fail danger must state that the repository can be "
            "deleted or reconfigured",
        )
        self.assertIn(
            "reconfigured",
            danger,
            "the fail danger must state that the repository can be "
            "deleted or reconfigured",
        )
        self.assertIn(
            "GITHUB_TOKEN",
            danger,
            "the fail danger must state that the default GITHUB_TOKEN can "
            "be raised to write",
        )
        remedy = _field(finding, "remedy")
        self.assertIsInstance(remedy, str)
        self.assertTrue(
            remedy,
            "the fail finding must carry a non-empty remedy - every "
            "finding must say how to fix the danger",
        )
        self.assertIn(
            "doc/external/github/",
            remedy,
            "the fail remedy must name a saved page under "
            "doc/external/github/, so a reviewer can check the claim "
            "against the saved documentation",
        )

    def test_recorded_404_yields_warn_naming_disambiguator_and_undocumented_deny(self):
        # The saved page documents only 200 for this endpoint - the denial
        # code is not stated (doc/external/github/rest-api-endpoints-for-
        # actions-permissions.md). A 404 is therefore ambiguous between
        # "administration withheld" and "no access at all", so the probe
        # warns and names behaviour 2's target-access finding as the
        # disambiguator - it is the only finding that tells the two cases
        # apart.
        probe = self._prober()
        url = "https://api.github.com" + self.REPO_PATH

        findings = probe(
            "owner",
            "repo",
            self.TOKEN,
            opener=_opener(
                urllib.error.HTTPError(url, 404, "Not Found", None, None)
            ),
            timeout=10.0,
        )

        self.assertIsInstance(findings, list)
        self.assertEqual(
            len(findings),
            1,
            "the administration probe yields exactly one finding",
        )
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "warn",
            "a 404 on an endpoint that documents only 200 is ambiguous "
            "between withheld and no-access - a warn, not a pass and not "
            "a fail",
        )
        self.assertIsInstance(_field(finding, "danger"), str)
        self.assertTrue(
            _field(finding, "danger"),
            "the warn must name the danger: the report cannot rule out "
            "that the token holds Administration, only that the denial "
            "is unreadable",
        )
        text = " ".join(
            part
            for part in (
                _field(finding, "danger") or "",
                _field(finding, "reason") or "",
                _field(finding, "remedy") or "",
            )
            if part
        )
        self.assertTrue(
            piguard.CHECK_TARGET_ACCESS in text
            or "target access" in text,
            "the 404 warn must name behaviour 2's target-access finding "
            "as the disambiguator between 'administration withheld' and "
            "'no access at all'",
        )
        self.assertIn(
            "200",
            text,
            "the 404 warn must note that only 200 is documented for the "
            "endpoint, so the denial code is undocumented",
        )
        self.assertIn(
            "documented",
            text,
            "the 404 warn must state that the endpoint's denial code is "
            "not documented",
        )
        self.assertIn(
            "doc/external/github/",
            _field(finding, "remedy") or "",
            "the warn remedy must name a saved page under "
            "doc/external/github/, so a reviewer can check the claim "
            "against the saved documentation",
        )

    def test_recorded_401_yields_skipped_with_status_in_reason(self):
        probe = self._prober()
        url = "https://api.github.com" + self.REPO_PATH

        findings = probe(
            "owner",
            "repo",
            self.TOKEN,
            opener=_opener(
                urllib.error.HTTPError(url, 401, "Unauthorized", None, None)
            ),
            timeout=10.0,
        )

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "skipped",
            "a 401 on the permissions endpoint is not a scope answer the "
            "probe can interpret: it skips",
        )
        reason = _field(finding, "reason") or _field(finding, "danger") or ""
        self.assertIn(
            "401",
            reason,
            "the skipped finding's reason must carry the status 401, so "
            "the report shows why the probe did not run",
        )
        self.assertTrue(
            _field(finding, "remedy"),
            "every finding carries a non-empty remedy",
        )

    def test_recorded_other_status_yields_skipped_with_status_in_reason(self):
        probe = self._prober()
        url = "https://api.github.com" + self.REPO_PATH

        for status, phrase in (
            (500, "Internal Server Error"),
            (503, "Service Unavailable"),
        ):
            with self.subTest(status=status):
                findings = probe(
                    "owner",
                    "repo",
                    self.TOKEN,
                    opener=_opener(
                        urllib.error.HTTPError(url, status, phrase, None, None)
                    ),
                    timeout=10.0,
                )

                self.assertEqual(len(findings), 1)
                finding = findings[0]
                self.assertEqual(
                    _field(finding, "status"),
                    "skipped",
                    "any status other than 403, 200 or 404 is not a scope "
                    "answer the probe can interpret: it skips",
                )
                reason = (
                    _field(finding, "reason")
                    or _field(finding, "danger")
                    or ""
                )
                self.assertIn(
                    str(status),
                    reason,
                    "the skipped finding's reason must carry the status "
                    "{}, so the report shows why the probe did not "
                    "run".format(status),
                )
                self.assertTrue(
                    _field(finding, "remedy"),
                    "every finding carries a non-empty remedy",
                )

    def test_transport_failure_yields_skipped_with_nonempty_reason(self):
        probe = self._prober()
        for label, outcome in (
            ("URLError", urllib.error.URLError("Name or service not known")),
            ("socket.timeout", socket.timeout("timed out")),
            ("bare OSError", OSError("Network is unreachable")),
        ):
            with self.subTest(transport=label):
                findings = probe(
                    "owner",
                    "repo",
                    self.TOKEN,
                    opener=_opener(outcome),
                    timeout=10.0,
                )

                self.assertIsInstance(findings, list)
                self.assertEqual(
                    len(findings),
                    1,
                    "a transport failure yields one skipped finding, not "
                    "an exception",
                )
                finding = findings[0]
                self.assertEqual(
                    _field(finding, "status"),
                    "skipped",
                    "a transport failure is a skipped, not a pass or a "
                    "fail: a slow GitHub must not read as a scope answer",
                )
                reason = (
                    _field(finding, "reason")
                    or _field(finding, "danger")
                    or ""
                )
                self.assertIsInstance(reason, str)
                self.assertTrue(
                    reason,
                    "the skipped finding must carry a non-empty reason "
                    "naming the transport failure",
                )
                self.assertTrue(
                    _field(finding, "remedy"),
                    "every finding carries a non-empty remedy",
                )

    def test_no_token_yields_skipped_without_attempting_a_request(self):
        # Behaviour 7, this probe's share: a token-scope probe with no
        # token establishes no fact about any token, and no probe may
        # issue an unauthenticated request and read its status as a token
        # property.
        probe = self._prober()
        opener = _CapturingOpener(_FakeResponse(self._200_BODY, 200))

        findings = probe(
            "owner", "repo", None, opener=opener, timeout=10.0
        )

        self.assertIsNone(
            opener.captured,
            "with no token the probe must not attempt a request at all: "
            "a token-scope probe reads a token property, and an "
            "unauthenticated request establishes no fact about any token",
        )
        self.assertIsInstance(findings, list)
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "skipped",
            "no token means the probe skips - never a pass, a warn or a "
            "fail",
        )
        reason = (
            _field(finding, "reason")
            or _field(finding, "danger")
            or ""
        )
        self.assertTrue(
            reason,
            "the skipped finding must carry a non-empty reason stating "
            "that a token-scope probe with no token establishes no fact "
            "about any token",
        )
        self.assertTrue(
            _field(finding, "remedy"),
            "every finding carries a non-empty remedy",
        )

    def test_request_targets_the_actions_permissions_endpoint(self):
        # The probe is GET /repos/{owner}/{repo}/actions/permissions: the
        # recorded request it builds must carry that path, so the probe
        # cannot be pointed at a different endpoint later without a test
        # change.
        probe = self._prober()
        opener = _CapturingOpener(_FakeResponse(self._200_BODY, 200))

        probe("owner", "repo", self.TOKEN, opener=opener, timeout=10.0)

        request = opener.captured
        self.assertIsNotNone(
            request,
            "the probe must hand its opener a request to open",
        )
        url = getattr(request, "full_url", None) or getattr(request, "url", "")
        parsed = urllib.parse.urlparse(url)
        self.assertEqual(
            parsed.path,
            self.REPO_PATH,
            "the probe must issue GET "
            "/repos/{owner}/{repo}/actions/permissions - the "
            "administration endpoint - not any other path",
        )

    def test_findings_carry_the_module_finding_shape_and_render(self):
        # The finding dicts must match what render_finding already
        # consumes: a passed finding (403) renders without a danger, a
        # warn (404) carries a non-empty danger and remedy that survive
        # rendering, and a skipped finding (401) renders with its reason.
        # The fail finding (200) is asserted on its dict fields only -
        # render_finding has no fail branch yet, that is behaviour 9's
        # job, and a render assertion here would fail for the wrong
        # reason (the renderer, not the probe).
        probe = self._prober()
        url = "https://api.github.com" + self.REPO_PATH
        renderable_cases = [
            (
                "passed (403)",
                urllib.error.HTTPError(url, 403, "Forbidden", None, None),
            ),
            (
                "warn (404)",
                urllib.error.HTTPError(url, 404, "Not Found", None, None),
            ),
            (
                "skipped (401)",
                urllib.error.HTTPError(url, 401, "Unauthorized", None, None),
            ),
        ]

        for label, outcome in renderable_cases:
            with self.subTest(label=label):
                findings = probe(
                    "owner",
                    "repo",
                    self.TOKEN,
                    opener=_opener(outcome),
                    timeout=10.0,
                )
                self.assertEqual(len(findings), 1)
                finding = findings[0]
                self.assertIn(
                    _field(finding, "status"),
                    ("passed", "warn", "skipped", "fail"),
                    "finding status must be one of the four known statuses",
                )
                self.assertTrue(
                    _field(finding, "check"),
                    "every finding carries a non-empty check name",
                )
                self.assertIsInstance(_field(finding, "remedy"), str)
                self.assertTrue(
                    _field(finding, "remedy"),
                    "every finding carries a non-empty remedy",
                )
                line = piguard.render_finding(finding)
                self.assertIsInstance(line, str)
                self.assertTrue(
                    line,
                    "render_finding must produce a non-empty line for the "
                    "probe's finding",
                )
                self.assertNotIn(
                    "unknown:",
                    line,
                    "the probe's finding must render through the known "
                    "branches, not fall through to 'unknown:' - a shape "
                    "mismatch would hide the probe's result",
                )
                if _field(finding, "status") == "warn":
                    self.assertIn(
                        _field(finding, "danger"),
                        line,
                        "the rendered warn line must name the danger",
                    )
                    self.assertIn(
                        _field(finding, "remedy"),
                        line,
                        "the rendered warn line must name the remedy",
                    )
                if _field(finding, "status") == "skipped":
                    reason = (
                        _field(finding, "reason")
                        or _field(finding, "danger")
                        or ""
                    )
                    self.assertIn(
                        reason,
                        line,
                        "the rendered skipped line must carry the reason",
                    )

        # The fail finding, dict-level only: behaviour 9 covers its
        # rendering.
        with self.subTest(label="fail (200), dict-level"):
            findings = probe(
                "owner",
                "repo",
                self.TOKEN,
                opener=_opener(_FakeResponse(self._200_BODY, 200)),
                timeout=10.0,
            )
            self.assertEqual(len(findings), 1)
            finding = findings[0]
            self.assertEqual(_field(finding, "status"), "fail")
            self.assertTrue(
                _field(finding, "check"),
                "every finding carries a non-empty check name",
            )
            self.assertIsInstance(_field(finding, "danger"), str)
            self.assertTrue(
                _field(finding, "danger"),
                "the fail finding's danger must be non-empty",
            )
            self.assertIsInstance(_field(finding, "remedy"), str)
            self.assertTrue(
                _field(finding, "remedy"),
                "the fail finding's remedy must be non-empty",
            )

    def test_never_raises_across_every_recorded_mode(self):
        probe = self._prober()
        url = "https://api.github.com" + self.REPO_PATH
        modes = [
            (
                "403",
                urllib.error.HTTPError(url, 403, "Forbidden", None, None),
            ),
            ("200", _FakeResponse(self._200_BODY, 200)),
            (
                "404",
                urllib.error.HTTPError(url, 404, "Not Found", None, None),
            ),
            (
                "401",
                urllib.error.HTTPError(url, 401, "Unauthorized", None, None),
            ),
            (
                "500",
                urllib.error.HTTPError(url, 500, "Internal Server Error", None, None),
            ),
            (
                "URLError",
                urllib.error.URLError("Name or service not known"),
            ),
            ("socket.timeout", socket.timeout("timed out")),
            ("bare OSError", OSError("Network is unreachable")),
        ]
        for label, outcome in modes + [("no token", None)]:
            with self.subTest(mode=label):
                try:
                    if outcome is None:
                        findings = probe(
                            "owner", "repo", None,
                            opener=_CapturingOpener(
                                _FakeResponse(self._200_BODY, 200)
                            ),
                            timeout=10.0,
                        )
                    else:
                        findings = probe(
                            "owner",
                            "repo",
                            self.TOKEN,
                            opener=_opener(outcome),
                            timeout=10.0,
                        )
                except Exception as exc:
                    self.fail(
                        "probe_administration raised {} for the recorded "
                        "{}; every recorded mode must return a finding "
                        "list, not an exception".format(
                            type(exc).__name__, label
                        )
                    )
                self.assertIsInstance(
                    findings,
                    list,
                    "every recorded mode returns a finding list",
                )
                self.assertEqual(
                    len(findings),
                    1,
                    "the administration probe yields exactly one finding",
                )


class ProbeClassicTokenTests(unittest.TestCase):
    """Behaviour 4 of plans/verify-guards-token.md: ``probe_classic_token``.

    ``probe_classic_token(token=None, opener=None, timeout=None)`` runs the
    classic-token probe: a recorded ``GET /user`` through
    :func:`anvilkit.pi.piguard.fetch_probe` (behaviour 1, already green) -
    the endpoint needs no permissions on a fine-grained token and answers
    ``401`` unauthenticated
    (doc/external/github/rest-api-endpoints-for-users.md).

    The saved page settles the discriminator by a **negative**: the
    documented ``GET /user`` 200 body has **no ``scopes`` key at all**, so
    the scope list travels in the ``X-OAuth-Scopes`` response header -
    GitHub's own example shows ``X-OAuth-Scopes: repo, user`` - and scopes
    are normalized, so the honest discriminator is the header **present and
    non-empty**, never an exact scope string
    (doc/external/github/scopes-for-oauth-apps.md):

    - header present and non-empty (any casing) -> one ``fail`` finding
      quoting the scopes verbatim: a classic token grants every repo the
      owner can see, so the repo-scope guarantee is void regardless of the
      other probes. The finding is asserted on its dict fields only -
      ``render_finding``'s fail branch is behaviour 9's job.
    - header present but empty, or absent -> one ``passed`` finding worded
      "no classic OAuth scope header was returned" - never "this is a
      fine-grained token", which the docs do not license.
    - ``401`` -> one ``skipped`` finding whose reason carries the status.
    - transport failure -> one ``skipped`` finding whose reason is
      non-empty.
    - ``token=None`` -> one ``skipped`` finding (behaviour 7), and no
      request may be attempted at all.

    The body is never parsed for a ``scopes`` field - no such field exists.
    The finding dict shape is the one ``render_finding`` already consumes:
    ``status``, ``check``, ``rule``, ``danger``, ``source`` and ``remedy``
    (plus ``reason`` on a skip). Every test below runs over a recorded
    opener - no live network.
    """

    TOKEN = "ghp_recordedtoken"
    USER_PATH = "/user"
    # The documented GET /user 200 body (abridged from the saved page): the
    # full documented response contains no "scopes" key, and the probe must
    # not look for one.
    _USER_BODY = (
        b'{"login": "octocat", "id": 1, "type": "User", "site_admin": false}'
    )

    def _prober(self) -> Any:
        prober = getattr(piguard, "probe_classic_token", None)
        self.assertTrue(
            callable(prober),
            "anvilkit.pi.piguard.probe_classic_token is not callable; the "
            "classic-token token-scope probe has not been implemented yet",
        )
        return prober

    def test_recorded_200_with_nonempty_scopes_header_yields_one_fail_quoting_scopes(self):
        # The second emittable fail in the module. A non-empty
        # X-OAuth-Scopes header means the token is classic: it grants
        # access to every repository the owner can see, so the
        # repo-scope guarantee the other probes protect is void
        # (doc/external/github/scopes-for-oauth-apps.md,
        # doc/external/github/fine-grained-personal-access-tokens.md).
        # render_finding has no fail branch yet - behaviour 9 owns its
        # rendering - so this test asserts the finding dict fields
        # directly.
        probe = self._prober()
        opener = _CapturingOpener(
            _FakeResponse(
                self._USER_BODY,
                200,
                headers={"X-OAuth-Scopes": "repo, workflow"},
            )
        )

        findings = probe(self.TOKEN, opener=opener, timeout=10.0)

        self.assertIsInstance(findings, list)
        self.assertEqual(
            len(findings),
            1,
            "the classic-token probe yields exactly one finding",
        )
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "fail",
            "a non-empty X-OAuth-Scopes header means the token is "
            "classic: the probe fails",
        )
        danger = _field(finding, "danger")
        self.assertIsInstance(danger, str)
        self.assertTrue(
            danger,
            "the fail finding must carry a non-empty danger stating the "
            "consequence (behaviour 10)",
        )
        lowered = danger.lower()
        self.assertIn(
            "repo",
            lowered,
            "the fail danger must state that a classic token grants "
            "access to the repositories the owner can see",
        )
        self.assertTrue(
            "every" in lowered or "all" in lowered,
            "the fail danger must state that the access is to every "
            "repository the owner can see, not a selected subset",
        )
        self.assertIn(
            "void",
            lowered,
            "the fail danger must state that the repo-scope guarantee "
            "is void",
        )
        self.assertIn(
            "guarantee",
            lowered,
            "the fail danger must name the repo-scope guarantee that is "
            "void regardless of the other probes",
        )
        self.assertIn(
            "repo, workflow",
            danger,
            "the fail danger must quote the recorded scopes verbatim",
        )
        remedy = _field(finding, "remedy")
        self.assertIsInstance(remedy, str)
        self.assertTrue(
            remedy,
            "the fail finding must carry a non-empty remedy - every "
            "finding must say how to fix the danger",
        )
        self.assertIn(
            "doc/external/github/",
            remedy,
            "the fail remedy must name a saved page under "
            "doc/external/github/, so a reviewer can check the claim "
            "against the saved documentation",
        )

    def test_recorded_200_with_empty_scopes_header_yields_exactly_one_passed_finding(self):
        # An empty X-OAuth-Scopes header carries no scopes: the probe
        # passes with the "no header returned" wording, never a claim
        # about what kind of token this is.
        probe = self._prober()
        opener = _CapturingOpener(
            _FakeResponse(self._USER_BODY, 200, headers={"X-OAuth-Scopes": ""})
        )

        findings = probe(self.TOKEN, opener=opener, timeout=10.0)

        self.assertIsInstance(findings, list)
        self.assertEqual(
            len(findings),
            1,
            "the classic-token probe yields exactly one finding",
        )
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "passed",
            "an empty X-OAuth-Scopes header carries no scopes: the "
            "probe passes",
        )
        self.assertIsInstance(_field(finding, "remedy"), str)
        self.assertTrue(
            _field(finding, "remedy"),
            "every finding carries a non-empty remedy",
        )

    def test_recorded_200_with_scopes_header_absent_yields_exactly_one_passed_finding(self):
        probe = self._prober()
        opener = _CapturingOpener(_FakeResponse(self._USER_BODY, 200))

        findings = probe(self.TOKEN, opener=opener, timeout=10.0)

        self.assertIsInstance(findings, list)
        self.assertEqual(
            len(findings),
            1,
            "the classic-token probe yields exactly one finding",
        )
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "passed",
            "a missing X-OAuth-Scopes header means no classic OAuth "
            "scope header was returned: the probe passes",
        )
        self.assertIsInstance(_field(finding, "remedy"), str)
        self.assertTrue(
            _field(finding, "remedy"),
            "every finding carries a non-empty remedy",
        )

    def test_passed_finding_never_claims_the_token_is_fine_grained(self):
        # The docs do not license "this is a fine-grained token": GitHub
        # documents no X-OAuth-Scopes semantics for fine-grained PATs
        # (doc/external/github/scopes-for-oauth-apps.md), so an absent or
        # empty header is only "no classic OAuth scope header was
        # returned" - a statement about what the response did not carry,
        # not a classification of the token.
        probe = self._prober()
        cases = [
            ("header absent", _FakeResponse(self._USER_BODY, 200)),
            (
                "header empty",
                _FakeResponse(
                    self._USER_BODY, 200, headers={"X-OAuth-Scopes": ""}
                ),
            ),
        ]

        for label, response in cases:
            with self.subTest(case=label):
                findings = probe(
                    self.TOKEN, opener=_opener(response), timeout=10.0
                )
                self.assertEqual(len(findings), 1)
                finding = findings[0]
                self.assertEqual(_field(finding, "status"), "passed")
                text = " ".join(
                    part
                    for part in (
                        _field(finding, "danger") or "",
                        _field(finding, "reason") or "",
                        _field(finding, "remedy") or "",
                        _field(finding, "source") or "",
                    )
                    if part
                ).lower()
                self.assertIn(
                    "x-oauth-scopes",
                    text,
                    "the pass must name the header it observed (or did "
                    "not), so the finding says what the response did not "
                    "carry",
                )
                self.assertIn(
                    "header",
                    text,
                    "the pass wording is about the header - 'no classic "
                    "OAuth scope header was returned'",
                )
                self.assertNotIn(
                    "fine-grained token",
                    text,
                    "the pass must not claim the token is fine-grained: "
                    "GitHub documents no X-OAuth-Scopes semantics for "
                    "fine-grained PATs",
                )
                self.assertNotIn(
                    "fine grained token",
                    text,
                    "the pass must not claim the token is fine-grained",
                )

    def test_header_lookup_is_case_insensitive(self):
        # HTTP headers are case-insensitive; the recorded fixture may
        # spell the header however the server sent it, so the probe must
        # read it the same way - lowercase included.
        probe = self._prober()
        for label, header_key in (
            ("canonical casing", "X-OAuth-Scopes"),
            ("lowercase", "x-oauth-scopes"),
        ):
            with self.subTest(casing=label):
                findings = probe(
                    self.TOKEN,
                    opener=_opener(
                        _FakeResponse(
                            self._USER_BODY,
                            200,
                            headers={header_key: "repo, workflow"},
                        )
                    ),
                    timeout=10.0,
                )

                self.assertEqual(len(findings), 1)
                finding = findings[0]
                self.assertEqual(
                    _field(finding, "status"),
                    "fail",
                    "a non-empty X-OAuth-Scopes header is a fail in "
                    "every casing",
                )
                self.assertIn(
                    "repo, workflow",
                    _field(finding, "danger") or "",
                    "the fail danger must quote the recorded scopes "
                    "verbatim in every casing",
                )

    def test_body_carrying_a_scopes_key_is_never_consulted(self):
        # The saved page settles the negative: the documented GET /user
        # body has no "scopes" key at all
        # (doc/external/github/rest-api-endpoints-for-users.md), so a
        # body that does carry one must not be read as classic - the
        # finding depends only on the header.
        probe = self._prober()
        opener = _CapturingOpener(
            _FakeResponse(b'{"login": "octocat", "scopes": ["repo"]}', 200)
        )

        findings = probe(self.TOKEN, opener=opener, timeout=10.0)

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "passed",
            "the body is never parsed for a 'scopes' field - no such "
            "field exists: a 200 without the header passes regardless "
            "of the body",
        )

    def test_recorded_401_yields_skipped_with_status_in_reason(self):
        # A 401 on GET /user is the unauthenticated answer the saved page
        # documents: not a scope answer the probe can interpret. The
        # recorded error carries no headers (hdrs=None); the probe must
        # not crash on them.
        probe = self._prober()
        url = "https://api.github.com" + self.USER_PATH

        findings = probe(
            self.TOKEN,
            opener=_opener(
                urllib.error.HTTPError(url, 401, "Unauthorized", None, None)
            ),
            timeout=10.0,
        )

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "skipped",
            "a 401 on GET /user is not a scope answer the probe can "
            "interpret: it skips",
        )
        reason = _field(finding, "reason") or _field(finding, "danger") or ""
        self.assertIn(
            "401",
            reason,
            "the skipped finding's reason must carry the status 401, so "
            "the report shows why the probe did not run",
        )
        self.assertTrue(
            _field(finding, "remedy"),
            "every finding carries a non-empty remedy",
        )

    def test_transport_failure_yields_skipped_with_nonempty_reason(self):
        probe = self._prober()
        for label, outcome in (
            ("URLError", urllib.error.URLError("Name or service not known")),
            ("socket.timeout", socket.timeout("timed out")),
            ("bare OSError", OSError("Network is unreachable")),
        ):
            with self.subTest(transport=label):
                findings = probe(
                    self.TOKEN, opener=_opener(outcome), timeout=10.0
                )

                self.assertIsInstance(findings, list)
                self.assertEqual(
                    len(findings),
                    1,
                    "a transport failure yields one skipped finding, not "
                    "an exception",
                )
                finding = findings[0]
                self.assertEqual(
                    _field(finding, "status"),
                    "skipped",
                    "a transport failure is a skipped, not a pass or a "
                    "fail: a slow GitHub must not read as a scope answer",
                )
                reason = (
                    _field(finding, "reason")
                    or _field(finding, "danger")
                    or ""
                )
                self.assertIsInstance(reason, str)
                self.assertTrue(
                    reason,
                    "the skipped finding must carry a non-empty reason "
                    "naming the transport failure",
                )
                self.assertTrue(
                    _field(finding, "remedy"),
                    "every finding carries a non-empty remedy",
                )

    def test_no_token_yields_skipped_without_attempting_a_request(self):
        # Behaviour 7, this probe's share: a token-scope probe with no
        # token establishes no fact about any token, and no probe may
        # issue an unauthenticated request and read its status as a token
        # property.
        probe = self._prober()
        opener = _CapturingOpener(_FakeResponse(self._USER_BODY, 200))

        findings = probe(None, opener=opener, timeout=10.0)

        self.assertIsNone(
            opener.captured,
            "with no token the probe must not attempt a request at all: "
            "a token-scope probe reads a token property, and an "
            "unauthenticated request establishes no fact about any token",
        )
        self.assertIsInstance(findings, list)
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "skipped",
            "no token means the probe skips - never a pass or a fail",
        )
        reason = (
            _field(finding, "reason")
            or _field(finding, "danger")
            or ""
        )
        self.assertTrue(
            reason,
            "the skipped finding must carry a non-empty reason stating "
            "that a token-scope probe with no token establishes no fact "
            "about any token",
        )
        self.assertTrue(
            _field(finding, "remedy"),
            "every finding carries a non-empty remedy",
        )

    def test_request_targets_the_user_endpoint(self):
        # The probe is GET /user: the recorded request it builds must
        # carry that path, so the probe cannot be pointed at a different
        # endpoint later without a test change.
        probe = self._prober()
        opener = _CapturingOpener(_FakeResponse(self._USER_BODY, 200))

        probe(self.TOKEN, opener=opener, timeout=10.0)

        request = opener.captured
        self.assertIsNotNone(
            request,
            "the probe must hand its opener a request to open",
        )
        url = getattr(request, "full_url", None) or getattr(request, "url", "")
        parsed = urllib.parse.urlparse(url)
        self.assertEqual(
            parsed.path,
            self.USER_PATH,
            "the probe must issue GET /user - the classic-token "
            "endpoint - not any other path",
        )

    def test_findings_carry_the_module_finding_shape_and_render(self):
        # The finding dicts must match what render_finding already
        # consumes: a passed finding (header absent) renders without a
        # danger, and a skipped finding (401) renders with its reason.
        # The fail finding (header non-empty) is asserted on its dict
        # fields only - render_finding has no fail branch yet, that is
        # behaviour 9's job, and a render assertion here would fail for
        # the wrong reason (the renderer, not the probe).
        probe = self._prober()
        url = "https://api.github.com" + self.USER_PATH
        renderable_cases = [
            (
                "passed (header absent)",
                _FakeResponse(self._USER_BODY, 200),
            ),
            (
                "skipped (401)",
                urllib.error.HTTPError(url, 401, "Unauthorized", None, None),
            ),
        ]

        for label, outcome in renderable_cases:
            with self.subTest(label=label):
                findings = probe(
                    self.TOKEN, opener=_opener(outcome), timeout=10.0
                )
                self.assertEqual(len(findings), 1)
                finding = findings[0]
                self.assertIn(
                    _field(finding, "status"),
                    ("passed", "warn", "skipped", "fail"),
                    "finding status must be one of the four known statuses",
                )
                self.assertTrue(
                    _field(finding, "check"),
                    "every finding carries a non-empty check name",
                )
                self.assertIsInstance(_field(finding, "remedy"), str)
                self.assertTrue(
                    _field(finding, "remedy"),
                    "every finding carries a non-empty remedy",
                )
                line = piguard.render_finding(finding)
                self.assertIsInstance(line, str)
                self.assertTrue(
                    line,
                    "render_finding must produce a non-empty line for the "
                    "probe's finding",
                )
                self.assertNotIn(
                    "unknown:",
                    line,
                    "the probe's finding must render through the known "
                    "branches, not fall through to 'unknown:' - a shape "
                    "mismatch would hide the probe's result",
                )
                if _field(finding, "status") == "skipped":
                    reason = (
                        _field(finding, "reason")
                        or _field(finding, "danger")
                        or ""
                    )
                    self.assertIn(
                        reason,
                        line,
                        "the rendered skipped line must carry the reason",
                    )

        # The fail finding, dict-level only: behaviour 9 covers its
        # rendering.
        with self.subTest(label="fail (header non-empty), dict-level"):
            findings = probe(
                self.TOKEN,
                opener=_opener(
                    _FakeResponse(
                        self._USER_BODY,
                        200,
                        headers={"X-OAuth-Scopes": "repo, workflow"},
                    )
                ),
                timeout=10.0,
            )
            self.assertEqual(len(findings), 1)
            finding = findings[0]
            self.assertEqual(_field(finding, "status"), "fail")
            self.assertTrue(
                _field(finding, "check"),
                "every finding carries a non-empty check name",
            )
            self.assertIsInstance(_field(finding, "danger"), str)
            self.assertTrue(
                _field(finding, "danger"),
                "the fail finding's danger must be non-empty",
            )
            self.assertIsInstance(_field(finding, "remedy"), str)
            self.assertTrue(
                _field(finding, "remedy"),
                "the fail finding's remedy must be non-empty",
            )

    def test_never_raises_across_every_recorded_mode(self):
        probe = self._prober()
        url = "https://api.github.com" + self.USER_PATH
        modes = [
            (
                "200 (header non-empty)",
                _FakeResponse(
                    self._USER_BODY,
                    200,
                    headers={"X-OAuth-Scopes": "repo, workflow"},
                ),
            ),
            (
                "200 (header empty)",
                _FakeResponse(
                    self._USER_BODY, 200, headers={"X-OAuth-Scopes": ""}
                ),
            ),
            ("200 (header absent)", _FakeResponse(self._USER_BODY, 200)),
            (
                "401",
                urllib.error.HTTPError(url, 401, "Unauthorized", None, None),
            ),
            (
                "500",
                urllib.error.HTTPError(
                    url, 500, "Internal Server Error", None, None
                ),
            ),
            (
                "URLError",
                urllib.error.URLError("Name or service not known"),
            ),
            ("socket.timeout", socket.timeout("timed out")),
            ("bare OSError", OSError("Network is unreachable")),
        ]
        for label, outcome in modes + [("no token", None)]:
            with self.subTest(mode=label):
                try:
                    if outcome is None:
                        findings = probe(
                            None,
                            opener=_CapturingOpener(
                                _FakeResponse(self._USER_BODY, 200)
                            ),
                            timeout=10.0,
                        )
                    else:
                        findings = probe(
                            self.TOKEN, opener=_opener(outcome), timeout=10.0
                        )
                except Exception as exc:
                    self.fail(
                        "probe_classic_token raised {} for the recorded "
                        "{}; every recorded mode must return a finding "
                        "list, not an exception".format(
                            type(exc).__name__, label
                        )
                    )
                self.assertIsInstance(
                    findings,
                    list,
                    "every recorded mode returns a finding list",
                )
                self.assertEqual(
                    len(findings),
                    1,
                    "the classic-token probe yields exactly one finding",
                )


if __name__ == "__main__":
    unittest.main()
