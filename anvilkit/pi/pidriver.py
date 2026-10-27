"""Single-role run driver (``plans/pi-phase6-single-role.md``, behaviour 9).

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

One exception type: ``DriverError`` (behaviours 12-13 will raise it; none is
raised yet in this cycle).
"""

from typing import Any, Callable, Dict, Optional

from anvilkit.pi import pirole
from anvilkit.pi import pisandbox

# The wall-clock budget handed to the runner when the caller does not name
# one: a full role run must survive a long local-model turn, and the budget
# is a kill switch, not an expectation.
_DEFAULT_TIMEOUT_S = 900.0


class DriverError(Exception):
    """A run the driver could not carry out.

    A single exception type covers every driver failure, so callers need
    only one ``except`` clause. The container-start-failure rule (non-zero
    exit with empty stdout, behaviour 12) and the missing-prompt-file rule
    (behaviour 13) will raise it; it is distinct from ``pirole.RoleError``,
    which owns everything decided before the container starts.
    """


def run_role(
    definition: Dict[str, str],
    repo_path: str,
    tag: str,
    session_id: str,
    task: str,
    runner: Callable[[Dict[str, Any]], Dict[str, Any]],
    env: Optional[Dict[str, str]] = None,
    timeout_s: Optional[float] = None,
) -> Dict[str, Any]:
    """Run one role inside the sandbox container and return the runner's result.

    Composes ``pisandbox.run_argv(repo_path, tag, env=env)`` (the container
    command, ending at the image tag) with
    ``pirole.role_argv(definition, session_id, task)`` (the pi invocation,
    beginning with the single ``pi`` token) so the tag sits at the junction
    immediately before ``pi``. The runner is invoked exactly once with an
    invocation dict carrying ``argv``, ``cwd`` (the repo path), ``stdin``
    (``/dev/null``), ``timeout_s`` (the caller's budget or the driver's
    default) and, only when a mapping was passed, ``env`` - and the runner's
    six-key result dict is returned verbatim.

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
        timeout_s: optional wall-clock budget for the run; the driver's
            default applies when absent.

    Returns:
        Dict[str, Any]: the runner's six-key result dict, unmodified.

    Raises:
        SandboxError: from ``pisandbox.run_argv`` on a bad repo path, tag or
            env name.
        RoleError: from ``pirole.role_argv`` on an invalid session id or an
            empty definition field.
    """
    container_argv = pisandbox.run_argv(repo_path, tag, env=env)
    role_argv = pirole.role_argv(definition, session_id, task)
    invocation: Dict[str, Any] = {
        "argv": container_argv + role_argv,
        "cwd": repo_path,
        "stdin": "/dev/null",
        "timeout_s": _DEFAULT_TIMEOUT_S if timeout_s is None else float(timeout_s),
    }
    if env is not None:
        invocation["env"] = env
    return runner(invocation)
