"""Health checks against the llama-swap gateway.

Rendering is kept separate from probing so the CLI can emit either the human
table or ``--json`` from one unchanged check.

The module also answers a question the registry cannot: *does this model still
generate?* ``check_gateway`` only reports what llama-swap has registered and
loaded, which says nothing about whether the underlying vLLM worker can actually
answer. :func:`test_model` sends one real completion to find out.
"""

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

DEFAULT_TIMEOUT = 2.0

# Generation gets its own budget. llama-swap loads a cold model on demand, so the
# first token of the first request can be minutes away while weights are read
# and CUDA graphs are captured. Using DEFAULT_TIMEOUT here would make every cold
# model look broken; raising it to suit generation would make 'anvil status'
# hang on a dead host. They are genuinely two different questions.
DEFAULT_GENERATION_TIMEOUT = 1000.0

# Short and deterministic: the point is to prove the round trip works, not to
# exercise the model.
DEFAULT_PROBE_PROMPT = "Reply with the single word: pong"

# Enough for a sentence, small enough that a wedged model cannot stream for
# minutes.
DEFAULT_MAX_TOKENS = 32

_MODELS_PATH = "/v1/models"
_RUNNING_PATH = "/running"
_CHAT_PATH = "/v1/chat/completions"

_SEPARATOR = "-" * 60
_NAME_WIDTH = 45

_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_RESET = "\033[0m"

# vLLM's reasoning parsers can put the answer in 'reasoning_content' when
# 'content' is empty, which would otherwise look like a model that answered with
# nothing.
_CONTENT_KEYS = ("content", "reasoning_content")

# Keys under which llama-swap names a loaded model.
_MODEL_NAME_KEYS = ("model", "id", "name")


class ModelStatus:
    """One registered model and whether it is currently loaded."""

    def __init__(self, id: str, hot: bool) -> None:
        self.id = id
        self.hot = hot

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ModelStatus):
            return NotImplemented
        return self.id == other.id and self.hot == other.hot

    def __repr__(self) -> str:
        return "ModelStatus({!r}, hot={!r})".format(self.id, self.hot)


class ModelTestResult:
    """The outcome of asking one model to answer one prompt.

    ``unknown_model`` separates "you named a model this gateway has never heard
    of" - a typo, answerable by listing the registry - from "the model exists but
    did not answer", which is a real fault. Both are failures; only one of them
    is the user's spelling.
    """

    def __init__(
        self,
        port: int,
        model_id: str,
        prompt: str,
        ok: bool,
        reply: Optional[str] = None,
        error: Optional[str] = None,
        latency_seconds: Optional[float] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        unknown_model: bool = False,
        available_models: Optional[Sequence[str]] = None,
    ) -> None:
        self.port = port
        self.model_id = model_id
        self.prompt = prompt
        self.ok = ok
        self.reply = reply
        self.error = error
        self.latency_seconds = latency_seconds
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.unknown_model = unknown_model
        self.available_models: List[str] = list(available_models or [])

    def __repr__(self) -> str:
        return "ModelTestResult({!r}, ok={!r})".format(self.model_id, self.ok)


class GatewayStatus:
    """The outcome of probing the gateway.

    ``error`` means the gateway could not be reached at all. ``registry_error``
    and ``running_error`` mean it answered but one of its payloads was unusable -
    a distinction the old script could not make.
    """

    def __init__(
        self,
        port: int,
        online: bool,
        models: Optional[Sequence[ModelStatus]] = None,
        error: Optional[str] = None,
        registry_error: Optional[str] = None,
        running_error: Optional[str] = None,
    ) -> None:
        self.port = port
        self.online = online
        self.models: List[ModelStatus] = list(models or [])
        self.error = error
        self.registry_error = registry_error
        self.running_error = running_error


def check_gateway(port: int, timeout: float = DEFAULT_TIMEOUT) -> GatewayStatus:
    """Never raises for a network or payload problem."""
    try:
        registry_body = _fetch(port, _MODELS_PATH, timeout)
    except _ProbeError as exc:
        return GatewayStatus(port=port, online=False, error=str(exc))

    registry_error = None
    try:
        model_ids = _parse_registry(registry_body)
    except _ProbeError as exc:
        model_ids = []
        registry_error = str(exc)

    running_error = None
    running_ids: Set[str] = set()
    try:
        running_ids = _parse_running(_fetch(port, _RUNNING_PATH, timeout))
    except _ProbeError as exc:
        running_error = str(exc)

    return GatewayStatus(
        port=port,
        online=True,
        models=[ModelStatus(mid, mid in running_ids) for mid in model_ids],
        registry_error=registry_error,
        running_error=running_error,
    )


