"""Interactive prompts, every one of which can be bypassed.

This module owns exactly one thing: **deciding whether to ask**. Given a value
that may already have arrived from a CLI flag, plus ``--yes`` and interactivity
settings, it either returns that value or delegates to ``click`` to obtain one.

The asking itself - re-prompting on invalid input, choice validation, integer
ranges, hidden entry, y/n parsing - is click's job, and is not reimplemented here.

Resolution order for every function:

1. ``supplied`` is not None            -> use it, never prompt
2. ``assume_yes`` or not ``interactive`` -> use the default, never prompt
3. otherwise                            -> prompt
"""

import contextlib
import sys
from typing import Any, Iterator, List, Mapping, Optional, Sequence, TextIO

import click

CUSTOM_CHOICE_LABEL = "Custom model id"


class PromptError(Exception):
    """A value is needed but cannot be obtained without prompting."""


def ask(
    prompt: str,
    default: str,
    supplied: Optional[str] = None,
    assume_yes: bool = False,
    interactive: bool = True,
) -> str:
    if supplied is not None:
        return supplied

    if assume_yes or not interactive:
        return default

    try:
        return _read_line(prompt, default=default)
    except click.Abort:
        # Closed or exhausted stdin: the default is still a valid answer.
        return default


def ask_required(
    prompt: str,
    supplied: Optional[str] = None,
    assume_yes: bool = False,
    interactive: bool = True,
    hide_input: bool = False,
) -> str:
    """Ask for a value that has no default and may not be empty.

    Because no default exists, ``--yes`` cannot answer it and must fail loudly
    rather than silently write an empty credential.
    """
    if supplied is not None:
        return supplied

    if assume_yes or not interactive:
        raise PromptError(
            "{} is required but no value was supplied. Pass it as a flag when "
            "running non-interactively.".format(prompt)
        )

    try:
        # click re-prompts until non-empty because there is no default.
        return _read_line(prompt, hide_input=hide_input)
    except click.Abort:
        raise PromptError(
            "{} is required but stdin provided no value.".format(prompt)
        ) from None


def confirm(
    prompt: str,
    default: bool = False,
    supplied: Optional[bool] = None,
    assume_yes: bool = False,
    interactive: bool = True,
) -> bool:
    """Ask a yes/no question.

    ``assume_yes`` means "accept the defaults", so a question defaulting to no
    still answers no. Enabling a feature needs its own explicit flag.
    """
    if supplied is not None:
        return supplied

    if assume_yes or not interactive:
        return default

    try:
        return _read_confirmation(prompt, default=default)
    except click.Abort:
        return default


def ask_port(
    prompt: str,
    default: int,
    supplied: Optional[int] = None,
    assume_yes: bool = False,
    interactive: bool = True,
) -> int:
    """Ask for a TCP port, rejecting values outside 1-65535."""
    if supplied is not None:
        return int(supplied)

    if assume_yes or not interactive:
        return int(default)

    try:
        return int(
            _read_line(prompt, default=str(default), value_type=click.IntRange(1, 65535))
        )
    except click.Abort:
        return int(default)


def choose(
    prompt: str,
    options: Sequence[Mapping[str, Any]],
    default: str,
    supplied: Optional[str] = None,
    assume_yes: bool = False,
    interactive: bool = True,
    stream: Optional[TextIO] = None,
) -> str:
    """Present a numbered menu and return the chosen id.

    The options are data, read from ``anvil.yaml``. A final "custom" entry
    preserves the escape hatch that a hardcoded menu once provided.

    ``supplied`` is returned unvalidated, because ``--anthropic-model`` must
    accept any id.
    """
    if supplied is not None:
        return supplied

    ids = _option_ids(options, prompt)

    if assume_yes or not interactive:
        return default

    _render_menu(prompt, options, ids, default, stream)

    custom_index = len(ids) + 1
    default_index = ids.index(default) + 1 if default in ids else custom_index

    try:
        selection = int(
            _read_line(
                "   Select",
                default=str(default_index),
                value_type=click.IntRange(1, custom_index),
            )
        )
    except click.Abort:
        return default

    if selection <= len(ids):
        return ids[selection - 1]

    try:
        return _read_line("   Enter custom model id")
    except click.Abort:
        return default


