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

import re
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

#: B3 target (plan §Behaviors 3): the command file whose body still names
#: the stale ``/github-task-executor`` and "GitHub CLI".
EXECUTE_GITHUB_TASK_PATH = COMMANDS_DIR / "execute-github-task.md"

#: B4 target (plan §Behaviors 4): the command file whose body still names
#: the stale ``/github-task-writing``.
WRITE_GITHUB_TASK_PATH = COMMANDS_DIR / "write-github-task.md"

#: B5 target (plan §Behaviors 5): the bug-report template whose fenced
#: block gains Environment placeholder fields, an Impact section and a
#: Definition of Done checklist.
GITHUB_BUG_REPORT_PATH = COMMANDS_DIR / "github-bug-report.md"

#: B1 target (plans/implement-next-issue.md §Behaviors 1): the new command
#: file that ships in the template with frontmatter exactly
#: {description, mode} and mode 'tdd-manager'.
IMPLEMENT_NEXT_ISSUE_PATH = COMMANDS_DIR / "implement-next-issue.md"

#: B5: the four placeholder field labels that must appear as bold bullets
#: under ``### Environment`` (plan §Behaviors 5; each is the line prefix
#: ``- **<Label>**``).
B5_ENVIRONMENT_FIELD_LABELS = (
    "Component",
    "Python Version",
    "OS",
    "Related Dependencies",
)

#: B5: the four Definition of Done checklist items, in order — each is a
#: ``- [ ]`` checkbox line that must *start* with the phrase (key-phrase
#: convention: assert the phrase and its ``- [ ]`` shape, never raw bytes).
B5_DEFINITION_OF_DONE_ITEMS = (
    "Root cause identified and documented",
    "Fix implemented and passing all tests",
    "Regression tests added",
    "Related documentation updated",
)

#: B5 guard: a concrete Python version number (e.g. ``3.10``, ``3.10.4``,
#: ``3.8.1``). Placeholder spellings such as ``3.x`` carry no digits after
#: the dot and do not match — that is the point: the value is a template,
#: not a shipped answer.
B5_CONCRETE_PYTHON_VERSION_RE = re.compile(r"\b3\.\d")

#: B5 guard: a concrete OS name anywhere in the Environment section.
B5_CONCRETE_OS_RE = re.compile(r"\b(linux|macos|windows)\b", re.IGNORECASE)

#: B5 guard: concrete package names that must not arrive as shipped values
#: in the four Environment bullets. The source's example values are hints
#: for the filler, not values to ship (plan §Scope: "every field added is
#: a placeholder").
B5_CONCRETE_PACKAGE_BLACKLIST = (
    "requests",
    "flask",
    "django",
    "numpy",
    "pandas",
)

#: The tree B2 scans: every file under it, read as text, no skips
#: (plan §Behaviors 2). The tree is small and is markdown/XML only.
ROO_TEMPLATE_DIR = REPO_ROOT / "templates" / "roo_template"

#: B4 (plans/implement-next-issue.md §Behaviors 4): the five ranking
#: criteria in their required order. Each phrase is a key phrase the green
#: step can satisfy with prose latitude; asserting the sequence (position
#: i < position i+1) pins the ordering without pinning exact wording.
B4_RANKING_CRITERIA_IN_ORDER = (
    "bug over feature",
    "priority label",
    "milestone",
    "blocked",
    "oldest created_at",
)

#: B4: the explicit ordering word — an "outranks"/"before" style
#: statement that each earlier criterion outranks the later ones. The body
#: may pick either spelling; one occurrence of either suffices.
B4_ORDERING_PHRASES = ("outranks", "before")

#: B5 (plans/implement-next-issue.md §Behaviors 5): the key phrases that
#: pin the "list open pull requests" instruction — the body may name the
#: ``list_pull_requests`` function or the plain-English "open pull
#: request" phrase; either spelling suffices, so the green step keeps
#: prose latitude.
B5_PR_LISTING_PHRASES = ("list_pull_requests", "open pull request")

#: B5: the three closer keywords — ``Fixes``, ``Closes`` and
#: ``Resolves`` — each of which may reference an issue from an open
#: PR's title or body. All three are pinned (asserted lower-cased).
B5_CLOSER_KEYWORDS = ("fixes", "closes", "resolves")

#: B5: the issue-number reference shape — a ``#`` followed by the
#: reference (``#N``, ``#123``). The plan gives the shape
#: ``Resolves #N``; pinning the ``#`` shape at key-phrase level keeps
#: the green step latitude in how the placeholder is spelled.
B5_HASH_REF_RE = re.compile(r"#\s*\w")

#: B5: the exclusion verbs — the instruction to drop the referenced
#: issues may read "exclude*" or "filter*"; either suffices.
B5_EXCLUSION_PHRASES = ("exclu", "filter")

#: B5 error arm: the explicit-prohibition tokens — the error arm must
#: state "never proceed on the unfiltered issue list" with one of
#: these; the green step picks the wording.
B5_PROHIBITION_PHRASES = ("never", "do not", "must not")

#: B2: a ``.roo/commands/<name>`` reference, anchored at the path
#: boundary. ``<name>`` is a command filename (e.g.
#: ``pull-request-builder.md``), so the match ends at end-of-line,
#: whitespace, or a closing quote/backtick/paren — whatever terminates
#: the path in markdown or XML prose (the references in the tree sit in
#: prose lines and in backtick-quoted spans, e.g.
#: ``templates/roo_template/commands/create-pull-request.md:49``).
COMMAND_REF_RE = re.compile(
    r"\.roo/commands/([A-Za-z0-9._-]+?)(?=$|[\s)\]\"'`])"
)

#: B2 allowlist: referenced command names that live outside
#: ``templates/roo_template/commands/`` by design. ``update_roo_rules.md``
#: ships from ``templates/update_roo_rules.md`` (one level up) and is
#: placed into a *target's* ``.roo/commands/`` by provisioning — see
#: ``tests/test_provision.py`` ``test_installs_the_roo_rules_command``.
#: A second entry would mean a referenced command is not shipped, which
#: is the defect this test exists to catch (plan §Assumptions).
B2_ALLOWLISTED_COMMANDS = frozenset({"update_roo_rules.md"})


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


# --------------------------------------------------------------------------- #
# B2 — no dead .roo/commands/ reference in the roo template tree
# --------------------------------------------------------------------------- #

class B2DeadReferenceTests(unittest.TestCase):
    """B2 (plans/adopt-harvest-findings.md): no dead ``.roo/commands/``
    reference in the roo template tree.

    Boundary pin of B1's effect, with no production change of its own:
    ``templates/roo_template/commands/create-pull-request.md:49`` points
    at ``pull-request-builder.md``, which B1 shipped. The test is green
    from inception on this branch and turns red the moment someone
    references a command the template does not ship.

    Scan: every file under ``templates/roo_template/``, read as text,
    recursively, skipping nothing — the tree is small and is markdown
    and XML only, so no binary hazard. Each ``.roo/commands/<name>``
    occurrence is extracted with ``COMMAND_REF_RE`` (path up to
    end-of-line, whitespace, or a quote/paren boundary). Every
    referenced ``<name>`` must exist in
    ``templates/roo_template/commands/``, except the allowlisted
    ``update_roo_rules.md``.
    """

    def test_template_tree_scanned(self):
        # Guard: the scan actually has a tree to walk — a missing or
        # empty tree would vacuously pass the reference check.
        files = sorted(
            p for p in ROO_TEMPLATE_DIR.rglob("*") if p.is_file()
        )
        self.assertTrue(
            files,
            "template tree %s holds no files; the B2 scan is vacuous"
            % ROO_TEMPLATE_DIR,
        )

    def test_every_command_reference_resolves(self):
        # B2 output: every ``.roo/commands/<name>`` reference in the
        # template tree resolves to a file in
        # ``templates/roo_template/commands/``, or is allowlisted.
        dangling = []
        for path in sorted(ROO_TEMPLATE_DIR.rglob("*")):
            if not path.is_file():
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            for lineno, line in enumerate(lines, start=1):
                for match in COMMAND_REF_RE.finditer(line):
                    name = match.group(1)
                    if name in B2_ALLOWLISTED_COMMANDS:
                        continue
                    if not (COMMANDS_DIR / name).is_file():
                        dangling.append(
                            "%s:%d -> .roo/commands/%s"
                            % (
                                path.relative_to(REPO_ROOT),
                                lineno,
                                name,
                            )
                        )
        self.assertEqual(
            dangling,
            [],
            "dangling .roo/commands/ reference(s) in the template tree"
            " (target missing from templates/roo_template/commands/ and"
            " not allowlisted): %s" % "; ".join(dangling),
        )


# --------------------------------------------------------------------------- #
# B3 — execute-github-task.md names itself and the GitHub MCP server
# B4 — write-github-task.md names itself
# --------------------------------------------------------------------------- #

