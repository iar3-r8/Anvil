"""Tests for ``anvilkit.pi.piprompt.body_from_xml`` - the instruction-XML
to markdown prompt-body converter.

``plans/pi-role-prompts.md``, behaviour 4 (xml-to-prompt-body): given one
instruction XML's text, ``body_from_xml(text)`` returns a markdown body -
deterministic, so the same input twice is byte-identical. Error: malformed
XML raises ``PromptError`` naming the parse position; an empty string
raises ``PromptError`` too. Never a partial body, never a silent
empty-string return (behaviour 9 pins no-empty-body at the document
level; this behaviour pins it at the function level).

Pinned signature::

    body_from_xml(text: str) -> str

in module ``anvilkit.pi.piprompt``; the exception class ``PromptError``
is defined in the same module.

The production module does not exist yet. Following the house precedent
for red tests against a not-yet-existing module (``tests/test_piverdict.py``,
commit 930e968), the module is imported lazily through ``_piprompt()``
INSIDE each test body rather than at module top level, so this file
collects cleanly and every test is red for the right reason - the
``ModuleNotFoundError`` raised at the import step. A file-level
collection/import error is not an acceptable red.

The input is a small hand-written instruction XML (``FIXTURE_XML``): this
behaviour is about the conversion function in isolation, not about the
large real rule sources, which the lossless-conversion behaviour (5)
covers once the generator exists.
"""

import importlib
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _normalise(text):
    """Collapse whitespace runs so containment is checked on words, not
    on layout."""
    return re.sub(r"\s+", " ", text).strip()


# One instruction XML's text: a minimal, hand-written document - an
# <instructions> root holding an <overview>, a <workflow> with a single
# <step>, and a <best_practices> with a single <practice>. Kept small on
# purpose; the converter is tested in isolation.
FIXTURE_XML = (
    "<instructions>\n"
    "  <overview>Verify that the described behaviour holds.</overview>\n"
    "  <workflow>\n"
    '    <step number="1">\n'
    "      <title>Run the check</title>\n"
    "      Confirm the output matches the expectation.\n"
    "    </step>\n"
    "  </workflow>\n"
    "  <best_practices>\n"
    "    <practice>Keep the check fast and isolated.</practice>\n"
    "  </best_practices>\n"
    "</instructions>\n"
)

# The source text nodes the body must carry through.
OVERVIEW_TEXT = "Verify that the described behaviour holds."
STEP_TEXT = "Confirm the output matches the expectation."

# The fixture's tag names, whose XML spellings (<name> / </name>) must
# NOT appear verbatim in the body: the output is markdown, not a string
# dump of the source.
TAG_NAMES = (
    "instructions",
    "overview",
    "workflow",
    "step",
    "best_practices",
    "practice",
)

# An unclosed document: the parser reports an error instead of returning
# a tree, so no partial body is even possible.
MALFORMED_XML = "<instructions><workflow>"


class BodyFromXmlMarkdownTestCase(unittest.TestCase):
    """Happy path: one instruction XML's text converts to a non-empty
    markdown body carrying the source's text nodes, deterministically,
    without echoing the source's XML markup."""

    def _piprompt(self):
        """Import ``anvilkit.pi.piprompt`` lazily so this file collects
        while the module does not exist yet."""
        return importlib.import_module("anvilkit.pi.piprompt")

    def test_body_from_xml_valid_instructions_returns_markdown_containing_source_text(
        self,
    ) -> None:
        # Act: one instruction XML's text in, a markdown body out.
        piprompt = self._piprompt()
        body = piprompt.body_from_xml(FIXTURE_XML)

        # Assert: a non-empty string carrying the overview and step text
        # (whitespace-normalised containment).
        self.assertIsInstance(body, str)
        self.assertTrue(body.strip())
        normalised_body = _normalise(body)
        self.assertIn(
            _normalise(OVERVIEW_TEXT),
            normalised_body,
            "the overview text is missing from the body: %r" % body,
        )
        self.assertIn(
            _normalise(STEP_TEXT),
            normalised_body,
            "the step text is missing from the body: %r" % body,
        )

    def test_body_from_xml_same_input_twice_returns_byte_identical_body(
        self,
    ) -> None:
        # Act: the same input, twice.
        piprompt = self._piprompt()
        first = piprompt.body_from_xml(FIXTURE_XML)
        second = piprompt.body_from_xml(FIXTURE_XML)

        # Assert: deterministic - the same input twice is identical.
        self.assertEqual(first, second)

    def test_body_from_xml_output_does_not_echo_raw_xml_tags(self) -> None:
        # Act
        piprompt = self._piprompt()
        body = piprompt.body_from_xml(FIXTURE_XML)

        # Assert: no XML tag spelling survives verbatim in the body -
        # the conversion is to markdown, not a string dump.
        for name in TAG_NAMES:
            for tag in ("<%s>" % name, "</%s>" % name):
                self.assertNotIn(
                    tag,
                    body,
                    "raw XML tag %s survived verbatim in the body: %r"
                    % (tag, body),
                )


class BodyFromXmlErrorTestCase(unittest.TestCase):
    """Error path: malformed XML and an empty string both raise
    ``PromptError`` - never a partial body, never a silent empty-string
    return."""

    def _piprompt(self):
        """Import ``anvilkit.pi.piprompt`` lazily so this file collects
        while the module does not exist yet."""
        return importlib.import_module("anvilkit.pi.piprompt")

    def test_body_from_xml_malformed_xml_raises_prompt_error_naming_parse_position(
        self,
    ) -> None:
        # Arrange: an unclosed document - the parser cannot return a
        # tree for it.

        # Act / Assert: PromptError, and the message names the parse
        # position (a line number or a parse-error fragment) rather
        # than a bare "malformed XML".
        piprompt = self._piprompt()
        with self.assertRaises(piprompt.PromptError) as ctx:
            piprompt.body_from_xml(MALFORMED_XML)
        message = str(ctx.exception)
        self.assertRegex(
            message,
            r"\d+",
            "the error must name the parse position; got: %r" % message,
        )

    def test_body_from_xml_empty_string_raises_prompt_error(self) -> None:
        # Arrange: no XML at all.

        # Act / Assert: refused outright - no partial body, no silent
        # empty-string return.
        piprompt = self._piprompt()
        with self.assertRaises(piprompt.PromptError):
            piprompt.body_from_xml("")


if __name__ == "__main__":
    unittest.main()
