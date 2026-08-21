"""Tests for behaviour 2 of ``plans/kiss-agent-rules.md`` — testing
discipline in the qna-tester instructions.

The two files under test are data:

  * ``templates/roo_template/rules-qna-tester/instructions.xml`` (deployed
    by ``setup-repo``);
  * ``.roo/rules-qna-tester/instructions.xml`` (anvil's own local copy,
    gitignored — absent on a fresh clone / CI).

Each file currently holds root ``<instructions>``, a ``<workflow>`` of 6
numbered steps, a ``<best_practices>`` block of 9 ``<rule>`` elements, a
``<common_pitfalls>`` block of 3 ``<pitfall>`` elements, and a
``<reporting>`` block. Behaviour 2 is additive: five new ``<rule>``
elements and one new ``<pitfall>``.

This module follows the conventions of ``tests/test_templates_rules.py``
(behaviours 16-20 of ``plans/package-registry-context.md``): every
assertion is on the parsed XML structure plus key phrases, never on raw
bytes, so the green step has latitude in the prose. The shared loading /
parsing helpers and the ``XmlTemplateTestCase`` base are imported from
there. The **B19/B20 pattern** is reused: a shared base case carries the
assertions, with one subclass pointed at the template and one at the
local copy, which skips cleanly in ``setUp`` when the file is absent.
Whole-file equality between the template and the local copy is
deliberately NOT asserted: the local copy may carry repo-specific text.

The new guidance is about *which* tests to write. It must not contradict
the pre-existing "never weaken a test to make it pass" rule; that rule's
survival is asserted below (``test_preexisting_rules_survive``) and no
guard here would fail if the new rules merely coexist with it.
"""

import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Reused from the existing rules-XML module: the shared base case plus the
# parsing helpers. Imported after the sys.path fix above, matching the
# convention in tests/test_templates_rules.py itself.
from tests.test_templates_rules import (  # noqa: E402
    XmlTemplateTestCase,
    _all_steps,
    _element_text,
    _step_number,
)

QNA_TEMPLATE = (
    REPO_ROOT / "templates" / "roo_template" / "rules-qna-tester" / "instructions.xml"
)
LOCAL_QNA = REPO_ROOT / ".roo" / "rules-qna-tester" / "instructions.xml"

# The qna-tester instructions are parsed through a loader that escapes bare
# ampersands on a string copy before ElementTree sees the text, so an
# unescaped "&" (for example in a title like "Q&A") cannot abort the parse.
# The data files are well-formed today: the "Q&A Tester" bare-& defect the
# tolerance was written for has been fixed, and the strict well-formedness
# test below pins it, so a regression to an unescaped ampersand is caught
# even though this loader would still parse. A missing file, or a document
# malformed beyond an unescaped ampersand, still fails at load time.
_BARE_AMPERSAND = re.compile(r"&(?!(?:[a-zA-Z][a-zA-Z0-9]*|#[0-9]+|#x[0-9a-fA-F]+);)")


def _load_qna_instructions(path):
    """Parse the qna-tester instructions at *path*, returning the root
    element.

    Bare ampersands are escaped on a string copy before ElementTree sees
    the text, so an unescaped "&" (for example in a title like "Q&A") does
    not abort the parse; the file on disk is never touched. A missing file,
    or a document that is malformed beyond an unescaped ampersand, still
    fails at load time, so a genuinely corrupt document cannot slip through
    silently.
    """
    raw = Path(path).read_text(encoding="utf-8")
    escaped = _BARE_AMPERSAND.sub("&" + "amp;", raw)
    return ET.fromstring(escaped)


# Marker phrases, one per pre-existing <rule>, proving all 9 survive the
# additive change (checked case-insensitively against the combined text of
# every <rule>, so a single altered element that drops its marker fails).
ORIGINAL_RULE_MARKERS = (
    "strict tdd",
    "never weaken a test",
    "$home",
    "run in seconds",
    "returned data structures",
    "test_{function}_{scenario}_{expected}",
    "arrange, act, assert",
    "tempfile.temporarydirectory",
    "standalone_mode",
)

# Marker phrases, one per pre-existing <pitfall>, proving all 3 survive.
ORIGINAL_PITFALL_MARKERS = (
    "clirunner.isolation",
    "generator source text",
    "standalone mode",
)


