"""Tests for anvilkit.pi.picrew - the crew-spike run driver (``run_spike``).

Written before the implementation (TDD, ``plans/pi-crew-spike.md``: "drive
the one crew-spike run"). The production module ``anvilkit.pi.picrew`` does
not exist yet, so every test loads it through ``_picrew``, which fails with
the module's own ``ModuleNotFoundError`` - the right reason the suite is
red.

Design constraint pinned here: no test spawns ``pi``, npm or Docker.
``run_spike`` takes process execution as an **injected runner callable** in
the ``anvilkit.pi.pibakeoff.subprocess_runner`` shape - one invocation dict
in, one result dict out - and every test supplies a fake that records its
invocation and returns a canned result.

Pinned signature::

    run_spike(base_dir, runner, model_id, extension_path,
              gateway_host, gateway_port, context_window,
              max_tokens, timeout_s, *, timestamp,
              agent_home=None) -> dict

``base_dir`` is the results base dir (created if missing; its parent must
exist): the fixture lands at ``<base>/fixture``, the captured artifacts at
``<base>/results/{stdout, stderr, events.jsonl}``, and the flat
``record.json`` at ``<base>/record.json``. ``agent_home`` defaults to the
user's home (``pathlib.Path.home()``); the agent dir it points at is
``<agent_home>/.pi/agent`` - the ``PI_CODING_AGENT_DIR`` location
(doc/external/pi-dev/configuration.md).

Pinned runner contract (the ``pibakeoff.subprocess_runner`` shape, reused
as the production default)::

    {"argv": List[str], "cwd": str, "stdin": str,
     "timeout_s": float, "env": Dict[str, str]}

    {"exit_code": int, "stdout": str, "stderr": str,
     "wall_time_s": float, "timed_out": bool, "evidence": str}

- ``argv``: exactly
  ``["pi", "--mode", "json", "-e", <extension_path>, "--model",
  <model_id>, "--tools", "read,edit,write,team", "-a",
  "--no-session", "--", pibakeoff.BAKEOFF_PROMPT]`` - the goal prompt is
  the bake-off trivial task, reused verbatim so the crew run is comparable
  to the recorded bake-off configurations (``-e`` and ``--tools`` are the
  pi CLI flags, doc/external/pi-dev/cli.md);
- ``cwd``: ``str(<base>/fixture)`` - the fixture directory, verbatim;
- ``stdin``: ``"/dev/null"``;
- ``timeout_s``: the ``timeout_s`` argument passed to ``run_spike``;
- ``env``: exactly the two-key overlay
  ``{"PI_CREW_BROKER": "0", "PI_CODING_AGENT_DIR":
  str(<agent_home>/.pi/agent)}`` - the broker is off for this run
  (``PI_CREW_BROKER=0`` always wins,
  doc/external/pi-dev/packages/pi-crew.md) and the agent dir is relocated
  so the in-container run never touches the operator's real ``~/.pi``.

Pinned ``run_spike`` responsibilities:

- the agent dir receives ``models.json`` with content exactly
  ``json.dumps`` of ``piargv.models_document(model_id, gateway_port,
  context_window, max_tokens, host=gateway_host)`` - one builder, so the
  document cannot drift - and ``pi-crew.json`` carrying the pinned
  user-config values: ``runtime.mode`` ``"child-process"``,
  ``executeWorkers`` true, broker disabled, one concurrent worker (the
  locked values settable in user config only,
  doc/external/pi-dev/packages/pi-crew.md);
- the ``pifixture`` task is written into ``<base>/fixture`` before the
  runner call;
- the runner is invoked **exactly once**;
- stdout, stderr and the stdout-as-``events.jsonl`` drain are captured at
  the pinned artifact paths;
- ``team_tool_seen`` is derived by scanning the captured stdout JSONL for
  a ``team`` tool-execution record (tool records carry ``toolName``,
  doc/external/pi-dev/json-event-stream.md);
- ``crew_tree`` is the sorted list of relative POSIX paths of the files
  under ``<fixture>/.crew/`` - ``[]`` when the tree is absent (crew state
  persists under ``.crew/``, doc/external/pi-dev/packages/pi-crew.md);
- the fixture assertion is captured via ``pifixture.assertion_passes`` and
  lands under the record's ``assertion`` key (the ``{"passed", "stderr"}``
  shape);
- the flat ``record.json`` (module-local - **not** ``pirecord.build``,
  whose ``_CONFIG_VALUES`` is closed) carries at least ``config``,
  ``completed``, ``exit_code``, ``wall_time_s``, ``waited_for_input``,
  ``team_tool_seen``, ``crew_tree``, ``artifacts`` (a mapping including
  the ``stdout``/``stderr``/``jsonl`` artifact paths) and ``timestamp``
  (verbatim). ``completed`` is ``True`` iff ``exit_code == 0`` and the
  assertion passed. The returned dict is exactly the one written:
  ``json.loads(json.dumps(record, sort_keys=True)) == record`` - the
  record is JSON-native throughout.

One exception type: ``CrewSpikeError`` - raised (naming the offending
value) for an empty model id or an empty extension path, each before any
runner invocation.

Recorded outcomes, never exceptions: a non-zero exit, an absent
``.crew/`` tree, a ``team`` tool that never loads, and a
budget-exhausted run (``timed_out`` True, the pinned
``waited_for_input`` sentinel - the same treatment
``pibakeoff``/``pirecord`` give a blocked run) all become record values,
never raises.

``TestMain`` pins the in-container entrypoint::

    main(runner=None) -> int

- the gateway host and port come from the environment: a missing or
  empty ``PI_GATEWAY_HOST``, or a missing, empty or non-numeric
  ``PI_GATEWAY_PORT``, raises ``CrewSpikeError`` naming the variable, in
  every case before any runner invocation;
- the model id and context window come from
  ``anvilkit.config.read_models`` of the ``PI_CONFIG_PATH`` file (default
  the module constant ``_DEFAULT_CONFIG_PATH == "/app/config.yaml"``, the
  read-only bind the compose service mounts); an unreadable file raises
  ``ConfigError`` unwrapped;
- results land in ``PI_RESULTS_DIR`` (default the module constant
  ``_DEFAULT_RESULTS_DIR == "/workspace/results"``), passed to
  ``run_spike`` as a ``Path``; the crew extension path defaults to
  ``/usr/local/lib/node_modules/pi-crew/index.ts`` (the npm-global layout
  the crew-spike image uses, ``PI_EXTENSION_PATH`` override);
- an injected ``runner`` is handed to ``run_spike`` verbatim; when
  ``runner`` is ``None`` the default is the reused
  ``pibakeoff.subprocess_runner`` (identity, not equality);
- ``main`` returns 0 whenever the run was measured - a failed or
  budget-exhausted recorded outcome is still a successful run;
- the module's ``__main__`` guard is the only ``sys.exit`` (the compose
  service runs ``python3 -m anvilkit.pi.picrew``).
"""

