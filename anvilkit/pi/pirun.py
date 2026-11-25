"""Derivation for the `pi run` command, per plans/pi-phase14-run-command.md.

One job: derive the run's outputs from the issue payload — the branch name,
the PR title, the PR-body fields, and the kind — and map a run's outcome to
an exit code. This module derives, never executes: it performs no git, no
GitHub call and no file write; the actor lives in ``anvilkit.cli``.
"""

from typing import Any, Dict


class RunError(Exception):
    """Raised when a run's derivation or outcome cannot be resolved."""


def branch_for(kind: str, issue_number: int) -> str:
    """The branch the run works on, derived from the kind and the issue number.

    Returns ``"<kind>/issue-<issue_number>"`` — ``feature/issue-114`` for the
    feature kind, ``bugfix/issue-114`` for the bugfix kind.

    Raises ``RunError`` naming the number when ``issue_number`` is not positive.
    """
    if issue_number <= 0:
        raise RunError(
            "issue number must be positive, got {}".format(issue_number)
        )
    return "{}/issue-{}".format(kind, issue_number)


_TITLE_PLACEHOLDER = "(no title provided)"
_BODY_PLACEHOLDER = "(no body provided)"


def pr_fields_for(payload: Any) -> Dict[str, str]:
    """The PR title and body derived from an issue payload.

    Returns ``{"title": <issue title>, "body": <issue body>}`` from the
    payload returned by ``read_issue``. A field that is missing, ``None``, or
    an empty/whitespace-only string yields a stated placeholder for that
    field only: ``(no title provided)`` / ``(no body provided)`` — never the
    string ``"None"``. A payload that is not a dict is treated as missing
    both fields: both placeholders, and no exception is raised.
    """
    if not isinstance(payload, dict):
        return {"title": _TITLE_PLACEHOLDER, "body": _BODY_PLACEHOLDER}
    return {
        "title": _field(payload, "title", _TITLE_PLACEHOLDER),
        "body": _field(payload, "body", _BODY_PLACEHOLDER),
    }


def _field(payload: Any, key: str, placeholder: str) -> str:
    """The value at ``key`` as a string, or ``placeholder`` when it is not a
    non-blank string in the payload."""
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return placeholder