class B3B4CommandNameTests(unittest.TestCase):
    """B3 + B4 (plans/adopt-harvest-findings.md): the two template command
    files still name the *old* commands from the source repo.

    B3: ``execute-github-task.md`` — the body names ``/execute-github-task``
    (not the stale ``/github-task-executor``), names "GitHub MCP server"
    (not bare "GitHub CLI"), and carries no ``pytest`` wording: the source
    repo's test runner is that repo's toolchain and must not arrive by
    accident (plan §Scope, out of scope).

    B4: ``write-github-task.md`` — the body names ``/write-github-task``
    (not the stale ``/github-task-writing``).

    Both files exist, so the red reason is the assertion mismatch (wrong
    name present / expected name absent), not a missing file. B3 and B4
    land in the same green commit per the plan (§Behaviors 4: "Fold it
    into B3's red/green cycle"), which is why they share one class.
    Key-phrase convention as in B1/B2: assert phrases, never raw bytes.
    """

    def setUp(self):
        # Both targets must exist for this cycle: the red reason is the
        # assertion mismatch, not FileNotFoundError (plan requirement).
        for path in (EXECUTE_GITHUB_TASK_PATH, WRITE_GITHUB_TASK_PATH):
            self.assertTrue(
                path.is_file(),
                "template command file does not exist or is not a regular file: %s"
                % path,
            )
        self.execute_frontmatter, self.execute_body = load_template_command(
            EXECUTE_GITHUB_TASK_PATH
        )
        self.write_frontmatter, self.write_body = load_template_command(
            WRITE_GITHUB_TASK_PATH
        )

    # -- B3 output: the body names the new command ------------------------ #

    def test_execute_body_names_execute_github_task(self):
        # B3 output (plan §Behaviors 3): the body names
        # '/execute-github-task'.
        self.assertIn(
            "/execute-github-task",
            self.execute_body,
            "body of %s does not name '/execute-github-task'"
            % EXECUTE_GITHUB_TASK_PATH,
        )

    def test_execute_body_has_no_stale_github_task_executor(self):
        # B3 output (plan §Behaviors 3): neither old name may survive —
        # the stale '/github-task-executor' is gone (lines 8 and 13
        # today).
        self.assertNotIn(
            "github-task-executor",
            self.execute_body,
            "body of %s still contains the stale command name"
            " 'github-task-executor'" % EXECUTE_GITHUB_TASK_PATH,
        )

    # -- B3 output: GitHub MCP server, not bare GitHub CLI ----------------- #

    def test_execute_body_names_github_mcp_server(self):
        # B3 output (plan §Behaviors 3): the body names "GitHub MCP
        # server" (line 17 today says "using GitHub CLI").
        self.assertIn(
            "GitHub MCP server",
            self.execute_body,
            "body of %s does not name 'GitHub MCP server'"
            % EXECUTE_GITHUB_TASK_PATH,
        )

    def test_execute_body_has_no_bare_github_cli(self):
        # B3 output (plan §Behaviors 3): no bare "GitHub CLI" left — the
        # assertion is the two-word token, so other GitHub phrasing the
        # file legitimately carries (e.g. "GitHub issue", "github mcp")
        # stays legal.
        self.assertNotIn(
            "GitHub CLI",
            self.execute_body,
            "body of %s still contains bare 'GitHub CLI'"
            % EXECUTE_GITHUB_TASK_PATH,
        )

    # -- B3 error guard: the source's pytest wording is not adopted ------- #

    def test_execute_body_does_not_name_pytest(self):
        # Error (B3, plan §Scope): the source's pytest wording is NOT
        # adopted — no assertion requires a runner name, and this guard
        # asserts the body does not name 'pytest', so that repo's
        # toolchain cannot arrive by accident. The current body names
        # pytest in the Task Execution Guidelines, so this guard fails
        # today too; it turns green the moment that line is reworded
        # without a runner name.
        self.assertNotIn(
            "pytest",
            self.execute_body,
            "body of %s names 'pytest' — the source repo's toolchain"
            " must not be adopted" % EXECUTE_GITHUB_TASK_PATH,
        )

    # -- B4 output: the body names the new command ------------------------ #

    def test_write_body_names_write_github_task(self):
        # B4 output (plan §Behaviors 4): the body names
        # '/write-github-task' (line 11 today says
        # '/github-task-writing <description>').
        self.assertIn(
            "/write-github-task",
            self.write_body,
            "body of %s does not name '/write-github-task'"
            % WRITE_GITHUB_TASK_PATH,
        )

    def test_write_body_has_no_stale_github_task_writing(self):
        # B4 output (plan §Behaviors 4): the stale '/github-task-writing'
        # name is gone.
        self.assertNotIn(
            "github-task-writing",
            self.write_body,
            "body of %s still contains the stale command name"
            " 'github-task-writing'" % WRITE_GITHUB_TASK_PATH,
        )


# --------------------------------------------------------------------------- #
# B5 — github-bug-report.md: Environment fields, Impact, Definition of Done
# --------------------------------------------------------------------------- #

