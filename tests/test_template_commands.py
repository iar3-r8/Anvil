"""Tests for the provisioned roo template command files.

This module is the home for every behaviour of
``plans/adopt-harvest-findings.md`` that is verified against the *content* of
``templates/roo_template/commands/*.md``:

  * B1 — ``pull-request-builder.md`` ships in the template, generic, with
    valid frontmatter (implemented below);
  * B2 — no dead ``.roo/commands/`` reference;
  * B3 — ``execute-github-task.md`` names itself and the GitHub MCP server;
  * B4 — ``write-github-task.md`` names itself;
  * B5 — ``github-bug-report.md`` carries Environment fields, Impact and
    Definition of Done.

No existing module pins the *content* of the template command files:
``tests/test_provision.py`` only asserts that a provisioned target receives
a file, and ``tests/test_harvest_command.py`` points at ``.roo/``. This
module reuses that latter module's frontmatter-loader shape and key-phrase
convention: every assertion is on the parsed frontmatter structure and on
key phrases, never on raw bytes, so the green step has latitude in the
prose. The frontmatter shape follows ``.roo/commands/create-pull-request.md``
(a ``---``-delimited YAML block at the top of the file).
"""

import tempfile
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The directory the template commands ship in (plan §Scope).
COMMANDS_DIR = REPO_ROOT / "templates" / "roo_template" / "commands"

#: B1 target (plan §Behaviors 1): added verbatim from the source repo's
#: ``.roo/commands/pull-request-builder.md``.
PULL_REQUEST_BUILDER_PATH = COMMANDS_DIR / "pull-request-builder.md"


class TemplateCommandFrontmatterError(Exception):
    """A template command file's frontmatter is malformed: a ``---``
    delimiter is missing, the YAML does not parse, or the parsed
    frontmatter is not a mapping. The offending path is always named in
    the message."""


# --------------------------------------------------------------------------- #
# Shared loader: parse one markdown command file into (frontmatter, body)
# --------------------------------------------------------------------------- #

