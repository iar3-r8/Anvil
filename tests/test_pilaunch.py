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

It also covers re-generation: a second ``generate`` over a repo whose
``coder.md`` was hand-edited replaces the edit with the generated text and
leaves no backup anywhere under ``<repo>/.pi/``, and a third call leaves
every file byte-identical to the second call's result.

It also covers a changed documents source: two distinct target directories,
each generated once from the same profile root, with the
``piprompt.all_documents`` seam's output altered after the first
generation; the second directory's documents carry the change with no
re-provisioning step between, and the first directory stays byte-identical
to its first-generation result.

``anvilkit.pi.pilaunch`` is imported inside the helper rather than at
collection time, so the file collects cleanly while the module is
unimplemented and every test fails with the ``ModuleNotFoundError``
naming the missing module.
"""

import importlib
import tempfile
from unittest import mock
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


class TestGenerateIsIdempotentAndOverwriting(unittest.TestCase):
    """Re-generation overwrites a hand edit with no backup, and a third
    call changes nothing on disk.

    A hand edit is a build artifact: a second ``generate`` replaces it
    without warning and leaves no ``.bak`` or renamed copy anywhere under
    ``<repo>/.pi/``; a third call leaves every one of the seven files
    byte-identical to the second call's result.
    """

    # The hand edit the tests write over the generated coder document.
    HAND_EDIT = (
        "# Coder\n"
        "\n"
        "Hand-edited by an operator after generation.\n"
    )

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.repo = base / "repo"
        self.repo.mkdir()
        self.root = base / ".anvil"
        self.root.mkdir()
        _save_profile(self.root, self.repo)
        self.pi_dir = self.repo / ".pi"
        self.roles_dir = self.pi_dir / "roles"

    def _generate(self) -> Dict[str, str]:
        """Run pilaunch.generate over the repo and return its result."""
        pilaunch = _load_module()
        return pilaunch.generate(str(self.repo), self.root, PROFILE_NAME)

    def _hand_edit_coder(self) -> None:
        """Overwrite the generated coder.md with the test-owned HAND_EDIT."""
        coder = self.roles_dir / "coder.md"
        original = coder.read_text(encoding="utf-8")
        self.assertNotEqual(
            original,
            self.HAND_EDIT,
            "the hand edit must differ from the generated text",
        )
        coder.write_text(self.HAND_EDIT, encoding="utf-8")

    def _iter_dot_pi_files(self):
        """Yield every file under <repo>/.pi/, recursively."""
        for path in sorted(self.pi_dir.rglob("*")):
            if path.is_file():
                yield path

    def test_generate_hand_edited_coder_replaced_by_generated_text(self):
        self._generate()
        self._hand_edit_coder()

        self._generate()

        text = (self.roles_dir / "coder.md").read_text(encoding="utf-8")

        self.assertEqual(text, piprompt.all_documents()["coder"])

    def test_generate_hand_edited_coder_leaves_no_backup_under_dot_pi(self):
        self._generate()
        self._hand_edit_coder()

        self._generate()

        for path in self._iter_dot_pi_files():
            with self.subTest(path=str(path)):
                self.assertFalse(
                    path.name.endswith(".bak")
                    or path.name.endswith(".orig")
                    or path.name.endswith("~"),
                    "a backup file was left behind: %r" % path.name,
                )
                self.assertNotEqual(
                    path.read_text(encoding="utf-8"),
                    self.HAND_EDIT,
                    "the hand edit survives at %r" % str(path),
                )

    def test_generate_third_call_byte_identical_to_second_call(self):
        self._generate()
        second = self._generate()
        third = self._generate()

        self.assertEqual(third, second, "the third call resolved different documents")
        for stem, text in second.items():
            with self.subTest(stem=stem):
                on_disk = (self.roles_dir / (stem + ".md")).read_text(encoding="utf-8")
                self.assertEqual(on_disk, text)


class TestGenerateReachesSecondRepo(unittest.TestCase):
    """A changed documents source reaches a second repo's next generation.

    Two distinct target directories are each generated once from the same
    profile root, through two profiles that share it. After the first
    generation the ``piprompt.all_documents`` seam is patched, as seen
    through the ``anvilkit.pi.pilaunch`` namespace, to return one altered
    document; the patch is scoped to the mock context manager so no other
    test sees the changed documents. When ``generate`` is called again on
    the second directory only, that directory's documents carry the change
    with no re-provisioning step between, and the first directory's files
    stay byte-identical to its first-generation result.
    """

    # The rule change the tests apply to the documents source after the
    # first generation; it must differ from the generated coder text.
    CHANGED_CODER = (
        "# Coder\n"
        "\n"
        "Rule text updated in Anvil's templates after the first run.\n"
    )

    NAME_A = "gearworks-a"
    NAME_B = "gearworks-b"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.repo_a = base / "repo-a"
        self.repo_a.mkdir()
        self.repo_b = base / "repo-b"
        self.repo_b.mkdir()
        self.root = base / ".anvil"
        self.root.mkdir()
        self._save(self.repo_a, self.NAME_A)
        self._save(self.repo_b, self.NAME_B)
        self.roles_a = self.repo_a / ".pi" / "roles"
        self.roles_b = self.repo_b / ".pi" / "roles"

    def _save(self, target: Path, name: str) -> None:
        """Record a profile under ``name`` pointing at ``target``."""
        piprofile.save_profile(
            root=self.root,
            name=name,
            path=target,
            owner=OWNER,
            repo=REPO,
            base=BASE,
            project=dict(PROJECT_BLOCK),
        )

    def _generate(self, repo: Path, name: str) -> Dict[str, str]:
        """Run pilaunch.generate over ``repo`` and return its result."""
        pilaunch = _load_module()
        return pilaunch.generate(str(repo), self.root, name)

    def _changed_documents(self) -> Dict[str, str]:
        """The documents source after the rule change: one altered document."""
        changed = dict(piprompt.all_documents())
        changed["coder"] = self.CHANGED_CODER
        return changed

    def _roles_bytes(self, roles_dir: Path) -> Dict[str, bytes]:
        """Snapshot every file under ``roles_dir`` by name and raw bytes."""
        return {p.name: p.read_bytes() for p in sorted(roles_dir.iterdir())}

    def _assert_roles_unchanged(
        self,
        before: Dict[str, bytes],
        after: Dict[str, bytes],
    ) -> None:
        self.assertEqual(
            set(after),
            set(before),
            "the roles directory gained or lost files: %r" % sorted(after),
        )
        for name, data in before.items():
            with self.subTest(file=name):
                self.assertEqual(after[name], data, "%r changed" % name)

    def test_generate_first_generation_before_source_change_writes_original_coder(self):
        original = piprompt.all_documents()["coder"]
        self.assertNotEqual(
            original,
            self.CHANGED_CODER,
            "the rule change must alter the coder text",
        )

        self._generate(self.repo_a, self.NAME_A)

        text = (self.roles_a / "coder.md").read_text(encoding="utf-8")

        self.assertEqual(text, original)

    def test_generate_second_repo_after_source_change_carries_changed_text(self):
        self._generate(self.repo_a, self.NAME_A)
        pilaunch = _load_module()
        changed = self._changed_documents()

        with mock.patch.object(
            pilaunch.piprompt, "all_documents", return_value=changed
        ):
            self._generate(self.repo_b, self.NAME_B)

        for stem, document in changed.items():
            with self.subTest(stem=stem):
                text = (self.roles_b / (stem + ".md")).read_text(encoding="utf-8")
                self.assertEqual(text, document)
        self.assertTrue(
            (self.roles_b / "project.md").is_file(),
            "project.md is missing from the second repo's roles directory",
        )

    def test_generate_second_repo_after_source_change_first_repo_untouched(self):
        self._generate(self.repo_a, self.NAME_A)
        before = self._roles_bytes(self.roles_a)
        pilaunch = _load_module()
        changed = self._changed_documents()

        with mock.patch.object(
            pilaunch.piprompt, "all_documents", return_value=changed
        ):
            self._generate(self.repo_b, self.NAME_B)

        self._assert_roles_unchanged(before, self._roles_bytes(self.roles_a))


if __name__ == "__main__":
    unittest.main()
