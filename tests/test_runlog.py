"""Tests for ``anvilkit.pi.runlog`` - behaviours 1-14 of ``plans/pi-phase11-runlog.md``.

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

Behaviour 9 (``write-diff``), pinned from the plan:

    write_diff(run_dir, text)

- ``diff.patch`` holds the diff text verbatim, byte-for-byte;
- an empty diff still writes an empty file, since "changed nothing" is
  data - a run that changed nothing must remain distinguishable from a
  run whose diff was never recorded;
- a missing run directory raises ``RunLogError`` naming the path - the
  same guard as behaviour 8, pinned the same way.

Behaviour 10 (``write-commits``), pinned from the plan:

    write_commits(run_dir, commits)

- ``commits.json`` holds the list of ``{"sha", "subject"}`` entries via
  ``json.dumps``, in order - pinned by full-list equality of
  ``json.loads`` of the file;
- an empty list writes ``[]``;
- an entry with the wrong key set - a missing ``subject`` or an extra
  key - raises ``RunLogError`` naming the index of the offending entry,
  pinned as ``index <n>`` so the offending entry is locatable in a
  message without dictating the rendering.

Both classes seed a real run directory through the genuine ``start_run``
(behaviour 6), so the directory being written is a real on-disk run
directory, not a hand-built stand-in. While the writers are absent,
every test in the two classes is red at the fetch step: the module
attribute is not callable, and the red is that missing behaviour, not
a collection error of this file.

Behaviour 11 (``finish-run-marks-complete``), pinned from the plan:

    finish_run(run_dir, outcome, finished_at)

- ``meta.json`` is rewritten with ``finished_at``, the outcome and
  ``complete: true``, every other key preserved verbatim - pinned by
  full-dict equality of the re-read JSON against the expected merged
  dict, so no key can be dropped, altered or added;
- each of the four outcomes ``shipped`` / ``halted`` / ``failed`` /
  ``unknown`` is accepted (``unknown`` is the "we never learned"
  terminal);
- an outcome outside the four raises ``RunLogError`` naming the
  offending value and listing all four known outcomes, pinned in
  lookahead style; on a refused call ``meta.json`` is unchanged
  (full-dict equality against the pre-call dict) - a run's record is
  evidence and is not half-rewritten;
- a run directory whose ``meta.json`` is missing raises ``RunLogError``
  naming the path;
- a ``finished_at`` that is not a string raises ``RunLogError`` naming
  ``finished_at`` - the type-safety discipline behaviour 6 pins for
  ``started_at`` applies to the finish stamp as well.

The setup opens a real run through the genuine ``start_run``
(behaviour 6), so the ``meta.json`` being rewritten was written by
``start_run``, not a hand-built stand-in. While ``finish_run`` is
absent, every test here is red at the fetch step (``_finish_run``):
the module attribute is not callable, and the red is that missing
behaviour, not a collection error of this file.

Behaviour 12 (``open-run-complete``), pinned from the plan:

open_run(run_id, root) -> str (a Markdown report)

- given a run directory holding ``meta.json`` (complete), four streams,
``diff.patch`` and ``commits.json``, the report carries the run id and
both stamps, the intake, one section per role (session id, stream file
path, settled/aborted, the tool-call counters, tokens and cost from
``pievents``), then the diff and the commit sections;
- raw stream bytes are never inlined - only the file path, since a stream
can hold prompts, tool arguments and file contents. The pin holds by
splicing a sentinel into the coder stream's own content and asserting
it stays out of the report while the stream's path stays in it;
- a complete run is not marked ``INCOMPLETE`` - that mark belongs to
behaviour 14's half-written archives.

The archive is built end-to-end with the genuine writers (behaviours 6,
8, 9, 10 and 11) under a tempdir, and the per-role numbers (settled/
aborted, counters, tokens, cost) are computed in the test through
``pievents`` itself - ``parse`` then ``outcome`` and ``tool_calls`` - so
the pins are about the presence of the fixture's own numbers in the
report, not about re-deriving ``pievents``' arithmetic. While
``open_run`` is absent, every test here is red at the fetch step
(``_open_run``): the module attribute is not callable, and the red is
that missing behaviour, not a collection error of this file.

Behaviour 13 (``open-run-unparseable-stream``), pinned from the plan:

    Given: a ``<role>.jsonl`` that is empty, truncated or not JSON at
    all. When: ``open_run`` renders that role. Then: the section reads
    ``stream unparseable`` with the malformed-line count from
    ``pievents.parse`` and the stream's path, and every other role
    still renders. Error: ``open_run`` never raises on a malformed
    stream - the broken run is the one most worth reopening.

- Unparseable is read as zero parsed events, whatever the malformed
  count: ``pievents.parse`` is total and never raises, so the report
  cannot tell "every line malformed" from "no lines at all" except
  through the count it already carries. An empty stream is
  unparseable too, with an honest count of zero;
- the pinned rendering is the exact line
  ``stream unparseable: <n> malformed lines, no readable events``,
  where ``<n>`` is ``pievents.parse(text)["malformed_lines"]`` for the
  bytes the role's stream holds - computed in the tests through the
  real ``pievents.parse``, never hardcoded;
- a stream that parses to at least one event is not unparseable, even
  if it also carries malformed lines: the marker is the zero-events
  state, not the malformed-lines state;
- ``open_run`` returns a plain ``str`` on a broken archive - no test
  expects an exception.

The archive is built with the genuine writers under a tempdir, exactly
as behaviour 12 does: the broken role's stream is the raw malformed
text, the other roles' streams are the repository's well-formed
fixture. While the unparseable rendering is absent, every marker test
is red at the assertion: the broken role's section today renders the
path with the zero-facts and no "unparseable" wording at all.

Behaviour 14 (``open-run-incomplete``), pinned from the plan:

    Given: a run directory whose meta.json has complete: false, with
    diff.patch, commits.json or some streams absent. When: open_run is
    called. Then: the report is marked INCOMPLETE, each missing member
    renders as a readable absence (no diff recorded, no commits
    recorded, no stream recorded for <role>), and whatever did land
    still renders. Error: open_run never raises on a half-written
    archive - a run that died mid-way is still reopenable.

- The INCOMPLETE mark is pinned as the exact whole line
  ``status: INCOMPLETE`` - the rendering proposed for this behaviour,
  in the same ``key: value`` style as the report's ``started_at:`` and
  ``finished_at:`` lines; a finished run carries no ``INCOMPLETE`` text
  at all;
- each missing member renders the plan's pinned wording verbatim -
  ``no diff recorded`` for an absent ``diff.patch``,
  ``no commits recorded`` for an absent ``commits.json``, and
  ``no stream recorded for <role>`` for every role in the sessions map
  whose stream file is absent - and a role whose stream did land must
  not carry its absence wording;
- whatever did land still renders: in a report carrying the absence
  wording, the landed role's section still carries its session id, the
  stream's path and the fixture's own facts, and a landed ``diff.patch``
  / ``commits.json`` still renders its content while the report stays
  marked incomplete;
- ``open_run`` returns a plain ``str`` for every half-written shape the
  plan names - no test expects an exception.

The archives are built with the genuine writers (behaviours 6, 8, 9
and 10) under a tempdir and deliberately left unfinished: ``finish_run``
is never called, so ``complete`` stays ``false`` on disk, and every
test asserts that precondition on ``meta.json`` before reading the
report. The landed streams are the repository's well-formed fixture, so
the "what landed still renders" pins are the fixture's own facts,
computed in the tests through ``pievents`` itself. While the mark and
the absence wording are unimplemented, those tests are red at the
assertion: a ``complete: false`` run today renders with no INCOMPLETE
mark and no absence wording - the gaps.
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

from anvilkit.pi import pievents
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


class RunLogWriteDiffTestCase(unittest.TestCase):
    """Behaviour 9 (``write-diff``): ``write_diff(run_dir, text)``.

    The plan pins: given a run directory and the run's diff text,
    ``diff.patch`` holds the text verbatim; an empty diff still writes an
    empty file, since "changed nothing" is data. A missing run directory
    raises ``RunLogError`` naming the path - the same guard as behaviour 8.

    The happy-path setup opens a real run through the genuine ``start_run``
    (behaviour 6), so the run directory being written is a real on-disk run
    directory. While ``write_diff`` is absent, every test here is red at the
    fetch step (``_write_diff``): the module attribute is not callable, and
    the red is that missing behaviour, not a collection error of this file.
    """

    RUN_ID = EXPECTED_ID
    STARTED_AT = "2026-11-19T13:45:00Z"
    INTAKE = {"issue": 58, "text": "task body"}
    SESSIONS = {"coder": "run-20261119-134500-1a2b-coder"}

    # A realistic multi-line unified-diff fragment: the verbatim pin must
    # survive every byte, including the +/- marker lines and the final
    # trailing newline.
    DIFF_TEXT = (
        "diff --git a/anvilkit/pi/runlog.py b/anvilkit/pi/runlog.py\n"
        "index 1a2b3c4..5d6e7f8 100644\n"
        "--- a/anvilkit/pi/runlog.py\n"
        "+++ b/anvilkit/pi/runlog.py\n"
        "@@ -1,3 +1,4 @@\n"
        " def new_run_id():\n"
        "     pass\n"
        "+\n"
        "+def write_diff(run_dir, text):\n"
    )

    def _runlog(self):
        from anvilkit.pi import runlog

        return runlog

    def _write_diff(self):
        """Fetch ``anvilkit.pi.runlog.write_diff``."""
        runlog = self._runlog()
        write_diff = getattr(runlog, "write_diff", None)
        self.assertTrue(
            callable(write_diff),
            "anvilkit.pi.runlog.write_diff is not callable; behaviour 9 "
            "(write-diff) has not been implemented yet",
        )
        return write_diff

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
        """The file's exact bytes decoded as UTF-8, for verbatim pins."""
        return path.read_bytes().decode("utf-8")

    def test_write_diff_multiline_diff_written_verbatim(self):
        self._write_diff()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._seed_run_dir(root)
            self._write_diff()(run_dir, self.DIFF_TEXT)
            diff_path = run_dir / "diff.patch"
            self.assertTrue(
                diff_path.is_file(),
                "write_diff did not create %s" % diff_path,
            )
            self.assertEqual(
                self._read_text(diff_path),
                self.DIFF_TEXT,
                "diff.patch does not hold the diff text verbatim",
            )

    def test_write_diff_empty_diff_writes_empty_file(self):
        # "Changed nothing" is data: an empty diff still leaves a file, so
        # open_run can distinguish "no diff recorded" (absent) from a run
        # that changed nothing (present, empty).
        self._write_diff()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._seed_run_dir(root)
            self._write_diff()(run_dir, "")
            diff_path = run_dir / "diff.patch"
            self.assertTrue(
                diff_path.is_file(),
                "write_diff did not create %s for an empty diff; an empty "
                "diff is data (a run that changed nothing)" % diff_path,
            )
            self.assertEqual(diff_path.stat().st_size, 0)
            self.assertEqual(self._read_text(diff_path), "")

    def test_write_diff_missing_run_dir_raises_naming_path(self):
        # The same guard as behaviour 8: a missing run directory raises
        # RunLogError naming the path.
        self._write_diff()
        run_log_error = self._run_log_error()
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "no-such-run"
            with self.assertRaisesRegex(
                run_log_error, re.escape(str(missing))
            ):
                self._write_diff()(missing, self.DIFF_TEXT)


