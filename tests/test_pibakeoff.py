"""Tests for anvilkit.pi.pibakeoff - the bake-off run driver (``run_one``).

Written before the implementation (TDD, ``plans/pi-phase1b-docker.md``,
behaviour 4: "run one configuration"). The production module
``anvilkit.pi.pibakeoff`` does not exist yet, so every test loads it through
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

- ``argv``: exactly the ``anvilkit.pi.piargv`` output for that configuration
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

``TestRunAll`` pins the companion driver (behaviour 5: "run all and
report")::

    run_all(base_dir, runner, model_id, prompt, extension_path,
            gateway_host, gateway_port, context_window, max_tokens,
            timeout_s, *, timestamp, agent_home=None) -> (records, table)

- the three configurations run through ``run_one`` in the fixed order
  ``print``, ``json``, ``ultrawork`` (the table renders in input order),
  each with ``fixture_dir = base_dir/<config>/fixture`` and
  ``results_dir = base_dir/<config>/results``; ``run_all`` creates
  ``base_dir`` and the per-config directories;
- after each run, ``<results_dir>/record.json`` exists with content
  exactly ``json.dumps(record, sort_keys=True)``;
- ``<base_dir>/table.md`` exists with content exactly
  ``pirecord.render_table(records)`` (records in run order), and the
  returned ``table`` is that same string;
- a runner exception for one configuration does not abort the other two:
  the failed configuration still gets a record - ``waited_for_input``
  True, ``exit_code`` 1, ``wall_time_s`` 0.0, ``changed_files`` [], the
  empty-stream tool-call counters and outcome, and the exception's
  message (``str(exc)``) as the assertion's stderr - so the table still
  renders one row per configuration;
- the models document at ``<agent_home>/.pi/agent/models.json`` carries
  exactly ``json.dumps`` of ``piargv.models_document`` for the gateway,
  and a pre-existing document does not make ``run_all`` fail. ``run_one``
  already rewrites the document identically on every call, so the pinned
  contract is content-idempotent, not a write count.

``TestSubprocessRunner`` pins the companion seam (behaviour 7: "real
subprocess runner")::

    subprocess_runner(spec) -> result

- a plain module-level function taking exactly one spec dict
  (``{"argv": List[str], "cwd": str, "stdin": str, "timeout_s": float}``)
  and returning exactly one result dict with exactly the six
  runner-contract keys (``exit_code``, ``stdout``, ``stderr``,
  ``wall_time_s``, ``timed_out``, ``evidence``) - no more, no less;
- it executes the ``argv`` list with stdin from ``/dev/null`` in ``cwd``
  and drains stdout continuously, so a full pipe buffer cannot stall the
  child; on success ``timed_out`` is ``False`` and ``evidence`` ``""``;
- a run still blocked after ``timeout_s`` is killed (SIGKILL) and
  reported, never raised: ``timed_out`` ``True``, ``exit_code`` the
  pinned sentinel ``-9`` (subprocess's negative-signal convention, the
  same example this file's runner-contract docstring already uses),
  ``evidence`` a non-empty string containing the substring
  ``"timeout"`` and at least one digit (the elapsed seconds), and the
  output that did arrive before the kill present in ``stdout``;
- a spec missing ``timeout_s`` raises ``BakeoffError`` naming the key,
  before any process is spawned;
- an optional ``spec["env"]`` dict is merged over ``os.environ`` for the
  child (``plans/pi-phase2-approval.md``, behaviour 4: "runner environment
  overlay"), so a key the overlay names carries the child's value while
  every other parent variable survives; an absent or ``None`` ``env``
  inherits the parent environment unchanged; a non-dict ``env`` raises
  ``BakeoffError`` naming the key, before any process is spawned.

These tests run real system binaries (``/bin/echo``, ``/bin/sh -c``,
``/bin/sleep``) - no ``pi``, no mocks - and are bounded: each test under
~2 s, the class under ~5 s, so they are CI-safe.

``TestMain`` pins the in-container entrypoint (behaviour 8: "entrypoint
and compose wiring")::

    main(runner=None) -> int

- ``main`` returns the exit code and never calls ``sys.exit`` itself -
  the module's ``__main__`` guard does, pinned as source text: the
  module's last statement is ``sys.exit(main())`` under ``if __name__ ==
  "__main__":``, and it is the only ``sys.exit`` in the module;
- the gateway host and port come from the environment: a missing or
  empty ``PI_GATEWAY_HOST``/``PI_GATEWAY_PORT`` raises ``BakeoffError``
  naming the variable, and a non-numeric port raises ``BakeoffError``
  too - in every case before ``run_all`` is reached;
- the model id and context window come from
  ``anvilkit.config.read_models`` of the ``PI_CONFIG_PATH`` file (default
  the module constant ``_DEFAULT_CONFIG_PATH == "/app/config.yaml"``,
  the read-only bind the compose service mounts); an unreadable file
  raises ``anvilkit.config``'s ``ConfigError`` unwrapped;
- ``max_tokens``, the per-run timeout and the task prompt are module
  constants: ``BAKEOFF_MAX_TOKENS == 4096``, ``BAKEOFF_TIMEOUT_S ==
  600.0``, ``BAKEOFF_PROMPT`` (the phase-1 trivial task prompt,
  verbatim); the ultrawork extension path is
  ``<npm_root>/pi-ultrawork/src/index.ts`` with ``npm_root`` defaulting
  to the module constant ``_DEFAULT_NPM_ROOT ==
  "/usr/local/lib/node_modules"``;
- results land in ``PI_RESULTS_DIR`` (default the module constant
  ``_DEFAULT_RESULTS_DIR == "/workspace/results"``), passed to
  ``run_all`` as a ``Path``;
- an injected ``runner`` is handed to ``run_all`` verbatim; when
  ``runner`` is ``None`` the default is the module's own
  ``subprocess_runner`` (identity, not equality);
- ``main`` supplies its own ``timestamp`` (ISO-8601 UTC,
  ``YYYY-MM-DDTHH:MM:SSZ``) and passes ``agent_home=None`` (the
  container default);
- a NO-GO table is a successful run: the exit code is 0 either way.
"""