class B5BugReportSectionsTests(TemplateCommandTestCase):
    """B5 (plans/adopt-harvest-findings.md): the bug-report template's
    fenced block carries Environment placeholder fields, an Impact section
    and a Definition of Done checklist.

    Today the file's ``### Environment`` holds only the "only include if
    relevant" note (lines 42–43) with no field labels, and
    ``### Potential Hypotheses`` (lines 63–74) is the last template section
    — no Impact, no Definition of Done. Expected red reason: the
    missing-section / missing-bullet assertions fail; the file itself
    exists and loads, so this is NOT a file-not-found failure.

    The green step copies the source's sections verbatim from
    ``iar3-r8/Healthcare-Systems-R8@main`` ``.roo/commands/``
    ``github-bug-report.md`` with all values as placeholders. Key-phrase
    convention as in B1–B4: assert phrases and character offsets, never
    raw bytes, so the green step keeps prose latitude.

    Fence note: the fenced template block opens at ```` ```markdown ```` and
    its *closing* fence is the last standalone ```` ``` ```` line between the
    opening fence and the ``## Guidelines`` heading — the block deliberately
    contains inner code spans (a python block, file-path quotes) that are
    part of the template's own text, and the body carries later fences in
    the Guidelines prose; neither may be mistaken for the closing fence.
    """

    command_path = GITHUB_BUG_REPORT_PATH

    # -- helpers ------------------------------------------------------------ #

    def _section_span(self, heading):
        """Return ``(start, end)`` — the character offsets in ``self.body``
        of the section whose heading line is exactly ``heading``.

        ``start`` is the start of the heading line; ``end`` is the start of
        the next ``### `` heading line, or ``len(self.body)`` if this is the
        last section. Raises ``AssertionError`` when the heading is absent,
        so a missing section names itself in the failure.
        """
        marker = heading + "\n"
        start = self.body.find(marker)
        self.assertNotEqual(
            start,
            -1,
            "B5: section '%s' not found in the body of %s"
            % (heading, self.command_path),
        )
        rest = self.body[start + len(marker):]
        nxt = rest.find("\n### ")
        end = start + len(marker) + nxt if nxt != -1 else len(self.body)
        return start, end

    def _fence_span(self, heading):
        """Return ``(start, end)`` — the character offsets in
        ``self.body`` of the fenced template block (from the line after the
        ```` ```markdown ```` fence to the standalone ```` ``` ```` line that
        closes it), verified against the section whose heading line is
        ``heading``.

        The closing fence is the last *standalone* fence line — a line that
        is exactly three backticks — between the opening fence and the
        ``## Guidelines`` heading. Anchoring on that heading rather than on
        the section heading matters because the block deliberately contains
        inner code spans (a ```` ```python ```` block, the ```` ``` ````
        span around ``<file:path:line>``) and the body carries later fences
        in the Guidelines prose; neither may be mistaken for the closing
        fence. Raises ``AssertionError`` when the heading is absent, when
        the template block has no standalone closing fence before
        ``## Guidelines``, or when the heading sits outside the block.
        """
        open_idx = self.body.find("```markdown\n")
        self.assertNotEqual(
            open_idx,
            -1,
            "B5: opening '```markdown' fence not found in %s"
            % self.command_path,
        )
        block_start = open_idx + len("```markdown\n")
        guidelines_idx = self.body.find("## Guidelines")
        self.assertNotEqual(
            guidelines_idx,
            -1,
            "B5: '## Guidelines' heading not found in %s — the closing "
            "fence is anchored to it" % self.command_path,
        )
        marker = heading + "\n"
        heading_idx = self.body.find(marker)
        self.assertNotEqual(
            heading_idx,
            -1,
            "B5: section '%s' not found in the body of %s"
            % (heading, self.command_path),
        )
        close_idx = self.body.rfind("\n```", block_start, guidelines_idx)
        while close_idx != -1:
            # A standalone fence line is exactly three backticks: the line
            # must end right after them. This rejects the '```python'
            # opening fence (next char 'p') and any longer fence, while the
            # inner standalone fences lose to the true closing fence, which
            # is the LAST one before '## Guidelines'.
            next_char = self.body[close_idx + 4 : close_idx + 5]
            if next_char in ("", "\n"):
                break
            close_idx = self.body.rfind("\n```", block_start, close_idx)
        self.assertNotEqual(
            close_idx,
            -1,
            "B5: no standalone closing '```' fence between the opening "
            "fence and '## Guidelines' in %s" % self.command_path,
        )
        fence_end = close_idx + len("\n```")
        self.assertGreaterEqual(
            heading_idx,
            block_start,
            "B5: section '%s' sits before the opening fence (outside the "
            "fenced template block) in %s"
            % (heading, self.command_path),
        )
        self.assertLess(
            heading_idx,
            fence_end,
            "B5: section '%s' sits after the closing fence (outside the "
            "fenced template block) in %s"
            % (heading, self.command_path),
        )
        return block_start, fence_end

    def _environment_section(self):
        """Return the text of the ``### Environment`` section (up to the
        next ``### `` heading)."""
        start, end = self._section_span("### Environment")
        return self.body[start:end]

    def _environment_bullet_lines(self):
        """Return a ``{label: line}`` mapping of the bullet lines of the
        ``### Environment`` section. Each of the four field labels must own
        a line starting ``- **<Label>**:** — missing labels fail naming
        the label and the section text."""
        env_text = self._environment_section()
        lines = {}
        for label in B5_ENVIRONMENT_FIELD_LABELS:
            prefix = "- **%s**:" % label
            line = next(
                (
                    stripped
                    for stripped in env_text.splitlines()
                    if stripped.startswith(prefix)
                ),
                None,
            )
            self.assertIsNotNone(
                line,
                "B5: '### Environment' of %s has no bullet line starting "
                "with '%s'; section text:\n%s"
                % (self.command_path, prefix, env_text),
            )
            lines[label] = line
        return lines

    # -- B5 output: the four Environment field labels ----------------------- #

    def test_environment_names_component_field(self):
        self._environment_bullet_lines()["Component"]

    def test_environment_names_python_version_field(self):
        self._environment_bullet_lines()["Python Version"]

    def test_environment_names_os_field(self):
        self._environment_bullet_lines()["OS"]

    def test_environment_names_related_dependencies_field(self):
        self._environment_bullet_lines()["Related Dependencies"]

    # -- B5 output: the Impact section -------------------------------------- #

    def test_impact_section_has_severity_bullet(self):
        # The severity bullet must offer the Critical/High/Medium/Low
        # placeholder menu.
        start, end = self._section_span("### Impact")
        impact = self.body[start:end]
        line = next(
            (
                stripped
                for stripped in impact.splitlines()
                if stripped.startswith("- <Severity:")
            ),
            None,
        )
        self.assertIsNotNone(
            line,
            "B5: '### Impact' of %s has no bullet line starting with "
            "'- <Severity:'; section text:\n%s" % (self.command_path, impact),
        )
        self.assertIn("Critical/High/Medium/Low", line)

    def test_impact_section_has_affected_users_bullet(self):
        start, end = self._section_span("### Impact")
        impact = self.body[start:end]
        line = next(
            (
                stripped
                for stripped in impact.splitlines()
                if stripped.startswith("- <Affected users")
            ),
            None,
        )
        self.assertIsNotNone(
            line,
            "B5: '### Impact' of %s has no bullet line starting with "
            "'- <Affected users...'; section text:\n%s"
            % (self.command_path, impact),
        )

    def test_impact_section_has_workaround_bullet(self):
        # The workaround bullet must offer the Yes/No placeholder menu.
        start, end = self._section_span("### Impact")
        impact = self.body[start:end]
        line = next(
            (
                stripped
                for stripped in impact.splitlines()
                if stripped.startswith("- <Workaround available:")
            ),
            None,
        )
        self.assertIsNotNone(
            line,
            "B5: '### Impact' of %s has no bullet line starting with "
            "'- <Workaround available:'; section text:\n%s"
            % (self.command_path, impact),
        )
        self.assertIn("Yes/No", line)

    # -- B5 output: the Definition of Done checklist ------------------------ #

    def test_definition_of_done_has_root_cause_checkbox(self):
        start, end = self._section_span("### Definition of Done")
        dod = self.body[start:end]
        self.assertIn(
            "- [ ] %s" % B5_DEFINITION_OF_DONE_ITEMS[0],
            dod,
            "B5: '### Definition of Done' of %s is missing the root-cause "
            "checkbox; section text:\n%s" % (self.command_path, dod),
        )

    def test_definition_of_done_has_fix_checkbox(self):
        start, end = self._section_span("### Definition of Done")
        dod = self.body[start:end]
        self.assertIn(
            "- [ ] %s" % B5_DEFINITION_OF_DONE_ITEMS[1],
            dod,
            "B5: '### Definition of Done' of %s is missing the fix "
            "checkbox; section text:\n%s" % (self.command_path, dod),
        )

    def test_definition_of_done_has_regression_checkbox(self):
        start, end = self._section_span("### Definition of Done")
        dod = self.body[start:end]
        self.assertIn(
            "- [ ] %s" % B5_DEFINITION_OF_DONE_ITEMS[2],
            dod,
            "B5: '### Definition of Done' of %s is missing the regression "
            "tests checkbox; section text:\n%s" % (self.command_path, dod),
        )

    def test_definition_of_done_has_docs_checkbox(self):
        start, end = self._section_span("### Definition of Done")
        dod = self.body[start:end]
        self.assertIn(
            "- [ ] %s" % B5_DEFINITION_OF_DONE_ITEMS[3],
            dod,
            "B5: '### Definition of Done' of %s is missing the "
            "documentation checkbox; section text:\n%s"
            % (self.command_path, dod),
        )

    # -- B5 output: section positions --------------------------------------- #

    def test_impact_section_sits_after_potential_hypotheses(self):
        # Both sections must exist; the new section follows the existing
        # last template section by character offset.
        hypo_start, _ = self._section_span("### Potential Hypotheses")
        impact_start, _ = self._section_span("### Impact")
        self.assertGreater(
            impact_start,
            hypo_start,
            "B5: '### Impact' must sit after '### Potential Hypotheses' "
            "by character offset in %s" % self.command_path,
        )

    def test_definition_of_done_sits_after_potential_hypotheses(self):
        hypo_start, _ = self._section_span("### Potential Hypotheses")
        dod_start, _ = self._section_span("### Definition of Done")
        self.assertGreater(
            dod_start,
            hypo_start,
            "B5: '### Definition of Done' must sit after "
            "'### Potential Hypotheses' by character offset in %s"
            % self.command_path,
        )

    def test_impact_section_sits_inside_fenced_block(self):
        self._fence_span("### Impact")

    def test_definition_of_done_sits_inside_fenced_block(self):
        self._fence_span("### Definition of Done")

    # -- B5 error guards: every added value is a placeholder ---------------- #

    def test_environment_bullets_carry_no_concrete_python_version(self):
        # The Python Version bullet must read as a placeholder (it carries
        # a '<' or '{' marker), and no concrete version number like
        # '3.10' may appear in the Environment section.
        env_text = self._environment_section()
        line = self._environment_bullet_lines()["Python Version"]
        self.assertTrue(
            "<" in line or "{" in line,
            "B5: the Python Version bullet in %s carries no placeholder "
            "marker ('<...' or '{...}'): %r" % (self.command_path, line),
        )
        self.assertIsNone(
            B5_CONCRETE_PYTHON_VERSION_RE.search(env_text),
            "B5: '### Environment' of %s contains a concrete Python "
            "version number — a placeholder was expected; section text:\n%s"
            % (self.command_path, env_text),
        )

    def test_environment_section_names_no_concrete_os(self):
        env_text = self._environment_section()
        self.assertIsNone(
            B5_CONCRETE_OS_RE.search(env_text),
            "B5: '### Environment' of %s names a concrete OS — a "
            "placeholder was expected; section text:\n%s"
            % (self.command_path, env_text),
        )

    def test_environment_bullets_name_no_concrete_package(self):
        # The source's example values are hints for the filler, not values
        # to ship (plan §Scope: "every field added is a placeholder").
        env_text = self._environment_section()
        self._environment_bullet_lines()  # the four bullets must exist
        offenders = [
            name
            for name in B5_CONCRETE_PACKAGE_BLACKLIST
            if re.search(r"\b%s\b" % name, env_text, re.IGNORECASE)
        ]
        self.assertEqual(
            offenders,
            [],
            "B5: '### Environment' of %s names concrete package(s) %s — "
            "placeholders were expected; section text:\n%s"
            % (self.command_path, offenders, env_text),
        )

    # -- B5 preservation: existing content survives untouched --------------- #

    def test_environment_relevance_note_survives(self):
        # The existing "only include this section if environment details
        # are relevant" note (lines 42–43 today) must stay.
        self.assertIn(
            "Only include this section if environment details are relevant",
            self._environment_section(),
            "B5: the Environment relevance note was lost from %s"
            % self.command_path,
        )

    def test_guidelines_list_survives(self):
        # The existing '## Guidelines' list must survive the additions.
        self.assertIn(
            "## Guidelines",
            self.body,
            "B5: the '## Guidelines' list was lost from %s"
            % self.command_path,
        )
        self.assertIn(
            "Never invent facts",
            self.body,
            "B5: the Guidelines list content was lost from %s"
            % self.command_path,
        )


