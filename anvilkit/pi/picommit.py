"""Red/green commit messages and git argv for the red/green cycle.

One job: build the red and green commit messages and the ``git`` argv
the driver commits with, and nothing else. This module builds, never
executes: it performs no subprocess, no git and no file write; the
driver that acts on a built message lives in ``anvilkit.pi.picycle``.
The formats are the ones the TDD manager's instructions pin - the
"failing" in the red subject is load-bearing, and a red is never
amended or squashed into its green, so the message is one immutable
string.

House discipline, as ``anvilkit.pi.piverdict`` uses it: one behaviour
lands per red/green cycle, and the docstring says which ones have
landed. Behaviours 5, 6 and 7 of ``plans/pi-phase9-redgreen.md`` are
implemented here: ``red_message(scope, behaviour, number, plan_slug,
assertion, issue=None)`` builds the red commit message - subject
``test({scope}): cover {behaviour}, failing``, a blank line, the body
``Behaviour {n} of plans/{task-slug}.md; fails: {assertion}.`` - and
``green_message(scope, behaviour, number, plan_slug, kind, issue=None)``
builds the green commit message - subject ``feat({scope}): {behaviour}``
for a ``"feature"`` kind, ``fix({scope}): {behaviour}`` for a
``"bugfix"`` kind, a blank line, the body ``Behaviour {n} of
plans/{task-slug}.md. Green.`` Both append a ``Refs #{issue}`` trailer
that is omitted entirely when no issue number is given, trailer and
blank line together (one private helper owns that rule, so the two
builders cannot drift); "failing" never appears in a green message,
since it is what keeps the red distinct from its green in history.
An empty ``scope`` or ``behaviour`` raises ``CommitError`` naming the
offending field; an unknown branch kind raises ``CommitError`` naming
the offending kind, and the kind is validated before the field checks
so it is reported even when the other fields are fine.
``add_argv(repo, paths)`` and ``commit_argv(repo, message)`` build the
``git`` argv the driver executes - always a ``list``, never a shell
string, so no argument can be re-parsed: ``add_argv`` is
``["git", "-C", repo, "add", "--"] + list(paths)`` and ``commit_argv``
is ``["git", "-C", repo, "commit", "-m", message]``. The ``--``
separator in ``add_argv`` is load-bearing: every path is data after
it, so a path starting with ``-`` (e.g. ``-rf``) is never re-parsed
as an option. The message in ``commit_argv`` is ONE element,
byte-identical to the input - never split, never quoted, never run
through a shell - and ``--amend`` and ``--no-verify`` are never
emitted, since the red is never amended or squashed and the message
format is ours and immutable. An empty ``repo`` raises ``CommitError``
naming the field in both builders; an empty ``message`` raises
``CommitError`` naming it in ``commit_argv``. An empty ``paths`` list
is not an error: the plan does not pin it.

Stdlib only. One exception type: ``CommitError``.
"""

from typing import List, Optional, Sequence


class CommitError(Exception):
    """A commit message or git argv this module could not build.

    A single exception type covers every build failure, so callers
    need only one ``except`` clause. Every raise this module has
    belongs to behaviour 5, 6 or 7: an empty scope or behaviour
    raises it, since a message built from an empty scope or behaviour
    would be malformed history; an unknown branch kind raises it,
    since a green subject can only be ``feat`` or ``fix``; an empty
    repo path raises it in both argv builders, since ``git -C`` given
    no path is a command that could not have been meant; and an empty
    message raises it in ``commit_argv``, since a commit without a
    message is not the immutable string this module builds. Every
    message names the offending field or kind, so a failure is
    fixable without reading the source.
    """


def _append_trailer(lines: List[str], issue: Optional[int]) -> None:
    """Append the ``Refs #{issue}`` trailer to a message's line list.

    The trailer is the intake's reference; it is omitted entirely -
    no trailer, no blank-line-only tail - when ``issue`` is
    ``None``. Shared by the red and green builders so the two cannot
    drift apart on the same rule.
    """
    if issue is not None:
        lines.append("")
        lines.append("Refs #%d" % issue)


def red_message(
    scope: str,
    behaviour: str,
    number: int,
    plan_slug: str,
    assertion: str,
    issue: Optional[int] = None,
) -> str:
    """Build the red commit message for one behaviour's red step.

    ``scope`` and ``behaviour`` are the conventional-commit scope and
    the behaviour name; ``number`` is the behaviour's number in the
    plan; ``plan_slug`` is the plan file's slug, so the body cites
    ``plans/{plan_slug}.md``; ``assertion`` is the actual failing
    assertion of the red step; ``issue`` is the GitHub issue number
    the cycle runs under, or ``None`` when there is none.

    Behaviour 5 (red-message-format): the message is exactly four
    parts - subject ``test({scope}): cover {behaviour}, failing``, a
    blank line, the body ``Behaviour {n} of plans/{task-slug}.md;
    fails: {assertion}.``, and a ``Refs #{issue}`` trailer separated
    from the body by a blank line. The trailer is omitted entirely
    when ``issue`` is ``None`` - no trailer, no blank-line-only tail,
    so a message without an issue ends at the body. The "failing" in
    the subject is load-bearing: it is what keeps the red distinct
    from its green in history.

    Error: an empty ``scope`` or ``behaviour`` raises ``CommitError``
    naming the offending field - a message built from either would be
    malformed history. The checks run in the order the fields appear
    in the subject, so an empty scope is reported before an empty
    behaviour.
    """
    if not scope:
        raise CommitError("scope is empty; a red message names its scope")
    if not behaviour:
        raise CommitError(
            "behaviour is empty; a red message names its behaviour"
        )
    lines = [
        "test(%s): cover %s, failing" % (scope, behaviour),
        "",
        "Behaviour %d of plans/%s.md; fails: %s."
        % (number, plan_slug, assertion),
    ]
    _append_trailer(lines, issue)
    return "\n".join(lines)


