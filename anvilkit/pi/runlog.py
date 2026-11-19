"""Run-log run ids and the run archive (``plans/pi-phase11-runlog.md``).

A run id is ``run-YYYYMMDD-HHMMSS-<4hex>``: a zero-padded UTC stamp plus a
4-char lowercase-hex entropy suffix, so every Pi run (and the ``<run-id>-<role>``
session ids derived under it) is uniquely addressable. This module owns the id
format and its validation only - it does not touch the archive, the driver or
Pi itself.

``new_run_id`` accepts both values explicitly (behaviour 1); when either is
omitted it is computed at call time from the module's own references -
``datetime.now(timezone.utc)`` for the stamp and ``secrets.token_hex(2)`` for
the suffix (behaviour 2) - never local time, never a counter. Those
references are module-level names exactly so callers can patch them.

``start_run`` opens a run's archive directory ``logs/runs/<run-id>/`` and
writes ``meta.json`` before anything else runs (behaviour 6): a run that
dies mid-way leaves a readable record, with ``finished_at`` null,
``outcome`` unknown and ``complete`` false. Validation of ``intake``,
``sessions`` and ``started_at`` happens before any filesystem I/O, so a
rejected run is never half-recorded.

Stdlib only. One exception type: ``RunLogError``.
"""

import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from anvilkit.pi import pirole


class RunLogError(Exception):
    """A run id that cannot be built, or a run log that cannot be written."""


