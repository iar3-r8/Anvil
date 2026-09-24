"""RED tests for plans/cut-agent-context-cost.md, behaviour B9 (shared-rules split).

B9 moves content that only one mode needs out of the shared always-on rules
(``.roo/rules/architecture.md`` and ``.roo/rules/coding-guidelines.md``,
12,679 B, loaded by every mode on every subtask) into that mode's
``rules-{slug}/`` directory, which loads only for that mode:

* the **test guidelines** -> ``.roo/rules-qna-tester/instructions.xml``;
* the **documentation guidelines** and the **Documentation Finalisation**
  section -> ``.roo/rules-docs-manager/guidelines.xml``;
* the **module-by-module project-structure table** -> a file somewhere under
  ``.roo/`` outside the shared ``rules/`` directory (the plan does not name
  the file; the assertion scans the tree).

The template half does **not** move (the plan's one deliberate divergence):
``templates/roo_template/rules/architecture.md`` (352 B) and
``coding-guidelines.md`` (1,379 B) are placeholder scaffolds filled in per
repo by ``/update_roo_rules``. Instead the template's ``coding-guidelines.md``
gains a one-line note pointing the filling-in agent at that mode's
``rules-{slug}/`` directory. **No test here demands the template mirror the
local move** (plan B9: "This is why B9 does not mirror").

Destination layout (the mirror-parity decision the green step depends on)
---------------------------------------------------------------------------
The moved markdown content goes into the **existing XML files**
(``rules-qna-tester/instructions.xml``, ``rules-docs-manager/guidelines.xml``),
not into new markdown files: the plan's own byte table (section 7) forecasts
those two XML files growing (4,501 -> ~7,000 B; 2,630 -> ~4,200 B), which only
a content addition into them explains, and ``tests/test_rules_mirror.py``
(B1) requires the four rule XMLs to stay byte-identical between
``templates/roo_template/`` and ``.roo/`` -- the green step must therefore
add the content to **both** copies, keeping B1 green. (New *markdown* files
alongside the XML would not touch B1 either; the XML destination is chosen
because the plan's measurements already anticipate it.) No new template-side
``rules-{slug}/`` directory is created by B9, so -- per the plan's deployment
note -- **no new deployment assertion is written**; the existing
``B18ArchitectDeploymentTests`` and the mode-rules tests in
``tests/test_provision.py`` already prove ``_deploy_mode_rules`` copies
every ``rules-*`` directory it finds.

Assertion policy
----------------
* Every moved rule is asserted **present in its destination AND absent from
  the shared file**. "In both" matters: a half-finished move costs more than
  no move; a bullet in neither or in both fails, naming it.
* Assertions bind on **stable stems** (lower-cased substrings), never on
  whole sentences, so the green step has prose latitude.
* What stays shared stays: the Python 3.8 floor, the dependency policy,
  naming, the ``json.dumps`` / ``subprocess`` safety rules (guards, expected
  green on arrival), plus the short orientation paragraph, the
  configuration-ownership boundary and the port-precedence rule.
* The entire local half is gitignored, so local assertions **skip** when
  ``.roo/`` is absent (fresh clone / CI); template assertions always run.
"""

import re
import unittest
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# -- the shared (always-on) local files, the move source -- #
LOCAL_RULES_DIR = REPO_ROOT / ".roo" / "rules"
SHARED_ARCHITECTURE = LOCAL_RULES_DIR / "architecture.md"
SHARED_CODING_GUIDELINES = LOCAL_RULES_DIR / "coding-guidelines.md"

# -- the destinations of the move (existing XML; see module docstring) -- #
LOCAL_QNA = REPO_ROOT / ".roo" / "rules-qna-tester" / "instructions.xml"
LOCAL_DOCS = REPO_ROOT / ".roo" / "rules-docs-manager" / "guidelines.xml"

# -- the template half (tracked; no move, note only) -- #
TEMPLATE_RULES_DIR = REPO_ROOT / "templates" / "roo_template" / "rules"
TEMPLATE_CODING_GUIDELINES = TEMPLATE_RULES_DIR / "coding-guidelines.md"
TEMPLATE_ROOT = REPO_ROOT / "templates" / "roo_template"

# The ``rules-*`` directories the template may ship: exactly the four
# pre-B9 ones (B9 creates no new template-side directory).
EXPECTED_TEMPLATE_RULE_DIRS = frozenset(
    [
        "rules-architect",
        "rules-docs-manager",
        "rules-qna-tester",
        "rules-tdd-manager",
    ]
)