# --------------------------------------------------------------------------- #
# B1 — implement-next-issue.md ships in the template, with valid frontmatter
# --------------------------------------------------------------------------- #

class B1ImplementNextIssueTests(TemplateCommandTestCase):
    """B1 (plans/implement-next-issue.md): ``implement-next-issue.md`` ships
    in the template with valid frontmatter.

    Expected red reason: the file does not exist yet, so every test fails in
    ``setUp`` with the file-not-found assertion (``load_template_command``
    would raise ``FileNotFoundError`` on a missing path). That is the
    intended failure mode — the green step creates the file with
    frontmatter keys exactly ``{description, mode}`` and
    ``mode: tdd-manager`` (plan §Behaviors 1), nothing else.

    Body phrases are deliberately not pinned here: behaviours 2–9 of the
    plan are separate red/green cycles with their own key-phrase tests.
    """

    command_path = IMPLEMENT_NEXT_ISSUE_PATH

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
        # B1 error: the frontmatter is delimited by '---' on the first
        # line and a closing '---'; an unclosed block would raise
        # TemplateCommandFrontmatterError at load time, naming the path.
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

    def test_frontmatter_key_set_is_description_and_mode(self):
        # B1 output (plan §Behaviors 1): the key set is exactly
        # {description, mode}. A stray key from a later cycle would fail
        # here.
        self.assertEqual(
            set(self.frontmatter),
            {"description", "mode"},
            "frontmatter of %s must have exactly the keys "
            "{'description', 'mode'}; got: %r"
            % (self.command_path, sorted(self.frontmatter)),
        )

    def test_frontmatter_mode_is_tdd_manager(self):
        # B1 output (plan §Behaviors 1): mode is 'tdd-manager' — the mode
        # slug the handoff targets (templates/roo_template/.roomodes).
        self.assertIn(
            "mode",
            self.frontmatter,
            "frontmatter of %s has no 'mode' key; keys: %r"
            % (self.command_path, sorted(self.frontmatter)),
        )
        self.assertEqual(
            self.frontmatter["mode"],
            "tdd-manager",
            "mode in %s is %r; expected 'tdd-manager'"
            % (self.command_path, self.frontmatter["mode"]),
        )


# --------------------------------------------------------------------------- #
# B2 — implement-next-issue.md body: usage names the command and its argument
# --------------------------------------------------------------------------- #

class B2ImplementNextIssueUsageTests(TemplateCommandTestCase):
    """B2 (plans/implement-next-issue.md): the usage section names
    ``/implement-next-issue`` and documents the optional free-form argument.

    Expected red reason: the body is still the stub ("Implement the next
    issue" plus a TODO line), so the usage heading and both usage phrases
    are absent — the failures are missing-phrase assertions, not a
    file-not-found. The file exists and loads (behaviour 1 is green), so
    this cycle is pure prose.

    Scope: behaviour 2 only. Ranking order, PR exclusion, the
    confirmation question, the tdd-manager handoff and the empty-queue
    prose are behaviours 3–9, each with its own later cycle.

    Key-phrase convention as in B3–B5: assert phrases on the parsed body,
    never raw bytes, so the green step keeps prose latitude.
    """

    command_path = IMPLEMENT_NEXT_ISSUE_PATH

    # -- B2 output: the usage section is present ---------------------------- #

    def test_body_has_usage_section(self):
        # B2 output: a usage section exists — the sibling command files
        # (execute-github-task.md) carry a 'Usage' heading, and the usage
        # form must sit under one here too.
        self.assertIn(
            "Usage",
            self.body,
            "body of %s does not carry a 'Usage' section" % self.command_path,
        )

    # -- B2 output: the usage names the command and its argument ------------ #

    def test_body_names_implement_next_issue(self):
        # B2 output (plan §Behaviors 2): the usage names
        # '/implement-next-issue'.
        self.assertIn(
            "/implement-next-issue",
            self.body,
            "usage of %s does not name '/implement-next-issue'"
            % self.command_path,
        )

    def test_body_documents_optional_context_argument_shape(self):
        # B2 output (plan §Behaviors 2): the free-form argument is
        # documented in the '/implement-next-issue <context>' shape.
        self.assertIn(
            "/implement-next-issue <context>",
            self.body,
            "usage of %s does not document the argument in the "
            "'/implement-next-issue <context>' shape" % self.command_path,
        )

    def test_body_states_the_argument_is_optional(self):
        # B2 output (plan §Behaviors 2): the argument is shown as
        # optional — the command also works with no argument.
        self.assertIn(
            "optional",
            self.body.lower(),
            "usage of %s does not state the argument is optional (the "
            "command must also work with no argument)" % self.command_path,
        )

    # -- B2 error guard: no required issue-number argument ------------------ #

    def test_body_has_no_required_issue_number_argument(self):
        # Error (B2, plan §Behaviors 2): a required argument such as an
        # issue number is /execute-github-task's contract
        # (templates/roo_template/commands/execute-github-task.md:8);
        # adopting its usage form here would make the argument mandatory.
        # Green by design at red time: the stub carries no usage at all,
        # and the guard must stay green once the usage lands.
        self.assertNotIn(
            "/implement-next-issue <issue-number>",
            self.body,
            "usage of %s carries the required '<issue-number>' argument "
            "shape — that is /execute-github-task's contract"
            % self.command_path,
        )


# --------------------------------------------------------------------------- #
# B3 — implement-next-issue.md body: the GitHub MCP prerequisite
# --------------------------------------------------------------------------- #

class B3ImplementNextIssuePrerequisiteTests(TemplateCommandTestCase):
    """B3 (plans/implement-next-issue.md): the body names the GitHub MCP
    server as a prerequisite and names ``.roo/rules/AGENTS.md`` as the
    source of the GitHub owner and repository name.

    The repo's intake/execution path is the MCP server, never a CLI, so the
    body must not name "GitHub CLI" — the sibling
    ``execute-github-task.md`` guard (``B3B4CommandNameTests``,
    ``tests/test_template_commands.py:581-601``) holds the same shape.

    Expected red reason: the current body is the usage section plus the
    stub intro — no prerequisites or repository-resolution prose — so the
    two present-phrase assertions fail on the missing phrases, not on a
    file-not-found. The file exists and loads (behaviours 1–2 are green).

    Scope: behaviour 3 only. The ranking chain (B4), the PR exclusion
    (B5), the context override (B6), the confirmation (B7), the handoff
    (B8) and the empty-queue (B9) prose are separate later cycles.

    Key-phrase convention as in B2–B5: assert phrases on the parsed body,
    never raw bytes, so the green step keeps prose latitude.
    """

    command_path = IMPLEMENT_NEXT_ISSUE_PATH

    # -- B3 output: the GitHub MCP server is a named prerequisite ---------- #

    def test_body_names_github_mcp_server(self):
        # B3 output (plan §Behaviors 3): the body names "GitHub MCP
        # server" as a prerequisite — the same phrase the sibling
        # execute-github-task.md guard pins (tests/test_template_commands.py:581-589).
        self.assertIn(
            "GitHub MCP server",
            self.body,
            "body of %s does not name 'GitHub MCP server' as a "
            "prerequisite" % self.command_path,
        )

    # -- B3 output: AGENTS.md is the named source of owner and repo -------- #

    def test_body_names_agents_md_as_repository_source(self):
        # B3 output (plan §Behaviors 3): the body names
        # '.roo/rules/AGENTS.md' as the source of the GitHub owner and
        # repository name (templates/roo_template/rules/AGENTS.md:23-24
        # is that source in the shipped template).
        self.assertIn(
            ".roo/rules/AGENTS.md",
            self.body,
            "body of %s does not name '.roo/rules/AGENTS.md' as the "
            "source of the GitHub owner and repository"
            % self.command_path,
        )

    # -- B3 error guard: the intake path is the MCP server, never a CLI ---- #

    def test_body_has_no_bare_github_cli(self):
        # Error (B3, plan §Behaviors 3): no "GitHub CLI" — the repo's
        # intake path is the MCP server. The assertion is the two-word
        # token, so other GitHub phrasing the body legitimately carries
        # (e.g. "GitHub issue", "github mcp") stays legal. Guard shape
        # mirrors tests/test_template_commands.py:591-601. Green by
        # design at red time: the stub names no CLI, and the guard must
        # stay green once the prerequisites land.
        self.assertNotIn(
            "GitHub CLI",
            self.body,
            "body of %s still contains bare 'GitHub CLI'" % self.command_path,
        )


