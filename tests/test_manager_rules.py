"""Tests for behaviour 3 of ``plans/kiss-agent-rules.md`` — the task-splitting
duty in the tdd-manager instructions.

The two files under test are data:

  * ``templates/roo_template/rules-tdd-manager/instructions.xml`` (deployed
    by ``setup-repo``);
  * ``.roo/rules-tdd-manager/instructions.xml`` (anvil's own local copy,
    gitignored — absent on a fresh clone / CI).

Each file currently holds root ``<instructions>``, a ``<workflow>`` of 10
numbered steps, a ``<delegation_contract>`` carrying
``<to_architect><payload>`` and ``<to_architect><required_report>``, plus
``<commit_convention>``, ``<loop_control>``, ``<best_practices>``,
``<common_pitfalls>`` and a ``<quality_checklist>`` of 4 categories.
Behaviour 3 is additive: one ``<practice priority="high">``, one
``<to_architect><payload><item>``, one ``<pitfall>`` and one
``<quality_checklist>`` ``<item>`` under the ``before_shipping`` category.

This module follows the conventions of ``tests/test_templates_rules.py``
(behaviours 16-20 of ``plans/package-registry-context.md``) and of
``tests/test_qna_rules.py``: every assertion is on the parsed XML structure
plus key phrases, never on raw bytes, so the green step has latitude in the
prose. The shared loading / parsing helpers and the ``XmlTemplateTestCase``
base are imported from ``tests/test_templates_rules.py``. The B19/B20
pattern is reused: a shared base case carries the assertions, with one
subclass pointed at the template and one at the local copy, which skips
cleanly in ``setUp`` when the file is absent.

RED expectation (this commit): the four new-content assertions fail on
assertion, for the right reason — the new ``<practice>``, ``<item>``,
``<pitfall>`` and checklist ``<item>`` do not exist yet. The structure
guards (10 contiguous steps, ``<instructions>`` root, qualitative-only
wording) pass now and must keep passing after the green step.

The qualitative-only guard scans only the added elements (identified by the
same phrase predicates the new-content tests use). Both files were verified
on 2026-08-20 to contain no digits-plus-"line(s)" phrase in any pre-existing
element, so scoping the guard to the added elements keeps it precise without
excluding any pre-existing text that could trip it.
"""

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Reused from the existing rules-XML module: the shared base case plus the
# parsing helpers. Imported after the sys.path fix above, matching the
# convention in tests/test_qna_rules.py.
from tests.test_templates_rules import (  # noqa: E402
    TDD_MANAGER_TEMPLATE,
    LOCAL_TDD_MANAGER,
    XmlTemplateTestCase,
    _all_steps,
    _architect_payload_items,
    _element_text,
    _step_number,
)

# A numeric line-count threshold, e.g. "500 lines", "1000lines", "300-line".
# Behaviour 3 must stay qualitative (plan §1, "No numeric pull-request size
# threshold"), so none of the newly added elements may carry such a phrase.
_DIGIT_LINE_THRESHOLD = re.compile(
    r"\b\d[\d,]*(?:\.\d+)?\s*[-\s]?lines?\b", re.IGNORECASE
)


# --------------------------------------------------------------------------- #
# Phrase predicates for the four added elements (lower-cased input)
# --------------------------------------------------------------------------- #

def _says_pull_request_must_stay_reviewable(text):
    """True when a ``<practice>``'s text says a pull request must stay
    reviewable / easy to understand, and that a task growing beyond that is
    split into smaller tasks."""
    reviewable = ("review" in text)  # covers "reviewable" as well
    split_small = ("split" in text) or ("small" in text)
    return reviewable and split_small


def _requires_plan_split_into_reviewable_behaviours(text):
    """True when a ``<to_architect><payload><item>``'s text requires the plan
    itself to be split into small, reviewable behaviours."""
    subject = ("plan" in text) or ("behaviour" in text) or ("behavior" in text)
    size = ("small" in text) or ("split" in text) or ("reviewable" in text)
    return subject and size


def _is_oversized_pull_request_mistake(text):
    """True when a ``<mistake>``'s text is letting a branch grow into a pull
    request too large to review."""
    size = ("large" in text) or ("big" in text) or ("huge" in text) or ("grow" in text)
    pull_request = ("pull request" in text) or ("review" in text)
    return size and pull_request


def _instead_says_split_the_task(text):
    """True when a pitfall's ``<instead>`` remedy is splitting the task."""
    return ("split" in text) and ("task" in text)


