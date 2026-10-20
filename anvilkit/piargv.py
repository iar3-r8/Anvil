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

Only ``print_argv`` exists in this cycle; ``json_argv``, ``ultrawork_argv`` and
``models_document`` land in later cycles of the same plan, each with its own
red test step.
"""

from typing import List


class ArgvError(Exception):
    """Any refusal to build an argument vector.

    A single exception type covers every invalid input, so callers need only
    one ``except`` clause.
    """


def print_argv(model_id: str, prompt: str) -> List[str]:
    """Build the argv for the bake-off print invocation (behaviour 4).

    The prompt is the final element, preceded by ``--`` so a prompt beginning
    with ``-`` is passed through verbatim rather than read as a flag.

    Raises:
        ArgvError: ``model_id`` or ``prompt`` is empty or whitespace-only.
    """
    if not model_id.strip():
        raise ArgvError("model id must not be empty")
    if not prompt.strip():
        raise ArgvError("prompt must not be empty")

    return [
        "pi",
        "-p",
        "--model",
        model_id,
        "--tools",
        "read,edit,write",
        "-a",
        "--no-session",
        "--",
        prompt,
    ]