# --------------------------------------------------------------------------- #
# B4 — implement-next-issue.md body: the ranking order
# --------------------------------------------------------------------------- #

class B4ImplementNextIssueRankingTests(TemplateCommandTestCase):
    """B4 (plans/implement-next-issue.md): the body states the five
    ranking criteria in order, each earlier criterion stated to outrank
    the later ones, with oldest ``created_at`` as the final tiebreaker.

    The criteria, in required order:

      1. bug over feature (issue type / bug label outranks feature)
      2. explicit priority label (degrades to the next tiebreaker when
         the label is absent — the repo has no ``priority:*`` labels
         today, so the criterion is written to degrade, not to fail)
      3. milestone presence
      4. not blocked (``issue_dependencies_summary.blocked_by == 0``)
      5. oldest ``created_at`` as the FINAL tiebreaker

    Expected red reason: the body currently carries the usage and
    prerequisites sections only — no ranking section — so every
    present-phrase assertion fails on a missing phrase, not on a
    file-not-found. The file exists and loads (behaviours 1–3 are green),
    so this cycle is pure prose.

    Scope: behaviour 4 only. PR exclusion (B5), context override (B6),
    confirmation (B7), handoff (B8) and empty-queue (B9) prose are
    separate later cycles.

    Key-phrase convention as in B2–B3: phrases are asserted on the
    parsed body (lower-cased so the green step has prose latitude),
    never raw bytes. The ordering is pinned by the *positions* of the
    five criterion phrases plus an explicit "outranks"/"before" style
    ordering word — not by exact sentence wording.
    """

    command_path = IMPLEMENT_NEXT_ISSUE_PATH

    # -- B4 output: the five criteria are named, in order ------------------ #

    def _criterion_positions(self):
        """Return the (lower-cased body, {criterion: first index}) pair.

        A criterion the body does not name maps to ``None`` (``str.find``
        returns -1, which would otherwise pass an ``assertIsNotNone``
        presence check); the tests turn ``None`` into a diagnostic
        assertion.
        """
        lowered = self.body.lower()
        positions = {}
        for criterion in B4_RANKING_CRITERIA_IN_ORDER:
            index = lowered.find(criterion)
            positions[criterion] = None if index == -1 else index
        return lowered, positions

    def test_body_names_all_five_ranking_criteria(self):
        # B4 output (plan §Behaviors 4): every one of the five criteria
        # is named in the body.
        _, positions = self._criterion_positions()
        for criterion in B4_RANKING_CRITERIA_IN_ORDER:
            self.assertIsNotNone(
                positions[criterion],
                "body of %s does not name the ranking criterion "
                "%r" % (self.command_path, criterion),
            )

    def test_criteria_appear_in_required_order(self):
        # B4 output (plan §Behaviors 4): the five criteria are stated in
        # order — bug over feature, priority label, milestone, not
        # blocked, oldest created_at — pinned by the first occurrence of
        # each phrase appearing before the first occurrence of the next.
        _, positions = self._criterion_positions()
        for earlier, later in zip(B4_RANKING_CRITERIA_IN_ORDER,
                                  B4_RANKING_CRITERIA_IN_ORDER[1:]):
            self.assertIsNotNone(
                positions[earlier],
                "body of %s does not name the ranking criterion %r, so "
                "its position before %r cannot hold"
                % (self.command_path, earlier, later),
            )
            self.assertIsNotNone(
                positions[later],
                "body of %s does not name the ranking criterion %r, so "
                "the position after %r cannot hold"
                % (self.command_path, later, earlier),
            )
            self.assertLess(
                positions[earlier],
                positions[later],
                "body of %s names %r at position %d and %r at "
                "position %d — the criteria must be stated in order: %s"
                % (self.command_path,
                   earlier, positions[earlier],
                   later, positions[later],
                   " then ".join(B4_RANKING_CRITERIA_IN_ORDER)),
            )

    def test_body_states_earlier_criteria_outrank_later_ones(self):
        # B4 output (plan §Behaviors 4): each earlier criterion is
        # stated to outrank the later ones — an explicit "outranks" /
        # "before" style ordering statement, at least one occurrence.
        lowered, _ = self._criterion_positions()
        self.assertTrue(
            any(phrase in lowered for phrase in B4_ORDERING_PHRASES),
            "body of %s carries no explicit %r ordering statement "
            "saying an earlier criterion outranks the later ones"
            % (self.command_path, " / ".join(B4_ORDERING_PHRASES)),
        )

    def test_oldest_created_at_is_the_final_tiebreaker(self):
        # B4 output (plan §Behaviors 4): criterion 5 is named and is the
        # FINAL tiebreaker — it is named, appears last among the five
        # criteria, and the body states it resolves ties ("tiebreaker").
        lowered, positions = self._criterion_positions()
        self.assertIsNotNone(
            positions["oldest created_at"],
            "body of %s does not name 'oldest created_at'"
            % self.command_path,
        )
        self.assertTrue(
            "tiebreaker" in lowered,
            "body of %s does not state 'created_at'/'oldest' as the "
            "final tiebreaker (missing 'tiebreaker')" % self.command_path,
        )
        named_positions = [pos for pos in positions.values() if pos is not None]
        self.assertTrue(
            named_positions,
            "body of %s names no ranking criteria at all" % self.command_path,
        )
        self.assertEqual(
            positions["oldest created_at"],
            max(named_positions),
            "body of %s names 'oldest created_at' but it is not the "
            "final criterion among the five" % self.command_path,
        )

    def test_priority_label_criterion_degrades_when_absent(self):
        # B4 output (plan §Assumptions): the repo has no ``priority:*``
        # labels today, so the criterion is written to DEGRADE to the
        # next tiebreaker when the label is absent — it must stay
        # correct on a repo that never adopts the convention.
        # Key-phrase level: one of the degrade/absent-wording tokens
        # suffices, so the green step keeps prose latitude.
        lowered, _ = self._criterion_positions()
        self.assertTrue(
            any(token in lowered
                for token in ("degrade", "absent", "missing")),
            "body of %s does not state that the 'priority label' "
            "criterion degrades to the next tiebreaker when the label "
            "is absent" % self.command_path,
        )

    # -- B4 error guard: no single-criterion ranking ------------------------ #

    def test_no_single_criterion_stated_as_the_sole_rule(self):
        # Error (B4, plan §Behaviors 4): no criterion may be stated as
        # the sole rule — a single-criterion ranking leaves ties
        # unresolved and makes the top candidate non-deterministic.
        # Green by design at red time: the stub names no criteria at
        # all, and the guard must stay green once the five-criterion
        # chain lands.
        for sole_rule_phrase in ("sole rule", "only rule", "the only criterion"):
            self.assertNotIn(
                sole_rule_phrase,
                self.body.lower(),
                "body of %s states %r — a single-criterion ranking "
                "leaves ties unresolved" % (self.command_path, sole_rule_phrase),
            )


# --------------------------------------------------------------------------- #
# B5 — implement-next-issue.md body: the pull-request exclusion
# --------------------------------------------------------------------------- #