# --------------------------------------------------------------------------- #
# Moved rules: (stem, description) pairs. Stems are lower-cased substrings,
# deliberately stable fragments of the current bullets, not whole sentences.
# --------------------------------------------------------------------------- #

QNA_STEMS = [
    ("failing test first", "strict TDD: failing test first"),
    ("weaken a test", "never weaken a test to make it pass"),
    ("network", "no test touches the network / Docker daemon / $HOME"),
    ("getpass", "the getpass / hide_input / CliRunner stdin traps"),
    ("source text", "assert on data structures, not source text"),
    ("standalone_mode", "test the real entry path (standalone vs not)"),
    ("seconds", "the suite must run in seconds"),
    ("regression test", "every bug gets a regression test before the fix"),
]

DOCS_STEMS = [
    # "defect", not "docstring": the staying-shared 'Module per concern'
    # bullet also says "says so in its docstring", so "docstring" would
    # false-fail the absent-from-shared assertion on a line that stays.
    ("defect", "module docstrings explain why, not what (defect it fixes)"),
    ("narrat", "comment the surprising, not the obvious"),
    ("readme", "keep README.md and doc/ accurate"),
    ("plans/", "record decisions and rationale in plans/"),
]

FINALISATION_STEMS = [
    ("docs manager", "switch to Docs Manager mode to finalise documentation"),
    ("commit", "ask commit vs branch before documentation work"),
]

# Distinctive module names from the architecture.md project-structure table.
# Stems that can legitimately survive in the destination text ("tests/",
# "templates/", "bootstrap.sh") are deliberately NOT asserted absent, so a
# condensed orientation paragraph in the shared file does not break the
# test; the destination-presence assertions prove the table landed somewhere.
MODULE_TABLE_STEMS = ["cli.py", "env.py", "compose.py"]

# What must REMAIN in the shared files (guards; green on arrival).
SHARED_ARCHITECTURE_MUST_KEEP = [
    ("anvilkit", "short orientation paragraph naming anvilkit/"),
    ("project structure", "the Project Structure heading"),
    ("config.yaml", "the configuration-ownership boundary"),
    ("read-only", "config.yaml stays READ-ONLY to Anvil"),
    ("precedence", "the port-precedence rule"),
]

SHARED_GUIDELINES_MUST_KEEP = [
    ("3.8", "the Python 3.8 floor"),
    ("stdlib first", "the stdlib-first dependency policy"),
    ("requirements.txt", "the pinned exceptions"),
    ("snake_case", "the naming conventions"),
    ("json.dumps", "never build structured text by string substitution"),
    ("subprocess", "subprocess takes a list, never a string, never shell=True"),
    ("exception type per module", "one exception type per module"),
]


# --------------------------------------------------------------------------- #
# Parsing helpers (markdown: front matter + sections; trees: file scans)
# --------------------------------------------------------------------------- #

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _read(path):
    # type: (Path) -> str
    return path.read_text(encoding="utf-8")


def _lower_lines(text):
    # type: (str) -> List[str]
    return [line.lower() for line in text.splitlines()]


def _section_lines(lines, title):
    # type: (List[str], str) -> Optional[List[str]]
    """Lines under the first heading whose title equals *title*
    (case-insensitive), up to the next heading of the same or a higher
    level. ``None`` when the heading is absent."""
    start = None
    for idx, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match and match.group(2).lower() == title.lower():
            start = idx + 1
            break
    if start is None:
        return None
    end = len(lines)
    for idx in range(start, len(lines)):
        match = _HEADING_RE.match(lines[idx])
        if match and len(match.group(1)) <= len(_heading_level(lines[idx])):
            end = idx
            break
    return lines[start:end]


def _heading_level(line):
    # type: (str) -> str
    match = _HEADING_RE.match(line)
    return match.group(1) if match else ""


def _markdown_body(path):
    # type: (Path) -> List[str]
    """The lower-cased body lines of a markdown file, front matter removed
    (the block between a leading ``---`` pair)."""
    lines = _lower_lines(_read(path))
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return lines[i + 1:]
    return lines


def _stem_present(stems, text_lines):
    # type: (List[Tuple[str, str]], List[str]) -> str
    """Return a diagnostic naming the first *stem* missing from
    *text_lines* (any line), or an empty string when all are present."""
    for stem, description in stems:
        if not any(stem in line for line in text_lines):
            return "%s (%r) missing from" % (description, stem)
    return ""


def _stem_absent(stems, text_lines):
    # type: (List[Tuple[str, str]], List[str]) -> str
    """Return a diagnostic naming the first *stem* still found in
    *text_lines* (any line), or an empty string when all are absent."""
    for stem, description in stems:
        for line in text_lines:
            if stem in line:
                return "%s (%r) still present: %s" % (
                    description,
                    stem,
                    line.strip(),
                )
    return ""


