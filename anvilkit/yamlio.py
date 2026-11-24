"""Safe YAML I/O - the only module permitted to import ``yaml``.

Anvil reads YAML and writes its own YAML files, and routing every access
through this module keeps a future parser swap to a one-file change.

``config.yaml`` is owned by llama-swap and stays hand-authored: Anvil reads it
and never writes it. ``save`` exists only for Anvil's own files (the profiles
store, per ``plans/pi-phase13-profiles.md``), and ``safe_dump`` on the write
side mirrors the safety property ``safe_load`` already gives on the read side.

``pyyaml`` is imported directly. The managed virtual environment provisioned by
``./anvil`` guarantees it is present, so there is no fallback path to maintain.
"""

from pathlib import Path
from typing import Any, Dict, Union

import yaml

PathLike = Union[str, Path]


class YamlError(Exception):
    """Any failure to read or write a YAML document.

    A single exception type covers a missing file, unreadable bytes, invalid
    syntax, an unsafe tag, a wrong top-level shape and an unwritable target
    path, so callers need only one ``except`` clause.
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


def save(path: PathLike, mapping: Dict[str, Any]) -> None:
    """Write ``mapping`` to ``path`` as a YAML document.

    For Anvil's own files only - ``config.yaml`` is owned by llama-swap and is
    never written. Missing parent directories are created.

    Raises:
        YamlError: the top level is not a mapping (checked before anything is
            written), or the path cannot be created or written.
    """
    if not isinstance(mapping, dict):
        raise YamlError(
            "Expected a mapping to save to {}, got {}".format(
                path, type(mapping).__name__
            )
        )

    path = Path(path)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # safe_dump mirrors the safety property of safe_load: the output is a
        # plain-data document, never a tag that could build arbitrary objects.
        text = yaml.safe_dump(mapping, default_flow_style=False, sort_keys=False)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise YamlError("Could not write {}: {}".format(path, exc)) from exc


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
