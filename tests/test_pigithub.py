"""Tests for anvilkit.pi.pigithub - GitHub intake read (behaviour 1).

Written before the implementation (TDD RED for behaviour 1 ``intake-read``
of plans/pi-phase10-github-loop.md): ``anvilkit/pi/pigithub.py`` does not
exist yet, so this file's import of ``anvilkit.pi.pigithub`` is the
expected red - the phase-9 precedent, where the first red commit was
exactly this import of the not-yet-existing module.

``read_issue(owner, repo, issue_number, token, opener=None, ...)`` reads
``GET /repos/{owner}/{repo}/issues/{issue_number}`` - the endpoint shape
documented in doc/external/github/rest-api-endpoints-for-issues.md - and
returns ``(issue, None)`` on a 200 whose body is a JSON object, the issue
carrying the ``number``, ``title`` and ``body`` the loop consumes. Every
other recorded outcome - a 301 (transferred), a 404 (unreadable), a 410
(deleted but readable), a 200 with a non-JSON body, a 200 with a JSON
body that is not an object, a ``URLError`` and a timeout - yields
``(None, reason)`` naming the situation. Nothing raises, and no token
text appears in any reason.

No test performs real network I/O: every test injects a recorded opener
(a urlopen-like callable, the same seam ``anvilkit/pi/piguard.py`` uses)
with abridged recorded response bodies carrying only the fields this
behaviour reads.
"""

import json
import socket
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit.pi import pigithub  # noqa: E402


# A sentinel whose full text is asserted absent from every reason: a
# credential that leaks into a user-facing string is a boundary failure,
# not a wording issue.
TOKEN = "ghp_sentinel_4f7a9c2e_intake_read"

OWNER = "octocat"
REPO = "Hello-World"
ISSUE_NUMBER = 1347
URL = "https://api.github.com/repos/{}/{}/issues/{}".format(
    OWNER, REPO, ISSUE_NUMBER
)

# The recorded 200 body, abridged to the fields the loop reads, in the
# shape the saved endpoint doc documents
# (doc/external/github/rest-api-endpoints-for-issues.md).
ISSUE_BODY: Dict[str, Any] = {
    "number": 1347,
    "title": "Found a bug",
    "body": "I'm having a problem with this.",
}


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


def _failure_openers() -> List[Tuple[str, Any]]:
    """(label, recorded opener) for every intake-read failure mode."""
    return [
        (
            "http 301",
            _opener(urllib.error.HTTPError(URL, 301, "Moved Permanently", None, None)),
        ),
        (
            "http 404",
            _opener(urllib.error.HTTPError(URL, 404, "Not Found", None, None)),
        ),
        (
            "http 410",
            _opener(urllib.error.HTTPError(URL, 410, "Gone", None, None)),
        ),
        (
            "non-json body",
            _opener(_FakeResponse(b"<html>GitHub Maintenance</html>")),
        ),
        (
            "json list body",
            _opener(_FakeResponse(json.dumps([ISSUE_NUMBER]).encode("utf-8"))),
        ),
        (
            "url error",
            _opener(urllib.error.URLError("Name or service not known")),
        ),
        (
            "bare socket.timeout",
            _opener(socket.timeout("timed out")),
        ),
        (
            "URLError wrapping socket.timeout",
            _opener(urllib.error.URLError(socket.timeout("timed out"))),
        ),
    ]


