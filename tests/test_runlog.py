"""Tests for ``anvilkit.pi.runlog`` - behaviours 1-8 of ``plans/pi-phase11-runlog.md``.

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

Behaviour 3 (``session-id-derivation``), pinned from the plan:

    session_id(run_id, role) -> "<run-id>-<role>"

- the plan's own example pins the exact id
  ``run-20261119-134500-1a2b-coder``, and one pin per role of
  ``pirole.ROLES`` (architect, coder, tester, docs) pins ``<run-id>-<role>``;
- the result is a plain ``str``;
- the run id crosses through verbatim: the behaviour specifies no
  validation of the run id, so a syntactically valid string that is not
  an id ``new_run_id`` would produce still just gets the role appended,
  with no exception;
- a role outside ``pirole.ROLES`` - including the empty string, which
  cannot be named in a message - raises ``RunLogError``; the non-empty
  case must name the offending role and list all four known roles.

While ``session_id`` is absent, every behaviour-3 test is red at the
fetch step: the module attribute is not callable.

Behaviour 4 (``[PIN] derived-ids-valid-for-pi``) is a green-now boundary
pin with no production change: it locks the seam between ``runlog`` and
``pirole``. For a run id built by ``new_run_id`` (behaviour 1) and each of
the four ``pirole.ROLES``, the derived id ``session_id(run_id, role)``
(behaviour 3) must pass ``pirole._validate_session_id`` and reach
``pirole.role_argv``'s returned argv byte-identical, in the exact
``["--session-id", <id>]`` adjacency. If the id format or the derivation
ever drifts in a way that breaks Pi's session-id rule, the pin fails.

Behaviour 5 (``archive-gitignored``), pinned from the plan:

    Given: the repository ``.gitignore``. When: it is read. Then: an
    explicit ``logs/runs/`` line is present, ``logs/stress-*.log`` stays
    covered by ``*.log``, and no new pattern ignores ``.pi/`` or
    ``.pi/roles/``. Error: a missing ``logs/runs/`` line fails naming it -
    ``*.log`` does not cover ``.jsonl``, ``.patch`` or ``.json`` archive
    members, so without it a run's prompts and tool output become
    committable.

The ``logs/runs/`` pin is red now - the committed ``.gitignore`` has no
such line - and green once the run-log archive directory is added. The
other two pins are green-now guards: they keep the stress writer's
``*.log`` coverage and keep the rendered role prompts in ``.pi/``
committable. The ``.pi`` guard flags an ignore line whose stripped form
is exactly ``.pi``, ``.pi/`` or ``.pi/*``, or that starts with ``.pi/``
(which also covers ``.pi/roles/``); comment and negation lines are not
ignore patterns and are not flagged.

Behaviour 6 (``start-run-writes-meta``), pinned from the plan:

    start_run(root, run_id, intake, sessions, started_at) -> Path

- creates ``root/logs/runs/<run-id>/``, returns it as a ``pathlib.Path``,
  and writes ``meta.json`` with exactly seven keys - ``run_id``,
  ``started_at``, ``finished_at`` (``None``), ``intake`` (``{"issue",
  "text"}``), ``sessions``, ``outcome`` (``"unknown"``) and ``complete``
  (``False``) - the key set is pinned by sorted-key-list equality so no
  extra key can sneak in;
- the file is JSON-native: it round-trips through
  ``json.loads(json.dumps(meta, sort_keys=True))`` unchanged, so a run
  that dies next is still readable;
- an empty ``sessions`` map is allowed and is written as ``{}``;
- an ``intake`` whose key set is not exactly ``{"issue", "text"}`` -
  missing a key, carrying an extra key, or not a dict at all - raises
  ``RunLogError`` naming ``intake``; a ``sessions`` map holding a role
  outside ``pirole.ROLES``, or a ``sessions`` that is not a dict, raises
  naming the offending role or ``sessions``; a ``started_at`` that is
  not a string raises naming ``started_at``;
- on an error nothing is written: the run directory either does not
  exist or holds no ``meta.json`` - the pin is meaningful because it
  fails on a write-then-validate implementation.

While ``start_run`` is absent, every behaviour-6 test is red at the
fetch step: the module attribute is not callable.

Behaviour 7 (``start-run-refuses-overwrite``), pinned from the plan:

    start_run(root, run_id, intake, sessions, started_at) with an existing
    logs/runs/<run-id>/ -> RunLogError naming the run id

- a second ``start_run`` with the same run id raises ``RunLogError`` naming
  the run id - a past run is evidence and is never overwritten;
- nothing on disk is touched: the original ``meta.json`` is intact
  (full-dict equality, not file existence) and no file under the root is
  added, removed or rewritten. The refused call deliberately carries
  different valid inputs, so an overwriting implementation is caught by the
  comparison rather than passing it invisibly;
- a different run id in the same root succeeds while the first run's
  directory and meta are untouched - no cross-run interference.

The setup opens a real run through the genuine ``start_run`` (behaviour 6),
so the archive being refused is a real on-disk run. While the refusal is
unimplemented, the two refusal tests are red at the second call: the current
``start_run`` uses ``exist_ok=True`` and silently rewrites ``meta.json``.
"""

