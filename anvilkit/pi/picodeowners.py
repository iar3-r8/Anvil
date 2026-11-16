"""Build the CODEOWNERS walkthrough text for the free-plan fix.

One job: behaviours 1 and 2 of
plans/file-path-interactive-free-plan.md — ``codeowners_body`` returns
the CODEOWNERS text whose owner line is ``/.github/ @{owner}``,
GitHub's own "most secure method": the file owns itself (the saved page
``doc/external/github/about-code-owners.md``, section "CODEOWNERS and
branch protection"), and ``walkthrough_steps`` turns that body plus the
repository and base branch into the six ordered display steps.
Behaviour 13 of plans/file-path-codeowners-interactive.md adds the
last-push rule as ``last_push_step`` (the extra display step) and the
self-approval advisory as ``self_approval_warning`` (one line, or None).
The module builds text only — it never writes a file, never makes a
network call and never prompts; the prompt belongs to the cli layer.
"""

from typing import Any, Dict, List, Optional


class CodeownersError(Exception):
    """A CODEOWNERS body input that cannot be turned into the text."""


def codeowners_body(owners: str) -> str:
    """Return the CODEOWNERS text whose owner line lists the normalised handles.

    ``owners`` is the handle string: one or several whitespace-separated
    handles, each with an optional leading ``@``. Each handle is split on
    whitespace, stripped, and normalised to exactly one leading ``@``
    (every leading ``@`` is stripped, then one is re-added), and used
    verbatim otherwise — no quoting, no escaping, no case-folding — with
    the order the user gave preserved and the handles joined with single
    spaces. A single clean handle returns behaviour 1's one-handle line
    unchanged (behaviour 11 of plans/file-path-codeowners-interactive.md).

    The owner line is ``/.github/ `` plus the normalised handles — the
    ``/.github/`` prefix is GitHub's "most secure method": the CODEOWNERS
    file owns itself (``doc/external/github/about-code-owners.md``, section
    "CODEOWNERS and branch protection"). A comment line tells the reader to
    EDIT the pre-filled handles to the real owners, who need explicit write
    access to the repository per the same page.

    The handles reach the returned file content only — they are never
    shell- or string-substituted into anything executable. Deterministic:
    the same ``owners`` returns the identical string.

    Raises :class:`CodeownersError` if ``owners`` is empty or
    whitespace-only, or if any handle is empty after stripping the
    optional leading ``@`` (e.g. ``"@"``) — the handle is never guessed.
    """
    tokens = owners.split()
    if not tokens:
        raise CodeownersError(
            "refusing to build a CODEOWNERS body without an owner: "
            "the handle is pre-filled and never guessed"
        )
    handles: List[str] = []
    for token in tokens:
        handle = token.strip().lstrip("@")
        if not handle:
            raise CodeownersError(
                "refusing to build a CODEOWNERS body with an empty handle "
                "{!r}: a handle that is only @ is never guessed".format(token)
            )
        handles.append("@" + handle)
    owner = " ".join(handles)
    return (
        "# CODEOWNERS — pre-filled; edit the handle below to the real\n"
        "# owners, who need explicit write access to the repository.\n"
        "/.github/ {owner}\n"
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


def commit_commands() -> List[str]:
    """Return the three git command strings for the CODEOWNERS commit, built never run.

    Behaviour 12 of plans/file-path-codeowners-interactive.md: the path is
    fixed at ``.github/CODEOWNERS`` and the commit message is fixed text, so
    the function takes no parameters — nothing the user typed can be
    interpolated into a command (the handles reach the file content via
    behaviour 11, never a command). The strings are display text for the
    user to run: each stays at most 80 characters, the module imports no
    subprocess and the call produces no side effect. Deterministic: two
    calls return equal lists.
    """
    return [
        "git add {path}".format(path=".github/CODEOWNERS"),
        'git commit -m "{message}"'.format(
            message="Add CODEOWNERS for the review gate"
        ),
        "git push",
    ]


def last_push_step() -> str:
    """Return the extra walkthrough step for the last-push approval rule.

    Behaviour 13 of plans/file-path-codeowners-interactive.md: the six
    walkthrough steps end at the review gate, but a code owner may
    approve their own change, so the gate is weak without the last push
    rule — the cli layer (behaviour 15) prints this step after them. It
    names the UI rule verbatim, "Require approval of the most recent
    reviewable push" (doc/external/github/about-protected-branches.md:
    "the most recent reviewable push must be approved by someone other
    than the person who pushed it"), and the rulesets parameter
    ``require_last_push_approval`` (doc/external/github/rest-api-
    endpoints-for-rules.md). Display text: every line stays at most 80
    characters. Pure: the call prompts, writes and raises nothing;
    deterministic — two calls return the identical string.
    """
    return (
        '7. Also tick "Require approval of the most recent reviewable '
        'push"\n'
        "   (rulesets param require_last_push_approval): a code owner "
        "can\n"
        "   approve their own change, so without it the gate is weak."
    )


def self_approval_warning(owner: str, repo_owner: str) -> Optional[str]:
    """Return the one-line self-approval advisory, or None to print nothing.

    Behaviour 13 of plans/file-path-codeowners-interactive.md: when the
    CODEOWNERS owner the user chose is the repository owner, that owner
    can approve their own change, which weakens the review gate unless
    the ``require_last_push_approval`` rulesets option is on. Both
    handles are normalised — stripped, with every leading ``@``
    removed — then compared case-insensitively. A handle containing
    ``/`` is a team, not a user identity, and never matches: it returns
    None even on an exact match. Differing handles return None (the
    caller prints nothing). On a match, returns exactly one line, at
    most 80 characters for the pinned owner ``iar3-r8``, built with
    ``.format`` so the handle is data, never substituted into anything
    executable. Pure: the call prompts, writes and raises nothing.
    """
    normalised_owner = owner.strip().lstrip("@")
    normalised_repo = repo_owner.strip().lstrip("@")
    if "/" in normalised_owner or "/" in normalised_repo:
        return None
    if normalised_owner.lower() != normalised_repo.lower():
        return None
    return (
        "{owner} repo owner: approve own change unless "
        "require_last_push_approval."
    ).format(owner=normalised_owner)