class RunLogWriteCommitsTestCase(unittest.TestCase):
    """Behaviour 10 (``write-commits``): ``write_commits(run_dir, commits)``.

    The plan pins: given a run directory and a list of ``{"sha", "subject"}``
    entries, ``commits.json`` holds the list via ``json.dumps``, in order; an
    empty list writes ``[]``. An entry with the wrong key set - a missing
    ``subject`` or an extra key - raises ``RunLogError`` naming the index of
    the offending entry (the mechanical analogue of behaviour 6's key-set
    guard).

    The index pin is ``index <n>`` in the message: the plan says the error
    names the index, and pinning the word plus the number (with flexible
    spacing) holds the contract - the offending entry is locatable - without
    dictating the rendering.

    The happy-path setup opens a real run through the genuine ``start_run``
    (behaviour 6), so the run directory being written is a real on-disk run
    directory. While ``write_commits`` is absent, every test here is red at
    the fetch step (``_write_commits``): the module attribute is not
    callable, and the red is that missing behaviour, not a collection error
    of this file.
    """

    RUN_ID = EXPECTED_ID
    STARTED_AT = "2026-11-19T13:45:00Z"
    INTAKE = {"issue": 58, "text": "task body"}
    SESSIONS = {"coder": "run-20261119-134500-1a2b-coder"}

    COMMITS = [
        {"sha": "a1b2c3d", "subject": "feat(x): the thing"},
        {"sha": "e4f5g6h", "subject": "fix(y): the bug"},
    ]

    def _runlog(self):
        from anvilkit.pi import runlog

        return runlog

    def _write_commits(self):
        """Fetch ``anvilkit.pi.runlog.write_commits``."""
        runlog = self._runlog()
        write_commits = getattr(runlog, "write_commits", None)
        self.assertTrue(
            callable(write_commits),
            "anvilkit.pi.runlog.write_commits is not callable; behaviour 10 "
            "(write-commits) has not been implemented yet",
        )
        return write_commits

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

    def test_write_commits_list_written_in_order(self):
        self._write_commits()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._seed_run_dir(root)
            self._write_commits()(run_dir, self.COMMITS)
            commits_path = run_dir / "commits.json"
            self.assertTrue(
                commits_path.is_file(),
                "write_commits did not create %s" % commits_path,
            )
            self.assertEqual(
                json.loads(commits_path.read_text(encoding="utf-8")),
                self.COMMITS,
                "commits.json does not hold the commit list in order",
            )

    def test_write_commits_empty_list_writes_empty_json_array(self):
        # No commits in the run is data, exactly as an empty diff is:
        # commits.json exists and reads back as [].
        self._write_commits()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._seed_run_dir(root)
            self._write_commits()(run_dir, [])
            commits_path = run_dir / "commits.json"
            self.assertTrue(
                commits_path.is_file(),
                "write_commits did not create %s for an empty list; a run "
                "with no commits is data" % commits_path,
            )
            self.assertEqual(
                json.loads(commits_path.read_text(encoding="utf-8")),
                [],
                "commits.json for an empty list must read back as []",
            )

    def test_write_commits_missing_subject_raises_naming_index(self):
        # Entry 0 lacks "subject": the error must name index 0.
        self._write_commits()
        run_log_error = self._run_log_error()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._seed_run_dir(root)
            bad = [{"sha": "a1b2c3d"}, self.COMMITS[1]]
            with self.assertRaisesRegex(run_log_error, r"index\s*0"):
                self._write_commits()(run_dir, bad)

    def test_write_commits_extra_key_raises_naming_index(self):
        # Entry 1 carries an extra key: the error must name index 1.
        self._write_commits()
        run_log_error = self._run_log_error()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._seed_run_dir(root)
            extra = dict(self.COMMITS[1])
            extra["extra"] = 1
            bad = [self.COMMITS[0], extra]
            with self.assertRaisesRegex(run_log_error, r"index\s*1"):
                self._write_commits()(run_dir, bad)