import importlib
import importlib.util
import inspect
import json
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import anvilkit.config as piconfig
from anvilkit.pi import pievents as pievents
from anvilkit.pi import pirecord as pirecord
from anvilkit.pi import piargv as piargv

MODEL_ID = "matrix.vars.coder"
PROMPT = "Fix the adder"
EXTENSION_PATH = "/opt/pi/packages/pi-ultrawork/src/index.ts"
GATEWAY_HOST = "llama-swap"
GATEWAY_PORT = 8080
CONTEXT_WINDOW = 32768
MAX_TOKENS = 4096
TIMEOUT_S = 900.0
TIMESTAMP = "2026-10-21T00:00:00Z"

# The closed thirteen-key record shape, pinned by anvilkit.pi.pirecord.build.
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
        """Import anvilkit.pi.pibakeoff, failing clearly if the module is absent."""
        spec = importlib.util.find_spec("anvilkit.pi.pibakeoff")
        self.assertIsNotNone(
            spec,
            "anvilkit.pi.pibakeoff cannot be imported; the bake-off run "
            "driver (behaviour 4) has not been implemented yet",
        )
        return importlib.import_module("anvilkit.pi.pibakeoff")

    def _get_run_one(self) -> Callable:
        """Fetch ``anvilkit.pi.pibakeoff.run_one``, failing clearly if absent."""
        pibakeoff = self._pibakeoff()
        run_one = getattr(pibakeoff, "run_one", None)
        self.assertTrue(
            callable(run_one),
            "anvilkit.pi.pibakeoff.run_one is not callable; the run-one "
            "driver (behaviour 4) has not been implemented yet",
        )
        return run_one

    def _get_bakeoff_error(self):
        """Fetch ``anvilkit.pi.pibakeoff.BakeoffError``, failing clearly if absent."""
        pibakeoff = self._pibakeoff()
        bakeoff_error = getattr(pibakeoff, "BakeoffError", None)
        self.assertTrue(
            isinstance(bakeoff_error, type) and issubclass(bakeoff_error, Exception),
            "anvilkit.pi.pibakeoff.BakeoffError is not an exception type; the "
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


# The fixed run order for run_all (behaviour 5): the table renders in
# input order, so the order is part of the observable contract.
RUN_ALL_CONFIGS = ("print", "json", "ultrawork")

# The deterministic fake's canned result per configuration: a function of
# the argv it receives, so every config's record is predictable. json gets
# the JSON event stream and turns the fixture green; print also turns the
# fixture green (so the success table is PARTIAL, not GO); ultrawork stays
# red.
_RUN_ALL_RESULTS = {
    "print": {
        "exit_code": 0,
        "stdout": "print done\n",
        "stderr": "",
        "wall_time_s": 2.5,
        "timed_out": False,
        "evidence": "",
    },
    "json": {
        "exit_code": 0,
        "stdout": JSONL_STREAM,
        "stderr": "",
        "wall_time_s": 1.25,
        "timed_out": False,
        "evidence": "",
    },
    "ultrawork": {
        "exit_code": 0,
        "stdout": "ultrawork done\n",
        "stderr": "",
        "wall_time_s": 3.75,
        "timed_out": False,
        "evidence": "",
    },
}


def _expected_models_content() -> str:
    """The exact models-document content run_all must leave on disk."""
    return json.dumps(
        piargv.models_document(
            MODEL_ID,
            GATEWAY_PORT,
            CONTEXT_WINDOW,
            MAX_TOKENS,
            host=GATEWAY_HOST,
        )
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


class TestRunAll(PibakeoffTestCase):
    """run_all drives all three configurations end to end and reports
    (behaviour 5: "run all and report")."""

    def _get_run_all(self) -> Callable:
        """Fetch ``anvilkit.pi.pibakeoff.run_all``, failing clearly if absent."""
        pibakeoff = self._pibakeoff()
        run_all = getattr(pibakeoff, "run_all", None)
        self.assertTrue(
            callable(run_all),
            "anvilkit.pi.pibakeoff.run_all is not callable; the run-all "
            "driver (behaviour 5) has not been implemented yet",
        )
        return run_all

    def _all_fake(self, fail_on: Optional[str] = None) -> Callable:
        """A deterministic fake runner keyed on the argv it receives.

        The configuration is recovered from the argv tokens (``--mode``
        marks json, ``-e`` marks ultrawork, neither marks print) so the
        fake's behaviour is a pure function of its input. ``print`` and
        ``json`` rewrite the fixture's adder to the correct
        implementation (turning the assertion green); ``ultrawork``
        leaves it red. ``fail_on`` makes the fake raise ``OSError`` for
        that configuration, simulating a runner that blows up mid-run.
        """

        def fake_runner(invocation: Dict) -> Dict:
            fake_runner._calls.append(dict(invocation))
            argv = invocation["argv"]
            if argv[1] == "--mode":
                config = "json"
            elif "-e" in argv:
                config = "ultrawork"
            else:
                config = "print"
            if fail_on is not None and config == fail_on:
                raise OSError("boom-" + config)
            if config in ("print", "json"):
                adder = Path(invocation["cwd"]) / "bakeoff_fixture" / "adder.py"
                adder.write_text(
                    adder.read_text(encoding="utf-8").replace(
                        "return a - b", "return a + b"
                    ),
                    encoding="utf-8",
                )
            return dict(_RUN_ALL_RESULTS[config])

        fake_runner._calls = []
        return fake_runner

    def _call_run_all(self, run_all, base_dir, dirs, fake):
        """Call run_all with the standard inputs; the pinned call shape."""
        return run_all(
            base_dir,
            fake,
            MODEL_ID,
            PROMPT,
            EXTENSION_PATH,
            GATEWAY_HOST,
            GATEWAY_PORT,
            CONTEXT_WINDOW,
            MAX_TOKENS,
            TIMEOUT_S,
            timestamp=TIMESTAMP,
            agent_home=dirs["agent_home"],
        )

    @staticmethod
    def _expected_record(
        config: str,
        base_dir: Path,
        *,
        exit_code: int,
        wall_time_s: float,
        changed: List[str],
        passed: bool,
        events: List[dict],
        jsonl: Optional[str],
    ) -> Dict:
        """The record pirecord.build must produce for a run-all config."""
        results = base_dir / config / "results"
        return pirecord.build(
            config,
            model=MODEL_ID,
            exit_code=exit_code,
            wall_time_s=wall_time_s,
            waited_for_input=False,
            artifacts={
                "stdout": str(results / "stdout"),
                "stderr": str(results / "stderr"),
                "jsonl": jsonl,
                "before_digest": str(results / "before.sha256"),
                "after_digest": str(results / "after.sha256"),
            },
            tool_calls=pievents.tool_calls(events),
            outcome=pievents.outcome(events),
            assertion={"passed": passed, "stderr": ""},
            changed_files=changed,
            timestamp=TIMESTAMP,
        )

    @staticmethod
    def _failure_record(config: str, base_dir: Path, message: str) -> Dict:
        """The pinned record for a configuration whose runner raised.

        The exception's message lands as the assertion's stderr (the
        record's closed thirteen-key shape has no free-form evidence
        field); everything else is the no-measurement baseline: a
        non-zero sentinel exit code, zero wall time, no changed files,
        the empty-stream counters and outcome.
        """
        results = base_dir / config / "results"
        return pirecord.build(
            config,
            model=MODEL_ID,
            exit_code=1,
            wall_time_s=0.0,
            waited_for_input=True,
            artifacts={
                "stdout": str(results / "stdout"),
                "stderr": str(results / "stderr"),
                "jsonl": None,
                "before_digest": str(results / "before.sha256"),
                "after_digest": str(results / "after.sha256"),
            },
            tool_calls=pievents.tool_calls([]),
            outcome=pievents.outcome([]),
            assertion={"passed": False, "stderr": message},
            changed_files=[],
            timestamp=TIMESTAMP,
        )

    def _assert_record(self, record, expected):
        """Full-shape equality, masking the assertion's stderr the way
        the run_one tests do (its exact text is interpreter-dependent)."""
        self.assertEqual(RECORD_KEYS, set(record))
        actual = dict(record)
        actual_assertion = actual.pop("assertion")
        expected = dict(expected)
        expected_assertion = expected.pop("assertion")
        self.assertEqual(expected, actual)
        self.assertEqual(expected_assertion["passed"], actual_assertion["passed"])
        self.assertIsInstance(actual_assertion["stderr"], str)

    def test_run_all_invokes_runner_once_per_config_in_fixed_order(self):
        run_all = self._get_run_all()
        dirs = self._fresh()
        base_dir = dirs["results"]
        fake = self._all_fake()
        records, _ = self._call_run_all(run_all, base_dir, dirs, fake)
        # Exactly three runner invocations, one per configuration, in the
        # pinned order, each against its own per-config fixture directory.
        self.assertEqual(3, len(fake._calls))
        expected_argv = [
            piargv.print_argv(MODEL_ID, PROMPT),
            piargv.json_argv(MODEL_ID, PROMPT),
            piargv.ultrawork_argv(MODEL_ID, PROMPT, EXTENSION_PATH),
        ]
        for index, (config, argv) in enumerate(zip(RUN_ALL_CONFIGS, expected_argv)):
            self.assertEqual(
                {
                    "argv": argv,
                    "cwd": str(base_dir / config / "fixture"),
                    "stdin": "/dev/null",
                    "timeout_s": TIMEOUT_S,
                },
                fake._calls[index],
            )
        self.assertEqual(
            [record["config"] for record in records], list(RUN_ALL_CONFIGS)
        )

    def test_run_all_writes_record_json_sort_keys_per_config(self):
        run_all = self._get_run_all()
        dirs = self._fresh()
        base_dir = dirs["results"]
        fake = self._all_fake()
        records, _ = self._call_run_all(run_all, base_dir, dirs, fake)
        for config, record in zip(RUN_ALL_CONFIGS, records):
            record_path = base_dir / config / "results" / "record.json"
            self.assertTrue(record_path.is_file())
            self.assertEqual(
                json.dumps(record, sort_keys=True),
                record_path.read_text(encoding="utf-8"),
            )

    def test_run_all_records_match_pirecord_build_per_config(self):
        run_all = self._get_run_all()
        dirs = self._fresh()
        base_dir = dirs["results"]
        fake = self._all_fake()
        records, _ = self._call_run_all(run_all, base_dir, dirs, fake)
        json_events = pievents.parse(JSONL_STREAM)["events"]
        expected = {
            "print": self._expected_record(
                "print",
                base_dir,
                exit_code=0,
                wall_time_s=2.5,
                changed=["bakeoff_fixture/adder.py"],
                passed=True,
                events=[],
                jsonl=None,
            ),
            "json": self._expected_record(
                "json",
                base_dir,
                exit_code=0,
                wall_time_s=1.25,
                changed=["bakeoff_fixture/adder.py"],
                passed=True,
                events=json_events,
                jsonl=str(base_dir / "json" / "results" / "events.jsonl"),
            ),
            "ultrawork": self._expected_record(
                "ultrawork",
                base_dir,
                exit_code=0,
                wall_time_s=3.75,
                changed=[],
                passed=False,
                events=[],
                jsonl=None,
            ),
        }
        for record in records:
            self._assert_record(record, expected[record["config"]])

    def test_run_all_writes_table_md_and_returns_same_table(self):
        run_all = self._get_run_all()
        dirs = self._fresh()
        base_dir = dirs["results"]
        fake = self._all_fake()
        records, table = self._call_run_all(run_all, base_dir, dirs, fake)
        table_path = base_dir / "table.md"
        self.assertTrue(table_path.is_file())
        rendered = pirecord.render_table(records)
        # The table is written to table.md AND returned, byte-identical.
        self.assertEqual(rendered, table)
        self.assertEqual(rendered, table_path.read_text(encoding="utf-8"))
        # print and json turned green, ultrawork stayed red: PARTIAL, in
        # run order.
        self.assertTrue(table.endswith("PARTIAL (2 of 3 completed)"))

    def test_run_all_failed_config_does_not_abort_others(self):
        run_all = self._get_run_all()
        dirs = self._fresh()
        base_dir = dirs["results"]
        fake = self._all_fake(fail_on="json")
        records, table = self._call_run_all(run_all, base_dir, dirs, fake)
        # All three invocations happened; the order is unchanged.
        self.assertEqual(3, len(fake._calls))
        self.assertEqual(
            [record["config"] for record in records], list(RUN_ALL_CONFIGS)
        )
        print_record, json_record, ultrawork_record = records
        # The sibling configurations still built normal records.
        self._assert_record(
            print_record,
            self._expected_record(
                "print",
                base_dir,
                exit_code=0,
                wall_time_s=2.5,
                changed=["bakeoff_fixture/adder.py"],
                passed=True,
                events=[],
                jsonl=None,
            ),
        )
        self._assert_record(
            ultrawork_record,
            self._expected_record(
                "ultrawork",
                base_dir,
                exit_code=0,
                wall_time_s=3.75,
                changed=[],
                passed=False,
                events=[],
                jsonl=None,
            ),
        )
        # The failed configuration's record is still built, with the
        # exception message as the assertion's stderr.
        expected_failure = self._failure_record("json", base_dir, "boom-json")
        self._assert_record(json_record, expected_failure)
        self.assertEqual("boom-json", json_record["assertion"]["stderr"])
        self.assertFalse(json_record["completed"])
        # Its record.json is still written.
        record_path = base_dir / "json" / "results" / "record.json"
        self.assertTrue(record_path.is_file())
        self.assertEqual(
            json.dumps(json_record, sort_keys=True),
            record_path.read_text(encoding="utf-8"),
        )
        # The table still renders one row per configuration.
        self.assertIn("| print |", table)
        self.assertIn("| json |", table)
        self.assertIn("| ultrawork |", table)
        self.assertTrue(table.endswith("PARTIAL (1 of 3 completed)"))

    def test_run_all_writes_models_document_with_pinned_content(self):
        run_all = self._get_run_all()
        dirs = self._fresh()
        self._call_run_all(run_all, dirs["results"], dirs, self._all_fake())
        models_path = dirs["agent_home"] / ".pi" / "agent" / "models.json"
        self.assertTrue(models_path.is_file())
        self.assertEqual(
            _expected_models_content(), models_path.read_text(encoding="utf-8")
        )

    def test_run_all_tolerates_preexisting_models_document(self):
        run_all = self._get_run_all()
        dirs = self._fresh()
        models_path = dirs["agent_home"] / ".pi" / "agent" / "models.json"
        models_path.parent.mkdir(parents=True)
        models_path.write_text(_expected_models_content(), encoding="utf-8")
        self._call_run_all(run_all, dirs["results"], dirs, self._all_fake())
        self.assertEqual(
            _expected_models_content(), models_path.read_text(encoding="utf-8")
        )


# The six runner-contract keys, pinned exactly for the real runner: the
# result of ``subprocess_runner`` is a dict with precisely these keys.
_SUBPROCESS_RESULT_KEYS = {
    "exit_code",
    "stdout",
    "stderr",
    "wall_time_s",
    "timed_out",
    "evidence",
}


class TestSubprocessRunner(PibakeoffTestCase):
    """subprocess_runner - the real subprocess implementation of the runner
    contract (behaviour 7). Real system binaries, no pi, no mocks."""

    def _get_subprocess_runner(self) -> Callable:
        """Fetch ``anvilkit.pi.pibakeoff.subprocess_runner``, failing clearly if absent."""
        pibakeoff = self._pibakeoff()
        subprocess_runner = getattr(pibakeoff, "subprocess_runner", None)
        self.assertTrue(
            callable(subprocess_runner),
            "anvilkit.pi.pibakeoff.subprocess_runner is not callable; the real "
            "subprocess runner (behaviour 7) has not been implemented yet",
        )
        return subprocess_runner

    def _tmpdir(self) -> Path:
        """A per-test temporary directory, cleaned up automatically."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def _spec(self, argv: List[str], cwd: Path, timeout_s: float = 10.0) -> Dict[str, Any]:
        """The pinned invocation shape for subprocess_runner."""
        return {
            "argv": argv,
            "cwd": str(cwd),
            "stdin": "/dev/null",
            "timeout_s": timeout_s,
        }

    def test_subprocess_runner_basic_execution_contract(self):
        subprocess_runner = self._get_subprocess_runner()
        cwd = self._tmpdir()
        result = subprocess_runner(self._spec(["/bin/echo", "hello"], cwd))
        # Exactly the six runner-contract keys, no more.
        self.assertEqual(_SUBPROCESS_RESULT_KEYS, set(result))
        self.assertIsInstance(result["exit_code"], int)
        self.assertEqual(0, result["exit_code"])
        self.assertEqual("hello\n", result["stdout"])
        self.assertEqual("", result["stderr"])
        self.assertIsInstance(result["wall_time_s"], float)
        self.assertGreater(result["wall_time_s"], 0.0)
        self.assertIs(result["timed_out"], False)
        self.assertEqual("", result["evidence"])

    def test_subprocess_runner_nonzero_exit_code_reported(self):
        subprocess_runner = self._get_subprocess_runner()
        cwd = self._tmpdir()
        result = subprocess_runner(self._spec(["/bin/sh", "-c", "exit 3"], cwd))
        self.assertEqual(3, result["exit_code"])
        self.assertIs(result["timed_out"], False)
        self.assertEqual("", result["evidence"])

    def test_subprocess_runner_stderr_captured_separately(self):
        subprocess_runner = self._get_subprocess_runner()
        cwd = self._tmpdir()
        result = subprocess_runner(
            self._spec(["/bin/sh", "-c", "echo out; echo err 1>&2"], cwd)
        )
        self.assertEqual("out\n", result["stdout"])
        self.assertEqual("err\n", result["stderr"])
        self.assertIs(result["timed_out"], False)

    def test_subprocess_runner_cwd_honoured(self):
        subprocess_runner = self._get_subprocess_runner()
        cwd = self._tmpdir()
        result = subprocess_runner(self._spec(["/bin/sh", "-c", "pwd"], cwd))
        # Symlink-tolerant: compare resolved paths (e.g. /var -> /private/var).
        self.assertEqual(
            Path(cwd).resolve(), Path(result["stdout"].strip()).resolve()
        )

    def test_subprocess_runner_stdin_dev_null_read_does_not_block(self):
        subprocess_runner = self._get_subprocess_runner()
        cwd = self._tmpdir()
        started = time.monotonic()
        result = subprocess_runner(
            self._spec(["/bin/sh", "-c", "read line || true"], cwd)
        )
        elapsed = time.monotonic() - started
        # A read on a real tty or an inherited pipe would block until the
        # timeout; /dev/null EOFs it immediately.
        self.assertLess(elapsed, 5.0)
        self.assertEqual(0, result["exit_code"])
        self.assertEqual("", result["stdout"])
        self.assertIs(result["timed_out"], False)

    def test_subprocess_runner_large_stdout_drained_without_stall(self):
        subprocess_runner = self._get_subprocess_runner()
        cwd = self._tmpdir()
        # 1 MB through the pipe: a runner that stops draining would fill
        # the pipe buffer and the child would stall until the (bounded)
        # timeout; this pin is that it MUST complete with all the bytes.
        result = subprocess_runner(
            self._spec(["/bin/sh", "-c", "yes y | head -c 1000000"], cwd, timeout_s=15.0)
        )
        self.assertIs(result["timed_out"], False)
        self.assertEqual(0, result["exit_code"])
        self.assertEqual(1000000, len(result["stdout"]))
        self.assertLess(result["wall_time_s"], 15.0)

    def test_subprocess_runner_timeout_kills_process_and_returns_record(self):
        subprocess_runner = self._get_subprocess_runner()
        cwd = self._tmpdir()
        started = time.monotonic()
        # Must return, never raise: a blocked run becomes a record.
        result = subprocess_runner(
            self._spec(["/bin/sleep", "30"], cwd, timeout_s=0.5)
        )
        elapsed = time.monotonic() - started
        self.assertEqual(_SUBPROCESS_RESULT_KEYS, set(result))
        self.assertIs(result["timed_out"], True)
        # Pinned kill sentinel: SIGKILL, subprocess's negative-signal form.
        self.assertEqual(-9, result["exit_code"])
        # The evidence names the condition and carries the elapsed seconds.
        self.assertIsInstance(result["evidence"], str)
        self.assertNotEqual("", result["evidence"])
        self.assertIn("timeout", result["evidence"])
        self.assertTrue(any(ch.isdigit() for ch in result["evidence"]))
        # The kill landed at the budget, not after the sleep completed.
        self.assertGreaterEqual(result["wall_time_s"], 0.5)
        self.assertLess(result["wall_time_s"], 5.0)
        self.assertLess(elapsed, 5.0)

    def test_subprocess_runner_timeout_captures_last_output_seen(self):
        subprocess_runner = self._get_subprocess_runner()
        cwd = self._tmpdir()
        result = subprocess_runner(
            self._spec(["/bin/sh", "-c", "echo partial; sleep 30"], cwd, timeout_s=1.0)
        )
        self.assertIs(result["timed_out"], True)
        # The output that did arrive before the kill is in stdout, not lost.
        self.assertIn("partial", result["stdout"])
        self.assertNotEqual("", result["evidence"])

    def test_subprocess_runner_missing_timeout_s_raises_bakeoff_error_before_spawn(self):
        subprocess_runner = self._get_subprocess_runner()
        bakeoff_error = self._get_bakeoff_error()
        cwd = self._tmpdir()
        spec = {
            "argv": ["/bin/sleep", "30"],  # would hang for 30 s if spawned
            "cwd": str(cwd),
            "stdin": "/dev/null",
        }
        started = time.monotonic()
        with self.assertRaises(bakeoff_error) as ctx:
            subprocess_runner(spec)
        elapsed = time.monotonic() - started
        self.assertIn("timeout_s", str(ctx.exception))
        # Raised before any process spawned: no sleep in the wall time.
        self.assertLess(elapsed, 1.0)

    def test_subprocess_runner_env_dict_overlays_parent_env(self):
        subprocess_runner = self._get_subprocess_runner()
        cwd = self._tmpdir()
        with mock.patch.dict(
            os.environ, {"ANVIL_TEST_PARENT_VAR": "parent-value"}
        ):
            spec = self._spec(
                [
                    "/bin/sh",
                    "-c",
                    "printf '%s\\n%s\\n' "
                    "\"$ANVIL_TEST_OVERLAY_VAR\" \"$ANVIL_TEST_PARENT_VAR\"",
                ],
                cwd,
            )
            spec["env"] = {"ANVIL_TEST_OVERLAY_VAR": "overridden"}
            result = subprocess_runner(spec)
        lines = result["stdout"].splitlines()
        # The overlay key carries the spec value, not the parent's.
        self.assertEqual("overridden", lines[0])
        # The overlay merges over os.environ: other parent variables survive.
        self.assertEqual("parent-value", lines[1])
        self.assertEqual(0, result["exit_code"])
        self.assertIs(result["timed_out"], False)

    def test_subprocess_runner_env_absent_inherits_parent_env(self):
        subprocess_runner = self._get_subprocess_runner()
        cwd = self._tmpdir()
        with mock.patch.dict(
            os.environ, {"ANVIL_TEST_PARENT_VAR": "parent-value"}
        ):
            spec = self._spec(
                ["/bin/sh", "-c", "printf '%s\\n' \"$ANVIL_TEST_PARENT_VAR\""],
                cwd,
            )
            self.assertNotIn("env", spec)
            result = subprocess_runner(spec)
        # No env key: the child inherits the parent environment unchanged.
        self.assertEqual("parent-value\n", result["stdout"])
        self.assertEqual(0, result["exit_code"])
        self.assertIs(result["timed_out"], False)

    def test_subprocess_runner_env_none_inherits_parent_env(self):
        subprocess_runner = self._get_subprocess_runner()
        cwd = self._tmpdir()
        with mock.patch.dict(
            os.environ, {"ANVIL_TEST_PARENT_VAR": "parent-value"}
        ):
            spec = self._spec(
                ["/bin/sh", "-c", "printf '%s\\n' \"$ANVIL_TEST_PARENT_VAR\""],
                cwd,
            )
            spec["env"] = None
            result = subprocess_runner(spec)
        # An explicit None is the same as an absent env key.
        self.assertEqual("parent-value\n", result["stdout"])
        self.assertEqual(0, result["exit_code"])
        self.assertIs(result["timed_out"], False)

    def test_subprocess_runner_env_non_dict_raises_bakeoff_error_before_spawn(
        self,
    ):
        subprocess_runner = self._get_subprocess_runner()
        bakeoff_error = self._get_bakeoff_error()
        cwd = self._tmpdir()
        spec = {
            "argv": ["/bin/sleep", "30"],  # would hang for 30 s if spawned
            "cwd": str(cwd),
            "stdin": "/dev/null",
            "timeout_s": 10.0,
            "env": "not-a-dict",
        }
        started = time.monotonic()
        with self.assertRaises(bakeoff_error) as ctx:
            subprocess_runner(spec)
        elapsed = time.monotonic() - started
        self.assertIn("env", str(ctx.exception))
        # Raised before any process spawned: no sleep in the wall time.
        self.assertLess(elapsed, 1.0)


# ---------------------------------------------------------------------------
# anvilkit.pi.pibakeoff.main - the in-container entrypoint
# (plans/pi-phase1b-docker.md, behaviour 8: "entrypoint and compose
# wiring"). Written before the implementation; the module has no ``main``
# yet, so every test below fails with the explicit message
# "anvilkit.pi.pibakeoff.main is not callable" - never a bare AttributeError.
#
# The ``run_all`` seam is monkeypatched with a signature-bound recorder,
# so no test touches pi, npm or the gateway; the environment is patched
# per test (``PI_GATEWAY_HOST``/``PI_GATEWAY_PORT`` required,
# ``PI_CONFIG_PATH`` and ``PI_RESULTS_DIR`` optional).
# ---------------------------------------------------------------------------

# The phase-1 trivial task prompt (doc/pi-bakeoff/README.md), verbatim.
BAKEOFF_PROMPT_PIN = (
    "Edit `bakeoff_fixture/adder.py` so that `add(2, 3) == 5` passes. "
    "The function currently returns `a - b`; change it to `a + b`."
)

# A minimal config.yaml in the exact shape anvilkit.config.read_models
# expects: matrix.vars.coder naming a model present in the models section,
# with the context window carried in the cmd's --max-model-len.
CONFIG_YAML_PIN = """\
port: 8080

matrix:
  vars:
    coder: "test/coder-model"

models:
  "test/coder-model":
    cmd: "vllm serve --model test/coder-model --max-model-len 12345"
"""

PINNED_MAX_TOKENS = 4096
PINNED_TIMEOUT_S = 600.0
PINNED_DEFAULT_CONFIG_PATH = "/app/config.yaml"
PINNED_DEFAULT_RESULTS_DIR = "/workspace/results"
PINNED_DEFAULT_NPM_ROOT = "/usr/local/lib/node_modules"
PINNED_EXTENSION_PATH = (
    "/usr/local/lib/node_modules/pi-ultrawork/src/index.ts"
)

TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class TestMain(PibakeoffTestCase):
    """main - the in-container entrypoint (behaviour 8)."""

    def _get_main(self) -> Callable:
        """Fetch ``anvilkit.pi.pibakeoff.main``, failing clearly if absent."""
        pibakeoff = self._pibakeoff()
        main = getattr(pibakeoff, "main", None)
        self.assertTrue(
            callable(main),
            "anvilkit.pi.pibakeoff.main is not callable; the in-container "
            "entrypoint (behaviour 8) has not been implemented yet",
        )
        return main

    def _get_constant(self, name: str):
        """Fetch a module constant, failing clearly if it is absent."""
        pibakeoff = self._pibakeoff()
        value = getattr(pibakeoff, name, None)
        self.assertIsNotNone(
            value,
            "anvilkit.pi.pibakeoff.{} is missing; the entrypoint constants "
            "(behaviour 8) have not been implemented yet".format(name),
        )
        return value

    @staticmethod
    def _env(**overrides) -> Dict[str, str]:
        """A hermetic environment: no PI_* keys except the ones given."""
        env = {k: v for k, v in os.environ.items() if not k.startswith("PI_")}
        env.update(overrides)
        return env

    def _write_config(self, text: str = CONFIG_YAML_PIN) -> Path:
        """A real tmp config.yaml for read_models to parse."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "config.yaml"
        path.write_text(text, encoding="utf-8")
        return path

    def _happy_env(self, config_path: Path, **extra) -> Dict[str, str]:
        """The valid service environment, pointed at a real tmp config."""
        env = self._env(
            PI_GATEWAY_HOST="llama-swap",
            PI_GATEWAY_PORT="8080",
            PI_CONFIG_PATH=str(config_path),
        )
        env.update(extra)
        return env

    def _recorder(self, pibakeoff, table: str = "NO-GO"):
        """A ``run_all`` stand-in that records its bound call arguments.

        Signature-bound against the real ``run_all`` so the pin does not
        depend on whether ``main`` calls it positionally or by keyword.
        Returns ``(patcher, recorder)``; ``recorder.calls`` is the list of
        bound-argument dicts, one entry per call.
        """
        real_run_all = pibakeoff.run_all
        signature = inspect.signature(real_run_all)

        def recorder(*args, **kwargs):
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            recorder.calls.append(dict(bound.arguments))
            return ([{"config": "print"}], table)

        recorder.calls = []
        return mock.patch.object(pibakeoff, "run_all", recorder), recorder

    def test_main_missing_gateway_host_raises_bakeoff_error_naming_it(self):
        main = self._get_main()
        bakeoff_error = self._get_bakeoff_error()
        pibakeoff = self._pibakeoff()
        config_path = self._write_config()
        env = self._happy_env(config_path)
        del env["PI_GATEWAY_HOST"]
        patcher, recorder = self._recorder(pibakeoff)
        with patcher, mock.patch.dict(os.environ, env):
            with self.assertRaises(bakeoff_error) as ctx:
                main()
        self.assertIn("PI_GATEWAY_HOST", str(ctx.exception))
        self.assertEqual([], recorder.calls)

    def test_main_empty_gateway_port_raises_bakeoff_error_naming_it(self):
        main = self._get_main()
        bakeoff_error = self._get_bakeoff_error()
        pibakeoff = self._pibakeoff()
        config_path = self._write_config()
        env = self._happy_env(config_path, PI_GATEWAY_PORT="")
        patcher, recorder = self._recorder(pibakeoff)
        with patcher, mock.patch.dict(os.environ, env):
            with self.assertRaises(bakeoff_error) as ctx:
                main()
        self.assertIn("PI_GATEWAY_PORT", str(ctx.exception))
        self.assertEqual([], recorder.calls)

    def test_main_non_numeric_gateway_port_raises_bakeoff_error_naming_it(self):
        main = self._get_main()
        bakeoff_error = self._get_bakeoff_error()
        pibakeoff = self._pibakeoff()
        config_path = self._write_config()
        env = self._happy_env(config_path, PI_GATEWAY_PORT="not-a-port")
        patcher, recorder = self._recorder(pibakeoff)
        with patcher, mock.patch.dict(os.environ, env):
            with self.assertRaises(bakeoff_error) as ctx:
                main()
        self.assertIn("PI_GATEWAY_PORT", str(ctx.exception))
        self.assertEqual([], recorder.calls)

    def test_main_unreadable_config_raises_config_error_unwrapped(self):
        main = self._get_main()
        pibakeoff = self._pibakeoff()
        config_path = self._write_config()
        missing = config_path.parent / "does-not-exist.yaml"
        env = self._happy_env(config_path, PI_CONFIG_PATH=str(missing))
        patcher, recorder = self._recorder(pibakeoff)
        with patcher, mock.patch.dict(os.environ, env):
            # The ConfigError from anvilkit.config, propagated as-is -
            # not wrapped into a BakeoffError or any other type.
            with self.assertRaises(piconfig.ConfigError):
                main()
        self.assertEqual([], recorder.calls)

    def test_main_passes_gateway_env_and_config_topology_to_run_all(self):
        main = self._get_main()
        pibakeoff = self._pibakeoff()
        config_path = self._write_config()
        env = self._happy_env(config_path)
        patcher, recorder = self._recorder(pibakeoff)
        with patcher, mock.patch.dict(os.environ, env):
            exit_code = main()
        self.assertEqual(0, exit_code)
        self.assertEqual(1, len(recorder.calls))
        seen = recorder.calls[0]
        # Results land at the pinned container results directory, as a Path.
        self.assertEqual(Path(PINNED_DEFAULT_RESULTS_DIR), seen["base_dir"])
        # The model id and context window are read_models' answer, verbatim.
        self.assertEqual("test/coder-model", seen["model_id"])
        self.assertEqual(12345, seen["context_window"])
        # The gateway address is the service environment, port as an int.
        self.assertEqual("llama-swap", seen["gateway_host"])
        self.assertEqual(8080, seen["gateway_port"])
        self.assertIsInstance(seen["gateway_port"], int)
        # runner=None defaults to the module's own subprocess_runner.
        self.assertIs(pibakeoff.subprocess_runner, seen["runner"])
        # main supplies the stamp itself; the container default agent home.
        self.assertRegex(seen["timestamp"], TIMESTAMP_PATTERN)
        self.assertIsNone(seen["agent_home"])

    def test_main_passes_pinned_module_constants_to_run_all(self):
        main = self._get_main()
        pibakeoff = self._pibakeoff()
        # The constants exist and carry the pinned values.
        self.assertEqual(
            PINNED_DEFAULT_CONFIG_PATH,
            self._get_constant("_DEFAULT_CONFIG_PATH"),
        )
        self.assertEqual(
            PINNED_DEFAULT_RESULTS_DIR,
            self._get_constant("_DEFAULT_RESULTS_DIR"),
        )
        self.assertEqual(
            PINNED_DEFAULT_NPM_ROOT,
            self._get_constant("_DEFAULT_NPM_ROOT"),
        )
        self.assertEqual(
            PINNED_MAX_TOKENS, self._get_constant("BAKEOFF_MAX_TOKENS")
        )
        self.assertEqual(
            PINNED_TIMEOUT_S, self._get_constant("BAKEOFF_TIMEOUT_S")
        )
        self.assertEqual(
            BAKEOFF_PROMPT_PIN, self._get_constant("BAKEOFF_PROMPT")
        )
        config_path = self._write_config()
        env = self._happy_env(config_path)
        patcher, recorder = self._recorder(pibakeoff)
        with patcher, mock.patch.dict(os.environ, env):
            self.assertEqual(0, main())
        seen = recorder.calls[0]
        # And the constants are exactly what the driver receives.
        self.assertEqual(PINNED_MAX_TOKENS, seen["max_tokens"])
        self.assertEqual(PINNED_TIMEOUT_S, seen["timeout_s"])
        self.assertEqual(BAKEOFF_PROMPT_PIN, seen["prompt"])
        # The ultrawork extension entry, from the pinned global npm root.
        self.assertEqual(PINNED_EXTENSION_PATH, seen["extension_path"])
        self.assertEqual(
            str(Path(PINNED_DEFAULT_NPM_ROOT) / "pi-ultrawork" / "src" / "index.ts"),
            seen["extension_path"],
        )

    def test_main_results_dir_honours_pi_results_dir_env(self):
        main = self._get_main()
        pibakeoff = self._pibakeoff()
        config_path = self._write_config()
        env = self._happy_env(config_path, PI_RESULTS_DIR="/custom/results")
        patcher, recorder = self._recorder(pibakeoff)
        with patcher, mock.patch.dict(os.environ, env):
            self.assertEqual(0, main())
        self.assertEqual(Path("/custom/results"), recorder.calls[0]["base_dir"])

    def test_main_config_path_honours_pi_config_path_env(self):
        main = self._get_main()
        pibakeoff = self._pibakeoff()
        other_config = (
            "port: 8080\n"
            "\n"
            "matrix:\n"
            "  vars:\n"
            '    coder: "other/coder-model"\n'
            "\n"
            "models:\n"
            '  "other/coder-model":\n'
            '    cmd: "vllm serve --max-model-len 4321"\n'
        )
        config_path = self._write_config(other_config)
        env = self._happy_env(config_path)
        patcher, recorder = self._recorder(pibakeoff)
        with patcher, mock.patch.dict(os.environ, env):
            self.assertEqual(0, main())
        # The env-named file is the one read_models parsed.
        self.assertEqual("other/coder-model", recorder.calls[0]["model_id"])
        self.assertEqual(4321, recorder.calls[0]["context_window"])

    def test_main_extension_path_honours_pi_extension_path_env(self):
        main = self._get_main()
        pibakeoff = self._pibakeoff()
        config_path = self._write_config()
        # The devcontainer's npm root (doc/external: npm root -g probes
        # /usr/lib/node_modules there, not the bake-off image's prefix).
        devcontainer_path = (
            "/usr/lib/node_modules/pi-ultrawork/src/index.ts"
        )
        env = self._happy_env(config_path, PI_EXTENSION_PATH=devcontainer_path)
        patcher, recorder = self._recorder(pibakeoff)
        with patcher, mock.patch.dict(os.environ, env):
            self.assertEqual(0, main())
        # The env value reaches run_all verbatim, unmodified.
        self.assertEqual(
            devcontainer_path, recorder.calls[0]["extension_path"]
        )

    def test_main_extension_path_whitespace_only_treated_as_set(self):
        main = self._get_main()
        pibakeoff = self._pibakeoff()
        config_path = self._write_config()
        env = self._happy_env(config_path, PI_EXTENSION_PATH="   ")
        patcher, recorder = self._recorder(pibakeoff)
        with patcher, mock.patch.dict(os.environ, env):
            self.assertEqual(0, main())
        # main() adds no second validation: the whitespace-only value
        # reaches run_all as-is; ultrawork_argv (anvilkit/pi/piargv.py) is the
        # layer that rejects it.
        self.assertEqual("   ", recorder.calls[0]["extension_path"])

    def test_main_extension_path_falls_back_to_default_when_absent_or_empty(self):
        main = self._get_main()
        pibakeoff = self._pibakeoff()
        config_path = self._write_config()
        for label, env in (
            ("absent", self._happy_env(config_path)),
            ("empty string", self._happy_env(config_path, PI_EXTENSION_PATH="")),
        ):
            with self.subTest(PI_EXTENSION_PATH=label):
                patcher, recorder = self._recorder(pibakeoff)
                with patcher, mock.patch.dict(os.environ, env):
                    self.assertEqual(0, main())
                # The `or`-fallback style of PI_CONFIG_PATH and
                # PI_RESULTS_DIR: the Compose path is untouched.
                self.assertEqual(
                    PINNED_EXTENSION_PATH, recorder.calls[0]["extension_path"]
                )

    def test_main_default_config_path_is_the_read_only_mount(self):
        main = self._get_main()
        pibakeoff = self._pibakeoff()
        env = self._env(
            PI_GATEWAY_HOST="llama-swap",
            PI_GATEWAY_PORT="8080",
        )

        def read_models_spy(path):
            read_models_spy.calls.append(path)
            return piconfig.ModelTopology(
                coder_id="spied/coder",
                coder_context_window=777,
                embedder_id=None,
                gateway_port=8080,
            )

        read_models_spy.calls = []
        patcher, recorder = self._recorder(pibakeoff)
        with patcher, mock.patch("anvilkit.config.read_models", read_models_spy):
            with mock.patch.dict(os.environ, env):
                self.assertEqual(0, main())
        # With PI_CONFIG_PATH unset, the default is the module constant.
        self.assertEqual(1, len(read_models_spy.calls))
        self.assertEqual(
            Path(self._get_constant("_DEFAULT_CONFIG_PATH")),
            Path(read_models_spy.calls[0]),
        )
        self.assertEqual(
            Path(PINNED_DEFAULT_CONFIG_PATH), Path(read_models_spy.calls[0])
        )
        self.assertEqual("spied/coder", recorder.calls[0]["model_id"])
        self.assertEqual(777, recorder.calls[0]["context_window"])

    def test_main_injected_runner_passed_to_run_all_verbatim(self):
        main = self._get_main()
        pibakeoff = self._pibakeoff()
        config_path = self._write_config()
        env = self._happy_env(config_path)
        fake_runner = object()
        patcher, recorder = self._recorder(pibakeoff)
        with patcher, mock.patch.dict(os.environ, env):
            self.assertEqual(0, main(runner=fake_runner))
        self.assertIs(fake_runner, recorder.calls[0]["runner"])

    def test_main_exit_zero_when_table_is_nongo(self):
        main = self._get_main()
        pibakeoff = self._pibakeoff()
        config_path = self._write_config()
        env = self._happy_env(config_path)
        # The recorder's canned table is a NO-GO: the verdict is data, not
        # an exit condition - a run that measured a NO-GO is a successful
        # run, so main still returns 0.
        patcher, _ = self._recorder(pibakeoff, table="NO-GO")
        with patcher, mock.patch.dict(os.environ, env):
            self.assertEqual(0, main())

    def test_main_guard_is_the_only_sys_exit_and_is_last(self):
        pibakeoff = self._pibakeoff()
        source = Path(pibakeoff.__file__).read_text(encoding="utf-8")
        # The house rule: library code returns the exit code; only the
        # module's __main__ guard may call sys.exit.
        self.assertEqual(
            1,
            source.count("sys.exit"),
            "sys.exit must appear exactly once, in the __main__ guard; "
            "main() must return the exit code, not call sys.exit itself",
        )
        lines = [line for line in source.splitlines() if line.strip()]
        self.assertGreaterEqual(
            len(lines), 2, "the module source has no __main__ guard"
        )
        self.assertEqual(
            'if __name__ == "__main__":',
            lines[-2].strip(),
            "the module's final statement must be guarded by "
            "if __name__ == '__main__':",
        )
        self.assertEqual(
            "sys.exit(main())",
            lines[-1].strip(),
            "the __main__ guard must be sys.exit(main())",
        )


if __name__ == "__main__":
    unittest.main()
