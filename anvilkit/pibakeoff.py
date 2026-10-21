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
Docker installed. ``subprocess_runner`` is the production implementation of
that seam: it spawns the argv list, drains both pipes from reader threads so
a full pipe buffer cannot stall the child, and reports a timed-out run as a
blocked-run result (killed, never raised).

One exception type: ``BakeoffError`` - raised for an unknown configuration
value, naming it, before any runner invocation happens.
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import anvilkit.config as piconfig
import anvilkit.piargv as piargv
import anvilkit.pievents as pievents
import anvilkit.pifixture as pifixture
import anvilkit.pirecord as pirecord


# The in-container entrypoint's pinned defaults (behaviour 8). ``config.yaml``
# is the read-only bind the compose service mounts; the results directory is
# the repo bind the operator reads the deliverables from; the npm root is the
# global install location the bake-off image puts pi-ultrawork in.
_DEFAULT_CONFIG_PATH = "/app/config.yaml"
_DEFAULT_RESULTS_DIR = "/workspace/results"
_DEFAULT_NPM_ROOT = "/usr/local/lib/node_modules"

# The phase-1 run parameters, pinned by doc/pi-bakeoff/README.md: the max
# output tokens, the per-run wall-clock budget, and the phase-1 trivial task
# prompt (verbatim).
BAKEOFF_MAX_TOKENS = 4096
BAKEOFF_TIMEOUT_S = 600.0
BAKEOFF_PROMPT = (
    "Edit `bakeoff_fixture/adder.py` so that `add(2, 3) == 5` passes. "
    "The function currently returns `a - b`; change it to `a + b`."
)


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


def _drain_pipe(fd: int, buffer: List[bytes]) -> None:
   """Reader-thread body: accumulate the pipe into ``buffer`` until EOF.

   Continuous draining is the load-bearing part of the runner contract:
   Pi's JSON event stream (``doc/external/pi-dev/json-event-stream.md``)
   must never be allowed to stall on a full pipe buffer, so the reader
   loops until the child closes the pipe. The read is a raw ``os.read``
   on the file descriptor, not a buffered ``read(n)``: a buffered read
   would block until a full ``n`` bytes arrive, losing partial output
   that must survive the kill path (e.g. a line printed right before a
   long sleep).
   """
   while True:
       chunk = os.read(fd, 65536)
       if not chunk:
           return
       buffer.append(chunk)


def subprocess_runner(spec: Dict[str, Any]) -> Dict[str, Any]:
   """The production runner: execute the spec, drain, and report.

   The real implementation of the runner seam the driver takes as an
   injected callable: spawn ``spec["argv"]`` as a list with
   ``subprocess.Popen`` (never a string, never ``shell=True``) in
   ``spec["cwd"]`` with stdin from ``/dev/null``, then drain stdout and
   stderr each from its own reader thread so neither can stall on a full
   pipe buffer, while the main thread enforces the wall-clock deadline
   ``spec["timeout_s"]``.

   A run still blocked after the deadline is killed (SIGKILL) and reported,
   never raised: the child runs in its own session, the whole process
   group is SIGKILLed, and the result carries ``timed_out`` True,
   ``exit_code`` ``-9`` (subprocess's negative-signal convention for a
   SIGKILL), the elapsed seconds as ``wall_time_s``, an ``evidence``
   string naming the timeout with the budget, and the partial output
   captured so far in ``stdout``. A plain ``communicate(timeout=...)``
   would not do: on timeout it discards the partial output the blocked-run
   path relies on.

   Args:
       spec: The invocation dict: ``argv`` (list of strings), ``cwd``
           (string), ``stdin`` (string; ``/dev/null``), ``timeout_s``
           (float, the wall-clock budget).

   Returns:
       Dict[str, Any]: exactly the six runner-contract keys, ``exit_code``
       (int), ``stdout`` (str), ``stderr`` (str), ``wall_time_s`` (float),
       ``timed_out`` (bool) and ``evidence`` (str, ``""`` unless blocked).

   Raises:
       BakeoffError: the spec is missing ``timeout_s``; the key is named
       and no process is spawned.
   """
   timeout_s = spec.get("timeout_s")
   if timeout_s is None:
       raise BakeoffError("spec is missing the required key 'timeout_s'")

   argv: List[str] = spec["argv"]
   # start_new_session=True gives the child its own session and process
   # group, so the timeout kill can SIGKILL the whole group: a command
   # line like ``sh -c "echo partial; sleep 30"`` would otherwise
   # orphan the sleep, which keeps the pipe write-ends open, the readers
   # never see EOF, and the bounded joins stall for the full budget.
   proc = subprocess.Popen(
       argv,
       cwd=spec["cwd"],
       stdin=subprocess.DEVNULL,
       stdout=subprocess.PIPE,
       stderr=subprocess.PIPE,
       start_new_session=True,
   )

   stdout_buffer: List[bytes] = []
   stderr_buffer: List[bytes] = []
   stdout_reader = threading.Thread(
       target=_drain_pipe, args=(proc.stdout.fileno(), stdout_buffer)
   )
   stderr_reader = threading.Thread(
       target=_drain_pipe, args=(proc.stderr.fileno(), stderr_buffer)
   )
   stdout_reader.start()
   stderr_reader.start()

   start = time.monotonic()
   deadline = start + timeout_s
   timed_out = False
   while True:
       remaining = deadline - time.monotonic()
       if remaining <= 0:
           timed_out = True
           # Kill the whole group (the child is its own session leader, so
           # pgid == pid) and reap the direct child.
           os.killpg(proc.pid, signal.SIGKILL)
           proc.wait()
           break
       try:
           proc.wait(timeout=remaining)
           break
       except subprocess.TimeoutExpired:
           continue

   elapsed = time.monotonic() - start
   # On the kill path the group was SIGKILLed and the direct child reaped;
   # -9 is the pinned sentinel, subprocess's negative-signal form for
   # SIGKILL. On success wait() already reaped the child, so returncode is
   # the process's own status.
   exit_code = -9 if timed_out else proc.returncode

   # Join both readers on every path: on success the pipes are closed and
   # the threads are already out; on the kill path the group SIGKILL
   # closes the pipes, so the bounded joins cannot leak a thread.
   stdout_reader.join(timeout=5.0)
   stderr_reader.join(timeout=5.0)

   # Release the pipe file descriptors on both paths; the captured bytes
   # are already in the buffers, so closing loses nothing.
   if proc.stdout is not None:
       proc.stdout.close()
   if proc.stderr is not None:
       proc.stderr.close()

   stdout = b"".join(stdout_buffer).decode("utf-8", "replace")
   stderr = b"".join(stderr_buffer).decode("utf-8", "replace")

   if timed_out:
       evidence = "timeout after {}s; process killed".format(timeout_s)
   else:
       evidence = ""

   return {
       "exit_code": exit_code,
       "stdout": stdout,
       "stderr": stderr,
       "wall_time_s": elapsed,
       "timed_out": timed_out,
       "evidence": evidence,
   }


