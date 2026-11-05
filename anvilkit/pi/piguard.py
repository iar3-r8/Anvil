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
import re
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

CHECK_HISTORY_REWRITE = "history_rewrite"
CHECK_REVIEW = "review"
CHECK_UPDATE_RESTRICTION = "update_restriction"
CHECK_FILE_PATHS = "file_paths"

# The token-scope probe's check name (behaviour 2 of
# plans/verify-guards-token.md).
CHECK_TARGET_ACCESS = "target_access"

# The administration probe's check name (behaviour 3 of
# plans/verify-guards-token.md).
CHECK_ADMINISTRATION = "administration"

# The classic-token probe's check name (behaviour 4 of
# plans/verify-guards-token.md).
CHECK_CLASSIC_TOKEN = "classic_token"

# The check name for the workflows-withheld finding (behaviour 5 of
# plans/verify-guards-token.md): the documented-unprovable case, one
# constant finding per run, not one per repo or per probe.
CHECK_WORKFLOWS_WITHHELD = "workflows_withheld"

# The rules endpoint lives on the API host, not the web host. Two GETs per
# run, run rarely, so no caching (plans/pi-guard-verification.md).
_RULES_API_BASE = "https://api.github.com"

# Generous on purpose: a slow GitHub must not turn a live check into a
# skipped one (plans/pi-guard-verification.md, Assumptions).
DEFAULT_RULES_TIMEOUT = 10.0

# The X-GitHub-Api-Version the saved probe-endpoint docs pin, sent by the
# token-scope probes. A new constant on purpose: fetch_branch_rules
# predates those docs and sends no version header, and its existing header
# behaviour is untouched (doc/external/github/rest-api-endpoints-for-
# actions-permissions.md, doc/external/github/rest-api-endpoints-for-users.md).
_PROBE_API_VERSION = "2026-03-10"

# The API rule types the history-rewrite guard looks for, in report order.
# These are the API names, not the UI labels: the endpoint returns
# 'non_fast_forward' for what the UI calls "Block force pushes".
_HISTORY_REWRITE_RULES = ("non_fast_forward", "deletion")

# Cited by every finding so a reviewer can check each claim against the
# saved endpoint documentation.
_ENDPOINT_DOC = "doc/external/github/rest-api-endpoints-for-rules.md"
_RULES_DOC = "doc/external/github/available-rules-for-rulesets.md"

# Cited by the target-access probe's findings. No saved page documents
# GET /repos/{owner}/{repo}'s access semantics directly, so the probe cites
# the nearest saved page: it documents that a fine-grained token reaches
# only the repositories selected at creation, which is exactly what a 404
# on the target repo tells the report reader.
_FINE_GRAINED_DOC = "doc/external/github/fine-grained-personal-access-tokens.md"

# Cited by the administration probe's findings. It documents that the
# endpoint requires Administration repository permissions (read) and
# documents only 200 - the denial code is not stated - which is exactly
# what makes a 404 there ambiguous (behaviour 3).
_ACTIONS_PERMISSIONS_DOC = (
    "doc/external/github/rest-api-endpoints-for-actions-permissions.md"
)

# Cited by the workflows-withheld finding. It documents that the
# workflows list endpoint requires "Actions" repository permissions
# (read) - not the workflows permission - and that it works
# unauthenticated on public repos, so a 200 proves nothing about the
# token (behaviour 5).
_WORKFLOWS_DOC = "doc/external/github/rest-api-endpoints-for-workflows.md"

# Cited by the classic-token probe's findings. It documents that a token's
# scope list is the X-OAuth-Scopes response header and that scopes are
# normalized - which is exactly why the probe's discriminator is a
# non-empty header, never an exact scope string (behaviour 4).
_OAUTH_SCOPES_DOC = "doc/external/github/scopes-for-oauth-apps.md"

# What an agent could do while the target access is unmeasured: the skipped
# finding carries it so it stands on its own rather than leaning on the
# renderer (the _SKIPPED_DANGERS pattern).
_TARGET_ACCESS_SKIP_DANGER = (
    "whether the token can reach the target repository at all is "
    "unmeasured: no later probe's denial can be read as a withholding, "
    "and this report cannot rule out that the probes ran against a "
    "repository the token never had"
)

# The same, for the administration probe: the unmeasured hole is that the
# token may hold Administration (read) on the target.
_ADMINISTRATION_SKIP_DANGER = (
    "whether the token holds Administration (read) on the target is "
    "unmeasured: this report cannot rule out that the token can delete or "
    "reconfigure the repository and raise the default GITHUB_TOKEN "
    "permissions to write"
)

# The same, for the classic-token probe: the unmeasured hole is that the
# token may be classic, in which case it reaches every repository the
# owner can see.
_CLASSIC_TOKEN_SKIP_DANGER = (
    "whether the token is classic is unmeasured: a classic token grants "
    "access to every repository the owner can see, so the repo-scope "
    "guarantee may be void, and this report cannot rule it out"
)