# --------------------------------------------------------------------------- #
# Phrase predicates for the new content (lower-cased text in, bool out)
# --------------------------------------------------------------------------- #

def _says_do_not_test_everything(text):
    """True when a rule says NOT to test everything — a "not" / "skip"
    negation together with "everything"."""
    negation = ("not" in text) or ("skip" in text)
    return negation and ("everything" in text)


def _covers_business_logic(text):
    """True when a rule is about business logic / business rules."""
    subject = "business" in text
    kind = ("logic" in text) or ("rule" in text)
    return subject and kind


def _covers_edge_cases(text):
    """True when a rule names edge cases AND at least one of the example
    categories: boundary values, empty inputs or nulls."""
    has_edge_cases = "edge case" in text
    has_example = ("boundary" in text) or ("null" in text) or ("empty" in text)
    return has_edge_cases and has_example


def _covers_error_paths(text):
    """True when a rule names error paths."""
    return "error path" in text


def _says_test_bug_before_fix(text):
    """True when a rule says write a test for a bug BEFORE fixing it."""
    return ("bug" in text) and ("before" in text) and ("fix" in text)


def _skips_trivial_code(text):
    """True when a rule names trivial code to skip — getters/setters AND at
    least one of trivial wrappers / third-party code."""
    accessors = ("getter" in text) or ("setter" in text)
    trivial = ("trivial wrapper" in text) or ("third-party" in text)
    return accessors and trivial


def _says_tests_isolated_repeatable_self_checking(text):
    """True when a rule says tests are isolated, repeatable and
    self-checking."""
    return (
        ("isolated" in text)
        and ("repeatable" in text)
        and ("self-checking" in text)
    )


def _names_over_testing_trivial_code(text):
    """True when a pitfall is about over-testing trivial code — an
    over-testing noun together with trivial / data-holder / configuration /
    wrapper subjects."""
    over = ("over-test" in text) or ("over testing" in text)
    trivial = (
        ("trivial" in text)
        or ("data holder" in text)
        or ("configuration" in text)
        or ("wrapper" in text)
    )
    return over and trivial


# --------------------------------------------------------------------------- #
# Shared assertions, pointed at either the template or the local copy
# --------------------------------------------------------------------------- #