def format_status(status: GatewayStatus, use_color: bool = True) -> str:
    lines = []

    if not status.online:
        lines.append(
            "🔴 Swap Router Gateway (Port {}): OFFLINE (Service completely "
            "down)".format(status.port)
        )
        if status.error:
            lines.append("   ↳ {}".format(status.error))
        lines.append(_SEPARATOR)
        return "\n".join(lines)

    lines.append(
        "🟢 Swap Router Gateway (Port {}): ONLINE & ROUTING".format(status.port)
    )
    lines.append("--- Registered Model Matrix ---")

    if status.registry_error:
        lines.append(
            "⚠️  Could not read the router gateway registry: {}".format(
                status.registry_error
            )
        )
    if status.running_error:
        lines.append(
            "⚠️  Could not read live model state: {} (models shown as "
            "cold)".format(status.running_error)
        )

    if not status.models:
        if not status.registry_error:
            lines.append("⚠️  No models returned by the router gateway registry.")
    else:
        for model in status.models:
            lines.append(_format_model_line(model, use_color))

    lines.append(_SEPARATOR)
    return "\n".join(lines)


def format_json(status: GatewayStatus) -> str:
    payload: Dict[str, Any] = {
        "port": status.port,
        "online": status.online,
        "models": [{"id": m.id, "hot": m.hot} for m in status.models],
        "error": status.error,
        "registry_error": status.registry_error,
        "running_error": status.running_error,
    }
    return json.dumps(payload, indent=2)


def build_chat_request(
    model_id: str, prompt: str, max_tokens: int
) -> Dict[str, Any]:
    """Built as a dict, never assembled by string substitution.

    Public so ``--dry-run`` can show the request without sending it.
    """
    return {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        # A streamed response would have to be reassembled for no benefit: this
        # probe wants the whole answer, not the first token.
        "stream": False,
        # Reasoning models spend tokens thinking before they answer. This key
        # is silently ignored by gateways that do not understand it.
        "chat_template_kwargs": {"enable_thinking": False},
    }


