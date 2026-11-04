"""Tests for ``anvilkit.pi.piprompt.body_from_xml`` - the lossless half of
the instruction-XML to markdown prompt-body conversion.

``plans/pi-role-prompts.md``, behaviour 5 (conversion-is-lossless): given a
source XML and its generated body, every rule, step and overview text node
of the source must appear in the body (whitespace-normalised comparison);
any source clause absent from the body fails quoting the clause and naming
the XML's relative path - nothing is dropped or reworded silently. This is
the mechanical form of the issue's DoD item "any rule dropped or reworded
is recorded with its reason": a dropped clause cannot pass, and a failing
test IS the record of the drop.

Unlike ``tests/test_piprompt_body.py`` (behaviour 4, which converts a small
hand-written fixture in isolation), this module reads the REAL tracked rule
sources at test time - the four XMLs the generator will feed - so a clause
dropped from a real document cannot slip through:

  * ``templates/roo_template/rules-architect/instructions.xml``;
  * ``templates/roo_template/rules-qna-tester/instructions.xml``;
  * ``templates/roo_template/rules-tdd-manager/instructions.xml``;
  * ``templates/roo_template/rules-docs-manager/guidelines.xml``.

Clause extraction follows the house precedent in
``tests/test_templates_rules.py`` and ``tests/test_piprompt_body.py``:
parse with ``xml.etree.ElementTree``, whitespace-normalise by collapsing
runs of whitespace to single spaces, and assert containment on the
normalised body. The clauses are every non-empty ``itertext()`` node of
the parsed document - the element text and tail text across the whole
tree in document order (overview, every step's title and body, every
practice/rule, the delegation contract, the commit conventions, ...).
One test per source file, so a failing clause points at its file.

RED expectation (this commit): the behaviour-4 ``body_from_xml`` renders
the sections it knows and collapses the rest to one bullet per element,
and it refuses a root that is not ``<instructions>`` - so one or more of
the four files loses clauses (or a body). Each such failure is the RIGHT
red reason: the conversion genuinely drops (or refuses) content of a real
tracked source, and the failure names the source path and quotes the
first missing clause. A missing file or a parse error is reported the
same way - named, never a skip (all four sources are tracked).

A guard per file asserts the source yields a meaningful number of
clauses, so a source that stops parsing to nothing cannot make the
containment checks vacuously green.
"""

import importlib
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TEMPLATE_ROOT = REPO_ROOT / "templates" / "roo_template"

# (relative path from templates/roo_template, human label), one test per
# source file so a failing clause points at its file.
RULE_SOURCES = (
    (
        "rules-architect/instructions.xml",
        "architect instructions",
    ),
    (
        "rules-qna-tester/instructions.xml",
        "qna-tester instructions",
    ),
    (
        "rules-tdd-manager/instructions.xml",
        "tdd-manager instructions",
    ),
    (
        "rules-docs-manager/guidelines.xml",
        "docs-manager guidelines",
    ),
)

# A tracked rule source yields many clauses; far fewer than this means
# the document stopped parsing to content and the containment checks
# below would be vacuous.
_MINIMUM_CLAUSES = 10


def _normalise(text):
    # type: (str) -> str
    """Collapse whitespace runs so containment is checked on words, not
    on layout (same normalisation as ``tests/test_piprompt_body.py``)."""
    return re.sub(r"\s+", " ", text).strip()


def _collect_clauses(rel):
    # type: (str) -> List[str]
    """Every non-empty text node of the source at *rel* - element text
    and tail text across the whole tree, in document order -
    whitespace-normalised.

    A missing file or a document that does not parse fails naming *rel*,
    so a corrupt source cannot silently shrink the clause set.
    """
    path = TEMPLATE_ROOT / rel
    if not path.is_file():
        raise AssertionError(
            "tracked rule source is missing: templates/roo_template/%s" % rel
        )
    try:
        root = ET.parse(str(path)).getroot()
    except ET.ParseError as exc:
        raise AssertionError(
            "tracked rule source is not well-formed XML: "
            "templates/roo_template/%s (%s)" % (rel, exc)
        )
    return [
        normalised
        for normalised in (_normalise(part) for part in root.itertext())
        if normalised
    ]


class LosslessConversionBase(unittest.TestCase):
    """Behaviour 5: every clause of one tracked rule source appears in
    its generated body, whitespace-normalised.

    One subclass per source file carries the single containment test,
    so a missing clause names the file it came from. ``_piprompt``
    imports lazily inside the test body (precedent:
    ``tests/test_piprompt_body.py``) so a missing module or a missing
    ``body_from_xml`` fails the test with the import error, never the
    collection.
    """

    rel = None  # type: Tuple[str, str]

    def setUp(self):
        if self.rel is None:
            self.skipTest("abstract base class; run a concrete subclass")

    def _body(self, path):
        """Convert *path*'s text with ``body_from_xml``.

        Returns ``None`` when the converter itself refuses the source
        (its ``PromptError``): a refused source is a dropped source, and
        the caller reports it in the same missing-clause format as a
        partially dropped one.
        """
        module = importlib.import_module("anvilkit.pi.piprompt")
        try:
            return module.body_from_xml(
                path.read_text(encoding="utf-8")
            )
        except module.PromptError:
            return None

    def test_every_source_clause_appears_in_the_body(self):
        path = TEMPLATE_ROOT / self.rel[0]
        clauses = _collect_clauses(self.rel[0])
        self.assertGreaterEqual(
            len(clauses),
            _MINIMUM_CLAUSES,
            "only %d non-empty text nodes were extracted from "
            "templates/roo_template/%s; the source has %s, so the "
            "containment checks below would be vacuous"
            % (len(clauses), self.rel[0], self.rel[1]),
        )
        body = self._body(path)
        if body is None:
            self.fail(
                "no body was produced for the %s "
                "(templates/roo_template/%s); all %d source clause(s) "
                "are absent; the first is %r"
                % (self.rel[1], self.rel[0], len(clauses), clauses[0][:60])
            )
        normalised_body = _normalise(body)
        missing = [
            clause for clause in clauses if clause not in normalised_body
        ]
        if missing:
            # self.fail (not assertFalse's message argument) so the
            # diagnostic is only built on the failure path - a
            # truthy-condition message would index missing[0] even
            # when every clause is present.
            self.fail(
                "%d source clause(s) of the %s are absent from the "
                "generated body (templates/roo_template/%s); the first "
                "missing clause is %r"
                % (len(missing), self.rel[1], self.rel[0], missing[0][:60])
            )


class ArchitectInstructionsLossless(LosslessConversionBase):
    rel = RULE_SOURCES[0]


class QnaTesterInstructionsLossless(LosslessConversionBase):
    rel = RULE_SOURCES[1]


class TddManagerInstructionsLossless(LosslessConversionBase):
    rel = RULE_SOURCES[2]


class DocsManagerGuidelinesLossless(LosslessConversionBase):
    rel = RULE_SOURCES[3]
