"""Run-log run ids (``plans/pi-phase11-runlog.md``, behaviours 1 and 2).

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

Stdlib only. One exception type: ``RunLogError``.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

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