class QnaTestingDisciplineBase(XmlTemplateTestCase):
    """Shared assertions for behaviour 2 of ``plans/kiss-agent-rules.md``.

    One subclass points at the template, one at the anvil repo's local
    ``.roo`` copy, so the local copy cannot drift from the template on the
    new guidance. Only the parsed structure and key phrases are locked,
    never whole-file equality.

    The class itself is collected by ``unittest`` because it is a
    ``TestCase`` subclass; ``setUp`` skips it, so only the two concrete
    subclasses run the assertions (precedent:
    ``TddManagerRequirementBase`` in tests/test_templates_rules.py).

    ``setUp`` parses through :func:`_load_qna_instructions` rather than the
    shared ``_load_xml``: the loader's ampersand tolerance (a leftover from
    the now-fixed "Q&A Tester" bare-& defect) can never abort the suite on
    that token. Everything else about loading is inherited (a missing file
    still fails, never skips, for the template).
    """

    def setUp(self):
        if self.template_path is None:
            self.skipTest("abstract base class; run a concrete subclass")
        self.root = _load_qna_instructions(self.template_path)

    # -- structure guards (pass now, must keep passing after the green step) -- #

    def test_document_parses_with_instructions_root(self):
        # Well-formed XML is proven by having parsed in setUp; the root tag
        # is asserted on the parsed element, never by substring.
        self.assertEqual(self.root.tag, "instructions")

    def test_document_is_strictly_well_formed_xml(self):
        # The document must stay well-formed XML *without* any loader
        # tolerance: a strict ElementTree.parse on the raw file must
        # succeed, so setUp's ampersand-tolerant loader can never mask a
        # malformed file. Parse the file itself, capture the ParseError
        # rather than letting it raise, and assert it is None.
        parse_error = None
        try:
            ET.parse(str(self.template_path))
        except ET.ParseError as exc:
            parse_error = exc
        self.assertIsNone(
            parse_error,
            "%s is not well-formed XML (strict ElementTree.parse failed): %s"
            % (self.template_path, parse_error),
        )

    def test_workflow_keeps_six_steps_with_contiguous_numbers(self):
        # The workflow is untouched by behaviour 2: exactly 6 steps, with a
        # contiguous 1..N sequence of `number` attributes and no duplicates.
        steps = _all_steps(self.root)
        self.assertEqual(
            len(steps),
            6,
            "expected the qna-tester workflow to keep its 6 steps, found %d; "
            "numbers: %r" % (len(steps), [_step_number(s) for s in steps]),
        )
        raw = [_step_number(step) for step in steps]
        self.assertTrue(
            all(n is not None for n in raw),
            "every <step> must carry a number attribute; got %r" % (raw,),
        )
        numbers = sorted(int(n) for n in raw)
        self.assertEqual(
            numbers,
            list(range(1, len(steps) + 1)),
            "step numbers are not a contiguous 1..%d sequence: %r"
            % (len(steps), numbers),
        )

    def test_preexisting_rules_survive(self):
        # Behaviour 2 is additive: all 9 pre-existing <rule> elements
        # survive, each recognised by its marker phrase.
        rules = self.root.findall("best_practices/rule")
        self.assertGreaterEqual(
            len(rules),
            9,
            "expected the 9 pre-existing <rule> elements to survive; found %d"
            % len(rules),
        )
        all_text = " ".join(_element_text(r) for r in rules)
        for marker in ORIGINAL_RULE_MARKERS:
            self.assertIn(
                marker,
                all_text,
                "an existing <rule> is missing or was altered (expected "
                "marker %r). Rule texts: %r" % (marker, all_text),
            )

    def test_preexisting_pitfalls_survive(self):
        # All 3 pre-existing <pitfall> elements survive.
        pitfalls = self.root.findall("common_pitfalls/pitfall")
        self.assertGreaterEqual(
            len(pitfalls),
            3,
            "expected the 3 pre-existing <pitfall> elements to survive; "
            "found %d" % len(pitfalls),
        )
        all_text = " ".join(_element_text(p) for p in pitfalls)
        for marker in ORIGINAL_PITFALL_MARKERS:
            self.assertIn(
                marker,
                all_text,
                "an existing <pitfall> is missing or was altered (expected "
                "marker %r). Pitfall texts: %r" % (marker, all_text),
            )

    def test_reporting_block_untouched(self):
        # The <reporting> block — its leaf <rule>, <on_failure> and
        # <on_success> — is untouched by behaviour 2.
        reporting = self.root.find("reporting")
        self.assertIsNotNone(reporting, "<reporting> block is missing")
        leaf = reporting.find("rule")
        self.assertIsNotNone(leaf, "<reporting> has no leaf <rule>")
        self.assertIn(
            "leaf in the delegation graph",
            _element_text(leaf),
            "the <reporting> leaf <rule> was altered: %r" % _element_text(leaf),
        )
        on_failure = reporting.find("on_failure")
        self.assertIsNotNone(on_failure, "<reporting> has no <on_failure>")
        self.assertIn(
            "verbatim",
            _element_text(on_failure),
            "<reporting><on_failure> was altered: %r" % _element_text(on_failure),
        )
        on_success = reporting.find("on_success")
        self.assertIsNotNone(on_success, "<reporting> has no <on_success>")
        self.assertIn(
            "new capabilities confirmed",
            _element_text(on_success),
            "<reporting><on_success> was altered: %r" % _element_text(on_success),
        )

    # -- behaviour 2: the five new <rule> elements in <best_practices> -- #

    def _best_practice_rules(self):
        return self.root.findall("best_practices/rule")

    def _rules_matching(self, predicate):
        return [r for r in self._best_practice_rules() if predicate(_element_text(r))]

    def _rule_texts(self):
        return [_element_text(r) for r in self._best_practice_rules()]

    def test_new_rule_says_do_not_test_everything(self):
        # Point 1: do not test everything — a "not" / "skip" negation
        # together with "everything".
        matching = self._rules_matching(_says_do_not_test_everything)
        self.assertTrue(
            matching,
            "no <rule> in <best_practices> says not to test everything "
            "(looked for 'not'/'skip' + 'everything'). Rule texts: %r"
            % self._rule_texts(),
        )

    def test_new_rule_covers_business_logic(self):
        # Point 2a: cover business logic / business rules.
        matching = self._rules_matching(_covers_business_logic)
        self.assertTrue(
            matching,
            "no <rule> in <best_practices> covers business logic / business "
            "rules. Rule texts: %r" % self._rule_texts(),
        )

    def test_new_rule_covers_edge_cases(self):
        # Point 2b: edge cases, named with at least one example category
        # (boundary values, empty inputs, nulls).
        matching = self._rules_matching(_covers_edge_cases)
        self.assertTrue(
            matching,
            "no <rule> in <best_practices> covers edge cases (looked for "
            "'edge case' + 'boundary'/'null'/'empty'). Rule texts: %r"
            % self._rule_texts(),
        )

    def test_new_rule_covers_error_paths(self):
        # Point 2c: error paths — how the code handles bad data and
        # failures.
        matching = self._rules_matching(_covers_error_paths)
        self.assertTrue(
            matching,
            "no <rule> in <best_practices> covers error paths (looked for "
            "'error path'). Rule texts: %r" % self._rule_texts(),
        )

    def test_new_rule_writes_test_for_bug_before_fix(self):
        # Point 3: write a test for a bug BEFORE fixing it.
        matching = self._rules_matching(_says_test_bug_before_fix)
        self.assertTrue(
            matching,
            "no <rule> in <best_practices> says to write a test for a bug "
            "before fixing it (looked for 'bug' + 'before' + 'fix'). Rule "
            "texts: %r" % self._rule_texts(),
        )

    def test_new_rule_skips_trivial_code(self):
        # Point 4: skip getters/setters AND trivial wrappers / third-party
        # code.
        matching = self._rules_matching(_skips_trivial_code)
        self.assertTrue(
            matching,
            "no <rule> in <best_practices> says to skip getters/setters and "
            "trivial wrappers / third-party code (looked for 'getter'/'setter' "
            "+ 'trivial wrapper'/'third-party'). Rule texts: %r"
            % self._rule_texts(),
        )

    def test_new_rule_says_tests_are_isolated_repeatable_self_checking(self):
        # Point 5: tests are isolated, repeatable and self-checking.
        matching = self._rules_matching(
            _says_tests_isolated_repeatable_self_checking
        )
        self.assertTrue(
            matching,
            "no <rule> in <best_practices> says tests are isolated, "
            "repeatable and self-checking (looked for 'isolated' + "
            "'repeatable' + 'self-checking'). Rule texts: %r"
            % self._rule_texts(),
        )

    # -- behaviour 2: the new <pitfall> in <common_pitfalls> -- #

    def test_new_pitfall_names_over_testing_trivial_code(self):
        # A <pitfall> naming over-testing trivial code — simple data
        # holders, framework configuration or thin wrappers.
        pitfalls = self.root.findall("common_pitfalls/pitfall")
        self.assertTrue(pitfalls, "<common_pitfalls> has no <pitfall> elements")
        matching = [p for p in pitfalls if _names_over_testing_trivial_code(_element_text(p))]
        self.assertTrue(
            matching,
            "no <pitfall> in <common_pitfalls> is about over-testing trivial "
            "code (looked for 'over-test'/'over testing' + 'trivial'/'data "
            "holder'/'configuration'/'wrapper'). Pitfall texts: %r"
            % [_element_text(p) for p in pitfalls],
        )


class QnaTemplateTests(QnaTestingDisciplineBase):
    """Behaviour 2: the qna-tester TEMPLATE instructions carry the testing
    discipline."""

    template_path = QNA_TEMPLATE


class QnaLocalTests(QnaTestingDisciplineBase):
    """Behaviour 2: the anvil repo's OWN qna-tester rules carry the same
    testing discipline.

    The same assertions run against the local copy, so it cannot drift from
    the template on this point. Only the new rules are locked, never
    whole-file equality.

    ``.roo`` is gitignored, so the local copy is absent on a fresh clone
    (and on CI). ``setUp`` skips every test cleanly in that case (precedent:
    ``B20LocalTddManagerTests``); when the file is provisioned, the full
    assertion set runs exactly as written in the base class.
    """

    template_path = LOCAL_QNA

    def setUp(self):
        if not self.template_path.exists():
            self.skipTest(
                "anvil repo local .roo copy not provisioned; nothing to check"
            )
        super().setUp()


if __name__ == "__main__":
    unittest.main()
