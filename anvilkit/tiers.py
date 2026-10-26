"""Tier table - mapping a tier id to a GPU slot plan.

Anvil names exactly four device slots on every tier, but how many of them the
coder model spans depends on how many GPUs the host has. This module owns the
lookup table that answers "how many coder slots does this tier use?", the
strict lookup that turns a tier id into that plan, the slot defaults each plan
carries, and the pairing of answered ids with the four ``.env`` device keys.
It decides nothing else: prompting lives in ``prompts``, the ``.env`` write
lives in ``cli``.

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
    """One entry of the tier table: a human label plus the slot plan.

    The ``default_*`` fields are raw strings for the generic, coder and
    embedder slots - the coder default is a comma-separated list that feeds
    straight back into :func:`split_coder_ids`.
    """

    id: str
    label: str
    coder_slots: int
    default_generic: str
    default_coder: str
    default_embedder: str


# Ordered for display; the low tier spans one GPU, mid is today's shipped
# default with the coder on two, and high spans eight GPUs (its four device
# keys still cover two of them for the coder).
#
# Slot defaults: low reuses one id for every slot, because a single-GPU host
# has exactly one GPU to name; mid is today's shipped default (generic 0,
# coder 0,1, embedder 2); high spreads the four device keys over GPUs 0-3,
# leaving the remaining four GPUs for the user to wire up in config.yaml.
TIERS: Tuple[Tier, ...] = (
    Tier(
        id="low",
        label="Low — 1 GPU / 40 GB VRAM",
        coder_slots=1,
        default_generic="0",
        default_coder="0",
        default_embedder="0",
    ),
    Tier(
        id="mid",
        label="Mid — 2 GPU",
        coder_slots=2,
        default_generic="0",
        default_coder="0,1",
        default_embedder="2",
    ),
    Tier(
        id="high",
        label="High — 8 GPU / 320 GB VRAM",
        coder_slots=2,
        default_generic="0",
        default_coder="1,2",
        default_embedder="3",
    ),
)

_BY_ID: Dict[str, Tier] = {tier.id: tier for tier in TIERS}


def split_coder_ids(tier: Tier, coder_id: str) -> Tuple[str, ...]:
    """Turn the supplied coder id(s) into one device id per coder slot.

    ``coder_id`` is a comma-separated list of GPU ids. A single id applies to
    the whole coder model and is broadcast across every coder slot of
    ``tier``; a list of exactly ``tier.coder_slots`` ids is used as-is. The
    result is a tuple ready to be written one per device key by the caller.

    Raises:
        TierError: ``coder_id`` is empty or whitespace-only, or any entry
            between commas is empty or whitespace-only; a GPU id must name
            an actual device. Also raised when more ids are given than the
            tier has coder slots, naming the tier and its slot count so the
            user sees what to change.
    """
    if not coder_id.strip():
        raise TierError(
            "Coder id must be a non-empty device id, got: '{}'".format(coder_id)
        )
    ids = tuple(part.strip() for part in coder_id.split(","))
    if any(not part for part in ids):
        raise TierError(
            "Every coder id must be a non-empty device id, got: '{}'".format(
                coder_id
            )
        )
    if len(ids) > tier.coder_slots:
        raise TierError(
            "Tier '{}' has {} coder slot(s), but {} device id(s) were given: "
            "'{}'".format(tier.id, tier.coder_slots, len(ids), coder_id)
        )
    if len(ids) == 1:
        return ids * tier.coder_slots
    return ids


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


def assign(
    tier: Tier,
    generic_id: str,
    coder_ids: Tuple[str, ...],
    embedder_id: str,
) -> Tuple[Tuple[str, str], ...]:
    """Pair the answered device ids with the four ``.env`` device keys.

    ``coder_ids`` is the already-split tuple exactly as returned by
    :func:`split_coder_ids` (exactly ``tier.coder_slots`` ids), so this
    function adds no validation of its own - ``split_coder_ids`` stays the
    single validation seam. The pairs come back in the order
    ``LLM_DEVICE_ID_0``, ``LLM_DEVICE_ID_1``, ``LLM_DEVICE_ID_2``,
    ``INDEXER_STORAGE_DEVICE_ID``; on the low tier the single coder id is
    reused for ``LLM_DEVICE_ID_2`` so a single-GPU host never names a device
    it does not have.

    Returns:
        Four ``(key, value)`` pairs, one per device key, in ``.env`` order.
    """
    if tier.coder_slots == 1:
        coder_first = coder_second = coder_ids[0]
    else:
        coder_first, coder_second = coder_ids[0], coder_ids[1]
    return (
        ("LLM_DEVICE_ID_0", generic_id),
        ("LLM_DEVICE_ID_1", coder_first),
        ("LLM_DEVICE_ID_2", coder_second),
        ("INDEXER_STORAGE_DEVICE_ID", embedder_id),
    )