import importlib
import inspect
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import anvilkit.config as piconfig
from anvilkit.pi import pibakeoff
from anvilkit.pi import piargv

MODEL_ID = "matrix.vars.coder"
EXTENSION_PATH = "/opt/pi/pi-crew/index.ts"
GATEWAY_HOST = "llama-swap"
GATEWAY_PORT = 8080
CONTEXT_WINDOW = 32768
MAX_TOKENS = 4096
TIMEOUT_S = 1800.0
TIMESTAMP = "2026-11-02T00:00:00Z"

# The locked user-config values the agent-dir pi-crew.json must carry
# (doc/external/pi-dev/packages/pi-crew.md: runtime.mode and
# executeWorkers are settable in user config only; the broker is on by
# default, so the spike pins it off).
PI_CREW_JSON_PIN = {
    "runtime": {"mode": "child-process"},
    "executeWorkers": True,
    "broker": {"enabled": False},
    "limits": {"maxConcurrentWorkers": 1},
}

# The flat record's required keys (plans/pi-crew-spike.md: "carrying at
# least ..."). The record may carry more keys.
REQUIRED_RECORD_KEYS = {
    "config",
    "completed",
    "exit_code",
    "wall_time_s",
    "waited_for_input",
    "team_tool_seen",
    "crew_tree",
    "artifacts",
    "timestamp",
}

# A recorded stdout carrying one tool_execution pair for the ``team``
# tool. Tool records carry ``toolName``
# (doc/external/pi-dev/json-event-stream.md).
TEAM_STDOUT = "\n".join(
    [
        json.dumps(
            {
                "type": "tool_execution_start",
                "toolCallId": "tc-team-1",
                "toolName": "team",
                "args": {"action": "run", "team": "default", "goal": "fix the adder"},
            }
        ),
        json.dumps(
            {
                "type": "tool_execution_end",
                "toolCallId": "tc-team-1",
                "toolName": "team",
                "isError": False,
                "durationMs": 1200,
            }
        ),
    ]
) + "\n"

