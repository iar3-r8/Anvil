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
start (the rules are documented on ``run_role``).
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
    """Run one resolved role in the sandbox container and return the runner's result.

    - timeout_s: the caller's budget when given; otherwise the tier-aware
      default (local unbounded, frontier cost kill switch).
    - A non-zero exit with empty stdout is a container start failure and
      raises ``DriverError``; any non-zero exit with output is agent data
      and is returned verbatim.
    - check_prompt_file: a missing prompt file raises ``pirole.RoleError``
      before the runner is invoked.

    Args:
        env: optional env mapping for the container; ``None`` means no ``-e`` tokens.
        timeout_s: optional wall-clock budget; absent means the tier-aware default.
        check_prompt_file: verify the resolved prompt file exists before running.

    Returns:
        Dict[str, Any]: the runner's six-key result dict, unmodified.

    Raises:
        SandboxError: from ``pisandbox.run_argv`` on a bad repo path, tag or env name.
        RoleError: from ``pirole.role_argv`` on an invalid session id or empty field;
            or from the missing-prompt-file check.
        DriverError: when the exit code is non-zero and stdout is empty.
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
