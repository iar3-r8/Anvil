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
import re
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

# The pinned wording an absent field renders on its labelled line.
NOT_RECORDED = "not recorded"


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


def _empty_block_record():
    """Return a record whose ``project`` block is entirely empty."""
    record = _record()
    record["project"] = {}
    return record


def _missing_structure_record():
    """Return a record whose ``project`` block has no ``structure`` key."""
    record = _record()
    del record["project"]["structure"]
    return record


def _none_owner_record():
    """Return a record carrying ``None`` for ``owner``."""
    record = _record()
    record["owner"] = None
    return record


def _none_configuration_record():
    """Return a record whose ``project`` block carries ``None`` for ``configuration``."""
    record = _record()
    record["project"]["configuration"] = None
    return record


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


class ProjectDocumentAbsentFieldsTestCase(unittest.TestCase):
    """Absent project facts render the pinned absence wording, never a placeholder.

    An absent field — a missing block key, an empty block, or a ``None``
    value — renders the pinned line ``not recorded`` on its labelled line.
    ``piproject.project_document`` never raises on an absent field; the
    empty block is the common case ``piprofileflow.record_profile`` writes
    today. No ``<...>`` placeholder the shared rule sources carry may
    survive into the rendered document.
    """

    def _assert_no_placeholder(self, document):
        match = re.search(r"<[^>]*>", document)
        if match is not None:
            self.fail(
                "a <...> placeholder survives into the rendered document: %r"
                % match.group(0)
            )

    def test_project_document_empty_block_renders_absent_lines_for_block_fields(
        self,
    ):
        document = _document(_empty_block_record())
        self.assertIsInstance(
            document,
            str,
            "project_document must return the project.md text for an "
            "empty project block, got %s" % type(document).__name__,
        )
        absent = _labelled_lines(document, NOT_RECORDED)
        self.assertEqual(
            len(absent),
            3,
            "an empty project block must render three absent labelled "
            "lines (%r); found %r" % (NOT_RECORDED, absent),
        )
        for value in (OWNER, REPO):
            self.assertTrue(
                _labelled_lines(document, value),
                "top-level value %r must still render for an empty "
                "project block" % value,
            )
        self._assert_no_placeholder(document)

    def test_project_document_missing_block_key_renders_absent_line_for_that_field(
        self,
    ):
        document = _document(_missing_structure_record())
        absent = _labelled_lines(document, NOT_RECORDED)
        self.assertEqual(
            len(absent),
            1,
            "a block missing one key must render exactly one absent "
            "labelled line (%r); found %r" % (NOT_RECORDED, absent),
        )
        for value in (OWNER, REPO, PROJECT_NAME, PROJECT_CONFIGURATION):
            self.assertTrue(
                _labelled_lines(document, value),
                "present value %r must still render when one block key "
                "is missing" % value,
            )
        self._assert_no_placeholder(document)

    def test_project_document_none_owner_renders_absent_line_for_owner(self):
        document = _document(_none_owner_record())
        absent = _labelled_lines(document, NOT_RECORDED)
        self.assertEqual(
            len(absent),
            1,
            "a record carrying None for owner must render exactly one "
            "absent labelled line (%r); found %r" % (NOT_RECORDED, absent),
        )
        for value in (
            REPO,
            PROJECT_NAME,
            PROJECT_STRUCTURE,
            PROJECT_CONFIGURATION,
        ):
            self.assertTrue(
                _labelled_lines(document, value),
                "present value %r must still render when owner is None"
                % value,
            )
        self._assert_no_placeholder(document)

    def test_project_document_none_block_value_renders_absent_line_for_that_field(
        self,
    ):
        document = _document(_none_configuration_record())
        absent = _labelled_lines(document, NOT_RECORDED)
        self.assertEqual(
            len(absent),
            1,
            "a block value set to None must render exactly one absent "
            "labelled line (%r); found %r" % (NOT_RECORDED, absent),
        )
        for value in (OWNER, REPO, PROJECT_NAME, PROJECT_STRUCTURE):
            self.assertTrue(
                _labelled_lines(document, value),
                "present value %r must still render when one block "
                "value is None" % value,
            )
        self._assert_no_placeholder(document)

    def test_project_document_none_owner_and_none_block_value_render_each_absent_line(
        self,
    ):
        record = _none_owner_record()
        record["project"]["structure"] = None
        document = _document(record)
        absent = _labelled_lines(document, NOT_RECORDED)
        self.assertEqual(
            len(absent),
            2,
            "a None owner plus one None block value must render exactly "
            "two absent labelled lines (%r); found %r" % (NOT_RECORDED, absent),
        )
        for value in (REPO, PROJECT_NAME, PROJECT_CONFIGURATION):
            self.assertTrue(
                _labelled_lines(document, value),
                "present value %r must still render alongside None "
                "values" % value,
            )
        self._assert_no_placeholder(document)


class ProjectDocumentRejectsNonRecordTestCase(unittest.TestCase):
    """A non-mapping record, or a record whose ``project`` value is not a mapping, is refused before any text is built.

    ``piproject.project_document`` raises ``ProjectError`` naming the
    offending field (``record`` or ``project``) and its actual type, so
    an operator sees their mistake, not a bare traceback. The refusal is
    pinned against acceptance: a record that IS a mapping carrying a
    mapping ``project`` block still returns the rendered text.
    """

    def _assert_rejected(self, record, field, type_name):
        module = importlib.import_module("anvilkit.pi.piproject")
        with self.assertRaises(module.ProjectError) as context:
            _document(record)
        message = str(context.exception)
        self.assertIn(
            field,
            message,
            "the ProjectError message must name the offending field %r; "
            "got %r" % (field, message),
        )
        self.assertIn(
            type_name,
            message,
            "the ProjectError message must name the actual type %r of "
            "field %r; got %r" % (type_name, field, message),
        )

    def test_project_document_none_record_raises_project_error_naming_record(
        self,
    ):
        self._assert_rejected(None, "record", "NoneType")

    def test_project_document_string_record_raises_project_error_naming_record(
        self,
    ):
        self._assert_rejected("gearworks", "record", "str")

    def test_project_document_list_record_raises_project_error_naming_record(
        self,
    ):
        self._assert_rejected(["gearworks"], "record", "list")

    def test_project_document_string_project_raises_project_error_naming_project(
        self,
    ):
        record = _record()
        record["project"] = "a single sentence of structure notes"
        self._assert_rejected(record, "project", "str")

    def test_project_document_none_project_raises_project_error_naming_project(
        self,
    ):
        record = _record()
        record["project"] = None
        self._assert_rejected(record, "project", "NoneType")

    def test_project_document_list_project_raises_project_error_naming_project(
        self,
    ):
        record = _record()
        record["project"] = ["name", "structure", "configuration"]
        self._assert_rejected(record, "project", "list")

    def test_project_document_mapping_record_with_mapping_project_is_accepted(
        self,
    ):
        document = _document(_record())
        self.assertIsInstance(
            document,
            str,
            "a mapping record with a mapping project block must return "
            "the project.md text, got %s" % type(document).__name__,
        )
        self.assertTrue(
            document.strip(),
            "a mapping record with a mapping project block must not be "
            "rejected; the document came back empty",
        )
