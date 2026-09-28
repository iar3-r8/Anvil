"""Tests for behaviour 2 of ``plans/adopt-tool-swap-harvest-findings.md`` —
the docs-manager ``page_prose`` workflow step, its three accompanying
``<best_practices>`` rules (the link-to-the-plan rule is gone: the plan is
not part of the documentation, so no rule may tell the writer to link to
it), and the ``<communication><completion>`` self-check clause.

The two files under test are data:

  * ``templates/roo_template/rules-docs-manager/guidelines.xml`` (deployed
    by ``setup-repo``);
  * ``.roo/rules-docs-manager/guidelines.xml`` (anvil's own local copy,
    gitignored — absent on a fresh clone / CI).

Each file holds root ``<guidelines>``: a ``<workflow>`` of four
``name``-keyed steps (``start``, ``code_comments``, ``usage_docs``,
``structure``), a ``<best_practices>`` block of 9 ``<rule>`` elements, a
``<documentation_finalisation>`` block of 2 ``<rule>`` elements, a
``<constraints>`` block and a ``<communication>`` block. Behaviour 2
inserts one ``<step name="page_prose">`` between ``usage_docs`` and
``structure``, appends three rules, and extends ``<completion>``.

This module follows the conventions of ``tests/test_qna_rules.py``: every
assertion is on the parsed XML structure plus key phrases, never on raw
bytes. The shared ``XmlTemplateTestCase`` base and the ``_element_text``
helper are imported from ``tests/test_templates_rules.py``; the
template-plus-local B19/B20 pattern is reused with a local subclass that
skips cleanly when ``.roo/`` is absent. The shared
``_all_steps``/``_step_number`` helpers assume ``number`` attributes, but
the docs-manager steps are ``name``-keyed, so :func:`_step_by_name`
here is the right shape. Whole-file equality between the template and
the local copy is deliberately NOT asserted (``tests/test_rules_mirror.py``
guards byte-identity separately).

The new ``<self_check>`` must run ``grep -rniE`` over ``doc/`` excluding
``doc/external/`` plus ``README.md`` — the source's bare ``docs/`` target
and its ``docs/configuration.md`` skip are NOT adopted, so a verbatim copy
of the source text fails this module.
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
# text helper. Imported after the sys.path fix above, matching the
# convention in tests/test_templates_rules.py itself.
from tests.test_templates_rules import (  # noqa: E402
    XmlTemplateTestCase,
    _element_text,
)

DOCS_TEMPLATE = (
    REPO_ROOT / "templates" / "roo_template" / "rules-docs-manager" / "guidelines.xml"
)
LOCAL_DOCS = REPO_ROOT / ".roo" / "rules-docs-manager" / "guidelines.xml"

# The docs-manager guidelines are parsed through a loader that escapes bare
# ampersands on a string copy before ElementTree sees the text, keeping the
# same tolerance pattern as the qna-tester module for consistency. The data
# files are well-formed today, so a missing file, or a document malformed
# beyond an unescaped ampersand, still fails at load time.
_BARE_AMPERSAND = re.compile(r"&(?!(?:[a-zA-Z][a-zA-Z0-9]*|#[0-9]+|#x[0-9a-fA-F]+);)")


def _load_docs_guidelines(path):
    """Parse the docs-manager guidelines at *path*, returning the root
    element.

    Bare ampersands are escaped on a string copy before ElementTree sees
    the text, so an unescaped "&" does not abort the parse; the file on
    disk is never touched. A missing file, or a document that is malformed
    beyond an unescaped ampersand, still fails at load time, so a genuinely
    corrupt document cannot slip through silently.
    """
    raw = Path(path).read_text(encoding="utf-8")
    escaped = _BARE_AMPERSAND.sub("&" + "amp;", raw)
    return ET.fromstring(escaped)


def _step_by_name(root, name):
    """Return the ``<step>`` under ``<workflow>`` whose ``name`` attribute
    equals *name*, or ``None``.

    Local because the shared ``_step_number`` helper assumes ``number``
    attributes and the docs-manager steps are ``name``-keyed.
    """
    for step in root.findall(".//workflow/step"):
        if step.get("name") == name:
            return step
    return None


# Marker phrases, one per each of the 9 original <rule> elements, proving
# all 9 survive the additive change (checked case-insensitively against
# the combined text of every <rule>, so a single altered element that drops
# its marker fails).
ORIGINAL_RULE_MARKERS = (
    'the "why", never the "what"',
    "vcs log",
    "mirror the current",
    "one guide per concern",
    "from memory",
    "docstrings",
    "surprising",
    "readme.md and doc/",
    "architectural decisions",
)

ORIGINAL_STEP_NAMES = ("start", "code_comments", "usage_docs", "structure")


# --------------------------------------------------------------------------- #
# Phrase predicates for the new content (lower-cased text in, bool out)
# --------------------------------------------------------------------------- #

def _verify_strips_delivery_vocabulary(text):
    """True when a ``<verify>`` says a page must strip delivery vocabulary:
    slice letters, milestone identifiers, behaviour numbers, pull request
    numbers, commit hashes and shipped/will-ship (shipped/planned)
    sequencing."""
    vocabulary = (
        "slice" in text
        and "milestone" in text
        and "behaviour" in text
        and ("pull request" in text or " pr " in text)
        and "commit" in text
        and ("shipped" in text or "will-ship" in text or "planned" in text)
    )
    says_as_it_is_now = "as it is now" in text
    return vocabulary and says_as_it_is_now


def _verify_says_vocabulary_belongs_in_plan_commit_pr(text):
    """True when a ``<verify>`` says the vocabulary belongs in the plan,
    commit message and pull request."""
    names_plan = "plan" in text
    names_commit_message = (
        "commit message" in text
        or ("commit" in text and "message" in text)
    )
    names_pr = ("pull request" in text) or ("pull requests" in text)
    return names_plan and names_commit_message and names_pr


def _self_check_is_scoped_grep_invocation(text):
    """True when a ``<self_check>`` carries a ``grep -rniE`` invocation
    whose targets include ``doc/`` and ``README.md`` and which EXCLUDES
    ``doc/external/`` — and does not name the source's ``configuration.md``
    example.

    The source's self-check greps ``docs/ README.md`` and skips
    ``docs/configuration.md``; a verbatim copy of the source text fails
    this predicate on three counts: it names bare ``docs/`` instead of
    ``doc/``, it carries no ``doc/external`` exclusion, and it names
    ``configuration.md``.
    """
    has_grep = "grep -rnie" in text
    targets_doc_dir = "doc/" in text
    targets_readme = "readme.md" in text
    excludes_external = "doc/external" in text
    rejects_source_target = "docs/" not in text
    rejects_source_example = "configuration.md" not in text
    return (
        has_grep
        and targets_doc_dir
        and targets_readme
        and excludes_external
        and rejects_source_target
        and rejects_source_example
    )


def _allow_mentions_capability_limit_or_schedule(text):
    """True when an ``<allow>`` is a plain capability-limit note."""
    capability = ("capability limit" in text) or ("capability-limit" in text)
    schedule = "schedule" in text
    return capability or schedule


def _forbid_mentions_timeline_or_milestone(text):
    """True when a ``<forbid>`` bans a project timeline."""
    return ("timeline" in text) or ("milestone" in text)


def _rule_bans_delivery_vocabulary(text):
    """True when a rule is the delivery-vocabulary ban: the page describes
    the system as it is now, and the delivery vocabulary is named (slice,
    milestone, behaviour, pull request, commit) — but the rule must NOT
    carry the duplicated homes clause, pinned by the absence of
    "permanent and searchable". The rule still contains the words
    "plan", "commit" and "pull request" as vocabulary items, so the
    negative targets the clause, not the words."""
    vocabulary = (
        "slice" in text
        and "milestone" in text
        and "behaviour" in text
        and ("pull request" in text)
        and "commit" in text
    )
    says_now = "as it is now" in text
    no_duplicated_homes_clause = "permanent and searchable" not in text
    return vocabulary and says_now and no_duplicated_homes_clause


def _rule_capability_limit_useful_schedule_not(text):
    """True when a rule says a capability limit is useful but a schedule
    is not — and the rule does NOT carry both "link" and "plan".

    The trailing "the reader who wants the plan gets a link to it" clause
    is the same link-to-the-plan advice the standalone rule carried, so the
    predicate now requires its absence alongside the positive requirement.
    """
    capability = ("capability limit" in text) or ("capability-limit" in text)
    schedule = "schedule" in text
    negates = (
        ("not" in text)
        or ("never" in text)
        or ("no" in text)
        or ("useful" in text and "not useful" in text)
    )
    no_plan_link = not ("link" in text and "plan" in text)
    return capability and schedule and negates and no_plan_link


def _rule_internal_design_pages_banned_equally(text):
    """True when a rule says internal design pages may be technical but the
    delivery-vocabulary ban applies to them equally."""
    internal = "internal" in text or "design page" in text
    technical = "technical" in text
    ban_applies = (
        ("equally" in text)
        or ("still applies" in text)
        or ("applies the same" in text)
        or ("apply the same" in text)
        or ("also applies" in text)
        or ("just as" in text)
    )
    return internal and technical and ban_applies


def _rule_says_readme_doc_accurate_clear_and_simple(text):
    """True when a rule names README.md and doc/ and demands they stay
    accurate AND clear AND simple to understand.

    R5 of the review round: the ORIGINAL rule 8 ("Keep README.md and
    doc/ accurate; detailed guides live in doc/.") pins only the accuracy
    half. The reworded rule must keep "accurate" (so a reword that drops
    it fails here and in ``test_original_best_practice_rules_survive``)
    and add "clear" and "simple to understand".
    """
    names_targets = "readme.md and doc/" in text
    accurate = "accurate" in text
    clear = "clear" in text
    simple = "simple" in text
    return names_targets and accurate and clear and simple


def _completion_reports_page_prose_self_check(text):
    """True when the ``<completion>`` text reports the page_prose
    self-check: it names ``page_prose``, says the grep was run, and that
    every hit was fixed or justified."""
    names_step = "page_prose" in text
    ran_grep = "grep" in text
    says_fixed_or_justified = "fixed" in text and "justified" in text
    says_every_hit = ("every hit" in text) or ("all hits" in text)
    return names_step and ran_grep and says_fixed_or_justified and says_every_hit


# --------------------------------------------------------------------------- #
# Shared assertions, pointed at either the template or the local copy
# --------------------------------------------------------------------------- #

class DocsManagerPageProseBase(XmlTemplateTestCase):
    """Shared assertions for behaviour 2 of
    ``plans/adopt-tool-swap-harvest-findings.md``.

    One subclass points at the template, one at the anvil repo's local
    ``.roo`` copy, so the local copy cannot drift from the template on the
    new guidance. Only the parsed structure and key phrases are locked,
    never whole-file equality.

    The class itself is collected by ``unittest`` because it is a
    ``TestCase`` subclass; ``setUp`` skips it, so only the two concrete
    subclasses run the assertions (precedent:
    ``QnaTestingDisciplineBase`` in tests/test_qna_rules.py).

    ``setUp`` parses through :func:`_load_docs_guidelines` rather than the
    shared ``_load_xml``: the loader's ampersand tolerance keeps the same
    pattern as the qna-tester module so an unescaped "&" can never abort
    the suite. Everything else about loading is inherited (a missing file
    still fails, never skips, for the template).
    """

    def setUp(self):
        if self.template_path is None:
            self.skipTest("abstract base class; run a concrete subclass")
        self.root = _load_docs_guidelines(self.template_path)

    # -- structure guards (pass now, must keep passing after the green step) -- #

    def test_document_parses_with_guidelines_root(self):
        # Well-formed XML is proven by having parsed in setUp; the root tag
        # is asserted on the parsed element, never by substring.
        self.assertEqual(self.root.tag, "guidelines")

    def test_original_workflow_steps_survive_by_name(self):
        # The four original workflow steps survive, recognised by name
        # (the docs-manager steps are name-keyed, not number-keyed).
        for name in ORIGINAL_STEP_NAMES:
            step = _step_by_name(self.root, name)
            self.assertIsNotNone(
                step,
                "original workflow step %r is missing from <workflow>" % name,
            )

    def test_original_best_practice_rules_survive(self):
        # Additive behaviour: all 9 original <rule> elements survive, each
        # recognised by its marker phrase.
        rules = self.root.findall("best_practices/rule")
        self.assertGreaterEqual(
            len(rules),
            9,
            "expected the 9 original <rule> elements to survive; found %d"
            % len(rules),
        )
        all_text = " ".join(_element_text(r) for r in rules)
        for marker in ORIGINAL_RULE_MARKERS:
            self.assertIn(
                marker,
                all_text,
                "an original <rule> is missing or was altered (expected "
                "marker %r). Rule texts: %r" % (marker, all_text),
            )

    def test_original_rule_8_says_readme_doc_accurate_clear_and_simple(self):
        # R5: rule 8 keeps its accuracy requirement (still pinned by the
        # "readme.md and doc/" marker in
        # test_original_best_practice_rules_survive) and gains the
        # reviewer's "clear and simple to understand" demand. The
        # predicate fails on the current accuracy-only rule text; a
        # reword that drops "accurate" also fails, so the original
        # requirement stays pinned through the reword.
        matching = self._rules_matching(
            _rule_says_readme_doc_accurate_clear_and_simple
        )
        self.assertTrue(
            matching,
            "no <rule> in <best_practices> says README.md and doc/ must "
            "stay accurate AND clear AND simple to understand (looked "
            "for 'readme.md and doc/' + 'accurate' + 'clear' + "
            "'simple'). Rule texts: %r" % self._rule_texts(),
        )

    def test_documentation_finalisation_block_survives(self):
        # The <documentation_finalisation> block the source lacks survives,
        # with its two rules, one of which mentions switching to Docs
        # Manager mode.
        block = self.root.find("documentation_finalisation")
        self.assertIsNotNone(
            block, "<documentation_finalisation> block is missing"
        )
        rules = block.findall("rule")
        self.assertEqual(
            len(rules),
            2,
            "expected the <documentation_finalisation> block to keep its 2 "
            "rules, found %d" % len(rules),
        )
        all_text = " ".join(_element_text(r) for r in rules)
        self.assertIn(
            "docs manager mode",
            all_text,
            "the rule mentioning the switch to Docs Manager mode was "
            "altered: %r" % all_text,
        )

    def test_constraints_and_communication_blocks_survive(self):
        # The <constraints> and <communication> blocks survive.
        self.assertIsNotNone(
            self.root.find("constraints"), "<constraints> block is missing"
        )
        self.assertIsNotNone(
            self.root.find("communication"), "<communication> block is missing"
        )

    # -- behaviour 2: the new <step name="page_prose"> -- #

    def _page_prose_step(self):
        step = _step_by_name(self.root, "page_prose")
        self.assertIsNotNone(
            step,
            "no <step name=\"page_prose\"> in <workflow>; steps present: %r"
            % [s.get("name") for s in self.root.findall(".//workflow/step")],
        )
        return step

    def test_page_prose_step_exists_between_usage_docs_and_structure(self):
        # The new step exists and sits between usage_docs and structure in
        # document order.
        step = self._page_prose_step()
        usage_docs = _step_by_name(self.root, "usage_docs")
        structure = _step_by_name(self.root, "structure")
        self.assertIsNotNone(usage_docs, "usage_docs step is missing")
        self.assertIsNotNone(structure, "structure step is missing")
        positions = {
            id(s): i
            for i, s in enumerate(self.root.findall(".//workflow/step"))
        }
        self.assertLess(
            positions[id(usage_docs)],
            positions[id(step)],
            "page_prose must come after usage_docs in document order",
        )
        self.assertLess(
            positions[id(step)],
            positions[id(structure)],
            "page_prose must come before structure in document order",
        )

    def test_page_prose_verify_strips_delivery_vocabulary(self):
        # The step's <verify> strips delivery vocabulary from page prose:
        # slice letters, milestone identifiers, behaviour numbers, pull
        # request numbers, commit hashes and shipped/will-ship sequencing.
        step = self._page_prose_step()
        verify = step.find("verify")
        self.assertIsNotNone(verify, "page_prose step has no <verify>")
        text = _element_text(verify)
        self.assertTrue(
            _verify_strips_delivery_vocabulary(text),
            "<verify> does not strip delivery vocabulary (looked for "
            "'slice' + 'milestone' + 'behaviour' + 'pull request' + "
            "'commit' + 'shipped'/'planned' + 'as it is now'). Verify text: "
            "%r" % text,
        )

    def test_page_prose_verify_says_vocabulary_belongs_in_plan_commit_pr(self):
        # The <verify> says the vocabulary belongs in the plan, commit
        # message and pull request.
        step = self._page_prose_step()
        verify = step.find("verify")
        self.assertIsNotNone(verify, "page_prose step has no <verify>")
        text = _element_text(verify)
        self.assertTrue(
            _verify_says_vocabulary_belongs_in_plan_commit_pr(text),
            "<verify> does not say the vocabulary belongs in the plan, "
            "commit message and pull request (looked for 'plan' + "
            "'commit message' + 'pull request'). Verify text: %r" % text,
        )

    def test_page_prose_self_check_is_scoped_grep_invocation(self):
        # The step's <self_check> carries a grep -rniE invocation whose
        # targets include doc/ and README.md and which EXCLUDES
        # doc/external/; the source's bare "docs/" target and its
        # configuration.md example are not adopted.
        step = self._page_prose_step()
        self_check = step.find("self_check")
        self.assertIsNotNone(
            self_check, "page_prose step has no <self_check>"
        )
        text = _element_text(self_check)
        self.assertTrue(
            _self_check_is_scoped_grep_invocation(text),
            "<self_check> is not a grep -rniE over doc/ excluding "
            "doc/external/ plus README.md (looked for 'grep -rnie' + "
            "'doc/' + 'readme.md' + 'doc/external'; rejected bare 'docs/' "
            "and 'configuration.md'). Self-check text: %r" % text,
        )

    def test_page_prose_allows_capability_limit_forbids_timeline(self):
        # The step carries an <allow> for a plain capability-limit note
        # and a <forbid> for a project timeline.
        step = self._page_prose_step()
        allows = step.findall("allow")
        matching_allow = [a for a in allows if _allow_mentions_capability_limit_or_schedule(_element_text(a))]
        self.assertTrue(
            matching_allow,
            "no <allow> on page_prose is a plain capability-limit / "
            "schedule note (looked for 'capability limit'/'capability-"
            "limit' or 'schedule'). Allow texts: %r"
            % [_element_text(a) for a in allows],
        )
        forbids = step.findall("forbid")
        matching_forbid = [f for f in forbids if _forbid_mentions_timeline_or_milestone(_element_text(f))]
        self.assertTrue(
            matching_forbid,
            "no <forbid> on page_prose bans a project timeline (looked for "
            "'timeline' or 'milestone'). Forbid texts: %r"
            % [_element_text(f) for f in forbids],
        )

    # -- behaviour 2: the three new <rule> elements in <best_practices> -- #

    def _best_practice_rules(self):
        return self.root.findall("best_practices/rule")

    def _rules_matching(self, predicate):
        return [r for r in self._best_practice_rules() if predicate(_element_text(r))]

    def _rule_texts(self):
        return [_element_text(r) for r in self._best_practice_rules()]

    def test_best_practices_grows_from_nine_to_exactly_twelve_rules(self):
        # R3 removed the link-to-the-plan rule: 9 originals + 3 new = 12.
        rules = self._best_practice_rules()
        self.assertEqual(
            len(rules),
            12,
            "expected <best_practices> to hold exactly 12 <rule> elements "
            "(9 original + 3 new), found %d. Rule texts: %r"
            % (len(rules), self._rule_texts()),
        )

    def test_new_rule_bans_delivery_vocabulary_on_pages(self):
        # (a) R2: the page describes the system as it is now and the
        # delivery vocabulary is named (slice, milestone, behaviour, pull
        # request, commit), but the duplicated "belongs in the plan, the
        # commit message, and the pull request, each of which is permanent
        # and searchable" tail clause is dropped — the rule stays short.
        matching = self._rules_matching(_rule_bans_delivery_vocabulary)
        self.assertTrue(
            matching,
            "no <rule> in <best_practices> is the delivery-vocabulary ban "
            "(looked for 'slice' + 'milestone' + 'behaviour' + 'pull "
            "request' + 'commit' + 'as it is now', and rejected the "
            "duplicated homes clause 'permanent and searchable'). Rule "
            "texts: %r" % self._rule_texts(),
        )

    def test_new_rule_says_capability_limit_useful_schedule_not(self):
        # (b) A capability limit is useful; a schedule is not — and R3
        # struck the trailing "the reader who wants the plan gets a link
        # to it" clause, so the rule must not carry both "link" and "plan".
        matching = self._rules_matching(
            _rule_capability_limit_useful_schedule_not
        )
        self.assertTrue(
            matching,
            "no <rule> in <best_practices> says a capability limit is "
            "useful but a schedule is not, without pointing the reader at "
            "a link to the plan (looked for 'capability "
            "limit'/'capability-limit' + 'schedule' + a negation, and "
            "rejected any rule carrying both 'link' and 'plan'). Rule "
            "texts: %r" % self._rule_texts(),
        )

    def test_new_rule_says_internal_design_pages_banned_equally(self):
        # (c) Internal design pages may be technical, but the ban applies
        # to them equally.
        matching = self._rules_matching(
            _rule_internal_design_pages_banned_equally
        )
        self.assertTrue(
            matching,
            "no <rule> in <best_practices> says internal design pages may "
            "be technical but the ban applies equally (looked for "
            "'internal'/'design page' + 'technical' + 'equally'/'still "
            "applies'/'just as'). Rule texts: %r" % self._rule_texts(),
        )

    def test_no_rule_tells_the_writer_to_link_to_the_plan(self):
        # R3 negative guard: no <rule> may carry both "link" and "plan".
        # The plan is not part of the documentation, so no rule may tell
        # the writer to link to it — the guard also reaches the
        # capability-limit rule's trailing "…gets a link to it" clause.
        # "plans/" and "planned" match "plan" as substrings but carry no
        # "link", so those rules are unaffected.
        for rule in self._best_practice_rules():
            text = _element_text(rule)
            self.assertFalse(
                ("link" in text) and ("plan" in text),
                "a <rule> tells the writer to link to the plan, which is "
                "not part of the documentation: %r" % text,
            )

    def test_no_rule_names_the_source_configuration_guide_model_page(self):
        # Negative guard: the source's docs/configuration-guide.md
        # model-page rule is NOT adopted; no <rule> names it.
        for rule in self._best_practice_rules():
            text = _element_text(rule)
            self.assertNotIn(
                "configuration-guide.md",
                text,
                "a <rule> names the source's tool-swap-specific "
                "configuration-guide.md model-page rule, which is not "
                "adopted: %r" % text,
            )

    # -- behaviour 2: the <communication><completion> self-check clause -- #

    def test_completion_reports_the_page_prose_self_check(self):
        # The <completion> text reports the self-check: it names
        # page_prose and that the grep was run and every hit fixed or
        # justified.
        communication = self.root.find("communication")
        self.assertIsNotNone(communication, "<communication> block is missing")
        completion = communication.find("completion")
        self.assertIsNotNone(
            completion, "<communication> has no <completion>"
        )
        text = _element_text(completion)
        self.assertTrue(
            _completion_reports_page_prose_self_check(text),
            "<completion> does not report the page_prose self-check "
            "(looked for 'page_prose' + 'grep' + 'fixed' + 'justified' + "
            "'every hit'). Completion text: %r" % text,
        )


class DocsTemplateTests(DocsManagerPageProseBase):
    """Behaviour 2: the docs-manager TEMPLATE guidelines carry the
    page_prose step."""

    template_path = DOCS_TEMPLATE


class DocsLocalTests(DocsManagerPageProseBase):
    """Behaviour 2: the anvil repo's OWN docs-manager guidelines carry the
    same page_prose step.

    The same assertions run against the local copy, so it cannot drift from
    the template on this point. Only the new content is locked, never
    whole-file equality (byte-identity is guarded separately by
    ``tests/test_rules_mirror.py``).

    ``.roo`` is gitignored, so the local copy is absent on a fresh clone
    (and on CI). ``setUp`` skips every test cleanly in that case; when the
    file is provisioned, the full assertion set runs exactly as written in
    the base class.
    """

    template_path = LOCAL_DOCS

    def setUp(self):
        if not self.template_path.exists():
            self.skipTest(
                "anvil repo local .roo copy not provisioned; nothing to check"
            )
        super().setUp()


if __name__ == "__main__":
    unittest.main()
