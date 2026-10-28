"""Host smoke test for the real single-role stack.

Renders per-layer verdicts for a human: one line per layer carrying its name
and detail, a verdict glyph for passed and failed layers, and indented fix
lines beneath a failing layer only. This behaviour is the report renderer
behaviour 1 of ``plans/smoke-test.md``. ``summarize`` (behaviour 2) turns the
layer results into the process exit code the CLI returns, and
``check_docker_daemon`` (behaviour 4) is layer 1's daemon check: it runs the
injected docker runner once with the version-probe argv and turns the outcome
into a ``LayerResult`` -- a ``FileNotFoundError`` from the runner is a fail
saying docker is not on PATH, never a traceback.
``check_sandbox_image`` (behaviour 5) is layer 1's image-presence check,
over the same injected runner: it inspects the image tag (defaulting to the
plan's pinned tag) and derives its fail fix line from
``anvilkit.pi.pisandbox.build_argv`` so it cannot drift from the build
command. ``check_sandbox_network`` (behaviour 6) is layer 1's
internal-network-presence check, over the same runner: it inspects the
adopted :data:`INTERNAL_NETWORK` name and its fail fix line names that
compose creates the network. ``check_gateway_container`` (behaviour 7) is
layer 2's gateway container check, over the same runner: it lists running
containers filtered by the adopted :data:`GATEWAY_CONTAINER` name and passes
only when a line of the output equals that name exactly (after stripping) --
never a substring -- with the compose-up command as the fail fix line.
``check_gateway_model`` (behaviour 8) is layer 2's coder-model check: it
reads the coder id from llama-swap's read-only ``config.yaml`` through the
injected ``read_models`` seam and probes the resolved host port through the
injected ``check_gateway`` seam, which default to the real
:func:`anvilkit.config.read_models` and :func:`anvilkit.health.check_gateway`.
It passes only when the coder id is registered on the gateway and hot;
offline, id-absent and id-present-but-cold each yield their own distinct
detail, a ``ConfigError`` from ``read_models`` fails the layer naming the
file, and every detail states that the in-network port is 8080 regardless of
the host ``LLM_PORT``. ``check_agent_volume`` (behaviour 9) is layer 3's
agent-volume-presence check, over the same runner: it inspects the adopted
:data:`NAMED_VOLUME` name and passes only when the inspect exits 0; a
non-zero exit fails with a detail saying the volume is created on first run
and stays empty until seeded. ``check_models_json`` (behaviour 10) is
layer 3's models.json-readability check, over the same runner and with an
image tag defaulting to :data:`DEFAULT_IMAGE_TAG`: it cats the agent home's
``models.json`` in a container running as the adopted image uid and returns
the layer result plus the exact stdout on a pass (so behaviour 11 can parse
it) and ``None`` on every fail; a readable but empty or whitespace-only
file fails as unseeded, a no-such-file stderr fails with the seed
instruction and no chown line, and a permission stderr fails with the
``chown -R`` one-liner as its fix line, composed from the adopted
constants. ``check_coder_id`` (behaviour 11) is layer 3'
coder-id-match check, over no runner: it parses the exact stdout
:func:`check_models_json` exposed on a pass as the models.json shape
of ``tests/fixtures/golden_pi_models.json`` -- a top-level
``providers`` mapping of provider name to provider object, each
provider carrying a ``models`` list, each model carrying an ``id``
-- and reads the coder id from llama-swap's read-only
``config.yaml`` through the injected ``read_models`` seam (default
:func:`anvilkit.config.read_models`). It passes, naming the provider
carrying the id and the id itself, when the coder id appears as some
``providers.<name>.models[].id``; the id absent fails, printing both
the expected coder id and the seeded ids found, malformed JSON fails
naming the parse error, and a missing or non-dict ``providers`` key,
a provider with no ``models`` key, or a ``models`` that is not a list
fails saying so -- a ``KeyError``, ``TypeError`` or
``JSONDecodeError`` never escapes. ``repair_models_json`` (behaviour 12)
is layer 3's ``--fix`` repair, over the same runner: it takes the exact
``(LayerResult, Optional[str])`` tuple :func:`check_models_json` returned
and, only when ``fix`` is set and the read failed with a fix line carrying
the chown one-liner, spawns the root chown exactly once and retries the
read exactly once with the identical argv, the retry's verdict -- and its
exact stdout on a pass -- becoming the final one; a chown that itself exits
non-zero fails the layer with the chown's stderr in the detail and no read
retry at all, and a pass, ``fix=False``, or a failure without the chown fix
line (missing-file or generic) returns the first read's verdict unchanged,
spawning nothing. ``check_role_prompt`` (behaviour 13) is layer 4's
role-prompt-presence check, over no runner: a plain read-only filesystem
check on the target repo -- it derives the path from the injected
``resolve_role`` seam's ``prompt_path`` (default a closure over the real
:func:`anvilkit.pi.pirole.resolve`, whose prompt path does not depend on
the model ids), and an existing non-empty file passes naming the absolute
path, a missing path fails saying it is missing with a fix line carrying
the minimal content to write, an empty or whitespace-only file fails
saying it is empty -- a detail distinct from the missing one -- and a
directory at the path fails saying it is not a file; it never creates,
modifies, deletes or renames anything. ``new_session_id``
(behaviour 14) mints a fresh session id per invocation --
``smoke-<UTC timestamp>-<random suffix>`` -- from ``datetime.datetime``
and ``secrets.token_hex``, so two calls never collide even within the
same tick and the id always passes the real
:func:`anvilkit.pi.pirole.role_argv` session-id validation (letters,
numbers, ``.``, ``_``, ``-``; starts and ends alphanumeric).
``check_coder_run`` (behaviour 15) is layer 5's real coder run: it calls
the real :func:`anvilkit.pi.pidriver.run_role` with the resolved coder
definition (via the injectable ``resolve_role`` seam, defaulting to a
closure over the real :func:`anvilkit.pi.pirole.resolve`), a fresh session
id from :func:`new_session_id`, the target repo, the image tag, the
trivial task and the injected runner -- never wrapping or mocking the
driver, so the driver's own ``DriverError`` rule (non-zero exit with empty
stdout) genuinely fires. It passes only when ``exit_code == 0``,
``timed_out is False`` and ``pievents.parse(stdout)`` yields at least one
record -- judged on the stream existing, never on stderr or model content;
each failing condition names itself in its own distinct detail, a
``DriverError`` from the driver fails the layer with the exception's
message, and a prior layer not passing makes the layer ``skipped`` with
the runner uncalled. ``check_bad_image_tag`` (behaviour 16) is the
bad-image-tag sub-check of the layer-6 report name ``failure-paths``: it
calls the same real :func:`anvilkit.pi.pidriver.run_role` with an image
tag no image matches (so the daemon refuses the start -- non-zero exit,
empty stdout -- and the driver's own ``DriverError`` genuinely fires)
with the resolved coder definition (via the same injectable
``resolve_role`` seam as :func:`check_coder_run`, so no real model is
ever needed), a fresh :func:`new_session_id` and the injected runner --
never wrapping or mocking the driver. When the ``DriverError`` fires the
layer PASSES, naming the ``DriverError``, the bad tag and the daemon
stderr in its detail; when ``run_role`` returns instead the failure path
did not fire and the layer FAILS saying so -- the opposite verdict of
behaviour 15, whose ``DriverError`` is a failure.

The four pinned names -- the agent volume, the internal network, the image
uid and the agent home -- are adopted as module-level constants from
``anvilkit.pi.pisandbox`` (behaviour 3), so this module never re-spells them
as literals. The gateway container name is the compose ``container_name``,
spelled once as :data:`GATEWAY_CONTAINER` (behaviour 7).
"""

