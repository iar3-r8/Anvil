"""Tests for anvilkit.pirecord - the bake-off run record builder.

Written before the implementation (TDD, ``plans/pi-phase1-bakeoff.md``,
behaviour 11: "run record"). Behaviour 12 (``render_table``) lands in a
later cycle as further classes in the same file.

The three dimension sources the record assembles are:

- **run outcome** - the exit code, wall time, the waited-for-input
  evidence flag and the artifact paths, measured by the host recipe
  (behaviours 13-15);
- **the model's work** - the tool-call counters shaped exactly as
  ``anvilkit.pievents.tool_calls`` returns them (behaviour 9) and the
  outcome/usage dict shaped exactly as ``anvilkit.pievents.outcome``
  returns them (behaviour 10);
- **the fixture state** - the assertion result shaped exactly as
  ``anvilkit.pifixture.assertion_passes`` returns it (behaviour 2) and
  the changed-files list shaped exactly as
  ``anvilkit.pifixture.changed_files`` returns it (behaviour 3).

The production module ``anvilkit.pirecord`` does not exist yet, so every
test loads it through ``_pirecord``, which fails with a clear assertion
instead of letting a collection-time ImportError mask the reason the
suite is red.

Pinned signature:

    build(config, *, model, exit_code, wall_time_s, waited_for_input,
          artifacts, tool_calls, outcome, assertion, changed_files,
          timestamp) -> dict

Everything after ``config`` is keyword-only, so a half-recorded run
cannot accidentally pass a dimension in the wrong position: the caller
must name every dimension, and :func:`_missing` below can point at the
exact field whose value arrived ``None``.

Pinned record shape: a plain dict with exactly these keys, JSON-native
throughout (so ``json.loads(json.dumps(record, sort_keys=True)) ==
record`` holds by construction - no ``Path`` objects, no sets, no
booleans smuggled in as ints):

- ``"config"``: ``str`` - one of ``"print"``, ``"json"``, ``"ultrawork"``;
- ``"completed"``: ``bool`` - ``True`` iff ``exit_code == 0`` AND the
  assertion's ``passed`` is ``True`` (both directions pinned);
- ``"exit_code"``: ``int``;
- ``"wall_time_s"``: ``float`` - the host-measured wall time in seconds;
- ``"waited_for_input"``: ``bool`` - the host recipe's evidence flag
  (behaviour 13 records it ``True`` when the process blocks on stdin);
- ``"changed_files"``: ``List[str]`` - verbatim from
  ``pifixture.changed_files``, deletions carrying their ``"deleted:"``
  prefix;
- ``"tool_calls"``: ``dict`` - verbatim the five-counter dict from
  ``pievents.tool_calls``;
- ``"tokens"``: ``dict`` - ``{"input": int, "output": int,
  "totalTokens": int}`` lifted from the outcome dict (the three token
  fields of the last ``message_update.usage``); the remaining outcome
  fields (``settled``, ``aborted``, ``usage_reported``) are NOT
  embedded - they are stream-level facts about the JSONL, not
  dimensions of the record, and the record key list is closed by
  ``RECORD_KEYS``;
- ``"cost_total"``: ``float`` - lifted from the outcome dict's
  ``cost_total`` (the flattened ``cost.total``);
- ``"waited_for_input"`` (see above);
- ``"artifacts"``: ``dict`` - exactly the keys ``stdout``, ``stderr``,
  ``jsonl``, ``before_digest``, ``after_digest``, each a ``str`` path;
  ``jsonl`` is the one field allowed to be ``None``, for the
  print/ultrawork runs that produce no JSONL stream;
- ``"assertion"``: ``dict`` - verbatim the
  ``{"passed": bool, "stderr": str}`` from
  ``pifixture.assertion_passes``;
- ``"model"``: ``str``;
- ``"timestamp"``: ``str`` - the caller passes the ISO-8601 UTC
  stamp (pinned format ``YYYY-MM-DDTHH:MM:SSZ``, e.g.
  ``datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")``); ``build``
  stores it verbatim and must not reformat, so records written by the
  host recipe at different times still sort lexicographically.

Error path: any of the five dimensions missing (a required argument
``None``, ``artifacts`` missing a key, ``outcome``/``tool_calls``
missing a counter key) raises ``RecordError`` whose message names the
missing field, so a half-recorded run cannot become a verdict. One
exception type: ``RecordError``.
"""

import importlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from typing import Callable, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Closed key sets: the pinned record shape leaves the coder no room for
# undocumented fields, because several tests assert the complete dict
# by value.
RECORD_KEYS = {
    "config",
    "completed",
    "exit_code",
    "wall_time_s",
    "waited_for_input",
    "changed_files",
    "tool_calls",
    "tokens",
    "cost_total",
    "artifacts",
    "assertion",
    "model",
    "timestamp",
}
ARTIFACT_KEYS = {"stdout", "stderr", "jsonl", "before_digest", "after_digest"}
TOOL_CALL_KEYS = {"attempted", "succeeded", "failed", "unfinished", "orphaned"}
OUTCOME_KEYS = {
    "settled",
    "aborted",
    "input",
    "output",
    "totalTokens",
    "cost_total",
    "usage_reported",
}
CONFIG_VALUES = ("print", "json", "ultrawork")

# The pinned timestamp format: ISO-8601 UTC, no offset, Z suffix.
TIMESTAMP = "2026-10-20T21:00:00Z"


class PirecordTestCase(unittest.TestCase):
    def _pirecord(self):
        """Import anvilkit.pirecord, failing clearly if the module is absent."""
        spec = importlib.util.find_spec("anvilkit.pirecord")
        self.assertIsNotNone(
            spec,
            "anvilkit.pirecord cannot be imported; the run-record "
            "builder (behaviour 11) has not been implemented yet",
        )
        return importlib.import_module("anvilkit.pirecord")

    def _get_build(self) -> Callable:
        """Fetch ``anvilkit.pirecord.build``, failing clearly if absent."""
        pirecord = self._pirecord()
        build = getattr(pirecord, "build", None)
        self.assertTrue(
            callable(build),
            "anvilkit.pirecord.build is not callable; the run-record "
            "builder (behaviour 11) has not been implemented yet",
        )
        return build

    def _get_record_error(self):
        """Fetch ``anvilkit.pirecord.RecordError``, failing clearly if absent."""
        pirecord = self._pirecord()
        record_error = getattr(pirecord, "RecordError", None)
        self.assertTrue(
            isinstance(record_error, type) and issubclass(record_error, Exception),
            "anvilkit.pirecord.RecordError is not an exception type; the "
            "half-record guard (behaviour 11) has not been implemented yet",
        )
        return record_error

    @staticmethod
    def _tool_calls():
        """The tool-call counters exactly as pievents.tool_calls returns them."""
        return {
            "attempted": 2,
            "succeeded": 1,
            "failed": 1,
            "unfinished": 0,
            "orphaned": 0,
        }

    @staticmethod
    def _get_outcome():
        """The outcome dict exactly as pievents.outcome returns it.

        Named ``_get_outcome`` on purpose: ``unittest.TestCase`` owns an
        instance attribute called ``_outcome`` (set by ``TestCase.run()``
        to its internal ``_Outcome`` result tracker), which would shadow a
        helper of that name and turn every call into
        ``TypeError: '_Outcome' object is not callable``.
        """
        return {
            "settled": True,
            "aborted": False,
            "input": 1200,
            "output": 350,
            "totalTokens": 1550,
            "cost_total": 0.0021,
            "usage_reported": True,
        }

    @staticmethod
    def _assertion(passed=True):
        """The assertion result exactly as pifixture.assertion_passes returns it."""
        return {"passed": passed, "stderr": "" if passed else "AssertionError"}

    @staticmethod
    def _artifacts(jsonl=None):
        """The five artifact paths; jsonl may be None (print/ultrawork runs)."""
        return {
            "stdout": "/runs/run-json/stdout.txt",
            "stderr": "/runs/run-json/stderr.txt",
            "jsonl": jsonl,
            "before_digest": "/runs/run-json/before.sha256",
            "after_digest": "/runs/run-json/after.sha256",
        }

    def _build(self, build, config="json", **overrides):
        """Call build with one fully-populated set of dimensions.

        ``config`` names the bake-off configuration under test (the
        default ``"json"`` is the only one that produces a JSONL stream,
        which is what the default ``artifacts`` carries); the
        print/ultrawork tests pass it explicitly because those runs have
        no JSONL. ``overrides`` replaces individual arguments, so each
        error test can null out exactly one dimension and nothing else.
        """
        kwargs = dict(
            model="matrix.vars.coder",
            exit_code=0,
            wall_time_s=41.5,
            waited_for_input=False,
            artifacts=self._artifacts("/runs/run-json/events.jsonl"),
            tool_calls=self._tool_calls(),
            outcome=self._get_outcome(),
            assertion=self._assertion(True),
            changed_files=["bakeoff_fixture/adder.py"],
            timestamp=TIMESTAMP,
        )
        kwargs.update(overrides)
        return build(config, **kwargs)


