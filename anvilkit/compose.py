"""Driving ``docker compose`` and the container runtime.

Why subprocess rather than the Docker SDK for Python: Compose v2 is a Go CLI
plugin, and its file parsing, profile resolution and service dependency ordering
are not part of the Engine API the SDK wraps. ``up``/``build``/``restart``/
``logs``/``down`` therefore have to invoke the CLI regardless. Using the SDK for
only the container sweep would add a dependency, a second mocking strategy in the
tests, and a way for ``doctor`` to report a daemon the CLI cannot actually reach
(rootless setups, docker contexts, ``DOCKER_HOST``). One seam keeps the diagnosis
honest.

Constraints this module holds to:

* argv is a **list**, never a string, so no value can be re-split or interpreted
  by a shell;
* the orphan sweep parses the container list in Python, so an empty list is a
  no-op rather than a dependency on GNU ``xargs -r``;
* exit codes are returned, never raised as a process abort, so the CLI decides
  what a failure means;
* ``dry_run`` prints every command without executing any of it.
"""

import subprocess
from typing import Callable, List, Optional, Sequence, Union
from pathlib import Path

PathLike = Union[str, Path]

DEFAULT_PROFILE = "coder"

# llama-swap spawns on-demand vLLM containers under this name prefix.
ORPHAN_NAME_FILTER = "name=vllm-"

_DOCKER = "docker"


class ComposeError(Exception):
    """The container tooling is unusable - typically ``docker`` is not installed."""


class Compose:
    """A thin, testable wrapper around the ``docker compose`` CLI."""

    def __init__(
        self,
        project_dir: PathLike,
        profile: str = DEFAULT_PROFILE,
        dry_run: bool = False,
        echo: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.project_dir = str(project_dir)
        self.profile = profile
        self.dry_run = dry_run
        self._echo = echo

    def up(self, extra_args: Optional[Sequence[str]] = None) -> int:
        """Start the stack detached."""
        return self._compose(["up", "-d"], extra_args)

    def build(self, extra_args: Optional[Sequence[str]] = None) -> int:
        return self._compose(["build"], extra_args)

    def restart(self, extra_args: Optional[Sequence[str]] = None) -> int:
        return self._compose(["restart"], extra_args)

    def logs(
        self, follow: bool = True, extra_args: Optional[Sequence[str]] = None
    ) -> int:
        return self._compose(["logs", "-f"] if follow else ["logs"], extra_args)

    def ps(self, extra_args: Optional[Sequence[str]] = None) -> int:
        """List services.

        Deliberately profile-free, so ``status`` reports every container rather
        than only those in the active profile.
        """
        return self._run([_DOCKER, "compose", "ps"] + list(extra_args or []))

    def down(
        self,
        extra_args: Optional[Sequence[str]] = None,
        purge_orphans: bool = True,
    ) -> int:
        """Stop the stack and, by default, sweep up orphaned vLLM containers.

        The sweep is skipped when compose itself failed, and its result never
        masks compose's exit code.
        """
        code = self._compose(["down"], extra_args)

        if code == 0 and purge_orphans:
            self.purge_orphans()

        return code

    def purge_orphans(self) -> List[str]:
        """Stop and remove leftover on-demand vLLM containers.

        Best-effort: returns the ids it acted on and never raises, because a
        sweep failure must not mask the result of the command that triggered it.
        """
        listing = [
            _DOCKER,
            "ps",
            "-a",
            "--filter",
            ORPHAN_NAME_FILTER,
            "-q",
        ]

        if self.dry_run:
            self._report(listing)
            return []

        try:
            result = subprocess.run(
                listing, cwd=self.project_dir, capture_output=True, text=True
            )
        except FileNotFoundError:
            return []

        if result.returncode != 0:
            return []

        container_ids = (result.stdout or "").split()
        if not container_ids:
            return []

        # Stop before remove; a failed stop must not prevent the removal attempt.
        self._try(([_DOCKER, "stop"] + container_ids))
        self._try(([_DOCKER, "rm"] + container_ids))

        return container_ids

    def _compose(
        self, action: Sequence[str], extra_args: Optional[Sequence[str]] = None
    ) -> int:
        argv = [_DOCKER, "compose", "--profile", self.profile]
        argv.extend(action)
        argv.extend(extra_args or [])
        return self._run(argv)

    def _run(self, argv: Sequence[str]) -> int:
        if self.dry_run:
            self._report(argv)
            return 0

        try:
            # shell=False: argv stays a list, so no argument is ever re-parsed.
            return subprocess.run(list(argv), cwd=self.project_dir).returncode
        except FileNotFoundError as exc:
            raise ComposeError(
                "Could not run 'docker'. Is Docker installed and on your PATH?"
            ) from exc

    def _try(self, argv: Sequence[str]) -> int:
        """Run a best-effort command, swallowing a missing binary."""
        try:
            return self._run(argv)
        except ComposeError:
            return 1

    def _report(self, argv: Sequence[str]) -> None:
        if self._echo is not None:
            self._echo("would run: {}".format(" ".join(argv)))

    def __repr__(self) -> str:
        return "Compose(project_dir={!r}, profile={!r}, dry_run={!r})".format(
            self.project_dir, self.profile, self.dry_run
        )


def docker_available() -> bool:
    """True when the Docker daemon answers - a ``doctor`` probe."""
    return _probe([_DOCKER, "version", "--format", "{{.Server.Version}}"])


def compose_v2_available() -> bool:
    """True when the Compose v2 plugin is installed.

    v1's separate ``docker-compose`` binary is not accepted: every command here
    uses the ``docker compose`` subcommand form.
    """
    return _probe([_DOCKER, "compose", "version"])


def nvidia_available() -> bool:
    """True when ``nvidia-smi`` runs, indicating usable GPU tooling."""
    return _probe(["nvidia-smi", "--list-gpus"])


def _probe(argv: Sequence[str]) -> bool:
    try:
        result = subprocess.run(list(argv), capture_output=True, text=True)
    except (FileNotFoundError, OSError):
        return False

    return result.returncode == 0