import dataclasses
import datetime
import json
import os
import secrets
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from anvilkit import config, health
from anvilkit.pi import pidriver, pievents, pirole, pisandbox

# The stable header rendered by ``format_report``, even when there is nothing
# else to say. Later behaviours assert this exact string.
HEADER = "Anvil smoke test"

# The four pinned names, adopted from ``anvilkit.pi.pisandbox`` rather than
# re-spelled (behaviour 3 of ``plans/smoke-test.md``).
NAMED_VOLUME = pisandbox._NAMED_VOLUME
INTERNAL_NETWORK = pisandbox._INTERNAL_NETWORK
IMAGE_UID = pisandbox._IMAGE_UID
AGENT_HOME = pisandbox._AGENT_HOME

# Canonical layer states.
STATE_OK = "ok"
STATE_FAILED = "failed"
STATE_SKIPPED = "skipped"

PASS_GLYPH = "\u2705"  # ✅
FAIL_GLYPH = "\u274c"  # ❌
# A skipped layer carries neither verdict glyph, but is not silent either: a
# plain bullet keeps it on its own line without claiming a verdict.
SKIP_MARK = "-"


@dataclasses.dataclass
class LayerResult:
    """The outcome of one smoke-test layer.

    ``ok`` is a state string, one of :data:`STATE_OK`, :data:`STATE_FAILED`
    or :data:`STATE_SKIPPED`; ``detail`` is the one-line human explanation;
    ``fix_lines`` are the remediation commands, shown under a failing layer
    only.
    """

    name: str
    ok: str
    detail: str
    fix_lines: Sequence[str] = ()


def _layer_lines(result: "LayerResult") -> Sequence[str]:
    """The report lines for one layer: its line, plus fix lines for failures."""
    if result.ok == STATE_OK:
        head = "%s %s: %s" % (PASS_GLYPH, result.name, result.detail)
    elif result.ok == STATE_FAILED:
        head = "%s %s: %s" % (FAIL_GLYPH, result.name, result.detail)
    else:  # STATE_SKIPPED — never a verdict glyph, never its fix lines.
        head = "%s %s: %s" % (SKIP_MARK, result.name, result.detail)
    if result.ok == STATE_FAILED:
        return (head,) + tuple("  " + fix for fix in result.fix_lines)
    return (head,)


def format_report(results: Sequence["LayerResult"]) -> str:
    """Render one verdict line per layer, in order, under the stable header.

    A passing layer gets the ✅ line, a failing layer the ❌ line with its
    fix lines indented beneath it, a skipped layer a plain line; fix lines
    never print for passing or skipped results, and an empty list renders
    only :data:`HEADER`.
    """
    lines = [HEADER]
    for result in results:
        lines.extend(_layer_lines(result))
    return "\n".join(lines) + "\n"


