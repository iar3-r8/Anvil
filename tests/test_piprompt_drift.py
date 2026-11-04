"""Drift guard for plans/pi-role-prompts.md, behaviour 12.

The six ``.pi/roles/*.md`` documents are **generated** from the tracked
``templates/roo_template/`` sources and **checked in**. This module is the
guard that turns "edited a tracked source but forgot to regenerate the
committed documents" into a red test instead of silent drift, mirroring
``tests/test_rules_mirror.py`` (which byte-compares the tracked
``templates/roo_template/`` rules against the local ``.roo/`` copies).

Behaviour 12, verbatim from the plan:

* Given: the committed ``.pi/roles/*.md``
* When: the documents are regenerated in memory from
  ``templates/roo_template/``
* Then: each committed file is byte-identical to its regenerated form
* Error: drift fails naming the path and both byte counts; a missing
  committed file fails (it is tracked, not a skip)

The regeneration seam is ``anvilkit.pi.piprompt.all_documents()`` ->
``Dict[str, str]``: the six documents keyed by file stem, built from the
already-green ``shared_document()`` and ``role_document(name)``.

This module is expected to arrive RED for exactly two independent
reasons, and no other: ``all_documents`` does not exist yet, and five of
the six committed documents are not checked in yet. Both are the GREEN
deliverable. The test file itself must collect cleanly - the missing
attribute is only touched inside the ``_regenerate`` helper, so each test
fails with its own diagnostic rather than the whole module erroring at
import time.

Edge behaviour, per the plan (and deliberately different from
``test_rules_mirror``): a committed ``.pi/roles/*.md`` is a **tracked
deliverable**, so a missing file **fails** naming the path - it is never
a skip. The byte comparison is also anti-vacuous: each committed file is
asserted non-empty before it is compared, so an empty committed file can
never satisfy an empty regenerated document.
"""

import unittest
from pathlib import Path

from anvilkit.pi import piprompt

REPO_ROOT = Path(__file__).resolve().parent.parent

# The checked-in deliverable the guard protects.
ROLES_ROOT = REPO_ROOT / ".pi" / "roles"

# The six committed documents, as (file stem, human label). The stem is
# both the mapping key of all_documents() and the file name under
# .pi/roles/.
STEMS = (
    ("shared-agents", "shared-agents chain root"),
    ("architect", "architect role"),
    ("coder", "coder role"),
    ("tester", "tester role"),
    ("docs", "docs role"),
    ("tdd-manager", "tdd-manager role"),
)


def _drift_message(stem, committed_size, regenerated_size):
    """Failure text naming the drifted path and the byte count of both
    copies, so a reviewer sees which copy drifted and by how much - the
    same diagnostic style as test_rules_mirror._drift_message."""
    return (
        "regeneration drift: .pi/roles/%s.md is not byte-identical to "
        "its regenerated form from templates/roo_template/ (committed "
        "%d bytes, regenerated %d bytes)"
        % (stem, committed_size, regenerated_size)
    )


def _regenerate():
    """Regenerate the six documents in memory via the pinned seam.

    ``piprompt.all_documents()`` must return the six documents as a
    mapping of stem -> full document text: ``shared-agents`` from
    ``shared_document()`` and the five roles from ``role_document(name)``.
    Called inside each test, so a missing ``all_documents`` is a clean
    per-test AttributeError, never a collection error.
    """
    return piprompt.all_documents()


class PiPromptDriftTestCase(unittest.TestCase):
    """Each committed .pi/roles/*.md is byte-identical to regeneration."""

    # -- behaviour 12: the six committed documents -- #

    def test_shared_agents_committed_file_is_byte_identical_to_regeneration(self):
        self._assert_committed_matches("shared-agents")

    def test_architect_committed_file_is_byte_identical_to_regeneration(self):
        self._assert_committed_matches("architect")

    def test_coder_committed_file_is_byte_identical_to_regeneration(self):
        self._assert_committed_matches("coder")

    def test_tester_committed_file_is_byte_identical_to_regeneration(self):
        self._assert_committed_matches("tester")

    def test_docs_committed_file_is_byte_identical_to_regeneration(self):
        self._assert_committed_matches("docs")

    def test_tdd_manager_committed_file_is_byte_identical_to_regeneration(self):
        self._assert_committed_matches("tdd-manager")

    def _assert_committed_matches(self, stem):
        """Assert .pi/roles/<stem>.md exists, is non-empty, and is
        byte-identical to the regenerated document for that stem."""
        committed = ROLES_ROOT / (stem + ".md")
        self.assertTrue(
            committed.is_file(),
            "committed role file is missing: .pi/roles/%s.md is a tracked "
            "deliverable, not a skip" % stem,
        )
        committed_bytes = committed.read_bytes()
        self.assertGreater(
            len(committed_bytes),
            0,
            "committed role file is empty, so the byte comparison would "
            "be vacuous: .pi/roles/%s.md" % stem,
        )
        documents = _regenerate()
        self.assertIn(
            stem,
            documents,
            "regeneration produced no document for %r: the six stems are "
            "%s" % (stem, ", ".join(s for s, _ in STEMS)),
        )
        regenerated_bytes = documents[stem].encode("utf-8")
        self.assertEqual(
            committed_bytes,
            regenerated_bytes,
            _drift_message(
                stem, len(committed_bytes), len(regenerated_bytes)
            ),
        )

    # -- the regenerated set is exactly the six, no more, no fewer -- #

    def test_regenerated_set_is_exactly_the_six_stems(self):
        documents = _regenerate()
        expected = {stem for stem, _ in STEMS}
        missing = expected - set(documents)
        extra = set(documents) - expected
        self.assertEqual(
            set(documents),
            expected,
            "regenerated set is not exactly the six stems (missing: %s, "
            "extra: %s)" % (sorted(missing), sorted(extra)),
        )

    # -- the guard must be stable, not flaky -- #

    def test_regeneration_is_deterministic(self):
        first = _regenerate()
        second = _regenerate()
        first_bytes = {s: d.encode("utf-8") for s, d in first.items()}
        second_bytes = {s: d.encode("utf-8") for s, d in second.items()}
        differing = sorted(
            s
            for s in set(first_bytes) | set(second_bytes)
            if first_bytes.get(s) != second_bytes.get(s)
        )
        self.assertEqual(
            first_bytes,
            second_bytes,
            "regeneration is not deterministic: calling all_documents() "
            "twice produced different bytes for %s" % differing,
        )

    # -- error behaviour: the drift message is diagnostic, not opaque -- #

    def test_drift_message_names_path_and_both_byte_counts(self):
        message = _drift_message("architect", 17900, 18000)
        for expected in (
            ".pi/roles/architect.md",
            "17900",
            "18000",
        ):
            self.assertIn(
                expected,
                message,
                "drift message does not name %r: %r" % (expected, message),
            )


if __name__ == "__main__":
    unittest.main()
