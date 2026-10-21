"""Phase-2 approval run driver - one job: drive the approval configurations.

``plans/pi-phase2-approval.md``, behaviour 6: "run one approval
configuration" and behaviour 7: "run all four and report". ``run_one``
drives one of the four phase-2 configurations -
``approve``, ``no-approve``, ``mcp-list-approve``, ``mcp-list-no-approve`` -
end to end: it writes the project fixture (``anvilkit.pitrust``) into the
project directory, writes the models document into the ISOLATED per-run
agent directory (never the invoking user's ``~/.pi``), materialises the
before/after project digests (``before.sha256`` / ``after.sha256``, the
``anvilkit.pifixture.digest_fixture`` manifest of the project directory
taken before the runner is invoked and after it returns), invokes the
injected runner exactly once with the configuration's argv, captures the
artifacts (stdout, stderr, and events.jsonl for the two ``--mode json``
configs; evidence.txt for a timed-out run) and returns the
``anvilkit.pirecord.build`` record for the run.

This module decides nothing about tokens: the argv comes verbatim from
``anvilkit.piargv`` (``approval_argv`` / ``mcp_list_argv``), the project
fixture from ``anvilkit.pitrust`` and the record shape from
``anvilkit.pirecord`` - it only composes them in order. The stream
accounting runs on the captured stdout for the two ``--mode json`` configs
and on the empty event list for the mcp-list configs (whose stdout is a
``pi mcp list --json`` document, not a stream), mirroring
``anvilkit.pibakeoff``. Process execution is the seam: the caller injects a
``runner`` callable that takes one invocation dict (``argv``, ``cwd``,
``stdin``, ``timeout_s``, ``env``) and returns one result dict (``exit_code``,
``stdout``, ``stderr``, ``wall_time_s``, ``timed_out``, ``evidence``), so the
driver is testable without ``pi`` installed.

The assertion is computed from the captured assistant output: for the model
configs the marker token must be present in stdout (``kind`` ``"marker"``);
for the mcp-list configs the probe server name must be present in stdout
(``kind`` ``"server-name"``). A missing marker (or server name) is a
recorded ``passed: False``, never an exception; a budget-exhausted run is a
record with ``waited_for_input`` True, the partial stream still in the
stdout artifact and the runner's evidence in evidence.txt - never an
exception.

One exception type: ``ApprovalError`` - raised (naming the value) for an
unknown configuration, before the runner is invoked and before the project
fixture is written.
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import anvilkit.piargv as piargv
import anvilkit.pievents as pievents
import anvilkit.pifixture as pifixture
import anvilkit.pirecord as pirecord
import anvilkit.pitrust as pitrust


#: The four pinned phase-2 configurations (behaviour 6).
_CONFIG_VALUES = (
    "approve",
    "no-approve",
    "mcp-list-approve",
    "mcp-list-no-approve",
)

#: The wall-clock budget for the two ``--mode json`` model runs (behaviour 6).
_APPROVE_TIMEOUT_S = 300.0

#: The wall-clock budget for the two mcp-list runs (behaviour 6).
_MCP_LIST_TIMEOUT_S = 60.0

#: The server name the project mcp.json entry carries (``pitrust._SERVER_NAME``);
#: the assertion target for the mcp-list configs - ``pi mcp list --json`` must
#: name it even when the server never connects.
_SERVER_NAME = "anvil-trust-probe"


class ApprovalError(Exception):
    """Any refusal to drive a phase-2 approval configuration.

    A single exception type covers the one current failure - an unknown
    configuration value - so callers need only one ``except`` clause. The
    message names the value so the caller knows which argument to fix.
    """


def _argv_for(config: str, model_id: str, prompt: str) -> List[str]:
    """The exact argv for a known configuration, from the piargv builders."""
    if config == "approve":
        return piargv.approval_argv(model_id, prompt, True)
    if config == "no-approve":
        return piargv.approval_argv(model_id, prompt, False)
    if config == "mcp-list-approve":
        return piargv.mcp_list_argv(True)
    return piargv.mcp_list_argv(False)


def _budget_for(config: str) -> float:
    """The per-configuration wall-clock budget handed to the runner."""
    if config in ("approve", "no-approve"):
        return _APPROVE_TIMEOUT_S
    return _MCP_LIST_TIMEOUT_S


def _is_mode_json(config: str) -> bool:
    """True for the two ``--mode json`` configs, whose stdout is a stream."""
    return config in ("approve", "no-approve")


def _assertion(config: str, marker: str, stdout: str) -> Dict[str, Any]:
    """The assertion dimension, computed from the captured assistant output.

    For the model configs the marker token must be present in stdout
    (``kind`` ``"marker"``); for the mcp-list configs the probe server name
    must be present in stdout (``kind`` ``"server-name"``). A miss is a
    recorded ``passed: False`` - never an exception.
    """
    if _is_mode_json(config):
        passed = marker in stdout
        detail = (
            "marker found in assistant output"
            if passed
            else "marker not found in assistant output"
        )
        return {"passed": passed, "kind": "marker", "detail": detail}
    passed = _SERVER_NAME in stdout
    detail = (
        "server name present in mcp list output"
        if passed
        else "server name absent from mcp list output"
    )
    return {"passed": passed, "kind": "server-name", "detail": detail}


def run_one(
    config: str,
    project_dir: Union[Path, str],
    results_dir: Union[Path, str],
    runner: Callable[[Dict[str, Any]], Dict[str, Any]],
    agent_dir: Union[Path, str],
    model_id: str,
    gateway_host: str,
    gateway_port: int,
    context_window: int,
    max_tokens: int,
    prompt: str,
    marker: str,
    unreachable_command: str,
    *,
    timestamp: str,
) -> Dict[str, Any]:
    """Drive one phase-2 approval configuration end to end.

    The sequence is: validate ``config`` (an unknown value raises
    :class:`ApprovalError` naming it, before the runner is invoked and
    before the project fixture is written); create ``results_dir`` if
    missing (its parent must exist); write the project fixture via
    ``pitrust.write_project`` into ``project_dir``; write the models
    document to ``<agent_dir>/.pi/agent/models.json`` (parents created;
    ``agent_dir`` is the ISOLATED per-run agent directory, never defaulted
    to the user's home); write the before-run project digest (the
    ``pifixture.digest_fixture`` manifest of ``project_dir``, serialised
    sorted) to ``before.sha256`` in ``results_dir``; invoke ``runner``
    exactly once with the configuration's argv, the project directory as
    cwd, stdin ``/dev/null``, the configuration's budget (300 s for the
    model runs, 60 s for the mcp-list runs) and an ``env`` overlay
    carrying ``PI_CODING_AGENT_DIR`` pointing at the agent directory;
    write the after-run digest to ``after.sha256``; capture stdout
    and stderr as artifacts; drain stdout to ``events.jsonl`` for the two
    ``--mode json`` configs only; for a timed-out run write the runner's
    ``evidence`` to ``evidence.txt``; and build the record with
    ``pirecord.build``.

    Args:
        config: One of ``"approve"``, ``"no-approve"``,
            ``"mcp-list-approve"``, ``"mcp-list-no-approve"``.
        project_dir: The fresh project directory; the fixture destination
            and the runner's cwd.
        results_dir: Where the artifacts land; created if missing.
        runner: The process-execution seam; one call, one invocation dict.
        agent_dir: The isolated per-run agent directory; handed to the
            child as ``PI_CODING_AGENT_DIR`` and the home of the models
            document. Never the invoking user's home.
        model_id: The model id for the argv and the models document.
        gateway_host: The gateway host for the models document.
        gateway_port: The gateway port for the models document.
        context_window: The context window for the models document.
        max_tokens: The max tokens for the models document.
        prompt: The fixed phase-2 marker prompt.
        marker: The marker token the project fixture instructs the model
            to echo; the assertion target for the model configs.
        unreachable_command: The single executable not on PATH that the
            project mcp.json entry names.
        timestamp: The ISO-8601 UTC stamp stored verbatim in the record.

    Returns:
        Dict[str, Any]: exactly the record ``pirecord.build`` produces for
        the composed dimensions.

    Raises:
        ApprovalError: ``config`` is not one of the four pinned
            configurations; the value is named and no runner invocation
            happens, and no project fixture is written.
    """
    if config not in _CONFIG_VALUES:
        raise ApprovalError(
            "unknown configuration {!r}: expected one of {}".format(
                config, ", ".join(_CONFIG_VALUES)
            )
        )

    project_dir = Path(project_dir)
    results_dir = Path(results_dir)
    agent_dir = Path(agent_dir)

    results_dir.mkdir(parents=True, exist_ok=True)

    project_dir.mkdir(parents=True, exist_ok=True)
    pitrust.write_project(project_dir, marker, unreachable_command)

    models_path = agent_dir / ".pi" / "agent" / "models.json"
    models_path.parent.mkdir(parents=True, exist_ok=True)
    models_path.write_text(
        json.dumps(
            piargv.models_document(
                model_id,
                gateway_port,
                context_window,
                max_tokens,
                host=gateway_host,
            )
        ),
        encoding="utf-8",
    )

    before_manifest = json.dumps(
        pifixture.digest_fixture(project_dir), sort_keys=True
    )
    (results_dir / "before.sha256").write_text(
        before_manifest, encoding="utf-8"
    )

    result = runner(
        {
            "argv": _argv_for(config, model_id, prompt),
            "cwd": str(project_dir),
            "stdin": "/dev/null",
            "timeout_s": _budget_for(config),
            "env": {"PI_CODING_AGENT_DIR": str(agent_dir)},
        }
    )

    (results_dir / "after.sha256").write_text(
        json.dumps(pifixture.digest_fixture(project_dir), sort_keys=True),
        encoding="utf-8",
    )

    stdout = result["stdout"]
    (results_dir / "stdout").write_text(stdout, encoding="utf-8")
    (results_dir / "stderr").write_text(result["stderr"], encoding="utf-8")

    if _is_mode_json(config):
        events_path = results_dir / "events.jsonl"
        events_path.write_text(stdout, encoding="utf-8")
        events = pievents.parse(stdout)["events"]
        jsonl_artifact: Optional[str] = str(events_path)
    else:
        events = []
        jsonl_artifact = None

    if result["timed_out"]:
        (results_dir / "evidence.txt").write_text(
            result["evidence"], encoding="utf-8"
        )

    return pirecord.build(
        config,
        model=model_id,
        exit_code=result["exit_code"],
        wall_time_s=result["wall_time_s"],
        waited_for_input=result["timed_out"],
        artifacts={
            "stdout": str(results_dir / "stdout"),
            "stderr": str(results_dir / "stderr"),
            "jsonl": jsonl_artifact,
            "before_digest": str(results_dir / "before.sha256"),
            "after_digest": str(results_dir / "after.sha256"),
        },
        tool_calls=pievents.tool_calls(events),
        outcome=pievents.outcome(events),
        assertion=_assertion(config, marker, stdout),
        changed_files=[],
        timestamp=timestamp,
    )


def _fallback_record(
    config: str, results_dir: Path, model_id: str, message: str, timestamp: str
) -> Dict[str, Any]:
    """The no-measurement record for a configuration whose runner raised.

    Mirrors ``anvilkit.pibakeoff._fallback_record``: the exception's message
    lands as the assertion's stderr (the closed thirteen-key record shape has
    no free-form evidence field); everything else is the baseline: a non-zero
    sentinel exit code, zero wall time, no changed files, the empty-stream
    counters and outcome, and the pinned artifact paths with ``jsonl`` None.
    """
    return pirecord.build(
        config,
        model=model_id,
        exit_code=1,
        wall_time_s=0.0,
        waited_for_input=True,
        artifacts={
            "stdout": str(results_dir / "stdout"),
            "stderr": str(results_dir / "stderr"),
            "jsonl": None,
            "before_digest": str(results_dir / "before.sha256"),
            "after_digest": str(results_dir / "after.sha256"),
        },
        tool_calls=pievents.tool_calls([]),
        outcome=pievents.outcome([]),
        assertion={"passed": False, "stderr": message},
        changed_files=[],
        timestamp=timestamp,
    )


def run_all(
    base_dir: Union[Path, str],
    runner: Callable[[Dict[str, Any]], Dict[str, Any]],
    model_id: str,
    gateway_host: str,
    gateway_port: int,
    context_window: int,
    max_tokens: int,
    prompt: str,
    marker: str,
    unreachable_command: str,
    *,
    timestamp: str,
) -> Tuple[List[Dict[str, Any]], str]:
    """Drive all four phase-2 approval configurations end to end and report.

    ``plans/pi-phase2-approval.md``, behaviour 7: "run all four and report".
    A thin orchestrator over :func:`run_one`: the four configurations run in
    the fixed order ``approve``, ``no-approve``, ``mcp-list-approve``,
    ``mcp-list-no-approve``, each against ``<base_dir>/<config>/project``
    (the fixture destination and the runner's cwd) with artifacts under
    ``<base_dir>/<config>/results`` and the per-run agent directory at
    ``<base_dir>/<config>/agent`` (one fresh, isolated agent directory per
    configuration, never the invoking user's home). ``base_dir`` and the
    per-config directories are created. After each configuration a
    ``record.json`` with content exactly ``json.dumps(record,
    sort_keys=True)`` is written to the results directory. Finally
    ``table.md`` is written to ``<base_dir>/table.md`` with content exactly
    ``pirecord.render_table(records)`` (records in run order), and that same
    string is returned.

    Failure isolation (mirroring ``anvilkit.pibakeoff.run_all``): if
    ``run_one`` raises for one configuration (any exception from the runner
    or the run), the exception is caught and a no-measurement fallback record
    is built for that configuration - the exception's message becomes the
    assertion's stderr - so the other configurations still run and the table
    still renders one row per configuration. No exception escapes.

    Args:
        base_dir: The run root; created if missing, with one ``<config>``
            subtree per configuration.
        runner: The process-execution seam, passed to ``run_one`` verbatim.
        model_id: The model id for the argv and the models document.
        gateway_host: The gateway host for the models document.
        gateway_port: The gateway port for the models document.
        context_window: The context window for the models document.
        max_tokens: The max tokens for the models document.
        prompt: The fixed phase-2 marker prompt.
        marker: The marker token the project fixture instructs the model to
            echo; the assertion target for the model configs.
        unreachable_command: The single executable not on PATH that the
            project mcp.json entry names.
        timestamp: The ISO-8601 UTC stamp stored verbatim in every record;
            the driver owns the clock and passes it through.

    Returns:
        Tuple[List[Dict[str, Any]], str]: the records in run order and the
        rendered table.
    """
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    records: List[Dict[str, Any]] = []
    for config in _CONFIG_VALUES:
        project_dir = base_dir / config / "project"
        agent_dir = base_dir / config / "agent"
        results_dir = base_dir / config / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        try:
            record = run_one(
                config,
                project_dir,
                results_dir,
                runner,
                agent_dir,
                model_id,
                gateway_host,
                gateway_port,
                context_window,
                max_tokens,
                prompt,
                marker,
                unreachable_command,
                timestamp=timestamp,
            )
        except Exception as exc:
            record = _fallback_record(
                config, results_dir, model_id, str(exc), timestamp
            )
        (results_dir / "record.json").write_text(
            json.dumps(record, sort_keys=True), encoding="utf-8"
        )
        records.append(record)

    table = pirecord.render_table(records)
    (base_dir / "table.md").write_text(table, encoding="utf-8")
    return records, table