# The same, for the workflows-withheld finding: the unmeasured hole is
# that the token may hold the workflows permission (write only), which
# is the documented privilege-escalation path - editing the CI
# workflows the agent's own runs flow through (behaviour 5).
_WORKFLOWS_WITHHELD_SKIP_DANGER = (
    "whether the workflows permission is withheld is unmeasured: the "
    "token may be able to edit CI workflows on the target - the "
    "documented privilege-escalation path - and no read-only call can "
    "rule it out"
)

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
    "update": (
        "anyone with push access can push straight to the branch, with no "
        "gate: the update rule would restrict ref updates to users with "
        "bypass permission, and without it ordinary pushes are all that "
        "stands between a ref and a rewrite"
    ),
    "file_path_restriction": (
        "a push can change the restricted file paths - "
        ".github/workflows/**, what CI runs - with no gate: the rule "
        "would prevent commits that include changes in those paths from "
        "being pushed to the commit graph, and without it an agent's "
        "change lands on them directly"
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
    CHECK_UPDATE_RESTRICTION: (
        "whether updates to the branch are restricted to users with "
        "bypass permission is unmeasured: without the 'update' rule, "
        "anyone with push access can push straight to the branch, with "
        "no gate, and this report cannot rule it out"
    ),
    CHECK_FILE_PATHS: (
        "whether the restricted file paths - .github/workflows/**, what "
        "CI runs - are protected from pushes is unmeasured: without the "
        "'file_path_restriction' rule, a push can change them, with no "
        "gate, and this report cannot rule it out"
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


def fetch_probe(
    url: str,
    token: Optional[str] = None,
    opener: Optional[Callable[..., Any]] = None,
    timeout: Optional[float] = None,
) -> Tuple[Optional[int], Optional[Any], Optional[bytes], Optional[str]]:
    """Issue one read-only GET and observe the answer; never raises.

    The fetch seam for the token-scope probes (behaviour 1 of
    plans/verify-guards-token.md): builds a ``GET`` for ``url`` with
    ``Accept: application/vnd.github+json`` and
    ``X-GitHub-Api-Version`` pinned to the version the saved probe-endpoint
    docs use (doc/external/github/rest-api-endpoints-for-actions-permissions.
    md and doc/external/github/rest-api-endpoints-for-users.md) and opens it
    through ``opener``, which defaults to ``urllib.request.urlopen``. A
    ``token`` adds the ``Authorization: Bearer <token>`` header - the same
    shape :func:`fetch_branch_rules` builds - and without one the request
    goes out with no ``Authorization`` header at all. That contrast is the
    point: in :func:`fetch_branch_rules` a missing token is an
    unauthenticated attempt the endpoint allows, whereas a probe is meant to
    measure a token's scope, so this function simply sends what it is given
    and decides nothing - a fact about a token cannot be established without
    one, and that judgement belongs to the probes, not the fetch.

    An ``HTTPError`` is a **successful observation**: its ``code`` and
    ``headers`` are returned with ``reason=None``, because a ``403`` is the
    compliant answer to a token-scope probe - a denial is the data. Only
    transport-level failures - a ``URLError``, a ``socket.timeout``, a bare
    ``OSError`` - yield ``(None, None, None, reason)`` with a non-empty
    reason string; this function never raises.

    Returns ``(status, headers, body, reason)``: the response's status code
    (``getcode``), its headers, its body as raw bytes - the probes inspect
    headers and, where they parse, decode - and ``None`` on any HTTP answer,
    or the three ``None``s with the reason string on a transport failure.
    The reason never carries the token.

    ``opener`` is the injection seam: tests pass a recorded opener, so the
    suite never touches the live network. ``timeout`` is passed through to
    the opener unchanged.
    """
    if opener is None:
        opener = urllib.request.urlopen

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _PROBE_API_VERSION,
    }
    if token:
        headers["Authorization"] = "Bearer {}".format(token)
    request = urllib.request.Request(url, headers=headers)

    try:
        with opener(request, timeout=timeout) as response:
            status = response.getcode()
            resp_headers = dict(response.headers)
            body = response.read()
    except urllib.error.HTTPError as exc:
        # An HTTPError is a successful observation, not a failure: a 403 is
        # the compliant answer to a probe, so return the status and headers
        # as data. exc.hdrs is the attribute HTTPError always sets, even
        # when no response body was captured (exc.headers is only present
        # when one was).
        body: Optional[bytes]
        try:
            body = exc.read()
        except Exception:
            body = None
        # exc.hdrs is None when no response headers were captured.
        return exc.code, dict(exc.hdrs) if exc.hdrs is not None else {}, body, None
    except socket.timeout as exc:
        return None, None, None, "probe timed out contacting {}: {}".format(url, exc)
    except urllib.error.URLError as exc:
        # URLError wraps the real cause, including socket.timeout on some
        # versions (same pattern as fetch_branch_rules and
        # anvilkit/health.py).
        reason = exc.reason
        if isinstance(reason, socket.timeout):
            return None, None, None, "probe timed out contacting {}".format(url)
        return None, None, None, "probe could not reach {}: {}".format(url, reason)
    except OSError as exc:
        return None, None, None, "probe could not reach {}: {}".format(url, exc)

    return status, resp_headers, body, None


def probe_target_access(
    owner: str,
    repo: str,
    token: Optional[str] = None,
    opener: Optional[Callable[..., Any]] = None,
    timeout: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """The first token-scope probe: does the token reach the target repo at all?

    Issues ``GET /repos/{owner}/{repo}`` through :func:`fetch_probe`
    (behaviour 1 of plans/verify-guards-token.md) - one probe, one API call -
    and interprets the observation:

    - ``200`` -> one ``passed`` finding: the target is reachable, so a later
      probe's denial can be read as a withholding.
    - ``404`` -> one ``warn`` finding: the token cannot reach the target repo
      at all, so no other probe's denial can be read as a withholding - an
      under-scoped token and an unreachable target look identical on every
      other probe, and this finding is the disambiguator.
    - ``401`` or any other status -> one ``skipped`` finding whose reason
      carries the status.
    - a transport reason from :func:`fetch_probe` -> one ``skipped`` finding
      with a non-empty reason.

    This probe differs from :func:`fetch_branch_rules` in what a missing
    token means: there, a missing token is an unauthenticated attempt the
    endpoint allows on public repositories; here, a missing token is a
    **skip** - no request is attempted at all - because a token-scope probe
    reads a token's property, and an unauthenticated request establishes no
    fact about any token (behaviour 7).

    The 404 remedy cites ``doc/external/github/fine-grained-personal-access-
    tokens.md`` - the nearest saved page, which documents that a fine-grained
    token reaches only the repositories selected at creation; no saved page
    documents ``GET /repos/{owner}/{repo}``'s access semantics directly.

    Never raises; always returns a list of findings. Never echoes a token
    into a finding or a reason (module invariant).
    """
    target = "{}/{}".format(owner, repo)
    url = "{}/repos/{}/{}".format(_RULES_API_BASE, owner, repo)
    skipped_remedy = (
        "make the token valid and scoped to {} and api.github.com "
        "reachable, then re-run; see {}".format(target, _FINE_GRAINED_DOC)
    )

    if not token:
        return [
            {
                "status": "skipped",
                "check": CHECK_TARGET_ACCESS,
                "rule": None,
                "danger": _TARGET_ACCESS_SKIP_DANGER,
                "source": None,
                "reason": (
                    "no token supplied: a token-scope probe with no token "
                    "establishes no fact about any token, so the probe "
                    "skips rather than issuing an unauthenticated request "
                    "and reading its status as a token property - unlike "
                    "fetch_branch_rules, where a missing token is an "
                    "unauthenticated attempt"
                ),
                "remedy": skipped_remedy,
            }
        ]

    status, _headers, _body, reason = fetch_probe(
        url, token, opener=opener, timeout=timeout
    )

    if reason is not None:
        return [
            {
                "status": "skipped",
                "check": CHECK_TARGET_ACCESS,
                "rule": None,
                "danger": _TARGET_ACCESS_SKIP_DANGER,
                "source": None,
                "reason": reason,
                "remedy": skipped_remedy,
            }
        ]

    if status == 200:
        return [
            {
                "status": "passed",
                "check": CHECK_TARGET_ACCESS,
                "rule": None,
                "danger": "",
                "source": None,
                "remedy": (
                    "nothing to do - the token reaches {}, so later probes' "
                    "denials are interpretable; see {}".format(
                        target, _FINE_GRAINED_DOC
                    )
                ),
            }
        ]

    if status == 404:
        return [
            {
                "status": "warn",
                "check": CHECK_TARGET_ACCESS,
                "rule": None,
                "danger": (
                    "the token cannot reach {} at all, so no other probe's "
                    "denial can be read as a withholding: an under-scoped "
                    "token and an unreachable target look identical on "
                    "every other probe".format(target)
                ),
                "source": None,
                "remedy": (
                    "recreate the token with Repository access "
                    "'Only select repositories' including {}; see "
                    "{}".format(target, _FINE_GRAINED_DOC)
                ),
            }
        ]

    return [
        {
            "status": "skipped",
            "check": CHECK_TARGET_ACCESS,
            "rule": None,
            "danger": _TARGET_ACCESS_SKIP_DANGER,
            "source": None,
            "reason": "GitHub returned HTTP {} for {}".format(status, url),
            "remedy": skipped_remedy,
        }
    ]


def probe_administration(
    owner: str,
    repo: str,
    token: Optional[str] = None,
    opener: Optional[Callable[..., Any]] = None,
    timeout: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """The second token-scope probe: does the token hold Administration on the target?

    Issues ``GET /repos/{owner}/{repo}/actions/permissions`` through
    :func:`fetch_probe` (behaviour 1 of plans/verify-guards-token.md) - one
    probe, one API call - and interprets the observation. The saved page
    doc/external/github/rest-api-endpoints-for-actions-permissions.md
    documents the endpoint as gated on **Administration repository
    permissions (read)** and documents **only ``200``** - the denial code is
    not stated - so a ``403`` is read as the withholding and a ``404`` is
    left ambiguous:

    - ``403`` -> one ``passed`` finding: administration is withheld - the
      compliant answer, because a fine-grained token created per the recipe
      has no ``administration`` permission.
    - ``200`` -> one ``fail`` finding - the first emittable ``fail`` in the
      module: the token holds ``administration: read`` on the target, so the
      repository can be deleted or reconfigured and the default
      ``GITHUB_TOKEN`` permissions raised to write (the plan's danger
      wording, per the saved page). The finding carries a non-empty danger
      (the consequence first) and a non-empty remedy citing the saved page.
    - ``404`` -> one ``warn`` finding: the page documents only ``200``, so a
      404 is ambiguous between "administration withheld" and "no access at
      all" - the finding names the target-access probe
      (:func:`probe_target_access`, :data:`CHECK_TARGET_ACCESS`) as the
      disambiguator.
    - ``401`` or any other status -> one ``skipped`` finding whose reason
      carries the status.
    - a transport reason from :func:`fetch_probe` -> one ``skipped`` finding
      with a non-empty reason.

    Like :func:`probe_target_access`, a missing or empty token is a
    **skip** - no request is attempted at all - because a token-scope probe
    reads a token's property, and an unauthenticated request establishes no
    fact about any token (behaviour 7).

    Never raises; always returns a list of findings. Never echoes a token
    into a finding or a reason (module invariant).
    """
    target = "{}/{}".format(owner, repo)
    url = "{}/repos/{}/{}/actions/permissions".format(
        _RULES_API_BASE, owner, repo
    )
    skipped_remedy = (
        "make the token valid and scoped to {}, and api.github.com "
        "reachable, then re-run; see {}".format(
            target, _ACTIONS_PERMISSIONS_DOC
        )
    )

    if not token:
        return [
            {
                "status": "skipped",
                "check": CHECK_ADMINISTRATION,
                "rule": None,
                "danger": _ADMINISTRATION_SKIP_DANGER,
                "source": None,
                "reason": (
                    "no token supplied: a token-scope probe with no token "
                    "establishes no fact about any token, so the probe "
                    "skips rather than issuing an unauthenticated request "
                    "and reading its status as a token property - unlike "
                    "fetch_branch_rules, where a missing token is an "
                    "unauthenticated attempt"
                ),
                "remedy": skipped_remedy,
            }
        ]

    status, _headers, _body, reason = fetch_probe(
        url, token, opener=opener, timeout=timeout
    )

    if reason is not None:
        return [
            {
                "status": "skipped",
                "check": CHECK_ADMINISTRATION,
                "rule": None,
                "danger": _ADMINISTRATION_SKIP_DANGER,
                "source": None,
                "reason": reason,
                "remedy": skipped_remedy,
            }
        ]

    if status == 403:
        return [
            {
                "status": "passed",
                "check": CHECK_ADMINISTRATION,
                "rule": None,
                "danger": "",
                "source": None,
                "remedy": (
                    "nothing to do - a 403 means Administration is "
                    "withheld on {}, the compliant answer for a "
                    "fine-grained token created without the permission; "
                    "see {}".format(target, _ACTIONS_PERMISSIONS_DOC)
                ),
            }
        ]

    if status == 200:
        return [
            {
                "status": "fail",
                "check": CHECK_ADMINISTRATION,
                "rule": None,
                "danger": (
                    "the token holds Administration (read) on {}: the "
                    "repository can be deleted or reconfigured, and the "
                    "default GITHUB_TOKEN permissions can be raised to "
                    "write".format(target)
                ),
                "source": None,
                "remedy": (
                    "recreate the token without the Administration "
                    "permission - the token recipe omits it on purpose; "
                    "see {}".format(_ACTIONS_PERMISSIONS_DOC)
                ),
            }
        ]

    if status == 404:
        return [
            {
                "status": "warn",
                "check": CHECK_ADMINISTRATION,
                "rule": None,
                "danger": (
                    "the saved page documents only 200 for this endpoint, "
                    "so a 404 is ambiguous between 'administration "
                    "withheld' and 'no access at all' - the denial code is "
                    "not documented: this report cannot rule out that the "
                    "token holds Administration, only that the denial is "
                    "unreadable - the {} check (target access) is the "
                    "disambiguator".format(CHECK_TARGET_ACCESS)
                ),
                "source": None,
                "remedy": (
                    "run the target-access probe to distinguish an "
                    "under-scoped token from an unreachable target; "
                    "endpoint in {}".format(_ACTIONS_PERMISSIONS_DOC)
                ),
            }
        ]

    return [
        {
            "status": "skipped",
            "check": CHECK_ADMINISTRATION,
            "rule": None,
            "danger": _ADMINISTRATION_SKIP_DANGER,
            "source": None,
            "reason": "GitHub returned HTTP {} for {}".format(status, url),
            "remedy": skipped_remedy,
        }
    ]


def probe_classic_token(
    token: Optional[str] = None,
    opener: Optional[Callable[..., Any]] = None,
    timeout: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """The third token-scope probe: is the token a classic (OAuth-scoped) token?

    Issues ``GET /user`` through :func:`fetch_probe` (behaviour 1 of
    plans/verify-guards-token.md) - one probe, one API call, no owner or repo
    - and reads the ``X-OAuth-Scopes`` response header, looked up
    case-insensitively (HTTP headers are case-insensitive; the ``headers``
    value from :func:`fetch_probe` is a dict that may be empty). The saved
    page doc/external/github/scopes-for-oauth-apps.md settles the
    discriminator: a token's scope list is that header - GitHub's own
    example shows ``X-OAuth-Scopes: repo, user`` - and scopes are
    normalized, so exact-string matching is brittle; the honest
    discriminator is the header **present and non-empty**.

    - header present and non-empty -> one ``fail`` finding - the second
      emittable ``fail`` in the module: a classic token grants access to
      *every* repository the owner can see (the saved page says the same),
      so the repo-scope guarantee the other probes protect is void
      regardless of their answers. The finding quotes the recorded scopes
      verbatim and carries a non-empty remedy citing the saved page.
    - header present but empty, or absent -> one ``passed`` finding worded
      "no classic OAuth scope header was returned" - deliberately *not*
      "this is a fine-grained token", because the saved page documents no
      ``X-OAuth-Scopes`` semantics for fine-grained PATs and does not
      license that claim.
    - ``401`` or any other status -> one ``skipped`` finding whose reason
      carries the status; for an ``HTTPError`` the headers may be absent,
      and the skip records the status, never the header.
    - a transport reason from :func:`fetch_probe` -> one ``skipped`` finding
      with a non-empty reason.

    The body is **never** parsed for a ``scopes`` field: the documented
    ``GET /user`` 200 body (doc/external/github/rest-api-endpoints-for-users.
    md) contains no such key, so a recorded body carrying one is ignored.

    Like :func:`probe_target_access` and :func:`probe_administration`, a
    missing or empty token is a **skip** - no request is attempted at all -
    because a token-scope probe reads a token's property, and an
    unauthenticated request establishes no fact about any token (behaviour
    7).

    Never raises; always returns a list of findings. Never echoes a token
    into a finding or a reason (module invariant).
    """
    url = "{}/user".format(_RULES_API_BASE)
    skipped_remedy = (
        "make the token valid and api.github.com reachable, then re-run; "
        "see {}".format(_OAUTH_SCOPES_DOC)
    )

    if not token:
        return [
            {
                "status": "skipped",
                "check": CHECK_CLASSIC_TOKEN,
                "rule": None,
                "danger": _CLASSIC_TOKEN_SKIP_DANGER,
                "source": None,
                "reason": (
                    "no token supplied: a token-scope probe with no token "
                    "establishes no fact about any token, so the probe "
                    "skips rather than issuing an unauthenticated request "
                    "and reading its status as a token property - unlike "
                    "fetch_branch_rules, where a missing token is an "
                    "unauthenticated attempt"
                ),
                "remedy": skipped_remedy,
            }
        ]

    status, headers, _body, reason = fetch_probe(
        url, token, opener=opener, timeout=timeout
    )

    if reason is not None:
        return [
            {
                "status": "skipped",
                "check": CHECK_CLASSIC_TOKEN,
                "rule": None,
                "danger": _CLASSIC_TOKEN_SKIP_DANGER,
                "source": None,
                "reason": reason,
                "remedy": skipped_remedy,
            }
        ]

    if status != 200:
        # 401 is the unauthenticated answer the saved page documents for
        # GET /user; any other status is likewise not a scope answer. The
        # headers of a non-200 are not consulted: an HTTPError's headers
        # may be absent, and a skip records the status, not the header.
        return [
            {
                "status": "skipped",
                "check": CHECK_CLASSIC_TOKEN,
                "rule": None,
                "danger": _CLASSIC_TOKEN_SKIP_DANGER,
                "source": None,
                "reason": "GitHub returned HTTP {} for {}".format(status, url),
                "remedy": skipped_remedy,
            }
        ]

    scopes = ""
    if isinstance(headers, dict):
        for key, value in headers.items():
            if isinstance(key, str) and key.lower() == "x-oauth-scopes":
                scopes = value if isinstance(value, str) else str(value)
                break

    if scopes:
        return [
            {
                "status": "fail",
                "check": CHECK_CLASSIC_TOKEN,
                "rule": None,
                "danger": (
                    "the response carried the X-OAuth-Scopes header "
                    "verbatim: {!r} - a classic token grants access to "
                    "every repository the owner can see, so the "
                    "repo-scope guarantee is void regardless of the other "
                    "probes".format(scopes)
                ),
                "source": None,
                "remedy": (
                    "recreate the token as a fine-grained PAT with "
                    "Repository access 'Only select repositories' and no "
                    "classic scopes; where scopes live and how they are "
                    "normalized: {}".format(_OAUTH_SCOPES_DOC)
                ),
            }
        ]

    return [
        {
            "status": "passed",
            "check": CHECK_CLASSIC_TOKEN,
            "rule": None,
            "danger": "",
            "source": None,
            "remedy": (
                "nothing to do - no classic OAuth scope header was "
                "returned (the X-OAuth-Scopes header was absent or empty); "
                "that says the response carried no scopes, not what kind "
                "of token this is; see {}".format(_OAUTH_SCOPES_DOC)
            ),
        }
    ]


def workflows_withheld_finding() -> List[Dict[str, Any]]:
    """The workflows-withheld finding (behaviour 5 of plans/verify-guards-token.md).

    Takes nothing - no network, no token, no owner or repo - and returns a
    constant one-element findings list. The ``workflows`` permission has
    access level ``write`` only - no ``read`` form exists - per the
    permission table in doc/external/github/fine-grained-personal-access-
    tokens.md, and the workflows list endpoint
    (``GET /repos/{owner}/{repo}/actions/workflows``) is gated on
    "Actions" repository permissions (read), not ``workflows``, and works
    unauthenticated on public repos (doc/external/github/rest-api-endpoints-
    for-workflows.md). So no read-only call can prove the ``workflows``
    withholding: the only call that would is a write, which the probes must
    not perform.

    The finding is therefore ``skipped``, never ``passed`` - the #68
    rule's exact case: an unprovable withholding must not read as clean.
    Deterministic: every call returns equal findings. Never raises. The
    finding renders through :func:`render_finding`'s existing ``skipped``
    branch, which carries the ``reason``.
    """
    reason = (
        "the workflows permission has no read level (write only, per the "
        "permission table in {}) and no read-only endpoint is gated on it "
        "- the workflows list endpoint is gated on Actions: read and works "
        "unauthenticated on public repos, so a 200 from it proves nothing "
        "about the token ({}); the only call that would prove the "
        "workflows withholding is a write, which the probes must not "
        "perform - the withholding is unprovable by a read-only call".format(
            _FINE_GRAINED_DOC, _WORKFLOWS_DOC
        )
    )
    remedy = (
        "manual check: open the token's permission table in the GitHub "
        "settings UI (or re-create the token per the recipe) and confirm "
        "the workflows permission is absent there; the workflow list "
        "endpoint is documented in {} and the workflows-permission row "
        "(write only) in {}".format(_WORKFLOWS_DOC, _FINE_GRAINED_DOC)
    )
    return [
        {
            "status": "skipped",
            "check": CHECK_WORKFLOWS_WITHHELD,
            "rule": None,
            "danger": _WORKFLOWS_WITHHELD_SKIP_DANGER,
            "source": None,
            "reason": reason,
            "remedy": remedy,
        }
    ]


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
    for check in (
        CHECK_HISTORY_REWRITE,
        CHECK_REVIEW,
        CHECK_UPDATE_RESTRICTION,
        CHECK_FILE_PATHS,
    ):
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


def check_update(rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One update finding: passed if ``update`` is active, warn if not.

    ``rules`` is the parsed body of
    ``GET /repos/{owner}/{repo}/rules/branches/{branch}``: a list, and only
    ``type``, ``ruleset_source`` and ``parameters`` of an ``update`` element
    are read. A rule present yields a ``passed`` finding under the
    ``update_restriction`` check naming the rule's API type and its
    ``ruleset_source``, with
    ``parameters.update_allows_fetch_and_merge`` recorded on the finding -
    ``False`` means fetches and merges are the only allowed updates, a
    weaker restriction than the name suggests, and the report must show it
    (the zero-approvals precedent). An unreadable ``parameters`` object
    records ``None`` rather than guessing. A rule absent yields a ``warn``
    finding naming the danger (anyone with push access can push straight to
    the branch, with no gate) and a concrete fix.
    """
    rule = None
    for candidate in rules:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("type") == "update":
            rule = candidate
            break

    if rule is None:
        return [
            {
                "status": "warn",
                "check": CHECK_UPDATE_RESTRICTION,
                "rule": "update",
                "danger": _DANGERS["update"],
                "source": None,
                "remedy": (
                    "add an 'update' rule to a ruleset covering this "
                    "branch: rule semantics in {}, endpoint in {}".format(
                        _RULES_DOC, _ENDPOINT_DOC
                    )
                ),
            }
        ]

    parameters = rule.get("parameters")
    if not isinstance(parameters, dict):
        parameters = {}
    allows_fetch_and_merge = parameters.get("update_allows_fetch_and_merge")
    return [
        {
            "status": "passed",
            "check": CHECK_UPDATE_RESTRICTION,
            "rule": "update",
            "danger": "",
            "source": _or_unknown(rule.get("ruleset_source")),
            "update_allows_fetch_and_merge": allows_fetch_and_merge,
            "remedy": (
                "nothing to do - the 'update' rule is active for this "
                "branch, update_allows_fetch_and_merge: {}; see {}".format(
                    allows_fetch_and_merge, _RULES_DOC
                )
            ),
        }
    ]


def check_file_paths(rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One file-path finding: passed if ``file_path_restriction`` is active, warn if not.

    ``rules`` is the parsed body of
    ``GET /repos/{owner}/{repo}/rules/branches/{branch}``: a list, and only
    ``type``, ``ruleset_source`` and ``parameters`` of a
    ``file_path_restriction`` element are read. A rule present yields a
    ``passed`` finding under the ``file_paths`` check naming the rule's API
    type and its ``ruleset_source``, with
    ``parameters.restricted_file_paths`` recorded on the finding - an empty
    list is a rule that restricts nothing, a weaker guard than the name
    suggests, and the report must show it (the zero-approvals precedent). An
    unreadable ``parameters`` object, a missing ``restricted_file_paths``
    key, or a value that is not a list records an empty list rather than
    ``None``: an empty restriction set is the only honest value for a rule
    whose paths cannot be read, and the finding must never raise. A rule
    absent yields a ``warn`` finding naming the danger (a push can change
    ``.github/workflows/**`` - what CI runs - with no gate) and a concrete
    fix. A duplicated rule type takes the first element, as
    :func:`check_history_rewrite` does.
    """
    rule = None
    for candidate in rules:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("type") == "file_path_restriction":
            rule = candidate
            break

    if rule is None:
        return [
            {
                "status": "warn",
                "check": CHECK_FILE_PATHS,
                "rule": "file_path_restriction",
                "danger": _DANGERS["file_path_restriction"],
                "source": None,
                "remedy": (
                    "add a 'file_path_restriction' rule to a ruleset "
                    "covering this branch: rule semantics in {}, endpoint "
                    "in {}".format(_RULES_DOC, _ENDPOINT_DOC)
                ),
            }
        ]

    parameters = rule.get("parameters")
    if not isinstance(parameters, dict):
        parameters = {}
    restricted_file_paths = parameters.get("restricted_file_paths")
    if not isinstance(restricted_file_paths, list):
        restricted_file_paths = []
    return [
        {
            "status": "passed",
            "check": CHECK_FILE_PATHS,
            "rule": "file_path_restriction",
            "danger": "",
            "source": _or_unknown(rule.get("ruleset_source")),
            "restricted_file_paths": restricted_file_paths,
            "remedy": (
                "nothing to do - the 'file_path_restriction' rule is "
                "active for this branch, restricted_file_paths: {}; see "
                "{}".format(restricted_file_paths, _RULES_DOC)
            ),
        }
    ]


def check_all(rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The concatenation of every defined check, in fixed report order.

    Runs :func:`check_history_rewrite`, :func:`check_review`,
    :func:`check_update` and :func:`check_file_paths` in that order and
    returns their findings concatenated, so a five-rule array yields
    exactly five findings - one per rule - with the two history-rewrite
    rules first. This is the single seam both CLI call sites
    (verify-guards and doctor's Guards section) report through: a check
    added here reaches both without edits to either (behaviour 7 of
    plans/verify-guards-five-rules.md). The function fetches nothing and
    never calls ``sys.exit``: an empty array yields five ``warn``
    findings and raises nothing.
    """
    findings: List[Dict[str, Any]] = []
    for check in (
        check_history_rewrite,
        check_review,
        check_update,
        check_file_paths,
    ):
        findings.extend(check(rules))
    return findings


def render_finding(finding: Dict[str, Any]) -> str:
    """One human-readable line per finding; no network, no exit.

    A ``passed`` line names the rule's API type and states that the rule
    is present - plus the caveat that ``bypass_actors`` is only returned
    to users with write access to the ruleset, so on a read-only token the
    branch must never be called simply "protected": an unseen bypass entry
    is an unmeasured hole. A passed review finding also keeps its recorded
    ``required_approving_review_count`` visible, and a passed update
    finding keeps its recorded ``update_allows_fetch_and_merge`` visible -
    a weak value stays on the line (the zero-approvals precedent) - while
    a finding whose parameters were unreadable claims no value at all. A
    passed file-path finding keeps its recorded ``restricted_file_paths``
    visible, listing every recorded path verbatim with no elision; an
    empty recorded list - explicit ``[]`` or an unreadable parameter -
    renders the explicit "no restricted paths recorded" rather than a
    bare "protected". A ``warn`` line names the danger and the remedy. A
    ``skipped`` line carries the reason the check could not run.
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
        allows = finding.get("update_allows_fetch_and_merge")
        if allows is not None:
            line += " (update_allows_fetch_and_merge: {})".format(allows)
        paths = finding.get("restricted_file_paths")
        if paths is not None:
            if paths:
                line += " (restricted_file_paths: {})".format(
                    ", ".join(str(path) for path in paths)
                )
            else:
                line += " (no restricted paths recorded)"
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


def summarize(findings: List[Dict[str, Any]]) -> int:
    """The exit-status seam: ``1`` when any finding has status ``fail``, else ``0``.

    The ``verify-guards`` command interprets its findings to decide its exit
    status; that interpretation is a pure function of the findings, so it is
    testable with no typer and no network. ``warn`` and ``skipped`` alone
    yield ``0``: a warning or an unrunnable check is reported, not a failure
    (behaviour 7 of plans/pi-guard-verification.md). This slice emits no
    ``fail`` finding, but the contract is what the follow-up slice's fail
    findings will drive, so it is pinned now.
    """
    for finding in findings:
        if finding.get("status") == "fail":
            return 1
    return 0


def render_report(findings: List[Dict[str, Any]]) -> List[str]:
    """One line per finding, in order; empty findings yield an empty report.

    The report always prints - including on failure - so nothing may be
    dropped: each line delegates to :func:`render_finding`, which is the only
    place a finding's text is written, so the report and the single-finding
    renderer can never drift apart (behaviour 7).
    """
    return [render_finding(finding) for finding in findings]


def _or_unknown(value: Any) -> str:
    """A ruleset_source is expected on every active rule; name the gap if not."""
    if isinstance(value, str) and value:
        return value
    return "unknown"


# Owner/repo pair shapes a GitHub remote can take: HTTPS and SSH, each with or
# without the .git suffix. The HTTPS forms also accept an optional userinfo
# component (user or user:token) before the host - the form git leaves behind
# after a clone with an embedded token - which is discarded so the credential
# can never reach a returned value (behaviour 6). Both host spellings are
# anchored so a lookalike host (bitbucket.org, gitlab.com, ...) can never
# match, even with a userinfo (plans/pi-guard-verification.md: never a guess).
_GITHUB_HTTPS_RE = re.compile(r"^https://(?:[^/@]+@)?github\.com/([^/]+)/([^/]+)/?\.git/?$")
_GITHUB_HTTPS_BARE_RE = re.compile(r"^https://(?:[^/@]+@)?github\.com/([^/]+)/([^/]+)$")
_GITHUB_SSH_RE = re.compile(r"^git@github\.com:([^/]+)/([^/]+)/?\.git/?$")
_GITHUB_SSH_BARE_RE = re.compile(r"^git@github\.com:([^/]+)/([^/]+)$")


def parse_github_remote(url: str) -> Optional[Tuple[str, str]]:
    """Parse ``(owner, repo)`` from a GitHub remote URL; never raises.

    The HTTPS and SSH forms of the same remote give the same answer, with the
    ``.git`` suffix stripped: ``https://github.com/owner/repo[.git]`` and
    ``git@github.com:owner/repo[.git]`` all yield ``("owner", "repo")``.

    Anything the parser cannot account for - a non-GitHub host, an unparsable
    string, an empty owner or repo - yields ``None``: a URL that does not
    name a GitHub repository exactly is a skip, not a guess (behaviour 6).
    """
    if not isinstance(url, str):
        return None
    for pattern in (
        _GITHUB_HTTPS_RE,
        _GITHUB_HTTPS_BARE_RE,
        _GITHUB_SSH_RE,
        _GITHUB_SSH_BARE_RE,
    ):
        match = pattern.match(url)
        if match is None:
            continue
        owner, repo = match.group(1), match.group(2)
        if owner and repo:
            return owner, repo
        return None
    return None


def resolve_repository(
    path: Union[str, Path],
    runner: Optional[Callable[..., str]] = None,
) -> Optional[Tuple[str, str]]:
    """Resolve ``(owner, repo)`` from the origin remote of the git repo at ``path``.

    ``runner`` is an injectable seam (the same discipline as the opener in
    :func:`fetch_branch_rules`): a callable returning the origin URL string,
    or empty / raising when there is no remote. When ``runner`` is ``None``
    the real ``git remote get-url origin`` runs via subprocess - a list,
    never a shell - and a non-zero exit or empty output is treated as
    no-remote, exactly as a raising or empty runner would be.

    The origin URL is fed to :func:`parse_github_remote`, so no origin or a
    non-GitHub origin yields ``None``: the identity is either known or
    absent, never guessed (behaviour 6).
    """
    if runner is None:
        def runner() -> str:
            completed = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=str(path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    "git remote get-url origin exited {}".format(completed.returncode)
                )
            return completed.stdout.decode("utf-8", errors="replace").strip()

    try:
        origin = runner()
    except Exception:
        return None
    if not isinstance(origin, str) or not origin.strip():
        return None
    return parse_github_remote(origin.strip())
