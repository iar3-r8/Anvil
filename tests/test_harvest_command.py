"""Tests for the /harvest-roo-templates chat command (plans/harvest-roo-templates.md).

This module is the home for every behaviour of that plan that is verified
against the command file itself:

  * B1 — the command file exists with valid frontmatter (implemented below);
  * B3-B8 — body-content behaviours; each will land in its own test case class
    pointed at the same file, built on the shared loader below.

The command file under test is ``.roo/commands/harvest-roo-templates.md`` in
this repository. B1 is currently red: the file does not exist yet, so every
B1 test fails at load time with the file-not-found assertion — the expected
kind of failure, not an import or collection error.

Every assertion is on the parsed frontmatter structure and on key phrases,
never on raw bytes, so the green step has latitude in the prose (precedent:
``tests/test_templates_rules.py``). The frontmatter shape follows
``.roo/commands/create-pull-request.md`` (a ``---``-delimited YAML block at the
top of the file).
"""

import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The command file under test (plan §Scope: anvil-only, re-included through a
# .gitignore negation, never provisioned into target repos).
COMMAND_PATH = REPO_ROOT / ".roo" / "commands" / "harvest-roo-templates.md"


class HarvestFrontmatterError(Exception):
    """The command file's frontmatter is malformed: a ``---`` delimiter is
    missing, the YAML does not parse, or the parsed frontmatter is not a
    mapping. The offending path is always named in the message."""


# --------------------------------------------------------------------------- #
# Shared loader: parse one markdown command file into (frontmatter, body)
# --------------------------------------------------------------------------- #

def load_harvest_command(path):
    """Read and parse *path* (a roo markdown command file).

    Returns a ``(frontmatter, body)`` tuple: *frontmatter* is the parsed YAML
    mapping between the opening ``---`` on line 1 and the closing ``---``;
    *body* is the markdown text after the closing delimiter, as a string.

    Raises:
        FileNotFoundError: the file is missing.
        HarvestFrontmatterError: the opening or closing ``---`` delimiter is
            absent, the frontmatter does not parse as YAML, or it does not
            parse to a mapping. The path is always named in the message.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise HarvestFrontmatterError(
            "missing opening '---' delimiter on line 1 of %s" % path
        )
    close_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            close_index = index
            break
    if close_index is None:
        raise HarvestFrontmatterError(
            "missing closing '---' delimiter in %s" % path
        )
    frontmatter_text = "\n".join(lines[1:close_index])
    try:
        frontmatter = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        raise HarvestFrontmatterError(
            "frontmatter of %s does not parse as YAML: %s" % (path, exc)
        ) from exc
    if not isinstance(frontmatter, dict):
        raise HarvestFrontmatterError(
            "frontmatter of %s is not a YAML mapping" % path
        )
    body = "\n".join(lines[close_index + 1:])
    return frontmatter, body


# --------------------------------------------------------------------------- #
# Base test case: loads and parses the command file
# --------------------------------------------------------------------------- #

class HarvestCommandTestCase(unittest.TestCase):
    """Shared loading for the harvest command file.

    Subclasses set ``command_path``; ``setUp`` loads it once so every test
    asserts on the parsed frontmatter and body, and a missing or malformed
    document surfaces at load time. Later behaviours (B3-B8) subclass this
    pointed at the same file and assert on ``self.body``.
    """

    command_path = None

    def setUp(self):
        if self.command_path is None:
            self.skipTest("abstract base class; run a concrete subclass")
        self.assertTrue(
            self.command_path.is_file(),
            "command file does not exist or is not a regular file: %s"
            % self.command_path,
        )
        self.frontmatter, self.body = load_harvest_command(self.command_path)


# --------------------------------------------------------------------------- #
# B1 — the command file exists with valid frontmatter
# --------------------------------------------------------------------------- #

class B1CommandFileFrontmatterTests(HarvestCommandTestCase):
    """B1 (plans/harvest-roo-templates.md): the command file exists with valid
    frontmatter.

    Expected red reason: ``.roo/commands/harvest-roo-templates.md`` does not
    exist yet, so every test fails in ``setUp`` with the file-not-found
    assertion. That is the intended failure mode — the green step creates the
    file, nothing else.
    """

    command_path = COMMAND_PATH

    def test_command_file_is_a_regular_file(self):
        # B1 output: the path is a file, not a directory or a missing path.
        # setUp already asserted this; the explicit test keeps the requirement
        # named in the suite.
        self.assertTrue(
            self.command_path.is_file(),
            "command file does not exist or is not a regular file: %s"
            % self.command_path,
        )

    def test_frontmatter_is_bounded_by_both_delimiters(self):
        # Edge (B1): frontmatter is delimited by '---' on the first line and a
        # closing '---'. The loader would have raised for either missing one;
        # this test pins the requirement on the file itself.
        lines = self.command_path.read_text(encoding="utf-8").splitlines()
        self.assertTrue(lines, "command file is empty")
        self.assertEqual(
            lines[0].strip(),
            "---",
            "first line of %s is not the opening '---' delimiter" % self.command_path,
        )
        self.assertTrue(
            any(line.strip() == "---" for line in lines[1:]),
            "no closing '---' delimiter after line 1 in %s" % self.command_path,
        )

    def test_frontmatter_is_a_mapping(self):
        # The parsed frontmatter is a YAML mapping, not a scalar or a list.
        self.assertIsInstance(
            self.frontmatter,
            dict,
            "frontmatter of %s did not parse to a mapping" % self.command_path,
        )

    def test_frontmatter_has_non_empty_description(self):
        # B1 output: a non-empty 'description' key.
        self.assertIn(
            "description",
            self.frontmatter,
            "frontmatter of %s has no 'description' key; keys: %r"
            % (self.command_path, sorted(self.frontmatter)),
        )
        description = self.frontmatter["description"]
        self.assertIsInstance(description, str, "'description' is not a string")
        self.assertTrue(
            description.strip(),
            "'description' in %s is empty" % self.command_path,
        )

    def test_frontmatter_mode_is_architect(self):
        # B1 output: 'mode: Architect', so the command runs in the planning
        # mode rather than editing code on sight.
        self.assertEqual(
            str(self.frontmatter.get("mode", "")).strip(),
            "Architect",
            "frontmatter of %s does not declare mode: Architect; got %r"
            % (self.command_path, self.frontmatter.get("mode")),
        )


# --------------------------------------------------------------------------- #
# B1 — edge cases: malformed frontmatter is rejected with the path named
# --------------------------------------------------------------------------- #

class B1FrontmatterEdgeTests(unittest.TestCase):
    """B1 edges (plans/harvest-roo-templates.md): the loader rejects a missing
    delimiter and unparseable YAML, naming the offending path in the error.

    These run against synthetic files in a temp directory, so they hold before
    the real command file exists and keep holding after it does.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _write(self, content):
        """Write *content* to a temp .md file and return its path."""
        path = Path(self._tmp.name) / "command.md"
        path.write_text(content, encoding="utf-8")
        return path

    def test_missing_file_fails_with_file_not_found(self):
        # A path that does not exist raises FileNotFoundError, not a
        # frontmatter error: the two failure classes stay distinct. The real
        # (absent) command path is used, so this is also a live check of the
        # B1 pre-condition.
        with self.assertRaises(FileNotFoundError):
            load_harvest_command(COMMAND_PATH)

    def test_missing_opening_delimiter_fails_with_path_named(self):
        # Edge (B1): a file that does not start with '---' fails.
        path = self._write(
            "description: no opening delimiter\nmode: Architect\n---\n\nbody\n"
        )
        with self.assertRaises(HarvestFrontmatterError) as ctx:
            load_harvest_command(path)
        self.assertIn(
            str(path), str(ctx.exception),
            "error must name the offending path; got: %s" % ctx.exception,
        )

    def test_missing_closing_delimiter_fails_with_path_named(self):
        # Edge (B1): a file whose frontmatter is never closed fails.
        path = self._write(
            "---\ndescription: no closing delimiter\nmode: Architect\n\nbody\n"
        )
        with self.assertRaises(HarvestFrontmatterError) as ctx:
            load_harvest_command(path)
        self.assertIn(
            str(path), str(ctx.exception),
            "error must name the offending path; got: %s" % ctx.exception,
        )

    def test_unparseable_frontmatter_fails_with_path_named(self):
        # Error (B1): unparseable YAML in the frontmatter fails with the path
        # named in the error.
        path = self._write(
            "---\ndescription: [unclosed list\n  mode: Architect\n---\n\nbody\n"
        )
        with self.assertRaises(HarvestFrontmatterError) as ctx:
            load_harvest_command(path)
        self.assertIn(
            str(path), str(ctx.exception),
            "error must name the offending path; got: %s" % ctx.exception,
        )

    def test_valid_file_parses_to_mapping_and_body(self):
        # Guard: the loader's happy path returns a mapping plus the body text,
        # so B3-B8 can assert on ``body`` against the real file.
        path = self._write(
            "---\ndescription: a command\nmode: Architect\n---\n\nbody line\n"
        )
        frontmatter, body = load_harvest_command(path)
        self.assertEqual(frontmatter["description"], "a command")
        self.assertEqual(frontmatter["mode"], "Architect")
        self.assertIn("body line", body)


if __name__ == "__main__":
    unittest.main()