def summarize(results: Sequence["LayerResult"]) -> int:
    """Map the layer results onto the process exit code.

    The layer number is the 1-based position in the list: positions 1–4 are
    the docker class (exit 4), positions 5–6 the internal class (exit 1). A
    state that is neither :data:`STATE_OK` nor :data:`STATE_SKIPPED` counts
    as failed in its positional class; a skipped layer never contributes to a
    non-zero exit. When both classes have failures the docker class (4)
    wins; an empty list yields 0.
    """
    docker_failed = False
    internal_failed = False
    for position, result in enumerate(results, start=1):
        if result.ok in (STATE_OK, STATE_SKIPPED):
            continue
        if position <= 4:
            docker_failed = True
        else:
            internal_failed = True
    if docker_failed:
        return 4
    if internal_failed:
        return 1
    return 0


# The version probe layer 1 runs (behaviour 4 of ``plans/smoke-test.md``):
# list-form argv only, no shell.
DAEMON_ARGV = ["docker", "version", "--format", "{{.Server.Version}}"]


def check_docker_daemon(
    docker_runner: Callable[[Sequence[str]], Tuple[int, str, str]]
) -> "LayerResult":
    """Layer 1: is the Docker daemon reachable?

    ``docker_runner`` is the injected seam with the contract
    ``docker_runner(argv) -> (exit_code, stdout, stderr)``. It is called
    exactly once with :data:`DAEMON_ARGV`; exit 0 passes with the trimmed
    server version in the detail, a non-zero exit fails with the stderr in
    the detail, and a ``FileNotFoundError`` from the runner fails saying
    docker is not on PATH -- it never escapes as a traceback.
    """
    try:
        exit_code, stdout, stderr = docker_runner(DAEMON_ARGV)
    except FileNotFoundError:
        return LayerResult(
            name="docker-daemon",
            ok=STATE_FAILED,
            detail="docker not on PATH",
        )
    if exit_code == 0:
        return LayerResult(
            name="docker-daemon",
            ok=STATE_OK,
            detail="server %s" % stdout.strip(),
        )
    return LayerResult(
        name="docker-daemon",
        ok=STATE_FAILED,
        detail=stderr.strip(),
    )


# The image tag layer 1's image check inspects by default (behaviour 5 of
# ``plans/smoke-test.md``): the plan's pinned default, spelled here once and
# never re-typed into an argv.
DEFAULT_IMAGE_TAG = "pi-sandbox"


def check_sandbox_image(
   docker_runner: Callable[[Sequence[str]], Tuple[int, str, str]],
   tag: str = DEFAULT_IMAGE_TAG,
) -> "LayerResult":
   """Layer 1: is the sandbox image present under ``tag``?

   ``docker_runner`` is the same injected seam as
   :func:`check_docker_daemon`, with the contract
   ``docker_runner(argv) -> (exit_code, stdout, stderr)``. It is called
   exactly once with ``["docker", "image", "inspect", <tag>]``; exit 0
   passes, a non-zero exit fails with its stderr in the detail and exactly
   one fix line, ``" ".join(pisandbox.build_argv(tag))`` -- derived from the
   same public builder the image is actually built with, so a Dockerfile-
   path change cannot leave the fix stale. A ``FileNotFoundError`` from the
   runner fails saying docker is not on PATH, mirroring the daemon check.
   """
   try:
       exit_code, _stdout, stderr = docker_runner(
           ["docker", "image", "inspect", tag]
       )
   except FileNotFoundError:
       return LayerResult(
           name="sandbox-image",
           ok=STATE_FAILED,
           detail="docker not on PATH",
       )
   if exit_code == 0:
       return LayerResult(
           name="sandbox-image",
           ok=STATE_OK,
           detail="image %s present" % tag,
       )
   return LayerResult(
       name="sandbox-image",
       ok=STATE_FAILED,
       detail=stderr.strip(),
       fix_lines=(" ".join(pisandbox.build_argv(tag)),),
   )


# The compose-up that creates the internal network (behaviour 6 of
# ``plans/smoke-test.md``): the plan pins this exact command, so it is
# spelled here once and never re-typed.
NETWORK_FIX_COMMAND = "docker compose --profile coder up -d"


def check_sandbox_network(
   docker_runner: Callable[[Sequence[str]], Tuple[int, str, str]]
) -> "LayerResult":
   """Layer 1: is the internal network present?

   ``docker_runner`` is the same injected seam as
   :func:`check_docker_daemon`, with the contract
   ``docker_runner(argv) -> (exit_code, stdout, stderr)``. It is called
   exactly once with ``["docker", "network", "inspect", <name>]`` where
   ``<name>`` is the adopted :data:`INTERNAL_NETWORK` constant, never a
   re-spelled literal, so a rename in ``anvilkit.pi.pisandbox`` keeps the
   check and the run in step. Exit 0 passes, a non-zero exit fails with
   its stderr in the detail and exactly one fix line naming that compose
   creates the network, and a ``FileNotFoundError`` from the runner fails
   saying docker is not on PATH, mirroring the daemon check.
   """
   try:
       exit_code, _stdout, stderr = docker_runner(
           ["docker", "network", "inspect", INTERNAL_NETWORK]
       )
   except FileNotFoundError:
       return LayerResult(
           name="sandbox-network",
           ok=STATE_FAILED,
           detail="docker not on PATH",
       )
   if exit_code == 0:
       return LayerResult(
           name="sandbox-network",
           ok=STATE_OK,
           detail="network %s present" % INTERNAL_NETWORK,
       )
   return LayerResult(
       name="sandbox-network",
       ok=STATE_FAILED,
       detail=stderr.strip(),
       fix_lines=(NETWORK_FIX_COMMAND + "  # compose creates the network",),
   )


