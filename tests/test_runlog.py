"""Tests for ``anvilkit.pi.runlog`` - behaviour 1 of ``plans/pi-phase11-runlog.md``.

Written before the implementation (TDD). The production module
``anvilkit/pi/runlog.py`` does not exist yet, so every test loads it through
``_runlog``; until the module lands, every test here is red at that import -
``ModuleNotFoundError: No module named 'anvilkit.pi.runlog'`` - which is the
expected red for the first behaviour of a new module, and keeps the failure
reason visible instead of letting a collection-time error mask it.

Behaviour 1 (``run-id-format``), pinned from the plan:

    new_run_id(now=..., entropy=...) -> "run-YYYYMMDD-HHMMSS-<4hex>"

- the id is built from an injected aware-UTC ``datetime`` and a 4-char
  lowercase-hex entropy string, zero-padded throughout - the plan's own
  example pins the exact id ``run-20261119-134500-1a2b``;
- the returned id is a plain ``str``;
- a naive or non-UTC ``now``, or an entropy string that is not exactly
  four lowercase hex chars, raises ``RunLogError`` naming the offending
  value - the message must identify the offending value in either its
  ``str()`` or its ``repr()`` rendering, so a typo is fixable without
  reading the source. The empty entropy string cannot be named in a
  message, so its test pins only that it raises.
"""

import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The aware-UTC instant behaviour 1 uses throughout: the plan's own example,
# so the pinned id is the plan's own example id.
UTC_NOW = datetime(2026, 11, 19, 13, 45, 0, tzinfo=timezone.utc)
ENTROPY = "1a2b"
EXPECTED_ID = "run-20261119-134500-1a2b"

# A datetime with every single-digit field, so any missing zero-pad shows
# up in the id.
SINGLE_DIGIT_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
SINGLE_DIGIT_ID = "run-20260102-030405-beef"

# Every entropy that is not exactly 4 lowercase hex chars.
BAD_ENTROPIES = ("1a2", "1a2b3", "1A2B", "1a2g")


class RunLogTestCase(unittest.TestCase):
    def _runlog(self):
        """Import the module under test.

        While ``anvilkit/pi/runlog.py`` does not exist yet, this line is the
        red: every test fails here with the import error of the missing
        module, not with a collection error of the test file.
        """
        from anvilkit.pi import runlog

        return runlog

    def _new_run_id(self):
        """Fetch ``anvilkit.pi.runlog.new_run_id``."""
        runlog = self._runlog()
        new_run_id = getattr(runlog, "new_run_id", None)
        self.assertTrue(
            callable(new_run_id),
            "anvilkit.pi.runlog.new_run_id is not callable; behaviour 1 "
            "(run-id-format) has not been implemented yet",
        )
        return new_run_id

    def _run_log_error(self):
        """Fetch ``anvilkit.pi.runlog.RunLogError``."""
        runlog = self._runlog()
        run_log_error = getattr(runlog, "RunLogError", None)
        self.assertTrue(
            isinstance(run_log_error, type)
            and issubclass(run_log_error, Exception),
            "anvilkit.pi.runlog.RunLogError is not an exception type; "
            "behaviour 1 (run-id-format) has not been implemented yet",
        )
        return run_log_error

    @staticmethod
    def _value_pattern(value):
        """A regex matching a message that names ``value``.

        The offending value may be rendered into the message by ``str()``
        or by ``repr()``; both spellings are accepted so the pin holds on
        the contract (the value is named) without dictating the rendering.
        """
        return "|".join(
            re.escape(rendered) for rendered in (str(value), repr(value))
        )

    def test_new_run_id_aware_utc_returns_pinned_id(self):
        new_run_id = self._new_run_id()
        self.assertEqual(new_run_id(now=UTC_NOW, entropy=ENTROPY), EXPECTED_ID)

    def test_new_run_id_single_digit_fields_zero_padded(self):
        new_run_id = self._new_run_id()
        self.assertEqual(
            new_run_id(now=SINGLE_DIGIT_NOW, entropy="beef"),
            SINGLE_DIGIT_ID,
        )

    def test_new_run_id_returns_plain_str(self):
        new_run_id = self._new_run_id()
        run_id = new_run_id(now=UTC_NOW, entropy=ENTROPY)
        self.assertIs(type(run_id), str)

    def test_new_run_id_naive_now_raises_naming_value(self):
        new_run_id = self._new_run_id()
        run_log_error = self._run_log_error()
        naive_now = datetime(2026, 11, 19, 13, 45, 0)
        with self.assertRaisesRegex(
            run_log_error, self._value_pattern(naive_now)
        ):
            new_run_id(now=naive_now, entropy=ENTROPY)

    def test_new_run_id_non_utc_now_raises_naming_value(self):
        new_run_id = self._new_run_id()
        run_log_error = self._run_log_error()
        non_utc_now = datetime(
            2026, 11, 19, 13, 45, 0, tzinfo=timezone(timedelta(hours=2))
        )
        with self.assertRaisesRegex(
            run_log_error, self._value_pattern(non_utc_now)
        ):
            new_run_id(now=non_utc_now, entropy=ENTROPY)

    def test_new_run_id_bad_entropy_raises_naming_value(self):
        new_run_id = self._new_run_id()
        run_log_error = self._run_log_error()
        for entropy in BAD_ENTROPIES:
            with self.subTest(entropy=entropy):
                with self.assertRaisesRegex(
                    run_log_error, self._value_pattern(entropy)
                ):
                    new_run_id(now=UTC_NOW, entropy=entropy)

    def test_new_run_id_empty_entropy_raises(self):
        new_run_id = self._new_run_id()
        run_log_error = self._run_log_error()
        with self.assertRaises(run_log_error):
            new_run_id(now=UTC_NOW, entropy="")


if __name__ == "__main__":
    unittest.main()
