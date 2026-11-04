"""Load-bearing-constraint pins on the committed ``.pi/roles`` documents.

``plans/pi-role-prompts.md``, behaviour 14 (each-prompt-carries-its-
load-bearing-constraints), verbatim from the plan:

* Given: each generated role document
* When: it is searched for that role's named constraints
* Then: non-empty, and present — architect: the citation requirement and the
  blocking unknown-interface rule; tester: never weaken a test; docs: ask
  commit-or-branch; tdd-manager: the red/green dispatch and the coder-
  never-edits-a-test rule; coder: the one-liner only
* Error: an absent constraint fails quoting it and naming the role

This is the issue's DoD item "a test asserts each role's prompt is non-empty
and contains its load-bearing constraints". Unlike behaviour 5
(``tests/test_piprompt_lossless.py``), which mechanically checks that every
source XML clause survives conversion, this module names the SPECIFIC
clauses doing the work per role, so a conversion that keeps the words but
drops the operative sentence is caught even where a mechanical clause check
would be coarse.

The containment checks run against the **committed** files' bodies — the
text after the closing frontmatter delimiter is what reaches the Pi session
— read directly, whitespace-normalised the same way
``tests/test_piprompt_lossless.py`` normalises. ``shared-agents`` is the
shared layer pinned by behaviour 7, and the plan names no constraints for
it, so it is deliberately not pinned here (no invented constraints).

These pins are expected to PASS on arrival: behaviour 5's losslessness
already guarantees every source clause survives into the bodies, and the
named constraints are all source clauses. If a named constraint is absent
from a committed body, that is a genuine finding reported by the failing
test — quoting the absent constraint and naming the role file — not a
reason to weaken the assertion.
"""

import re
import unittest
from pathlib import Path
from typing import Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# The checked-in deliverable these pins protect.
ROLES_ROOT = REPO_ROOT / ".pi" / "roles"


def _normalise(text):
    # type: (str) -> str
    """Collapse whitespace runs so containment is checked on words, not
    on layout (same normalisation as ``tests/test_piprompt_lossless.py``)."""
    return re.sub(r"\s+", " ", text).strip()


def _body_of(role_file):
    # type: (Path) -> str
    """Read the committed role document at *role_file* and return its
    markdown body — the text after the closing ``---`` delimiter,
    surrounding blank lines stripped.

    Mirrors ``tests/test_piprompt_delivered.py``'s frontmatter split: a
    missing file, or a document whose first line is not the opening
    ``---`` or that never closes it, raises AssertionError naming the
    file, so a malformed document fails at extraction instead of
    reaching the containment checks as an unreadable or frontmatter-
    contaminated body.
    """
    if not role_file.is_file():
        raise AssertionError(
            "committed role document is missing: .pi/roles/%s"
            % role_file.name
        )
    lines = role_file.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise AssertionError(
            ".pi/roles/%s does not open with the '---' frontmatter "
            "delimiter on line 1 (first line: %r)"
            % (role_file.name, lines[0] if lines else None)
        )
    close_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            close_index = index
            break
    if close_index is None:
        raise AssertionError(
            ".pi/roles/%s has no closing '---' delimiter after line 1"
            % role_file.name
        )
    return "\n".join(lines[close_index + 1 :]).strip()


class RoleConstraintsBase(unittest.TestCase):
    """Behaviour 14: the committed role document is non-empty and carries
    every one of that role's named load-bearing constraints.

    One subclass per role (precedent: ``tests/test_piprompt_lossless.py``),
    so an absent constraint names the role file it came from.
    """

    role = ""  # type: str
    constraints = ()  # type: Tuple[str, ...]

    def setUp(self):
        if not self.role:
            self.skipTest("abstract base class; run a concrete subclass")

    def test_committed_body_is_non_empty_and_carries_its_named_constraints(self):
        # Arrange + Act: the committed document's body, the text that
        # reaches the Pi session.
        role_file = ROLES_ROOT / (self.role + ".md")
        body = _body_of(role_file)

        # Assert 1: the document is non-empty.
        self.assertTrue(
            body,
            "the committed .pi/roles/%s body is empty; the %s role would "
            "be injected with no instructions at all"
            % (self.role + ".md", self.role),
        )

        # Assert 2: every named constraint is present, whitespace-
        # normalised.
        normalised_body = _normalise(body)
        missing = [
            constraint
            for constraint in self.constraints
            if constraint not in normalised_body
        ]
        if missing:
            # self.fail (not assertFalse's message argument) so the
            # diagnostic is only built on the failure path.
            self.fail(
                "%d load-bearing constraint(s) of the %s role are absent "
                "from .pi/roles/%s; the first missing constraint is %r"
                % (len(missing), self.role, self.role + ".md", missing[0])
            )


class ArchitectConstraintsCase(RoleConstraintsBase):
    role = "architect"
    constraints = (
        # The citation requirement: a third-party fact is never asserted
        # without a checkable source behind it.
        "Cite the saved file or URL wherever a third-party fact is asserted",
        # The blocking unknown-interface rule: an unknown interface stops
        # the plan rather than being planned around.
        "Unknown third-party interfaces are blocking. Do not plan around them.",
    )


class TesterConstraintsCase(RoleConstraintsBase):
    role = "tester"
    constraints = (
        # Never weaken a test to make it pass — the clause that keeps the
        # red/green loop honest from the testing side.
        "Never weaken a test to make it pass",
    )


class DocsConstraintsCase(RoleConstraintsBase):
    role = "docs"
    constraints = (
        # Ask commit-or-branch: the documentation scope is the user's
        # call, never the documenter's assumption.
        "Always ask the user whether to document the current commit or the current branch",
    )


class TddManagerConstraintsCase(RoleConstraintsBase):
    role = "tdd-manager"
    constraints = (
        # The red/green dispatch: the overview line that states the
        # manager's core job is keeping the cycle honest.
        "red/green cycle kept honest",
        # The coder-never-edits-a-test rule: green means making the red
        # tests pass, changing no test file.
        "Make exactly those tests pass, changing no test file",
    )


class CoderConstraintsCase(RoleConstraintsBase):
    role = "coder"
    constraints = (
        # The one-liner. Presence only — the byte-exact pin lives in
        # tests/test_piprompt_delivered.py (behaviour 10) and is not
        # duplicated here.
        "You write and modify code.",
    )


if __name__ == "__main__":
    unittest.main()