# The gateway container name (behaviour 7 of ``plans/smoke-test.md``): the
# ``container_name`` from ``docker-compose.yml`` -- the service/DNS name is
# only an address, never the match.
GATEWAY_CONTAINER = "llama-swap-service"


def check_gateway_container(
   docker_runner: Callable[[Sequence[str]], Tuple[int, str, str]]
) -> "LayerResult":
   """Layer 2: is the gateway container running?

   ``docker_runner`` is the same injected seam as
   :func:`check_docker_daemon`, with the contract
   ``docker_runner(argv) -> (exit_code, stdout, stderr)``. It is called
   exactly once with ``["docker", "ps", "--filter", "name=<container>",
   "--format", "{{.Names}}"]`` where ``<container>`` is the adopted
   :data:`GATEWAY_CONTAINER` constant. Exit 0 passes when some line of the
   output, stripped, equals the container name exactly -- never a
   substring, so a longer container that merely contains it fails; a
   non-zero exit, or an output with no exact line (including empty
   output), fails with the stderr in the detail and one fix line carrying
   the compose-up command. A ``FileNotFoundError`` from the runner fails
   saying docker is not on PATH, mirroring the daemon check.
   """
   try:
       exit_code, stdout, stderr = docker_runner(
           ["docker", "ps", "--filter", "name=" + GATEWAY_CONTAINER,
            "--format", "{{.Names}}"]
       )
   except FileNotFoundError:
       return LayerResult(
           name="gateway-container",
           ok=STATE_FAILED,
           detail="docker not on PATH",
       )
   if exit_code != 0:
       return LayerResult(
           name="gateway-container",
           ok=STATE_FAILED,
           detail=stderr.strip(),
           fix_lines=(NETWORK_FIX_COMMAND
                      + "  # compose starts the gateway container",),
       )
   if any(line.strip() == GATEWAY_CONTAINER
          for line in stdout.splitlines()):
       return LayerResult(
           name="gateway-container",
           ok=STATE_OK,
           detail="container %s running" % GATEWAY_CONTAINER,
       )
   return LayerResult(
       name="gateway-container",
       ok=STATE_FAILED,
       detail="container %s not running" % GATEWAY_CONTAINER,
       fix_lines=(NETWORK_FIX_COMMAND
                  + "  # compose starts the gateway container",),
   )


# The in-network port the gateway always serves on, which layer 2's
# gateway-model detail states on pass and on every fail, regardless of the
# host LLM_PORT (behaviour 8 of ``plans/smoke-test.md``).
_IN_NETWORK_PORT = "8080"
_IN_NETWORK_FACT = (
   "the in-network port is %s regardless of the host LLM_PORT"
   % _IN_NETWORK_PORT
)


def check_gateway_model(
   port: int,
   config_path: config.PathLike,
   check_gateway: Callable[[int], health.GatewayStatus] = health.check_gateway,
   read_models: Callable[[config.PathLike], config.ModelTopology] = config.read_models,
) -> "LayerResult":
   """Layer 2: is the coder model registered on the gateway and hot?

   ``read_models`` (default :func:`anvilkit.config.read_models`) is called
   once with ``config_path``; its ``coder_id`` (``matrix.vars.coder``) is the
   id this layer matches -- never a hard-coded one. ``check_gateway``
   (default :func:`anvilkit.health.check_gateway`) is called once with the
   resolved port, positionally. The layer passes when the gateway is online,
   the coder id is among ``status.models`` and that entry is hot. Each
   failure mode -- offline, id absent, id present but cold -- carries its own
   distinct detail, and a ``ConfigError`` from ``read_models`` fails the
   layer naming ``config_path``; no exception ever escapes. Every detail,
   pass or fail, states that the in-network port is :data:`_IN_NETWORK_PORT`
   regardless of the host ``LLM_PORT``.
   """
   try:
       topology = read_models(config_path)
   except config.ConfigError as exc:
       return LayerResult(
           name="gateway-model",
           ok=STATE_FAILED,
           detail="cannot read the coder id from %s: %s; %s"
           % (config_path, exc, _IN_NETWORK_FACT),
       )
   status = check_gateway(port)
   if not status.online:
       return LayerResult(
           name="gateway-model",
           ok=STATE_FAILED,
           detail="gateway is offline (%s); %s"
           % (status.error or "no reason given", _IN_NETWORK_FACT),
       )
   entry = None
   for model in status.models:
       if model.id == topology.coder_id:
           entry = model
           break
   if entry is None:
       return LayerResult(
           name="gateway-model",
           ok=STATE_FAILED,
           detail="coder model %s is not registered on the gateway; %s"
           % (topology.coder_id, _IN_NETWORK_FACT),
       )
   if not entry.hot:
       return LayerResult(
           name="gateway-model",
           ok=STATE_FAILED,
           detail="coder model %s is registered but cold; %s"
           % (topology.coder_id, _IN_NETWORK_FACT),
       )
   return LayerResult(
       name="gateway-model",
       ok=STATE_OK,
       detail="coder model %s is registered and hot; %s"
       % (topology.coder_id, _IN_NETWORK_FACT),
   )


