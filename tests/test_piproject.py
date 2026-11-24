"""Tests for anvilkit.pi.piproject — the project.md document.

Written before the implementation (TDD, ``plans/pi-phase12-launch-gen.md``).
This file covers the project-document-from-record behaviour: the rendered
document carries the record's five project facts — ``owner``, ``repo`` and
the ``project`` block's ``name``, ``structure`` and ``configuration`` —
each on its own labelled line, with the owner and repository values
present in the text where the shared rule sources leave the
``<Repository name>`` / ``<Github user>`` placeholders.

The record is built as a plain dict matching the shape
``piprofile.load_profile`` returns (top-level ``path``, ``owner``, ``repo``,
``base``, ``token_env`` plus a ``project`` block); the store is never
imported. ``anvilkit.pi.piproject`` is imported inside the helper rather
than at collection time, so the file collects cleanly while the module is
unimplemented and every test fails with the ``ModuleNotFoundError`` naming
the missing module.
"""

import importlib
import unittest


# The tests own these values; they are pairwise non-substring so the
# distinct-line check cannot be satisfied by accident.
OWNER = "octo-org"
REPO = "gearworks"
PROJECT_NAME = "Gearworks Tool"
PROJECT_STRUCTURE = (
    "anvilkit/ holds one module per concern; templates/ holds scaffolding"
)
PROJECT_CONFIGURATION = "config.yaml is read-only; secrets live in .env"


def _record():
    """Return a full profile record in the shape load_profile returns."""
    return {
        "path": "/home/dev/workspaces/gearworks",
        "owner": OWNER,
        "repo": REPO,
        "base": "main",
        "token_env": "GITHUB_TOKEN_GEARWORKS",
        "project": {
            "name": PROJECT_NAME,
            "structure": PROJECT_STRUCTURE,
            "configuration": PROJECT_CONFIGURATION,
        },
    }


def _document(record):
    """Return ``piproject.project_document(record)`` for the given record."""
    piproject = importlib.import_module("anvilkit.pi.piproject")
    return piproject.project_document(record)


def _labelled_lines(document, value):
    """Return the document's lines that carry ``value`` under a label.

    A labelled line ends with ``value`` and carries non-whitespace text
    (the label) before it, so the fact reads as ``label: value`` or any
    other labelling that puts the value at the end of its own line.
    """
    labelled = []
    for line in document.splitlines():
        stripped = line.strip()
        if stripped.endswith(value) and stripped != value:
            labelled.append(stripped)
    return labelled


class ProjectDocumentFromRecordTestCase(unittest.TestCase):
    """The rendered document carries the record's five project facts."""

    def _document(self):
        return _document(_record())

    def test_project_document_full_record_returns_text_document(self):
        document = self._document()
        self.assertIsInstance(
            document,
            str,
            "project_document must return the project.md text, "
            "got %s" % type(document).__name__,
        )
        self.assertTrue(
            document.strip(),
            "the rendered document is empty for a full record",
        )

    def test_project_document_full_record_owner_on_labelled_line(self):
        document = self._document()
        labelled = _labelled_lines(document, OWNER)
        self.assertTrue(
            labelled,
            "owner %r must appear on its own labelled line in the "
            "rendered document; no labelled line found" % OWNER,
        )

    def test_project_document_full_record_repo_on_labelled_line(self):
        document = self._document()
        labelled = _labelled_lines(document, REPO)
        self.assertTrue(
            labelled,
            "repo %r must appear on its own labelled line in the "
            "rendered document; no labelled line found" % REPO,
        )

    def test_project_document_full_record_project_name_on_labelled_line(self):
        document = self._document()
        labelled = _labelled_lines(document, PROJECT_NAME)
        self.assertTrue(
            labelled,
            "project name %r must appear on its own labelled line in "
            "the rendered document; no labelled line found" % PROJECT_NAME,
        )

    def test_project_document_full_record_project_structure_on_labelled_line(self):
        document = self._document()
        labelled = _labelled_lines(document, PROJECT_STRUCTURE)
        self.assertTrue(
            labelled,
            "project structure %r must appear on its own labelled line "
            "in the rendered document; no labelled line found"
            % PROJECT_STRUCTURE,
        )

    def test_project_document_full_record_project_configuration_on_labelled_line(
        self,
    ):
        document = self._document()
        labelled = _labelled_lines(document, PROJECT_CONFIGURATION)
        self.assertTrue(
            labelled,
            "project configuration %r must appear on its own labelled "
            "line in the rendered document; no labelled line found"
            % PROJECT_CONFIGURATION,
        )

    def test_project_document_full_record_values_on_distinct_lines(self):
        document = self._document()
        values = (
            OWNER,
            REPO,
            PROJECT_NAME,
            PROJECT_STRUCTURE,
            PROJECT_CONFIGURATION,
        )
        for line in document.splitlines():
            present = [value for value in values if value in line]
            self.assertLessEqual(
                len(present),
                1,
                "one line carries several project facts: %r" % line,
            )
