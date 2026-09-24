"""Tests for the AGENTS.md rule files.

plans/kiss-agent-rules.md, behaviour 1:

Behaviour 1 adds one new top-level section — a ``##`` heading naming simplicity,
for example ``## Keep It Simple`` — to both copies of the shared always-on agent
rules:

  * the template deployed by ``setup-repo``:
    ``templates/roo_template/rules/AGENTS.md``;
  * the anvil repo's own local copy: ``.roo/rules/AGENTS.md``.

The new section carries short assertive bullets stating six points (simplest
solution; optimise only when asked or measured; happy path first; fail safely;
log unexpected states; handle a rare edge case only when real users or real
data hit it, with a data-loss / security exception).

The template files are data and may be asserted on directly (precedent:
``tests/test_mcp_template.py`` and the docstring of ``tests/test_templates_rules.py``).
That precedent parses XML and asserts on parsed structure plus key phrases,
never on raw bytes; this module does the markdown equivalent — it parses
headings and bullet lines and asserts on the parsed structure plus key phrases,
never on whole-file text. The two files legitimately differ on the
repo-specific Github line, so whole-file equality between them is deliberately
not asserted.

Pattern: a shared base test case carrying the assertions, one concrete
subclass pointed at the template, one at the local ``.roo`` copy whose
``setUp`` skips cleanly when the file is absent (``.roo`` is gitignored, so
the copy is missing on a fresh clone / CI) — the B19/B20 pattern from
``tests/test_templates_rules.py``. A missing or unreadable TEMPLATE fails the
tests; only the local copy skips.
"""

import re
import unittest
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

AGENTS_TEMPLATE = (
    REPO_ROOT / "templates" / "roo_template" / "rules" / "AGENTS.md"
)
LOCAL_AGENTS = REPO_ROOT / ".roo" / "rules" / "AGENTS.md"

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+")

# A ``##`` heading names simplicity when its title carries one of these stems.
# Deliberately loose so the green step has latitude in the exact wording.
_SIMPLICITY_TITLE_STEMS = ("simpl", "kiss")


# --------------------------------------------------------------------------- #
# Markdown parsing helpers
# --------------------------------------------------------------------------- #

def _split_front_matter(lines):
    # type: (List[str]) -> Tuple[str, List[str]]
    """Split *lines* into (front-matter text, body lines).

    Front matter is the block between a leading ``---`` line and the next
    ``---`` line. Returns ``("", lines)`` when the file has no front matter,
    so a missing or truncated block fails the front-matter guard rather than
    being silently treated as intact.
    """
    if not lines or lines[0].strip() != "---":
        return "", lines
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), lines[i + 1:]
    return "", lines


def _section_lines(body_lines, level, title):
    # type: (List[str], int, str) -> Optional[List[str]]
    """Return the lines under the first heading of *level* whose title equals
    *title* (case-insensitive), up to the next heading of the same or a
    higher level. ``None`` when the heading is absent."""
    start = None
    for idx, line in enumerate(body_lines):
        match = _HEADING_RE.match(line)
        if (
            match
            and len(match.group(1)) == level
            and match.group(2).lower() == title.lower()
        ):
            start = idx + 1
            break
    if start is None:
        return None
    end = len(body_lines)
    for idx in range(start, len(body_lines)):
        match = _HEADING_RE.match(body_lines[idx])
        if match and len(match.group(1)) <= level:
            end = idx
            break
    return body_lines[start:end]


def _section_text(section_lines):
    # type: (Optional[List[str]]) -> str
    """All of a section's lines as one lower-cased string."""
    if section_lines is None:
        return ""
    return " ".join(section_lines).lower()


def _bullet_lines(section_lines):
    # type: (Optional[List[str]]) -> List[str]
    """The bullet lines (``-``/``*``/``+`` items at any indent) in a section."""
    if section_lines is None:
        return []
    return [line for line in section_lines if _BULLET_RE.match(line)]


def _bullets_text(section_lines):
    # type: (Optional[List[str]]) -> str
    """A section's bullet lines as one lower-cased string."""
    return " ".join(_bullet_lines(section_lines)).lower()


def _simplicity_section_lines(body_lines):
    # type: (List[str]) -> Optional[List[str]]
    """The lines under the first ``##`` heading whose title names simplicity
    (``simpl``/``kiss`` stem), up to the next ``##`` or top-level heading.
    ``None`` when no such section exists — the red state."""
    start = None
    for idx, line in enumerate(body_lines):
        match = _HEADING_RE.match(line)
        if match and len(match.group(1)) == 2:
            title = match.group(2).lower()
            if any(stem in title for stem in _SIMPLICITY_TITLE_STEMS):
                start = idx + 1
                break
    if start is None:
        return None
    end = len(body_lines)
    for idx in range(start, len(body_lines)):
        match = _HEADING_RE.match(body_lines[idx])
        if match and len(match.group(1)) <= 2:
            end = idx
            break
    return body_lines[start:end]


