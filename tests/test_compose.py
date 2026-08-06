"""Tests for anvilkit.compose - the docker compose wrapper.

Written before the implementation (TDD step 7).

Replaces ``anvil:195-272``. The contract under test is the **exact argv** handed
to the operating system, because that is the whole observable behaviour of a
subprocess wrapper. ``subprocess.run`` is always patched, so no test contacts a
real Docker daemon.

Why subprocess and not the Docker SDK for Python (decided 2026-08-05): the SDK
wraps the Engine API, and Compose v2 is a Go CLI plugin whose file parsing,
profile resolution and dependency ordering are not exposed there - so ``up`` and
friends must shell out regardless. Using the SDK only for the container sweep
would add a dependency, a second mocking strategy, and a way for ``doctor`` to
disagree with the CLI that actually runs the stack (rootless, contexts,
``DOCKER_HOST``). One seam, one truth.

The orphan cleanup at ``anvil:271`` gets particular attention:

.. code-block:: bash

    docker ps -a --filter "name=vllm-" -q | xargs -r docker stop | xargs -r docker rm || true

``xargs -r`` is a GNU extension; without it, an empty container list makes
``docker stop`` run with no arguments and fail. ``test_no_containers_runs_nothing``
pins the empty case down.
"""

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import compose  # noqa: E402

PROJECT_DIR = "/fake/project"


class Recorder:
    """Records every subprocess.run call and returns canned results."""

    def __init__(self, stdout="", returncode=0, returncodes=None):
        self.calls = []
        self.stdout = stdout
        self.returncode = returncode
        # Optional overrides keyed by a token that appears in the argv.
        self.returncodes = returncodes or {}

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))

        code = self.returncode
        for needle, override in self.returncodes.items():
            if needle in argv:
                code = override
                break

        return subprocess.CompletedProcess(argv, code, stdout=self.stdout)

    @property
    def argvs(self):
        return [argv for argv, _ in self.calls]

    @property
    def first_argv(self):
        return self.argvs[0]

    @property
    def first_kwargs(self):
        return self.calls[0][1]


def runner(**kwargs):
    """Patch subprocess.run with a Recorder, returning (patcher, recorder)."""
    recorder = Recorder(**kwargs)
    return mock.patch("subprocess.run", side_effect=recorder), recorder


class ArgvTests(unittest.TestCase):
    """Each subcommand must produce the argv the bash script produced."""

    def setUp(self):
        self.compose = compose.Compose(project_dir=PROJECT_DIR)

    def _argv_for(self, method, *args, **kwargs):
        patcher, recorder = runner()
        with patcher:
            getattr(self.compose, method)(*args, **kwargs)
        return recorder.first_argv

    def test_up_matches_the_bash_invocation(self):
        self.assertEqual(
            self._argv_for("up"),
            ["docker", "compose", "--profile", "coder", "up", "-d"],
        )

    def test_build_matches_the_bash_invocation(self):
        self.assertEqual(
            self._argv_for("build"),
            ["docker", "compose", "--profile", "coder", "build"],
        )

    def test_restart_matches_the_bash_invocation(self):
        self.assertEqual(
            self._argv_for("restart"),
            ["docker", "compose", "--profile", "coder", "restart"],
        )

    def test_logs_follows_by_default(self):
        self.assertEqual(
            self._argv_for("logs"),
            ["docker", "compose", "--profile", "coder", "logs", "-f"],
        )

    def test_logs_can_omit_follow(self):
        self.assertEqual(
            self._argv_for("logs", follow=False),
            ["docker", "compose", "--profile", "coder", "logs"],
        )

    def test_ps_carries_no_profile_like_the_bash_status_command(self):
        """anvil:211 ran a bare 'docker compose ps' with no --profile."""
        self.assertEqual(self._argv_for("ps"), ["docker", "compose", "ps"])

    def test_down_matches_the_bash_invocation(self):
        patcher, recorder = runner()
        with patcher:
            self.compose.down(purge_orphans=False)

        self.assertEqual(
            recorder.first_argv,
            ["docker", "compose", "--profile", "coder", "down"],
        )

    def test_commands_run_in_the_project_directory(self):
        patcher, recorder = runner()
        with patcher:
            self.compose.up()

        self.assertEqual(recorder.first_kwargs.get("cwd"), PROJECT_DIR)

    def test_profile_is_configurable(self):
        patcher, recorder = runner()
        with patcher:
            compose.Compose(project_dir=PROJECT_DIR, profile="gpu").up()

        self.assertEqual(
            recorder.first_argv,
            ["docker", "compose", "--profile", "gpu", "up", "-d"],
        )