class B5ImplementNextIssuePrExclusionTests(TemplateCommandTestCase):
    """B5 (plans/implement-next-issue.md): the body states the
    pull-request exclusion.

    The exclusion has three instruction arms plus an error arm:

      * listing — the body instructs listing open pull requests, naming
        ``list_pull_requests`` or "open pull requests";
      * closer exclusion — the body instructs excluding any issue
        referenced by a ``Fixes``/``Closes``/``Resolves #N`` closer in an
        open PR's title or body;
      * defensive skip — the body instructs skipping any returned issue
        entry that is itself a pull request (GitHub's issues endpoint
        may return PRs as entries, plan §Assumptions);
      * error arm — when the PR listing fails or returns an error, the
        body instructs REPORTING the failure and STOPPING, never
        proceeding on the unfiltered issue list.

    Expected red reason: the body currently carries the usage,
    prerequisites and ranking sections only — no exclusion section — so
    every present-phrase assertion fails on a missing phrase, not on a
    file-not-found. The file exists and loads (behaviours 1-4 are
    green), so this cycle is pure prose.

    Scope: behaviour 5 only. Context override (B6), confirmation (B7),
    handoff (B8) and empty-queue (B9) prose are separate later cycles.

    Key-phrase convention as in B2-B4: phrases are asserted on the
    parsed body (lower-cased), never raw bytes, so the green step keeps
    prose latitude — concepts and keywords are pinned, not exact
    sentences.
    """

    command_path = IMPLEMENT_NEXT_ISSUE_PATH

    def _lowered(self):
        """The parsed body, lower-cased for key-phrase matching."""
        return self.body.lower()

    # -- B5 output: listing the open pull requests -------------------------- #

    def test_body_instructs_listing_open_pull_requests(self):
        # B5 output (plan §Behaviors 5): the body instructs listing open
        # pull requests — naming the 'list_pull_requests' function or
        # the plain-English "open pull request" phrase (either
        # suffices).
        lowered = self._lowered()
        self.assertTrue(
            any(phrase in lowered for phrase in B5_PR_LISTING_PHRASES),
            "body of %s does not instruct listing open pull requests "
            "(missing both %r)"
            % (self.command_path, " / ".join(B5_PR_LISTING_PHRASES)),
        )

    # -- B5 output: the closer-keyword exclusion ---------------------------- #

    def test_body_pins_all_three_closer_keywords(self):
        # B5 output (plan §Behaviors 5): all three closer keywords —
        # Fixes / Closes / Resolves — are named, so an issue referenced
        # by any of them in an open PR is excluded.
        lowered = self._lowered()
        for keyword in B5_CLOSER_KEYWORDS:
            self.assertIn(
                keyword,
                lowered,
                "body of %s does not name the closer keyword %r"
                % (self.command_path, keyword),
            )

    def test_body_pins_hash_issue_reference_shape(self):
        # B5 output (plan §Behaviors 5): the '#N' issue-reference shape
        # is pinned at key-phrase level — a '#' followed by the
        # reference, e.g. 'Resolves #N'.
        self.assertIsNotNone(
            B5_HASH_REF_RE.search(self._lowered()),
            "body of %s carries no '#' issue-reference shape (e.g. "
            "'Resolves #N')" % self.command_path,
        )

    def test_body_states_closers_checked_in_pr_title_and_body(self):
        # B5 output (plan §Behaviors 5): the closer is looked for in an
        # open PR's title or body — both words are named.
        lowered = self._lowered()
        for word in ("title", "body"):
            self.assertIn(
                word,
                lowered,
                "body of %s does not state that the closer is checked in "
                "the open PR's %r" % (self.command_path, word),
            )

    def test_body_states_excluding_the_referenced_issues(self):
        # B5 output (plan §Behaviors 5): the issues referenced by an
        # open PR's closer are excluded from the candidates — an
        # exclusion verb ('exclude*' or 'filter*') is named.
        lowered = self._lowered()
        self.assertTrue(
            any(phrase in lowered for phrase in B5_EXCLUSION_PHRASES),
            "body of %s does not instruct EXCLUDING the issues "
            "referenced by an open PR's closer (missing %r)"
            % (self.command_path, " / ".join(B5_EXCLUSION_PHRASES)),
        )

    # -- B5 output: the defensive skip of PR entries ------------------------ #

    def test_body_instructs_skipping_issue_entries_that_are_pull_requests(self):
        # B5 output (plan §Behaviors 5 + §Assumptions): GitHub's issues
        # endpoint may return pull requests as issue entries, so the
        # body instructs SKIPPING any returned entry that is itself a
        # pull request.
        lowered = self._lowered()
        self.assertIn(
            "skip",
            lowered,
            "body of %s does not instruct skipping entries"
            % self.command_path,
        )
        self.assertIn(
            "pull request",
            lowered,
            "body of %s does not name 'pull request' in the skip "
            "instruction" % self.command_path,
        )

    # -- B5 error arm: report and stop on a failed PR listing --------------- #

    def test_body_error_arm_names_listing_failure_trigger(self):
        # B5 error (plan §Behaviors 5): the error arm is triggered when
        # the PR listing fails or returns an error.
        self.assertIn(
            "fail",
            self._lowered(),
            "body of %s does not name the listing-failure trigger "
            "('fail*')" % self.command_path,
        )

    def test_body_error_arm_instructs_report_and_stop(self):
        # B5 error (plan §Behaviors 5): on the failure the body
        # instructs REPORTING it and STOPPING — a silent fallback would
        # re-select work already in flight.
        lowered = self._lowered()
        for phrase in ("report", "stop"):
            self.assertIn(
                phrase,
                lowered,
                "body of %s does not instruct %r on a failed PR listing"
                % (self.command_path, phrase),
            )

    def test_body_error_arm_carries_explicit_prohibition(self):
        # B5 error (plan §Behaviors 5): the body states the prohibition
        # — never proceed on the unfiltered issue list. One of the
        # explicit-prohibition tokens suffices; the green step picks
        # the wording.
        lowered = self._lowered()
        self.assertTrue(
            any(phrase in lowered for phrase in B5_PROHIBITION_PHRASES),
            "body of %s carries no explicit prohibition (one of %r) "
            "against proceeding on the unfiltered issue list"
            % (self.command_path, " / ".join(B5_PROHIBITION_PHRASES)),
        )


# --------------------------------------------------------------------------- #
# B6 — implement-next-issue.md body: the free-form context override
# --------------------------------------------------------------------------- #

#: B6 (plans/implement-next-issue.md §Behaviors 6): the override-statement
#: tokens — the body must say the supplied context overrides the ranking
#: chain outright. 'outrank*' is deliberately NOT an option here: the
#: committed B4 ranking prose already says each earlier criterion
#: 'outranks' the later ones, so accepting it would make this test green
#: on the ranking section while the override is still missing. The green
#: step picks among 'override*' / 'precedence' / 'takes priority'.
B6_OVERRIDE_PHRASES = ("override", "precedence", "takes priority")

#: B6 error arm: the no-match trigger tokens — 'no match' or the
#: 'matches no' spelling; either suffices. Neither spelling appears in
#: the committed B1-B5 prose ('no open blockers' is the closest and does
#: not match).
B6_NO_MATCH_PHRASES = ("no match", "matches no")

#: B6 error arm: the say-so tokens — the body instructs telling the user
#: that the context matched nothing. 'say*' covers say/saying/says; the
#: other spellings keep prose latitude.
B6_SAY_SO_PHRASES = ("say", "state so", "state that")

#: B6 error arm: the fallback tokens — 'fallback' / 'fall back' /
#: 'falling back'; either spelling suffices. Note 'fallback' already
#: appears once in the committed B5 prose ('a silent fallback would
#: re-select work'); the test's red failure therefore comes from the
#: say-so half, which is genuinely absent.
B6_FALLBACK_PHRASES = ("fallback", "fall back", "falling back")


