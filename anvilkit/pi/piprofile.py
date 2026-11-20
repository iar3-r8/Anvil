"""Name-charset gate and write half of the ``~/.anvil/profiles.yaml`` store.

Decide whether a candidate profile name is a name Anvil can address —
behaviour 1 of ``plans/pi-phase13-profiles.md`` — and record a
provisioning — behaviour 4 ("save-writes-record") — into a ``version: 1``
store, keeping it to one path, one profile: a re-save under the same name
updates the record in place (behaviour 5), and a save under a new name for
a path another record already holds renames that record in place, carrying
its ``project`` block across (behaviour 6). ``valid_name`` returns ``True``
for non-empty names drawn entirely from ``[A-Za-z0-9._-]`` and ``False``
for the empty string, a character outside the set, or a leading ``-``,
``.`` or digit: a leading hyphen reads as a CLI flag and a mangled name
maps to a key Anvil never reads. ``token_env_for`` (behaviour 2) derives
the GitHub token variable, and ``save_profile`` writes the record under
the name into the store, refusing — with a ``ProfileError`` naming the
existing path — a re-save that keeps the name but points at a different
existing directory (behaviour 7). The read behaviours (``load_profile``,
``list_profiles``) will follow. This module imports no ``subprocess`` and
no ``yaml`` — reading and writing the file is ``yamlio``'s licence.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Union

from anvilkit import yamlio

#: The whole permitted body of a profile name.
_CHARSET = re.compile(r"[A-Za-z0-9._-]+\Z")

#: The charset a failure message must quote so the operator can fix the
#: name without reading the source.
_ALLOWED_CHARSET = "[A-Za-z0-9._-]"

#: The store file, a direct child of the root: ``root`` stands in for
#: ``~/.anvil``, so the file is ``<root>/profiles.yaml`` — the root is
#: the directory that receives it, never a parent of it.
_STORE_FILENAME = "profiles.yaml"


class ProfileError(Exception):
    """A profile input or store state that Anvil can act on.

    Raised by the later store behaviours (an invalid name reaching
    ``token_env_for`` or ``save_profile``, an unknown name, a vanished
    path); every message names the offending value so the operator can
    fix it without reading the YAML.
    """


def valid_name(name: str) -> bool:
    """Return whether ``name`` is an addressable profile name.

    ``True`` requires all three: the name is non-empty, every character
    lies in ``[A-Za-z0-9._-]``, and the first character is not ``-``,
    ``.`` or a digit. A leading hyphen would read as a CLI flag, a
    leading dot as a hidden file, and a leading digit as a number rather
    than the repository basename the prompt defaults to.
    """
    if not name:
        return False
    if name[0] in "-." or name[0].isdigit():
        return False
    return _CHARSET.match(name) is not None


def token_env_for(name: str) -> str:
    """Derive the GitHub token environment variable for ``name``.

    Behaviour 2 of ``plans/pi-phase13-profiles.md``: returns
    ``GITHUB_TOKEN_`` + the name upper-cased, with ``.`` and ``-`` mapped to
    ``_`` so the result is a legal identifier (``project-x`` ->
    ``GITHUB_TOKEN_PROJECT_X``). The mapping is deterministic across calls.
    A name that fails ``valid_name`` raises ``ProfileError`` naming the
    name and the allowed charset ``[A-Za-z0-9._-]`` — it is never silently
    sanitised, because a mangled name would resolve to a token the operator
    never intended.
    """
    if not valid_name(name):
        raise ProfileError(
            "invalid profile name %r: use only %s"
            % (name, _ALLOWED_CHARSET)
        )
    body = name.replace(".", "_").replace("-", "_").upper()
    return "GITHUB_TOKEN_" + body


def save_profile(
    root: Union[str, Path],
    name: str,
    path: Union[str, Path],
    owner: Optional[str],
    repo: Optional[str],
    base: Optional[str],
    project: Dict[str, Any],
) -> None:
    """Record a provisioning under ``name`` in ``<root>/profiles.yaml``.

    Behaviour 4 ("save-writes-record") of
    ``plans/pi-phase13-profiles.md``: writes the store holding
    ``version: 1`` and, under ``name``, a record with the ``path``
    resolved to absolute, ``owner``, ``repo``, ``base``, the
    ``token_env`` from behaviour 2, and the ``project`` block as given —
    an empty block is valid and round-trips. ``root`` stands in for
    ``~/.anvil``: it is the directory that receives ``profiles.yaml``,
    and its missing parent directories are created.

    Raises:
        ProfileError: the name fails ``valid_name`` (the name is named),
            ``path`` is not an existing directory (the path is named),
            or the store already holds a record under ``name`` whose
            path is a different existing directory (the existing path
            is named) — the last is behaviour 7. In every case nothing
            is written: the store file, if any, is untouched and no
            directories are created.
    """
    if not valid_name(name):
        raise ProfileError(
            "invalid profile name %r: use only %s" % (name, _ALLOWED_CHARSET)
        )
    absolute = os.path.abspath(str(path))
    if not os.path.isdir(absolute):
        raise ProfileError(
            "profile path %s is not an existing directory" % absolute
        )
    _save_into_store(root, name, absolute, owner, repo, base, project)


def _save_into_store(
    root: Union[str, Path],
    name: str,
    absolute: str,
    owner: Optional[str],
    repo: Optional[str],
    base: Optional[str],
    project: Dict[str, Any],
) -> None:
    """Write the record for ``name`` into the store under ``root``.

    Private load-mutate-save flow shared by the write behaviours: load
    the store (a missing file is an empty store, not an error), replace
    the record under ``name`` keeping ``version: 1``, and save. A re-save
    under the same name updates the record in place (behaviour 5); a save
    under a new name for a path another record already holds renames that
    record in place — the old key is dropped, its ``project`` block is
    carried across, and the identity fields come from this save
    (behaviour 6) — so the store never holds two records for one path.
    The same-name-different-path refusal (behaviour 7) mutates here too:
    before any of the mutations below, a record already carrying this name
    at a different existing directory is refused. The validation that must
    precede any write lives in ``save_profile``, so a raised ``ProfileError``
    leaves the file and the directory tree untouched.
    """
    store_path = Path(root) / _STORE_FILENAME
    try:
        store = yamlio.load(store_path) if store_path.exists() else {}
    except yamlio.YamlError as exc:
        raise ProfileError("could not read profile store: {}".format(exc)) from exc

    # Behaviour 7 (refuse name collision): a record that already carries
    # this name at a different existing directory is refused before any
    # mutation — a silent overwrite would leave a later run editing the
    # wrong repository. The error names the EXISTING path, in the
    # absolute form the store records it, so the operator learns which
    # repository the name already points at. A stale record whose path
    # no longer exists is not a collision: the save proceeds.
    existing = store.get(name)
    if isinstance(existing, dict):
        existing_path = existing.get("path")
        if (
            isinstance(existing_path, str)
            and existing_path != absolute
            and os.path.isdir(existing_path)
        ):
            raise ProfileError(
                "profile name %r already points at %s: choose another "
                "name to point at %s" % (name, existing_path, absolute)
            )

    store["version"] = 1

    # Behaviour 6 (rename on same path): one path, one profile. A record
    # under a different name that already carries this absolute path is
    # renamed in place — its key is dropped and its project block carried
    # across, so the new record's identity fields come from this save
    # while the project block survives the rename.
    carried_project = None
    for key, existing in list(store.items()):
        if key in ("version", name):
            continue
        if isinstance(existing, dict) and existing.get("path") == absolute:
            if carried_project is None and isinstance(
                existing.get("project"), dict
            ):
                carried_project = dict(existing["project"])
            del store[key]

    project_block = dict(project)
    if carried_project:
        project_block = carried_project

    store[name] = {
        "path": absolute,
        "owner": owner,
        "repo": repo,
        "base": base,
        "token_env": token_env_for(name),
        "project": project_block,
    }

    try:
        yamlio.save(store_path, store)
    except yamlio.YamlError as exc:
        raise ProfileError("could not write profile store: {}".format(exc)) from exc