class ExtraArgumentTests(unittest.TestCase):
    """User arguments pass through, as '"$@"' did in bash."""

    def setUp(self):
        self.compose = compose.Compose(project_dir=PROJECT_DIR)

    def _argv_with_extra(self, method, extra, **kwargs):
        patcher, recorder = runner()
        with patcher:
            getattr(self.compose, method)(extra_args=extra, **kwargs)
        return recorder.first_argv

    def test_up_appends_extra_arguments(self):
        self.assertEqual(
            self._argv_with_extra("up", ["--build", "llama-swap"]),
            [
                "docker",
                "compose",
                "--profile",
                "coder",
                "up",
                "-d",
                "--build",
                "llama-swap",
            ],
        )

    def test_logs_appends_service_names_after_the_follow_flag(self):
        self.assertEqual(
            self._argv_with_extra("logs", ["llama-swap"]),
            ["docker", "compose", "--profile", "coder", "logs", "-f", "llama-swap"],
        )

    def test_build_appends_extra_arguments(self):
        self.assertEqual(
            self._argv_with_extra("build", ["--no-cache"]),
            ["docker", "compose", "--profile", "coder", "build", "--no-cache"],
        )

    def test_restart_appends_extra_arguments(self):
        self.assertEqual(
            self._argv_with_extra("restart", ["llama-swap"]),
            ["docker", "compose", "--profile", "coder", "restart", "llama-swap"],
        )

    def test_down_appends_extra_arguments(self):
        self.assertEqual(
            self._argv_with_extra("down", ["--volumes"], purge_orphans=False),
            ["docker", "compose", "--profile", "coder", "down", "--volumes"],
        )

    def test_extra_arguments_are_not_shell_interpreted(self):
        """A list argv means '; rm -rf' is data, not a command separator."""
        argv = self._argv_with_extra("up", ["; rm -rf /"])

        self.assertEqual(argv[-1], "; rm -rf /")

    def test_no_shell_is_used(self):
        patcher, recorder = runner()
        with patcher:
            self.compose.up()

        self.assertNotEqual(recorder.first_kwargs.get("shell"), True)


class ExitCodeTests(unittest.TestCase):
    """Exit codes propagate instead of being swallowed."""

    def setUp(self):
        self.compose = compose.Compose(project_dir=PROJECT_DIR)

    def test_success_returns_zero(self):
        patcher, _ = runner(returncode=0)
        with patcher:
            self.assertEqual(self.compose.up(), 0)

    def test_failure_returns_the_docker_exit_code(self):
        patcher, _ = runner(returncode=17)
        with patcher:
            self.assertEqual(self.compose.up(), 17)

    def test_missing_docker_binary_raises_compose_error(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("docker")):
            with self.assertRaises(compose.ComposeError):
                self.compose.up()

    def test_missing_docker_binary_message_names_docker(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("docker")):
            with self.assertRaises(compose.ComposeError) as ctx:
                self.compose.up()

        self.assertIn("docker", str(ctx.exception).lower())


class OrphanCleanupTests(unittest.TestCase):
    """Regression tests for the 'xargs -r' cleanup at anvil:271."""

    def setUp(self):
        self.compose = compose.Compose(project_dir=PROJECT_DIR)

    def test_lists_orphans_with_the_expected_filter(self):
        patcher, recorder = runner(stdout="")
        with patcher:
            self.compose.purge_orphans()

        self.assertEqual(
            recorder.first_argv,
            ["docker", "ps", "-a", "--filter", "name=vllm-", "-q"],
        )

    def test_orphan_listing_captures_output(self):
        patcher, recorder = runner(stdout="")
        with patcher:
            self.compose.purge_orphans()

        self.assertTrue(recorder.first_kwargs.get("capture_output"))

    def test_no_containers_runs_nothing(self):
        """The empty case the bash version needed 'xargs -r' to survive."""
        patcher, recorder = runner(stdout="")
        with patcher:
            removed = self.compose.purge_orphans()

        self.assertEqual(removed, [])
        self.assertEqual(len(recorder.argvs), 1, "only the listing should run")

    def test_whitespace_only_output_runs_nothing(self):
        patcher, recorder = runner(stdout="\n  \n")
        with patcher:
            removed = self.compose.purge_orphans()

        self.assertEqual(removed, [])
        self.assertEqual(len(recorder.argvs), 1)

    def test_single_container_is_stopped_then_removed(self):
        patcher, recorder = runner(stdout="abc123\n")
        with patcher:
            removed = self.compose.purge_orphans()

        self.assertEqual(removed, ["abc123"])
        self.assertEqual(
            recorder.argvs[1:],
            [
                ["docker", "stop", "abc123"],
                ["docker", "rm", "abc123"],
            ],
        )

    def test_multiple_containers_are_batched_into_one_stop_and_one_rm(self):
        patcher, recorder = runner(stdout="abc123\ndef456\n")
        with patcher:
            removed = self.compose.purge_orphans()

        self.assertEqual(removed, ["abc123", "def456"])
        self.assertEqual(
            recorder.argvs[1:],
            [
                ["docker", "stop", "abc123", "def456"],
                ["docker", "rm", "abc123", "def456"],
            ],
        )

    def test_listing_failure_is_tolerated(self):
        """The bash version ended in '|| true'; cleanup is best-effort."""
        patcher, _ = runner(stdout="", returncode=1)
        with patcher:
            removed = self.compose.purge_orphans()

        self.assertEqual(removed, [])

    def test_stop_failure_does_not_prevent_removal(self):
        patcher, recorder = runner(stdout="abc123\n", returncodes={"stop": 1})
        with patcher:
            self.compose.purge_orphans()

        self.assertIn(["docker", "rm", "abc123"], recorder.argvs)

    def test_missing_docker_during_cleanup_is_tolerated(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("docker")):
            self.assertEqual(self.compose.purge_orphans(), [])


