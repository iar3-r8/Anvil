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


def _or_unknown(value: Any) -> str:
    """A ruleset_source is expected on every active rule; name the gap if not."""
    if isinstance(value, str) and value:
        return value
    return "unknown"
