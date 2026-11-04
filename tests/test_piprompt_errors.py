"""Tests for the document-level error surface of
``anvilkit.pi.piprompt.role_document``.

``plans/pi-role-prompts.md``, behaviour 9
(unknown-role-or-missing-source-raises): given an unknown role name, or
a known role whose source file is absent, when the document for it is
built, then nothing is returned. Error: ``PromptError`` names the role
and the path it looked for; no partial document and no empty-body
fallback is ever produced.

Behaviours 4-8 are green: ``source_for`` already pins unknown-name and
``shared-agents`` at the MAP level, and ``role_document`` already
refuses ``shared-agents``. This file pins the DOCUMENT-LEVEL error
surface: building a document never returns a partial or empty-body
document.

Pinned seam for this cycle::

    role_document(name: str, templates_root: Optional[Path] = None) -> str

The optional ``templates_root`` parameter defaults to the tracked
``templates/roo_template/`` directory; it is the test seam for the
missing-source error and lets a test point at a temp dir. The
positive-path tests call it zero-argument or with the default, so
tracked-path behaviour stays pinned.

RED expectation (this commit): ``role_document`` does not accept a
``templates_root`` keyword yet, so the missing-source test fails with
``TypeError: role_document() got an unexpected keyword argument
'templates_root'``: a TypeError on a missing parameter is the right
red reason for the seam (the function cannot accept the kwarg yet).
The unknown-name test and the no-empty-body test exercise behaviour
that already landed in earlier cycles and are expected to pass on
arrival; they pin the document-level half of behaviour 9 against the
real tracked sources.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit.pi import piprompt  # noqa: E402

# The tracked template root role_document reads from by default.
TEMPLATES_ROOT = REPO_ROOT / "templates" / "roo_template"

# The five roles role_document serves: the four XML roles plus the
# coder.
ROLE_NAMES = ("architect", "tester", "docs", "tdd-manager", "coder")

# The four XML sources, relative to templates/roo_template/ - the same
# values behaviour 8 pins for source_for, so the two cannot drift.
XML_SOURCES = {
    "architect": "rules-architect/instructions.xml",
    "tester": "rules-qna-tester/instructions.xml",
    "docs": "rules-docs-manager/guidelines.xml",
    "tdd-manager": "rules-tdd-manager/instructions.xml",
}

# The role whose source is removed in the missing-source test, and the
# relative source path it removes from the temp tree.
MISSING_ROLE = "architect"
MISSING_SOURCE = XML_SOURCES[MISSING_ROLE]


def _split_document(document: str) -> Tuple[str, str]:
    """Split one role document into ``(frontmatter_text, body_text)``.

    Mirrors the extraction in ``tests/test_piprompt_frontmatter.py``
    and ``tests/test_piprompt_shared.py``: the frontmatter block is the
    lines between the opening ``---`` on line 1 and the first closing
    ``---`` after it. Raises AssertionError naming the problem when a
    delimiter is missing, so a malformed document fails at the
    extraction step instead of slipping through to a vacuous check.
    """
    lines = document.splitlines()
    if not lines or lines[0].strip() != "---":
        raise AssertionError(
            "role document does not open with the '---' frontmatter "
            "delimiter on line 1 (first line: %r)"
            % (lines[0] if lines else None)
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
    return "\n".join(lines[1:close_index]), "\n".join(lines[close_index + 1 :])


def _copy_templates_root_into(tmp: str) -> Path:
    """Copy the tracked ``templates/roo_template/`` tree into ``tmp``
    and return the copy's root.

    The copy is byte-for-byte: the missing-source test relies on it
    carrying every source except the one it deletes, and the
    anti-vacuity assertions in the test verify exactly that.
    """
    return shutil.copytree(TEMPLATES_ROOT, Path(tmp) / "roo_template")


class RoleDocumentErrorSurfaceCase(unittest.TestCase):
    """Behaviour 9: building a document for an unknown role, or for a
    known role whose source file is absent, raises PromptError naming
    the role and the path it looked for; no partial document and no
    empty-body fallback is ever produced."""

    def test_role_document_unknown_name_raises_prompt_error_naming_it(self) -> None:
        # Act + Assert: building a document for a name that is not one
        # of the five roles raises PromptError naming the offender.
        # The six-name listing is already pinned at the source_for
        # level (tests/test_piprompt_source_map.py); at the document
        # level only the offender has to be named.
        with self.assertRaises(piprompt.PromptError) as ctx:
            piprompt.role_document("orchestrator")
        self.assertIn(
            "orchestrator",
            str(ctx.exception),
            "the PromptError for an unknown role must name the "
            "offending name (got: %r)" % str(ctx.exception),
        )

    def test_role_document_missing_source_raises_prompt_error_naming_role_and_path(
        self,
    ) -> None:
        # Arrange: a temp dir holding a copy of the tracked
        # templates/roo_template/ tree, with the architect's source
        # removed from it.
        with tempfile.TemporaryDirectory() as tmp:
            templates_root = _copy_templates_root_into(tmp)
            removed = templates_root / MISSING_SOURCE

            # Anti-vacuity (before the call): the temp tree carried
            # the three other XML sources and the rules/ dir, so the
            # failure below is genuinely "the one file is missing",
            # not "the whole tree is absent".
            for role, source in XML_SOURCES.items():
                if role != MISSING_ROLE:
                    self.assertTrue(
                        (templates_root / source).is_file(),
                        "the temp templates tree did not carry %s: the "
                        "missing-source failure would be 'the whole "
                        "tree is absent', not 'the one file is missing'"
                        % source,
                    )
            self.assertTrue(
                (templates_root / "rules").is_dir(),
                "the temp templates tree did not carry the rules/ dir: "
                "the missing-source failure would be 'the whole tree "
                "is absent', not 'the one file is missing'",
            )

            removed.unlink()

            # Act + Assert: building the document against that tree
            # raises PromptError naming BOTH the role and the missing
            # relative path. assertRaises guarantees nothing is
            # returned, so the no-partial-document half of the
            # behaviour is covered by this raise - it is not
            # duplicated.
            with self.assertRaises(piprompt.PromptError) as ctx:
                piprompt.role_document(MISSING_ROLE, templates_root=templates_root)
            message = str(ctx.exception)
            self.assertIn(
                MISSING_ROLE,
                message,
                "the PromptError for a missing source must name the "
                "role (got: %r)" % message,
            )
            self.assertIn(
                MISSING_SOURCE,
                message,
                "the PromptError for a missing source must name the "
                "relative path it looked for (got: %r)" % message,
            )

    def test_role_document_bodies_are_never_empty_or_whitespace_only(self) -> None:
        # Act: build each of the five role documents against the
        # default tracked path and take the body after the closing
        # '---'.
        for role in ROLE_NAMES:
            document = piprompt.role_document(role)
            _, body = _split_document(document)

            # Assert: the body is non-empty and not whitespace-only -
            # an empty-body fallback is never produced. This pins the
            # "no silent empty-body return" half of the behaviour
            # against the real tracked sources.
            self.assertTrue(
                body.strip(),
                "role_document(%r) returned a document whose body after "
                "the closing '---' is empty or whitespace-only: an "
                "empty-body fallback is never returned" % role,
            )


if __name__ == "__main__":
    unittest.main()
