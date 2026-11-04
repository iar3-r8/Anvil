"""The GitHub interaction surface for the intake loop: the module that
talks to the GitHub REST API on behalf of
``plans/pi-phase10-github-loop.md``.

One job per public function, all over the same recorded REST seam: an
injectable ``opener`` defaulting to ``urllib.request.urlopen`` and an
optional ``timeout``, so the suite never touches the live network. A
``token`` supplied by the host driver adds only the ``Authorization``
header: an absent token sends an unauthenticated request, never a skip.
The API version header is pinned to ``2022-11-28`` (the plan's
Assumptions), and the endpoint shapes follow the saved documentation -
``doc/external/github/rest-api-endpoints-for-issues.md`` and its
siblings. Every network or payload failure is translated into a
``reason`` string naming the situation: the read function never raises,
returns ``(None, reason)`` - and no token text ever reaches a reason,
which names the URL and the situation only, never the request headers.

House discipline, as ``anvilkit.pi.picycle``'s docstring uses it: one
behaviour lands per red/green cycle, and the docstring says which have
landed. Behaviour 1 of plans/pi-phase10-github-loop.md is implemented
here.
"""

import json
import socket
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Optional, Tuple

# The issues endpoint lives on the API host, not the web host
# (doc/external/github/rest-api-endpoints-for-issues.md).
_GITHUB_API_BASE = "https://api.github.com"

# Pinned by the plan's Assumptions: the saved pages rendered against a
# later default, and these endpoints' documented shapes are unchanged
# between them.
_API_VERSION = "2022-11-28"

# Generous on purpose: a slow GitHub must not turn a readable issue
# into an unreadable one (the same default anvilkit/pi/piguard.py pins
# for its fetches).
DEFAULT_ISSUE_TIMEOUT = 10.0

# Cited by the reasons so a reviewer can check each claim against the
# saved endpoint documentation.
_ISSUES_DOC = "doc/external/github/rest-api-endpoints-for-issues.md"


class GitHubError(Exception):
    """The module's single exception, raised on a bad argument.

    Behaviour 1 (the read) never raises - it returns ``(None, reason)``.
    Defined now so the module compiles as the later behaviours land:
    behaviour 5 raises it for an empty stage, behaviour 6 for an empty
    argv field, and behaviour 8 for a missing example
    (plans/pi-phase10-github-loop.md).
    """


def read_issue(
    owner: str,
    repo: str,
    issue_number: int,
    token: Optional[str] = None,
    opener: Optional[Callable[..., Any]] = None,
    timeout: Optional[float] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Read one issue; never raises.

    Builds ``GET {api}/repos/{owner}/{repo}/issues/{issue_number}``
    (doc/external/github/rest-api-endpoints-for-issues.md) with
    ``Accept: application/vnd.github+json`` and the pinned
    ``X-GitHub-Api-Version`` header. A ``token`` adds the
    ``Authorization: Bearer`` header; without one the request goes out
    unauthenticated - a missing token is not a skip, only an actual
    request failure is.

    Returns ``(issue, None)`` on a 200 whose body is a JSON object, the
    issue read from that object: ``number``, ``title`` and ``body``
    exactly as recorded, a ``null`` body staying ``None``, never the
    string ``"None"``. Every other recorded outcome yields
    ``(None, reason)`` naming the situation - a 301 (moved, i.e.
    transferred), a 404 (not readable there), a 410 (deleted, gone), a
    200 with a non-JSON body, a 200 with a JSON body that is not an
    object, a ``URLError`` (GitHub unreachable) and a timeout
    (including a ``socket.timeout`` wrapped in a ``URLError``). No
    reason ever carries the token text.

    ``opener`` defaults to ``urllib.request.urlopen``; tests inject a
    recorded opener, so the suite never touches the live network.
    """
    if opener is None:
        opener = urllib.request.urlopen
    if timeout is None:
        timeout = DEFAULT_ISSUE_TIMEOUT

    url = "{}/repos/{}/{}/issues/{}".format(
        _GITHUB_API_BASE, owner, repo, issue_number
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _API_VERSION,
    }
    if token:
        headers["Authorization"] = "Bearer {}".format(token)
    request = urllib.request.Request(url, headers=headers)

    try:
        with opener(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return None, _http_error_reason(exc.code, url)
    except socket.timeout:
        return None, "timeout after {}s contacting {}".format(timeout, url)
    except urllib.error.URLError as exc:
        # URLError wraps the real cause, including socket.timeout on
        # some versions (the same pattern as anvilkit/pi/piguard.py).
        if isinstance(exc.reason, socket.timeout):
            return None, "timeout after {}s contacting {}".format(timeout, url)
        return None, "GitHub was unreachable for {}: {}".format(url, exc.reason)
    except OSError as exc:
        return None, "GitHub was unreachable for {}: {}".format(url, exc)

    try:
        payload = json.loads(body)
    except ValueError as exc:
        return None, (
            "GitHub returned a 200 with a non-JSON body for {}: {} - "
            "the issues endpoint answers with a JSON object (see {})".format(
                url, exc, _ISSUES_DOC
            )
        )
    if not isinstance(payload, dict):
        return None, (
            "GitHub returned a 200 whose JSON body is not an issue "
            "object for {}: expected an object (dict), got {} (see "
            "{})".format(url, type(payload).__name__, _ISSUES_DOC)
        )
    return payload, None


def _http_error_reason(code: int, url: str) -> str:
    """A reason naming the recorded HTTP error situation; never the token.

    Only the status code and the URL are named - the ``Authorization``
    header is request-side and must never round-trip into a
    user-facing reason (behaviour 15 pins the boundary project-wide).
    """
    if code == 301:
        return (
            "GitHub returned 301 moved permanently for {}: the issue was "
            "moved (transferred to another repository), so it is no "
            "longer readable at its recorded location (see {})".format(
                url, _ISSUES_DOC
            )
        )
    if code == 404:
        return (
            "GitHub returned 404 not found for {}: the issue is not "
            "readable there - it does not exist, or the request lacks "
            "read access to it (see {})".format(url, _ISSUES_DOC)
        )
    if code == 410:
        return (
            "GitHub returned 410 gone for {}: the issue has been "
            "deleted, so it can no longer be read (see {})".format(
                url, _ISSUES_DOC
            )
        )
    return "GitHub returned HTTP {} for {}".format(code, url)