# A recorded stdout whose tool_execution records name other tools only:
# the ``team`` tool never loaded.
NO_TEAM_STDOUT = "\n".join(
    [
        json.dumps(
            {
                "type": "tool_execution_start",
                "toolCallId": "tc-1",
                "toolName": "read",
                "args": {"path": "TASK.md"},
            }
        ),
        json.dumps(
            {
                "type": "tool_execution_end",
                "toolCallId": "tc-1",
                "toolName": "read",
                "isError": False,
            }
        ),
    ]
) + "\n"


class PicrewTestCase(unittest.TestCase):
    """Shared import guards, fakes and temp trees for the picrew suite."""

    def _picrew(self):
        """Import anvilkit.pi.picrew.

        Fails with the module's own ``ModuleNotFoundError`` - the right
        reason the suite is red - until the driver exists.
        """
        return importlib.import_module("anvilkit.pi.picrew")

    def _get_run_spike(self) -> Callable:
        """Fetch ``anvilkit.pi.picrew.run_spike``, failing clearly if absent."""
        picrew = self._picrew()
        run_spike = getattr(picrew, "run_spike", None)
        self.assertTrue(
            callable(run_spike),
            "anvilkit.pi.picrew.run_spike is not callable; the crew-spike "
            "driver has not been implemented yet",
        )
        return run_spike

    def _get_crew_spike_error(self):
        """Fetch ``anvilkit.pi.picrew.CrewSpikeError``, failing clearly if absent."""
        picrew = self._picrew()
        crew_spike_error = getattr(picrew, "CrewSpikeError", None)
        self.assertTrue(
            isinstance(crew_spike_error, type)
            and issubclass(crew_spike_error, Exception),
            "anvilkit.pi.picrew.CrewSpikeError is not an exception type; "
            "the single exception type for the crew-spike driver has not "
            "been implemented yet",
        )
        return crew_spike_error

    def _fake(
        self,
        result: Optional[Dict[str, Any]] = None,
        edit: bool = False,
        crew_tree: Optional[List[str]] = None,
    ) -> Callable:
        """A fake runner recording its invocation and returning a canned result.

        ``edit=True`` makes the fake simulate a successful agent edit: it
        rewrites ``<fixture>/bakeoff_fixture/adder.py`` to the correct
        implementation, so the fixture assertion turns green. ``crew_tree``
        is a list of relative paths the fake creates under
        ``<fixture>/.crew/`` (parents included), simulating the crew state
        the extension would persist during the run.
        """

        def fake_runner(invocation: Dict[str, Any]) -> Dict[str, Any]:
            fake_runner._calls.append(dict(invocation))
            cwd = Path(invocation["cwd"])
            if edit:
                adder = cwd / "bakeoff_fixture" / "adder.py"
                adder.write_text(
                    adder.read_text(encoding="utf-8").replace(
                        "return a - b", "return a + b"
                    ),
                    encoding="utf-8",
                )
            if crew_tree:
                for rel in crew_tree:
                    path = cwd / ".crew" / rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("crew state\n", encoding="utf-8")
            if result is not None:
                return dict(result)
            return PicrewTestCase._default_result()

        fake_runner._calls = []  # type: ignore[attr-defined]
        return fake_runner

    @staticmethod
    def _default_result() -> Dict[str, Any]:
        """A clean, successful runner result (the baseline)."""
        return {
            "exit_code": 0,
            "stdout": "done\n",
            "stderr": "",
            "wall_time_s": 2.5,
            "timed_out": False,
            "evidence": "",
        }

    def _fresh(self) -> Dict[str, Path]:
        """A per-test temp tree: results base dir (created by run_spike)
        and agent home."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        return {
            "root": root,
            "base": root / "base",
            "agent_home": root / "agent-home",
        }

    @staticmethod
    def _expected_argv(model_id: str, extension_path: str) -> List[str]:
        """The exact argv the crew-spike invocation must carry."""
        return [
            "pi",
            "--mode",
            "json",
            "-e",
            extension_path,
            "--model",
            model_id,
            "--tools",
            "read,edit,write,team",
            "-a",
            "--no-session",
            "--",
            pibakeoff.BAKEOFF_PROMPT,
        ]

    @staticmethod
    def _expected_env_overlay(agent_home: Path) -> Dict[str, str]:
        """The exact env overlay the crew-spike invocation must carry."""
        return {
            "PI_CREW_BROKER": "0",
            "PI_CODING_AGENT_DIR": str(Path(agent_home) / ".pi" / "agent"),
        }

    def _run(self, run_spike, dirs, fake, **overrides):
        """Call run_spike with the standard inputs; ``overrides`` replace one."""
        kwargs = dict(
            base_dir=dirs["base"],
            runner=fake,
            model_id=MODEL_ID,
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
        return run_spike(**kwargs)


class TestAgentFiles(PicrewTestCase):
    """The agent dir receives the models document (from the piargv
    builder) and the pinned pi-crew user config."""

    def test_run_spike_models_document_matches_piargv_builder(self):
        run_spike = self._get_run_spike()
        dirs = self._fresh()
        self._run(run_spike, dirs, self._fake())
        models_path = dirs["agent_home"] / ".pi" / "agent" / "models.json"
        self.assertTrue(models_path.is_file())
        self.assertEqual(
            json.dumps(
                piargv.models_document(
                    MODEL_ID,
                    GATEWAY_PORT,
                    CONTEXT_WINDOW,
                    MAX_TOKENS,
                    host=GATEWAY_HOST,
                )
            ),
            models_path.read_text(encoding="utf-8"),
        )

    def test_run_spike_pi_crew_json_carries_pinned_user_config(self):
        run_spike = self._get_run_spike()
        dirs = self._fresh()
        self._run(run_spike, dirs, self._fake())
        crew_path = dirs["agent_home"] / ".pi" / "agent" / "pi-crew.json"
        self.assertTrue(crew_path.is_file())
        self.assertEqual(
            PI_CREW_JSON_PIN, json.loads(crew_path.read_text(encoding="utf-8"))
        )

    def test_run_spike_agent_home_defaults_to_user_home(self):
        run_spike = self._get_run_spike()
        dirs = self._fresh()
        fake = self._fake()
        with mock.patch("pathlib.Path.home", return_value=dirs["agent_home"]):
            self._run(run_spike, dirs, fake, agent_home=None)
        models_path = dirs["agent_home"] / ".pi" / "agent" / "models.json"
        self.assertTrue(models_path.is_file())
        # The env overlay relocates the same resolved agent dir.
        self.assertEqual(
            self._expected_env_overlay(dirs["agent_home"]),
            fake._calls[0]["env"],  # type: ignore[attr-defined]
        )


class TestFixtureAndInvocation(PicrewTestCase):
    """The pifixture task lands in <base>/fixture and the runner is
    invoked exactly once with the pinned spec."""

    def test_run_spike_runner_invoked_exactly_once_with_pinned_spec(self):
        run_spike = self._get_run_spike()
        dirs = self._fresh()
        fake = self._fake()
        self._run(run_spike, dirs, fake)
        self.assertEqual(1, len(fake._calls))  # type: ignore[attr-defined]
        self.assertEqual(
            {
                "argv": self._expected_argv(MODEL_ID, EXTENSION_PATH),
                "cwd": str(dirs["base"] / "fixture"),
                "stdin": "/dev/null",
                "timeout_s": TIMEOUT_S,
                "env": self._expected_env_overlay(dirs["agent_home"]),
            },
            fake._calls[0],  # type: ignore[attr-defined]
        )

    def test_run_spike_writes_fixture_into_base_fixture_dir(self):
        run_spike = self._get_run_spike()
        dirs = self._fresh()
        self._run(run_spike, dirs, self._fake())
        fixture = dirs["base"] / "fixture"
        self.assertTrue((fixture / "bakeoff_fixture" / "adder.py").is_file())
        self.assertTrue((fixture / "tests" / "test_adder.py").is_file())
        self.assertTrue((fixture / "TASK.md").is_file())


class TestCapturedArtifacts(PicrewTestCase):
    """stdout, stderr and the stdout-as-events.jsonl drain are captured
    at the pinned artifact paths, and record.json is the flat record."""

    def test_run_spike_captures_stdout_stderr_and_events_jsonl(self):
        run_spike = self._get_run_spike()
        dirs = self._fresh()
        fake = self._fake(
            result={
                "exit_code": 0,
                "stdout": TEAM_STDOUT,
                "stderr": "crew: worker 1 started\n",
                "wall_time_s": 1.25,
                "timed_out": False,
                "evidence": "",
            }
        )
        record = self._run(run_spike, dirs, fake)
        results = dirs["base"] / "results"
        self.assertEqual(
            TEAM_STDOUT, (results / "stdout").read_text(encoding="utf-8")
        )
        self.assertEqual(
            "crew: worker 1 started\n",
            (results / "stderr").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            TEAM_STDOUT, (results / "events.jsonl").read_text(encoding="utf-8")
        )
        # The record's artifact paths point at those files.
        artifacts = record["artifacts"]
        self.assertEqual(str(results / "stdout"), artifacts["stdout"])
        self.assertEqual(str(results / "stderr"), artifacts["stderr"])
        self.assertEqual(str(results / "events.jsonl"), artifacts["jsonl"])

    def test_run_spike_record_json_written_sort_keys_and_matches_return(self):
        run_spike = self._get_run_spike()
        dirs = self._fresh()
        record = self._run(run_spike, dirs, self._fake())
        record_path = dirs["base"] / "record.json"
        self.assertTrue(record_path.is_file())
        content = record_path.read_text(encoding="utf-8")
        self.assertEqual(json.dumps(record, sort_keys=True), content)
        self.assertEqual(record, json.loads(content))


class TestRecordKeys(PicrewTestCase):
    """The flat record carries the required keys with the values the
    fake's canned result determines."""

    def test_run_spike_record_carries_required_flat_keys(self):
        run_spike = self._get_run_spike()
        dirs = self._fresh()
        record = self._run(run_spike, dirs, self._fake())
        self.assertIsInstance(record, dict)
        self.assertTrue(REQUIRED_RECORD_KEYS.issubset(set(record)))
        # The pinnable values, from the fake's canned result.
        self.assertEqual(0, record["exit_code"])
        self.assertEqual(2.5, record["wall_time_s"])
        self.assertIs(False, record["waited_for_input"])
        self.assertIs(False, record["team_tool_seen"])
        self.assertEqual([], record["crew_tree"])
        self.assertEqual(TIMESTAMP, record["timestamp"])
        self.assertIsInstance(record["config"], str)
        self.assertNotEqual("", record["config"])
        # The fixture assertion: the fake did not edit the fixture, so red.
        self.assertIs(False, record["assertion"]["passed"])
        self.assertIsInstance(record["assertion"]["stderr"], str)
        self.assertIs(False, record["completed"])

    def test_run_spike_completed_true_when_exit_zero_and_assertion_passes(self):
        run_spike = self._get_run_spike()
        dirs = self._fresh()
        record = self._run(run_spike, dirs, self._fake(edit=True))
        self.assertIs(True, record["assertion"]["passed"])
        self.assertIs(True, record["completed"])

    def test_run_spike_completed_false_when_exit_nonzero_even_if_assertion_passes(
        self,
    ):
        run_spike = self._get_run_spike()
        dirs = self._fresh()
        fake = self._fake(
            edit=True,
            result={
                "exit_code": 3,
                "stdout": "done\n",
                "stderr": "",
                "wall_time_s": 2.5,
                "timed_out": False,
                "evidence": "",
            },
        )
        record = self._run(run_spike, dirs, fake)
        self.assertIs(True, record["assertion"]["passed"])
        self.assertIs(False, record["completed"])