def _option_ids(options: Sequence[Mapping[str, Any]], prompt: str) -> List[str]:
    if not options:
        raise PromptError("{}: no options were offered".format(prompt))

    ids = []
    for option in options:
        option_id = option.get("id")
        if not option_id:
            raise PromptError(
                "{}: every option needs an 'id' (got {!r})".format(prompt, option)
            )
        ids.append(str(option_id))

    return ids


def _render_menu(
    prompt: str,
    options: Sequence[Mapping[str, Any]],
    ids: Sequence[str],
    default: str,
    stream: Optional[TextIO],
) -> None:
    width = max(len(option_id) for option_id in ids)

    _emit("", stream)
    _emit("   {}:".format(prompt), stream)

    for index, option in enumerate(options, start=1):
        label = option.get("label")
        line = "     {}) {:<{width}}".format(index, ids[index - 1], width=width)
        if label:
            line += "  ({})".format(label)
        _emit(line, stream)

    _emit("     {}) {}".format(len(ids) + 1, CUSTOM_CHOICE_LABEL), stream)
    _emit("", stream)


def _emit(text: str, stream: Optional[TextIO]) -> None:
    click.echo(text, file=stream)


def _read_line(
    prompt: str,
    default: Optional[str] = None,
    hide_input: bool = False,
    value_type: Optional[Any] = None,
) -> str:
    """Single seam through which every keystroke arrives.

    Tests patch this to prove that a bypassed prompt never reads stdin.

    Behaviour 22: a prompt with no default must terminate on an exhausted
    stdin instead of re-prompting forever. click 8.1.7's own loop only
    breaks out of an empty answer when a default is set, so on an
    exhausted fake stdin (``CliRunner``'s reader returns ``""`` at EOF
    rather than raising) it re-asks until the process is killed. The
    read is therefore wrapped: an empty line while ``sys.stdin`` is
    provably at its end raises :class:`click.Abort`, which the caller's
    existing ``except click.Abort`` already maps (to the default for a
    default-carrying prompt, to ``PromptError`` for ``ask_required``).
    A blank line with more input behind it still re-prompts, and a real
    terminal is untouched: ``input``/``getpass`` raise ``EOFError``
    there, which click converts to ``Abort`` on its own (termui.py:141).
    """
    with _wrap_prompt_readers(default):
        return click.prompt(
            prompt,
            default=default,
            hide_input=hide_input,
            type=value_type,
            show_default=True,
        )


@contextlib.contextmanager
def _wrap_prompt_readers(default: Optional[str]) -> "Iterator[None]":
    """Wrap click's prompt readers so an empty read at stdin's end aborts.

    click ``prompt`` has no ``prompt_func`` parameter (8.1.7), so the read is
    wrapped the same way ``CliRunner.isolation`` itself wraps it: by
    temporarily rebinding ``click.termui.visible_prompt_func`` /
    ``hidden_prompt_func`` around the call. The wrapper still calls click's
    reader, so no terminal I/O is re-implemented; it only inspects the line
    the reader returned.
    """
    termui = click.termui

    def guard(f):
        def guarded(text: str) -> str:
            value = f(text)
            if not value and default is None and _stdin_exhausted():
                raise click.Abort()
            return value

        return guarded

    old_visible = termui.visible_prompt_func
    old_hidden = termui.hidden_prompt_func
    termui.visible_prompt_func = guard(old_visible)
    termui.hidden_prompt_func = guard(old_hidden)
    try:
        yield
    finally:
        termui.visible_prompt_func = old_visible
        termui.hidden_prompt_func = old_hidden


def _stdin_exhausted() -> bool:
    """True when ``sys.stdin`` has no more data, decided without consuming any.

    A blank answer (``""``) at the end of a finite stream is exhaustion; the
    same answer mid-stream is just a blank line and must re-prompt. The probe
    reads one character and restores the position, so it costs the prompt
    nothing. It is only ever reached after the reader has already returned at
    the end of the stream, so it cannot block. A stream that cannot report
    its position (a real terminal, whose reader raises ``EOFError`` on
    exhaustion anyway) reports False, leaving that path on click's own
    ``Abort`` handling.
    """
    stream = sys.stdin
    if stream is None or stream.isatty():
        return False
    try:
        position = stream.tell()
        byte = stream.read(1)
        stream.seek(position)
    except (AttributeError, OSError, ValueError):
        return False
    return byte == ""


def _read_confirmation(prompt: str, default: bool) -> bool:
    return click.confirm(prompt, default=default)