import json
import re
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit.pi import pirole

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
            before.replace(microsecond=0),
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


class RunLogSessionIdTestCase(unittest.TestCase):
    """Behaviour 3 (``session-id-derivation``): ``session_id(run_id, role)``.

    The plan pins the return value as ``<run-id>-<role>`` and says nothing
    about re-validating the run id, so these tests pin the verbatim
    reading: the run id crosses through unchanged - even a syntactically
    valid string ``new_run_id`` would never produce - and only the role
    is checked, against ``pirole.ROLES``.

    While ``session_id`` is absent, every test here is red at the fetch
    step (``_session_id``): the module attribute is not callable, and the
    red is that missing behaviour, not a collection error of this file.
    """

    RUN_ID = EXPECTED_ID

    def _runlog(self):
        from anvilkit.pi import runlog

        return runlog

    def _session_id(self):
        """Fetch ``anvilkit.pi.runlog.session_id``."""
        runlog = self._runlog()
        session_id = getattr(runlog, "session_id", None)
        self.assertTrue(
            callable(session_id),
            "anvilkit.pi.runlog.session_id is not callable; behaviour 3 "
            "(session-id-derivation) has not been implemented yet",
        )
        return session_id

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
    def _naming_and_listing_pattern(offender):
        """A regex pinning a message that names ``offender`` and the roles.

        ``re.search`` finds a match at any position, and a lookahead
        asserts each name appears somewhere in the message, so the pin
        holds on the contract - the offending role is named, and all
        four known roles are listed - without dictating word order or
        rendering.
        """
        return "".join(
            "(?=.*" + re.escape(name) + ")" for name in (offender,) + pirole.ROLES
        )

    def test_session_id_plan_example_pinned(self):
        session_id = self._session_id()
        self.assertEqual(
            session_id(self.RUN_ID, "coder"), "run-20261119-134500-1a2b-coder"
        )

    def test_session_id_one_pin_per_known_role(self):
        session_id = self._session_id()
        for role in pirole.ROLES:
            with self.subTest(role=role):
                self.assertEqual(
                    session_id(self.RUN_ID, role), self.RUN_ID + "-" + role
                )

    def test_session_id_returns_plain_str(self):
        session_id = self._session_id()
        session = session_id(self.RUN_ID, "coder")
        self.assertIs(type(session), str)

    def test_session_id_run_id_crosses_through_verbatim(self):
        # A syntactically valid Pi session-id string that no run id is
        # (the entropy block is not 4 lowercase hex chars): the plan
        # specifies no validation of the run id, so the role is simply
        # appended and no exception is raised.
        session_id = self._session_id()
        foreign_run_id = "run-19991231-235959-ZZZZ"
        self.assertEqual(
            session_id(foreign_run_id, "coder"), foreign_run_id + "-coder"
        )

    def test_session_id_unknown_role_raises_naming_role_and_listing_known_roles(self):
        session_id = self._session_id()
        run_log_error = self._run_log_error()
        with self.assertRaisesRegex(
            run_log_error, self._naming_and_listing_pattern("reviewer")
        ):
            session_id(self.RUN_ID, "reviewer")

    def test_session_id_empty_role_raises(self):
        session_id = self._session_id()
        run_log_error = self._run_log_error()
        with self.assertRaises(run_log_error):
            session_id(self.RUN_ID, "")