def check_agent_volume(
   docker_runner: Callable[[Sequence[str]], Tuple[int, str, str]]
) -> "LayerResult":
   """Layer 3: does the agent volume exist?

   ``docker_runner`` is the same injected seam as
   :func:`check_docker_daemon`, with the contract
   ``docker_runner(argv) -> (exit_code, stdout, stderr)``. It is called
   exactly once with ``["docker", "volume", "inspect", <name>]`` where
   ``<name>`` is the adopted :data:`NAMED_VOLUME` constant, never a
   re-spelled literal, so a rename in ``anvilkit.pi.pisandbox`` keeps the
   check and the run in step. Exit 0 passes, a non-zero exit fails with a
   detail saying the volume is created on first run and stays empty until
   seeded, and a ``FileNotFoundError`` from the runner fails saying docker
   is not on PATH, mirroring the daemon check.
   """
   try:
       exit_code, _stdout, stderr = docker_runner(
           ["docker", "volume", "inspect", NAMED_VOLUME]
       )
   except FileNotFoundError:
       return LayerResult(
           name="agent-volume",
           ok=STATE_FAILED,
           detail="docker not on PATH",
       )
   if exit_code == 0:
       return LayerResult(
           name="agent-volume",
           ok=STATE_OK,
           detail="volume %s present" % NAMED_VOLUME,
       )
   return LayerResult(
       name="agent-volume",
       ok=STATE_FAILED,
       detail="volume %s missing -- created on first run, stays empty "
              "until seeded" % NAMED_VOLUME,
   )


def _models_json_read_argv(tag: str) -> List[str]:
    """The list-form argv that cats the agent's models.json (behaviour 10).

    Every name is read from the adopted constants, never re-spelled; the
    behaviour-12 retry reuses this helper, so its argv cannot drift from
    the first read's.
    """
    return [
        "docker",
        "run",
        "--rm",
        "-v",
        NAMED_VOLUME + ":" + AGENT_HOME,
        "--user",
        IMAGE_UID,
        tag,
        "cat",
        AGENT_HOME + "/models.json",
    ]


def _chown_argv(tag: str) -> List[str]:
    """The list-form argv the root chown runs with (behaviour 12).

    Only the root user id and the ``chown`` verb are literals; every name
    is read from the adopted constants, so the repair and the fail fix line
    are composed from the same argv and cannot drift.
    """
    return [
        "docker",
        "run",
        "--rm",
        "-v",
        NAMED_VOLUME + ":" + AGENT_HOME,
        "--user",
        "0",
        tag,
        "chown",
        "-R",
        IMAGE_UID + ":" + IMAGE_UID,
        AGENT_HOME,
    ]


def _models_json_verdict(
    exit_code: int,
    stdout: str,
    stderr: str,
    tag: str,
) -> Tuple["LayerResult", Optional[str]]:
    """Turn one read's raw outcome into the behaviour-10 verdict 2-tuple.

    Exit 0 with non-empty stdout is the pass state, exposing the exact
    stdout; exit 0 with an empty or whitespace-only stdout is a fail saying
    the file is unseeded, with no content exposed; a non-zero exit whose
    stderr says no such file is a fail saying the file is missing and must
    be seeded, with no chown fix line; any other non-zero exit is a fail
    with the stderr in the detail and exactly one fix line carrying the
    root chown one-liner. ``tag`` feeds the chown fix line only.
    """
    if exit_code == 0:
        if not stdout.strip():
            return (
                LayerResult(
                    name="models-json",
                    ok=STATE_FAILED,
                    detail="%s/models.json is readable but unseeded "
                           "(empty or whitespace-only)" % AGENT_HOME,
                ),
                None,
            )
        return (
            LayerResult(
                name="models-json",
                ok=STATE_OK,
                detail="models.json readable by the image uid",
            ),
            stdout,
        )
    if "no such file" in stderr.lower():
        return (
            LayerResult(
                name="models-json",
                ok=STATE_FAILED,
                detail="%s/models.json is missing; seed it into the agent "
                       "volume before re-running" % AGENT_HOME,
            ),
            None,
        )
    return (
        LayerResult(
            name="models-json",
            ok=STATE_FAILED,
            detail=stderr.strip(),
            fix_lines=(" ".join(_chown_argv(tag)),),
        ),
        None,
    )


