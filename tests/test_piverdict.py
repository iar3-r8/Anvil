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

Behaviours 1-2 are pinned here. Behaviours 3-4 (wrong-kind-of-red,
reason-must-match) each get their own red/green cycle and are not asserted
in this file yet.
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


if __name__ == "__main__":
    unittest.main()