class TestRecordShape(PirecordTestCase):
    """The pinned record shape: exactly the thirteen keys, each with the
    documented value, for every legal configuration."""

    def test_build_returns_dict_with_exactly_thirteen_keys(self):
        build = self._get_build()
        record = self._build(build)
        self.assertIsInstance(
            record,
            dict,
            "build must return a plain dict, so the go/no-go table "
            "(behaviour 12) can read it and json.dumps it directly",
        )
        self.assertEqual(
            set(record),
            RECORD_KEYS,
            "build must return exactly the thirteen pinned keys: no "
            "extra keys, no missing keys",
        )

    def test_build_json_run_returns_pinned_record(self):
        build = self._get_build()
        self.assertEqual(
            self._build(build),
            {
                "config": "json",
                "completed": True,
                "exit_code": 0,
                "wall_time_s": 41.5,
                "waited_for_input": False,
                "changed_files": ["bakeoff_fixture/adder.py"],
                "tool_calls": self._tool_calls(),
                "tokens": {"input": 1200, "output": 350, "totalTokens": 1550},
                "cost_total": 0.0021,
                "artifacts": self._artifacts("/runs/run-json/events.jsonl"),
                "assertion": self._assertion(True),
                "model": "matrix.vars.coder",
                "timestamp": TIMESTAMP,
            },
            "the record must carry the thirteen dimensions verbatim: "
            "tokens lifted from the outcome's three token fields, "
            "cost_total from the outcome, tool_calls and assertion "
            "embedded unmodified, timestamp stored as passed",
        )

    def test_build_print_run_returns_pinned_record(self):
        build = self._get_build()
        record = self._build(
            build,
            config="print",
            artifacts=self._artifacts(jsonl=None),
            changed_files=[],
        )
        self.assertEqual(record["config"], "print")
        self.assertIsNone(
            record["artifacts"]["jsonl"],
            "the print run produces no JSONL stream: artifacts.jsonl "
            "must stay None, not be dropped and not be an empty string",
        )
        self.assertEqual(record["changed_files"], [])

    def test_build_ultrawork_run_returns_pinned_record(self):
        build = self._get_build()
        record = self._build(
            build,
            config="ultrawork",
            artifacts=self._artifacts(jsonl=None),
        )
        self.assertEqual(record["config"], "ultrawork")
        self.assertIsNone(record["artifacts"]["jsonl"])

    def test_build_record_survives_sorted_json_round_trip(self):
        # Behaviour 11's serialization contract: the record is
        # json.dumps(sort_keys=True)-able, i.e. fully JSON-native.
        build = self._get_build()
        record = self._build(build)
        self.assertEqual(
            json.loads(json.dumps(record, sort_keys=True)),
            record,
            "the record must be JSON-native: no Path objects, no sets, "
            "no values json.dumps cannot serialize",
        )

    def test_build_tokens_lifted_from_outcome_not_embedded_wholesale(self):
        build = self._get_build()
        record = self._build(build)
        self.assertEqual(
            record["tokens"],
            {"input": 1200, "output": 350, "totalTokens": 1550},
            "tokens must be exactly the three token fields of the "
            "outcome dict - lifted, not the outcome dict itself",
        )
        self.assertEqual(record["cost_total"], 0.0021)
        self.assertNotIn(
            "outcome",
            record,
            "the outcome dict is a source, not a record field: settled, "
            "aborted and usage_reported stay in the JSONL artifacts, "
            "not in the closed record key set",
        )


class TestCompleted(PirecordTestCase):
    """The verdict field: completed is True iff the process exited 0
    AND the fixture assertion passes - both directions pinned."""

    def test_build_exit_zero_and_assertion_passed_is_completed(self):
        build = self._get_build()
        record = self._build(build)  # exit_code=0, passed=True
        self.assertIs(record["completed"], True)

    def test_build_exit_zero_but_assertion_failed_is_not_completed(self):
        build = self._get_build()
        record = self._build(build, assertion=self._assertion(False))
        self.assertIs(
            record["completed"],
            False,
            "the process exited cleanly but the fixture's assertion "
            "still fails: the run did not complete the task",
        )

    def test_build_assertion_passed_but_exit_nonzero_is_not_completed(self):
        build = self._get_build()
        record = self._build(build, exit_code=1)
        self.assertIs(
            record["completed"],
            False,
            "the fixture was fixed but the process exited non-zero: "
            "a crashed or killed run cannot count as completed",
        )

    def test_build_exit_nonzero_and_assertion_failed_is_not_completed(self):
        build = self._get_build()
        record = self._build(build, exit_code=137, assertion=self._assertion(False))
        self.assertIs(record["completed"], False)

    def test_build_completion_never_depends_on_waited_for_input(self):
        # The host blocks on stdin (behaviour 13's error case): the run
        # is recorded with waited_for_input True, and the verdict field
        # reflects only exit code and assertion.
        build = self._get_build()
        record = self._build(build, waited_for_input=True)
        self.assertIs(record["completed"], True)
        self.assertIs(record["waited_for_input"], True)


