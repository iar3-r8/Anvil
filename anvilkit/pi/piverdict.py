"""Red/green verdict classifier for one suite run.

One job: classify the result of a single ``unittest`` suite run into a
verdict, and nothing else. This module decides, never acts: it performs
no subprocess, no Docker and no git, and it builds no commit message;
the driver that acts on a verdict lives in ``anvilkit.pi.picycle``. It
reads exactly two attributes of the result, ``errors`` and ``failures``,
so the two kinds of red stay separable the way ``TestResult`` keeps
them apart - the exit code cannot separate them.

At this stage of the red/green cycle behaviours 1-2 of
``plans/pi-phase9-redgreen.md`` are implemented: a result with empty
``errors`` and ``failures`` classifies as ``"green"`` (behaviour 1),
and a result carrying ``failures`` but no ``errors`` classifies as
``"red"`` (behaviour 2). A green raises nothing, whatever ``reason``
holds, empty included (``reason`` is ignored on the green path, since
a green has no failure to match against); a genuine red also raises
nothing at this stage. The remaining verdicts - ``"wrong_kind"``
(behaviour 3, the ``errors`` list) and the reason-matching rule
(behaviour 4, including its empty-reason ``VerdictError``) - are not
implemented yet and each lands in its own red/green cycle; a result
carrying ``errors`` raises ``VerdictError`` until behaviour 3 does.

Stdlib only. One exception type: ``VerdictError``.
"""

import unittest


class VerdictError(Exception):
    """A verdict the classifier could not give.

    A single exception type covers every classification failure, so
    callers need only one ``except`` clause. Today it fires only for a
    result carrying ``errors``, which the classifier has not learned to
    judge yet (behaviour 3 lands ``"wrong_kind"``); behaviour 4 will
    additionally raise it when a genuine red carries an empty reason,
    since an unstated reason cannot be verified. Every message names
    the offending value, so a failure is fixable without reading the
    source.
    """


def classify(result: unittest.TestResult, reason: str) -> str:
    """Classify one suite run into its verdict.

    ``result`` is the object a ``unittest`` run produces - anything
    exposing the ``errors`` and ``failures`` lists of ``(test,
    traceback_text)`` tuples, ``TestResult`` being the production case.
    ``reason`` is the stated expected-failure reason: it is ignored on
    the green path, where no failure exists to match it against, so an
    empty ``reason`` never raises there.

    Behaviour 1 (verdict-green): when both ``errors`` and ``failures``
    are empty the verdict is ``"green"`` and nothing is raised.

    Behaviour 2 (verdict-genuine-red): when ``errors`` is empty and
    ``failures`` is non-empty the verdict is ``"red"`` and nothing is
    raised - a failed assertion is the right kind of red. ``reason`` is
    not yet matched against the failure text (behaviour 4); any reason
    is accepted on this path for now.

    A result carrying ``errors`` is a non-green result the classifier
    does not judge yet - it raises ``VerdictError`` naming the counts,
    until behaviour 3 lands ``"wrong_kind"``.
    """
    if not result.errors and not result.failures:
        return "green"
    if not result.errors:
        return "red"
    raise VerdictError(
        "cannot classify a result carrying errors yet: {} error(s), "
        "{} failure(s); behaviour 3 of plans/pi-phase9-redgreen.md "
        "has not landed".format(len(result.errors), len(result.failures))
    )
