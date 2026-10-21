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
from anvilkit import yamlio  # noqa: E402

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


# ---------------------------------------------------------------------------
# pi-bakeoff Compose service (behaviour 3 of plans/pi-phase1b-docker.md).
#
# The service does not exist yet; until the coder adds it, every test below
# that touches the service fails with the explicit message
# "service 'pi-bakeoff' not defined in docker-compose.yml" -- never from a
# bare KeyError. The regression guard tests are green already: they pin the
# parts of the file the green step must not clobber.
#
# Pinned compose forms (the coder implements exactly these):
#   build        the dict form {context: ".", dockerfile: "docker/Dockerfile.bakeoff"}
#   environment  a list of "KEY=value" strings, as llama-swap already uses
#   volumes      long object form {type, source, target} for every entry
# ---------------------------------------------------------------------------

COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
BAKEOFF_SERVICE = "pi-bakeoff"
# The string build form is unbuildable: a string whose path names a
# Dockerfile makes the build context the Dockerfile's own directory
# (docker/), and docker/Dockerfile.bakeoff COPYs anvilkit/, which exists
# only at the repo root. The dict form puts the context at the repo root
# and addresses the Dockerfile relative to it.
BAKEOFF_BUILD = {
    "context": ".",
    "dockerfile": "docker/Dockerfile.bakeoff",
}
AGENT_HOME_TARGET = "/home/bakeoff/.pi/agent"
RESULTS_TARGET = "/workspace/results"
GATEWAY_ENV_VARS = ("PI_GATEWAY_HOST=llama-swap", "PI_GATEWAY_PORT=8080")
LLM_NETWORK = "llm-network"
CODER_SERVICES = ("coder_qdrant", "llama-swap")


class BakeoffServiceCase(unittest.TestCase):
    """Shared access to ``docker-compose.yml`` via ``anvilkit.yamlio``."""

    @property
    def data(self):
        try:
            return yamlio.load(COMPOSE_FILE)
        except yamlio.YamlError as exc:
            self.fail("could not parse docker-compose.yml: {}".format(exc))

    @property
    def services(self):
        services = self.data.get("services")
        self.assertIsInstance(
            services, dict, "docker-compose.yml has no top-level 'services:'"
        )
        return services

    @property
    def service(self):
        if BAKEOFF_SERVICE not in self.services:
            self.fail(
                "service '{}' not defined in docker-compose.yml".format(
                    BAKEOFF_SERVICE
                )
            )
        return self.services[BAKEOFF_SERVICE]

    def volume_entries(self):
        """The pi-bakeoff service's volumes as a list of long-form dicts.

        The long object form is pinned: a short string form here means the
        compose file does not implement the pinned form and must fail.
        """
        entries = self.service.get("volumes") or []
        for entry in entries:
            if not isinstance(entry, dict):
                self.fail(
                    "pi-bakeoff volume entry {!r} is not the pinned long "
                    "object form {{type, source, target}}".format(entry)
                )
        return list(entries)

    def top_level_volumes(self):
        return self.data.get("volumes") or {}


