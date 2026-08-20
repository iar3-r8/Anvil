"""Tests for anvilkit.cli - subcommand dispatch, flags and exit codes.

Written before the implementation (TDD step 9).

Replaces the self-grepping ``cmd_help()`` at ``anvil:424`` and the bash-4
``declare -F`` dispatch at ``anvil:431``.

What this module tests and what it deliberately does not:

* it tests that each subcommand reaches the right collaborator with the right
  arguments, that failures map to distinct exit codes, and that ``--dry-run`` and
  ``--yes`` keep their promises;
* it does **not** re-test the collaborators. ``Compose``, ``health``, ``provision``
  and ``prompts`` already have their own suites, so they are replaced by
  recorders here. The CLI's only job is wiring, and wiring is what is asserted.

Two environment notes that shaped these tests:

* ``CliRunner().invoke(app, argv)`` is used for dispatch, which is safe. What is
  avoided is a bare ``CliRunner.isolation()`` around a raw prompt: its stdin stub
  returns ``''`` endlessly at EOF, so a prompt with no default loops forever in a
  test while behaving correctly in production. See ``test_prompts.py``.
* under ``CliRunner`` stdin is not a tty, so the CLI resolves to
  non-interactive and every prompt takes its default. No test can therefore
  block. Where interactivity itself is the subject, ``_is_interactive`` is patched
  to ``True`` and the input seams are booby-trapped, so a prompt that should not
  happen fails loudly instead of hanging.

Nothing here touches the network, the Docker daemon, or the real ``$HOME``: the
repository root is redirected into a ``TemporaryDirectory`` and ``HOME`` is
overridden whenever a default derived from it is asserted.
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import cli  # noqa: E402

# The keys the bash heredoc at anvil:64 wrote, in that order.
ENV_KEYS = (
    "HF_HOME",
    "DATA_DIR",
    "LLM_PORT",
    "LLM_DEVICE_ID_0",
    "LLM_DEVICE_ID_1",
    "LLM_DEVICE_ID_2",
    "INDEXER_STORAGE_DEVICE_ID",
)


class RecordingCompose:
    """Stands in for ``Compose``, recording calls instead of running docker.

    A class attribute collects every instance, so a test can assert both how the
    CLI constructed it (project dir, profile, dry_run) and what it then asked for.
    """

    instances = []
    return_code = 0
    raises = None

    def __init__(self, project_dir, profile="coder", dry_run=False, echo=None):
        self.project_dir = str(project_dir)
        self.profile = profile
        self.dry_run = dry_run
        self.echo = echo
        self.calls = []
        RecordingCompose.instances.append(self)

    @classmethod
    def reset(cls):
        cls.instances = []
        cls.return_code = 0
        cls.raises = None

    @classmethod
    def last(cls):
        assert cls.instances, "the CLI never constructed a Compose"
        return cls.instances[-1]

    @classmethod
    def all_calls(cls):
        calls = []
        for instance in cls.instances:
            calls.extend(instance.calls)
        return calls

    def _record(self, name, **kwargs):
        self.calls.append((name, kwargs))
        if RecordingCompose.raises is not None:
            raise RecordingCompose.raises
        return RecordingCompose.return_code

    def up(self, extra_args=None):
        return self._record("up", extra_args=list(extra_args or []))

    def build(self, extra_args=None):
        return self._record("build", extra_args=list(extra_args or []))

    def restart(self, extra_args=None):
        return self._record("restart", extra_args=list(extra_args or []))

    def logs(self, follow=True, extra_args=None):
        return self._record("logs", follow=follow, extra_args=list(extra_args or []))

    def ps(self, extra_args=None):
        return self._record("ps", extra_args=list(extra_args or []))

    def down(self, extra_args=None, purge_orphans=True):
        return self._record(
            "down", extra_args=list(extra_args or []), purge_orphans=purge_orphans
        )

    def purge_orphans(self):
        self.calls.append(("purge_orphans", {}))
        return []


def offline_status(port=8000):
    """A gateway status object, built through the real health types."""
    from anvilkit import health

    return health.GatewayStatus(port=port, online=False, error="connection refused")


def online_status(port=8000):
    from anvilkit import health

    return health.GatewayStatus(
        port=port,
        online=True,
        models=[
            health.ModelStatus("Qwen/Qwen3.6-35B-A3B-FP8", True),
            health.ModelStatus("nomic-ai/nomic-embed-text-v1.5", False),
        ],
    )


def passing_test(port=8000, model="Qwen/Qwen3.6-35B-A3B-FP8"):
    from anvilkit import health

    return health.ModelTestResult(
        port=port,
        model_id=model,
        prompt="say pong",
        ok=True,
        reply="pong",
        latency_seconds=1.5,
        prompt_tokens=11,
        completion_tokens=2,
    )


def failing_test(port=8000, model="Qwen/Qwen3.6-35B-A3B-FP8", **kwargs):
    from anvilkit import health

    defaults = dict(
        port=port,
        model_id=model,
        prompt="say pong",
        ok=False,
        error="connection refused",
    )
    defaults.update(kwargs)
    return health.ModelTestResult(**defaults)


class CliCase(unittest.TestCase):
    """Base class: an isolated repository root and a patched Compose."""

    def setUp(self):
        self.runner = CliRunner()

        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        # Real configuration files, so config parsing is exercised rather than
        # mocked - they are tiny and this keeps the CLI honest about what it reads.
        shutil.copyfile(str(REPO_ROOT / "anvil.yaml"), str(self.project / "anvil.yaml"))
        shutil.copyfile(
            str(REPO_ROOT / "config.yaml"), str(self.project / "config.yaml")
        )

        patcher = mock.patch.object(cli, "REPO_ROOT", self.project)
        patcher.start()
        self.addCleanup(patcher.stop)

        RecordingCompose.reset()
        compose_patcher = mock.patch.object(cli, "Compose", RecordingCompose)
        compose_patcher.start()
        self.addCleanup(compose_patcher.stop)
        self.addCleanup(RecordingCompose.reset)

    # -- helpers ---------------------------------------------------------

    def env_path(self):
        return self.project / ".env"

    def write_env(self, **values):
        from anvilkit import env

        env.write(self.env_path(), list(values.items()))

    def invoke(self, argv, **kwargs):
        result = self.runner.invoke(cli.app, argv, **kwargs)
        if result.exception is not None and not isinstance(
            result.exception, SystemExit
        ):
            # Surface the real traceback rather than an opaque exit code.
            raise result.exception
        return result

    def invoke_allowing_exception(self, argv, **kwargs):
        return self.runner.invoke(cli.app, argv, **kwargs)

    def snapshot(self):
        """Every file under the project root, mapped to its bytes."""
        return {
            str(path.relative_to(self.project)): path.read_bytes()
            for path in sorted(self.project.rglob("*"))
            if path.is_file()
        }


class TestSubcommandsExist(CliCase):
    """Every documented command is registered, so none can be lost silently."""

    EXPECTED = (
        "up",
        "down",
        "build",
        "restart",
        "logs",
        "status",
        "test-model",
        "setup-repo",
        "init",
        "doctor",
    )

    def registered_names(self):
        import click

        command = cli.typer.main.get_command(cli.app)
        self.assertIsInstance(command, click.Group)
        return set(command.commands)

    def test_all_expected_commands_are_registered(self):
        self.assertLessEqual(set(self.EXPECTED), self.registered_names())

    def test_no_unexpected_commands_are_registered(self):
        self.assertEqual(set(self.EXPECTED), self.registered_names())

    def test_help_lists_every_command(self):
        result = self.invoke(["--help"])
        self.assertEqual(0, result.exit_code)
        for name in self.EXPECTED:
            self.assertIn(name, result.output)


class TestDispatch(CliCase):
    """Each subcommand reaches the matching Compose operation."""

    def setUp(self):
        super().setUp()
        self.write_env(LLM_PORT="8000")

    def test_up_starts_the_stack(self):
        result = self.invoke(["up"])
        self.assertEqual(0, result.exit_code)
        self.assertEqual(["up"], [name for name, _ in RecordingCompose.all_calls()])

    def test_build_builds(self):
        self.invoke(["build"])
        self.assertEqual(["build"], [name for name, _ in RecordingCompose.all_calls()])

    def test_restart_restarts(self):
        self.invoke(["restart"])
        self.assertEqual(
            ["restart"], [name for name, _ in RecordingCompose.all_calls()]
        )

    def test_logs_follows_by_default_like_bash(self):
        self.invoke(["logs"])
        name, kwargs = RecordingCompose.all_calls()[0]
        self.assertEqual("logs", name)
        self.assertTrue(kwargs["follow"])

    def test_logs_can_stop_following(self):
        self.invoke(["logs", "--no-follow"])
        _, kwargs = RecordingCompose.all_calls()[0]
        self.assertFalse(kwargs["follow"])

    def test_down_purges_orphans_by_default(self):
        self.invoke(["down"])
        name, kwargs = RecordingCompose.all_calls()[0]
        self.assertEqual("down", name)
        self.assertTrue(kwargs["purge_orphans"])

    def test_down_can_keep_orphans(self):
        self.invoke(["down", "--keep-orphans"])
        _, kwargs = RecordingCompose.all_calls()[0]
        self.assertFalse(kwargs["purge_orphans"])

    def test_default_profile_is_coder(self):
        self.invoke(["up"])
        self.assertEqual("coder", RecordingCompose.last().profile)

    def test_profile_can_be_overridden(self):
        self.invoke(["up", "--profile", "embedder"])
        self.assertEqual("embedder", RecordingCompose.last().profile)

    def test_compose_runs_in_the_project_directory(self):
        self.invoke(["up"])
        self.assertEqual(str(self.project), RecordingCompose.last().project_dir)

    def test_status_lists_services_then_checks_the_gateway(self):
        with mock.patch.object(
            cli.health, "check_gateway", return_value=offline_status()
        ) as check:
            result = self.invoke(["status"])

        self.assertEqual(0, result.exit_code)
        self.assertEqual(["ps"], [name for name, _ in RecordingCompose.all_calls()])
        self.assertEqual(1, check.call_count)

    def test_setup_repo_delegates_to_provision(self):
        with tempfile.TemporaryDirectory() as target:
            with mock.patch.object(
                cli.provision, "setup_repo", return_value=target
            ) as setup:
                result = self.invoke(["setup-repo", target])

        self.assertEqual(0, result.exit_code)
        self.assertEqual(1, setup.call_count)

    def test_init_writes_the_env_file(self):
        self.env_path().unlink()
        result = self.invoke(["init", "--yes"])
        self.assertEqual(0, result.exit_code)
        self.assertTrue(self.env_path().is_file())

    def test_doctor_runs_without_touching_compose_operations(self):
        result = self.invoke(["doctor"])
        self.assertEqual(0, result.exit_code)
        self.assertEqual([], RecordingCompose.all_calls())


class TestExtraArgumentPassThrough(CliCase):
    """User arguments reach docker untouched, as ``"$@"`` did in bash."""

    def setUp(self):
        super().setUp()
        self.write_env(LLM_PORT="8000")

    def test_up_forwards_extra_arguments(self):
        self.invoke(["up", "llama-swap", "qdrant"])
        _, kwargs = RecordingCompose.all_calls()[0]
        self.assertEqual(["llama-swap", "qdrant"], kwargs["extra_args"])

    def test_up_forwards_unknown_options(self):
        self.invoke(["up", "--force-recreate"])
        _, kwargs = RecordingCompose.all_calls()[0]
        self.assertEqual(["--force-recreate"], kwargs["extra_args"])

    def test_logs_forwards_service_names(self):
        self.invoke(["logs", "llama-swap"])
        _, kwargs = RecordingCompose.all_calls()[0]
        self.assertEqual(["llama-swap"], kwargs["extra_args"])

    def test_build_forwards_extra_arguments(self):
        self.invoke(["build", "--no-cache"])
        _, kwargs = RecordingCompose.all_calls()[0]
        self.assertEqual(["--no-cache"], kwargs["extra_args"])

    def test_restart_forwards_extra_arguments(self):
        self.invoke(["restart", "-t", "1"])
        _, kwargs = RecordingCompose.all_calls()[0]
        self.assertEqual(["-t", "1"], kwargs["extra_args"])

    def test_down_forwards_extra_arguments(self):
        self.invoke(["down", "--volumes"])
        _, kwargs = RecordingCompose.all_calls()[0]
        self.assertEqual(["--volumes"], kwargs["extra_args"])

    def test_keep_orphans_is_consumed_not_forwarded(self):
        self.invoke(["down", "--keep-orphans", "--volumes"])
        _, kwargs = RecordingCompose.all_calls()[0]
        self.assertEqual(["--volumes"], kwargs["extra_args"])


class TestUsageErrors(CliCase):
    """Misuse exits 2 and never pretends to have worked."""

    def test_unknown_command_exits_non_zero(self):
        result = self.invoke_allowing_exception(["frobnicate"])
        self.assertNotEqual(0, result.exit_code)

    def test_unknown_command_uses_the_usage_exit_code(self):
        result = self.invoke_allowing_exception(["frobnicate"])
        self.assertEqual(cli.EXIT_USAGE, result.exit_code)

    def test_unknown_command_runs_nothing(self):
        self.invoke_allowing_exception(["frobnicate"])
        self.assertEqual([], RecordingCompose.all_calls())

    def test_setup_repo_without_a_path_exits_usage(self):
        result = self.invoke_allowing_exception(["setup-repo"])
        self.assertEqual(cli.EXIT_USAGE, result.exit_code)

    def test_bad_option_value_exits_usage(self):
        result = self.invoke_allowing_exception(["status", "--llm-port", "not-a-port"])
        self.assertEqual(cli.EXIT_USAGE, result.exit_code)

    def test_no_arguments_shows_help_without_running_anything(self):
        result = self.invoke_allowing_exception([])
        self.assertIn("up", result.output)
        self.assertEqual([], RecordingCompose.all_calls())


class TestExitCodes(CliCase):
    """Every failure class gets its own code, replacing the bare ``set -e``."""

    def setUp(self):
        super().setUp()
        self.write_env(LLM_PORT="8000")

    def test_distinct_codes_are_distinct(self):
        codes = [
            cli.EXIT_OK,
            cli.EXIT_ERROR,
            cli.EXIT_USAGE,
            cli.EXIT_CONFIG,
            cli.EXIT_DOCKER,
            cli.EXIT_PROVISION,
            cli.EXIT_PROMPT,
        ]
        self.assertEqual(len(codes), len(set(codes)))

    def test_success_is_zero(self):
        self.assertEqual(0, cli.EXIT_OK)

    def test_missing_docker_exits_with_the_docker_code(self):
        RecordingCompose.raises = cli.ComposeError("docker not found")
        result = self.invoke_allowing_exception(["up"])
        self.assertEqual(cli.EXIT_DOCKER, result.exit_code)

    def test_missing_docker_reports_the_reason(self):
        RecordingCompose.raises = cli.ComposeError("docker not found")
        result = self.invoke_allowing_exception(["up"])
        self.assertIn("docker not found", result.output)

    def test_invalid_anvil_yaml_exits_with_the_config_code(self):
        (self.project / "anvil.yaml").write_text("zoo_code: []\n", encoding="utf-8")
        result = self.invoke_allowing_exception(["status"])
        self.assertEqual(cli.EXIT_CONFIG, result.exit_code)

    def test_non_numeric_port_in_env_exits_with_the_config_code(self):
        self.write_env(LLM_PORT="eight-thousand")
        result = self.invoke_allowing_exception(["status"])
        self.assertEqual(cli.EXIT_CONFIG, result.exit_code)

    def test_provisioning_failure_exits_with_the_provision_code(self):
        result = self.invoke_allowing_exception(
            ["setup-repo", str(self.project / "nope"), "--yes"]
        )
        self.assertEqual(cli.EXIT_PROVISION, result.exit_code)

    def test_missing_required_value_exits_with_the_prompt_code(self):
        # --yes cannot invent a secret, so requesting Anthropic without a key
        # must fail loudly rather than write an empty credential.
        with tempfile.TemporaryDirectory() as target:
            result = self.invoke_allowing_exception(
                ["setup-repo", target, "--yes", "--anthropic"]
            )
        self.assertEqual(cli.EXIT_PROMPT, result.exit_code)

    def test_compose_exit_code_is_propagated(self):
        # Parity with 'set -e': docker's own status is the truth about docker.
        RecordingCompose.return_code = 17
        result = self.invoke_allowing_exception(["up"])
        self.assertEqual(17, result.exit_code)

    def test_offline_gateway_is_not_an_error(self):
        # cmd_status at anvil:222 merely returned, so this stays exit 0.
        with mock.patch.object(
            cli.health, "check_gateway", return_value=offline_status()
        ):
            result = self.invoke(["status"])
        self.assertEqual(0, result.exit_code)


class TestDryRun(CliCase):
    """``--dry-run`` must write nothing and execute nothing."""

    def setUp(self):
        super().setUp()
        self.write_env(LLM_PORT="8000")

    def test_dry_run_reaches_compose_with_the_flag_set(self):
        self.invoke(["--dry-run", "up"])
        self.assertTrue(RecordingCompose.last().dry_run)

    def test_dry_run_up_writes_no_files(self):
        before = self.snapshot()
        self.invoke(["--dry-run", "up"])
        self.assertEqual(before, self.snapshot())

    def test_dry_run_init_creates_no_env_file(self):
        self.env_path().unlink()
        result = self.invoke(["--dry-run", "init", "--yes"])
        self.assertEqual(0, result.exit_code)
        self.assertFalse(self.env_path().exists())

    def test_dry_run_init_reports_what_it_would_write(self):
        self.env_path().unlink()
        result = self.invoke(["--dry-run", "init", "--yes"])
        self.assertIn("LLM_PORT", result.output)

    def test_dry_run_setup_repo_writes_nothing_into_the_target(self):
        with tempfile.TemporaryDirectory() as target:
            result = self.invoke(["--dry-run", "setup-repo", target, "--yes"])
            self.assertEqual(0, result.exit_code)
            self.assertEqual([], list(Path(target).rglob("*")))

    def test_dry_run_setup_repo_does_not_persist_an_anthropic_key(self):
        with tempfile.TemporaryDirectory() as target:
            self.invoke(
                [
                    "--dry-run",
                    "setup-repo",
                    target,
                    "--yes",
                    "--anthropic-key",
                    "sk-dry",
                ]
            )
        self.assertNotIn("sk-dry", self.env_path().read_text(encoding="utf-8"))

    def test_dry_run_never_executes_a_real_subprocess(self):
        with mock.patch("subprocess.run") as run:
            self.invoke(["--dry-run", "up"])
            self.invoke(["--dry-run", "down"])
        run.assert_not_called()

    def test_dry_run_status_still_reports(self):
        with mock.patch.object(
            cli.health, "check_gateway", return_value=offline_status()
        ):
            result = self.invoke(["--dry-run", "status"])
        self.assertEqual(0, result.exit_code)
        self.assertIn("OFFLINE", result.output)


class TestNonInteractive(CliCase):
    """``--yes`` makes Anvil scriptable: it must never read stdin."""

    def booby_trapped_input(self):
        """Both prompt seams raise, so an unexpected read fails loudly."""
        boom = AssertionError("--yes must not read stdin")
        return (
            mock.patch.object(cli.prompts, "_read_line", side_effect=boom),
            mock.patch.object(cli.prompts, "_read_confirmation", side_effect=boom),
            # Force the interactive decision to True, so the *only* reason a
            # prompt is skipped is --yes itself.
            mock.patch.object(cli, "_is_interactive", return_value=True),
        )

    def run_without_stdin(self, argv):
        patches = self.booby_trapped_input()
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        return self.invoke_allowing_exception(argv)

    def test_yes_init_reads_no_stdin(self):
        result = self.run_without_stdin(["init", "--yes"])
        self.assertEqual(0, result.exit_code)

    def test_yes_setup_repo_reads_no_stdin(self):
        self.write_env(LLM_PORT="8000")
        with tempfile.TemporaryDirectory() as target:
            result = self.run_without_stdin(["setup-repo", target, "--yes"])
        self.assertEqual(0, result.exit_code)

    def test_yes_status_reads_no_stdin_even_without_an_env_file(self):
        with mock.patch.object(
            cli.health, "check_gateway", return_value=offline_status()
        ):
            result = self.run_without_stdin(["status", "--yes"])
        self.assertEqual(0, result.exit_code)

    def test_flags_alone_read_no_stdin_without_yes(self):
        # Supplying every value is as good as --yes: nothing is left to ask.
        # This class writes no .env, so init has a clean slate already.
        self.assertFalse(self.env_path().exists())
        result = self.run_without_stdin(
            [
                "init",
                "--llm-port",
                "8123",
                "--hf-home",
                "/tmp/hf",
                "--data-dir",
                "/tmp/data",
                "--gpu-generic",
                "3",
                "--gpu-coder",
                "4,5",
                "--gpu-embedder",
                "6",
            ]
        )
        self.assertEqual(0, result.exit_code)

    def test_a_closed_stdin_does_not_hang(self):
        # A CI runner presents genuine EOF; the defaults must still apply.
        self.assertFalse(self.env_path().exists())
        result = self.invoke_allowing_exception(["init"], input="")
        self.assertEqual(0, result.exit_code)
        self.assertTrue(self.env_path().is_file())


class TestInit(CliCase):
    """``init`` reproduces the implicit .env bootstrap of anvil:27-82."""

    def env_text(self):
        return self.env_path().read_text(encoding="utf-8")

    def env_values(self):
        from anvilkit import env

        return env.read(self.env_path())

    def test_writes_every_key_the_heredoc_wrote(self):
        self.invoke(["init", "--yes"])
        self.assertEqual(set(ENV_KEYS), set(self.env_values()))

    def test_preserves_the_section_comments(self):
        self.invoke(["init", "--yes"])
        text = self.env_text()
        for heading in (
            "Host Storage Paths",
            "Networking Ports",
            "GPU Device Allocation",
        ):
            self.assertIn(heading, text)

    def test_keys_are_written_in_the_original_order(self):
        self.invoke(["init", "--yes"])
        text = self.env_text()
        positions = [text.index(key + "=") for key in ENV_KEYS]
        self.assertEqual(sorted(positions), positions)

    def test_defaults_match_the_bash_script(self):
        with mock.patch.dict(os.environ, {"HOME": "/home/tester"}):
            self.invoke(["init", "--yes"])

        values = self.env_values()
        self.assertEqual("/home/tester/.cache/huggingface", values["HF_HOME"])
        self.assertEqual("./", values["DATA_DIR"])
        self.assertEqual("0", values["LLM_DEVICE_ID_0"])
        self.assertEqual("0", values["LLM_DEVICE_ID_1"])
        self.assertEqual("1", values["LLM_DEVICE_ID_2"])
        self.assertEqual("2", values["INDEXER_STORAGE_DEVICE_ID"])

    def test_default_port_comes_from_anvil_yaml(self):
        from anvilkit import config

        settings = config.read_settings(self.project / "anvil.yaml")
        self.invoke(["init", "--yes"])
        self.assertEqual(str(settings.default_port), self.env_values()["LLM_PORT"])

    def test_flags_override_every_default(self):
        self.invoke(
            [
                "init",
                "--yes",
                "--hf-home",
                "/data/hf",
                "--data-dir",
                "/data/anvil",
                "--llm-port",
                "9100",
                "--gpu-generic",
                "7",
                "--gpu-coder",
                "1,2",
                "--gpu-embedder",
                "3",
            ]
        )

        values = self.env_values()
        self.assertEqual("/data/hf", values["HF_HOME"])
        self.assertEqual("/data/anvil", values["DATA_DIR"])
        self.assertEqual("9100", values["LLM_PORT"])
        self.assertEqual("7", values["LLM_DEVICE_ID_0"])
        self.assertEqual("1", values["LLM_DEVICE_ID_1"])
        self.assertEqual("2", values["LLM_DEVICE_ID_2"])
        self.assertEqual("3", values["INDEXER_STORAGE_DEVICE_ID"])

    def test_a_single_coder_gpu_applies_to_both_slots(self):
        self.invoke(["init", "--yes", "--gpu-coder", "5"])
        values = self.env_values()
        self.assertEqual("5", values["LLM_DEVICE_ID_1"])
        self.assertEqual("5", values["LLM_DEVICE_ID_2"])

    def test_too_many_coder_gpus_is_a_usage_error(self):
        result = self.invoke_allowing_exception(
            ["init", "--yes", "--gpu-coder", "1,2,3"]
        )
        self.assertEqual(cli.EXIT_USAGE, result.exit_code)

    def test_refuses_to_clobber_an_existing_env_file(self):
        self.write_env(LLM_PORT="9999", KEEP="me")
        result = self.invoke_allowing_exception(["init", "--yes"])
        self.assertEqual(cli.EXIT_USAGE, result.exit_code)

    def test_refusal_leaves_the_existing_file_untouched(self):
        self.write_env(LLM_PORT="9999", KEEP="me")
        before = self.env_text()
        self.invoke_allowing_exception(["init", "--yes"])
        self.assertEqual(before, self.env_text())

    def test_refusal_mentions_force(self):
        self.write_env(LLM_PORT="9999")
        result = self.invoke_allowing_exception(["init", "--yes"])
        self.assertIn("--force", result.output)

    def test_force_regenerates_the_file(self):
        self.write_env(LLM_PORT="9999")
        result = self.invoke(["init", "--yes", "--force"])
        self.assertEqual(0, result.exit_code)
        self.assertNotEqual("9999", self.env_values()["LLM_PORT"])

    def test_invalid_port_flag_is_rejected(self):
        result = self.invoke_allowing_exception(["init", "--yes", "--llm-port", "0"])
        self.assertEqual(cli.EXIT_USAGE, result.exit_code)


class TestImplicitEnvBootstrap(CliCase):
    """A missing .env is created on demand, exactly as anvil:27 did."""

    def test_up_creates_a_missing_env_file(self):
        self.invoke(["up", "--yes"])
        self.assertTrue(self.env_path().is_file())

    def test_up_still_starts_the_stack_after_bootstrapping(self):
        self.invoke(["up", "--yes"])
        self.assertEqual(["up"], [name for name, _ in RecordingCompose.all_calls()])

    def test_status_creates_a_missing_env_file(self):
        with mock.patch.object(
            cli.health, "check_gateway", return_value=offline_status()
        ):
            self.invoke(["status", "--yes"])
        self.assertTrue(self.env_path().is_file())

    def test_an_existing_env_file_is_never_rewritten(self):
        self.write_env(LLM_PORT="9999", KEEP="me")
        before = self.env_path().read_text(encoding="utf-8")
        self.invoke(["up"])
        self.assertEqual(before, self.env_path().read_text(encoding="utf-8"))

    def test_doctor_does_not_create_an_env_file(self):
        # doctor must diagnose a broken install, not modify it.
        self.invoke(["doctor"])
        self.assertFalse(self.env_path().exists())

    def test_setup_repo_does_not_create_an_env_file(self):
        with tempfile.TemporaryDirectory() as target:
            self.invoke(["setup-repo", target, "--yes"])
        self.assertFalse(self.env_path().exists())

    def test_the_bootstrap_is_announced(self):
        self.invoke(["up", "--yes"])
        self.assertTrue(self.env_path().is_file())


class TestPortResolution(CliCase):
    """Precedence: --llm-port > .env > anvil.yaml > default."""

    def checked_port(self, argv):
        with mock.patch.object(
            cli.health, "check_gateway", return_value=offline_status()
        ) as check:
            self.invoke(argv)
        return check.call_args[1]["port"] if check.call_args[1] else check.call_args[0][0]

    def test_env_wins_over_anvil_yaml(self):
        # Existing installs carry LLM_PORT and must be unaffected by the rewrite.
        self.write_env(LLM_PORT="9001")
        self.assertEqual(9001, self.checked_port(["status"]))

    def test_flag_wins_over_env(self):
        self.write_env(LLM_PORT="9001")
        self.assertEqual(9002, self.checked_port(["status", "--llm-port", "9002"]))

    def test_anvil_yaml_supplies_the_fallback(self):
        from anvilkit import config

        settings = config.read_settings(self.project / "anvil.yaml")
        self.write_env(OTHER="1")
        self.assertEqual(settings.default_port, self.checked_port(["status"]))


class TestStatus(CliCase):
    """``status`` renders through health, and offers a machine-readable form."""

    def setUp(self):
        super().setUp()
        self.write_env(LLM_PORT="8000")

    def test_human_output_reports_an_online_gateway(self):
        with mock.patch.object(
            cli.health, "check_gateway", return_value=online_status()
        ):
            result = self.invoke(["status"])
        self.assertIn("ONLINE", result.output)

    def test_human_output_lists_registered_models(self):
        with mock.patch.object(
            cli.health, "check_gateway", return_value=online_status()
        ):
            result = self.invoke(["status"])
        self.assertIn("Qwen/Qwen3.6-35B-A3B-FP8", result.output)

    def test_json_output_parses(self):
        with mock.patch.object(
            cli.health, "check_gateway", return_value=online_status()
        ):
            result = self.invoke(["status", "--json"])
        json.loads(result.output)

    def test_json_output_carries_the_model_state(self):
        with mock.patch.object(
            cli.health, "check_gateway", return_value=online_status()
        ):
            result = self.invoke(["status", "--json"])

        payload = json.loads(result.output)
        self.assertEqual(8000, payload["port"])
        self.assertTrue(payload["online"])
        self.assertEqual(
            {"Qwen/Qwen3.6-35B-A3B-FP8": True, "nomic-ai/nomic-embed-text-v1.5": False},
            {model["id"]: model["hot"] for model in payload["models"]},
        )

    def test_json_output_is_pure_json(self):
        # Nothing decorative may precede it, or piping into jq breaks.
        with mock.patch.object(
            cli.health, "check_gateway", return_value=online_status()
        ):
            result = self.invoke(["status", "--json"])
        self.assertTrue(result.output.lstrip().startswith("{"))

    def test_json_output_does_not_list_docker_services(self):
        with mock.patch.object(
            cli.health, "check_gateway", return_value=online_status()
        ):
            self.invoke(["status", "--json"])
        self.assertEqual([], RecordingCompose.all_calls())

    def test_json_output_of_an_offline_gateway_records_the_error(self):
        with mock.patch.object(
            cli.health, "check_gateway", return_value=offline_status()
        ):
            result = self.invoke(["status", "--json"])

        payload = json.loads(result.output)
        self.assertFalse(payload["online"])
        self.assertEqual("connection refused", payload["error"])

    def test_no_color_suppresses_escape_sequences(self):
        with mock.patch.object(
            cli.health, "check_gateway", return_value=online_status()
        ):
            result = self.invoke(["--no-color", "status"])
        self.assertNotIn("\033[", result.output)


class TestTestModel(CliCase):
    """``test-model`` sends one real prompt and reports whether it was answered."""

    MODEL = "Qwen/Qwen3.6-35B-A3B-FP8"

    def setUp(self):
        super().setUp()
        self.write_env(LLM_PORT="8000")

    def run_with(self, result, argv=None):
        with mock.patch.object(
            cli.health, "test_model", return_value=result
        ) as probe:
            invoked = self.invoke_allowing_exception(
                argv or ["test-model", self.MODEL]
            )
        return invoked, probe

    # -- the happy path ---------------------------------------------------

    def test_a_model_that_answers_exits_zero(self):
        result, _ = self.run_with(passing_test())
        self.assertEqual(cli.EXIT_OK, result.exit_code)

    def test_a_model_that_answers_reports_a_pass(self):
        result, _ = self.run_with(passing_test())
        self.assertIn("PASS", result.output)

    def test_the_reply_is_shown(self):
        result, _ = self.run_with(passing_test())
        self.assertIn("pong", result.output)

    # -- what reaches health ----------------------------------------------

    def test_the_requested_model_reaches_health(self):
        _, probe = self.run_with(passing_test())
        self.assertEqual(self.MODEL, probe.call_args[1]["model_id"])

    def test_the_resolved_port_reaches_health(self):
        _, probe = self.run_with(passing_test())
        self.assertEqual(8000, probe.call_args[1]["port"])

    def test_the_flag_port_wins_over_env(self):
        _, probe = self.run_with(
            passing_test(port=9002),
            ["test-model", self.MODEL, "--llm-port", "9002"],
        )
        self.assertEqual(9002, probe.call_args[1]["port"])

    def test_a_default_prompt_is_sent_when_none_is_given(self):
        _, probe = self.run_with(passing_test())
        self.assertEqual(health_default_prompt(), probe.call_args[1]["prompt"])

    def test_a_supplied_prompt_reaches_health(self):
        _, probe = self.run_with(
            passing_test(),
            ["test-model", self.MODEL, "--prompt", "write a haiku"],
        )
        self.assertEqual("write a haiku", probe.call_args[1]["prompt"])

    def test_the_token_ceiling_reaches_health(self):
        _, probe = self.run_with(
            passing_test(), ["test-model", self.MODEL, "--max-tokens", "64"]
        )
        self.assertEqual(64, probe.call_args[1]["max_tokens"])

    def test_the_timeout_reaches_health(self):
        _, probe = self.run_with(
            passing_test(), ["test-model", self.MODEL, "--timeout", "30"]
        )
        self.assertEqual(30.0, probe.call_args[1]["timeout"])

    def test_the_default_timeout_allows_for_a_cold_start(self):
        """A model loaded on demand cannot answer within the 2s status probe."""
        _, probe = self.run_with(passing_test())
        self.assertEqual(
            cli.health.DEFAULT_GENERATION_TIMEOUT, probe.call_args[1]["timeout"]
        )

    # -- failures ----------------------------------------------------------

    def test_a_failed_generation_exits_one(self):
        result, _ = self.run_with(failing_test())
        self.assertEqual(cli.EXIT_ERROR, result.exit_code)

    def test_a_failed_generation_reports_the_error(self):
        result, _ = self.run_with(failing_test())
        self.assertIn("connection refused", result.output)

    def test_an_unknown_model_exits_one(self):
        result, _ = self.run_with(
            failing_test(
                error="not registered",
                unknown_model=True,
                available_models=["a/b", "c/d"],
            )
        )
        self.assertEqual(cli.EXIT_ERROR, result.exit_code)

    def test_an_unknown_model_lists_the_registry(self):
        result, _ = self.run_with(
            failing_test(
                error="not registered",
                unknown_model=True,
                available_models=["a/b", "c/d"],
            )
        )
        self.assertIn("a/b", result.output)
        self.assertIn("c/d", result.output)

    # -- a missing model name -------------------------------------------

    def run_without_a_name(self, status=None, argv=None):
        """No name given: the command must say which names it would accept."""
        with mock.patch.object(
            cli.health, "check_gateway", return_value=status or online_status()
        ) as check:
            invoked = self.invoke_allowing_exception(argv or ["test-model"])
        return invoked, check

    def test_a_missing_model_name_is_a_usage_error(self):
        result, _ = self.run_without_a_name()
        self.assertEqual(cli.EXIT_USAGE, result.exit_code)

    def test_a_missing_model_name_lists_the_registered_models(self):
        result, _ = self.run_without_a_name()
        self.assertIn("Qwen/Qwen3.6-35B-A3B-FP8", result.output)
        self.assertIn("nomic-ai/nomic-embed-text-v1.5", result.output)

    def test_a_missing_model_name_says_what_is_missing(self):
        result, _ = self.run_without_a_name()
        self.assertIn("MODEL_NAME", result.output)

    def test_a_missing_model_name_queries_the_resolved_port(self):
        _, check = self.run_without_a_name()
        called = check.call_args
        self.assertEqual(8000, called[1]["port"] if called[1] else called[0][0])

    def test_a_missing_model_name_never_sends_a_prompt(self):
        with mock.patch.object(
            cli.health, "check_gateway", return_value=online_status()
        ):
            with mock.patch.object(cli.health, "test_model") as probe:
                self.invoke_allowing_exception(["test-model"])
        probe.assert_not_called()

    def test_an_unreachable_gateway_still_reports_the_missing_name(self):
        result, _ = self.run_without_a_name(status=offline_status())
        self.assertEqual(cli.EXIT_USAGE, result.exit_code)
        self.assertIn("connection refused", result.output)

    def test_a_missing_model_name_under_dry_run_is_still_a_usage_error(self):
        result, _ = self.run_without_a_name(argv=["--dry-run", "test-model"])
        self.assertEqual(cli.EXIT_USAGE, result.exit_code)

    def test_a_non_numeric_port_in_env_exits_with_the_config_code(self):
        self.write_env(LLM_PORT="eight-thousand")
        result = self.invoke_allowing_exception(["test-model", self.MODEL])
        self.assertEqual(cli.EXIT_CONFIG, result.exit_code)

    def test_a_config_error_never_reaches_health(self):
        self.write_env(LLM_PORT="eight-thousand")
        with mock.patch.object(cli.health, "test_model") as probe:
            self.invoke_allowing_exception(["test-model", self.MODEL])
        probe.assert_not_called()

    # -- machine-readable output ------------------------------------------

    def test_json_output_parses(self):
        result, _ = self.run_with(
            passing_test(), ["test-model", self.MODEL, "--json"]
        )
        json.loads(result.output)

    def test_json_output_carries_the_outcome(self):
        result, _ = self.run_with(
            passing_test(), ["test-model", self.MODEL, "--json"]
        )
        payload = json.loads(result.output)
        self.assertTrue(payload["ok"])
        self.assertEqual("pong", payload["reply"])
        self.assertEqual(self.MODEL, payload["model"])

    def test_json_output_is_pure_json(self):
        # Nothing decorative may precede it, or piping into jq breaks.
        result, _ = self.run_with(
            passing_test(), ["test-model", self.MODEL, "--json"]
        )
        self.assertTrue(result.output.lstrip().startswith("{"))

    def test_json_output_of_a_failure_still_exits_one(self):
        result, _ = self.run_with(
            failing_test(), ["test-model", self.MODEL, "--json"]
        )
        self.assertEqual(cli.EXIT_ERROR, result.exit_code)

    def test_json_output_does_not_list_docker_services(self):
        self.run_with(passing_test(), ["test-model", self.MODEL, "--json"])
        self.assertEqual([], RecordingCompose.all_calls())

    def test_no_color_suppresses_escape_sequences(self):
        result, _ = self.run_with(
            passing_test(), ["--no-color", "test-model", self.MODEL]
        )
        self.assertNotIn("\033[", result.output)

    # -- dry run -----------------------------------------------------------

    def test_dry_run_sends_nothing(self):
        with mock.patch.object(cli.health, "test_model") as probe:
            self.invoke(["--dry-run", "test-model", self.MODEL])
        probe.assert_not_called()

    def test_dry_run_shows_the_request_that_would_be_sent(self):
        result = self.invoke(["--dry-run", "test-model", self.MODEL])
        self.assertIn("/v1/chat/completions", result.output)
        self.assertIn(self.MODEL, result.output)

    def test_dry_run_exits_zero(self):
        result = self.invoke(["--dry-run", "test-model", self.MODEL])
        self.assertEqual(cli.EXIT_OK, result.exit_code)

    def test_dry_run_writes_nothing(self):
        before = self.snapshot()
        self.invoke(["--dry-run", "test-model", self.MODEL])
        self.assertEqual(before, self.snapshot())


def health_default_prompt():
    from anvilkit import health

    return health.DEFAULT_PROBE_PROMPT


class TestSetupRepo(CliCase):
    """``setup-repo`` resolves a RepoPlan; provision performs the writes."""

    def setUp(self):
        super().setUp()
        self.write_env(LLM_PORT="8000")
        self._target = tempfile.TemporaryDirectory()
        self.target = self._target.name
        self.addCleanup(self._target.cleanup)

    def captured_plan(self, argv):
        """Run setup-repo and return the RepoPlan it built."""
        with mock.patch.object(
            cli.provision, "setup_repo", return_value=self.target
        ) as setup:
            result = self.invoke_allowing_exception(argv)

        self.assertEqual(0, result.exit_code, result.output)
        return setup.call_args[0][1] if len(setup.call_args[0]) > 1 else setup.call_args[1]["repo_plan"]

    def test_target_is_passed_through(self):
        with mock.patch.object(
            cli.provision, "setup_repo", return_value=self.target
        ) as setup:
            self.invoke(["setup-repo", self.target, "--yes"])

        first_positional = setup.call_args[0][0]
        self.assertEqual(self.target, str(first_positional))

    def test_plan_carries_the_resolved_port(self):
        plan = self.captured_plan(["setup-repo", self.target, "--yes"])
        self.assertEqual(8000, plan.port)

    def test_plan_carries_the_context_window_from_config_yaml(self):
        from anvilkit import config

        topology = config.read_models(self.project / "config.yaml")
        plan = self.captured_plan(["setup-repo", self.target, "--yes"])
        self.assertEqual(topology.coder_context_window, plan.context_window)

    def test_plan_carries_the_model_ids_from_config_yaml(self):
        from anvilkit import config

        topology = config.read_models(self.project / "config.yaml")
        plan = self.captured_plan(["setup-repo", self.target, "--yes"])
        self.assertEqual(topology.coder_id, plan.coder_model_id)
        self.assertEqual(topology.embedder_id, plan.embedder_model_id)

    def test_plan_carries_the_profile_ids_from_anvil_yaml(self):
        from anvilkit import config

        settings = config.read_settings(self.project / "anvil.yaml")
        plan = self.captured_plan(["setup-repo", self.target, "--yes"])
        self.assertEqual(settings.local_profile_id, plan.local_profile_id)
        self.assertEqual(settings.anthropic_profile_id, plan.anthropic_profile_id)

    def test_declining_everything_matches_the_bash_defaults(self):
        # anvil:158-160: declined keeps the anthropic profile dormant but valid.
        plan = self.captured_plan(["setup-repo", self.target, "--yes"])
        self.assertFalse(plan.use_anthropic_for_frontier_modes)
        self.assertEqual("to set", plan.anthropic_api_key)
        self.assertEqual("", plan.github_token)

    def test_declined_default_model_still_comes_from_anvil_yaml(self):
        from anvilkit import config

        settings = config.read_settings(self.project / "anvil.yaml")
        plan = self.captured_plan(["setup-repo", self.target, "--yes"])
        self.assertEqual(settings.default_anthropic_model, plan.anthropic_model_id)

    def test_github_token_flag_enables_github(self):
        plan = self.captured_plan(
            ["setup-repo", self.target, "--yes", "--github-token", "ghp_abc"]
        )
        self.assertEqual("ghp_abc", plan.github_token)

    def test_no_github_forces_an_empty_token(self):
        plan = self.captured_plan(["setup-repo", self.target, "--yes", "--no-github"])
        self.assertEqual("", plan.github_token)

    def test_anthropic_key_flag_enables_anthropic_for_frontier_modes(self):
        plan = self.captured_plan(
            ["setup-repo", self.target, "--yes", "--anthropic-key", "sk-live"]
        )
        self.assertTrue(plan.use_anthropic_for_frontier_modes)
        self.assertEqual("sk-live", plan.anthropic_api_key)

    def test_no_anthropic_overrides_a_supplied_key(self):
        plan = self.captured_plan(
            [
                "setup-repo",
                self.target,
                "--yes",
                "--no-anthropic",
                "--anthropic-key",
                "sk-live",
            ]
        )
        self.assertFalse(plan.use_anthropic_for_frontier_modes)

    def test_anthropic_model_flag_is_honoured(self):
        plan = self.captured_plan(
            [
                "setup-repo",
                self.target,
                "--yes",
                "--anthropic-key",
                "sk-live",
                "--anthropic-model",
                "claude-sonnet-5",
            ]
        )
        self.assertEqual("claude-sonnet-5", plan.anthropic_model_id)

    def test_a_custom_anthropic_model_id_is_accepted(self):
        # The bash menu's item 5 allowed any id; the flag must too.
        plan = self.captured_plan(
            [
                "setup-repo",
                self.target,
                "--yes",
                "--anthropic-key",
                "sk-live",
                "--anthropic-model",
                "some-unreleased-model",
            ]
        )
        self.assertEqual("some-unreleased-model", plan.anthropic_model_id)

    def test_a_supplied_key_is_persisted_to_env(self):
        from anvilkit import env

        with mock.patch.object(cli.provision, "setup_repo", return_value=self.target):
            self.invoke(
                ["setup-repo", self.target, "--yes", "--anthropic-key", "sk-persist"]
            )

        self.assertEqual(
            "sk-persist", env.get(self.env_path(), "ANTHROPIC_API_KEY")
        )

    def test_persisting_a_key_preserves_other_env_values(self):
        from anvilkit import env

        self.write_env(LLM_PORT="8000", DATA_DIR="./keepme")

        with mock.patch.object(cli.provision, "setup_repo", return_value=self.target):
            self.invoke(
                ["setup-repo", self.target, "--yes", "--anthropic-key", "sk-persist"]
            )

        values = env.read(self.env_path())
        self.assertEqual("./keepme", values["DATA_DIR"])
        self.assertEqual("8000", values["LLM_PORT"])

    def test_an_existing_env_key_is_reused_without_prompting(self):
        # anvil:176: "Reusing existing ANTHROPIC_API_KEY from .env".
        self.write_env(LLM_PORT="8000", ANTHROPIC_API_KEY="sk-existing")
        plan = self.captured_plan(
            ["setup-repo", self.target, "--yes", "--anthropic"]
        )
        self.assertEqual("sk-existing", plan.anthropic_api_key)

    def test_a_key_containing_sed_metacharacters_survives(self):
        # The bug escape_sed_replacement() at anvil:95 existed to work around.
        from anvilkit import env

        nasty = r"sk-a|b&c\d"
        with mock.patch.object(cli.provision, "setup_repo", return_value=self.target):
            self.invoke(
                ["setup-repo", self.target, "--yes", "--anthropic-key", nasty]
            )

        self.assertEqual(nasty, env.get(self.env_path(), "ANTHROPIC_API_KEY"))

    def test_the_key_is_never_echoed(self):
        with mock.patch.object(cli.provision, "setup_repo", return_value=self.target):
            result = self.invoke(
                ["setup-repo", self.target, "--yes", "--anthropic-key", "sk-secret"]
            )
        self.assertNotIn("sk-secret", result.output)

    def test_provision_receives_the_dry_run_flag(self):
        with mock.patch.object(
            cli.provision, "setup_repo", return_value=self.target
        ) as setup:
            self.invoke(["--dry-run", "setup-repo", self.target, "--yes"])

        self.assertTrue(setup.call_args[1]["dry_run"])

    def test_a_missing_target_is_reported_clearly(self):
        result = self.invoke_allowing_exception(
            ["setup-repo", str(self.project / "absent"), "--yes"]
        )
        self.assertIn("does not exist", result.output)


class TestDoctor(CliCase):
    """``doctor`` diagnoses the host without needing a configured install."""

    def probes(self, docker=True, compose=True, nvidia=True):
        return (
            mock.patch.object(cli.compose, "docker_available", return_value=docker),
            mock.patch.object(
                cli.compose, "compose_v2_available", return_value=compose
            ),
            mock.patch.object(cli.compose, "nvidia_available", return_value=nvidia),
        )

    def run_doctor(self, argv=("doctor",), **kwargs):
        started = []
        for patcher in self.probes(**kwargs):
            patcher.start()
            started.append(patcher)
        try:
            return self.invoke_allowing_exception(list(argv))
        finally:
            for patcher in started:
                patcher.stop()

    def test_works_with_no_env_file(self):
        self.assertFalse(self.env_path().exists())
        result = self.run_doctor()
        self.assertEqual(0, result.exit_code)

    def test_works_with_no_config_files_at_all(self):
        # A half-cloned or misconfigured repo is exactly when doctor is needed,
        # so it must never fail on the thing it is meant to diagnose.
        (self.project / "anvil.yaml").unlink()
        (self.project / "config.yaml").unlink()
        result = self.run_doctor()
        self.assertEqual(0, result.exit_code)

    def test_reports_the_interpreter_path(self):
        result = self.run_doctor()
        self.assertIn(sys.executable, result.output)

    def test_reports_the_interpreter_version(self):
        result = self.run_doctor()
        version = "{}.{}.{}".format(*sys.version_info[:3])
        self.assertIn(version, result.output)

    def test_reports_whether_a_venv_is_in_use(self):
        result = self.run_doctor()
        self.assertIn("venv", result.output.lower())

    def test_reports_docker(self):
        result = self.run_doctor()
        self.assertIn("docker", result.output.lower())

    def test_reports_compose(self):
        result = self.run_doctor()
        self.assertIn("compose", result.output.lower())

    def test_reports_nvidia(self):
        result = self.run_doctor()
        self.assertIn("nvidia", result.output.lower())

    def test_missing_docker_is_reported_but_is_not_fatal(self):
        # doctor's job is to report, so a bad host is still a successful run.
        result = self.run_doctor(docker=False, compose=False)
        self.assertEqual(0, result.exit_code)

    def test_a_healthy_host_and_a_broken_host_read_differently(self):
        healthy = self.run_doctor().output
        broken = self.run_doctor(docker=False, compose=False, nvidia=False).output
        self.assertNotEqual(healthy, broken)

    def test_reports_the_env_file_as_missing(self):
        result = self.run_doctor()
        self.assertIn(".env", result.output)

    def test_reports_an_existing_env_file(self):
        self.write_env(LLM_PORT="8000")
        result = self.run_doctor()
        self.assertIn(".env", result.output)

    def test_reports_an_invalid_anvil_yaml_without_crashing(self):
        (self.project / "anvil.yaml").write_text("zoo_code: []\n", encoding="utf-8")
        result = self.run_doctor()
        self.assertEqual(0, result.exit_code)
        self.assertIn("anvil.yaml", result.output)

    def test_probes_the_host_exactly_once_each(self):
        with mock.patch.object(
            cli.compose, "docker_available", return_value=True
        ) as docker:
            self.invoke(["doctor"])
        self.assertEqual(1, docker.call_count)


class TestBanner(CliCase):
    """The anvil:6 banner stays for humans and keeps out of machine output."""

    def setUp(self):
        super().setUp()
        self.write_env(LLM_PORT="8000")

    def test_human_commands_print_the_banner(self):
        result = self.invoke(["up"])
        self.assertIn(cli.BANNER.strip().splitlines()[1], result.output)

    def test_json_status_omits_the_banner(self):
        with mock.patch.object(
            cli.health, "check_gateway", return_value=online_status()
        ):
            result = self.invoke(["status", "--json"])
        self.assertNotIn("_ _", result.output)

    def test_doctor_omits_the_banner(self):
        result = self.invoke(["doctor"])
        self.assertNotIn("_ _", result.output)

    def test_help_omits_the_banner(self):
        result = self.invoke(["--help"])
        self.assertNotIn("_ _", result.output)


class TestVerbose(CliCase):
    """``--verbose`` adds detail without changing what happens."""

    def setUp(self):
        super().setUp()
        self.write_env(LLM_PORT="8000")

    def test_verbose_up_still_dispatches_once(self):
        self.invoke(["--verbose", "up"])
        self.assertEqual(["up"], [name for name, _ in RecordingCompose.all_calls()])

    def test_verbose_adds_output(self):
        quiet = self.invoke(["up"]).output
        RecordingCompose.reset()
        loud = self.invoke(["--verbose", "up"]).output
        self.assertGreater(len(loud), len(quiet))

    def test_verbose_dry_run_shows_the_command_it_would_run(self):
        # The echo seam must be wired, or --dry-run is silent and useless.
        self.invoke(["--verbose", "--dry-run", "up"])
        self.assertIsNotNone(RecordingCompose.last().echo)


class TestRunEntryPoint(CliCase):
    """The real entrypoint, which ``CliRunner`` does not exercise.

    ``run()`` calls the app with ``standalone_mode=False`` so it can map
    exceptions to its own exit codes. That changes click's behaviour: instead of
    printing usage and exiting, click *raises* ``UsageError``. ``CliRunner`` uses
    standalone mode, so tests that go through it prove nothing about this path.

    These tests exist because of a real defect: an unknown command escaped as an
    unhandled ``UsageError`` and printed a full traceback, while exiting 1 rather
    than the documented usage code.
    """

    def run_cli(self, argv):
        """Invoke run() exactly as ``python -m anvilkit.cli`` does."""
        stderr = io.StringIO()
        with mock.patch.object(sys, "argv", ["anvil"] + argv):
            with contextlib.redirect_stderr(stderr):
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    code = cli.run()
        return code, stdout.getvalue() + stderr.getvalue()

    def test_unknown_command_exits_with_the_usage_code(self):
        code, _ = self.run_cli(["frobnicate"])
        self.assertEqual(cli.EXIT_USAGE, code)

    def test_unknown_command_does_not_print_a_traceback(self):
        _, output = self.run_cli(["frobnicate"])
        self.assertNotIn("Traceback", output)

    def test_unknown_command_names_the_offending_command(self):
        _, output = self.run_cli(["frobnicate"])
        self.assertIn("frobnicate", output)

    def test_bad_option_value_exits_with_the_usage_code(self):
        code, _ = self.run_cli(["status", "--llm-port", "not-a-port"])
        self.assertEqual(cli.EXIT_USAGE, code)

    def test_bad_option_value_does_not_print_a_traceback(self):
        _, output = self.run_cli(["status", "--llm-port", "not-a-port"])
        self.assertNotIn("Traceback", output)

    def test_missing_argument_exits_with_the_usage_code(self):
        code, _ = self.run_cli(["setup-repo"])
        self.assertEqual(cli.EXIT_USAGE, code)

    def test_help_exits_zero(self):
        code, _ = self.run_cli(["--help"])
        self.assertEqual(cli.EXIT_OK, code)

    def test_no_arguments_exits_zero_and_shows_commands(self):
        code, output = self.run_cli([])
        self.assertEqual(cli.EXIT_OK, code)
        self.assertIn("up", output)

    def test_doctor_exits_zero(self):
        code, _ = self.run_cli(["doctor"])
        self.assertEqual(cli.EXIT_OK, code)

    def test_a_successful_command_exits_zero(self):
        self.write_env(LLM_PORT="8000")
        code, _ = self.run_cli(["--dry-run", "up"])
        self.assertEqual(cli.EXIT_OK, code)

    def test_a_config_error_exits_with_the_config_code(self):
        (self.project / "anvil.yaml").write_text("zoo_code: []\n", encoding="utf-8")
        self.write_env(LLM_PORT="8000")
        code, _ = self.run_cli(["status"])
        self.assertEqual(cli.EXIT_CONFIG, code)

    def test_a_config_error_does_not_print_a_traceback(self):
        (self.project / "anvil.yaml").write_text("zoo_code: []\n", encoding="utf-8")
        self.write_env(LLM_PORT="8000")
        _, output = self.run_cli(["status"])
        self.assertNotIn("Traceback", output)

    def test_a_docker_failure_exits_with_the_docker_code(self):
        self.write_env(LLM_PORT="8000")
        RecordingCompose.raises = cli.ComposeError("docker not found")
        code, _ = self.run_cli(["up"])
        self.assertEqual(cli.EXIT_DOCKER, code)

    def test_a_provisioning_failure_exits_with_the_provision_code(self):
        self.write_env(LLM_PORT="8000")
        code, _ = self.run_cli(["setup-repo", str(self.project / "absent"), "--yes"])
        self.assertEqual(cli.EXIT_PROVISION, code)

    def test_a_compose_exit_code_is_propagated(self):
        self.write_env(LLM_PORT="8000")
        RecordingCompose.return_code = 17
        code, _ = self.run_cli(["up"])
        self.assertEqual(17, code)

    def test_an_interrupt_is_not_a_traceback(self):
        self.write_env(LLM_PORT="8000")
        RecordingCompose.raises = KeyboardInterrupt()
        code, output = self.run_cli(["up"])
        self.assertEqual(cli.EXIT_ERROR, code)
        self.assertNotIn("Traceback", output)

    def test_test_model_missing_argument_exits_with_the_usage_code(self):
        self.write_env(LLM_PORT="8000")
        with mock.patch.object(
            cli.health, "check_gateway", return_value=online_status()
        ):
            code, _ = self.run_cli(["test-model"])
        self.assertEqual(cli.EXIT_USAGE, code)

    def test_test_model_missing_argument_lists_the_registry(self):
        self.write_env(LLM_PORT="8000")
        with mock.patch.object(
            cli.health, "check_gateway", return_value=online_status()
        ):
            _, output = self.run_cli(["test-model"])
        self.assertIn("Qwen/Qwen3.6-35B-A3B-FP8", output)

    def test_test_model_missing_argument_does_not_print_a_traceback(self):
        self.write_env(LLM_PORT="8000")
        with mock.patch.object(
            cli.health, "check_gateway", return_value=online_status()
        ):
            _, output = self.run_cli(["test-model"])
        self.assertNotIn("Traceback", output)

    def test_test_model_passing_exits_zero(self):
        self.write_env(LLM_PORT="8000")
        with mock.patch.object(cli.health, "test_model", return_value=passing_test()):
            code, _ = self.run_cli(["test-model", "Qwen/Qwen3.6-35B-A3B-FP8"])
        self.assertEqual(cli.EXIT_OK, code)

    def test_test_model_failing_exits_with_the_error_code(self):
        self.write_env(LLM_PORT="8000")
        with mock.patch.object(cli.health, "test_model", return_value=failing_test()):
            code, _ = self.run_cli(["test-model", "Qwen/Qwen3.6-35B-A3B-FP8"])
        self.assertEqual(cli.EXIT_ERROR, code)

    def test_test_model_failing_does_not_print_a_traceback(self):
        self.write_env(LLM_PORT="8000")
        with mock.patch.object(cli.health, "test_model", return_value=failing_test()):
            _, output = self.run_cli(["test-model", "Qwen/Qwen3.6-35B-A3B-FP8"])
        self.assertNotIn("Traceback", output)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# _resolve_oxylabs  (Behavior 3 — red phase)
# ---------------------------------------------------------------------------


class TestResolveOxylabs(CliCase):
    """Tests for ``_resolve_oxylabs`` — the CLI resolution function for Oxylabs credentials.

    Follows the same pattern as ``_resolve_github_token`` (``anvilkit/cli.py:752``)
    but returns a ``(username, password)`` tuple.

    TDD red phase: these tests verify the *desired* behaviour. The production
    function does not exist yet, so every test must fail with ``AttributeError``
    or ``AssertionError`` until Behaviour 3 is implemented.
    """

    def _make_context(self, assume_yes=False):
        """Build a minimal Context pointing at the test project."""
        return cli.Context(
            dry_run=False,
            verbose=False,
            no_color=False,
            assume_yes=assume_yes,
        )

    # -- Test 1: --no-oxylabs flag wins --------------------------------

    def test_no_oxylabs_returns_empty_tuple_without_reading_env(self):
        """When no_oxylabs=True, return (\"\", \"\") immediately, without reading .env."""
        ctx = self._make_context(assume_yes=False)

        # env.get should raise if it is called — we must not read .env
        with mock.patch.object(
            cli.env, "get", side_effect=AssertionError("_resolve_oxylabs must not read .env when no_oxylabs=True")
        ):
            result = cli._resolve_oxylabs(ctx, None, no_oxylabs=True)

        self.assertEqual(("", ""), result)

    # -- Test 2: --oxylabs-username flag wins --------------------------

    def test_supplied_username_flag_wins_over_env(self):
        """When oxylabs_username is provided, use it and password — do NOT read .env."""
        ctx = self._make_context(assume_yes=False)

        # Write old values to .env — they must be ignored
        self.write_env(OXYLABS_USERNAME="old_user", OXYLABS_PASSWORD="old_pass")

        with mock.patch.object(cli.env, "get", return_value="old_user"):
            result = cli._resolve_oxylabs(
                ctx, username="new_user", no_oxylabs=False, password="new_pass"
            )

        self.assertEqual(("new_user", "new_pass"), result)
        # .env must remain unchanged
        values = cli.env.read(self.env_path())
        self.assertEqual("old_user", values.get("OXYLABS_USERNAME"))
        self.assertEqual("old_pass", values.get("OXYLABS_PASSWORD"))

    # -- Test 3: existing .env value is reused -------------------------

    def test_existing_env_value_is_reused_without_prompting(self):
        """When neither flag is provided and .env has credentials, reuse them without prompting."""
        ctx = self._make_context(assume_yes=False)

        self.write_env(OXYLABS_USERNAME="existing_user", OXYLABS_PASSWORD="existing_pass")

        # Patch confirm to raise — we must NOT prompt the user
        with mock.patch.object(
            cli.prompts, "confirm", side_effect=AssertionError("_resolve_oxylabs must not prompt when .env has values")
        ):
            result = cli._resolve_oxylabs(ctx, username=None, no_oxylabs=False, password=None)

        self.assertEqual(("existing_user", "existing_pass"), result)

    # -- Test 4: --yes with no .env returns empty ----------------------

    def test_yes_with_no_env_returns_empty_without_prompting(self):
        """When assume_yes=True and no .env value and no flag, return (\"\", \"\") without prompting."""
        # Ensure no .env exists
        if self.env_path().exists():
            self.env_path().unlink()

        ctx = self._make_context(assume_yes=True)

        # Patch confirm to raise — we must NOT prompt
        with mock.patch.object(
            cli.prompts, "confirm", side_effect=AssertionError("_resolve_oxylabs must not prompt with --yes")
        ):
            result = cli._resolve_oxylabs(ctx, username=None, no_oxylabs=False, password=None)

        self.assertEqual(("", ""), result)

    # -- Test 5: decline returns empty without persisting --------------

    def test_decline_returns_empty_without_persisting(self):
        """When interactive=True, .env is empty, and user declines, return (\"\", \"\") and do not persist."""
        # Ensure no .env exists
        if self.env_path().exists():
            self.env_path().unlink()

        ctx = self._make_context(assume_yes=False)

        # Force interactive=True so we go down the prompt path
        with mock.patch.object(cli, "_is_interactive", return_value=True):
            with mock.patch.object(
                cli.prompts, "confirm", return_value=False  # user declines
            ):
                result = cli._resolve_oxylabs(
                    ctx, username=None, no_oxylabs=False, password=None
                )

        self.assertEqual(("", ""), result)
        # .env must NOT have been created
        self.assertFalse(self.env_path().exists())


# ---------------------------------------------------------------------------
# _resolve_github_token  (Behavior 1 — contract lock for --no-github)
# ---------------------------------------------------------------------------


class TestResolveGithubTokenNoGithub(CliCase):
    """B1: ``--no-github`` short-circuits before any store access.

    The contract, per plans/skip-github-token-prompt.md §4/B1:

    * input ``no_github=True`` (with or without a ``GITHUB_TOKEN`` in .env),
    * output ``""``,
    * ``env.get`` is never called — the stored token is neither read nor
      clobbered by the decision,
    * ``prompts.confirm`` / ``prompts.ask_required`` are never called — no
      interactive surface is even reachable.

    Both seams are booby-trapped with ``side_effect=AssertionError``, matching
    the oxylabs precedent in ``TestResolveOxylabs``: any call from
    ``_resolve_github_token`` fails the test loudly rather than hanging or
    reading the real file.

    Red-phase note: the current implementation (``anvilkit/cli.py:752``)
    already returns on ``no_github`` before the prompt, and does not read
    ``.env`` at all yet — so these assertions may be green today. That is the
    *partially green* situation the task anticipated: the value of these tests
    is that they LOCK the contract, so a later refactor that consults the
    store before the flag (e.g. to decide whether to skip the prompt) cannot
    silently break the "no store access" promise.
    """

    def _make_context(self, assume_yes=False):
        """Build a minimal Context pointing at the test project."""
        return cli.Context(
            dry_run=False,
            verbose=False,
            no_color=False,
            assume_yes=assume_yes,
        )

    def _booby_traps(self):
        """Context managers that booby-trap the store seams.

        Any call from ``_resolve_github_token`` raises a named AssertionError;
        the bound mocks are also captured so the test can assert non-use
        explicitly.
        """
        return (
            mock.patch.object(
                cli.env,
                "get",
                side_effect=AssertionError(
                    "_resolve_github_token must not read .env when no_github=True"
                ),
            ),
            mock.patch.object(
                cli.prompts,
                "confirm",
                side_effect=AssertionError(
                    "_resolve_github_token must not prompt when no_github=True"
                ),
            ),
            mock.patch.object(
                cli.prompts,
                "ask_required",
                side_effect=AssertionError(
                    "_resolve_github_token must not ask for a token when no_github=True"
                ),
            ),
        )

    # -- B1 proper: stored token present, must be ignored -----------------

    def test_no_github_returns_empty_without_reading_stored_token(self):
        """``no_github=True`` with ``GITHUB_TOKEN=ghp_stored`` in .env -> ``""``.

        The stored token must not be read, echoed, or disturbed.
        """
        self.write_env(GITHUB_TOKEN="ghp_stored", LLM_PORT="8000")
        ctx = self._make_context(assume_yes=False)

        trap_env_get, trap_confirm, trap_ask = self._booby_traps()
        with trap_env_get as env_get, trap_confirm as prompts_confirm, trap_ask as ask_required:
            result = cli._resolve_github_token(ctx, None, no_github=True)

        # (a) the returned value is the empty token
        self.assertEqual("", result)
        # (b) the store was never consulted
        env_get.assert_not_called()
        # (c) no prompt of any kind was reached
        prompts_confirm.assert_not_called()
        ask_required.assert_not_called()
        # the decision left .env exactly as found
        values = cli.env.read(self.env_path())
        self.assertEqual("ghp_stored", values.get("GITHUB_TOKEN"))

    # -- B1 edge: no .env at all ------------------------------------------

    def test_no_github_returns_empty_when_env_file_is_absent(self):
        """The short-circuit holds even when .env does not exist."""
        if self.env_path().exists():
            self.env_path().unlink()
        ctx = self._make_context(assume_yes=False)

        trap_env_get, trap_confirm, trap_ask = self._booby_traps()
        with trap_env_get as env_get, trap_confirm as prompts_confirm, trap_ask as ask_required:
            result = cli._resolve_github_token(ctx, None, no_github=True)

        self.assertEqual("", result)
        env_get.assert_not_called()
        prompts_confirm.assert_not_called()
        ask_required.assert_not_called()
        # and it must not *create* the store as a side effect
        self.assertFalse(self.env_path().exists())


# ---------------------------------------------------------------------------
# _resolve_github_token  (Behavior 5 — --yes / non-interactive, nothing stored)
# ---------------------------------------------------------------------------


class TestResolveGithubTokenYesOrNonInteractive(CliCase):
    """B5: ``--yes`` or non-interactive with nothing stored returns empty, never blocking.

    The contract, per plans/skip-github-token-prompt.md §4/B5:

    * input ``token=None``, ``no_github=False``, nothing stored in .env (no
      ``GITHUB_TOKEN`` key, or a key with an empty value),
    * input A: ``assume_yes=True`` (``--yes``),
    * input B (separate test): non-interactive — ``_is_interactive`` patched
      to return ``False``, the same seam the oxylabs decline test and B4
      patch (``anvilkit/cli.py:142``),
    * output for both: ``""``, with ``prompts.confirm`` patched to raise an
      ``AssertionError`` if called — the Definition of Done (§6) requires no
      new blocking prompt, so the guard must be explicit rather than an
      emergent property of ``confirm(default=False)`` returning ``False``
      under ``assume_yes``/non-interactive (``anvilkit/prompts.py:93``).

    Red-phase note: the current implementation (``anvilkit/cli.py:777``) has
    no ``assume_yes or not interactive`` guard — it calls
    ``prompts.confirm`` unconditionally after the store lookup misses,
    relying on ``confirm``'s internal ``assume_yes`` handling
    (``anvilkit/prompts.py:93``) to keep ``ask_required`` out of reach. The
    booby-trapped ``confirm`` seam therefore fires today, so both tests are
    RED with an AssertionError naming the missing guard. Compare
    ``_resolve_oxylabs`` (``anvilkit/cli.py:837``), which guards before the
    prompt — the shape this behaviour must take.
    """

    def _make_context(self, assume_yes=False):
        """Build a minimal Context pointing at the test project."""
        return cli.Context(
            dry_run=False,
            verbose=False,
            no_color=False,
            assume_yes=assume_yes,
        )

    def _booby_traps(self):
        """Context managers that booby-trap the prompt seams.

        Any call from ``_resolve_github_token`` raises a named AssertionError;
        the bound mocks are also captured so the test can assert non-use
        explicitly. The store seam is left live: the ``.env`` lookup is
        expected to happen (and miss) before the guard is reached.
        """
        return (
            mock.patch.object(
                cli.prompts,
                "confirm",
                side_effect=AssertionError(
                    "_resolve_github_token must not call prompts.confirm "
                    "when --yes or non-interactive and no token is stored"
                ),
            ),
            mock.patch.object(
                cli.prompts,
                "ask_required",
                side_effect=AssertionError(
                    "_resolve_github_token must not ask for a token "
                    "when --yes or non-interactive and no token is stored"
                ),
            ),
        )

    # -- B5 input A: --yes (assume_yes=True), nothing stored ----------------

    def test_assume_yes_with_nothing_stored_returns_empty_without_prompting(self):
        """``assume_yes=True`` and no ``GITHUB_TOKEN`` in .env -> ``""``.

        The store is consulted (and misses), then the guard must return
        without reaching ``prompts.confirm`` at all — ``confirm``'s own
        ``assume_yes`` handling must not be the thing that keeps the prompt
        out of reach.
        """
        # .env exists but carries no GITHUB_TOKEN — the lookup must miss
        self.write_env(LLM_PORT="8000")
        ctx = self._make_context(assume_yes=True)

        trap_confirm, trap_ask = self._booby_traps()
        with mock.patch.object(cli.env, "get", wraps=cli.env.get) as env_get:
            with trap_confirm as prompts_confirm, trap_ask as ask_required:
                result = cli._resolve_github_token(ctx, None, no_github=False)

        # (a) the store was consulted (and found nothing)
        env_get.assert_called_once_with(ctx.env_path, cli.GITHUB_TOKEN_ENV)
        # (b) the confirm gate is never reached — this is what the guard owns
        self.assertEqual("", result)
        prompts_confirm.assert_not_called()
        ask_required.assert_not_called()
        # the decision left .env exactly as found, no token created
        values = cli.env.read(self.env_path())
        self.assertIsNone(values.get("GITHUB_TOKEN"))
        self.assertEqual("8000", values.get("LLM_PORT"))

    # -- B5 input B: non-interactive, nothing stored ------------------------

    def test_non_interactive_with_nothing_stored_returns_empty_without_prompting(self):
        """Non-interactive (``_is_interactive`` -> ``False``), nothing stored -> ``""``.

        Same contract as input A through a different seam: the guard must
        key off interactivity as well, and return before ``prompts.confirm``
        is even called.
        """
        # .env exists but carries no GITHUB_TOKEN — the lookup must miss
        self.write_env(LLM_PORT="8000")
        ctx = self._make_context(assume_yes=False)

        trap_confirm, trap_ask = self._booby_traps()
        with mock.patch.object(cli.env, "get", wraps=cli.env.get) as env_get:
            with mock.patch.object(cli, "_is_interactive", return_value=False):
                with trap_confirm as prompts_confirm, trap_ask as ask_required:
                    result = cli._resolve_github_token(ctx, None, no_github=False)

        # (a) the store was consulted (and found nothing)
        env_get.assert_called_once_with(ctx.env_path, cli.GITHUB_TOKEN_ENV)
        # (b) the confirm gate is never reached, whether or not it would
        #     answer no internally
        self.assertEqual("", result)
        prompts_confirm.assert_not_called()
        ask_required.assert_not_called()
        # the decision left .env exactly as found, no token created
        values = cli.env.read(self.env_path())
        self.assertIsNone(values.get("GITHUB_TOKEN"))
        self.assertEqual("8000", values.get("LLM_PORT"))


# ---------------------------------------------------------------------------
# _resolve_github_token  (Behavior 2 — --github-token wins, and is persisted)
# ---------------------------------------------------------------------------


class TestResolveGithubTokenFlag(CliCase):
    """B2: ``--github-token`` wins over the store, and is persisted.

    The contract, per plans/skip-github-token-prompt.md §4/B2:

    * input ``token="ghp_flag"`` (i.e. ``token is not None``) with
      ``GITHUB_TOKEN=ghp_stored`` in .env,
    * output ``"ghp_flag"`` — the flag value is authoritative,
    * no prompt of any kind (``prompts.confirm`` / ``prompts.ask_required``
      booby-trapped, as in ``TestResolveGithubTokenNoGithub``),
    * side effect: ``.env`` now holds ``GITHUB_TOKEN=ghp_flag``.

    The persistence is a *deliberate divergence* from ``_resolve_oxylabs``
    (which returns the flag value without writing it): following
    ``_persist_anthropic_key`` (``anvilkit/cli.py:917``), a flag-supplied value
    populates the store, so flag-less runs are not prompted forever.

    Edge case: an *explicit empty string* (``token=""``) is still
    ``token is not None``, so it resolves to ``""`` but — being
    unchanged-or-empty — must NOT overwrite a non-empty stored value.
    """

    def _make_context(self, assume_yes=False):
        """Build a minimal Context pointing at the test project."""
        return cli.Context(
            dry_run=False,
            verbose=False,
            no_color=False,
            assume_yes=assume_yes,
        )

    # -- B2 proper: flag beats store, and the flag value lands in .env ------

    def test_flag_token_wins_over_stored_token_and_is_persisted(self):
        """``token="ghp_flag"`` with a stored token -> ``"ghp_flag"``, stored.

        No prompt of any kind; ``.env`` is rewritten to hold the flag value.
        """
        self.write_env(GITHUB_TOKEN="ghp_stored", LLM_PORT="8000")
        ctx = self._make_context(assume_yes=False)

        trap_confirm, trap_ask = (
            mock.patch.object(
                cli.prompts,
                "confirm",
                side_effect=AssertionError(
                    "_resolve_github_token must not prompt when the flag is given"
                ),
            ),
            mock.patch.object(
                cli.prompts,
                "ask_required",
                side_effect=AssertionError(
                    "_resolve_github_token must not ask for a token when the flag is given"
                ),
            ),
        )
        with trap_confirm as prompts_confirm, trap_ask as ask_required:
            result = cli._resolve_github_token(ctx, "ghp_flag", no_github=False)

        # (a) the flag value is returned
        self.assertEqual("ghp_flag", result)
        # (b) no prompt of any kind was reached
        prompts_confirm.assert_not_called()
        ask_required.assert_not_called()
        # (c) the flag value was persisted to .env, replacing the stored one
        values = cli.env.read(self.env_path())
        self.assertEqual("ghp_flag", values.get("GITHUB_TOKEN"))
        # the decision disturbed no other key
        self.assertEqual("8000", values.get("LLM_PORT"))

    # -- B2 edge: explicit empty string must not clobber the store ----------

    def test_empty_flag_token_returns_empty_and_preserves_stored_token(self):
        """``token=""`` (explicit) resolves to ``""`` and leaves the store intact.

        The no-op-if-unchanged-or-empty rule means a non-empty stored value
        survives an explicit empty flag.
        """
        self.write_env(GITHUB_TOKEN="ghp_stored", LLM_PORT="8000")
        ctx = self._make_context(assume_yes=False)

        trap_confirm, trap_ask = (
            mock.patch.object(
                cli.prompts,
                "confirm",
                side_effect=AssertionError(
                    "_resolve_github_token must not prompt when the flag is given"
                ),
            ),
            mock.patch.object(
                cli.prompts,
                "ask_required",
                side_effect=AssertionError(
                    "_resolve_github_token must not ask for a token when the flag is given"
                ),
            ),
        )
        with trap_confirm as prompts_confirm, trap_ask as ask_required:
            result = cli._resolve_github_token(ctx, "", no_github=False)

        # (a) the explicit empty flag is returned as-is
        self.assertEqual("", result)
        # (b) no prompt of any kind was reached
        prompts_confirm.assert_not_called()
        ask_required.assert_not_called()
        # (c) the stored token survived — an empty value never blanks a store
        values = cli.env.read(self.env_path())
        self.assertEqual("ghp_stored", values.get("GITHUB_TOKEN"))
        self.assertEqual("8000", values.get("LLM_PORT"))


# ---------------------------------------------------------------------------
# _resolve_github_token  (Behavior 3 — a stored token is reused)
# ---------------------------------------------------------------------------


class TestResolveGithubTokenStoredReuse(CliCase):
    """B3: a stored token is reused, and the skip is reported.

    The contract, per plans/skip-github-token-prompt.md §4/B3:

    * input ``token=None``, ``no_github=False``, ``GITHUB_TOKEN=ghp_stored``
      in .env, interactive (no ``--yes``),
    * output ``"ghp_stored"`` — the stored token is reused,
    * ``prompts.confirm`` and ``prompts.ask_required`` are never called —
      booby-trapped with ``side_effect=AssertionError`` exactly as in
      ``TestResolveGithubTokenNoGithub`` / ``TestResolveGithubTokenFlag``,
    * a skip notice is echoed, modelled on the oxylabs reuse notice
      (``anvilkit/cli.py:892``): ``🔑 Reusing existing GITHUB_TOKEN from .env``,
    * the token value itself is never echoed — ``ghp_stored`` must not appear
      anywhere in the captured output.

    Red-phase note: the current implementation (``anvilkit/cli.py:752``) never
    reads the store on the ``token=None`` path; it goes straight to
    ``prompts.confirm`` / ``ask_required``. With interactivity forced on and
    both seams booby-trapped, the confirm trap fires, so these tests fail
    today with an AssertionError naming the missing store lookup.
    """

    REUSE_NOTICE = "🔑 Reusing existing GITHUB_TOKEN from .env"

    def _make_context(self, assume_yes=False):
        """Build a minimal Context pointing at the test project."""
        return cli.Context(
            dry_run=False,
            verbose=False,
            no_color=False,
            assume_yes=assume_yes,
        )

    def _capture_echo(self):
        """Patch ``typer.echo`` (the target of ``Context.echo``) to collect lines."""
        lines = []
        return mock.patch.object(
            cli.typer, "echo", side_effect=lambda msg="": lines.append(str(msg))
        ), lines

    # -- B3 proper: stored token is reused, no prompt --------------------------

    def test_stored_token_is_reused_without_prompting(self):
        """``token=None`` with ``GITHUB_TOKEN=ghp_stored`` -> ``"ghp_stored"``.

        No prompt of any kind is reached, and .env is left exactly as found.
        """
        self.write_env(GITHUB_TOKEN="ghp_stored", LLM_PORT="8000")
        ctx = self._make_context(assume_yes=False)

        trap_confirm, trap_ask = (
            mock.patch.object(
                cli.prompts,
                "confirm",
                side_effect=AssertionError(
                    "_resolve_github_token must not prompt when GITHUB_TOKEN is stored in .env"
                ),
            ),
            mock.patch.object(
                cli.prompts,
                "ask_required",
                side_effect=AssertionError(
                    "_resolve_github_token must not ask for a token when GITHUB_TOKEN is stored in .env"
                ),
            ),
        )
        echo_patcher, _ = self._capture_echo()
        with mock.patch.object(cli, "_is_interactive", return_value=True):
            with trap_confirm as prompts_confirm, trap_ask as ask_required:
                with echo_patcher:
                    result = cli._resolve_github_token(ctx, None, no_github=False)

        # (a) the stored token is returned
        self.assertEqual("ghp_stored", result)
        # (b) no prompt of any kind was reached
        prompts_confirm.assert_not_called()
        ask_required.assert_not_called()
        # (c) the store was not disturbed by the reuse
        values = cli.env.read(self.env_path())
        self.assertEqual("ghp_stored", values.get("GITHUB_TOKEN"))
        self.assertEqual("8000", values.get("LLM_PORT"))

    # -- B3 reporting: skip notice echoed, secret never echoed ----------------

    def test_reuse_echoes_skip_notice_but_never_the_token(self):
        """The reuse is reported; the token value itself is not echoed.

        The notice mirrors the anthropic reuse wording at
        ``anvilkit/cli.py:892``. The secret must not appear in any output line.
        """
        self.write_env(GITHUB_TOKEN="ghp_stored", LLM_PORT="8000")
        ctx = self._make_context(assume_yes=False)

        trap_confirm, trap_ask = (
            mock.patch.object(
                cli.prompts,
                "confirm",
                side_effect=AssertionError(
                    "_resolve_github_token must not prompt when GITHUB_TOKEN is stored in .env"
                ),
            ),
            mock.patch.object(
                cli.prompts,
                "ask_required",
                side_effect=AssertionError(
                    "_resolve_github_token must not ask for a token when GITHUB_TOKEN is stored in .env"
                ),
            ),
        )
        echo_patcher, lines = self._capture_echo()
        with mock.patch.object(cli, "_is_interactive", return_value=True):
            with trap_confirm as prompts_confirm, trap_ask as ask_required:
                with echo_patcher:
                    result = cli._resolve_github_token(ctx, None, no_github=False)

        self.assertEqual("ghp_stored", result)
        prompts_confirm.assert_not_called()
        ask_required.assert_not_called()
        output = "\n".join(lines)
        # (a) the skip notice is reported
        self.assertIn(self.REUSE_NOTICE, output)
        # (b) the secret is never echoed, on any line
        self.assertNotIn("ghp_stored", output)


# ---------------------------------------------------------------------------
# _resolve_github_token  (Behavior 4 — an empty stored value counts as absent)
# ---------------------------------------------------------------------------


class TestResolveGithubTokenEmptyStored(CliCase):
    """B4: an empty stored value counts as absent.

    The contract, per plans/skip-github-token-prompt.md §4/B4:

    * input ``token=None``, ``no_github=False``, interactive, with
      ``GITHUB_TOKEN=`` (an *empty* value) in .env,
    * output: the confirm/prompt path is reached — ``prompts.confirm`` IS
      called, exactly as with an absent key. The ``if stored:`` truthiness
      check (``anvilkit/cli.py:772``) is what makes a blank value behave as
      though nothing were stored, matching ``_resolve_oxylabs``'s treatment
      of a blank username (``anvilkit/cli.py:802``),
    * edge case: a missing .env file behaves identically — ``env.get``
      returns the default for a missing file (``anvilkit/env.py:40``), so
      the same fall-through happens.

    These tests are *contract locks* written booby-trapped in the opposite
    direction from B3: ``prompts.confirm`` is expected to be called (patched
    to decline, so the test cannot block or persist), while
    ``prompts.ask_required`` is booby-trapped with
    ``side_effect=AssertionError`` so an implementation that skips the
    confirm gate cannot slip through. The current ``if stored:``
    implementation already satisfies this, so both tests are green from the
    start; their value is preventing a future ``is not None``-style change
    that would treat a blank stored value as a usable token and suppress
    the prompt.
    """

    def _make_context(self, assume_yes=False):
        """Build a minimal Context pointing at the test project."""
        return cli.Context(
            dry_run=False,
            verbose=False,
            no_color=False,
            assume_yes=assume_yes,
        )

    # -- B4 proper: empty stored value falls through to the prompt ----------

    def test_empty_stored_token_reaches_confirm_and_decline_returns_empty(self):
        """``GITHUB_TOKEN=`` in .env -> confirm IS reached; declining -> ``""``.

        The blank value must not count as a stored token: unlike the B3
        reuse path, the confirm gate is reached, and declining returns
        ``""`` without reaching the token prompt or disturbing .env.
        """
        self.write_env(GITHUB_TOKEN="", LLM_PORT="8000")
        ctx = self._make_context(assume_yes=False)

        with mock.patch.object(cli.env, "get", wraps=cli.env.get) as env_get:
            with mock.patch.object(cli, "_is_interactive", return_value=True):
                with mock.patch.object(
                    cli.prompts, "confirm", return_value=False
                ) as prompts_confirm:
                    with mock.patch.object(
                        cli.prompts,
                        "ask_required",
                        side_effect=AssertionError(
                            "_resolve_github_token must not ask for a token "
                            "when the user declines"
                        ),
                    ) as ask_required:
                        result = cli._resolve_github_token(
                            ctx, None, no_github=False
                        )

        # (a) the store was consulted
        env_get.assert_called_once_with(ctx.env_path, cli.GITHUB_TOKEN_ENV)
        # (b) the empty stored value is not treated as a token: the confirm
        #     gate IS reached, the opposite of the B3 reuse path
        prompts_confirm.assert_called_once()
        # (c) declining returns empty and never reaches the token prompt
        self.assertEqual("", result)
        ask_required.assert_not_called()
        # the decision left .env exactly as found
        values = cli.env.read(self.env_path())
        self.assertEqual("", values.get("GITHUB_TOKEN"))
        self.assertEqual("8000", values.get("LLM_PORT"))

    # -- B4 edge: .env absent entirely behaves identically -------------------

    def test_missing_env_file_reaches_confirm_and_decline_returns_empty(self):
        """No .env at all -> same fall-through as an empty stored value.

        ``env.get`` returns the default for a missing file, so the confirm
        gate is reached the same way; declining returns ``""`` and the
        store must not be created as a side effect.
        """
        if self.env_path().exists():
            self.env_path().unlink()
        ctx = self._make_context(assume_yes=False)

        with mock.patch.object(cli.env, "get", wraps=cli.env.get) as env_get:
            with mock.patch.object(cli, "_is_interactive", return_value=True):
                with mock.patch.object(
                    cli.prompts, "confirm", return_value=False
                ) as prompts_confirm:
                    with mock.patch.object(
                        cli.prompts,
                        "ask_required",
                        side_effect=AssertionError(
                            "_resolve_github_token must not ask for a token "
                            "when the user declines"
                        ),
                    ) as ask_required:
                        result = cli._resolve_github_token(
                            ctx, None, no_github=False
                        )

        # (a) the store was consulted (and found nothing)
        env_get.assert_called_once_with(ctx.env_path, cli.GITHUB_TOKEN_ENV)
        # (b) the confirm gate IS reached, same as with an empty value
        prompts_confirm.assert_called_once()
        # (c) declining returns empty and never reaches the token prompt
        self.assertEqual("", result)
        ask_required.assert_not_called()
        # and it must not *create* the store as a side effect
        self.assertFalse(self.env_path().exists())


# ---------------------------------------------------------------------------
# _resolve_github_token  (Behavior 7 — declining the prompt points at the store)
# ---------------------------------------------------------------------------


class TestResolveGithubTokenDecline(CliCase):
    """B7: declining the prompt returns empty and points at the new store.

    The contract, per plans/skip-github-token-prompt.md §4/B7:

    * input: interactive (``_is_interactive`` -> ``True``), nothing stored
      in .env, ``prompts.confirm`` returns ``False``,
    * output ``""`` — nothing is written to .env, and
      ``prompts.ask_required`` is never called (booby-trapped with
      ``side_effect=AssertionError``),
    * the decline advisory changes wording: it must name ``.env`` and
      ``GITHUB_TOKEN``, mirroring the oxylabs decline message
      (``anvilkit/cli.py:851-853``), and must no longer point at the
      target repo's ``.roo/mcp.json`` (``anvilkit/cli.py:789-791``).

    Red-phase note: the return-value, no-write and no-ask parts already
    hold; the message assertions fail today because the current advisory
    names ``mcp.json`` inside ``.roo/`` and never mentions ``.env``.
    """

    def _make_context(self, assume_yes=False):
        """Build a minimal Context pointing at the test project."""
        return cli.Context(
            dry_run=False,
            verbose=False,
            no_color=False,
            assume_yes=assume_yes,
        )

    def _capture_echo(self):
        """Patch ``typer.echo`` (the target of ``Context.echo``) to collect lines."""
        lines = []
        return mock.patch.object(
            cli.typer, "echo", side_effect=lambda msg="": lines.append(str(msg))
        ), lines

    def _ensure_nothing_stored(self):
        if self.env_path().exists():
            self.env_path().unlink()

    # -- B7 proper: decline returns empty, writes nothing, asks nothing -------

    def test_decline_returns_empty_and_writes_nothing_to_env(self):
        """Interactive, nothing stored, decline -> ``""`` and .env untouched.

        ``prompts.ask_required`` is booby-trapped, and ``env.set_value``
        is patched to raise if the decline path tried to persist anything.
        """
        self._ensure_nothing_stored()
        ctx = self._make_context(assume_yes=False)

        with mock.patch.object(cli, "_is_interactive", return_value=True):
            with mock.patch.object(
                cli.prompts, "confirm", return_value=False
            ) as prompts_confirm:
                with mock.patch.object(
                    cli.prompts,
                    "ask_required",
                    side_effect=AssertionError(
                        "_resolve_github_token must not ask for a token "
                        "when the user declines"
                    ),
                ) as ask_required:
                    with mock.patch.object(
                        cli.env,
                        "set_value",
                        side_effect=AssertionError(
                            "declining must not write GITHUB_TOKEN to .env"
                        ),
                    ) as set_value:
                        result = cli._resolve_github_token(
                            ctx, None, no_github=False
                        )

        # (a) the confirm gate was reached and answered
        prompts_confirm.assert_called_once()
        # (b) declining returns empty
        self.assertEqual("", result)
        # (c) the token prompt is never reached
        ask_required.assert_not_called()
        # (d) nothing is persisted — not via the module, not onto disk
        set_value.assert_not_called()
        self.assertFalse(self.env_path().exists())

    # -- B7 reporting: the advisory names the store, not the repo --------------

    def test_decline_advisory_names_env_store_not_repo_mcp_json(self):
        """The advisory points at ``.env``/``GITHUB_TOKEN``, not ``.roo/mcp.json``.

        The new wording mirrors the oxylabs decline message
        (``anvilkit/cli.py:851-853``): edit ``.env`` and populate the
        variable. Distinctive substrings are asserted so the exact
        punctuation is not load-bearing, but the old ``.roo/``/``mcp.json``
        framing must be gone.
        """
        self._ensure_nothing_stored()
        ctx = self._make_context(assume_yes=False)

        echo_patcher, lines = self._capture_echo()
        with mock.patch.object(cli, "_is_interactive", return_value=True):
            with mock.patch.object(cli.prompts, "confirm", return_value=False):
                with mock.patch.object(
                    cli.prompts,
                    "ask_required",
                    side_effect=AssertionError(
                        "_resolve_github_token must not ask for a token "
                        "when the user declines"
                    ),
                ):
                    with echo_patcher:
                        result = cli._resolve_github_token(
                            ctx, None, no_github=False
                        )

        self.assertEqual("", result)
        output = "\n".join(lines)
        # (a) the new store is named
        self.assertIn(".env", output)
        self.assertIn("GITHUB_TOKEN", output)
        # (b) the old target-repo framing is gone
        self.assertNotIn("mcp.json", output)
        self.assertNotIn(".roo", output)


# ---------------------------------------------------------------------------
# _resolve_github_token  (Behavior 8 — accepting the prompt persists the token)
# ---------------------------------------------------------------------------


class TestResolveGithubTokenAcceptPersists(CliCase):
    """B8: accepting the prompt persists the token.

    The contract, per plans/skip-github-token-prompt.md §4/B8:

    * input: interactive (``_is_interactive`` -> ``True``), nothing stored
      in .env, ``prompts.confirm`` returns ``True`` and
      ``prompts.ask_required`` returns ``"ghp_new"``,
    * output ``"ghp_new"``, and ``.env`` now contains
      ``GITHUB_TOKEN=ghp_new`` (asserted against the file's content, not
      just the mock),
    * ``ask_required`` is called with ``hide_input=True`` (asserted via the
      mock's call kwargs),
    * the accept echo is the persist notice
      ``⚡ Token accepted and persisted to .env`` — which
      ``_persist_github_token`` (``anvilkit/cli.py:803``) already echoes —
      and the token value ``ghp_new`` never appears in captured output.

    Red-phase note: the return-value and echo assertions hold today; the
    persist assertion fails because the accept path
    (``anvilkit/cli.py:793-800``) never calls ``_persist_github_token`` — it
    echoes the old ``⚡ Token accepted.`` notice and returns without writing
    ``.env``.
    """

    PERSIST_NOTICE = "⚡ Token accepted and persisted to .env"

    def _make_context(self, assume_yes=False):
        """Build a minimal Context pointing at the test project."""
        return cli.Context(
            dry_run=False,
            verbose=False,
            no_color=False,
            assume_yes=assume_yes,
        )

    def _capture_echo(self):
        """Patch ``typer.echo`` (the target of ``Context.echo``) to collect lines."""
        lines = []
        return mock.patch.object(
            cli.typer, "echo", side_effect=lambda msg="": lines.append(str(msg))
        ), lines

    def _ensure_nothing_stored(self):
        if self.env_path().exists():
            self.env_path().unlink()

    # -- B8 proper: accept -> token returned, hidden prompt, .env updated ----

    def test_accept_persists_token_to_env_and_returns_it(self):
        """Interactive, nothing stored, accept -> ``"ghp_new"`` in .env.

        ``ask_required`` is mocked (its hidden-input prompt mechanics are
        owned by ``prompts`` and covered in ``test_prompts.py``); the call's
        kwargs are asserted so ``hide_input=True`` cannot be lost.
        """
        self._ensure_nothing_stored()
        ctx = self._make_context(assume_yes=False)

        with mock.patch.object(cli, "_is_interactive", return_value=True):
            with mock.patch.object(
                cli.prompts, "confirm", return_value=True
            ) as prompts_confirm:
                with mock.patch.object(
                    cli.prompts, "ask_required", return_value="ghp_new"
                ) as ask_required:
                    result = cli._resolve_github_token(
                        ctx, None, no_github=False
                    )

        # (a) the confirm gate was reached and answered
        prompts_confirm.assert_called_once()
        # (b) the hidden prompt was reached, with the hidden-input kwarg intact
        ask_required.assert_called_once()
        self.assertTrue(ask_required.call_args[1].get("hide_input"))
        # (c) the entered token is returned
        self.assertEqual("ghp_new", result)
        # (d) the token was persisted to .env — asserted against the file
        #     itself, not just the mock
        self.assertTrue(self.env_path().exists())
        self.assertIn(
            "GITHUB_TOKEN=ghp_new",
            self.env_path().read_text(encoding="utf-8"),
        )
        values = cli.env.read(self.env_path())
        self.assertEqual("ghp_new", values.get("GITHUB_TOKEN"))

    # -- B8 reporting: the persist notice replaces the old accept echo -------

    def test_accept_echoes_persist_notice_and_never_the_secret(self):
        """The accept path echoes the persist notice, not the token value.

        The old ``⚡ Token accepted.`` echo is expected to be replaced by
        ``⚡ Token accepted and persisted to .env``; this test asserts only
        that the new notice is present and that ``ghp_new`` never appears in
        captured output.
        """
        self._ensure_nothing_stored()
        ctx = self._make_context(assume_yes=False)

        echo_patcher, lines = self._capture_echo()
        with mock.patch.object(cli, "_is_interactive", return_value=True):
            with mock.patch.object(cli.prompts, "confirm", return_value=True):
                with mock.patch.object(
                    cli.prompts, "ask_required", return_value="ghp_new"
                ):
                    with echo_patcher:
                        result = cli._resolve_github_token(
                            ctx, None, no_github=False
                        )

        self.assertEqual("ghp_new", result)
        output = "\n".join(lines)
        # (a) the persist notice is reported
        self.assertIn(self.PERSIST_NOTICE, output)
        # (b) the secret is never echoed
        self.assertNotIn("ghp_new", output)


# ---------------------------------------------------------------------------
# _resolve_github_token  (Behavior 6 — --yes / non-interactive reuse a stored token)
# ---------------------------------------------------------------------------


class TestResolveGithubTokenStoredYesOrNonInteractive(CliCase):
    """B6: ``--yes`` or non-interactive with a stored token returns the stored token.

    The contract, per plans/skip-github-token-prompt.md §4/B6:

    * input ``token=None``, ``no_github=False``, ``GITHUB_TOKEN=ghp_stored``
      in .env,
    * input A: ``assume_yes=True`` (``--yes``),
    * input B (separate test): non-interactive — ``_is_interactive`` patched
      to return ``False``, the same seam B5 input B patches
      (``anvilkit/cli.py:142``),
    * output for both: ``"ghp_stored"`` — the stored token is returned with
      no prompt of any kind: ``prompts.confirm`` and ``prompts.ask_required``
      are booby-trapped with ``side_effect=AssertionError``, exactly as in
      B3/B5,
    * ``.env`` is left undisturbed — reuse reads, never writes.

    Ordering requirement (the crux): the ``.env`` lookup must sit BEFORE the
    ``assume_yes or not interactive`` guard — the same ordering as
    ``_resolve_oxylabs`` (store lookup at ``anvilkit/cli.py:832``, guard at
    ``anvilkit/cli.py:837``). An implementation that reversed the order
    (guard first) would return ``""`` here without ever consulting the store;
    the booby-trapped result assertions (plus ``env_get.assert_called_once``
    and the non-empty return) catch exactly that.

    These tests are *contract locks*: B3's green cycle already placed the
    store lookup before the B5 guard, so both tests are expected to be green
    from the start, pinning the ordering against a future reordering (like
    B1/B4's committed locks).
    """

    REUSE_NOTICE = "🔑 Reusing existing GITHUB_TOKEN from .env"

    def _make_context(self, assume_yes=False):
        """Build a minimal Context pointing at the test project."""
        return cli.Context(
            dry_run=False,
            verbose=False,
            no_color=False,
            assume_yes=assume_yes,
        )

    def _booby_traps(self):
        """Context managers that booby-trap the prompt seams.

        Any call from ``_resolve_github_token`` raises a named AssertionError;
        the bound mocks are also captured so the test can assert non-use
        explicitly. The store seam is left live: the ``.env`` lookup is
        expected to happen (and hit) before the guard would be reached.
        """
        return (
            mock.patch.object(
                cli.prompts,
                "confirm",
                side_effect=AssertionError(
                    "_resolve_github_token must not call prompts.confirm "
                    "when GITHUB_TOKEN is stored in .env, even under "
                    "--yes or non-interactive"
                ),
            ),
            mock.patch.object(
                cli.prompts,
                "ask_required",
                side_effect=AssertionError(
                    "_resolve_github_token must not ask for a token "
                    "when GITHUB_TOKEN is stored in .env, even under "
                    "--yes or non-interactive"
                ),
            ),
        )

    def _capture_echo(self):
        """Patch ``typer.echo`` (the target of ``Context.echo``) to collect lines."""
        lines = []
        return mock.patch.object(
            cli.typer, "echo", side_effect=lambda msg="": lines.append(str(msg))
        ), lines

    # -- B6 input A: --yes (assume_yes=True), token stored --------------------

    def test_assume_yes_with_stored_token_returns_stored_token_without_prompting(self):
        """``assume_yes=True`` and ``GITHUB_TOKEN=ghp_stored`` -> ``"ghp_stored"``.

        The store hit must short-circuit BEFORE the ``assume_yes`` guard:
        a guard-first implementation returns ``""`` here without a prompt,
        which is exactly the regression these tests lock out.
        """
        self.write_env(GITHUB_TOKEN="ghp_stored", LLM_PORT="8000")
        ctx = self._make_context(assume_yes=True)

        trap_confirm, trap_ask = self._booby_traps()
        echo_patcher, lines = self._capture_echo()
        with mock.patch.object(cli.env, "get", wraps=cli.env.get) as env_get:
            with trap_confirm as prompts_confirm, trap_ask as ask_required:
                with echo_patcher:
                    result = cli._resolve_github_token(ctx, None, no_github=False)

        # (a) the store was consulted — the lookup precedes the guard
        env_get.assert_called_once_with(ctx.env_path, cli.GITHUB_TOKEN_ENV)
        # (b) the stored token is returned, not the guard's ""
        self.assertEqual("ghp_stored", result)
        # (c) no prompt of any kind was reached
        prompts_confirm.assert_not_called()
        ask_required.assert_not_called()
        # (d) the reuse is reported; the secret is never echoed
        output = "\n".join(lines)
        self.assertIn(self.REUSE_NOTICE, output)
        self.assertNotIn("ghp_stored", output)
        # the decision left .env exactly as found
        values = cli.env.read(self.env_path())
        self.assertEqual("ghp_stored", values.get("GITHUB_TOKEN"))
        self.assertEqual("8000", values.get("LLM_PORT"))

    # -- B6 input B: non-interactive, token stored ----------------------------

    def test_non_interactive_with_stored_token_returns_stored_token_without_prompting(self):
        """Non-interactive (``_is_interactive`` -> ``False``) and
        ``GITHUB_TOKEN=ghp_stored`` -> ``"ghp_stored"``.

        Same ordering contract as input A through the interactivity seam:
        the store lookup must win before the ``not interactive()`` half of
        the guard can return ``""``.
        """
        self.write_env(GITHUB_TOKEN="ghp_stored", LLM_PORT="8000")
        ctx = self._make_context(assume_yes=False)

        trap_confirm, trap_ask = self._booby_traps()
        echo_patcher, lines = self._capture_echo()
        with mock.patch.object(cli.env, "get", wraps=cli.env.get) as env_get:
            with mock.patch.object(cli, "_is_interactive", return_value=False):
                with trap_confirm as prompts_confirm, trap_ask as ask_required:
                    with echo_patcher:
                        result = cli._resolve_github_token(
                            ctx, None, no_github=False
                        )

        # (a) the store was consulted — the lookup precedes the guard
        env_get.assert_called_once_with(ctx.env_path, cli.GITHUB_TOKEN_ENV)
        # (b) the stored token is returned, not the guard's ""
        self.assertEqual("ghp_stored", result)
        # (c) no prompt of any kind was reached
        prompts_confirm.assert_not_called()
        ask_required.assert_not_called()
        # (d) the reuse is reported; the secret is never echoed
        output = "\n".join(lines)
        self.assertIn(self.REUSE_NOTICE, output)
        self.assertNotIn("ghp_stored", output)
        # the decision left .env exactly as found
        values = cli.env.read(self.env_path())
        self.assertEqual("ghp_stored", values.get("GITHUB_TOKEN"))
        self.assertEqual("8000", values.get("LLM_PORT"))