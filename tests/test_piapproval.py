"""Tests for anvilkit.piapproval - the phase-2 approval run driver.

Written before the implementation (TDD, ``plans/pi-phase2-approval.md``,
behaviour 6: "run one approval configuration"). The production module
``anvilkit.piapproval`` does not exist yet, so every test loads it through
``_piapproval``, which fails with a clear assertion instead of letting a
collection-time ImportError mask the reason the suite is red.

Design constraint pinned here: no test spawns ``pi``. ``run_one`` takes
process execution as an **injected runner callable** following the
``anvilkit.pibakeoff`` contract, and every test supplies a recorder fake
that captures the invocation dict and returns a canned result.

Pinned signature::

    run_one(config, project_dir, results_dir, runner, agent_dir, model_id,
            gateway_host, gateway_port, context_window, max_tokens,
            prompt, marker, unreachable_command, *, timestamp) -> dict

- ``config`` is one of ``"approve"``, ``"no-approve"``,
  ``"mcp-list-approve"``, ``"mcp-list-no-approve"``;
- ``project_dir``: the fresh project directory; ``run_one`` writes the
  ``pitrust.write_project`` fixture into it, and it is the runner's cwd;
- ``results_dir``: where the artifacts land; created if missing (its parent
  exists);
- ``runner``: the process-execution seam; one call per ``run_one``;
- ``agent_dir``: the ISOLATED per-run agent directory (the value handed to
  the child as ``PI_CODING_AGENT_DIR``); never the invoking user's home -
  every test passes an explicit temp directory;
- ``model_id``, ``gateway_host``, ``gateway_port``, ``context_window``,
  ``max_tokens``: feed both the argv (``model_id``) and the models document
  written to ``<agent_dir>/.pi/agent/models.json``;
- ``prompt``: the fixed phase-2 marker prompt (the tests own its value);
- ``marker``: the marker token the project fixture's APPEND_SYSTEM.md
  instructs the model to echo;
- ``unreachable_command``: the single executable not on PATH that the
  project ``mcp.json`` entry names;
- ``timestamp``: the ISO-8601 UTC stamp stored verbatim in the record.

Pinned per-config budgets (passed to the runner as ``timeout_s``):

- ``approve`` / ``no-approve`` (the two ``--mode json`` configs): 300.0
- ``mcp-list-approve`` / ``mcp-list-no-approve``: 60.0

Pinned runner contract (the ``anvilkit.pibakeoff`` seam, plus the
behaviour-4 env overlay)::

    invocation: {"argv": List[str], "cwd": str, "stdin": "/dev/null",
                 "timeout_s": float,
                 "env": {"PI_CODING_AGENT_DIR": str(agent_dir)}}
    result:     {"exit_code": int, "stdout": str, "stderr": str,
                 "wall_time_s": float, "timed_out": bool, "evidence": str}

Pinned ``run_one`` responsibilities:

- the project fixture via ``pitrust.write_project`` into ``project_dir``
  (``.pi/settings.json``, ``.pi/APPEND_SYSTEM.md`` carrying the marker,
  ``.pi/mcp.json`` with the one unreachable stdio server named
  ``anvil-trust-probe``);
- the models document at ``<agent_dir>/.pi/agent/models.json`` - exactly
  ``json.dumps`` of
  ``piargv.models_document(model_id, gateway_port, context_window,
  max_tokens, host=gateway_host)``; the agent directory is a DIFFERENT
  directory from the project directory;
- the runner invoked exactly once, with the config's exact argv
  (``piargv.approval_argv(model_id, prompt, approve)`` /
  ``piargv.mcp_list_argv(approve)``), ``cwd = str(project_dir)``, stdin
  ``/dev/null``, the config's budget, and an ``env`` dict carrying
  ``PI_CODING_AGENT_DIR`` pointing at the per-run agent directory;
- artifacts ``stdout`` and ``stderr`` in ``results_dir`` for every config,
  and ``events.jsonl`` (verbatim stdout) ONLY for the two ``--mode json``
  configs - absent for the mcp-list configs;
- the record is exactly what ``pirecord.build`` produces, with the
  assertion dimension computed from the captured assistant output (the
  runner's stdout): for the model configs the marker must be present; for
  the mcp-list configs the server name ``anvil-trust-probe`` must be
  present. A missing marker (or server name) is a recorded
  ``passed: False``, never an exception;
- a timed-out runner result (``timed_out: True``) yields a record with
  ``waited_for_input: True``, the partial stream still in the ``stdout``
  artifact and the runner's ``evidence`` written to ``evidence.txt`` in
  ``results_dir`` - never an exception.

One exception type: ``ApprovalError`` - raised (naming the value) for an
unknown ``config``, before the runner is invoked.
"""

import importlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import anvilkit.piargv as piargv
import anvilkit.pievents as pievents
import anvilkit.pirecord as pirecord

MODEL_ID = "matrix.vars.coder"
GATEWAY_HOST = "llama-swap"
GATEWAY_PORT = 8080
CONTEXT_WINDOW = 32768
MAX_TOKENS = 4096
TIMESTAMP = "2026-10-21T00:00:00Z"

# The tests own these values; the module takes them as arguments and must
# never hardcode them.
PROMPT = (
    "Reply with the marker token ANVIL-PHASE2-MARKER in one word, "
    "and nothing else."
)
MARKER = "ANVIL-PHASE2-MARKER"
UNREACHABLE_COMMAND = "anvil-nonexistent-mcp-server"

# The server name the project mcp.json entry carries - the assertion
# target for the two mcp-list configs.
SERVER_NAME = "anvil-trust-probe"

# Per-config wall-clock budgets (plans/pi-phase2-approval.md, behaviour 6):
# 300 s per model run, 60 s per mcp-list run.
BUDGET_APPROVE_S = 300.0
BUDGET_MCP_LIST_S = 60.0

# A realistic two-line JSONL stream whose message_end carries the marker:
# the ``--mode json`` assistant output for the positive marker case.
JSONL_WITH_MARKER = "\n".join(
    [
        json.dumps(
            {
                "type": "message_update",
                "usage": {
                    "input": 800,
                    "output": 12,
                    "totalTokens": 812,
                    "cost": {"total": 0.0004},
                },
            }
        ),
        json.dumps(
            {"type": "message_end", "message": {"content": MARKER}}
        ),
    ]
) + "\n"

# The same framing without the marker: the negative marker case. The marker
# must not appear anywhere in the stream.
JSONL_WITHOUT_MARKER = "\n".join(
    [
        json.dumps(
            {
                "type": "message_update",
                "usage": {
                    "input": 800,
                    "output": 4,
                    "totalTokens": 804,
                    "cost": {"total": 0.0004},
                },
            }
        ),
        json.dumps(
            {"type": "message_end", "message": {"content": "understood"}}
        ),
    ]
) + "\n"
assert MARKER not in JSONL_WITHOUT_MARKER

# The partial stream a timed-out --mode json run may have drained before
# the kill: one line, still valid JSONL.
JSONL_PARTIAL = (
    json.dumps(
        {
            "type": "message_update",
            "usage": {
                "input": 100,
                "output": 1,
                "totalTokens": 101,
                "cost": {"total": 0.0001},
            },
        }
    )
    + "\n"
)

# ``pi mcp list --json`` stdout with the probe server reachable on paper:
# the positive mcp-list case.
MCP_LIST_WITH_SERVER = json.dumps(
    {
        "servers": [
            {
                "name": SERVER_NAME,
                "enabled": True,
                "connected": False,
                "error": "spawn anvil-nonexistent-mcp-server ENOENT",
            }
        ]
    },
    indent=2,
) + "\n"

# The negative mcp-list case: a valid document that never names the server.
MCP_LIST_WITHOUT_SERVER = json.dumps({"servers": []}, indent=2) + "\n"
assert SERVER_NAME not in MCP_LIST_WITHOUT_SERVER

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

CONFIGS = (
    "approve",
    "no-approve",
    "mcp-list-approve",
    "mcp-list-no-approve",
)