def _mcp_hygiene_intro_lines(body_lines):
    # type: (List[str]) -> Optional[List[str]]
    """The lines under ``## MCP server or tool usage`` that come BEFORE the
    first ``###`` subsection — where plans/cut-agent-context-cost.md (B7)
    places the new hygiene bullets.

    Slicing here (instead of the whole section) is what keeps a bullet added
    under ``### Github`` or ``### Oxylabs`` from passing: it lands in a
    subsection, not the intro. ``None`` when the ``##`` section or either
    subsection is missing — a red state that the placement test reports."""
    section = _section_lines(body_lines, 2, "MCP server or tool usage")
    if section is None:
        return None
    intro = []
    for line in section:
        match = _HEADING_RE.match(line)
        if match and len(match.group(1)) == 3:
            break
        intro.append(line)
    return intro


def _heading_span(body_lines, level, title):
    # type: (List[str], int, str) -> Optional[Tuple[int, int]]
    """The ``(start, end)`` body-line indices of the first heading of
    *level* whose title equals *title* (case-insensitive): ``start`` is the
    line after the heading, ``end`` the index of the next heading of the
    same or a higher level (the body's end when there is none). ``None``
    when the heading is absent.

    The indices are what the orphan test needs — the surviving-subsection
    tests call ``_section_lines`` over the whole body, so they cannot tell
    a ``###`` subsection nested under ``## MCP server or tool usage`` from
    one that has been pushed under some other ``##`` heading."""
    start = None
    for idx, line in enumerate(body_lines):
        match = _HEADING_RE.match(line)
        if (
            match
            and len(match.group(1)) == level
            and match.group(2).lower() == title.lower()
        ):
            start = idx + 1
            break
    if start is None:
        return None
    end = len(body_lines)
    for idx in range(start, len(body_lines)):
        match = _HEADING_RE.match(body_lines[idx])
        if match and len(match.group(1)) <= level:
            end = idx
            break
    return start, end


# --------------------------------------------------------------------------- #
# Base test case: loads and parses one AGENTS.md file
# --------------------------------------------------------------------------- #