class BakeoffServiceDefinitionTests(BakeoffServiceCase):
    """The shape the pi-bakeoff service must carry."""

    def test_service_is_defined(self):
        self.assertIn(
            BAKEOFF_SERVICE,
            self.services,
            "service '{}' not defined in docker-compose.yml".format(
                BAKEOFF_SERVICE
            ),
        )

    def test_build_is_the_bakeoff_dockerfile(self):
        self.assertEqual(
            self.service.get("build"),
            BAKEOFF_BUILD,
            "pi-bakeoff must build from the dict form "
            "{{context: '.', dockerfile: 'docker/Dockerfile.bakeoff'}} "
            "(context at the repo root; a string build form would make "
            "docker/ the context and break the COPY anvilkit/)".format(),
        )

    def test_service_joins_the_llm_network(self):
        networks = self.service.get("networks")
        self.assertIsInstance(
            networks, list, "pi-bakeoff networks must be a list"
        )
        self.assertIn(LLM_NETWORK, networks)

    def test_profiles_is_exactly_bakeoff(self):
        self.assertEqual(
            self.service.get("profiles"),
            ["bakeoff"],
            "pi-bakeoff must carry exactly profiles: [\"bakeoff\"]",
        )

    def test_coder_profile_does_not_start_the_service(self):
        self.assertNotIn(
            "coder",
            self.service.get("profiles") or [],
            "pi-bakeoff must not be started by --profile coder",
        )

    def test_gateway_host_and_port_come_from_environment(self):
        env = self.service.get("environment")
        self.assertIsInstance(
            env,
            list,
            "pi-bakeoff environment must be the list of KEY=value strings, "
            "as llama-swap already uses",
        )
        for var in GATEWAY_ENV_VARS:
            self.assertIn(
                var,
                env,
                "pi-bakeoff environment must carry {!r} (in-network "
                "llama-swap address, pinned so the run driver can read it)".format(var),
            )

    def test_agent_home_is_a_named_volume(self):
        top = self.top_level_volumes()
        matches = [
            e
            for e in self.volume_entries()
            if e.get("target") == AGENT_HOME_TARGET
        ]
        self.assertTrue(
            matches,
            "pi-bakeoff must mount a volume at the container agent home "
            "{!r}".format(AGENT_HOME_TARGET),
        )
        entry = matches[0]
        self.assertEqual(
            entry.get("type"),
            "volume",
            "the agent-home mount at {!r} must be a named volume, "
            "got: {!r}".format(AGENT_HOME_TARGET, entry),
        )
        source = entry.get("source")
        self.assertIn(
            source,
            top,
            "named volume source {!r} must be declared in the top-level "
            "'volumes:' of docker-compose.yml (that is what makes it "
            "named, not a bind)".format(source),
        )

    def test_results_is_a_relative_bind_mount(self):
        top = self.top_level_volumes()
        matches = [
            e for e in self.volume_entries() if e.get("target") == RESULTS_TARGET
        ]
        self.assertTrue(
            matches,
            "pi-bakeoff must bind-mount results at {!r}".format(RESULTS_TARGET),
        )
        entry = matches[0]
        self.assertEqual(
            entry.get("type"),
            "bind",
            "the results mount at {!r} must be a bind, got: "
            "{!r}".format(RESULTS_TARGET, entry),
        )
        source = entry.get("source")
        self.assertTrue(
            isinstance(source, str) and source.startswith("./"),
            "the results bind source must be a repo-root relative path "
            "starting with './', got: {!r}".format(source),
        )
        self.assertNotIn(
            source,
            top,
            "the results bind source {!r} must not also be declared in "
            "the top-level 'volumes:'".format(source),
        )


# ---------------------------------------------------------------------------
# pi-bakeoff entrypoint and compose wiring (behaviour 8 of
# plans/pi-phase1b-docker.md).
#
# The in-container entrypoint is `python3 -m anvilkit.pibakeoff` (behaviour 8
# of the plan: "it reads PI_GATEWAY_HOST/PI_GATEWAY_PORT from the
# environment ... the model id and context window from the read-only mounted
# config.yaml via anvilkit.config.read_models ... it runs run_all against
# /workspace/results and exits 0 when done"). For that to work the service
# must pin `command` to the module and bind-mount the llama-swap config
# read-only at /app/config.yaml so `read_models` can resolve the coder model.
#
#
# The token must be `python3`, not `python`: the image installs only
# the distro python3, so bare `python` is not on PATH, and the node base
# image's entrypoint prepends `node` to any command whose first token is
# not a resolvable system command - which is what made the first host run
# die with "Cannot find module '/workspace/python'" (behaviour 9).
#
# Until the coder adds both, every test below fails with the explicit
# message naming the missing key - never a bare KeyError.
# ---------------------------------------------------------------------------