class PiapprovalTestCase(unittest.TestCase):
    """Shared guard + fake-runner machinery for the red module."""

    def _piapproval(self):
        """Import anvilkit.piapproval, failing clearly if the module is absent."""
        spec = importlib.util.find_spec("anvilkit.piapproval")
        self.assertIsNotNone(
            spec,
            "anvilkit.piapproval cannot be imported; the phase-2 approval "
            "run driver (behaviour 6) has not been implemented yet",
        )
        return importlib.import_module("anvilkit.piapproval")

    def _get_run_one(self) -> Callable:
        """Fetch ``anvilkit.piapproval.run_one``, failing clearly if absent."""
        piapproval = self._piapproval()
        run_one = getattr(piapproval, "run_one", None)
        self.assertTrue(
            callable(run_one),
            "anvilkit.piapproval.run_one is not callable; the run-one "
            "driver (behaviour 6) has not been implemented yet",
        )
        return run_one

    def _get_approval_error(self):
        """Fetch ``anvilkit.piapproval.ApprovalError``, failing clearly if absent."""
        piapproval = self._piapproval()
        approval_error = getattr(piapproval, "ApprovalError", None)
        self.assertTrue(
            isinstance(approval_error, type)
            and issubclass(approval_error, Exception),
            "anvilkit.piapproval.ApprovalError is not an exception type; "
            "the unknown-config guard (behaviour 6) has not been "
            "implemented yet",
        )
        return approval_error

    def _fake(
        self, result: Optional[Dict[str, Any]] = None
    ) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
        """A recorder runner capturing each invocation, canned result."""

        def fake_runner(invocation: Dict[str, Any]) -> Dict[str, Any]:
            fake_runner._calls.append(dict(invocation))
            if result is not None:
                return dict(result)
            return self._default_result()

        fake_runner._calls = []
        return fake_runner

    @staticmethod
    def _default_result() -> Dict[str, Any]:
        """A clean, successful runner result (the baseline)."""
        return {
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "wall_time_s": 1.5,
            "timed_out": False,
            "evidence": "",
        }

    def _fresh(self) -> Dict[str, Path]:
        """A per-test temp tree: project dir, results dir, agent dir.

        The agent dir is a DIFFERENT temp directory from the project dir:
        the isolated per-run agent directory, never the user's home.
        """
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        return {
            "root": root,
            "project": root / "project",
            "results": root / "results",
            "agent_dir": root / "agent",
        }

    def _run(
        self, run_one, dirs: Dict[str, Path], config: str, fake, **overrides
    ) -> Dict[str, Any]:
        """Call run_one with the standard inputs; ``overrides`` replace one."""
        kwargs = dict(
            config=config,
            project_dir=dirs["project"],
            results_dir=dirs["results"],
            runner=fake,
            agent_dir=dirs["agent_dir"],
            model_id=MODEL_ID,
            gateway_host=GATEWAY_HOST,
            gateway_port=GATEWAY_PORT,
            context_window=CONTEXT_WINDOW,
            max_tokens=MAX_TOKENS,
            prompt=PROMPT,
            marker=MARKER,
            unreachable_command=UNREACHABLE_COMMAND,
            timestamp=TIMESTAMP,
        )
        kwargs.update(overrides)
        return run_one(**kwargs)

    @staticmethod
    def _argv_for(config: str) -> list:
        """The exact argv a config must hand to the runner."""
        if config == "approve":
            return piargv.approval_argv(MODEL_ID, PROMPT, True)
        if config == "no-approve":
            return piargv.approval_argv(MODEL_ID, PROMPT, False)
        if config == "mcp-list-approve":
            return piargv.mcp_list_argv(True)
        if config == "mcp-list-no-approve":
            return piargv.mcp_list_argv(False)
        raise AssertionError("unknown config in test: " + config)

    @staticmethod
    def _budget_for(config: str) -> float:
        if config in ("approve", "no-approve"):
            return BUDGET_APPROVE_S
        return BUDGET_MCP_LIST_S

    def _assert_invocation(self, fake, dirs: Dict[str, Path], config: str) -> None:
        """Exactly one runner call, with the full pinned invocation dict."""
        self.assertEqual(
            1,
            len(fake._calls),
            "the runner must be invoked exactly once per run_one",
        )
        self.assertEqual(
            {
                "argv": self._argv_for(config),
                "cwd": str(dirs["project"]),
                "stdin": "/dev/null",
                "timeout_s": self._budget_for(config),
                "env": {
                    "PI_CODING_AGENT_DIR": str(dirs["agent_dir"])
                },
            },
            fake._calls[0],
            "the runner invocation must carry exactly the config's argv, "
            "cwd = project dir, stdin /dev/null, the config's budget, "
            "and an env dict pointing PI_CODING_AGENT_DIR at the per-run "
            "agent directory",
        )

    @staticmethod
    def _expected_record(
        *,
        config: str,
        dirs: Dict[str, Path],
        exit_code: int,
        wall_time_s: float,
        waited_for_input: bool,
        jsonl: Optional[str],
        stdout: str,
        passed: bool,
        kind: str,
        detail: str,
    ) -> Dict[str, Any]:
        """The record pirecord.build must produce for these dimensions.

        The phase-2 runs run with tools disabled (``-nt`` / mcp-list), so
        the project tree is never edited and ``changed_files`` is empty.
        For the mcp-list configs the stdout is not a JSONL stream, so the
        stream accounting runs on the empty event list.
        """
        results = dirs["results"]
        events = (
            pievents.parse(stdout)["events"] if jsonl is not None else []
        )
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
            outcome=pievents.outcome(events),
            assertion={"passed": passed, "kind": kind, "detail": detail},
            changed_files=[],
            timestamp=TIMESTAMP,
        )


