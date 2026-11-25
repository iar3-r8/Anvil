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


def pr_fields_for(payload: Dict[str, Any]) -> Dict[str, str]:
    """The PR title and body derived from an issue payload.

    Placeholder for the red step of behaviour 4; the derivation lands in the
    green step.
    """
    return {"title": "", "body": ""}
