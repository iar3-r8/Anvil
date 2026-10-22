"""Checks over GitHub branch rules, returning findings.

Two jobs, in one pipeline. First, :func:`fetch_branch_rules` performs the
``GET /repos/{owner}/{repo}/rules/branches/{branch}`` request and translates
every network or payload failure into a ``reason`` - it never raises, and a
missing token is not a skip, only an unauthenticated attempt: the endpoint
allows that on public repositories. Second, the check functions interpret the
JSON array and report, per rule type, whether a guard is present; a check
that could not run becomes a ``skipped`` finding via
:func:`skipped_findings`, never a pass.

The module never writes and never calls ``sys.exit``. Every finding it can
emit carries a non-empty ``remedy``: a finding that cannot say how to fix the
danger - or make the check runnable - is a programming error, not a result.
"""

import json
import socket
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

CHECK_HISTORY_REWRITE = "history_rewrite"
CHECK_REVIEW = "review"

# The rules endpoint lives on the API host, not the web host. Two GETs per
# run, run rarely, so no caching (plans/pi-guard-verification.md).
_RULES_API_BASE = "https://api.github.com"

# Generous on purpose: a slow GitHub must not turn a live check into a
# skipped one (plans/pi-guard-verification.md, Assumptions).
DEFAULT_RULES_TIMEOUT = 10.0

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

# What an agent could do while a check is unmeasured, per check: the
# specific reason names why the check did not run, the danger names the
# hole the report cannot rule out. A skipped finding carries both, so it
# stands on its own rather than leaning on the renderer.
_SKIPPED_DANGERS = {
    CHECK_HISTORY_REWRITE: (
        "whether the branch history can be rewritten by a force push, or "
        "the branch itself deleted, is unmeasured: an agent could do "
        "either with no gate, and this report cannot rule it out"
    ),
    CHECK_REVIEW: (
        "whether an agent's change can land on the branch unreviewed is "
        "unmeasured: a push could go straight to the branch, and this "
        "report cannot rule it out"
    ),
}


def fetch_branch_rules(
    owner: str,
    repo: str,
    branch: str,
    token: Optional[str] = None,
    opener: Optional[Callable[..., Any]] = None,
    timeout: Optional[float] = DEFAULT_RULES_TIMEOUT,
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """Fetch the active rules for ``branch``; never raises.

    Builds ``GET {api}/repos/{owner}/{repo}/rules/branches/{branch}`` with
    ``Accept: application/vnd.github+json``. A ``token`` adds the
    ``Authorization`` header; without one the request goes out
    unauthenticated, which the endpoint allows on public repositories - a
    missing token is therefore not a skip, only an actual request failure
    is (plans/pi-guard-verification.md, Assumptions).

    Returns ``(rules, None)`` on a 200 whose body is a JSON array, and
    ``(None, reason)`` on a ``URLError``, a timeout (including a
    ``socket.timeout`` wrapped in a ``URLError``), an ``HTTPError``, or a
    non-JSON body. A network timeout is a skipped, not a fail: a slow
    GitHub must not make a provisioning command unusable.

    ``opener`` defaults to ``urllib.request.urlopen``; tests inject a
    recorded opener, so the suite never touches the live network.
    """
    if opener is None:
        opener = urllib.request.urlopen
    if timeout is None:
        timeout = DEFAULT_RULES_TIMEOUT

    url = "{}/repos/{}/{}{}/rules/branches/{}".format(
        _RULES_API_BASE, owner, repo, "", branch
    )
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = "Bearer {}".format(token)
    request = urllib.request.Request(url, headers=headers)

    try:
        with opener(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            # Rulesets are unavailable on private repos under GitHub Free,
            # so a 404 may be a plan limit, not a misconfiguration
            # (doc/external/github/available-rules-for-rulesets.md). Name
            # the situation; do not accuse whoever is reading the report.
            return None, (
                "GitHub returned 404 for the branch rules of {}/{} "
                "({}): rulesets are unavailable on private repos under "
                "GitHub Free, so this may be a plan limit rather than a "
                "misconfiguration; see {}".format(
                    owner, repo, url, _RULES_DOC
                )
            )
        return None, "GitHub returned HTTP {} for {}".format(exc.code, url)
    except socket.timeout as exc:
        return None, (
            "timed out after {}s contacting {}".format(timeout, url)
        )
    except urllib.error.URLError as exc:
        # URLError wraps the real cause, including socket.timeout on some
        # versions (same pattern as anvilkit/health.py).
        if isinstance(exc.reason, socket.timeout):
            return None, "timed out after {}s contacting {}".format(timeout, url)
        return None, "GitHub was unreachable for {}: {}".format(url, exc.reason)
    except OSError as exc:
        return None, "GitHub was unreachable for {}: {}".format(url, exc)

    try:
        payload = json.loads(body)
    except ValueError as exc:
        return None, "GitHub returned a non-JSON body for {}: {}".format(url, exc)
    if not isinstance(payload, list):
        return None, (
            "GitHub returned a JSON body that is not a rules array for "
            "{}: expected a list".format(url)
        )
    return payload, None


def skipped_findings(reason: str) -> List[Dict[str, Any]]:
    """One ``skipped`` finding per defined check, in report order.

    A check that could not run - a failed or unreadable fetch - must never
    count toward a clean report, so each defined check gets its own
    ``skipped`` finding carrying ``reason`` (why it did not run), a
    non-empty ``danger`` naming the unmeasured hole the report cannot rule
    out, and a non-empty ``remedy`` naming what makes the check runnable
    again (behaviours 4 and 5). ``render_finding`` renders the ``reason``
    field for skipped lines; the finding stands on its own either way.
    """
    findings = []
    for check in (CHECK_HISTORY_REWRITE, CHECK_REVIEW):
        findings.append(
            {
                "status": "skipped",
                "check": check,
                "rule": None,
                "danger": _SKIPPED_DANGERS[check],
                "source": None,
                "reason": reason,
                "remedy": (
                    "make the rules endpoint reachable and readable - "
                    "check network access to api.github.com and, for "
                    "private repos, a token with Metadata read - then re-"
                    "run; endpoint in {}".format(_ENDPOINT_DOC)
                ),
            }
        )
    return findings


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
