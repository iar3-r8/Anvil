"""Run-log run ids (``plans/pi-phase11-runlog.md``, behaviour 1).

A run id is ``run-YYYYMMDD-HHMMSS-<4hex>``: a zero-padded UTC stamp from an
injected aware datetime plus a 4-char lowercase-hex entropy suffix, so every
Pi run (and the ``<run-id>-<role>`` session ids derived under it) is uniquely
addressable. This module owns the id format and its validation only - it does
not touch the archive, the driver or Pi itself.

Stdlib only. One exception type: ``RunLogError``.
"""

from datetime import datetime, timedelta


class RunLogError(Exception):
    """A run id that cannot be built, or a run log that cannot be opened."""


def new_run_id(now: datetime, entropy: str) -> str:
    """Return ``run-YYYYMMDD-HHMMSS-<4hex>`` for the instant ``now``.

    ``now`` must be an aware datetime in UTC; ``entropy`` must be exactly
    four lowercase hex characters. Either violation raises ``RunLogError``
    naming the offending value.
    """
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