class TestModuleGuards(PiapprovalTestCase):
    """The red step: the module, its function and its exception type."""

    def test_module_is_importable(self):
        self._piapproval()

    def test_run_one_is_callable(self):
        self._get_run_one()

    def test_approval_error_is_an_exception_type(self):
        self._get_approval_error()


class TestRunOneInvocation(PiapprovalTestCase):
    """run_one invokes the injected runner exactly once with the
    configuration's exact argv, cwd, stdin, budget and agent-dir env."""

    def test_invocation_approve_argv_cwd_stdin_budget_env(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake(result=self._result_with_stdout(JSONL_WITH_MARKER))
        self._run(run_one, dirs, "approve", fake)
        self._assert_invocation(fake, dirs, "approve")

    def test_invocation_no_approve_argv_uses_no_approve_flag(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake(result=self._result_with_stdout(JSONL_WITH_MARKER))
        self._run(run_one, dirs, "no-approve", fake)
        self._assert_invocation(fake, dirs, "no-approve")
        self.assertIn("-na", fake._calls[0]["argv"])
        self.assertNotIn("-a", fake._calls[0]["argv"])

    def test_invocation_mcp_list_approve_argv(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake(result=self._result_with_stdout(MCP_LIST_WITH_SERVER))
        self._run(run_one, dirs, "mcp-list-approve", fake)
        self._assert_invocation(fake, dirs, "mcp-list-approve")

    def test_invocation_mcp_list_no_approve_argv(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake(result=self._result_with_stdout(MCP_LIST_WITH_SERVER))
        self._run(run_one, dirs, "mcp-list-no-approve", fake)
        self._assert_invocation(fake, dirs, "mcp-list-no-approve")
        self.assertIn("-na", fake._calls[0]["argv"])

    def test_budget_approve_is_300_seconds(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake()
        self._run(run_one, dirs, "approve", fake)
        self.assertEqual(
            BUDGET_APPROVE_S,
            fake._calls[0]["timeout_s"],
            "the approve config must carry the 300 s model-run budget",
        )

    def test_budget_no_approve_is_300_seconds(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake()
        self._run(run_one, dirs, "no-approve", fake)
        self.assertEqual(
            BUDGET_APPROVE_S,
            fake._calls[0]["timeout_s"],
            "the no-approve config must carry the 300 s model-run budget",
        )

    def test_budget_mcp_list_approve_is_60_seconds(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake()
        self._run(run_one, dirs, "mcp-list-approve", fake)
        self.assertEqual(
            BUDGET_MCP_LIST_S,
            fake._calls[0]["timeout_s"],
            "the mcp-list-approve config must carry the 60 s budget",
        )

    def test_budget_mcp_list_no_approve_is_60_seconds(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake()
        self._run(run_one, dirs, "mcp-list-no-approve", fake)
        self.assertEqual(
            BUDGET_MCP_LIST_S,
            fake._calls[0]["timeout_s"],
            "the mcp-list-no-approve config must carry the 60 s budget",
        )

    def test_env_points_pi_coding_agent_dir_at_the_agent_dir(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake()
        self._run(run_one, dirs, "approve", fake)
        env = fake._calls[0]["env"]
        self.assertIsInstance(
            env,
            dict,
            "the runner invocation must carry an env overlay dict",
        )
        self.assertEqual(
            str(dirs["agent_dir"]),
            env.get("PI_CODING_AGENT_DIR"),
            "the env overlay must point PI_CODING_AGENT_DIR at the "
            "per-run agent directory",
        )

    @staticmethod
    def _result_with_stdout(stdout: str) -> Dict[str, Any]:
        result = PiapprovalTestCase._default_result()
        result["stdout"] = stdout
        return result


class TestModelsDocumentAndProject(PiapprovalTestCase):
    """run_one writes the isolated agent-directory models document and
    the project fixture, keeping the agent directory away from the
    project directory."""

    def test_models_document_at_agent_dir_matches_models_document(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake()
        self._run(run_one, dirs, "approve", fake)
        models_path = dirs["agent_dir"] / ".pi" / "agent" / "models.json"
        self.assertTrue(
            models_path.is_file(),
            "the models document must be written to "
            "<agent_dir>/.pi/agent/models.json",
        )
        expected = piargv.models_document(
            MODEL_ID,
            GATEWAY_PORT,
            CONTEXT_WINDOW,
            MAX_TOKENS,
            host=GATEWAY_HOST,
        )
        self.assertEqual(
            expected,
            json.loads(models_path.read_text(encoding="utf-8")),
            "the models document must parse to piargv.models_document "
            "for the gateway (providers/llamaswap/baseUrl)",
        )

    def test_agent_dir_is_a_different_directory_from_project_dir(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake()
        self._run(run_one, dirs, "approve", fake)
        self.assertNotEqual(
            dirs["agent_dir"].resolve(),
            dirs["project"].resolve(),
            "the agent directory must be isolated from the project "
            "directory",
        )
        self.assertTrue(
            (dirs["agent_dir"] / ".pi" / "agent" / "models.json").is_file(),
            "the models document must live under the agent directory, "
            "not the project directory",
        )
        self.assertFalse(
            (dirs["project"] / ".pi" / "agent").exists(),
            "the project .pi/ must not grow an agent/ subtree",
        )

    def test_project_fixture_written_with_unreachable_server(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake()
        self._run(run_one, dirs, "mcp-list-approve", fake)
        pi_dir = dirs["project"] / ".pi"
        for name in ("settings.json", "APPEND_SYSTEM.md", "mcp.json"):
            self.assertTrue(
                (pi_dir / name).is_file(),
                "the project fixture must include .pi/" + name,
            )
        self.assertIn(
            MARKER,
            (pi_dir / "APPEND_SYSTEM.md").read_text(encoding="utf-8"),
            "APPEND_SYSTEM.md must instruct the marker token",
        )
        mcp = json.loads((pi_dir / "mcp.json").read_text(encoding="utf-8"))
        servers = mcp.get("mcpServers")
        self.assertIsInstance(servers, dict)
        self.assertEqual(
            [SERVER_NAME],
            sorted(servers),
            "the project mcp.json must carry exactly one server named "
            "anvil-trust-probe",
        )
        self.assertEqual(
            UNREACHABLE_COMMAND,
            servers[SERVER_NAME].get("command"),
            "the single mcpServers entry must name the unreachable "
            "command passed to run_one",
        )


class TestRecordAndArtifacts(PiapprovalTestCase):
    """run_one returns the pirecord.build record for the run and writes
    the artifacts the record's dimensions require."""

    def test_clean_approve_run_returns_thirteen_key_record(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake(result=self._result_with_stdout(JSONL_WITH_MARKER))
        record = self._run(run_one, dirs, "approve", fake)
        self.assertEqual(RECORD_KEYS, set(record))
        expected = self._expected_record(
            config="approve",
            dirs=dirs,
            exit_code=0,
            wall_time_s=1.5,
            waited_for_input=False,
            jsonl=str(dirs["results"] / "events.jsonl"),
            stdout=JSONL_WITH_MARKER,
            passed=True,
            kind="marker",
            detail="marker found in assistant output",
        )
        self.assertEqual(expected, record)

    def test_events_jsonl_written_only_for_mode_json_configs(self):
        run_one = self._get_run_one()
        for config, payload in (
            ("approve", JSONL_WITH_MARKER),
            ("no-approve", JSONL_WITH_MARKER),
        ):
            with self.subTest(config=config):
                dirs = self._fresh()
                fake = self._fake(
                    result=self._result_with_stdout(payload)
                )
                record = self._run(run_one, dirs, config, fake)
                events_path = dirs["results"] / "events.jsonl"
                self.assertTrue(
                    events_path.is_file(),
                    config + " must write events.jsonl to the results "
                    "directory",
                )
                self.assertEqual(
                    payload,
                    events_path.read_text(encoding="utf-8"),
                    "events.jsonl must carry the captured stdout "
                    "verbatim",
                )
                self.assertEqual(
                    str(events_path),
                    record["artifacts"]["jsonl"],
                    "the record's jsonl artifact must point at "
                    "events.jsonl for the --mode json configs",
                )
        for config, payload in (
            ("mcp-list-approve", MCP_LIST_WITH_SERVER),
            ("mcp-list-no-approve", MCP_LIST_WITH_SERVER),
        ):
            with self.subTest(config=config):
                dirs = self._fresh()
                fake = self._fake(
                    result=self._result_with_stdout(payload)
                )
                record = self._run(run_one, dirs, config, fake)
                self.assertFalse(
                    (dirs["results"] / "events.jsonl").exists(),
                    config + " must NOT write events.jsonl (the mcp-list "
                    "configs produce no JSONL stream)",
                )
                self.assertIsNone(
                    record["artifacts"]["jsonl"],
                    "the record's jsonl artifact must be None for the "
                    "mcp-list configs",
                )

    def test_stdout_and_stderr_artifacts_written_for_every_config(self):
        run_one = self._get_run_one()
        for config, payload in (
            ("approve", JSONL_WITH_MARKER),
            ("no-approve", JSONL_WITH_MARKER),
            ("mcp-list-approve", MCP_LIST_WITH_SERVER),
            ("mcp-list-no-approve", MCP_LIST_WITH_SERVER),
        ):
            with self.subTest(config=config):
                stderr_text = "probe: unreachable server\n"
                dirs = self._fresh()
                fake = self._fake(
                    result=self._result_with_stdout(payload, stderr_text)
                )
                record = self._run(run_one, dirs, config, fake)
                stdout_artifact = dirs["results"] / "stdout"
                stderr_artifact = dirs["results"] / "stderr"
                self.assertTrue(stdout_artifact.is_file())
                self.assertTrue(stderr_artifact.is_file())
                self.assertEqual(
                    payload,
                    stdout_artifact.read_text(encoding="utf-8"),
                    "the stdout artifact must carry the runner's stdout "
                    "verbatim",
                )
                self.assertEqual(
                    stderr_text,
                    stderr_artifact.read_text(encoding="utf-8"),
                    "the stderr artifact must carry the runner's stderr "
                    "verbatim",
                )
                self.assertEqual(
                    str(stdout_artifact),
                    record["artifacts"]["stdout"],
                )
                self.assertEqual(
                    str(stderr_artifact),
                    record["artifacts"]["stderr"],
                )

    def test_missing_marker_is_recorded_not_raised(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake(
            result=self._result_with_stdout(JSONL_WITHOUT_MARKER)
        )
        record = self._run(run_one, dirs, "approve", fake)
        self.assertEqual(RECORD_KEYS, set(record))
        self.assertEqual(
            {"passed": False, "kind": "marker", "detail":
             "marker not found in assistant output"},
            record["assertion"],
            "a missing marker must be a recorded passed: False, not an "
            "exception",
        )
        self.assertFalse(record["completed"])

    def test_mcp_list_server_name_present_passes(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        # pi mcp list exits 1 when an enabled server is not connected:
        # a negative process result with a positive assertion.
        fake = self._fake(
            result={
                "exit_code": 1,
                "stdout": MCP_LIST_WITH_SERVER,
                "stderr": "",
                "wall_time_s": 0.75,
                "timed_out": False,
                "evidence": "",
            }
        )
        record = self._run(run_one, dirs, "mcp-list-approve", fake)
        self.assertEqual(RECORD_KEYS, set(record))
        self.assertEqual(
            {"passed": True, "kind": "server-name", "detail":
             "server name present in mcp list output"},
            record["assertion"],
            "the mcp-list assertion must be server-name-present",
        )
        self.assertFalse(
            record["completed"],
            "completed requires exit_code 0 AND a passing assertion",
        )

    def test_mcp_list_server_name_absent_is_recorded_not_raised(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake(
            result=self._result_with_stdout(MCP_LIST_WITHOUT_SERVER)
        )
        record = self._run(run_one, dirs, "mcp-list-no-approve", fake)
        self.assertEqual(RECORD_KEYS, set(record))
        self.assertEqual(
            {"passed": False, "kind": "server-name", "detail":
             "server name absent from mcp list output"},
            record["assertion"],
            "a missing server name must be a recorded passed: False, "
            "not an exception",
        )
        self.assertFalse(record["completed"])

    @staticmethod
    def _result_with_stdout(stdout: str, stderr: str = "") -> Dict[str, Any]:
        result = PiapprovalTestCase._default_result()
        result["stdout"] = stdout
        result["stderr"] = stderr
        return result


class TestTimeoutAndUnknownConfig(PiapprovalTestCase):
    """A budget-exhausted run is a record, never an exception; an unknown
    config is a named error before the runner is invoked."""

    def test_timed_out_run_yields_record_with_evidence_and_partial_stdout(
        self
    ):
        run_one = self._get_run_one()
        dirs = self._fresh()
        evidence = (
            "budget exhausted: pi was still blocked on input after "
            "300 s; process group SIGKILLed"
        )
        fake = self._fake(
            result={
                "exit_code": -9,
                "stdout": JSONL_PARTIAL,
                "stderr": "",
                "wall_time_s": 300.0,
                "timed_out": True,
                "evidence": evidence,
            }
        )
        record = self._run(run_one, dirs, "approve", fake)
        self.assertEqual(RECORD_KEYS, set(record))
        self.assertEqual(
            True,
            record["waited_for_input"],
            "a budget-exhausted run must be recorded as "
            "waited_for_input: True",
        )
        self.assertEqual(
            -9,
            record["exit_code"],
            "the timed-out run's exit code must be the runner's, verbatim",
        )
        self.assertEqual(
            JSONL_PARTIAL,
            (dirs["results"] / "stdout").read_text(encoding="utf-8"),
            "the partial stream must still be captured in the stdout "
            "artifact",
        )
        evidence_path = dirs["results"] / "evidence.txt"
        self.assertTrue(
            evidence_path.is_file(),
            "the runner's evidence must be written to evidence.txt in "
            "the results directory",
        )
        self.assertEqual(
            evidence,
            evidence_path.read_text(encoding="utf-8"),
            "evidence.txt must carry the runner's evidence verbatim",
        )

    def test_timed_out_mcp_list_run_yields_record_not_exception(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake(
            result={
                "exit_code": -9,
                "stdout": "",
                "stderr": "",
                "wall_time_s": 60.0,
                "timed_out": True,
                "evidence": "blocked after 60 s",
            }
        )
        record = self._run(run_one, dirs, "mcp-list-approve", fake)
        self.assertEqual(RECORD_KEYS, set(record))
        self.assertEqual(True, record["waited_for_input"])
        self.assertEqual(
            "blocked after 60 s",
            (dirs["results"] / "evidence.txt").read_text(encoding="utf-8"),
        )

    def test_unknown_config_raises_approval_error_before_runner(self):
        run_one = self._get_run_one()
        approval_error = self._get_approval_error()
        dirs = self._fresh()
        fake = self._fake()
        with self.assertRaises(approval_error) as ctx:
            self._run(run_one, dirs, "wat", fake)
        self.assertIn(
            "wat",
            str(ctx.exception),
            "the error must name the unknown configuration value",
        )
        self.assertEqual(
            0,
            len(fake._calls),
            "an unknown config must not invoke the runner",
        )
        project_files = (
            [path.as_posix() for path in dirs["project"].rglob("*")]
            if dirs["project"].exists()
            else []
        )
        self.assertEqual(
            [],
            project_files,
            "an unknown config must not write the project fixture",
        )


if __name__ == "__main__":
    unittest.main()