class AgentsRulesBase(unittest.TestCase):
    """Shared loading/parsing and assertions for the AGENTS.md files.

    Subclasses set ``template_path``; ``setUp`` reads and splits it once so
    every test asserts on parsed structure. A missing or unreadable file
    raises here and fails the tests — the local subclass skips first, so only
    the template path relies on the failure.

    The class itself is collected by ``unittest`` because it is a
    ``TestCase`` subclass carrying test methods; ``setUp`` skips it, so
    only the two concrete subclasses run the assertions (precedent:
    ``TddManagerRequirementBase`` in ``tests/test_templates_rules.py``).
    """

    template_path = None

    def setUp(self):
        if self.template_path is None:
            self.skipTest("abstract base class; run a concrete subclass")
        text = self.template_path.read_text(encoding="utf-8")
        self.front_matter, self.body_lines = _split_front_matter(
            text.splitlines()
        )
        self.simplicity_lines = _simplicity_section_lines(self.body_lines)

    # -- edge guards: pre-existing content survives (pass now, keep passing) -- #

    def test_yaml_front_matter_intact_with_always_on_trigger(self):
        self.assertNotEqual(
            self.front_matter,
            "",
            "AGENTS.md lost its YAML front matter block",
        )
        self.assertIn(
            "trigger: always_on",
            self.front_matter,
            "front matter no longer declares trigger: always_on; got %r"
            % self.front_matter,
        )
        self.assertIn(
            "description: Agent guidelines",
            self.front_matter,
            "front matter no longer declares the Agent guidelines "
            "description; got %r" % self.front_matter,
        )

    def test_code_change_process_section_survives_with_its_four_bullets(self):
        section = _section_lines(self.body_lines, 2, "Code Change Process")
        self.assertIsNotNone(
            section,
            "the ## Code Change Process section is missing",
        )
        bullets = _bullets_text(section)
        for marker in (
            "do not jump to conclusions",
            "ask for clarification",
            "collaborate first",
            "present options",
        ):
            self.assertIn(
                marker,
                bullets,
                "a Code Change Process bullet is missing or was altered "
                "(expected marker %r). Bullets: %r" % (marker, bullets),
            )

    def test_mcp_server_section_survives(self):
        section = _section_lines(self.body_lines, 2, "MCP server or tool usage")
        self.assertIsNotNone(
            section,
            "the ## MCP server or tool usage section is missing",
        )
        self.assertTrue(
            _section_text(section).strip(),
            "the MCP server or tool usage section is empty",
        )

    def test_github_subsection_survives(self):
        section = _section_lines(self.body_lines, 3, "Github")
        self.assertIsNotNone(section, "the ### Github subsection is missing")
        self.assertIn(
            "github mcp",
            _section_text(section),
            "the ### Github subsection no longer names the github MCP",
        )

    def test_oxylabs_subsection_survives_with_its_bullets(self):
        section = _section_lines(self.body_lines, 3, "Oxylabs")
        self.assertIsNotNone(
            section, "the ### Oxylabs subsection is missing"
        )
        bullets = _bullets_text(section)
        for marker in ("blocking", "doc/external", "cite", "unavailable"):
            self.assertIn(
                marker,
                bullets,
                "an Oxylabs bullet is missing or was altered (expected "
                "marker %r). Bullets: %r" % (marker, bullets),
            )

    # -- B7 (plans/cut-agent-context-cost.md): MCP call hygiene -- #
    #
    # Three bullets under the existing ``## MCP server or tool usage`` section:
    # prefer narrow queries; request the smallest page size that answers the
    # question; keep issue comments short BECAUSE every add_issue_comment
    # echoes the body back. The stems are deliberately loose so the green
    # step can word the bullets naturally; the echo-back reason is the
    # substance, so it is matched on two separate stems ("echo" plus
    # "add_issue_comment") rather than one long phrase.

    def test_mcp_hygiene_bullets_exist_before_the_subsections(self):
        intro = _mcp_hygiene_intro_lines(self.body_lines)
        self.assertIsNotNone(
            intro,
            "cannot locate the intro of the ## MCP server or tool usage "
            "section (the section or a ### subsection is missing) in %s"
            % self.template_path,
        )
        self.assertTrue(
            any(_BULLET_RE.match(line) for line in intro),
            "no bullets sit under ## MCP server or tool usage before its "
            "first ### subsection — the B7 hygiene bullets are missing. "
            "Intro lines: %r" % intro,
        )

    def test_mcp_hygiene_bullets_prefer_narrow_queries(self):
        text = _section_text(_mcp_hygiene_intro_lines(self.body_lines))
        self.assertIn(
            "narrow",
            text,
            "no MCP hygiene bullet says to prefer narrow queries. "
            "Section intro: %r" % text,
        )

    def test_mcp_hygiene_bullets_request_smallest_page_size(self):
        text = _section_text(_mcp_hygiene_intro_lines(self.body_lines))
        self.assertIn(
            "smallest page size",
            text,
            "no MCP hygiene bullet says to request the smallest page size "
            "that answers the question. Section intro: %r" % text,
        )

    def test_mcp_hygiene_bullets_keep_issue_comments_short(self):
        text = _section_text(_mcp_hygiene_intro_lines(self.body_lines))
        self.assertTrue(
            ("issue comment" in text) and ("short" in text),
            "no MCP hygiene bullet says to keep issue comments short. "
            "Section intro: %r" % text,
        )

    def test_mcp_hygiene_bullets_explain_the_add_issue_comment_echo_cost(
        self,
    ):
        text = _section_text(_mcp_hygiene_intro_lines(self.body_lines))
        self.assertTrue(
            ("add_issue_comment" in text) and ("echo" in text),
            "no MCP hygiene bullet carries the causal clause: because every "
            "add_issue_comment echoes the body back, a long comment is paid "
            "for on arrival and again on every later turn. "
            "Section intro: %r" % text,
        )

    def test_mcp_hygiene_bullets_do_not_orphan_the_subsections(self):
        section = _heading_span(
            self.body_lines, 2, "MCP server or tool usage"
        )
        self.assertIsNotNone(
            section,
            "the ## MCP server or tool usage section is missing in %s, so "
            "the B7 bullets have nowhere valid to live" % self.template_path,
        )
        for title in ("Github", "Oxylabs"):
            span = _heading_span(self.body_lines, 3, title)
            self.assertIsNotNone(
                span,
                "the ### %s subsection is missing — the B7 bullets must "
                "not orphan it" % title,
            )
            self.assertTrue(
                section[0] < span[0] and span[1] <= section[1],
                "the ### %s subsection is no longer nested inside ## MCP "
                "server or tool usage (section spans body lines %d..%d, "
                "subsection spans %d..%d) — the B7 bullets were placed "
                "outside the section"
                % (title, section[0], section[1], span[0], span[1]),
            )

    # -- the behaviour: a ## simplicity section with six assertive bullets -- #

    def test_simplicity_section_exists_with_a_top_level_heading(self):
        self.assertIsNotNone(
            self.simplicity_lines,
            "no top-level (##) heading naming simplicity (e.g. "
            "'## Keep It Simple') was found in %s" % self.template_path,
        )

    def test_simplicity_bullets_name_the_simplest_solution(self):
        text = _bullets_text(self.simplicity_lines)
        self.assertTrue(
            ("simpl" in text) and ("solution" in text),
            "no simplicity bullet says the simplest solution that meets "
            "the requirement is the right one. Bullets: %r" % text,
        )

    def test_simplicity_bullets_optimise_only_when_asked_or_measured(self):
        text = _bullets_text(self.simplicity_lines)
        asked = ("ask" in text) or ("request" in text) or ("measured" in text)
        self.assertTrue(
            ("optimi" in text) and asked,
            "no simplicity bullet restricts optimisation to what the user "
            "asks for or a measured problem. Bullets: %r" % text,
        )

    def test_simplicity_bullets_build_the_happy_path_first(self):
        text = _bullets_text(self.simplicity_lines)
        self.assertIn(
            "happy path",
            text,
            "no simplicity bullet says to build the happy path first, "
            "delivering the main feature before the rare case. "
            "Bullets: %r" % text,
        )

    def test_simplicity_bullets_fail_safely(self):
        text = _bullets_text(self.simplicity_lines)
        self.assertTrue(
            ("fail" in text) and ("safe" in text),
            "no simplicity bullet says to fail safely (clear controlled "
            "error or safe default) on an unexpected state. "
            "Bullets: %r" % text,
        )

    def test_simplicity_bullets_log_unexpected_states(self):
        text = _bullets_text(self.simplicity_lines)
        self.assertTrue(
            ("log" in text) and ("unexpected" in text),
            "no simplicity bullet says to log unexpected states so their "
            "real frequency is known. Bullets: %r" % text,
        )

    def test_simplicity_bullets_handle_rare_edge_cases_when_real(self):
        text = _bullets_text(self.simplicity_lines)
        real = ("real user" in text) or ("real data" in text)
        self.assertTrue(
            ("edge case" in text) and real,
            "no simplicity bullet defers a rare edge case until real "
            "users or real data hit it. Bullets: %r" % text,
        )

    def test_simplicity_bullets_fix_data_loss_or_security_immediately(self):
        text = _bullets_text(self.simplicity_lines)
        self.assertTrue(
            ("data loss" in text) or ("data-loss" in text) or ("security" in text),
            "no simplicity bullet names the exception: a data-loss or "
            "security risk is fixed immediately. Bullets: %r" % text,
        )


