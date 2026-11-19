"""Tests for ``anvilkit.pi.runlog`` - behaviours 1 and 2 of ``plans/pi-phase11-runlog.md``.

Written before the implementation (TDD). Every test loads the module through
the deferred import in ``_runlog`` so that, while a behaviour is missing, the
failure is the behaviour's own error at the line under test, not a
collection-time error of the test file.

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

Behaviour 2 (``run-id-defaults``), pinned from the plan:

    new_run_id() -> "run-YYYYMMDD-HHMMSS-<4hex>" with the stamp from the
    module's own ``datetime.now(timezone.utc)`` and the suffix from the
    module's own ``secrets.token_hex(2)`` - never local time, never a
    counter.

The tests define the seam: production must expose patchable module-level
references named ``datetime`` and ``secrets`` in ``anvilkit.pi.runlog``. The
tests patch ``runlog.datetime`` with a stub whose ``now(...)`` returns a
fixed aware-UTC datetime, and ``runlog.secrets`` with a stub whose
``token_hex`` returns a fixed hex string. While ``new_run_id`` has no
defaults, every behaviour-2 test is red at the no-argument call:
``TypeError: new_run_id() missing 2 required positional arguments``.
Behaviour 1 stays green - the defaults are additive and apply only when the
arguments are absent.
"""

import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

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


class _FixedClock:
    """A datetime stand-in whose ``now(...)`` returns a fixed aware-UTC instant.

    ``now`` records each call so a test can pin that the default consulted
    the clock as ``now(timezone.utc)``, and returns a real ``datetime`` so
    ``utcoffset`` and ``strftime`` work on it exactly as on a real clock
    reading.
    """

    def __init__(self, fixed_now):
        self._fixed_now = fixed_now
        self.datetime = datetime
        self.calls = []

    def now(self, tz=None):
        self.calls.append(tz)
        return self._fixed_now


class _FixedEntropy:
    """A secrets stand-in whose ``token_hex(n)`` yields fixed hex strings.

    ``token_hex`` records each call so a test can pin that the default
    consulted the entropy source as ``token_hex(2)``.
    """

    def __init__(self, values):
        self._values = list(values)
        self.calls = []

    def token_hex(self, nbytes):
        self.calls.append(nbytes)
        return self._values.pop(0)


class RunLogDefaultsTestCase(unittest.TestCase):
    """Behaviour 2 (``run-id-defaults``): ``new_run_id()`` with no arguments.

    The defaults are the seam: the stamp must come from the module's own
    ``datetime.now(timezone.utc)`` and the suffix from the module's own
    ``secrets.token_hex(2)``. The tests patch the module-level references
    ``runlog.datetime`` and ``runlog.secrets`` - production must expose them
    under exactly those names for the patch to land.
    """

    DEFAULTS_NOW = datetime(2026, 11, 19, 13, 45, 0, tzinfo=timezone.utc)
    DEFAULTS_ENTROPY = "cafe"
    DEFAULTS_ID = "run-20261119-134500-cafe"

    def _runlog(self):
        from anvilkit.pi import runlog

        return runlog

    def _patched_new_run_id(self, now=DEFAULTS_NOW, entropies=("cafe",)):
        """Fetch ``new_run_id`` with the module's clock and entropy patched.

        Patching the module's own ``datetime`` and ``secrets`` references is
        what makes the test deterministic; ``runlog.datetime`` and
        ``runlog.secrets`` must be the names the defaults resolve through.
        """
        runlog = self._runlog()
        new_run_id = getattr(runlog, "new_run_id", None)
        self.assertTrue(
            callable(new_run_id),
            "anvilkit.pi.runlog.new_run_id is not callable; behaviour 1 "
            "(run-id-format) has not been implemented yet",
        )
        # ``secrets`` does not exist on the module yet - ``create=True``
        # keeps the red at the no-argument call (TypeError) instead of a
        # patch-time AttributeError. The seam is still pinned: the default
        # must *consult* the patched object, or the id will not match.
        clock = _FixedClock(now)
        entropy = _FixedEntropy(entropies)
        clock_patch = mock.patch.object(runlog, "datetime", clock)
        entropy_patch = mock.patch.object(
            runlog, "secrets", entropy, create=True
        )
        return clock, entropy, clock_patch, entropy_patch, new_run_id

    def test_no_arguments_id_built_from_module_clock_and_entropy(self):
        clock, entropy, clock_patch, entropy_patch, new_run_id = (
            self._patched_new_run_id()
        )
        with clock_patch, entropy_patch:
            self.assertEqual(new_run_id(), self.DEFAULTS_ID)
        # The plan's "Then": the stamp comes from datetime.now(timezone.utc)
        # and the suffix from secrets.token_hex(2) - pinned by the exact
        # arguments the defaults passed to the module's own references.
        self.assertEqual(clock.calls, [timezone.utc])
        self.assertEqual(entropy.calls, [2])

    def test_no_arguments_reads_clock_on_every_call_not_a_constant(self):
        # A counter or a captured-at-import value would give identical ids;
        # a local-time clock would not track the patched UTC instant.
        clock, entropy, clock_patch, entropy_patch, new_run_id = (
            self._patched_new_run_id(entropies=("aaaa", "bbbb"))
        )
        with clock_patch, entropy_patch:
            first = new_run_id()
            second = new_run_id()
        self.assertEqual(
            (first, second), ("run-20261119-134500-aaaa", "run-20261119-134500-bbbb")
        )

    def test_no_arguments_stamp_tracks_utc_clock(self):
        # No patching: the stamp must be taken from the real UTC clock within
        # the call's own second. A local-time stamp on a non-UTC host would
        # land outside the [before, after] UTC window; a second-rollover
        # between the two readings is allowed by comparing as UTC datetimes.
        runlog = self._runlog()
        new_run_id = getattr(runlog, "new_run_id", None)
        self.assertTrue(
            callable(new_run_id),
            "anvilkit.pi.runlog.new_run_id is not callable; behaviour 1 "
            "(run-id-format) has not been implemented yet",
        )
        before = datetime.now(timezone.utc)
        run_id = new_run_id()
        after = datetime.now(timezone.utc)
        self.assertRegex(run_id, r"^run-\d{8}-\d{6}-[0-9a-f]{4}$")
        stamp = datetime.strptime(run_id[4:-5], "%Y%m%d-%H%M%S").replace(
            tzinfo=timezone.utc
        )
        self.assertGreaterEqual(
            stamp,
            before,
            "stamp %s predates the call's start %s; the default must come "
            "from datetime.now(timezone.utc), never local time"
            % (stamp.isoformat(), before.isoformat()),
        )
        self.assertLessEqual(
            stamp,
            after,
            "stamp %s postdates the call's end %s" % (stamp.isoformat(), after.isoformat()),
        )

    def test_explicit_arguments_ignoring_defaults_still_behave_as_behaviour_1(self):
        # The defaults are additive: with explicit arguments the function
        # must use exactly what it is given, never the module clock.
        clock, entropy, clock_patch, entropy_patch, new_run_id = (
            self._patched_new_run_id()
        )
        other_now = datetime(2020, 2, 3, 4, 5, 6, tzinfo=timezone.utc)
        with clock_patch, entropy_patch:
            self.assertEqual(
                new_run_id(now=other_now, entropy="dead"),
                "run-20200203-040506-dead",
            )
        # Neither seam may be consulted when both arguments are explicit.
        self.assertEqual(clock.calls, [])
        self.assertEqual(entropy.calls, [])


if __name__ == "__main__":
    unittest.main()
