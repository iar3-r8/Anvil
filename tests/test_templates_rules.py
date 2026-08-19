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

Behaviours 16 and 17 are written in this module. The file-loading helpers and
the ``XmlTemplateTestCase`` base are deliberately shared so 18-20 slot in
without restructuring: 19 and 20 each need a subclass pointed at
``TDD_MANAGER_TEMPLATE`` and ``LOCAL_TDD_MANAGER`` respectively; 18 provisions
a target and reads the deployed copy from a temp dir.

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


# --------------------------------------------------------------------------- #
# Behaviour 17: the blocking user-validation gate
# --------------------------------------------------------------------------- #

def _mentions_user_validation(text):
    """True when *text* (lower-cased) asks the architect to validate or confirm
    something with the user."""
    action = ("validat" in text) or ("confirm" in text)
    return action and ("user" in text)


def _mentions_planning_session(text):
    """True when *text* places the gate during the planning session."""
    return ("planning" in text) and ("session" in text or "during" in text)


def _covers_newly_defined_behaviours(text):
    """True when *text* is about validating newly defined behaviours. "new"
    also matches "newly"."""
    behaviour = ("behaviour" in text) or ("behavior" in text)
    return behaviour and ("new" in text)


def _covers_nonstandard_packages(text):
    """True when *text* covers a proposed use of a non-standard package, using
    the plan's phrasing: "non-standard" or "standard dependencies"."""
    return ("package" in text) and (
        ("non-standard" in text) or ("standard dependencies" in text)
    )


def _states_it_is_blocking(text):
    """True when *text* states the gate is blocking — work must not proceed
    without the user's confirmation."""
    return (
        ("blocking" in text)
        or ("must not proceed" in text)
        or ("do not proceed" in text)
        or ("without confirmation" in text)
    )


def _before_plan_written(text):
    """True when *text* places the gate before the plan is written."""
    ordering = ("before" in text) or ("prior to" in text)
    target = ("plan" in text) and ("writ" in text)
    return ordering and target


def _validation_gate_steps(root):
    """Return steps whose text asks for validation/confirmation with the
    user."""
    return [
        step
        for step in _all_steps(root)
        if _mentions_user_validation(_element_text(step))
    ]


def _is_gate_practice(text):
    """True when a <practice>'s text is about validating with the user before
    the plan is written."""
    return _mentions_user_validation(text) and (
        ("behaviour" in text)
        or ("behavior" in text)
        or ("package" in text)
        or ("plan" in text)
    )


def _is_proceeding_without_confirmation(text):
    """True when a <mistake>'s text is proceeding without the user's
    confirmation / validation."""
    return (
        ("without" in text)
        and (("confirm" in text) or ("validat" in text))
        and (("proceed" in text) or ("continue" in text) or ("writ" in text))
    )


def _is_gate_checklist_item(text):
    """True when a quality-checklist item mentions validating with the user."""
    return _mentions_user_validation(text) and (
        ("behaviour" in text)
        or ("behavior" in text)
        or ("package" in text)
    )


