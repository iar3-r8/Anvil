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
from typing import Dict, Optional

from anvilkit.pi import pirole


class RunLogError(Exception):
    """A run id that cannot be built, or a run log that cannot be opened."""


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
    _validate_start_inputs(intake, sessions, started_at)
    run_dir = root / "logs" / "runs" / run_id
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