class RunLogDerivedIdPinTestCase(unittest.TestCase):
    """Behaviour 4 (``[PIN] derived-ids-valid-for-pi``): a green-now boundary pin.

    No production change. This pins the seam between ``runlog`` and
    ``pirole``: for a run id from behaviour 1 and each of the four
    ``pirole.ROLES``, the derived session id from behaviour 3 must

    - pass ``pirole._validate_session_id`` - called directly, so a drift
      in the id format is caught at Pi's own validation rule, not only at
      argv build time;
    - reach ``pirole.role_argv``'s returned argv byte-identical, in the
      exact ``["--session-id", <id>]`` adjacency - pinned by index, not
      membership, so an id that ``role_argv`` rewrote or reordered fails.

    If any pin is red at the committed state, that is a real defect in
    behaviours 1-3, not in this pin.
    """

    CODE_MODEL_ID = "coder-model"
    FRONTIER_MODEL_ID = "frontier-model"
    TASK = "task"

    # The second fixed instant uses a different entropy from the
    # canonical pin, so the character set exercised includes digits in
    # the stamp and the entropy block of the derived ids.
    SECOND_ENTROPY = "0f1e"

    def _runlog(self):
        from anvilkit.pi import runlog

        return runlog

    def _id_functions(self):
        """Fetch ``new_run_id`` and ``session_id`` from the module under test."""
        runlog = self._runlog()
        new_run_id = getattr(runlog, "new_run_id", None)
        session_id = getattr(runlog, "session_id", None)
        self.assertTrue(
            callable(new_run_id),
            "anvilkit.pi.runlog.new_run_id is not callable; behaviour 1 "
            "(run-id-format) has not been implemented yet",
        )
        self.assertTrue(
            callable(session_id),
            "anvilkit.pi.runlog.session_id is not callable; behaviour 3 "
            "(session-id-derivation) has not been implemented yet",
        )
        return new_run_id, session_id

    def _assert_session_id_adjacency(self, argv, derived_id):
        """Pin the exact ``["--session-id", <id>]`` adjacency by index."""
        flags = [i for i, token in enumerate(argv) if token == "--session-id"]
        self.assertEqual(
            len(flags),
            1,
            "expected exactly one --session-id token in argv %r" % (argv,),
        )
        i = flags[0]
        self.assertEqual(
            argv[i : i + 2],
            ["--session-id", derived_id],
            "derived id %r did not reach the argv byte-identical: %r"
            % (derived_id, argv[i : i + 2]),
        )

    def _pin_run_id(self, now, entropy):
        """Run both seams for every role under one fixed run id."""
        new_run_id, session_id = self._id_functions()
        run_id = new_run_id(now=now, entropy=entropy)
        for role in pirole.ROLES:
            with self.subTest(role=role, run_id=run_id):
                derived_id = session_id(run_id, role)
                # Seam 1: Pi's own session-id rule accepts the derived id.
                pirole._validate_session_id(derived_id)
                # Seam 2: the id reaches role_argv's output byte-identical.
                definition = pirole.resolve(
                    role, self.CODE_MODEL_ID, self.FRONTIER_MODEL_ID
                )
                argv = pirole.role_argv(definition, derived_id, self.TASK)
                self._assert_session_id_adjacency(argv, derived_id)

    def test_canonical_run_id_each_role_passes_validation_and_reaches_argv(self):
        # The plan's own example run id, run-20261119-134500-1a2b.
        self._pin_run_id(UTC_NOW, ENTROPY)

    def test_single_digit_run_id_each_role_passes_validation_and_reaches_argv(self):
        # Single-digit fields in the stamp and a different entropy, so the
        # derived ids exercise digits inside the id, not only in the middle.
        self._pin_run_id(SINGLE_DIGIT_NOW, self.SECOND_ENTROPY)


