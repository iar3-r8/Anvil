"""Markdown prompt bodies and role documents for ``.pi/roles``.

One job: build and validate the markdown body of a ``.pi/roles/*.md``
prompt document, assemble the complete role document - frontmatter
plus body - for one named role, build the shared chain-root
document from the three tracked rule sources, and expose the role
source map, and nothing else.

House discipline, as ``anvilkit.pi.piverdict`` uses it: one behaviour
lands per red/green cycle, and the docstring says which ones have
landed. Three behaviours of ``plans/pi-role-prompts.md`` are
implemented here. Behaviour 4 (xml-to-prompt-body): ``body_from_xml(text)``
parses ``text`` as one ``<instructions>`` document (or the
docs-manager source's ``<guidelines>`` document, the plan's source
map's fourth tracked root) and returns a markdown body -
deterministic, so the same input twice is byte-identical.
``<overview>`` becomes a ``## Overview`` section; each
``<workflow>/<step>`` a numbered list item carrying its ``<title>``
and its own text (the step's ``number`` attribute when present, else
its position); each ``<best_practices>/<practice>`` a bullet; any
other section a heading plus one bullet per child. Only text nodes
are emitted - a raw XML tag spelling never survives in the body.

Behaviour 6 (frontmatter-shape): ``role_document(name)`` returns the
complete document - a YAML frontmatter block delimited by ``---``
lines, carrying exactly two keys (a non-empty ``description`` and
``extends: shared-agents``), then the markdown body - for one named
role. The body is ``body_from_xml``'s output for the role's tracked
source under ``templates/roo_template/``; the coder has no XML
source and carries the literal one-liner. The frontmatter is emitted
as literal text - ``yamlio`` stays the only module that touches
``yaml``, and the tests parse the block back. This module reads the
tracked template sources itself; the write seam for the finished
documents lives in ``anvilkit.render`` (behaviour 11).

Behaviour 7 (shared-prompt-is-root): ``shared_document()`` returns the
complete ``shared-agents`` document - one frontmatter block of its own
(a non-empty ``description``, no ``extends`` - it is the chain root -
and no ``model``/``thinking``/``tools``) over the bodies of the three
tracked rule sources under ``templates/roo_template/rules/``,
concatenated in the fixed order ``AGENTS.md``, ``architecture.md``,
``coding-guidelines.md`` - so it is the layer every role extends. Each
source's own Zoo frontmatter block is stripped: ``trigger:``/
``always_on`` is dispatch metadata for the Zoo renderer, not a rule,
and every markdown content line of each source's body survives in the
output. Deterministic - the same inputs twice give a byte-identical
document. The optional ``rules_dir`` parameter defaults to the tracked
directory; it exists so the missing-source error is testable against a
temp dir.

Behaviour 8 (role-source-map): ``source_for(name)`` is the public
surface of the module's private source table - the same table
``role_document``'s body lookup reads, so the two cannot drift. The
four XML roles return their path string relative to
``templates/roo_template/`` (e.g. ``rules-architect/instructions.xml``);
the coder has no XML source and returns the literal one-liner itself.

Error: empty or whitespace-only ``text`` raises ``PromptError``;
malformed XML raises ``PromptError`` naming the parse position the
parser reported; a root that is neither an ``<instructions>`` nor a
``<guidelines>`` element raises ``PromptError`` naming what it got;
and a document that
parses but carries no text raises ``PromptError`` too - never a
partial body, never a silent empty-string return.
``role_document`` raises ``PromptError`` for ``shared-agents`` - the
chain root has no parent to extend, and is built by behaviour 7's
``shared_document`` - and for an unknown role name, naming the role
and listing the known ones. ``source_for`` raises ``PromptError`` for
any name that is not one of the five roles - ``shared-agents``
included, the chain root having no source file of its own - naming it
and listing the six known names. ``shared_document`` raises
``PromptError`` naming a missing source file - never a partial document.

Stdlib only. One exception type: ``PromptError``.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class PromptError(Exception):
    """A prompt body this module could not build or validate.

    A single exception type covers every failure of
    ``body_from_xml``, so callers need only one ``except`` clause: an
    empty input, a malformed document (naming the parse position), a
    root that is neither an ``<instructions>`` nor a ``<guidelines>``
    element, and a document that parses but carries no text. Every
    message names the
    offending value, so a failure is fixable without reading the
    source.
    """


def body_from_xml(text: str) -> str:
    """Build the markdown body of one ``.pi/roles`` prompt document.

    ``text`` is one instruction XML's text - a document rooted at an
    ``<instructions>`` element, or at the docs-manager source's
    ``<guidelines>`` element (the plan's source map names both). The
    return is the markdown body only:
    no frontmatter, no file name, deterministic - the same input twice
    is byte-identical.

    Behaviour 4 (xml-to-prompt-body): the body carries the source's
    text nodes - the overview, each step's title and text, each
    practice - laid out as markdown headings, numbered items and
    bullets, with no raw XML tag spelling surviving in the output.

    Error: empty or whitespace-only ``text`` raises ``PromptError``;
    malformed XML raises ``PromptError`` naming the parse position;
    a root that is neither ``<instructions>`` nor ``<guidelines>``
    raises ``PromptError`` naming the tag it got; a document
    carrying no text at all raises
    ``PromptError`` - never a partial body, never an empty string.
    """
    if not text or not text.strip():
        raise PromptError(
            "the instruction XML text is empty; there is no body to build"
        )
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        # ParseError's str carries "line X, column Y" - the parse
        # position this behaviour pins into the message.
        raise PromptError(
            "malformed instruction XML at %s: no body is built from a "
            "document that does not parse" % str(exc)
        ) from exc
    if not isinstance(root.tag, str):
        raise PromptError(
            "the instruction XML root is not an element (got a %s); "
            "the body needs an <instructions> document"
            % type(root.tag).__name__
        )
    if root.tag not in ("instructions", "guidelines"):
        raise PromptError(
            "the instruction XML root must be <instructions> or "
            "<guidelines>, got <%s>" % root.tag
        )
    body = "\n".join(_render(root)).strip()
    if not body:
        raise PromptError(
            "the instruction XML carries no text; an empty body is "
            "never returned"
        )
    return body + "\n"


# The repo root: this file lives at <root>/anvilkit/pi/piprompt.py.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# The tracked rule sources, keyed by role name - the plan's source map
# (plans/pi-role-prompts.md behaviour 8), and the single source of
# truth for both role_document's body lookup and source_for's public
# surface, so the two cannot drift.
_ROLE_SOURCES = {
    "architect": "rules-architect/instructions.xml",
    "tester": "rules-qna-tester/instructions.xml",
    "docs": "rules-docs-manager/guidelines.xml",
    "tdd-manager": "rules-tdd-manager/instructions.xml",
}

# The coder carries no XML source: its body is this one-liner verbatim
# (the plan's decision 1 - nothing authored).
_CODER_BODY = "You write and modify code."

# The one-line purpose each role document carries as its frontmatter
# description: a non-empty plain YAML scalar, no characters that need
# quoting, so the literal-text frontmatter parses back by construction.
_ROLE_DESCRIPTIONS = {
    "architect": "Plan and design before implementation.",
    "coder": "Write and modify code.",
    "tester": "Write and run the tests for the behaviour.",
    "docs": "Keep documentation accurate after changes.",
    "tdd-manager": "Run test-driven development end to end.",
}

# The role names role_document serves, in the order the error message
# lists them. shared-agents is not here: it is the chain root, built by
# behaviour 7's shared_document, and refused by role_document.
_ROLE_NAMES = tuple(_ROLE_SOURCES) + ("coder",)

# The six known names behaviour 8's error line lists: the five roles
# plus the chain root. source_for and role_document's unknown-name
# errors both list this one tuple, so the two cannot drift.
_KNOWN_NAMES = _ROLE_NAMES + ("shared-agents",)

# The three shared rule sources, in the fixed order behaviour 7 pins:
# the shared document concatenates them in exactly this order, and the
# default rules dir the parameter falls back to.
_SHARED_SOURCES = ("AGENTS.md", "architecture.md", "coding-guidelines.md")
_SHARED_RULES_DIR = _REPO_ROOT / "templates" / "roo_template" / "rules"

# The shared document's own frontmatter description: the chain root
# every role extends. One non-empty plain YAML scalar, no characters
# that need quoting, so the literal-text frontmatter parses back by
# construction. No extends (it is the root) and no routing keys.
_SHARED_DESCRIPTION = "Shared rules every role extends."


def role_document(name: str) -> str:
    """Build the complete document for one named role.

    The return is the finished ``.pi/roles`` document: ``---`` on line
    1, a YAML frontmatter block carrying exactly two keys - a non-empty
    role-appropriate ``description`` and ``extends: shared-agents`` - a
    closing ``---``, then the markdown body. The body is
    ``body_from_xml``'s output for the role's tracked source under
    ``templates/roo_template/``; the coder has no XML source and carries
    the literal one-liner instead. The frontmatter is emitted as
    literal text (the plan's decision): ``yamlio`` stays the only
    module that touches ``yaml``, and the tests parse the block back.

    Behaviour 6 of ``plans/pi-role-prompts.md`` (frontmatter-shape) is
    implemented here: no ``model``, ``thinking`` or ``tools`` key ever
    appears - routing stays in ``pirole.ROLES``, a role file is not a
    routing authority.

    Error: ``shared-agents`` raises ``PromptError`` naming the role -
    the chain root has no parent to extend and is built by behaviour
    7's ``shared_body``; an unknown role name raises ``PromptError``
    naming the role and listing the known ones.
    """
    if name == "shared-agents":
        raise PromptError(
            "shared-agents is the chain root: it has no parent to "
            "extend, so it is never built by role_document"
        )
    if name not in _ROLE_NAMES:
        raise PromptError(
            "unknown role %r: the known names are %s"
            % (name, ", ".join(_KNOWN_NAMES))
        )
    body = _role_body(name)
    if not body.endswith("\n"):
        body += "\n"
    frontmatter = "description: %s\nextends: shared-agents" % _ROLE_DESCRIPTIONS[name]
    return "---\n" + frontmatter + "\n---\n" + body


def shared_document(rules_dir: Optional[Path] = None) -> str:
    """Build the complete ``shared-agents`` chain-root document.

    Behaviour 7 of ``plans/pi-role-prompts.md``
    (shared-prompt-is-root): the return is the finished
    ``.pi/roles/shared-agents.md`` document - a single YAML
    frontmatter block of its own, delimited by ``---`` lines, carrying
    only a non-empty ``description`` (no ``extends`` - it is the chain
    root and has no parent to extend - and no ``model``, ``thinking``
    or ``tools``; routing stays in ``pirole.ROLES``), then the bodies
    of the three tracked rule sources under ``rules_dir`` -
    ``AGENTS.md``, ``architecture.md``, ``coding-guidelines.md`` -
    concatenated in that fixed order, one blank line between sources,
    so it is the layer every role document extends.

    Each source's own Zoo frontmatter block is stripped: its
    ``trigger:``/``always_on`` is dispatch metadata for the Zoo
    renderer, not a rule, and every markdown content line of each
    source's body survives in the output. Deterministic - the same
    inputs twice give a byte-identical document.

    ``rules_dir`` defaults to the tracked
    ``templates/roo_template/rules/``; it exists so the missing-source
    error is testable against a temp dir.

    Error: a missing source file raises ``PromptError`` naming it -
    never a partial document.
    """
    if rules_dir is None:
        rules_dir = _SHARED_RULES_DIR
    bodies = []
    for name in _SHARED_SOURCES:
        path = rules_dir / name
        if not path.is_file():
            raise PromptError(
                "shared source %s is missing from %s: the shared "
                "document is built from all three sources, so no "
                "partial document is returned" % (name, rules_dir)
            )
        bodies.append(_strip_source_frontmatter(path.read_text(encoding="utf-8")))
    # One blank line between sources: the deterministic separator.
    body = "\n\n".join(bodies)
    if not body.endswith("\n"):
        body += "\n"
    return (
        "---\n"
        "description: %s\n"
        "---\n" % _SHARED_DESCRIPTION
    ) + body


def source_for(name: str) -> str:
    """The tracked source ``role_document`` builds ``name``'s body from.

    Behaviour 8 of ``plans/pi-role-prompts.md`` (role-source-map): the
    return is whatever ``role_document`` reads for this role's body -
    the same private table, so the two cannot drift. The four XML
    roles return their path string relative to
    ``templates/roo_template/``, exactly as the plan writes it (e.g.
    ``rules-architect/instructions.xml``); the coder has no XML source
    and returns the literal one-liner itself, not a sentinel.

    Error: any other name - ``shared-agents`` included, the chain root
    having no source file of its own - raises ``PromptError`` naming
    it and listing the six known names.
    """
    if name == "coder":
        return _CODER_BODY
    if name in _ROLE_SOURCES:
        return _ROLE_SOURCES[name]
    raise PromptError(
        "unknown role %r: the known names are %s"
        % (name, ", ".join(_KNOWN_NAMES))
    )


def _strip_source_frontmatter(text: str) -> str:
    """One rule source's markdown body, its own frontmatter stripped.

    The frontmatter block is the leading ``---`` line, the lines up to
    and including the first closing ``---`` after it - the same
    extraction ``tests/test_piprompt_frontmatter.py`` pins for the
    generated documents - and the body is the remainder, whitespace-
    trimmed. Raises ``PromptError`` naming the problem when the
    delimiters are missing, so a source whose body cannot be located
    fails loudly rather than leaking its own frontmatter into the
    shared document.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise PromptError(
            "a shared rule source does not open with a '---' "
            "frontmatter delimiter on line 1 (first line: %r)"
            % (lines[0] if lines else None)
        )
    close_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            close_index = index
            break
    if close_index is None:
        raise PromptError(
            "a shared rule source has no closing '---' delimiter after "
            "line 1, so its body cannot be located"
        )
    return "\n".join(lines[close_index + 1 :]).strip("\n")


def _role_body(name: str) -> str:
    """The markdown body for one known role: ``body_from_xml``'s output
    for the role's tracked XML source, or the coder's literal
    one-liner. Callers must have validated ``name`` against
    ``_ROLE_NAMES`` first."""
    if name == "coder":
        return _CODER_BODY
    source = _REPO_ROOT / "templates" / "roo_template" / _ROLE_SOURCES[name]
    return body_from_xml(source.read_text(encoding="utf-8"))


def _render(root: ET.Element) -> List[str]:
    """Lay the parsed document out as markdown lines, in document order."""
    lines = []
    for section in root:
        tag = section.tag
        if not isinstance(tag, str):
            raise PromptError(
                "the instruction XML carries a non-element node (a %s); "
                "only elements are rendered" % type(tag).__name__
            )
        if tag == "overview":
            _append_overview(lines, section)
        elif tag == "workflow":
            _append_workflow(lines, section)
        elif tag == "best_practices":
            _append_best_practices(lines, section)
        else:
            _append_generic(lines, tag, section)
    return lines


def _append_overview(lines: List[str], section: ET.Element) -> None:
    """``<overview>``: one ``## Overview`` section carrying its text."""
    text = _element_text(section)
    if not text:
        return
    lines.extend(["## Overview", "", text, ""])


def _append_workflow(lines: List[str], section: ET.Element) -> None:
    """``<workflow>``: one numbered list item per ``<step>``.

    A step's item is its ``number`` attribute when present, else its
    position; its ``<title>`` is bolded and the step's own text
    (title excluded) follows indented beneath it.
    """
    items = []
    for index, step in enumerate(section, start=1):
        title, body = _step_parts(step)
        number = step.get("number") or str(index)
        if title and body:
            items.append(("%s. **%s**" % (number, title), body))
        elif title:
            items.append(("%s. **%s**" % (number, title), ""))
        else:
            items.append(("%s. %s" % (number, body), ""))
    if not items:
        return
    lines.append("## Workflow")
    lines.append("")
    for first, rest in items:
        lines.append(first)
        if rest:
            lines.append("   %s" % rest)
    lines.append("")


def _append_best_practices(lines: List[str], section: ET.Element) -> None:
    """``<best_practices>``: one bullet per ``<practice>``."""
    bullets = [
        practice_text
        for practice_text in (_element_text(p) for p in section)
        if practice_text
    ]
    if not bullets:
        return
    lines.append("## Best practices")
    lines.append("")
    lines.extend("- %s" % bullet for bullet in bullets)
    lines.append("")


def _append_generic(
    lines: List[str], tag: str, section: ET.Element
) -> None:
    """Any other section: a title-cased heading, one bullet per child
    (or the section's own text when it has no children). A section
    without text contributes nothing rather than an empty heading."""
    heading = tag.replace("_", " ").strip().title() or "Section"
    children = list(section)
    if children:
        bullets = [
            child_text
            for child_text in (_element_text(c) for c in children)
            if child_text
        ]
        if not bullets:
            return
        lines.append("## %s" % heading)
        lines.append("")
        lines.extend("- %s" % bullet for bullet in bullets)
        lines.append("")
    else:
        text = _element_text(section)
        if not text:
            return
        lines.extend(["## %s" % heading, "", text, ""])


def _element_text(element: ET.Element) -> str:
    """All the text of ``element`` and its descendants, in document
    order, collapsed to single spaces.

    Only text nodes and tails are read - a tag name never survives,
    which is what keeps the body markdown rather than a string dump
    of the source.
    """
    parts = []
    if element.text:
        parts.append(element.text)
    for child in element:
        child_text = _element_text(child)
        if child_text:
            parts.append(child_text)
        if child.tail:
            parts.append(child.tail)
    return " ".join(
        part.strip() for part in parts if part and part.strip()
    )


def _step_parts(step: ET.Element) -> Tuple[Optional[str], str]:
    """A step's ``<title>`` text (or ``None``) and the step's own text
    with the ``<title>`` element excluded, both normalised."""
    title = None
    parts = []
    if step.text:
        parts.append(step.text)
    for child in step:
        if child.tag == "title":
            title = (child.text or "").strip() or None
        else:
            child_text = _element_text(child)
            if child_text:
                parts.append(child_text)
        if child.tail:
            parts.append(child.tail)
    body = " ".join(part.strip() for part in parts if part and part.strip())
    return title, body
