"""Tests for the /harvest-roo-templates chat command (plans/harvest-roo-templates.md).

This module is the home for every behaviour of that plan that is verified
against the command file itself:

  * B1 — the command file exists with valid frontmatter (implemented below);
  * B2 — the file is tracked despite .roo/* being gitignored (implemented
    below; runs ``git check-ignore``, so it does not need the command file's
    content);
  * B3-B8 — body-content behaviours; each will land in its own test case class
    pointed at the same file, built on the shared loader below.

The command file under test is ``.roo/commands/harvest-roo-templates.md`` in
this repository. B1 is green: the file exists and its frontmatter validates.
B2 is currently red: the .gitignore negation is not present yet, so
``test_command_file_is_not_ignored`` fails while the two stay-ignored guards
hold.

Every assertion is on the parsed frontmatter structure and on key phrases,
never on raw bytes, so the green step has latitude in the prose (precedent:
``tests/test_templates_rules.py``). The frontmatter shape follows
``.roo/commands/create-pull-request.md`` (a ``---``-delimited YAML block at the
top of the file).
"""

import re
import subprocess
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
        # frontmatter error: the two failure classes stay distinct. The absent
        # path is a synthetic temp path, so this holds against the loader's
        # error contract in both red and green states (the real command file
        # may or may not exist, and neither matters here).
        absent_path = Path(self._tmp.name) / "absent.md"
        with self.assertRaises(FileNotFoundError):
            load_harvest_command(absent_path)

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


# --------------------------------------------------------------------------- #
# B2 — the file is tracked despite .roo/* being gitignored
# --------------------------------------------------------------------------- #