class RunLogGitignorePinTestCase(unittest.TestCase):
    """Behaviour 5 (``archive-gitignored``): pins the repository ``.gitignore``.

    Red now: the committed ``.gitignore`` has no ``logs/runs/`` line, so
    the archive's ``.jsonl``, ``.patch`` and ``.json`` members would be
    committable. The two green-now guards keep the stress writer's
    ``*.log`` coverage and keep ``.pi/`` (including ``.pi/roles/``)
    committable.
    """

    RUNS_LINE = "logs/runs/"
    LOG_LINE = "*.log"
    PI_PREFIX = ".pi/"

    @staticmethod
    def _gitignore_lines():
        """The repository ``.gitignore`` as a list of stripped lines."""
        gitignore = REPO_ROOT / ".gitignore"
        lines = gitignore.read_text(encoding="utf-8").splitlines()
        return [line.strip() for line in lines]

    @classmethod
    def _ignore_lines(cls):
        """Only the lines that are ignore patterns.

        Blank lines, comment lines (``#``) and negation lines (``!``)
        are not ignore patterns; a negation like ``!.pi/foo`` re-includes
        rather than ignores, so none of them may trip the ``.pi`` guard.
        """
        return [
            line
            for line in cls._gitignore_lines()
            if line
            and not line.startswith("#")
            and not line.startswith("!")
        ]

    def test_gitignore_present(self):
        self.assertTrue(
            (REPO_ROOT / ".gitignore").is_file(),
            "the repository .gitignore is missing; behaviour 5 "
            "(archive-gitignored) cannot be pinned without it",
        )

    def test_logs_runs_line_present(self):
        # The primary pin: red until the archive directory is ignored.
        lines = self._gitignore_lines()
        self.assertIn(
            self.RUNS_LINE,
            lines,
            ".gitignore is missing the explicit %r line; *.log does not "
            "cover the .jsonl, .patch or .json members of logs/runs/, so "
            "a run's prompts and tool output would become committable"
            % self.RUNS_LINE,
        )

    def test_star_log_line_still_present(self):
        # Green-now guard: logs/stress-*.log stays covered by *.log.
        lines = self._gitignore_lines()
        self.assertIn(
            self.LOG_LINE,
            lines,
            ".gitignore lost the %r line; the stress writer's "
            "logs/stress-*.log files would no longer be ignored"
            % self.LOG_LINE,
        )

    def test_no_pattern_ignores_pi(self):
        # Green-now guard: rendered role prompts in .pi/ stay committable.
        # Flags a line whose stripped form is exactly .pi, .pi/ or .pi/*,
        # or that starts with .pi/ (which also covers .pi/roles/).
        offenders = [
            line
            for line in self._ignore_lines()
            if line in (".pi", ".pi/", ".pi/*")
            or line.startswith(self.PI_PREFIX)
        ]
        self.assertEqual(
            offenders,
            [],
            ".gitignore ignores .pi/ or .pi/roles/ via the over-broad "
            "pattern(s) %r; the rendered role prompts under .pi/ must "
            "stay committable" % (offenders,),
        )