class ReadIssueTests(unittest.TestCase):
    """Behaviour 1 (intake-read) of plans/pi-phase10-github-loop.md.

    ``read_issue`` must never raise: every failure mode yields
    ``(None, reason)`` naming the situation, and no reason carries the
    token text. Every test runs over a recorded opener - no live network.
    """

    def _read(self, opener: Any) -> Tuple[Any, Any]:
        return pigithub.read_issue(OWNER, REPO, ISSUE_NUMBER, TOKEN, opener=opener)

    def _assert_failure(self, label: str, opener: Any) -> str:
        """Run one recorded failure and assert ``(None, reason)``; return the reason."""
        issue, reason = self._read(opener)

        self.assertIsNone(
            issue,
            "{}: no issue exists when the read failed".format(label),
        )
        self.assertIsInstance(
            reason,
            str,
            "{}: the failure must record a string reason".format(label),
        )
        self.assertTrue(
            reason,
            "{}: the failure must record a non-empty reason".format(label),
        )
        self.assertNotIn(
            TOKEN,
            reason,
            "{}: the token text must never appear in a reason".format(label),
        )
        return reason

    def test_read_issue_200_json_object_returns_issue_and_none(self):
        for label, fixture in (
            ("recorded issue", dict(ISSUE_BODY)),
            # An issue body may be null
            # (doc/external/github/rest-api-endpoints-for-issues.md): the
            # null must survive as None, never the string "None".
            (
                "null body",
                {"number": 7, "title": "No description", "body": None},
            ),
        ):
            with self.subTest(fixture=label):
                issue, reason = self._read(
                    _opener(_FakeResponse(json.dumps(fixture).encode("utf-8")))
                )

                self.assertIsNone(
                    reason,
                    "a 200 with a JSON object is a success: no reason expected",
                )
                self.assertIsInstance(
                    issue,
                    dict,
                    "the issue must be the JSON object from the body",
                )
                self.assertEqual(
                    issue,
                    fixture,
                    "the issue must be read from the JSON object: number, "
                    "title and body exactly as recorded",
                )

    def test_read_issue_301_returns_none_and_reason_naming_moved(self):
        reason = self._assert_failure(
            "http 301",
            _opener(urllib.error.HTTPError(URL, 301, "Moved Permanently", None, None)),
        )

        self.assertIn(
            "301",
            reason,
            "the reason must name the situation: 301 moved permanently "
            "(doc/external/github/rest-api-endpoints-for-issues.md)",
        )

    def test_read_issue_404_returns_none_and_reason_naming_not_found(self):
        reason = self._assert_failure(
            "http 404",
            _opener(urllib.error.HTTPError(URL, 404, "Not Found", None, None)),
        )

        self.assertIn(
            "404",
            reason,
            "the reason must name the situation: 404 unreadable "
            "(doc/external/github/rest-api-endpoints-for-issues.md)",
        )

    def test_read_issue_410_returns_none_and_reason_naming_gone(self):
        reason = self._assert_failure(
            "http 410",
            _opener(urllib.error.HTTPError(URL, 410, "Gone", None, None)),
        )

        self.assertIn(
            "410",
            reason,
            "the reason must name the situation: 410 deleted but readable "
            "(doc/external/github/rest-api-endpoints-for-issues.md)",
        )

    def test_read_issue_200_non_json_body_returns_none_and_reason_naming_json(self):
        reason = self._assert_failure(
            "non-json body",
            _opener(_FakeResponse(b"<html>GitHub Maintenance</html>")),
        )

        self.assertIn(
            "json",
            reason.lower(),
            "the reason must name the situation: the 200 body is not JSON",
        )

    def test_read_issue_200_json_list_body_returns_none_and_reason_naming_non_object(self):
        # A list IS valid JSON, so the reason must distinguish "parsed
        # fine, but not an issue object" from the non-JSON case.
        reason = self._assert_failure(
            "json list body",
            _opener(_FakeResponse(json.dumps([ISSUE_NUMBER]).encode("utf-8"))),
        )

        self.assertTrue(
            "object" in reason.lower() or "dict" in reason.lower(),
            "the reason must name the situation: the JSON body is not an "
            "issue object",
        )

    def test_read_issue_url_error_returns_none_and_reason_without_raising(self):
        reason = self._assert_failure(
            "url error",
            _opener(urllib.error.URLError("Name or service not known")),
        )

        self.assertIn(
            "reach",
            reason.lower(),
            "the reason must name the situation: GitHub was unreachable",
        )

    def test_read_issue_timeout_returns_none_and_reason_naming_timeout(self):
        for label, outcome in (
            ("bare socket.timeout", socket.timeout("timed out")),
            (
                "URLError wrapping socket.timeout",
                urllib.error.URLError(socket.timeout("timed out")),
            ),
        ):
            with self.subTest(timeout=label):
                reason = self._assert_failure(
                    "timeout ({})".format(label), _opener(outcome)
                )

                self.assertTrue(
                    "time out" in reason.lower() or "timeout" in reason.lower(),
                    "the reason must name the situation: a timeout",
                )

    def test_read_issue_no_reason_ever_carries_token_text(self):
        # Drift guard on the credential boundary for behaviour 1: the
        # sentinel token is driven through every recorded failure path,
        # and none of the resulting reasons may carry its text.
        for label, opener in _failure_openers():
            with self.subTest(failure=label):
                issue, reason = self._read(opener)

                self.assertIsNone(issue)
                self.assertIsInstance(reason, str)
                self.assertTrue(reason)
                self.assertNotIn(
                    TOKEN,
                    reason,
                    "the token text must never appear in a reason ({})".format(
                        label
                    ),
                )
