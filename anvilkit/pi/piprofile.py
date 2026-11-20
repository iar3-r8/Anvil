"""Name-charset gate and write half of the ``~/.anvil/profiles.yaml`` store.

Two jobs so far: decide whether a candidate profile name is a name Anvil
can address — behaviour 1 of ``plans/pi-phase13-profiles.md`` — and
record a provisioning — behaviour 4 ("save-writes-record").
``valid_name`` returns ``True`` for non-empty names drawn entirely from
``[A-Za-z0-9._-]`` and ``False`` for the empty string, a character
outside the set, or a leading ``-``, ``.`` or digit: a leading hyphen
reads as a CLI flag and a mangled name maps to a key Anvil never reads.
``token_env_for`` (behaviour 2) derives the GitHub token variable, and
``save_profile`` writes the record under the name into a ``version: 1``
store. The read behaviours (``load_profile``, ``list_profiles``) and
the in-place update, rename and collision handling (behaviours 5-7)
will follow. This module imports no ``subprocess`` and no ``yaml`` —
reading and writing the file is ``yamlio``'s licence.
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
            or ``path`` is not an existing directory (the path is named).
            In both cases nothing is written: the store file, if any,
            is untouched and no directories are created.
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
    the record under ``name`` keeping ``version: 1``, and save. The
    validation that must precede any write lives in ``save_profile``, so
    a raised ``ProfileError`` leaves the file and the directory tree
    untouched. The in-place update, rename and collision handling
    (behaviours 5-7) mutate here once they are implemented.
    """
    store_path = Path(root) / _STORE_FILENAME
    try:
        store = yamlio.load(store_path) if store_path.exists() else {}
    except yamlio.YamlError as exc:
        raise ProfileError("could not read profile store: {}".format(exc)) from exc

    store["version"] = 1
    store[name] = {
        "path": absolute,
        "owner": owner,
        "repo": repo,
        "base": base,
        "token_env": token_env_for(name),
        "project": dict(project),
    }

    try:
        yamlio.save(store_path, store)
    except yamlio.YamlError as exc:
        raise ProfileError("could not write profile store: {}".format(exc)) from exc