class B2GitIgnoreNegationTests(unittest.TestCase):
    """B2 (plans/harvest-roo-templates.md): the command file escapes the
    ``.roo/*`` ignore rule through the three-line negation in ``.gitignore``.

    ``git check-ignore -q`` is run once per path (list argument, never
    ``shell=True``, ``cwd=REPO_ROOT``): exit 0 means git reports the path as
    ignored, exit 1 means not ignored.

    ``--no-index`` is load-bearing, not decorative: the target file is
    tracked (the B1 green commit force-added it), and ``check-ignore`` without
    ``--no-index`` reports indexed paths as not-ignored regardless of the
    ignore rules. Without the flag, ``test_command_file_is_not_ignored``
    would pass with or without the negation and pin nothing. With it, the
    command evaluates the ignore rules alone — exactly the behaviour this
    test locks in: the target is not ignored, and nothing else in ``.roo/``
    is reopened.

    Expected red reason: the negation is not in ``.gitignore`` yet, so the
    target matches ``.roo/*`` and ``test_command_file_is_not_ignored``
    fails. The green step adds the three negation lines; nothing else.

    Edge behaviour, per the plan: git missing (``FileNotFoundError``) or the
    tree not a git work tree (a distinct fatal, exit 128) -> **skip**, not
    fail — the same skip-not-fail treatment ``tests/test_rules_mirror.py``
    gives an unprovisioned ``.roo/``.
    """

    #: The file the negation must re-include — and the only file it may.
    TARGET = ".roo/commands/harvest-roo-templates.md"
    #: A non-command ``.roo/`` member: the negation re-includes one file,
    #: not the directory.
    MCP_PATH = ".roo/mcp.json"
    #: A sibling command: the negation must not spill past its one target.
    #: ``check-ignore`` does not require the path to exist.
    SIBLING = ".roo/commands/create-pull-request.md"

    def _check_ignored(self, path):
        """Run ``git check-ignore --no-index -q <path>`` and return ``True``
        iff git reports *path* as ignored (exit 0).

        Skips the test — never fails it — when git is not installed or the
        tree is not a git work tree.
        """
        try:
            proc = subprocess.run(
                ["git", "check-ignore", "--no-index", "-q", path],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            self.skipTest("git is not installed; cannot run check-ignore")
        if proc.returncode not in (0, 1):
            stderr = proc.stderr.decode("utf-8", "replace").strip()
            self.skipTest(
                "git check-ignore could not evaluate %s (exit %d): %s"
                % (path, proc.returncode, stderr or "no stderr")
            )
        return proc.returncode == 0

    def test_command_file_is_not_ignored(self):
        # B2 output: with the negation in place, the target is NOT ignored.
        self.assertFalse(
            self._check_ignored(self.TARGET),
            "%s is ignored: the .gitignore negation is missing or "
            "ineffective; it must re-include exactly this file"
            % self.TARGET,
        )

    def test_mcp_json_stays_ignored(self):
        # B2 output, second half: the negation must not reopen .roo/.
        self.assertTrue(
            self._check_ignored(self.MCP_PATH),
            "%s is no longer ignored: the negation reopened the whole "
            ".roo/ directory instead of singling out one file"
            % self.MCP_PATH,
        )

    def test_sibling_command_stays_ignored(self):
        # Guard: the negation must not spill to sibling commands.
        self.assertTrue(
            self._check_ignored(self.SIBLING),
            "%s is no longer ignored: the negation spilled beyond its "
            "single target file"
            % self.SIBLING,
        )


# --------------------------------------------------------------------------- #
# B3 — the command names what it reads
# --------------------------------------------------------------------------- #

class B3InventorySourcesTests(HarvestCommandTestCase):
    """B3 (plans/harvest-roo-templates.md): the command body names all five
    inventory sources it reads in the other repo.

    One named test per source, so a missing source fails its own test.
    Assertions are on the presence of each source path as a distinct token —
    never on the surrounding prose — so the green step has latitude: the
    sources may appear in a bullet list, a sentence, or a table.

    Expected red reason: the current body is the B1 placeholder (a heading
    and an empty "## Inventory" section) and names none of the five sources,
    so every source test fails, and so does the absent-source handling test.
    """

    command_path = COMMAND_PATH

    def _source_named(self, token):
        """True iff *token* appears in the body as a distinct token, not
        embedded in a longer identifier (a non-word character or start of
        line must precede it)."""
        return re.search(r"(?<!\w)" + re.escape(token), self.body) is not None

    def test_body_names_roomodes_source(self):
        self.assertTrue(
            self._source_named(".roomodes"),
            "body does not name the .roomodes inventory source",
        )

    def test_body_names_roo_rules_source(self):
        self.assertTrue(
            self._source_named(".roo/rules/"),
            "body does not name the .roo/rules/ inventory source",
        )

    def test_body_names_roo_rules_wildcard_source(self):
        self.assertTrue(
            self._source_named(".roo/rules-*/"),
            "body does not name the .roo/rules-*/ inventory source",
        )

    def test_body_names_roo_commands_source(self):
        self.assertTrue(
            self._source_named(".roo/commands/"),
            "body does not name the .roo/commands/ inventory source",
        )

    def test_body_names_roo_skills_source(self):
        # Edge (B3): .roo/skills/ is empty in this repo but exists as a
        # provisioned subdirectory, so it is in scope and must be listed.
        self.assertTrue(
            self._source_named(".roo/skills/"),
            "body does not name the .roo/skills/ inventory source",
        )

    def test_body_says_missing_source_is_reported_absent(self):
        # B3 error handling: a source directory missing in the other repo is
        # reported as "absent", not treated as a diff finding. The predicate
        # is deliberately loose — the body only has to state that a missing
        # source is noted as absent and the harvest continues — so the green
        # step has latitude in the exact wording.
        self.assertRegex(
            self.body,
            r"\babsent\b",
            "body does not state that a missing inventory source is "
            "reported as 'absent' and the harvest continues",
        )


# --------------------------------------------------------------------------- #
# B4 — the diff is one-way
# --------------------------------------------------------------------------- #

class B4OneWayDiffTests(HarvestCommandTestCase):
    """B4 (plans/harvest-roo-templates.md): the body states the comparison is
    one-way.

    The comparison reports only what the other repository has and
    ``templates/roo_template/`` lacks, and it explicitly forbids proposing
    deletions from our templates: anything that exists in the templates but
    not in the other repo is out of scope. The plan's rationale is that a
    two-way diff would flag every anvil-specific rule as "missing" from the
    other repo and drown the signal.

    Assertions are loose phrase predicates — case-insensitive, one sentence
    wide, never on raw prose — so the green step has latitude in the exact
    wording, but each predicate is specific enough that a two-way command
    would fail it.

    Expected red reason: the current body is the B1 frontmatter plus the B3
    Inventory section only; it never names ``templates/roo_template/``,
    never restricts the report to one direction, and never mentions deletion
    or removal at all, so all three tests fail.
    """

    command_path = COMMAND_PATH

    #: B4 output, part 1: the baseline the comparison is made against.
    BASELINE = "templates/roo_template/"

    #: "one-way" said explicitly, or the report restricted to one direction:
    #: "only" + something our templates lack/miss/is absent, in one sentence.
    #: A two-way body would say "both" or "two-way" and would not restrict
    #: the report to "only ... lack".
    ONE_WAY_RE = re.compile(
        r"one[- ]?way"
        r"|\bonly\b[^.;]*?\b(?:lack\w*|missing|absent)\b",
        re.IGNORECASE,
    )

    #: B4 output, part 2: deletion from our templates is negated — "never
    #: delete", "do not propose removing", "never suggests deleting". A
    #: negator (never / do not / don't / not / no) in the same sentence as a
    #: delete/remove word. A two-way body would name deletions as a valid
    #: finding and would not negate them.
    NO_DELETIONS_RE = re.compile(
        r"\b(?:never|do\s+not|don'?t|not|no)\b"
        r"[^.;]*?\b(?:delet\w*|remov\w*)\b",
        re.IGNORECASE,
    )

    def test_body_names_roo_template_as_baseline(self):
        # B4 output, part 1: the body names templates/roo_template/ as the
        # baseline the other repo's contents are compared against.
        self.assertTrue(
            re.search(
                r"(?<!\w)" + re.escape(self.BASELINE), self.body
            ) is not None,
            "body does not name %s as the baseline for the comparison"
            % self.BASELINE,
        )

    def test_body_states_comparison_is_one_way(self):
        # B4 output, part 1: the comparison reports only what the other repo
        # has and our templates lack — not the reverse.
        self.assertRegex(
            self.body,
            self.ONE_WAY_RE,
            "body does not state that the comparison is one-way (reports "
            "only what the other repo has and templates/roo_template/ lacks)",
        )

    def test_body_forbids_deletions_from_our_templates(self):
        # B4 output, part 2: the body explicitly forbids proposing deletions
        # from our templates — anything in templates/roo_template/ but not in
        # the other repo is out of scope. The negation must sit in the same
        # sentence as the delete/remove word, so "never delete", "do not
        # propose removing" and "never suggests deleting" all pass.
        self.assertRegex(
            self.body,
            self.NO_DELETIONS_RE,
            "body does not forbid proposing deletions/removals from our "
            "templates (anything in templates/roo_template/ but not in the "
            "other repo must be stated out of scope)",
        )


# --------------------------------------------------------------------------- #
# B5 — findings are classified, and wording is never auto-adopted
# --------------------------------------------------------------------------- #

class B5FindingClassificationTests(HarvestCommandTestCase):
    """B5 (plans/harvest-roo-templates.md): the body defines three finding
    classes — a whole new file, a new section within an existing file, and
    divergent wording of an existing section — and states that divergent
    wording is reported for judgement, never adopted automatically.

    The plan's rationale: our templates carry deliberate local edits (the
    tdd-manager byte ceiling, the architect's package-registry step), so
    auto-adopting another repo's wording would silently revert them.

    Assertions are loose phrase predicates — case-insensitive, tolerant of
    near-synonyms ("changed wording" for "divergent wording", "added
    section" for "new section") — but each is specific enough that a body
    lacking the classification, or one that auto-adopts wording, fails.

    Expected red reason: the current body is the B1 frontmatter plus the
    Inventory and Comparison sections (B1-B4) only; it names no finding
    classes and never mentions adopting, copying, overwriting or
    rewriting, so all four tests fail.
    """

    command_path = COMMAND_PATH

    #: Class 1: a whole NEW FILE — present in the other repo, absent from
    #: templates/roo_template/. "new file" also matches inside "whole new
    #: file", "entirely new file" and "brand-new file" (a hyphen is a word
    #: boundary), so the green step keeps latitude.
    NEW_FILE_RE = re.compile(r"\bnew\s+files?\b", re.IGNORECASE)

    #: Class 2: a NEW SECTION within an existing file, plus the near-
    #: synonyms the green step may pick.
    NEW_SECTION_RE = re.compile(
        r"\bnew\s+sections?\b"
        r"|\badded\s+sections?\b"
        r"|\badditional\s+sections?\b",
        re.IGNORECASE,
    )

    #: Class 3: DIVERGENT WORDING of an existing section — the plan's term
    #: plus the near-synonyms the green step may pick.
    DIVERGENT_WORDING_RE = re.compile(
        r"\b(?:divergen\w*|changed|different|altered|reworded)\s+wording\b",
        re.IGNORECASE,
    )

    #: Guard: a negator within one sentence of an adopt-family verb. A body
    #: that auto-adopts another repo's wording would name adopt/copy/
    #: overwrite/rewrite without negating it. "cope" is excluded by spelling
    #: the cop-* forms out.
    _NEVER_ADOPT_RE = re.compile(
        r"\b(?:never|do\s+not|don'?t|not|no)\b"
        r"[^.;]{0,80}?"
        r"\b(?:adopt\w*|cop(?:y|ies|ied|ying)|overwrit\w*|rewrit\w*)\b",
        re.IGNORECASE,
    )

    def test_body_classifies_whole_new_file(self):
        # B5 output, class 1: the body names a whole new file as a finding
        # class (present in the other repo, absent from our templates).
        self.assertRegex(
            self.body,
            self.NEW_FILE_RE,
            "body does not name a whole new file as a finding class "
            "(a file present in the other repo but absent from "
            "templates/roo_template/)",
        )

    def test_body_classifies_new_section_in_existing_file(self):
        # B5 output, class 2: the body names a new section within an
        # existing file as a finding class.
        self.assertRegex(
            self.body,
            self.NEW_SECTION_RE,
            "body does not name a new section within an existing file as "
            "a finding class",
        )

    def test_body_classifies_divergent_wording(self):
        # B5 output, class 3: the body names divergent wording of an
        # existing section as a finding class.
        self.assertRegex(
            self.body,
            self.DIVERGENT_WORDING_RE,
            "body does not name divergent wording of an existing section "
            "as a finding class",
        )

    def _wording_never_auto_adopted(self):
        """True iff the body negates the adoption of wording: a negator
        within one sentence of an adopt-family verb, with the passage
        around it about wording (``wording`` / ``divergen*``).

        The wording context keeps this from being satisfied by the B4
        deletion negation ("never proposes removing or deleting"), and the
        sentence-scoped negator keeps a bare "copy the file verbatim"
        from satisfying it.
        """
        body = self.body
        for match in self._NEVER_ADOPT_RE.finditer(body):
            window = body[max(0, match.start() - 120):match.end()]
            if re.search(r"\b(?:wording|divergen\w*)\b", window, re.IGNORECASE):
                return True
        return False

    def test_body_forbids_auto_adopting_divergent_wording(self):
        # B5 guard: divergent wording is reported for judgement and never
        # adopted automatically — the user or agent decides, and the
        # command must not silently rewrite our template wording.
        self.assertTrue(
            self._wording_never_auto_adopted(),
            "body does not state that divergent wording is reported for "
            "judgement and never adopted/copied/overwritten/rewritten "
            "automatically",
        )


if __name__ == "__main__":
    unittest.main()
