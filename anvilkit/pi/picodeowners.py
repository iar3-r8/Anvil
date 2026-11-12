"""Build the CODEOWNERS walkthrough text for the free-plan fix.

One job: behaviour 1 of plans/file-path-interactive-free-plan.md —
``codeowners_body`` returns the CODEOWNERS text whose owner line is
``/.github/ @{owner}``, GitHub's own "most secure method": the file owns
itself (the saved page ``doc/external/github/about-code-owners.md``,
section "CODEOWNERS and branch protection"). The module builds text only —
it never writes a file, never makes a network call and never prompts; the
walkthrough steps and the prompt belong to later behaviours.
"""


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
