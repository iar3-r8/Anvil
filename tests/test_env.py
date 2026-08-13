"""Tests for anvilkit.env - safe ``.env`` reading and writing.

Written before the implementation (TDD step 3).

This module replaces two of the worst defects in the bash script, and the tests
below are written to fail against those old behaviours:

* ``anvil:193`` - ``export $(grep -v '^#' .env | xargs)`` word-splits on spaces,
  mangles quoted values, and exports garbage into the process environment.
* ``anvil:112`` - ``sed -i "s|^ANTHROPIC_API_KEY=.*|...|"`` is GNU-only (breaks on
  macOS/BSD) and needed ``escape_sed_replacement()`` at ``anvil:95`` to survive
  keys containing ``\\``, ``&`` or ``|``.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import env  # noqa: E402


class EnvTestCase(unittest.TestCase):
    def setUp(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        self.tmp_path = Path(tmp_dir.name)
        self.env_path = self.tmp_path / ".env"

    def write_env(self, content):
        self.env_path.write_text(content, encoding="utf-8")
        return self.env_path


class TestRead(EnvTestCase):
    def test_reads_simple_pairs(self):
        self.write_env("LLM_PORT=8000\nDATA_DIR=./data\n")

        values = env.read(self.env_path)

        self.assertEqual(values["LLM_PORT"], "8000")
        self.assertEqual(values["DATA_DIR"], "./data")

    def test_missing_file_returns_empty_mapping(self):
        # 'help' and 'doctor' must work before .env exists.
        self.assertEqual(env.read(self.tmp_path / "absent.env"), {})

    def test_skips_comments_and_blank_lines(self):
        self.write_env(
            "# --- Host Storage Paths ---\n"
            "\n"
            "HF_HOME=/cache/hf\n"
            "\n"
            "# --- Networking Ports ---\n"
            "LLM_PORT=8000\n"
        )

        values = env.read(self.env_path)

        self.assertEqual(values, {"HF_HOME": "/cache/hf", "LLM_PORT": "8000"})

    def test_preserves_values_containing_spaces(self):
        # The old 'xargs' pipeline split this into separate tokens.
        self.write_env("ANTHROPIC_API_KEY=to set\n")

        self.assertEqual(env.read(self.env_path)["ANTHROPIC_API_KEY"], "to set")

    def test_preserves_paths_with_spaces(self):
        self.write_env("DATA_DIR=/home/user/My Documents/anvil\n")

        self.assertEqual(
            env.read(self.env_path)["DATA_DIR"], "/home/user/My Documents/anvil"
        )

    def test_strips_surrounding_double_quotes(self):
        self.write_env('DATA_DIR="/home/user/my data"\n')

        self.assertEqual(env.read(self.env_path)["DATA_DIR"], "/home/user/my data")

    def test_strips_surrounding_single_quotes(self):
        self.write_env("DATA_DIR='/home/user/my data'\n")

        self.assertEqual(env.read(self.env_path)["DATA_DIR"], "/home/user/my data")

    def test_keeps_inner_quotes_intact(self):
        self.write_env('GREETING=say "hello" loudly\n')

        self.assertEqual(env.read(self.env_path)["GREETING"], 'say "hello" loudly')

    def test_preserves_values_containing_equals_signs(self):
        # Base64 and JWT-style secrets routinely contain '='.
        self.write_env("TOKEN=abc==def=ghi\n")

        self.assertEqual(env.read(self.env_path)["TOKEN"], "abc==def=ghi")

    def test_preserves_sed_metacharacters_in_values(self):
        # These are exactly what escape_sed_replacement() existed to neutralise.
        self.write_env("ANTHROPIC_API_KEY=sk-ant-a\\b&c|d\n")

        self.assertEqual(
            env.read(self.env_path)["ANTHROPIC_API_KEY"], "sk-ant-a\\b&c|d"
        )

    def test_preserves_hash_inside_a_value(self):
        # A '#' mid-value is data, not a comment.
        self.write_env("TOKEN=abc#def\n")

        self.assertEqual(env.read(self.env_path)["TOKEN"], "abc#def")

    def test_ignores_leading_export_keyword(self):
        self.write_env("export LLM_PORT=8000\n")

        self.assertEqual(env.read(self.env_path)["LLM_PORT"], "8000")

    def test_tolerates_whitespace_around_key_and_value(self):
        self.write_env("  LLM_PORT = 8000  \n")

        self.assertEqual(env.read(self.env_path)["LLM_PORT"], "8000")

    def test_last_duplicate_key_wins(self):
        # Matches the old 'grep ... | tail -1' behaviour at anvil:102.
        self.write_env("LLM_PORT=8000\nLLM_PORT=9000\n")

        self.assertEqual(env.read(self.env_path)["LLM_PORT"], "9000")

    def test_empty_value_is_preserved_as_empty_string(self):
        self.write_env("HF_TOKEN=\n")

        self.assertEqual(env.read(self.env_path)["HF_TOKEN"], "")

    def test_file_without_trailing_newline_is_read_fully(self):
        self.env_path.write_text("LLM_PORT=8000", encoding="utf-8")

        self.assertEqual(env.read(self.env_path)["LLM_PORT"], "8000")

    def test_lines_without_equals_are_ignored(self):
        self.write_env("this is not a pair\nLLM_PORT=8000\n")

        self.assertEqual(env.read(self.env_path), {"LLM_PORT": "8000"})

    def test_does_not_mutate_the_process_environment(self):
        # The old script exported everything into the shell; we must not.
        marker = "ANVIL_TEST_MUST_NOT_LEAK"
        self.write_env("{}=leaked\n".format(marker))

        env.read(self.env_path)

        self.assertNotIn(marker, os.environ)


class TestGet(EnvTestCase):
    def test_returns_value_when_present(self):
        self.write_env("ANTHROPIC_API_KEY=sk-ant-existing\n")

        self.assertEqual(
            env.get(self.env_path, "ANTHROPIC_API_KEY"), "sk-ant-existing"
        )

    def test_returns_none_when_key_absent(self):
        self.write_env("LLM_PORT=8000\n")

        self.assertIsNone(env.get(self.env_path, "ANTHROPIC_API_KEY"))

    def test_returns_default_when_key_absent(self):
        self.write_env("LLM_PORT=8000\n")

        self.assertEqual(env.get(self.env_path, "MISSING", default="fallback"), "fallback")

    def test_returns_none_when_file_absent(self):
        self.assertIsNone(env.get(self.tmp_path / "absent.env", "ANY"))


class TestSet(EnvTestCase):
    def test_creates_file_when_absent(self):
        env.set_value(self.env_path, "LLM_PORT", "8000")

        self.assertTrue(self.env_path.is_file())
        self.assertEqual(env.read(self.env_path)["LLM_PORT"], "8000")

    def test_appends_new_key_without_disturbing_existing_ones(self):
        self.write_env("LLM_PORT=8000\nDATA_DIR=./data\n")

        env.set_value(self.env_path, "ANTHROPIC_API_KEY", "sk-ant-new")

        values = env.read(self.env_path)
        self.assertEqual(values["LLM_PORT"], "8000")
        self.assertEqual(values["DATA_DIR"], "./data")
        self.assertEqual(values["ANTHROPIC_API_KEY"], "sk-ant-new")

    def test_replaces_existing_key_rather_than_duplicating_it(self):
        self.write_env("ANTHROPIC_API_KEY=old-key\nLLM_PORT=8000\n")

        env.set_value(self.env_path, "ANTHROPIC_API_KEY", "new-key")

        content = self.env_path.read_text(encoding="utf-8")
        self.assertEqual(content.count("ANTHROPIC_API_KEY"), 1)
        self.assertEqual(env.read(self.env_path)["ANTHROPIC_API_KEY"], "new-key")

    def test_replacement_preserves_surrounding_lines_and_order(self):
        self.write_env(
            "# --- Host Storage Paths ---\n"
            "HF_HOME=/cache/hf\n"
            "ANTHROPIC_API_KEY=old-key\n"
            "# --- Networking Ports ---\n"
            "LLM_PORT=8000\n"
        )

        env.set_value(self.env_path, "ANTHROPIC_API_KEY", "new-key")

        lines = self.env_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "# --- Host Storage Paths ---")
        self.assertEqual(lines[1], "HF_HOME=/cache/hf")
        self.assertEqual(lines[2], "ANTHROPIC_API_KEY=new-key")
        self.assertEqual(lines[3], "# --- Networking Ports ---")
        self.assertEqual(lines[4], "LLM_PORT=8000")

    def test_appends_cleanly_when_file_lacks_trailing_newline(self):
        # anvil:115 needed a tail -c 1 check to avoid gluing keys together.
        self.env_path.write_text("LLM_PORT=8000", encoding="utf-8")

        env.set_value(self.env_path, "ANTHROPIC_API_KEY", "sk-ant-new")

        values = env.read(self.env_path)
        self.assertEqual(values["LLM_PORT"], "8000")
        self.assertEqual(values["ANTHROPIC_API_KEY"], "sk-ant-new")

    def test_written_file_always_ends_with_newline(self):
        env.set_value(self.env_path, "LLM_PORT", "8000")

        self.assertTrue(self.env_path.read_text(encoding="utf-8").endswith("\n"))

    def test_value_with_sed_metacharacters_round_trips(self):
        # The decisive regression: no escaping helper, no corruption.
        secret = "sk-ant-a\\b&c|d/e"

        env.set_value(self.env_path, "ANTHROPIC_API_KEY", secret)

        self.assertEqual(env.read(self.env_path)["ANTHROPIC_API_KEY"], secret)

    def test_value_with_spaces_round_trips(self):
        env.set_value(self.env_path, "DATA_DIR", "/home/user/My Documents")

        self.assertEqual(
            env.read(self.env_path)["DATA_DIR"], "/home/user/My Documents"
        )

    def test_does_not_match_keys_by_substring(self):
        # Setting 'KEY' must not rewrite 'ANTHROPIC_API_KEY'.
        self.write_env("ANTHROPIC_API_KEY=untouched\n")

        env.set_value(self.env_path, "KEY", "separate")

        values = env.read(self.env_path)
        self.assertEqual(values["ANTHROPIC_API_KEY"], "untouched")
        self.assertEqual(values["KEY"], "separate")

    def test_creates_parent_directories_when_needed(self):
        nested = self.tmp_path / "deeper" / "still" / ".env"

        env.set_value(nested, "LLM_PORT", "8000")

        self.assertTrue(nested.is_file())

    def test_set_value_preserves_anthropic_api_key_and_github_token_when_setting_oxylabs(self):
        """Verify env.set_value preserves existing keys when persisting oxylabs credentials.

        This is the decisive test for the Behavior 4 contract: when ``_resolve_oxylabs``
        calls ``env.set_value`` twice (once for OXYLABS_USERNAME, once for
        OXYLABS_PASSWORD), every pre-existing key in the file must remain
        byte-for-byte unchanged.
        """
        self.write_env(
            "ANTHROPIC_API_KEY=sk-abc123\n"
            "GITHUB_TOKEN=ghp_old\n"
        )

        env.set_value(self.env_path, "OXYLABS_USERNAME", "user1")
        env.set_value(self.env_path, "OXYLABS_PASSWORD", "pass1")

        content = self.env_path.read_text(encoding="utf-8")

        self.assertIn("ANTHROPIC_API_KEY=sk-abc123\n", content)
        self.assertIn("GITHUB_TOKEN=ghp_old\n", content)
        self.assertIn("OXYLABS_USERNAME=user1\n", content)
        self.assertIn("OXYLABS_PASSWORD=pass1\n", content)


class TestWriteMany(EnvTestCase):
    def test_writes_all_pairs_in_given_order(self):
        env.write(
            self.env_path,
            [("HF_HOME", "/cache/hf"), ("DATA_DIR", "./"), ("LLM_PORT", "8000")],
        )

        values = env.read(self.env_path)
        self.assertEqual(values["HF_HOME"], "/cache/hf")
        self.assertEqual(values["DATA_DIR"], "./")
        self.assertEqual(values["LLM_PORT"], "8000")

    def test_supports_section_comments(self):
        env.write(
            self.env_path,
            [("LLM_PORT", "8000")],
            sections={"LLM_PORT": "--- Networking Ports ---"},
        )

        content = self.env_path.read_text(encoding="utf-8")
        self.assertIn("# --- Networking Ports ---", content)
        self.assertEqual(env.read(self.env_path)["LLM_PORT"], "8000")

    def test_overwrites_previous_content(self):
        self.write_env("STALE=value\n")

        env.write(self.env_path, [("LLM_PORT", "8000")])

        self.assertNotIn("STALE", env.read(self.env_path))


if __name__ == "__main__":
    unittest.main()
