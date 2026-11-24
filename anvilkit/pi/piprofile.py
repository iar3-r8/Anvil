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
existing directory (behaviour 7), and refusing — naming the offending
field — any save whose ``owner``, ``repo``, ``base`` or ``project`` value
starts with a token prefix rather than naming a key (behaviour 8), and
refusing — naming the project field — a ``project`` block that is not a
mapping, before any filesystem effect (behaviour 12).
``load_profile`` reads a record back out of the store, refusing — with a
``ProfileError`` naming the unknown name and listing the known profile
names — a name the store does not hold, so a typo is fixable without
reading the YAML (behaviour 9), and refusing — naming the profile and
the vanished path — a record whose ``path`` no longer exists on disk,
checked per record so a healthy profile still loads while a sibling's
path has vanished (behaviour 10). ``list_profiles`` names every profile
the store holds, sorted (behaviour 11), and
``profile_path`` returns a record's stored ``path`` verbatim with NO
existence check — a vanished path comes back exactly as stored, which
is what keeps ``profile list`` a working discovery tool (behaviour 19).
``resolve_token`` resolves a profile's GitHub token — the value in
the home ``.env`` under the profile's own ``token_env`` key
outranks the install ``.env``'s ``GITHUB_TOKEN``, the empty
string when neither holds one (behaviour 13). This
module imports no ``subprocess`` and
no ``yaml`` — reading and writing the file is ``yamlio``'s licence.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from anvilkit import env
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

#: The install ``.env`` key the resolution order always falls back
#: to (behaviour 13): the literal ``GITHUB_TOKEN``, regardless of
#: the profile's own ``token_env``.
_FALLBACK_TOKEN_ENV = "GITHUB_TOKEN"