class TestTeamToolSeen(PicrewTestCase):
    """team_tool_seen is derived from the captured stdout JSONL: one
    recorded stream names the ``team`` tool, one does not."""

    def test_run_spike_team_tool_seen_true_when_stdout_records_team_tool(self):
        run_spike = self._get_run_spike()
        dirs = self._fresh()
        fake = self._fake(
            result={
                "exit_code": 0,
                "stdout": TEAM_STDOUT,
                "stderr": "",
                "wall_time_s": 1.25,
                "timed_out": False,
                "evidence": "",
            }
        )
        record = self._run(run_spike, dirs, fake)
        self.assertIs(True, record["team_tool_seen"])

    def test_run_spike_team_tool_seen_false_when_stdout_records_other_tools_only(
        self,
    ):
        run_spike = self._get_run_spike()
        dirs = self._fresh()
        fake = self._fake(
            result={
                "exit_code": 0,
                "stdout": NO_TEAM_STDOUT,
                "stderr": "",
                "wall_time_s": 1.25,
                "timed_out": False,
                "evidence": "",
            }
        )
        record = self._run(run_spike, dirs, fake)
        self.assertIs(False, record["team_tool_seen"])


class TestCrewTree(PicrewTestCase):
    """crew_tree is the sorted relative-path listing of
    <fixture>/.crew/ - empty when the tree is absent."""

    def test_run_spike_crew_tree_lists_sorted_relative_paths(self):
        run_spike = self._get_run_spike()
        dirs = self._fresh()
        fake = self._fake(
            crew_tree=["tasks/task-1.json", "manifest.json", "events/events.jsonl"]
        )
        record = self._run(run_spike, dirs, fake)
        self.assertEqual(
            ["events/events.jsonl", "manifest.json", "tasks/task-1.json"],
            record["crew_tree"],
        )

    def test_run_spike_crew_tree_empty_when_tree_absent(self):
        run_spike = self._get_run_spike()
        dirs = self._fresh()
        record = self._run(run_spike, dirs, self._fake())
        self.assertEqual([], record["crew_tree"])


