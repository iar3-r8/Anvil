"""Red/green verdict classifier for one suite run.

One job: classify the result of a single ``unittest`` suite run into a
verdict, and nothing else. This module decides, never acts: it performs
no subprocess, no Docker and no git, and it builds no commit message;
the driver that acts on a verdict lives in ``anvilkit.pi.picycle``. It
reads exactly two attributes of the result, ``errors`` and ``failures``,
so the two kinds of red stay separable the way ``TestResult`` keeps
them apart - the exit code cannot separate them.

All four behaviours of ``plans/pi-phase9-redgreen.md`` are
implemented: a result with empty ``errors`` and ``failures``
classifies as ``"green"`` (behaviour 1); a result carrying
``failures`` but no ``errors`` is a genuine red (behaviour 2); a
result carrying a non-empty ``errors`` list classifies as
``"wrong_kind"`` regardless of ``failures`` (behaviour 3) - the
check runs before the red check, so an error outranks a failure and
a wrong-kind run with a coincidental assertion failure can never be
misread as a genuine red; and on a genuine red the stated
``reason`` must match the failure text (behaviour 4) - a match
yields ``"red"`` and a mismatch yields ``"reason_mismatch"``,
never ``"red"``. A green raises nothing, whatever ``reason`` holds,
empty included (``reason`` is ignored on the green path, since a
green has no failure to match against). On the genuine-red
matching path only, an empty ``reason`` raises ``VerdictError``:
an unstated reason cannot be verified.

Stdlib only. One exception type: ``VerdictError``.
"""

import unittest


class VerdictError(Exception):
    """A verdict the classifier could not give.

    A single exception type covers every classification failure, so
    callers need only one ``except`` clause. Behaviours 1-3 raise
    nothing - a green is ``"green"``, a mismatch is
    ``"reason_mismatch"`` and a result carrying ``errors`` is
    ``"wrong_kind"``; a mismatch is a verdict, not a failure to
    give. The one raise belongs to behaviour 4: a genuine red
    carrying an empty reason raises it, since an unstated reason
    cannot be verified. Every message names the offending value, so
    a failure is fixable without reading the source.
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
    ``failures`` is non-empty the run is a genuine red - a failed
    assertion is the right kind of red - and the verdict is decided by
    behaviour 4's reason check: a matching ``reason`` yields
    ``"red"``.

    Behaviour 3 (verdict-wrong-kind-of-red): when ``errors`` is
    non-empty the verdict is ``"wrong_kind"`` regardless of
    ``failures`` and nothing is raised. The check runs after green and
    before red, so an error outranks a failure - without that priority
    a wrong-kind run with a coincidental assertion failure would
    misclassify as ``"red"`` and poison the history (DoD 5).

    Behaviour 4 (verdict-reason-must-match), on the genuine-red path
    only: an empty ``reason`` raises ``VerdictError`` naming it, since
    an unstated reason cannot be verified; otherwise the ``reason`` is
    compared against the failure text as a containment check
    (``reason in failure_text`` - a substring of the traceback, no
    regex, no case-folding), matching ANY entry of ``failures``: a
    genuine red with several failures is ``"red"`` when the reason
    appears in at least one entry's traceback text, and
    ``"reason_mismatch"`` otherwise. A mismatch never yields
    ``"red"``.
    """
    if not result.errors and not result.failures:
        return "green"
    if result.errors:
        return "wrong_kind"
    if not reason:
        raise VerdictError("the stated expected-failure reason is empty")
    if any(reason in traceback_text for _, traceback_text in result.failures):
        return "red"
    return "reason_mismatch"
