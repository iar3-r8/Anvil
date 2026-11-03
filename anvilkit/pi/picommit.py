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
landed. Behaviours 5 and 6 of ``plans/pi-phase9-redgreen.md`` are
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
so it is reported even when the other fields are fine. Behaviour 7
(git-argv-is-a-list) is not yet implemented; it lands in its own
cycle.

Stdlib only. One exception type: ``CommitError``.
"""

from typing import List, Optional


class CommitError(Exception):
    """A commit message or argv this builder could not build.

    A single exception type covers every build failure, so callers
    need only one ``except`` clause. Every raise this module has
    today belongs to behaviour 5 or 6: an empty scope or behaviour
    raises it, since a message built from an empty scope or behaviour
    would be malformed history, and an unknown branch kind raises it,
    since a green subject can only be ``feat`` or ``fix``. Every
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
