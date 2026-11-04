"""Tests for the token-budget report of ``anvilkit.pi.piprompt``.

``plans/pi-role-prompts.md``, behaviour 16
(budget-check-reports-never-truncates): given each role's layered total
(shared body + role body, the two flags Pi concatenates) and the window
262144 from behaviour 2, when ``piprompt.budget_report(documents, window)``
is called, then a record per role — name, estimate, window, ``within``
flag — and a test fails when any role is over, naming the role, its
estimate and the window. Error: no code path shortens, elides or
summarises a body; the test asserts each written body still contains its
source's final clause, so an over-budget role is reported red rather than
half-delivered (a half-delivered rule set is worse than an absent one,
because it looks like it worked).

Pinned seam::

    budget_report(documents: Dict[str, str], window: int) -> List[Dict[str, Any]]

Layered-total pin (from the issue's pinned-seam note): the two
``--append-system-prompt`` FLAGS carry the two FILES, so the layered
total for a role is the FULL document text of both files as committed —
frontmatter and all (the frontmatter is part of the file bytes Pi
appends):

    estimate = estimate_tokens(shared_full_document + role_full_document)

for the five roles, and ``estimate_tokens(shared_full_document)`` for
``shared-agents`` itself (it is the chain root: nothing is prepended to
it). Each record carries ``name`` (str), ``estimate`` (int), ``window``
(int) and ``within`` (bool, ``estimate <= window``). The report is
records only — it never returns or writes modified document text.

Window pin: ``config.read_models(REPO_ROOT / "config.yaml",
strict_context_window=True).coder_context_window`` — behaviour 2's
strict seam; the number is read, never defaulted.

RED expectation (this commit): ``budget_report`` does not exist in
``anvilkit.pi.piprompt`` yet, so every test in this file fails with
``AttributeError: module 'anvilkit.pi.piprompt' has no attribute
'budget_report'``: a clean per-test AttributeError is the right red
reason for a missing function (no collection, import or syntax error —
both modules import fine, the seam is simply absent). The final-clause
containment of test 4 is already true on the committed documents
(behaviours 5 and 12 are green), so that test is expected to turn green
the moment the seam lands; its red on arrival is the same AttributeError.
"""

import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import config  # noqa: E402
from anvilkit.pi import piprompt  # noqa: E402

TEMPLATE_ROOT = REPO_ROOT / "templates" / "roo_template"
ROLES_DIR = REPO_ROOT / ".pi" / "roles"

# The six stems ``all_documents`` returns, and the only keys a budget
# report over the real documents may carry.
STEMS = (
    "shared-agents",
    "architect",
    "coder",
    "tester",
    "docs",
    "tdd-manager",
)


def _normalise(text):
    # type: (str) -> str
    """Collapse whitespace runs so containment is checked on words, not
    on layout (same normalisation as
    ``tests/test_piprompt_lossless.py``)."""
    return re.sub(r"\s+", " ", text).strip()


def _layered_total(documents, stem):
    # type: (Dict[str, str], str) -> str
    """The layered total for one stem, pinned on the FULL document text
    of the two files Pi's two ``--append-system-prompt`` flags append:
    the shared document's text plus the role document's text (frontmatter
    included — it is part of the file bytes). ``shared-agents`` is the
    chain root: its layered total is its own document only.

    Recomputed independently here in the test, so a report whose estimate
    drifts from the pinned estimator of behaviour 15 fails."""
    if stem == "shared-agents":
        return documents["shared-agents"]
    return documents["shared-agents"] + documents[stem]


def _coder_window():
    # type: () -> int
    """The coder model's context window, READ from the repository
    ``config.yaml`` through behaviour 2's strict seam — never the
    262144 default of a lenient read."""
    topology = config.read_models(
        REPO_ROOT / "config.yaml", strict_context_window=True
    )
    return topology.coder_context_window


def _final_clause_xml(rel):
    # type: (str) -> str
    """The last non-empty ``itertext()`` node of the tracked XML source
    at *rel*, whitespace-normalised (the extraction
    ``tests/test_piprompt_lossless.py`` pins). A source that yields no
    text node fails naming the path — the absence check below must not
    run against a vacuous clause."""
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
    nodes = [_normalise(part) for part in root.itertext()]
    nodes = [node for node in nodes if node]
    if not nodes:
        raise AssertionError(
            "tracked rule source yields no text node: "
            "templates/roo_template/%s" % rel
        )
    return nodes[-1]


