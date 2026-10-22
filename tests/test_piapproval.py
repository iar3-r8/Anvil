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
  written to ``<agent_dir>/models.json`` (flat - ``PI_CODING_AGENT_DIR``
  names the agent directory itself);
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
- the models document at ``<agent_dir>/models.json`` (flat -
  ``PI_CODING_AGENT_DIR`` names the agent directory itself) - exactly
  ``json.dumps`` of
  ``piargv.models_document(model_id, gateway_port, context_window,
  max_tokens, host=gateway_host)``; the agent directory is a DIFFERENT
  directory from the project directory;
- trust-store seeding (behaviour 10) - live pi 1.3.0 rejects ``-a``/
  ``-na`` on the ``pi mcp list`` subcommand, so the trust decision for
  the mcp-list pair comes from ``<agent_dir>/trust.json`` (pi's
  ProjectTrustStore: a JSON map of the resolved absolute project
  directory to true), not from a flag: for ``mcp-list-approve`` a
  trust.json of exactly ``{str(project_dir.resolve()): True}`` is
  written, for ``mcp-list-no-approve`` NO trust.json is written, and
  the two model configs seed nothing either, keeping their
  ``-a``/``-na`` distinction flag-driven and unconfounded;
- the runner invoked exactly once, with the config's exact argv
  (``piargv.approval_argv(model_id, prompt, approve)`` /
  ``piargv.mcp_list_argv()`` - no argument, no approve flag),
  ``cwd = str(project_dir)``, stdin
  ``/dev/null``, the config's budget, and an ``env`` dict carrying
  ``PI_CODING_AGENT_DIR`` pointing at the per-run agent directory;
- artifacts ``stdout`` and ``stderr`` in ``results_dir`` for every config,
  and ``events.jsonl`` (verbatim stdout) ONLY for the two ``--mode json``
  configs - absent for the mcp-list configs;
- the before/after digest artifacts ``before.sha256`` / ``after.sha256``
  in ``results_dir`` for every config: a SHA-256 manifest of the files
  under ``project_dir`` (relative posix path -> hexdigest, the
  ``pifixture.digest_fixture`` shape, ``json.dumps`` sorted) taken before
  the runner is invoked and after it returns. The phase-2 runs disable
  all tools (``-nt``), so the agent cannot modify the project fixture and
  the two manifests are byte-identical;
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

``TestMain`` pins the entrypoint (behaviour 8: "entrypoint")::

    main(runner=None) -> int

- ``main`` returns the exit code and never calls ``sys.exit`` itself -
  the module's ``__main__`` guard does, pinned as source text: the
  module's last statement is ``sys.exit(main())`` under ``if __name__ ==
  "__main__":``, and it is the only ``sys.exit`` in the module;
- the gateway host and port come from the environment: a missing or
  empty ``PI_GATEWAY_HOST`` raises ``ApprovalError`` naming the
  variable, and a missing, empty or non-numeric ``PI_GATEWAY_PORT``
  raises ``ApprovalError`` naming the variable too - in every case
  before ``run_all`` is reached (the recorder sees zero calls);
- the model id and context window come from
  ``anvilkit.config.read_models`` of the ``PI_CONFIG_PATH`` file (default
  the module constant ``_DEFAULT_CONFIG_PATH``, the repo-root
  ``config.yaml`` relative to the repo - the same file the Compose
  service binds read-only at ``/app/config.yaml``); an unreadable or
  invalid file raises ``anvilkit.config``'s ``ConfigError`` unwrapped;
- ``max_tokens``, ``prompt``, ``marker`` and ``unreachable_command`` are
  module constants (``MAX_TOKENS == 4096``, ``PROMPT``, ``MARKER``,
  ``UNREACHABLE_COMMAND`` - the phase-2 values these tests already own);
  they reach ``run_all`` verbatim;
- results land in ``PI_RESULTS_DIR`` (default the module constant
  ``_DEFAULT_RESULTS_DIR``, the repo-root ``./results``-shaped default),
  passed to ``run_all`` as a ``Path``;
- an injected ``runner`` is handed to ``run_all`` verbatim; when
  ``runner`` is ``None`` the default is the module's own
  ``subprocess_runner`` seam (``anvilkit.pibakeoff.subprocess_runner``,
  imported - not re-implemented);
- ``main`` supplies its own ``timestamp`` (ISO-8601 UTC,
  ``YYYY-MM-DDTHH:MM:SSZ``);