def _local_destination_lines():
    # type: () -> List[str]
    """All lower-cased lines of every file under ``.roo/`` OUTSIDE the
    shared ``rules/`` directory. The project-structure table's destination
    file is not named by the plan, so the presence assertions bind on the
    whole mode-specific tree; the shared ``rules/`` files are excluded so a
    bullet left behind fails the destination assertion instead of silently
    passing here."""
    lines = []
    for path in sorted((REPO_ROOT / ".roo").rglob("*")):
        if not path.is_file():
            continue
        try:
            if LOCAL_RULES_DIR in path.parents:
                continue
        except TypeError:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines.extend(_lower_lines(text))
    return lines


def _template_rule_dirs():
    # type: () -> List[str]
    return sorted(
        p.name for p in TEMPLATE_ROOT.iterdir() if p.is_dir() and p.name.startswith("rules-")
    )


# --------------------------------------------------------------------------- #
# Local half (gitignored .roo/): skip cleanly when absent
# --------------------------------------------------------------------------- #

class LocalRulesBase(unittest.TestCase):
    """Base for the local-half assertions: skips when ``.roo/`` is not
    provisioned (fresh clone / CI), and otherwise requires the three local
    files under test to exist -- a missing one is a failure, not a skip."""

    def setUp(self):
        if not (REPO_ROOT / ".roo").is_dir():
            self.skipTest(
                "anvil repo local .roo/ directory not provisioned; "
                "nothing to check"
            )
        for path in (SHARED_ARCHITECTURE, SHARED_CODING_GUIDELINES, LOCAL_QNA, LOCAL_DOCS):
            self.assertTrue(
                path.is_file(),
                "local rules file missing (not a skip; .roo/ is provisioned): %s"
                % path,
            )


class LocalQnaTestGuidelinesTests(LocalRulesBase):
    """The test guidelines leave the shared coding-guidelines.md for
    ``rules-qna-tester/instructions.xml`` -- present in the destination
    AND absent from the shared file (a bullet in both, or in neither,
    fails naming it)."""

    def test_test_guidelines_present_in_qna_tester_instructions(self):
        text_lines = _lower_lines(_read(LOCAL_QNA))
        missing = _stem_present(QNA_STEMS, text_lines)
        self.assertEqual(
            missing,
            "",
            "moved test guideline not present in .roo/rules-qna-tester/"
            "instructions.xml: %s" % missing,
        )

    def test_test_guidelines_absent_from_shared_coding_guidelines(self):
        text_lines = _lower_lines(_read(SHARED_CODING_GUIDELINES))
        present = _stem_absent(QNA_STEMS, text_lines)
        self.assertEqual(
            present,
            "",
            "moved test guideline not absent from the shared "
            ".roo/rules/coding-guidelines.md (a half-finished move costs "
            "more than no move): %s" % present,
        )

    def test_test_guidelines_heading_gone_from_shared(self):
        lines = _markdown_body(SHARED_CODING_GUIDELINES)
        section = _section_lines(lines, "Test guidelines")
        self.assertIsNone(
            section,
            "the shared coding-guidelines.md still carries a '## Test "
            "guidelines' section; the section is moved, not merely "
            "emptied",
        )


class LocalDocsGuidelinesTests(LocalRulesBase):
    """The documentation guidelines and the Documentation Finalisation
    section leave the shared coding-guidelines.md for
    ``rules-docs-manager/guidelines.xml``."""

    def test_documentation_guidelines_present_in_docs_manager_guidelines(self):
        text_lines = _lower_lines(_read(LOCAL_DOCS))
        missing = _stem_present(DOCS_STEMS + FINALISATION_STEMS, text_lines)
        self.assertEqual(
            missing,
            "",
            "moved documentation rule not present in .roo/rules-docs-manager/"
            "guidelines.xml: %s" % missing,
        )

    def test_documentation_guidelines_absent_from_shared_coding_guidelines(self):
        text_lines = _lower_lines(_read(SHARED_CODING_GUIDELINES))
        present = _stem_absent(DOCS_STEMS + FINALISATION_STEMS, text_lines)
        self.assertEqual(
            present,
            "",
            "moved documentation rule not absent from the shared "
            ".roo/rules/coding-guidelines.md (a half-finished move costs "
            "more than no move): %s" % present,
        )

    def test_documentation_sections_gone_from_shared(self):
        lines = _markdown_body(SHARED_CODING_GUIDELINES)
        for title in ("Documentation guidelines", "Documentation Finalisation"):
            self.assertIsNone(
                _section_lines(lines, title),
                "the shared coding-guidelines.md still carries a '## %s' "
                "section; the section is moved, not merely emptied" % title,
            )