def _final_clause_markdown(path):
    # type: (Path) -> str
    """The last non-empty line of a tracked markdown source,
    whitespace-normalised. Used for the coder one-liner (its body is the
    literal, so its final clause is itself) and for
    ``rules/coding-guidelines.md`` — the fixed-order last source of the
    shared document, whose last content line is therefore the shared
    document's final clause."""
    if not path.is_file():
        raise AssertionError("tracked source is missing: %s" % path)
    lines = [
        _normalise(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    lines = [line for line in lines if line]
    if not lines:
        raise AssertionError("tracked source has no content lines: %s" % path)
    return lines[-1]


def _final_clause_for(stem):
    # type: (str) -> str
    """The final clause of the tracked source for one stem — the end of
    the body a half-delivered document would drop:

    * the four XML roles: the last non-empty ``itertext()`` node of
      their tracked source;
    * ``coder``: the one-liner itself (behaviour 10 — its source IS the
      literal, so its final clause is the one-liner, normalised);
    * ``shared-agents``: the last content line of
      ``rules/coding-guidelines.md``, the fixed-order last of the three
      shared sources, so it is the shared document's final clause.
    """
    if stem == "coder":
        return _normalise(piprompt.source_for("coder"))
    if stem == "shared-agents":
        return _final_clause_markdown(
            TEMPLATE_ROOT / "rules" / "coding-guidelines.md"
        )
    return _final_clause_xml(
        piprompt.source_for(stem)
    )


class BudgetReportRealMeasurementTest(unittest.TestCase):
    """The real measurement (the DoD item "token size of each prompt
    measured against the local model's context window"): the six
    regenerated documents against the coder window READ from the
    repository config.yaml, never the default."""

    def test_budget_report_real_documents_all_roles_within_coder_window(self) -> None:
        # Arrange: the window from behaviour 2's strict seam, and the six
        # documents regenerated in memory.
        window = _coder_window()
        documents = piprompt.all_documents()

        # Act.
        records = piprompt.budget_report(documents, window)

        # Assert: one record per stem — the six, no more, no fewer.
        self.assertEqual(len(records), len(STEMS))
        names = [record["name"] for record in records]
        self.assertEqual(sorted(names), sorted(STEMS))
        for record in records:
            self.assertIsInstance(record["name"], str)
            self.assertIsInstance(record["estimate"], int)
            self.assertIsInstance(record["window"], int)
            self.assertIsInstance(record["within"], bool)
            self.assertEqual(record["window"], window)

        # A role over its window fails naming the role, its estimate and
        # the window — an over-budget prompt is a finding, not a pass.
        over = [record for record in records if not record["within"]]
        if over:
            detail = "; ".join(
                "role %r estimates %d tokens against window %d"
                % (r["name"], r["estimate"], r["window"])
                for r in over
            )
            self.fail("role prompt(s) exceed the coder context window: " + detail)


class BudgetReportOverBudgetTest(unittest.TestCase):
    """Over-budget is REPORTED, not raised, not truncated: a synthetic
    documents dict with one huge role and a small window yields a record
    with ``within`` False for the over-budget role (True for the
    others), no exception, and the input dict untouched — byte-identical
    before and after. A budget check that trims to fit would be the
    half-delivered rule set the issue forbids."""

    def _synthetic_documents(self):
        # type: () -> Dict[str, str]
        return {
            "shared-agents": (
                "---\ndescription: A shared document.\n---\n"
                "Small shared body.\n"
            ),
            "giant-role": "x" * 1_000_000,
            "tiny-role": "tiny body\n",
        }

    def test_budget_report_over_budget_role_reports_within_false_and_others_true(
        self,
    ) -> None:
        # Arrange: a fake role far over a small window, beside two that
        # fit.
        documents = self._synthetic_documents()
        window = 10_000

        # Act: the call must complete without raising — reporting is the
        # contract, an exception is not.
        records = piprompt.budget_report(documents, window)

        # Assert: one record per key, and the over-budget role is the
        # only one reported out of budget.
        self.assertEqual(len(records), len(documents))
        by_name = {record["name"]: record for record in records}
        self.assertEqual(set(by_name), set(documents))
        self.assertFalse(
            by_name["giant-role"]["within"],
            "giant-role's layered total of 1,000,000+ bytes against a "
            "%d-token window must be reported over budget" % window,
        )
        self.assertTrue(by_name["tiny-role"]["within"])
        self.assertTrue(by_name["shared-agents"]["within"])

    def test_budget_report_does_not_truncate_or_alter_input_documents(self) -> None:
        # Arrange: capture the input byte for byte.
        documents = self._synthetic_documents()
        snapshot = {name: text for name, text in documents.items()}
        window = 10_000

        # Act.
        piprompt.budget_report(documents, window)

        # Assert: the input dict is byte-identical — no shortening, no
        # elision, no reordering, no key dropped.
        self.assertEqual(set(documents), set(snapshot))
        for name in snapshot:
            self.assertEqual(
                documents[name],
                snapshot[name],
                "budget_report altered the input document %r: a budget "
                "check reports, it never edits" % name,
            )


class BudgetReportRecordShapeTest(unittest.TestCase):
    """Records are complete and well-typed: for the real documents, every
    record's estimate equals ``estimate_tokens`` recomputed independently
    in the test on the pinned layered total (the report cannot drift from
    the pinned estimator), its window equals the argument, and its
    ``within`` equals ``estimate <= window``. The report is records only
    — each carries exactly the four pinned keys and never modified
    document text."""

    def test_budget_report_records_match_pinned_estimator_window_and_within(self) -> None:
        # Arrange.
        window = _coder_window()
        documents = piprompt.all_documents()

        # Act.
        records = piprompt.budget_report(documents, window)

        # Assert: one record per stem, each a four-key record whose
        # values are re-derivable from the pinned estimator.
        by_name = {record["name"]: record for record in records}
        self.assertEqual(set(by_name), set(STEMS))
        for stem in STEMS:
            with self.subTest(stem=stem):
                record = by_name[stem]
                self.assertEqual(
                    set(record),
                    {"name", "estimate", "window", "within"},
                    "a record carries exactly name/estimate/window/within "
                    "— it is records only, never modified document text",
                )
                expected = piprompt.estimate_tokens(_layered_total(documents, stem))
                self.assertEqual(
                    record["estimate"],
                    expected,
                    "estimate for %r must equal estimate_tokens of the "
                    "layered total (shared document + role document, full "
                    "text); a drift from the pinned estimator makes the "
                    "budget check untrustworthy" % stem,
                )
                self.assertNotIsInstance(record["estimate"], bool)
                self.assertEqual(
                    record["window"], window, "window must equal the argument"
                )
                self.assertEqual(
                    record["within"],
                    record["estimate"] <= window,
                    "within must be exactly (estimate <= window)",
                )
                self.assertIsInstance(record["within"], bool)


class BudgetReportNeverTruncatesTest(unittest.TestCase):
    """No code path shortens a body: after calling ``budget_report`` on
    the real documents, each committed ``.pi/roles/<stem>.md`` still
    contains its source's FINAL clause (whitespace-normalised). This is
    the mechanical form of "an over-budget role is reported red rather
    than half-delivered": nothing the budget check touches may elide the
    end of a body — a half-delivered rule set looks like it worked, so
    the last clause is the one that must survive."""

    def test_committed_role_documents_still_contain_source_final_clause(self) -> None:
        # Arrange: the final clause per stem, extracted from the tracked
        # sources.
        clauses = {stem: _final_clause_for(stem) for stem in STEMS}

        # Act: run the budget check on the real documents.
        window = _coder_window()
        documents = piprompt.all_documents()
        piprompt.budget_report(documents, window)

        # Assert: the end of every committed body survives.
        for stem in STEMS:
            with self.subTest(stem=stem):
                path = ROLES_DIR / (stem + ".md")
                self.assertTrue(
                    path.is_file(),
                    "committed role document is missing: .pi/roles/%s.md "
                    "(it is tracked, not a skip)" % stem,
                )
                committed = _normalise(path.read_text(encoding="utf-8"))
                self.assertIn(
                    clauses[stem],
                    committed,
                    "the final clause of the %r source is absent from "
                    "committed .pi/roles/%s.md: a body was shortened or "
                    "elided, and a half-delivered rule set looks like it "
                    "worked — the clause is %r"
                    % (stem, stem, clauses[stem][:60]),
                )


class BudgetReportDeterminismTest(unittest.TestCase):
    """The report is deterministic: two calls on equal inputs produce
    equal records, so a CI re-run cannot flip a role between within and
    over budget without a document or a config change."""

    def test_budget_report_same_inputs_produce_equal_records(self) -> None:
        # Arrange: the same documents and window, as two equal copies.
        window = _coder_window()
        documents_a = piprompt.all_documents()
        documents_b = piprompt.all_documents()
        self.assertEqual(documents_a, documents_b)

        # Act: two independent calls on equal inputs.
        records_a = piprompt.budget_report(dict(documents_a), window)
        records_b = piprompt.budget_report(dict(documents_b), window)

        # Assert: equal records, key for key.
        self.assertEqual(records_a, records_b)


if __name__ == "__main__":
    unittest.main()
