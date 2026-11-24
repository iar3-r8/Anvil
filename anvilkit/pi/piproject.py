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
    """
    project = record["project"]
    facts = (
        ("Repository", record["repo"]),
        ("Github user", record["owner"]),
        ("Name", project["name"]),
        ("Structure", project["structure"]),
        ("Configuration", project["configuration"]),
    )
    return _render(facts)


def _render(facts: Tuple[Tuple[str, str], ...]) -> str:
    """Join the heading and one labelled line per fact with newlines."""
    lines = ["# Project"]
    lines.extend("{}: {}".format(label, value) for label, value in facts)
    return "\n".join(lines)
