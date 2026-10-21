"""Tests for anvilkit.pibakeoff - the bake-off run driver (``run_one``).

Written before the implementation (TDD, ``plans/pi-phase1b-docker.md``,
behaviour 4: "run one configuration"). The production module
``anvilkit.pibakeoff`` does not exist yet, so every test loads it through
``_pibakeoff``, which fails with a clear assertion instead of letting a
collection-time ImportError mask the reason the suite is red.

Design constraint pinned here: no test spawns ``pi`` or Docker. ``run_one``
takes process execution as an **injected runner callable**, and every test
supplies a fake that records its invocation and returns a canned result.

Pinned signature::

    run_one(config, fixture_dir, results_dir, runner, model_id, prompt,
            extension_path, gateway_host, gateway_port, context_window,
            max_tokens, timeout_s, *, timestamp, agent_home=None) -> dict

``config`` is one of ``"print"``, ``"json"``, ``"ultrawork"``. ``results_dir``
is created by ``run_one`` if missing (its parent exists). ``agent_home``
defaults to the user's home (``pathlib.Path.home()``); the in-container
driver passes the container agent home explicitly. ``timestamp`` is the
ISO-8601 UTC stamp stored verbatim in the record (the driver owns the
clock; tests pass a pinned constant so the expected record is fully
deterministic).

Pinned runner contract - the fake's recorded invocation and return value:

invocation (a single dict, one call per ``run_one``)::

    {"argv": List[str], "cwd": str, "stdin": str, "timeout_s": float}

- ``argv``: exactly the ``anvilkit.piargv`` output for that configuration
  (``print_argv`` / ``json_argv`` / ``ultrawork_argv(model_id, prompt,
  extension_path)``);
- ``cwd``: ``str(fixture_dir)`` - the fixture directory, verbatim;
- ``stdin``: ``"/dev/null"``;
- ``timeout_s``: the ``timeout_s`` argument passed to ``run_one``.

result (a dict with exactly these keys)::

    {"exit_code": int, "stdout": str, "stderr": str,
     "wall_time_s": float, "timed_out": bool, "evidence": str}

- ``exit_code`` is always an ``int``; for a timed-out run it is the
  process's termination status (e.g. ``-9`` for a SIGKILL after the
  timeout). It can never be ``None``: ``pirecord.build`` rejects a missing
  exit code and a blocked run still becomes a record;
- ``timed_out`` is the source of the record's ``waited_for_input`` flag;
- ``evidence`` is the driver's evidence string for the blocked run, ``""``
  otherwise.

Pinned ``run_one`` responsibilities (composed from the existing modules,
unchanged):

- ``pifixture.write_fixture(fixture_dir)`` on the fresh fixture directory,
  before the runner call; the record's ``changed_files`` is
  ``pifixture.changed_files`` of the before-digest (taken before the runner
  call) against the fixture tree after it - so a fake that edits
  ``bakeoff_fixture/adder.py`` on disk proves the digest/change-detection
  path end to end;
- the agent-directory models document is written to
  ``<agent_home>/.pi/agent/models.json`` (parent directories created), its
  content exactly ``json.dumps`` of
  ``piargv.models_document(model_id, gateway_port, context_window,
  max_tokens, host=gateway_host)``;
- for config ``"json"`` only: the runner's stdout is drained verbatim to
  ``<results_dir>/events.jsonl`` and parsed with ``pievents.parse``; the
  record's ``tool_calls`` and tokens come from
  ``pievents.tool_calls`` / ``pievents.outcome`` of that stream. For
  ``"print"`` and ``"ultrawork"`` the empty stream is used and the
  ``jsonl`` artifact is ``None``;
- stdout and stderr are captured to ``<results_dir>/stdout`` and
  ``<results_dir>/stderr``;
- a timed-out runner (``timed_out=True``) yields a record with
  ``waited_for_input=True``, ``completed=False``, and the runner's
  ``evidence`` written to ``<results_dir>/evidence.txt`` (the record's
  closed thirteen-key shape has no free-form evidence field, so the
  evidence lands in the results directory next to the artifacts) - never
  an exception;
- the record is exactly what ``pirecord.build`` produces for those
  dimensions.

One exception type: ``BakeoffError`` - raised (naming the value) for an
unknown ``config``; no runner invocation happens in that case.
"""

import importlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Callable, Dict, List, Optional
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import anvilkit.pievents as pievents
import anvilkit.pirecord as pirecord
import anvilkit.piargv as piargv

MODEL_ID = "matrix.vars.coder"
PROMPT = "Fix the adder"
EXTENSION_PATH = "/opt/pi/packages/pi-ultrawork/src/index.ts"
GATEWAY_HOST = "llama-swap"
GATEWAY_PORT = 8080
CONTEXT_WINDOW = 32768
MAX_TOKENS = 4096
TIMEOUT_S = 900.0
TIMESTAMP = "2026-10-21T00:00:00Z"

# The closed thirteen-key record shape, pinned by anvilkit.pirecord.build.
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

# A small hand-built JSON event stream the json-config fake returns as
# stdout: two tool-call ends (one of them orphaned, one matching a start),
# one usage report, no agent_settled.
JSONL_STREAM = "\n".join(
    [
        json.dumps(
            {
                "type": "message_update",
                "usage": {
                    "input": 1200,
                    "output": 350,
                    "totalTokens": 1550,
                    "cost": {"total": 0.0021},
                },
            }
        ),
        json.dumps({"type": "tool_execution_start", "toolCallId": "tc-1"}),
        json.dumps({"type": "tool_execution_end", "toolCallId": "tc-1"}),
        json.dumps(
            {"type": "tool_execution_end", "toolCallId": "tc-2", "isError": True}
        ),
    ]
) + "\n"


