"""Markdown prompt bodies from one instruction XML's text.

One job: build and validate the markdown body of a ``.pi/roles/*.md``
prompt document from one instruction XML's text, and nothing else.
Pure: text in, text out, no file I/O - the caller supplies the XML's
text; this module never reads ``templates/roo_template/`` itself. The
other plan behaviours (source map, shared body, frontmatter, budget)
have their own modules' cycles; the write seam for the finished
documents lives in ``anvilkit.render``
(``plans/pi-role-prompts.md`` behaviour 11).

House discipline, as ``anvilkit.pi.piverdict`` uses it: one behaviour
lands per red/green cycle, and the docstring says which one has
landed. Behaviour 4 of ``plans/pi-role-prompts.md``
(xml-to-prompt-body) is implemented here: ``body_from_xml(text)``
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

Error: empty or whitespace-only ``text`` raises ``PromptError``;
malformed XML raises ``PromptError`` naming the parse position the
parser reported; a root that is neither an ``<instructions>`` nor a
``<guidelines>`` element raises ``PromptError`` naming what it got;
and a document that
parses but carries no text raises ``PromptError`` too - never a
partial body, never a silent empty-string return.

Stdlib only. One exception type: ``PromptError``.
"""

import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple


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
