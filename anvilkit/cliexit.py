"""The CLI's exit vocabulary: the per-class exit codes and the single helper that builds a failing ``typer.Exit``."""

import typer

# EXIT_USAGE uses click's own code (2) to avoid conflicting answers.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_CONFIG = 3
EXIT_DOCKER = 4
EXIT_PROVISION = 5
EXIT_PROMPT = 6
# Stress: 7 means no results were produced at all; 8 means the run finished
# and found failures, which is a successful measurement, so it gets its own
# code rather than reusing EXIT_ERROR.
EXIT_STRESS_UNAVAILABLE = 7
EXIT_STRESS_FAILURES = 8
# A blocked setup-repo guard gate: nothing was provisioned and nothing is
# wrong with Anvil - the user's GitHub needs a fix (plans/setup-repo-guards.md
# behaviour 9 pins the code and the message wording in a later cycle).
EXIT_GUARDS_BLOCKED = 9


def fail(message: str, code: int) -> typer.Exit:
    """Echo *message* on stderr and return a ``typer.Exit`` carrying *code*."""
    typer.echo(message, err=True)
    return typer.Exit(code)
