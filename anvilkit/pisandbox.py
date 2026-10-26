"""Sandbox image argv builders - one job: turn inputs into ``docker`` command lines.

The sandbox image is the container the coding agent runs inside. This
module is the single place that decides what the ``docker build`` and
``docker run`` argument vectors for it look like, so the driver that
executes them can ``subprocess`` without re-deriving token order. It
builds and does not execute: no ``subprocess`` call lives here.

Builders return a ``List[str]``, never a string: the list goes straight
to ``subprocess`` with no shell, so no token can be re-parsed and no
quoting rules need to be obeyed.

``build_argv`` builds the image build, with the context at the repo root
never the Dockerfile's directory. ``run_argv`` builds the container run
and ends at the image tag - the ``pi`` invocation itself (model, prompt,
tools) is the driver's job, not part of this argv. The optional
env mapping is an allowlist: exactly three names may be passed in, and a
name that looks like a credential is refused before it reaches the
container, where every process inside can read any variable passed in.
"""

from pathlib import Path
from typing import Dict, List, Optional


class SandboxError(Exception):
    """Any refusal to build a sandbox build or run argv.

    A single exception type covers every invalid input - an empty tag, an
    empty or relative ``repo_path``, a ``.pi`` component in the repo path,
    and an env name outside the allowlist or one that looks like a
    credential - so callers need only one ``except`` clause.
    """


# Pinned names; they must not drift from docker/Dockerfile.sandbox (the
# ``sandbox`` user at uid 1001, the container-local agent home), from the
# ``sandbox-internal`` network declared in docker-compose.yml, and from
# the named volume that keeps the agent home stable across runs.
_WORKSPACE = "/workspace"
_AGENT_HOME = "/home/sandbox/.pi/agent"
_NAMED_VOLUME = "sandbox-agent"
_INTERNAL_NETWORK = "sandbox-internal"
_IMAGE_UID = "1001"
_DOCKERFILE = "docker/Dockerfile.sandbox"

# Exactly these names may be passed into the container, each for a stated
# reason - the gateway pair the in-network sandbox needs to reach
# llama-swap, and the agent directory that points Pi at the
# container-local home.
_ALLOWED_ENV_NAMES = (
    "PI_GATEWAY_HOST",
    "PI_GATEWAY_PORT",
    "PI_CODING_AGENT_DIR",
)
_CREDENTIAL_MARKERS = ("TOKEN", "KEY", "SECRET")


def _validate_tag(tag: str) -> None:
    """Raise if the image tag is empty or whitespace-only.

    Raises:
        SandboxError: ``tag`` is empty or whitespace-only.
    """
    if not tag.strip():
        raise SandboxError("tag must not be empty")


def _validate_repo_path(repo_path: str) -> None:
    """Raise if the host repo path is empty, relative, or needs ``.pi``.

    A ``.pi`` path component means a run that appears to need the host
    agent home, which is misconfigured and refused by name; ``.pi`` only
    as a fragment of a longer component (e.g. ``pictures``) is fine, so
    the check is component-based, never a substring match.

    Raises:
        SandboxError: ``repo_path`` is empty, not absolute, or has a
            ``.pi`` path component.
    """
    if not repo_path:
        raise SandboxError("repo_path must not be empty")
    if not Path(repo_path).is_absolute():
        raise SandboxError("repo_path must be an absolute path")
    if ".pi" in Path(repo_path).parts:
        raise SandboxError(
            "repo_path %s has a .pi component; a run that appears to need "
            "the host agent home is misconfigured" % repo_path
        )


def _env_tokens(env: Dict[str, str]) -> List[str]:
    """Convert the allowlisted env mapping into ``-e`` token pairs.

    Each name becomes exactly two tokens, ``-e`` then ``NAME=VALUE``. A
    name containing a credential marker is refused with the credential
    reason - values passed in are readable by every process inside -
    before the allowlist is applied, so it cannot be waved through as a
    generic refusal.

    Raises:
        SandboxError: an env name looks like a credential, or is not one
            of the three allowlisted names.
    """
    tokens: List[str] = []
    for name, value in env.items():
        if any(marker in name for marker in _CREDENTIAL_MARKERS):
            raise SandboxError(
                "env name %s looks like a credential (values passed into "
                "the container are readable by every process inside); only "
                "%s may be passed"
                % (name, ", ".join(_ALLOWED_ENV_NAMES))
            )
        if name not in _ALLOWED_ENV_NAMES:
            raise SandboxError(
                "env name %s is not allowed; only %s may be passed"
                % (name, ", ".join(_ALLOWED_ENV_NAMES))
            )
        tokens.extend(["-e", name + "=" + value])
    return tokens


def build_argv(tag: str) -> List[str]:
    """Build the argv for the sandbox image build.

    The context is the repo root (``.``), never the Dockerfile's
    directory, so the build sees the same tree an operator would.

    Raises:
        SandboxError: ``tag`` is empty or whitespace-only.
    """
    _validate_tag(tag)
    return ["docker", "build", "-t", tag, "-f", _DOCKERFILE, "."]


def run_argv(
    repo_path: str,
    tag: str,
    env: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Build the argv for the sandbox container run.

    The host repo is bound at ``/workspace``; the container-local agent
    home is the named volume ``sandbox-agent``, never a host bind, so
    nothing in the host's ``~/.pi`` can be reached. The container rides
    only the internal network, runs as the image's non-root uid, drops
    all capabilities, and may not gain privileges. An env mapping adds
    one ``-e`` pair per allowlisted name. The argv ends at the image tag;
    the ``pi`` invocation itself is the driver's job, not part of this argv.

    Raises:
        SandboxError: ``repo_path`` is empty, not absolute, or has a
            ``.pi`` component; ``tag`` is empty or whitespace-only; or an
            env name is outside the allowlist or looks like a credential.
    """
    _validate_repo_path(repo_path)
    _validate_tag(tag)
    tokens = [
        "docker",
        "run",
        "--rm",
        "-v",
        repo_path + ":" + _WORKSPACE,
        "-v",
        _NAMED_VOLUME + ":" + _AGENT_HOME,
        "--network",
        _INTERNAL_NETWORK,
        "--user",
        _IMAGE_UID,
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
    ]
    tokens.extend(_env_tokens(env if env is not None else {}))
    tokens.append(tag)
    return tokens
