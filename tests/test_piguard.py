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
from typing import Any, Callable, Dict, List, Optional, Tuple

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
            self.assertIsInstance(
                _field(finding, "remedy"),
                str,
                "remedy must be a string on a passed finding",
            )
            # A passed rule has nothing to fix; its remedy may now be
            # empty (behaviour 2 of plans/guard-finding-compact.md) -
            # nothing prints it any more.

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
        self.assertIn(
            "Restrict deletions",
            _field(warn, "remedy") or "",
            "the deletion warn's remedy must name the GitHub UI label the "
            "missing rule turns on - 'Restrict deletions' - per "
            "doc/external/github/available-rules-for-rulesets.md",
        )
        self.assertNotIn(
            "doc/external/",
            _field(warn, "remedy") or "",
            "the warn remedy must carry no doc path (behaviour 2 of "
            "plans/guard-finding-compact.md)",
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
        self.assertIsInstance(
            _field(finding, "remedy"),
            str,
            "remedy must be a string on a passed finding",
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
                self.assertIn(
                    "Require a pull request before merging",
                    _field(warn, "remedy") or "",
                    "the review warn's remedy must name the GitHub UI "
                    "label the missing rule turns on - 'Require a pull "
                    "request before merging' - per "
                    "doc/external/github/available-rules-for-rulesets.md",
                )
                self.assertNotIn(
                    "doc/external/",
                    _field(warn, "remedy") or "",
                    "the warn remedy must carry no doc path (behaviour 2 "
                    "of plans/guard-finding-compact.md)",
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
        self.assertIsInstance(
            _field(passed[0], "remedy"),
            str,
            "remedy must be a string on a passed finding",
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
    push straight to the branch, with no gate) and a remedy naming the
    GitHub UI label the missing rule turns on - "Restrict updates" - per
    doc/external/github/available-rules-for-rulesets.md.
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
        self.assertIsInstance(
            _field(finding, "remedy"),
            str,
            "remedy must be a string on a passed finding",
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
                self.assertIn(
                    "Restrict updates",
                    _field(warn, "remedy") or "",
                    "the update warn's remedy must name the GitHub UI "
                    "label the missing rule turns on - 'Restrict updates' "
                    "- per doc/external/github/available-rules-for-"
                    "rulesets.md",
                )
                self.assertNotIn(
                    "doc/external/",
                    _field(warn, "remedy") or "",
                    "the warn remedy must carry no doc path (behaviour 2 "
                    "of plans/guard-finding-compact.md)",
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
                self.assertIsInstance(
                    _field(finding, "remedy"),
                    str,
                    "remedy must be a string on a passed finding",
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
    runs - with no gate) and a remedy naming the GitHub UI label the
    missing rule turns on - "Restrict file paths" - per
    doc/external/github/available-rules-for-rulesets.md.
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
        self.assertIsInstance(
            _field(finding, "remedy"),
            str,
            "remedy must be a string on a passed finding",
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
                self.assertIn(
                    "Restrict file paths",
                    _field(warn, "remedy") or "",
                    "the file-path warn's remedy must name the GitHub UI "
                    "label the missing rule turns on - 'Restrict file "
                    "paths' - per doc/external/github/available-rules-"
                    "for-rulesets.md",
                )
                self.assertNotIn(
                    "doc/external/",
                    _field(warn, "remedy") or "",
                    "the warn remedy must carry no doc path (behaviour 2 "
                    "of plans/guard-finding-compact.md)",
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
                self.assertIsInstance(
                    _field(finding, "remedy"),
                    str,
                    "remedy must be a string on a passed finding",
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
    """Behaviour 3 of plans/guard-finding-compact.md: render_finding is the one vocabulary.

    ``render_finding(finding)`` takes one finding dict (the shape the check
    functions return) and returns the human-readable line for it; no network
    is involved. The line is ``{prefix}: {label} - {substance}``: the
    existing ``ok:``/``warn:``/``fail:``/``skipped:`` prefix, the label
    (the rule, or the check on a token finding), and the finding's own
    short substance - its ``brief`` on a pass. Every word of the line comes
    from the finding's own fields: the hard-coded bypass caveat is not a
    finding field, so it leaves the per-finding line and returns once as
    the module's trailing note (behaviour 8 of
    plans/guard-finding-compact.md, doc/external/github/
    rest-api-endpoints-for-rules.md).

    Re-pointed in the red for behaviour 3: the old pins asserted the
    hard-coded caveat on every passed line and the ``fix:`` tail on the
    warn line; the new pins assert the compact composition.
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

    def test_passed_history_rewrite_findings_render_label_and_brief_without_caveat(self):
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
                self.assertTrue(
                    line.startswith(
                        "ok: {}".format(_field(finding, "rule"))
                    ),
                    "the passed line must keep the 'ok:' prefix and its "
                    "label: {!r}".format(line),
                )
                self.assertIn(
                    _field(finding, "brief"),
                    line,
                    "the passed line must carry the finding's own brief - "
                    "every word from the finding's fields: {!r}".format(line),
                )
                self.assertLessEqual(
                    len(line),
                    160,
                    "the rendered line must be at most 160 characters, "
                    "got {}: {!r}".format(len(line), line),
                )
                self.assertNotIn(
                    "bypass",
                    line.lower(),
                    "the bypass caveat is not a finding field, so a per-"
                    "finding line carrying it invents a word; it returns "
                    "once as the trailing note: {!r}".format(line),
                )

    def test_passed_review_finding_renders_label_brief_and_count(self):
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
                self.assertTrue(
                    line.startswith("ok: pull_request"),
                    "the passed line must keep its 'ok:' prefix and label: "
                    "{!r}".format(line),
                )
                self.assertIn(
                    _field(findings[0], "brief"),
                    line,
                    "the passed line must carry the finding's own brief - "
                    "every word from the finding's fields: {!r}".format(line),
                )
                self.assertLessEqual(
                    len(line),
                    160,
                    "the rendered line must be at most 160 characters, "
                    "got {}: {!r}".format(len(line), line),
                )
                self.assertNotIn(
                    "bypass",
                    line.lower(),
                    "the bypass caveat is not a finding field, so a per-"
                    "finding line carrying it invents a word: "
                    "{!r}".format(line),
                )
                self.assertRegex(
                    line,
                    r"\b{}\b".format(count),
                    "the recorded required-approving-review count of {} must "
                    "stay visible in the rendered line - a zero count must "
                    "not be hidden".format(count),
                )

    def test_passed_update_finding_renders_label_brief_and_value(self):
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
                    _field(findings[0], "brief"),
                    line,
                    "the passed line must carry the finding's own brief - "
                    "every word from the finding's fields: {!r}".format(line),
                )
                self.assertLessEqual(
                    len(line),
                    160,
                    "the rendered line must be at most 160 characters, "
                    "got {}: {!r}".format(len(line), line),
                )
                self.assertNotIn(
                    "bypass",
                    line.lower(),
                    "the bypass caveat is not a finding field, so a per-"
                    "finding line carrying it invents a word: "
                    "{!r}".format(line),
                )
                self.assertIn(
                    "True" if value else "False",
                    line,
                    "the recorded update_allows_fetch_and_merge value of {} "
                    "must stay visible in the rendered line - a weak value "
                    "must not be hidden".format(value),
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
                    _field(findings[0], "brief"),
                    line,
                    "the passed line must carry the finding's own brief - "
                    "every word from the finding's fields: {!r}".format(line),
                )
                self.assertLessEqual(
                    len(line),
                    160,
                    "the rendered line must be at most 160 characters, "
                    "got {}: {!r}".format(len(line), line),
                )
                self.assertNotIn(
                    "bypass",
                    line.lower(),
                    "the bypass caveat is not a finding field, so a per-"
                    "finding line carrying it invents a word: "
                    "{!r}".format(line),
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

    def test_passed_file_path_finding_renders_label_brief_and_paths(self):
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
                    _field(findings[0], "brief"),
                    line,
                    "the passed line must carry the finding's own brief - "
                    "every word from the finding's fields: {!r}".format(line),
                )
                self.assertLessEqual(
                    len(line),
                    160,
                    "the rendered line must be at most 160 characters, "
                    "got {}: {!r}".format(len(line), line),
                )
                self.assertNotIn(
                    "bypass",
                    line.lower(),
                    "the bypass caveat is not a finding field, so a per-"
                    "finding line carrying it invents a word: "
                    "{!r}".format(line),
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
            _field(findings[0], "brief"),
            line,
            "the passed line must carry the finding's own brief - every "
            "word from the finding's fields: {!r}".format(line),
        )
        self.assertLessEqual(
            len(line),
            160,
            "the rendered line must be at most 160 characters, got {}: "
            "{!r}".format(len(line), line),
        )
        self.assertNotIn(
            "bypass",
            line.lower(),
            "the bypass caveat is not a finding field, so a per-finding "
            "line carrying it invents a word: {!r}".format(line),
        )
        self.assertIn(
            "no paths recorded",
            line,
            "an empty restriction list must render the explicit phrase "
            "'no paths recorded' (case-sensitive) - a weak value is "
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
                    _field(findings[0], "brief"),
                    line,
                    "the passed line must carry the finding's own brief - "
                    "every word from the finding's fields: {!r}".format(line),
                )
                self.assertLessEqual(
                    len(line),
                    160,
                    "the rendered line must be at most 160 characters, "
                    "got {}: {!r}".format(len(line), line),
                )
                self.assertNotIn(
                    "bypass",
                    line.lower(),
                    "the bypass caveat is not a finding field, so a per-"
                    "finding line carrying it invents a word: "
                    "{!r}".format(line),
                )
                self.assertIn(
                    "no paths recorded",
                    line,
                    "no paths were returned, so the line must read 'no "
                    "paths recorded' - it must not claim a path that was "
                    "not returned",
                )

    def test_warn_finding_lines_render_label_and_brief_without_inline_fix(self):
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
                self.assertTrue(
                    line.startswith(
                        "warn: {}".format(_field(warn, "rule"))
                    ),
                    "the rendered warn line must keep its 'warn:' prefix "
                    "and its label: {!r}".format(line),
                )
                self.assertIn(
                    _field(warn, "brief"),
                    line,
                    "the rendered warn line must carry the finding's own "
                    "brief - every word from the finding's fields: "
                    "{!r}".format(line),
                )
                self.assertLessEqual(
                    len(line),
                    160,
                    "the rendered line must be at most 160 characters, "
                    "got {}: {!r}".format(len(line), line),
                )
                self.assertNotIn(
                    "fix:",
                    line,
                    "the remedy no longer rides inline on the per-finding "
                    "line - the fixes move to the report's 'To fix' "
                    "section (behaviour 7 of plans/guard-finding-compact."
                    "md): {!r}".format(line),
                )


class RenderFindingCompositionTests(unittest.TestCase):
    """Behaviour 3 of plans/guard-finding-compact.md: the one vocabulary.

    For each of the twenty emittable findings - five branch rules at
    passed and warn, the four ``skipped_findings`` checks and the five
    token checks at their statuses - ``render_finding(finding)`` returns
    a line that is ``{prefix}: {label} - {substance}``:

    - the existing prefix convention: ``ok:`` for passed, ``warn:``,
      ``fail:`` and ``skipped:``;
    - the label: the finding's ``rule`` when it carries one, else its
      ``check``;
    - the substance: the finding's own short ``brief`` - the approved
      sample report's clause after the em dash. Every word of the line
      comes from the finding's own fields, so the hard-coded bypass
      caveat (which is not a finding field) must not appear: it returns
      once as the module's trailing note (behaviour 8,
      doc/external/github/rest-api-endpoints-for-rules.md).

    The line is at most 160 characters. A finding with an unknown status
    still returns the ``unknown:`` fallthrough unchanged;
    ``render_report`` is unchanged and still delegates (pinned in
    ``RenderReportTests``).

    The producer matrix is cycle 1's ``FindingBriefTests`` sweep, driven
    as in production over recorded openers - no live network. The sweep
    covers the twenty findings and their parameter variants; the same
    four assertions hold for every one of them.
    """

    _PREFIXES = {
        "passed": "ok",
        "warn": "warn",
        "fail": "fail",
        "skipped": "skipped",
    }

    def _every_finding(self) -> List[Tuple[str, Dict[str, Any]]]:
        """Cycle 1's producer matrix: every finding the producers can emit."""
        matrix = FindingBriefTests(
            "test_every_emittable_finding_carries_a_brief"
        )
        findings = matrix._every_brief_finding()
        self.assertGreaterEqual(
            len(findings),
            20,
            "fixture sanity: the sweep must cover the twenty emittable "
            "findings, got {}".format(len(findings)),
        )
        return findings

    def test_twenty_findings_render_prefix_label_brief_in_at_most_160_chars(self):
        for label, finding in self._every_finding():
            with self.subTest(finding=label):
                status = _field(finding, "status")
                self.assertIn(
                    status,
                    self._PREFIXES,
                    "fixture sanity: a producer emitted an unknown status "
                    "{!r}".format(status),
                )
                prefix = self._PREFIXES[status]
                rule = _field(finding, "rule")
                label_ = rule if rule is not None else _field(finding, "check")

                line = piguard.render_finding(finding)

                self.assertIsInstance(line, str)
                self.assertTrue(
                    line,
                    "render_finding must produce a non-empty line",
                )
                self.assertTrue(
                    line.startswith("{}: {}".format(prefix, label_)),
                    "the line must keep its {!r} prefix and its label "
                    "{!r}: {!r}".format(prefix, label_, line),
                )
                self.assertLessEqual(
                    len(line),
                    160,
                    "the line must be at most 160 characters, got {}: "
                    "{!r}".format(len(line), line),
                )
                self.assertIn(
                    _field(finding, "brief"),
                    line,
                    "the line must carry the finding's own brief - every "
                    "word from the finding's fields: {!r}".format(line),
                )

    def test_no_finding_line_carries_the_bypass_caveat(self):
        # The bypass caveat is not a finding field; a per-finding line
        # carrying it would be inventing a word. It returns once as the
        # module's trailing note (behaviour 8 of
        # plans/guard-finding-compact.md), never on a finding's line.
        for label, finding in self._every_finding():
            with self.subTest(finding=label):
                line = piguard.render_finding(finding)
                self.assertNotIn(
                    "bypass",
                    line.lower(),
                    "the line must not carry the bypass caveat - it is "
                    "not a finding field: {!r}".format(line),
                )
                self.assertNotIn(
                    "bypass_actors",
                    line,
                    "the line must not name bypass_actors - it is not a "
                    "finding field: {!r}".format(line),
                )

    def test_unknown_status_finding_renders_unknown_prefix_without_crashing(self):
        # A status that is not passed, warn, skipped or fail still falls
        # through to the ``unknown:`` line, unchanged (behaviour 3's
        # error clause): the report must mark it, not crash on it.
        finding = {
            "status": "mystery",
            "check": "history_rewrite",
            "rule": "deletion",
            "danger": "",
            "source": None,
            "remedy": "",
        }

        line = piguard.render_finding(finding)

        self.assertIsInstance(line, str)
        self.assertTrue(
            line.startswith("unknown:"),
            "the fallthrough for truly-unknown statuses must be "
            "preserved: {!r}".format(line),
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
                self.assertIsInstance(
                    carried,
                    str,
                    "each skipped finding carries a reason string",
                )
                self.assertTrue(
                    carried,
                    "each skipped finding carries a non-empty reason",
                )
                # Behaviour 2 of plans/guard-finding-compact.md: the
                # reason the fetch failed is shortened at the source -
                # a single sentence of at most 100 characters, no doc
                # path, no "see:" clause - not the raw fetch error.
                self.assertLessEqual(
                    len(carried),
                    100,
                    "the skipped reason must be at most 100 characters, "
                    "got {}: {!r}".format(len(carried), carried),
                )
                self.assertNotIn(
                    ". ",
                    carried,
                    "the skipped reason must be a single sentence: "
                    "{!r}".format(carried),
                )
                self.assertNotIn(
                    "doc/external/",
                    carried,
                    "the skipped reason must carry no doc path: "
                    "{!r}".format(carried),
                )
                self.assertNotIn(
                    "see:",
                    carried,
                    "the skipped reason must carry no 'see:' clause: "
                    "{!r}".format(carried),
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
                self.assertTrue(
                    line.startswith(
                        "skipped: {}".format(_field(finding, "check"))
                    ),
                    "the rendered skipped line must keep its 'skipped: "
                    "{check}' prefix and its label: {line!r}".format(
                        check=_field(finding, "check"), line=line
                    ),
                )
                self.assertIn(
                    _field(finding, "brief"),
                    line,
                    "the rendered skipped line must carry the finding's "
                    "own brief - every word from the finding's fields: "
                    "{!r}".format(line),
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
                if status != "passed":
                    # The module invariant (behaviour 5, kept by behaviour
                    # 2 of plans/guard-finding-compact.md): every
                    # warn/fail/skipped finding still names what to do.
                    self.assertTrue(
                        remedy,
                        "a non-passing finding ({}) with an empty remedy "
                        "is a programming error: it cannot name the "
                        "concrete fix".format(status),
                    )
                # A passed finding's remedy may be empty now that nothing
                # prints it (behaviour 2 of plans/guard-finding-
                # compact.md).
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

    def test_non_passing_findings_remedy_is_short_and_carries_no_doc_path(self):
        checked = 0
        for label, finding in self._every_finding():
            status = _field(finding, "status")
            if status not in ("warn", "skipped"):
                continue
            checked += 1
            with self.subTest(finding=label):
                remedy = _field(finding, "remedy") or ""
                self.assertLessEqual(
                    len(remedy),
                    100,
                    "the {} finding on rule {!r} remedy must be a single "
                    "sentence of at most 100 characters, got {}: "
                    "{!r}".format(status, _field(finding, "rule"), len(remedy), remedy),
                )
                self.assertNotIn(
                    ". ",
                    remedy,
                    "the {} finding on rule {!r} remedy must be a single "
                    "sentence: {!r}".format(status, _field(finding, "rule"), remedy),
                )
                self.assertNotIn(
                    "doc/external/",
                    remedy,
                    "the {} finding on rule {!r} must carry no doc path in "
                    "its remedy (behaviour 2 of "
                    "plans/guard-finding-compact.md): {!r}".format(
                        status, _field(finding, "rule"), remedy
                    ),
                )
                self.assertNotIn(
                    "see:",
                    remedy,
                    "the {} finding on rule {!r} must carry no 'see:' "
                    "clause in its remedy (behaviour 2 of "
                    "plans/guard-finding-compact.md): {!r}".format(
                        status, _field(finding, "rule"), remedy
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


class GateVerdictTests(unittest.TestCase):
    """Behaviour 1 of plans/setup-repo-guards.md - ``gate_verdict(findings)``.

    The gate seam ``setup-repo`` runs before any provisioning:
    ``"clean"`` iff no finding is ``fail`` and none is ``warn``;
    ``"blocked"`` otherwise. ``skipped`` never blocks - it is an honest
    "could not verify" (issue #100, decision 2) - and an unknown status is
    neither a fail nor a warn. This is a SIBLING of ``summarize``, not a
    change to it: ``verify-guards`` keeps "1 iff any fail" with a ``warn``
    still exiting 0, while the gate needs a fail OR a warn to block. Pure:
    one positional findings list, a ``str`` result, no network, no write,
    never raises.
    """

    def _verdict(self) -> Any:
        gate = getattr(piguard, "gate_verdict", None)
        self.assertTrue(
            callable(gate),
            "anvilkit.pi.piguard.gate_verdict is not callable; the gate "
            "verdict seam has not been implemented yet",
        )
        return gate

    def _finding(self, status: str, check: str) -> Dict[str, Any]:
        """One finding in the module's own shape, carrying ``status``/``check``."""
        return {
            "status": status,
            "check": check,
            "rule": None,
            "danger": "the guard is unmet",
            "source": None,
            "remedy": "see "
            + "doc/external/github/available-rules-for-rulesets.md",
        }

    def test_clean_when_all_passed_and_skipped(self):
        verdict = self._verdict()
        findings = (
            piguard.check_history_rewrite(
                [
                    rule("non_fast_forward", "main-guard"),
                    rule("deletion", "main-guard"),
                ]
            )
            + piguard.skipped_findings("GitHub was unreachable")
        )
        self.assertEqual(
            [f for f in findings if _field(f, "status") in ("fail", "warn")],
            [],
            "fixture sanity: only passed and skipped findings",
        )

        self.assertEqual(
            verdict(findings),
            "clean",
            "passed and skipped alone must be clean - skipped is an honest "
            "'could not verify' and never blocks",
        )

    def test_clean_when_empty(self):
        verdict = self._verdict()

        self.assertEqual(
            verdict([]),
            "clean",
            "no findings at all means nothing failed and nothing warned",
        )

    def test_blocked_on_a_single_warn(self):
        verdict = self._verdict()
        findings = (
            piguard.check_history_rewrite(
                [rule("non_fast_forward", "main-guard")]
            )
            + piguard.skipped_findings("GitHub was unreachable")
        )
        self.assertEqual(
            [f for f in findings if _field(f, "status") == "warn"],
            [findings[1]],
            "fixture sanity: exactly one warn among the passed and skipped",
        )
        self.assertEqual(
            [f for f in findings if _field(f, "status") == "fail"],
            [],
            "fixture sanity: no fail finding - this is the case summarize "
            "reports as 0, the key difference this gate must close",
        )

        self.assertEqual(
            verdict(findings),
            "blocked",
            "a single warn among passed and skipped must block the gate: "
            "unlike summarize, a warn is a reportable problem here, not an "
            "exit-0",
        )

    def test_blocked_on_a_single_fail(self):
        verdict = self._verdict()
        fail_finding = self._finding("fail", "administration")
        findings = (
            piguard.check_history_rewrite(
                [
                    rule("non_fast_forward", "main-guard"),
                    rule("deletion", "main-guard"),
                ]
            )
            + piguard.skipped_findings("GitHub was unreachable")
            + [fail_finding]
        )
        self.assertEqual(
            [f for f in findings if _field(f, "status") == "fail"],
            [fail_finding],
            "fixture sanity: exactly one fail among the passed and skipped",
        )

        self.assertEqual(
            verdict(findings),
            "blocked",
            "a single fail among passed and skipped must block the gate",
        )

    def test_blocked_when_both_warn_and_fail_present(self):
        verdict = self._verdict()
        fail_finding = self._finding("fail", "administration")
        findings = (
            piguard.check_history_rewrite(
                [rule("non_fast_forward", "main-guard")]
            )
            + [fail_finding]
        )
        self.assertEqual(
            [f for f in findings if _field(f, "status") == "warn"],
            [findings[1]],
            "fixture sanity: exactly one warn is present",
        )
        self.assertEqual(
            [f for f in findings if _field(f, "status") == "fail"],
            [fail_finding],
            "fixture sanity: exactly one fail is present",
        )

        self.assertEqual(
            verdict(findings),
            "blocked",
            "a warn and a fail together must block the gate",
        )

    def test_skipped_never_blocks(self):
        verdict = self._verdict()
        findings = piguard.skipped_findings("no origin remote: could not verify")
        self.assertEqual(
            [_field(f, "status") for f in findings],
            ["skipped"] * len(findings),
            "fixture sanity: the list is skipped-only - the no-origin / "
            "could-not-verify case",
        )

        self.assertEqual(
            verdict(findings),
            "clean",
            "skipped-only findings must be clean: a check that could not "
            "verify is honest, not a block (issue #100, decision 2)",
        )

    def test_unknown_status_is_neither_fail_nor_warn(self):
        verdict = self._verdict()
        unknown = self._finding("weird", "history_rewrite")
        findings = (
            piguard.check_history_rewrite(
                [
                    rule("non_fast_forward", "main-guard"),
                    rule("deletion", "main-guard"),
                ]
            )
            + piguard.skipped_findings("GitHub was unreachable")
            + [unknown]
        )
        self.assertEqual(
            [f for f in findings if _field(f, "status") == "weird"],
            [unknown],
            "fixture sanity: a finding with a status outside the four "
            "documented ones is present",
        )
        self.assertEqual(
            [f for f in findings if _field(f, "status") in ("fail", "warn")],
            [],
            "fixture sanity: the unknown status is neither a fail nor a "
            "warn",
        )

        self.assertEqual(
            verdict(findings),
            "clean",
            "an unknown status must be neither a fail nor a warn - the "
            "gate must not crash on it and must not block on it",
        )

    def test_pure_and_never_raises(self):
        verdict = self._verdict()
        # _verdict already pinned callability. One positional findings list
        # is the whole call shape: no token, no repo, no network, no write.
        for label, findings in (
            (
                "clean side",
                piguard.check_history_rewrite(
                    [
                        rule("non_fast_forward", "main-guard"),
                        rule("deletion", "main-guard"),
                    ]
                )
                + piguard.skipped_findings("GitHub was unreachable"),
            ),
            (
                "blocked side",
                piguard.check_history_rewrite(
                    [rule("non_fast_forward", "main-guard")]
                )
                + [self._finding("fail", "administration")],
            ),
        ):
            with self.subTest(side=label):
                result = verdict(findings)
                self.assertIsInstance(
                    result,
                    str,
                    "gate_verdict returns the verdict as a str, not an int "
                    "or a bool",
                )
                self.assertIn(
                    result,
                    {"clean", "blocked"},
                    "the verdict is exactly 'clean' or 'blocked'",
                )


class GateRemediationTests(unittest.TestCase):
    """Behaviour 2 of plans/setup-repo-guards.md - ``gate_remediation``.

    The remediation seam ``setup-repo`` runs once the gate is blocked: given
    the branch findings and the token findings as two separate lists it
    answers which of the two prepared fixes a junior must apply.
    ``needs_ruleset`` is true iff any BRANCH finding is ``fail`` or ``warn``;
    ``needs_token_recipe`` is true iff any TOKEN finding is ``fail``. The
    recipe is the fix for a bad token, and a token ``warn`` (a reachable
    named repo) is a scope judgement with its own remedy text: it blocks the
    gate via :func:`gate_verdict`, but it prints no recipe. Pure: two
    positional findings lists, a ``Dict[str, bool]`` with exactly the keys
    ``"needs_ruleset"`` and ``"needs_token_recipe"``, no network, no write,
    never raises.
    """

    def _remediation(self) -> Any:
        remediation = getattr(piguard, "gate_remediation", None)
        self.assertTrue(
            callable(remediation),
            "anvilkit.pi.piguard.gate_remediation is not callable; the gate "
            "remediation seam has not been implemented yet",
        )
        return remediation

    def _finding(self, status: str, check: str) -> Dict[str, Any]:
        """One finding in the module's own shape, carrying ``status``/``check``."""
        return {
            "status": status,
            "check": check,
            "rule": None,
            "danger": "the guard is unmet",
            "source": None,
            "remedy": "see "
            + "doc/external/github/available-rules-for-rulesets.md",
        }

    def _branch_warn(self) -> List[Dict[str, Any]]:
        """A branch list mixing ``passed``, ``warn`` and ``skipped``.

        ``check_history_rewrite`` over a single active rule yields one
        ``passed`` (the rule present) and one ``warn`` (the other rule
        absent); ``skipped_findings`` supplies the ``skipped`` side.
        """
        findings = (
            piguard.check_history_rewrite([rule("non_fast_forward", "main-guard")])
            + piguard.skipped_findings("GitHub was unreachable")
        )
        self.assertIn(
            "warn",
            [_field(f, "status") for f in findings],
            "fixture sanity: the branch list carries a warn finding",
        )
        self.assertEqual(
            [f for f in findings if _field(f, "status") == "fail"],
            [],
            "fixture sanity: the branch list carries no fail finding",
        )
        return findings

    def _token_fail_finding(self) -> Dict[str, Any]:
        """The real ``administration`` 200 ``fail`` the probe emits."""
        finding = piguard.probe_administration(
            "owner",
            "repo",
            token="token-xyz",
            opener=_opener(_FakeResponse(b"{}", 200)),
        )[0]
        self.assertEqual(
            _field(finding, "status"),
            "fail",
            "fixture sanity: a 200 on the administration endpoint is a fail",
        )
        self.assertEqual(
            _field(finding, "check"),
            "administration",
            "fixture sanity: the fail finding names the administration probe",
        )
        return finding

    def _token_warn_finding(self) -> Dict[str, Any]:
        """The real ``named_repo`` 200 ``warn`` the probe emits.

        A reachable named repo is a scope judgement with its own remedy
        text: it blocks the gate but is NOT a bad token, so it must never
        set ``needs_token_recipe``.
        """
        finding = piguard.probe_named_repo(
            "owner/other",
            token="token-xyz",
            opener=_opener(_FakeResponse(b'{"full_name": "owner/other"}', 200)),
        )[0]
        self.assertEqual(
            _field(finding, "status"),
            "warn",
            "fixture sanity: a 200 on the named repo is a warn, not a fail",
        )
        self.assertEqual(
            _field(finding, "check"),
            "named_repo",
            "fixture sanity: the warn finding names the named_repo probe",
        )
        return finding

    def test_empty_lists_need_nothing(self):
        remediation = self._remediation()
        empty: List[Dict[str, Any]] = []

        result = remediation(empty, empty)

        self.assertEqual(
            result,
            {"needs_ruleset": False, "needs_token_recipe": False},
            "no findings at all means no ruleset and no token recipe",
        )

    def test_branch_warn_needs_ruleset(self):
        remediation = self._remediation()
        branch = self._branch_warn()

        result = remediation(branch, [])

        self.assertEqual(
            result,
            {"needs_ruleset": True, "needs_token_recipe": False},
            "a single branch warn (no fail) needs the ruleset, and an "
            "empty token list needs no recipe",
        )

    def test_branch_fail_needs_ruleset(self):
        remediation = self._remediation()
        fail_finding = self._finding("fail", "history_rewrite")
        branch = (
            piguard.check_history_rewrite(
                [
                    rule("non_fast_forward", "main-guard"),
                    rule("deletion", "main-guard"),
                ]
            )
            + [fail_finding]
        )
        self.assertEqual(
            [f for f in branch if _field(f, "status") == "fail"],
            [fail_finding],
            "fixture sanity: exactly one fail among the passed branch "
            "findings",
        )

        result = remediation(branch, [])

        self.assertEqual(
            result,
            {"needs_ruleset": True, "needs_token_recipe": False},
            "a single branch fail needs the ruleset, and an empty token "
            "list needs no recipe",
        )

    def test_branch_clean_needs_no_ruleset(self):
        remediation = self._remediation()
        branch = (
            piguard.check_history_rewrite(
                [
                    rule("non_fast_forward", "main-guard"),
                    rule("deletion", "main-guard"),
                ]
            )
            + piguard.skipped_findings("GitHub was unreachable")
        )
        self.assertEqual(
            [f for f in branch if _field(f, "status") in ("fail", "warn")],
            [],
            "fixture sanity: only passed and skipped branch findings",
        )

        result = remediation(branch, [])

        self.assertEqual(
            result,
            {"needs_ruleset": False, "needs_token_recipe": False},
            "passed and skipped branch findings alone need no ruleset - "
            "skipped is an honest 'could not verify' and never triggers "
            "a fix",
        )

    def test_token_fail_needs_recipe(self):
        remediation = self._remediation()
        fail_finding = self._token_fail_finding()
        branch = [self._finding("passed", "history_rewrite")]
        self.assertEqual(
            [f for f in branch if _field(f, "status") in ("fail", "warn")],
            [],
            "fixture sanity: the branch side is a clean passed finding",
        )

        result = remediation(branch, [fail_finding])

        self.assertEqual(
            result,
            {"needs_ruleset": False, "needs_token_recipe": True},
            "a single token fail needs the recipe - the recipe is the fix "
            "for a bad token - and a clean branch list needs no ruleset",
        )

    def test_token_warn_blocks_but_needs_no_recipe(self):
        remediation = self._remediation()
        warn_finding = self._token_warn_finding()
        branch = [self._finding("passed", "history_rewrite")]
        self.assertEqual(
            [f for f in branch if _field(f, "status") in ("fail", "warn")],
            [],
            "fixture sanity: the branch side is clean",
        )
        self.assertEqual(
            [f for f in [warn_finding] if _field(f, "status") == "fail"],
            [],
            "fixture sanity: the token warn is NOT a fail - the key "
            "subtlety of the behaviour",
        )

        result = remediation(branch, [warn_finding])

        self.assertFalse(
            result["needs_token_recipe"],
            "a token warn (a reachable named repo) is a scope judgement "
            "with its own remedy text: it blocks the gate via gate_verdict "
            "but the recipe is only for a bad token, so it must not set "
            "needs_token_recipe",
        )
        self.assertFalse(
            result["needs_ruleset"],
            "a clean branch list must not need the ruleset just because "
            "a token warn is present - the two booleans are computed "
            "from the right list",
        )

    def test_token_skipped_needs_no_recipe(self):
        remediation = self._remediation()
        skipped = piguard.workflows_withheld_finding()
        self.assertEqual(
            [_field(f, "status") for f in skipped],
            ["skipped"] * len(skipped),
            "fixture sanity: the workflows-withheld finding is the "
            "constant skipped token finding",
        )

        result = remediation([], skipped)

        self.assertEqual(
            result,
            {"needs_ruleset": False, "needs_token_recipe": False},
            "a skipped token finding triggers neither fix - a check that "
            "could not verify is honest, not a bad token",
        )

    def test_the_lists_are_independent(self):
        remediation = self._remediation()
        branch_fail = self._finding("fail", "history_rewrite")
        branch_warn = self._finding("warn", "history_rewrite")
        token_fail = self._token_fail_finding()

        # A branch fail and a token fail together: BOTH flags true, each
        # computed from its own list.
        both = remediation([branch_fail], [token_fail])
        self.assertEqual(
            both,
            {"needs_ruleset": True, "needs_token_recipe": True},
            "a branch fail and a token fail together set both flags - the "
            "two booleans are computed independently from the right list",
        )

        # A branch warn and a token fail: both true, for the same reason.
        warn_fail = remediation([branch_warn], [token_fail])
        self.assertEqual(
            warn_fail,
            {"needs_ruleset": True, "needs_token_recipe": True},
            "a branch warn and a token fail together set both flags",
        )

        # Cross-check: a token fail must NOT set needs_ruleset.
        token_only = remediation([], [token_fail])
        self.assertFalse(
            token_only["needs_ruleset"],
            "a token fail must not set needs_ruleset - the ruleset is the "
            "fix for a branch finding, not a token finding",
        )

        # Cross-check: a branch fail must NOT set needs_token_recipe.
        branch_only = remediation([branch_fail], [])
        self.assertFalse(
            branch_only["needs_token_recipe"],
            "a branch fail must not set needs_token_recipe - the recipe is "
            "the fix for a token finding, not a branch finding",
        )

    def test_pure_and_never_raises(self):
        remediation = self._remediation()
        # _remediation already pinned callability. Two positional findings
        # lists are the whole call shape: no token, no repo, no network,
        # no write.
        for label, branch, token in (
            (
                "clean side",
                piguard.check_history_rewrite(
                    [
                        rule("non_fast_forward", "main-guard"),
                        rule("deletion", "main-guard"),
                    ]
                ),
                [],
            ),
            (
                "blocked side",
                piguard.check_history_rewrite([rule("non_fast_forward", "main-guard")]),
                [self._token_fail_finding()],
            ),
        ):
            with self.subTest(side=label):
                # Snapshot the inputs so the purity check can prove the
                # function did not mutate them.
                branch_before = [dict(f) for f in branch]
                token_before = [dict(f) for f in token]

                result = remediation(branch, token)

                self.assertIsInstance(
                    result,
                    dict,
                    "gate_remediation returns a dict, not a tuple, list or "
                    "bool",
                )
                self.assertEqual(
                    set(result),
                    {"needs_ruleset", "needs_token_recipe"},
                    "the result carries exactly the two pinned keys, no "
                    "more and no fewer: got {!r}".format(sorted(result)),
                )
                for key in ("needs_ruleset", "needs_token_recipe"):
                    self.assertIsInstance(
                        result[key],
                        bool,
                        "the value for {!r} is a bool, not an int or a "
                        "string".format(key),
                    )
                self.assertEqual(
                    [dict(f) for f in branch],
                    branch_before,
                    "gate_remediation must not mutate its branch findings",
                )
                self.assertEqual(
                    [dict(f) for f in token],
                    token_before,
                    "gate_remediation must not mutate its token findings",
                )
                # Idempotent: a second call returns the same mapping.
                self.assertEqual(
                    remediation(branch, token),
                    result,
                    "gate_remediation is pure: the same inputs yield the "
                    "same mapping on every call",
                )


class GateInvariantSweep(unittest.TestCase):
    """Behaviour 14 of plans/setup-repo-guards.md - the gate invariants,
    one sweep over EVERY status the probes can emit.

    Not a repeat of the per-status tests in :class:`GateVerdictTests` and
    :class:`GateRemediationTests` (which pin the cells one by one, mixed
    with real probe fixtures); this is the MATRIX in one place: every
    single-status set, alone, for both functions, plus the mixed clean
    case and the unknown-status behaviour. Its value is completeness:
    :attr:`STATUSES` names every status a probe can emit, so a future
    probe that invents a new status must be deliberately classified here
    - it cannot silently un-pin the gate. The "clean gate writes no file
    and prints no recipe" half of behaviour 14 is pinned by
    ``test_clean_gate_provisions_as_today`` in tests/test_cli.py, which
    this sweep reuses rather than duplicates.
    """

    # The exact status vocabulary of anvilkit/pi/piguard.py, derived from
    # every "status": literal the probes emit: the branch checks
    # (check_history_rewrite / check_review / check_update_restriction /
    # check_file_paths) emit passed / warn / skipped via skipped_findings,
    # and the token probes (probe_target_access / probe_administration /
    # probe_classic_token / workflows_withheld_finding / probe_named_repo)
    # add fail. There is no "ok" status: "ok" appears in the module only
    # as a render prefix for a passed block (_BLOCK_PREFIXES), so the
    # plan's "passed" resolves to the real spelling "passed".
    STATUSES = ("passed", "warn", "fail", "skipped")

    # The check name carried by a finding of each status, in the shape the
    # probes really emit it. fail never comes from a branch check - only
    # from the token probes (administration 200, classic_token scopes) -
    # but the gate must still block on a lone fail finding wherever it sits
    # in the concatenated list, which is what the branch-side sweep pins.
    _BRANCH_CHECK_BY_STATUS = {
        "passed": "history_rewrite",   # rule present
        "warn": "history_rewrite",      # rule absent
        "fail": "administration",       # token probe's fail; verdict blocks anyway
        "skipped": "history_rewrite",   # skipped_findings over a branch check
    }
    _TOKEN_CHECK_BY_STATUS = {
        "passed": "administration",     # probe_administration 403
        "warn": "named_repo",           # probe_named_repo 200
        "fail": "administration",       # probe_administration 200
        "skipped": "workflows_withheld",  # the constant skipped finding
    }

    # The pinned matrix, one column per status in STATUSES.
    _VERDICT_BY_STATUS = {
        "passed": "clean",
        "warn": "blocked",
        "fail": "blocked",
        "skipped": "clean",
    }
    # (needs_ruleset, needs_token_recipe) for a LONE branch finding.
    _REMED_BRANCH_BY_STATUS = {
        "passed": (False, False),
        "warn": (True, False),   # warn asymmetry: the ruleset IS the fix
        "fail": (True, False),
        "skipped": (False, False),
    }
    # (needs_ruleset, needs_token_recipe) for a LONE token finding.
    _REMED_TOKEN_BY_STATUS = {
        "passed": (False, False),
        "warn": (False, False),   # warn asymmetry: a scope judgement, no recipe
        "fail": (False, True),    # only a bad token gets the recipe
        "skipped": (False, False),
    }

    def _finding(self, status: str, check: str) -> Dict[str, Any]:
        """One finding in the module's own shape, carrying ``status``/``check``."""
        return {
            "status": status,
            "check": check,
            "rule": None,
            "danger": "the guard is unmet",
            "source": None,
            "remedy": "see "
            + "doc/external/github/available-rules-for-rulesets.md",
        }

    def test_status_set_is_exactly_the_probe_vocabulary(self):
        """STATUSES is not vacuous: every entry is emitted by a real probe,
        and the probes exercised cover exactly that set."""
        produced = {
            _field(f, "status")
            for f in (
                piguard.check_history_rewrite(
                    [
                        rule("non_fast_forward", "main-guard"),
                        rule("deletion", "main-guard"),
                    ]
                )
                + piguard.check_history_rewrite(
                    [rule("non_fast_forward", "main-guard")]
                )
                + piguard.skipped_findings("no origin remote")
                + piguard.probe_administration(
                    "owner",
                    "repo",
                    token="token-xyz",
                    opener=_opener(_FakeResponse(b"{}", 200)),
                )
                + piguard.probe_administration(
                    "owner",
                    "repo",
                    token="token-xyz",
                    opener=_opener(_FakeResponse(b"{}", 403)),
                )
                + piguard.probe_named_repo(
                    "owner/other",
                    token="token-xyz",
                    opener=_opener(_FakeResponse(b'{"full_name": "owner/other"}', 200)),
                )
                + piguard.workflows_withheld_finding()
            )
        }

        self.assertEqual(
            produced,
            set(self.STATUSES),
            "the sweep's status list must match the statuses the probes "
            "actually emit - a new status here means a new row in the "
            "matrix, not a silently un-pinned gate",
        )

    def test_verdict_for_each_status_alone_in_the_branch_list(self):
        verdict = getattr(piguard, "gate_verdict", None)
        self.assertTrue(callable(verdict), "gate_verdict seam missing")
        self.assertEqual(
            set(self._VERDICT_BY_STATUS),
            set(self.STATUSES),
            "the verdict matrix must name every status in STATUSES",
        )

        for status in self.STATUSES:
            with self.subTest(status=status):
                finding = self._finding(
                    status, self._BRANCH_CHECK_BY_STATUS[status]
                )
                self.assertEqual(
                    verdict([finding]),
                    self._VERDICT_BY_STATUS[status],
                    "a lone {} finding in the branch list must yield "
                    "{}".format(status, self._VERDICT_BY_STATUS[status]),
                )

    def test_verdict_for_each_status_alone_in_the_token_list(self):
        """gate_verdict sees one concatenated list, so a lone token finding
        of each status must yield the same verdict as its branch
        counterpart: the warn asymmetry is about remediation, not the
        verdict - a lone token warn still BLOCKS."""
        verdict = getattr(piguard, "gate_verdict", None)
        self.assertTrue(callable(verdict), "gate_verdict seam missing")

        for status in self.STATUSES:
            with self.subTest(status=status):
                finding = self._finding(
                    status, self._TOKEN_CHECK_BY_STATUS[status]
                )
                self.assertEqual(
                    verdict([finding]),
                    self._VERDICT_BY_STATUS[status],
                    "a lone {} token finding must yield the same verdict "
                    "as a branch finding: {}".format(
                        status, self._VERDICT_BY_STATUS[status]
                    ),
                )

    def test_remediation_for_each_branch_status_alone(self):
        remediation = getattr(piguard, "gate_remediation", None)
        self.assertTrue(callable(remediation), "gate_remediation seam missing")
        self.assertEqual(
            set(self._REMED_BRANCH_BY_STATUS),
            set(self.STATUSES),
            "the branch remediation matrix must name every status in STATUSES",
        )

        for status in self.STATUSES:
            with self.subTest(status=status):
                finding = self._finding(
                    status, self._BRANCH_CHECK_BY_STATUS[status]
                )
                needs_ruleset, needs_recipe = self._REMED_BRANCH_BY_STATUS[status]
                self.assertEqual(
                    remediation([finding], []),
                    {"needs_ruleset": needs_ruleset, "needs_token_recipe": needs_recipe},
                    "a lone branch {} finding must set exactly "
                    "needs_ruleset={} and needs_token_recipe={}".format(
                        status, needs_ruleset, needs_recipe
                    ),
                )

    def test_remediation_for_each_token_status_alone(self):
        remediation = getattr(piguard, "gate_remediation", None)
        self.assertTrue(callable(remediation), "gate_remediation seam missing")
        self.assertEqual(
            set(self._REMED_TOKEN_BY_STATUS),
            set(self.STATUSES),
            "the token remediation matrix must name every status in STATUSES",
        )

        for status in self.STATUSES:
            with self.subTest(status=status):
                finding = self._finding(
                    status, self._TOKEN_CHECK_BY_STATUS[status]
                )
                needs_ruleset, needs_recipe = self._REMED_TOKEN_BY_STATUS[status]
                self.assertEqual(
                    remediation([], [finding]),
                    {"needs_ruleset": needs_ruleset, "needs_token_recipe": needs_recipe},
                    "a lone token {} finding must set exactly "
                    "needs_ruleset={} and needs_token_recipe={}".format(
                        status, needs_ruleset, needs_recipe
                    ),
                )

    def test_mixed_passed_and_skipped_in_both_lists_is_clean(self):
        """The caller concatenates the two lists for the verdict; a
        passed+skipped set on both sides must be clean and need no fix."""
        verdict = piguard.gate_verdict
        remediation = piguard.gate_remediation

        branch = [
            self._finding("passed", "history_rewrite"),
            self._finding("skipped", "history_rewrite"),
        ]
        token = [
            self._finding("passed", "administration"),
            self._finding("skipped", "workflows_withheld"),
        ]

        self.assertEqual(
            verdict(branch + token),
            "clean",
            "passed and skipped in both lists, concatenated as the caller "
            "does, must be clean",
        )
        self.assertEqual(
            remediation(branch, token),
            {"needs_ruleset": False, "needs_token_recipe": False},
            "passed and skipped trigger neither prepared fix",
        )

    def test_unknown_status_pins_nothing(self):
        """A status string the probes never emit must be deliberately
        classified, not silently absorbed: today it neither blocks nor
        triggers a fix, and this sweep keeps that pin explicit."""
        verdict = piguard.gate_verdict
        remediation = piguard.gate_remediation

        bogus = self._finding("bogus", "history_rewrite")

        self.assertEqual(
            verdict([bogus]),
            "clean",
            "an unknown status must not block the gate today; if the gate "
            "starts blocking on unknown statuses, this pin must be changed "
            "deliberately",
        )
        self.assertEqual(
            remediation([bogus], [bogus]),
            {"needs_ruleset": False, "needs_token_recipe": False},
            "an unknown status must not trigger either prepared fix today",
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
      The warn remedy states the fix in short words, no doc path
      (behaviour 2 of plans/guard-finding-compact.md).
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
        # A passed probe has nothing to fix; its remedy may now be empty
        # (behaviour 2 of plans/guard-finding-compact.md).
        self.assertIsInstance(_field(finding, "remedy"), str)

    def test_recorded_404_yields_warn_naming_no_access_and_recreating_the_token(self):
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
        # The approved sample's "To fix" entry for this finding, with the
        # recorded target substituted for the sample's:
        # "recreate the token with access to {target} only".
        self.assertIn(
            "recreate the token with access to owner/repo only",
            _field(finding, "remedy") or "",
            "the warn remedy must be the sample's short fix naming the "
            "recorded target - no doc path",
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
        # The sample's skip-variant word for a 401, exactly: the short
        # reason carries the status and nothing else - the URL is dropped.
        self.assertEqual(
            _field(finding, "reason"),
            "GitHub returned HTTP 401",
            "the skipped finding's reason must be the sample's short 401 "
            "reason, so the report shows why the probe did not run",
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
        # The sample's skip-variant word for a missing token, exactly.
        self.assertEqual(
            _field(finding, "reason"),
            "no token in .env",
            "the skipped finding's reason must be the sample's short "
            "no-token reason, so the report shows why the probe did not "
            "run",
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
                if _field(finding, "status") != "passed":
                    self.assertTrue(
                        _field(finding, "remedy"),
                        "a non-passing finding carries a non-empty remedy",
                    )
                # A passed probe has nothing to fix; its remedy may now be
                # empty (behaviour 2 of plans/guard-finding-compact.md).
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
                        _field(finding, "brief"),
                        line,
                        "the rendered warn line must carry the finding's "
                        "brief - the danger words the probe records",
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
        # A passed probe has nothing to fix; its remedy may now be empty
        # (behaviour 2 of plans/guard-finding-compact.md).
        self.assertIsInstance(_field(finding, "remedy"), str)

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
        # The sample's fail danger, exactly (behaviour 2 of
        # plans/guard-finding-compact.md, approved sample):
        # "the token can delete or reconfigure iar3-r8/anvil" - the
        # GITHUB_TOKEN clause is dropped with the doc path.
        self.assertEqual(
            danger,
            "the token can delete or reconfigure owner/repo",
            "the fail danger must be the sample's short danger naming "
            "the recorded target - the GITHUB_TOKEN clause is dropped "
            "along with the doc path",
        )
        remedy = _field(finding, "remedy")
        self.assertIsInstance(remedy, str)
        self.assertTrue(
            remedy,
            "the fail finding must carry a non-empty remedy - every "
            "finding must say how to fix the danger",
        )
        # The sample's "To fix" entry for this finding, with the recorded
        # target substituted for the sample's.
        self.assertIn(
            "recreate the token without the Administration permission",
            remedy,
            "the fail remedy must be the sample's short fix - no doc "
            "path",
        )
        self.assertNotIn(
            "doc/external/",
            remedy,
            "the fail remedy must carry no doc path (behaviour 2 of "
            "plans/guard-finding-compact.md)",
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
        # The approved sample's "To fix" entry for this 404 warn:
        # "recreate the token with access to {target} only" - the
        # disambiguation against target_access lives in the remedy's
        # "only", not in the danger.
        self.assertIn(
            "recreate the token with access to owner/repo only",
            _field(finding, "remedy") or "",
            "the 404 warn's remedy must be the sample's short fix naming "
            "the recorded target with 'only' - the disambiguation against "
            "target_access",
        )
        self.assertNotIn(
            "doc/external/",
            _field(finding, "remedy") or "",
            "the 404 warn's remedy must carry no doc path (behaviour 2 "
            "of plans/guard-finding-compact.md)",
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
        # The sample's skip-variant word for a 401, exactly.
        self.assertEqual(
            _field(finding, "reason"),
            "GitHub returned HTTP 401",
            "the skipped finding's reason must be the sample's short 401 "
            "reason, so the report shows why the probe did not run",
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
        # The sample's skip-variant word for a missing token, exactly.
        self.assertEqual(
            _field(finding, "reason"),
            "no token in .env",
            "the skipped finding's reason must be the sample's short "
            "no-token reason, so the report shows why the probe did not "
            "run",
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
                if _field(finding, "status") != "passed":
                    self.assertTrue(
                        _field(finding, "remedy"),
                        "a non-passing finding carries a non-empty remedy",
                    )
                # A passed probe has nothing to fix; its remedy may now be
                # empty (behaviour 2 of plans/guard-finding-compact.md).
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
                        _field(finding, "brief"),
                        line,
                        "the rendered warn line must carry the finding's "
                        "brief - the danger words the probe records",
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
        # The sample's "To fix" entry for this finding, with the recorded
        # target substituted for the sample's.
        self.assertIn(
            "recreate it as a fine-grained token, owner/repo only",
            remedy,
            "the fail remedy must be the sample's short fix - no doc "
            "path",
        )
        self.assertNotIn(
            "doc/external/",
            remedy,
            "the fail remedy must carry no doc path (behaviour 2 of "
            "plans/guard-finding-compact.md)",
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
        # A passed probe has nothing to fix; its remedy may now be empty
        # (behaviour 2 of plans/guard-finding-compact.md).
        self.assertIsInstance(_field(finding, "remedy"), str)

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
        # A passed probe has nothing to fix; its remedy may now be empty
        # (behaviour 2 of plans/guard-finding-compact.md).
        self.assertIsInstance(_field(finding, "remedy"), str)

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
                        _field(finding, "brief") or "",
                        _field(finding, "danger") or "",
                        _field(finding, "reason") or "",
                        _field(finding, "remedy") or "",
                        _field(finding, "source") or "",
                    )
                    if part
                ).lower()
                self.assertIn(
                    "no classic",
                    text,
                    "the pass must state that no classic OAuth scopes "
                    "were returned - a statement about what the response "
                    "did not carry, not a classification of the token",
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
        # The sample's skip-variant word for a 401, exactly.
        self.assertEqual(
            _field(finding, "reason"),
            "GitHub returned HTTP 401",
            "the skipped finding's reason must be the sample's short 401 "
            "reason, so the report shows why the probe did not run",
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
        # The sample's skip-variant word for a missing token, exactly.
        self.assertEqual(
            _field(finding, "reason"),
            "no token in .env",
            "the skipped finding's reason must be the sample's short "
            "no-token reason, so the report shows why the probe did not "
            "run",
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
                if _field(finding, "status") != "passed":
                    self.assertTrue(
                        _field(finding, "remedy"),
                        "a non-passing finding carries a non-empty remedy",
                    )
                # A passed probe has nothing to fix; its remedy may now be
                # empty (behaviour 2 of plans/guard-finding-compact.md).
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


class WorkflowsWithheldFindingTests(unittest.TestCase):
    """Behaviour 5 of plans/verify-guards-token.md: ``workflows_withheld_finding``.

    ``workflows_withheld_finding()`` takes no network and no token - and, per
    the plan, no arguments at all: "Given: nothing; the function takes no
    network and no token". It is the documented-unprovable case, so the
    honest result is a constant ``skipped`` finding, never ``passed``:

    - the ``workflows`` permission has access level **``write`` only** - no
      ``read`` form exists (the permission table in
      ``doc/external/github/fine-grained-personal-access-tokens.md``);
    - the workflows list endpoint,
      ``GET /repos/{owner}/{repo}/actions/workflows``, is gated on
      **"Actions" repository permissions (read)** - not ``workflows`` - and
      works unauthenticated on public repos, so a ``200`` from it proves
      nothing about the token
      (``doc/external/github/rest-api-endpoints-for-workflows.md``);
    - so **no read-only call can prove the ``workflows`` withholding**: the
      only call that would prove it is a write, which the probes must not
      perform.

    Under the #68 rule - a check that cannot run is ``skipped``, never
    ``passed`` - an unprovable withholding must report as ``skipped`` with
    that reason, and the finding's ``remedy`` must tell a human how to verify
    the withholding by hand (a saved page plus a manual check), since the
    probe cannot. The finding dict shape is the one ``render_finding``
    already consumes: ``status``, ``check``, ``rule``, ``danger``,
    ``source`` and ``remedy`` (plus ``reason`` on a skip). No test below
    touches the network: the function takes no opener and no token at all.
    """

    # The saved pages the finding may cite, per the plan: "the remedy names
    # the saved page and the manual UI check".
    _WORKFLOWS_DOC = "doc/external/github/rest-api-endpoints-for-workflows.md"
    _FINE_GRAINED_DOC = (
        "doc/external/github/fine-grained-personal-access-tokens.md"
    )

    def _producer(self) -> Any:
        producer = getattr(piguard, "workflows_withheld_finding", None)
        self.assertTrue(
            callable(producer),
            "anvilkit.pi.piguard.workflows_withheld_finding is not callable; "
            "the workflows-withheld finding has not been implemented yet",
        )
        return producer

    def test_called_with_no_arguments_yields_exactly_one_skipped_finding(self):
        # The plan's contract, verbatim in substance: Given nothing, When it
        # is called, Then exactly one skipped finding. The function takes no
        # network and no token, so the call carries no opener and no token -
        # the callability-seam failure (the function does not exist yet) is
        # the expected red.
        produce = self._producer()

        findings = produce()

        self.assertIsInstance(
            findings,
            list,
            "the finding must be returned as a list of findings, like every "
            "other finding producer in the module",
        )
        self.assertEqual(
            len(findings),
            1,
            "exactly one finding expected: the workflows withholding is "
            "one documented-unprovable case, not one per repo or per run",
        )
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "skipped",
            "the workflows withholding is unprovable by a read-only call, so "
            "it must be reported skipped - the #68 rule's exact case",
        )

    def test_finding_is_never_passed(self):
        # An explicit pin distinct from the equality above: an unprovable
        # withholding must never read as clean. If a later edit made the
        # finding "pass" because nothing bad was observed, this fails -
        # "nothing bad observed" is the opposite of "the withholding is
        # verified".
        produce = self._producer()

        findings = produce()

        self.assertEqual(
            len(findings),
            1,
            "fixture sanity: exactly one finding",
        )
        status = _field(findings[0], "status")
        self.assertNotEqual(
            status,
            "passed",
            "an unprovable withholding must never read as clean: 'we saw "
            "nothing bad' is not 'the workflows permission is withheld', "
            "and a passed status would let the report claim a guarantee no "
            "read-only call established",
        )

    def test_reason_names_no_read_level_and_read_only_unprovability(self):
        # The core fact the finding must carry: the ``workflows`` permission
        # has no ``read`` level, no read-only endpoint is gated on it, so
        # the withholding is unprovable without a write. The wording may be
        # split across ``reason`` and ``danger``, so assert across both -
        # but the substance must be there, and it must name the workflows
        # permission specifically, not just "some permission".
        produce = self._producer()

        findings = produce()

        self.assertEqual(
            len(findings),
            1,
            "fixture sanity: exactly one finding",
        )
        finding = findings[0]
        text = " ".join(
            part
            for part in (
                _field(finding, "reason") or "",
                _field(finding, "danger") or "",
            )
            if part
        )
        self.assertTrue(
            text,
            "the skipped finding must carry a non-empty reason or danger "
            "naming why the check did not run",
        )
        lowered = text.lower()
        self.assertIn(
            "workflows",
            lowered,
            "the finding must name the 'workflows' permission specifically - "
            "it is the documented-unprovable case, not a generic skip",
        )
        self.assertRegex(
            lowered,
            r"\bno read\b",
            "the reason must state that the workflows permission has no "
            "read level (doc/external/github/fine-grained-personal-access-"
            "tokens.md: the permission table lists 'write' only)",
        )
        self.assertRegex(
            lowered,
            r"\bread[- ]only\b",
            "the reason must state that the withholding is unprovable by a "
            "read-only call: the workflows list endpoint is gated on "
            "Actions: read and works unauthenticated on public repos, so no "
            "read endpoint is gated on the workflows permission "
            "(doc/external/github/rest-api-endpoints-for-workflows.md)",
        )
        self.assertRegex(
            lowered,
            r"\bwrite\b",
            "the reason must state that the only call that would prove the "
            "withholding is a write, which the probes must not perform",
        )

    def test_remedy_points_to_the_manual_check_in_github_settings(self):
        # The probe cannot verify the withholding, so the remedy must tell a
        # human how to verify it by hand - a manual check in GitHub settings
        # where the Workflows permission is visible by absence. Behaviour 2
        # words this as a single short sentence with no doc path (the saved
        # page is no longer named; the remedy points at the manual check).
        produce = self._producer()

        findings = produce()

        self.assertEqual(
            len(findings),
            1,
            "fixture sanity: exactly one finding",
        )
        finding = findings[0]
        remedy = _field(finding, "remedy")
        self.assertIsInstance(
            remedy,
            str,
            "remedy must be a string",
        )
        self.assertTrue(
            remedy,
            "every finding carries a non-empty remedy: a finding that "
            "cannot say what the user can do to verify the withholding is "
            "a programming error",
        )
        self.assertIn(
            "in GitHub settings",
            remedy,
            "the remedy must point at the manual check's place - the "
            "GitHub settings, where the Workflows permission is visible "
            "by absence",
        )
        self.assertIn(
            "Workflows permission",
            remedy,
            "the remedy must name what the human checks for - the absence "
            "of the Workflows permission - the substance of the withholding",
        )
        remedy_lower = remedy.lower()
        self.assertIn(
            "check the token",
            remedy_lower,
            "the remedy must tell a human to perform the check by hand - "
            "the probe cannot do it",
        )
        self.assertTrue(
            "ui" in remedy_lower
            or "interface" in remedy_lower
            or "settings" in remedy_lower,
            "the remedy must point at the manual check's place - the "
            "token's permission table in the GitHub settings UI, where "
            "the workflows permission is visible by absence",
        )

    def test_repeated_calls_are_deterministic_and_never_raise(self):
        # The finding is a constant, not derived from any input: no
        # network, no token, no owner/repo - so calling it any number of
        # times must return the same finding, and never raise. A function
        # that secretly took an opener or a token and read from it could
        # not satisfy this with no arguments supplied.
        produce = self._producer()

        first = produce()
        second = produce()
        third = produce()

        for label, findings in (
            ("first call", first),
            ("second call", second),
            ("third call", third),
        ):
            with self.subTest(call=label):
                self.assertIsInstance(findings, list)
                self.assertEqual(
                    len(findings),
                    1,
                    "every call yields exactly one finding, with no "
                    "opener or token supplied",
                )
        self.assertEqual(
            first,
            second,
            "the finding is a constant: two calls with no network and no "
            "token must return equal findings - one derived from an input "
            "would not be",
        )
        self.assertEqual(
            second,
            third,
            "the finding is a constant: a third call must return the same "
            "finding again, and calling it any number of times never "
            "raises",
        )

    def test_finding_carries_check_constant_and_nonempty_danger(self):
        # The module's finding shape: a check name (the new
        # CHECK_WORKFLOWS_WITHHELD constant - present and stable across
        # calls), a non-empty danger (behaviour 10: a non-empty danger on
        # every non-passing finding), and a non-empty remedy.
        produce = self._producer()

        findings = produce()

        self.assertEqual(
            len(findings),
            1,
            "fixture sanity: exactly one finding",
        )
        finding = findings[0]
        check = _field(finding, "check")
        self.assertIsInstance(
            check,
            str,
            "the finding must carry a check name",
        )
        self.assertTrue(
            check,
            "the finding must carry a non-empty check name - the new "
            "CHECK_WORKFLOWS_WITHHELD constant, so check_token_all can "
            "report it alongside the other probes",
        )
        self.assertEqual(
            check,
            "workflows_withheld",
            "the check name must be the stable CHECK_WORKFLOWS_WITHHELD "
            "value - a renamed or missing check would un-pin the "
            "behaviour-10 sweep and the behaviour-8 concatenation order",
        )
        danger = _field(finding, "danger")
        self.assertIsInstance(
            danger,
            str,
            "danger must be a string",
        )
        self.assertTrue(
            danger,
            "a non-passing finding must carry a non-empty danger naming "
            "the hole the report cannot rule out (behaviour 10): that the "
            "workflows withholding is unverified",
        )
        remedy = _field(finding, "remedy")
        self.assertIsInstance(remedy, str)
        self.assertTrue(remedy, "every finding carries a non-empty remedy")

    def test_rendered_finding_is_nonempty_and_mentions_the_reason(self):
        # A skipped finding renders through render_finding's existing
        # skipped branch - no new branch is needed, and it must not fall
        # through to the bare "unknown:" line, which would hide the
        # unprovable-withholding case in the report.
        produce = self._producer()

        findings = produce()

        self.assertEqual(
            len(findings),
            1,
            "fixture sanity: exactly one finding",
        )
        finding = findings[0]
        line = piguard.render_finding(finding)

        self.assertIsInstance(line, str)
        self.assertTrue(
            line,
            "render_finding must produce a non-empty line for the "
            "workflows-withheld finding",
        )
        self.assertNotIn(
            "unknown:",
            line,
            "the finding must render through the known branches, not fall "
            "through to 'unknown:' - a shape mismatch would hide the "
            "unprovable-withholding case in the report",
        )
        self.assertTrue(
            line.startswith("skipped: {}".format(_field(finding, "check"))),
            "the rendered skipped line must keep its 'skipped: "
            "{check}' prefix and its label: {line!r}".format(
                check=_field(finding, "check"), line=line
            ),
        )
        self.assertIn(
            _field(finding, "brief"),
            line,
            "the rendered skipped line must carry the finding's own brief "
            "- every word from the finding's fields: {!r}".format(line),
        )


class ProbeNamedRepoTests(unittest.TestCase):
    """Behaviour 6 of plans/verify-guards-token.md: ``probe_named_repo``.

    ``probe_named_repo(other_repo, token=None, opener=None, timeout=None)``
    runs the named-repo probe: a recorded ``GET /repos/{other_owner}/
    {other_name}`` through :func:`anvilkit.pi.piguard.fetch_probe`
    (behaviour 1, already green) against the raw user-supplied
    ``--other-repo OWNER/REPO`` string. The probe splits the string
    itself (behaviour 18 amendment of the committed behaviour 6/8 seam):
    it is never guessed, and the owner in it is not assumed to equal the
    target's owner (plan Assumptions) - the target owner is no longer a
    parameter at all, so a ``somebody-else/other-repo`` string is probed
    as written.

    The framing rule this probe exists to encode: a ``404`` is the honest
    answer, and it only proves one thing. A repository the token is not
    scoped to returns ``404``, so the probe establishes "the token is not
    scoped to that one repository" - it cannot enumerate the token's full
    repository list, and the finding must say exactly that. (A ``404`` on
    the *target* repository is the louder, different finding: behaviour 2's
    target-access warn, not this probe's.)

    - ``404``  -> one ``passed`` finding worded "proves only that the
      token is not scoped to {other_owner}/{other_name}; it cannot
      enumerate the token's full repository list" - both halves: the
      specific proof and the explicit non-claim - with a non-empty
      remedy carrying a ``doc/external/github/`` path.
    - ``200``  -> one ``warn`` finding: the token reaches more than the
      target, so a compromise of it is not confined to the target repo.
    - ``403``  -> one ``skipped`` finding: a permission denial is not a
      scope answer the probe can interpret.
    - any other status -> one ``skipped`` finding whose reason carries
      the status.
    - transport failure -> one ``skipped`` finding whose reason is
      non-empty.
    - ``token=None`` -> one ``skipped`` finding (behaviour 7), and no
      request may be attempted at all.
    - ``other_repo`` missing, empty or malformed (no ``/``, more than
      one ``/``, or an empty owner/repo part after strip) -> exactly
      one ``skipped`` finding whose reason and remedy name ``--other-repo``
      as the fix, never a pass, and the opener is never called: when
      the input is unparseable there is nothing to probe.

    The finding dict shape is the one ``render_finding`` already
    consumes: ``status``, ``check``, ``rule``, ``danger``, ``source``
    and ``remedy`` (plus ``reason`` on a skip). Every test below runs
    over a recorded opener - no live network.
    """

    TOKEN = "ghp_recordedtoken"
    OTHER_REPO = "someorg/other-repo"
    REPO_PATH = "/repos/someorg/other-repo"
    _200_BODY = b'{"full_name": "someorg/other-repo"}'

    def _prober(self) -> Any:
        prober = getattr(piguard, "probe_named_repo", None)
        self.assertTrue(
            callable(prober),
            "anvilkit.pi.piguard.probe_named_repo is not callable; the "
            "named-repo token-scope probe has not been implemented yet",
        )
        return prober

    def test_check_named_repo_constant_is_present_and_stable(self):
        # The probe's check-name constant, in the module's stable CHECK_*
        # vocabulary: snake_case of the probe's subject, the same spelling
        # pattern as CHECK_TARGET_ACCESS ("target_access"),
        # CHECK_ADMINISTRATION ("administration") and CHECK_CLASSIC_TOKEN
        # ("classic_token").
        constant = getattr(piguard, "CHECK_NAMED_REPO", None)
        self.assertIsNotNone(
            constant,
            "anvilkit.pi.piguard.CHECK_NAMED_REPO must exist: the "
            "named-repo probe's check-name constant is part of the "
            "module's stable CHECK_* vocabulary",
        )
        self.assertEqual(
            constant,
            "named_repo",
            "CHECK_NAMED_REPO follows the sibling check-name spelling "
            "pattern (target_access, administration, classic_token)",
        )

    def test_recorded_404_yields_exactly_one_passed_finding_naming_the_scope_limit(self):
        # The framing rule: a 404 is the honest answer, and it only proves
        # one thing - the token is not scoped to that one repository. It
        # cannot enumerate the token's full repository list, so the
        # finding must say exactly that: the specific proof AND the
        # explicit non-claim, naming the split parts of the raw
        # --other-repo string as written.
        probe = self._prober()
        url = "https://api.github.com" + self.REPO_PATH

        findings = probe(
            self.OTHER_REPO,
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
            "the named-repo probe yields exactly one finding",
        )
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "passed",
            "a 404 on the other repo is the honest answer: the token is "
            "not scoped to it - the probe passes",
        )
        remedy = _field(finding, "remedy")
        self.assertIsInstance(remedy, str)
        self.assertTrue(
            remedy,
            "every finding carries a non-empty remedy",
        )
        self.assertIn(
            "not scoped to someorg/other-repo",
            remedy,
            "the passed finding must state the specific proof: the token "
            "is not scoped to that one repository - the split parts of "
            "the raw --other-repo string, as written",
        )
        self.assertIn(
            "cannot enumerate",
            remedy,
            "the passed finding must carry the explicit non-claim: the "
            "probe cannot enumerate the token's full repository list - a "
            "pass that claims more than one 404 proves overstates the "
            "evidence",
        )
        self.assertIn(
            "full repository list",
            remedy,
            "the non-claim must name what cannot be enumerated: the "
            "token's full repository list",
        )
        self.assertIn(
            "cannot enumerate the full repository list",
            remedy,
            "the passed remedy must carry the scope-limit non-claim as a "
            "single clause - the probe proves only that this one repo is "
            "out of reach, never a full-list clearance (behaviour 2 "
            "drops the doc path)",
        )

    def test_recorded_200_yields_exactly_one_warn_finding_reaching_more_than_the_target(self):
        # A 200 means the token reaches this other repository too: the
        # scope is wider than the target, so a compromise of the token is
        # not confined to the target repository. The warn carries the
        # consequence (the danger) and a remedy naming a saved page under
        # doc/external/github/.
        probe = self._prober()
        opener = _CapturingOpener(_FakeResponse(self._200_BODY, 200))

        findings = probe(
            self.OTHER_REPO, self.TOKEN, opener=opener, timeout=10.0
        )

        self.assertIsInstance(findings, list)
        self.assertEqual(
            len(findings),
            1,
            "the named-repo probe yields exactly one finding",
        )
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "warn",
            "a 200 on the other repo means the token reaches more than "
            "the target - a warn, not a pass and not a fail",
        )
        danger = _field(finding, "danger")
        self.assertIsInstance(danger, str)
        self.assertTrue(
            danger,
            "the warn must carry a non-empty danger stating the "
            "consequence: a compromise of this token is not confined to "
            "the target repository",
        )
        self.assertIn(
            "target",
            danger,
            "the warn's danger must state that the token reaches more "
            "than the target - that is what the 200 establishes",
        )
        remedy = _field(finding, "remedy")
        self.assertIsInstance(remedy, str)
        self.assertTrue(
            remedy,
            "every finding carries a non-empty remedy",
        )
        self.assertIn(
            "recreate the token",
            remedy,
            "the warn remedy must tell the user the fix - recreate the "
            "token - now worded as a short sentence, not a doc path "
            "(behaviour 2)",
        )
        self.assertIn(
            "target",
            remedy,
            "the warn remedy must name the target the token should be "
            "scoped to only - the substance of the 200 finding",
        )

    def test_no_other_repo_supplied_yields_skipped_naming_the_flag_without_request(self):
        # Nothing to probe: no request is attempted, and the finding must
        # name --other-repo as the fix, never a pass - a pass with no
        # repository named would claim a scope fact that was never
        # measured.
        probe = self._prober()
        for label, other_repo in (("None", None), ("empty string", "")):
            with self.subTest(other_repo=label):
                opener = _CapturingOpener(_FakeResponse(self._200_BODY, 200))

                findings = probe(
                    other_repo,
                    self.TOKEN,
                    opener=opener,
                    timeout=10.0,
                )

                self.assertIsNone(
                    opener.captured,
                    "with no other repository supplied the probe must not "
                    "attempt a request at all: there is nothing to probe",
                )
                self.assertIsInstance(findings, list)
                self.assertEqual(
                    len(findings),
                    1,
                    "the named-repo probe yields exactly one finding",
                )
                finding = findings[0]
                self.assertEqual(
                    _field(finding, "status"),
                    "skipped",
                    "no other repo supplied means the probe skips - never "
                    "a pass",
                )
                reason = (
                    _field(finding, "reason")
                    or _field(finding, "danger")
                    or ""
                )
                self.assertTrue(
                    reason,
                    "the skipped finding must carry a non-empty reason",
                )
                self.assertIn(
                    "--other-repo",
                    _field(finding, "remedy") or "",
                    "the skipped finding must name --other-repo as the "
                    "fix: supplying a repository is what makes the probe "
                    "runnable",
                )

    def test_recorded_403_yields_skipped_permission_denial_not_scope_answer(self):
        # A 403 on the other repo is a permission denial, not a scope
        # answer: unlike the administration probe, where 403 is the
        # compliant withholding, here the probe cannot read a denial as
        # "not scoped to" - it skips.
        probe = self._prober()
        url = "https://api.github.com" + self.REPO_PATH

        findings = probe(
            self.OTHER_REPO,
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
            "the named-repo probe yields exactly one finding",
        )
        finding = findings[0]
        self.assertEqual(
            _field(finding, "status"),
            "skipped",
            "a 403 on the other repo is a permission denial, not a scope "
            "answer the probe can interpret: it skips, it does not pass "
            "and it does not warn",
        )
        reason = (
            _field(finding, "reason")
            or _field(finding, "danger")
            or ""
        )
        self.assertTrue(
            reason,
            "the skipped finding must carry a non-empty reason naming "
            "the denial",
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
                    self.OTHER_REPO,
                    self.TOKEN,
                    opener=_opener(
                        urllib.error.HTTPError(url, status, phrase, None, None)
                    ),
                    timeout=10.0,
                )

                self.assertEqual(
                    len(findings),
                    1,
                    "the named-repo probe yields exactly one finding",
                )
                finding = findings[0]
                self.assertEqual(
                    _field(finding, "status"),
                    "skipped",
                    "any status other than 404 or 200 is not a scope "
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
                    self.OTHER_REPO,
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
            self.OTHER_REPO, None, opener=opener, timeout=10.0
        )

        self.assertIsNone(
            opener.captured,
            "with no token the probe must not attempt a request at all: "
            "a token-scope probe reads a token property, and an "
            "unauthenticated request establishes no fact about any token",
        )
        self.assertIsInstance(findings, list)
        self.assertEqual(
            len(findings),
            1,
            "the named-repo probe yields exactly one finding",
        )
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

    def test_request_targets_the_other_repo_endpoint_never_the_target(self):
        # The probe is GET /repos/{other_owner}/{other_name} for the raw
        # --other-repo string: the recorded request it builds must carry
        # that path as written, so the probe hits the *other* repository
        # - never the target. The owner in the string is the owner
        # probed: with no target owner in the signature, a string whose
        # owner differs from any target is probed as written (plan
        # Assumptions, behaviour 18).
        probe = self._prober()
        for label, other_repo, expected in (
            (
                "supplied halves",
                "someorg/other-repo",
                "/repos/someorg/other-repo",
            ),
            (
                "owner differs from any target owner",
                "somebody-else/other-repo",
                "/repos/somebody-else/other-repo",
            ),
        ):
            with self.subTest(label=label):
                opener = _CapturingOpener(_FakeResponse(self._200_BODY, 200))

                probe(other_repo, self.TOKEN, opener=opener, timeout=10.0)

                request = opener.captured
                self.assertIsNotNone(
                    request,
                    "the probe must hand its opener a request to open",
                )
                url = getattr(request, "full_url", None) or getattr(
                    request, "url", ""
                )
                parsed = urllib.parse.urlparse(url)
                self.assertEqual(
                    parsed.path,
                    expected,
                    "the probe must issue GET "
                    "/repos/{{other_owner}}/{{other_name}} for the "
                    "supplied string - {} - not any other path".format(
                        expected
                    ),
                )
                self.assertNotEqual(
                    parsed.path,
                    "/repos/owner/repo",
                    "the probe must never hit the target repository: a "
                    "404 there is behaviour 2's louder finding, not "
                    "this probe's",
                )

    def test_findings_carry_the_module_finding_shape_and_render(self):
        # The finding dicts must match what render_finding already
        # consumes: a passed finding (404) renders without falling to the
        # unknown line, a warn (200) carries a non-empty danger and
        # remedy that survive rendering, and the skipped findings (403,
        # no other repo, malformed other repo, no token) render with
        # their reason. A shape mismatch would make render_finding fall
        # through to the "unknown: ..." line and hide the probe's result.
        probe = self._prober()
        url = "https://api.github.com" + self.REPO_PATH
        cases = [
            (
                "passed (404)",
                urllib.error.HTTPError(url, 404, "Not Found", None, None),
            ),
            ("warn (200)", _FakeResponse(self._200_BODY, 200)),
            (
                "skipped (403)",
                urllib.error.HTTPError(url, 403, "Forbidden", None, None),
            ),
        ]

        for label, outcome in cases:
            with self.subTest(label=label):
                findings = probe(
                    self.OTHER_REPO,
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
                if _field(finding, "status") != "passed":
                    self.assertTrue(
                        _field(finding, "remedy"),
                        "a non-passing finding carries a non-empty remedy",
                    )
                # A passed probe has nothing to fix; its remedy may now be
                # empty (behaviour 2 of plans/guard-finding-compact.md).
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
                        _field(finding, "brief"),
                        line,
                        "the rendered warn line must carry the finding's "
                        "brief - the danger words the probe records",
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

        # The three skip modes that must not attempt a request render
        # with their reason, through the same skipped branch.
        skip_cases = (
            (
                "skipped (no other repo)",
                None,
                self.TOKEN,
            ),
            (
                "skipped (malformed other repo)",
                "no-slash-here",
                self.TOKEN,
            ),
            (
                "skipped (no token)",
                self.OTHER_REPO,
                None,
            ),
        )
        for label, other_repo, token in skip_cases:
            with self.subTest(label=label):
                opener = _CapturingOpener(_FakeResponse(self._200_BODY, 200))
                findings = probe(
                    other_repo,
                    token,
                    opener=opener,
                    timeout=10.0,
                )
                self.assertEqual(len(findings), 1)
                finding = findings[0]
                self.assertEqual(
                    _field(finding, "status"),
                    "skipped",
                    "an unrunnable named-repo probe renders as a skip",
                )
                line = piguard.render_finding(finding)
                self.assertIsInstance(line, str)
                self.assertTrue(
                    line,
                    "render_finding must produce a non-empty line for the "
                    "probe's skipped finding",
                )
                self.assertNotIn(
                    "unknown:",
                    line,
                    "the skipped finding must render through the known "
                    "branches, not fall through to 'unknown:'",
                )
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
            (
                "404",
                urllib.error.HTTPError(url, 404, "Not Found", None, None),
            ),
            ("200", _FakeResponse(self._200_BODY, 200)),
            (
                "403",
                urllib.error.HTTPError(url, 403, "Forbidden", None, None),
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
        for label, outcome in modes:
            with self.subTest(mode=label):
                try:
                    findings = probe(
                        self.OTHER_REPO,
                        self.TOKEN,
                        opener=_opener(outcome),
                        timeout=10.0,
                    )
                except Exception as exc:
                    self.fail(
                        "probe_named_repo raised {} for the recorded "
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
                    "the named-repo probe yields exactly one finding",
                )

        for label, other_repo, token in (
            ("no other repo", None, self.TOKEN),
            ("malformed other repo", "a/b/c", self.TOKEN),
            ("no token", self.OTHER_REPO, None),
        ):
            with self.subTest(mode=label):
                try:
                    findings = probe(
                        other_repo,
                        token,
                        opener=_CapturingOpener(
                            _FakeResponse(self._200_BODY, 200)
                        ),
                        timeout=10.0,
                    )
                except Exception as exc:
                    self.fail(
                        "probe_named_repo raised {} for the {}; every "
                        "mode must return a finding list, not an "
                        "exception".format(type(exc).__name__, label)
                    )
                self.assertIsInstance(
                    findings,
                    list,
                    "every recorded mode returns a finding list",
                )
                self.assertEqual(
                    len(findings),
                    1,
                    "the named-repo probe yields exactly one finding",
                )

    def test_malformed_other_repo_yields_one_skipped_naming_the_flag_and_never_calls_the_opener(self):
        # Behaviour 18: a --other-repo value that is not OWNER/REPO -
        # no slash, more than one slash, or an empty owner/repo part
        # after strip - cannot be probed: exactly one skipped finding
        # whose reason and remedy name --other-repo as the fix, and the
        # opener is never called, because when the input is unparseable
        # there is nothing to probe.
        probe = self._prober()
        for label, other_repo in (
            ("no slash", "no-slash-here"),
            ("two slashes", "a/b/c"),
            ("empty owner part", "/other-repo"),
            ("empty repo part", "owner/"),
            ("whitespace only", "   "),
        ):
            with self.subTest(other_repo=other_repo):
                opener = _CapturingOpener(_FakeResponse(self._200_BODY, 200))

                findings = probe(
                    other_repo,
                    self.TOKEN,
                    opener=opener,
                    timeout=10.0,
                )

                self.assertIsNone(
                    opener.captured,
                    "with a malformed --other-repo the opener must never "
                    "be called: the input is unparseable, so there is "
                    "nothing to probe",
                )
                self.assertIsInstance(findings, list)
                self.assertEqual(
                    len(findings),
                    1,
                    "a malformed --other-repo yields exactly one "
                    "finding - a skip, never a crash",
                )
                finding = findings[0]
                self.assertEqual(
                    _field(finding, "check"),
                    "named_repo",
                    "the malformed input is reported in the named-repo "
                    "slot under the probe's check constant",
                )
                self.assertEqual(
                    _field(finding, "status"),
                    "skipped",
                    "a malformed --other-repo is a skip - never a pass, "
                    "a warn or a fail",
                )
                reason = (
                    _field(finding, "reason") or _field(finding, "danger")
                )
                self.assertTrue(
                    reason,
                    "the skipped finding must carry a non-empty reason "
                    "naming the unparseable input",
                )
                self.assertIn(
                    "--other-repo",
                    reason,
                    "the skipped finding's reason must name --other-repo "
                    "as the value that is wrong",
                )
                self.assertIn(
                    "--other-repo",
                    _field(finding, "remedy") or "",
                    "the skipped finding's remedy must name --other-repo "
                    "as the fix: supplying a well-formed OWNER/REPO is "
                    "what makes the probe runnable",
                )


class _RecordingOpener:
    """An opener that records every request path it is handed, then plays
    back one recorded outcome (or raises) on each call.

    The multi-request sibling of :class:`_CapturingOpener`:
    ``check_token_all`` routes every network probe through the same single
    opener, so one opener must survive several calls and remember all of
    them - the recorded path list is how a test proves the probes share
    one fetch seam.
    """

    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome
        self.paths: List[str] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        request = args[0]
        url = getattr(request, "full_url", None) or getattr(request, "url", "")
        self.paths.append(urllib.parse.urlparse(url).path)
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


class CheckTokenAllTests(unittest.TestCase):
    """Behaviour 8 of plans/verify-guards-token.md: ``check_token_all``.

    ``check_token_all(owner, repo, token=None, other_repo=None, opener=None,
    timeout=None)`` is the token-scope probe concatenation: the findings of
    behaviours 2, 3, 4, 5 and 6 - target_access, administration,
    classic_token, workflows_withheld and named_repo - returned in that
    fixed order. It is the single seam both CLI call sites (verify-guards
    and doctor's Guards section) will report through: a probe added here
    reaches both with no edit at either, so the fixed, explicit order is
    the load-bearing contract, and the one injected opener is the one seam
    every network probe routes through (each probe routes through
    ``fetch_probe``, never a parallel fetch path).

    ``other_repo`` is the raw user-supplied ``--other-repo OWNER/REPO``
    value, passed to :func:`anvilkit.pi.piguard.probe_named_repo`
    unsplit: the target ``owner`` feeds the other four probes only, never
    the named-repo probe, whose request uses the string's own owner
    (behaviour 18).

    - ``token=None`` -> every network probe skips (behaviour 7) but the
      constant ``workflows_withheld`` finding is still present in its
      position - it takes no network and no token.
    - no other repo supplied -> the named_repo slot is the probe's
      no-other-repo ``skipped``, not a missing slot.
    - a malformed other repo (not ``OWNER/REPO``) -> the named_repo slot
      is the probe's malformed-input ``skipped`` naming
      ``--other-repo``, not a missing slot and not an exception
      (behaviour 18).
    - an all-failing opener -> all five findings ``skipped``, never an
      exception: never raises, never exits.

    Every test below runs over a recorded opener - no live network.
    """

    TOKEN = "ghp_recordedtoken"
    OWNER = "owner"
    REPO = "repo"
    # The raw --other-repo value: its own owner (someorg) differs from
    # the target's owner (owner), so the named_repo slot's request is
    # distinguishable from the target probes' requests - behaviour 18:
    # the target owner never feeds the named-repo probe.
    OTHER_REPO = "someorg/other-repo"

    # The fixed concatenation order: behaviours 2, 3, 4, 5 and 6.
    EXPECTED_CHECK_ORDER = (
        "target_access",
        "administration",
        "classic_token",
        "workflows_withheld",
        "named_repo",
    )

    _KNOWN_STATUSES = ("passed", "warn", "skipped", "fail")

    def _checker(self) -> Any:
        checker = getattr(piguard, "check_token_all", None)
        self.assertTrue(
            callable(checker),
            "anvilkit.pi.piguard.check_token_all is not callable; the "
            "token-scope probe concatenation has not been implemented yet",
        )
        return checker

    def _all_200_opener(self) -> Any:
        return _RecordingOpener(_FakeResponse(b'{"ok": true}', 200))

    def test_fully_succeeding_opener_yields_findings_in_the_fixed_check_order(self):
        # The load-bearing assertion: with a fully-succeeding recorded
        # opener (200 everywhere, no scope header) the findings must come
        # out in the fixed order target_access, administration,
        # classic_token, workflows_withheld, named_repo.
        checker = self._checker()
        opener = self._all_200_opener()

        findings = checker(
            self.OWNER,
            self.REPO,
            token=self.TOKEN,
            other_repo=self.OTHER_REPO,
            opener=opener,
            timeout=10.0,
        )

        self.assertIsInstance(findings, list)
        self.assertEqual(
            len(findings),
            5,
            "each of the five probes contributes its own one-element "
            "finding list, so all probes running means exactly five "
            "findings",
        )
        self.assertEqual(
            [_field(f, "check") for f in findings],
            list(self.EXPECTED_CHECK_ORDER),
            "the findings must come out in the fixed order target_access, "
            "administration, classic_token, workflows_withheld, "
            "named_repo - both call sites gain a future probe with no "
            "edit at either only because that order is explicit",
        )

    def test_each_probe_contributes_exactly_one_finding(self):
        checker = self._checker()

        findings = checker(
            self.OWNER,
            self.REPO,
            token=self.TOKEN,
            other_repo=self.OTHER_REPO,
            opener=self._all_200_opener(),
            timeout=10.0,
        )

        self.assertEqual(len(findings), 5)
        for check in self.EXPECTED_CHECK_ORDER:
            with self.subTest(check=check):
                matching = [f for f in findings if _field(f, "check") == check]
                self.assertEqual(
                    len(matching),
                    1,
                    "the {} probe must contribute exactly its own "
                    "one-element finding list - a probe contributing "
                    "zero or two findings would break the fixed "
                    "concatenation".format(check),
                )

    def test_workflows_withheld_is_present_in_position_when_the_other_probes_skip(self):
        # The workflows_withheld finding is a constant: it takes no
        # network and no token, so it must survive even when every
        # network probe skips for a missing token - in its fixed
        # position, not appended, not dropped.
        checker = self._checker()
        opener = _RecordingOpener(_FakeResponse(b'{"ok": true}', 200))

        findings = checker(
            self.OWNER,
            self.REPO,
            token=None,
            other_repo=self.OTHER_REPO,
            opener=opener,
            timeout=10.0,
        )

        self.assertEqual(
            [_field(f, "check") for f in findings],
            list(self.EXPECTED_CHECK_ORDER),
            "even when all four network probes skip, the five slots stay "
            "in their fixed order",
        )
        self.assertEqual(
            [_field(f, "status") for f in findings],
            ["skipped"] * 5,
            "a missing token skips every network probe (behaviour 7), and "
            "the constant workflows_withheld finding is skipped too - "
            "nothing passes",
        )
        workflows = findings[3]
        self.assertEqual(
            _field(workflows, "check"),
            "workflows_withheld",
            "the workflows_withheld slot stays in its fourth position",
        )
        self.assertEqual(
            _field(workflows, "status"),
            "skipped",
            "the workflows withholding is unprovable by a read-only call: "
            "skipped, never passed, even when no token is supplied",
        )
        self.assertEqual(
            opener.paths,
            [],
            "with no token no network probe may attempt a request - the "
            "workflows_withheld finding must come from the constant, not "
            "a fetch",
        )

    def test_no_other_repo_supplied_yields_the_named_repo_skip_not_a_missing_slot(self):
        checker = self._checker()
        opener = _RecordingOpener(_FakeResponse(b'{"ok": true}', 200))

        findings = checker(
            self.OWNER,
            self.REPO,
            token=self.TOKEN,
            other_repo=None,
            opener=opener,
            timeout=10.0,
        )

        self.assertEqual(
            [_field(f, "check") for f in findings],
            list(self.EXPECTED_CHECK_ORDER),
            "an absent other repo must not drop the named_repo slot or "
            "shift the fixed order",
        )
        named = findings[4]
        self.assertEqual(
            _field(named, "status"),
            "skipped",
            "no other repo supplied is the probe's no-other-repo skipped - "
            "never a pass, never a missing finding, never a crash",
        )
        self.assertNotIn(
            "/repos/{}".format(self.OTHER_REPO),
            opener.paths,
            "with no other repo supplied the named-repo probe must not "
            "attempt a request: there is nothing to probe",
        )

    def test_all_failing_opener_yields_five_skipped_findings_not_an_exception(self):
        checker = self._checker()

        try:
            findings = checker(
                self.OWNER,
                self.REPO,
                token=self.TOKEN,
                other_repo=self.OTHER_REPO,
                opener=_RecordingOpener(
                    urllib.error.URLError("Name or service not known")
                ),
                timeout=10.0,
            )
        except Exception as exc:
            self.fail(
                "check_token_all raised {} for an opener failing every "
                "call; an all-failing opener must yield all-skipped "
                "findings, not an exception".format(type(exc).__name__)
            )

        self.assertIsInstance(findings, list)
        self.assertEqual(
            len(findings),
            5,
            "an all-failing opener still yields one finding per probe "
            "slot - a report that drops a slot hides a probe",
        )
        self.assertEqual(
            [_field(f, "status") for f in findings],
            ["skipped"] * 5,
            "a transport failure on every call skips every network probe, "
            "and the constant workflows_withheld finding is skipped too - "
            "nothing passes, nothing fails",
        )
        for finding in findings:
            with self.subTest(check=_field(finding, "check")):
                carried = _field(finding, "reason") or _field(finding, "danger")
                self.assertIsInstance(carried, str)
                self.assertTrue(
                    carried,
                    "every skipped finding carries a non-empty reason "
                    "(or danger) naming why the probe did not run",
                )
                self.assertTrue(
                    _field(finding, "remedy"),
                    "every skipped finding carries a non-empty remedy",
                )

    def test_never_raises_across_the_documented_transport_set(self):
        # fetch_probe documents exactly this transport set (URLError,
        # socket.timeout, bare OSError); check_token_all must return
        # their findings, never propagate them - across every probe.
        checker = self._checker()
        for label, outcome in (
            ("URLError", urllib.error.URLError("Name or service not known")),
            ("socket.timeout", socket.timeout("timed out")),
            ("bare OSError", OSError("Network is unreachable")),
        ):
            with self.subTest(transport=label):
                try:
                    findings = checker(
                        self.OWNER,
                        self.REPO,
                        token=self.TOKEN,
                        other_repo=self.OTHER_REPO,
                        opener=_RecordingOpener(outcome),
                        timeout=10.0,
                    )
                except Exception as exc:
                    self.fail(
                        "check_token_all raised {} for the recorded {}; "
                        "every documented transport failure must be "
                        "returned as skipped findings, not thrown".format(
                            type(exc).__name__, label
                        )
                    )
                self.assertEqual(
                    [_field(f, "status") for f in findings],
                    ["skipped"] * 5,
                    "every documented transport failure skips all five "
                    "slots",
                )

    def test_every_finding_is_wellformed_in_the_all_ran_case(self):
        # The module's finding invariant on behaviour 8's own output: a
        # known status and a non-empty string remedy on every finding.
        # Behaviour 10 will sweep the whole module; the concatenation's
        # output should already be shape-correct.
        checker = self._checker()

        findings = checker(
            self.OWNER,
            self.REPO,
            token=self.TOKEN,
            other_repo=self.OTHER_REPO,
            opener=self._all_200_opener(),
            timeout=10.0,
        )

        self.assertEqual(len(findings), 5)
        for finding in findings:
            with self.subTest(check=_field(finding, "check")):
                status = _field(finding, "status")
                self.assertIn(
                    status,
                    self._KNOWN_STATUSES,
                    "the finding's status {!r} is not one of the four "
                    "known statuses; the report cannot interpret it".format(
                        status
                    ),
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
                    "a finding with an empty remedy is a programming "
                    "error: it cannot name the concrete fix",
                )

    def test_one_injected_opener_reaches_every_probe_endpoint_exactly_once(self):
        # The opener is the single seam: with one injected opener, every
        # network probe must reach its endpoint through it. The recorded
        # paths pin that check_token_all routes through the probes (which
        # route through fetch_probe), not a parallel fetch path.
        checker = self._checker()
        opener = self._all_200_opener()

        checker(
            self.OWNER,
            self.REPO,
            token=self.TOKEN,
            other_repo=self.OTHER_REPO,
            opener=opener,
            timeout=10.0,
        )

        self.assertEqual(
            sorted(opener.paths),
            sorted(
                [
                    "/repos/{}/{}".format(self.OWNER, self.REPO),
                    "/repos/{}/{}/actions/permissions".format(
                        self.OWNER, self.REPO
                    ),
                    "/user",
                    "/repos/{}".format(self.OTHER_REPO),
                ]
            ),
            "the one injected opener must see exactly the four probe "
            "endpoints - the target repo, its actions/permissions, "
            "/user, and the named other repo - no more, no fewer, and "
            "each exactly once. The named-repo endpoint is /repos/"
            "someorg/other-repo - the string's OWN owner, not the "
            "target's: the target /repos/owner/repo is hit by the "
            "first probes only (behaviour 18)",
        )

    def test_no_token_attempts_no_network_request_at_all(self):
        checker = self._checker()
        opener = _RecordingOpener(_FakeResponse(b'{"ok": true}', 200))

        findings = checker(
            self.OWNER,
            self.REPO,
            token=None,
            other_repo=self.OTHER_REPO,
            opener=opener,
            timeout=10.0,
        )

        self.assertEqual(
            opener.paths,
            [],
            "with no token no network request may be attempted at all: a "
            "token-scope probe reads a token property, and an "
            "unauthenticated request establishes no fact about any token",
        )
        self.assertEqual(len(findings), 5)
        self.assertEqual(
            [_field(f, "check") for f in findings],
            list(self.EXPECTED_CHECK_ORDER),
            "five findings: four probe-skips plus the constant "
            "workflows_withheld skip, in their fixed order",
        )
        self.assertEqual(
            [_field(f, "status") for f in findings],
            ["skipped"] * 5,
            "with no token nothing passes",
        )

    def test_malformed_other_repo_yields_the_named_repo_skip_not_an_exception(self):
        # Behaviour 18: a raw --other-repo value that is not OWNER/REPO
        # must surface as the named_repo slot's skipped finding - the
        # total stays five, the fixed order holds, and no exception
        # escapes the concatenation.
        checker = self._checker()
        opener = _RecordingOpener(_FakeResponse(b'{"ok": true}', 200))

        try:
            findings = checker(
                self.OWNER,
                self.REPO,
                token=self.TOKEN,
                other_repo="no-slash-here",
                opener=opener,
                timeout=10.0,
            )
        except Exception as exc:
            self.fail(
                "check_token_all raised {} for a malformed other_repo; "
                "the malformed value must surface as the named-repo "
                "skipped slot, not an exception".format(
                    type(exc).__name__
                )
            )

        self.assertEqual(
            len(findings),
            5,
            "a malformed other_repo still yields five findings - the "
            "named_repo slot is its skipped finding, not a missing "
            "slot",
        )
        self.assertEqual(
            [_field(f, "check") for f in findings],
            list(self.EXPECTED_CHECK_ORDER),
            "the fixed order must survive a malformed other_repo",
        )
        named = findings[4]
        self.assertEqual(
            _field(named, "status"),
            "skipped",
            "the named_repo slot for a malformed other_repo is a skip - "
            "never a pass, a warn or a fail",
        )
        carried = (
            _field(named, "reason")
            or _field(named, "danger")
            or _field(named, "remedy")
            or ""
        )
        self.assertIn(
            "--other-repo",
            carried,
            "the named_repo skip for a malformed other_repo must name "
            "--other-repo as the value to fix",
        )
        self.assertNotIn(
            "/repos/no-slash-here",
            opener.paths,
            "a malformed other_repo has no parseable repository: the "
            "named-repo probe must not attempt a request for it",
        )


class RenderFindingFailBranchTests(unittest.TestCase):
    """Behaviour 9: render_finding renders a fail finding.

    The token probes (behaviours 3 and 4 of plans/verify-guards-token.md)
    are the first to emit a ``fail`` finding. ``render_finding`` has no
    ``fail`` branch yet, so a ``fail`` falls through to the
    ``"unknown: ... finding for rule None"`` line - which would hide the
    first real failure the family can emit.

    The fail line must be marked as a failure (a ``fail:`` prefix,
    consistent with the ``ok:`` / ``warn:`` / ``skipped:`` convention the
    other branches use), name the danger and the remedy (a ``fix:``-like
    position, consistent with the ``warn:`` branch), and work for token
    findings whose ``rule`` is ``None`` - the fallthrough's ``for rule
    None`` is exactly the bug being fixed.

    The empty-danger / empty-remedy programming-error case is NOT
    asserted here: behaviour 10's sweep owns it.
    """

    def _assert_fail_line(self, finding: Dict[str, Any], line: str) -> None:
        # Behaviour 3 of plans/guard-finding-compact.md: the fail line is
        # the one vocabulary - "fail: {label} - {brief}" - where the label
        # is the finding's rule (or its check on a token finding) and the
        # brief is the finding's own short substance. Every word of the
        # line comes from the finding's own fields; the remedy no longer
        # rides inline (it moves to the report's "To fix" section,
        # behaviour 7), so the old "fix: {remedy}" tail is re-pointed here.
        self.assertIsInstance(line, str)
        self.assertTrue(
            line,
            "a fail finding must render a non-empty line",
        )
        self.assertNotIn(
            "unknown:",
            line,
            "a fail finding must be distinct from the 'unknown:' "
            "fallthrough - that line would hide the first real failure "
            "the family can emit: {!r}".format(line),
        )
        rule = _field(finding, "rule")
        label = rule if rule is not None else _field(finding, "check")
        self.assertTrue(
            line.startswith("fail: {}".format(label)),
            "the fail line must keep its 'fail:' prefix and its label "
            "{!r}, consistent with the ok:/warn:/skipped: prefix "
            "convention: {!r}".format(label, line),
        )
        self.assertIn(
            _field(finding, "brief"),
            line,
            "the rendered fail line must carry the finding's own brief - "
            "every word from the finding's fields: {!r}".format(line),
        )
        self.assertLessEqual(
            len(line),
            160,
            "the rendered line must be at most 160 characters, got {}: "
            "{!r}".format(len(line), line),
        )

    def test_wellformed_fail_finding_renders_failure_line_with_label_and_brief(self):
        finding = {
            "status": "fail",
            "check": "administration",
            "rule": None,
            "brief": "the token can delete or reconfigure owner/repo",
            "danger": (
                "the token holds Administration (read) on owner/repo: "
                "the repository can be deleted or reconfigured, and the "
                "default GITHUB_TOKEN permissions can be raised to write"
            ),
            "source": None,
            "remedy": (
                "recreate the token without the Administration "
                "permission - the token recipe omits it on purpose; see "
                "doc/external/github/"
                "rest-api-endpoints-for-actions-permissions.md"
            ),
        }

        line = piguard.render_finding(finding)

        self._assert_fail_line(finding, line)

    def test_probe_fail_findings_with_rule_none_do_not_render_rule_none(self):
        # The real fail findings behaviours 3 and 4 emit: both carry
        # rule=None, so the fail line must not depend on rule being
        # non-None.
        for label, finding in (
            (
                "administration (behaviour 3, 200)",
                piguard.probe_administration(
                    "owner",
                    "repo",
                    token="token-xyz",
                    opener=_opener(_FakeResponse(b"{}", 200)),
                )[0],
            ),
            (
                "classic_token (behaviour 4, non-empty scopes header)",
                piguard.probe_classic_token(
                    "token-xyz",
                    opener=_opener(
                        _FakeResponse(
                            b"{}",
                            200,
                            headers={"X-OAuth-Scopes": "repo, user"},
                        )
                    ),
                )[0],
            ),
        ):
            with self.subTest(probe=label):
                self.assertEqual(
                    _field(finding, "status"),
                    "fail",
                    "fixture sanity: the probe emits a fail finding",
                )
                self.assertIsNone(
                    _field(finding, "rule"),
                    "fixture sanity: a token finding carries rule=None",
                )

                line = piguard.render_finding(finding)

                self._assert_fail_line(finding, line)
                self.assertNotIn(
                    "rule None",
                    line,
                    "the fail line must not render the token finding's "
                    "rule as 'rule None' - the fallthrough's 'for rule "
                    "None' is the bug being fixed: {!r}".format(line),
                )
                self.assertNotIn(
                    "None",
                    line,
                    "the fail line must not depend on rule being "
                    "non-None: neither the danger nor the remedy of a "
                    "token fail finding carries 'None': {!r}".format(line),
                )

    def test_minimal_fail_finding_is_not_routed_through_another_branch(self):
        # Only the fields a fail finding carries - no reason, no source -
        # so a green that routes fail through the warn (or any other)
        # branch cannot quietly work: it would render a 'warn:' line for
        # a finding the report must mark as a failure.
        finding = {
            "status": "fail",
            "check": "administration",
            "rule": None,
            "brief": "the token can delete or reconfigure owner/repo",
            "danger": "the repository can be deleted",
            "remedy": "recreate the token without Administration",
        }

        line = piguard.render_finding(finding)

        self.assertTrue(
            line.startswith("fail:"),
            "a fail finding must render the fail line, not be routed "
            "through another branch: {!r}".format(line),
        )
        for prefix in ("warn:", "ok:", "skipped:", "unknown:"):
            self.assertNotIn(
                prefix,
                line,
                "a fail finding must not carry a {!r} marker: "
                "{!r}".format(prefix, line),
            )
        self.assertIn("the token can delete or reconfigure owner/repo", line)

    def test_existing_branches_render_the_one_vocabulary(self):
        # Behaviour 3 of plans/guard-finding-compact.md: every branch of
        # render_finding renders the one vocabulary - "{prefix}: {label}
        # - {the finding's own brief}" - built from the finding's own
        # fields. Re-pointed from the old verbose pins: the passed line
        # drops the hard-coded caveat (it returns once as the trailing
        # note, behaviour 8), the warn line drops the inline "fix:" tail
        # (the fixes move to the report's "To fix" section, behaviour 7),
        # and the skipped line drops the "check could not run:" phrasing
        # (the brief is the finding's own word for it).
        render = piguard.render_finding

        # passed: the rule's API type on the line, and the finding's own
        # brief - the sample's clause - as the substance.
        passed = piguard.check_history_rewrite(
            [rule("non_fast_forward", "main-guard")]
        )[0]
        self.assertEqual(
            _field(passed, "status"),
            "passed",
            "fixture sanity: an active rule passes",
        )
        self.assertEqual(
            render(passed),
            "ok: {} - {}".format(
                _field(passed, "rule"), _field(passed, "brief")
            ),
        )
        self.assertNotIn(
            "bypass",
            render(passed).lower(),
            "the hard-coded caveat leaves the per-finding line; it is "
            "not a finding field",
        )

        # warn: the "warn: {label} - {brief}" composition, built from the
        # finding's own fields - no inline fix.
        warn = [
            f
            for f in piguard.check_history_rewrite(
                [rule("non_fast_forward", "main-guard")]
            )
            if _field(f, "status") == "warn"
        ][0]
        self.assertEqual(
            render(warn),
            "warn: {} - {}".format(
                _field(warn, "rule"), _field(warn, "brief")
            ),
        )

        # skipped: the "skipped: {check} - {brief}" composition - the
        # brief is the finding's own word for why the check did not run.
        skipped = piguard.skipped_findings(
            "GitHub was unreachable: connection refused"
        )[0]
        self.assertEqual(
            render(skipped),
            "skipped: {} - {}".format(
                _field(skipped, "check"), _field(skipped, "brief")
            ),
        )

    def test_genuinely_unknown_status_still_falls_through_to_unknown_line(self):
        finding = {
            "status": "bogus",
            "check": "history_rewrite",
            "rule": "deletion",
            "danger": "",
            "source": None,
            "remedy": "",
        }

        line = piguard.render_finding(finding)

        self.assertEqual(
            line,
            "unknown: bogus finding for rule deletion",
            "a status that is not passed, warn, skipped or fail must "
            "still fall through to the 'unknown:' line - only 'fail' is "
            "given a real branch",
        )
        self.assertTrue(
            line.startswith("unknown:"),
            "the fallthrough for truly-unknown statuses must be "
            "preserved: {!r}".format(line),
        )


class RenderFindingWarnTokenTests(unittest.TestCase):
    """Behaviour 17 plus behaviour 3 of plans/guard-finding-compact.md.

    The token-scope probes (behaviours 2, 3 and 6 of
    plans/verify-guards-token.md) emit ``warn`` findings carrying
    ``rule=None`` and a ``check`` name. A ``warn`` finding renders a line
    that names what is being warned about - for a token finding
    (``rule=None``) that is the ``check`` name, never a literal ``None``.

    The one vocabulary (behaviour 3 of
    plans/guard-finding-compact.md): the warn line is
    ``warn: {label} - {brief}`` - the label the rule (non-None) or the
    check (token findings), the substance the finding's own short
    ``brief``. The old ``; fix: {remedy}`` tail is re-pointed: the fixes
    move to the report's "To fix" section (behaviour 7), so the per-
    finding line no longer carries the remedy.
    """

    def _assert_token_warn_line(self, finding: Dict[str, Any], line: str) -> None:
        self.assertIsInstance(line, str)
        self.assertTrue(
            line,
            "a warn finding must render a non-empty line",
        )
        self.assertTrue(
            line.startswith("warn:"),
            "a warn finding must render a line marked with a 'warn:' "
            "prefix, consistent with the ok:/warn:/skipped:/fail: prefix "
            "convention the other branches use: {!r}".format(line),
        )
        self.assertNotIn(
            "None",
            line,
            "a token warn finding carries rule=None, and the line must "
            "name the check, not a literal 'None' - the 'warn: None - ...' "
            "rendering is the defect: {!r}".format(line),
        )
        self.assertTrue(
            line.startswith("warn: {} - ".format(_field(finding, "check"))),
            "the warn line must name the check first, mirroring the "
            "fail branch's 'fail: {{check}} - ...' shape: {!r}".format(line),
        )
        self.assertIn(
            _field(finding, "brief"),
            line,
            "the rendered warn line must carry the finding's own brief - "
            "every word from the finding's fields: {!r}".format(line),
        )
        self.assertLessEqual(
            len(line),
            160,
            "the rendered line must be at most 160 characters, got {}: "
            "{!r}".format(len(line), line),
        )

    def test_probe_warn_findings_with_rule_none_render_check_not_literal_none(self):
        # The real warn findings behaviours 2, 3 and 6 emit: all carry
        # rule=None, so the warn line must not depend on rule being
        # non-None.
        target_url = "https://api.github.com/repos/owner/repo"
        admin_url = (
            "https://api.github.com/repos/owner/repo/actions/permissions"
        )
        for label, finding in (
            (
                "target_access (behaviour 2, 404)",
                piguard.probe_target_access(
                    "owner",
                    "repo",
                    token="token-xyz",
                    opener=_opener(
                        urllib.error.HTTPError(
                            target_url, 404, "Not Found", None, None
                        )
                    ),
                )[0],
            ),
            (
                "administration (behaviour 3, 404)",
                piguard.probe_administration(
                    "owner",
                    "repo",
                    token="token-xyz",
                    opener=_opener(
                        urllib.error.HTTPError(
                            admin_url, 404, "Not Found", None, None
                        )
                    ),
                )[0],
            ),
            (
                "named_repo (behaviour 6, 200)",
                piguard.probe_named_repo(
                    "owner/other",
                    token="token-xyz",
                    opener=_opener(
                        _FakeResponse(b'{"full_name": "owner/other"}', 200)
                    ),
                )[0],
            ),
        ):
            with self.subTest(probe=label):
                self.assertEqual(
                    _field(finding, "status"),
                    "warn",
                    "fixture sanity: the probe emits a warn finding",
                )
                self.assertIsNone(
                    _field(finding, "rule"),
                    "fixture sanity: a token finding carries rule=None",
                )

                line = piguard.render_finding(finding)

                self._assert_token_warn_line(finding, line)

    def test_minimal_token_warn_finding_renders_check_not_literal_none(self):
        # Only the fields a token warn finding carries - no reason, no
        # source - so the assertion isolates the warn branch from the
        # probes.
        finding = {
            "status": "warn",
            "check": "administration",
            "rule": None,
            "brief": "cannot tell whether administration is withheld",
            "danger": "d",
            "remedy": "r",
        }

        line = piguard.render_finding(finding)

        self._assert_token_warn_line(finding, line)

    def test_rule_based_warn_finding_renders_the_one_vocabulary(self):
        # The rule-based warns (check_history_rewrite, check_review, ...)
        # carry a non-None rule and render the one vocabulary
        # (behaviour 3 of plans/guard-finding-compact.md):
        # "warn: {rule} - {brief}" - the label the rule, the substance the
        # finding's own brief. Re-pointed from the old "warn: {rule} -
        # {danger}; fix: {remedy}" pin: the fix moves to the report's
        # "To fix" section (behaviour 7), so the per-finding line no
        # longer carries the remedy.
        warn = [
            f
            for f in piguard.check_history_rewrite(
                [rule("non_fast_forward", "main-guard")]
            )
            if _field(f, "status") == "warn"
        ][0]
        self.assertEqual(
            _field(warn, "status"),
            "warn",
            "fixture sanity: an absent rule warns",
        )
        self.assertIsNotNone(
            _field(warn, "rule"),
            "fixture sanity: a rule-based warn carries a non-None rule",
        )

        self.assertEqual(
            piguard.render_finding(warn),
            "warn: {} - {}".format(
                _field(warn, "rule"),
                _field(warn, "brief"),
            ),
        )


class RenderFindingBlockTests(unittest.TestCase):
    """Behaviour 19 of plans/verify-guards-token.md: ``render_finding_block``.

    The new human-facing renderer for ONE finding. ``render_finding_block(
    finding, width=80)`` returns a small block of lines:

    - a headline line - a status prefix consistent with the existing
      ``ok:``/``warn:``/``fail:``/``skipped:`` convention, then a label: the
      ``rule`` when the finding carries one, otherwise the ``check`` name,
      never a literal ``None``;
    - for passed, ONE line (behaviour 4 of
      plans/guard-finding-compact.md): the marked headline carrying the
      finding's brief after an em dash - no detail line, no ``see:``
      line, no bypass caveat;
    - for warn/fail, ONE line (behaviour 5 of
      plans/guard-finding-compact.md): the marked headline carrying the
      finding's brief - the danger words - after an em dash; a long brief
      wraps within ``width`` with no elision, and there is no detail line
      and no ``fix:`` line, which now lives in the report's "To fix"
      section (behaviour 7);
    - for skipped, a headline plus one ``how:`` line (behaviour 6 of
      plans/guard-finding-compact.md): the marked headline carrying the
      finding's brief after an em dash, followed by one indented
      ``  how: {remedy}`` line saying how the check can be run - no
      detail line (the old ``_block_substance`` detail drops), no
      ``fix:`` line; a missing ``brief`` falls back to the ``reason``, a
      missing ``remedy`` emits no ``how:`` line, and a long brief or
      remedy wraps within ``width`` with no elision.

    The existing single-line ``render_finding`` is untouched; its
    byte-for-byte pins (behaviours 9/17) keep passing, and this class pins
    only the new block's substance and shape - never the wrap points.
    """

    def _block(self, finding, width=80):
        """Render ONE finding as a block, asserting its outer shape.

        Fails at the callability seam when ``render_finding_block`` does not
        exist yet - the RED reason for this whole class.
        """
        renderer = getattr(piguard, "render_finding_block", None)
        self.assertTrue(
            callable(renderer),
            "anvilkit.pi.piguard.render_finding_block is not callable; the "
            "behaviour-19 block renderer has not been implemented yet",
        )
        block = renderer(finding, width=width)
        self.assertIsInstance(
            block, list, "render_finding_block must return a list of lines"
        )
        self.assertGreaterEqual(
            len(block), 2, "a finding block has a headline plus detail lines"
        )
        for line in block:
            self.assertIsInstance(line, str)
            self.assertLessEqual(
                len(line),
                width,
                "a block line exceeds the requested width {!r}: {!r}".format(
                    width, line
                ),
            )
        return block

    @staticmethod
    def _compact(text):
        """The text with every whitespace character removed.

        A wrap may only change whitespace (line breaks, indentation), so
        word-for-word survival of a substance is checkable by comparing
        the whitespace-free forms - without pinning the wrap points.
        """
        return "".join(text.split())

    def _passed_block(self, finding, width=80):
        """Render a passed finding as a block and pin its one-line shape.

        Behaviour 4 of plans/guard-finding-compact.md: a passed block is
        exactly one line - the marked headline with the finding's own
        brief after an em dash. No detail line, no ``see:`` line, no
        bypass caveat: the remedy no longer prints per finding. The
        shared shape pins live here so each passed test pins content,
        not shape.
        """
        renderer = getattr(piguard, "render_finding_block", None)
        self.assertTrue(
            callable(renderer),
            "anvilkit.pi.piguard.render_finding_block is not callable; the "
            "behaviour-19 block renderer has not been implemented yet",
        )
        block = renderer(finding, width=width)
        self.assertIsInstance(
            block, list, "render_finding_block must return a list of lines"
        )
        for line in block:
            self.assertIsInstance(line, str)
            self.assertLessEqual(
                len(line),
                width,
                "a block line exceeds the requested width {!r}: {!r}".format(
                    width, line
                ),
            )
        self.assertEqual(
            len(block),
            1,
            "a passed block is ONE line - the marked headline with the "
            "brief after an em dash:\nblock: {!r}".format(block),
        )
        label = _field(finding, "rule") or _field(finding, "check")
        expected = "✅ ok: {} — {}".format(label, _field(finding, "brief"))
        self.assertEqual(
            block[0],
            expected,
            "the passed line must be exactly the marked headline with the "
            "em-dash brief: expected {!r}, got {!r}".format(expected, block[0]),
        )
        text = "\n".join(block)
        self.assertNotIn(
            "see:",
            text,
            "a passed block carries no 'see:' line - the remedy no longer "
            "prints per finding:\nblock: {!r}".format(block),
        )
        self.assertNotIn(
            "bypass",
            text,
            "a passed block carries no bypass caveat - it is printed once "
            "as the trailing note:\nblock: {!r}".format(block),
        )
        return block

    def _warn_fail_block(self, finding, width=80):
        """Render a warn or fail finding as a block and pin its one-line shape.

        Behaviour 5 of plans/guard-finding-compact.md: a warn or fail
        block is the marked headline carrying the finding's own brief
        after an em dash - ``"{mark} warn: {label} — {brief}"`` for a
        warn, ``"{mark} fail: {label} — {brief}"`` for a fail - exactly
        like the passed line (behaviour 4); the warn/fail brief just
        happens to be the danger words (the cycle-1/2 pins established
        brief == the danger clause). No detail line and no ``fix:`` line:
        the remedy no longer prints per finding - it moves to the
        report's "To fix" section (behaviour 7). A long brief wraps to
        more lines, every one within ``width``, with no elision. The
        shared shape pins live here so each warn/fail test pins content,
        not shape.
        """
        renderer = getattr(piguard, "render_finding_block", None)
        self.assertTrue(
            callable(renderer),
            "anvilkit.pi.piguard.render_finding_block is not callable; the "
            "behaviour-19 block renderer has not been implemented yet",
        )
        status = _field(finding, "status")
        self.assertIn(
            status,
            ("warn", "fail"),
            "this helper pins only warn and fail blocks, got status "
            "{!r}".format(status),
        )
        block = renderer(finding, width=width)
        self.assertIsInstance(
            block, list, "render_finding_block must return a list of lines"
        )
        for line in block:
            self.assertIsInstance(line, str)
            self.assertLessEqual(
                len(line),
                width,
                "a block line exceeds the requested width {!r}: {!r}".format(
                    width, line
                ),
            )
        prefix = "⚠️ warn" if status == "warn" else "❌ fail"
        label = _field(finding, "rule") or _field(finding, "check")
        headline = "{}: {} — {}".format(prefix, label, _field(finding, "brief"))
        self.assertNotIn(
            "fix:",
            "\n".join(block),
            "a warn/fail block carries no 'fix:' line - the remedy moves "
            "to the report's 'To fix' section (behaviour 7 of "
            "plans/guard-finding-compact.md):\nblock: {!r}".format(block),
        )
        self.assertEqual(
            self._compact("\n".join(block)),
            self._compact(headline),
            "the warn/fail block is the marked em-dash headline, wrapped - "
            "nothing added (no detail line), nothing elided:\n"
            "expected text: {!r}\nblock: {!r}".format(headline, block),
        )
        self.assertTrue(
            block[0].startswith(
                "{}: {}".format(prefix, label)
            ),
            "the block's first line must be the marked headline: "
            "{!r}".format(block[0]),
        )
        return block

    def _skipped_block(self, finding, width=80):
        """Render a skipped finding as a block and pin its two-line shape.

        Behaviour 6 of plans/guard-finding-compact.md: a skipped block is
        the marked em-dash headline plus one indented ``how:`` line -
        ``["{mark} skipped: {label} — {brief}", "  how: {remedy}"]`` -
        exactly two lines, one if the remedy is missing. The headline
        carries the finding's brief after an em dash, like the
        passed/warn/fail lines (behaviours 4-5); the ``how:`` line says
        how the check can be run - the user's "quickly tell how they can
        be checked". A missing ``brief`` falls back to the ``reason``; a
        missing ``remedy`` emits no ``how:`` line rather than an empty
        one. There is no detail line (the old ``_block_substance``
        detail drops) and no ``fix:`` line (the prefix word changes for
        skipped only - ``how:`` is the fixed furniture, behaviour 12).
        A long brief or remedy wraps within ``width`` with no elision.
        The shared shape pins live here so each skipped test pins
        content, not shape.
        """
        renderer = getattr(piguard, "render_finding_block", None)
        self.assertTrue(
            callable(renderer),
            "anvilkit.pi.piguard.render_finding_block is not callable; the "
            "behaviour-19 block renderer has not been implemented yet",
        )
        block = renderer(finding, width=width)
        self.assertIsInstance(
            block, list, "render_finding_block must return a list of lines"
        )
        for line in block:
            self.assertIsInstance(line, str)
            self.assertLessEqual(
                len(line),
                width,
                "a block line exceeds the requested width {!r}: {!r}".format(
                    width, line
                ),
            )
        label = _field(finding, "rule") or _field(finding, "check")
        brief = _field(finding, "brief")
        headline_text = _field(finding, "reason")
        if isinstance(brief, str) and brief:
            headline_text = brief
        headline = "⏭️ skipped: {} — {}".format(label, headline_text)
        self.assertTrue(
            block[0].startswith("⏭️ skipped: {}".format(label)),
            "the block's first line must be the marked skipped headline: "
            "{!r}".format(block[0]),
        )
        self.assertNotIn(
            "fix:",
            "\n".join(block),
            "a skipped block carries no 'fix:' line - the remedy rides on "
            "the indented 'how:' line instead (behaviour 6 of "
            "plans/guard-finding-compact.md):\nblock: {!r}".format(block),
        )
        expected = self._compact(headline)
        remedy = _field(finding, "remedy")
        if isinstance(remedy, str) and remedy:
            expected += self._compact("  how: " + remedy)
        self.assertEqual(
            self._compact("\n".join(block)),
            expected,
            "the skipped block is the em-dash headline plus the one "
            "'how:' line - nothing added (no detail line), nothing "
            "elided:\nexpected text: {!r}\nblock: {!r}".format(headline, block),
        )
        return block

    # ------------------------------------------------------------------
    # Behaviour 4 of plans/guard-finding-compact.md: a passed block is
    # ONE line - "{mark} ok: {label} — {brief}".
    # ------------------------------------------------------------------

    def test_passed_branch_finding_block_is_one_em_dash_line(self):
        # The real check_all producer: a non_fast_forward rule present in
        # the rules array yields a passed branch finding (rule set). The
        # block is exactly one line - the marked headline with the
        # finding's own brief after an em dash.
        finding = piguard.check_all([rule("non_fast_forward", "main-guard")])[0]
        self.assertEqual(
            "passed", _field(finding, "status"), "fixture sanity"
        )
        self.assertEqual(
            "non_fast_forward", _field(finding, "rule"), "fixture sanity"
        )

        block = self._passed_block(finding)
        self.assertEqual(
            block,
            ["✅ ok: non_fast_forward — {}".format(_field(finding, "brief"))],
            "a passed branch block is exactly the marked headline with "
            "the em-dash brief:\nblock: {!r}".format(block),
        )

    def test_passed_pull_request_block_carries_recorded_count_in_the_line(self):
        # The recorded-value pass: the required-approvals count lives in
        # the finding's own brief, on the one line - sample words, from
        # the real check_review producer.
        finding = piguard.check_review(
            [pull_request_rule("main-guard", 2)]
        )[0]
        self.assertEqual(
            "passed", _field(finding, "status"), "fixture sanity"
        )
        self.assertEqual(
            2,
            _field(finding, "required_approving_review_count"),
            "fixture sanity: the recorded count must be 2",
        )

        block = self._passed_block(finding)
        self.assertEqual(
            block,
            [
                "✅ ok: pull_request — review required "
                "(2 required approvals)"
            ],
            "the passed pull_request block is one line carrying the "
            "recorded count from the brief:\nblock: {!r}".format(block),
        )

    def test_passed_update_block_carries_recorded_value_in_the_line(self):
        # The recorded-value pass: update_allows_fetch_and_merge=False
        # lives in the finding's own brief, on the one line - from the
        # real check_update producer.
        finding = piguard.check_update(
            [
                update_rule(
                    "main-guard", {"update_allows_fetch_and_merge": False}
                )
            ]
        )[0]
        self.assertEqual(
            "passed", _field(finding, "status"), "fixture sanity"
        )
        self.assertEqual(
            False,
            _field(finding, "update_allows_fetch_and_merge"),
            "fixture sanity: the recorded value must be False",
        )

        block = self._passed_block(finding)
        self.assertEqual(
            block,
            [
                "✅ ok: update — direct pushes restricted "
                "(fetch and merge: False)"
            ],
            "the passed update block is one line carrying the recorded "
            "value from the brief:\nblock: {!r}".format(block),
        )

    def test_passed_file_path_block_carries_recorded_path_in_the_line(self):
        # The recorded-value pass: the restricted paths live in the
        # finding's own brief, on the one line - from the real
        # check_file_paths producer.
        finding = piguard.check_file_paths(
            [
                file_path_rule(
                    "main-guard",
                    {"restricted_file_paths": [".github/workflows/**"]},
                )
            ]
        )[0]
        self.assertEqual(
            "passed", _field(finding, "status"), "fixture sanity"
        )
        self.assertEqual(
            [".github/workflows/**"],
            _field(finding, "restricted_file_paths"),
            "fixture sanity: the recorded path must be recorded",
        )

        block = self._passed_block(finding)
        self.assertEqual(
            block,
            [
                "✅ ok: file_path_restriction — listed paths "
                "protected (.github/workflows/**)"
            ],
            "the passed file_path_restriction block is one line carrying "
            "the recorded path from the brief:\nblock: {!r}".format(block),
        )

    def test_passed_file_path_block_wraps_long_brief_with_no_elision(self):
        # The many-restricted-paths case: headline + brief exceeds 80, so
        # the block wraps to more than one line - every line within
        # width, with no elision (the wrapped text is the headline and
        # nothing else), and line 0 is the marked headline.
        long_paths = [
            ".github/workflows/nightly-integration-suite.yml",
            "infrastructure/terraform/modules/production-network/**",
            "deployment/k8s/base/production-cluster-manifests/**",
        ]
        finding = piguard.check_file_paths(
            [
                file_path_rule(
                    "main-guard",
                    {"restricted_file_paths": long_paths},
                )
            ]
        )[0]
        brief = _field(finding, "brief")
        headline = "✅ ok: file_path_restriction — {}".format(brief)
        self.assertGreater(
            len(headline),
            80,
            "fixture sanity: the headline plus the brief must exceed 80 "
            "to force a wrap: {!r}".format(headline),
        )

        block = piguard.render_finding_block(finding, width=80)
        self.assertIsInstance(
            block, list, "render_finding_block must return a list of lines"
        )
        self.assertGreater(
            len(block),
            1,
            "an over-width passed block must wrap to more than one "
            "line:\nblock: {!r}".format(block),
        )
        for line in block:
            self.assertLessEqual(
                len(line),
                80,
                "a wrapped passed line exceeds width 80: {!r}".format(line),
            )
        self.assertTrue(
            block[0].startswith("✅ ok: file_path_restriction"),
            "line 0 must be the marked headline: {!r}".format(block[0]),
        )
        # No elision and no extra content: with every whitespace
        # character removed, the block IS the one-line headline.
        self.assertEqual(
            self._compact("\n".join(block)),
            self._compact(headline),
            "the wrapped passed block must carry the headline - brief "
            "included - with nothing added and nothing elided:\n"
            "expected text: {!r}\nblock: {!r}".format(headline, block),
        )
        for path in long_paths:
            self.assertIn(
                path,
                "".join("".join(block).split()),
                "a recorded path was elided by the wrap: {!r}".format(path),
            )

    # ------------------------------------------------------------------
    # Behaviour 5 of plans/guard-finding-compact.md: a warn or fail block
    # is ONE line - "{mark} warn|fail: {label} — {brief}"; the warn/fail
    # brief is the danger words (the cycle-1/2 pins established brief ==
    # the danger clause). No detail line, no ``fix:`` line - the remedy
    # moves to the report's "To fix" section (behaviour 7).
    # ------------------------------------------------------------------

    def test_fail_finding_block_is_one_em_dash_line(self):
        # The real behaviour-3 finding: a 200 on the actions-permissions
        # endpoint is the first emittable fail, and it carries rule=None, so
        # the headline must name the check, never the rule. (Re-pointed
        # from the detail + "fix:" pins: the block is the marked em-dash
        # headline only - the brief, which is the danger words for a fail
        # finding, after the em dash.)
        findings = piguard.probe_administration(
            "owner",
            "repo",
            "ghp_blocktest",
            opener=_opener(
                _FakeResponse(b'{"enabled": true, "allowed_actions": "selected"}', 200)
            ),
            timeout=10.0,
        )
        finding = [
            f for f in findings if _field(f, "status") == "fail"
        ][0]
        self.assertIsNone(
            _field(finding, "rule"),
            "fixture sanity: the administration fail carries rule=None",
        )

        block = self._warn_fail_block(finding)
        self.assertEqual(
            block,
            [
                "❌ fail: {} — {}".format(
                    piguard.CHECK_ADMINISTRATION, _field(finding, "brief")
                )
            ],
            "the fail block is exactly the marked em-dash headline - the "
            "brief is the danger words for a fail finding:\n"
            "block: {!r}".format(block),
        )
        self.assertIn(
            piguard.CHECK_ADMINISTRATION,
            block[0],
            "the fail headline must name the check: {!r}".format(block[0]),
        )
        self.assertNotIn(
            "None",
            block[0],
            "the fail headline must never print a literal 'None': "
            "{!r}".format(block[0]),
        )
        self.assertNotIn(
            "doc/external/",
            self._compact("\n".join(block)),
            "the fail block must carry no doc path (behaviour 2 of "
            "plans/guard-finding-compact.md):\nblock: {!r}".format(block),
        )

    def test_warn_finding_block_is_one_em_dash_line(self):
        # The real behaviour-6 warn: a 200 on the named other repo means
        # the token reaches more than the target - rule=None, so the
        # headline keys on the check. (Re-pointed from the detail +
        # "fix:" pins: the block is the marked em-dash headline only -
        # the brief, which is the danger words for a warn finding, after
        # the em dash. This fixture's headline exceeds 80, so the block
        # wraps - the substance is pinned word-for-word, not the wrap
        # points.)
        findings = piguard.probe_named_repo(
            "someorg/other-repo",
            "ghp_blocktest",
            opener=_opener(
                _FakeResponse(b'{"full_name": "someorg/other-repo"}', 200)
            ),
            timeout=10.0,
        )
        finding = [
            f for f in findings if _field(f, "status") == "warn"
        ][0]
        self.assertIsNone(
            _field(finding, "rule"),
            "fixture sanity: the named_repo warn carries rule=None",
        )

        block = self._warn_fail_block(finding)
        self.assertIn(
            piguard.CHECK_NAMED_REPO,
            block[0],
            "the warn headline must name the check: {!r}".format(block[0]),
        )
        self.assertNotIn(
            "None",
            "".join(block),
            "the warn block must never print a literal 'None': "
            "block: {!r}".format(block),
        )
        self.assertIn(
            self._compact(_field(finding, "brief")),
            self._compact("\n".join(block)),
            "the warn block must carry the finding's own brief (the "
            "danger words) word-for-word:\nblock: {!r}".format(block),
        )
        self.assertNotIn(
            "doc/external/",
            self._compact("\n".join(block)),
            "the warn block must carry no doc path (behaviour 2 of "
            "plans/guard-finding-compact.md):\nblock: {!r}".format(block),
        )

    def test_warn_branch_finding_block_is_one_em_dash_line(self):
        # The real check_all producer: a rules array with deletion active
        # and non_fast_forward absent yields a warn branch finding (rule
        # set) - the approved sample report's first line. The block is
        # exactly one line - the marked headline with the finding's own
        # brief (the danger words) after an em dash; no detail line, no
        # "fix:" anywhere.
        findings = piguard.check_all([rule("deletion", "main-guard")])
        warn = [
            f
            for f in findings
            if _field(f, "status") == "warn"
            and _field(f, "rule") == "non_fast_forward"
        ][0]
        self.assertEqual(
            "history can be rewritten or erased by a force push",
            _field(warn, "brief"),
            "fixture sanity: the recorded warn brief",
        )

        block = self._warn_fail_block(warn)
        self.assertEqual(
            block,
            ["⚠️ warn: non_fast_forward — {}".format(_field(warn, "brief"))],
            "a warn branch block is exactly the marked headline with the "
            "em-dash brief:\nblock: {!r}".format(block),
        )

    def test_fail_token_finding_block_is_one_em_dash_line(self):
        # The real token probe: a non-empty X-OAuth-Scopes header is the
        # second emittable fail, and it carries rule=None, so the headline
        # must name the check, never the rule.
        findings = piguard.probe_classic_token(
            "ghp_blocktest",
            opener=_opener(
                _FakeResponse(
                    b'{"login": "owner"}',
                    200,
                    headers={"X-OAuth-Scopes": "repo, user"},
                )
            ),
            timeout=10.0,
        )
        finding = [
            f for f in findings if _field(f, "status") == "fail"
        ][0]
        self.assertIsNone(
            _field(finding, "rule"),
            "fixture sanity: the classic_token fail carries rule=None",
        )

        block = self._warn_fail_block(finding)
        self.assertEqual(
            block,
            [
                "❌ fail: {} — {}".format(
                    piguard.CHECK_CLASSIC_TOKEN, _field(finding, "brief")
                )
            ],
            "the classic_token fail block is exactly the marked em-dash "
            "headline:\nblock: {!r}".format(block),
        )
        self.assertIn(
            piguard.CHECK_CLASSIC_TOKEN,
            block[0],
            "the fail headline must name the check: {!r}".format(block[0]),
        )
        self.assertNotIn(
            "None",
            block[0],
            "the fail headline must never print a literal 'None': "
            "{!r}".format(block[0]),
        )

    def test_warn_token_finding_block_names_check_and_never_prints_none(self):
        # Behaviour 5's error clause: a token warn finding (rule=None)
        # names its ``check`` - never a literal "None" - and is ONE line
        # with the brief (the danger words) after an em dash. The
        # recorded 404 is the warn case of the target-access probe.
        findings = piguard.probe_target_access(
            "owner",
            "repo",
            "ghp_blocktest",
            opener=_opener(
                urllib.error.HTTPError(
                    "https://api.github.com/repos/owner/repo",
                    404,
                    "Not Found",
                    None,
                    None,
                )
            ),
            timeout=10.0,
        )
        finding = [
            f for f in findings if _field(f, "status") == "warn"
        ][0]
        self.assertIsNone(
            _field(finding, "rule"),
            "fixture sanity: a token warn finding carries rule=None",
        )

        block = self._warn_fail_block(finding)
        self.assertEqual(
            block,
            [
                "⚠️ warn: {} — {}".format(
                    piguard.CHECK_TARGET_ACCESS, _field(finding, "brief")
                )
            ],
            "a token warn block is one line naming the check with the "
            "brief after an em dash:\nblock: {!r}".format(block),
        )
        self.assertIn(
            piguard.CHECK_TARGET_ACCESS,
            block[0],
            "the warn headline must name the check: {!r}".format(block[0]),
        )
        self.assertNotIn(
            "None",
            block[0],
            "the warn headline must never print a literal 'None': "
            "{!r}".format(block[0]),
        )

    def test_warn_finding_block_wraps_long_brief_with_no_elision(self):
        # Behaviour 5's error clause: a warn finding whose brief is long
        # enough for the headline to exceed 80 wraps to more than one
        # line - every line within the width, with no elision (the
        # wrapped text is the headline and nothing else), and line 0 is
        # the marked headline. The fixture is a recorded 404 on a target
        # repo whose name is long enough to push the brief past the
        # width.
        long_repo = "an-extremely-long-repository-name-for-the-wrap-case"
        findings = piguard.probe_target_access(
            "someorg",
            long_repo,
            "ghp_blocktest",
            opener=_opener(
                urllib.error.HTTPError(
                    "https://api.github.com/repos/someorg/" + long_repo,
                    404,
                    "Not Found",
                    None,
                    None,
                )
            ),
            timeout=10.0,
        )
        finding = [
            f for f in findings if _field(f, "status") == "warn"
        ][0]
        brief = _field(finding, "brief")
        headline = "⚠️ warn: target_access — {}".format(brief)
        self.assertGreater(
            len(headline),
            80,
            "fixture sanity: the headline plus the brief must exceed 80 "
            "to force a wrap: {!r}".format(headline),
        )

        block = piguard.render_finding_block(finding, width=80)
        self.assertIsInstance(
            block, list, "render_finding_block must return a list of lines"
        )
        self.assertGreater(
            len(block),
            1,
            "an over-width warn block must wrap to more than one "
            "line:\nblock: {!r}".format(block),
        )
        for line in block:
            self.assertLessEqual(
                len(line),
                80,
                "a wrapped warn line exceeds width 80: {!r}".format(line),
            )
        self.assertTrue(
            block[0].startswith("⚠️ warn: target_access"),
            "line 0 must be the marked headline: {!r}".format(block[0]),
        )
        # No elision and no extra content: with every whitespace
        # character removed, the block IS the one-line headline.
        self.assertEqual(
            self._compact("\n".join(block)),
            self._compact(headline),
            "the wrapped warn block must carry the headline - brief "
            "included - with nothing added and nothing elided:\n"
            "expected text: {!r}\nblock: {!r}".format(headline, block),
        )
        self.assertNotIn(
            "fix:",
            "\n".join(block),
            "a wrapped warn block carries no 'fix:' line:\n"
            "block: {!r}".format(block),
        )

    # ------------------------------------------------------------------
    # Behaviour 6 of plans/guard-finding-compact.md: a skipped block is
    # a headline plus one how line -
    # ["{mark} skipped: {label} — {brief}", "  how: {remedy}"].
    # ------------------------------------------------------------------

    def test_workflows_withheld_skipped_block_is_headline_plus_how_line(self):
        # The constant workflows_withheld skip: the approved sample report's
        # exact words - the em-dash brief on the headline, the remedy on
        # the one indented "how:" line. (Re-pointed from the detail +
        # "fix:" pins of the old block shape: the detail line drops, the
        # "fix:" line becomes the "how:" line, the headline gains the
        # em-dash brief.)
        finding = piguard.workflows_withheld_finding()[0]
        self.assertEqual(
            "skipped", _field(finding, "status"), "fixture sanity"
        )
        self.assertEqual(
            "workflows_withheld", _field(finding, "check"), "fixture sanity"
        )

        block = self._skipped_block(finding)
        self.assertEqual(
            block,
            [
                "⏭️ skipped: workflows_withheld — no read-only call can prove this",
                "  how: in GitHub settings, check the token has no Workflows permission",
            ],
            "the skipped workflows_withheld block is exactly the marked "
            "em-dash headline plus the one indented 'how:' line with the "
            "sample's exact words:\nblock: {!r}".format(block),
        )

    def test_skipped_block_is_headline_plus_one_how_line(self):
        # The skipped_findings producer over the recorded 404 fetch
        # reason: every skipped finding is the marked em-dash headline
        # (the short brief after the em dash) plus one indented "how:"
        # line carrying the "then re-run" remedy - no "fix:" anywhere,
        # no detail line.
        url = "https://api.github.com/repos/owner/repo/rules/branches/main"
        rules, reason = piguard.fetch_branch_rules(
            "owner",
            "repo",
            "main",
            opener=_opener(
                urllib.error.HTTPError(url, 404, "Not Found", None, None)
            ),
        )
        self.assertIsNone(rules, "fixture sanity: the 404 records a reason")
        self.assertTrue(
            reason, "fixture sanity: the fetch failure records a reason"
        )
        findings = piguard.skipped_findings(reason)
        self.assertEqual(
            4, len(findings), "fixture sanity: one skipped finding per check"
        )
        for finding in findings:
            with self.subTest(check=_field(finding, "check")):
                self.assertEqual(
                    "skipped", _field(finding, "status"), "fixture sanity"
                )
                brief = _field(finding, "brief")
                remedy = _field(finding, "remedy")
                label = _field(finding, "check")
                block = self._skipped_block(finding)
                self.assertEqual(
                    block,
                    [
                        "⏭️ skipped: {} — {}".format(label, brief),
                        "  how: {}".format(remedy),
                    ],
                    "a skipped finding is exactly the marked em-dash "
                    "headline plus one indented 'how:' line with the "
                    "remedy:\nblock: {!r}".format(block),
                )
                self.assertNotIn(
                    "fix:",
                    "\n".join(block),
                    "the skipped block carries no 'fix:' line:\n"
                    "block: {!r}".format(block),
                )
                self.assertNotIn(
                    "doc/external/",
                    self._compact("\n".join(block)),
                    "the skipped block must carry no doc path (behaviour "
                    "2 of plans/guard-finding-compact.md):\n"
                    "block: {!r}".format(block),
                )

    def test_skipped_no_origin_block_headline_carries_brief_not_long_reason(self):
        # The no-origin skip: the long CLI-owned reason (pinned verbatim
        # in tests/test_cli.py for the noun invariant) is never printed
        # in the block - the headline carries the short brief "no GitHub
        # origin remote", and the "how:" line carries the remedy.
        reason = (
            "owner/repo could not be resolved from the origin remote of "
            "/tmp/target: the target has no origin, or its remote is not "
            "a GitHub repository, and the identity is never guessed"
        )
        findings = piguard.skipped_findings(reason)
        self.assertEqual(
            4, len(findings), "fixture sanity: one skipped finding per check"
        )
        for finding in findings:
            with self.subTest(check=_field(finding, "check")):
                self.assertEqual(
                    "no GitHub origin remote",
                    _field(finding, "brief"),
                    "fixture sanity: the no-origin skip brief is the "
                    "sample's clause",
                )
                block = self._skipped_block(finding)
                self.assertEqual(
                    len(block),
                    2,
                    "the skipped no-origin block is the headline plus "
                    "the one 'how:' line:\nblock: {!r}".format(block),
                )
                self.assertTrue(
                    block[0].endswith(
                        " — no GitHub origin remote"
                    ),
                    "the no-origin headline carries the brief after the "
                    "em dash:\nblock: {!r}".format(block),
                )
                long_reason_in_block = self._compact(reason)
                self.assertNotIn(
                    long_reason_in_block,
                    self._compact("\n".join(block)),
                    "the long CLI-owned no-origin reason must not be "
                    "printed in the block - the headline carries the "
                    "brief:\nreason: {!r}\nblock: {!r}".format(reason, block),
                )
                self.assertEqual(
                    block[1],
                    "  how: run this in a clone whose origin is a GitHub repo",
                    "the 'how:' line carries the no-origin remedy:\n"
                    "block: {!r}".format(block),
                )

    def test_skipped_block_missing_brief_falls_back_to_reason(self):
        # Behaviour 6's error clause: a skipped finding with no brief
        # renders the reason after the em dash - no "None", no crash.
        finding = {
            "status": "skipped",
            "check": "history_rewrite",
            "rule": None,
            "reason": "the branch rules could not be fetched",
            "remedy": "re-run once the branch rules can be fetched",
        }
        self.assertNotIn("brief", finding, "fixture sanity: no brief key")

        block = self._skipped_block(finding)
        self.assertEqual(
            block,
            [
                "⏭️ skipped: history_rewrite — "
                "the branch rules could not be fetched",
                "  how: re-run once the branch rules can be fetched",
            ],
            "a skipped finding with no brief falls back to the reason "
            "after the em dash - no 'None', no crash:\n"
            "block: {!r}".format(block),
        )
        self.assertNotIn(
            "None",
            "\n".join(block),
            "the block must never print a literal 'None': "
            "block: {!r}".format(block),
        )

    def test_skipped_block_missing_remedy_emits_no_how_line(self):
        # Behaviour 6's error clause: a skipped finding with no remedy
        # (or an empty one) is exactly ONE line - the em-dash headline -
        # no "how:" line at all, let alone an empty one.
        for remedy in (None, ""):
            with self.subTest(remedy=remedy):
                finding = {
                    "status": "skipped",
                    "check": "history_rewrite",
                    "rule": None,
                    "brief": "api.github.com was unreachable",
                    "remedy": remedy,
                }
                block = self._skipped_block(finding)
                self.assertEqual(
                    block,
                    [
                        "⏭️ skipped: history_rewrite — "
                        "api.github.com was unreachable"
                    ],
                    "a skipped finding with no remedy is exactly one "
                    "line - the em-dash headline - no 'how:' line, no "
                    "empty 'how:' line:\nblock: {!r}".format(block),
                )
                self.assertNotIn(
                    "how:",
                    "\n".join(block),
                    "no 'how:' line of any kind when the remedy is "
                    "missing:\nblock: {!r}".format(block),
                )

    def test_skipped_block_wraps_long_brief_or_remedy_with_no_elision(self):
        # Behaviour 6's error clause: a skipped finding whose brief or
        # remedy is long enough for the block to exceed 80 wraps every
        # line within the width, with nothing elided - the block is the
        # wrapped headline plus the wrapped "how:" line and nothing
        # else, and line 0 is the marked headline.
        long_brief = (
            "the branch rules endpoint returned an answer that names a "
            "situation the user has to read to understand"
        )
        long_remedy = (
            "check the network access to api.github.com and the "
            "repository plan that gates the branch rules, then re-run "
            "this command once the fetch can succeed"
        )
        finding = {
            "status": "skipped",
            "check": "history_rewrite",
            "rule": None,
            "brief": long_brief,
            "reason": long_brief,
            "remedy": long_remedy,
        }

        block = piguard.render_finding_block(finding, width=80)
        self.assertIsInstance(
            block, list, "render_finding_block must return a list of lines"
        )
        self.assertGreater(
            len(block),
            2,
            "a skipped block with a long brief and remedy must wrap to "
            "more than two lines:\nblock: {!r}".format(block),
        )
        for line in block:
            self.assertLessEqual(
                len(line),
                80,
                "a wrapped skipped line exceeds width 80: {!r}".format(line),
            )
        self.assertTrue(
            block[0].startswith("⏭️ skipped: history_rewrite"),
            "line 0 must be the marked skipped headline: {!r}".format(block[0]),
        )
        # A long brief wraps the headline, so the 'how:' line is not
        # pinned to a fixed index - it is the only 'how:' line, and it
        # follows the wrapped headline directly (a long remedy can wrap
        # after it, so it is not necessarily the last line).
        how_lines = [
            line for line in block[1:] if line.lstrip().startswith("how:")
        ]
        self.assertEqual(
            1,
            len(how_lines),
            "the wrapped skipped block carries exactly one 'how:' line:\n"
            "block: {!r}".format(block),
        )
        how_index = block.index(how_lines[0])
        self.assertEqual(
            self._compact("\n".join(block[:how_index])),
            self._compact("⏭️ skipped: history_rewrite — {}".format(long_brief)),
            "the lines before the 'how:' line are exactly the wrapped "
            "headline - nothing else precedes it:\n"
            "block: {!r}".format(block),
        )
        # No elision and no extra content: with every whitespace
        # character removed, the block IS the headline plus the one
        # "how:" line.
        expected = self._compact(
            "⏭️ skipped: history_rewrite — {}".format(long_brief)
        ) + self._compact("  how: " + long_remedy)
        self.assertEqual(
            self._compact("\n".join(block)),
            expected,
            "the wrapped skipped block must carry the headline and the "
            "'how:' line - brief and remedy included - with nothing "
            "added and nothing elided:\nexpected text: {!r}\n"
            "block: {!r}".format(expected, block),
        )

    def test_branch_rule_passed_block_carries_brief_on_the_headline(self):
        # Behaviour 4 of plans/guard-finding-compact.md: a rule-based
        # passed finding (rule set) is ONE line - the rule name on the
        # marked headline, the recorded approval count inside the
        # finding's own brief, after an em dash. The bypass caveat (a
        # non-finding field) and the indented ``see:`` line both leave
        # the block. (Re-pointed from the caveat + detail + see: pins:
        # the substance now lives on line 0.)
        findings = piguard.check_review([pull_request_rule("main-guard", 1)])
        finding = findings[0]
        self.assertEqual(
            "passed", _field(finding, "status"), "fixture sanity"
        )
        self.assertEqual(
            "pull_request", _field(finding, "rule"), "fixture sanity"
        )
        self.assertEqual(
            1,
            _field(finding, "required_approving_review_count"),
            "fixture sanity: the recorded count must be 1",
        )

        block = self._passed_block(finding)
        self.assertEqual(
            block,
            [
                "✅ ok: pull_request — review required "
                "(1 required approvals)"
            ],
            "the passed block is one line: the marked headline with the "
            "brief (recorded count included) after an em dash:\n"
            "block: {!r}".format(block),
        )

    def test_token_passed_block_names_check_and_never_prints_none(self):
        # Behaviour 4 of plans/guard-finding-compact.md: a token passed
        # finding (rule=None) is ONE line naming its ``check`` - never a
        # literal "None" - with the brief after an em dash. (Re-pointed
        # from the headline + see: line pins: the block carries no
        # ``see:`` line and no detail any more; the check name and the
        # no-None invariant move onto the one line.)
        findings = piguard.probe_target_access(
            "owner",
            "repo",
            "ghp_blocktest",
            opener=_opener(_FakeResponse(b'{"full_name": "owner/repo"}', 200)),
            timeout=10.0,
        )
        finding = [
            f for f in findings if _field(f, "status") == "passed"
        ][0]
        self.assertIsNone(
            _field(finding, "rule"),
            "fixture sanity: a token passed finding carries rule=None",
        )

        block = self._passed_block(finding)
        self.assertEqual(
            block,
            [
                "✅ ok: {} — {}".format(
                    piguard.CHECK_TARGET_ACCESS, _field(finding, "brief")
                )
            ],
            "a token passed block is one line naming the check with the "
            "brief after an em dash:\nblock: {!r}".format(block),
        )

    def test_passed_finding_block_does_not_repeat_the_see_line(self):
        # Behaviour 4 of plans/guard-finding-compact.md: a passed block
        # is ONE line - the marked headline with the brief after an em
        # dash. There is no ``see:`` line any more and no detail to
        # restate one: the line carries the brief, and neither "see:"
        # nor a bypass caveat appears anywhere in the block.
        # (Re-pointed from the 6-word-phrase dedup pin over the old
        # detail + see: lines.)
        def passed_finding_fixture():
            # The same fixtures the other passed pins use.
            branch = piguard.check_review(
                [pull_request_rule("main-guard", 1)]
            )[0]
            token = [
                f
                for f in piguard.probe_target_access(
                    "owner",
                    "repo",
                    "ghp_blocktest",
                    opener=_opener(
                        _FakeResponse(b'{"full_name": "owner/repo"}', 200)
                    ),
                    timeout=10.0,
                )
                if _field(f, "status") == "passed"
            ][0]
            return [
                ("branch_rule", branch, _field(branch, "brief")),
                ("token", token, _field(token, "brief")),
            ]

        for name, finding, brief in passed_finding_fixture():
            self.assertEqual(
                "passed", _field(finding, "status"), "fixture sanity ({})".format(name)
            )
            block = self._passed_block(finding, width=80)
            text = "\n".join(block)
            self.assertIn(
                brief,
                text,
                "the one line must carry the finding's own brief: "
                "expected {!r} in the block:\nblock: {!r}".format(brief, block),
            )
            self.assertNotIn(
                "see:",
                text,
                "a passed block has no 'see:' line any more:\n"
                "block: {!r}".format(block),
            )

    def test_narrower_width_wraps_to_strictly_more_lines(self):
        # Width is a real parameter: the long skipped reason wraps to
        # strictly more lines at width 40 than at 80, and no line ever
        # exceeds the given width.
        finding = piguard.workflows_withheld_finding()[0]
        wide = self._block(finding, width=80)
        narrow = self._block(finding, width=40)
        for line in narrow:
            self.assertLessEqual(len(line), 40)
        for line in wide:
            self.assertLessEqual(len(line), 80)
        self.assertGreater(
            len(narrow),
            len(wide),
            "width=40 must wrap to strictly more lines than width=80 for "
            "a long finding:\nwidth=80 ({!r} lines): {!r}\nwidth=40 ({!r} "
            "lines): {!r}".format(len(wide), wide, len(narrow), narrow),
        )

    def test_same_finding_and_width_render_equal_blocks(self):
        # Deterministic: same finding, same width -> equal blocks, so the
        # report is diffable across runs.
        finding = piguard.workflows_withheld_finding()[0]
        self.assertEqual(self._block(finding), self._block(finding))


class FindingBlockHeadlineMarkTests(unittest.TestCase):
    """The status mark on a finding block's headline.

    Every guard finding block's headline gains a status mark prepended
    with one space, so doctor's Guards section and the other report sites
    read at a glance:

    - ``passed``  -> ``✅ ok: {label} — {brief}``
    - ``warn``    -> ``⚠️ warn: {label} — {brief}``
    - ``fail``    -> ``❌ fail: {label} — {brief}``
    - ``skipped`` -> ``⏭️ skipped: {label} — {brief}``
    - anything else -> unchanged: ``unknown: {label}`` (no mark)

    Since behaviours 4-6 of plans/guard-finding-compact.md, every marked
    headline carries the finding's brief after an em dash (for a skipped
    finding, a missing ``brief`` falls back to its ``reason``); the mark
    is part of the wrapped headline (the wrap budget includes it), and the
    passed/warn/fail blocks are one line while a skipped block is the
    headline plus one indented ``how:`` line.
    """

    # The four marks, pinned as literal strings - the set is exactly these.
    PASSED_MARK = "✅"
    WARN_MARK = "⚠️"
    FAIL_MARK = "❌"
    SKIPPED_MARK = "⏭️"

    @staticmethod
    def _finding(status, label, detail="the guard detail", remedy="fix the guard"):
        """One finding carrying ``status`` and a headline ``label`` (rule).

        The finding also carries the short ``brief`` the one-vocabulary
        line (behaviour 3 of plans/guard-finding-compact.md) renders as
        its substance; the old renderer ignores the key, so adding it
        leaves every existing pin unchanged.
        """
        return {
            "status": status,
            "check": "history_rewrite",
            "rule": label,
            "brief": detail,
            "danger": detail,
            "remedy": remedy,
        }

    def _first_line(self, finding, width=80):
        block = piguard.render_finding_block(finding, width=width)
        self.assertIsInstance(block, list)
        self.assertGreaterEqual(len(block), 1)
        return block[0]

    def test_passed_headline_starts_with_check_mark(self):
        # Behaviour 4 of plans/guard-finding-compact.md: the passed
        # headline carries the finding's brief after an em dash - line 0
        # is the whole block. (Re-pointed from the bare-mark + headline
        # pin: the em-dash brief is part of the headline now.)
        finding = self._finding("passed", "non_fast_forward")
        self.assertEqual(
            self._first_line(finding),
            "{} ok: non_fast_forward — the guard detail".format(
                self.PASSED_MARK
            ),
            "a passed headline must be the mark, one space, the plain "
            "headline and the em-dash brief: {!r}",
        )

    def test_warn_headline_starts_with_warning_mark(self):
        # Behaviour 5 of plans/guard-finding-compact.md: the warn headline
        # carries the finding's brief (the danger words) after an em dash
        # - line 0 is the marked em-dash form. (Re-pointed from the
        # un-briefed headline pin.)
        finding = self._finding("warn", "deletion")
        self.assertEqual(
            self._first_line(finding),
            "{} warn: deletion — the guard detail".format(self.WARN_MARK),
            "a warn headline must be the mark, one space, the plain "
            "headline and the em-dash brief: {!r}",
        )

    def test_fail_headline_starts_with_cross_mark(self):
        # Behaviour 5 of plans/guard-finding-compact.md: the fail headline
        # carries the finding's brief (the danger words) after an em dash
        # - line 0 is the marked em-dash form. (Re-pointed from the
        # un-briefed headline pin.)
        finding = self._finding("fail", "pull_request")
        self.assertEqual(
            self._first_line(finding),
            "{} fail: pull_request — the guard detail".format(self.FAIL_MARK),
            "a fail headline must be the mark, one space, the plain "
            "headline and the em-dash brief: {!r}",
        )

    def test_skipped_headline_starts_with_skipped_mark(self):
        # Behaviour 6 of plans/guard-finding-compact.md: the skipped
        # headline carries the finding's brief after an em dash, like
        # the other statuses - line 0 is the marked em-dash form.
        # (Re-pointed from the un-briefed headline pin.)
        finding = self._finding("skipped", "workflows_withheld")
        self.assertEqual(
            self._first_line(finding),
            "{} skipped: workflows_withheld — the guard detail".format(
                self.SKIPPED_MARK
            ),
            "a skipped headline must be the mark, one space, the plain "
            "headline and the em-dash brief: {!r}",
        )

    def test_unknown_status_headline_carries_no_mark(self):
        finding = self._finding("mystery", "non_fast_forward")
        line = self._first_line(finding)
        self.assertEqual(
            line,
            "unknown: non_fast_forward",
            "an unknown-status headline is unchanged - no mark: {!r}",
        )
        for mark in (
            self.PASSED_MARK,
            self.WARN_MARK,
            self.FAIL_MARK,
            self.SKIPPED_MARK,
        ):
            self.assertNotIn(mark, line)

    def test_mark_participates_in_the_wrap_at_narrow_width(self):
        # A long label at a narrow width: the mark is part of the wrapped
        # headline, so every line of the block is still at most the width.
        long_label = "a_very_long_rule_name_that_needs_wrapping"
        finding = self._finding("warn", long_label)
        block = piguard.render_finding_block(finding, width=40)
        for line in block:
            self.assertLessEqual(
                len(line),
                40,
                "a block line exceeds the width 40: {!r}".format(line),
            )
        # The mark must be on a line (the wrapped headline carries it).
        self.assertTrue(
            any(self.WARN_MARK in line for line in block),
            "the warn mark must appear on a line of the block:\n{!r}".format(
                block
            ),
        )

    def test_warn_block_is_one_marked_em_dash_line(self):
        # Behaviour 5 of plans/guard-finding-compact.md: the warn block
        # is ONE line - the marked em-dash headline with the brief. The
        # old detail line and the indented "fix:" line this test used to
        # pin byte-for-byte are gone: the remedy moves to the report's
        # "To fix" section (behaviour 7). (Re-pointed and renamed from
        # the old warn-layout pin; the mark assertion is kept.)
        finding = self._finding("warn", "file_path_restriction")
        block = piguard.render_finding_block(finding)
        self.assertEqual(
            block,
            ["⚠️ warn: file_path_restriction — the guard detail"],
            "the warn block is one line: the marked headline with the "
            "brief after an em dash - no detail line, no 'fix:' "
            "line:\nblock: {!r}".format(block),
        )
        self.assertTrue(
            block[0].startswith(self.WARN_MARK),
            "the warn headline must start with the warning mark: "
            "{!r}".format(block[0]),
        )


class TokenFindingInvariantSweepTests(unittest.TestCase):
    """Behaviour 10 of plans/verify-guards-token.md: a [PIN] boundary pin over
    the token-scope findings the probes of behaviours 2-6 can emit.

    A [PIN] sweeps the invariants over the production code as it is: the code
    is believed correct, so the sweep may already pass - and that is the
    correct outcome for a boundary pin. Its job is to break on future drift:
    a finding that later drops its remedy, loses its danger, or renders
    through the ``unknown:`` fallthrough must fail these tests, and no
    assertion may be weakened to reach green - a new probe absent from the
    sweep silently un-pins the invariant, so the swept check set is pinned to
    the five.

    The sweep drives the probes over every recorded outcome: the recorded
    200/403/404/401/500 responses, the transport failures (URLError,
    socket.timeout, bare OSError), the no-token skip, and (named_repo) the
    no-other-repo skip; ``check_token_all`` is driven over the same opener
    matrix to sweep the fixed-order concatenation, and the constant
    ``workflows_withheld`` finding is swept on its own. Every test runs over
    a recorded opener - no live network.
    """

    TOKEN = "ghp_recordedtoken"
    OWNER = "owner"
    REPO = "repo"
    # Raw --other-repo value (behaviour 18): the sweep used the target
    # owner as the other's owner, so the recorded URLs stay identical to
    # the pre-amendment sweep - only the call shape changed.
    OTHER_REPO = "{}/{}".format("owner", "other")
    _API = "https://api.github.com"
    _KNOWN_STATUSES = ("passed", "warn", "skipped", "fail")

    # The fixed set of probe checks this sweep must cover: a probe added to
    # the module that is absent from the sweep silently un-pins the
    # invariant, so the swept set is pinned to exactly these five.
    EXPECTED_SWEEP_CHECKS = (
        "target_access",
        "administration",
        "classic_token",
        "workflows_withheld",
        "named_repo",
    )

    def _http_outcome(self, code: int) -> Any:
        """One recorded HTTPError for the status code; a denial is data."""
        return urllib.error.HTTPError(
            self._API + "/user", code, "recorded", None, None
        )

    def _probe_cases(self) -> List[Tuple[str, Callable[..., List[Dict[str, Any]]]]]:
        """(label, zero-argument probe call) over the full recorded matrix.

        Every probe, over the recorded 200/403/404/401/500 responses, the
        three documented transport failures, the no-token skip and
        (named_repo) the no-other-repo skip - every finding behaviours
        2-6 can emit.
        """
        outcomes = (
            [
                # The classic-token discriminator is the X-OAuth-Scopes
                # header, so its 200 records the header
                # present-and-non-empty: the same opener is the fail case
                # there and the plain 200 for the other probes.
                (
                    "HTTP 200 (X-OAuth-Scopes: repo, user)",
                    _opener(
                        _FakeResponse(
                            b"{}",
                            200,
                            headers={"X-OAuth-Scopes": "repo, user"},
                        )
                    ),
                ),
                ("HTTP 403", _opener(self._http_outcome(403))),
                ("HTTP 404", _opener(self._http_outcome(404))),
                ("HTTP 401", _opener(self._http_outcome(401))),
                ("HTTP 500", _opener(self._http_outcome(500))),
            ]
        )
        transport = (
            (
                "URLError",
                urllib.error.URLError("Name or service not known"),
            ),
            ("socket.timeout", socket.timeout("timed out")),
            ("bare OSError", OSError("Network is unreachable")),
        )
        cases: List[Tuple[str, Callable[..., List[Dict[str, Any]]]]] = [
            (
                "no token",
                lambda: piguard.probe_target_access(self.OWNER, self.REPO),
            ),
            (
                "no token",
                lambda: piguard.probe_administration(self.OWNER, self.REPO),
            ),
            ("no token", lambda: piguard.probe_classic_token()),
            (
                "no other repo",
                lambda: piguard.probe_named_repo(None),
            ),
            (
                "no token",
                lambda: piguard.probe_named_repo(self.OTHER_REPO),
            ),
        ]
        for label, opener in outcomes:
            cases.append(
                (
                    label,
                    lambda opener=opener: piguard.probe_target_access(
                        self.OWNER, self.REPO, self.TOKEN, opener
                    ),
                )
            )
            cases.append(
                (
                    label,
                    lambda opener=opener: piguard.probe_administration(
                        self.OWNER, self.REPO, self.TOKEN, opener
                    ),
                )
            )
            cases.append(
                (
                    label,
                    lambda opener=opener: piguard.probe_classic_token(
                        self.TOKEN, opener
                    ),
                )
            )
            cases.append(
                (
                    label,
                    lambda opener=opener: piguard.probe_named_repo(
                        self.OTHER_REPO, self.TOKEN, opener
                    ),
                )
            )
        for label, failure in transport:
            opener = _opener(failure)
            cases.append(
                (
                    label,
                    lambda opener=opener: piguard.probe_target_access(
                        self.OWNER, self.REPO, self.TOKEN, opener
                    ),
                )
            )
            cases.append(
                (
                    label,
                    lambda opener=opener: piguard.probe_administration(
                        self.OWNER, self.REPO, self.TOKEN, opener
                    ),
                )
            )
            cases.append(
                (
                    label,
                    lambda opener=opener: piguard.probe_classic_token(
                        self.TOKEN, opener
                    ),
                )
            )
            cases.append(
                (
                    label,
                    lambda opener=opener: piguard.probe_named_repo(
                        self.OTHER_REPO, self.TOKEN, opener
                    ),
                )
            )
        cases.append(
            ("constant", lambda: piguard.workflows_withheld_finding())
        )
        return cases

    def _every_token_finding(self) -> List[Tuple[str, Dict[str, Any]]]:
        """Every token finding the probes can emit as of today, with a label.

        Direct per-probe calls over the recorded matrix, plus the
        ``check_token_all`` concatenation over the same opener matrix - a
        probe or a status dropped from either side would shrink the swept
        set and trip the non-vacuity pin.
        """
        findings: List[Tuple[str, Dict[str, Any]]] = []
        for label, call in self._probe_cases():
            for finding in call():
                findings.append(
                    (
                        "{}/{}: {}".format(
                            label,
                            _field(finding, "check"),
                            _field(finding, "status"),
                        ),
                        finding,
                    )
                )
        for label, findings_list in self._check_token_all_matrix():
            for finding in findings_list:
                findings.append(
                    (
                        "check_token_all({})/{}/{}".format(
                            label,
                            _field(finding, "check"),
                            _field(finding, "status"),
                        ),
                        finding,
                    )
                )
        return findings

    def _check_token_all_matrix(
        self,
    ) -> List[Tuple[str, List[Dict[str, Any]]]]:
        """``check_token_all`` over the recorded opener matrix, with labels.

        The one injected opener sees every endpoint, so each recorded
        outcome plays back on every probe - the concatenation's five
        findings are swept across the full matrix, plus the no-token and
        no-other-repo calls.
        """
        checker = piguard.check_token_all
        # (label, recorded outcome): a recorded response or a recorded
        # exception, replayed on every probe call by the one injected
        # _RecordingOpener.
        outcomes = (
            [
                ("HTTP 200", _FakeResponse(b'{"ok": true}', 200)),
                ("HTTP 403", self._http_outcome(403)),
                ("HTTP 404", self._http_outcome(404)),
                ("HTTP 401", self._http_outcome(401)),
                ("HTTP 500", self._http_outcome(500)),
                (
                    "classic 200 + X-OAuth-Scopes",
                    _FakeResponse(
                        b"{}",
                        200,
                        headers={"X-OAuth-Scopes": "repo, user"},
                    ),
                ),
                (
                    "URLError",
                    urllib.error.URLError("Name or service not known"),
                ),
                ("socket.timeout", socket.timeout("timed out")),
                ("bare OSError", OSError("Network is unreachable")),
            ]
        )
        pairs: List[Tuple[str, List[Dict[str, Any]]]] = []
        for label, outcome in outcomes:
            pairs.append(
                (
                    label,
                    checker(
                        self.OWNER,
                        self.REPO,
                        token=self.TOKEN,
                        other_repo=self.OTHER_REPO,
                        opener=_RecordingOpener(outcome),
                        timeout=10.0,
                    ),
                )
            )
        pairs.append(
            (
                "no token",
                checker(
                    self.OWNER,
                    self.REPO,
                    token=None,
                    other_repo=self.OTHER_REPO,
                    opener=_RecordingOpener(
                        _FakeResponse(b'{"ok": true}', 200)
                    ),
                    timeout=10.0,
                ),
            )
        )
        pairs.append(
            (
                "no other repo",
                checker(
                    self.OWNER,
                    self.REPO,
                    token=self.TOKEN,
                    other_repo=None,
                    opener=_RecordingOpener(
                        _FakeResponse(b'{"ok": true}', 200)
                    ),
                    timeout=10.0,
                ),
            )
        )
        return pairs

    def _assert_finding_invariants(self, finding: Dict[str, Any]) -> None:
        """The per-finding invariants, asserted under the caller's subTest."""
        status = _field(finding, "status")
        self.assertIn(
            status,
            self._KNOWN_STATUSES,
            "finding status {!r} is not one of the four known statuses; "
            "the report cannot interpret it".format(status),
        )
        remedy = _field(finding, "remedy")
        self.assertIsInstance(
            remedy,
            str,
            "remedy must be a string, not {!r}".format(type(remedy).__name__),
        )
        if status != "passed":
            # A non-passing token finding must still name the fix
            # (behaviour 10, kept by behaviour 2 of
            # plans/guard-finding-compact.md).
            self.assertTrue(
                remedy,
                "a non-passing token finding ({}) with an empty remedy "
                "is a programming error: it cannot name the concrete "
                "fix".format(status),
            )
        # A passed token finding's remedy may be empty now that nothing
        # prints it (behaviour 2 of plans/guard-finding-compact.md).
        if status != "passed":
            danger = _field(finding, "danger")
            self.assertIsInstance(
                danger,
                str,
                "danger must be a string, not {!r}".format(type(danger).__name__),
            )
            self.assertTrue(
                danger,
                "a non-passing token finding ({}) must name what an agent "
                "could do while the fact is unmeasured or violated; its "
                "danger is empty".format(status),
            )
            self.assertLessEqual(
                len(remedy),
                100,
                "the {} token finding for check {!r} remedy must be a "
                "single sentence of at most 100 characters, got {}: "
                "{!r}".format(
                    status, _field(finding, "check"), len(remedy), remedy
                ),
            )
            self.assertNotIn(
                ". ",
                remedy,
                "the {} token finding for check {!r} remedy must be a "
                "single sentence: {!r}".format(
                    status, _field(finding, "check"), remedy
                ),
            )
            self.assertNotIn(
                "doc/external/",
                remedy,
                "the {} token finding for check {!r} must carry no doc "
                "path in its remedy (behaviour 2 of "
                "plans/guard-finding-compact.md): {!r}".format(
                    status, _field(finding, "check"), remedy
                ),
            )
            self.assertNotIn(
                "see:",
                remedy,
                "the {} token finding for check {!r} must carry no "
                "'see:' clause in its remedy (behaviour 2 of "
                "plans/guard-finding-compact.md): {!r}".format(
                    status, _field(finding, "check"), remedy
                ),
            )
        line = piguard.render_finding(finding)
        self.assertIsInstance(line, str)
        self.assertTrue(
            line,
            "render_finding must produce a non-empty line for every token "
            "finding",
        )
        if status == "fail":
            self.assertNotIn(
                "unknown:",
                line,
                "a fail finding must not render through the 'unknown:' "
                "fallthrough - that line would hide the first real failure "
                "the family can emit: {!r}".format(line),
            )

    def test_every_token_finding_the_probes_can_emit_holds_the_invariants(self):
        findings = self._every_token_finding()
        self.assertGreater(
            len(findings),
            0,
            "the sweep produced no findings; the recorded matrix must "
            "exercise the probes' real output",
        )
        for label, finding in findings:
            with self.subTest(finding=label):
                self._assert_finding_invariants(finding)

    def test_sweep_is_not_vacuous_and_covers_exactly_the_five_probe_checks(self):
        findings = self._every_token_finding()
        statuses = {_field(f, "status") for _label, f in findings}
        checks = {_field(f, "check") for _label, f in findings}
        for required in ("fail", "warn", "skipped"):
            self.assertIn(
                required,
                statuses,
                "the sweep must actually exercise at least one {} finding, "
                "so a probe that stops emitting it - or drops out of the "
                "sweep - breaks the pin instead of silently un-pinning "
                "it".format(required),
            )
        self.assertEqual(
            checks,
            set(self.EXPECTED_SWEEP_CHECKS),
            "the swept check set must be exactly the five token probes; a "
            "new probe absent from the sweep silently un-pins the "
            "invariant: swept={}".format(sorted(checks)),
        )


class SummarizeTokenFindingsTests(unittest.TestCase):
    """Behaviour 11 of plans/verify-guards-token.md: a [PIN] boundary pin
    over ``summarize`` on token findings.

    The first live exercise of the reserved path: the token probes are the
    first to emit a ``fail``, so the exit-status seam is pinned against the
    findings they actually produce - not hand-built dicts. ``1`` when any
    finding has status ``fail``, ``0`` otherwise; ``warn`` and ``skipped``
    alone yield ``0``; the empty list yields ``0``; an unknown status is
    not a fail. Every test runs over a recorded opener - no live network.
    """

    TOKEN = "ghp_recordedtoken"
    OWNER = "owner"
    REPO = "repo"
    # Raw --other-repo value (behaviour 18): the same owner/repo pair the
    # pre-amendment call passed as the two positional halves, now the
    # single raw string the probe splits itself.
    OTHER_REPO = "owner/other"
    _API = "https://api.github.com"

    def _summarizer(self) -> Any:
        summarizer = getattr(piguard, "summarize", None)
        self.assertTrue(
            callable(summarizer),
            "anvilkit.pi.piguard.summarize is not callable; the exit-status "
            "seam has not been implemented yet",
        )
        return summarizer

    def _token_findings_without_fail(self) -> List[Dict[str, Any]]:
        """Real token findings mixing passed/warn/skipped - no fail.

        One finding per probe, each in a recorded non-fail mode:
        target_access 200 (passed), administration 403 (passed),
        classic_token 200 with no scope header (passed),
        workflows_withheld (constant skipped), named_repo 404 (passed);
        plus the warn and skipped findings the same probes emit on a 404
        target and a transport failure.
        """
        http = lambda code: urllib.error.HTTPError(
            self._API + "/user", code, "recorded", None, None
        )
        findings: List[Dict[str, Any]] = []
        findings.extend(
            piguard.probe_target_access(
                self.OWNER,
                self.REPO,
                self.TOKEN,
                _opener(_FakeResponse(b'{"ok": true}', 200)),
            )
        )
        findings.extend(
            piguard.probe_administration(
                self.OWNER,
                self.REPO,
                self.TOKEN,
                _opener(http(403)),
            )
        )
        findings.extend(
            piguard.probe_classic_token(
                self.TOKEN, _opener(_FakeResponse(b"{}", 200))
            )
        )
        findings.extend(piguard.workflows_withheld_finding())
        findings.extend(
            piguard.probe_named_repo(
                self.OTHER_REPO,
                self.TOKEN,
                _opener(http(404)),
            )
        )
        # The warn and skipped modes of the same probes.
        findings.extend(
            piguard.probe_target_access(
                self.OWNER,
                self.REPO,
                self.TOKEN,
                _opener(http(404)),
            )
        )
        findings.extend(
            piguard.probe_named_repo(
                self.OTHER_REPO,
                self.TOKEN,
                _opener(http(200)),
            )
        )
        findings.extend(
            piguard.probe_administration(
                self.OWNER,
                self.REPO,
                self.TOKEN,
                _opener(urllib.error.URLError("Name or service not known")),
            )
        )
        return findings

    def _token_findings_all_fail(self) -> List[Dict[str, Any]]:
        """A list every element of which is a real ``fail`` token finding.

        Only two probes can emit a fail - administration (200) and
        classic_token (non-empty scopes header) - so the all-fail list is
        their fail findings together, each from the real probe over a
        recorded opener.
        """
        findings: List[Dict[str, Any]] = []
        findings.extend(
            piguard.probe_administration(
                self.OWNER,
                self.REPO,
                self.TOKEN,
                _opener(_FakeResponse(b"{}", 200)),
            )
        )
        findings.extend(
            piguard.probe_classic_token(
                self.TOKEN,
                _opener(
                    _FakeResponse(
                        b"{}",
                        200,
                        headers={"X-OAuth-Scopes": "repo, user"},
                    )
                ),
            )
        )
        return findings

    def test_token_findings_mixed_passed_warn_skipped_without_fail_yield_zero(self):
        summarize = self._summarizer()
        findings = self._token_findings_without_fail()

        self.assertEqual(
            [f for f in findings if _field(f, "status") == "fail"],
            [],
            "fixture sanity: the list carries no fail finding",
        )
        statuses = {_field(f, "status") for f in findings}
        for required in ("passed", "warn", "skipped"):
            self.assertIn(
                required,
                statuses,
                "fixture sanity: the list must mix the three non-failing "
                "statuses, and it lacks {}".format(required),
            )

        self.assertEqual(
            summarize(findings),
            0,
            "token findings mixing passed, warn and skipped must exit 0 - "
            "a warning or an unrunnable probe is reported, not a failure",
        )

    def test_exactly_one_real_token_fail_among_non_fail_findings_yields_one(self):
        summarize = self._summarizer()
        non_fail = self._token_findings_without_fail()
        for label, fail_finding in (
            (
                "administration (behaviour 3, 200)",
                piguard.probe_administration(
                    self.OWNER,
                    self.REPO,
                    self.TOKEN,
                    _opener(_FakeResponse(b"{}", 200)),
                )[0],
            ),
            (
                "classic_token (behaviour 4, non-empty scopes header)",
                piguard.probe_classic_token(
                    self.TOKEN,
                    _opener(
                        _FakeResponse(
                            b"{}",
                            200,
                            headers={"X-OAuth-Scopes": "repo, user"},
                        )
                    ),
                )[0],
            ),
        ):
            with self.subTest(fail=label):
                self.assertEqual(
                    _field(fail_finding, "status"),
                    "fail",
                    "fixture sanity: the probe emits a fail finding",
                )
                findings = non_fail + [fail_finding]
                self.assertEqual(
                    [f for f in findings if _field(f, "status") == "fail"],
                    [fail_finding],
                    "fixture sanity: exactly one fail finding among the "
                    "token findings",
                )

                self.assertEqual(
                    summarize(findings),
                    1,
                    "a single real token fail among passed, warn and "
                    "skipped findings must yield the exit status 1 - the "
                    "first live exercise of the reserved path",
                )

    def test_all_fail_token_findings_yield_one(self):
        summarize = self._summarizer()
        findings = self._token_findings_all_fail()

        self.assertEqual(
            [_field(f, "status") for f in findings],
            ["fail"] * len(findings),
            "fixture sanity: every finding in the all-fail list is a fail",
        )
        self.assertGreaterEqual(
            len(findings),
            2,
            "fixture sanity: both fail-emitting probes (administration, "
            "classic_token) contribute their fail finding",
        )
        self.assertEqual(
            [_field(f, "check") for f in findings],
            ["administration", "classic_token"],
            "fixture sanity: the all-fail list holds the two probes that "
            "can emit a fail",
        )

        self.assertEqual(
            summarize(findings),
            1,
            "a list of all-fail token findings must yield the exit "
            "status 1",
        )

    def test_empty_token_findings_yield_zero(self):
        summarize = self._summarizer()

        self.assertEqual(
            summarize([]),
            0,
            "no findings at all means nothing failed",
        )

    def test_unknown_status_is_not_a_fail(self):
        summarize = self._summarizer()
        finding = {
            "status": "bogus",
            "check": "administration",
            "rule": None,
            "danger": "d",
            "source": None,
            "remedy": "r; see doc/external/github/"
            "rest-api-endpoints-for-actions-permissions.md",
        }

        self.assertEqual(
            summarize([finding]),
            0,
            "a status that is not exactly 'fail' must not be read as a "
            "failure - only the literal fail status drives the exit "
            "status",
        )


class FindingBriefTests(unittest.TestCase):
    """Behaviour 1 of plans/guard-finding-compact.md: brief on every finding.

    Every emittable finding - the five branch rules at passed and warn,
    the four ``skipped_findings`` checks and the five token checks at
    their statuses - carries a non-empty ``brief`` string of at most 60
    characters, plain words, no doc path, no API jargon beyond the rule
    name: the one short clause the compact report's headline carries
    after the em dash.

    The approved sample report recorded with the plan is the wording
    authority for the briefs. Exact-word pins: wherever the sample gives
    a word for a producer path, the tests pin that exact string - the
    five branch passed briefs, the five branch warn briefs,
    "no paths recorded" on an empty or unreadable
    ``restricted_file_paths``, and the token briefs the sample names
    (the sample's target ``iar3-r8/anvil`` and other repo
    ``someorg/other`` are the sample run's values, so those briefs pin
    the sample's form with the recorded value substituted).
    Shape-only pins: the statuses the sample does not name (a
    target-access 404 warn, an administration 200 fail or 404 warn, a
    classic-token fail) and the parentheticals at values the sample
    does not show (counts other than 2, ``fetch and merge: True``,
    multiple restricted paths) - there the tests pin non-empty, at most
    60 characters, no doc path, and the recorded value in parentheses.

    The producers are driven as in production: the branch findings
    through ``check_all`` over recorded rules-array shapes, the skipped
    findings through ``skipped_findings`` over the reasons
    ``fetch_branch_rules`` actually records (and the resolve-failure
    reason the CLI builds), and the token findings through the five
    probes over recorded openers - no live network.
    """

    OWNER = "owner"
    REPO = "repo"
    TOKEN = "ghp_recordedtoken"
    # The sample report's named other repo: its owner differs from the
    # target's owner, as the sample's does (someorg vs iar3-r8).
    OTHER_REPO = "someorg/other"

    # The resolve-failure reason the CLI builds when the target has no
    # GitHub origin (anvilkit/cli.py, _collect_guard_findings) - the
    # input ``skipped_findings`` actually receives on that path.
    _NO_ORIGIN_REASON = (
        "owner/repo could not be resolved from the origin remote of "
        "{}: the {} has no origin, or its remote is not a GitHub "
        "repository, and the identity is never guessed"
    )

    def _assert_brief_shape(self, finding: Any, label: str) -> str:
        """The shape every finding's brief must carry; returns the brief."""
        brief = _field(finding, "brief")
        self.assertIsInstance(
            brief,
            str,
            "{}: the finding must carry a brief string".format(label),
        )
        self.assertTrue(
            brief.strip(),
            "{}: the brief must be non-empty".format(label),
        )
        self.assertLessEqual(
            len(brief),
            60,
            "{}: the brief must be at most 60 characters, got {} "
            "characters: {!r}".format(label, len(brief), brief),
        )
        self.assertNotIn(
            "doc/external/",
            brief,
            "{}: the brief must carry no doc path: {!r}".format(label, brief),
        )
        return brief

    def _fetch_reason(self, outcome: Any) -> str:
        """The reason ``fetch_branch_rules`` records for a recorded failure."""
        rules, reason = piguard.fetch_branch_rules(
            self.OWNER, self.REPO, "main", opener=_opener(outcome)
        )
        self.assertIsNone(
            rules,
            "fixture sanity: a failed fetch must not be reported as rules",
        )
        self.assertIsInstance(reason, str, "fixture sanity")
        self.assertTrue(reason, "fixture sanity: a failed fetch records a reason")
        return reason

    # ------------------------------------------------------------------
    # The branch findings, produced by check_all
    # ------------------------------------------------------------------

    def test_check_all_all_five_rules_passed_briefs_match_sample_words(self):
        findings = piguard.check_all(
            [
                rule("non_fast_forward", "main-protected"),
                rule("deletion", "main-protected"),
                pull_request_rule("main-protected", 2),
                update_rule(
                    "main-protected",
                    {"update_allows_fetch_and_merge": False},
                ),
                file_path_rule(
                    "main-protected",
                    {"restricted_file_paths": [".github/workflows/**"]},
                ),
            ]
        )
        self.assertEqual(
            [_field(f, "status") for f in findings],
            ["passed"] * 5,
            "fixture sanity: all five rules active yield five passed "
            "findings",
        )
        expected = (
            ("non_fast_forward", "force pushes blocked"),
            ("deletion", "branch deletion blocked"),
            ("pull_request", "review required (2 required approvals)"),
            ("update", "direct pushes restricted (fetch and merge: False)"),
            (
                "file_path_restriction",
                "listed paths protected (.github/workflows/**)",
            ),
        )
        for finding, (rule_type, brief) in zip(findings, expected):
            with self.subTest(rule=rule_type):
                self.assertEqual(
                    _field(finding, "rule"),
                    rule_type,
                    "fixture sanity: the finding names its rule",
                )
                self.assertEqual(
                    _field(finding, "brief"),
                    brief,
                    "the passed {} brief must be the sample's "
                    "clause".format(rule_type),
                )

    def test_check_all_empty_rules_warn_briefs_match_sample_words(self):
        findings = piguard.check_all([])

        self.assertEqual(
            [_field(f, "status") for f in findings],
            ["warn"] * 5,
            "fixture sanity: an empty rules array warns on all five rules",
        )
        expected = (
            (
                "non_fast_forward",
                "history can be rewritten or erased by a force push",
            ),
            ("deletion", "the branch can be deleted, with all its history"),
            ("pull_request", "changes can land on main with no review"),
            ("update", "anyone with push access can push straight to main"),
            (
                "file_path_restriction",
                "a push can change .github/workflows/**, what CI runs",
            ),
        )
        for finding, (rule_type, brief) in zip(findings, expected):
            with self.subTest(rule=rule_type):
                self.assertEqual(
                    _field(finding, "rule"),
                    rule_type,
                    "fixture sanity: the finding names its rule",
                )
                self.assertEqual(
                    _field(finding, "brief"),
                    brief,
                    "the warn {} brief must be the sample's "
                    "clause".format(rule_type),
                )

    def test_review_passed_brief_ends_with_recorded_count_in_parentheses(self):
        for count in (0, 1, 3):
            with self.subTest(count=count):
                findings = piguard.check_all(
                    [pull_request_rule("main-protected", count)]
                )
                passed = [
                    f
                    for f in findings
                    if _field(f, "rule") == "pull_request"
                    and _field(f, "status") == "passed"
                ]
                self.assertEqual(
                    len(passed),
                    1,
                    "fixture sanity: one passed review finding",
                )
                brief = self._assert_brief_shape(
                    passed[0],
                    "pull_request passed (count={})".format(count),
                )
                self.assertTrue(
                    brief.endswith("({} required approvals)".format(count)),
                    "the passed review brief must end with the recorded "
                    "count in parentheses, got: {!r}".format(brief),
                )

    def test_update_passed_brief_ends_with_recorded_value_in_parentheses(self):
        for value in (False, True):
            with self.subTest(value=value):
                findings = piguard.check_all(
                    [
                        update_rule(
                            "main-protected",
                            {"update_allows_fetch_and_merge": value},
                        )
                    ]
                )
                matching = [
                    f
                    for f in findings
                    if _field(f, "rule") == "update"
                    and _field(f, "status") == "passed"
                ]
                self.assertEqual(
                    len(matching), 1, "fixture sanity: one passed update finding"
                )
                brief = self._assert_brief_shape(
                    matching[0],
                    "update passed (value={})".format(value),
                )
                self.assertTrue(
                    brief.endswith("(fetch and merge: {})".format(value)),
                    "the passed update brief must end with the recorded "
                    "value in parentheses, got: {!r}".format(brief),
                )

    def test_file_paths_passed_brief_ends_with_recorded_paths_in_parentheses(self):
        paths = [".github/workflows/**", "config.yaml"]
        findings = piguard.check_all(
            [
                file_path_rule(
                    "main-protected", {"restricted_file_paths": paths}
                )
            ]
        )
        matching = [
            f
            for f in findings
            if _field(f, "rule") == "file_path_restriction"
            and _field(f, "status") == "passed"
        ]
        self.assertEqual(
            len(matching), 1, "fixture sanity: one passed file-path finding"
        )
        brief = self._assert_brief_shape(
            matching[0],
            "file_path_restriction passed ({} paths)".format(len(paths)),
        )
        self.assertTrue(
            brief.endswith(")"),
            "the passed file-path brief must end with the recorded paths "
            "in parentheses, got: {!r}".format(brief),
        )
        for path in paths:
            self.assertIn(
                path,
                brief,
                "the passed file-path brief must carry the recorded path "
                "{!r}, got: {!r}".format(path, brief),
            )

    def test_file_paths_passed_brief_says_no_paths_recorded_when_empty(self):
        findings = piguard.check_all(
            [
                file_path_rule(
                    "main-protected", {"restricted_file_paths": []}
                )
            ]
        )
        finding = [
            f
            for f in findings
            if _field(f, "rule") == "file_path_restriction"
        ][0]
        self.assertEqual(
            _field(finding, "restricted_file_paths"),
            [],
            "fixture sanity: an explicit empty list is recorded",
        )
        brief = self._assert_brief_shape(
            finding,
            "file_path_restriction passed (restricted_file_paths=[])",
        )
        self.assertIn(
            "no paths recorded",
            brief,
            "an empty restricted_file_paths must render 'no paths "
            "recorded', got: {!r}".format(brief),
        )

    def test_file_paths_passed_brief_says_no_paths_recorded_when_parameters_unreadable(self):
        cases = (
            ("parameters key absent", file_path_rule("main-protected")),
            (
                "parameters is not a dict",
                dict(file_path_rule("main-protected"), parameters="not a dict"),
            ),
            (
                "restricted_file_paths is not a list",
                file_path_rule(
                    "main-protected",
                    {"restricted_file_paths": "config.yaml"},
                ),
            ),
        )
        for label, element in cases:
            with self.subTest(parameters=label):
                findings = piguard.check_all([element])
                finding = [
                    f
                    for f in findings
                    if _field(f, "rule") == "file_path_restriction"
                ][0]
                self.assertEqual(
                    _field(finding, "restricted_file_paths"),
                    [],
                    "fixture sanity: unreadable parameters record an empty "
                    "list",
                )
                brief = self._assert_brief_shape(
                    finding,
                    "file_path_restriction passed (unreadable: {})".format(
                        label
                    ),
                )
                self.assertIn(
                    "no paths recorded",
                    brief,
                    "an unreadable restricted_file_paths must render 'no "
                    "paths recorded', got: {!r}".format(brief),
                )

    # ------------------------------------------------------------------
    # The skipped findings, produced by skipped_findings
    # ------------------------------------------------------------------

    def test_skipped_findings_no_origin_reason_brief_matches_sample(self):
        reason = self._NO_ORIGIN_REASON.format("/tmp/target", "target")
        findings = piguard.skipped_findings(reason)
        self.assertEqual(
            len(findings), 4, "fixture sanity: one skipped finding per check"
        )
        for finding in findings:
            with self.subTest(check=_field(finding, "check")):
                brief = self._assert_brief_shape(
                    finding, "skipped ({})".format(_field(finding, "check"))
                )
                self.assertEqual(
                    brief,
                    "no GitHub origin remote",
                    "the no-origin skip brief must be the sample's clause",
                )

    def test_skipped_findings_404_reason_brief_matches_sample(self):
        reason = self._fetch_reason(
            urllib.error.HTTPError(
                "https://api.github.com/repos/owner/repo/rules/branches/main",
                404,
                "Not Found",
                None,
                None,
            )
        )
        findings = piguard.skipped_findings(reason)
        for finding in findings:
            with self.subTest(check=_field(finding, "check")):
                brief = self._assert_brief_shape(
                    finding, "skipped ({})".format(_field(finding, "check"))
                )
                self.assertEqual(
                    brief,
                    "GitHub returned 404 for the branch rules",
                    "the 404 skip brief must be the sample's clause",
                )

    def test_skipped_findings_unreachable_reason_brief_matches_sample(self):
        reason = self._fetch_reason(
            urllib.error.URLError("Name or service not known")
        )
        findings = piguard.skipped_findings(reason)
        for finding in findings:
            with self.subTest(check=_field(finding, "check")):
                brief = self._assert_brief_shape(
                    finding, "skipped ({})".format(_field(finding, "check"))
                )
                self.assertEqual(
                    brief,
                    "api.github.com was unreachable",
                    "the unreachable skip brief must be the sample's clause",
                )

    # ------------------------------------------------------------------
    # The token findings, produced by the five probes
    # ------------------------------------------------------------------

    def test_target_access_passed_brief_names_the_target(self):
        findings = piguard.probe_target_access(
            self.OWNER,
            self.REPO,
            self.TOKEN,
            _opener(_FakeResponse(b'{"full_name": "owner/repo"}', 200)),
        )
        self.assertEqual(
            _field(findings[0], "status"),
            "passed",
            "fixture sanity: a 200 on the target passes",
        )
        brief = self._assert_brief_shape(
            findings[0], "target_access passed (200)"
        )
        self.assertEqual(
            brief,
            "the token reaches {}/{}".format(self.OWNER, self.REPO),
            "the passed target-access brief must be the sample's clause "
            "with the recorded target",
        )

    def test_target_access_no_token_brief_matches_sample(self):
        findings = piguard.probe_target_access(self.OWNER, self.REPO, None)
        self.assertEqual(
            _field(findings[0], "status"),
            "skipped",
            "fixture sanity: no token skips the probe",
        )
        brief = self._assert_brief_shape(
            findings[0], "target_access no-token skip"
        )
        self.assertEqual(
            brief,
            "no token in .env",
            "the no-token skip brief must be the sample's clause",
        )

    def test_target_access_404_brief_shape(self):
        findings = piguard.probe_target_access(
            self.OWNER,
            self.REPO,
            self.TOKEN,
            _opener(
                urllib.error.HTTPError(
                    "https://api.github.com/repos/owner/repo",
                    404,
                    "Not Found",
                    None,
                    None,
                )
            ),
        )
        self.assertEqual(
            _field(findings[0], "status"),
            "warn",
            "fixture sanity: a 404 on the target warns",
        )
        self._assert_brief_shape(findings[0], "target_access 404 warn")

    def test_target_access_401_brief_matches_sample(self):
        findings = piguard.probe_target_access(
            self.OWNER,
            self.REPO,
            self.TOKEN,
            _opener(
                urllib.error.HTTPError(
                    "https://api.github.com/repos/owner/repo",
                    401,
                    "Unauthorized",
                    None,
                    None,
                )
            ),
        )
        self.assertEqual(
            _field(findings[0], "status"),
            "skipped",
            "fixture sanity: a 401 is not a scope answer",
        )
        brief = self._assert_brief_shape(
            findings[0], "target_access 401 skip"
        )
        self.assertEqual(
            brief,
            "GitHub returned HTTP 401",
            "the 401 skip brief must be the sample's clause",
        )

    def test_administration_passed_brief_matches_sample(self):
        findings = piguard.probe_administration(
            self.OWNER,
            self.REPO,
            self.TOKEN,
            _opener(
                urllib.error.HTTPError(
                    "https://api.github.com/repos/owner/repo/actions/permissions",
                    403,
                    "Forbidden",
                    None,
                    None,
                )
            ),
        )
        self.assertEqual(
            _field(findings[0], "status"),
            "passed",
            "fixture sanity: a 403 is the compliant answer",
        )
        brief = self._assert_brief_shape(
            findings[0], "administration passed (403)"
        )
        self.assertEqual(
            brief,
            "Administration withheld (403)",
            "the passed administration brief must be the sample's clause",
        )

    def test_administration_fail_brief_shape(self):
        findings = piguard.probe_administration(
            self.OWNER,
            self.REPO,
            self.TOKEN,
            _opener(_FakeResponse(b"{}", 200)),
        )
        self.assertEqual(
            _field(findings[0], "status"),
            "fail",
            "fixture sanity: a 200 on the permissions endpoint fails",
        )
        self._assert_brief_shape(findings[0], "administration fail (200)")

    def test_administration_warn_brief_shape(self):
        findings = piguard.probe_administration(
            self.OWNER,
            self.REPO,
            self.TOKEN,
            _opener(
                urllib.error.HTTPError(
                    "https://api.github.com/repos/owner/repo/actions/permissions",
                    404,
                    "Not Found",
                    None,
                    None,
                )
            ),
        )
        self.assertEqual(
            _field(findings[0], "status"),
            "warn",
            "fixture sanity: a 404 is ambiguous, so it warns",
        )
        self._assert_brief_shape(findings[0], "administration warn (404)")

    def test_classic_token_passed_brief_matches_sample(self):
        findings = piguard.probe_classic_token(
            self.TOKEN,
            _opener(_FakeResponse(b'{"login": "owner"}', 200)),
        )
        self.assertEqual(
            _field(findings[0], "status"),
            "passed",
            "fixture sanity: no scope header passes",
        )
        brief = self._assert_brief_shape(
            findings[0], "classic_token passed (no scopes)"
        )
        self.assertEqual(
            brief,
            "no classic OAuth scopes returned",
            "the passed classic-token brief must be the sample's clause",
        )

    def test_classic_token_fail_brief_shape(self):
        findings = piguard.probe_classic_token(
            self.TOKEN,
            _opener(
                _FakeResponse(
                    b'{"login": "owner"}',
                    200,
                    headers={"X-OAuth-Scopes": "repo, user"},
                )
            ),
        )
        self.assertEqual(
            _field(findings[0], "status"),
            "fail",
            "fixture sanity: a non-empty scope header fails",
        )
        self._assert_brief_shape(
            findings[0], "classic_token fail (scopes recorded)"
        )

    def test_workflows_withheld_brief_matches_sample(self):
        findings = piguard.workflows_withheld_finding()
        self.assertEqual(
            _field(findings[0], "status"),
            "skipped",
            "fixture sanity: the withholding is unprovable, so it skips",
        )
        brief = self._assert_brief_shape(
            findings[0], "workflows_withheld constant"
        )
        self.assertEqual(
            brief,
            "no read-only call can prove this",
            "the workflows-withheld brief must be the sample's clause",
        )

    def test_named_repo_no_other_repo_brief_matches_sample(self):
        findings = piguard.probe_named_repo(None, self.TOKEN)
        self.assertEqual(
            _field(findings[0], "status"),
            "skipped",
            "fixture sanity: nothing to probe skips",
        )
        brief = self._assert_brief_shape(
            findings[0], "named_repo no-other-repo skip"
        )
        self.assertEqual(
            brief,
            "no other repo named",
            "the no-other-repo brief must be the sample's clause",
        )

    def test_named_repo_malformed_brief_matches_sample(self):
        findings = piguard.probe_named_repo("oops", self.TOKEN)
        self.assertEqual(
            _field(findings[0], "status"),
            "skipped",
            "fixture sanity: malformed input skips, opener never called",
        )
        brief = self._assert_brief_shape(
            findings[0], "named_repo malformed skip"
        )
        self.assertEqual(
            brief,
            "--other-repo 'oops' is not OWNER/REPO",
            "the malformed-input brief must be the sample's clause",
        )

    def test_named_repo_passed_brief_names_the_other_repo(self):
        findings = piguard.probe_named_repo(
            self.OTHER_REPO,
            self.TOKEN,
            _opener(
                urllib.error.HTTPError(
                    "https://api.github.com/repos/someorg/other",
                    404,
                    "Not Found",
                    None,
                    None,
                )
            ),
        )
        self.assertEqual(
            _field(findings[0], "status"),
            "passed",
            "fixture sanity: a 404 on the other repo passes",
        )
        brief = self._assert_brief_shape(findings[0], "named_repo passed (404)")
        self.assertEqual(
            brief,
            "does not reach {} (404)".format(self.OTHER_REPO),
            "the passed named-repo brief must be the sample's clause "
            "with the recorded other repo",
        )

    def test_named_repo_warn_brief_names_the_other_repo(self):
        findings = piguard.probe_named_repo(
            self.OTHER_REPO,
            self.TOKEN,
            _opener(_FakeResponse(b'{"full_name": "someorg/other"}', 200)),
        )
        self.assertEqual(
            _field(findings[0], "status"),
            "warn",
            "fixture sanity: a 200 on the other repo warns",
        )
        brief = self._assert_brief_shape(findings[0], "named_repo warn (200)")
        self.assertEqual(
            brief,
            "also reaches {}, so a leak is not confined here".format(
                self.OTHER_REPO
            ),
            "the warn named-repo brief must be the sample's clause with "
            "the recorded other repo",
        )

    def test_named_repo_403_brief_matches_sample(self):
        findings = piguard.probe_named_repo(
            self.OTHER_REPO,
            self.TOKEN,
            _opener(
                urllib.error.HTTPError(
                    "https://api.github.com/repos/someorg/other",
                    403,
                    "Forbidden",
                    None,
                    None,
                )
            ),
        )
        self.assertEqual(
            _field(findings[0], "status"),
            "skipped",
            "fixture sanity: a 403 is not a scope answer",
        )
        brief = self._assert_brief_shape(findings[0], "named_repo 403 skip")
        self.assertEqual(
            brief,
            "GitHub returned 403, not a scope answer",
            "the 403 named-repo brief must be the sample's clause",
        )

    # ------------------------------------------------------------------
    # The sweep: every producer path
    # ------------------------------------------------------------------

    def _every_brief_finding(self) -> List[Tuple[str, Dict[str, Any]]]:
        """Every finding the producers can emit as of today, with a label.

        The same producer paths the per-finding tests above cover:
        ``check_all`` over recorded rules-array shapes,
        ``skipped_findings`` over the recorded fetch reasons and the
        resolve-failure reason, every token probe over its recorded
        outcomes, and the ``check_token_all`` concatenation over a
        recorded 200 opener. A producer added to the module that is
        absent from this sweep silently un-pins the invariant, so keep
        the sweep in sync with the producers.
        """
        findings: List[Tuple[str, Dict[str, Any]]] = []
        rules_arrays = (
            ("empty array", []),
            (
                "all five rules",
                [
                    rule("non_fast_forward", "main-protected"),
                    rule("deletion", "main-protected"),
                    pull_request_rule("main-protected", 2),
                    update_rule(
                        "main-protected",
                        {"update_allows_fetch_and_merge": False},
                    ),
                    file_path_rule(
                        "main-protected",
                        {"restricted_file_paths": [".github/workflows/**"]},
                    ),
                ],
            ),
            (
                "all five rules, weak parameters",
                [
                    rule("non_fast_forward", "main-protected"),
                    rule("deletion", "main-protected"),
                    pull_request_rule("main-protected", 0),
                    update_rule(
                        "main-protected",
                        {"update_allows_fetch_and_merge": True},
                    ),
                    file_path_rule(
                        "main-protected",
                        {"restricted_file_paths": []},
                    ),
                ],
            ),
        )
        for label, rules in rules_arrays:
            for finding in piguard.check_all(rules):
                findings.append(
                    (
                        "check_all/{}: {} on rule {!r}".format(
                            label,
                            _field(finding, "status"),
                            _field(finding, "rule"),
                        ),
                        finding,
                    )
                )
        url = "https://api.github.com/repos/owner/repo/rules/branches/main"
        skip_reasons = (
            (
                "no origin",
                self._NO_ORIGIN_REASON.format("/tmp/target", "target"),
            ),
            (
                "http 404",
                self._fetch_reason(
                    urllib.error.HTTPError(url, 404, "Not Found", None, None)
                ),
            ),
            (
                "unreachable",
                self._fetch_reason(
                    urllib.error.URLError("Name or service not known")
                ),
            ),
            (
                "http 401",
                self._fetch_reason(
                    urllib.error.HTTPError(url, 401, "Unauthorized", None, None)
                ),
            ),
        )
        for label, reason in skip_reasons:
            for finding in piguard.skipped_findings(reason):
                findings.append(
                    (
                        "skipped_findings/{}: {} on check {!r}".format(
                            label,
                            _field(finding, "status"),
                            _field(finding, "check"),
                        ),
                        finding,
                    )
                )
        target_url = "https://api.github.com/repos/owner/repo"
        admin_url = (
            "https://api.github.com/repos/owner/repo/actions/permissions"
        )
        other_url = "https://api.github.com/repos/someorg/other"
        probe_calls = (
            (
                "target_access no-token",
                lambda: piguard.probe_target_access(
                    self.OWNER, self.REPO, None
                ),
            ),
            (
                "target_access 200",
                lambda: piguard.probe_target_access(
                    self.OWNER,
                    self.REPO,
                    self.TOKEN,
                    _opener(_FakeResponse(b'{"full_name": "owner/repo"}', 200)),
                ),
            ),
            (
                "target_access 404",
                lambda: piguard.probe_target_access(
                    self.OWNER,
                    self.REPO,
                    self.TOKEN,
                    _opener(
                        urllib.error.HTTPError(
                            target_url, 404, "Not Found", None, None
                        )
                    ),
                ),
            ),
            (
                "administration 403",
                lambda: piguard.probe_administration(
                    self.OWNER,
                    self.REPO,
                    self.TOKEN,
                    _opener(
                        urllib.error.HTTPError(
                            admin_url, 403, "Forbidden", None, None
                        )
                    ),
                ),
            ),
            (
                "administration 200",
                lambda: piguard.probe_administration(
                    self.OWNER,
                    self.REPO,
                    self.TOKEN,
                    _opener(_FakeResponse(b"{}", 200)),
                ),
            ),
            (
                "administration 404",
                lambda: piguard.probe_administration(
                    self.OWNER,
                    self.REPO,
                    self.TOKEN,
                    _opener(
                        urllib.error.HTTPError(
                            admin_url, 404, "Not Found", None, None
                        )
                    ),
                ),
            ),
            (
                "classic_token no-token",
                lambda: piguard.probe_classic_token(None),
            ),
            (
                "classic_token 200 no scopes",
                lambda: piguard.probe_classic_token(
                    self.TOKEN,
                    _opener(_FakeResponse(b'{"login": "owner"}', 200)),
                ),
            ),
            (
                "classic_token 200 scopes",
                lambda: piguard.probe_classic_token(
                    self.TOKEN,
                    _opener(
                        _FakeResponse(
                            b'{"login": "owner"}',
                            200,
                            headers={"X-OAuth-Scopes": "repo, user"},
                        )
                    ),
                ),
            ),
            (
                "workflows_withheld constant",
                lambda: piguard.workflows_withheld_finding(),
            ),
            (
                "named_repo none",
                lambda: piguard.probe_named_repo(None, self.TOKEN),
            ),
            (
                "named_repo malformed",
                lambda: piguard.probe_named_repo("oops", self.TOKEN),
            ),
            (
                "named_repo 404",
                lambda: piguard.probe_named_repo(
                    self.OTHER_REPO,
                    self.TOKEN,
                    _opener(
                        urllib.error.HTTPError(
                            other_url, 404, "Not Found", None, None
                        )
                    ),
                ),
            ),
            (
                "named_repo 200",
                lambda: piguard.probe_named_repo(
                    self.OTHER_REPO,
                    self.TOKEN,
                    _opener(_FakeResponse(b'{"full_name": "someorg/other"}', 200)),
                ),
            ),
            (
                "named_repo 403",
                lambda: piguard.probe_named_repo(
                    self.OTHER_REPO,
                    self.TOKEN,
                    _opener(
                        urllib.error.HTTPError(
                            other_url, 403, "Forbidden", None, None
                        )
                    ),
                ),
            ),
        )
        for label, call in probe_calls:
            for finding in call():
                findings.append(
                    (
                        "{}: {} on check {!r}".format(
                            label,
                            _field(finding, "status"),
                            _field(finding, "check"),
                        ),
                        finding,
                    )
                )
        for finding in piguard.check_token_all(
            self.OWNER,
            self.REPO,
            token=self.TOKEN,
            other_repo=self.OTHER_REPO,
            opener=_opener(_FakeResponse(b'{"ok": true}', 200)),
        ):
            findings.append(
                (
                    "check_token_all: {} on check {!r}".format(
                        _field(finding, "status"), _field(finding, "check")
                    ),
                    finding,
                )
            )
        return findings

    def test_every_emittable_finding_carries_a_brief(self):
        findings = self._every_brief_finding()

        self.assertGreaterEqual(
            len(findings),
            20,
            "fixture sanity: the sweep must cover the twenty emittable "
            "findings, got {}".format(len(findings)),
        )
        self.assertEqual(
            {_field(f, "check") for _label, f in findings},
            {
                "history_rewrite",
                "review",
                "update_restriction",
                "file_paths",
                "target_access",
                "administration",
                "classic_token",
                "workflows_withheld",
                "named_repo",
            },
            "fixture sanity: the sweep must cover every emitting check",
        )
        for label, finding in findings:
            with self.subTest(finding=label):
                self._assert_brief_shape(finding, label)

    # ------------------------------------------------------------------
    # Behaviour 2 of plans/guard-finding-compact.md: short danger, reason
    # and remedy
    # ------------------------------------------------------------------

    def _assert_short_field_shape(
        self, value: Any, label: str, allow_long: bool = False
    ) -> None:
        """The shape a non-empty danger/reason/remedy must carry.

        ``allow_long`` lifts only the 100-character length bound; every
        other assertion (single sentence, no doc path, no 'see:' clause)
        still applies. It exists for the one reason this module passes
        through but does not own: the no-origin reason is built in
        anvilkit.cli._collect_guard_findings (not here), pinned word-for-word
        in tests/test_cli.py - including the noun invariant "the project has
        no origin" - and it is ~173 chars because it names the target path
        and the full resolution failure. It is never printed inside a finding
        block (the headline carries the brief), so the 100-char bound - which
        exists to keep a block line short - does not apply to it.
        """
        self.assertIsInstance(
            value,
            str,
            "{}: the field must be a string, got {!r}".format(label, value),
        )
        if not allow_long:
            self.assertLessEqual(
                len(value),
                100,
                "{}: the field must be a single sentence of at most 100 "
                "characters, got {} characters: {!r}".format(
                    label, len(value), value
                ),
            )
        self.assertNotIn(
            ". ",
            value,
            "{}: the field must be a single sentence - a sentence break "
            "inside it: {!r}".format(label, value),
        )
        self.assertNotIn(
            "doc/external/",
            value,
            "{}: the field must carry no doc path: {!r}".format(label, value),
        )
        self.assertNotIn(
            "see:",
            value,
            "{}: the field must carry no 'see:' clause: "
            "{!r}".format(label, value),
        )

    def test_every_emittable_finding_danger_reason_and_remedy_are_short(self):
        """Behaviour 2: every emittable danger/reason/remedy is one short
        sentence with no doc path and no 'see:' clause.

        One documented exemption: the no-origin *reason* is exempt from the
        100-char length bound only (see _assert_short_field_shape). It is
        built and pinned verbatim in
        anvilkit.cli._collect_guard_findings / tests/test_cli.py - including
        the noun invariant "the project has no origin" - and is passed through
        skipped_findings untouched. It is never printed inside a finding block
        (the headline carries the brief), so the bound that exists to keep a
        block line short does not apply to it. Every other assertion on that
        subtest (no doc path, no 'see:' clause, single sentence) still
        applies, and the remedy is still pinned.
        """
        findings = self._every_brief_finding()
        for label, finding in findings:
            with self.subTest(finding=label):
                status = _field(finding, "status")
                danger = _field(finding, "danger")
                reason = _field(finding, "reason")
                remedy = _field(finding, "remedy")

                # danger: a single short sentence, no doc path, and never
                # the bypass caveat - the caveat is printed once as the
                # trailing note, not repeated per finding.
                if isinstance(danger, str) and danger:
                    self._assert_short_field_shape(
                        danger, "{}: danger".format(label)
                    )
                    self.assertNotIn(
                        "bypass",
                        danger,
                        "{}: the danger must not carry the bypass caveat "
                        "- it is printed once as the trailing note: "
                        "{!r}".format(label, danger),
                    )

                # reason: present only on a skipped finding, and then a
                # single short sentence with no doc path.
                if isinstance(reason, str) and reason:
                    self.assertEqual(
                        status,
                        "skipped",
                        "{}: a reason is only carried by a skipped "
                        "finding".format(label),
                    )
                    # The no-origin reason is CLI-owned and pinned verbatim
                    # in tests/test_cli.py (the noun invariant "the project
                    # has no origin"), so it is exempt from the 100-char
                    # length bound only - see the helper's docstring.
                    self._assert_short_field_shape(
                        reason,
                        "{}: reason".format(label),
                        allow_long=("has no origin" in reason),
                    )

                # remedy: a single short sentence with no doc path and no
                # 'see:' clause; non-empty on every non-passing finding,
                # and may be empty on a passed one now that nothing prints
                # it.
                if isinstance(remedy, str) and remedy:
                    self._assert_short_field_shape(
                        remedy, "{}: remedy".format(label)
                    )
                if status != "passed":
                    self.assertTrue(
                        remedy,
                        "{}: a non-passing finding ({}) must still carry a "
                        "non-empty remedy (the module invariant)".format(
                            label, status
                        ),
                    )


if __name__ == "__main__":
    unittest.main()
