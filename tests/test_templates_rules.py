"""Tests for the roo_template rules XML files (plans/package-registry-context.md, Group E).

This module is the shared home for the template-instruction tests in Group E of
``plans/package-registry-context.md``:

  * behaviour 16 — the architect template gains a "check for an existing
    solution" step, plus its ``<practice>`` / ``<pitfall>`` /
    ``<quality_checklist>`` companions (implemented below);
  * behaviour 17 — the blocking user-validation gate;
  * behaviour 18 — deployment of the architect instructions to a target;
  * behaviour 19 — the tdd-manager template requires the validated plan;
  * behaviour 20 — the anvil repo's own tdd-manager rules carry it too.

Only behaviour 16 is written in this red step. The file-loading helpers and the
``XmlTemplateTestCase`` base below are deliberately shared so 17-20 slot in
without restructuring: 17 reuses ``ArchitectTemplateTestCase``; 19 and 20 each
need a subclass pointed at ``TDD_MANAGER_TEMPLATE`` and ``LOCAL_TDD_MANAGER``
respectively; 18 provisions a target and reads the deployed copy from a temp
dir.

Every assertion is on the parsed XML structure and on key phrases, never on raw
bytes, so the green step has latitude in the prose. The template files are data
and are asserted on directly (precedent: ``tests/test_mcp_template.py`` and the
plan's note that template files "may be asserted on directly").
"""

import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The rules XML files under test. B16 targets the architect template; the other
# two are loaded for the later B19/B20 cycles.
ARCHITECT_TEMPLATE = (
    REPO_ROOT / "templates" / "roo_template" / "rules-architect" / "instructions.xml"
)
TDD_MANAGER_TEMPLATE = (
    REPO_ROOT / "templates" / "roo_template" / "rules-tdd-manager" / "instructions.xml"
)
LOCAL_TDD_MANAGER = REPO_ROOT / ".roo" / "rules-tdd-manager" / "instructions.xml"

# The six step titles present in the architect template before behaviour 16.
# Behaviour 16 is additive: all of these must survive with their content.
ORIGINAL_STEP_TITLES = [
    "Understand the requirement",
    "Assess interface knowledge",
    "Handle unknown interfaces",
    "Fetch comprehensively",
    "Write the plan",
    "Review the plan",
]

