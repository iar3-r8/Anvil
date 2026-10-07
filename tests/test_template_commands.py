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