def new_run_id(
    now: Optional[datetime] = None,
    entropy: Optional[str] = None,
) -> str:
    """Return ``run-YYYYMMDD-HHMMSS-<4hex>`` for the instant ``now``.

    ``now`` must be an aware datetime in UTC; ``entropy`` must be exactly
    four lowercase hex characters. Either violation raises ``RunLogError``
    naming the offending value. When ``now`` is ``None`` it defaults to
    ``datetime.now(timezone.utc)`` and when ``entropy`` is ``None`` it
    defaults to ``secrets.token_hex(2)``, both consulted at call time via
    the module-level ``datetime`` and ``secrets`` references.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if entropy is None:
        entropy = secrets.token_hex(2)
    if now.utcoffset() is None:
        raise RunLogError(
            "now must be an aware datetime in UTC, got naive %r" % (now,)
        )
    if now.utcoffset() != timedelta(0):
        raise RunLogError(
            "now must be a UTC datetime, got %r" % (now,)
        )
    if len(entropy) != 4 or any(
        char not in "0123456789abcdef" for char in entropy
    ):
        raise RunLogError(
            "entropy must be exactly 4 lowercase hex chars, got %r"
            % (entropy,)
        )
    return "run-" + now.strftime("%Y%m%d-%H%M%S") + "-" + entropy


def session_id(run_id: str, role: str) -> str:
    """Return ``<run-id>-<role>`` for the run ``run_id``.

    The run id crosses through verbatim - it is not revalidated against
    ``new_run_id``'s format, so a syntactically valid string this module
    would never produce still gets the role appended. The role is the only
    checked input: it must be one of ``pirole.ROLES``, and any other value
    raises ``RunLogError`` naming the offending role and listing all four
    known roles.
    """
    if role not in pirole.ROLES:
        raise RunLogError(
            "unknown role %r: the known roles are %s"
            % (role, ", ".join(pirole.ROLES))
        )
    return run_id + "-" + role


def start_run(
    root: Path,
    run_id: str,
    intake: Dict[str, object],
    sessions: Dict[str, str],
    started_at: str,
) -> Path:
    """Open the archive directory for run ``run_id`` and write its ``meta.json``.

    If ``root/logs/runs/<run-id>/`` already exists the run is refused before
    any validation or I/O: ``RunLogError`` names the run id and nothing on
    disk is touched (behaviour 7 - a past run is evidence and is never
    overwritten).

    Creates ``root/logs/runs/<run-id>/`` and writes ``meta.json`` with exactly
    the seven planned keys - ``run_id``, ``started_at``, ``finished_at`` (null),
    ``intake``, ``sessions``, ``outcome`` (``"unknown"``) and ``complete``
    (false) - so a run that dies mid-way leaves a readable record. Returns the
    run directory's ``Path``.

    ``run_id`` is taken as given (it is produced by ``new_run_id``). The other
    three inputs are validated before any filesystem I/O: ``intake`` must be a
    dict with exactly the keys ``{"issue", "text"}``, ``sessions`` must be a
    dict whose keys are all in ``pirole.ROLES``, and ``started_at`` must be a
    ``str``. Any violation raises ``RunLogError`` naming the offending field
    (or role) and leaves no ``meta.json`` behind.
    """
    run_dir = root / "logs" / "runs" / run_id
    if run_dir.exists():
        raise RunLogError(
            "run %r already has an archive at %s and will not be "
            "overwritten" % (run_id, run_dir)
        )
    _validate_start_inputs(intake, sessions, started_at)
    run_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": None,
        "intake": intake,
        "sessions": sessions,
        "outcome": "unknown",
        "complete": False,
    }
    (run_dir / "meta.json").write_text(
        json.dumps(meta), encoding="utf-8"
    )
    return run_dir


def _validate_start_inputs(
    intake: object,
    sessions: object,
    started_at: object,
) -> None:
    """Check the three validated ``start_run`` inputs; raise ``RunLogError``.

    Pure validation - no filesystem I/O - so a rejected run is never
    half-recorded. Each violation names its field: ``intake`` for a missing,
    extra or non-dict intake, ``sessions`` (or the offending role) for a
    non-dict sessions map or an unknown role, and ``started_at`` for a
    non-string value.
    """
    if not isinstance(intake, dict) or set(intake.keys()) != {"issue", "text"}:
        raise RunLogError(
            "intake must be a dict with exactly the keys "
            "{'issue', 'text'}, got %r" % (intake,)
        )
    if not isinstance(sessions, dict):
        raise RunLogError(
            "sessions must be a dict of role to session id, got %r"
            % (sessions,)
        )
    for role in sessions:
        if role not in pirole.ROLES:
            raise RunLogError(
                "sessions has an unknown role %r: the known roles are %s"
                % (role, ", ".join(pirole.ROLES))
            )
    if not isinstance(started_at, str):
        raise RunLogError(
            "started_at must be a str, got %r" % (started_at,)
        )


def write_stream(run_dir: Path, role: str, text: str) -> None:
    """Write the role's captured stream to ``<role>.jsonl`` byte-for-byte.

    ``text`` is the driver's captured ``result["stdout"]`` and is written
    verbatim in UTF-8 with no newline added: an empty stream writes an empty
    file, and an unparseable stream is kept unchanged - the captured bytes
    are data, so this module never parses or rewrites a stream. ``role``
    must be one of ``pirole.ROLES`` (otherwise ``RunLogError`` names the
    role and no file is created), and ``run_dir`` must exist as a directory
    (otherwise ``RunLogError`` names the path).
    """
    if role not in pirole.ROLES:
        raise RunLogError(
            "unknown role %r: the known roles are %s"
            % (role, ", ".join(pirole.ROLES))
        )
    _require_run_dir(run_dir)
    (run_dir / (role + ".jsonl")).write_text(text, encoding="utf-8")


def write_diff(run_dir: Path, text: str) -> None:
    """Write the run's diff text to ``diff.patch`` verbatim.

    An empty diff still writes an empty file, since "changed nothing" is
    data - a run that changed nothing stays distinguishable from a run
    whose diff was never recorded. A missing run directory raises
    ``RunLogError`` naming the path, the same guard as ``write_stream``.
    """
    _require_run_dir(run_dir)
    (run_dir / "diff.patch").write_text(text, encoding="utf-8")


def write_commits(run_dir: Path, commits: List[Dict[str, str]]) -> None:
    """Write the run's commit list to ``commits.json`` via ``json.dumps``.

    ``commits`` must be a list whose entries are each a dict with exactly
    the keys ``{"sha", "subject"}``, in order; an entry with a missing or
    extra key raises ``RunLogError`` naming the index of the offending
    entry. An empty list writes ``[]``. A missing run directory raises
    ``RunLogError`` naming the path.
    """
    if not isinstance(commits, list):
        raise RunLogError(
            "commits must be a list of {'sha', 'subject'} dicts, got %r"
            % (commits,)
        )
    for index, entry in enumerate(commits):
        if not isinstance(entry, dict) or set(entry.keys()) != {
            "sha",
            "subject",
        }:
            raise RunLogError(
                "commits entry at index %d must be a dict with exactly the "
                "keys {'sha', 'subject'}, got %r" % (index, entry)
            )
    _require_run_dir(run_dir)
    (run_dir / "commits.json").write_text(json.dumps(commits), encoding="utf-8")


def _require_run_dir(run_dir: Path) -> None:
    """Raise ``RunLogError`` naming the path if ``run_dir`` is not a directory.

    The shared missing-run-directory guard for the archive writers - the
    same guard as behaviour 8, pinned the same way by every writer.
    """
    if not run_dir.is_dir():
        raise RunLogError(
            "run directory does not exist or is not a directory: %s"
            % (run_dir,)
        )
