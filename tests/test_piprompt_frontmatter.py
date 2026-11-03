"""Tests for ``anvilkit.pi.piprompt.role_document`` - the frontmatter
shape of one generated ``.pi/roles/*.md`` document.

``plans/pi-role-prompts.md``, behaviour 6 (frontmatter-shape): given a
generated role document (not ``shared-agents``), when its frontmatter
block is parsed via ``anvilkit.yamlio``, then exactly two keys - a
non-empty ``description`` and ``extends: shared-agents``. Error: a
missing, extra or misspelled key fails naming it; ``model``,
``thinking`` and ``tools`` must be absent (routing stays in
``pirole.ROLES``; a role file is not a routing authority).

Pinned seam for this cycle::

    role_document(name: str) -> str

builds the complete document - a YAML frontmatter block delimited by
``---`` lines, then the markdown body - for one named role from the
tracked ``templates/roo_template/`` rules, reusing
``body_from_xml`` for the XML sources. The positive tests use the
role ``"architect"`` (its source is
``templates/roo_template/rules-architect/instructions.xml``); its body
must be ``body_from_xml``'s output for that file.

RED expectation (this commit): ``role_document`` does not exist yet.
The module ``anvilkit.pi.piprompt`` DOES exist (behaviours 4-5 are
green), so it is imported at module top level - the file therefore
collects with no import/collection/syntax error, and every test fails
at the call site with ``AttributeError: module 'anvilkit.pi.piprompt'
has no attribute 'role_document'``: a clean per-test AttributeError is
the right red reason, not a collection error.

Frontmatter extraction follows the house precedent in
``tests/test_harvest_command.py``: the opening ``---`` on line 1, the
first closing ``---`` after it, and the lines between are the
frontmatter block. Parsing goes through ``anvilkit.yamlio.loads`` -
``yamlio`` is the only module that may touch ``yaml``, and the
generator emits frontmatter as literal text that the tests parse back.
"""

import sys
import unittest
from pathlib import Path
from typing import Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import yamlio  # noqa: E402
from anvilkit.pi import piprompt  # noqa: E402

# The architect role's tracked rule source; its body must be
# body_from_xml's output for exactly this file.
ARCHITECT_SOURCE = (
    REPO_ROOT / "templates" / "roo_template" / "rules-architect" / "instructions.xml"
)

# The two and only two frontmatter keys a role document may carry.
EXPECTED_KEYS = ["description", "extends"]

# Routing fields a role file must never claim: routing stays in
# pirole.ROLES, so a role document is not a routing authority.
ROUTING_KEYS = ("model", "thinking", "tools")