def main(
   runner: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
) -> int:
   """The in-container entrypoint (behaviour 8: "entrypoint and compose
   wiring").

   Reads the gateway address from the service environment, the model id and
   context window from llama-swap's ``config.yaml`` (the read-only bind the
   compose service mounts), and drives all three configurations through
   :func:`run_all` with the module's pinned constants. The files on disk
   (the records, the table) are the deliverable, so the returned
   ``(records, table)`` is discarded.

   Args:
       runner: The process-execution seam; defaults to the module's own
           :func:`subprocess_runner`. Tests inject a fake here.

   Returns:
       int: 0 on a completed ``run_all`` - even when the table reads
       NO-GO, a run that measured a verdict is a successful run.

   Raises:
       BakeoffError: ``PI_GATEWAY_HOST`` is missing or empty, or
           ``PI_GATEWAY_PORT`` is missing, empty or non-numeric; the
           variable is named and ``run_all`` is never reached.
       anvilkit.config.ConfigError: the ``PI_CONFIG_PATH`` file is
           unreadable or semantically invalid; propagated unwrapped.
   """
   gateway_host = os.environ.get("PI_GATEWAY_HOST", "")
   if not gateway_host:
       raise BakeoffError(
           "PI_GATEWAY_HOST must be set and non-empty (the in-network "
           "gateway address)"
       )

   gateway_port_raw = os.environ.get("PI_GATEWAY_PORT", "")
   if not gateway_port_raw:
       raise BakeoffError(
           "PI_GATEWAY_PORT must be set and non-empty (the gateway port)"
       )
   try:
       gateway_port = int(gateway_port_raw)
   except ValueError:
       raise BakeoffError(
           "PI_GATEWAY_PORT must be a number, got {!r}".format(
               gateway_port_raw
           )
       ) from None

   config_path = os.environ.get("PI_CONFIG_PATH") or _DEFAULT_CONFIG_PATH
   results_dir = os.environ.get("PI_RESULTS_DIR") or _DEFAULT_RESULTS_DIR
   extension_path = os.environ.get("PI_EXTENSION_PATH") or str(
       Path(_DEFAULT_NPM_ROOT) / "pi-ultrawork" / "src" / "index.ts"
   )
   timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

   topology = piconfig.read_models(Path(config_path))
   run_all(
       Path(results_dir),
       runner if runner is not None else subprocess_runner,
       topology.coder_id,
       BAKEOFF_PROMPT,
       extension_path,
       gateway_host,
       gateway_port,
       topology.coder_context_window,
       BAKEOFF_MAX_TOKENS,
       BAKEOFF_TIMEOUT_S,
       timestamp=timestamp,
       agent_home=None,
   )
   return 0


if __name__ == "__main__":
   sys.exit(main())
