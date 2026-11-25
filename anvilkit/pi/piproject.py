"""Render the profile record into the ``project.md`` document text.

One concern only (``plans/pi-phase12-launch-gen.md``, behaviour 1): turn the
record ``piprofile.load_profile`` returns into the ``project.md`` text that
``pilaunch.generate`` writes into ``<repo>/.pi/roles/``. The document carries
the five project facts — the record's top-level ``owner`` and ``repo`` plus
the ``project`` block's ``name``, ``structure`` and ``configuration`` — each
on its own labelled line, so the values fill the
``<Repository name>`` / ``<Github user>`` placeholders the shared rule
sources leave behind.

The document is built from the record's values, not substituted into a
template, so no value is escaped or mangled on its way in.

Stdlib only. One exception type: ``ProjectError``, the module's single
failure point for the error paths its later behaviours raise.
"""

from typing import Any, Dict, Tuple


#: The pinned wording an absent field renders on its labelled line.
_NOT_RECORDED = "not recorded"


class ProjectError(Exception):
    """The profile record cannot be turned into the ``project.md`` text.

    A single exception type covers every refusal this module raises, so
    callers need only one ``except`` clause. Every message names the field
    whose value is at fault.
    """


def project_document(record: Dict[str, Any]) -> str:
    """Return the ``project.md`` text for a loaded profile record.

    The record is the mapping ``piprofile.load_profile`` returns: top-level
    ``owner`` and ``repo`` plus a ``project`` block holding ``name``,
    ``structure`` and ``configuration``. The five values are rendered one per
    labelled line, in that order, under a single ``# Project`` heading, so
    the shared sources' ``<Repository name>`` / ``<Github user>``
    placeholders are filled by real values.

    A field whose key is missing or whose value is ``None`` renders the
    pinned line ``not recorded`` instead — an absent field is never a
    refusal and never raises; the empty ``project`` block
    ``piprofileflow.record_profile`` writes today is the common case.

    A record that is not a mapping, or a ``project`` value that is present
    but not a mapping, is refused with ``ProjectError`` naming the field
    (``record`` or ``project``) and its actual type, raised before any text
    is built (``plans/pi-phase12-launch-gen.md``, behaviour 3). A missing
    ``project`` key is an absent field, not a refusal.
    """
    if not isinstance(record, dict):
        raise ProjectError(
            "record must be a mapping, got {}".format(type(record).__name__)
        )
    if "project" in record and not isinstance(record["project"], dict):
        raise ProjectError(
            "project must be a mapping, got {}".format(
                type(record["project"]).__name__
            )
        )
    project = record.get("project")
    if project is None:
        project = {}
    facts = (
        ("Repository", _value(record, "repo")),
        ("Github user", _value(record, "owner")),
        ("Name", _value(project, "name")),
        ("Structure", _value(project, "structure")),
        ("Configuration", _value(project, "configuration")),
    )
    return _render(facts)


def _value(mapping: Dict[str, Any], key: str) -> str:
    """Return ``mapping[key]``, or the pinned absence wording if absent.

    A missing key and a ``None`` value are both absent; anything else is
    rendered verbatim.
    """
    value = mapping.get(key)
    return _NOT_RECORDED if value is None else value


def _render(facts: Tuple[Tuple[str, str], ...]) -> str:
    """Join the heading and one labelled line per fact with newlines."""
    lines = ["# Project"]
    lines.extend("{}: {}".format(label, value) for label, value in facts)
    return "\n".join(lines)
