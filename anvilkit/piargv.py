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

``print_argv`` and ``json_argv`` exist so far; ``ultrawork_argv`` and
``models_document`` land in later cycles of the same plan, each with its own
red test step.
"""

from typing import List


class ArgvError(Exception):
    """Any refusal to build an argument vector.

    A single exception type covers every invalid input, so callers need only
    one ``except`` clause.
    """


def _validate(model_id: str, prompt: str) -> None:
    """Raise if either input is empty or whitespace-only.

    Raises:
        ArgvError: ``model_id`` or ``prompt`` is empty or whitespace-only.
    """
    if not model_id.strip():
        raise ArgvError("model id must not be empty")
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