def check_models_json(
    docker_runner: Callable[[Sequence[str]], Tuple[int, str, str]],
    tag: str = DEFAULT_IMAGE_TAG,
) -> Tuple["LayerResult", Optional[str]]:
    """Layer 3: is the agent's models.json readable by the image uid?

   ``docker_runner`` is the same injected seam as
   :func:`check_docker_daemon`, with the contract
   ``docker_runner(argv) -> (exit_code, stdout, stderr)``. It is called
   exactly once with the list-form argv
   ``["docker", "run", "--rm", "-v", <NAMED_VOLUME>:<AGENT_HOME>,
   "--user", <IMAGE_UID>, <tag>, "cat", <AGENT_HOME>/models.json"]`` --
   every name from the adopted constants, the tag defaulting to
   :data:`DEFAULT_IMAGE_TAG`. The second element of the returned
   2-tuple carries the exact stdout the in-container ``cat`` printed, so
   behaviour 11 can parse it; it is ``None`` on every fail. Exit 0 with
   non-empty stdout is the pass state; exit 0 with an empty or
   whitespace-only stdout is a fail saying the file is unseeded, with no
   content exposed; a non-zero exit whose stderr says no such file is a
   fail saying the file is missing and must be seeded, with no chown fix
   line; any other non-zero exit is a fail with the stderr in the detail
   and exactly one fix line carrying the root ``chown -R`` one-liner
   composed from the adopted constants. A ``FileNotFoundError`` from the
   runner fails saying docker is not on PATH, mirroring the daemon check.
   """
    try:
        exit_code, stdout, stderr = docker_runner(
            _models_json_read_argv(tag)
        )
    except FileNotFoundError:
        return (
            LayerResult(
                name="models-json",
                ok=STATE_FAILED,
                detail="docker not on PATH",
            ),
            None,
        )
    return _models_json_verdict(exit_code, stdout, stderr, tag)


def repair_models_json(
    docker_runner: Callable[[Sequence[str]], Tuple[int, str, str]],
    *,
    tag: str = DEFAULT_IMAGE_TAG,
    fix: bool = False,
    first_read: Tuple["LayerResult", Optional[str]],
) -> Tuple["LayerResult", Optional[str]]:
    """Layer 3: the ``--fix`` chown-and-retry repair (behaviour 12).

    ``docker_runner`` is the same injected seam as
    :func:`check_models_json`, with the contract
    ``docker_runner(argv) -> (exit_code, stdout, stderr)``. ``first_read``
    is the exact ``(LayerResult, Optional[str])`` tuple
    :func:`check_models_json` returned, and the repair decides from it. A
    pass, ``fix=False``, or a failure whose fix lines carry no chown one-
    liner (the missing-file and generic failures) returns ``first_read``
    unchanged, spawning nothing. ``fix=True`` with a permission failure --
    a fix line carrying the root chown one-liner -- spawns the chown
    exactly once with :func:`_chown_argv` and retries the read exactly
    once with the identical argv :func:`check_models_json` used; the
    retry's verdict -- and its exact stdout on a pass -- is the final one
    returned. A chown that itself exits non-zero fails the layer with the
    chown's stderr in the detail and no read retry at all. A
    ``FileNotFoundError`` from the runner fails the layer saying docker is
    not on PATH, mirroring the read check.
    """
    result, _content = first_read
    if result.ok != STATE_FAILED or not fix:
        return first_read
    if not any("chown" in fix_line for fix_line in result.fix_lines):
        return first_read
    try:
        exit_code, _chown_stdout, chown_stderr = docker_runner(
            _chown_argv(tag)
        )
    except FileNotFoundError:
        return (
            LayerResult(
                name="models-json",
                ok=STATE_FAILED,
                detail="docker not on PATH",
            ),
            None,
        )
    if exit_code != 0:
        return (
            LayerResult(
                name="models-json",
                ok=STATE_FAILED,
                detail="chown failed: %s" % chown_stderr.strip(),
            ),
            None,
        )
    try:
        exit_code, stdout, stderr = docker_runner(_models_json_read_argv(tag))
    except FileNotFoundError:
        return (
            LayerResult(
                name="models-json",
                ok=STATE_FAILED,
                detail="docker not on PATH",
            ),
            None,
        )
    return _models_json_verdict(exit_code, stdout, stderr, tag)


def check_coder_id(
    models_json_text: str,
    config_path: config.PathLike,
    read_models: Callable[[config.PathLike], config.ModelTopology] = config.read_models,
) -> "LayerResult":
    """Layer 3: does the seeded models.json register the coder model?

    ``read_models`` (default :func:`anvilkit.config.read_models`) is called
    once with ``(config_path, False)`` and its ``coder_id``
    (``matrix.vars.coder``) is the id this layer matches -- never a
    hard-coded one. ``models_json_text`` is the exact stdout
    :func:`check_models_json` exposed on a pass; it is parsed as the
    models.json shape of ``tests/fixtures/golden_pi_models.json`` -- a
    top-level ``providers`` mapping of provider name to provider object,
    each provider carrying a ``models`` list, each model carrying an
    ``id``. The layer passes when the coder id appears as some
    ``providers.<name>.models[].id``, naming the provider carrying it and
    the id itself; the id absent fails, printing both the expected coder
    id and the seeded ids found. A ``JSONDecodeError`` fails naming the
    parse error, a missing or non-dict ``providers`` key fails naming
    ``providers``, and a provider with no ``models`` key or a ``models``
    that is not a list fails saying so -- a ``KeyError``, ``TypeError`` or
    ``JSONDecodeError`` never escapes.
    """
    topology = read_models(config_path, False)
    coder_id = topology.coder_id
    try:
        document = json.loads(models_json_text)
    except json.JSONDecodeError as exc:
        return LayerResult(
            name="coder-id-match",
            ok=STATE_FAILED,
            detail="models.json does not parse: %s" % exc,
        )
    providers = document.get("providers") if isinstance(document, dict) else None
    if not isinstance(providers, dict):
        return LayerResult(
            name="coder-id-match",
            ok=STATE_FAILED,
            detail="models.json has no providers mapping",
        )
    seeded_ids = []  # type: List[str]
    carrying_provider = None  # type: Optional[str]
    for provider_name, provider in providers.items():
        if not isinstance(provider, dict):
            continue
        models = provider.get("models")
        if not isinstance(models, list):
            return LayerResult(
                name="coder-id-match",
                ok=STATE_FAILED,
                detail="provider %s has no models list" % provider_name,
            )
        for model in models:
            if not isinstance(model, dict):
                continue
            model_id = model.get("id")
            if not isinstance(model_id, str):
                continue
            seeded_ids.append(model_id)
            if model_id == coder_id and carrying_provider is None:
                carrying_provider = provider_name
    if carrying_provider is not None:
        return LayerResult(
            name="coder-id-match",
            ok=STATE_OK,
            detail="coder model %s is registered under provider %s"
            % (coder_id, carrying_provider),
        )
    return LayerResult(
        name="coder-id-match",
        ok=STATE_FAILED,
        detail="coder model %s is not registered; models.json seeds %s"
        % (coder_id, ", ".join(seeded_ids) if seeded_ids else "no models"),
    )


