"""Safe YAML loading - the only module permitted to import ``yaml``.

Anvil reads YAML but never writes it: ``config.yaml`` is owned by llama-swap and
stays hand-authored. This module therefore exposes a load-only surface, and
routing every access through it keeps a future parser swap to a one-file change.

``pyyaml`` is imported directly. The managed virtual environment provisioned by
``./anvil`` guarantees it is present, so there is no fallback path to maintain.
"""

from pathlib import Path
from typing import Any, Dict, Union

import yaml

PathLike = Union[str, Path]


class YamlError(Exception):
    """Any failure to read a YAML document.

    A single exception type covers a missing file, unreadable bytes, invalid
    syntax, an unsafe tag and a wrong top-level shape, so callers need only one
    ``except`` clause.
    """


def load(path: PathLike) -> Dict[str, Any]:
    """Load a YAML mapping from ``path``.

    Raises:
        YamlError: the file is missing, unreadable, malformed, contains unsafe
            tags, or its top-level document is not a mapping.
    """
    path = Path(path)

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise YamlError("Configuration file not found: {}".format(path)) from None
    except OSError as exc:
        raise YamlError("Could not read {}: {}".format(path, exc)) from exc

    return _parse(text, source=str(path))


def loads(text: str) -> Dict[str, Any]:
    return _parse(text, source="<string>")


def _parse(text: str, source: str) -> Dict[str, Any]:
    try:
        # safe_load is the decisive safety property: a config file must never be
        # able to execute code or instantiate arbitrary Python objects.
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise YamlError("Invalid YAML in {}: {}".format(source, exc)) from exc

    if data is None:
        return {}

    if not isinstance(data, dict):
        raise YamlError(
            "Expected a mapping at the top level of {}, got {}".format(
                source, type(data).__name__
            )
        )

    return data