def _split_role_document(document):
    # type: (str) -> Tuple[str, str]
    """Split one role document into ``(frontmatter_text, body_text)``.

    Mirrors the extraction in ``tests/test_harvest_command.py``: the
    frontmatter block is the lines between the opening ``---`` on line
    1 and the first closing ``---`` after it. Raises AssertionError
    naming the problem when a delimiter is missing, so a malformed
    document fails at the extraction step instead of slipping through
    to a vacuous parse.
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


def _architect_frontmatter():
    # type: () -> dict
    """Build the architect role document and parse its frontmatter block
    via ``yamlio``.

    Raises AssertionError (naming the missing delimiter) when the
    document's ``---`` delimiters are missing; lets ``yamlio.YamlError``
    propagate when the block does not parse, so a malformed block fails
    loudly at the parse step.
    """
    document = piprompt.role_document("architect")
    frontmatter_text, _ = _split_role_document(document)
    return yamlio.loads(frontmatter_text)


class RoleDocumentFrontmatterShapeCase(unittest.TestCase):
    """Behaviour 6: a generated role document's frontmatter is exactly
    ``description`` plus ``extends: shared-agents`` - nothing else."""

    def test_role_document_architect_frontmatter_has_exactly_two_keys_description_and_extends(
        self,
    ) -> None:
        # Act: build the architect document, parse its frontmatter block
        # via yamlio.
        document = piprompt.role_document("architect")
        self.assertIsInstance(
            document, str, "role_document must return the document as a string"
        )
        frontmatter = _architect_frontmatter()

        # Assert: EXACTLY the two keys - description and extends. The
        # assertion is on the sorted key list with the offending keys
        # named in the message (symmetric difference), so a missing,
        # extra or misspelled key each fails pointing at itself: the
        # test cannot be vacuous for a wrong shape.
        actual_keys = sorted(frontmatter)
        offending = sorted(set(actual_keys) ^ set(EXPECTED_KEYS))
        self.assertEqual(
            actual_keys,
            EXPECTED_KEYS,
            "architect frontmatter must have exactly the keys %r, got %r "
            "(offending keys: %r)" % (EXPECTED_KEYS, actual_keys, offending),
        )

    def test_role_document_architect_description_non_empty_and_extends_shared_agents(
        self,
    ) -> None:
        # Act: parse the architect frontmatter block.
        frontmatter = _architect_frontmatter()

        # Assert: a non-empty description, and extends pinned exactly
        # to the chain root.
        description = frontmatter.get("description")
        self.assertIsInstance(
            description, str,
            "architect frontmatter 'description' is not a string (keys: %r)"
            % sorted(frontmatter),
        )
        self.assertTrue(
            description.strip(),
            "architect frontmatter 'description' is empty",
        )
        self.assertEqual(
            frontmatter.get("extends"),
            "shared-agents",
            "architect frontmatter must extend 'shared-agents' exactly, got %r"
            % frontmatter.get("extends"),
        )

    def test_role_document_architect_frontmatter_carries_no_routing_keys(self) -> None:
        # Act: parse the architect frontmatter block.
        frontmatter = _architect_frontmatter()

        # Assert: none of model/thinking/tools appears in the parsed
        # mapping - routing stays in pirole.ROLES, a role file is not a
        # routing authority. Any present key is named.
        present = [key for key in ROUTING_KEYS if key in frontmatter]
        self.assertEqual(
            present,
            [],
            "architect frontmatter must not carry routing keys %r "
            "(routing stays in pirole.ROLES); found: %r" % (list(ROUTING_KEYS), present),
        )

    def test_role_document_architect_frontmatter_is_well_formed_yaml_mapping(
        self,
    ) -> None:
        # Act: build the document, split the frontmatter block, parse it.
        document = piprompt.role_document("architect")
        frontmatter_text, _ = _split_role_document(document)
        try:
            frontmatter = yamlio.loads(frontmatter_text)
        except yamlio.YamlError as exc:
            self.fail(
                "architect frontmatter is not well-formed YAML: %s" % exc
            )

        # Assert: the parse result is a mapping, not a scalar or a list -
        # a misspelled or duplicated key cannot slip through as a
        # non-mapping or an extra key.
        self.assertIsInstance(
            frontmatter,
            dict,
            "architect frontmatter did not parse to a mapping (got %s)"
            % type(frontmatter).__name__,
        )

    def test_role_document_shared_agents_raises_prompt_error_chain_root(self) -> None:
        # shared-agents is the chain root: it is built by behaviour 7's
        # shared_body, and a root has no parent to extend - it must
        # never come back from role_document with an ``extends``.
        # Error boundary only; the shared-agents document shape is
        # behaviour 7's cycle, not asserted here.
        with self.assertRaises(piprompt.PromptError) as ctx:
            piprompt.role_document("shared-agents")
        self.assertIn(
            "shared-agents",
            str(ctx.exception),
            "PromptError must name the role it refused (got: %s)" % ctx.exception,
        )


class RoleDocumentBodyReuseCase(unittest.TestCase):
    """The pinned seam reuses ``body_from_xml`` for the XML sources: the
    architect document's body is ``body_from_xml``'s output for its
    tracked source file - the generator never re-derives the body by
    any other path."""

    def test_role_document_architect_body_is_body_from_xml_of_tracked_source(self) -> None:
        # Act: build the architect document, take the body after the
        # closing '---', and build the expected body from the tracked
        # source via the existing behaviour-4 seam.
        document = piprompt.role_document("architect")
        _, body = _split_role_document(document)
        expected = piprompt.body_from_xml(ARCHITECT_SOURCE.read_text(encoding="utf-8"))

        # Assert: the body is body_from_xml's output for the architect
        # source. Both sides are stripped so the comparison is on the
        # body's content, not on the layout whitespace between the
        # closing delimiter and the body.
        self.assertEqual(
            body.strip(),
            expected.strip(),
            "architect document body is not body_from_xml's output for %s",
            ARCHITECT_SOURCE.relative_to(REPO_ROOT),
        )


if __name__ == "__main__":
    unittest.main()
