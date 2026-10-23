"""Tier table - mapping a tier id to a GPU slot plan.

Anvil names exactly four device slots on every tier, but how many of them the
coder model spans depends on how many GPUs the host has. This module owns the
lookup table that answers "how many coder slots does this tier use?", and the
strict lookup that turns a tier id into that plan. It decides nothing else:
prompting lives in ``prompts``, the ``.env`` write lives in ``cli``.

The ids are looked up exactly, with no lowercasing and no stripping, so a typo
fails loudly instead of resolving silently to the wrong hardware.
"""

import dataclasses
from typing import Dict, Tuple


class TierError(Exception):
    """Any failure to resolve a tier id.

    A single exception type covers every bad id - unknown, wrong case or
    whitespace-padded - so callers need only one ``except`` clause.
    """


@dataclasses.dataclass(frozen=True)
class Tier:
    """One entry of the tier table: a human label plus the slot plan."""

    id: str
    label: str
    coder_slots: int


# Ordered for display; the low tier spans one GPU, mid is today's shipped
# default with the coder on two, and high spans eight GPUs (its four device
# keys still cover two of them for the coder).
TIERS: Tuple[Tier, ...] = (
    Tier(id="low", label="Low — 1 GPU / 40 GB VRAM", coder_slots=1),
    Tier(id="mid", label="Mid — 2 GPU", coder_slots=2),
    Tier(id="high", label="High — 8 GPU / 320 GB VRAM", coder_slots=2),
)

_BY_ID: Dict[str, Tier] = {tier.id: tier for tier in TIERS}


def split_coder_ids(tier: Tier, coder_id: str) -> Tuple[str, ...]:
    """Broadcast one supplied coder id across every coder slot of ``tier``.

    A single GPU id applies to the whole coder model: the result is a tuple
    of ``tier.coder_slots`` entries, each equal to ``coder_id``, ready to be
    written one per device key by the caller.

    Raises:
        TierError: ``coder_id`` is empty or whitespace-only; a GPU id must
            name an actual device.
    """
    if not coder_id.strip():
        raise TierError(
            "Coder id must be a non-empty device id, got: '{}'".format(coder_id)
        )
    return (coder_id,) * tier.coder_slots


def plan(name: str) -> Tier:
    """Resolve ``name`` to its tier plan.

    The lookup is exact: no lowercasing, no stripping, so ``"LOW"`` and
    ``" low "`` both fail loudly rather than resolving to ``"low"``.

    Raises:
        TierError: the id is unknown, wrong case, or padded with whitespace;
            the message lists every valid id.
    """
    tier = _BY_ID.get(name)
    if tier is None:
        available = ", ".join(t.id for t in TIERS)
        raise TierError("Unknown tier: '{}'. Available tiers: {}".format(name, available))
    return tier
