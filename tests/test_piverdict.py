"""Tests for ``anvilkit.pi.piverdict`` - the red/green verdict classifier.

``plans/pi-phase9-redgreen.md``, behaviour 1 (verdict-green): a suite
result whose ``errors`` and ``failures`` lists are both empty classifies
as ``green``.

The production module exists and behaviour 1 is landed, so tests import
it at module top level (after the ``sys.path`` bootstrap). The behaviour-1
class keeps its original per-test ``_piverdict()`` lazy import, unchanged
from the cycle in which it was written.

Pinned signature::

    classify(result, reason) -> str

- ``result``: a ``unittest.TestResult`` (or any object exposing the
  ``errors`` and ``failures`` lists of ``(test, traceback_text)`` tuples
  - ``TestResult.addError`` appends to ``self.errors``, ``addFailure`` to
  ``self.failures``);
- ``reason``: the stated expected-failure reason;
- the verdict is one of ``"green"`` / ``"red"`` / ``"wrong_kind"`` /
  ``"reason_mismatch"``.

Behaviours 1-3 are pinned here. Behaviour 4 (reason-must-match) gets its
own red/green cycle and is not asserted in this file yet.
"""

import importlib
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import anvilkit.pi.piverdict

# A non-empty reason so the green test does not depend on the plan's
# open question of whether an empty ``reason`` raises ``VerdictError``
# on the green path (behaviour 4 pins the empty-reason raise in the
# genuine-red context only). The green verdict must not depend on the
# reason's value: the plan states "Error: none" for behaviour 1.
REASON = "the assertion fails until the production module exists"

# The exact traceback text of behaviour 2's single failure entry, in the
# shape ``TestResult.addFailure`` produces - ``(test, traceback_text)``.
# It is deterministic by construction (a module constant, not a real run),
# so the test pins it verbatim.
FAILURE_TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "./tests/test_example.py", line 12, in test_example\n'
    "    self.assertEqual(1, 2)\n"
    "AssertionError: 1 != 2\n"
)

# The exact traceback text of behaviour 3's single error entry, in the
# shape ``TestResult.addError`` produces - ``(test, traceback_text)``.
# An import error, one of the plan's three error kinds; the specific kind
# is irrelevant to the verdict. It is deterministic by construction, the
# same way as FAILURE_TRACEBACK.
ERROR_TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "./tests/test_example.py", line 3, in <module>\n'
    "    import missing_module\n"
    "ModuleNotFoundError: No module named 'missing_module'\n"
)


class ClassifyGreenTestCase(unittest.TestCase):
    """Behaviour 1's test class, kept as written during the cycle in
    which ``anvilkit/pi/piverdict.py`` did not yet exist.

    The import happens inside the test (``_piverdict``) rather than at
    module top level, so that while the module did not exist the test
    failed at the import step (``ModuleNotFoundError``) instead of
    breaking collection of the file. The module now exists; the import
    simply succeeds.
    """

    def _piverdict(self):
        """Import ``anvilkit.pi.piverdict``."""
        return importlib.import_module("anvilkit.pi.piverdict")

    def test_classify_empty_errors_and_failures_returns_green(self) -> None:
        # Arrange: a real TestResult whose error and failure lists are
        # both empty - the givens of behaviour 1.
        result = unittest.TestResult()
        self.assertEqual(result.errors, [])
        self.assertEqual(result.failures, [])

        # Act
        piverdict = self._piverdict()
        verdict = piverdict.classify(result, REASON)

        # Assert
        self.assertEqual(verdict, "green")


