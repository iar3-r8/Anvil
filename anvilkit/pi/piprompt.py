"""Markdown prompt documents for ``.pi/roles``.

One job: build the markdown body of a prompt document from its
instruction XML, assemble the five role documents and the shared
chain-root document from the tracked rule sources, and report their
token budgets. Deterministic: the same inputs twice give
byte-identical documents. Stdlib only. One exception type:
``PromptError``.
"""

import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class PromptError(Exception):
    """A prompt document this module could not build or validate.

    One type for every failure - empty or malformed input, an
    unexpected root tag, a missing source file, an unknown role name -
    so callers need a single ``except``; every message names the
    offending value.
    """


def body_from_xml(text: str) -> str:
    """Build the markdown body of one ``.pi/roles`` prompt document.

    ``text`` is one instruction XML document, rooted at
    ``<instructions>`` or the docs-manager source's ``<guidelines>``.
    Returns the markdown body only - no frontmatter - deterministic,
    and never partial or empty: a textless, malformed or wrongly-
    rooted document raises ``PromptError`` naming the problem.
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

# The tracked template root the role documents read their XML sources
# from by default: the parent of the shared rules dir.
_TEMPLATES_ROOT = _REPO_ROOT / "templates" / "roo_template"

# The three shared rule sources, in the fixed order behaviour 7 pins:
# the shared document concatenates them in exactly this order, and the
# default rules dir the parameter falls back to.
_SHARED_SOURCES = ("AGENTS.md", "architecture.md", "coding-guidelines.md")
_SHARED_RULES_DIR = _TEMPLATES_ROOT / "rules"

# The shared document's own frontmatter description: the chain root
# every role extends. One non-empty plain YAML scalar, no characters
# that need quoting, so the literal-text frontmatter parses back by
# construction. No extends (it is the root) and no routing keys.
_SHARED_DESCRIPTION = "Shared rules every role extends."


def role_document(name: str, templates_root: Optional[Path] = None) -> str:
    """Build the complete document for one named role.

    Returns the finished ``.pi/roles`` document: a YAML frontmatter
    block carrying a role-appropriate ``description`` and
    ``extends: shared-agents``, then the markdown body built from the
    role's tracked source. Deterministic, and no ``model``,
    ``thinking`` or ``tools`` key ever appears. ``shared-agents`` (the
    chain root, built by ``shared_document``), an unknown name, or a
    missing source raises ``PromptError`` naming it - no partial
    document is ever returned. ``templates_root`` defaults to the
    tracked ``templates/roo_template/``.
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
    body = _role_body(name, templates_root)
    if not body.endswith("\n"):
        body += "\n"
    frontmatter = "description: %s\nextends: shared-agents" % _ROLE_DESCRIPTIONS[name]
    return "---\n" + frontmatter + "\n---\n" + body


def shared_document(rules_dir: Optional[Path] = None) -> str:
    """Build the complete ``shared-agents`` chain-root document.

    Returns the layer every role document extends: a frontmatter block
    of its own (a non-empty ``description``, no ``extends``), then the
    bodies of the three tracked shared rule sources, concatenated in
    the fixed order ``AGENTS.md``, ``architecture.md``,
    ``coding-guidelines.md``, one blank line between sources. Each
    source's own frontmatter is stripped; every content line survives.
    Deterministic; a missing source raises ``PromptError`` naming it -
    never a partial document. ``rules_dir`` defaults to the tracked
    ``templates/roo_template/rules/``.
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

    The four XML roles return their path relative to
    ``templates/roo_template/`` (e.g. ``rules-architect/instructions.xml``);
    the coder has no XML source and returns its literal one-liner. Any
    other name - ``shared-agents`` included - raises ``PromptError``
    naming it and listing the known names.
    """
    if name == "coder":
        return _CODER_BODY
    if name in _ROLE_SOURCES:
        return _ROLE_SOURCES[name]
    raise PromptError(
        "unknown role %r: the known names are %s"
        % (name, ", ".join(_KNOWN_NAMES))
    )


def all_documents() -> Dict[str, str]:
    """The six ``.pi/roles`` documents, keyed by file stem.

    ``shared-agents`` from ``shared_document()`` and the five roles from
    ``role_document(name)`` - the complete regeneration of the committed
    documents, and the single entry point the drift guard and the write
    seam consume. Deterministic: two calls are byte-identical.
    """
    return {
        "shared-agents": shared_document(),
        "architect": role_document("architect"),
        "coder": role_document("coder"),
        "tester": role_document("tester"),
        "docs": role_document("docs"),
        "tdd-manager": role_document("tdd-manager"),
    }


def estimate_tokens(text: str) -> int:
    """A conservative token estimate for one prompt document's text.

    Returns ``ceil(len(text.encode("utf-8")) / 3)`` - an exact ``int``,
    deterministic and monotonic in the text's UTF-8 byte length, so a
    budget check can divide and compare it against the model's window.
    A deliberate over-estimate, not a tokenizer: a pass against the
    window is trustworthy, a fail may be conservative. Empty text
    returns 0.
    """
    return math.ceil(len(text.encode("utf-8")) / 3)


def budget_report(documents: Dict[str, str], window: int) -> List[Dict[str, Any]]:
    """The token-budget report over a set of role documents.

    ``documents`` maps stem to full document text (as
    ``all_documents()`` returns it); ``window`` is the model's context
    window. Returns one record per key in sorted-key order, each with
    ``name``, ``estimate``, ``window`` and ``within``: the estimate is
    ``estimate_tokens`` of the stem's layered total - shared document
    plus role document, or the document itself for ``shared-agents``
    (the chain root, nothing prepended to it). Records only: an
    over-budget role is reported with ``within`` False, never raised,
    and no document text is ever shortened, elided or rewritten.
    Deterministic: the same inputs twice give equal records.
    """
    records = []
    for name in sorted(documents):
        if name == "shared-agents":
            layered = documents["shared-agents"]
        else:
            layered = documents["shared-agents"] + documents[name]
        estimate = estimate_tokens(layered)
        records.append(
            {
                "name": name,
                "estimate": estimate,
                "window": window,
                "within": estimate <= window,
            }
        )
    return records


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


def _role_body(name: str, templates_root: Optional[Path]) -> str:
    """The markdown body for one known role: ``body_from_xml``'s output
    for the role's XML source under ``templates_root``, or the coder's
    literal one-liner. Callers must have validated ``name`` against
    ``_ROLE_NAMES`` first. ``templates_root`` of ``None`` means the
    tracked ``templates/roo_template/``. A known role whose source file
    is absent under ``templates_root`` raises ``PromptError`` naming
    the role and the relative path - a missing source never yields a
    partial or empty-body document."""
    if name == "coder":
        return _CODER_BODY
    root = templates_root if templates_root is not None else _TEMPLATES_ROOT
    relative = _ROLE_SOURCES[name]
    source = root / relative
    if not source.is_file():
        raise PromptError(
            "source for role %r is missing: looked for %s under %s, "
            "and no document is returned for a role whose source is "
            "absent" % (name, relative, root)
        )
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
