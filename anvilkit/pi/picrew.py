"""Crew-spike run driver - one job: drive the single crew-spike run.

``plans/pi-crew-spike.md`` behaviour 2 drives the one recorded ``pi-crew``
spike: a single ``pi --mode json`` invocation with the crew extension loaded
(``-e``) and the ``team`` tool allowlisted, against the ``pifixture`` trivial
red task reused verbatim from ``pibakeoff.BAKEOFF_PROMPT`` so the crew run is
comparable to the three recorded bake-off configurations.

The driver decides nothing about tokens: the models document comes from
``anvilkit.pi.piargv.models_document``, the fixture and the red/green
assertion from ``anvilkit.pi.pifixture``, and process execution is the seam
reused from ``anvilkit.pi.pibakeoff`` - the caller injects a ``runner``
callable that takes one invocation dict (``argv``, ``cwd``, ``stdin``,
``timeout_s``, ``env``) and returns one result dict (``exit_code``,
``stdout``, ``stderr``, ``wall_time_s``, ``timed_out``, ``evidence``).
``main`` is the in-container entrypoint (``python3 -m anvilkit.pi.picrew``):
it reads the gateway address from the service environment, the model id and
context window from llama-swap's ``config.yaml``, and drives the one run with
the module's pinned constants. The flat ``record.json`` it writes is
module-local - not ``pirecord.build``, whose ``_CONFIG_VALUES`` is closed.

One exception type: ``CrewSpikeError`` - raised (naming the offending value)
for an empty model id or an empty extension path before any runner
invocation, and in ``main`` for a missing/empty ``PI_GATEWAY_HOST`` or a
missing/empty/non-numeric ``PI_GATEWAY_PORT``. A non-zero exit, an absent
``.crew/`` tree, a ``team`` tool that never loads, and a budget-exhausted run
are all **recorded outcomes** in the record, never exceptions.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .. import config as piconfig
from . import pibakeoff
from . import piargv
from . import pifixture


# The in-container entrypoint's pinned defaults: ``config.yaml`` is the
# read-only bind the compose service mounts; the results directory is the
# repo bind the operator reads the deliverables from; the crew extension is
# the npm-global install layout the crew-spike image uses.
_DEFAULT_CONFIG_PATH = "/app/config.yaml"
_DEFAULT_RESULTS_DIR = "/workspace/results"
_DEFAULT_EXTENSION_PATH = "/usr/local/lib/node_modules/pi-crew/index.ts"

# The spike run parameters: the max output tokens and the per-run
# wall-clock budget, sized for a multi-worker run (child Pi processes are
# spawned per task), not the bake-off's 600 s.
CREW_SPIKE_MAX_TOKENS = 4096
CREW_SPIKE_TIMEOUT_S = 1800.0

# The locked pi-crew user-config values the agent dir must carry
# (doc/external/pi-dev/packages/pi-crew.md: ``runtime.mode`` and
# ``executeWorkers`` are settable in user config only; the broker is on by
# default, so the spike pins it off, and one concurrent worker keeps the
# recorded run comparable).
_PI_CREW_USER_CONFIG: Dict[str, Any] = {
    "runtime": {"mode": "child-process"},
    "executeWorkers": True,
    "broker": {"enabled": False},
    "limits": {"maxConcurrentWorkers": 1},
}

# The flat record's config label - the closed ``pirecord`` config set has no
# crew entry, so the label lives here.
_CONFIG_LABEL = "crew-spike"


class CrewSpikeError(Exception):
    """Any refusal to drive the crew-spike run.

    A single exception type covers every current refusal - an empty model
    id, an empty extension path, and the ``main`` gateway environment
    failures - so callers need one ``except`` clause. The message names the
    offending value so the caller knows which argument to fix.
    """


def _team_tool_seen(stdout: str) -> bool:
    """True iff the captured stdout JSONL names the ``team`` tool.

    Tool-execution records carry ``toolName``
    (doc/external/pi-dev/json-event-stream.md); a start, update or end
    record naming ``team`` is the proof the tool loaded. Lines that are not
    JSON objects are skipped, so a partial or non-JSON stream cannot
    break the scan.
    """
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        event_type = record.get("type")
        if not isinstance(event_type, str) or not event_type.startswith(
            "tool_execution"
        ):
            continue
        if record.get("toolName") == "team":
            return True
    return False


def _crew_tree(fixture_dir: Path) -> List[str]:
    """The sorted relative POSIX paths of the files under ``.crew/``.

    Crew state persists under ``<fixture>/.crew/`` (manifest, tasks,
    events, artifacts - doc/external/pi-dev/packages/pi-crew.md). The tree
    is absent when the extension never ran its state machine, so an empty
    list is the recorded outcome, not an error.
    """
    crew_dir = fixture_dir / ".crew"
    if not crew_dir.is_dir():
        return []
    return sorted(
        path.relative_to(crew_dir).as_posix()
        for path in crew_dir.rglob("*")
        if path.is_file()
    )


def run_spike(
    base_dir: Path,
    runner: Callable[[Dict[str, Any]], Dict[str, Any]],
    model_id: str,
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
    """Drive the single crew-spike run end to end.

    The sequence is: validate the model id and the extension path; create
    ``base_dir`` if missing (its parent must exist); write the agent-directory
    ``models.json`` (content exactly ``json.dumps`` of
    ``piargv.models_document`` - one builder, so the document cannot drift)
    and the pinned ``pi-crew.json`` user config to
    ``<agent_home>/.pi/agent`` (parents created; ``agent_home`` defaults to
    ``pathlib.Path.home()``); write the ``pifixture`` task into
    ``<base>/fixture``; invoke ``runner`` exactly once with the pinned crew
    argv, the fixture directory as cwd, stdin ``/dev/null``, the given
    timeout and the two-key env overlay that disables the broker and
    relocates the agent dir; capture stdout, stderr and the
    stdout-as-``events.jsonl`` drain at the pinned artifact paths under
    ``<base>/results``; derive ``team_tool_seen`` from the captured stream,
    the sorted ``.crew/`` listing and the fixture assertion; and write the
    flat ``record.json`` (module-local) at ``<base>/record.json`` with
    content exactly ``json.dumps(record, sort_keys=True)``.

    Args:
        base_dir: The results base dir; created if missing. The fixture
            lands at ``<base>/fixture``, the artifacts at
            ``<base>/results/{stdout, stderr, events.jsonl}`` and the record
            at ``<base>/record.json``.
        runner: The process-execution seam; one call, one invocation dict.
        model_id: The model id for the argv and the models document.
        extension_path: The pi-crew extension path loaded via ``-e``.
        gateway_host: The gateway host for the models document.
        gateway_port: The gateway port for the models document.
        context_window: The context window for the models document.
        max_tokens: The max tokens for the models document.
        timeout_s: The wall-clock budget handed to the runner.
        timestamp: The ISO-8601 UTC stamp stored verbatim in the record;
            the caller owns the clock and passes it through.
        agent_home: The agent home for the agent dir; defaults to the
            user's home when ``None``.

    Returns:
        Dict[str, Any]: exactly the flat record written to
        ``record.json`` - JSON-native throughout. ``completed`` is True iff
        the exit code is 0 and the fixture assertion passed.

    Raises:
        CrewSpikeError: ``model_id`` or ``extension_path`` is empty or
            whitespace-only; the value is named and no runner invocation
            happens.
    """
    if not model_id.strip():
        raise CrewSpikeError("model id must not be empty")
    if not extension_path.strip():
        raise CrewSpikeError("extension path must not be empty")

    base_dir = Path(base_dir)
    fixture_dir = base_dir / "fixture"
    results_dir = base_dir / "results"
    home = Path.home() if agent_home is None else Path(agent_home)
    agent_dir = home / ".pi" / "agent"

    base_dir.mkdir(exist_ok=True)
    results_dir.mkdir(exist_ok=True)

    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "models.json").write_text(
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
    (agent_dir / "pi-crew.json").write_text(
        json.dumps(_PI_CREW_USER_CONFIG, sort_keys=True), encoding="utf-8"
    )

    pifixture.write_fixture(fixture_dir)

    result = runner(
        {
            "argv": [
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
            ],
            "cwd": str(fixture_dir),
            "stdin": "/dev/null",
            "timeout_s": timeout_s,
            "env": {
                "PI_CREW_BROKER": "0",
                "PI_CODING_AGENT_DIR": str(agent_dir),
            },
        }
    )

    stdout = result["stdout"]
    (results_dir / "stdout").write_text(stdout, encoding="utf-8")
    (results_dir / "stderr").write_text(result["stderr"], encoding="utf-8")
    (results_dir / "events.jsonl").write_text(stdout, encoding="utf-8")

    assertion = pifixture.assertion_passes(fixture_dir)

    record: Dict[str, Any] = {
        "config": _CONFIG_LABEL,
        "completed": result["exit_code"] == 0 and assertion["passed"],
        "exit_code": result["exit_code"],
        "wall_time_s": result["wall_time_s"],
        "waited_for_input": result["timed_out"],
        "team_tool_seen": _team_tool_seen(stdout),
        "crew_tree": _crew_tree(fixture_dir),
        "artifacts": {
            "stdout": str(results_dir / "stdout"),
            "stderr": str(results_dir / "stderr"),
            "jsonl": str(results_dir / "events.jsonl"),
        },
        "assertion": assertion,
        "timestamp": timestamp,
    }

    (base_dir / "record.json").write_text(
        json.dumps(record, sort_keys=True), encoding="utf-8"
    )
    return record


def main(
    runner: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
) -> int:
    """The in-container entrypoint (``python3 -m anvilkit.pi.picrew``).

    Reads the gateway address from the service environment, the model id and
    context window from llama-swap's ``config.yaml`` (the read-only bind the
    compose service mounts), and drives the single crew-spike run through
    :func:`run_spike` with the module's pinned constants. The record and the
    artifacts on disk are the deliverable, so the returned record is
    discarded.

    Args:
        runner: The process-execution seam; defaults to the reused
            ``pibakeoff.subprocess_runner`` (identity, not equality). Tests
            inject a fake here; an injected runner is handed to
            :func:`run_spike` verbatim.

    Returns:
        int: 0 whenever the run was measured - a failed or budget-exhausted
        recorded outcome is still a successful run.

    Raises:
        CrewSpikeError: ``PI_GATEWAY_HOST`` is missing or empty, or
            ``PI_GATEWAY_PORT`` is missing, empty or non-numeric; the
            variable is named and no runner invocation happens.
        anvilkit.config.ConfigError: the ``PI_CONFIG_PATH`` file is
            unreadable or semantically invalid; propagated unwrapped.
    """
    gateway_host = os.environ.get("PI_GATEWAY_HOST", "")
    if not gateway_host:
        raise CrewSpikeError(
            "PI_GATEWAY_HOST must be set and non-empty (the in-network "
            "gateway address)"
        )

    gateway_port_raw = os.environ.get("PI_GATEWAY_PORT", "")
    if not gateway_port_raw:
        raise CrewSpikeError(
            "PI_GATEWAY_PORT must be set and non-empty (the gateway port)"
        )
    try:
        gateway_port = int(gateway_port_raw)
    except ValueError:
        raise CrewSpikeError(
            "PI_GATEWAY_PORT must be a number, got {!r}".format(
                gateway_port_raw
            )
        ) from None

    config_path = os.environ.get("PI_CONFIG_PATH") or _DEFAULT_CONFIG_PATH
    results_dir = os.environ.get("PI_RESULTS_DIR") or _DEFAULT_RESULTS_DIR
    extension_path = (
        os.environ.get("PI_EXTENSION_PATH") or _DEFAULT_EXTENSION_PATH
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    topology = piconfig.read_models(Path(config_path))
    run_spike(
        Path(results_dir),
        runner if runner is not None else pibakeoff.subprocess_runner,
        topology.coder_id,
        extension_path,
        gateway_host,
        gateway_port,
        topology.coder_context_window,
        CREW_SPIKE_MAX_TOKENS,
        CREW_SPIKE_TIMEOUT_S,
        timestamp=timestamp,
        agent_home=None,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
