"""Tests for the .gitignore template shipped with Anvil.

Written before the implementation.

The .gitignore template lives in ``templates/.gitignore.template`` and lists
every path that Anvil-produced artifacts write to.  Setup-repo copies it into
the target repository so developers do not accidentally commit sensitive or
generated files.

This module only validates the template contents — it does not exercise the
full provisioning flow.
"""

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The set of paths every Anvil-produced .gitignore must cover.
REQUIRED_ENTRIES = [
    "zoo-code-settings.json",
    ".roo/mcp.json",
    ".env",
    "anvil.local.yaml",
    ".venv/.anvil-requirements-stamp",
]


def _parse_gitignore(content: str) -> set[str]:
    """Return stripped, non-blank, non-comment lines from *content*."""
    entries: set[str] = set()
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        entries.add(stripped)
    return entries


class GitignoreTemplateTests(unittest.TestCase):
    """Validate that templates/.gitignore.template lists all sensitive paths."""

    def test_template_file_exists(self):
        """The template must be shipped inside the repository."""
        template_path = (
            REPO_ROOT / "templates" / ".gitignore.template"
        )
        self.assertTrue(
            template_path.is_file(),
            f"templates/.gitignore.template not found at {template_path}",
        )

    def test_entries_are_superset_of_required_paths(self):
        """Every required entry must appear in the template."""
        template_path = (
            REPO_ROOT / "templates" / ".gitignore.template"
        )
        self.assertTrue(
            template_path.is_file(),
            f"templates/.gitignore.template not found at {template_path}",
        )

        content = template_path.read_text(encoding="utf-8")
        entries = _parse_gitignore(content)

        missing: list[str] = []
        for entry in REQUIRED_ENTRIES:
            if entry not in entries:
                missing.append(entry)

        self.assertEqual(
            missing,
            [],
            (
                f"templates/.gitignore.template is missing the following "
                f"required entries: {missing}. "
                f"Current entries: {sorted(entries)}"
            ),
        )

    def test_comments_and_blank_lines_are_ignored(self):
        """Comment lines and blank lines must not appear as entries."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".gitignore.template", delete=False
        ) as tmp:
            tmp.write(
                "# Comment line\n"
                "\n"
                ".env\n"
                "   \n"
                "# Another comment\n"
                ".venv/.anvil-requirements-stamp\n"
            )
            tmp_path = Path(tmp.name)

        try:
            content = tmp_path.read_text(encoding="utf-8")
            entries = _parse_gitignore(content)
            self.assertNotIn("# Comment line", entries)
            self.assertNotIn("# Another comment", entries)
            self.assertIn(".env", entries)
            self.assertIn(".venv/.anvil-requirements-stamp", entries)
        finally:
            tmp_path.unlink()
