"""Derivation for the `pi run` command, per plans/pi-phase14-run-command.md.

One job: derive the run's outputs from the issue payload — the branch name,
the PR title, the PR-body fields, and the kind — and map a run's outcome to
an exit code. This module derives, never executes: it performs no git, no
GitHub call and no file write; the actor lives in ``anvilkit.cli``.
"""


class RunError(Exception):
    """Raised when a run's derivation or outcome cannot be resolved."""


def branch_for(kind: str, issue_number: int) -> str:
    """The branch the run works on, derived from the kind and the issue number.

    Placeholder for the red step of behaviour 3; the derivation lands in the
    green step.
    """
    return ""