class TemplateAgentsRulesTests(AgentsRulesBase):
    """Behaviour 1: the AGENTS.md TEMPLATE gains the simplicity section."""

    template_path = AGENTS_TEMPLATE

    def test_github_line_keeps_repo_placeholders(self):
        # Edge: the repo-specific Github line is undisturbed on the template
        # side; it carries the deployment placeholders, not real names.
        section = _section_lines(self.body_lines, 3, "Github")
        self.assertIsNotNone(section, "the ### Github subsection is missing")
        text = _section_text(section)
        self.assertIn("<github user>", text)
        self.assertIn("<repository name>", text)


class LocalAgentsRulesTests(AgentsRulesBase):
    """Behaviour 1: the anvil repo's OWN AGENTS.md carries the same section.

    The same assertions run against the local copy, so it cannot drift from
    the template on this point. Only the new rules and the surviving
    sections are locked, never whole-file equality.

    ``.roo`` is gitignored, so the local copy is absent on a fresh clone
    (and on CI). ``setUp`` skips every test cleanly in that case; when the
    file is provisioned, the full assertion set runs exactly as written in
    the base class.
    """

    template_path = LOCAL_AGENTS

    def setUp(self):
        if not self.template_path.exists():
            self.skipTest(
                "anvil repo local .roo/rules/AGENTS.md not provisioned; "
                "nothing to check"
            )
        super().setUp()

    def test_github_line_names_the_anvil_repo(self):
        # Edge: the repo-specific Github line is undisturbed on the local
        # side; it names the real user and repository.
        section = _section_lines(self.body_lines, 3, "Github")
        self.assertIsNotNone(section, "the ### Github subsection is missing")
        text = _section_text(section)
        self.assertIn("iar3-r8", text)
        self.assertIn("anvil", text)


if __name__ == "__main__":
    unittest.main()
