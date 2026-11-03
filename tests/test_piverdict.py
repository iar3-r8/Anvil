"""Tests for ``anvilkit.pi.piverdict`` - the red/green verdict classifier.

``plans/pi-phase9-redgreen.md``, behaviour 1 (verdict-green): a suite
result whose ``errors`` and ``failures`` lists are both empty classifies
as ``green``.

The production module ``anvilkit.pi.piverdict`` does not exist yet, so
every test loads it through ``_piverdict`` - the lazy import whose
``ModuleNotFoundError`` is the right reason the suite is red. The import
happens inside each test, not at module top level, so the file still
collects and a failure is a clean per-test error rather than a file-level
collection error.

Pinned signature::

    classify(result, reason) -> str

- ``result``: a ``unittest.TestResult`` (or any object exposing the
  ``errors`` and ``failures`` lists of ``(test, traceback_text)`` tuples
  - ``TestResult.addError`` appends to ``self.errors``, ``addFailure`` to
  ``self.failures``);
- ``reason``: the stated expected-failure reason;
- the verdict is one of ``"green"`` / ``"red"`` / ``"wrong_kind"`` /
  ``"reason_mismatch"``.

Only behaviour 1 is pinned here. Behaviours 2-4 (genuine red,
wrong-kind-of-red, reason-must-match) each get their own red/green cycle
and are not asserted in this file yet.
"""

import importlib
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# A non-empty reason so the green test does not depend on the plan's
# open question of whether an empty ``reason`` raises ``VerdictError``
# on the green path (behaviour 4 pins the empty-reason raise in the
# genuine-red context only). The green verdict must not depend on the
# reason's value: the plan states "Error: none" for behaviour 1.
REASON = "the assertion fails until the production module exists"


class ClassifyGreenTestCase(unittest.TestCase):
    """Shared lazy import of the not-yet-existing ``piverdict`` module.

    The import happens inside each test, not at module top level, so
    that while ``anvilkit/pi/piverdict.py`` does not exist yet the tests
    fail at the import step (``ModuleNotFoundError``) instead of breaking
    collection of the file.
    """

    def _piverdict(self):
        """Import ``anvilkit.pi.piverdict``.

        Fails with the module's own ``ModuleNotFoundError`` - the right
        reason the suite is red - until the classifier exists.
        """
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


if __name__ == "__main__":
    unittest.main()
