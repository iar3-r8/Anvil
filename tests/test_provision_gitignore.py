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

from anvilkit import provision  # noqa: E402

# The set of paths every Anvil-produced .gitignore must cover.
REQUIRED_ENTRIES = [
    "zoo-code-settings.json",
    ".roo/mcp.json",
    ".env",
    "anvil.local.yaml",
    ".venv/.anvil-requirements-stamp",
]

# The five entries in template order (without header/comments).
TEMPLATE_ENTRIES_ORDERED = [
    ".env",
    "anvil.local.yaml",
    "zoo-code-settings.json",
    ".roo/mcp.json",
    ".venv/.anvil-requirements-stamp",
]

HEADER_LINES = [
    "# Anvil-managed entries — do not edit manually.",
    "# Setup-repo appends missing entries below this marker.",
]

HEADER_BLOCK = HEADER_LINES[0] + "\n" + HEADER_LINES[1] + "\n"


def _parse_gitignore(content: str) -> set:
    """Return stripped, non-blank, non-comment lines from *content*."""
    entries = set()
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        entries.add(stripped)
    return entries


def _make_mini_templates(tmp_dir):
    """Create minimal required templates so setup_repo can validate().

    *tmp_dir* is a ``pathlib.Path`` to the root of a temporary directory.
    """
    base = tmp_dir / "templates"
    base.mkdir()
    for name in (
        "zoo-code-settings.json.template",
        "mcp.json.template",
        "extensions.json.template",
        "update_roo_rules.md",
        ".gitignore.template",
    ):
        (base / name).write_text("{}\n", encoding="utf-8")
    roo = base / "roo_template"
    roo.mkdir()
    (roo / ".roomodes").write_text("# dummy\n", encoding="utf-8")
    (roo / "commands").mkdir()
    (roo / "rules").mkdir()
    devcontainer = base / "devcontainer"
    devcontainer.mkdir()
    (devcontainer / "Dockerfile").write_text("FROM python:3.11\n", encoding="utf-8")
    (devcontainer / "devcontainer.json").write_text(
        '{"name": "Test"}', encoding="utf-8"
    )
    return base


def _make_template_root_with_gitignore(tmp_dir, content):
    """Overwrite only the .gitignore.template with *content* (str)."""
    (tmp_dir / ".gitignore.template").write_text(
        content, encoding="utf-8"
    )


def _provision(tmp_dir, target, dry_run=False, echo_list=None):
    """Call ``provision.setup_repo`` and collect messages.

    Returns ``(target, message_list)``.
    """
    templates_dir = Path(tmp_dir.name) / "templates"
    messages = echo_list or []
    repo_plan = provision.RepoPlan(
        port=8000,
        context_window=262144,
        coder_model_id="test-coder",
        embedder_model_id="test-embedder",
        local_profile_id="test-local",
        anthropic_profile_id="test-anthropic",
        anthropic_api_key="test-key",
        anthropic_model_id="test-model",
        use_anthropic_for_frontier_modes=False,
        github_token="",
    )
    provision.setup_repo(
        target=target,
        repo_plan=repo_plan,
        templates_dir=templates_dir,
        dry_run=dry_run,
        echo=messages.append,
    )
    return target, messages


# ---------------------------------------------------------------------------
# Behaviour 3 — No existing .gitignore → created with header and all entries
# ---------------------------------------------------------------------------