class RunLogStartRunTestCase(unittest.TestCase):
    """Behaviour 6 (``start-run-writes-meta``): ``start_run`` writes the archive.

    The plan's discipline is that a run that dies mid-way leaves a readable
    archive, so ``meta.json`` exists from the start with ``finished_at``
    null, ``outcome`` unknown and ``complete`` false. These tests pin the
    seven-key shape exactly, the JSON-native round-trip, the empty-sessions
    allowance, every error path naming its field, and that a validation
    error writes nothing.

    While ``start_run`` is absent, every test here is red at the fetch
    step (``_start_run``): the module attribute is not callable, and the
    red is that missing behaviour, not a collection error of this file.
    """

    RUN_ID = EXPECTED_ID
    STARTED_AT = "2026-11-19T13:45:00Z"
    INTAKE = {"issue": 58, "text": "task body"}
    SESSIONS = {"coder": "run-20261119-134500-1a2b-coder"}
    META_KEYS = sorted(
        [
            "run_id",
            "started_at",
            "finished_at",
            "intake",
            "sessions",
            "outcome",
            "complete",
        ]
    )

    def _runlog(self):
        from anvilkit.pi import runlog

        return runlog

    def _start_run(self):
        """Fetch ``anvilkit.pi.runlog.start_run``."""
        runlog = self._runlog()
        start_run = getattr(runlog, "start_run", None)
        self.assertTrue(
            callable(start_run),
            "anvilkit.pi.runlog.start_run is not callable; behaviour 6 "
            "(start-run-writes-meta) has not been implemented yet",
        )
        return start_run

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

    def _start(self, root, intake=None, sessions=None, started_at=None):
        """Call ``start_run`` with the canonical pins unless overridden."""
        return self._start_run()(
            root,
            self.RUN_ID,
            self.INTAKE if intake is None else intake,
            self.SESSIONS if sessions is None else sessions,
            self.STARTED_AT if started_at is None else started_at,
        )

    def _read_meta(self, root):
        """The parsed ``meta.json`` of the run directory under ``root``."""
        meta_path = root / "logs" / "runs" / self.RUN_ID / "meta.json"
        return json.loads(meta_path.read_text(encoding="utf-8"))

    def test_start_run_creates_run_dir_returns_path_writes_seven_key_meta(self):
        self._start_run()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._start(root)
            self.assertIsInstance(run_dir, Path)
            self.assertEqual(run_dir, root / "logs" / "runs" / self.RUN_ID)
            self.assertTrue(run_dir.is_dir())
            self.assertTrue((run_dir / "meta.json").is_file())
            meta = self._read_meta(root)
            self.assertEqual(
                sorted(meta),
                self.META_KEYS,
                "meta.json key set must be exactly the seven planned keys; "
                "got %r" % (sorted(meta),),
            )
            self.assertEqual(meta["run_id"], self.RUN_ID)
            self.assertEqual(meta["started_at"], self.STARTED_AT)
            self.assertIsNone(meta["finished_at"])
            self.assertEqual(meta["intake"], self.INTAKE)
            self.assertEqual(meta["sessions"], self.SESSIONS)
            self.assertEqual(meta["outcome"], "unknown")
            self.assertIs(meta["complete"], False)

    def test_start_run_meta_json_round_trips(self):
        # JSON-native: a run that dies next is still readable, which holds
        # only if the file round-trips through a dump/load unchanged.
        self._start_run()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._start(root)
            meta = self._read_meta(root)
            self.assertEqual(
                json.loads(json.dumps(meta, sort_keys=True)),
                meta,
                "meta.json is not JSON-native: it changed on round-trip",
            )

    def test_start_run_empty_sessions_map_allowed_and_written_as_empty_dict(self):
        self._start_run()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._start(root, sessions={})
            self.assertTrue(run_dir.is_dir())
            self.assertEqual(self._read_meta(root)["sessions"], {})

    def _assert_bad_intake(self, intake):
        run_log_error = self._run_log_error()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(run_log_error, "intake"):
                self._start(root, intake=intake)

    def test_start_run_intake_missing_key_raises_naming_intake(self):
        self._start_run()
        self._assert_bad_intake({"issue": 58})

    def test_start_run_intake_extra_key_raises_naming_intake(self):
        self._start_run()
        self._assert_bad_intake({"issue": 58, "text": "task body", "extra": 1})

    def test_start_run_intake_not_a_dict_raises_naming_intake(self):
        self._start_run()
        self._assert_bad_intake("task body")

    def test_start_run_sessions_unknown_role_raises_naming_role_or_sessions(self):
        self._start_run()
        run_log_error = self._run_log_error()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad_sessions = dict(self.SESSIONS)
            bad_sessions["reviewer"] = self.RUN_ID + "-reviewer"
            with self.assertRaisesRegex(run_log_error, "reviewer|sessions"):
                self._start(root, sessions=bad_sessions)

    def test_start_run_sessions_not_a_dict_raises_naming_sessions(self):
        self._start_run()
        run_log_error = self._run_log_error()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(run_log_error, "sessions"):
                self._start(root, sessions=[("coder", self.RUN_ID + "-coder")])

    def test_start_run_started_at_not_a_string_raises_naming_started_at(self):
        self._start_run()
        run_log_error = self._run_log_error()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(run_log_error, "started_at"):
                self._start(root, started_at=12345)

    def test_start_run_bad_intake_writes_nothing(self):
        # Validate-then-write discipline: a rejected intake must leave no
        # meta.json behind. The pin allows the directory to be absent (the
        # expected case) or to exist without meta.json; it fails on a
        # write-then-validate implementation, which would leave a
        # half-recorded run.
        self._start_run()
        run_log_error = self._run_log_error()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(run_log_error):
                self._start(root, intake={"issue": 58})
            run_dir = root / "logs" / "runs" / self.RUN_ID
            self.assertTrue(
                not run_dir.exists() or not (run_dir / "meta.json").exists(),
                "start_run wrote to %s despite a validation error; a run "
                "that failed intake must not be half-recorded" % run_dir,
            )


