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

B2 of ``plans/cut-agent-context-cost.md`` is also covered here: the batching
rule for no-production-change behaviours. It is additive — one more
``<practice priority="high">``, one more ``<to_architect><payload><item>``,
plus a guard that the pre-existing "One behaviour per cycle" practice
survives, because B2 bounds that rule rather than replacing it.

RED expectation for B2 (this commit): the two new-content assertions fail on
assertion for the right reason — neither the batching practice nor the
payload item exists yet. The survival guard passes now and must keep
passing after the green step.

B3 of the same plan is covered here too: the brief-concision rule for
subtask messages — a brief gives the behaviour, the failure and the
constraints, and gives rationale in one or two sentences with a pointer to
the plan rather than reproducing the argument. It may live in the
``<delegation_contract><preamble>`` or as a ``<best_practices><practice>``;
the test accepts either location. A guard asserts the pre-existing "Write
self-contained subtask messages" practice survives: self-containedness is
the requirement, length is what is bounded (plan §9).

RED expectation for B3 (this commit): the concision-rule assertion fails on
assertion — no preamble or practice states the rule yet. The self-contained
survival guard passes now and must keep passing after the green step.

B4 of the same plan is covered here too: the targeted-test rule — while
iterating, the targeted test file (or single test) is run, and the full
suite is run before committing. The plan (§5, B4) places the rule in the
step 6 / step 7 ``<verification>`` elements AND as a
``<best_practices><practice>``; this test requires BOTH locations, because
the workflow copy is what the manager actually sees mid-cycle and the
practice copy is the form that survives B6's condensation. A separate
guard asserts that the pre-existing full-suite-before-commit gate in step
7's verification ("Run the full suite yourself, not only the new tests.
Commit only on green.") still stands: B4 bounds that gate, it does not
replace it (plan §9). If the targeted-test rule is present but the
full-suite gate is gone, the guard fails naming the missing gate — the
rule must not be readable as licence to commit on a targeted run.

RED expectation for B4 (this commit): the two new-location assertions fail
on assertion — no verification or practice states the targeted-test rule
yet. The full-suite-gate guard passes now and must keep passing after the
green step.

