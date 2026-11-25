"""Tests for anvilkit.pi.pilaunch — launch-time role document generation.

Written before the implementation (TDD, ``plans/pi-phase12-launch-gen.md``).
This file covers the generate-writes-seven-documents behaviour: a target
repo directory, a profile root and a profile name in; afterwards
``<repo>/.pi/roles/`` holds exactly seven files — the six
``piprompt.all_documents()`` stems plus ``project.md`` — with the six
generic documents byte-identical to what ``piprompt.all_documents()``
produces, ``project.md`` equal to ``piproject.project_document(record)``
for the stored record, and the result passing
``smoke.check_role_prompt``.

``anvilkit.pi.pilaunch`` is imported inside the helper rather than at
collection time, so the file collects cleanly while the module is
unimplemented and every test fails with the ``ModuleNotFoundError``
naming the missing module.
"""

import importlib
import tempfile
import unittest
from pathlib import Path
from typing import Dict

from anvilkit import smoke
from anvilkit.pi import piprofile
from anvilkit.pi import piproject
from anvilkit.pi import piprompt


# The profile name the tests address in the store.
PROFILE_NAME = "gearworks"

# The tests own these record values; they are fixed so the expected
# documents can be recomputed by the test from the same record.
OWNER = "octo-org"
REPO = "gearworks"
BASE = "main"
PROJECT_BLOCK = {
    "name": "Gearworks Tool",
    "structure": (
        "anvilkit/ holds one module per concern; templates/ holds scaffolding"
    ),
    "configuration": "config.yaml is read-only; secrets live in .env",
}


def _load_module():
    """Return the pilaunch module, importing it inside the call."""
    return importlib.import_module("anvilkit.pi.pilaunch")


def _save_profile(root: Path, target: Path) -> None:
    """Save a test-owned profile pointing at ``target`` under ``PROFILE_NAME``."""
    piprofile.save_profile(
        root=root,
        name=PROFILE_NAME,
        path=target,
        owner=OWNER,
        repo=REPO,
        base=BASE,
        project=dict(PROJECT_BLOCK),
    )


class TestGenerateWritesSevenDocuments(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.repo = base / "repo"
        self.repo.mkdir()
        self.root = base / ".anvil"
        self.root.mkdir()
        _save_profile(self.root, self.repo)
        self.roles_dir = self.repo / ".pi" / "roles"

    def _generate(self) -> Dict[str, str]:
        """Run pilaunch.generate over the fresh repo and return its result."""
        pilaunch = _load_module()
        return pilaunch.generate(str(self.repo), self.root, PROFILE_NAME)

    def test_generate_writes_exactly_seven_role_files(self):
        self._generate()

        entries = sorted(p.name for p in self.roles_dir.iterdir())

        self.assertEqual(len(entries), 7, "the roles directory holds %r" % entries)
        for entry in entries:
            self.assertTrue(
                (self.roles_dir / entry).is_file(),
                "%r is not a file" % entry,
            )

    def test_generate_file_names_match_six_stems_plus_project(self):
        self._generate()

        expected = {stem + ".md" for stem in piprompt.all_documents()}
        expected.add("project.md")
        entries = {p.name for p in self.roles_dir.iterdir()}

        self.assertEqual(entries, expected)

    def test_generate_generic_documents_match_piprompt_byte_for_byte(self):
        self._generate()

        for stem, document in piprompt.all_documents().items():
            with self.subTest(stem=stem):
                text = (self.roles_dir / (stem + ".md")).read_text(encoding="utf-8")
                self.assertEqual(text, document)

    def test_generate_project_md_matches_project_document_for_record(self):
        self._generate()

        record = piprofile.load_profile(self.root, PROFILE_NAME)
        expected = piproject.project_document(record)
        text = (self.roles_dir / "project.md").read_text(encoding="utf-8")

        self.assertEqual(text, expected)

    def test_generate_result_passes_smoke_role_prompt_check(self):
        self._generate()

        result = smoke.check_role_prompt(str(self.repo))

        self.assertEqual(
            result.ok,
            smoke.STATE_OK,
            "layer %r failed: %s" % (result.name, result.detail),
        )


if __name__ == "__main__":
    unittest.main()
