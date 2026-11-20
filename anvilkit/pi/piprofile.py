"""Name-charset gate for the ``~/.anvil/profiles.yaml`` store.

One job: decide whether a candidate profile name is a name Anvil can
address — behaviour 1 of ``plans/pi-phase13-profiles.md``.
``valid_name`` returns ``True`` for non-empty names drawn entirely from
``[A-Za-z0-9._-]`` and ``False`` for the empty string, a character
outside the set, or a leading ``-``, ``.`` or digit: a leading hyphen
reads as a CLI flag and a mangled name maps to a key Anvil never reads.
Behaviour 2 (token-env derivation) lands here too; the later store
behaviours (save and load) will follow. This module imports no
``subprocess`` and no ``yaml`` — writing the file is ``yamlio``'s
licence.
"""

import re

#: The whole permitted body of a profile name.
_CHARSET = re.compile(r"[A-Za-z0-9._-]+\Z")

#: The charset a failure message must quote so the operator can fix the
#: name without reading the source.
_ALLOWED_CHARSET = "[A-Za-z0-9._-]"


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
