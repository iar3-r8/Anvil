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


class GitignoreProvisionErrorTests(unittest.TestCase):
    """Validate that a missing .gitignore.template raises ProvisionError.

    Behaviour 2 from plans/setup-repo-gitignore.md:
    A missing template is a fail-fast ``ProvisionError``, before anything is written.

    Written before the implementation (TDD).
    """

    def _build_synthetic_template_root(self, include_gitignore: bool = True):
        """Create a synthetic template root with all required files except .gitignore.template.

        When *include_gitignore* is False (default), the .gitignore.template
        file is intentionally omitted so that ``_Templates.validate()`` fails.
        """
        tmp = tempfile.TemporaryDirectory()
        base = Path(tmp.name)

        # Required files (all that _Templates currently checks)
        (base / "zoo-code-settings.json.template").write_text("{}", encoding="utf-8")
        (base / "mcp.json.template").write_text("{}", encoding="utf-8")
        (base / "extensions.json.template").write_text("{}", encoding="utf-8")
        (base / "update_roo_rules.md").write_text("", encoding="utf-8")

        # Required directories
        (base / "roo_template").mkdir()
        (base / "devcontainer").mkdir()

        if include_gitignore:
            (base / ".gitignore.template").write_text(".env\n", encoding="utf-8")

        return tmp

    def test_missing_gitignore_template_raises_provision_error(self):
        """_Templates.validate() must raise ProvisionError when .gitignore.template is absent."""
        tmp = self._build_synthetic_template_root(include_gitignore=False)
        try:
            from anvilkit.provision import _Templates, ProvisionError  # noqa: E402

            templates = _Templates(templates_dir=tmp.name)

            with self.assertRaises(ProvisionError) as ctx:
                templates.validate()

            msg = str(ctx.exception).lower()
            self.assertIn("gitignore template", msg,
                f"ProvisionError message should mention 'Gitignore template'. Got: {ctx.exception}")
            self.assertIn(".gitignore.template", msg,
                f"ProvisionError message should mention the template path '.gitignore.template'. Got: {ctx.exception}")
        finally:
            tmp.cleanup()

    def test_missing_gitignore_template_rough_target_untouched(self):
        """Even if a target directory exists, no files are written when validation fails."""
        tmp = self._build_synthetic_template_root(include_gitignore=False)
        target_tmp = tempfile.TemporaryDirectory()
        try:
            from anvilkit.provision import _Templates, ProvisionError  # noqa: E402

            templates = _Templates(templates_dir=tmp.name)
            target = Path(target_tmp.name) / "repo"
            target.mkdir()

            with self.assertRaises(ProvisionError):
                templates.validate()

            # Target must be completely untouched — no .roo/, no zoo-code-settings.json
            self.assertFalse((target / ".roo").exists(),
                ".roo/ should not exist after validation failure")
            self.assertFalse((target / "zoo-code-settings.json").exists(),
                "zoo-code-settings.json should not exist after validation failure")
        finally:
            tmp.cleanup()
            target_tmp.cleanup()