def load_template_command(path):
    """Read and parse *path* (a roo markdown command file).

    Returns a ``(frontmatter, body)`` tuple: *frontmatter* is the parsed
    YAML mapping between the opening ``---`` on line 1 and the closing
    ``---``; *body* is the markdown text after the closing delimiter, as a
    string.

    Raises:
        FileNotFoundError: the file is missing.
        TemplateCommandFrontmatterError: the opening or closing ``---``
            delimiter is absent, the frontmatter does not parse as YAML,
            or it does not parse to a mapping. The path is always named
            in the message.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise TemplateCommandFrontmatterError(
            "missing opening '---' delimiter on line 1 of %s" % path
        )
    close_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            close_index = index
            break
    if close_index is None:
        raise TemplateCommandFrontmatterError(
            "missing closing '---' delimiter in %s" % path
        )
    frontmatter_text = "\n".join(lines[1:close_index])
    try:
        frontmatter = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        raise TemplateCommandFrontmatterError(
            "frontmatter of %s does not parse as YAML: %s" % (path, exc)
        ) from exc
    if not isinstance(frontmatter, dict):
        raise TemplateCommandFrontmatterError(
            "frontmatter of %s is not a YAML mapping" % path
        )
    body = "\n".join(lines[close_index + 1:])
    return frontmatter, body


# --------------------------------------------------------------------------- #
# Base test case: loads and parses one template command file
# --------------------------------------------------------------------------- #

class TemplateCommandTestCase(unittest.TestCase):
    """Shared loading for a template command file.

    Subclasses set ``command_path``; ``setUp`` loads it once so every test
    asserts on the parsed frontmatter and body, and a missing or malformed
    document surfaces at load time. Behaviours B2-B5 subclass this pointed
    at the other command files and assert on ``self.body``.
    """

    command_path = None

    def setUp(self):
        if self.command_path is None:
            self.skipTest("abstract base class; run a concrete subclass")
        self.assertTrue(
            self.command_path.is_file(),
            "template command file does not exist or is not a regular file: %s"
            % self.command_path,
        )
        self.frontmatter, self.body = load_template_command(self.command_path)


# --------------------------------------------------------------------------- #
# B1 — pull-request-builder.md ships in the template, generic
# --------------------------------------------------------------------------- #

class B1PullRequestBuilderTests(TemplateCommandTestCase):
    """B1 (plans/adopt-harvest-findings.md): ``pull-request-builder.md``
    ships in the template.

    The file is added verbatim from
    ``iar3-r8/Healthcare-Systems-R8@main``
    ``.roo/commands/pull-request-builder.md`` (plan §Interface-facts:
    ``description`` frontmatter only, no ``mode:``; sections Structure /
    Content Rules / Example Format / What to Include / What to Exclude /
    Execution; sole path example ``src/api/``).

    Expected red reason: ``templates/roo_template/commands/`` holds four
    files and no ``pull-request-builder.md``, so every test fails in
    ``setUp`` with the file-not-found assertion. That is the intended
    failure mode — the green step creates the file, nothing else.
    """

    command_path = PULL_REQUEST_BUILDER_PATH

    # -- B1 output: the file ships ---------------------------------------- #

    def test_file_is_a_regular_file(self):
        # B1 output: the path is a file, not a directory or a missing
        # path. setUp already asserted this; the explicit test keeps the
        # requirement named in the suite.
        self.assertTrue(
            self.command_path.is_file(),
            "template command file does not exist or is not a regular file: %s"
            % self.command_path,
        )

    # -- B1 output: valid frontmatter ------------------------------------- #

    def test_frontmatter_is_bounded_by_both_delimiters(self):
        # Edge (B1): frontmatter is delimited by '---' on the first line
        # and a closing '---'. The loader would have raised for either
        # missing one; this test pins the requirement on the file itself.
        lines = self.command_path.read_text(encoding="utf-8").splitlines()
        self.assertTrue(lines, "template command file is empty")
        self.assertEqual(
            lines[0].strip(),
            "---",
            "first line of %s is not the opening '---' delimiter"
            % self.command_path,
        )
        self.assertTrue(
            any(line.strip() == "---" for line in lines[1:]),
            "no closing '---' delimiter after line 1 in %s" % self.command_path,
        )

    def test_frontmatter_is_a_mapping(self):
        # B1 output: the '---'-delimited frontmatter parses to a mapping.
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

    def test_frontmatter_is_description_only(self):
        # B1 output (plan §Interface-facts): the source file is generic —
        # 'description' frontmatter only, no 'mode:'. Asserting the exact
        # key set keeps the adopted file generic: a 'mode:' or any other
        # field from the source would fail here.
        self.assertEqual(
            set(self.frontmatter),
            {"description"},
            "frontmatter of %s must be 'description' only (no 'mode:' or "
            "other keys); got: %r" % (self.command_path, sorted(self.frontmatter)),
        )

    # -- B1 output: the body names the expected sections ------------------ #

    def test_body_names_structure_section(self):
        self.assertIn(
            "Structure",
            self.body,
            "body of %s does not name the Structure section" % self.command_path,
        )

    def test_body_names_content_rules_section(self):
        self.assertIn(
            "Content Rules",
            self.body,
            "body of %s does not name the Content Rules section" % self.command_path,
        )

    def test_body_names_execution_section(self):
        self.assertIn(
            "Execution",
            self.body,
            "body of %s does not name the Execution section" % self.command_path,
        )

    def test_body_names_context_example_heading(self):
        # B1 output: the example format shows the '### Context' heading.
        self.assertIn(
            "### Context",
            self.body,
            "body of %s does not carry the '### Context' example heading"
            % self.command_path,
        )

    def test_body_names_changes_example_heading(self):
        # B1 output: the example format shows the '### Changes' heading.
        self.assertIn(
            "### Changes",
            self.body,
            "body of %s does not carry the '### Changes' example heading"
            % self.command_path,
        )

    # -- B1 error guards: no repo-specific token survives ----------------- #

    def test_file_has_no_healthcare_token(self):
        # Error (B1): the source is a healthcare repo; its name must not
        # arrive in the generic template copy.
        self.assertNotIn(
            "Healthcare",
            self.body,
            "body of %s contains the repo-specific token 'Healthcare'"
            % self.command_path,
        )

    def test_file_has_no_iar3_r8_token(self):
        # Error (B1): the source owner must not arrive either.
        self.assertNotIn(
            "iar3-r8",
            self.body,
            "body of %s contains the repo-specific token 'iar3-r8'"
            % self.command_path,
        )

    def test_file_has_no_src_frontend_path(self):
        # Error (B1): 'src/frontend/' is a source-repo path and must not
        # survive into the template.
        self.assertNotIn(
            "src/frontend/",
            self.body,
            "body of %s contains the source path 'src/frontend/'"
            % self.command_path,
        )

    def test_file_names_src_api_example(self):
        # B1 output (plan §Interface-facts): the generic 'src/api/' example
        # is the only path the source file contains — so it must be present
        # in the shipped copy.
        self.assertIn(
            "src/api/",
            self.body,
            "body of %s does not carry the 'src/api/' example path"
            % self.command_path,
        )


# --------------------------------------------------------------------------- #
# B1 — edge cases: the loader's error contract
# --------------------------------------------------------------------------- #

class B1LoaderEdgeTests(unittest.TestCase):
    """B1 edges (plans/adopt-harvest-findings.md): the template-command
    loader rejects a missing file and malformed frontmatter, naming the
    offending path in the error.

    These run against synthetic files in a temp directory, so they hold
    before the real command file exists and keep holding after it does.
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
        # frontmatter error: the two failure classes stay distinct. The
        # absent path is synthetic, so this holds in both red and green
        # states.
        absent_path = Path(self._tmp.name) / "absent.md"
        with self.assertRaises(FileNotFoundError):
            load_template_command(absent_path)

    def test_missing_opening_delimiter_fails_with_path_named(self):
        # Edge (B1): a file that does not start with '---' fails.
        path = self._write(
            "description: no opening delimiter\n---\n\nbody\n"
        )
        with self.assertRaises(TemplateCommandFrontmatterError) as ctx:
            load_template_command(path)
        self.assertIn(
            str(path), str(ctx.exception),
            "error must name the offending path; got: %s" % ctx.exception,
        )

    def test_missing_closing_delimiter_fails_with_path_named(self):
        # Edge (B1): a file whose frontmatter is never closed fails.
        path = self._write(
            "---\ndescription: no closing delimiter\n\nbody\n"
        )
        with self.assertRaises(TemplateCommandFrontmatterError) as ctx:
            load_template_command(path)
        self.assertIn(
            str(path), str(ctx.exception),
            "error must name the offending path; got: %s" % ctx.exception,
        )

    def test_valid_file_parses_to_mapping_and_body(self):
        # Guard: the loader's happy path returns a mapping plus the body
        # text, so B1-B5 can assert on ``body`` against the real files.
        path = self._write(
            "---\ndescription: a command\n---\n\nbody line\n"
        )
        frontmatter, body = load_template_command(path)
        self.assertEqual(frontmatter["description"], "a command")
        self.assertIn("body line", body)