BAKEOFF_COMMAND = ["python3", "-m", "anvilkit.pibakeoff"]
CONFIG_BIND_TARGET = "/app/config.yaml"
CONFIG_BIND_SOURCE = "./config.yaml"


class BakeoffEntrypointWiringTests(BakeoffServiceCase):
    """Behaviour 8: the service's command and its read-only config mount."""

    def test_command_runs_the_pibakeoff_module(self):
        self.assertEqual(
            self.service.get("command"),
            BAKEOFF_COMMAND,
            "pi-bakeoff must set command: {} so `docker compose run` "
            "drives the in-container driver (behaviour 8); a missing or "
            "different command means the operator must hand it one, which "
            "is what the pre-behaviour-8 recipe did".format(BAKEOFF_COMMAND),
        )

    def test_config_yaml_is_bind_mounted_read_only_at_app_config(self):
        entries = [
            e
            for e in self.volume_entries()
            if e.get("target") == CONFIG_BIND_TARGET
        ]
        self.assertTrue(
            entries,
            "pi-bakeoff must bind-mount config.yaml at {!r} so "
            "anvilkit.config.read_models can resolve the coder model "
            "(behaviour 8)".format(CONFIG_BIND_TARGET),
        )
        entry = entries[0]
        self.assertEqual(
            entry.get("type"),
            "bind",
            "the config mount at {!r} must be a bind (llama-swap's "
            "read-only config), got: {!r}".format(CONFIG_BIND_TARGET, entry),
        )
        self.assertEqual(
            entry.get("source"),
            CONFIG_BIND_SOURCE,
            "the config bind source must be the repo-root {!r} (the "
            "llama-swap config Anvil reads), got: "
            "{!r}".format(CONFIG_BIND_SOURCE, entry.get("source")),
        )
        # The pin: read_only is exactly True. `main` must only read the
        # config, never write it back - a read-only bind enforces that.
        self.assertIs(
            entry.get("read_only"),
            True,
            "the config bind at {!r} must be read-only (read_only: true); "
            "got: {!r}".format(CONFIG_BIND_TARGET, entry),
        )


class BakeoffServiceAbsenceTests(BakeoffServiceCase):
    """What the pi-bakeoff service must NOT mount (asserted by absence)."""

    def test_no_docker_socket_is_mounted(self):
        for entry in self.volume_entries():
            source = str(entry.get("source") or "")
            self.assertNotIn(
                "docker.sock",
                source,
                "pi-bakeoff must not mount the Docker socket; found "
                "source {!r}".format(source),
            )

    def test_no_host_pi_directory_is_mounted(self):
        top = self.top_level_volumes()
        for entry in self.volume_entries():
            source = str(entry.get("source") or "")
            if source in top:
                continue  # named volume: its name is opaque, not a host path
            components = [c for c in source.split("/") if c]
            self.assertNotIn(
                ".pi",
                components,
                "pi-bakeoff must not bind a host .pi path (credentials, "
                "sessions); found source {!r}".format(source),
            )


class BakeoffRegressionGuardTests(BakeoffServiceCase):
    """Adding pi-bakeoff must not clobber what is already in the file."""

    def test_coder_services_keep_the_coder_profile(self):
        for name in CODER_SERVICES:
            svc = self.services.get(name)
            self.assertIsInstance(
                svc,
                dict,
                "existing service '{}' is missing from "
                "docker-compose.yml".format(name),
            )
            self.assertEqual(
                svc.get("profiles"),
                ["coder"],
                "service '{}' must still carry exactly profiles: "
                "[\"coder\"]".format(name),
            )

    def test_llm_network_keeps_its_name(self):
        networks = self.data.get("networks") or {}
        self.assertEqual(
            (networks.get(LLM_NETWORK) or {}).get("name"),
            LLM_NETWORK,
            "networks.{} must keep name: {}".format(LLM_NETWORK, LLM_NETWORK),
        )


if __name__ == "__main__":
    unittest.main()