class TestRecordedOutcomes(PicrewTestCase):
    """A non-zero exit and a budget-exhausted run are recorded outcomes,
    never exceptions."""

    def test_run_spike_nonzero_exit_recorded_not_raised(self):
        run_spike = self._get_run_spike()
        dirs = self._fresh()
        fake = self._fake(
            result={
                "exit_code": 3,
                "stdout": "partial output\n",
                "stderr": "crew: worker failed\n",
                "wall_time_s": 42.0,
                "timed_out": False,
                "evidence": "",
            }
        )
        record = self._run(run_spike, dirs, fake)
        self.assertEqual(3, record["exit_code"])
        self.assertIs(False, record["waited_for_input"])
        self.assertIs(False, record["completed"])
        # The output is still captured on a failed run.
        results = dirs["base"] / "results"
        self.assertEqual(
            "partial output\n", (results / "stdout").read_text(encoding="utf-8")
        )
        self.assertEqual(
            "crew: worker failed\n", (results / "stderr").read_text(encoding="utf-8")
        )
        self.assertTrue((dirs["base"] / "record.json").is_file())

    def test_run_spike_timeout_recorded_with_waited_for_input_true(self):
        run_spike = self._get_run_spike()
        dirs = self._fresh()
        fake = self._fake(
            result={
                "exit_code": -9,
                "stdout": "",
                "stderr": "",
                "wall_time_s": TIMEOUT_S,
                "timed_out": True,
                "evidence": "timeout after 1800.0s; process killed",
            }
        )
        record = self._run(run_spike, dirs, fake)
        self.assertIs(True, record["waited_for_input"])
        self.assertEqual(-9, record["exit_code"])
        self.assertEqual(TIMEOUT_S, record["wall_time_s"])
        self.assertIs(False, record["completed"])
        self.assertTrue((dirs["base"] / "record.json").is_file())