class DownSequenceTests(unittest.TestCase):
    """'down' composes the compose call with the orphan sweep."""

    def setUp(self):
        self.compose = compose.Compose(project_dir=PROJECT_DIR)

    def test_down_purges_orphans_by_default(self):
        patcher, recorder = runner(stdout="abc123\n")
        with patcher:
            self.compose.down()

        self.assertEqual(
            recorder.argvs,
            [
                ["docker", "compose", "--profile", "coder", "down"],
                ["docker", "ps", "-a", "--filter", "name=vllm-", "-q"],
                ["docker", "stop", "abc123"],
                ["docker", "rm", "abc123"],
            ],
        )

    def test_down_can_keep_orphans(self):
        patcher, recorder = runner(stdout="abc123\n")
        with patcher:
            self.compose.down(purge_orphans=False)

        self.assertEqual(len(recorder.argvs), 1)

    def test_down_returns_the_compose_exit_code_not_the_cleanup_one(self):
        patcher, _ = runner(stdout="abc123\n", returncodes={"stop": 3})
        with patcher:
            self.assertEqual(self.compose.down(), 0)

    def test_failed_compose_down_skips_cleanup_like_set_e_did(self):
        patcher, recorder = runner(stdout="abc123\n", returncodes={"down": 5})
        with patcher:
            code = self.compose.down()

        self.assertEqual(code, 5)
        self.assertEqual(len(recorder.argvs), 1)


class DryRunTests(unittest.TestCase):
    """--dry-run must not execute anything."""

    def setUp(self):
        self.compose = compose.Compose(project_dir=PROJECT_DIR, dry_run=True)

    def test_up_executes_nothing(self):
        patcher, recorder = runner()
        with patcher:
            code = self.compose.up()

        self.assertEqual(recorder.argvs, [])
        self.assertEqual(code, 0)

    def test_down_executes_nothing_including_cleanup(self):
        patcher, recorder = runner(stdout="abc123\n")
        with patcher:
            self.compose.down()

        self.assertEqual(recorder.argvs, [])

    def test_purge_orphans_executes_nothing(self):
        patcher, recorder = runner(stdout="abc123\n")
        with patcher:
            self.assertEqual(self.compose.purge_orphans(), [])

        self.assertEqual(recorder.argvs, [])

    def test_dry_run_reports_the_argv_it_would_have_run(self):
        printed = []
        dry = compose.Compose(
            project_dir=PROJECT_DIR, dry_run=True, echo=printed.append
        )

        patcher, _ = runner()
        with patcher:
            dry.up()

        self.assertTrue(any("docker compose" in line for line in printed))


class AvailabilityTests(unittest.TestCase):
    """'doctor' needs to ask whether docker and compose v2 are usable."""

    def test_docker_available_when_version_succeeds(self):
        patcher, recorder = runner(returncode=0)
        with patcher:
            self.assertTrue(compose.docker_available())

        self.assertEqual(recorder.first_argv[:2], ["docker", "version"])

    def test_docker_unavailable_when_version_fails(self):
        patcher, _ = runner(returncode=1)
        with patcher:
            self.assertFalse(compose.docker_available())

    def test_docker_unavailable_when_binary_missing(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("docker")):
            self.assertFalse(compose.docker_available())

    def test_compose_v2_available_when_compose_version_succeeds(self):
        patcher, recorder = runner(
            returncode=0, stdout="Docker Compose version v2.24.0\n"
        )
        with patcher:
            self.assertTrue(compose.compose_v2_available())

        self.assertEqual(recorder.first_argv, ["docker", "compose", "version"])

    def test_compose_v2_unavailable_when_subcommand_missing(self):
        patcher, _ = runner(returncode=125)
        with patcher:
            self.assertFalse(compose.compose_v2_available())

    def test_compose_v2_unavailable_when_binary_missing(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("docker")):
            self.assertFalse(compose.compose_v2_available())

    def test_nvidia_available_when_smi_succeeds(self):
        patcher, recorder = runner(returncode=0, stdout="NVIDIA-SMI 550\n")
        with patcher:
            self.assertTrue(compose.nvidia_available())

        self.assertEqual(recorder.first_argv[0], "nvidia-smi")

    def test_nvidia_unavailable_when_smi_missing(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("nvidia-smi")):
            self.assertFalse(compose.nvidia_available())


if __name__ == "__main__":
    unittest.main()
