"""Tests for anvilkit.piguard - GitHub ruleset guard checks (behaviours 1-4).

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
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

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


class _FakeResponse:
    """A minimal urlopen response: readable and usable as a context manager."""

    def __init__(self, body: bytes, status: int = 200) -> None:
        self._body = body
        self.status = status

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


class _SkippedAssertions:
    """Mixin of shared assertions on what a failed fetch must turn into.

    Deliberately a plain mixin, not a ``unittest.TestCase``: only the
    concrete test classes inherit ``unittest.TestCase`` (with this mixin
    second, for the assertion methods), which is what the test loader
    looks for when discovering tests.

    Behaviour 4 of plans/pi-guard-verification.md: a check that cannot run
    yields a ``skipped`` finding carrying the reason - never ``passed``,
    never an exception. One skipped finding per defined check, each with a
    non-empty reason and a non-empty remedy (behaviour 5 invariant: a
    finding that cannot say what the user can do to make the check runnable
    is a programming error).
    """

    def _assert_skipped_findings(self, findings: Any, reason: str) -> None:
        self.assertIsInstance(findings, list)
        checks = [_field(f, "check") for f in findings]
        self.assertEqual(
            checks.count("history_rewrite"),
            1,
            "exactly one skipped finding expected for the history_rewrite check",
        )
        self.assertEqual(
            checks.count("review"),
            1,
            "exactly one skipped finding expected for the review check",
        )
        self.assertEqual(
            [_field(f, "status") for f in findings],
            ["skipped", "skipped"],
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
            "anvilkit.piguard.fetch_branch_rules is not callable; the rules "
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


class SkippedFindingsTests(unittest.TestCase, _SkippedAssertions):
    """Behaviour 4 (rendering half): a skipped finding is visually distinct from a pass.

    ``skipped_findings(reason)`` yields one ``skipped`` finding per defined
    check (history_rewrite, review), each carrying the reason and a remedy
    naming what the user can do to make the check runnable.
    ``render_finding`` already carries the reason for a skipped finding; the
    rendered line must say the check could not run - never a passed-style
    ``ok:`` prefix.
    """

    def _skipped_findings(self) -> Any:
        producer = getattr(piguard, "skipped_findings", None)
        self.assertTrue(
            callable(producer),
            "anvilkit.piguard.skipped_findings is not callable; the "
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


if __name__ == "__main__":
    unittest.main()