class TestRunSpikeErrors(PicrewTestCase):
    """An empty model id or extension path raises CrewSpikeError naming
    the value, before any runner invocation."""

    def test_run_spike_empty_model_id_raises_crew_spike_error_before_runner(self):
        run_spike = self._get_run_spike()
        crew_spike_error = self._get_crew_spike_error()
        for value in ("", "   "):
            with self.subTest(model_id=value):
                dirs = self._fresh()
                fake = self._fake()
                with self.assertRaises(crew_spike_error) as ctx:
                    self._run(run_spike, dirs, fake, model_id=value)
                self.assertIn("model", str(ctx.exception).lower())
                self.assertEqual([], fake._calls)  # type: ignore[attr-defined]

    def test_run_spike_empty_extension_path_raises_crew_spike_error_before_runner(
        self,
    ):
        run_spike = self._get_run_spike()
        crew_spike_error = self._get_crew_spike_error()
        for value in ("", "   "):
            with self.subTest(extension_path=value):
                dirs = self._fresh()
                fake = self._fake()
                with self.assertRaises(crew_spike_error) as ctx:
                    self._run(run_spike, dirs, fake, extension_path=value)
                self.assertIn("extension", str(ctx.exception).lower())
                self.assertEqual([], fake._calls)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# anvilkit.pi.picrew.main - the in-container entrypoint. The compose
# service runs ``python3 -m anvilkit.pi.picrew`` with the gateway address
# in the environment and the read-only config.yaml bind mounted.
#
# ``run_spike`` is monkeypatched with a signature-bound recorder, so no
# test touches pi, npm or the gateway; the environment is patched per
# test (``PI_GATEWAY_HOST``/``PI_GATEWAY_PORT`` required,
# ``PI_CONFIG_PATH`` and ``PI_RESULTS_DIR`` optional).
# ---------------------------------------------------------------------------

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

PINNED_DEFAULT_CONFIG_PATH = "/app/config.yaml"
PINNED_DEFAULT_RESULTS_DIR = "/workspace/results"
PINNED_DEFAULT_EXTENSION_PATH = "/usr/local/lib/node_modules/pi-crew/index.ts"

TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class TestMain(PicrewTestCase):
    """main - the in-container entrypoint."""

    def _get_main(self) -> Callable:
        """Fetch ``anvilkit.pi.picrew.main``, failing clearly if absent."""
        picrew = self._picrew()
        main = getattr(picrew, "main", None)
        self.assertTrue(
            callable(main),
            "anvilkit.pi.picrew.main is not callable; the in-container "
            "entrypoint has not been implemented yet",
        )
        return main

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

    def _dummy_record(self) -> Dict[str, Any]:
        """A flat record the run_spike stand-in can return."""
        return {
            "config": "crew-spike",
            "completed": False,
            "exit_code": 0,
            "wall_time_s": 1.0,
            "waited_for_input": False,
            "team_tool_seen": False,
            "crew_tree": [],
            "artifacts": {},
            "timestamp": TIMESTAMP,
        }

    def _recorder(self, picrew, record: Optional[Dict[str, Any]] = None):
        """A ``run_spike`` stand-in that records its bound call arguments.

        Signature-bound against the real ``run_spike`` so the pin does not
        depend on whether ``main`` calls it positionally or by keyword.
        Returns ``(patcher, recorder)``; ``recorder.calls`` is the list of
        bound-argument dicts, one entry per call.
        """
        real_run_spike = picrew.run_spike
        signature = inspect.signature(real_run_spike)

        def recorder(*args, **kwargs):
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            recorder.calls.append(dict(bound.arguments))  # type: ignore[attr-defined]
            return dict(record if record is not None else self._dummy_record())

        recorder.calls = []  # type: ignore[attr-defined]
        return mock.patch.object(picrew, "run_spike", recorder), recorder

    def test_main_missing_gateway_host_raises_crew_spike_error_before_runner(self):
        main = self._get_main()
        crew_spike_error = self._get_crew_spike_error()
        picrew = self._picrew()
        config_path = self._write_config()
        env = self._happy_env(config_path)
        del env["PI_GATEWAY_HOST"]
        patcher, recorder = self._recorder(picrew)
        fake = self._fake()
        with patcher, mock.patch.dict(os.environ, env):
            with self.assertRaises(crew_spike_error) as ctx:
                main(runner=fake)
        self.assertIn("PI_GATEWAY_HOST", str(ctx.exception))
        self.assertEqual([], fake._calls)  # type: ignore[attr-defined]
        self.assertEqual([], recorder.calls)  # type: ignore[attr-defined]

    def test_main_empty_gateway_port_raises_crew_spike_error_before_runner(self):
        main = self._get_main()
        crew_spike_error = self._get_crew_spike_error()
        picrew = self._picrew()
        config_path = self._write_config()
        env = self._happy_env(config_path, PI_GATEWAY_PORT="")
        patcher, recorder = self._recorder(picrew)
        fake = self._fake()
        with patcher, mock.patch.dict(os.environ, env):
            with self.assertRaises(crew_spike_error) as ctx:
                main(runner=fake)
        self.assertIn("PI_GATEWAY_PORT", str(ctx.exception))
        self.assertEqual([], fake._calls)  # type: ignore[attr-defined]
        self.assertEqual([], recorder.calls)  # type: ignore[attr-defined]

    def test_main_non_numeric_gateway_port_raises_crew_spike_error_before_runner(
        self,
    ):
        main = self._get_main()
        crew_spike_error = self._get_crew_spike_error()
        picrew = self._picrew()
        config_path = self._write_config()
        env = self._happy_env(config_path, PI_GATEWAY_PORT="not-a-port")
        patcher, recorder = self._recorder(picrew)
        fake = self._fake()
        with patcher, mock.patch.dict(os.environ, env):
            with self.assertRaises(crew_spike_error) as ctx:
                main(runner=fake)
        self.assertIn("PI_GATEWAY_PORT", str(ctx.exception))
        self.assertEqual([], fake._calls)  # type: ignore[attr-defined]
        self.assertEqual([], recorder.calls)  # type: ignore[attr-defined]

    def test_main_unreadable_config_raises_config_error_unwrapped(self):
        main = self._get_main()
        picrew = self._picrew()
        config_path = self._write_config()
        missing = config_path.parent / "does-not-exist.yaml"
        env = self._happy_env(config_path, PI_CONFIG_PATH=str(missing))
        patcher, recorder = self._recorder(picrew)
        with patcher, mock.patch.dict(os.environ, env):
            # The ConfigError from anvilkit.config, propagated as-is -
            # not wrapped into a CrewSpikeError or any other type.
            with self.assertRaises(piconfig.ConfigError):
                main()
        self.assertEqual([], recorder.calls)  # type: ignore[attr-defined]

    def test_main_returns_zero_when_run_measured(self):
        main = self._get_main()
        picrew = self._picrew()
        config_path = self._write_config()
        env = self._happy_env(config_path)
        patcher, recorder = self._recorder(picrew)
        with patcher, mock.patch.dict(os.environ, env):
            self.assertEqual(0, main())
        self.assertEqual(1, len(recorder.calls))  # type: ignore[attr-defined]

    def test_main_returns_zero_when_recorded_outcome_is_failure(self):
        main = self._get_main()
        picrew = self._picrew()
        config_path = self._write_config()
        env = self._happy_env(config_path)
        # A measured run whose record carries a failed outcome: the
        # verdict is data, not an exit condition - a run that measured a
        # failure is a successful run, so main still returns 0.
        failure_record = self._dummy_record()
        failure_record.update({"exit_code": 3, "completed": False})
        patcher, _ = self._recorder(picrew, record=failure_record)
        with patcher, mock.patch.dict(os.environ, env):
            self.assertEqual(0, main())

    def test_main_injected_runner_passed_to_run_spike_verbatim(self):
        main = self._get_main()
        picrew = self._picrew()
        config_path = self._write_config()
        env = self._happy_env(config_path)
        fake_runner = object()
        patcher, recorder = self._recorder(picrew)
        with patcher, mock.patch.dict(os.environ, env):
            self.assertEqual(0, main(runner=fake_runner))
        self.assertIs(
            fake_runner, recorder.calls[0]["runner"]  # type: ignore[attr-defined]
        )

    def test_main_default_runner_is_pibakeoff_subprocess_runner(self):
        main = self._get_main()
        picrew = self._picrew()
        config_path = self._write_config()
        env = self._happy_env(config_path)
        patcher, recorder = self._recorder(picrew)
        with patcher, mock.patch.dict(os.environ, env):
            self.assertEqual(0, main())
        self.assertIs(
            pibakeoff.subprocess_runner,
            recorder.calls[0]["runner"],  # type: ignore[attr-defined]
        )

    def test_main_passes_gateway_env_and_config_topology_to_run_spike(self):
        main = self._get_main()
        picrew = self._picrew()
        # The container defaults, pinned like the bake-off entrypoint.
        self.assertEqual(PINNED_DEFAULT_CONFIG_PATH, picrew._DEFAULT_CONFIG_PATH)
        self.assertEqual(PINNED_DEFAULT_RESULTS_DIR, picrew._DEFAULT_RESULTS_DIR)
        config_path = self._write_config()
        env = self._happy_env(config_path)
        patcher, recorder = self._recorder(picrew)
        with patcher, mock.patch.dict(os.environ, env):
            self.assertEqual(0, main())
        seen = recorder.calls[0]  # type: ignore[attr-defined]
        # Results land at the pinned container results directory, as a Path.
        self.assertEqual(Path(PINNED_DEFAULT_RESULTS_DIR), seen["base_dir"])
        # The model id and context window are read_models' answer, verbatim.
        self.assertEqual("test/coder-model", seen["model_id"])
        self.assertEqual(12345, seen["context_window"])
        # The gateway address is the service environment, port as an int.
        self.assertEqual("llama-swap", seen["gateway_host"])
        self.assertEqual(8080, seen["gateway_port"])
        self.assertIsInstance(seen["gateway_port"], int)
        # The crew extension, from the pinned global npm root.
        self.assertEqual(PINNED_DEFAULT_EXTENSION_PATH, seen["extension_path"])
        # max_tokens and the per-run timeout are module-owned values.
        self.assertIsInstance(seen["max_tokens"], int)
        self.assertGreater(seen["max_tokens"], 0)
        self.assertGreater(seen["timeout_s"], 0)
        # main supplies the stamp itself; the container default agent home.
        self.assertRegex(seen["timestamp"], TIMESTAMP_PATTERN)
        self.assertIsNone(seen["agent_home"])

    def test_main_results_dir_honours_pi_results_dir_env(self):
        main = self._get_main()
        picrew = self._picrew()
        config_path = self._write_config()
        env = self._happy_env(config_path, PI_RESULTS_DIR="/custom/results")
        patcher, recorder = self._recorder(picrew)
        with patcher, mock.patch.dict(os.environ, env):
            self.assertEqual(0, main())
        self.assertEqual(
            Path("/custom/results"),
            recorder.calls[0]["base_dir"],  # type: ignore[attr-defined]
        )

    def test_main_guard_is_the_only_sys_exit_and_is_last(self):
        picrew = self._picrew()
        source = Path(picrew.__file__).read_text(encoding="utf-8")
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