- a table in which all four assertions failed is a successful run: the
  exit code is 0 either way - a negative finding is a successful
  measurement.
"""

import hashlib
import importlib
import importlib.util
import inspect
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import anvilkit.config as piconfig
import anvilkit.pibakeoff as pibakeoff
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
            return piargv.mcp_list_argv()
        if config == "mcp-list-no-approve":
            return piargv.mcp_list_argv()
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
        # Live pi 1.3.0 rejects -a/-na on the subcommand: the mcp-list argv
        # carries no trust flag for either mcp-list configuration (the trust
        # difference is materialised by the trust store, not a flag).
        self.assertNotIn("-a", fake._calls[0]["argv"])
        self.assertNotIn("-na", fake._calls[0]["argv"])

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
        models_path = dirs["agent_dir"] / "models.json"
        self.assertTrue(
            models_path.is_file(),
            "the models document must be written flat to "
            "<agent_dir>/models.json (PI_CODING_AGENT_DIR names the agent "
            "directory itself)",
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
            (dirs["agent_dir"] / "models.json").is_file(),
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


class TestTrustStoreSeeding(PiapprovalTestCase):
    """Trust-store seeding materialises the mcp-list difference (behaviour
    10): live pi 1.3.0 rejects -a/-na on the pi mcp list subcommand, so
    the mcp-list trust decision comes from <agent_dir>/trust.json - pi's
    ProjectTrustStore, a JSON map of the resolved absolute project
    directory to true - not from a flag.

    Every test pre-seeds <agent_dir>/trust.json with a canary entry under
    an unrelated key, so the pinned trust state is one ``run_one`` must
    actively materialise (a pre-existing trust.json is overwritten - the
    agent directory is fresh per run), not one the tests would pass on
    the current no-op production:

    - ``mcp-list-approve`` must overwrite the canary with exactly
      ``{str(project_dir.resolve()): true}``;
    - ``mcp-list-no-approve`` must end with NO trust.json on disk, so
      the project is untrusted and ``pi mcp list`` reports the empty
      server list plus the not-trusted note;
    - the two model configs must also end with NO trust.json, keeping
      their ``-a``/``-na`` distinction flag-driven and unconfounded.
    """

    @staticmethod
    def _trust_path(dirs: Dict[str, Path]) -> Path:
        return dirs["agent_dir"] / "trust.json"

    @staticmethod
    def _result_with_stdout(stdout: str) -> Dict[str, Any]:
        result = PiapprovalTestCase._default_result()
        result["stdout"] = stdout
        return result

    @staticmethod
    def _seed_canary(dirs: Dict[str, Path]) -> None:
        """A pre-existing trust.json under an unrelated key."""
        path = TestTrustStoreSeeding._trust_path(dirs)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"trust-store-canary": True}), encoding="utf-8"
        )

    def test_mcp_list_approve_seeds_trust_store_with_resolved_project_dir(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        self._seed_canary(dirs)
        fake = self._fake(result=self._result_with_stdout(MCP_LIST_WITH_SERVER))
        self._run(run_one, dirs, "mcp-list-approve", fake)
        trust_path = self._trust_path(dirs)
        self.assertTrue(
            trust_path.is_file(),
            "mcp-list-approve must seed <agent_dir>/trust.json so pi mcp "
            "list trusts the project and loads .pi/mcp.json",
        )
        self.assertEqual(
            {str(dirs["project"].resolve()): True},
            json.loads(trust_path.read_text(encoding="utf-8")),
            "the trust store must map exactly the resolved absolute "
            "project directory to true - the canonical form pi's "
            "ProjectTrustStore looks up - and must overwrite any "
            "pre-existing trust.json; the pre-seeded canary must not "
            "survive",
        )

    def test_mcp_list_no_approve_seeds_no_trust_store(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        self._seed_canary(dirs)
        fake = self._fake(result=self._result_with_stdout(MCP_LIST_WITHOUT_SERVER))
        self._run(run_one, dirs, "mcp-list-no-approve", fake)
        self.assertFalse(
            self._trust_path(dirs).exists(),
            "mcp-list-no-approve must end with NO <agent_dir>/trust.json "
            "so the project is untrusted and pi mcp list reports an "
            "empty server list with the not-trusted note; the "
            "pre-seeded canary must not survive a run that leaves the "
            "project untrusted",
        )

    def test_model_configs_seed_no_trust_store(self):
        run_one = self._get_run_one()
        for config in ("approve", "no-approve"):
            with self.subTest(config=config):
                dirs = self._fresh()
                self._seed_canary(dirs)
                fake = self._fake(
                    result=self._result_with_stdout(JSONL_WITH_MARKER)
                )
                self._run(run_one, dirs, config, fake)
                self.assertFalse(
                    self._trust_path(dirs).exists(),
                    config + " must end with NO <agent_dir>/trust.json - "
                    "the model pair's trust distinction stays "
                    "flag-driven (-a / -na) and unconfounded, so the "
                    "pre-seeded canary must not survive",
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

    def test_before_digest_artifact_written_to_results_dir(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake()
        record = self._run(run_one, dirs, "approve", fake)
        before_path = dirs["results"] / "before.sha256"
        self.assertTrue(
            before_path.is_file(),
            "run_one must materialise the before-run digest at "
            "results/before.sha256 so the record's before_digest artifact "
            "does not dangle",
        )
        self.assertEqual(
            str(before_path),
            record["artifacts"]["before_digest"],
            "the record's before_digest artifact must point at the "
            "materialised before.sha256 file",
        )

    def test_after_digest_artifact_written_to_results_dir(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake()
        record = self._run(run_one, dirs, "no-approve", fake)
        after_path = dirs["results"] / "after.sha256"
        self.assertTrue(
            after_path.is_file(),
            "run_one must materialise the after-run digest at "
            "results/after.sha256 so the record's after_digest artifact "
            "does not dangle",
        )
        self.assertEqual(
            str(after_path),
            record["artifacts"]["after_digest"],
            "the record's after_digest artifact must point at the "
            "materialised after.sha256 file",
        )

    def test_before_and_after_digest_artifacts_are_byte_identical(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake()
        self._run(run_one, dirs, "approve", fake)
        before_path = dirs["results"] / "before.sha256"
        after_path = dirs["results"] / "after.sha256"
        self.assertTrue(
            before_path.is_file(),
            "run_one must materialise before.sha256 in the results "
            "directory",
        )
        self.assertTrue(
            after_path.is_file(),
            "run_one must materialise after.sha256 in the results "
            "directory",
        )
        self.assertEqual(
            before_path.read_bytes(),
            after_path.read_bytes(),
            "the phase-2 runs disable all tools (-nt), so the agent "
            "cannot modify the project fixture; the before and after "
            "manifests must be byte-identical",
        )

    def test_digest_artifacts_parse_as_relative_path_manifest(self):
        run_one = self._get_run_one()
        dirs = self._fresh()
        fake = self._fake()
        self._run(run_one, dirs, "approve", fake)
        for name in ("before.sha256", "after.sha256"):
            with self.subTest(artifact=name):
                manifest = json.loads(
                    (dirs["results"] / name).read_text(encoding="utf-8")
                )
                self.assertIsInstance(
                    manifest,
                    dict,
                    name + " must parse as a JSON object (the "
                    "pifixture.digest_fixture shape)",
                )
                self.assertTrue(
                    all(
                        isinstance(key, str) and not key.startswith("/")
                        for key in manifest
                    ),
                    "manifest keys must be relative posix paths from "
                    "project_dir",
                )
                self.assertIn(
                    ".pi/mcp.json",
                    manifest,
                    "the manifest must include the project fixture file "
                    ".pi/mcp.json (relative to project_dir)",
                )
                expected_digest = hashlib.sha256(
                    (dirs["project"] / ".pi" / "mcp.json").read_bytes()
                ).hexdigest()
                self.assertEqual(
                    expected_digest,
                    manifest[".pi/mcp.json"],
                    "the manifest's .pi/mcp.json entry must be the "
                    "sha256 hexdigest of the fixture file under "
                    "project_dir",
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


class TestRunAll(PiapprovalTestCase):
    """run_all drives all four phase-2 configurations end to end and
    reports (plans/pi-phase2-approval.md, behaviour 7: "run all four and
    report").

    Pinned signature::

        run_all(base_dir, runner, model_id, gateway_host, gateway_port,
                context_window, max_tokens, prompt, marker,
                unreachable_command, *, timestamp) -> (records, table)

    Pinned layout: each configuration runs against
    ``<base_dir>/<config>/project`` (the fixture destination and the
    runner's cwd) with artifacts under ``<base_dir>/<config>/results``;
    the per-run agent directory is ``<base_dir>/<config>/agent`` (one
    fresh, isolated agent directory per configuration, never the
    invoking user's home). ``record.json`` (content exactly
    ``json.dumps(record, sort_keys=True)``) lands in each configuration's
    results directory; ``table.md`` (content exactly
    ``pirecord.render_table(records)``, records in run order) is written
    to ``<base_dir>/table.md`` and the same string is returned.

    Failure isolation: if ``run_one`` raises for one configuration (any
    exception from the runner or the run), the exception is caught and a
    no-measurement fallback record is built for that configuration - the
    exception's message becomes the assertion's stderr - so the other
    configurations still run and the table still renders one row per
    configuration.
    """

    def _get_run_all(self) -> Callable:
        """Fetch ``anvilkit.piapproval.run_all``, failing clearly if absent."""
        piapproval = self._piapproval()
        run_all = getattr(piapproval, "run_all", None)
        self.assertTrue(
            callable(run_all),
            "anvilkit.piapproval.run_all is not callable; the run-all "
            "driver (behaviour 7) has not been implemented yet",
        )
        return run_all

    def _all_fake(self, fail_on: Optional[str] = None) -> Callable:
        """A deterministic fake runner keyed on the argv it receives.

        The configuration is recovered from the argv tokens (``mcp`` is
        the second token for the mcp-list configs; ``-a``/``-na`` picks
        the approve variant) so the fake's behaviour is a pure function
        of its input. The model configs answer with the marker stream,
        the mcp-list configs with the probe-server document. ``fail_on``
        makes the fake raise ``OSError`` for that configuration,
        simulating a runner that blows up mid-run.
        """

        def fake_runner(invocation: Dict[str, Any]) -> Dict[str, Any]:
            fake_runner._calls.append(dict(invocation))
            argv = invocation["argv"]
            if argv[1] == "mcp":
                config = (
                    "mcp-list-approve" if "-a" in argv else "mcp-list-no-approve"
                )
                payload = MCP_LIST_WITH_SERVER
            elif "-a" in argv:
                config = "approve"
                payload = JSONL_WITH_MARKER
            else:
                config = "no-approve"
                payload = JSONL_WITH_MARKER
            if fail_on is not None and config == fail_on:
                raise OSError("boom-" + config)
            return self._result_with_stdout(payload)

        fake_runner._calls = []
        return fake_runner

    @staticmethod
    def _result_with_stdout(stdout: str, stderr: str = "") -> Dict[str, Any]:
        result = PiapprovalTestCase._default_result()
        result["stdout"] = stdout
        result["stderr"] = stderr
        return result

    def _call_run_all(self, run_all, base_dir, fake):
        """Call run_all with the standard inputs; the pinned call shape."""
        return run_all(
            base_dir,
            fake,
            MODEL_ID,
            GATEWAY_HOST,
            GATEWAY_PORT,
            CONTEXT_WINDOW,
            MAX_TOKENS,
            PROMPT,
            MARKER,
            UNREACHABLE_COMMAND,
            timestamp=TIMESTAMP,
        )

    @staticmethod
    def _expected_record(config: str, base_dir: Path) -> Dict[str, Any]:
        """The record pirecord.build must produce for a run-all config.

        Mirrors ``PiapprovalTestCase._expected_record`` with the
        run-all layout: the artifacts live under
        ``<base_dir>/<config>/results``.
        """
        results = base_dir / config / "results"
        stdout = JSONL_WITH_MARKER if config in (
            "approve",
            "no-approve",
        ) else MCP_LIST_WITH_SERVER
        events = (
            pievents.parse(stdout)["events"]
            if config in ("approve", "no-approve")
            else []
        )
        if config in ("approve", "no-approve"):
            passed = MARKER in stdout
            kind = "marker"
            detail = (
                "marker found in assistant output"
                if passed
                else "marker not found in assistant output"
            )
        else:
            passed = SERVER_NAME in stdout
            kind = "server-name"
            detail = (
                "server name present in mcp list output"
                if passed
                else "server name absent from mcp list output"
            )
        return pirecord.build(
            config,
            model=MODEL_ID,
            exit_code=0,
            wall_time_s=1.5,
            waited_for_input=False,
            artifacts={
                "stdout": str(results / "stdout"),
                "stderr": str(results / "stderr"),
                "jsonl": (
                    str(results / "events.jsonl")
                    if config in ("approve", "no-approve")
                    else None
                ),
                "before_digest": str(results / "before.sha256"),
                "after_digest": str(results / "after.sha256"),
            },
            tool_calls=pievents.tool_calls(events),
            outcome=pievents.outcome(events),
            assertion={"passed": passed, "kind": kind, "detail": detail},
            changed_files=[],
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
        the run_one tests do (its exact text is not pinned for the
        normal configs)."""
        self.assertEqual(RECORD_KEYS, set(record))
        actual = dict(record)
        actual_assertion = actual.pop("assertion")
        expected = dict(expected)
        expected_assertion = expected.pop("assertion")
        self.assertEqual(expected, actual)
        self.assertEqual(
            expected_assertion.get("passed"), actual_assertion.get("passed")
        )

    def test_run_all_is_callable(self):
        self._get_run_all()

    def test_run_all_invokes_runner_once_per_config_in_fixed_order(self):
        run_all = self._get_run_all()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base_dir = Path(tmp.name) / "run"
        fake = self._all_fake()
        records, _ = self._call_run_all(run_all, base_dir, fake)
        # Exactly four runner invocations, one per configuration, in the
        # pinned order, each against its own per-config project directory
        # with a per-config agent directory in the env overlay.
        self.assertEqual(4, len(fake._calls))
        expected_argv = [
            piargv.approval_argv(MODEL_ID, PROMPT, True),
            piargv.approval_argv(MODEL_ID, PROMPT, False),
            piargv.mcp_list_argv(),
            piargv.mcp_list_argv(),
        ]
        expected_budgets = [
            BUDGET_APPROVE_S,
            BUDGET_APPROVE_S,
            BUDGET_MCP_LIST_S,
            BUDGET_MCP_LIST_S,
        ]
        for index, (config, argv, budget) in enumerate(
            zip(CONFIGS, expected_argv, expected_budgets)
        ):
            self.assertEqual(
                {
                    "argv": argv,
                    "cwd": str(base_dir / config / "project"),
                    "stdin": "/dev/null",
                    "timeout_s": budget,
                    "env": {"PI_CODING_AGENT_DIR": str(base_dir / config / "agent")},
                },
                fake._calls[index],
                "the runner invocation for "
                + config
                + " must carry exactly the config's argv, cwd = the "
                "per-config project dir, stdin /dev/null, the config's "
                "budget, and an env dict pointing PI_CODING_AGENT_DIR at "
                "the per-config agent directory",
            )
        self.assertEqual(
            [record["config"] for record in records], list(CONFIGS)
        )

    def test_run_all_writes_record_json_sort_keys_per_config(self):
        run_all = self._get_run_all()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base_dir = Path(tmp.name) / "run"
        fake = self._all_fake()
        records, _ = self._call_run_all(run_all, base_dir, fake)
        for config, record in zip(CONFIGS, records):
            record_path = base_dir / config / "results" / "record.json"
            self.assertTrue(
                record_path.is_file(),
                config + " must write record.json to its own results dir",
            )
            self.assertEqual(
                json.dumps(record, sort_keys=True),
                record_path.read_text(encoding="utf-8"),
                config + "'s record.json must carry exactly "
                "json.dumps(record, sort_keys=True)",
            )

    def test_run_all_records_match_pirecord_build_per_config(self):
        run_all = self._get_run_all()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base_dir = Path(tmp.name) / "run"
        fake = self._all_fake()
        records, _ = self._call_run_all(run_all, base_dir, fake)
        for record in records:
            self._assert_record(
                record, self._expected_record(record["config"], base_dir)
            )

    def test_run_all_writes_table_md_and_returns_same_table(self):
        run_all = self._get_run_all()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base_dir = Path(tmp.name) / "run"
        fake = self._all_fake()
        records, table = self._call_run_all(run_all, base_dir, fake)
        table_path = base_dir / "table.md"
        self.assertTrue(
            table_path.is_file(),
            "run_all must write table.md to the base dir",
        )
        rendered = pirecord.render_table(records)
        # The table is written to table.md AND returned, byte-identical.
        self.assertEqual(
            rendered,
            table,
            "the returned table must be exactly pirecord.render_table"
            " (records in run order)",
        )
        self.assertEqual(
            rendered,
            table_path.read_text(encoding="utf-8"),
            "table.md must carry exactly pirecord.render_table(records)",
        )
        # One row per configuration, in run order.
        for config in CONFIGS:
            self.assertIn("| " + config + " |", table)

    def test_run_all_failed_config_does_not_abort_others(self):
        run_all = self._get_run_all()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base_dir = Path(tmp.name) / "run"
        fake = self._all_fake(fail_on="no-approve")
        records, table = self._call_run_all(run_all, base_dir, fake)
        # All four invocations happened; the order is unchanged.
        self.assertEqual(4, len(fake._calls))
        self.assertEqual(
            [record["config"] for record in records], list(CONFIGS)
        )
        approve_record, no_approve_record, mcp_a_record, mcp_na_record = records
        # The sibling configurations still built normal records.
        self._assert_record(
            approve_record, self._expected_record("approve", base_dir)
        )
        self._assert_record(
            mcp_a_record, self._expected_record("mcp-list-approve", base_dir)
        )
        self._assert_record(
            mcp_na_record,
            self._expected_record("mcp-list-no-approve", base_dir),
        )
        # The failed configuration's record is still built, with the
        # exception message as the assertion's stderr.
        expected_failure = self._failure_record(
            "no-approve", base_dir, "boom-no-approve"
        )
        self._assert_record(no_approve_record, expected_failure)
        self.assertEqual(
            "boom-no-approve",
            no_approve_record["assertion"]["stderr"],
            "the fallback record's assertion stderr must carry the "
            "exception's message",
        )
        self.assertFalse(
            no_approve_record["completed"],
            "a no-measurement fallback record must not be completed",
        )
        # Its record.json is still written.
        record_path = base_dir / "no-approve" / "results" / "record.json"
        self.assertTrue(record_path.is_file())
        self.assertEqual(
            json.dumps(no_approve_record, sort_keys=True),
            record_path.read_text(encoding="utf-8"),
        )
        # The table still renders one row per configuration, in order.
        for config in CONFIGS:
            self.assertIn("| " + config + " |", table)
        self.assertTrue(table.endswith("PARTIAL (3 of 4 completed)"))


# ---------------------------------------------------------------------------
# Behaviour 8: "entrypoint" (``python3 -m anvilkit.piapproval``)
#
# The ``run_all`` seam is monkeypatched with a signature-bound recorder,
# so no test touches pi, the gateway or the real config.yaml; the
# environment is patched per test (``PI_GATEWAY_HOST``/``PI_GATEWAY_PORT``
# required, ``PI_CONFIG_PATH`` and ``PI_RESULTS_DIR`` optional).
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

# The entrypoint's pinned defaults (behaviour 8): the repo-root
# read-only config.yaml, and the repo-root ./results-shaped results dir
# (the devcontainer recipe's PI_RESULTS_DIR=./results shape).
PINNED_DEFAULT_CONFIG_PATH = str(REPO_ROOT / "config.yaml")
PINNED_DEFAULT_RESULTS_DIR = "results"

TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class TestMain(PiapprovalTestCase):
    """main - the devcontainer entrypoint (behaviour 8)."""

    def _get_main(self) -> Callable:
        """Fetch ``anvilkit.piapproval.main``, failing clearly if absent."""
        piapproval = self._piapproval()
        main = getattr(piapproval, "main", None)
        self.assertTrue(
            callable(main),
            "anvilkit.piapproval.main is not callable; the devcontainer "
            "entrypoint (behaviour 8) has not been implemented yet",
        )
        return main

    def _get_constant(self, name: str):
        """Fetch a module constant, failing clearly if it is absent."""
        piapproval = self._piapproval()
        value = getattr(piapproval, name, None)
        self.assertIsNotNone(
            value,
            "anvilkit.piapproval.{} is missing; the entrypoint constants "
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
        """The valid devcontainer environment, pointed at a real tmp config."""
        env = self._env(
            PI_GATEWAY_HOST="host.docker.internal",
            PI_GATEWAY_PORT="8080",
            PI_CONFIG_PATH=str(config_path),
        )
        env.update(extra)
        return env

    def _recorder(self, piapproval, table: str = "NO-GO (0 of 4 passed)"):
        """A ``run_all`` stand-in that records its bound call arguments.

        Signature-bound against the real ``run_all`` so the pin does not
        depend on whether ``main`` calls it positionally or by keyword.
        Returns ``(patcher, recorder)``; ``recorder.calls`` is the list of
        bound-argument dicts, one entry per call. The canned records all
        carry a failed assertion: a negative finding is a successful
        measurement, and ``main`` must not care.
        """
        real_run_all = piapproval.run_all
        signature = inspect.signature(real_run_all)

        def recorder(*args, **kwargs):
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            recorder.calls.append(dict(bound.arguments))
            return (
                [
                    {"config": config, "assertion": {"passed": False}}
                    for config in CONFIGS
                ],
                table,
            )

        recorder.calls = []
        return mock.patch.object(piapproval, "run_all", recorder), recorder

    def test_main_missing_or_empty_gateway_host_raises_approval_error_naming_it(
        self,
    ):
        main = self._get_main()
        approval_error = self._get_approval_error()
        piapproval = self._piapproval()
        config_path = self._write_config()
        envs = {
            "missing": {
                k: v for k, v in self._happy_env(config_path).items()
                if k != "PI_GATEWAY_HOST"
            },
            "empty": self._happy_env(config_path, PI_GATEWAY_HOST=""),
        }
        for label, env in envs.items():
            with self.subTest(PI_GATEWAY_HOST=label):
                patcher, recorder = self._recorder(piapproval)
                with patcher, mock.patch.dict(os.environ, env):
                    with self.assertRaises(approval_error) as ctx:
                        main()
                self.assertIn("PI_GATEWAY_HOST", str(ctx.exception))
                self.assertEqual([], recorder.calls)

    def test_main_missing_or_empty_gateway_port_raises_approval_error_naming_it(
        self,
    ):
        main = self._get_main()
        approval_error = self._get_approval_error()
        piapproval = self._piapproval()
        config_path = self._write_config()
        envs = {
            "missing": {
                k: v for k, v in self._happy_env(config_path).items()
                if k != "PI_GATEWAY_PORT"
            },
            "empty": self._happy_env(config_path, PI_GATEWAY_PORT=""),
        }
        for label, env in envs.items():
            with self.subTest(PI_GATEWAY_PORT=label):
                patcher, recorder = self._recorder(piapproval)
                with patcher, mock.patch.dict(os.environ, env):
                    with self.assertRaises(approval_error) as ctx:
                        main()
                self.assertIn("PI_GATEWAY_PORT", str(ctx.exception))
                self.assertEqual([], recorder.calls)

    def test_main_non_numeric_gateway_port_raises_approval_error_naming_it(
        self,
    ):
        main = self._get_main()
        approval_error = self._get_approval_error()
        piapproval = self._piapproval()
        config_path = self._write_config()
        env = self._happy_env(config_path, PI_GATEWAY_PORT="not-a-port")
        patcher, recorder = self._recorder(piapproval)
        with patcher, mock.patch.dict(os.environ, env):
            with self.assertRaises(approval_error) as ctx:
                main()
        self.assertIn("PI_GATEWAY_PORT", str(ctx.exception))
        self.assertEqual([], recorder.calls)

    def test_main_unreadable_config_raises_config_error_unwrapped(self):
        main = self._get_main()
        piapproval = self._piapproval()
        config_path = self._write_config()
        missing = config_path.parent / "does-not-exist.yaml"
        env = self._happy_env(config_path, PI_CONFIG_PATH=str(missing))
        patcher, recorder = self._recorder(piapproval)
        with patcher, mock.patch.dict(os.environ, env):
            # The ConfigError from anvilkit.config, propagated as-is -
            # not wrapped into an ApprovalError or any other type.
            with self.assertRaises(piconfig.ConfigError):
                main()
        self.assertEqual([], recorder.calls)

    def test_main_passes_gateway_env_and_config_topology_to_run_all(self):
        main = self._get_main()
        piapproval = self._piapproval()
        config_path = self._write_config()
        env = self._happy_env(config_path)
        patcher, recorder = self._recorder(piapproval)
        with patcher, mock.patch.dict(os.environ, env):
            exit_code = main()
        self.assertEqual(0, exit_code)
        self.assertEqual(1, len(recorder.calls))
        seen = recorder.calls[0]
        # Results land at the pinned repo-root results directory, as a Path.
        self.assertEqual(Path(PINNED_DEFAULT_RESULTS_DIR), seen["base_dir"])
        # The model id and context window are read_models' answer, verbatim.
        self.assertEqual("test/coder-model", seen["model_id"])
        self.assertEqual(12345, seen["context_window"])
        # The gateway address is the devcontainer environment, port as int.
        self.assertEqual("host.docker.internal", seen["gateway_host"])
        self.assertEqual(8080, seen["gateway_port"])
        self.assertIsInstance(seen["gateway_port"], int)
        # runner=None defaults to the imported pibakeoff subprocess_runner.
        self.assertIs(pibakeoff.subprocess_runner, seen["runner"])
        # main supplies the stamp itself.
        self.assertRegex(seen["timestamp"], TIMESTAMP_PATTERN)

    def test_main_passes_pinned_module_constants_to_run_all(self):
        main = self._get_main()
        piapproval = self._piapproval()
        # The constants exist and carry the pinned values.
        self.assertEqual(
            PINNED_DEFAULT_CONFIG_PATH,
            self._get_constant("_DEFAULT_CONFIG_PATH"),
        )
        self.assertEqual(
            PINNED_DEFAULT_RESULTS_DIR,
            self._get_constant("_DEFAULT_RESULTS_DIR"),
        )
        self.assertEqual(MAX_TOKENS, self._get_constant("MAX_TOKENS"))
        self.assertEqual(PROMPT, self._get_constant("PROMPT"))
        self.assertEqual(MARKER, self._get_constant("MARKER"))
        self.assertEqual(
            UNREACHABLE_COMMAND, self._get_constant("UNREACHABLE_COMMAND")
        )
        config_path = self._write_config()
        env = self._happy_env(config_path)
        patcher, recorder = self._recorder(piapproval)
        with patcher, mock.patch.dict(os.environ, env):
            self.assertEqual(0, main())
        seen = recorder.calls[0]
        # And the constants are exactly what the driver receives.
        self.assertEqual(MAX_TOKENS, seen["max_tokens"])
        self.assertEqual(PROMPT, seen["prompt"])
        self.assertEqual(MARKER, seen["marker"])
        self.assertEqual(UNREACHABLE_COMMAND, seen["unreachable_command"])

    def test_main_results_dir_honours_pi_results_dir_env(self):
        main = self._get_main()
        piapproval = self._piapproval()
        config_path = self._write_config()
        env = self._happy_env(config_path, PI_RESULTS_DIR="/custom/results")
        patcher, recorder = self._recorder(piapproval)
        with patcher, mock.patch.dict(os.environ, env):
            self.assertEqual(0, main())
        self.assertEqual(
            Path("/custom/results"), recorder.calls[0]["base_dir"]
        )

    def test_main_config_path_honours_pi_config_path_env(self):
        main = self._get_main()
        piapproval = self._piapproval()
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
        patcher, recorder = self._recorder(piapproval)
        with patcher, mock.patch.dict(os.environ, env):
            self.assertEqual(0, main())
        # The env-named file is the one read_models parsed.
        self.assertEqual("other/coder-model", recorder.calls[0]["model_id"])
        self.assertEqual(4321, recorder.calls[0]["context_window"])

    def test_main_default_config_path_is_the_repo_root_config(self):
        main = self._get_main()
        piapproval = self._piapproval()
        env = self._env(
            PI_GATEWAY_HOST="host.docker.internal",
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
        patcher, recorder = self._recorder(piapproval)
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
        piapproval = self._piapproval()
        config_path = self._write_config()
        env = self._happy_env(config_path)
        fake_runner = object()
        patcher, recorder = self._recorder(piapproval)
        with patcher, mock.patch.dict(os.environ, env):
            self.assertEqual(0, main(runner=fake_runner))
        self.assertIs(fake_runner, recorder.calls[0]["runner"])

    def test_main_exit_zero_when_all_assertions_failed(self):
        main = self._get_main()
        piapproval = self._piapproval()
        config_path = self._write_config()
        env = self._happy_env(config_path)
        # The recorder's canned run measured all four configurations and
        # every assertion failed: a negative finding is a successful
        # measurement, so main still returns 0.
        patcher, _ = self._recorder(piapproval, table="NO-GO (0 of 4 passed)")
        with patcher, mock.patch.dict(os.environ, env):
            self.assertEqual(0, main())

    def test_main_guard_is_the_only_sys_exit_and_is_last(self):
        piapproval = self._piapproval()
        source = Path(piapproval.__file__).read_text(encoding="utf-8")
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
