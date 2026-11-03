"""Red/green verdict classifier for one suite run.

One job: classify the result of a single ``unittest`` suite run into a
verdict, and nothing else. This module decides, never acts: it performs
no subprocess, no Docker and no git, and it builds no commit message;
the driver that acts on a verdict lives in ``anvilkit.pi.picycle``. It
reads exactly two attributes of the result, ``errors`` and ``failures``,
so the two kinds of red stay separable the way ``TestResult`` keeps
them apart - the exit code cannot separate them.

At this stage of the red/green cycle only behaviour 1 of
``plans/pi-phase9-redgreen.md`` is implemented: a result with empty
``errors`` and ``failures`` classifies as ``"green"``, and a green
raises nothing, whatever ``reason`` holds, empty included (``reason``
is ignored on the green path, since a green has no failure to match
against). The remaining verdicts - ``"red"`` (behaviour 2),
``"wrong_kind"`` (behaviour 3) and the reason-matching rule
(behaviour 4) - are not implemented yet and each lands in its own
red/green cycle; a non-green result raises ``VerdictError`` until they
do.

Stdlib only. One exception type: ``VerdictError``.
"""

import unittest


class VerdictError(Exception):
    """A verdict the classifier could not give.

    A single exception type covers every classification failure, so
    callers need only one ``except`` clause. Today it names a non-green
    result the classifier has not learned to judge yet (behaviours 2-4);
    behaviour 4 will additionally raise it when a genuine red carries
    an empty reason, since an unstated reason cannot be verified.
    Every message names the offending value, so a failure is fixable
    without reading the source.
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
    are empty the verdict is ``"green"`` and nothing is raised. A
    non-empty ``errors`` or ``failures`` is a non-green result the
    classifier does not judge yet - it raises ``VerdictError`` naming
    the counts, until behaviours 2-4 land their verdicts.
    """
    if not result.errors and not result.failures:
        return "green"
    raise VerdictError(
        "cannot classify a non-green result yet: {} error(s), {} "
        "failure(s); behaviours 2-4 of plans/pi-phase9-redgreen.md "
        "have not landed".format(len(result.errors), len(result.failures))
    )