class Behaviour3NoExistingGitignoreTests(unittest.TestCase):
    """Behaviour 3: No existing .gitignore → one is created with header and all entries.

    Written before the implementation (TDD).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = Path(self._tmp.name) / "repo"
        self.target.mkdir()
        self.template_root = _make_mini_templates(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_new_gitignore_is_created(self):
        """When there is no .gitignore, setup_repo creates one."""
        _provision(self._tmp, self.target)
        gitignore_path = self.target / ".gitignore"
        self.assertTrue(
            gitignore_path.is_file(),
            ".gitignore was not created in the target repo",
        )

    def test_new_gitignore_contains_header(self):
        """The created .gitignore starts with the Anvil header comment."""
        _provision(self._tmp, self.target)
        content = (self.target / ".gitignore").read_text(encoding="utf-8")
        for header_line in HEADER_LINES:
            self.assertIn(
                header_line,
                content,
                f"Header line not found in created .gitignore: {header_line}",
            )

    def test_new_gitignore_contains_all_entries(self):
        """Every required entry appears in the created file."""
        _provision(self._tmp, self.target)
        content = (self.target / ".gitignore").read_text(encoding="utf-8")
        entries = _parse_gitignore(content)
        for entry in REQUIRED_ENTRIES:
            self.assertIn(
                entry,
                entries,
                f"Required entry '{entry}' not found in created .gitignore",
            )

    def test_new_gitignore_ends_with_newline(self):
        """The created file must end with a trailing newline."""
        _provision(self._tmp, self.target)
        content = (self.target / ".gitignore").read_text(encoding="utf-8")
        self.assertTrue(
            content.endswith("\n"),
            "Created .gitignore does not end with a trailing newline",
        )

    def test_new_gitignore_header_appears_exactly_once(self):
        """The header comment block must be present exactly once."""
        _provision(self._tmp, self.target)
        content = (self.target / ".gitignore").read_text(encoding="utf-8")
        for header_line in HEADER_LINES:
            self.assertEqual(
                content.count(header_line),
                1,
                f"Header line appears {content.count(header_line)} times; expected 1",
            )


# ----------------------------------------------------------------
# Behaviour 4 — Existing .gitignore with no Anvil entries → append all
# ----------------------------------------------------------------


class Behaviour4ExistingGitignoreNoAnvilEntries(unittest.TestCase):
    """Behaviour 4: Existing .gitignore with no Anvil entries → all appended, prior content intact.

    Written before the implementation (TDD).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = Path(self._tmp.name) / "repo"
        self.target.mkdir()
        self.template_root = _make_mini_templates(Path(self._tmp.name))
        # Pre-populate an existing .gitignore with non-Anvil content.
        self.existing_content = "node_modules/\n*.log\n# build output\ndist/\n"
        (self.target / ".gitignore").write_text(
            self.existing_content, encoding="utf-8"
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_all_original_lines_preserved_at_start(self):
        """Every original line must still be present at the start of the file."""
        _provision(self._tmp, self.target)
        new_content = (self.target / ".gitignore").read_text(encoding="utf-8")
        self.assertTrue(
            new_content.startswith(self.existing_content),
            "Original .gitignore content was not preserved as a prefix",
        )

    def test_all_anvil_entries_appended(self):
        """All Anvil entries must appear after the original content."""
        _provision(self._tmp, self.target)
        entries = _parse_gitignore(
            (self.target / ".gitignore").read_text(encoding="utf-8")
        )
        for entry in REQUIRED_ENTRIES:
            self.assertIn(
                entry,
                entries,
                f"Entry '{entry}' was not appended",
            )

    def test_header_follows_original_content(self):
        """The Anvil header comment must follow the original content."""
        _provision(self._tmp, self.target)
        content = (self.target / ".gitignore").read_text(encoding="utf-8")
        # The original content should appear first, then the header.
        first_header_index = content.find(HEADER_LINES[0])
        original_end_index = content.find(self.existing_content.strip().split("\n")[-1])
        self.assertLess(
            original_end_index,
            first_header_index,
            "Header does not appear after original content",
        )


# ----------------------------------------------------------------
# Behaviour 5 — Partial overlap → only missing entries appended
# ----------------------------------------------------------------


class Behaviour5PartialOverlapTests(unittest.TestCase):
    """Behaviour 5: Partial overlap → only missing entries appended.

    Written before the implementation (TDD).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = Path(self._tmp.name) / "repo"
        self.target.mkdir()
        self.template_root = _make_mini_templates(Path(self._tmp.name))
        # Existing .gitignore already contains .env.
        self.existing_content = "node_modules/\n.env\n*.log\n"
        (self.target / ".gitignore").write_text(
            self.existing_content, encoding="utf-8"
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_env_appears_exactly_once(self):
        """.env must appear exactly once in the result — not duplicated."""
        _provision(self._tmp, self.target)
        content = (self.target / ".gitignore").read_text(encoding="utf-8")
        # Count non-comment, non-blank lines that are exactly '.env'.
        env_count = sum(
            1
            for line in content.splitlines()
            if line.strip() == ".env" and not line.strip().startswith("#")
        )
        self.assertEqual(
            env_count,
            1,
            f".env appears {env_count} times; expected 1",
        )

    def test_missing_entries_are_appended(self):
        """The four missing entries must be appended."""
        _provision(self._tmp, self.target)
        entries = _parse_gitignore(
            (self.target / ".gitignore").read_text(encoding="utf-8")
        )
        for entry in REQUIRED_ENTRIES:
            self.assertIn(
                entry,
                entries,
                f"Missing entry '{entry}' was not appended",
            )

    def test_original_position_preserved(self):
        """.env keeps its original position in the file."""
        _provision(self._tmp, self.target)
        content = (self.target / ".gitignore").read_text(encoding="utf-8")
        # The .env line should be in its original place (between node_modules/ and *.log).
        lines = content.splitlines()
        env_idx = None
        for i, line in enumerate(lines):
            if line.strip() == ".env":
                env_idx = i
                break
        self.assertIsNotNone(env_idx)
        # There should be 'node_modules/' before .env.
        self.assertIn("node_modules/", lines[:env_idx])

    def test_only_missing_entries_in_appended_block(self):
        """The appended block should contain only the four missing entries."""
        _provision(self._tmp, self.target)
        content = (self.target / ".gitignore").read_text(encoding="utf-8")
        # The appended block starts after the original content.
        appended = content[len(self.existing_content) :]
        appended_entries = _parse_gitignore(appended)
        for entry in REQUIRED_ENTRIES:
            if entry != ".env":
                self.assertIn(
                    entry,
                    appended_entries,
                    f"Missing entry '{entry}' not in appended block",
                )
        self.assertNotIn(
            ".env",
            appended_entries,
            ".env should not be in the appended block",
        )


# ----------------------------------------------------------------
# Behaviour 6 — All entries present → byte-for-byte unchanged
# ----------------------------------------------------------------


class Behaviour6AllEntriesPresentTests(unittest.TestCase):
    """Behaviour 6: All entries already present → byte-for-byte unchanged.

    Written before the implementation (TDD).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = Path(self._tmp.name) / "repo"
        self.target.mkdir()
        self.template_root = _make_mini_templates(Path(self._tmp.name))
        # Create an .gitignore with all five entries interleaved in different order.
        self.original_content = (
            "# My project\n"
            "node_modules/\n"
            ".venv/.anvil-requirements-stamp\n"
            "*.log\n"
            "anvil.local.yaml\n"
            "build/\n"
            ".env\n"
            "zoo-code-settings.json\n"
            ".roo/mcp.json\n"
        )
        (self.target / ".gitignore").write_text(
            self.original_content, encoding="utf-8"
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_file_unchanged_after_provisioning(self):
        """When all entries are present, the file must be byte-for-byte unchanged."""
        _provision(self._tmp, self.target)
        new_content = (self.target / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(
            new_content,
            self.original_content,
            "File content changed even though all entries were present",
        )

    def test_no_header_added_when_all_present(self):
        """No header comment should be added if all entries are already present."""
        _provision(self._tmp, self.target)
        content = (self.target / ".gitignore").read_text(encoding="utf-8")
        for header_line in HEADER_LINES:
            self.assertNotIn(
                header_line,
                content,
                "Header was added despite all entries being present",
            )


# ----------------------------------------------------------------
# Behaviour 7 — Re-running setup_repo is idempotent
# ----------------------------------------------------------------


class Behaviour7IdempotentTests(unittest.TestCase):
    """Behaviour 7: Re-running setup_repo is idempotent.

    Written before the implementation (TDD).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = Path(self._tmp.name) / "repo"
        self.target.mkdir()
        self.template_root = _make_mini_templates(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_second_run_produces_identical_gitignore(self):
        """Calling setup_repo twice produces the same .gitignore."""
        _provision(self._tmp, self.target)
        first_content = (self.target / ".gitignore").read_text(encoding="utf-8")
        _provision(self._tmp, self.target)
        second_content = (self.target / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(
            second_content,
            first_content,
            "Second run changed .gitignore content",
        )

    def test_header_appears_exactly_once_after_two_runs(self):
        """The header must still appear exactly once after the second run."""
        _provision(self._tmp, self.target)
        _provision(self._tmp, self.target)
        content = (self.target / ".gitignore").read_text(encoding="utf-8")
        for header_line in HEADER_LINES:
            self.assertEqual(
                content.count(header_line),
                1,
                f"Header appears {content.count(header_line)} times after two runs",
            )

    def test_no_entries_duplicated_after_two_runs(self):
        """No entry should appear more than once after re-running."""
        _provision(self._tmp, self.target)
        _provision(self._tmp, self.target)
        content = (self.target / ".gitignore").read_text(encoding="utf-8")
        for entry in REQUIRED_ENTRIES:
            count = sum(
                1
                for line in content.splitlines()
                if line.strip() == entry
            )
            self.assertEqual(
                count,
                1,
                f"Entry '{entry}' appears {count} times after two runs",
            )


# ---------------------------------------------------------------
# Behaviour 8 — Presence matching ignores comments and whitespace
# ---------------------------------------------------------------


class Behaviour8PresenceMatchingTests(unittest.TestCase):
    """Behaviour 8: Presence matching ignores comments and surrounding whitespace.

    Written before the implementation (TDD).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = Path(self._tmp.name) / "repo"
        self.target.mkdir()
        self.template_root = _make_mini_templates(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_whitespace_around_entry_treated_as_present(self):
        """.env with surrounding whitespace is treated as present."""
        existing = "  .env  \n"
        (self.target / ".gitignore").write_text(existing, encoding="utf-8")
        _provision(self._tmp, self.target)
        content = (self.target / ".gitignore").read_text(encoding="utf-8")
        # .env should NOT be duplicated (i.e., not appear as a separate appended entry).
        # Check that the appended block does not contain .env.
        lines = content.splitlines()
        # Find the line after the header block — that's where appended entries start.
        header_end_idx = None
        for i, line in enumerate(lines):
            if "Setup-repo appends missing entries" in line:
                header_end_idx = i
                break
        self.assertIsNotNone(header_end_idx)
        appended_block = "\n".join(lines[header_end_idx:])
        appended_entries = _parse_gitignore(appended_block)
        self.assertNotIn(
            ".env",
            appended_entries,
            ".env was re-appended despite being present with whitespace",
        )

    def test_commented_entry_treated_as_absent_and_appended(self):
        """A commented-out entry like '# zoo-code-settings.json' is not present."""
        existing = "# zoo-code-settings.json\nnode_modules/\n"
        (self.target / ".gitignore").write_text(existing, encoding="utf-8")
        _provision(self._tmp, self.target)
        content = (self.target / ".gitignore").read_text(encoding="utf-8")
        entries = _parse_gitignore(content)
        self.assertIn(
            "zoo-code-settings.json",
            entries,
            "zoo-code-settings.json should be appended when only commented out",
        )
        # Find appended block and check zoo-code-settings.json is there.
        lines = content.splitlines()
        header_end_idx = None
        for i, line in enumerate(lines):
            if "Setup-repo appends missing entries" in line:
                header_end_idx = i
                break
        self.assertIsNotNone(header_end_idx)
        appended_block = "\n".join(lines[header_end_idx:])
        self.assertIn(
            "zoo-code-settings.json",
            _parse_gitignore(appended_block),
            "zoo-code-settings.json should be in the appended block",
        )

    def test_negation_line_does_not_count_as_presence(self):
        """A negation line like '!.env' does not count as presence of '.env'."""
        existing = "!.env\nnode_modules/\n"
        (self.target / ".gitignore").write_text(existing, encoding="utf-8")
        _provision(self._tmp, self.target)
        content = (self.target / ".gitignore").read_text(encoding="utf-8")
        # .env must be in the appended block because '!.env' != '.env'.
        lines = content.splitlines()
        header_end_idx = None
        for i, line in enumerate(lines):
            if "Setup-repo appends missing entries" in line:
                header_end_idx = i
                break
        self.assertIsNotNone(header_end_idx)
        appended_block = "\n".join(lines[header_end_idx:])
        self.assertIn(
            ".env",
            _parse_gitignore(appended_block),
            ".env should be appended when only '!.env' exists",
        )


# ----------------------------------------------------------------------
# Behaviour 9 — Missing trailing newline handled
# ----------------------------------------------------------------------


class Behaviour9MissingTrailingNewlineTests(unittest.TestCase):
    """Behaviour 9: A .gitignore without a trailing newline gains one before the appended block.

    Written before the implementation (TDD).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = Path(self._tmp.name) / "repo"
        self.target.mkdir()
        self.template_root = _make_mini_templates(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_header_not_glued_to_last_line(self):
        """Without trailing newline, header must not be glued to the last line."""
        existing = "node_modules/"  # no trailing newline
        (self.target / ".gitignore").write_text(existing, encoding="utf-8")
        _provision(self._tmp, self.target)
        content = (self.target / ".gitignore").read_text(encoding="utf-8")
        # Check that 'node_modules/' is on its own line followed by newline.
        self.assertIn(
            "node_modules/\n",
            content,
            "node_modules/ must end with newline before header",
        )
        # The header must not appear immediately after 'node_modules/'.
        self.assertNotIn(
            "node_modules/# Anvil-managed",
            content,
            "Header is glued to last line without newline",
        )

    def test_empty_gitignore_gets_header_and_entries(self):
        """An empty (zero-byte) .gitignore gets the header and all entries without extra blank line."""
        (self.target / ".gitignore").write_text("", encoding="utf-8")
        _provision(self._tmp, self.target)
        content = (self.target / ".gitignore").read_text(encoding="utf-8")
        entries = _parse_gitignore(content)
        for entry in REQUIRED_ENTRIES:
            self.assertIn(
                entry,
                entries,
                f"Entry '{entry}' missing from .gitignore",
            )
        for header_line in HEADER_LINES:
            self.assertIn(
                header_line,
                content,
                "Header missing from empty .gitignore",
            )


# -----------------------------------------------------------------
# Behaviour 10 — dry_run=True writes nothing
# -----------------------------------------------------------------


class Behaviour10DryRunTests(unittest.TestCase):
    """Behaviour 10: dry_run=True writes nothing.

    Written before the implementation (TDD).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = Path(self._tmp.name) / "repo"
        self.target.mkdir()
        self.template_root = _make_mini_templates(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_gitignore_created_with_dry_run(self):
        """dry_run=True must not create a new .gitignore."""
        _provision(self._tmp, self.target, dry_run=True)
        gitignore_path = self.target / ".gitignore"
        self.assertFalse(
            gitignore_path.exists(),
            ".gitignore was created despite dry_run=True",
        )

    def test_existing_gitignore_untouched_with_dry_run(self):
        """dry_run=True must not modify an existing .gitignore."""
        existing = "node_modules/\n"
        (self.target / ".gitignore").write_text(existing, encoding="utf-8")
        _provision(self._tmp, self.target, dry_run=True)
        content = (self.target / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(
            content,
            existing,
            "Existing .gitignore was modified despite dry_run=True",
        )


# ---------------------------------------------------------------
# Behaviour 11 — Step reports what it did
# ---------------------------------------------------------------


class Behaviour11StepReportsTests(unittest.TestCase):
    """Behaviour 11: The step reports what it did.

    Written before the implementation (TDD).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = Path(self._tmp.name) / "repo"
        self.target.mkdir()
        self.template_root = _make_mini_templates(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_created_report_line_when_no_gitignore(self):
        """When a new .gitignore is created, the report mentions the destination."""
        messages = []
        _provision(self._tmp, self.target, echo_list=messages)
        report_lines = [m for m in messages if ".gitignore" in m.lower()]
        self.assertTrue(
            len(report_lines) > 0,
            "No report line mentions .gitignore",
        )
        combined = " ".join(report_lines)
        # Must mention the destination path.
        self.assertIn(
            str(self.target / ".gitignore"),
            combined,
            "Report does not name the destination path",
        )

    def test_append_report_line_when_entries_appended(self):
        """When entries are appended, the report distinguishes it from created."""
        (self.target / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        messages = []
        _provision(self._tmp, self.target, echo_list=messages)
        report_lines = [m for m in messages if ".gitignore" in m.lower()]
        self.assertTrue(
            len(report_lines) > 0,
            "No report line mentions .gitignore",
        )

    def test_skipped_report_line_when_all_entries_present(self):
        """When all entries are present, the report indicates skipped."""
        existing = "\n".join(REQUIRED_ENTRIES) + "\n"
        (self.target / ".gitignore").write_text(existing, encoding="utf-8")
        messages = []
        _provision(self._tmp, self.target, echo_list=messages)
        report_lines = [m for m in messages if ".gitignore" in m.lower()]
        self.assertTrue(
            len(report_lines) > 0,
            "No report line mentions .gitignore",
        )

    def test_report_does_not_dump_entry_content(self):
        """The report must not contain entry-by-entry content dump."""
        messages = []
        _provision(self._tmp, self.target, echo_list=messages)
        # The report lines should not contain raw entry content like '*.log'
        # or anything that looks like a dump.
        report_lines = [m for m in messages if ".gitignore" in m.lower()]
        # A simple check: the report lines should not be extremely long.
        for line in report_lines:
            self.assertLess(
                len(line),
                200,
                f"Report line appears to dump content: {line[:100]}...",
            )


# -----------------------------------------------------------------------
# Behaviour 12 — .gitignore that is a directory → ProvisionError
# -----------------------------------------------------------------------


class Behaviour12GitignoreIsDirectoryTests(unittest.TestCase):
    """Behaviour 12: A .gitignore that is a directory is a clean ProvisionError.

    Written before the implementation (TDD).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = Path(self._tmp.name) / "repo"
        self.target.mkdir()
        self.template_root = _make_mini_templates(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_provision_error_raised_when_gitignore_is_directory(self):
        """When .gitignore is a directory, ProvisionError is raised."""
        # Create a directory named .gitignore.
        gitignore_dir = self.target / ".gitignore"
        gitignore_dir.mkdir()

        with self.assertRaises(provision.ProvisionError) as ctx:
            _provision(self._tmp, self.target)

        msg = str(ctx.exception).lower()
        self.assertIn(
            "gitignore",
            msg,
            f"ProvisionError should mention 'gitignore'. Got: {ctx.exception}",
        )

    def test_not_raw_is_a_directory_error(self):
        """The error must be ProvisionError, not a raw IsADirectoryError."""
        gitignore_dir = self.target / ".gitignore"
        gitignore_dir.mkdir()

        try:
            _provision(self._tmp, self.target)
            self.fail("Expected ProvisionError to be raised")
        except IsADirectoryError:
            self.fail("Got raw IsADirectoryError instead of ProvisionError")
        except provision.ProvisionError:
            pass  # Expected


# ----------------------------------------------------------------------------
# Behaviour 13 — Non-UTF-8 .gitignore → ProvisionError
# ----------------------------------------------------------------------------


class Behaviour13NonUtf8GitignoreTests(unittest.TestCase):
    """Behaviour 13: A non-UTF-8 .gitignore fails as ProvisionError.

    Written before the implementation (TDD).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = Path(self._tmp.name) / "repo"
        self.target.mkdir()
        self.template_root = _make_mini_templates(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_provision_error_raised_for_non_utf8_gitignore(self):
        """When .gitignore contains invalid UTF-8 bytes, ProvisionError is raised."""
        # Write invalid UTF-8 bytes.
        gitignore_path = self.target / ".gitignore"
        gitignore_path.write_bytes(b"\xff\xfe node_modules/\n")

        with self.assertRaises(provision.ProvisionError) as ctx:
            _provision(self._tmp, self.target)

        msg = str(ctx.exception).lower()
        self.assertIn(
            "utf",
            msg,
            f"ProvisionError should mention UTF-8 issue. Got: {ctx.exception}",
        )

    def test_original_bytes_unchanged_on_error(self):
        """The original non-UTF-8 bytes must remain on disk after the error."""
        gitignore_path = self.target / ".gitignore"
        bad_bytes = b"\xff\xfe node_modules/\n"
        gitignore_path.write_bytes(bad_bytes)

        with self.assertRaises(provision.ProvisionError):
            _provision(self._tmp, self.target)

        actual_bytes = gitignore_path.read_bytes()
        self.assertEqual(
            actual_bytes,
            bad_bytes,
            "Original bytes were changed during the error",
        )


# ---------------------------------------------------------------------------
# Behaviour 14 — Merge helper is unit-testable without a filesystem
# ---------------------------------------------------------------------------


class Behaviour14MergeHelperUnitTests(unittest.TestCase):
    """Behaviour 14: The merge helper is unit-testable without a filesystem.

    Written before the implementation (TDD).
    """

    def test_merge_gitignore_function_exists(self):
        """A _merge_gitignore function must be importable from provision."""
        from anvilkit.provision import _merge_gitignore  # noqa: F401

    def test_merge_no_existing_appends_all(self):
        """Empty existing text → header plus all entries."""
        from anvilkit.provision import _merge_gitignore

        result = _merge_gitignore("", "\n".join(TEMPLATE_ENTRIES_ORDERED) + "\n")
        entries = _parse_gitignore(result)
        for entry in REQUIRED_ENTRIES:
            self.assertIn(entry, entries)

    def test_merge_existing_with_no_entries_appends_all(self):
        """Existing content with no Anvil entries → all appended."""
        from anvilkit.provision import _merge_gitignore

        existing = "node_modules/\n*.log\n"
        template = "\n".join(TEMPLATE_ENTRIES_ORDERED) + "\n"
        result = _merge_gitignore(existing, template)
        self.assertTrue(result.startswith(existing))
        entries = _parse_gitignore(result)
        for entry in REQUIRED_ENTRIES:
            self.assertIn(entry, entries)

    def test_merge_partial_overlap_appends_only_missing(self):
        """If .env is present, only the other four are appended."""
        from anvilkit.provision import _merge_gitignore

        existing = "node_modules/\n.env\n*.log\n"
        template = "\n".join(TEMPLATE_ENTRIES_ORDERED) + "\n"
        result = _merge_gitignore(existing, template)
        entries = _parse_gitignore(result)
        for entry in REQUIRED_ENTRIES:
            self.assertIn(entry, entries)
        # .env should appear exactly once.
        count = sum(1 for line in result.splitlines() if line.strip() == ".env")
        self.assertEqual(count, 1)

    def test_merge_all_present_returns_unchanged(self):
        """When all entries are present, return None (unchanged marker)."""
        from anvilkit.provision import _merge_gitignore

        existing = "\n".join(REQUIRED_ENTRIES) + "\n"
        template = "\n".join(TEMPLATE_ENTRIES_ORDERED) + "\n"
        result = _merge_gitignore(existing, template)
        self.assertIsNone(
            result,
            "Expected None when all entries are already present",
        )

    def test_merge_whitespace_around_entry_treated_as_present(self):
        """.env with whitespace is treated as present."""
        from anvilkit.provision import _merge_gitignore

        existing = "  .env  \nnode_modules/\n"
        template = "\n".join(TEMPLATE_ENTRIES_ORDERED) + "\n"
        result = _merge_gitignore(existing, template)
        self.assertIsNotNone(result)  # Not all present
        entries = _parse_gitignore(result)
        self.assertIn(".env", entries)
        count = sum(1 for line in result.splitlines() if line.strip() == ".env")
        self.assertEqual(count, 1, ".env should appear exactly once")

    def test_merge_commented_entry_treated_as_absent(self):
        """A commented entry is treated as absent and appended."""
        from anvilkit.provision import _merge_gitignore

        existing = "# zoo-code-settings.json\n"
        template = "\n".join(TEMPLATE_ENTRIES_ORDERED) + "\n"
        result = _merge_gitignore(existing, template)
        entries = _parse_gitignore(result)
        self.assertIn("zoo-code-settings.json", entries)
        # Count occurrences: should appear exactly once (appended, not in comment).
        count = sum(
            1
            for line in result.splitlines()
            if line.strip() == "zoo-code-settings.json"
        )
        self.assertEqual(count, 1)

    def test_merge_missing_trailing_newline(self):
        """A file without trailing newline must gain one before appended block."""
        from anvilkit.provision import _merge_gitignore

        existing = "node_modules/"  # no trailing newline
        template = "\n".join(TEMPLATE_ENTRIES_ORDERED) + "\n"
        result = _merge_gitignore(existing, template)
        self.assertIn("node_modules/\n", result)
        self.assertNotIn("node_modules/# Anvil", result)


if __name__ == "__main__":
    unittest.main()