class RunLogOverwriteRefusalTestCase(unittest.TestCase):
    """Behaviour 7 (``start-run-refuses-overwrite``): an existing archive is
    never overwritten.

    The plan pins: given a ``logs/runs/<run-id>/`` that already exists,
    ``start_run`` called with that id touches nothing on disk and raises
    ``RunLogError`` naming the run id - a past run is evidence.

    The setup opens a real run through the genuine ``start_run`` (behaviour
    6), so the archive being refused is a real on-disk run, not a hand-built
    directory. The refused call deliberately carries different valid inputs:
    an implementation that overwrites would leave those new values in
    ``meta.json`` and be caught by the full-dict comparison - with identical
    inputs the overwrite would pass the pin invisibly.

    While the refusal is unimplemented, the two refusal tests are red at the
    second call: ``start_run`` currently succeeds with ``exist_ok=True`` and
    silently rewrites ``meta.json``. The cross-run test is a green-now guard
    against a refusal that would lock the whole ``logs/runs/`` tree.
    """

    RUN_ID = EXPECTED_ID
    OTHER_RUN_ID = "run-20261119-134501-2b3c"
    STARTED_AT = "2026-11-19T13:45:00Z"
    INTAKE = {"issue": 58, "text": "task body"}
    SESSIONS = {"coder": "run-20261119-134500-1a2b-coder"}

    # Deliberately different valid inputs for the refused second call.
    NEW_STARTED_AT = "2026-11-19T14:00:00Z"
    NEW_INTAKE = {"issue": 59, "text": "a later task"}
    NEW_SESSIONS = {"coder": "run-20261119-134500-1a2b-coder"}

    OTHER_STARTED_AT = "2026-11-19T13:45:01Z"
    OTHER_INTAKE = {"issue": 60, "text": "another task"}
    OTHER_SESSIONS = {"coder": "run-20261119-134501-2b3c-coder"}

    def _runlog(self):
        from anvilkit.pi import runlog

        return runlog

    def _start_run(self):
        """Fetch ``anvilkit.pi.runlog.start_run``."""
        runlog = self._runlog()
        start_run = getattr(runlog, "start_run", None)
        self.assertTrue(
            callable(start_run),
            "anvilkit.pi.runlog.start_run is not callable; behaviour 6 "
            "(start-run-writes-meta) has not been implemented yet",
        )
        return start_run

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

    def _seed_run(self, root):
        """Open a real run with valid inputs so its archive exists on disk."""
        start_run = self._start_run()
        start_run(
            root, self.RUN_ID, self.INTAKE, self.SESSIONS, self.STARTED_AT
        )

    @staticmethod
    def _read_meta(root, run_id):
        """The parsed ``meta.json`` of run ``run_id`` under ``root``."""
        meta_path = root / "logs" / "runs" / run_id / "meta.json"
        return json.loads(meta_path.read_text(encoding="utf-8"))

    @staticmethod
    def _tree(root):
        """Every file under ``root`` as sorted relative POSIX paths.

        A snapshot of the whole tree, so "nothing on disk is touched" is
        pinned in full: the meta comparison catches an in-place rewrite, and
        the tree snapshot catches a file added or removed anywhere under the
        root.
        """
        return sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file()
        )

    def test_start_run_existing_run_id_raises_naming_run_id(self):
        start_run = self._start_run()
        run_log_error = self._run_log_error()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_run(root)
            with self.assertRaisesRegex(run_log_error, re.escape(self.RUN_ID)):
                start_run(
                    root,
                    self.RUN_ID,
                    self.NEW_INTAKE,
                    self.NEW_SESSIONS,
                    self.NEW_STARTED_AT,
                )

    def test_start_run_existing_run_id_touches_nothing_on_disk(self):
        start_run = self._start_run()
        run_log_error = self._run_log_error()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_run(root)
            original_meta = self._read_meta(root, self.RUN_ID)
            before_tree = self._tree(root)
            with self.assertRaises(run_log_error):
                start_run(
                    root,
                    self.RUN_ID,
                    self.NEW_INTAKE,
                    self.NEW_SESSIONS,
                    self.NEW_STARTED_AT,
                )
            self.assertEqual(
                self._read_meta(root, self.RUN_ID),
                original_meta,
                "start_run rewrote the existing run's meta.json; a past "
                "run is evidence and must never be overwritten",
            )
            self.assertEqual(
                self._tree(root),
                before_tree,
                "start_run changed files on disk while refusing an "
                "existing run; nothing may be touched",
            )

    def test_start_run_different_run_id_succeeds_and_first_run_untouched(self):
        start_run = self._start_run()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_run(root)
            original_meta = self._read_meta(root, self.RUN_ID)
            second_dir = start_run(
                root,
                self.OTHER_RUN_ID,
                self.OTHER_INTAKE,
                self.OTHER_SESSIONS,
                self.OTHER_STARTED_AT,
            )
            first_dir = root / "logs" / "runs" / self.RUN_ID
            self.assertIsInstance(second_dir, Path)
            self.assertEqual(
                second_dir, root / "logs" / "runs" / self.OTHER_RUN_ID
            )
            self.assertTrue(second_dir.is_dir())
            self.assertNotEqual(first_dir, second_dir)
            # The first run is untouched: its directory still exists and its
            # meta is the original, whole.
            self.assertTrue(first_dir.is_dir())
            self.assertEqual(
                self._read_meta(root, self.RUN_ID),
                original_meta,
                "opening a second run in the same root disturbed the first "
                "run's archive",
            )
    
    
