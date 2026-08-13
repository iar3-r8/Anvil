"""Generating the Zoo Code artifacts: ``zoo-code-settings.json`` and ``mcp.json``.

Templates are parsed as JSON, values are substituted into the resulting data
structures, and the output is produced with ``json.dumps``.

Constraints:

* output is valid JSON **by construction**, not by luck of escaping;
* secrets containing ``\\``, ``&``, ``|`` or a quote can no longer corrupt the
  output;
* ``contextWindow`` stays a JSON number rather than a textually substituted token.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

PathLike = Union[str, Path]

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

ZOO_TEMPLATE = _TEMPLATES_DIR / "zoo-code-settings.json.template"
MCP_TEMPLATE = _TEMPLATES_DIR / "mcp.json.template"
EXTENSIONS_TEMPLATE = _TEMPLATES_DIR / "extensions.json.template"

# The zoo template holds a bare ${CONTEXT_WINDOW} where a JSON number belongs, so
# it is not parseable until that token is replaced with a valid literal.
_CONTEXT_WINDOW_TOKEN = "${CONTEXT_WINDOW}"

_INDENT = 4


class RenderError(Exception):
    """A template is missing, malformed, or lacks an expected structure."""


def zoo_code_settings(
    port: int,
    context_window: int,
    coder_model_id: str,
    embedder_model_id: Optional[str],
    local_profile_id: str,
    anthropic_profile_id: str,
    anthropic_api_key: str,
    anthropic_model_id: str,
    use_anthropic_for_frontier_modes: bool,
) -> str:
    """Render ``zoo-code-settings.json`` as a JSON string."""
    settings = _load_zoo_template(context_window)

    base_url = "http://localhost:{}/v1".format(port)

    profiles = settings["providerProfiles"]
    api_configs = profiles["apiConfigs"]

    local = api_configs["llama_swap"]
    local["openAiBaseUrl"] = base_url
    local["openAiModelId"] = coder_model_id
    local["id"] = local_profile_id
    local["openAiCustomModelInfo"]["contextWindow"] = int(context_window)

    anthropic = api_configs["anthropic"]
    anthropic["anthropicApiKey"] = anthropic_api_key
    anthropic["apiModelId"] = anthropic_model_id
    anthropic["id"] = anthropic_profile_id

    frontier_profile_id = (
        anthropic_profile_id if use_anthropic_for_frontier_modes else local_profile_id
    )
    profiles["modeApiConfigs"] = {
        "architect": frontier_profile_id,
        "code": local_profile_id,
        "ask": local_profile_id,
        "debug": local_profile_id,
        "orchestrator": frontier_profile_id,
    }

    index_config = settings["globalSettings"]["codebaseIndexConfig"]
    index_config["codebaseIndexOpenAiCompatibleBaseUrl"] = base_url
    if embedder_model_id:
        index_config["codebaseIndexEmbedderModelId"] = embedder_model_id

    return _to_json(settings)


def mcp_settings(
    workspace_folder: str,
    github_token: str,
    oxylabs_username: str = "",
    oxylabs_password: str = "",
) -> str:
    """Render ``.roo/mcp.json`` as a JSON string."""
    config = _load_json_template(MCP_TEMPLATE)

    servers = config["mcpServers"]

    servers["github"]["env"]["GITHUB_PERSONAL_ACCESS_TOKEN"] = github_token

    git_args = servers["git"]["args"]
    servers["git"]["args"] = [
        workspace_folder if arg == "${workspaceFolder}" else arg for arg in git_args
    ]

    # Always substitute env values so no `${}` tokens remain in output.
    # When credentials are empty, set disabled=True to signal the MCP client.
    servers["oxylabs"]["env"]["OXYLABS_USERNAME"] = oxylabs_username
    servers["oxylabs"]["env"]["OXYLABS_PASSWORD"] = oxylabs_password
    if not oxylabs_username and not oxylabs_password:
        servers["oxylabs"]["disabled"] = True

    return _to_json(config)


def extensions_settings() -> str:
    return _to_json(_load_json_template(EXTENSIONS_TEMPLATE))


def write_text(path: PathLike, content: str) -> None:
    """Create parents and ensure a trailing newline."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not content.endswith("\n"):
        content += "\n"

    path.write_text(content, encoding="utf-8")


def _load_zoo_template(context_window: int) -> Dict[str, Any]:
    try:
        text = ZOO_TEMPLATE.read_text(encoding="utf-8")
    except OSError as exc:
        raise RenderError("Could not read {}: {}".format(ZOO_TEMPLATE, exc)) from exc

    if _CONTEXT_WINDOW_TOKEN not in text:
        raise RenderError(
            "{} no longer contains {}; the template and renderer have drifted "
            "apart".format(ZOO_TEMPLATE, _CONTEXT_WINDOW_TOKEN)
        )

    text = text.replace(_CONTEXT_WINDOW_TOKEN, str(int(context_window)))

    return _parse_json(text, source=ZOO_TEMPLATE)


def _load_json_template(path: Path) -> Dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RenderError("Could not read {}: {}".format(path, exc)) from exc

    return _parse_json(text, source=path)


def _parse_json(text: str, source: Path) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RenderError("Invalid JSON in {}: {}".format(source, exc)) from exc


def _to_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, indent=_INDENT)
