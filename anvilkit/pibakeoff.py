"""Bake-off run driver - one job: drive one bake-off configuration end to end.

Phase 1b (``plans/pi-phase1b-docker.md``, behaviour 4) runs one of the three
bake-off configurations - print, json, ultrawork - against a fresh fixture
directory and returns the ``anvilkit.pirecord.build`` record for it.

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
from typing import Any, Callable, Dict, List, Optional

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