class B6ImplementNextIssueContextOverrideTests(TemplateCommandTestCase):
    """B6 (plans/implement-next-issue.md): the body states that supplied
    context OVERRIDES the ranking chain outright.

    Two arms:

      * output — the argument-handling prose states that an issue matching
        the supplied context wins the selection outright, overriding the
        five-criterion ranking chain, and that the one-line rationale
        names the match;
      * error arm — when the context matches no open issue, the body
        instructs saying so and falling back to the unbiased ranking
        rather than selecting nothing.

    Expected red reason: the body currently carries the usage,
    prerequisites, ranking and pull-request-exclusion sections only — no
    argument-handling section — so every present-phrase assertion fails
    on a missing phrase, not on a file-not-found. The file exists and
    loads (behaviours 1-5 are green), so this cycle is pure prose.

    Phrases are asserted on the whole lower-cased body. Each pinned
    phrase is verified absent from the committed B1-B5 prose, with three
    deliberate exceptions that are satisfied there by other behaviour's
    own words and therefore cannot be the red reason: 'context' (the
    B2 usage line), 'win' (the B4 final tiebreaker) and 'fallback' (the
    B5 error sentence). Every test's red failure comes from a phrase
    that is genuinely B6's: 'override*'/'precedence'/'takes priority',
    'match', 'rationale', 'no match', 'say*', 'unbiased'.

    'outrank*' is deliberately not accepted for the override: the B4
    ranking prose already carries it, so accepting it would make the
    override test green on the ranking section while the override is
    still missing.

    Scope: behaviour 6 only. The confirmation question (B7), the
    tdd-manager handoff (B8) and the empty-queue stop (B9) prose are
    separate later cycles and are not pinned here.

    Key-phrase convention as in B2-B5: phrases are asserted on the
    parsed body (lower-cased), never raw bytes — concepts and keywords
    (override, match, rationale, fallback, no match, unbiased) are
    pinned, not exact sentences, so the green step keeps prose latitude.
    """

    command_path = IMPLEMENT_NEXT_ISSUE_PATH

    def _lowered(self):
        """The parsed body, lower-cased for key-phrase matching."""
        return self.body.lower()

    # -- B6 output: supplied context overrides the ranking chain ------------ #

    def test_body_states_context_overrides_the_ranking(self):
        # B6 output (plan §Behaviors 6): the supplied context OVERRIDES
        # the ranking chain outright — one of the override-statement
        # tokens is named. See B6_OVERRIDE_PHRASES for why 'outrank*'
        # is not an option (it is the B4 section's own word).
        lowered = self._lowered()
        self.assertTrue(
            any(phrase in lowered for phrase in B6_OVERRIDE_PHRASES),
            "body of %s does not state that supplied context overrides "
            "the ranking chain (missing %r)"
            % (self.command_path, " / ".join(B6_OVERRIDE_PHRASES)),
        )

    def test_body_states_matching_issue_wins(self):
        # B6 output (plan §Behaviors 6): an issue matching the supplied
        # context wins the selection outright — 'match' is the word the
        # committed B1-B5 prose does not carry; 'context' and 'win' are
        # pinned alongside it so the win is the override's, not the
        # ranking section's tiebreaker win.
        lowered = self._lowered()
        for phrase in ("context", "match", "win"):
            self.assertIn(
                phrase,
                lowered,
                "body of %s does not state that an issue matching the "
                "supplied context wins (missing %r)" % (self.command_path, phrase),
            )

    def test_body_states_the_rationale_names_the_match(self):
        # B6 output (plan §Behaviors 6): the one-line rationale names
        # the match — 'rationale' is absent from the committed B1-B5
        # prose, so its presence is B6's own signal.
        lowered = self._lowered()
        for phrase in ("rationale", "match"):
            self.assertIn(
                phrase,
                lowered,
                "body of %s does not state that the rationale names the "
                "match (missing %r)" % (self.command_path, phrase),
            )

    # -- B6 error arm: the context matches no open issue --------------------- #

    def test_body_error_arm_names_the_no_match_trigger(self):
        # B6 error (plan §Behaviors 6): the error arm is triggered when
        # the context matches NO open issue — 'no match' or the
        # 'matches no' spelling; either suffices. Neither spelling
        # appears in the committed B1-B5 prose.
        lowered = self._lowered()
        self.assertTrue(
            any(phrase in lowered for phrase in B6_NO_MATCH_PHRASES),
            "body of %s does not name the no-match trigger (missing %r)"
            % (self.command_path, " / ".join(B6_NO_MATCH_PHRASES)),
        )

    def test_body_error_arm_instructs_saying_so_and_falling_back(self):
        # B6 error (plan §Behaviors 6): on a no-match the body instructs
        # SAYING so and FALLING BACK. 'say*' is the red reason — it is
        # absent from the committed B1-B5 prose; the fallback half is
        # already satisfied there by the B5 error sentence ('a silent
        # fallback'), so it stays as a pin for the green step rather
        # than as the red trigger.
        lowered = self._lowered()
        self.assertTrue(
            any(phrase in lowered for phrase in B6_SAY_SO_PHRASES),
            "body of %s does not instruct saying so on a no-match "
            "(missing %r)" % (self.command_path, " / ".join(B6_SAY_SO_PHRASES)),
        )
        self.assertTrue(
            any(phrase in lowered for phrase in B6_FALLBACK_PHRASES),
            "body of %s does not instruct falling back on a no-match "
            "(missing %r)" % (self.command_path, " / ".join(B6_FALLBACK_PHRASES)),
        )

    def test_body_error_arm_falls_back_to_the_unbiased_ranking(self):
        # B6 error (plan §Behaviors 6): the fallback target is the
        # UNBIASED RANKING rather than selecting nothing — 'unbiased'
        # is the word that names the target and is absent from the
        # committed B1-B5 prose. ('ranking' alone is the B4 section's
        # own word, so pinning it adds no signal.)
        lowered = self._lowered()
        self.assertIn(
            "unbiased",
            lowered,
            "body of %s does not name the 'unbiased' fallback target"
            % self.command_path,
        )


# --------------------------------------------------------------------------- #
# B7 — implement-next-issue.md body: the single confirmation question
# --------------------------------------------------------------------------- #

#: B7 (plans/implement-next-issue.md §Behaviors 7): the presentation
#: tokens — the body must instruct PRESENTING the top candidate to the
#: user before asking. None of these appears in the committed B1-B6
#: prose, so any one of them is a genuine B7 signal. The green step
#: picks the wording.
B7_PRESENTATION_PHRASES = ("present", "show", "display")

#: B7: the exactly-one tokens — the confirmation must be EXACTLY ONE
#: question. 'only one' is accepted as a spelling variant; neither
#: phrase appears in the committed B1-B6 prose.
B7_SINGLE_QUESTION_PHRASES = ("exactly one", "only one")

#: B7 error arm: the no-further-question tokens — the body must say no
#: FURTHER question is asked unless the issue is genuinely ambiguous.
#: None of these appears in the committed B1-B6 prose.
B7_NO_FURTHER_PHRASES = ("no further", "no other", "no additional")


class B7ImplementNextIssueConfirmationTests(TemplateCommandTestCase):
    """B7 (plans/implement-next-issue.md): the body states the single
    confirmation question.

    Three instruction arms plus a cross-file guard:

      * presentation — the body instructs presenting the top candidate
        WITH its number, title and a one-line rationale;
      * single question — the body instructs asking EXACTLY ONE
        confirmation question before any work starts;
      * error arm — the body instructs asking NO FURTHER question
        unless the issue itself is genuinely ambiguous;
      * guard — the body must not carry execute-github-task's
        "at least 2-3 clarifying questions" instruction
        (templates/roo_template/commands/execute-github-task.md:59);
        that multi-question mandate belongs to the sibling command
        only. Guard shape mirrors the sibling B3 cross-file negative
        assertions (tests/test_template_commands.py:635-645).

    Expected red reason: the body currently ends at the argument-
    handling section — no confirmation section — so every present-
    phrase assertion fails on a missing phrase, not on a file-not-
    find. The file exists and loads (behaviours 1-6 are green), so
    this cycle is pure prose.

    Phrases are asserted on the whole lower-cased body. The red
    failures come from phrases genuinely absent from the committed
    B1-B6 prose: the presentation verb, 'top candidate', 'number',
    'exactly one'/'only one', 'question', 'no further'/'no other'/
    'no additional', 'unless' and 'ambiguous'. A few pins ('title',
    'one-line', 'rationale', 'confirm', 'before', 'work') are already
    satisfied by other behaviours' own words and stay as pins for
    the green step rather than red triggers.

    Scope: behaviour 7 only. The tdd-manager handoff (B8) and the
    empty-queue stop (B9) prose are separate later cycles and are
    not pinned here.

    Key-phrase convention as in B2-B6: phrases are asserted on the
    parsed body (lower-cased), never raw bytes — concepts and
    keywords (present, top candidate, number, one question, confirm,
    rationale, no further, unless, ambiguous) are pinned, not exact
    sentences, so the green step keeps prose latitude.
    """

    command_path = IMPLEMENT_NEXT_ISSUE_PATH

    def _lowered(self):
        """The parsed body, lower-cased for key-phrase matching."""
        return self.body.lower()

    # -- B7 output: the top candidate is presented -------------------------- #

    def test_body_instructs_presenting_the_top_candidate(self):
        # B7 output (plan §Behaviors 7): the body instructs PRESENTING
        # the top candidate — a presentation verb plus 'top candidate';
        # neither appears in the committed B1-B6 prose.
        lowered = self._lowered()
        self.assertTrue(
            any(phrase in lowered for phrase in B7_PRESENTATION_PHRASES),
            "body of %s does not instruct presenting the top candidate "
            "(missing %r)"
            % (self.command_path, " / ".join(B7_PRESENTATION_PHRASES)),
        )
        self.assertIn(
            "top candidate",
            lowered,
            "body of %s does not name the 'top candidate'"
            % self.command_path,
        )

    def test_body_states_the_candidate_is_shown_with_number_title_rationale(self):
        # B7 output (plan §Behaviors 7): the presentation carries the
        # candidate's NUMBER, TITLE and a one-line RATIONALE. 'number'
        # is the red trigger (absent from the committed B1-B6 prose);
        # 'title', 'one-line' and 'rationale' are already carried by
        # the B5/B6 prose and stay as pins for the green step.
        lowered = self._lowered()
        for phrase in ("number", "title", "rationale"):
            self.assertIn(
                phrase,
                lowered,
                "body of %s does not state that the top candidate is "
                "shown with its %r" % (self.command_path, phrase),
            )
        self.assertTrue(
            any(phrase in lowered for phrase in ("one-line", "one line")),
            "body of %s does not state that the rationale is "
            "one-line" % self.command_path,
        )

    # -- B7 output: exactly one confirmation question ----------------------- #

    def test_body_instructs_exactly_one_confirmation_question(self):
        # B7 output (plan §Behaviors 7): the body instructs asking
        # EXACTLY ONE confirmation question. Both 'exactly one'/'only
        # one' and 'question' are absent from the committed B1-B6
        # prose; 'confirm' is already carried by the intro line and
        # stays as a pin.
        lowered = self._lowered()
        self.assertTrue(
            any(phrase in lowered for phrase in B7_SINGLE_QUESTION_PHRASES),
            "body of %s does not instruct asking EXACTLY ONE "
            "confirmation question (missing %r)"
            % (self.command_path, " / ".join(B7_SINGLE_QUESTION_PHRASES)),
        )
        self.assertIn(
            "question",
            lowered,
            "body of %s does not name the confirmation 'question'"
            % self.command_path,
        )
        self.assertIn(
            "confirm",
            lowered,
            "body of %s does not name 'confirm*' in the confirmation "
            "instruction" % self.command_path,
        )

    def test_body_states_the_question_comes_before_any_work(self):
        # B7 output (plan §Behaviors 7): the confirmation question is
        # asked BEFORE ANY WORK STARTS. 'before' and 'work' are
        # already carried by the B5 prose ('before ranking', 'work
        # that is already being implemented') and stay as pins; the
        # question-side phrases are pinned by the previous test.
        lowered = self._lowered()
        for phrase in ("before", "work"):
            self.assertIn(
                phrase,
                lowered,
                "body of %s does not state that the confirmation "
                "question comes %r work starts" % (self.command_path, phrase),
            )

    # -- B7 error arm: no further question unless the issue is ambiguous ---- #

    def test_body_error_arm_instructs_no_further_question(self):
        # B7 error (plan §Behaviors 7): the body instructs asking NO
        # FURTHER question. 'no further'/'no other'/'no additional'
        # are all absent from the committed B1-B6 prose.
        lowered = self._lowered()
        self.assertTrue(
            any(phrase in lowered for phrase in B7_NO_FURTHER_PHRASES),
            "body of %s does not instruct asking no further question "
            "(missing %r)"
            % (self.command_path, " / ".join(B7_NO_FURTHER_PHRASES)),
        )

    def test_body_error_arm_names_the_genuinely_ambiguous_exception(self):
        # B7 error (plan §Behaviors 7): the exception to the
        # no-further-question rule is that the ISSUE ITSELF is
        # GENUINELY AMBIGUOUS — 'unless' and 'ambiguous' are both
        # absent from the committed B1-B6 prose.
        lowered = self._lowered()
        for phrase in ("unless", "ambiguous"):
            self.assertIn(
                phrase,
                lowered,
                "body of %s does not name the %r exception for the "
                "no-further-question rule" % (self.command_path, phrase),
            )

    # -- B7 guard: the sibling's multi-question mandate is not adopted ------ #

    def test_body_has_no_multi_question_clarifying_mandate(self):
        # Guard (B7, plan §Behaviors 7): the body must NOT carry
        # execute-github-task's "at least 2-3 clarifying questions"
        # instruction (templates/roo_template/commands/execute-github-
        # task.md:59) — that multi-question mandate belongs to the
        # sibling command only. Guard shape mirrors the sibling B3
        # cross-file negative assertions
        # (tests/test_template_commands.py:635-645). Green by design
        # at red time: the confirmation section does not exist yet,
        # and the guard must stay green once the single-question
        # prose lands.
        for token in ("clarifying", "2-3"):
            self.assertNotIn(
                token,
                self._lowered(),
                "body of %s carries the multi-question mandate token "
                "%r — that belongs to /execute-github-task only"
                % (self.command_path, token),
            )