class RunLogWriteStreamTestCase(unittest.TestCase):
    """Behaviour 8 (``write-stream-verbatim``): ``write_stream(run_dir, role, text)``.

    The plan pins: given a run directory, a role and the driver's captured
    ``result["stdout"]``, ``<role>.jsonl`` holds the text byte-for-byte. An
    empty stream writes an empty file, and an unparseable stream is kept
    unchanged - those are the runs worth reading, so this module never parses
    or rewrites a stream. An unknown role raises ``RunLogError`` naming it;
    a missing run directory raises naming the path.

    The happy-path setup opens a real run through the genuine ``start_run``
    (behaviour 6), so the run directory being written is a real on-disk run
    directory, not a hand-built stand-in. While ``write_stream`` is absent,
    every test here is red at the fetch step (``_write_stream``): the module
    attribute is not callable, and the red is that missing behaviour, not a
    collection error of this file.
    """

    RUN_ID = EXPECTED_ID
    STARTED_AT = "2026-11-19T13:45:00Z"
    INTAKE = {"issue": 58, "text": "task body"}
    SESSIONS = {"coder": "run-20261119-134500-1a2b-coder"}

    # A realistic multi-line JSONL stream, in the shape of the driver's
    # captured result["stdout"]: content is data, never parsed.
    STREAM = (
        '{"type": "session", "version": 3, '
        '"id": "9f1c7a42-6e3d-4b8a-9c2f-7d5e8a1b3c4d", '
        '"timestamp": "2026-11-19T13:45:00.000Z", "cwd": "/workspace"}\n'
        '{"type": "agent_start"}\n'
        '{"type": "agent_end", "messages": [], "willRetry": false}\n'
        '{"type": "agent_settled", "aborted": false}\n'
    )

    def _runlog(self):
        from anvilkit.pi import runlog

        return runlog

    def _write_stream(self):
        """Fetch ``anvilkit.pi.runlog.write_stream``."""
        runlog = self._runlog()
        write_stream = getattr(runlog, "write_stream", None)
        self.assertTrue(
            callable(write_stream),
            "anvilkit.pi.runlog.write_stream is not callable; behaviour 8 "
            "(write-stream-verbatim) has not been implemented yet",
        )
        return write_stream

    def _start_run(self):
        """Fetch ``anvilkit.pi.runlog.start_run``."""
        runlog = self._runlog()
        start_run = getattr(runlog, "start_run", None)
        self.assertTrue(
            callable(start_run),
            "anvilkit.pi.runlog.start_run is not callable; behaviour 6 "
            "(start-run-writes-meta) has not been implemented yet",
        )
        return start_run

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

    def _seed_run_dir(self, root):
        """Open a real run through ``start_run`` and return its run directory."""
        return self._start_run()(
            root, self.RUN_ID, self.INTAKE, self.SESSIONS, self.STARTED_AT
        )

    @staticmethod
    def _read_text(path):
        """The file's exact bytes decoded as UTF-8, for byte-for-byte pins."""
        return path.read_bytes().decode("utf-8")

    def test_write_stream_coder_multiline_jsonl_written_verbatim(self):
        self._write_stream()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._seed_run_dir(root)
            self._write_stream()(run_dir, "coder", self.STREAM)
            stream_path = run_dir / "coder.jsonl"
            self.assertTrue(
                stream_path.is_file(),
                "write_stream did not create %s" % stream_path,
            )
            self.assertEqual(
                self._read_text(stream_path),
                self.STREAM,
                "coder.jsonl does not hold the captured stream byte-for-byte",
            )

    def test_write_stream_trailing_newline_round_trips_exactly(self):
        self._write_stream()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._seed_run_dir(root)
            with_trailing = '{"type": "agent_start"}\n{"type": "agent_end"}\n'
            self._write_stream()(run_dir, "tester", with_trailing)
            self.assertEqual(
                self._read_text(run_dir / "tester.jsonl"),
                with_trailing,
                "a stream with a trailing newline was rewritten; the "
                "written bytes must equal the input exactly",
            )

    def test_write_stream_no_trailing_newline_round_trips_exactly(self):
        self._write_stream()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._seed_run_dir(root)
            no_trailing = '{"type": "agent_start"}\n{"type": "agent_end"}'
            self._write_stream()(run_dir, "docs", no_trailing)
            self.assertEqual(
                self._read_text(run_dir / "docs.jsonl"),
                no_trailing,
                "a stream without a trailing newline was rewritten; the "
                "written bytes must equal the input exactly",
            )

    def test_write_stream_empty_stream_writes_empty_file(self):
        self._write_stream()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._seed_run_dir(root)
            self._write_stream()(run_dir, "tester", "")
            stream_path = run_dir / "tester.jsonl"
            self.assertTrue(
                stream_path.is_file(),
                "write_stream did not create %s for an empty stream; an "
                "empty stream is data (a run that produced nothing)"
                % stream_path,
            )
            self.assertEqual(stream_path.stat().st_size, 0)
            self.assertEqual(self._read_text(stream_path), "")

    def test_write_stream_unparseable_stream_kept_unchanged(self):
        self._write_stream()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._seed_run_dir(root)
            unparseable = "not json at all\n\ncut off {"
            self._write_stream()(run_dir, "docs", unparseable)
            self.assertEqual(
                self._read_text(run_dir / "docs.jsonl"),
                unparseable,
                "an unparseable stream was modified; this module must keep "
                "the captured bytes unchanged - those are the runs worth "
                "reading",
            )

    def test_write_stream_unknown_role_raises_naming_role_and_creates_no_file(self):
        self._write_stream()
        run_log_error = self._run_log_error()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._seed_run_dir(root)
            with self.assertRaisesRegex(run_log_error, "reviewer"):
                self._write_stream()(run_dir, "reviewer", "x")
            self.assertFalse(
                (run_dir / "reviewer.jsonl").exists(),
                "write_stream created reviewer.jsonl despite an unknown "
                "role; a rejected role must write nothing",
            )

    def test_write_stream_missing_run_dir_raises_naming_path(self):
        self._write_stream()
        run_log_error = self._run_log_error()
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "no-such-run"
            with self.assertRaisesRegex(
                run_log_error, re.escape(str(missing))
            ):
                self._write_stream()(missing, "coder", "x")


if __name__ == "__main__":
    unittest.main()