class RunLogFinishRunTestCase(unittest.TestCase):
    """Behaviour 11 (``finish-run-marks-complete``): ``finish_run`` rewrites
    the run's ``meta.json``.

    The plan pins: given a run directory whose ``meta.json`` was written by
    ``start_run``, calling ``finish_run(run_dir, outcome, finished_at)``
    rewrites ``meta.json`` with ``finished_at``, the outcome and
    ``complete: true``, every other key preserved verbatim. An outcome
    outside the four known terminals raises ``RunLogError`` naming it and
    listing the four; a missing ``meta.json`` raises naming the path; a
    ``finished_at`` that is not a string raises naming the field.

    The setup opens a real run through the genuine ``start_run``
    (behaviour 6), so the ``meta.json`` being rewritten was written by
    ``start_run``. While ``finish_run`` is absent, every test here is red at
    the fetch step (``_finish_run``): the module attribute is not callable,
    and the red is that missing behaviour, not a collection error of this
    file.
    """

    RUN_ID = EXPECTED_ID
    STARTED_AT = "2026-11-19T13:45:00Z"
    INTAKE = {"issue": 58, "text": "task body"}
    SESSIONS = {"coder": "run-20261119-134500-1a2b-coder"}
    FINISHED_AT = "2026-11-19T14:00:00Z"
    OUTCOMES = ("shipped", "halted", "failed", "unknown")

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

    def _finish_run(self):
        """Fetch ``anvilkit.pi.runlog.finish_run``."""
        runlog = self._runlog()
        finish_run = getattr(runlog, "finish_run", None)
        self.assertTrue(
            callable(finish_run),
            "anvilkit.pi.runlog.finish_run is not callable; behaviour 11 "
            "(finish-run-marks-complete) has not been implemented yet",
        )
        return finish_run

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
    def _meta_path(run_dir):
        """The ``meta.json`` path of the run directory."""
        return run_dir / "meta.json"

    @staticmethod
    def _read_meta(run_dir):
        """The parsed ``meta.json`` of the run directory."""
        meta_path = run_dir / "meta.json"
        return json.loads(meta_path.read_text(encoding="utf-8"))

    @staticmethod
    def _expected_meta(outcome, finished_at):
        """The full ``meta.json`` dict ``finish_run`` must leave on disk.

        Every key ``start_run`` wrote is present and verbatim; only
        ``finished_at``, ``outcome`` and ``complete`` differ. Full-dict
        equality against this shape is what keeps any dropped, altered or
        added key red.
        """
        return {
            "run_id": EXPECTED_ID,
            "started_at": "2026-11-19T13:45:00Z",
            "finished_at": finished_at,
            "intake": {"issue": 58, "text": "task body"},
            "sessions": {"coder": "run-20261119-134500-1a2b-coder"},
            "outcome": outcome,
            "complete": True,
        }

    @staticmethod
    def _naming_and_listing_pattern(offender):
        """A regex pinning a message that names ``offender`` and the outcomes.

        ``re.search`` finds a match at any position, and a lookahead
        asserts each name appears somewhere in the message, so the pin
        holds on the contract - the offending outcome is named, and all
        four known outcomes are listed - without dictating word order or
        rendering.
        """
        known = ("shipped", "halted", "failed", "unknown")
        return "".join(
            "(?=.*" + re.escape(name) + ")" for name in (offender,) + known
        )

    def test_finish_run_shipped_rewrites_meta_marking_complete(self):
        finish_run = self._finish_run()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._seed_run_dir(root)
            finish_run(run_dir, "shipped", self.FINISHED_AT)
            meta = self._read_meta(run_dir)
            self.assertEqual(
                meta,
                self._expected_meta("shipped", self.FINISHED_AT),
                "finish_run did not leave the full planned meta.json: "
                "finished_at, outcome and complete must be set and every "
                "other key preserved verbatim",
            )
            self.assertEqual(meta["finished_at"], self.FINISHED_AT)
            self.assertEqual(meta["outcome"], "shipped")
            self.assertIs(meta["complete"], True)

    def test_finish_run_each_known_outcome_is_accepted(self):
        finish_run = self._finish_run()
        for outcome in self.OUTCOMES:
            with self.subTest(outcome=outcome):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    run_dir = self._seed_run_dir(root)
                    finish_run(run_dir, outcome, self.FINISHED_AT)
                    meta = self._read_meta(run_dir)
                    self.assertEqual(
                        meta,
                        self._expected_meta(outcome, self.FINISHED_AT),
                        "finish_run rejected or misrecorded the known "
                        "outcome %r" % (outcome,),
                    )

    def test_finish_run_unknown_outcome_is_the_never_learned_terminal(self):
        # "unknown" is the "we never learned" terminal: it is a valid
        # finished outcome, not a sign of an unfinished run.
        finish_run = self._finish_run()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._seed_run_dir(root)
            finish_run(run_dir, "unknown", self.FINISHED_AT)
            meta = self._read_meta(run_dir)
            self.assertEqual(meta["outcome"], "unknown")
            self.assertIs(meta["complete"], True)

    def test_finish_run_bad_outcome_raises_naming_it_and_listing_known(self):
        finish_run = self._finish_run()
        run_log_error = self._run_log_error()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._seed_run_dir(root)
            with self.assertRaisesRegex(
                run_log_error, self._naming_and_listing_pattern("cancelled")
            ):
                finish_run(run_dir, "cancelled", self.FINISHED_AT)

    def test_finish_run_bad_outcome_leaves_meta_unchanged(self):
        # A finished run's evidence is not half-rewritten: a refused call
        # must leave meta.json byte-for-byte what start_run wrote.
        finish_run = self._finish_run()
        run_log_error = self._run_log_error()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._seed_run_dir(root)
            original_meta = self._read_meta(run_dir)
            with self.assertRaises(run_log_error):
                finish_run(run_dir, "cancelled", self.FINISHED_AT)
            self.assertEqual(
                self._read_meta(run_dir),
                original_meta,
                "finish_run rewrote meta.json despite refusing the outcome; "
                "a run's record must not be half-rewritten",
            )

    def test_finish_run_missing_meta_raises_naming_path(self):
        # The run directory exists but holds no meta.json: the error must
        # name the path, so a half-written archive is locatable.
        finish_run = self._finish_run()
        run_log_error = self._run_log_error()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._seed_run_dir(root)
            # The run directory exists but its meta.json has been deleted:
            # a half-written archive.
            (run_dir / "meta.json").unlink()
            meta_path = run_dir / "meta.json"
            with self.assertRaisesRegex(run_log_error, re.escape(str(meta_path))):
                finish_run(run_dir, "shipped", self.FINISHED_AT)

    def test_finish_run_finished_at_not_a_string_raises_naming_field(self):
        # The type-safety discipline behaviour 6 pins for started_at
        # applies to the finish stamp as well.
        finish_run = self._finish_run()
        run_log_error = self._run_log_error()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._seed_run_dir(root)
            with self.assertRaisesRegex(run_log_error, "finished_at"):
                finish_run(run_dir, "shipped", 123)


