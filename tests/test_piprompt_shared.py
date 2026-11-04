"""Tests for ``anvilkit.pi.piprompt.shared_document`` - the shared
chain-root document of the ``.pi/roles`` prompt chain.

``plans/pi-role-prompts.md``, behaviour 7 (shared-prompt-is-root):
given ``rules/AGENTS.md``, ``rules/architecture.md`` and
``rules/coding-guidelines.md``, when ``shared_document()``
concatenates the three in that fixed order, then one
``shared-agents.md`` with a ``description`` and no ``extends`` - it
is the chain root. Error: a missing source file raises
``PromptError`` naming it; the order is fixed, so the byte-compare in
behaviour 12 catches a reordering.

Source fact pinned here: each of the three tracked sources already
carries its own Zoo Code YAML frontmatter block (``---`` /
``description: ...`` / ``trigger: always_on`` / ``---``) followed by a
markdown body. The generated document has exactly one frontmatter
block of its own, so the seam must strip each source's own frontmatter
block when concatenating: the ``trigger:`` lines are Zoo-specific
dispatch metadata, not rules - dropping them is a recorded mechanical
choice, not a rule drop - and every markdown content line of each
source must survive.

Pinned seam for this cycle::

    shared_document(rules_dir: Optional[Path] = None) -> str

builds the complete ``shared-agents`` document (YAML frontmatter block
plus body) from the three tracked sources at
``templates/roo_template/rules/``. The optional ``rules_dir``
parameter defaults to that tracked path; it is the test seam for the
missing-source error and is flagged in the delivery report as a seam
decision for the coder to confirm (the plan names the zero-argument
shape).

RED expectation (this commit): ``shared_document`` does not exist
yet. The module ``anvilkit.pi.piprompt`` DOES exist (behaviours 4-6
are green), so it is imported at module top level - the file
therefore collects with no import/collection/syntax error, and every
test that calls the seam fails with ``AttributeError: module
'anvilkit.pi.piprompt' has no attribute 'shared_document'``: a clean
per-test AttributeError is the right red reason, not a collection
error. The anti-vacuity test pins the source-file extraction (a fact
about the tracked sources, not the new seam) and passes in red.

Frontmatter extraction follows the house precedent in
``tests/test_piprompt_frontmatter.py``: the opening ``---`` on line
1, the first closing ``---`` after it, and the lines between are the
frontmatter block. Parsing goes through ``anvilkit.yamlio.loads`` -
``yamlio`` is the only module that may touch ``yaml``, and the
generator emits frontmatter as literal text that the tests parse back.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import yamlio  # noqa: E402
from anvilkit.pi import piprompt  # noqa: E402

# The three shared rule sources, in the fixed order behaviour 7 pins.
# The shared document concatenates them in exactly this order.
RULES_DIR = REPO_ROOT / "templates" / "roo_template" / "rules"
SHARED_SOURCES = ("AGENTS.md", "architecture.md", "coding-guidelines.md")

# Routing fields a role file must never claim: routing stays in
# pirole.ROLES, so the shared document is not a routing authority.
ROUTING_KEYS = ("model", "thinking", "tools")

# Zoo dispatch metadata each source's own frontmatter carries and that
# must not survive into the generated document.
STRIPPED_METADATA = ("trigger:", "always_on")


def _split_document(document):
    # type: (str) -> Tuple[str, str]
    """Split one prompt document into ``(frontmatter_text, body_text)``.

    Mirrors the extraction in ``tests/test_piprompt_frontmatter.py``:
    the frontmatter block is the lines between the opening ``---`` on
    line 1 and the first closing ``---`` after it. Raises AssertionError
    naming the problem when a delimiter is missing, so a malformed
    document fails at the extraction step instead of slipping through
    to a vacuous parse.
    """
    lines = document.splitlines()
    if not lines or lines[0].strip() != "---":
        raise AssertionError(
            "shared document does not open with the '---' frontmatter "
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
            "shared document has no closing '---' delimiter after line 1"
        )
    frontmatter_text = "\n".join(lines[1:close_index])
    body_text = "\n".join(lines[close_index + 1 :])
    return frontmatter_text, body_text


def _shared_frontmatter():
    # type: () -> dict
    """Build the shared document and parse its frontmatter block via
    ``yamlio``.

    Raises AssertionError (naming the missing delimiter) when the
    document's ``---`` delimiters are missing; lets
    ``yamlio.YamlError`` propagate when the block does not parse, so a
    malformed block fails loudly at the parse step.
    """
    document = piprompt.shared_document()
    frontmatter_text, _ = _split_document(document)
    return yamlio.loads(frontmatter_text)


def _shared_body_lines():
    # type: () -> List[str]
    """The shared document's body, one whitespace-normalised non-empty
    line per entry - the comparison side of the order/completeness
    check."""
    document = piprompt.shared_document()
    _, body = _split_document(document)
    return [
        " ".join(line.split()) for line in body.splitlines() if line.strip()
    ]


def _source_content_lines(name):
    # type: (str) -> List[str]
    """The non-empty markdown content lines of one rule source, after
    its own ``---`` frontmatter block, whitespace-normalised.

    Every markdown content line of the source must survive into the
    shared document; this is the comparison side of the completeness
    check, and its non-triviality is itself pinned (anti-vacuity).
    Raises AssertionError naming the source when its own frontmatter
    delimiters are missing, so the body cannot be located.
    """
    path = RULES_DIR / name
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise AssertionError(
            "rule source %s does not open with the '---' frontmatter "
            "delimiter on line 1 (first line: %r); the source body "
            "cannot be located" % (name, lines[0] if lines else None)
        )
    close_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            close_index = index
            break
    if close_index is None:
        raise AssertionError(
            "rule source %s has no closing '---' delimiter after line 1; "
            "the source body cannot be located" % name
        )
    return [
        " ".join(line.split())
        for line in lines[close_index + 1 :]
        if line.strip()
    ]


def _subsequence_end(body_lines, content_lines, start, source):
    # type: (List[str], List[str], int, str) -> int
    """Match ``content_lines`` as an in-order subsequence of
    ``body_lines`` starting at ``start``.

    Returns the index of the last matched line, or raises
    AssertionError naming the first content line that does not match.
    Matching starts strictly after the previous source's last matched
    line, so the call chain across the three sources pins the fixed
    order as well as the per-source completeness.
    """
    position = start
    last = start - 1
    for content in content_lines:
        found = None
        while position < len(body_lines):
            if body_lines[position] == content:
                found = position
                break
            position += 1
        if found is None:
            raise AssertionError(
                "%s: content line %r does not appear in the shared "
                "document body after line index %d (the line is missing "
                "or out of order)" % (source, content, start)
            )
        last = found
        position = found + 1
    return last


class SharedDocumentRootCase(unittest.TestCase):
    """Behaviour 7: the shared chain root is the three tracked rule
    sources concatenated in fixed order under one frontmatter block -
    a ``description`` and no ``extends``."""

    def test_shared_document_opens_with_frontmatter_and_has_non_empty_description(
        self,
    ) -> None:
        # Act: build the shared document and parse its frontmatter
        # block via yamlio.
        document = piprompt.shared_document()
        lines = document.splitlines()
        frontmatter = _shared_frontmatter()

        # Assert: the document opens with '---' on line 1, the
        # frontmatter parses to a mapping, and the description is a
        # non-empty string.
        self.assertTrue(
            lines and lines[0].strip() == "---",
            "shared document must open with the '---' frontmatter "
            "delimiter on line 1 (first line: %r)"
            % (lines[0] if lines else None),
        )
        self.assertIsInstance(
            frontmatter,
            dict,
            "shared document frontmatter did not parse to a mapping (got %s)"
            % type(frontmatter).__name__,
        )
        description = frontmatter.get("description")
        self.assertIsInstance(
            description,
            str,
            "shared document frontmatter 'description' is not a string "
            "(keys: %r)" % sorted(frontmatter),
        )
        self.assertTrue(
            description.strip(),
            "shared document frontmatter 'description' is empty",
        )

    def test_shared_document_frontmatter_has_no_extends_or_routing_keys(self) -> None:
        # Act: parse the shared document's frontmatter block.
        frontmatter = _shared_frontmatter()

        # Assert: no 'extends' - the shared document is the chain root
        # and has no parent to extend - and no routing keys, so the
        # document is not a routing authority. Any present key is
        # named.
        self.assertNotIn(
            "extends",
            frontmatter,
            "shared document frontmatter carries 'extends': the shared "
            "document is the chain root and has no parent to extend",
        )
        present = [key for key in ROUTING_KEYS if key in frontmatter]
        self.assertEqual(
            present,
            [],
            "shared document frontmatter must not carry routing keys %r "
            "(routing stays in pirole.ROLES); found: %r"
            % (list(ROUTING_KEYS), present),
        )

    def test_shared_document_body_carries_each_sources_content_in_fixed_order(
        self,
    ) -> None:
        # Act: take the shared body's normalised lines and match each
        # source's content lines as an in-order subsequence, starting
        # strictly after the previous source's last matched line.
        body_lines = _shared_body_lines()
        start = 0
        for name in SHARED_SOURCES:
            content_lines = _source_content_lines(name)
            self.assertTrue(
                content_lines,
                "%s: no content lines were extracted after the "
                "frontmatter block; the completeness check would be "
                "vacuous" % name,
            )
            start = _subsequence_end(body_lines, content_lines, start, name) + 1

        # Assert: reaching this point without the helpers raising means
        # every non-empty content line of all three sources appears in
        # the body, each source in order and the sources in the fixed
        # order AGENTS.md, architecture.md, coding-guidelines.md.

    def test_shared_document_carries_no_source_frontmatter_metadata(self) -> None:
        # Act: build the shared document.
        document = piprompt.shared_document()

        # Assert: neither 'trigger:' nor 'always_on' appears anywhere
        # in the document - the stripped dispatch metadata of a
        # source's own frontmatter block must not reappear.
        for token in STRIPPED_METADATA:
            self.assertNotIn(
                token,
                document,
                "shared document carries the stripped Zoo dispatch "
                "metadata %r: a source's own frontmatter block leaked "
                "into the document" % token,
            )

    def test_shared_document_is_byte_identical_across_calls(self) -> None:
        # Act: build the document twice.
        first = piprompt.shared_document()
        second = piprompt.shared_document()

        # Assert: deterministic - byte-identical.
        self.assertEqual(
            first,
            second,
            "shared_document must be deterministic: two calls returned "
            "different documents",
        )

    def test_shared_document_missing_source_raises_prompt_error_naming_it(self) -> None:
        # Arrange: a rules dir carrying two of the three sources, with
        # the tracked content of the ones present.
        missing = "coding-guidelines.md"
        with tempfile.TemporaryDirectory() as tmp:
            rules_dir = Path(tmp)
            for name in SHARED_SOURCES:
                if name != missing:
                    (rules_dir / name).write_text(
                        (RULES_DIR / name).read_text(encoding="utf-8"),
                        encoding="utf-8",
                    )

            # Act + Assert: building against that dir raises
            # PromptError naming the missing file.
            with self.assertRaises(piprompt.PromptError) as ctx:
                piprompt.shared_document(rules_dir=rules_dir)
            self.assertIn(
                missing,
                str(ctx.exception),
                "PromptError must name the missing source file (got: %s)"
                % ctx.exception,
            )

    def test_source_content_extraction_is_non_trivial(self) -> None:
        # Act: extract each tracked source's content lines - a fact
        # about the sources, not the seam, so this passes in red and
        # keeps the completeness check honest in green.
        for name in SHARED_SOURCES:
            content_lines = _source_content_lines(name)

            # Assert: the extraction is non-trivial, so the
            # completeness check cannot pass on an empty comparison.
            self.assertGreaterEqual(
                len(content_lines),
                5,
                "%s: only %d content lines were extracted after the "
                "frontmatter block; the completeness check would be "
                "vacuous" % (name, len(content_lines)),
            )


if __name__ == "__main__":
    unittest.main()