# A step title names "searching for an existing package/solution" when it carries
# a searching verb and an existing/solution noun. Deliberately loose so the green
# step has latitude in the exact wording.
_SEARCH_TITLE_RE = re.compile(
    r"\b(search|check|look|find|investigate|consider|scan|reuse|use)\b"
    r".*"
    r"\b(existing|prior[- ]?art|already|solution|package|wheel|maintained|reuse)"
    r"\b",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# Shared parsing helpers
# --------------------------------------------------------------------------- #

def _load_xml(path):
    """Parse *path* with ElementTree and return the root element.

    Raises (via :func:`xml.etree.ElementTree.parse`) if the file is missing or
    not well-formed XML, so a corrupt document is caught at load time rather
    than silently passing.
    """
    return ET.parse(str(path)).getroot()


def _element_text(element):
    """Return all of *element*'s text (element + descendants) as one
    lower-cased, whitespace-collapsed string."""
    text = " ".join(element.itertext())
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower()


def _all_steps(root):
    """Return every ``<step>`` element under the ``<workflow>``."""
    return root.findall(".//workflow/step")


def _step_title(step):
    title = step.find("title")
    if title is None:
        return ""
    return (title.text or "").strip()


def _step_number(step):
    return step.get("number")


def _find_steps_by_phrase(root, phrase):
    """Return steps whose full text contains *phrase* (case-insensitive)."""
    needle = phrase.lower()
    return [step for step in _all_steps(root) if needle in _element_text(step)]


def _step_by_title(root, title):
    """Return the step whose ``<title>`` equals *title*, or ``None``."""
    wanted = title.lower()
    for step in _all_steps(root):
        if _step_title(step).lower() == wanted:
            return step
    return None


def _package_registry_steps(root):
    """Return steps whose text names the ``package-registry`` MCP server."""
    return _find_steps_by_phrase(root, "package-registry")


def _title_names_search_for_existing(title):
    return _SEARCH_TITLE_RE.search(title) is not None


def _requires_check_before_solution(text):
    """True when *text* (lower-cased) says the check must happen before a coded
    solution is defined. Accepts "before"/"prior"/"first" for ordering and
    "solution"/"code" for the thing being defined."""
    ordering = ("before" in text) or ("prior" in text) or ("first" in text)
    target = ("solution" in text) or ("code" in text)
    return ordering and target


def _mentions_existing_package(text):
    """True when a practice's text is about reusing an existing/maintained
    package rather than writing one."""
    return ("package" in text) and (
        ("existing" in text)
        or ("maintained" in text)
        or ("solved" in text)
        or ("reuse" in text)
        or ("already" in text)
    )


def _is_bespoke_implementation_mistake(text):
    """True when a ``<mistake>``'s text is writing a bespoke/own implementation
    of an already-solved problem."""
    bespoke = ("bespoke" in text) or ("own" in text)
    solved = (
        ("solved" in text)
        or ("existing" in text)
        or ("already" in text)
        or ("maintained" in text)
        or ("package" in text)
    )
    return bespoke and solved


def _mentions_package_check(text):
    """True when a quality-checklist item mentions the existing-solution /
    package-registry check."""
    subject = ("package" in text) or ("registry" in text)
    action = (
        ("existing" in text)
        or ("maintained" in text)
        or ("solution" in text)
        or ("check" in text)
        or ("search" in text)
    )
    return subject and action


# --------------------------------------------------------------------------- #
# Base test case: loads and parses one rules XML file
# --------------------------------------------------------------------------- #

class XmlTemplateTestCase(unittest.TestCase):
    """Shared loading/parsing for the rules XML template files.

    Subclasses set ``template_path``; ``setUp`` parses it once so every test
    asserts on the structure, and a malformed document surfaces at load time.
    """

    template_path = None

    def setUp(self):
        self.assertIsNotNone(
            self.template_path,
            "subclass must set template_path to a rules XML file",
        )
        self.root = _load_xml(self.template_path)


class ArchitectTemplateTestCase(XmlTemplateTestCase):
    """Behaviour 16: the architect template gains the existing-solution step."""

    template_path = ARCHITECT_TEMPLATE

    # -- structure guards (pass now, must keep passing after the green step) -- #

    def test_root_tag_is_instructions_and_document_parses(self):
        # Edge: the document stays well-formed XML whose root is <instructions>.
        # Well-formedness is proven by having parsed in setUp; the root tag is
        # asserted on the parsed element, never by substring.
        self.assertEqual(self.root.tag, "instructions")

    def test_step_numbers_are_contiguous_1_to_n_with_no_duplicates(self):
        # The step `number` attributes form a contiguous 1..N sequence with no
        # duplicate or missing number. Passes now (1..6) and must still pass
        # once behaviour 16 inserts and renumbers a step (1..N+1).
        raw = [_step_number(step) for step in _all_steps(self.root)]
        self.assertTrue(
            all(n is not None for n in raw),
            "every <step> must carry a number attribute; got %r" % (raw,),
        )
        numbers = [int(n) for n in raw]
        self.assertEqual(
            sorted(numbers),
            list(range(1, len(numbers) + 1)),
            "step numbers are not a contiguous 1..N sequence: %r" % (sorted(numbers),),
        )
        self.assertEqual(
            len(set(numbers)),
            len(numbers),
            "duplicate step numbers present: %r" % (sorted(numbers),),
        )

    def test_existing_oxylabs_steps_and_content_still_present(self):
        # Edge: the new step is additive — the pre-existing oxylabs steps and
        # their content survive.
        titles = [_step_title(step) for step in _all_steps(self.root)]
        for original in ORIGINAL_STEP_TITLES:
            self.assertIn(
                original,
                titles,
                "original step %r is missing from the workflow; titles: %r"
                % (original, titles),
            )
        oxylabs_steps = _find_steps_by_phrase(self.root, "oxylabs")
        self.assertGreaterEqual(
            len(oxylabs_steps),
            2,
            "expected the pre-existing oxylabs steps to still be present, but only "
            "%d step(s) mention oxylabs" % len(oxylabs_steps),
        )

    # -- behaviour 16: the new "check for an existing solution" step -- #

    def test_package_registry_step_exists(self):
        # A <step> whose text names the package-registry MCP server must exist.
        steps = _package_registry_steps(self.root)
        self.assertTrue(
            steps,
            "no <step> in <workflow> mentions the 'package-registry' MCP server; "
            "step titles: %r"
            % [_step_title(s) for s in _all_steps(self.root)],
        )

    def test_package_registry_step_title_names_searching_for_existing_package(self):
        # The step's <title> names searching for an existing package/solution.
        steps = _package_registry_steps(self.root)
        self.assertTrue(
            steps,
            "no <step> mentions 'package-registry'; cannot check its title",
        )
        matching = [
            s for s in steps if _title_names_search_for_existing(_step_title(s))
        ]
        self.assertTrue(
            matching,
            "a package-registry step exists but none has a <title> that names a "
            "search for an existing package/solution. Titles seen: %r"
            % [_step_title(s) for s in steps],
        )

    def test_package_registry_step_names_the_package_registry_mcp_server(self):
        # The step's text names the package-registry MCP server.
        steps = _package_registry_steps(self.root)
        self.assertTrue(
            steps,
            "no <step> mentions 'package-registry'; it must name the MCP server",
        )
        naming = [
            s
            for s in steps
            if ("mcp" in _element_text(s)) or ("server" in _element_text(s))
        ]
        self.assertTrue(
            naming,
            "a package-registry step exists but none names it as an MCP server "
            "(expected 'package-registry' together with 'mcp' or 'server')",
        )

    def test_package_registry_step_requires_check_before_coded_solution(self):
        # The step requires the check to happen before a coded solution is
        # defined.
        steps = _package_registry_steps(self.root)
        self.assertTrue(
            steps,
            "no <step> mentions 'package-registry'; cannot check ordering",
        )
        matching = [
            s
            for s in steps
            if _requires_check_before_solution(_element_text(s))
        ]
        self.assertTrue(
            matching,
            "no package-registry step requires the check to happen before a coded "
            "solution is defined (looked for 'before'/'prior'/'first' + "
            "'solution'/'code')",
        )

    def test_package_registry_step_numbered_after_understand_before_write_plan(self):
        # The step's number places it after "Understand the requirement" and
        # before "Write the plan".
        steps = _package_registry_steps(self.root)
        self.assertTrue(
            steps,
            "no <step> mentions 'package-registry'; cannot check its position",
        )
        understand = _step_by_title(self.root, "Understand the requirement")
        write_plan = _step_by_title(self.root, "Write the plan")
        self.assertIsNotNone(
            understand, "'Understand the requirement' step is missing"
        )
        self.assertIsNotNone(write_plan, "'Write the plan' step is missing")
        lower = int(understand.get("number"))
        upper = int(write_plan.get("number"))
        placed = [
            s
            for s in steps
            if int(s.get("number")) is not None
            and lower < int(s.get("number")) < upper
        ]
        self.assertTrue(
            placed,
            "no package-registry step is numbered between 'Understand the "
            "requirement' (%d) and 'Write the plan' (%d); package-registry step "
            "numbers: %r"
            % (lower, upper, [s.get("number") for s in steps]),
        )

    # -- behaviour 16: the matching best-practice / pitfall / checklist -- #

    def test_best_practices_has_existing_package_practice(self):
        # A <practice> whose text is about reusing an existing / well-maintained
        # package.
        practices = self.root.findall(".//best_practices/practice")
        self.assertTrue(practices, "<best_practices> has no <practice> elements")
        matching = [
            p for p in practices if _mentions_existing_package(_element_text(p))
        ]
        self.assertTrue(
            matching,
            "no <practice> in <best_practices> is about reusing an existing / "
            "well-maintained package",
        )

    def test_common_pitfalls_has_bespoke_implementation_pitfall(self):
        # A <pitfall> whose <mistake> is writing a bespoke implementation of a
        # solved problem.
        pitfalls = self.root.findall(".//common_pitfalls/pitfall")
        self.assertTrue(pitfalls, "<common_pitfalls> has no <pitfall> elements")

        def _mistake_text(pitfall):
            mistake = pitfall.find("mistake")
            return _element_text(mistake) if mistake is not None else ""

        matching = [p for p in pitfalls if _is_bespoke_implementation_mistake(_mistake_text(p))]
        self.assertTrue(
            matching,
            "no <pitfall> has a <mistake> about writing a bespoke / own "
            "implementation of an already-solved problem",
        )

    def test_quality_checklist_has_package_check_item(self):
        # A <quality_checklist> item that mentions the package check.
        # Items live inside <category> elements, so match them at any depth
        # under <quality_checklist>.
        items = self.root.findall(".//quality_checklist//item")
        self.assertTrue(items, "<quality_checklist> has no <item> elements")
        matching = [i for i in items if _mentions_package_check(_element_text(i))]
        self.assertTrue(
            matching,
            "no <quality_checklist> <item> mentions the existing-solution / "
            "package-registry check",
        )


if __name__ == "__main__":
    unittest.main()