def _checks_reviewable_pull_request_size(text):
    """True when a ``<quality_checklist>`` ``<item>`` checks the pull request
    is a reviewable size."""
    size = ("reviewable" in text) or ("size" in text)
    pull_request = ("pull request" in text) or ("change" in text)
    return size and pull_request


# --------------------------------------------------------------------------- #
# Shared base case, run against the template and the local copy
# --------------------------------------------------------------------------- #

class TaskSplittingDutyTests(XmlTemplateTestCase):
    """Shared assertions for behaviour 3 (plan §3), pointed at either the
    tdd-manager template or the anvil repo's local copy.

    Both files carry the same delegation contract and workflow, so the
    added content is asserted structurally on both.

    The class itself is collected by ``unittest`` because its name matches
    the default ``Test`` suffix; ``setUp`` skips it, so only the two
    concrete subclasses run the assertions.
    """

    template_path = None

    def setUp(self):
        if self.template_path is None:
            self.skipTest("abstract base class; run a concrete subclass")
        super().setUp()

    # -- helpers: the candidate added elements, identified by phrase -- #

    def _added_practices(self):
        """Return the ``<best_practices>`` practices whose text states the
        reviewable / split-small duty."""
        practices = self.root.findall(".//best_practices/practice")
        return [
            p
            for p in practices
            if _says_pull_request_must_stay_reviewable(_element_text(p))
        ]

    def _added_payload_items(self):
        """Return the ``<to_architect><payload>`` items that require the plan
        to be split into small, reviewable behaviours."""
        payload = _architect_payload_items(self.root)
        return [
            i
            for i in payload
            if _requires_plan_split_into_reviewable_behaviours(_element_text(i))
        ]

    def _added_pitfalls(self):
        """Return the ``<common_pitfalls>`` pitfalls whose ``<mistake>`` is
        the oversized pull request."""
        pitfalls = self.root.findall(".//common_pitfalls/pitfall")
        return [
            p
            for p in pitfalls
            if _is_oversized_pull_request_mistake(
                _element_text(p.find("mistake"))
                if p.find("mistake") is not None
                else ""
            )
        ]

    def _added_checklist_items(self):
        """Return the ``<quality_checklist>`` items under the
        ``before_shipping`` category that check the pull request is a
        reviewable size."""
        items = []
        for category in self.root.findall(".//quality_checklist/category"):
            if (category.get("name") or "") != "before_shipping":
                continue
            for item in category.findall("item"):
                if _checks_reviewable_pull_request_size(_element_text(item)):
                    items.append(item)
        return items

    def _all_added_elements(self):
        """Every element added by behaviour 3, identified by phrase."""
        return (
            self._added_practices()
            + self._added_payload_items()
            + self._added_pitfalls()
            + self._added_checklist_items()
        )

    # -- structure guards (pass now, must keep passing after the green step) -- #

    def test_document_parses_with_instructions_root(self):
        # Well-formed XML is proven by having parsed in setUp; the root tag is
        # asserted on the parsed element, never by substring.
        self.assertEqual(self.root.tag, "instructions")

    def test_workflow_still_has_ten_contiguous_steps(self):
        # The added content is additive to best_practices, the delegation
        # contract, common_pitfalls and the quality checklist — it must not
        # introduce a new workflow step. Passes now (10 steps) and must still
        # pass after the green step.
        steps = _all_steps(self.root)
        self.assertEqual(
            len(steps),
            10,
            "the workflow has %d steps; behaviour 3 is additive and must not "
            "add or remove a workflow step" % len(steps),
        )
        raw = [_step_number(step) for step in steps]
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

    def test_added_texts_carry_no_numeric_line_threshold(self):
        # QUALITATIVE-ONLY GUARD: the newly added texts state no numeric
        # line-count threshold — the PR-size wording stays qualitative
        # (user's decision, plan §1). The four added elements are identified
        # by the same phrase predicates the new-content tests use, and their
        # full text is scanned for a digits-plus-"line(s)" phrase such as
        # "500 lines" or "300-line".
        #
        # The guard scans only the added elements: both files were verified
        # (2026-08-20) to contain no such phrase in any pre-existing element,
        # so pre-existing text cannot trip the guard and none is excluded
        # from it by accident.
        offenders = [
            _element_text(element)
            for element in self._all_added_elements()
            if _DIGIT_LINE_THRESHOLD.search(_element_text(element))
        ]
        self.assertFalse(
            offenders,
            "a newly added element states a numeric line-count threshold; "
            "the PR-size wording must stay qualitative. Offending text: %r"
            % offenders,
        )

    # -- behaviour 3: the four added elements (RED on this commit) -- #

    def test_best_practices_has_high_priority_reviewable_pull_request_practice(self):
        # A <practice priority="high"> whose <rule> states that a pull request
        # must stay reviewable and easy to understand, and that a task
        # growing beyond that is split into smaller tasks.
        practices = self.root.findall(".//best_practices/practice")
        self.assertTrue(practices, "<best_practices> has no <practice> elements")
        matching = [
            p
            for p in practices
            if p.get("priority") == "high"
            and _says_pull_request_must_stay_reviewable(_element_text(p))
        ]
        self.assertTrue(
            matching,
            "no <practice priority='high'> in <best_practices> states that a "
            "pull request must stay reviewable and that a task growing beyond "
            "that is split into smaller tasks (looked for 'review'/'reviewable' "
            "+ 'split'/'small'). Existing practices: %r"
            % [_element_text(p) for p in practices],
        )

    def test_architect_payload_requires_plan_split_into_reviewable_behaviours(self):
        # A <to_architect><payload><item> requiring the PLAN itself to be
        # split into small, reviewable behaviours, so the discipline reaches
        # the planning process and not only coding and testing.
        payload = _architect_payload_items(self.root)
        self.assertTrue(
            payload,
            "<delegation_contract> has no <to_architect><payload><item> elements",
        )
        matching = self._added_payload_items()
        self.assertTrue(
            matching,
            "no <to_architect><payload><item> requires the plan to be split "
            "into small, reviewable behaviours (looked for 'plan'/'behaviour' "
            "+ 'small'/'split'/'reviewable'). Payload item texts: %r"
            % [_element_text(i) for i in payload],
        )

    def test_common_pitfalls_names_oversized_pull_request(self):
        # A <pitfall> whose <mistake> is letting a branch grow into a pull
        # request too large to review, with the <instead> being to split the
        # task.
        pitfalls = self.root.findall(".//common_pitfalls/pitfall")
        self.assertTrue(pitfalls, "<common_pitfalls> has no <pitfall> elements")
        matching = self._added_pitfalls()
        self.assertTrue(
            matching,
            "no <pitfall> has a <mistake> about letting a branch grow into a "
            "pull request too large to review (looked for 'large'/'big'/'huge'/"
            "'grow' + 'pull request'/'review'). Existing mistake texts: %r"
            % [
                _element_text(p.find("mistake"))
                for p in pitfalls
                if p.find("mistake") is not None
            ],
        )
        for pitfall in matching:
            instead = pitfall.find("instead")
            self.assertIsNotNone(
                instead,
                "the oversized-pull-request <pitfall> has no <instead> remedy",
            )
            self.assertTrue(
                _instead_says_split_the_task(_element_text(instead)),
                "the oversized-pull-request pitfall's <instead> does not say to "
                "split the task (looked for 'split' + 'task'). Text: %r"
                % _element_text(instead),
            )

    def test_before_shipping_checklist_checks_reviewable_pull_request_size(self):
        # An <item> in the before_shipping category of <quality_checklist>
        # checking the pull request is a reviewable size.
        categories = self.root.findall(".//quality_checklist/category")
        before_shipping = [
            c for c in categories if (c.get("name") or "") == "before_shipping"
        ]
        self.assertTrue(
            before_shipping,
            "<quality_checklist> has no category named 'before_shipping'; "
            "category names: %r" % [c.get("name") for c in categories],
        )
        existing = [
            item for cat in before_shipping for item in cat.findall("item")
        ]
        self.assertTrue(existing, "the before_shipping category has no <item> elements")
        matching = self._added_checklist_items()
        self.assertTrue(
            matching,
            "no <item> in the before_shipping category checks the pull request "
            "is a reviewable size (looked for 'reviewable'/'size' + 'pull "
            "request'/'change'). Existing item texts: %r"
            % [_element_text(i) for i in existing],
        )


class ManagerTaskSplittingTemplateTests(TaskSplittingDutyTests):
    """Behaviour 3: the tdd-manager TEMPLATE carries the task-splitting duty."""

    template_path = TDD_MANAGER_TEMPLATE


class ManagerTaskSplittingLocalTests(TaskSplittingDutyTests):
    """Behaviour 3: the anvil repo's OWN tdd-manager rules carry the same
    duty.

    ``.roo`` is gitignored, so the local copy is absent on a fresh clone
    (and on CI). ``setUp`` skips every local test cleanly in that case; when
    the file is provisioned, the full assertion set runs exactly as written
    above in the base class.
    """

    template_path = LOCAL_TDD_MANAGER

    def setUp(self):
        if not self.template_path.exists():
            self.skipTest(
                "anvil repo local .roo copy not provisioned; nothing to check"
            )
        super().setUp()


if __name__ == "__main__":
    unittest.main()
