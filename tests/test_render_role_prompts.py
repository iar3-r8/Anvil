"""Tests for the role-prompt write seam in anvilkit.render.

plans/pi-role-prompts.md behaviour 11 (render-writes-role-prompts):
``render.role_prompts(root, documents)`` writes one ``.md`` file per
mapping entry, at ``<root>/.pi/roles/<stem>.md``, each byte-identical to
its in-memory document, and never writes outside the given root.

The documents are opaque strings here: building and validating them is
piprompt's job (behaviours 4-9), so this module pins only the write seam
— the path layout, the verbatim bytes, containment to the root, parent
directory creation, and ``RenderError`` on an unwritable path or an
empty (misconfigured) documents mapping.
"""

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import render  # noqa: E402

# The six committed role stems; behaviour 13 pins that the committed set
# is exactly these. The seam itself is generic over the mapping it is
# given, so the tests pass the full set.
STEMS = ("shared-agents", "architect", "coder", "tester", "docs", "tdd-manager")


def six_documents():
    """Distinct opaque documents for the six stems.

    Every document ends with a newline except ``coder``'s, which does
    not: the seam must write the bytes verbatim, so a missing trailing
    newline on the input must not be invented on the way to disk.
    """
    return {
        "shared-agents": "# Shared agents\nShared document body.\n",
        "architect": "# Architect\nArchitect document body.\n",
        "coder": "You write and modify code.",
        "tester": "# Tester\nTester document body.\n",
        "docs": "# Docs\nDocs document body.\n",
        "tdd-manager": "# TDD manager\nTDD manager document body.\n",
    }


def roles_dir(root):
    return Path(root) / ".pi" / "roles"


class TestRolePrompts(unittest.TestCase):
    """Behaviour 11: render owns the role-prompt write seam."""

    def test_role_prompts_writes_one_md_per_stem_matching_its_document_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            documents = six_documents()

            render.role_prompts(root, documents)

            entries = sorted(entry.name for entry in roles_dir(root).iterdir())
            self.assertEqual(
                entries,
                sorted(stem + ".md" for stem in STEMS),
                "exactly one .md file per stem under .pi/roles/",
            )
            for stem, document in documents.items():
                self.assertEqual(
                    (roles_dir(root) / (stem + ".md")).read_bytes(),
                    document.encode("utf-8"),
                    "{}: written bytes must equal the document byte for byte".format(stem),
                )

    def test_role_prompts_writes_no_file_outside_the_given_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            render.role_prompts(root, six_documents())

            files = sorted(
                str(path.relative_to(root))
                for path in root.rglob("*")
                if path.is_file()
            )
            self.assertEqual(
                files,
                sorted(".pi/roles/{}.md".format(stem) for stem in STEMS),
                "the only files under the root are the six role documents — "
                "nothing in the root itself, in .pi/, or anywhere else",
            )

    def test_role_prompts_unwritable_path_raises_render_error_leaving_no_partial_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # .pi as a file makes .pi/roles/ impossible to create.
            (root / ".pi").write_text("not a directory", encoding="utf-8")

            with self.assertRaises(render.RenderError):
                render.role_prompts(root, six_documents())

            self.assertTrue(
                (root / ".pi").is_file(),
                "the pre-existing .pi file must survive the failed call",
            )
            for stem in STEMS:
                self.assertFalse(
                    (roles_dir(root) / (stem + ".md")).exists(),
                    "{}: no partial file may be left behind".format(stem),
                )

    def test_role_prompts_creates_the_roles_directory_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertFalse((root / ".pi").exists())

            render.role_prompts(root, six_documents())

            self.assertTrue(
                roles_dir(root).is_dir(),
                "the .pi/roles/ directory must be created, not assumed to pre-exist",
            )
            for stem in STEMS:
                self.assertTrue(
                    (roles_dir(root) / (stem + ".md")).is_file(),
                    "{}: the document must be written after the directory is created".format(stem),
                )

    def test_role_prompts_empty_documents_mapping_raises_render_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with self.assertRaises(render.RenderError):
                render.role_prompts(root, {})

            written = [path for path in root.rglob("*") if path.is_file()]
            self.assertEqual(
                written,
                [],
                "an empty documents mapping fails fast and writes nothing",
            )


if __name__ == "__main__":
    unittest.main()