class LocalProjectStructureTests(LocalRulesBase):
    """The module-by-module project-structure table leaves the shared
    architecture.md. Its destination file is not named by the plan, so
    presence is asserted across every file under ``.roo/`` outside the
    shared ``rules/`` directory."""

    def test_module_table_absent_from_shared_architecture(self):
        text_lines = _lower_lines(_read(SHARED_ARCHITECTURE))
        present = _stem_absent(
            [(stem, "module-table row %r" % stem) for stem in MODULE_TABLE_STEMS],
            text_lines,
        )
        self.assertEqual(
            present,
            "",
            "module-by-module detail not absent from the shared "
            ".roo/rules/architecture.md (a half-finished move costs more "
            "than no move): %s" % present,
        )

    def test_module_table_present_in_a_mode_specific_destination(self):
        text_lines = _local_destination_lines()
        missing = _stem_present(
            [(stem, "module-table row %r" % stem) for stem in MODULE_TABLE_STEMS],
            text_lines,
        )
        self.assertEqual(
            missing,
            "",
            "module-by-module detail found in neither the shared file "
            "nor any file under .roo/ outside rules/: %s" % missing,
        )


class LocalSharedRemainsTests(LocalRulesBase):
    """Guards: what every mode genuinely needs stays shared (expected
    green on arrival)."""

    def test_shared_architecture_keeps_orientation_boundary_and_precedence(self):
        text_lines = _lower_lines(_read(SHARED_ARCHITECTURE))
        missing = _stem_present(SHARED_ARCHITECTURE_MUST_KEEP, text_lines)
        self.assertEqual(
            missing,
            "",
            "content that must stay shared is missing from the shared "
            ".roo/rules/architecture.md: %s" % missing,
        )

    def test_shared_coding_guidelines_keeps_floor_policy_naming_and_safety(self):
        text_lines = _lower_lines(_read(SHARED_CODING_GUIDELINES))
        missing = _stem_present(SHARED_GUIDELINES_MUST_KEEP, text_lines)
        self.assertEqual(
            missing,
            "",
            "content that must stay shared is missing from the shared "
            ".roo/rules/coding-guidelines.md: %s" % missing,
        )


# --------------------------------------------------------------------------- #
# Template half (tracked): no move, one note
# --------------------------------------------------------------------------- #

class TemplateCodingGuidelinesNoteTests(unittest.TestCase):
    """The template's coding-guidelines.md gains a one-line note telling
    the filling-in agent to put mode-specific guidance in that mode's
    ``rules-{slug}/`` directory. The template files are placeholders;
    nothing in this module demands the template mirror the local move."""

    def setUp(self):
        self.assertTrue(
            TEMPLATE_CODING_GUIDELINES.is_file(),
            "tracked template file is missing: "
            "templates/roo_template/rules/coding-guidelines.md",
        )
        self.lines = _lower_lines(_read(TEMPLATE_CODING_GUIDELINES))

    def test_mode_specific_rules_slug_note_is_present(self):
        note_lines = [
            line for line in self.lines if "mode-specific" in line and "rules-" in line
        ]
        self.assertTrue(
            note_lines,
            "templates/roo_template/rules/coding-guidelines.md has no note "
            "pointing the filling-in agent at the mode-specific rules-{slug}/ "
            "directory (expected a line naming both 'mode-specific' and a "
            "'rules-...' directory)",
        )

    def test_mode_specific_note_is_one_line(self):
        # The plan says "a one-line note". Bound it: the word may appear on
        # exactly one line (rewording latitude is kept; a paragraph is not).
        count = sum(1 for line in self.lines if "mode-specific" in line)
        self.assertEqual(
            count,
            1,
            "the mode-specific guidance note spans %d lines; the plan "
            "calls for one line" % count,
        )

    def test_template_creates_no_new_rules_directories(self):
        # B9 creates no new template-side rules-{slug}/ directory, so no new
        # deployment assertion is needed: _deploy_mode_rules already copies
        # every rules-* directory it finds (B18 precedent).
        actual = _template_rule_dirs()
        self.assertEqual(
            set(actual),
            set(EXPECTED_TEMPLATE_RULE_DIRS),
            "template rules-* directories changed (expected %r, found %r); "
            "a new directory would also need a deployment assertion"
            % (sorted(EXPECTED_TEMPLATE_RULE_DIRS), actual),
        )


if __name__ == "__main__":
    unittest.main()