class RunLogOpenRunCompleteTestCase(unittest.TestCase):
    """Behaviour 12 (``open-run-complete``): ``open_run(run_id, root)``.

    The plan pins: given a run directory holding ``meta.json`` (complete),
    four streams, ``diff.patch`` and ``commits.json``, ``open_run(run_id,
    root)`` returns a Markdown report - the run id and stamps, the intake,
    one section per role carrying the session id, settled/aborted, the
    tool-call counters, tokens and cost from ``pievents``, then the diff
    and commit sections. Raw stream bytes are never inlined - only the
    file path, since a stream can hold prompts, tool arguments and file
    contents. Error: none on well-formed input.

    The archive is built end-to-end with the real writer functions
    (behaviours 6, 8, 9, 10, 11) under a tempdir: ``start_run`` opens the
    run, each role's stream is built from the repository's realistic Pi
    JSONL fixture, ``write_diff`` and ``write_commits`` land the diff and
    the commit list, and ``finish_run`` marks the run complete. The
    per-role facts are computed in the test with ``pievents`` itself -
    ``parse(text)["events"]`` then ``outcome`` and ``tool_calls`` - so the
    pins are about presence of the fixture's own numbers in the report,
    not about re-deriving ``pievents``' arithmetic.

    While ``open_run`` is absent, every test here is red at the fetch
    step (``_open_run``): the module attribute is not callable, and the
    red is that missing behaviour, not a collection error of this file.
    """

    RUN_ID = EXPECTED_ID
    STARTED_AT = "2026-11-19T13:45:00Z"
    FINISHED_AT = "2026-11-19T14:00:00Z"
    INTAKE = {"issue": 58, "text": "task body"}
    SESSIONS = {role: EXPECTED_ID + "-" + role for role in pirole.ROLES}

    # The repo's realistic Pi JSONL fixture: the same well-formed
    # multi-event stream backs every role, so the archive is the
    # end-to-end shape the reopen command must read.
    FIXTURE_TEXT = (
        REPO_ROOT / "tests" / "fixtures" / "pi_events_sample.jsonl"
    ).read_text(encoding="utf-8")

    # A sentinel that appears only inside a stream line: it is spliced
    # into the coder stream's first text delta, so it lands in the
    # content of a message_update record while the stream stays
    # well-formed JSONL. It must never surface in the report - raw
    # stream bytes are data and are referenced by path only.
    SENTINEL = "SENTINEL-RAW-STREAM-DO-NOT-INLINE-9f3a1c"
    FIXTURE_DELTA = '"delta": "Running the suite now"'
    SENTINEL_DELTA = '"delta": "Running the suite now ' + SENTINEL + '"'

    DIFF_TEXT = (
        "diff --git a/anvilkit/pi/runlog.py b/anvilkit/pi/runlog.py\n"
        "index 1a2b3c4..5d6e7f8 100644\n"
        "--- a/anvilkit/pi/runlog.py\n"
        "+++ b/anvilkit/pi/runlog.py\n"
        "@@ -1,3 +1,4 @@\n"
        " def open_run(run_id, root):\n"
        "+    return report\n"
    )

    COMMITS = [
        {"sha": "a1b2c3d9", "subject": "feat(runlog): open_run report"},
        {"sha": "e4f5a6b7", "subject": "fix(runlog): absent archive guard"},
    ]

    def _runlog(self):
        from anvilkit.pi import runlog

        return runlog

    def _open_run(self):
        """Fetch ``anvilkit.pi.runlog.open_run``."""
        runlog = self._runlog()
        open_run = getattr(runlog, "open_run", None)
        self.assertTrue(
            callable(open_run),
            "anvilkit.pi.runlog.open_run is not callable; behaviour 12 "
            "(open-run-complete) has not been implemented yet",
        )
        return open_run

    def _writer(self, name, behaviour):
        """Fetch a green archive writer from the module under test."""
        runlog = self._runlog()
        writer = getattr(runlog, name, None)
        self.assertTrue(
            callable(writer),
            "anvilkit.pi.runlog.%s is not callable; behaviour %s has not "
            "been implemented yet" % (name, behaviour),
        )
        return writer

    def _stream_for(self, role):
        """The role's stream: the fixture, sentinel in the coder's first
        text delta."""
        text = self.FIXTURE_TEXT
        if role == "coder":
            text = text.replace(self.FIXTURE_DELTA, self.SENTINEL_DELTA)
        return text

    def _build_complete_archive(self, root):
        """Build the complete archive with the real writers; return the
        run directory."""
        start_run = self._writer("start_run", "6 (start-run-writes-meta)")
        write_stream = self._writer(
            "write_stream", "8 (write-stream-verbatim)"
        )
        write_diff = self._writer("write_diff", "9 (write-diff)")
        write_commits = self._writer("write_commits", "10 (write-commits)")
        finish_run = self._writer(
            "finish_run", "11 (finish-run-marks-complete)"
        )
        run_dir = start_run(
            root, self.RUN_ID, self.INTAKE, self.SESSIONS, self.STARTED_AT
        )
        for role in pirole.ROLES:
            write_stream(run_dir, role, self._stream_for(role))
        write_diff(run_dir, self.DIFF_TEXT)
        write_commits(run_dir, self.COMMITS)
        finish_run(run_dir, "shipped", self.FINISHED_AT)
        return run_dir

    def _open(self, root):
        """Build the complete archive under ``root``; return the report
        and the run directory it lives in."""
        run_dir = self._build_complete_archive(root)
        report = self._open_run()(self.RUN_ID, root)
        return report, run_dir

    def _fixture_facts(self):
        """The fixture stream's outcome and tool-call facts via
        ``pievents`` itself."""
        events = pievents.parse(self.FIXTURE_TEXT)["events"]
        return pievents.outcome(events), pievents.tool_calls(events)

    def test_open_run_complete_archive_returns_markdown_str(self):
        self._open_run()
        with tempfile.TemporaryDirectory() as tmp:
            report, run_dir = self._open(Path(tmp))
        self.assertIs(
            type(report),
            str,
            "open_run must return the Markdown report as a plain str, "
            "got %r" % (type(report),),
        )

    def test_open_run_carries_run_id(self):
        self._open_run()
        with tempfile.TemporaryDirectory() as tmp:
            report, run_dir = self._open(Path(tmp))
        self.assertIn(
            self.RUN_ID,
            report,
            "the report does not carry the run id %r" % (self.RUN_ID,),
        )

    def test_open_run_carries_started_at_and_finished_at(self):
        self._open_run()
        with tempfile.TemporaryDirectory() as tmp:
            report, run_dir = self._open(Path(tmp))
        for stamp in (self.STARTED_AT, self.FINISHED_AT):
            with self.subTest(stamp=stamp):
                self.assertIn(
                    stamp,
                    report,
                    "the report does not carry the stamp %r as written "
                    "in meta.json" % (stamp,),
                )

    def test_open_run_carries_intake_issue_and_text(self):
        self._open_run()
        with tempfile.TemporaryDirectory() as tmp:
            report, run_dir = self._open(Path(tmp))
        self.assertIn(
            str(self.INTAKE["issue"]),
            report,
            "the report does not carry the intake issue number %r"
            % (self.INTAKE["issue"],),
        )
        self.assertIn(
            self.INTAKE["text"],
            report,
            "the report does not carry the intake task text %r"
            % (self.INTAKE["text"],),
        )

    def test_open_run_complete_report_not_marked_incomplete(self):
        # Behaviour 14 marks half-written archives INCOMPLETE; a complete
        # run must not carry that mark.
        self._open_run()
        with tempfile.TemporaryDirectory() as tmp:
            report, run_dir = self._open(Path(tmp))
        self.assertNotIn(
            "INCOMPLETE",
            report,
            "a complete run's report must not be marked INCOMPLETE; that "
            "mark is reserved for a half-written archive",
        )

    def test_open_run_each_role_section_carries_session_id_and_stream_path(self):
        self._open_run()
        with tempfile.TemporaryDirectory() as tmp:
            report, run_dir = self._open(Path(tmp))
        for role in pirole.ROLES:
            with self.subTest(role=role):
                self.assertIn(
                    self.SESSIONS[role],
                    report,
                    "the %r section does not carry the role's session id "
                    "%r" % (role, self.SESSIONS[role]),
                )
                stream_path = run_dir / (role + ".jsonl")
                self.assertIn(
                    str(stream_path),
                    report,
                    "the %r section does not carry the stream file path %s"
                    % (role, stream_path),
                )

    def test_open_run_role_sections_carry_outcome_counters_tokens_and_cost(self):
        # The fixture's own numbers, computed via pievents itself: every
        # role's stream is the fixture, so presence anywhere in the report
        # suffices - the pin is about the values reaching the report, not
        # about re-deriving pievents' arithmetic.
        self._open_run()
        with tempfile.TemporaryDirectory() as tmp:
            report, run_dir = self._open(Path(tmp))
        outcome, calls = self._fixture_facts()
        for value in (
            outcome["input"],
            outcome["output"],
            outcome["totalTokens"],
            outcome["cost_total"],
            calls["attempted"],
            calls["succeeded"],
            calls["failed"],
            calls["unfinished"],
            calls["orphaned"],
        ):
            with self.subTest(value=value):
                self.assertIn(
                    str(value),
                    report,
                    "the report does not carry the value %r derived from "
                    "the fixture stream via pievents (tokens, cost or a "
                    "tool-call counter)" % (value,),
                )
        for word in ("settled", "aborted"):
            with self.subTest(word=word):
                self.assertIn(
                    word,
                    report,
                    "the report does not carry the %r state of the stream"
                    % (word,),
                )

    def test_open_run_diff_section_carries_diff(self):
        # The diff is ours to show: a recognizable fragment of the diff
        # text must appear in the report.
        self._open_run()
        with tempfile.TemporaryDirectory() as tmp:
            report, run_dir = self._open(Path(tmp))
        fragment = "diff --git a/anvilkit/pi/runlog.py b/anvilkit/pi/runlog.py"
        self.assertIn(
            fragment,
            report,
            "the report does not carry the diff section's content (%r)"
            % (fragment,),
        )

    def test_open_run_commits_section_carries_both_commits_in_order(self):
        self._open_run()
        with tempfile.TemporaryDirectory() as tmp:
            report, run_dir = self._open(Path(tmp))
        first, second = self.COMMITS
        for commit in self.COMMITS:
            with self.subTest(sha=commit["sha"]):
                self.assertIn(
                    commit["sha"],
                    report,
                    "the report does not carry the commit sha %r"
                    % (commit["sha"],),
                )
                self.assertIn(
                    commit["subject"],
                    report,
                    "the report does not carry the commit subject %r"
                    % (commit["subject"],),
                )
        self.assertLess(
            report.index(first["subject"]),
            report.index(second["subject"]),
            "the commits are not rendered in the order commits.json holds "
            "them",
        )
        self.assertLess(
            report.index(first["sha"]),
            report.index(second["sha"]),
            "the commit shas are not rendered in the order commits.json "
            "holds them",
        )

    def test_open_run_never_inlines_raw_stream_bytes(self):
        # A stream can hold prompts, tool arguments and file contents: the
        # report references a stream by its file path, never by its bytes.
        self._open_run()
        with tempfile.TemporaryDirectory() as tmp:
            report, run_dir = self._open(Path(tmp))
        self.assertNotIn(
            self.SENTINEL,
            report,
            "the report inlined raw stream bytes: %r appears only inside "
            "the coder stream and must stay out of the report"
            % (self.SENTINEL,),
        )
        self.assertIn(
            str(run_dir / "coder.jsonl"),
            report,
            "the report does not carry the coder stream's file path in "
            "place of its bytes",
        )


