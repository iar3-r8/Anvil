"""Reading ``config.yaml`` (llama-swap's) and ``anvil.yaml`` (Anvil's own).

Ownership boundary:

* ``config.yaml`` belongs to llama-swap and is read-only to Anvil, which parses
  it only to learn which model is the coder and what its context window is. It
  is parsed structurally, so reordering or reindenting a model block cannot
  change the answer.
* ``anvil.yaml`` holds Anvil's own values: the gateway fallback port, the Zoo
  Code profile ids, and the Anthropic model menu.
"""

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

from . import yamlio

PathLike = Union[str, Path]

# Used when a model's cmd carries no --max-model-len.
DEFAULT_CONTEXT_WINDOW = 262144

# llama-swap's own default when config.yaml omits 'port'.
DEFAULT_GATEWAY_PORT = 8080

_MAX_MODEL_LEN_FLAG = "--max-model-len"

_ALLOWED_SETTINGS_KEYS = {"version", "gateway", "zoo_code"}
_REQUIRED_ZOO_CODE_KEYS = (
    "local_profile_id",
    "anthropic_profile_id",
    "default_anthropic_model",
    "anthropic_models",
)


class ConfigError(Exception):
    """A configuration file is missing, malformed, or semantically invalid."""


class ModelTopology:
    """The subset of llama-swap's configuration that Anvil needs."""

    def __init__(
        self,
        coder_id: str,
        coder_context_window: int,
        embedder_id: Optional[str],
        gateway_port: int,
    ) -> None:
        self.coder_id = coder_id
        self.coder_context_window = coder_context_window
        self.embedder_id = embedder_id
        self.gateway_port = gateway_port


class AnvilSettings:
    """Anvil's own values, read from ``anvil.yaml``."""

    def __init__(self, data: Mapping[str, Any]) -> None:
        gateway = data.get("gateway") or {}
        zoo_code = data["zoo_code"]

        self.default_port = int(gateway.get("default_port", DEFAULT_GATEWAY_PORT))
        self.local_profile_id = zoo_code["local_profile_id"]
        self.anthropic_profile_id = zoo_code["anthropic_profile_id"]
        self.default_anthropic_model = zoo_code["default_anthropic_model"]
        self.anthropic_models: List[Dict[str, Any]] = list(zoo_code["anthropic_models"])


def read_models(path: PathLike) -> ModelTopology:
    """Read model topology from llama-swap's ``config.yaml``.

    Raises:
        ConfigError: the file is unreadable, ``matrix.vars.coder`` is missing, or
            it names a model absent from the ``models`` section.
    """
    data = _load(path)

    matrix_vars = (data.get("matrix") or {}).get("vars") or {}
    models = data.get("models") or {}

    coder_id = matrix_vars.get("coder")
    if not coder_id:
        raise ConfigError(
            "matrix.vars.coder is not defined in {}; Anvil cannot tell which "
            "model is the coder".format(path)
        )

    if coder_id not in models:
        raise ConfigError(
            "matrix.vars.coder names {!r}, which is not defined in the models "
            "section of {}".format(coder_id, path)
        )

    return ModelTopology(
        coder_id=coder_id,
        coder_context_window=_extract_context_window(models[coder_id]),
        embedder_id=matrix_vars.get("nomic"),
        gateway_port=int(data.get("port", DEFAULT_GATEWAY_PORT)),
    )


def read_settings(
    path: PathLike, local_path: Optional[PathLike] = None
) -> AnvilSettings:
    """Read ``anvil.yaml``, merging ``anvil.local.yaml`` over it when present."""
    data = _load(path)

    if local_path is not None and Path(local_path).is_file():
        data = _deep_merge(data, _load(local_path))

    _validate_settings(data, path)

    return AnvilSettings(data)


def resolve_port(
    flag_value: Optional[int], env_value: Optional[str], default_port: int
) -> int:
    """Resolve the gateway port: CLI flag, then ``.env``, then the default.

    ``.env`` outranks ``anvil.yaml`` so a machine-specific ``LLM_PORT`` keeps
    working without editing committed configuration.
    """
    if flag_value is not None:
        return int(flag_value)

    if env_value:
        try:
            return int(env_value)
        except ValueError:
            raise ConfigError(
                "LLM_PORT must be a number, got {!r}".format(env_value)
            ) from None

    return int(default_port)


def _extract_context_window(model: Mapping[str, Any]) -> int:
    """Pull ``--max-model-len`` out of a located model's command string.

    The value genuinely lives inside a command line, which is llama-swap's
    design. The model is resolved structurally first, so only its own command is
    scanned and the value need not be the final token on the line.
    """
    command = model.get("cmd")
    if not command:
        return DEFAULT_CONTEXT_WINDOW

    tokens = str(command).split()
    for index, token in enumerate(tokens):
        # Supports both '--max-model-len 262144' and '--max-model-len=262144'.
        if token.startswith(_MAX_MODEL_LEN_FLAG + "="):
            candidate = token.split("=", 1)[1]
        elif token == _MAX_MODEL_LEN_FLAG and index + 1 < len(tokens):
            candidate = tokens[index + 1]
        else:
            continue

        try:
            return int(candidate)
        except ValueError:
            continue

    return DEFAULT_CONTEXT_WINDOW


def _validate_settings(data: Mapping[str, Any], path: PathLike) -> None:
    unknown = set(data) - _ALLOWED_SETTINGS_KEYS
    if unknown:
        raise ConfigError(
            "Unknown key(s) in {}: {}. Allowed: {}".format(
                path, ", ".join(sorted(unknown)), ", ".join(sorted(_ALLOWED_SETTINGS_KEYS))
            )
        )

    zoo_code = data.get("zoo_code")
    if not isinstance(zoo_code, dict):
        raise ConfigError("{} is missing the 'zoo_code' section".format(path))

    missing = [key for key in _REQUIRED_ZOO_CODE_KEYS if not zoo_code.get(key)]
    if missing:
        raise ConfigError(
            "{} is missing required zoo_code key(s): {}".format(
                path, ", ".join(missing)
            )
        )

    models = zoo_code["anthropic_models"]
    if not isinstance(models, list) or not models:
        raise ConfigError(
            "{}: zoo_code.anthropic_models must be a non-empty list".format(path)
        )

    for entry in models:
        if not isinstance(entry, dict) or not entry.get("id"):
            raise ConfigError(
                "{}: every zoo_code.anthropic_models entry needs an 'id'".format(path)
            )

    offered = [entry["id"] for entry in models]
    if zoo_code["default_anthropic_model"] not in offered:
        raise ConfigError(
            "{}: default_anthropic_model {!r} is not among the offered models "
            "{}".format(path, zoo_code["default_anthropic_model"], offered)
        )


def _deep_merge(
    base: Mapping[str, Any], override: Mapping[str, Any]
) -> Dict[str, Any]:
    """Merge recursively, mutating neither argument."""
    merged = dict(base)

    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = value

    return merged


def _load(path: PathLike) -> Dict[str, Any]:
    try:
        return yamlio.load(path)
    except yamlio.YamlError as exc:
        raise ConfigError(str(exc)) from exc
