"""Bake-off run driver - one job: drive bake-off configurations end to end.

Phase 1b (``plans/pi-phase1b-docker.md``) drives the three bake-off
configurations - print, json, ultrawork. Behaviour 4 (``run_one``) runs one
of them against a fresh fixture directory and returns the
``anvilkit.pirecord.build`` record for it; behaviour 5 (``run_all``) is a
thin orchestrator over it - the three configurations in the fixed order, a
``record.json`` per configuration, one ``table.md`` for the lot, and a
no-measurement fallback record when one configuration's runner raises, so a
single failure never aborts the other two.

This module decides nothing about tokens: the argv comes verbatim from
``anvilkit.piargv``, the fixture and digests from ``anvilkit.pifixture``, the
stream accounting from ``anvilkit.pievents`` and the record shape from
``anvilkit.pirecord`` - it only composes them in order. Process execution is
the seam: the caller injects a ``runner`` callable that takes one invocation
dict (``argv``, ``cwd``, ``stdin``, ``timeout_s``) and returns one result dict
(``exit_code``, ``stdout``, ``stderr``, ``wall_time_s``, ``timed_out``,
``evidence``), so the driver is importable and testable without ``pi`` or
Docker installed.

One exception type: ``BakeoffError`` - raised for an unknown configuration
value, naming it, before any runner invocation happens.
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import anvilkit.piargv as piargv
import anvilkit.pievents as pievents
import anvilkit.pifixture as pifixture
import anvilkit.pirecord as pirecord


class BakeoffError(Exception):
    """Any refusal to drive a bake-off configuration.

    A single exception type covers the one current failure - an unknown
    configuration value - so callers need only one ``except`` clause. The
    message names the value so the caller knows which argument to fix.
    """


def _argv_for(
    config: str, model_id: str, prompt: str, extension_path: str
) -> List[str]:
    """The exact argv for a known configuration, from the piargv builders."""
    if config == "print":
        return piargv.print_argv(model_id, prompt)
    if config == "json":
        return piargv.json_argv(model_id, prompt)
    return piargv.ultrawork_argv(model_id, prompt, extension_path)


def _write_digest(results_dir: Path, name: str, digest: Dict[str, str]) -> None:
    """Write a fixture digest to the pinned results-directory artifact."""
    (results_dir / name).write_text(
        json.dumps(digest, sort_keys=True), encoding="utf-8"
    )


def run_one(
    config: str,
    fixture_dir: Path,
    results_dir: Path,
    runner: Callable[[Dict[str, Any]], Dict[str, Any]],
    model_id: str,
    prompt: str,
    extension_path: str,
    gateway_host: str,
    gateway_port: int,
    context_window: int,
    max_tokens: int,
    timeout_s: float,
    *,
    timestamp: str,
    agent_home: Optional[Path] = None,
) -> Dict[str, Any]:
    """Drive one bake-off configuration against a fresh fixture directory.

    The sequence is: create ``results_dir`` if missing (its parent must
    exist); write the agent-directory models document to
    ``<agent_home>/.pi/agent/models.json`` (parents created; ``agent_home``
    defaults to ``pathlib.Path.home()``); write the fixture into
    ``fixture_dir``; take the before-digest; invoke ``runner`` exactly once
    with the configuration's argv, the fixture directory as cwd, stdin
    ``/dev/null`` and the given timeout; take the after-digest and compute
    ``changed_files``; drain stdout to ``events.jsonl`` for the json config
    only (print and ultrawork use the empty stream); capture stdout and
    stderr as artifacts; and for a timed-out run write the runner's
    ``evidence`` to ``evidence.txt`` - a blocked run becomes a record with
    ``waited_for_input`` True, never an exception.

    Args:
        config: One of ``"print"``, ``"json"``, ``"ultrawork"``.
        fixture_dir: The fresh fixture destination for this run.
        results_dir: Where the artifacts land; created if missing.
        runner: The process-execution seam; one call, one invocation dict.
        model_id: The model id for the argv and the models document.
        prompt: The task prompt passed to the invocation.
        extension_path: The pi-ultrawork extension path (ultrawork only).
        gateway_host: The gateway host for the models document.
        gateway_port: The gateway port for the models document.
        context_window: The context window for the models document.
        max_tokens: The max tokens for the models document.
        timeout_s: The wall-clock budget handed to the runner.
        timestamp: The ISO-8601 UTC stamp stored verbatim in the record;
            the driver owns the clock and passes it through.
        agent_home: The agent home for the models document; defaults to
            the user's home when ``None``.

    Returns:
        Dict[str, Any]: exactly the record ``pirecord.build`` produces for
        the composed dimensions.

    Raises:
        BakeoffError: ``config`` is not one of the three pinned
            configurations; the value is named and no runner invocation
            happens.
    """
    if config not in ("print", "json", "ultrawork"):
        raise BakeoffError(
            "unknown configuration {!r}: expected one of print, json, "
            "ultrawork".format(config)
        )

    fixture_dir = Path(fixture_dir)
    results_dir = Path(results_dir)
    home = Path.home() if agent_home is None else Path(agent_home)

    results_dir.mkdir(exist_ok=True)

    models_path = home / ".pi" / "agent" / "models.json"
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

    pifixture.write_fixture(fixture_dir)
    before = pifixture.digest_fixture(fixture_dir)
    _write_digest(results_dir, "before.sha256", before)

    result = runner(
        {
            "argv": _argv_for(config, model_id, prompt, extension_path),
            "cwd": str(fixture_dir),
            "stdin": "/dev/null",
            "timeout_s": timeout_s,
        }
    )

    after = pifixture.digest_fixture(fixture_dir)
    _write_digest(results_dir, "after.sha256", after)
    changed = pifixture.changed_files(before, fixture_dir)

    stdout = result["stdout"]
    (results_dir / "stdout").write_text(stdout, encoding="utf-8")
    (results_dir / "stderr").write_text(result["stderr"], encoding="utf-8")

    if config == "json":
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
        assertion=pifixture.assertion_passes(fixture_dir),
        changed_files=changed,
        timestamp=timestamp,
    )


# The fixed run-all order (behaviour 5); the table renders in input order,
# so the order is part of the observable contract.
_RUN_ALL_CONFIGS: Tuple[str, ...] = ("print", "json", "ultrawork")


def _fallback_record(
    config: str, results_dir: Path, model_id: str, message: str, timestamp: str
) -> Dict[str, Any]:
    """The no-measurement record for a configuration whose runner raised.

    The exception's message lands as the assertion's stderr (the closed
    thirteen-key record shape has no free-form evidence field); everything
    else is the baseline: a non-zero sentinel exit code, zero wall time, no
    changed files, the empty-stream counters and outcome, and the pinned
    artifact paths with ``jsonl`` None.
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
    base_dir: Path,
    runner: Callable[[Dict[str, Any]], Dict[str, Any]],
    model_id: str,
    prompt: str,
    extension_path: str,
    gateway_host: str,
    gateway_port: int,
    context_window: int,
    max_tokens: int,
    timeout_s: float,
    *,
    timestamp: str,
    agent_home: Optional[Path] = None,
) -> Tuple[List[Dict[str, Any]], str]:
    """Drive all three bake-off configurations end to end and report.

    A thin orchestrator over :func:`run_one`: the configurations run in the
    fixed order ``print``, ``json``, ``ultrawork``, each against
    ``<base_dir>/<config>/fixture`` with artifacts under
    ``<base_dir>/<config>/results`` (``base_dir`` and the per-config
    directories are created). After each configuration a ``record.json``
    with content exactly ``json.dumps(record, sort_keys=True)`` is written
    to the results directory. Finally ``table.md`` is written to
    ``<base_dir>/table.md`` with content exactly
    ``pirecord.render_table(records)`` (records in run order), and that same
    string is returned.

    Failure isolation: if ``run_one`` raises for one configuration (any
    exception from the runner or the run), the exception is caught and a
    no-measurement fallback record is built for that configuration - the
    exception's message becomes the assertion's stderr - so the other
    configurations still run and the table still renders one row per
    configuration.

    Args:
        base_dir: The run root; created if missing, with one ``<config>``
            subtree per configuration.
        runner: The process-execution seam, passed to ``run_one`` verbatim.
        model_id: The model id for the argv and the models document.
        prompt: The task prompt passed to each invocation.
        extension_path: The pi-ultrawork extension path (ultrawork only).
        gateway_host: The gateway host for the models document.
        gateway_port: The gateway port for the models document.
        context_window: The context window for the models document.
        max_tokens: The max tokens for the models document.
        timeout_s: The wall-clock budget handed to the runner.
        timestamp: The ISO-8601 UTC stamp stored verbatim in every record;
            the driver owns the clock and passes it through.
        agent_home: The agent home for the models document; defaults to
            the user's home when ``None``.

    Returns:
        Tuple[List[Dict[str, Any]], str]: the records in run order and the
        rendered table.
    """
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    records: List[Dict[str, Any]] = []
    for config in _RUN_ALL_CONFIGS:
        fixture_dir = base_dir / config / "fixture"
        results_dir = base_dir / config / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        try:
            record = run_one(
                config,
                fixture_dir,
                results_dir,
                runner,
                model_id,
                prompt,
                extension_path,
                gateway_host,
                gateway_port,
                context_window,
                max_tokens,
                timeout_s,
                timestamp=timestamp,
                agent_home=agent_home,
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