B5 of the same plan is covered here too: the sequencing constraint — a
behaviour that invalidates an existing test cannot be sequenced before
the cycle that rewrites that test, because the pre-commit discipline
makes such a green step uncommittable (plan §3 applies the constraint to
this plan's own ordering). The plan (§5, B5) requires it in BOTH
``<to_architect><payload>`` (so the architect sequences the plan
accordingly) and ``<loop_control>`` (so the manager enforces it while
looping); two separate assertions cover the two locations, so a failure
names exactly which one is missing.

RED expectation for B5 (this commit): the two location assertions fail on
assertion — no payload item and no ``<loop_control>`` element states the
constraint yet. The existing payload-item survival test in
``tests/test_templates_rules.py``
(``test_existing_to_architect_payload_items_still_present``) passes now
and must keep passing: B5 adds a fifth requirement to the payload, it
does not disturb the four markers that test pins.

B6 of the same plan is covered here too: the shrink's byte ceiling. The
tdd-manager instructions file is 22,959 bytes and every tdd-manager
subtask pays for it, so the ceiling — 12 KB, a named module constant —
is asserted directly on the file's byte count. That is the one sanctioned
exception to this module's "never on raw bytes" convention (plan §6):
size is the observable being controlled, so the ceiling is the
requirement itself, not a proxy for one; it reads no phrase and
constrains no wording, so the green step keeps full latitude in the
prose. The ceiling never stands alone — the phrase predicates of this
module and of ``tests/test_templates_rules.py`` run alongside it and
bound the loss: the ceiling bounds the size, the phrase predicates bound
the loss.

RED expectation for B6 (this commit): the byte-ceiling assertion fails
for both the template and the local copy (22,959 bytes against a
12,288-byte ceiling), reporting the actual byte count and the overage.
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


# --------------------------------------------------------------------------- #
# B2 of plans/cut-agent-context-cost.md — the batching rule for
# no-production-change behaviours
# --------------------------------------------------------------------------- #

def _says_no_production_change_behaviours_may_batch(text):
    """True when a ``<practice>``'s text states that behaviours which need no
    production change (pure boundary pins on existing behaviour) may be
    batched into one subtask.

    Stems (all lower-cased, whitespace-collapsed input):
      * the thing being batched: ``"batch"``
      * the qualification, any one of:
          - no production change: ``"production"`` +
            (``"chang"`` | ``"modif"``)
          - a pure boundary pin: ``"pin"``
    Both the thing and at least one qualification must be present, so a
    practice that merely mentions batching something else (e.g. commits) does
    not match.
    """
    batches = ("batch" in text)
    qualification = (
        ("pin" in text)
        or (("production" in text)
            and (("chang" in text) or ("modif" in text)))
    )
    return batches and qualification


def _says_architect_must_mark_batchable_behaviours(text):
    """True when a ``<to_architect><payload><item>``'s text tells the
    architect to mark, in the plan, the behaviours that may be batched (the
    no-production-change ones), so the manager need not re-derive which
    qualify.

    Stems:
      * the action: ``"mark"`` (covers "marked", "marks")
      * the subject: ``"batch"``
    Both must be present, so an item about marking something unrelated (e.g.
    assumptions) does not match.
    """
    return ("mark" in text) and ("batch" in text)


def _says_one_behaviour_per_cycle(text):
    """True when a ``<practice>``'s text is the pre-existing "One behaviour
    per cycle" rule that B2 bounds but must not delete.

    Stems: ``"behaviour"``/``"behavior"`` + ``"cycle"``; ``"one"`` or
    ``"single"`` when present confirms the unit. "cycle" is the distinctive
    stem — no other practice uses it.
    """
    behaviour = ("behaviour" in text) or ("behavior" in text)
    return behaviour and ("cycle" in text)


class BatchingRuleTests(XmlTemplateTestCase):
    """Shared assertions for B2 (plan §5, B2), pointed at either the
    tdd-manager template or the anvil repo's local copy.

    B2 is additive and bounds the pre-existing "One behaviour per cycle"
    practice without replacing it: the new batching practice and the new
    architect payload item must appear, and the one-behaviour-per-cycle
    practice must survive. Each failure message names exactly which element
    is missing, and the one-behaviour-per-cycle failure says so explicitly —
    it is not a wording nit.

    The class itself is collected by ``unittest`` because its name matches
    the default ``Test`` suffix; ``setUp`` skips it, so only the two
    concrete subclasses run the assertions.
    """

    template_path = None

    def setUp(self):
        if self.template_path is None:
            self.skipTest("abstract base class; run a concrete subclass")
        super().setUp()

    def test_best_practices_has_high_priority_batching_practice(self):
        # A <practice priority="high"> in <best_practices> stating that
        # behaviours which are pure boundary pins on existing behaviour,
        # needing no production change, may be batched into one subtask.
        practices = self.root.findall(".//best_practices/practice")
        self.assertTrue(practices, "<best_practices> has no <practice> elements")
        matching = [
            p
            for p in practices
            if p.get("priority") == "high"
            and _says_no_production_change_behaviours_may_batch(_element_text(p))
        ]
        self.assertTrue(
            matching,
            "no <practice priority='high'> in <best_practices> states that "
            "no-production-change (pure boundary-pin) behaviours may be "
            "batched into one subtask (looked for 'batch' + 'pin' | "
            "'production'+'chang'/'modif'). Existing practice texts: %r"
            % [_element_text(p) for p in practices],
        )

    def test_architect_payload_tells_architect_to_mark_batchable_behaviours(self):
        # A <to_architect><payload><item> telling the architect to mark the
        # batchable (no-production-change) behaviours in the plan, so the
        # manager can batch without re-deriving which ones qualify.
        payload = _architect_payload_items(self.root)
        self.assertTrue(
            payload,
            "<delegation_contract> has no <to_architect><payload><item> elements",
        )
        matching = [
            i for i in payload
            if _says_architect_must_mark_batchable_behaviours(_element_text(i))
        ]
        self.assertTrue(
            matching,
            "no <to_architect><payload><item> tells the architect to mark the "
            "no-production-change behaviours as batchable in the plan "
            "(looked for 'mark' + 'batch'). Payload item texts: %r"
            % [_element_text(i) for i in payload],
        )

    def test_one_behaviour_per_cycle_practice_still_present(self):
        # B2 bounds the pre-existing "One behaviour per cycle" practice; it
        # does not replace it. If this practice has gone, the failure must
        # say so explicitly — a reader must not mistake this for a wording
        # nit.
        practices = self.root.findall(".//best_practices/practice")
        self.assertTrue(practices, "<best_practices> has no <practice> elements")
        matching = [
            p for p in practices
            if _says_one_behaviour_per_cycle(_element_text(p))
        ]
        self.assertTrue(
            matching,
            "the pre-existing 'One behaviour per cycle' <practice> has been "
            "REMOVED or mangled beyond recognition — B2 is meant to bound it, "
            "not replace it (looked for 'behaviour'/'behavior' + 'cycle'). "
            "This is not a wording nit: the batching practice does not "
            "restore the one-behaviour-per-cycle discipline. Existing "
            "practice texts: %r"
            % [_element_text(p) for p in practices],
        )


class ManagerBatchingTemplateTests(BatchingRuleTests):
    """B2: the tdd-manager TEMPLATE carries the batching rule."""

    template_path = TDD_MANAGER_TEMPLATE


class ManagerBatchingLocalTests(BatchingRuleTests):
    """B2: the anvil repo's OWN tdd-manager rules carry the same rule.

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


# --------------------------------------------------------------------------- #
# B3 of plans/cut-agent-context-cost.md — the brief-concision rule for
# subtask messages
# --------------------------------------------------------------------------- #

def _says_brief_gives_essentials_and_points_to_plan(text):
    """True when a ``<preamble>`` or ``<practice>`` text states the
    brief-concision rule: the subtask brief gives the behaviour, the
    failure and the constraints, and the rationale is one or two
    sentences with a pointer to the plan rather than the argument
    reproduced.

    Stems (all on lower-cased, whitespace-collapsed input):
      * half 1 — the essentials that must be given, all three:
        ``"behav"`` (behaviour/behavior), ``"failure"``, ``"constrain"``
        (constraints/constraint);
      * half 2 — the bound on the rationale: ``"rationale"`` +
        ``"plan"`` + a pointer concept (``"point"`` | ``"refer"`` |
        ``"cit"``) + a no-reproduction concept (``"reproduc"`` |
        ``"restat"`` | ``"repeat"`` | ``"rather than"`` | ``"instead"``
        | ``"not"``).

    The ``"not"`` disjunct is deliberately weak: it is one member of a
    long AND, so it cannot cross-match on its own; it keeps the
    predicate alive if the rule is phrased "not the argument" rather
    than "rather than reproducing the argument". No existing preamble
    or practice text satisfies all the stems together (verified
    against the file at red time), so the match is not vacuous.
    """
    essentials = (
        ("behav" in text) and ("failure" in text) and ("constrain" in text)
    )
    plan_pointer = (
        ("rationale" in text)
        and ("plan" in text)
        and (("point" in text) or ("refer" in text) or ("cit" in text))
    )
    not_restate = (
        ("reproduc" in text)
        or ("restat" in text)
        or ("repeat" in text)
        or ("rather than" in text)
        or ("instead" in text)
        or ("not" in text)
    )
    return essentials and plan_pointer and not_restate


def _says_write_self_contained_subtask_messages(text):
    """True when a ``<practice>``'s text is the pre-existing "Write
    self-contained subtask messages" rule that B3 bounds, not replaces.

    Stems: ``"self-contain"`` (self-contained/self-containedness) +
    ``"subtask"``. Both appear in the rule sentence itself, so an
    honest condensation of the practice keeps the match while deleting
    the practice breaks it.
    """
    return ("self-contain" in text) and ("subtask" in text)


class ConcisionRuleTests(XmlTemplateTestCase):
    """Shared assertions for B3 (plan §5, B3), pointed at either the
    tdd-manager template or the anvil repo's local copy.

    B3 adds the brief-concision rule — the brief gives the behaviour,
    the failure and the constraints; the rationale is one or two
    sentences with a pointer to the plan, not the argument reproduced.
    The plan allows the rule to live in the
    ``<delegation_contract><preamble>`` or as a ``<best_practices>``
    ``<practice>``; the test accepts either location so the green step
    is not forced into one spot. The pre-existing "Write
    self-contained subtask messages" practice must survive:
    self-containedness is the requirement, length is what is bounded
    (plan §9) — if it has gone, the failure says so explicitly rather
    than as a wording nit.

    The class itself is collected by ``unittest`` because its name
    matches the default ``Test`` suffix; ``setUp`` skips it, so only
    the two concrete subclasses run the assertions.
    """

    template_path = None

    def setUp(self):
        if self.template_path is None:
            self.skipTest("abstract base class; run a concrete subclass")
        super().setUp()

    def _concision_rule_candidates(self):
        """The elements that may carry the B3 rule: the delegation
        preamble first, then every ``<best_practices>`` practice, each
        labelled with a human-readable location for the failure
        diagnostic."""
        candidates = []
        preamble = self.root.find(".//delegation_contract/preamble")
        if preamble is not None:
            candidates.append(("delegation_contract/preamble", preamble))
        practices = self.root.findall(".//best_practices/practice")
        candidates.extend(
            ("best_practices/practice[%d]" % (index + 1), practice)
            for index, practice in enumerate(practices)
        )
        return candidates

    def test_concision_rule_present_in_preamble_or_practice(self):
        # The rule may live in the <delegation_contract><preamble> or
        # as a <best_practices><practice>; accept either location.
        candidates = self._concision_rule_candidates()
        self.assertTrue(
            candidates,
            "neither <delegation_contract><preamble> nor "
            "<best_practices> exists; nothing to check the rule against",
        )
        matching = [
            (where, element)
            for where, element in candidates
            if _says_brief_gives_essentials_and_points_to_plan(
                _element_text(element)
            )
        ]
        self.assertTrue(
            matching,
            "no <delegation_contract><preamble> or <best_practices>"
            "<practice> states the brief-concision rule (the brief gives "
            "the behaviour, the failure and the constraints; the rationale "
            "is one or two sentences with a pointer to the plan, not the "
            "argument reproduced) (looked for 'behav'+'failure'+'constrain' "
            "+ 'rationale'+'plan'+('point'|'refer'|'cit') + "
            "('reproduc'|'restat'|'repeat'|'rather than'|'instead'|'not'). "
            "Every candidate's text: %r"
            % [(where, _element_text(element)) for where, element in candidates],
        )

    def test_self_contained_subtask_messages_practice_still_present(self):
        # B3 bounds the pre-existing "Write self-contained subtask
        # messages" practice; it does not replace it. Self-containedness
        # is the requirement, length is what is bounded (plan §9). If
        # this practice has gone, the failure must say so explicitly —
        # a reader must not mistake this for a wording nit.
        practices = self.root.findall(".//best_practices/practice")
        self.assertTrue(practices, "<best_practices> has no <practice> elements")
        matching = [
            p for p in practices
            if _says_write_self_contained_subtask_messages(_element_text(p))
        ]
        self.assertTrue(
            matching,
            "the pre-existing 'Write self-contained subtask messages' "
            "<practice> has been REMOVED or mangled beyond recognition — "
            "B3 is meant to bound it (self-containedness is the "
            "requirement; length is what is bounded), not replace it "
            "(looked for 'self-contain' + 'subtask'). This is not a "
            "wording nit: the concision rule does not restore the "
            "self-contained discipline. Existing practice texts: %r"
            % [_element_text(p) for p in practices],
        )


class ManagerConcisionTemplateTests(ConcisionRuleTests):
    """B3: the tdd-manager TEMPLATE carries the brief-concision rule."""

    template_path = TDD_MANAGER_TEMPLATE


class ManagerConcisionLocalTests(ConcisionRuleTests):
    """B3: the anvil repo's OWN tdd-manager rules carry the same rule.

    ``.roo`` is gitignored, so the local copy is absent on a fresh clone
    (and on CI). ``setUp`` skips every local test cleanly in that case;
    when the file is provisioned, the full assertion set runs exactly as
    written above in the base class.
    """

    template_path = LOCAL_TDD_MANAGER

    def setUp(self):
        if not self.template_path.exists():
            self.skipTest(
                "anvil repo local .roo copy not provisioned; nothing to check"
            )
        super().setUp()


# --------------------------------------------------------------------------- #
# B4 of plans/cut-agent-context-cost.md — the targeted-test rule: run the
# targeted test file while iterating, the full suite before committing
# --------------------------------------------------------------------------- #

def _says_run_targeted_tests_while_iterating(text):
    """True when a ``<verification>`` or ``<practice>`` text states the
    B4 rule: while iterating, the targeted test (file / single test) is
    run.

    Stems (all on lower-cased, whitespace-collapsed input):
      * the thing being run, any one of:
          ``"target"`` (targeted/target/test file), ``"single test"``,
          ``"new tests"``, ``"failing tests"``;
      * the temporal scope, any one of:
          ``"while"`` (while iterating), ``"iterat"`` (iterating/
          iteration), ``"per cycl"`` (per cycle / each cycle),
          ``"red/green"`` (the red/green loop).
    Both halves must be present, so a verification that merely tells the
    manager to run something (the existing "Run the suite yourself" of
    step 6) or that merely mentions iteration without a narrowed run does
    not match. Verified against both files at red time: no existing
    element carries any of the "thing" stems together with any of the
    temporal stems.
    """
    narrowed = (
        ("target" in text)
        or ("single test" in text)
        or ("new tests" in text)
        or ("failing tests" in text)
    )
    while_iterating = (
        ("while" in text)
        or ("iterat" in text)
        or ("per cycl" in text)
        or ("red/green" in text)
    )
    return narrowed and while_iterating


def _says_full_suite_required_before_commit(text):
    """True when a ``<verification>`` text states the pre-existing
    full-suite-before-commit gate (step 7, plan line 106): the full
    suite is run, and the commit happens only on green.

    Stems (all on lower-cased, whitespace-collapsed input):
      * the run: ``"full"`` + (``"suite"`` | ``"tests"``);
      * the gate: a commit term (``"commit"`` | ``"green"``) plus an
        only-if-green form (``"only"`` | ``"before"``) — "Commit only on
        green" carries ``"commit"`` + ``"green"`` + ``"only"`` and no
        other existing verification carries them together.
    """
    full_run = ("full" in text) and (("suite" in text) or ("tests" in text))
    gate = (
        (("commit" in text) or ("green" in text))
        and (("only" in text) or ("before" in text))
    )
    return full_run and gate


class TargetedTestRuleTests(XmlTemplateTestCase):
    """Shared assertions for B4 (plan §5, B4), pointed at either the
    tdd-manager template or the anvil repo's local copy.

    B4 is additive: the targeted-test rule (run the targeted test file
    while iterating; the full suite before committing) must appear in
    BOTH the step 6 / step 7 ``<verification>`` elements and as a
    ``<best_practices><practice>`` — the plan names both locations, so
    the test requires both. A separate guard asserts the pre-existing
    full-suite-before-commit gate in step 7's verification survives:
    plan §9 lists it as bounded, never weakened, and the missing-gate
    failure names the gate explicitly so the targeted-test rule can
    never be read as licence to commit on a targeted run.

    The class itself is collected by ``unittest`` because its name
    matches the default ``Test`` suffix; ``setUp`` skips it, so only
    the two concrete subclasses run the assertions.
    """

    template_path = None

    def setUp(self):
        if self.template_path is None:
            self.skipTest("abstract base class; run a concrete subclass")
        super().setUp()

    def _step_verifications(self, numbers):
        """The ``<verification>`` elements of the workflow steps whose
        ``number`` attribute is in *numbers* (step 6 and step 7), each
        labelled with its step number for the failure diagnostic. Steps
        missing a ``<verification>`` are not fabricated — their absence
        is part of the red state."""
        candidates = []
        for step in _all_steps(self.root):
            if _step_number(step) not in numbers:
                continue
            verification = step.find("verification")
            if verification is not None:
                candidates.append((_step_number(step), verification))
        return candidates

    def _targeted_rule_verification_candidates(self):
        """Step 6 / step 7 ``<verification>`` elements, for the red
        assertion that the targeted-test rule is absent there today."""
        return self._step_verifications(["6", "7"])

    def test_step_verifications_state_targeted_tests_while_iterating(self):
        # RED on this commit: the plan says the rule "belongs in
        # <step number='6'> / <step number='7'> <verification>", and
        # today neither verification mentions running the targeted test
        # file while iterating — step 6 says "Run the suite yourself"
        # (the full suite, on the red step) and step 7 says "Run the
        # full suite yourself, not only the new tests. Commit only on
        # green." (the gate, which the next test pins). The green step
        # must add the narrowed run to one of these two verifications.
        candidates = self._targeted_rule_verification_candidates()
        self.assertTrue(
            candidates,
            "neither <step number='6'> nor <step number='7'> has a "
            "<verification> element; the targeted-test rule has nowhere "
            "to live in the workflow",
        )
        matching = [
            (number, element)
            for number, element in candidates
            if _says_run_targeted_tests_while_iterating(_element_text(element))
        ]
        self.assertTrue(
            matching,
            "no <verification> in <step number='6'> or <step number='7'> "
            "states the targeted-test rule (run the targeted test file / "
            "single test while iterating; the full suite is run before "
            "committing) (looked for ('target'|'single test'|'new tests'|"
            "'failing tests') + ('while'|'iterat'|'per cycl'|'red/green'). "
            "Note: 'run the full suite' alone is the gate, not this rule "
            "— it carries no 'target' stem. Every candidate's text: %r"
            % [
                ("step " + number, _element_text(element))
                for number, element in candidates
            ],
        )

    def test_best_practices_has_high_priority_targeted_test_practice(self):
        # RED on this commit: no <practice priority="high"> states the
        # targeted-test rule yet. The practice form is what must survive
        # B6's condensation, so the plan wants it there even though the
        # workflow verifications carry the same rule.
        practices = self.root.findall(".//best_practices/practice")
        self.assertTrue(practices, "<best_practices> has no <practice> elements")
        matching = [
            p
            for p in practices
            if p.get("priority") == "high"
            and _says_run_targeted_tests_while_iterating(_element_text(p))
        ]
        self.assertTrue(
            matching,
            "no <practice priority='high'> in <best_practices> states the "
            "targeted-test rule (run the targeted test file / single test "
            "while iterating; the full suite is run before committing) "
            "(looked for ('target'|'single test'|'new tests'|'failing "
            "tests') + ('while'|'iterat'|'per cycl'|'red/green'). Existing "
            "practice texts: %r"
            % [_element_text(p) for p in practices],
        )

    def test_full_suite_before_commit_gate_still_stated(self):
        # GREEN on this commit; the assertion that protects rigour.
        # Step 7's existing verification says "Run the full suite
        # yourself, not only the new tests. Commit only on green."
        # (plan line 106). B4 bounds that gate — targeted tests while
        # iterating — but must not delete it. If the gate is gone while
        # the targeted-test rule exists, the manager is left with
        # licence to commit on a targeted run, and this failure says
        # so explicitly rather than as a wording nit.
        verifications = self._step_verifications(["6", "7"])
        self.assertTrue(
            verifications,
            "neither <step number='6'> nor <step number='7'> has a "
            "<verification> element; the full-suite-before-commit gate "
            "has nowhere to live in the workflow",
        )
        matching = [
            (number, element)
            for number, element in verifications
            if _says_full_suite_required_before_commit(_element_text(element))
        ]
        self.assertTrue(
            matching,
            "the full-suite-before-commit gate has been REMOVED from step "
            "6/7 <verification> — the rule to run the FULL suite (not only "
            "the new tests) before committing is gone. This is not a "
            "wording nit: without it the B4 targeted-test rule reads as "
            "licence to commit on a targeted run (looked for 'full'+"
            "('suite'|'tests') + ('commit'|'green') + ('only'|'before')). "
            "Plan §9: the full-suite-before-commit rule is bounded by B4, "
            "never weakened. Every step 6/7 <verification> text: %r"
            % [
                ("step " + number, _element_text(element))
                for number, element in verifications
            ],
        )


class ManagerTargetedTestTemplateTests(TargetedTestRuleTests):
    """B4: the tdd-manager TEMPLATE carries the targeted-test rule."""

    template_path = TDD_MANAGER_TEMPLATE


class ManagerTargetedTestLocalTests(TargetedTestRuleTests):
    """B4: the anvil repo's OWN tdd-manager rules carry the same rule.

    ``.roo`` is gitignored, so the local copy is absent on a fresh clone
    (and on CI). ``setUp`` skips every local test cleanly in that case;
    when the file is provisioned, the full assertion set runs exactly as
    written above in the base class.
    """

    template_path = LOCAL_TDD_MANAGER

    def setUp(self):
        if not self.template_path.exists():
            self.skipTest(
                "anvil repo local .roo copy not provisioned; nothing to check"
            )
        super().setUp()


# --------------------------------------------------------------------------- #
# B5 of plans/cut-agent-context-cost.md — the sequencing constraint: a
# behaviour that invalidates an existing test cannot be sequenced before
# the cycle that rewrites that test
# --------------------------------------------------------------------------- #

def _says_invalidating_behaviour_cannot_precede_rewrite_cycle(text):
    """True when a ``<item>`` or a ``<loop_control>`` content element
    states the B5 sequencing constraint: a behaviour that invalidates an
    existing test cannot be sequenced before the cycle that rewrites
    that test.

    Stems (all on lower-cased, whitespace-collapsed input):
      * the invalidation, both halves:
          ``"invalidat"`` (invalidates/invalidating/invalidation) and
          (``"test"`` | ``"assert"``);
      * the ordering, all three:
          ``"sequenc"`` (sequence/sequenced/sequencing), an ordering word
          (``"before"`` | ``"after"`` | ``"precede"`` | ``"prior"`` |
          ``"follow"``), and ``"cycl"`` (cycle/cycles).

    Cross-match check (verified against both files at red time): neither
    ``"invalidat"`` nor ``"sequenc"`` occurs in either file's text — the
    only ``"sequenc"`` hit in the raw file is the ``<consequence>`` tag
    name, which ``itertext`` never returns. So no existing element can
    match, including ``<loop_control>``'s failure-handling and ambiguity
    cases, which talk about re-planning, regressions and the architect
    (the ``regression`` case carries "test" + "cycle", but no
    ``"invalidat"`` and no ``"sequenc"``).
    """
    invalidation = (
        ("invalidat" in text)
        and (("test" in text) or ("assert" in text))
    )
    ordering = (
        ("sequenc" in text)
        and (
            ("before" in text)
            or ("after" in text)
            or ("precede" in text)
            or ("prior" in text)
            or ("follow" in text)
        )
        and ("cycl" in text)
    )
    return invalidation and ordering


class SequencingConstraintTests(XmlTemplateTestCase):
    """Shared assertions for B5 (plan §5, B5), pointed at either the
    tdd-manager template or the anvil repo's local copy.

    B5 adds the sequencing constraint — a behaviour that invalidates an
    existing test cannot be sequenced before the cycle that rewrites
    that test — in BOTH ``<to_architect><payload>`` and
    ``<loop_control>``. The plan is explicit: stated in only one of the
    two places fails, naming the missing one; so the two locations are
    covered by two separate assertions rather than one combined check.

    The class itself is collected by ``unittest`` because its name
    matches the default ``Test`` suffix; ``setUp`` skips it, so only the
    two concrete subclasses run the assertions.
    """

    template_path = None

    def setUp(self):
        if self.template_path is None:
            self.skipTest("abstract base class; run a concrete subclass")
        super().setUp()

    def _loop_control_candidates(self):
        """The ``<loop_control>`` content elements the B5 rule may live
        in: every leaf element (the ``<case>``, ``<criterion>``,
        ``<hard_stop>``, ``<invariant>``, ``<ledger>`` and similar
        elements where the text actually lives), plus
        ``<loop_control>`` itself as a fallback for text written
        directly under it.

        The leaf elements are scanned individually rather than their
        containers (``<failure_handling>``, ``<ambiguity_handling>``,
        ``<termination>``) as a whole, so the match cannot be assembled
        out of stems scattered across two elements. Returns ``None``
        when the document has no ``<loop_control>`` at all.
        """
        loop_control = self.root.find(".//loop_control")
        if loop_control is None:
            return None
        candidates = [
            element
            for element in loop_control.iter()
            if element is not loop_control and len(element) == 0
        ]
        candidates.append(loop_control)
        return candidates

    def test_architect_payload_states_sequencing_constraint(self):
        # RED on this commit: no <to_architect><payload><item> tells the
        # architect to sequence a behaviour that invalidates an existing
        # test at or after the cycle that rewrites that test. The
        # constraint belongs in BOTH this payload item and
        # <loop_control> (see
        # test_loop_control_states_sequencing_constraint); this
        # assertion covers the payload half, so its failure names the
        # missing location as <to_architect><payload>.
        payload = _architect_payload_items(self.root)
        self.assertTrue(
            payload,
            "<delegation_contract> has no <to_architect><payload><item> elements",
        )
        matching = [
            i
            for i in payload
            if _says_invalidating_behaviour_cannot_precede_rewrite_cycle(
                _element_text(i)
            )
        ]
        self.assertTrue(
            matching,
            "the sequencing constraint is MISSING from "
            "<to_architect><payload> (looked for 'invalidat'+"
            "('test'|'assert') + 'sequenc'+"
            "('before'|'after'|'precede'|'prior'|'follow')+'cycl'). B5 "
            "requires it in BOTH <to_architect><payload> and "
            "<loop_control>; the missing location here is "
            "<to_architect><payload>. Payload item texts: %r"
            % [_element_text(i) for i in payload],
        )

    def test_loop_control_states_sequencing_constraint(self):
        # RED on this commit: no element of <loop_control> states the
        # sequencing constraint. The manager must enforce it while
        # looping: a behaviour that invalidates an existing test cannot
        # be sequenced before the cycle that rewrites that test, because
        # the pre-commit discipline makes such a green step
        # uncommittable, so getting the order wrong forces a mid-flight
        # re-plan.
        #
        # Note for the green step: <loop_control> already contains
        # failure-handling and ambiguity cases that talk about
        # re-planning and the architect (green_still_failing,
        # plan_ambiguous_but_requirement_clear); none of them carries
        # the 'invalidat' + 'sequenc' stems, so they do not satisfy this
        # assertion.
        candidates = self._loop_control_candidates()
        self.assertIsNotNone(
            candidates,
            "document has no <loop_control> element; the sequencing "
            "constraint has nowhere to live in the loop rules",
        )
        matching = [
            element
            for element in candidates
            if _says_invalidating_behaviour_cannot_precede_rewrite_cycle(
                _element_text(element)
            )
        ]
        self.assertTrue(
            matching,
            "the sequencing constraint is MISSING from <loop_control> "
            "(looked for 'invalidat'+('test'|'assert') + "
            "'sequenc'+('before'|'after'|'precede'|'prior'|'follow')"
            "'cycl' in every leaf element of <loop_control> and in the "
            "element itself). B5 requires it in BOTH <to_architect>"
            "<payload> and <loop_control>; the missing location here is "
            "<loop_control>. The existing failure-handling and ambiguity "
            "cases talk about re-planning and the architect without "
            "stating this constraint, so they do not qualify. Every "
            "candidate's text: %r"
            % [_element_text(element) for element in candidates],
        )


class ManagerSequencingTemplateTests(SequencingConstraintTests):
    """B5: the tdd-manager TEMPLATE carries the sequencing constraint."""

    template_path = TDD_MANAGER_TEMPLATE


class ManagerSequencingLocalTests(SequencingConstraintTests):
    """B5: the anvil repo's OWN tdd-manager rules carry the same
    constraint.

    ``.roo`` is gitignored, so the local copy is absent on a fresh clone
    (and on CI). ``setUp`` skips every local test cleanly in that case;
    when the file is provisioned, the full assertion set runs exactly as
    written above in the base class.
    """

    template_path = LOCAL_TDD_MANAGER

    def setUp(self):
        if not self.template_path.exists():
            self.skipTest(
                "anvil repo local .roo copy not provisioned; nothing to check"
            )
        super().setUp()


# --------------------------------------------------------------------------- #
# B6 of plans/cut-agent-context-cost.md — the shrink: a byte ceiling on
# the tdd-manager instructions file
# --------------------------------------------------------------------------- #

# The byte ceiling for ``rules-tdd-manager/instructions.xml`` (both copies).
#
# plans/cut-agent-context-cost.md §5 (B6) sets the ceiling at 12 KB: the
# file is 22,959 bytes today and every tdd-manager subtask pays for it.
# §6 records why a byte-count assertion is the one sanctioned exception
# to "never assert on the source text of the thing under test": the
# ceiling is not a proxy for a requirement — size is the observable being
# controlled, so the ceiling is the requirement itself. It is also the
# narrowest assertion possible: one number against one threshold; it reads
# no phrase and constrains no wording, so the green step keeps full
# latitude in the prose.
#
# The ceiling never stands alone. The phrase predicates of this module and
# of tests/test_templates_rules.py run alongside it and prove no rule was
# lost: the ceiling bounds the size, the phrase predicates bound the loss.
# A document emptied to zero bytes cannot pass this test either: it fails
# to parse in XmlTemplateTestCase.setUp before the assertion runs, and its
# root tag and ten contiguous steps are asserted by
# test_document_parses_with_instructions_root and
# test_workflow_still_has_ten_contiguous_steps.
TDD_MANAGER_BYTE_CEILING = 12_288  # 12 KB, per plans/cut-agent-context-cost.md §5 (B6)


class ByteCeilingTests(XmlTemplateTestCase):
    """Shared assertion for B6 (plan §5, B6), pointed at either the
    tdd-manager template or the anvil repo's local copy.

    One narrow assertion: the file's byte count is at or below
    TDD_MANAGER_BYTE_CEILING. It reads no phrase and constrains no
    wording — that latitude is the point, and it is why the assertion is
    defensible (plan §6). Over the ceiling, the test fails reporting the
    actual byte count and the overage, not just "too big".

    Parsing is inherited from XmlTemplateTestCase.setUp, so a malformed or
    emptied document fails at load time rather than passing silently; the
    root tag and the ten contiguous steps are asserted by
    TaskSplittingDutyTests, not re-asserted here.

    The class itself is collected by ``unittest`` because its name matches
    the default ``Test`` suffix; ``setUp`` skips it, so only the two
    concrete subclasses run the assertion.
    """

    template_path = None

    def setUp(self):
        if self.template_path is None:
            self.skipTest("abstract base class; run a concrete subclass")
        super().setUp()

    def test_file_is_at_or_below_byte_ceiling(self):
        actual = self.template_path.stat().st_size
        self.assertLessEqual(
            actual,
            TDD_MANAGER_BYTE_CEILING,
            "%s is %d bytes; the ceiling is %d bytes — %d bytes over. "
            "plans/cut-agent-context-cost.md §5 (B6): the file is too "
            "large and every tdd-manager subtask pays for it. Condense it "
            "— do not delete an element the phrase predicates in this "
            "module or in tests/test_templates_rules.py match."
            % (
                self.template_path,
                actual,
                TDD_MANAGER_BYTE_CEILING,
                actual - TDD_MANAGER_BYTE_CEILING,
            ),
        )


class ManagerByteCeilingTemplateTests(ByteCeilingTests):
    """B6: the tdd-manager TEMPLATE is at or below the byte ceiling."""

    template_path = TDD_MANAGER_TEMPLATE


class ManagerByteCeilingLocalTests(ByteCeilingTests):
    """B6: the anvil repo's OWN tdd-manager rules are at or below the byte
    ceiling.

    ``.roo`` is gitignored, so the local copy is absent on a fresh clone
    (and on CI). ``setUp`` skips every local test cleanly in that case; when
    the file is provisioned, the assertion runs exactly as written above in
    the base class.
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