# The minimal valid role markdown the missing-prompt fix line carries -- a
# minimal role prompt, pinned by its markdown heading.
_MINIMAL_ROLE_PROMPT = "## Coder\nYou write and modify code."


def _default_resolve_role(name: str) -> Dict[str, str]:
    """The default ``resolve_role``: the real :func:`anvilkit.pi.pirole.resolve`
    with placeholder model ids.

    ``pirole.resolve`` only validates the role name, and its ``prompt_path``
    is ``.pi/roles/<name>.md`` regardless of the ids, so the two ids the
    real signature requires can be placeholders here; the command (behaviour
    18) wraps the real ids around the same seam.
    """
    return pirole.resolve(name, "placeholder", "placeholder")


def check_role_prompt(
    repo_path: str,
    resolve_role: Callable[[str], Dict[str, str]] = _default_resolve_role,
) -> "LayerResult":
    """Layer 4: is the coder role's prompt file present in the target repo?

    A plain read-only filesystem check, over no runner. The path is derived,
    never spelled: ``repo_path`` joined with the
    ``resolve_role("coder")["prompt_path"]`` the injected seam returns
    (default a closure over the real :func:`anvilkit.pi.pirole.resolve`). An
    existing non-empty file passes, the detail carrying the absolute joined
    path; a missing path fails saying it is missing, the fix line carrying
    the minimal content to write; an empty or whitespace-only file fails
    saying it is empty -- a detail distinct from the missing one; a
    directory at the path fails saying it is not a file. This check never
    creates, modifies, deletes or renames anything: it diagnoses and prints
    (issue 83).
    """
    prompt_path = Path(repo_path) / resolve_role("coder")["prompt_path"]
    absolute = os.path.abspath(str(prompt_path))
    if not prompt_path.exists():
        return LayerResult(
            name="role-prompt",
            ok=STATE_FAILED,
            detail="role prompt missing at %s" % absolute,
            fix_lines=(
                ("create %s with at least:\n%s" % (absolute, _MINIMAL_ROLE_PROMPT)),
            ),
        )
    if prompt_path.is_dir():
        return LayerResult(
            name="role-prompt",
            ok=STATE_FAILED,
            detail="not a file at %s (a directory is there)" % absolute,
        )
    if not prompt_path.read_bytes().strip():
        return LayerResult(
            name="role-prompt",
            ok=STATE_FAILED,
            detail="role prompt is empty at %s" % absolute,
        )
    return LayerResult(
        name="role-prompt",
        ok=STATE_OK,
        detail="role prompt present at %s" % absolute,
    )


# The UTC timestamp :func:`new_session_id` stamps into each id
# (behaviour 14 of ``plans/smoke-test.md``): second resolution, compact,
# and alphanumeric-only, so the id's start and end characters are always
# letters or numbers no matter what the random suffix contributes.
_SESSION_ID_STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
# The random half of the id: 16 hex characters from the CSPRNG, which is
# what makes two calls differ even within the same tick -- the timestamp
# alone only guarantees freshness to the second.
_SESSION_ID_SUFFIX_BYTES = 8


def new_session_id() -> str:
    """Mint a fresh session id for one smoke-test invocation.

    Returns ``smoke-<UTC timestamp>-<random suffix>``: the plan's pinned
    ``smoke-`` prefix, a UTC timestamp at second resolution
    (:data:`_SESSION_ID_STAMP_FORMAT`), and a 16-hex-character suffix from
    :func:`secrets.token_hex`. Every character is in Pi's session-id body
    set (letters, numbers, ``.``, ``_``, ``-``) and the id starts and ends
    with a letter or number, so the real
    :func:`anvilkit.pi.pirole.role_argv` validation never rejects one;
    the random suffix makes two calls differ even when they land in the
    same tick, so no old session is ever resumed.
    """
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        _SESSION_ID_STAMP_FORMAT
    )
    return "smoke-" + stamp + "-" + secrets.token_hex(_SESSION_ID_SUFFIX_BYTES)


def _default_coder_run_resolve_role(name: str) -> Dict[str, str]:
    """The default ``resolve_role`` for :func:`check_coder_run`.

    The real :func:`anvilkit.pi.pirole.resolve` with the test-suite's
    placeholder model ids: the coder role runs on the local tier, so its
    ``model_id`` is the first id, and its ``prompt_path`` is id-independent,
    so the ids only pin the ``--model`` token the driver composes.
    """
    return pirole.resolve(name, "coder-model", "frontier-model")