class B17ValidationGateTests(ArchitectTemplateTestCase):
    """Behaviour 17: the architect template gains the blocking user-validation
    gate.

    Subclassing ``ArchitectTemplateTestCase`` re-runs its structure guards
    (well-formed XML with root ``instructions``, contiguous step numbering, the
    original steps still present) and its behaviour-16 assertions, so the
    green-step edit that adds the gate is verified again against the edges
    shared with behaviour 16.
    """

    def _gate_steps_or_fail(self, missing_hint):
        """Return the user-validation gate steps, failing with a diagnostic
        listing every step title when none exists."""
        steps = _validation_gate_steps(self.root)
        self.assertTrue(
            steps,
            "no <step> in <workflow> asks for validation/confirmation with the "
            "user; %s. Step titles: %r"
            % (missing_hint, [_step_title(s) for s in _all_steps(self.root)]),
        )
        return steps

    # -- the gate step: each requirement of plan §3, item 17 -- #

    def test_validation_gate_step_exists(self):
        # A <step> requiring the architect to validate with the user must exist.
        self._gate_steps_or_fail("expected the blocking user-validation gate step")

    def test_single_step_satisfies_every_gate_requirement(self):
        # One step must state the whole gate: user validation, during the
        # planning session, covering newly defined behaviours AND non-standard
        # packages, blocking, before the plan is written.
        def covers_all(step):
            text = _element_text(step)
            return (
                _mentions_user_validation(text)
                and _mentions_planning_session(text)
                and _covers_newly_defined_behaviours(text)
                and _covers_nonstandard_packages(text)
                and _states_it_is_blocking(text)
                and _before_plan_written(text)
            )

        matching = [s for s in _validation_gate_steps(self.root) if covers_all(s)]
        self.assertTrue(
            matching,
            "no single <step> states the whole gate (user validation + planning "
            "session + newly defined behaviours + non-standard packages + "
            "blocking + before the plan is written). Candidate gate step titles: "
            "%r; all step titles: %r"
            % (
                [_step_title(s) for s in _validation_gate_steps(self.root)],
                [_step_title(s) for s in _all_steps(self.root)],
            ),
        )

    def test_gate_step_happens_during_planning_session(self):
        # (ii) The gate happens during the planning session.
        steps = self._gate_steps_or_fail("cannot check planning-session placement")
        matching = [s for s in steps if _mentions_planning_session(_element_text(s))]
        self.assertTrue(
            matching,
            "no user-validation step places the gate during the planning session "
            "(looked for 'planning' together with 'session' or 'during')",
        )

    def test_gate_step_covers_newly_defined_behaviours(self):
        # (a) Every newly defined behaviour must be validated with the user.
        steps = self._gate_steps_or_fail("cannot check behaviour coverage")
        matching = [
            s for s in steps if _covers_newly_defined_behaviours(_element_text(s))
        ]
        self.assertTrue(
            matching,
            "no user-validation step covers newly defined behaviours (looked for "
            "'behaviour'/'behavior' together with 'new'/'newly')",
        )

    def test_gate_step_covers_nonstandard_packages(self):
        # (b) Any proposed use of a non-standard package must be validated, with
        # "non-standard" phrased per the plan: "non-standard" or "standard
        # dependencies".
        steps = self._gate_steps_or_fail("cannot check non-standard package coverage")
        matching = [
            s for s in steps if _covers_nonstandard_packages(_element_text(s))
        ]
        self.assertTrue(
            matching,
            "no user-validation step covers non-standard packages (looked for "
            "'package' together with 'non-standard' or 'standard dependencies')",
        )

    def test_gate_step_states_it_is_blocking(self):
        # The text states the gate is blocking: no proceeding without the
        # user's confirmation.
        steps = self._gate_steps_or_fail("cannot check blocking wording")
        matching = [s for s in steps if _states_it_is_blocking(_element_text(s))]
        self.assertTrue(
            matching,
            "no user-validation step states it is blocking (looked for "
            "'blocking', 'must not proceed', 'do not proceed' or 'without "
            "confirmation')",
        )

    def test_gate_step_comes_before_the_plan_is_written(self):
        # (v) The validation happens before the plan is written.
        steps = self._gate_steps_or_fail("cannot check before-writing ordering")
        matching = [s for s in steps if _before_plan_written(_element_text(s))]
        self.assertTrue(
            matching,
            "no user-validation step places the gate before the plan is written "
            "(looked for 'before'/'prior to' + 'plan' + 'write'/'written')",
        )

    # -- the matching best-practice / pitfall / checklist -- #

    def test_best_practices_has_high_priority_user_validation_practice(self):
        # A <practice priority="high"> whose text is about validating with the
        # user before the plan is written.
        practices = self.root.findall(".//best_practices/practice")
        self.assertTrue(practices, "<best_practices> has no <practice> elements")
        matching = [
            p
            for p in practices
            if p.get("priority") == "high" and _is_gate_practice(_element_text(p))
        ]
        self.assertTrue(
            matching,
            "no <practice priority='high'> in <best_practices> is about validating "
            "new behaviours / non-standard packages with the user; practice "
            "priorities: %r" % [p.get("priority") for p in practices],
        )

    def test_common_pitfalls_has_proceeding_without_confirmation_pitfall(self):
        # A <pitfall> whose <mistake> is proceeding without the user's
        # confirmation.
        pitfalls = self.root.findall(".//common_pitfalls/pitfall")
        self.assertTrue(pitfalls, "<common_pitfalls> has no <pitfall> elements")

        def _mistake_text(pitfall):
            mistake = pitfall.find("mistake")
            return _element_text(mistake) if mistake is not None else ""

        matching = [
            p
            for p in pitfalls
            if _is_proceeding_without_confirmation(_mistake_text(p))
        ]
        self.assertTrue(
            matching,
            "no <pitfall> has a <mistake> about proceeding without the user's "
            "confirmation / validation (looked for 'without' + 'confirm'/'validat' "
            "+ 'proceed'/'continue'/'write')",
        )

    def test_quality_checklist_planning_category_has_user_validation_item(self):
        # A <quality_checklist> <item> under the planning category that mentions
        # validating with the user.
        categories = self.root.findall(".//quality_checklist/category")
        self.assertTrue(
            categories, "<quality_checklist> has no <category> elements"
        )
        planning_cats = [
            c for c in categories if "plan" in (c.get("name") or "").lower()
        ]
        self.assertTrue(
            planning_cats,
            "<quality_checklist> has no category whose name mentions planning; "
            "category names: %r" % [c.get("name") for c in categories],
        )
        matching = []
        for category in planning_cats:
            for item in category.findall("item"):
                if _is_gate_checklist_item(_element_text(item)):
                    matching.append(item)
        self.assertTrue(
            matching,
            "no <item> in the planning category (names: %r) mentions validating "
            "with the user" % [c.get("name") for c in planning_cats],
        )


if __name__ == "__main__":
    unittest.main()
