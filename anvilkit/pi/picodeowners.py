"""Build the CODEOWNERS walkthrough text for the free-plan fix.

One job: behaviours 1 and 2 of
plans/file-path-interactive-free-plan.md — ``codeowners_body`` returns
the CODEOWNERS text whose owner line is ``/.github/ @{owner}``,
GitHub's own "most secure method": the file owns itself (the saved page
``doc/external/github/about-code-owners.md``, section "CODEOWNERS and
branch protection"), and ``walkthrough_steps`` turns that body plus the
repository and base branch into the six ordered display steps. The
module builds text only — it never writes a file, never makes a network
call and never prompts; the prompt belongs to a later behaviour.
"""

from typing import Any, Dict, List


class CodeownersError(Exception):
    """A CODEOWNERS body input that cannot be turned into the text."""


def codeowners_body(owner: str) -> str:
    """Return the CODEOWNERS text with the owner line ``/.github/ @{owner}``.

    The owner line is exactly ``/.github/ @{owner}`` — the ``/.github/``
    prefix is GitHub's "most secure method": the CODEOWNERS file owns
    itself (``doc/external/github/about-code-owners.md``, section
    "CODEOWNERS and branch protection"). A comment line tells the reader to
    EDIT the pre-filled handle to the real owners, who need explicit write
    access to the repository per the same page.

    ``owner`` is used verbatim — no quoting, no escaping, no case-folding —
    and is never shell- or string-substituted into anything executable.
    Deterministic: the same ``owner`` returns the identical string.

    Raises :class:`CodeownersError` if ``owner`` is empty or
    whitespace-only — the handle is never guessed.
    """
    if not owner or not owner.strip():
        raise CodeownersError(
            "refusing to build a CODEOWNERS body without an owner: "
            "the handle is pre-filled and never guessed"
        )
    return (
        "# CODEOWNERS — pre-filled; edit the handle below to the real\n"
        "# owners, who need explicit write access to the repository.\n"
        "/.github/ @{owner}\n"
    ).format(owner=owner)


def walkthrough_steps(owner: str, repo: str, branch: str, body: str) -> List[str]:
    """Return the six ordered CODEOWNERS walkthrough steps as display text.

    Each step is one or more short imperative lines a human follows
    (behaviour 2 of plans/file-path-interactive-free-plan.md), built from
    ``owner``, ``repo``, ``branch`` and ``body`` — never re-derived by the
    caller. The steps print as-is, so every line stays at most 80
    characters. The body is pre-built by the caller via
    ``codeowners_body``, so a ``CodeownersError`` from ``codeowners_body``
    propagates unchanged at the caller level and is not exercised inside
    this function; the branch-level guard below is this module's own.

    Raises :class:`CodeownersError` if ``branch`` is empty or
    whitespace-only — the base branch is never guessed.
    """
    if not branch or not branch.strip():
        raise CodeownersError(
            "refusing to build walkthrough steps without a base branch: "
            "the base branch is pre-filled and never guessed"
        )
    # Carry the body's content lines as step 1's payload - the exact owner
    # line is data, not display text. Only the owner line, not the full
    # body: the body's edit-me comment already names "write access", which
    # belongs to step 2, and the steps must appear in their contract order.
    payload_lines = [
        line
        for line in body.splitlines()
        if line and not line.lstrip().startswith("#")
    ]
    payload = payload_lines[0] if payload_lines else "/.github/ @" + owner
    return [
        (
            "1. Create .github/CODEOWNERS in {repo}:\n"
            "{payload}\n"
            "   Edit the handle to the real write-access owners."
        ).format(repo=repo, payload=payload),
        (
            "2. Owners need write access: an @user handle or an "
            "@org/team."
        ),
        (
            "3. Commit .github/CODEOWNERS to {branch} - the base branch."
        ).format(branch=branch),
        (
            "4. In Settings, open the {repo} rulesets and tick\n"
            "   \"Require review from Code Owners\", then Save."
        ).format(repo=repo),
        (
            "5. Re-run anvil verify-guards: the warn stays - review "
            "gate, not a push rule."
        ),
        (
            "6. Public repos only on GitHub Free; private repos need "
            "Pro, Team, Enterprise."
        ),
    ]


def wants_walkthrough(findings: List[Dict[str, Any]]) -> bool:
    """True iff a warn file_paths finding is present; the ask happens at the cli layer, behaviour 4."""
    for finding in findings:
        if isinstance(finding, dict):
            if finding.get("check") == "file_paths" and finding.get("status") == "warn":
                return True
    return False