class TestConfigValidation(PirecordTestCase):
    """config is closed to the three bake-off configurations."""

    def test_build_rejects_unknown_config_naming_the_field(self):
        build = self._get_build()
        record_error = self._get_record_error()
        with self.assertRaises(record_error) as ctx:
            build("rpc", **dict(
                model="m",
                exit_code=0,
                wall_time_s=1.0,
                waited_for_input=False,
                artifacts=self._artifacts(),
                tool_calls=self._tool_calls(),
                outcome=self._get_outcome(),
                assertion=self._assertion(),
                changed_files=[],
                timestamp=TIMESTAMP,
            ))
        self.assertIn(
            "config",
            str(ctx.exception),
            "the RecordError must name the rejected field 'config' so "
            "the caller knows which argument to fix",
        )

    def test_build_rejects_empty_config_naming_the_field(self):
        build = self._get_build()
        record_error = self._get_record_error()
        with self.assertRaises(record_error) as ctx:
            build("", **dict(
                model="m",
                exit_code=0,
                wall_time_s=1.0,
                waited_for_input=False,
                artifacts=self._artifacts(),
                tool_calls=self._tool_calls(),
                outcome=self._get_outcome(),
                assertion=self._assertion(),
                changed_files=[],
                timestamp=TIMESTAMP,
            ))
        self.assertIn("config", str(ctx.exception))

    def test_build_accepts_each_of_the_three_pinned_configs(self):
        build = self._get_build()
        for config in CONFIG_VALUES:
            with self.subTest(config=config):
                record = build(
                    config,
                    model="m",
                    exit_code=0,
                    wall_time_s=1.0,
                    waited_for_input=False,
                    artifacts=self._artifacts(),
                    tool_calls=self._tool_calls(),
                    outcome=self._get_outcome(),
                    assertion=self._assertion(),
                    changed_files=[],
                    timestamp=TIMESTAMP,
                )
                self.assertEqual(record["config"], config)


class TestMissingDimensions(PirecordTestCase):
    """Error path: any of the five dimensions missing raises
    RecordError naming the field, so a half-recorded run cannot become
    a verdict."""

    # (label, kwargs-override) pairs: each nulls out exactly one
    # dimension. The message must name that field.
    MISSING_CASES = [
        ("tool_calls", dict(tool_calls=None)),
        ("outcome", dict(outcome=None)),
        ("assertion", dict(assertion=None)),
        ("exit_code", dict(exit_code=None)),
        ("changed_files", dict(changed_files=None)),
        ("artifacts missing jsonl key", dict(
            artifacts={
                "stdout": "/s.txt",
                "stderr": "/e.txt",
                "before_digest": "/b.sha256",
                "after_digest": "/a.sha256",
            }
        )),
        (
            "outcome missing a counter key",
            dict(outcome={
                "settled": True,
                "aborted": False,
                "input": 1,
                "output": 1,
                "totalTokens": 2,
                "cost_total": 0.0,
                # usage_reported deliberately absent
            }),
        ),
        (
            "tool_calls missing a counter key",
            dict(tool_calls={
                "attempted": 1,
                "succeeded": 1,
                "failed": 0,
                "unfinished": 0,
                # orphaned deliberately absent
            }),
        ),
    ]

    def test_build_raises_record_error_naming_each_missing_field(self):
        build = self._get_build()
        record_error = self._get_record_error()
        for label, overrides in self.MISSING_CASES:
            with self.subTest(missing=label):
                with self.assertRaises(record_error) as ctx:
                    self._build(build, **overrides)
                message = str(ctx.exception)
                # Every case must name the missing field, so the
                # operator can see which dimension to recover.
                self.assertTrue(
                    label.split()[0] in message,
                    "the RecordError for %r must name the missing "
                    "field %r; got: %s" % (label, label.split()[0], message),
                )

    def test_build_raises_record_error_for_none_artifacts_naming_field(self):
        build = self._get_build()
        record_error = self._get_record_error()
        with self.assertRaises(record_error) as ctx:
            self._build(build, artifacts=None)
        self.assertIn("artifacts", str(ctx.exception))

    def test_build_error_is_bare_record_error_not_a_subclass_mismatch(self):
        # One exception type per module: the half-record guard must be
        # RecordError itself, so the host recipe needs one except.
        build = self._get_build()
        record_error = self._get_record_error()
        with self.assertRaises(record_error):
            self._build(build, tool_calls=None)
        with self.assertRaises(Exception):
            self._build(build, tool_calls=None)
        # And it is the module's own type, not an aliased built-in.
        self._pirecord()
        self.assertIs(type(self._catch_error(build, tool_calls=None)), record_error)

    def _catch_error(self, build, **kwargs):
        try:
            self._build(build, **kwargs)
        except Exception as error:  # noqa: BLE001 - the point is the type
            return error
        self.fail("build did not raise for a missing dimension")

    def test_build_rejects_non_string_timestamp_naming_field(self):
        # The caller passes the ISO-8601 UTC stamp; a non-string means
        # the dimension is missing, not that the format is optional.
        build = self._get_build()
        record_error = self._get_record_error()
        with self.assertRaises(record_error) as ctx:
            self._build(build, timestamp=1761000000)
        self.assertIn("timestamp", str(ctx.exception))


