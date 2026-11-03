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
landed. Only behaviour 5 (red-message-format) of
``plans/pi-phase9-redgreen.md`` is implemented here:
``red_message(scope, behaviour, number, plan_slug, assertion,
issue=None)`` builds the red commit message - subject
``test({scope}): cover {behaviour}, failing``, a blank line, the body
``Behaviour {n} of plans/{task-slug}.md; fails: {assertion}.``, and a
``Refs #{issue}`` trailer that is omitted entirely when no issue
number is given, trailer and blank line together. An empty ``scope``
or ``behaviour`` raises ``CommitError`` naming the offending field.
Behaviours 6 (green-message-format) and 7 (git-argv-is-a-list) are
not yet implemented; they land in their own cycles.

Stdlib only. One exception type: ``CommitError``.
"""

from typing import Optional


class CommitError(Exception):
    """A commit message or argv this builder could not build.

    A single exception type covers every build failure, so callers
    need only one ``except`` clause. The one raise this module has
    today belongs to behaviour 5: an empty scope or behaviour raises
    it, since a message built from an empty scope or behaviour would
    be malformed history. Every message names the offending field, so
    a failure is fixable without reading the source.
    """


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
    if issue is not None:
        lines.append("")
        lines.append("Refs #%d" % issue)
    return "\n".join(lines)
