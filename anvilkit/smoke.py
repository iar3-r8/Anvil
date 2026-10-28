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
compose creates the network.

The four pinned names -- the agent volume, the internal network, the image
uid and the agent home -- are adopted as module-level constants from
``anvilkit.pi.pisandbox`` (behaviour 3), so this module never re-spells them
as literals.
"""

import dataclasses
from typing import Callable, Sequence, Tuple

from anvilkit.pi import pisandbox

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