class RunLogOpenRunUnparseableTestCase(unittest.TestCase):
    """Behaviour 13 (``open-run-unparseable-stream``): ``open_run`` renders a
    broken stream.

    The plan pins: given a ``<role>.jsonl`` that is empty, truncated or not
    JSON at all, ``open_run`` renders that role's section as
    ``stream unparseable`` with the malformed-line count from
    ``pievents.parse`` and the stream's path, and every other role still
    renders; ``open_run`` never raises on a malformed stream - the broken
    run is the one most worth reopening.

    The unparseable reading is zero parsed events, whatever the malformed
    count: ``pievents.parse`` is total and never raises, so the report
    distinguishes "every line malformed" from "no lines at all" only
    through the count it carries. The pinned rendering is the exact line
    ``stream unparseable: <n> malformed lines, no readable events`` where
    ``<n>`` is ``pievents.parse(text)["malformed_lines"]`` for the bytes
    the role's stream holds - computed in the tests through the real
    ``pievents.parse``, never hardcoded. A stream that parses to at least
    one event is not unparseable, even when it carries malformed lines.

    The archive is built with the genuine writers (behaviours 6, 8, 11)
    under a tempdir: the broken role's stream is the raw malformed text,
    the other roles' streams are the repository's well-formed fixture.
    While the unparseable rendering is absent, every marker test is red
    at the assertion: the broken role's section today renders the path
    with the zero facts and no "unparseable" wording at all.
    """

    RUN_ID = EXPECTED_ID
    STARTED_AT = "2026-11-19T13:45:00Z"
    FINISHED_AT = "2026-11-19T14:00:00Z"
    INTAKE = {"issue": 58, "text": "task body"}
    SESSIONS = {role: EXPECTED_ID + "-" + role for role in pirole.ROLES}

    # The same well-formed fixture as behaviour 12 backs every healthy
    # role, so the broken role is the only one that differs.
    FIXTURE_TEXT = (
        REPO_ROOT / "tests" / "fixtures" / "pi_events_sample.jsonl"
    ).read_text(encoding="utf-8")

    # Not JSON at all: two lines, neither of which parses.
    NOT_JSON_TEXT = "totally not json\nalso not json\n"
    # Truncated: a single line cut mid-JSON, so the stream parses to zero
    # events with one malformed line - the zero-events state, not the
    # mixed one-event state (see MIXED_TEXT below).
    TRUNCATED_TEXT = '{"type": "agent_st'
    # A stream that parses to one event yet also carries a malformed
    # line: not unparseable, because the marker is the zero-events
    # state, not the malformed-lines state.
    MIXED_TEXT = '{"type": "agent_start"}\nnot json at all'

    def _runlog(self):
        from anvilkit.pi import runlog

        return runlog

    def _open_run(self):
        """Fetch ``anvilkit.pi.runlog.open_run`` (green since behaviour 12)."""
        runlog = self._runlog()
        open_run = getattr(runlog, "open_run", None)
        self.assertTrue(
            callable(open_run),
            "anvilkit.pi.runlog.open_run is not callable; behaviour 12 "
            "(open-run-complete) is a precondition of behaviour 13",
        )
        return open_run

    def _writer(self, name, behaviour):
        """Fetch a green archive writer from the module under test."""
        runlog = self._runlog()
        writer = getattr(runlog, name, None)
        self.assertTrue(
            callable(writer),
            "anvilkit.pi.runlog.%s is not callable; behaviour %s has not "
            "been implemented yet" % (name, behaviour),
        )
        return writer

    def _build_archive(self, root, broken_role, broken_text):
        """Build a complete archive with the genuine writers in which
        exactly ``broken_role``'s stream is ``broken_text`` and every
        other role's stream is the well-formed fixture. Returns the run
        directory."""
        start_run = self._writer("start_run", "6 (start-run-writes-meta)")
        write_stream = self._writer(
            "write_stream", "8 (write-stream-verbatim)"
        )
        finish_run = self._writer(
            "finish_run", "11 (finish-run-marks-complete)"
        )
        run_dir = start_run(
            root, self.RUN_ID, self.INTAKE, self.SESSIONS, self.STARTED_AT
        )
        for role in pirole.ROLES:
            text = broken_text if role == broken_role else self.FIXTURE_TEXT
            write_stream(run_dir, role, text)
        finish_run(run_dir, "shipped", self.FINISHED_AT)
        return run_dir

    def _role_section(self, report, role):
        """The report text of one role's section: from its header up to
        (not including) the next section header. Raises ``AssertionError``
        if the section header is missing."""
        header = "## Role: " + role
        start = report.index(header)
        rest = report[start + len(header):]
        for next_header in ("## Intake", "## Role:", "## Diff", "## Commits"):
            if rest.startswith(next_header):
                continue
            cut = rest.find(next_header)
            if cut != -1:
                return rest[:cut]
        return rest

    def _unparseable_line(self, text):
        """The exact pinned unparseable line for ``text``: the count is
        computed with the real ``pievents.parse``, never hardcoded."""
        return "stream unparseable: %d malformed lines, no readable events" % (
            pievents.parse(text)["malformed_lines"],
        )

    def test_open_run_not_json_stream_marker_with_derived_count_and_path(self):
        self._open_run()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._build_archive(root, "coder", self.NOT_JSON_TEXT)
            report = self._open_run()(self.RUN_ID, root)
        self.assertIsInstance(
            report,
            str,
            "open_run must return a str on a broken archive; the broken "
            "run is the one most worth reopening",
        )
        section = self._role_section(report, "coder")
        expected_line = self._unparseable_line(self.NOT_JSON_TEXT)
        self.assertEqual(
            expected_line,
            "stream unparseable: 2 malformed lines, no readable events",
            "test-precondition: pievents.parse must count both lines of "
            "%r as malformed" % (self.NOT_JSON_TEXT,),
        )
        self.assertIn(
            expected_line,
            section,
            "the coder section does not carry the pinned unparseable line "
            "%r (the count must be pievents.parse's malformed_lines for "
            "the stream's bytes)" % (expected_line,),
        )
        self.assertIn(
            str(run_dir / "coder.jsonl"),
            section,
            "the coder section does not carry the broken stream's path %s"
            % (run_dir / "coder.jsonl",),
        )
        # The count is derived from the bytes, not invented: the same
        # line must not appear in any healthy role's section.
        for role in pirole.ROLES:
            if role == "coder":
                continue
            with self.subTest(role=role):
                self.assertNotIn(
                    expected_line,
                    self._role_section(report, role),
                    "the healthy %r section must not carry the unparseable "
                    "marker" % (role,),
                )

    def test_open_run_truncated_stream_marker_with_derived_count(self):
        self._open_run()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._build_archive(root, "tester", self.TRUNCATED_TEXT)
            report = self._open_run()(self.RUN_ID, root)
        section = self._role_section(report, "tester")
        expected_line = self._unparseable_line(self.TRUNCATED_TEXT)
        self.assertEqual(
            expected_line,
            "stream unparseable: 1 malformed lines, no readable events",
            "test-precondition: pievents.parse must count the cut line "
            "of %r as malformed" % (self.TRUNCATED_TEXT,),
        )
        self.assertIn(
            expected_line,
            section,
            "the tester section does not carry the pinned unparseable "
            "line %r for the truncated stream" % (expected_line,),
        )
        self.assertIn(
            str(run_dir / "tester.jsonl"),
            section,
            "the tester section does not carry the truncated stream's path "
            "%s" % (run_dir / "tester.jsonl",),
        )

    def test_open_run_empty_stream_marker_with_zero_count(self):
        self._open_run()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._build_archive(root, "docs", "")
            report = self._open_run()(self.RUN_ID, root)
        self.assertIsInstance(report, str)
        section = self._role_section(report, "docs")
        expected_line = self._unparseable_line("")
        self.assertEqual(
            expected_line,
            "stream unparseable: 0 malformed lines, no readable events",
            "test-precondition: pievents.parse must count an empty stream "
            "as zero events with a malformed count of zero",
        )
        self.assertIn(
            expected_line,
            section,
            "the docs section does not carry the pinned unparseable line "
            "%r for an empty stream (zero events is unparseable, and the "
            "count renders as 0)" % (expected_line,),
        )
        self.assertIn(
            str(run_dir / "docs.jsonl"),
            section,
            "the docs section does not carry the empty stream's path %s"
            % (run_dir / "docs.jsonl",),
        )

    def test_open_run_mixed_stream_is_not_unparseable(self):
        # One valid line plus one malformed line parses to one event, so
        # it is not unparseable: the marker is the zero-events state, not
        # the malformed-lines state.
        self._open_run()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._build_archive(root, "architect", self.MIXED_TEXT)
            report = self._open_run()(self.RUN_ID, root)
        section = self._role_section(report, "architect")
        self.assertEqual(
            pievents.parse(self.MIXED_TEXT)["malformed_lines"],
            1,
            "test-precondition: pievents.parse must count the one bad line "
            "of %r as malformed while parsing one event" % (self.MIXED_TEXT,),
        )
        self.assertNotIn(
            "stream unparseable",
            section,
            "a stream that parses to at least one event must not be marked "
            "unparseable, even when it carries a malformed line",
        )

    def test_open_run_broken_role_and_healthy_role_render_in_one_report(self):
        self._open_run()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._build_archive(root, "coder", self.NOT_JSON_TEXT)
            report = self._open_run()(self.RUN_ID, root)
        # The broken role carries the marker.
        coder_section = self._role_section(report, "coder")
        self.assertIn(
            self._unparseable_line(self.NOT_JSON_TEXT),
            coder_section,
            "the broken coder section does not carry the unparseable marker",
        )
        # A healthy role still renders its facts: the fixture's own
        # session id, settled state, token totals and cost, all computed
        # via pievents itself.
        events = pievents.parse(self.FIXTURE_TEXT)["events"]
        outcome = pievents.outcome(events)
        calls = pievents.tool_calls(events)
        session = pievents.session(events)
        for role in ("architect", "tester", "docs"):
            with self.subTest(role=role):
                section = self._role_section(report, role)
                self.assertNotIn(
                    "stream unparseable",
                    section,
                    "the healthy %r section must not carry the unparseable "
                    "marker" % (role,),
                )
                self.assertIn(
                    session["session_id"],
                    section,
                    "the healthy %r section does not carry the fixture's "
                    "session id %r" % (role, session["session_id"]),
                )
                self.assertIn(
                    "settled: %s" % (outcome["settled"],),
                    section,
                    "the healthy %r section does not carry the fixture's "
                    "settled state" % (role,),
                )
                for value in (
                    outcome["input"],
                    outcome["output"],
                    outcome["totalTokens"],
                    outcome["cost_total"],
                    calls["attempted"],
                ):
                    self.assertIn(
                        str(value),
                        section,
                        "the healthy %r section does not carry the value "
                        "%r derived from the fixture stream via pievents"
                        % (role, value),
                    )

    def test_open_run_broken_stream_never_raises(self):
        # Every archive shape the plan names - not JSON, truncated, empty -
        # must come back as a report, not an exception.
        self._open_run()
        for text in (self.NOT_JSON_TEXT, self.TRUNCATED_TEXT, ""):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                run_dir = self._build_archive(root, "coder", text)
                report = self._open_run()(self.RUN_ID, root)
            self.assertIsInstance(
                report,
                str,
                "open_run raised or did not return a str on the stream %r; "
                "a malformed stream must never break the reopen" % (text,),
            )
            self.assertIn(
                self._unparseable_line(text),
                self._role_section(report, "coder"),
                "the coder section for %r does not carry the unparseable "
                "marker" % (text,),
            )