def green_message(
    scope: str,
    behaviour: str,
    number: int,
    plan_slug: str,
    kind: str,
    issue: Optional[int] = None,
) -> str:
    """Build the green commit message for one behaviour's green step.

    ``scope``, ``behaviour``, ``number``, ``plan_slug`` and ``issue``
    mean the same as in :func:`red_message`; ``kind`` is the branch
    kind - ``"feature"`` or ``"bugfix"`` - and picks the subject
    prefix: ``feat`` for a feature, ``fix`` for a bugfix.

    Behaviour 6 (green-message-format): the message is exactly four
    parts - subject ``feat({scope}): {behaviour}`` (or ``fix(...)``
    for a bugfix), a blank line, the body ``Behaviour {n} of
    plans/{task-slug}.md. Green.``, and a ``Refs #{issue}`` trailer
    separated from the body by a blank line. The trailer is omitted
    entirely when ``issue`` is ``None``, by the same helper the red
    uses - no trailer, no blank-line-only tail - so a green message
    without an issue ends at the body, which is why "Green." sits at
    the end of the body line, never of the whole message. "failing"
    never appears anywhere in a green message: it is what keeps the
    red distinct from its green in history.

    Error: an unknown ``kind`` raises ``CommitError`` naming the
    offending kind, validated before the field checks so it is
    reported even when the other fields are fine; an empty ``scope``
    or ``behaviour`` raises ``CommitError`` naming the offending
    field, in the same order the red uses.
    """
    prefixes = {"feature": "feat", "bugfix": "fix"}
    prefix = prefixes.get(kind)
    if prefix is None:
        raise CommitError(
            "unknown branch kind %r; a green message is built for a "
            "'feature' or a 'bugfix'" % kind
        )
    if not scope:
        raise CommitError("scope is empty; a green message names its scope")
    if not behaviour:
        raise CommitError(
            "behaviour is empty; a green message names its behaviour"
        )
    lines = [
        "%s(%s): %s" % (prefix, scope, behaviour),
        "",
        "Behaviour %d of plans/%s.md. Green." % (number, plan_slug),
    ]
    _append_trailer(lines, issue)
    return "\n".join(lines)


def add_argv(repo: str, paths: Sequence[str]) -> List[str]:
    """Build the ``git add`` argv that stages ``paths`` in ``repo``.

    ``repo`` is the repository path ``git -C`` runs in; ``paths`` are
    the paths to stage, in the order given.

    Behaviour 7 (git-argv-is-a-list), the add half: the return is a
    list, never a shell string, exactly
    ``["git", "-C", repo, "add", "--"] + list(paths)``. The ``--``
    separator is load-bearing: every path is data after it, so a path
    starting with ``-`` (e.g. ``-rf``) is never re-parsed as an
    option - the house rule that no argument can be re-parsed.
    ``paths`` is expanded in order, and an empty ``paths`` is not an
    error: the plan does not pin it.

    Error: an empty ``repo`` raises ``CommitError`` naming the field,
    since ``git -C`` given no path is a command that could not have
    been meant.
    """
    if not repo:
        raise CommitError(
            "repo is empty; the add argv needs a path to run in"
        )
    return ["git", "-C", repo, "add", "--"] + list(paths)


def commit_argv(repo: str, message: str) -> List[str]:
    """Build the ``git commit`` argv that commits ``message`` in ``repo``.

    ``repo`` is the repository path ``git -C`` runs in; ``message`` is
    the already-built commit message, one immutable string.

    Behaviour 7 (git-argv-is-a-list), the commit half: the return is
    a list, never a shell string, exactly
    ``["git", "-C", repo, "commit", "-m", message]``. The message is
    ONE element, byte-identical to the input - never split, never
    quoted, never run through a shell - so a multi-line message stays
    one element. ``--amend`` and ``--no-verify`` are never emitted:
    the red is never amended or squashed into its green, and the
    message format is ours and immutable.

    Error: an empty ``repo`` or an empty ``message`` raises
    ``CommitError`` naming the offending field, checked in the order
    the arguments appear, so an empty repo is reported before an
    empty message.
    """
    if not repo:
        raise CommitError(
            "repo is empty; the commit argv needs a path to run in"
        )
    if not message:
        raise CommitError(
            "message is empty; the commit argv carries the built message"
        )
    return ["git", "-C", repo, "commit", "-m", message]