#: The string prefixes a saved value must never start with (behaviour 8):
#: each one is the shape of a GitHub or GitLab token, so a value that starts
#: with one is a token smuggled into the store rather than a key name.
#: Start-of-string is the whole rule — the same prefix embedded after other
#: characters is an ordinary string, and the profile's own ``token_env`` is
#: derived from the name, never a smuggle-in vector.
_TOKEN_PREFIXES = (
    "ghp_",
    "gho_",
    "ghu_",
    "ghs_",
    "ghr_",
    "github_pat_",
    "glpat_",
)


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
    than a name the operator intended.
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
    project: Any,
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
            the ``project`` block is not a mapping (the project field is
            named) — behaviour 12, a value in ``owner``, ``repo``,
            ``base`` or the ``project`` block starts with a token prefix
            (the offending field is named) — behaviour 8, ``path`` is not
            an existing directory (the path is named), or the store
            already holds a record under ``name`` whose path is a
            different existing directory (the existing path is named) —
            the last is behaviour 7. In every case nothing is written:
            the store file, if any, is untouched and no directories are
            created.
    """
    if not valid_name(name):
        raise ProfileError(
            "invalid profile name %r: use only %s" % (name, _ALLOWED_CHARSET)
        )
    # Behaviour 12 (non-mapping project block): refused before the token
    # check, which reads the block, and before any filesystem effect — a
    # store that recorded a broken block would fail every later load.
    if not isinstance(project, dict):
        raise ProfileError(
            "profile project block must be a mapping of field to value, "
            "not a %s" % type(project).__name__
        )
    token_field = _token_field(owner, repo, base, project)
    if token_field is not None:
        raise ProfileError(
            "profile field %r starts with a token prefix: record the "
            "key name, not the token value" % token_field
        )
    absolute = os.path.abspath(str(path))
    if not os.path.isdir(absolute):
        raise ProfileError(
            "profile path %s is not an existing directory" % absolute
        )
    _save_into_store(root, name, absolute, owner, repo, base, project)


def load_profile(root: Union[str, Path], name: str) -> Dict[str, Any]:
    """Return the record stored under ``name`` in ``<root>/profiles.yaml``.

    Behaviour 9 ("load-unknown-name") of
    ``plans/pi-phase13-profiles.md``: the store is read through
    ``yamlio.load`` — a missing file is an empty store, not a read
    error — and the record held under ``name`` is returned with its
    fields intact: ``path``, ``owner``, ``repo``, ``base``,
    ``token_env`` and the ``project`` block as written by
    ``save_profile``. Behaviour 10 ("load-vanished-path") is enforced
    before the record is returned: the record's ``path`` must still be
    an existing directory, in the absolute form ``save_profile``
    records, and a path that has vanished refuses the load. The check
    is per record, never a store-wide scan, so a healthy profile loads
    even when a sibling's path has vanished.

    Raises:
        ProfileError: the store does not hold a record under ``name`` —
            the unknown name is named and the known profile names are
            listed, so a typo is fixable without reading the YAML. An
            empty or missing store invents no known names, and a
            malformed store raises the same way, wrapping the
            ``YamlError``. The record is held but its ``path`` no longer
            exists on disk — the profile name and the vanished path are
            both named, raised before any caller acts on the record.
            A read is a read: ``load_profile`` never writes, and a
            failed load leaves the filesystem untouched.
    """
    store = _load_store(root)
    record = store.get(name)
    if not isinstance(record, dict):
        _raise_unknown_profile(store, name)
    # Behaviour 10 (load-vanished-path): per-record, not a store-wide
    # scan — a healthy profile loads while a sibling's path has
    # vanished. The path is in the absolute form the store records it.
    stored_path = record.get("path")
    if not (isinstance(stored_path, str) and os.path.isdir(stored_path)):
        raise ProfileError(
            "profile %r points at a vanished path: %s"
            % (name, stored_path)
        )
    return record


def profile_path(root: Union[str, Path], name: str) -> str:
    """Return the ``path`` stored under ``name``, with NO existence check.

    Behaviour 19 ("raw-path-accessor") of
    ``plans/pi-phase13-profiles.md``: reads the store through
    ``_load_store`` and returns the record's stored ``path`` string
    verbatim — a vanished path is returned exactly as stored, which is
    what keeps ``profile list`` a working discovery tool: a record
    whose directory has been deleted still lists, while
    ``load_profile`` refuses the same record per behaviour 10. An
    unknown name raises the same ``ProfileError`` ``load_profile``
    raises (behaviour 9: the unknown name is named and the known
    profile names are listed, or "no profiles are saved" when the
    store is empty), and a malformed store raises the same way
    ``_load_store`` wraps ``YamlError``. A read is a read:
    ``profile_path`` never writes, and a missing root stays missing.

    Raises:
        ProfileError: the store does not hold a record under
            ``name`` — behaviour 9's message, naming the unknown
            name and listing the known profiles — or the store is
            malformed, wrapped from the ``YamlError``.
    """
    store = _load_store(root)
    record = store.get(name)
    if not isinstance(record, dict):
        _raise_unknown_profile(store, name)
    return record["path"]


def list_profiles(root: os.PathLike) -> List[str]:
    """Return the profile names the store under ``root`` holds, sorted.

    Behaviour 11 ("two-profiles-coexist") of
    ``plans/pi-phase13-profiles.md``: reads the store through
    ``_load_store`` and returns every key except ``version``, sorted
    lexicographically, so a store holding two profiles lists both names
    in the same order no matter the order they were saved. A missing
    file, a missing root and a file holding no profiles are all an
    empty list, never an error, and a malformed store raises
    ``ProfileError`` the way ``load_profile`` does. A listing is a read:
    it never writes, so neither ``root`` nor ``root/profiles.yaml``
    comes into existence as a side effect.
    """
    store = _load_store(root)
    return sorted(key for key in store if key != "version")


def resolve_token(
    profile: Dict[str, Any],
    home_env: Union[str, os.PathLike],
    install_env: Union[str, os.PathLike],
) -> str:
    """Return the profile's GitHub token, or the empty string.

    Behaviour 13 ("token-resolution-order") of
    ``plans/pi-phase13-profiles.md``: the value in ``home_env``
    (``~/.anvil/.env``) under the profile's own ``token_env`` key
    wins; absent there, the install ``.env``'s ``GITHUB_TOKEN`` —
    the fallback key is always the literal ``GITHUB_TOKEN``,
    regardless of the profile's ``token_env`` — is the fallback;
    absent in both, the empty string, never an exception: a
    missing token is a resolvable state the caller reports. Both
    paths are injectable keyword parameters with no default, so
    the suite runs with no real home — the injectable-home seam
    ``pibakeoff`` and ``picrew`` already set. Each file is read
    through ``env.read``, whose missing-file-yields-an-empty-mapping
    behaviour is exactly the read contract here: a read is a
    read, and neither file is ever created by a resolve.
    """
    token_key = profile.get("token_env")
    token = env.read(home_env).get(token_key)
    if not token:
        token = env.read(install_env).get(_FALLBACK_TOKEN_ENV)
    return token or ""


def _token_field(
    owner: Optional[str],
    repo: Optional[str],
    base: Optional[str],
    project: Dict[str, Any],
) -> Optional[str]:
    """Return the first field whose value is a token, or ``None``.

    Behaviour 8 of ``plans/pi-phase13-profiles.md``: a value is a token
    when it is a string that starts with one of ``_TOKEN_PREFIXES`` —
    start-of-string, no length floor, the prefix is the rule. The fields
    checked are ``owner``, ``repo``, ``base`` and the values at the top
    level of the ``project`` block (non-string values are not tokens);
    the profile's own ``token_env`` is derived, not supplied, and is
    never checked.
    """
    for field, value in (("owner", owner), ("repo", repo), ("base", base)):
        if isinstance(value, str) and value.startswith(_TOKEN_PREFIXES):
            return field
    for key, value in project.items():
        if isinstance(value, str) and value.startswith(_TOKEN_PREFIXES):
            return str(key)
    return None


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


def _raise_unknown_profile(store: Dict[str, Any], name: str) -> None:
    """Raise behaviour 9's ``ProfileError`` for a name the store lacks.

    Shared by ``load_profile`` and ``profile_path`` so the two reads
    fail with the same message: the unknown name is named and the
    known profile names are listed, so a typo is fixable without
    reading the YAML; an empty store invents no names and says so.
    """
    known = sorted(key for key in store if key != "version")
    if known:
        raise ProfileError(
            "unknown profile %r: known profiles are %s"
            % (name, ", ".join(known))
        )
    raise ProfileError("unknown profile %r: no profiles are saved" % name)


def _load_store(root: Union[str, Path]) -> Dict[str, Any]:
    """Read the store under ``root``; a missing file is an empty store.

    Behaviour 9 of ``plans/pi-phase13-profiles.md``: a missing
    ``profiles.yaml`` (or a missing ``root``) is an empty store, not a
    read error, and the store is read through ``yamlio.load`` with a
    failed read wrapped into ``ProfileError`` the way the write path
    does. The read touches nothing on disk: no file is created.
    """
    store_path = Path(root) / _STORE_FILENAME
    if not store_path.exists():
        return {}
    try:
        return yamlio.load(store_path)
    except yamlio.YamlError as exc:
        raise ProfileError("could not read profile store: {}".format(exc)) from exc
