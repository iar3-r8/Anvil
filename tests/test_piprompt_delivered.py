"""Coverage pins on the already-delivered ``.pi/roles`` state.

``plans/pi-role-prompts.md``, behaviours 10 and 13. Both behaviours pin the
committed state that behaviours 4-12 already deliver; like behaviours 1-3 and
the phase-9 pin commits, these tests are expected to pass on arrival - they
lock the delivered state against future drift.

Behaviour 10 (coder-prompt-preserves-one-liner), verbatim from the plan:

* Given: the ``coder`` role
* When: its document is built
* Then: the body is exactly ``You write and modify code.`` (decision 1 -
  nothing authored)
* Error: none beyond behaviour 9

Pinned two ways: the committed ``.pi/roles/coder.md`` file, and the
regenerated document from ``anvilkit.pi.piprompt.role_document("coder")``,
so the pin holds even if someone regenerates the files. Behaviour 12
(``tests/test_piprompt_drift.py``) pins byte-equality of the committed file
against regeneration separately; these tests pin the one-liner content
specifically.

Behaviour 13 (six-files-present), verbatim from the plan:

* Given: ``.pi/roles/``
* When: its ``*.md`` entries are listed
* Then: exactly ``shared-agents``, ``architect``, ``coder``, ``tester``,
  ``docs``, ``tdd-manager``
* Error: an extra or missing file fails naming it, so an orphan left by a
  renamed role cannot linger and be injected

The second listing test goes one step further than the plan's ``*.md``
wording and lists **all** entries: an orphan with a non-``.md`` extension
cannot be injected either, so it must not linger.
"""

import unittest
from pathlib import Path
from typing import Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

from anvilkit.pi import piprompt  # noqa: E402

# The checked-in deliverable these pins protect.
ROLES_ROOT = REPO_ROOT / ".pi" / "roles"
CODER_FILE = ROLES_ROOT / "coder.md"

# Behaviour 10's literal: the coder's entire body, nothing authored.
CODER_ONE_LINER = "You write and modify code."

# Behaviour 13: the six and only six ``.pi/roles`` documents.
EXPECTED_STEMS = {
    "shared-agents",
    "architect",
    "coder",
    "tester",
    "docs",
    "tdd-manager",
}


def _split_role_document(document):
    # type: (str) -> Tuple[str, str]
    """Split one role document into ``(frontmatter_text, body_text)``.

    Mirrors ``tests/test_piprompt_frontmatter.py``: the frontmatter block
    is the lines between the opening ``---`` on line 1 and the first
    closing ``---`` after it. Raises AssertionError naming the problem
    when a delimiter is missing, so a malformed document fails at the
    extraction step instead of slipping through to a vacuous comparison.
    """
    lines = document.splitlines()
    if not lines or lines[0].strip() != "---":
        raise AssertionError(
            "role document does not open with the '---' frontmatter "
            "delimiter on line 1 (first line: %r)" % (lines[0] if lines else None)
        )
    close_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            close_index = index
            break
    if close_index is None:
        raise AssertionError(
            "role document has no closing '---' delimiter after line 1"
        )
    frontmatter_text = "\n".join(lines[1:close_index])
    body_text = "\n".join(lines[close_index + 1 :])
    return frontmatter_text, body_text


class CoderPromptPreservesOneLinerCase(unittest.TestCase):
    """Behaviour 10: the coder document's body is exactly the one-liner."""

    def test_committed_coder_body_is_exactly_the_one_liner(self) -> None:
        # Act: read the committed coder document and extract its body -
        # the text after the closing '---', surrounding blank lines
        # stripped.
        document = CODER_FILE.read_text(encoding="utf-8")
        _frontmatter, body = _split_role_document(document)
        body = body.strip()

        # Assert: byte-exact, not just contains.
        self.assertEqual(
            body,
            CODER_ONE_LINER,
            "the committed .pi/roles/coder.md body must be exactly %r "
            "(decision 1 - nothing authored), got %r"
            % (CODER_ONE_LINER, body),
        )

    def test_regenerated_coder_body_is_exactly_the_one_liner(self) -> None:
        # Act: regenerate the coder document via the pinned seam and
        # extract its body.
        document = piprompt.role_document("coder")
        _frontmatter, body = _split_role_document(document)
        body = body.strip()

        # Assert: the pin holds on regeneration - generation and the
        # committed file agree on the one-liner specifically.
        self.assertEqual(
            body,
            CODER_ONE_LINER,
            "the regenerated coder document body must be exactly %r "
            "(decision 1 - nothing authored), got %r"
            % (CODER_ONE_LINER, body),
        )


class SixFilesPresentCase(unittest.TestCase):
    """Behaviour 13: ``.pi/roles/`` holds exactly the six ``.md`` files,
    and nothing else."""

    def test_committed_roles_directory_has_exactly_the_six_md_stems(self) -> None:
        # Act: list the ``*.md`` entries and reduce them to stems.
        stems = {
            entry.stem for entry in sorted(ROLES_ROOT.glob("*.md")) if entry.is_file()
        }

        # Assert: set equality, not subset - an orphan or a missing file
        # both fail, each named in the failure message.
        self.assertEqual(
            stems,
            EXPECTED_STEMS,
            ".pi/roles/ must contain exactly %s (missing: %s, extra: %s)"
            % (
                sorted(EXPECTED_STEMS),
                sorted(EXPECTED_STEMS - stems),
                sorted(stems - EXPECTED_STEMS),
            ),
        )

    def test_roles_directory_has_no_non_md_entries(self) -> None:
        # Act: list ALL entries in the directory, not just ``*.md``.
        entries = {entry.name for entry in sorted(ROLES_ROOT.iterdir())}

        # Assert: an orphan with the wrong extension cannot be injected
        # either, so it must not linger.
        offenders = sorted(
            name
            for name in entries
            if name not in {stem + ".md" for stem in EXPECTED_STEMS}
        )
        self.assertEqual(
            offenders,
            [],
            ".pi/roles/ contains non-'.md' or orphan entries: %s; every "
            "entry must be one of the six '%s' files"
            % (offenders, "'.md', '".join(sorted(EXPECTED_STEMS)) + "'.md"),
        )


if __name__ == "__main__":
    unittest.main()