def test_model(
    port: int,
    model_id: str,
    prompt: str = DEFAULT_PROBE_PROMPT,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout: float = DEFAULT_GENERATION_TIMEOUT,
    registry_timeout: float = DEFAULT_TIMEOUT,
) -> ModelTestResult:
    """Send ``prompt`` to ``model_id`` and report whether it answered.

    Like :func:`check_gateway`, this never raises for a network or payload
    problem: a model that fails to answer is the very thing being measured.

    The registry is consulted first, under the short ``registry_timeout``, so a
    misspelled name costs two seconds rather than potentially triggering a
    multi-minute model load. Matching is exact set membership, so a registered
    ``vendor/model-a-instruct`` never accepts a request for ``vendor/model-a``.
    """
    failed = _Failure(port, model_id, prompt)

    try:
        registered = _parse_registry(_fetch(port, _MODELS_PATH, registry_timeout))
    except _ProbeError as exc:
        return failed(str(exc))

    if model_id not in set(registered):
        return failed(
            "{!r} is not registered on the gateway at port {}".format(model_id, port),
            unknown_model=True,
            available_models=registered,
        )

    body = build_chat_request(model_id, prompt, max_tokens)

    started = time.monotonic()
    try:
        response = _post_json(port, _CHAT_PATH, body, timeout)
    except _ProbeError as exc:
        return failed(str(exc), latency_seconds=time.monotonic() - started)
    elapsed = time.monotonic() - started

    try:
        reply = _parse_completion(response)
    except _ProbeError as exc:
        return failed(str(exc), latency_seconds=elapsed)

    prompt_tokens, completion_tokens = _parse_usage(response)

    return ModelTestResult(
        port=port,
        model_id=model_id,
        prompt=prompt,
        ok=True,
        reply=reply,
        latency_seconds=elapsed,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def format_model_test(result: ModelTestResult, use_color: bool = True) -> str:
    lines = []

    if result.ok:
        marker, verdict, color = "🟢", "PASS", _GREEN
    else:
        marker, verdict, color = "🔴", "FAIL", _RED

    if use_color:
        verdict = "{}{}{}".format(color, verdict, _RESET)

    lines.append(
        "{} {} - {} (port {})".format(marker, verdict, result.model_id, result.port)
    )
    lines.append(_SEPARATOR)
    lines.append("  prompt   : {}".format(result.prompt))

    if result.ok:
        lines.append("  reply    : {}".format(result.reply))
        if result.latency_seconds is not None:
            lines.append("  latency  : {:.2f}s".format(result.latency_seconds))
        if result.prompt_tokens is not None or result.completion_tokens is not None:
            lines.append(
                "  tokens   : {} prompt, {} completion".format(
                    _or_unknown(result.prompt_tokens),
                    _or_unknown(result.completion_tokens),
                )
            )
    else:
        lines.append("  error    : {}".format(result.error))
        # The registry only helps when the name itself was wrong; dumping it
        # after a generation failure would bury the actual error.
        if result.unknown_model and result.available_models:
            lines.append("  registered models:")
            for model in result.available_models:
                lines.append("    - {}".format(model))

    lines.append(_SEPARATOR)
    return "\n".join(lines)


def format_model_test_json(result: ModelTestResult) -> str:
    payload: Dict[str, Any] = {
        "port": result.port,
        "model": result.model_id,
        "prompt": result.prompt,
        "ok": result.ok,
        "reply": result.reply,
        "error": result.error,
        "latency_seconds": result.latency_seconds,
        "usage": {
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
        },
        "unknown_model": result.unknown_model,
        "available_models": result.available_models,
    }
    return json.dumps(payload, indent=2)


def format_request(port: int, body: Mapping[str, Any]) -> str:
    lines = [
        "would POST to {}".format(_url(port, _CHAT_PATH)),
        _SEPARATOR,
        json.dumps(dict(body), indent=2),
        _SEPARATOR,
    ]
    return "\n".join(lines)


def format_request_json(port: int, body: Mapping[str, Any]) -> str:
    return json.dumps(
        {
            "port": port,
            "url": _url(port, _CHAT_PATH),
            "method": "POST",
            "body": dict(body),
        },
        indent=2,
    )


class _ProbeError(Exception):
    """An internal failure while probing; converted into fields on the status."""


class _Failure:
    """Builds a failed ModelTestResult without repeating its five fixed fields."""

    def __init__(self, port: int, model_id: str, prompt: str) -> None:
        self._port = port
        self._model_id = model_id
        self._prompt = prompt

    def __call__(self, error: str, **kwargs: Any) -> ModelTestResult:
        return ModelTestResult(
            port=self._port,
            model_id=self._model_id,
            prompt=self._prompt,
            ok=False,
            error=error,
            **kwargs
        )


def _or_unknown(value: Optional[int]) -> str:
    return "?" if value is None else str(value)


def _format_model_line(model: ModelStatus, use_color: bool) -> str:
    if model.hot:
        marker, state = "🟢", "ACTIVE & HOT"
        color = _GREEN
    else:
        marker, state = "🟡", "COLD / SWAPPED OUT (Lazy-loads on demand)"
        color = _YELLOW

    if use_color:
        marker = "{}{}{}".format(color, marker, _RESET)

    return "  {} {:<{width}} : {}".format(
        marker, model.id, state, width=_NAME_WIDTH
    )


def _url(port: int, path: str) -> str:
    return "http://localhost:{}{}".format(port, path)


def _fetch(port: int, path: str, timeout: float) -> str:
    """GET one gateway endpoint, translating every failure into _ProbeError."""
    return _read(urllib.request.urlopen, _url(port, path), path, timeout)


def _post_json(
    port: int, path: str, body: Mapping[str, Any], timeout: float
) -> Any:
    """POST a JSON body to one gateway endpoint and return the parsed reply.

    The body is serialised from a dict, so a prompt containing quotes, newlines
    or braces cannot corrupt the request.
    """
    request = urllib.request.Request(
        _url(port, path),
        data=json.dumps(dict(body)).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )

    return _load_json(_read(urllib.request.urlopen, request, path, timeout), path)


def _read(opener: Any, target: Any, path: str, timeout: float) -> str:
    """Perform one request, translating every failure into _ProbeError."""
    try:
        with opener(target, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise _ProbeError(
            "HTTP {} from {}{}".format(exc.code, path, _error_detail(exc))
        ) from exc
    except socket.timeout as exc:
        raise _ProbeError(
            "timed out after {}s contacting {}".format(timeout, path)
        ) from exc
    except urllib.error.URLError as exc:
        # URLError wraps the real cause, including socket.timeout on some versions.
        if isinstance(exc.reason, socket.timeout):
            raise _ProbeError(
                "timed out after {}s contacting {}".format(timeout, path)
            ) from exc
        raise _ProbeError("{}: {}".format(path, exc.reason)) from exc
    except OSError as exc:
        raise _ProbeError("{}: {}".format(path, exc)) from exc


def _error_detail(exc: urllib.error.HTTPError) -> str:
    """Extract the gateway's own explanation from an error response.

    A bare 'HTTP 400' hides the one thing worth knowing - for instance that an
    embedding model was asked for a chat completion. The body is read
    defensively: it may be absent, unreadable, or not JSON at all.
    """
    try:
        raw = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:  # pragma: no cover - depends on the failure mode
        return ""

    if not raw:
        return ""

    try:
        payload = json.loads(raw)
    except ValueError:
        return ": {}".format(raw)

    if isinstance(payload, dict):
        error = payload.get("error", payload.get("message"))
        if isinstance(error, dict):
            error = error.get("message")
        if isinstance(error, str) and error:
            return ": {}".format(error)

    return ": {}".format(raw)


def _parse_completion(payload: Any) -> str:
    """Extract the assistant's text from a chat-completion payload."""
    if not isinstance(payload, dict):
        raise _ProbeError("{} returned a non-object payload".format(_CHAT_PATH))

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise _ProbeError("{} returned no choices".format(_CHAT_PATH))

    first = choices[0]
    if not isinstance(first, dict):
        raise _ProbeError("{} returned a malformed choice".format(_CHAT_PATH))

    message = first.get("message")
    if not isinstance(message, dict):
        raise _ProbeError("{} returned a choice with no message".format(_CHAT_PATH))

    for key in _CONTENT_KEYS:
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    # 'length' means the model was still going when the budget ran out, which is
    # a different problem from a model that answered with nothing - and one the
    # user can fix with --max-tokens.
    if first.get("finish_reason") == "length":
        raise _ProbeError(
            "the model returned an empty reply: it hit the token limit before "
            "answering (raise --max-tokens)"
        )

    raise _ProbeError("the model returned an empty reply")


def _parse_usage(payload: Any) -> Tuple[Optional[int], Optional[int]]:
    """Extract the token counts, which are informative but never required."""
    if not isinstance(payload, dict):
        return None, None

    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None, None

    return _as_int(usage.get("prompt_tokens")), _as_int(
        usage.get("completion_tokens")
    )


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _load_json(body: str, path: str) -> Any:
    try:
        return json.loads(body)
    except ValueError as exc:
        raise _ProbeError("{} did not return JSON: {}".format(path, exc)) from exc


def _parse_registry(body: str) -> List[str]:
    """Extract model ids from an OpenAI-style ``/v1/models`` payload."""
    payload = _load_json(body, _MODELS_PATH)

    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, dict):
        if "data" not in payload:
            raise _ProbeError(
                "{} payload has no 'data' key".format(_MODELS_PATH)
            )
        entries = payload["data"]
    else:
        raise _ProbeError(
            "{} payload is neither an object nor a list".format(_MODELS_PATH)
        )

    if not isinstance(entries, list):
        raise _ProbeError("{} 'data' is not a list".format(_MODELS_PATH))

    ids = []
    for entry in entries:
        # Only the top level of each entry is read, so a nested 'id' - which the
        # old 'grep -o' happily scraped - is correctly ignored.
        if isinstance(entry, dict):
            candidate = entry.get("id")
        elif isinstance(entry, str):
            candidate = entry
        else:
            continue

        if isinstance(candidate, str) and candidate:
            ids.append(candidate)

    return ids


def _parse_running(body: str) -> Set[str]:
    """Extract loaded model ids, tolerating every observed payload shape."""
    payload = _load_json(body, _RUNNING_PATH)

    if isinstance(payload, dict):
        entries = payload.get("running", payload.get("models", []))
    elif isinstance(payload, list):
        entries = payload
    else:
        entries = []

    if not isinstance(entries, list):
        return set()

    running = set()
    for entry in entries:
        if isinstance(entry, str):
            if entry:
                running.add(entry)
            continue

        if not isinstance(entry, dict):
            continue

        for key in _MODEL_NAME_KEYS:
            value = entry.get(key)
            if isinstance(value, str) and value:
                running.add(value)
                break

    return running
