"""Bake-off invocation argv builders - one job: turn inputs into ``pi`` command lines.

The phase-1 bake-off (``plans/pi-phase1-bakeoff.md``) drives three ``pi``
invocations - print, json and ultrawork. This module is the single place that
decides what each invocation's argument vector looks like, so the host run
recipe (behaviour 18) can ``subprocess`` them without re-deriving token order.

Builders return a ``List[str]``, never a string: the list goes straight to
``subprocess`` with no shell, so no token can be re-parsed and no quoting rules
need to be obeyed. The fixture directory is deliberately NOT an argument -
the run recipe sets it as the subprocess cwd - which keeps every builder
independent of where the fixture happens to live.

``print_argv``, ``json_argv`` and ``ultrawork_argv`` build the three
invocations; ``models_document`` builds the Pi agent-directory models
document (``~/.pi/agent/models.json`` on the host, not a project file)
that points Pi at the local llama-swap gateway.
"""

import re
from typing import List


class ArgvError(Exception):
    """Any refusal to build an argument vector.

    A single exception type covers every invalid input, so callers need only
    one ``except`` clause.
    """


def _validate_model_id(model_id: str) -> None:
    """Raise if the model id is empty or whitespace-only.

    Raises:
        ArgvError: ``model_id`` is empty or whitespace-only.
    """
    if not model_id.strip():
        raise ArgvError("model id must not be empty")


def _validate(model_id: str, prompt: str) -> None:
    """Raise if either input is empty or whitespace-only.

    Raises:
        ArgvError: ``model_id`` or ``prompt`` is empty or whitespace-only.
    """
    _validate_model_id(model_id)
    if not prompt.strip():
        raise ArgvError("prompt must not be empty")


def _common_tail(model_id: str, prompt: str) -> List[str]:
    """Tokens after the harness form, shared by every invocation builder.

    The prompt is the final element, preceded by ``--`` so a prompt beginning
    with ``-`` is passed through verbatim rather than read as a flag.
    """
    return [
        "--model",
        model_id,
        "--tools",
        "read,edit,write",
        "-a",
        "--no-session",
        "--",
        prompt,
    ]


def print_argv(model_id: str, prompt: str) -> List[str]:
    """Build the argv for the bake-off print invocation (behaviour 4).

    Raises:
        ArgvError: ``model_id`` or ``prompt`` is empty or whitespace-only.
    """
    _validate(model_id, prompt)
    return ["pi", "-p"] + _common_tail(model_id, prompt)


def json_argv(model_id: str, prompt: str) -> List[str]:
    """Build the argv for the bake-off json invocation (behaviour 5).

    Identical to ``print_argv``'s output except the ``-p`` token is replaced
    by the two tokens ``--mode json`` at the same position. Both builders
    share ``_common_tail`` so the two invocations cannot drift apart.

    Raises:
        ArgvError: ``model_id`` or ``prompt`` is empty or whitespace-only.
    """
    _validate(model_id, prompt)
    return ["pi", "--mode", "json"] + _common_tail(model_id, prompt)


_UW_TOOLS = "read,edit,write,ulw_dispatch,ulw_complete"
_UW_TRIGGER = re.compile(r"\b(?:ultrawork|ulw)\b", re.IGNORECASE)


def ultrawork_argv(
    model_id: str, prompt: str, extension_path: str
) -> List[str]:
    """Build the argv for the bake-off ultrawork invocation (behaviour 6).

    The ``-p`` form plus the pi-ultrawork extension (``-e <path>``) and its
    two dispatch tools. The emitted prompt is the given prompt prefixed with
    ``"ultrawork "`` so the extension's whole-word trigger fires - unless the
    prompt already contains the trigger as a whole word, in which case it is
    passed through unchanged (never prefixed twice). The extension path is a
    real argv token, included verbatim with no shell or quoting.

    Raises:
        ArgvError: ``model_id``, ``prompt`` or ``extension_path`` is empty
            or whitespace-only.
    """
    _validate(model_id, prompt)
    if not extension_path.strip():
        raise ArgvError("extension path must not be empty")
    emitted_prompt = (
        prompt if _UW_TRIGGER.search(prompt) else "ultrawork " + prompt
    )
    return [
        "pi",
        "-p",
        "-e",
        extension_path,
        "--model",
        model_id,
        "--tools",
        _UW_TOOLS,
        "-a",
        "--no-session",
        "--",
        emitted_prompt,
    ]


def models_document(
    model_id: str, port: int, context_window: int, max_tokens: int
) -> dict:
    """Build the Pi agent-directory models document (behaviour 7).

    This is ``~/.pi/agent/models.json`` on the host, NOT a project file.
    It points Pi at the local llama-swap gateway through the dummy
    OpenAI-compatible provider, so the bake-off runs use the configured
    local model instead of a cloud key.

    The document is returned as a ``dict`` of JSON-native types; callers
    serialise it with ``json.dumps``. The dummy ``apiKey`` is the fixed
    placeholder ``"llamaswap-local"`` - Pi needs a non-empty string and
    the local gateway ignores it.

    Raises:
        ArgvError: ``model_id`` is empty or whitespace-only; ``port`` is
            outside 1-65535 (inclusive); or ``context_window`` < 1.
    """
    _validate_model_id(model_id)
    if not 1 <= port <= 65535:
        raise ArgvError("port must be in 1-65535")
    if context_window < 1:
        raise ArgvError("context window must be at least 1")
    return {
        "providers": {
            "llamaswap": {
                "baseUrl": "http://127.0.0.1:%d/v1" % port,
                "api": "openai-completions",
                "apiKey": "llamaswap-local",
                "models": [
                    {
                        "id": model_id,
                        "contextWindow": context_window,
                        "maxTokens": max_tokens,
                    }
                ],
            }
        }
    }