# --------------------------------------------------------------------------- #
# B8 — implement-next-issue.md body: the verbatim tdd-manager handoff
# --------------------------------------------------------------------------- #

#: B8 error arm (plans/implement-next-issue.md §Behaviors 8): the
#: DECLINED-confirmation trigger. The body may spell it "declined"
#: (adjective) or "declines" (verb); either suffices. Neither spelling
#: appears in the committed B1-B7 prose.
B8_DECLINED_PHRASES = ("declined", "declines")

#: B8 error arm: the NEXT-RANKED candidate the body must present on a
#: decline — "next-ranked" in either spelling, or the plain "next
#: candidate". None of these phrases appears in the committed B1-B7
#: prose (its one "next" is "next open GitHub issue", a different
#: meaning, not a ranking position).
B8_NEXT_CANDIDATE_PHRASES = (
    "next-ranked",
    "next ranked",
    "next candidate",
)


class B8ImplementNextIssueHandoffTests(TemplateCommandTestCase):
    """B8 (plans/implement-next-issue.md): the body states the verbatim
    tdd-manager handoff.

    Two instruction arms:

      * output — the post-confirmation section instructs handing the
        SELECTED ISSUE VERBATIM to the TDD-MANAGER PIPELINE; the mode
        slug ``tdd-manager`` must be named, not paraphrased;
      * error arm — on a DECLINED confirmation the body instructs
        PRESENTING THE NEXT-RANKED CANDIDATE rather than starting
        anything or re-asking about the same issue.

    Expected red reason: the body currently ends at the confirmation
    section — there is no post-confirmation handoff prose — so the
    tests fail on the missing phrases "verbatim", "declined"/
    "declines" and the next-candidate phrases, not on a file-not-find.
    The file exists and loads (behaviours 1-7 are green), so this
    cycle is pure prose. A few pins ("tdd-manager", "pipeline", "hand")
    are already carried by the intro line ("...confirms it with the
    user, and hands it to the tdd-manager pipeline.") and stay as pins
    for the green step rather than as red triggers.

    Scope: behaviour 8 only. The empty-queue stop (B9) prose is a
    separate later cycle and is not pinned here.

    Key-phrase convention as in B2-B7: phrases are asserted on the
    parsed body (lower-cased), never raw bytes — concepts and keywords
    (verbatim, tdd-manager, pipeline, hand, declined, next candidate)
    are pinned, not exact sentences, so the green step keeps prose
    latitude.
    """

    command_path = IMPLEMENT_NEXT_ISSUE_PATH

    def _lowered(self):
        """The parsed body, lower-cased for key-phrase matching."""
        return self.body.lower()

    # -- B8 output: the selected issue is handed over verbatim ------------- #

    def test_body_instructs_the_verbatim_handoff(self):
        # B8 output (plan §Behaviors 8): the handoff of the selected
        # issue is VERBATIM — 'verbatim' is the red trigger; it is
        # absent from the committed B1-B7 prose. 'hand' is already
        # carried by the intro line and stays as a pin.
        lowered = self._lowered()
        self.assertIn(
            "verbatim",
            lowered,
            "body of %s does not instruct handing the selected issue "
            "verbatim" % self.command_path,
        )
        self.assertIn(
            "hand",
            lowered,
            "body of %s does not use a 'hand*' verb for the handoff"
            % self.command_path,
        )

    def test_body_names_the_tdd_manager_mode_slug(self):
        # B8 output (plan §Behaviors 8): the handoff names the mode
        # slug 'tdd-manager' — paraphrasing the mode would leave the
        # dispatch target ambiguous. Already carried by the intro
        # line; this pin keeps it in the green-step prose.
        self.assertIn(
            "tdd-manager",
            self._lowered(),
            "body of %s does not name the 'tdd-manager' mode slug"
            % self.command_path,
        )

    def test_body_names_the_tdd_manager_pipeline(self):
        # B8 output (plan §Behaviors 8): the handoff target is the
        # tdd-manager PIPELINE, not a one-shot prompt. Already carried
        # by the intro line; this pin keeps it in the green-step prose.
        self.assertIn(
            "pipeline",
            self._lowered(),
            "body of %s does not name the 'pipeline' handoff target"
            % self.command_path,
        )

    # -- B8 error arm: the declined confirmation --------------------------- #

    def test_body_error_arm_names_the_declined_confirmation(self):
        # B8 error (plan §Behaviors 8): the error arm is triggered by
        # a DECLINED confirmation — 'declined'/'declines' is the red
        # trigger; neither spelling appears in the committed B1-B7
        # prose (the confirmation section only asks the question, it
        # never names a decline).
        lowered = self._lowered()
        self.assertTrue(
            any(phrase in lowered for phrase in B8_DECLINED_PHRASES),
            "body of %s does not name the declined-confirmation "
            "trigger (missing %r)"
            % (self.command_path, " / ".join(B8_DECLINED_PHRASES)),
        )

    def test_body_error_arm_instructs_presenting_the_next_ranked_candidate(self):
        # B8 error (plan §Behaviors 8): on a decline the body
        # instructs presenting the NEXT-RANKED CANDIDATE — a new
        # selection, not a re-ask about the same issue. The
        # next-candidate phrases are the red trigger; 'candidate'
        # alone is already carried by the B7 prose ("top candidate"),
        # so the position-qualifying phrase is what pins the
        # behaviour.
        lowered = self._lowered()
        self.assertTrue(
            any(phrase in lowered for phrase in B8_NEXT_CANDIDATE_PHRASES),
            "body of %s does not instruct presenting the next-ranked "
            "candidate on a decline (missing %r)"
            % (self.command_path, " / ".join(B8_NEXT_CANDIDATE_PHRASES)),
        )