class RunLogOpenRunIncompleteTestCase(unittest.TestCase):
    """Behaviour 14 (``open-run-incomplete``): ``open_run`` reopens a
    half-written archive.

    The plan pins: given a run directory whose ``meta.json`` has
    ``complete: false``, with ``diff.patch``, ``commits.json`` or some
    streams absent, ``open_run`` marks the report ``INCOMPLETE``,
    renders each missing member as a readable absence - the pinned
    wording ``no diff recorded``, ``no commits recorded`` and
    ``no stream recorded for <role>`` - and still renders whatever did
    land; it never raises, so a run that died mid-way is still
    reopenable.

    The INCOMPLETE rendering pinned here: a half-written report carries
    the exact whole line ``status: INCOMPLETE`` - the proposal for this
    behaviour, in the same ``key: value`` style as the report's
    ``started_at:`` and ``finished_at:`` lines. A finished run carries
    no ``INCOMPLETE`` text at all (the mirror of behaviour 12's
    existing pin, here from the incomplete side).

    The archives are built with the genuine writers (behaviours 6, 8, 9
    and 10) under a tempdir and deliberately left unfinished:
    ``finish_run`` is never called, so ``complete`` stays ``false`` on
    disk, and every test asserts that precondition on ``meta.json``
    before reading the report. The landed coder stream is the
    repository's well-formed fixture, so the "what landed still
    renders" pins are the fixture's own facts, computed in the tests
    through ``pievents`` itself. While the mark and the absence wording
    are unimplemented, those tests are red at the assertion: a
    ``complete: false`` run today renders with no INCOMPLETE mark and
    no absence wording - the gaps.
    """

    RUN_ID = EXPECTED_ID
    STARTED_AT = "2026-11-19T13:45:00Z"
    FINISHED_AT = "2026-11-19T14:00:00Z"
    INTAKE = {"issue": 58, "text": "task body"}
    SESSIONS = {role: EXPECTED_ID + "-" + role for role in pirole.ROLES}

    # The exact INCOMPLETE rendering this class proposes and pins: a
    # whole line, in the report's key: value style.
    INCOMPLETE_LINE = "status: INCOMPLETE"
    # The plan's pinned absence wording, verbatim.
    NO_DIFF = "no diff recorded"
    NO_COMMITS = "no commits recorded"

    # The repository's well-formed fixture: the landed coder stream, so
    # the "what landed still renders" pins are the fixture's own facts.
    FIXTURE_TEXT = (
        REPO_ROOT / "tests" / "fixtures" / "pi_events_sample.jsonl"
    ).read_text(encoding="utf-8")

    DIFF_TEXT = (
        "diff --git a/anvilkit/pi/runlog.py b/anvilkit/pi/runlog.py\n"
        "index 1a2b3c4..5d6e7f8 100644\n"
        "--- a/anvilkit/pi/runlog.py\n"
        "+++ b/anvilkit/pi/runlog.py\n"
        "@@ -1,3 +1,4 @@\n"
        " def open_run(run_id, root):\n"
        "+    return report\n"
    )
    DIFF_FRAGMENT = "diff --git a/anvilkit/pi/runlog.py b/anvilkit/pi/runlog.py"

    COMMITS = [
        {"sha": "a1b2c3d9", "subject": "feat(runlog): open_run report"},
        {"sha": "e4f5a6b7", "subject": "fix(runlog): absent archive guard"},
    ]

    def _runlog(self):
        from anvilkit.pi import runlog

        return runlog

    def _open_run(self):
        """Fetch ``anvilkit.pi.runlog.open_run`` (green since behaviour 12)."""
        runlog = self._runlog()
        open_run = getattr(runlog, "open_run", None)
        self.assertTrue(
            callable(open_run),
            "anvilkit.pi.runlog.open_run is not callable; behaviour 12 "
            "(open-run-complete) is a precondition of behaviour 14",
        )
        return open_run

    def _writer(self, name, behaviour):
        """Fetch a green archive writer from the module under test."""
        runlog = self._runlog()
        writer = getattr(runlog, name, None)
        self.assertTrue(
            callable(writer),
            "anvilkit.pi.runlog.%s is not callable; behaviour %s has not "
            "been implemented yet" % (name, behaviour),
        )
        return writer

    def _assert_incomplete_meta(self, run_dir):
        """Precondition: the archive on disk really is half-written.

        ``finish_run`` was never called, so ``meta.json``'s ``complete``
        must still be ``false``; without this check a builder that
        finished the run would test the complete path and pass
        invisibly.
        """
        meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertIs(
            meta["complete"],
            False,
            "the test archive must be half-written (complete: false); the "
            "builder must never call finish_run",
        )

    def _build_incomplete_archive(
        self, root, stream_roles=(), with_diff=False, with_commits=False
    ):
        """Build a half-written archive with the genuine writers.

        ``start_run`` opens the run with all four roles in the sessions
        map; only the listed roles' streams are written (each the
        well-formed fixture); the diff and the commits land only when
        asked. ``finish_run`` is never called, so the run stays
        ``complete: false`` on disk.
        """
        start_run = self._writer("start_run", "6 (start-run-writes-meta)")
        write_stream = self._writer(
            "write_stream", "8 (write-stream-verbatim)"
        )
        write_diff = self._writer("write_diff", "9 (write-diff)")
        write_commits = self._writer("write_commits", "10 (write-commits)")
        run_dir = start_run(
            root, self.RUN_ID, self.INTAKE, self.SESSIONS, self.STARTED_AT
        )
        for role in stream_roles:
            write_stream(run_dir, role, self.FIXTURE_TEXT)
        if with_diff:
            write_diff(run_dir, self.DIFF_TEXT)
        if with_commits:
            write_commits(run_dir, self.COMMITS)
        return run_dir

    def _build_finished_archive(self, root):
        """Build the complete behaviour-12 shape for the not-marked
        mirror pin: every member present, ``finish_run`` called."""
        start_run = self._writer("start_run", "6 (start-run-writes-meta)")
        write_stream = self._writer(
            "write_stream", "8 (write-stream-verbatim)"
        )
        write_diff = self._writer("write_diff", "9 (write-diff)")
        write_commits = self._writer("write_commits", "10 (write-commits)")
        finish_run = self._writer(
            "finish_run", "11 (finish-run-marks-complete)"
        )
        run_dir = start_run(
            root, self.RUN_ID, self.INTAKE, self.SESSIONS, self.STARTED_AT
        )
        for role in pirole.ROLES:
            write_stream(run_dir, role, self.FIXTURE_TEXT)
        write_diff(run_dir, self.DIFF_TEXT)
        write_commits(run_dir, self.COMMITS)
        finish_run(run_dir, "shipped", self.FINISHED_AT)
        return run_dir

    def _open(self, root, **build_kwargs):
        """Build the half-written archive; return the report and the run
        directory it lives in."""
        run_dir = self._build_incomplete_archive(root, **build_kwargs)
        self._assert_incomplete_meta(run_dir)
        report = self._open_run()(self.RUN_ID, root)
        return report, run_dir

    def _role_section(self, report, role):
        """The report text of one role's section: from its header up to
        (not including) the next section header. Raises ``AssertionError``
        if the section header is missing."""
        header = "## Role: " + role
        start = report.index(header)
        rest = report[start + len(header):]
        for next_header in ("## Intake", "## Role:", "## Diff", "## Commits"):
            if rest.startswith(next_header):
                continue
            cut = rest.find(next_header)
            if cut != -1:
                return rest[:cut]
        return rest

    def test_open_run_meta_only_run_report_marked_incomplete(self):
        # A run that died right after start_run: no streams, no diff, no
        # commits. The report must carry the INCOMPLETE mark as the exact
        # whole line this class proposes.
        self._open_run()
        with tempfile.TemporaryDirectory() as tmp:
            report, run_dir = self._open(Path(tmp))
        self.assertIs(
            type(report),
            str,
            "open_run must return a plain str on a half-written archive; "
            "a run that died mid-way is still reopenable",
        )
        self.assertIn(
            self.INCOMPLETE_LINE,
            report.splitlines(),
            "a half-written archive's report does not carry the exact "
            "line %r marking the run incomplete" % (self.INCOMPLETE_LINE,),
        )

    def test_open_run_finished_run_report_not_marked_incomplete(self):
        # The mirror pin from the incomplete side: a finished run -
        # every member present, complete: true - carries no INCOMPLETE
        # text at all.
        self._open_run()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._build_finished_archive(root)
            report = self._open_run()(self.RUN_ID, root)
        self.assertIs(type(report), str)
        self.assertNotIn(
            "INCOMPLETE",
            report,
            "a complete run's report must not be marked INCOMPLETE; that "
            "mark is reserved for a half-written archive",
        )

    def test_open_run_missing_members_render_pinned_absence_wording(self):
        # Only the coder's stream landed: the diff, the commits and the
        # other three roles' streams are absent, and each missing member
        # renders the plan's pinned wording verbatim.
        self._open_run()
        with tempfile.TemporaryDirectory() as tmp:
            report, run_dir = self._open(Path(tmp), stream_roles=("coder",))
        self.assertIn(
            self.NO_DIFF,
            report,
            "the report does not carry the pinned absence wording %r for "
            "the missing diff.patch" % (self.NO_DIFF,),
        )
        self.assertIn(
            self.NO_COMMITS,
            report,
            "the report does not carry the pinned absence wording %r for "
            "the missing commits.json" % (self.NO_COMMITS,),
        )
        for role in pirole.ROLES:
            with self.subTest(role=role):
                section = self._role_section(report, role)
                expected = "no stream recorded for " + role
                if role == "coder":
                    self.assertNotIn(
                        expected,
                        section,
                        "the coder's stream did land, so its section must "
                        "not carry %r" % (expected,),
                    )
                else:
                    self.assertIn(
                        expected,
                        section,
                        "the %r section does not carry the pinned absence "
                        "wording %r for its missing stream"
                        % (role, expected),
                    )

    def test_open_run_landed_coder_section_still_renders_session_path_and_facts(self):
        # Whatever did land still renders: in the same half-written
        # report that carries the absence wording, the coder's section
        # still carries its session id, the stream's path and the
        # fixture's own facts.
        self._open_run()
        with tempfile.TemporaryDirectory() as tmp:
            report, run_dir = self._open(Path(tmp), stream_roles=("coder",))
        section = self._role_section(report, "coder")
        events = pievents.parse(self.FIXTURE_TEXT)["events"]
        outcome = pievents.outcome(events)
        session = pievents.session(events)
        self.assertIn(
            "session id: " + self.SESSIONS["coder"],
            section,
            "the landed coder section does not carry its session id %r"
            % (self.SESSIONS["coder"],),
        )
        self.assertIn(
            str(run_dir / "coder.jsonl"),
            section,
            "the landed coder section does not carry the stream path %s"
            % (run_dir / "coder.jsonl",),
        )
        self.assertIn(
            "stream session: %s" % (session["session_id"],),
            section,
            "the landed coder section does not carry the fixture stream's "
            "session id %r" % (session["session_id"],),
        )
        self.assertIn(
            "settled: %s" % (outcome["settled"],),
            section,
            "the landed coder section does not carry the fixture stream's "
            "settled state",
        )
        for value in (
            outcome["input"],
            outcome["output"],
            outcome["totalTokens"],
            outcome["cost_total"],
        ):
            with self.subTest(value=value):
                self.assertIn(
                    str(value),
                    section,
                    "the landed coder section does not carry the value %r "
                    "derived from the fixture stream via pievents (tokens "
                    "or cost)" % (value,),
                )

    def test_open_run_partial_landing_diff_and_commits_render_with_mark(self):
        # diff.patch and commits.json landed but no stream did: the
        # report is still INCOMPLETE, the diff section carries the diff,
        # the commits section carries the commits, and every role's
        # missing stream renders the pinned absence wording.
        self._open_run()
        with tempfile.TemporaryDirectory() as tmp:
            report, run_dir = self._open(
                Path(tmp), with_diff=True, with_commits=True
            )
        self.assertIn(
            self.INCOMPLETE_LINE,
            report.splitlines(),
            "a run with a diff and commits but no streams is still "
            "half-written and must carry %r" % (self.INCOMPLETE_LINE,),
        )
        self.assertIn(
            self.DIFF_FRAGMENT,
            report,
            "the diff section does not carry the diff that did land (%r)"
            % (self.DIFF_FRAGMENT,),
        )
        for commit in self.COMMITS:
            with self.subTest(sha=commit["sha"]):
                self.assertIn(
                    commit["sha"],
                    report,
                    "the commits section does not carry the commit sha %r"
                    % (commit["sha"],),
                )
                self.assertIn(
                    commit["subject"],
                    report,
                    "the commits section does not carry the commit subject "
                    "%r" % (commit["subject"],),
                )
        for role in pirole.ROLES:
            with self.subTest(role=role):
                expected = "no stream recorded for " + role
                self.assertIn(
                    expected,
                    self._role_section(report, role),
                    "the %r section does not carry the pinned absence "
                    "wording %r for its missing stream" % (role, expected),
                )

    def test_open_run_every_half_written_shape_returns_str(self):
        # open_run never raises on a half-written archive: every shape
        # the plan names - no members at all, some streams, the diff,
        # the commits - comes back as a report, and every shape is
        # marked incomplete.
        self._open_run()
        shapes = (
            {},
            {"stream_roles": ("coder",)},
            {"stream_roles": ("coder", "tester")},
            {"with_diff": True},
            {"with_commits": True},
            {"with_diff": True, "with_commits": True},
        )
        for shape in shapes:
            with self.subTest(shape=shape), \
                    tempfile.TemporaryDirectory() as tmp:
                report, run_dir = self._open(Path(tmp), **shape)
            self.assertIs(
                type(report),
                str,
                "open_run did not return a str on the half-written shape "
                "%r; a run that died mid-way is still reopenable"
                % (shape,),
            )
            self.assertIn(
                self.INCOMPLETE_LINE,
                report.splitlines(),
                "the report for the half-written shape %r does not carry "
                "%r" % (shape, self.INCOMPLETE_LINE),
            )


if __name__ == "__main__":
    unittest.main()
