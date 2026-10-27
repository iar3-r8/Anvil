"""Role table for single-role Pi invocation (``plans/pi-phase6-single-role.md``, behaviour 4).

One job: map a role name to its definition - model id, tier, prompt path and
tools - and nothing else. This module decides, never acts: it performs no
subprocess, no Docker and no file I/O, so it is importable and exercisable
with no container (behaviour 14's seam guard). The argv builder (behaviour 5)
and the driver (behaviours 9-13) live in their own modules.

The table is deliberately fixed at four roles. ``architect`` is the only
frontier-tier role; ``coder``, ``tester`` and ``docs`` all run on the local
coder model. Every role starts at the default tool set and its own prompt
path under ``.pi/roles/`` (the prompt *content* is phase 8's job, not this
module's).

Stdlib only. One exception type: ``RoleError``.
"""

from typing import Dict

# The four known roles, in the order the error message lists them.
ROLES = ("architect", "coder", "tester", "docs")

# The only frontier-tier role; the other three run on the local coder model.
_FRONTIER_ROLES = frozenset(("architect",))

# Every role starts at Pi's default enabled tools
# (doc/external/pi-dev/cli.md, Tools); per-role divergence is #55 and #67.
_DEFAULT_TOOLS = "read,bash,edit,write"


class RoleError(Exception):
    """A role name is unknown or a role definition is missing its fields.

    A single exception type covers every role-table failure, so callers need
    only one ``except`` clause. Every message names the offending value, so
    a wrong name is fixable without reading the source.
    """


def resolve(name: str, coder_model_id: str, frontier_model_id: str) -> Dict[str, str]:
    """Resolve a role name to its definition dict.

    The definition carries exactly four keys: ``model_id`` (the frontier id
    for the frontier-tier role, the local coder id for the rest), ``tier``
    (``"frontier"`` or ``"local"``), ``prompt_path`` (``.pi/roles/<name>.md``)
    and ``tools`` (the default tool set). An unknown ``name`` raises
    ``RoleError`` naming it and listing the four known roles, so the caller
    can see what exists.
    """
    if name not in ROLES:
        raise RoleError(
            "unknown role {!r}: the known roles are {}".format(
                name, ", ".join(ROLES)
            )
        )
    if name in _FRONTIER_ROLES:
        model_id = frontier_model_id
        tier = "frontier"
    else:
        model_id = coder_model_id
        tier = "local"
    return {
        "model_id": model_id,
        "tier": tier,
        "prompt_path": ".pi/roles/{}.md".format(name),
        "tools": _DEFAULT_TOOLS,
    }