class TestArtifactValidation(PirecordTestCase):
    """The artifacts sub-dict: exactly the five pinned keys, each a
    path string, jsonl the one field allowed to be None."""

    def test_build_rejects_artifacts_with_extra_key(self):
        build = self._get_build()
        record_error = self._get_record_error()
        bad = self._artifacts("/runs/events.jsonl")
        bad["transcript"] = "/runs/transcript.md"
        with self.assertRaises(record_error):
            self._build(build, artifacts=bad)

    def test_build_rejects_artifacts_with_path_object(self):
        # Paths must be serialized to strings by the caller: a Path in
        # the record would break the json.dumps(sort_keys=True)
        # round-trip, and the error must name artifacts.
        build = self._get_build()
        record_error = self._get_record_error()
        bad = self._artifacts()
        bad["stdout"] = Path("/runs/stdout.txt")
        with self.assertRaises(record_error) as ctx:
            self._build(build, artifacts=bad)
        self.assertIn("artifacts", str(ctx.exception))

    def test_build_accepts_artifacts_with_none_jsonl(self):
        build = self._get_build()
        record = self._build(build, artifacts=self._artifacts(jsonl=None))
        self.assertIsNone(record["artifacts"]["jsonl"])

    def test_build_accepts_artifacts_with_string_jsonl(self):
        build = self._get_build()
        record = self._build(
            build, artifacts=self._artifacts("/runs/events.jsonl")
        )
        self.assertEqual(record["artifacts"]["jsonl"], "/runs/events.jsonl")


class TestDimensionVerbatim(PirecordTestCase):
    """The record embeds the dimension sources verbatim: tool_calls,
    the assertion dict and the changed_files list are stored unmodified,
    deletions keeping their ``deleted:`` prefix (behaviour 3), so
    "the model deleted the test" cannot be mistaken for success."""

    def test_build_embeds_tool_calls_verbatim(self):
        build = self._get_build()
        tool_calls = self._tool_calls()
        record = self._build(build)
        self.assertEqual(record["tool_calls"], tool_calls)

    def test_build_embeds_assertion_verbatim_including_stderr(self):
        build = self._get_build()
        assertion = self._assertion(False)
        record = self._build(build, assertion=assertion)
        self.assertEqual(
            record["assertion"],
            {"passed": False, "stderr": "AssertionError"},
            "the assertion dict is embedded whole, stderr included, so "
            "a failed run's traceback is one field away in the record",
        )

    def test_build_embeds_changed_files_with_deleted_prefix_verbatim(self):
        build = self._get_build()
        changed = ["bakeoff_fixture/adder.py", "deleted:tests/test_adder.py"]
        record = self._build(build, changed_files=changed)
        self.assertEqual(
            record["changed_files"],
            changed,
            "the deleted: prefix is change-detection's signal that a "
            "fixture file vanished: it must survive into the record "
            "byte for byte",
        )


if __name__ == "__main__":
    unittest.main()