class PibakeoffTestCase(unittest.TestCase):
    def _pibakeoff(self):
        """Import anvilkit.pibakeoff, failing clearly if the module is absent."""
        spec = importlib.util.find_spec("anvilkit.pibakeoff")
        self.assertIsNotNone(
            spec,
            "anvilkit.pibakeoff cannot be imported; the bake-off run "
            "driver (behaviour 4) has not been implemented yet",
        )
        return importlib.import_module("anvilkit.pibakeoff")

    def _get_run_one(self) -> Callable:
        """Fetch ``anvilkit.pibakeoff.run_one``, failing clearly if absent."""
        pibakeoff = self._pibakeoff()
        run_one = getattr(pibakeoff, "run_one", None)
        self.assertTrue(
            callable(run_one),
            "anvilkit.pibakeoff.run_one is not callable; the run-one "
            "driver (behaviour 4) has not been implemented yet",
        )
        return run_one

    def _get_bakeoff_error(self):
        """Fetch ``anvilkit.pibakeoff.BakeoffError``, failing clearly if absent."""
        pibakeoff = self._pibakeoff()
        bakeoff_error = getattr(pibakeoff, "BakeoffError", None)
        self.assertTrue(
            isinstance(bakeoff_error, type) and issubclass(bakeoff_error, Exception),
            "anvilkit.pibakeoff.BakeoffError is not an exception type; the "
            "unknown-config guard (behaviour 4) has not been implemented yet",
        )
        return bakeoff_error

    def _fake(self, result: Optional[Dict] = None, edit: bool = False) -> Callable:
        """A fake runner recording its invocation and returning a canned result.

        ``edit=True`` makes the fake simulate a successful pi edit: it
        rewrites ``<fixture>/bakeoff_fixture/adder.py`` to the correct
        implementation, so the before/after-digest path and the fixture
        assertion turn green end to end.
        """

        def fake_runner(invocation: Dict) -> Dict:
            fake_runner._calls.append(dict(invocation))
            if edit:
                fixture = Path(invocation["cwd"])
                adder = fixture / "bakeoff_fixture" / "adder.py"
                adder.write_text(
                    adder.read_text(encoding="utf-8").replace(
                        "return a - b", "return a + b"
                    ),
                    encoding="utf-8",
                )
            if result is not None:
                return dict(result)
            return PibakeoffTestCase._default_result()

        fake_runner._calls = []
        return fake_runner

    @staticmethod
    def _default_result() -> Dict:
        """A clean, successful runner result (the print/ultrawork baseline)."""
        return {
            "exit_code": 0,
            "stdout": "done\n",
            "stderr": "",
            "wall_time_s": 2.5,
            "timed_out": False,
            "evidence": "",
        }

    def _fresh(self) -> Dict[str, Path]:
        """A per-test temp tree: agent home, results dir, fixture dir."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        return {
            "root": root,
            "agent_home": root / "agent-home",
            "results": root / "results",
            "fixture": root / "fixture",
        }

    def _run(self, run_one, dirs, config, fake, **overrides):
        """Call run_one with the standard inputs; ``overrides`` replace one."""
        kwargs = dict(
            config=config,
            fixture_dir=dirs["fixture"],
            results_dir=dirs["results"],
            runner=fake,
            model_id=MODEL_ID,
            prompt=PROMPT,
            extension_path=EXTENSION_PATH,
            gateway_host=GATEWAY_HOST,
            gateway_port=GATEWAY_PORT,
            context_window=CONTEXT_WINDOW,
            max_tokens=MAX_TOKENS,
            timeout_s=TIMEOUT_S,
            timestamp=TIMESTAMP,
            agent_home=dirs["agent_home"],
        )
        kwargs.update(overrides)
        return run_one(**kwargs)

    @staticmethod
    def _expected_record(
        *,
        config: str,
        dirs: Dict[str, Path],
        exit_code: int,
        wall_time_s: float,
        waited_for_input: bool,
        changed: List[str],
        passed: bool,
        events: List[dict],
        jsonl: Optional[str],
    ) -> Dict:
        """The record pirecord.build must produce for these dimensions."""
        results = dirs["results"]
        outcome = pievents.outcome(events)
        return pirecord.build(
            config,
            model=MODEL_ID,
            exit_code=exit_code,
            wall_time_s=wall_time_s,
            waited_for_input=waited_for_input,
            artifacts={
                "stdout": str(results / "stdout"),
                "stderr": str(results / "stderr"),
                "jsonl": jsonl,
                "before_digest": str(results / "before.sha256"),
                "after_digest": str(results / "after.sha256"),
            },
            tool_calls=pievents.tool_calls(events),
            outcome=outcome,
            assertion={"passed": passed, "stderr": ""},
            changed_files=changed,
            timestamp=TIMESTAMP,
        )

    def _assert_expected(self, record, **expected_kwargs):
        """Full-shape equality, masking the assertion's stderr.

        The fixture assertion's stderr is the real subprocess traceback,
        whose exact text is interpreter-version dependent; the driver
        passes it through verbatim, so it is asserted as a ``str`` plus
        the pinned ``passed`` value, not as bytes.
        """
        self.assertEqual(RECORD_KEYS, set(record))
        expected = self._expected_record(**expected_kwargs)
        actual = dict(record)
        actual_assertion = actual.pop("assertion")
        passed = expected.pop("assertion")["passed"]
        self.assertEqual(expected, actual)
        self.assertEqual(passed, actual_assertion["passed"])
        self.assertIsInstance(actual_assertion["stderr"], str)


class TestFixtureLifecycle(PibakeoffTestCase):
    """run_one writes the fixture, invokes the pinned argv once with
    stdin /dev/null and cwd = fixture dir, and detects the fake's on-disk
    edit through the before/after digests."""

    def _assert_invocation(self, fake, dirs, argv):
        self.assertEqual(1, len(fake._calls))
        self.assertEqual(
            {
                "argv": argv,
                "cwd": str(dirs["fixture"]),
                "stdin": "/dev/null",
                "timeout_s": TIMEOUT_S,
            },
            fake._calls[0],
        )

    def test_run_one_json_fixture_lifecycle_and_changed_files(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake(
            result={
                "exit_code": 0,
                "stdout": JSONL_STREAM,
                "stderr": "",
                "wall_time_s": 1.25,
                "timed_out": False,
                "evidence": "",
            },
            edit=True,
        )
        record = self._run(run_one, dirs, "json", fake)
        self._assert_invocation(
            fake, dirs, piargv.json_argv(MODEL_ID, PROMPT)
        )
        # The fake's on-disk edit is detected end to end: exactly the one
        # rewritten file, nothing else, proving the digests bracketed the call.
        self.assertEqual(["bakeoff_fixture/adder.py"], record["changed_files"])

    def test_run_one_print_argv_and_no_edits(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake()
        record = self._run(run_one, dirs, "print", fake)
        self._assert_invocation(
            fake, dirs, piargv.print_argv(MODEL_ID, PROMPT)
        )
        self.assertEqual([], record["changed_files"])

    def test_run_one_ultrawork_argv_with_extension(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake()
        record = self._run(run_one, dirs, "ultrawork", fake)
        self._assert_invocation(
            fake, dirs, piargv.ultrawork_argv(MODEL_ID, PROMPT, EXTENSION_PATH)
        )
        self.assertEqual([], record["changed_files"])


class TestModelsDocument(PibakeoffTestCase):
    """The agent-directory models document lands at the pinned path with
    the exact pinned content."""

    @staticmethod
    def _expected_models_content() -> str:
        return json.dumps(
            piargv.models_document(
                MODEL_ID,
                GATEWAY_PORT,
                CONTEXT_WINDOW,
                MAX_TOKENS,
                host=GATEWAY_HOST,
            )
        )

    def test_run_one_writes_models_document_at_pinned_path(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        self._run(run_one, dirs, "print", self._fake())
        models_path = dirs["agent_home"] / ".pi" / "agent" / "models.json"
        self.assertTrue(models_path.is_file())
        self.assertEqual(
            self._expected_models_content(),
            models_path.read_text(encoding="utf-8"),
        )

    def test_run_one_defaults_agent_home_to_user_home(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        with mock.patch("pathlib.Path.home", return_value=dirs["agent_home"]):
            self._run(run_one, dirs, "print", self._fake(), agent_home=None)
        models_path = dirs["agent_home"] / ".pi" / "agent" / "models.json"
        self.assertTrue(models_path.is_file())
        self.assertEqual(
            self._expected_models_content(),
            models_path.read_text(encoding="utf-8"),
        )


class TestJsonDrain(PibakeoffTestCase):
    """For config json the runner's stdout is drained to events.jsonl and
    parsed; the record's tool calls and tokens come from that stream."""

    def test_run_one_json_drains_stdout_to_events_jsonl(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        events = pievents.parse(JSONL_STREAM)["events"]
        fake = self._fake(
            result={
                "exit_code": 0,
                "stdout": JSONL_STREAM,
                "stderr": "",
                "wall_time_s": 1.25,
                "timed_out": False,
                "evidence": "",
            },
            edit=True,
        )
        record = self._run(run_one, dirs, "json", fake)
        events_path = dirs["results"] / "events.jsonl"
        self.assertTrue(events_path.is_file())
        self.assertEqual(JSONL_STREAM, events_path.read_text(encoding="utf-8"))
        # The record's model-work dimensions are the stream's, not defaults.
        self.assertEqual(pievents.tool_calls(events), record["tool_calls"])
        self.assertEqual(
            pievents.outcome(events)["totalTokens"],
            record["tokens"]["totalTokens"],
        )
        self._assert_expected(
            record,
            config="json",
            dirs=dirs,
            exit_code=0,
            wall_time_s=1.25,
            waited_for_input=False,
            changed=["bakeoff_fixture/adder.py"],
            passed=True,
            events=events,
            jsonl=str(events_path),
        )

    def test_run_one_print_uses_empty_stream_and_null_jsonl(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake()
        record = self._run(run_one, dirs, "print", fake)
        self.assertIsNone(record["artifacts"]["jsonl"])
        self.assertEqual(pievents.tool_calls([]), record["tool_calls"])
        self._assert_expected(
            record,
            config="print",
            dirs=dirs,
            exit_code=0,
            wall_time_s=2.5,
            waited_for_input=False,
            changed=[],
            passed=False,
            events=[],
            jsonl=None,
        )

    def test_run_one_ultrawork_uses_empty_stream_and_null_jsonl(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake()
        record = self._run(run_one, dirs, "ultrawork", fake)
        self.assertIsNone(record["artifacts"]["jsonl"])
        self.assertEqual(pievents.tool_calls([]), record["tool_calls"])
        self._assert_expected(
            record,
            config="ultrawork",
            dirs=dirs,
            exit_code=0,
            wall_time_s=2.5,
            waited_for_input=False,
            changed=[],
            passed=False,
            events=[],
            jsonl=None,
        )


class TestRecord(PibakeoffTestCase):
    """The returned dict is exactly what pirecord.build produces for the
    composed dimensions, including the five artifact paths."""

    def test_run_one_success_record_matches_pirecord_build(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake()
        record = self._run(run_one, dirs, "print", fake)
        results = dirs["results"]
        # The artifacts exist at the pinned paths and carry the runner's streams.
        self.assertEqual(
            "done\n", (results / "stdout").read_text(encoding="utf-8")
        )
        self.assertEqual("", (results / "stderr").read_text(encoding="utf-8"))
        self._assert_expected(
            record,
            config="print",
            dirs=dirs,
            exit_code=0,
            wall_time_s=2.5,
            waited_for_input=False,
            changed=[],
            passed=False,
            events=[],
            jsonl=None,
        )
        self.assertEqual(record["artifacts"]["stdout"], str(results / "stdout"))
        self.assertEqual(record["artifacts"]["stderr"], str(results / "stderr"))
        self.assertEqual(record["artifacts"]["before_digest"], str(results / "before.sha256"))
        self.assertEqual(record["artifacts"]["after_digest"], str(results / "after.sha256"))
        self.assertEqual(record["model"], MODEL_ID)
        self.assertEqual(record["timestamp"], TIMESTAMP)

    def test_run_one_success_completed_is_true_when_fixture_turns_green(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake(
            result={
                "exit_code": 0,
                "stdout": JSONL_STREAM,
                "stderr": "",
                "wall_time_s": 1.25,
                "timed_out": False,
                "evidence": "",
            },
            edit=True,
        )
        record = self._run(run_one, dirs, "json", fake)
        self.assertTrue(record["completed"])
        self.assertTrue(record["assertion"]["passed"])


class TestBlockedRun(PibakeoffTestCase):
    """A runner that never returns output within the timeout yields a
    record with waited_for_input True and the evidence written out -
    never an exception."""

    def test_run_one_timed_out_runner_records_evidence_not_exception(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        partial_stdout = json.dumps(
            {"type": "tool_execution_start", "toolCallId": "tc-1"}
        )
        evidence = "pi blocked on stdin with no output for 900.0s"
        fake = self._fake(
            result={
                "exit_code": -9,
                "stdout": partial_stdout,
                "stderr": "",
                "wall_time_s": 900.0,
                "timed_out": True,
                "evidence": evidence,
            }
        )
        record = self._run(run_one, dirs, "json", fake)
        self.assertTrue(record["waited_for_input"])
        self.assertFalse(record["completed"])
        self.assertEqual(-9, record["exit_code"])
        self.assertEqual(900.0, record["wall_time_s"])
        self.assertEqual([], record["changed_files"])
        # The evidence lands in the results directory, not the closed record.
        evidence_path = dirs["results"] / "evidence.txt"
        self.assertTrue(evidence_path.is_file())
        self.assertEqual(evidence, evidence_path.read_text(encoding="utf-8"))
        # Partial output is still captured.
        self.assertEqual(
            partial_stdout, (dirs["results"] / "stdout").read_text(encoding="utf-8")
        )
        # A blocked json run still records the partial stream's dimensions.
        self.assertEqual(
            pievents.tool_calls(pievents.parse(partial_stdout)["events"]),
            record["tool_calls"],
        )


class TestErrors(PibakeoffTestCase):
    """An unknown configuration value raises BakeoffError naming it, and
    no runner invocation happens."""

    def test_run_one_unknown_config_raises_bakeoff_error(self):
        run_one = self._get_run_one()
        bakeoff_error = self._get_bakeoff_error()
        dirs = self._fresh()
        fake = self._fake()
        with self.assertRaises(bakeoff_error) as ctx:
            self._run(run_one, dirs, "stream", fake)
        self.assertIn("stream", str(ctx.exception))
        self.assertEqual([], fake._calls)


if __name__ == "__main__":
    unittest.main()