class ClassifyGenuineRedTestCase(unittest.TestCase):
    """Behaviour 2 (verdict-genuine-red): a result carrying one
    ``failures`` entry and no ``errors`` classifies as ``"red"``.

    The ``reason`` is set to the exact failure traceback text on
    purpose: behaviour 4 (reason-must-match, lands after this one) makes
    a mismatch between ``reason`` and the failure text yield
    ``"reason_mismatch"`` instead of ``"red"``. A matching reason keeps
    this test's ``"red"`` expectation valid for the life of the branch.

    The plan's "Then" also says the entry's traceback text "is carried
    through verbatim"; under the pinned contract ``classify(...) -> str``
    (a bare verdict) that carrying is not observable in ``classify``'s
    return. The natural observable - the red commit message's
    "fails: {assertion}" line - is behaviour 8's, so this test asserts
    only the verdict.
    """

    def test_classify_one_failure_no_errors_returns_red(self) -> None:
        # Arrange: a real TestResult with exactly one failure entry and
        # no errors - the givens of behaviour 2. The entry is the
        # ``(test, traceback_text)`` tuple that addFailure appends; it
        # is built here directly because addFailure renders its text
        # from a live exception tuple and cannot inject a pinned one.
        # classify's contract reads exactly those two lists, so the
        # list is the seam. The entry's first item is the failed test;
        # a sentinel stands in for it.
        result = unittest.TestResult()
        failing_test = object()
        result.failures.append((failing_test, FAILURE_TRACEBACK))
        self.assertEqual(result.errors, [])
        self.assertEqual(result.failures, [(failing_test, FAILURE_TRACEBACK)])

        # Act: reason is the exact failure text, so it cannot drift into
        # behaviour 4's mismatch path.
        verdict = anvilkit.pi.piverdict.classify(result, FAILURE_TRACEBACK)

        # Assert
        self.assertEqual(verdict, "red")


class ClassifyWrongKindTestCase(unittest.TestCase):
    """Behaviour 3 (verdict-wrong-kind-of-red): a result carrying an
    ``errors`` entry (import, collection or syntax) classifies as
    ``"wrong_kind"`` - even when ``failures`` is also non-empty, an
    error outranks a failure. Without that priority a wrong-kind run
    with a coincidental assertion failure would misclassify as
    ``"red"`` and poison the history (DoD 5 of the plan).

    ``reason`` is any non-empty string on this path: the plan's
    "Error: none" means no reason matching is expected for an error, so
    no test here asserts anything about ``reason``. The plan's "the
    verbatim error text is carried for re-delegation" is not
    observable in ``classify``'s return under the pinned contract
    ``classify(...) -> str`` - the carrying surfaces at the picycle
    layer (behaviour 9 returns the verbatim output) - so, as with
    behaviour 2's traceback carrying, this class asserts only the
    verdict.
    """

    REASON = "a non-empty reason that this path does not match"

    def test_classify_one_error_no_failures_returns_wrong_kind(self) -> None:
        # Arrange: a real TestResult with exactly one error entry and no
        # failures - the givens of behaviour 3's first shape. The entry
        # is the ``(test, traceback_text)`` tuple that addError appends;
        # it is built here directly because addError renders its text
        # from a live exception tuple and cannot inject a pinned one.
        # classify's contract reads exactly those two lists, so the
        # list is the seam, the same way as behaviour 2's test.
        result = unittest.TestResult()
        errored_test = object()
        result.errors.append((errored_test, ERROR_TRACEBACK))
        self.assertEqual(result.errors, [(errored_test, ERROR_TRACEBACK)])
        self.assertEqual(result.failures, [])

        # Act
        verdict = anvilkit.pi.piverdict.classify(result, self.REASON)

        # Assert
        self.assertEqual(verdict, "wrong_kind")

    def test_classify_one_error_and_one_failure_returns_wrong_kind(
        self,
    ) -> None:
        # Arrange: a real TestResult carrying an error entry AND a
        # simultaneous failure entry - behaviour 3's priority case.
        # The error must outrank the failure: without the priority rule
        # this result would classify "red" and poison the history.
        result = unittest.TestResult()
        errored_test = object()
        failing_test = object()
        result.errors.append((errored_test, ERROR_TRACEBACK))
        result.failures.append((failing_test, FAILURE_TRACEBACK))
        self.assertEqual(result.errors, [(errored_test, ERROR_TRACEBACK)])
        self.assertEqual(
            result.failures, [(failing_test, FAILURE_TRACEBACK)]
        )

        # Act
        verdict = anvilkit.pi.piverdict.classify(result, self.REASON)

        # Assert: the error outranks the failure.
        self.assertEqual(verdict, "wrong_kind")


if __name__ == "__main__":
    unittest.main()
