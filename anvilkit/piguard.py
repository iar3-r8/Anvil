"""Pure checks over GitHub branch rules, returning findings.

The module's single job: interpret the JSON array returned by
``GET /repos/{owner}/{repo}/rules/branches/{branch}`` and report, per rule
type, whether a guard is present. It never touches the network, never writes,
and never calls ``sys.exit`` — a check that cannot run is reported by its
caller as ``skipped``; this module only judges what it is handed.

Every finding it can emit carries a non-empty ``remedy``: a finding that
cannot say how to fix the danger is a programming error, not a result.
"""

from typing import Any, Dict, List

CHECK_HISTORY_REWRITE = "history_rewrite"
CHECK_REVIEW = "review"

# The API rule types the history-rewrite guard looks for, in report order.
# These are the API names, not the UI labels: the endpoint returns
# 'non_fast_forward' for what the UI calls "Block force pushes".
_HISTORY_REWRITE_RULES = ("non_fast_forward", "deletion")

# Cited by every finding so a reviewer can check each claim against the
# saved endpoint documentation.
_ENDPOINT_DOC = "doc/external/github/rest-api-endpoints-for-rules.md"
_RULES_DOC = "doc/external/github/available-rules-for-rulesets.md"

# What an agent could do if each rule is absent: the consequence, not the
# mechanism, stated first.
_DANGERS = {
    "non_fast_forward": (
        "branch history can be rewritten by a force push: commits that "
        "survived review can be replaced or erased, unrecoverably, with no "
        "review gate"
    ),
    "deletion": (
        "the branch itself can be deleted unrecoverably, taking its whole "
        "history with it, with no review gate"
    ),
    "pull_request": (
        "an agent's change can land on the branch unreviewed: a push goes "
        "straight to the branch, with no review gate"
    ),
}


def check_history_rewrite(rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One finding per history-rewrite rule: passed if active, warn if not.

    ``rules`` is the parsed body of
    ``GET /repos/{owner}/{repo}/rules/branches/{branch}``: a list, and only
    ``type`` and ``ruleset_source`` of each element are read. A rule present
    yields a ``passed`` finding naming the rule's API type and its
    ``ruleset_source``; a rule absent yields a ``warn`` finding naming the
    danger and a concrete fix. An empty list warns on every rule checked.
    """
    active: Dict[str, Any] = {}
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rule_type = rule.get("type")
        if isinstance(rule_type, str) and rule_type not in active:
            active[rule_type] = rule.get("ruleset_source")

    findings = []
    for rule_type in _HISTORY_REWRITE_RULES:
        if rule_type in active:
            findings.append(
                {
                    "status": "passed",
                    "check": CHECK_HISTORY_REWRITE,
                    "rule": rule_type,
                    "danger": "",
                    "source": _or_unknown(active[rule_type]),
                    "remedy": (
                        "nothing to do - the {!r} rule is active for this "
                        "branch; see {}".format(rule_type, _RULES_DOC)
                    ),
                }
            )
        else:
            findings.append(
                {
                    "status": "warn",
                    "check": CHECK_HISTORY_REWRITE,
                    "rule": rule_type,
                    "danger": _DANGERS[rule_type],
                    "source": None,
                    "remedy": (
                        "add a {!r} rule to a ruleset covering this branch: "
                        "rule semantics in {}, endpoint in {}".format(
                            rule_type, _RULES_DOC, _ENDPOINT_DOC
                        )
                    ),
                }
            )

    return findings


def check_review(rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One review finding: passed if ``pull_request`` is active, warn if not.

    ``rules`` is the parsed body of
    ``GET /repos/{owner}/{repo}/rules/branches/{branch}``: a list, and only
    ``type``, ``ruleset_source`` and ``parameters`` of a ``pull_request``
    element are read. A rule present yields a ``passed`` finding naming the
    rule's API type and its ``ruleset_source``, with
    ``parameters.required_approving_review_count`` recorded on the finding -
    zero approvals is a weaker guard than the name suggests, and the report
    must show it. A rule absent yields a ``warn`` finding naming the danger
    (a change can land unreviewed) and a concrete fix.
    """
    rule = None
    for candidate in rules:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("type") == "pull_request":
            rule = candidate
            break

    if rule is None:
        return [
            {
                "status": "warn",
                "check": CHECK_REVIEW,
                "rule": "pull_request",
                "danger": _DANGERS["pull_request"],
                "source": None,
                "remedy": (
                    "add a 'pull_request' rule to a ruleset covering this "
                    "branch: rule semantics in {}, endpoint in {}".format(
                        _RULES_DOC, _ENDPOINT_DOC
                    )
                ),
            }
        ]

    parameters = rule.get("parameters")
    if not isinstance(parameters, dict):
        parameters = {}
    count = parameters.get("required_approving_review_count")
    return [
        {
            "status": "passed",
            "check": CHECK_REVIEW,
            "rule": "pull_request",
            "danger": "",
            "source": _or_unknown(rule.get("ruleset_source")),
            "required_approving_review_count": count,
            "remedy": (
                "nothing to do - the 'pull_request' rule is active for this "
                "branch, requiring {} approving review(s); see {}".format(
                    count, _RULES_DOC
                )
            ),
        }
    ]


def render_finding(finding: Dict[str, Any]) -> str:
    """One human-readable line per finding; no network, no exit.

    A ``passed`` line names the rule's API type and states that the rule
    is present - plus the caveat that ``bypass_actors`` is only returned
    to users with write access to the ruleset, so on a read-only token the
    branch must never be called simply "protected": an unseen bypass entry
    is an unmeasured hole. A passed review finding also keeps its recorded
    ``required_approving_review_count`` visible. A ``warn`` line names the
    danger and the remedy. A ``skipped`` line carries the reason the check
    could not run.
    """
    rule = finding.get("rule")
    status = finding.get("status")
    if status == "passed":
        line = (
            "ok: the {} rule is present - but the bypass list is not "
            "visible on a read-only token (bypass_actors is only returned "
            "to users with write access to the ruleset)".format(rule)
        )
        count = finding.get("required_approving_review_count")
        if count is not None:
            line += " ({} required approvals)".format(count)
        return line
    if status == "warn":
        return "warn: {} - {}; fix: {}".format(
            rule, finding.get("danger"), finding.get("remedy")
        )
    if status == "skipped":
        reason = (
            finding.get("reason")
            or finding.get("danger")
            or "no reason recorded"
        )
        return "skipped: {} check could not run: {}".format(
            finding.get("check"), reason
        )
    return "unknown: {} finding for rule {}".format(status, rule)


def _or_unknown(value: Any) -> str:
    """A ruleset_source is expected on every active rule; name the gap if not."""
    if isinstance(value, str) and value:
        return value
    return "unknown"
