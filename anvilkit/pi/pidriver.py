"""Single-role run driver.

One job: compose the sandbox container argv (``pisandbox.run_argv``, which
ends at the image tag) with the role argv (``pirole.role_argv``, which
begins with the single ``pi`` token) and invoke the injected runner exactly
once with the result. The driver acts, never decides: the role definition
arrives already resolved, the token order is owned by the two builders, and
the driver holds no policy of its own.

The runner is an injected callable using the same seam
``anvilkit.pi.pibakeoff`` and ``anvilkit.pi.piapproval`` use: one invocation
dict in (``argv``, ``cwd``, ``stdin``, ``timeout_s``, optionally ``env``),
the six-key result dict out. The production runner is
``pibakeoff.subprocess_runner``; this module takes it as a parameter, so the
driver is testable with no Docker and imports no process-execution module
itself (stdlib only).

One exception type: ``DriverError``, raised when the container could not
start: a non-zero exit with empty stdout means the pi
process never ran, so there is no agent result to report. The
missing-prompt-file rule raises ``pirole.RoleError`` naming
the absolute path instead: it is a role-definition failure decided before
the container starts, not a container-start failure.
"""

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from anvilkit.pi import pirole
from anvilkit.pi import pisandbox

# The default budget for a frontier-tier run when the caller names none:
# a cost kill switch, not an expectation - a long local-model turn must
# never be killed for thinking, which is why the local tier has no budget.
_FRONTIER_KILL_SWITCH_S = 3600.0


class DriverError(Exception):
    """A run the driver could not carry out.

    A single exception type covers every driver failure, so callers need
    only one ``except`` clause. The container-start-failure rule (non-zero
    exit with empty stdout) raises it. The missing-prompt-file rule is
    distinct: it is a role-definition failure decided
    before the container starts, and raises ``pirole.RoleError`` naming the
    absolute path.
    """


def _default_timeout_s(tier: str) -> Optional[float]:
    """The budget for a run the caller did not budget: the local tier runs
    unbounded (``None``), the frontier tier gets the cost kill switch."""
    if tier == "frontier":
        return float(_FRONTIER_KILL_SWITCH_S)
    return None


def run_role(
    definition: Dict[str, str],
    repo_path: str,
    tag: str,
    session_id: str,
    task: str,
    runner: Callable[[Dict[str, Any]], Dict[str, Any]],
    env: Optional[Dict[str, str]] = None,
    timeout_s: Optional[float] = None,
    check_prompt_file: bool = False,
) -> Dict[str, Any]:
    """Run one role inside the sandbox container and return the runner's result.

    Composes ``pisandbox.run_argv(repo_path, tag, env=env)`` (the container
    command, ending at the image tag) with
    ``pirole.role_argv(definition, session_id, task)`` (the pi invocation,
    beginning with the single ``pi`` token) so the tag sits at the junction
    immediately before ``pi``. The runner is invoked exactly once with an
    invocation dict carrying ``argv``, ``cwd`` (the repo path), ``stdin``
    (``/dev/null``), ``timeout_s`` (the caller's budget when given, else
    the tier-aware default: unbounded for the local tier, the frontier
    cost kill switch for the frontier tier) and, only when a mapping was
    passed, ``env``.

    A non-zero exit with **empty** stdout is a container start failure, not
    an agent result: the pi process never ran, so there is no output to
    report, and the driver raises ``DriverError`` naming the image tag and
    quoting the runner's stderr. Any other outcome - including a non-zero
    exit with captured output - is the agent's own data and is returned
    verbatim.

    Args:
        definition: the already-resolved role definition dict from
            ``pirole.resolve``; the driver never calls ``resolve`` itself.
        repo_path: absolute host repo path, handed to ``pisandbox.run_argv``.
        tag: the sandbox image tag, handed to ``pisandbox.run_argv``.
        session_id: the session id, handed to ``pirole.role_argv`` verbatim.
        task: the task text, handed to ``pirole.role_argv`` verbatim.
        runner: the injected process-execution seam; the production runner
            is ``anvilkit.pi.pibakeoff.subprocess_runner``.
        env: optional env mapping for the container (the sandbox allowlist);
            ``None`` means no ``-e`` tokens.
        timeout_s: optional wall-clock budget for the run; when absent the
            tier-aware default applies (unbounded for the local tier, the
            frontier cost kill switch for the frontier tier).
        check_prompt_file: when True, the resolved absolute prompt path
            (``repo_path`` joined with the definition's ``prompt_path``)
            must be an existing file or the driver raises
            ``pirole.RoleError`` naming it, before any argv is composed
            and before the runner is invoked.

    Returns:
        Dict[str, Any]: the runner's six-key result dict, unmodified.

    Raises:
        SandboxError: from ``pisandbox.run_argv`` on a bad repo path, tag or
            env name.
        RoleError: from ``pirole.role_argv`` on an invalid session id or an
            empty definition field.
        DriverError: when the run's exit code is non-zero and its stdout is
            empty - the container start failed, and there is no agent
            result to return.
    """
    if check_prompt_file:
        prompt_file = Path(repo_path) / definition["prompt_path"]
        if not prompt_file.is_file():
            raise pirole.RoleError(
                "role prompt file not found: %s" % str(prompt_file)
            )
    container_argv = pisandbox.run_argv(repo_path, tag, env=env)
    role_argv = pirole.role_argv(definition, session_id, task)
    invocation: Dict[str, Any] = {
        "argv": container_argv + role_argv,
        "cwd": repo_path,
        "stdin": "/dev/null",
        "timeout_s": (
            float(timeout_s)
            if timeout_s is not None
            else _default_timeout_s(definition["tier"])
        ),
    }
    if env is not None:
        invocation["env"] = env
    result: Dict[str, Any] = runner(invocation)
    if result["exit_code"] != 0 and result["stdout"] == "":
        raise DriverError(
            "container start failed for image tag %r; stderr: %s"
            % (tag, result["stderr"])
        )
    return result
