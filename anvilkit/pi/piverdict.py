"""Red/green verdict classifier for one suite run.

One job: classify the result of a single ``unittest`` suite run into a
verdict, and nothing else. This module decides, never acts: it performs
no subprocess, no Docker and no git, and it builds no commit message;
the driver that acts on a verdict lives in ``anvilkit.pi.picycle``. It
reads exactly two attributes of the result, ``errors`` and ``failures``,
so the two kinds of red stay separable the way ``TestResult`` keeps
them apart - the exit code cannot separate them.

At this stage of the red/green cycle behaviours 1-3 of
``plans/pi-phase9-redgreen.md`` are implemented: a result with empty
``errors`` and ``failures`` classifies as ``"green"`` (behaviour 1);
a result carrying ``failures`` but no ``errors`` classifies as
``"red"`` (behaviour 2); and a result carrying a non-empty ``errors``
list classifies as ``"wrong_kind"`` regardless of ``failures``
(behaviour 3) - the check runs before the red check, so an error
outranks a failure and a wrong-kind run with a coincidental assertion
failure can never be misread as a genuine red. A green raises nothing,
whatever ``reason`` holds, empty included (``reason`` is ignored on
the green path, since a green has no failure to match against); a
genuine red also raises nothing at this stage. Only behaviour 4
(verbatim reason-matching on a genuine red, including its empty-reason
``VerdictError``) remains; it lands in its own red/green cycle.

Stdlib only. One exception type: ``VerdictError``.
"""

import unittest


class VerdictError(Exception):
    """A verdict the classifier could not give.

    A single exception type covers every classification failure, so
    callers need only one ``except`` clause. Behaviours 1-3 raise
    nothing - a result carrying ``errors`` classifies as
    ``"wrong_kind"``, never raises. The one raise that remains belongs
    to behaviour 4, not yet implemented: a genuine red carrying an
    empty reason will raise it, since an unstated reason cannot be
    verified. Every message names the offending value, so a failure is
    fixable without reading the source.
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

    Behaviour 3 (verdict-wrong-kind-of-red): when ``errors`` is
    non-empty the verdict is ``"wrong_kind"`` regardless of
    ``failures`` and nothing is raised. The check runs after green and
    before red, so an error outranks a failure - without that priority
    a wrong-kind run with a coincidental assertion failure would
    misclassify as ``"red"`` and poison the history (DoD 5).

    Behaviour 4 (reason-must-match) is not implemented yet; it will
    raise ``VerdictError`` when a genuine red carries an empty reason.
    """
    if not result.errors and not result.failures:
        return "green"
    if result.errors:
        return "wrong_kind"
    return "red"