def check_coder_run(
    runner: Callable[[Dict[str, Any]], Dict[str, Any]],
    repo_path: str,
    tag: str,
    task: str,
    earlier_layers_ok: bool = True,
    resolve_role: Callable[[str], Dict[str, str]] = _default_coder_run_resolve_role,
) -> "LayerResult":
    """Layer 5: the real coder run (behaviour 15 of ``plans/smoke-test.md``).

    ``runner`` is the same injected seam ``pidriver.run_role`` takes (one
    invocation dict in, the six-key result dict out), forwarded to the real
    driver unchanged -- never wrapped or mocked, so the driver's own
    ``DriverError`` rule (non-zero exit with empty stdout) is genuinely hit.
    ``repo_path`` and ``tag`` are forwarded to ``run_role`` unchanged;
    ``task`` is the trivial one-line instruction. The session id is a fresh
    :func:`new_session_id` product, so no old session is ever resumed. The
    layer is named ``"coder-run"``.

    When ``earlier_layers_ok`` is ``False`` the layer is
    :data:`STATE_SKIPPED` -- never passed, never failed -- and the runner is
    never invoked. Otherwise the check calls the real
    :func:`anvilkit.pi.pidriver.run_role` with the definition from
    ``resolve_role("coder")`` (default a closure over the real
    :func:`anvilkit.pi.pirole.resolve`), and the verdict is on the stream
    only, never on stderr or model content: it passes when ``exit_code`` is
    0, ``timed_out`` is ``False`` and :func:`anvilkit.pi.pievents.parse` of
    the stdout yields at least one record. Each failing condition names
    itself in its own distinct detail -- a non-zero exit names the exit code,
    a timed-out run names the timeout, an empty stream names the stream --
    and a ``DriverError`` raised by the driver fails the layer with the
    exception's message, so no traceback ever escapes.
    """
    if not earlier_layers_ok:
        return LayerResult(
            name="coder-run",
            ok=STATE_SKIPPED,
            detail="skipped: an earlier layer did not pass",
        )
    definition = resolve_role("coder")
    session_id = new_session_id()
    try:
        result = pidriver.run_role(
            definition,
            repo_path,
            tag,
            session_id,
            task,
            runner,
        )
    except pidriver.DriverError as exc:
        return LayerResult(
            name="coder-run",
            ok=STATE_FAILED,
            detail=str(exc),
        )
    if result["exit_code"] != 0:
        return LayerResult(
            name="coder-run",
            ok=STATE_FAILED,
            detail="coder run exited with code %s" % result["exit_code"],
        )
    if result["timed_out"] is not False:
        return LayerResult(
            name="coder-run",
            ok=STATE_FAILED,
            detail="coder run hit the timeout budget",
        )
    events = pievents.parse(result["stdout"])["events"]
    if len(events) < 1:
        return LayerResult(
            name="coder-run",
            ok=STATE_FAILED,
            detail="coder run produced no event stream",
        )
    return LayerResult(
        name="coder-run",
        ok=STATE_OK,
        detail="coder run completed: %d event record(s)" % len(events),
    )


def check_bad_image_tag(
    runner: Callable[[Dict[str, Any]], Dict[str, Any]],
    repo_path: str,
    tag: str,
    task: str,
    resolve_role: Callable[[str], Dict[str, str]] = _default_coder_run_resolve_role,
) -> "LayerResult":
    """The failure-paths layer's bad-image-tag sub-check (behaviour 16 of
    ``plans/smoke-test.md``).

    ``runner`` is the same injected seam ``pidriver.run_role`` takes (one
    invocation dict in, the six-key result dict out), forwarded to the real
    driver unchanged -- never wrapped or mocked, so the driver's own
    ``DriverError`` rule (non-zero exit with empty stdout) is genuinely hit.
    ``tag`` is an image tag no image matches, so the docker daemon refuses
    the start and the driver raises; ``repo_path`` and ``task`` are forwarded
    to ``run_role`` unchanged. The session id is a fresh
    :func:`new_session_id` product, and the definition comes from
    ``resolve_role("coder")`` with the behaviour-15 default seam -- its
    placeholder model ids mean no real model is ever needed, so this runs on
    a GPU-less host. The layer is named ``"bad-image-tag"``.

    When the driver's ``DriverError`` fires, the failure path is proved and
    the layer PASSES, its detail naming the ``DriverError`` and carrying the
    exception's message verbatim (which names the bad tag and the daemon
    stderr). When ``run_role`` returns instead -- exit 0 with or without a
    stream -- the failure path did not fire and the layer FAILS saying so,
    the opposite verdict of :func:`check_coder_run`, whose ``DriverError``
    is a failure.
    """
    definition = resolve_role("coder")
    session_id = new_session_id()
    try:
        result = pidriver.run_role(
            definition,
            repo_path,
            tag,
            session_id,
            task,
            runner,
        )
    except pidriver.DriverError as exc:
        return LayerResult(
            name="bad-image-tag",
            ok=STATE_OK,
            detail="DriverError fired as expected: %s" % exc,
        )
    return LayerResult(
        name="bad-image-tag",
        ok=STATE_FAILED,
        detail="the failure path did not fire: run returned with exit code %s"
        % result["exit_code"],
    )
