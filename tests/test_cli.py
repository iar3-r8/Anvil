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
from anvilkit import smoke  # noqa: E402
from anvilkit.pi import piruleset  # noqa: E402
# The six layer names in layer order, pinned by tests/test_smoke.py and
# imported (never re-spelled) so the two suites cannot drift.
from tests.test_smoke import LAYER_NAMES  # noqa: E402

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


# The five rule types build_ruleset writes, in the check_all report order
# (plans/verify-guards-five-rules.md, behaviour 8).
FIVE_RULE_NAMES = (
    "non_fast_forward",
    "deletion",
    "pull_request",
    "update",
    "file_path_restriction",
)


def five_rule_branch_rules():
    """The five rules build_ruleset writes, in the /rules/branches shape.

    The same translation as
    ``tests/test_piguard.RulesetWriteLockstepTests._fixture``: each element
    gains ``ruleset_source_type``, ``ruleset_source`` and ``ruleset_id``; the
    element's ``type`` and ``parameters`` are copied through unchanged into
    fresh dicts, so the ``build_ruleset()`` result is never mutated.
    """
    from anvilkit.pi import piruleset

    rules = []
    for element in piruleset.build_ruleset()["rules"]:
        fresh = {
            "type": element["type"],
            "ruleset_source_type": "repository",
            "ruleset_source": "main-protected",
            "ruleset_id": 1,
        }
        if "parameters" in element:
            fresh["parameters"] = dict(element["parameters"])
        rules.append(fresh)
    return rules


def token_finding(check, status, **extra):
    """A token-scope finding in the shape check_token_all returns.

    The CLI report tests build their fixtures through this so they pin the
    renderer's input - ``rule=None``, the check name, the status - rather
    than re-implementing a probe's output.
    """
    finding = {
        "check": check,
        "rule": None,
        "status": status,
        "danger": extra.get("danger", ""),
        "remedy": extra.get(
            "remedy",
            "doc/external/github/fine-grained-personal-access-tokens.md",
        ),
    }
    if status == "skipped":
        finding["reason"] = extra.get(
            "reason",
            "a token-scope probe with no token establishes no fact about any token",
        )
    return finding


def _finding_headline(finding):
    """The expected headline (first line) of a finding's block.

    The status maps to the marked prefix convention (✅ ok:/⚠️ warn:/
    ❌ fail:/⏭️ skipped: - the status mark, one space, then the existing
    prefix), and the label is the rule when the finding carries one,
    otherwise the check name - never a literal None (behaviour 19).
    """
    prefix = {
        "passed": "✅ ok",
        "warn": "⚠️ warn",
        "fail": "❌ fail",
        "skipped": "⏭️ skipped",
    }[finding.get("status")]
    label = finding.get("rule") or finding.get("check")
    return "{}: {}".format(prefix, label)


def assert_findings_reported_branch_then_token(
    lines, branch_findings, token_findings, full_output
):
    """Every branch-rule finding block and every token finding block is
    present, and the last branch block precedes the first token block
    (behaviour 19's order pin).

    A finding's block is located by its headline: the block's first line,
    which starts with the status prefix and the label (rule when present,
    else check). The detail and remedy lines are wrapped at 80 columns and
    may span multiple lines, so only the headline is a reliable anchor.
    """
    def index_of(finding):
        headline = _finding_headline(finding)
        for index, line in enumerate(lines):
            # The doctor's Guards section indents its lines; a block's
            # headline anchor must hold with or without that indent.
            if line.lstrip().startswith(headline):
                return index
        raise AssertionError(
            "finding block not reported; expected a line starting with "
            "{!r}\n{}".format(headline, full_output)
        )

    last_branch = max(index_of(f) for f in branch_findings)
    first_token = min(index_of(f) for f in token_findings)
    if last_branch >= first_token:
        raise AssertionError(
            "token finding blocks must be reported after the branch-rule "
            "finding blocks:\n{}".format(full_output)
        )


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
        "stress",
        "verify-guards",
        "smoke-test",
    )

    def registered_names(self):
        import click

        command = cli.typer.main.get_command(cli.app)
        self.assertIsInstance(command, click.Group)
        return set(command.commands)

    def test_all_expected_commands_are_registered(self):
        self.assertLessEqual(
            set(self.EXPECTED),
            self.registered_names(),
            "missing commands: {}".format(
                sorted(set(self.EXPECTED) - self.registered_names())
            ),
        )

    def test_no_unexpected_commands_are_registered(self):
        self.assertEqual(set(self.EXPECTED), self.registered_names())

    def test_help_lists_every_command(self):
        result = self.invoke(["--help"])
        self.assertEqual(0, result.exit_code)
        for name in self.EXPECTED:
            self.assertIn(name, result.output)

    def test_help_hints_at_per_command_help(self):
        """Root --help must point users to 'anvil <command> --help'."""
        result = self.invoke(["--help"])
        self.assertEqual(0, result.exit_code)
        self.assertIn(
            "anvil <command> --help",
            result.output,
            "root help does not tell the user to run "
            "'anvil <command> --help' for detailed per-command help",
        )


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


# ---------------------------------------------------------------------------
# stress (Behaviour 17 - TDD red)
# ---------------------------------------------------------------------------
#
# The ``stress`` subcommand does not exist yet. Click's answer to a call of an
# unknown command is exit code 2 - the SAME code as the usage errors this
# behaviour must produce - so a test that merely asserted ``exit_code == 2``
# would pass for the wrong reason right now. Every test in the class below
# therefore starts from the red guard: a named failure while the subcommand is
# missing, mirroring the guarded-import convention in ``test_stress.py``.
#
# The collaborator fakes are built from the REAL ``anvilkit.stress``
# dataclasses, which are already implemented (behaviours 10, 12, 13, 14), and
# every collaborator the CLI will call is patched in the namespace it will be
# imported from - ``anvilkit.cli`` - so no assertion depends on the green's
# import style.


def stress_ok(port=8000):
    from anvilkit import health

    return health.GatewayStatus(port=port, online=True, models=[])


def stress_gateway_with_models(port=8000, models=None):
    """A gateway whose registry is the one ``_report_available_models`` lists."""
    from anvilkit import health

    return health.GatewayStatus(
        port=port,
        online=True,
        models=[
            health.ModelStatus(mid, True)
            for mid in (models or ["org/alpha", "org/beta"])
        ],
    )


def stress_unavailable(port=8000, reason="connection refused"):
    from anvilkit import stress

    return stress.ModelAvailability(
        verdict="unreachable", available=[], reason=reason
    )


def stress_unknown_model(port=8000, available=None):
    from anvilkit import stress

    return stress.ModelAvailability(
        verdict="unknown_model",
        available=sorted(available or []),
        reason=None,
    )


def stress_available(port=8000, available=None):
    from anvilkit import stress

    return stress.ModelAvailability(
        verdict="ok", available=sorted(available or []), reason=None
    )


def warmup_ok():
    from anvilkit import stress

    return stress.WarmUpResult(
        ok=True, attempts=3, elapsed_seconds=42.0, error=None
    )


def warmup_failed():
    from anvilkit import stress

    return stress.WarmUpResult(
        ok=False,
        attempts=5,
        elapsed_seconds=120.0,
        error="connection refused",
    )


def stress_level(concurrency, succeeded, failed=0, requests=None, wall=10.0):
    from anvilkit import stress

    return stress.LevelSummary(
        concurrency=concurrency,
        requests=requests if requests is not None else succeeded + failed,
        succeeded=succeeded,
        failed=failed,
        latency_mean=0.5 if succeeded else None,
        latency_p50=0.5 if succeeded else None,
        latency_p95=1.0 if succeeded else None,
        latency_p99=2.0 if succeeded else None,
        latency_min=0.1 if succeeded else None,
        latency_max=2.0 if succeeded else None,
        requests_per_second=succeeded / wall if succeeded else 0.0,
        tokens_per_second=None,
        error_counts={"connection": failed} if failed else {},
        errors=["connection refused"] * failed if failed else [],
    )


def clean_report():
    from anvilkit import stress

    return stress.StressReport(
        model_id="org/alpha",
        port=8000,
        warm_up=warmup_ok(),
        levels=[stress_level(1, 20), stress_level(2, 20), stress_level(4, 20)],
        completed=True,
        started_at="2026-08-21T12:00:00Z",
        prompt="say pong",
        max_tokens=128,
        requests_per_level=20,
        max_clean_concurrency=4,
    )


def failing_report():
    from anvilkit import stress

    return stress.StressReport(
        model_id="org/alpha",
        port=8000,
        warm_up=warmup_ok(),
        levels=[
            stress_level(1, 20),
            stress_level(2, 18, failed=2),
            stress_level(4, 0, failed=20),
        ],
        completed=True,
        started_at="2026-08-21T12:00:00Z",
        prompt="say pong",
        max_tokens=128,
        requests_per_level=20,
        max_clean_concurrency=1,
    )


def _registered_commands():
    """The subcommands the typer app currently registers."""
    import click

    command = cli.typer.main.get_command(cli.app)
    if not isinstance(command, click.Group):
        return set()
    return set(command.commands or {})


def _require_stress_subcommand(message):
    """The red guard.

    Fails loudly - with a named message - while the ``stress`` subcommand is
    missing. A bare ``exit_code == 2`` assertion cannot stand in for this
    guard: typer/click answers "No such command 'stress'" with exit code 2,
    the very code the usage-error cases must earn from the real command.
    """
    assert "stress" in _registered_commands(), (
        "anvil stress subcommand is not implemented yet: {} (the 'stress' "
        "subcommand is missing from the registered commands {}; "
        "'No such command' would exit 2 and mask the real usage code)".format(
            message, sorted(_registered_commands())
        )
    )


class TestStress(CliCase):
    """``stress`` runs the concurrency ramp and maps the outcome to an exit code.

    Behaviour 17 of ``plans/stress-test.md``. The CLI decides; the ``stress``
    module and ``health`` act. Every collaborator is patched in the namespace
    the CLI will import it from (``anvilkit.cli`` for the stress functions,
    ``cli.health`` for the probe, as ``TestTestModel`` does), and the fakes are
    built from the real ``anvilkit.stress`` dataclasses.
    """

    MODEL = "org/alpha"
    AVAILABLE = ["org/alpha", "org/beta"]

    def setUp(self):
        super().setUp()
        self.write_env(LLM_PORT="8000")
        _require_stress_subcommand(self.id())

    def _log_file(self, name="stress.log"):
        return self.project / "logs" / name

    def _run_context(self, report, log_file=None):
        """Probe ok, model available, warm-up ok, a canned report -- everything
        past the verdict patched so only the wiring is under test.

        Yields a context manager whose ``check``, ``check_model``, ``warm``,
        ``run`` and ``log`` attributes are the patcher handles, so a test can
        assert both that the CLI reached the collaborator and what it asked.
        """
        log_file = log_file if log_file is not None else self._log_file()
        available = self.AVAILABLE

        class _Patches:
            def __init__(self, report, log_file, available):
                self._stack = contextlib.ExitStack()
                self.check = None
                self.check_model = None
                self.warm = None
                self.run = None
                self.log = None
                self.available = available

            def __enter__(self):
                self._stack.__enter__()
                self.check = self._stack.enter_context(
                    mock.patch.object(
                        cli.health, "check_gateway", return_value=stress_ok()
                    )
                )
                self.check_model = self._stack.enter_context(
                    mock.patch.object(
                        cli,
                        "check_model_available",
                        return_value=stress_available(available=self.available),
                    )
                )
                self.warm = self._stack.enter_context(
                    mock.patch.object(cli, "warm_up", return_value=warmup_ok())
                )
                self.run = self._stack.enter_context(
                    mock.patch.object(cli, "run_stress", return_value=report)
                )
                self.log = self._stack.enter_context(
                    mock.patch.object(cli, "log_path", return_value=log_file)
                )
                return self

            def __exit__(self, *exc_info):
                return self._stack.__exit__(*exc_info)

        return _Patches(report, log_file, available)

    def _clean_run_context(self, log_file=None):
        return self._run_context(clean_report(), log_file)

    def _failing_run_context(self, log_file=None):
        return self._run_context(failing_report(), log_file)

    # -- case 1: dry-run ---------------------------------------------------

    def test_dry_run_writes_nothing(self):
        """Nothing is written to the repository, not even a log file."""
        before = self.snapshot()
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()):
            self.invoke(["--dry-run", "stress", self.MODEL])
        self.assertEqual(before, self.snapshot())

    def test_dry_run_sends_nothing(self):
        """No warm-up and no measured request may go out under --dry-run."""
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()) as check, \
             mock.patch.object(cli, "check_model_available") as check_model, \
             mock.patch.object(cli, "warm_up") as warm, \
             mock.patch.object(cli, "run_stress") as run, \
             mock.patch.object(cli, "write_log") as write:
            self.invoke(["--dry-run", "stress", self.MODEL])
        # Nothing is sent: the probe is itself a network request, and the
        # plan puts --dry-run (step 3) before the probe (step 4).
        check.assert_not_called()
        check_model.assert_not_called()
        warm.assert_not_called()
        run.assert_not_called()
        write.assert_not_called()

    def test_dry_run_announces_the_levels_and_request_count(self):
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()):
            result = self.invoke(["--dry-run", "stress", self.MODEL, "--requests", "3"])
        # --max-concurrency defaults to 16, so the derived levels are 1,2,4,8,16.
        for level in ("1", "2", "4", "8", "16"):
            self.assertIn(level, result.output)
        self.assertIn("3", result.output)

    def test_dry_run_announces_the_resolved_port(self):
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()):
            result = self.invoke(["--dry-run", "stress", self.MODEL])
        self.assertIn("8000", result.output)

    def test_dry_run_announces_the_derived_log_path(self):
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()):
            result = self.invoke(["--dry-run", "stress", self.MODEL])
        self.assertIn("logs", result.output)
        self.assertIn(".log", result.output)

    def test_dry_run_announces_the_request_body(self):
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()):
            result = self.invoke(
                ["--dry-run", "stress", self.MODEL, "--prompt", "say pong", "--max-tokens", "64"]
            )
        body = health_build_chat_request("org/alpha", "say pong", 64)
        self.assertIn(body["model"], result.output)
        self.assertIn(body["messages"][0]["content"], result.output)
        self.assertIn('"max_tokens": 64', result.output)

    def test_dry_run_exits_zero(self):
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()):
            result = self.invoke(["--dry-run", "stress", self.MODEL])
        self.assertEqual(0, result.exit_code)

    # -- case 2: a clean run -------------------------------------------------

    def test_a_clean_run_exits_zero(self):
        with self._clean_run_context() as c:
            result = self.invoke(["stress", self.MODEL])
        self.assertEqual(0, result.exit_code)

    def test_a_clean_run_prints_the_report(self):
        with self._clean_run_context():
            result = self.invoke(["stress", self.MODEL])
        self.assertIn(self.MODEL, result.output)
        self.assertIn("Port: 8000", result.output)
        # The real text report carries one row per level; a clean level
        # renders its ok/fail cell as "20/0" (20 succeeded, 0 failed).
        # Asserted on the cell, not on column padding, which is the
        # formatter's business.
        self.assertEqual(3, result.output.count("20/0"))

    def test_a_clean_run_writes_the_log_by_default(self):
        target = self._log_file("clean.log")
        with self._clean_run_context(log_file=target) as c:
            self.invoke(["stress", self.MODEL, "--log-file", str(target)])
        self.assertTrue(target.is_file(), "the log file was not written")
        text = target.read_text(encoding="utf-8")
        self.assertIn(self.MODEL, text)
        self.assertIn("Port: 8000", text)
        self.assertTrue(text.rstrip().endswith("}"), "the log must end with the JSON block")

    def test_a_clean_run_warms_up_before_measuring(self):
        with self._clean_run_context() as patches:
            self.invoke(["stress", self.MODEL])
            patches.warm.assert_called_once()
            patches.run.assert_called_once()

    def test_no_warmup_skips_warm_up(self):
        with self._clean_run_context() as patches:
            self.invoke(["stress", self.MODEL, "--no-warmup"])
            patches.warm.assert_not_called()
            patches.run.assert_called_once()

    def test_json_output_is_pure_json_and_still_writes_the_log(self):
        target = self._log_file("json.log")
        with self._clean_run_context(log_file=target) as c:
            result = self.invoke(["stress", self.MODEL, "--json", "--log-file", str(target)])
        self.assertTrue(result.output.lstrip().startswith("{"))
        payload = json.loads(result.output)
        self.assertEqual(self.MODEL, payload["model"])
        self.assertEqual(8000, payload["port"])
        self.assertTrue(target.is_file(), "the log file is still written under --json")

    # -- case 3: a run with failures ------------------------------------------

    def test_a_run_with_failures_exits_with_the_failures_code(self):
        """EXIT_STRESS_FAILURES is the literal 8 - the constant does not exist yet."""
        with self._failing_run_context() as c:
            result = self.invoke(["stress", self.MODEL])
        self.assertEqual(8, result.exit_code)

    def test_a_run_with_failures_prints_the_report(self):
        with self._failing_run_context() as c:
            result = self.invoke(["stress", self.MODEL])
        self.assertIn(self.MODEL, result.output)
        # The all-failed level is a finding, not a crash: its failures show.
        self.assertIn("connection refused", result.output)

    def test_a_run_with_failures_writes_the_log(self):
        target = self._log_file("failures.log")
        with self._failing_run_context(log_file=target) as c:
            self.invoke(["stress", self.MODEL, "--log-file", str(target)])
        self.assertTrue(target.is_file())
        self.assertIn("connection refused", target.read_text(encoding="utf-8"))

    def test_a_run_with_failures_under_json_exits_with_the_failures_code(self):
        with self._failing_run_context() as c:
            result = self.invoke(["stress", self.MODEL, "--json"])
        self.assertEqual(8, result.exit_code)
        payload = json.loads(result.output)
        # The JSON document carries the failure, so a CI reader needs no text.
        total_failed = sum(level["failed"] for level in payload["levels"])
        self.assertGreater(total_failed, 0)

    def test_no_log_file_suppresses_the_log(self):
        with self._clean_run_context() as c:
            self.invoke(["stress", self.MODEL, "--no-log-file"])
        self.assertFalse((self.project / "logs").exists(), "--no-log-file must write nothing")

    # -- case 4: warm-up failure ----------------------------------------------

    def test_a_warmup_failure_exits_with_the_unavailable_code(self):
        """EXIT_STRESS_UNAVAILABLE is the literal 7 - the constant does not exist yet."""
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()), \
             mock.patch.object(cli, "check_model_available", return_value=stress_available(available=self.AVAILABLE)), \
             mock.patch.object(cli, "warm_up", return_value=warmup_failed()) as warm, \
             mock.patch.object(cli, "run_stress") as run, \
             mock.patch.object(cli, "write_log") as write:
            result = self.invoke(["stress", self.MODEL])
        self.assertEqual(7, result.exit_code)
        run.assert_not_called()
        write.assert_not_called()

    def test_a_warmup_failure_reports_the_reason(self):
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()), \
             mock.patch.object(cli, "check_model_available", return_value=stress_available(available=self.AVAILABLE)), \
             mock.patch.object(cli, "warm_up", return_value=warmup_failed()):
            result = self.invoke(["stress", self.MODEL])
        self.assertIn("connection refused", result.output)

    # -- case 5: no model named --------------------------------------------------

    def test_a_missing_model_name_is_a_usage_error(self):
        """Exit 2 here must be earned from the real command, so the guard above applies."""
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_gateway_with_models()) as check, \
             mock.patch.object(cli, "check_model_available") as check_model, \
             mock.patch.object(cli, "warm_up") as warm, \
             mock.patch.object(cli, "run_stress") as run:
            result = self.invoke(["stress"])
        self.assertEqual(2, result.exit_code)
        check_model.assert_not_called()
        warm.assert_not_called()
        run.assert_not_called()

    def test_a_missing_model_name_lists_the_registry(self):
        with mock.patch.object(
            cli.health, "check_gateway", return_value=stress_gateway_with_models()
        ):
            result = self.invoke(["stress"])
        self.assertIn("org/alpha", result.output)
        self.assertIn("org/beta", result.output)

    # -- case 6: unknown model -------------------------------------------------

    def test_an_unknown_model_is_a_usage_error(self):
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()), \
             mock.patch.object(cli, "check_model_available", return_value=stress_unknown_model(available=self.AVAILABLE)), \
             mock.patch.object(cli, "warm_up") as warm, \
             mock.patch.object(cli, "run_stress") as run:
            result = self.invoke(["stress", "org/not-registered"])
        self.assertEqual(2, result.exit_code)
        warm.assert_not_called()
        run.assert_not_called()

    def test_an_unknown_model_names_the_model_and_lists_the_available_ids(self):
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()), \
             mock.patch.object(cli, "check_model_available", return_value=stress_unknown_model(available=self.AVAILABLE)):
            result = self.invoke(["stress", "org/not-registered"])
        self.assertIn("org/not-registered", result.output)
        self.assertIn("org/alpha", result.output)
        self.assertIn("org/beta", result.output)

    def test_an_unknown_model_with_an_empty_registry_says_so(self):
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()), \
             mock.patch.object(cli, "check_model_available", return_value=stress_unknown_model(available=[])):
            result = self.invoke(["stress", "org/not-registered"])
        self.assertEqual(2, result.exit_code)
        self.assertIn("org/not-registered", result.output)

    # -- case 7: unreachable gateway --------------------------------------------

    def test_an_unreachable_gateway_exits_with_the_unavailable_code(self):
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()), \
             mock.patch.object(cli, "check_model_available", return_value=stress_unavailable(reason="connection refused")), \
             mock.patch.object(cli, "warm_up") as warm, \
             mock.patch.object(cli, "run_stress") as run:
            result = self.invoke(["stress", self.MODEL])
        self.assertEqual(7, result.exit_code)
        warm.assert_not_called()
        run.assert_not_called()

    def test_an_unreachable_gateway_reports_the_port_and_the_verbatim_reason(self):
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()), \
             mock.patch.object(cli, "check_model_available", return_value=stress_unavailable(reason="connection refused")):
            result = self.invoke(["stress", self.MODEL])
        self.assertIn("8000", result.output)
        self.assertIn("connection refused", result.output)

    # -- the collaborators are called with the resolved values -------------------

    def test_the_resolved_port_reaches_check_gateway(self):
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()) as check, \
             mock.patch.object(cli, "check_model_available", return_value=stress_available(available=self.AVAILABLE)), \
             mock.patch.object(cli, "warm_up", return_value=warmup_ok()), \
             mock.patch.object(cli, "run_stress", return_value=clean_report()), \
             mock.patch.object(cli, "log_path", return_value=self._log_file()):
            self.invoke(["stress", self.MODEL])
        called = check.call_args
        self.assertEqual(8000, called[1]["port"] if called[1] else called[0][0])

    def test_the_flag_port_wins_over_env(self):
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()) as check, \
             mock.patch.object(cli, "check_model_available", return_value=stress_available(available=self.AVAILABLE)), \
             mock.patch.object(cli, "warm_up", return_value=warmup_ok()), \
             mock.patch.object(cli, "run_stress", return_value=clean_report()), \
             mock.patch.object(cli, "log_path", return_value=self._log_file()):
            self.invoke(["stress", self.MODEL, "--llm-port", "9002"])
        called = check.call_args
        self.assertEqual(9002, called[1]["port"] if called[1] else called[0][0])

    def test_the_named_model_reaches_check_model_available(self):
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()), \
             mock.patch.object(cli, "check_model_available", return_value=stress_available(available=self.AVAILABLE)) as check_model, \
             mock.patch.object(cli, "warm_up", return_value=warmup_ok()), \
             mock.patch.object(cli, "run_stress", return_value=clean_report()), \
             mock.patch.object(cli, "log_path", return_value=self._log_file()):
            self.invoke(["stress", self.MODEL])
        called = check_model.call_args
        self.assertEqual(self.MODEL, called[1]["model_id"] if "model_id" in (called[1] or {}) else called[0][1] if called[0] else None)

    # -- verbose -----------------------------------------------------------------

    def test_verbose_prints_progress(self):
        with self._clean_run_context() as c:
            result = self.invoke(["--verbose", "stress", self.MODEL])
        self.assertGreater(len(result.output), 0)

    # -- default progress lines (addendum, behaviours 20-24 in one red) -------------
    #
    # The callbacks already exist in anvilkit.stress (behaviours 18 and 19,
    # green); what is missing is the CLI wiring: an announcement before
    # warm-up, one line per failed attempt, and one line per level start and
    # finish, all through shared.echo. The patches below are given
    # side_effects that fire the callback the CLI is expected to hand them,
    # with hand-built stress.WarmUpAttempt / stress.LevelEvent events, and
    # then return the canned fakes from this class. The helpers record what
    # the CLI actually passed and print nothing of their own, so every red
    # here is a named assertion: either the call_args say no callback was
    # handed, or the expected line is not in the output. The --json
    # pipeability, log-content and --verbose coexistence invariants are
    # folded in as assertions, per the process post-mortem: one feature,
    # one red.

    def _warm_side_effect(self, events, return_value):
        """A warm_up stand-in that fires on_attempt with hand-built events.

        Fires the callback the CLI actually handed (``None`` while the wiring
        is missing) and returns the plain canned ``return_value``, so the CLI
        sees a normal fake. It never prints and never raises: a missing
        callback is asserted by the test on the patch handle's call_args, and
        a line that is never fired simply never reaches the output.
        """

        def _warm(*args, **kwargs):
            # on_attempt is the sixth parameter of the real warm_up; accept
            # it positionally or by keyword so the fake cannot depend on the
            # green's calling style.
            on_attempt = kwargs.get("on_attempt", args[5] if len(args) >= 6 else None)
            if on_attempt is not None:
                for event in events:
                    on_attempt(event)
            return return_value

        return _warm

    def _levels_side_effect(self, report, return_value):
        """A run_stress stand-in that fires on_level with start/finish
        events built from the canned report's own summaries.

        ``requests`` comes from the CLI's own ``request_count`` kwarg (the
        real ``run_stress`` carries it in both phases) so ``--requests`` is
        honoured; the finish event still carries the canned summary, which
        is where the ok/failed counts live.
        """
        from anvilkit import stress

        def _run(*args, **kwargs):
            # on_level is the seventh parameter of the real run_stress.
            on_level = kwargs.get("on_level", args[6] if len(args) >= 7 else None)
            if on_level is not None:
                request_count = kwargs.get(
                    "request_count", args[2] if len(args) >= 3 else None
                )
                for summary in report.levels:
                    requests = (
                        request_count
                        if request_count is not None
                        else summary.requests
                        if summary.requests is not None
                        else summary.succeeded + summary.failed
                    )
                    on_level(
                        stress.LevelEvent(
                            phase="start",
                            concurrency=summary.concurrency,
                            requests=requests,
                            summary=None,
                        )
                    )
                    on_level(
                        stress.LevelEvent(
                            phase="finish",
                            concurrency=summary.concurrency,
                            requests=requests,
                            summary=summary,
                        )
                    )
            return return_value

        return _run

    def test_the_warmup_announcement_is_printed_before_warm_up(self):
        """Plain run: 'Warming up <model> at http://localhost:<port>…' before warm_up."""
        from anvilkit import stress

        events = [
            stress.WarmUpAttempt(1, 12.3, "connection refused", will_retry=True),
            stress.WarmUpAttempt(2, 18.7, "connection refused", will_retry=False),
        ]
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()), \
             mock.patch.object(
                 cli, "check_model_available",
                 return_value=stress_available(available=self.AVAILABLE),
             ), \
             mock.patch.object(
                 cli, "warm_up",
                 side_effect=self._warm_side_effect(events, warmup_failed()),
             ) as warm, \
             mock.patch.object(cli, "run_stress"), \
             mock.patch.object(cli, "write_log"):
            result = self.invoke(["stress", self.MODEL])
        warm_kwargs = (
            warm.call_args[1] if warm.call_args and warm.call_args[1] else {}
        )
        self.assertIsNotNone(
            warm_kwargs.get("on_attempt"),
            "cli.warm_up was not handed an on_attempt callback "
            "(call kwargs: {!r})".format(warm_kwargs),
        )
        announcement = "Warming up {} at http://localhost:8000…".format(self.MODEL)
        self.assertIn(
            announcement, result.output,
            "the warm-up announcement is missing from the default output:\n"
            + result.output,
        )
        # The announcement precedes the warm-up work, not the report.
        self.assertLess(result.output.index(announcement), result.output.index("Warm-up"))

    def test_warmup_retry_lines_are_printed_per_failed_attempt(self):
        """One indented line per failed attempt, verbatim error and elapsed."""
        from anvilkit import stress

        events = [
            stress.WarmUpAttempt(1, 12.3, "connection refused", will_retry=True),
            stress.WarmUpAttempt(2, 18.7, "", will_retry=True),
            stress.WarmUpAttempt(3, 25.0, None, will_retry=False),
        ]
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()), \
             mock.patch.object(
                 cli, "check_model_available",
                 return_value=stress_available(available=self.AVAILABLE),
             ), \
             mock.patch.object(
                 cli, "warm_up",
                 side_effect=self._warm_side_effect(events, warmup_failed()),
             ) as warm, \
             mock.patch.object(cli, "run_stress"), \
             mock.patch.object(cli, "write_log"):
            result = self.invoke(["stress", self.MODEL])
        warm_kwargs = (
            warm.call_args[1] if warm.call_args and warm.call_args[1] else {}
        )
        self.assertIsNotNone(
            warm_kwargs.get("on_attempt"),
            "cli.warm_up was not handed an on_attempt callback "
            "(call kwargs: {!r})".format(warm_kwargs),
        )
        output = result.output
        # The interval is the CLI's _WARMUP_RETRY_INTERVAL (5.0 -> '5' under :g).
        self.assertIn(
            "  warm-up attempt 1 failed after 12.3s: connection refused; "
            "retrying in {0:g}s".format(cli._WARMUP_RETRY_INTERVAL),
            output,
            "the retrying attempt line is missing:\n" + output,
        )
        # A None or empty error renders as 'no reason reported'.
        self.assertIn(
            "  warm-up attempt 2 failed after 18.7s: no reason reported; "
            "retrying in {0:g}s".format(cli._WARMUP_RETRY_INTERVAL),
            output,
            "a missing error must read 'no reason reported':\n" + output,
        )
        # The budget-exhausted attempt omits the retry clause.
        self.assertIn(
            "  warm-up attempt 3 failed after 25.0s: no reason reported",
            output,
            "the final attempt line is missing:\n" + output,
        )
        self.assertNotIn(
            "attempt 3 failed after 25.0s: no reason reported; retrying",
            output,
            "will_retry=False must not promise another attempt",
        )

    def test_warmup_retry_lines_precede_the_failure_message_and_exit_seven(self):
        """The retry lines do not replace the existing failure: order, stderr ❌, exit 7."""
        from anvilkit import stress

        events = [
            stress.WarmUpAttempt(1, 12.3, "connection refused", will_retry=True),
            stress.WarmUpAttempt(2, 120.0, "connection refused", will_retry=False),
        ]
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()), \
             mock.patch.object(
                 cli, "check_model_available",
                 return_value=stress_available(available=self.AVAILABLE),
             ), \
             mock.patch.object(
                 cli, "warm_up",
                 side_effect=self._warm_side_effect(events, warmup_failed()),
             ), \
             mock.patch.object(cli, "run_stress") as run, \
             mock.patch.object(cli, "write_log") as write:
            result = self.invoke(["stress", self.MODEL])
        output = result.output
        self.assertEqual(7, result.exit_code)
        run.assert_not_called()
        write.assert_not_called()
        self.assertIn("❌ Warm-up failed after 5 attempt(s): connection refused", output)
        self.assertIn(
            "  warm-up attempt 1 failed",
            output,
            "the retry line is missing:\n" + output,
        )
        self.assertLess(
            output.index("  warm-up attempt 1 failed"),
            output.index("❌ Warm-up failed"),
            "the retry lines must precede the existing failure message:\n" + output,
        )

    def test_a_plain_run_prints_no_warmup_announcement_when_no_warmup(self):
        """--no-warmup skips the phase, so nothing about warm-up is announced."""
        with self._clean_run_context() as c:
            result = self.invoke(["stress", self.MODEL, "--no-warmup"])
        c.warm.assert_not_called()
        self.assertNotIn(
            "Warming up", result.output,
            "--no-warmup must not announce a warm-up that never runs:\n" + result.output,
        )

    def test_dry_run_prints_no_warmup_announcement_and_sends_nothing(self):
        """--dry-run returns before the probe: no announcement, nothing sent."""
        with mock.patch.object(cli.health, "check_gateway") as check, \
             mock.patch.object(cli, "warm_up") as warm, \
             mock.patch.object(cli, "run_stress") as run:
            result = self.invoke(["--dry-run", "stress", self.MODEL])
        check.assert_not_called()
        warm.assert_not_called()
        run.assert_not_called()
        self.assertNotIn("Warming up", result.output)

    def test_a_clean_run_prints_one_line_per_level_start_and_finish(self):
        """Start line before the requests go out, finish line from the summary."""
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()), \
             mock.patch.object(
                 cli, "check_model_available",
                 return_value=stress_available(available=self.AVAILABLE),
             ), \
             mock.patch.object(cli, "warm_up", return_value=warmup_ok()), \
             mock.patch.object(
                 cli, "run_stress",
                 side_effect=self._levels_side_effect(clean_report(), clean_report()),
             ) as run, \
             mock.patch.object(cli, "log_path", return_value=self._log_file()):
            result = self.invoke(["stress", self.MODEL])
        run.assert_called_once()
        run_kwargs = (
            run.call_args[1] if run.call_args and run.call_args[1] else {}
        )
        self.assertIsNotNone(
            run_kwargs.get("on_level"),
            "cli.run_stress was not handed an on_level callback "
            "(call kwargs: {!r})".format(run_kwargs),
        )
        output = result.output
        for level in ("1", "2", "4"):
            start = "Level {}: sending 20 requests".format(level)
            finish = "Level {}: 20/20 ok, 0 failed".format(level)
            self.assertIn(start, output, "the level start line is missing:\n" + output)
            self.assertIn(finish, output, "the level finish line is missing:\n" + output)
            self.assertLess(
                output.index(start), output.index(finish),
                "the start line must precede its finish line:\n" + output,
            )
        # No per-request noise: exactly one start and one finish line per level.
        self.assertEqual(
            6, output.count("Level "),
            "expected one start and one finish line per level, got:\n" + output,
        )

    def test_a_failing_run_still_prints_the_all_failed_level_finish_line(self):
        """Zero successes is a finding, not a reason to stay silent."""
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()), \
             mock.patch.object(
                 cli, "check_model_available",
                 return_value=stress_available(available=self.AVAILABLE),
             ), \
             mock.patch.object(cli, "warm_up", return_value=warmup_ok()), \
             mock.patch.object(
                 cli, "run_stress",
                 side_effect=self._levels_side_effect(failing_report(), failing_report()),
             ) as run, \
             mock.patch.object(cli, "log_path", return_value=self._log_file()):
            result = self.invoke(["stress", self.MODEL])
        self.assertEqual(8, result.exit_code)
        run_kwargs = (
            run.call_args[1] if run.call_args and run.call_args[1] else {}
        )
        self.assertIsNotNone(
            run_kwargs.get("on_level"),
            "cli.run_stress was not handed an on_level callback "
            "(call kwargs: {!r})".format(run_kwargs),
        )
        output = result.output
        self.assertIn(
            "Level 4: 0/20 ok, 20 failed", output,
            "an all-failed level must still print its finish line:\n" + output,
        )
        self.assertIn(
            "Level 2: 18/20 ok, 2 failed",
            output,
            "a partially failed level must still print its finish line:\n" + output,
        )
        # The request count in the start line follows --requests.
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()), \
             mock.patch.object(
                 cli, "check_model_available",
                 return_value=stress_available(available=self.AVAILABLE),
             ), \
             mock.patch.object(cli, "warm_up", return_value=warmup_ok()), \
             mock.patch.object(
                 cli, "run_stress",
                 side_effect=self._levels_side_effect(clean_report(), clean_report()),
             ), \
             mock.patch.object(cli, "log_path", return_value=self._log_file()):
            result = self.invoke(["stress", self.MODEL, "--requests", "7"])
        self.assertIn(
            "Level 1: sending 7 requests", result.output,
            "the start line must carry the --requests figure:\n" + result.output,
        )

    def test_json_runs_pass_no_callbacks_and_stay_pure_json(self):
        """--json: warm_up and run_stress receive None, so the document is first."""
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()), \
             mock.patch.object(
                 cli, "check_model_available",
                 return_value=stress_available(available=self.AVAILABLE),
             ), \
             mock.patch.object(cli, "warm_up", return_value=warmup_ok()) as warm, \
             mock.patch.object(cli, "run_stress", return_value=clean_report()) as run, \
             mock.patch.object(cli, "log_path", return_value=self._log_file()):
            result = self.invoke(["stress", self.MODEL, "--json"])
        warm.assert_called_once()
        run.assert_called_once()
        warm_kwargs = warm.call_args[1] if warm.call_args[1] else {}
        run_kwargs = run.call_args[1] if run.call_args[1] else {}
        self.assertIsNone(
            warm_kwargs.get("on_attempt", None),
            "--json must hand warm_up no on_attempt callback (got {!r})".format(
                warm_kwargs.get("on_attempt")
            ),
        )
        self.assertIsNone(
            run_kwargs.get("on_level", None),
            "--json must hand run_stress no on_level callback (got {!r})".format(
                run_kwargs.get("on_level")
            ),
        )
        self.assertTrue(
            result.output.lstrip().startswith("{"),
            "stdout must still be pure JSON under --json:\n" + result.output[:400],
        )
        payload = json.loads(result.output)
        self.assertEqual(self.MODEL, payload["model"])
        self.assertNotIn("Warming up", result.output)
        self.assertNotIn("Level 1: sending", result.output)

    def test_json_warmup_failure_exits_seven_with_empty_stdout(self):
        """A --json warm-up failure: ❌ on stderr, exit 7, stdout stays empty."""
        # A separate runner captures the streams apart: the invariant is
        # about stderr, and the class runner mixes them into one buffer.
        runner = CliRunner(mix_stderr=False)
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()), \
             mock.patch.object(
                 cli, "check_model_available",
                 return_value=stress_available(available=self.AVAILABLE),
             ), \
             mock.patch.object(cli, "warm_up", return_value=warmup_failed()) as warm, \
             mock.patch.object(cli, "run_stress") as run, \
             mock.patch.object(cli, "write_log") as write:
            result = runner.invoke(cli.app, ["stress", self.MODEL, "--json"])
        warm.assert_called_once()
        warm_kwargs = (
            warm.call_args[1] if warm.call_args and warm.call_args[1] else {}
        )
        self.assertIsNone(warm_kwargs.get("on_attempt", None))
        run.assert_not_called()
        write.assert_not_called()
        self.assertEqual(7, result.exit_code)
        self.assertEqual(
            "", result.output,
            "stdout must stay empty for a --json run that produced no results:\n"
            + result.output,
        )
        self.assertIn("❌ Warm-up failed", result.stderr, "the failure must still be reported")

    def test_progress_lines_never_reach_the_log_file(self):
        """The noisiest default run still writes a log with only the two reports."""
        from anvilkit import stress

        events = [
            stress.WarmUpAttempt(1, 12.3, "connection refused", will_retry=True),
            stress.WarmUpAttempt(2, 30.5, "connection refused", will_retry=False),
        ]
        target = self._log_file("progress.log")
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()), \
             mock.patch.object(
                 cli, "check_model_available",
                 return_value=stress_available(available=self.AVAILABLE),
             ), \
             mock.patch.object(
                 cli, "warm_up",
                 side_effect=self._warm_side_effect(events, warmup_ok()),
             ), \
             mock.patch.object(
                 cli, "run_stress",
                 side_effect=self._levels_side_effect(failing_report(), failing_report()),
             ), \
             mock.patch.object(cli, "log_path", return_value=target):
            self.invoke(["stress", self.MODEL])
        self.assertTrue(target.is_file(), "the log file was not written")
        text = target.read_text(encoding="utf-8")
        self.assertTrue(
            text.startswith("Stress test: {}".format(self.MODEL)),
            "the log must still start with the report header:\n" + text[:200],
        )
        self.assertNotIn("Warming up", text)
        self.assertNotIn("warm-up attempt", text)
        self.assertNotIn("Level 1: sending", text)
        self.assertTrue(
            text.rstrip().endswith("}"),
            "the log must still end with the JSON block:\n" + text[-200:],
        )

    def test_verbose_runs_carry_both_the_detail_lines_and_the_default_lines(self):
        """--verbose keeps its three detail lines; the default lines coexist."""
        from anvilkit import stress

        events = [
            stress.WarmUpAttempt(1, 12.3, "connection refused", will_retry=True),
            stress.WarmUpAttempt(2, 30.5, "connection refused", will_retry=False),
        ]
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()), \
             mock.patch.object(
                 cli, "check_model_available",
                 return_value=stress_available(available=self.AVAILABLE),
             ), \
             mock.patch.object(
                 cli, "warm_up",
                 side_effect=self._warm_side_effect(events, warmup_ok()),
             ), \
             mock.patch.object(
                 cli, "run_stress",
                 side_effect=self._levels_side_effect(clean_report(), clean_report()),
             ), \
             mock.patch.object(cli, "log_path", return_value=self._log_file()):
            verbose = self.invoke(["--verbose", "stress", self.MODEL])
        output = verbose.output
        self.assertIn(
            "warming up {} at http://localhost:8000 (budget 600.0s)".format(self.MODEL),
            output,
            "the existing --verbose warming-up detail line is missing:\n" + output,
        )
        self.assertIn(
            "measuring {} at http://localhost:8000 (20 requests per level, timeout 120.0s)".format(
                self.MODEL
            ),
            output,
            "the existing --verbose measuring detail line is missing:\n" + output,
        )
        self.assertIn(
            "log written to {}".format(self._log_file()),
            output,
            "the existing --verbose log detail line is missing:\n" + output,
        )
        # The detail line (lower-case) and the default line (capitalised) are
        # distinct strings; a plain run carries the default line without the
        # detail line.
        self.assertIn(
            "Warming up {} at http://localhost:8000…".format(self.MODEL),
            output,
            "the default warm-up announcement is missing from the --verbose output:\n"
            + output,
        )
        with self._clean_run_context():
            plain = self.invoke(["stress", self.MODEL])
        self.assertIn(
            "Warming up {} at http://localhost:8000…".format(self.MODEL),
            plain.output,
            "the default warm-up announcement is missing from the plain output:\n"
            + plain.output,
        )
        self.assertNotIn(
            "warming up {} at http://localhost:8000 (budget".format(self.MODEL),
            plain.output,
            "the detail line must stay --verbose-only:\n" + plain.output,
        )
        self.assertNotIn("measuring {} at http://localhost:8000".format(self.MODEL), plain.output)

    def run_cli(self, argv):
        """Invoke ``run()`` exactly as ``python -m anvilkit.cli`` does.

        Mirrors ``TestRunEntryPoint.run_cli``: ``standalone_mode=False`` is
        the entry path the behavior-17 precedent pinned, which CliRunner
        (standalone mode) cannot see.
        """
        stderr = io.StringIO()
        with mock.patch.object(sys, "argv", ["anvil"] + argv):
            with contextlib.redirect_stderr(stderr):
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    code = cli.run()
        return code, stdout.getvalue() + stderr.getvalue()

    def test_run_entrypoint_clean_run_prints_the_progress_lines(self):
        """run() with standalone_mode=False: the progress lines reach stdout."""
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()), \
             mock.patch.object(
                 cli, "check_model_available",
                 return_value=stress_available(available=["org/alpha"]),
             ), \
             mock.patch.object(cli, "warm_up", return_value=warmup_ok()), \
             mock.patch.object(
                 cli, "run_stress",
                 side_effect=self._levels_side_effect(clean_report(), clean_report()),
             ), \
             mock.patch.object(
                 cli, "log_path",
                 side_effect=lambda *a, **k: Path(str(self.project / "logs" / "stress.log")),
             ):
            code, output = self.run_cli(["stress", "org/alpha"])
        self.assertEqual(cli.EXIT_OK, code)
        self.assertIn(
            "Warming up org/alpha at http://localhost:8000…", output,
            "the warm-up announcement is missing from the run() entrypoint output:\n"
            + output,
        )
        self.assertIn("Level 1: sending 20 requests", output)
        self.assertIn("Level 1: 20/20 ok, 0 failed", output)
        self.assertNotIn("Traceback", output)

    def test_run_entrypoint_json_stays_pure_json(self):
        """run() with --json: no progress line may precede the document."""
        with mock.patch.object(cli.health, "check_gateway", return_value=stress_ok()), \
             mock.patch.object(
                 cli, "check_model_available",
                 return_value=stress_available(available=["org/alpha"]),
             ), \
             mock.patch.object(cli, "warm_up", return_value=warmup_ok()) as warm, \
             mock.patch.object(cli, "run_stress", return_value=clean_report()) as run, \
             mock.patch.object(
                 cli, "log_path",
                 side_effect=lambda *a, **k: Path(str(self.project / "logs" / "stress.log")),
             ):
            code, output = self.run_cli(["stress", "org/alpha", "--json"])
        self.assertEqual(cli.EXIT_OK, code)
        warm_kwargs = warm.call_args[1] if warm.call_args[1] else {}
        run_kwargs = run.call_args[1] if run.call_args[1] else {}
        self.assertIsNone(warm_kwargs.get("on_attempt", None))
        self.assertIsNone(run_kwargs.get("on_level", None))
        self.assertTrue(
            output.lstrip().startswith("{"),
            "stdout must be pure JSON under --json via the run() entrypoint:\n"
            + output[:400],
        )
        self.assertEqual("org/alpha", json.loads(output)["model"])


def health_build_chat_request(model_id, prompt, max_tokens):
    from anvilkit import health

    return health.build_chat_request(model_id, prompt, max_tokens)


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

    def test_container_target_defaults_to_false(self):
        """Host-side setup-repo keeps rendering localhost URLs."""
        plan = self.captured_plan(["setup-repo", self.target, "--yes"])

        self.assertFalse(plan.container_target)

    def test_container_flag_sets_container_target(self):
        """--container re-points the rendered URLs at the llm-network containers."""
        plan = self.captured_plan(["setup-repo", self.target, "--yes", "--container"])

        self.assertTrue(plan.container_target)

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


# ---------------------------------------------------------------------------
# setup-repo guard gate (plans/setup-repo-guards.md): behaviour 4 is the red;
# behaviours 5 and 10 are boundary pins that pass now and must keep passing
# once the gate is wired in.
# ---------------------------------------------------------------------------


class TestSetupRepoGuardGate(CliCase):
    """``setup-repo`` gates on the guards before any provisioning.

    Behaviour 4 (red): with the guard seams patched to a blocked result,
    the run must never reach ``provision.setup_repo`` and must leave the
    target unchanged except for behaviour 7's one allowed file,
    ``.github-ruleset.json``. The before/after snapshot is the same
    recursive walk, minus that one allowed path - no .roo, no settings
    file, no .env write into it.

    Behaviour 5 (pin): a plain temp target has no git origin, so the real
    ``resolve_repository`` returns None, the branch findings are all
    skipped, the gate is clean, and provisioning proceeds exactly as
    before the gate existed.

    Behaviour 10 (pin): ``--no-github`` never touches a guard seam - the
    seams are booby-trapped, so any call fails the test - and
    provisioning proceeds with an empty token.
    """

    OWNER = "iar3-r8"
    REPO = "Anvil"

    def setUp(self):
        super().setUp()
        # The harness's usual default: a port to resolve, nothing else
        # stored. The blocked-gate tests store a token themselves, since
        # the gate needs one.
        self.write_env(LLM_PORT="8000")
        self._target = tempfile.TemporaryDirectory()
        self.target = self._target.name
        self.addCleanup(self._target.cleanup)

    # -- helpers -----------------------------------------------------------

    def _target_snapshot(self):
        """Every file under the target, mapped to its bytes."""
        root = Path(self.target)
        return {
            str(path.relative_to(root)): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def _blocked_seams(self):
        """Patcher trio: the guard seams yield a blocked result.

        The repository resolves, the fetched rules are an empty array, so
        the real ``check_all`` emits five ``warn`` findings (the plan's
        Interface facts). The token probes return no findings - only the
        branch warns are needed to block - which also keeps the run
        offline.
        """
        return (
            mock.patch.object(
                cli.piguard,
                "resolve_repository",
                return_value=(self.OWNER, self.REPO),
            ),
            mock.patch.object(
                cli.piguard,
                "fetch_branch_rules",
                return_value=([], None),
            ),
            mock.patch.object(
                cli.piguard,
                "check_token_all",
                return_value=[],
            ),
        )

    def _spy_provision(self, invoke_real=True):
        """A recorder over ``provision.setup_repo``.

        With ``invoke_real`` the spy delegates to the real provision, so a
        run that should not provision actually provisions - the target then
        gains files and the before/after snapshot proves it.
        """
        self._provision_calls = []

        if invoke_real:
            real = cli.provision.setup_repo

            def spy(target, repo_plan, **kwargs):
                self._provision_calls.append((str(target), repo_plan, kwargs))
                return real(target, repo_plan, **kwargs)
        else:
            def spy(target, repo_plan, **kwargs):
                self._provision_calls.append((str(target), repo_plan, kwargs))
                return str(target)

        patcher = mock.patch.object(cli.provision, "setup_repo", spy)
        patcher.start()
        self.addCleanup(patcher.stop)

    # -- behaviour 4: the gate runs before any provisioning (RED) ----------

    def test_blocked_gate_never_provisions(self):
        """A blocked gate stops the run: provision is never called and the
        target is byte-for-byte unchanged - no .roo, no settings file, no
        .env write into it (the project .env lives outside the target)."""
        self.write_env(GITHUB_TOKEN="ghp_test")
        before = self._target_snapshot()
        self._spy_provision(invoke_real=True)
        for patcher in self._blocked_seams():
            patcher.start()
            self.addCleanup(patcher.stop)

        result = self.invoke_allowing_exception(
            ["setup-repo", self.target, "--yes"]
        )

        self.assertEqual(
            0,
            len(self._provision_calls),
            "a blocked gate must never reach provision.setup_repo:\n{}".format(
                result.output
            ),
        )
        self.assertNotEqual(
            0,
            result.exit_code,
            "a blocked gate must stop the run, exit {}:\n{}".format(
                result.exit_code, result.output
            ),
        )
        after = self._target_snapshot()
        # Behaviour 7's relaxation: the one file the blocked run may
        # create in the target is the ruleset it prepares; nothing else
        # may appear, and the allowed file's content, if present, must be
        # the rendered ruleset itself.
        allowed = ".github-ruleset.json"
        unexpected = sorted(
            (set(after) - set(before)) - {allowed}
        )
        self.assertEqual(
            [],
            unexpected,
            "a blocked run must leave the target unchanged apart from "
            "{}; files that appeared: {}".format(allowed, unexpected),
        )
        if allowed in after:
            self.assertEqual(
                piruleset.render_ruleset_json(piruleset.build_ruleset()),
                after[allowed].decode("utf-8"),
            )

    def test_blocked_gate_exit_is_not_a_usage_or_config_error(self):
        """A blocked gate is a new failure class: whatever its code, it is
        not 2 (usage) and not 3 (config) - behaviour 9 pins the exact 9."""
        self.write_env(GITHUB_TOKEN="ghp_test")
        self._spy_provision(invoke_real=True)
        for patcher in self._blocked_seams():
            patcher.start()
            self.addCleanup(patcher.stop)

        result = self.invoke_allowing_exception(
            ["setup-repo", self.target, "--yes"]
        )

        self.assertEqual(0, len(self._provision_calls), result.output)
        self.assertNotIn(
            result.exit_code,
            (cli.EXIT_USAGE, cli.EXIT_CONFIG),
            "a blocked gate is neither a usage nor a config error, "
            "exit {}:\n{}".format(result.exit_code, result.output),
        )

    # -- behaviour 5: a clean gate provisions exactly as today (PIN) -------

    def test_clean_gate_provisions_as_today(self):
        """A plain temp target has no git origin, so the real
        resolve_repository returns None (unpatched - the genuine
        all-skipped case), the gate is clean, and provisioning proceeds
        exactly as before the gate existed: one provision.setup_repo
        call, exit 0, the usual provisioned artifacts, no
        .github-ruleset.json, no recipe text."""
        self._spy_provision(invoke_real=True)

        result = self.invoke_allowing_exception(
            ["setup-repo", self.target, "--yes"]
        )

        self.assertEqual(0, result.exit_code, result.output)
        self.assertEqual(1, len(self._provision_calls), result.output)
        provisioned_target, plan, _kwargs = self._provision_calls[0]
        self.assertEqual(self.target, provisioned_target)
        # The same RepoPlan fields the existing TestSetupRepo pins.
        self.assertEqual(8000, plan.port)
        self.assertEqual("", plan.github_token)
        self.assertFalse(plan.use_anthropic_for_frontier_modes)
        # The real provision wrote its usual artifacts into the target.
        self.assertTrue(
            (Path(self.target) / "zoo-code-settings.json").is_file()
        )
        self.assertTrue((Path(self.target) / ".roo" / "mcp.json").is_file())
        self.assertTrue(
            (Path(self.target) / ".vscode" / "extensions.json").is_file()
        )
        # A clean gate writes no ruleset and prints no recipe.
        self.assertFalse((Path(self.target) / ".github-ruleset.json").exists())
        self.assertNotIn("personal-access-tokens/new", result.output)
        self.assertNotIn("recipe", result.output.lower())

    # -- behaviour 10: --no-github skips the gate (PIN) ---------------------

    def test_no_github_skips_the_guard_seams(self):
        """With no GitHub there is nothing to gate: no resolve_repository,
        no fetch_branch_rules, no check_token_all - the seams are
        booby-trapped, so any call fails this test - and provisioning
        proceeds with an empty token."""
        boom = AssertionError("guard seam invoked under --no-github")
        self._spy_provision(invoke_real=False)
        traps = (
            mock.patch.object(
                cli.piguard, "resolve_repository", side_effect=boom
            ),
            mock.patch.object(
                cli.piguard, "fetch_branch_rules", side_effect=boom
            ),
            mock.patch.object(
                cli.piguard, "check_token_all", side_effect=boom
            ),
        )
        for patcher in traps:
            patcher.start()
            self.addCleanup(patcher.stop)

        result = self.invoke_allowing_exception(
            ["setup-repo", self.target, "--yes", "--no-github"]
        )

        self.assertEqual(0, result.exit_code, result.output)
        self.assertEqual(1, len(self._provision_calls), result.output)
        _provisioned_target, plan, _kwargs = self._provision_calls[0]
        self.assertEqual("", plan.github_token)

    # -- behaviour 6: a blocked gate prints the sectioned report (RED) ----
    # The gate reuses render_finding_block exactly as verify-guards does -
    # the behaviour-19 blocks, never re-derived - under the "Branch rules"
    # and "Token scope" headers, in that order.

    GATE_TOKEN = "ghp_blockedgate_secret_token"

    def _blocked_seams_with_token_findings(self, token_findings):
        """``_blocked_seams`` extended: ``check_token_all`` yields
        ``token_findings`` rather than none, so the blocked run has both
        branch warns and token findings to report."""
        seams = list(self._blocked_seams())
        seams[2] = mock.patch.object(
            cli.piguard,
            "check_token_all",
            return_value=token_findings,
        )
        return seams

    def _blocked_token_findings(self):
        """The token findings the blocked-report tests feed the seam: one
        ``fail`` (administration) in the shape the real probe emits -
        rule=None, the check name, a danger and a remedy - plus the
        constant ``skipped`` (workflows_withheld)."""
        return [
            token_finding(
                "administration",
                "fail",
                danger="the token can administer the target repository",
                remedy=(
                    "doc/external/github/rest-api-endpoints-for-actions-"
                    "permissions.md"
                ),
            ),
            cli.piguard.workflows_withheld_finding()[0],
        ]

    def _blocked_branch_findings(self):
        """The branch findings the seam yields: the real ``check_all`` over
        the empty rules the fetch seam returns - the same objects the run
        reports on, so the expected blocks are never re-derived."""
        return cli.piguard.check_all([])

    def _run_blocked_report(self, token_findings):
        """One blocked ``setup-repo`` run with the report fixtures wired in:
        a token in .env (the gate needs one), the branch warns from the
        empty-rules seam, and the given token findings. Returns the runner
        result."""
        self.write_env(GITHUB_TOKEN=self.GATE_TOKEN)
        for patcher in self._blocked_seams_with_token_findings(token_findings):
            patcher.start()
            self.addCleanup(patcher.stop)
        return self.invoke_allowing_exception(
            ["setup-repo", self.target, "--yes"]
        )

    def test_blocked_gate_prints_branch_rules_header_then_token_scope_header(
        self,
    ):
        """The blocked report carries a 'Branch rules' header before the
        first branch finding block and a 'Token scope' header before the
        first token finding block - branch headers precede the token
        header (behaviour 6)."""
        branch_findings = self._blocked_branch_findings()
        token_findings = self._blocked_token_findings()
        result = self._run_blocked_report(token_findings)
        lines = result.output.splitlines()

        def header_index(name):
            for index, line in enumerate(lines):
                if line == name:
                    return index
            self.fail(
                "the blocked report has no {!r} header line:\n{}".format(
                    name, result.output
                )
            )

        def first_headline_index(finding):
            headline = _finding_headline(finding)
            for index, line in enumerate(lines):
                if line.lstrip().startswith(headline):
                    return index
            self.fail(
                "the blocked report has no block for the finding with "
                "headline {!r}:\n{}".format(headline, result.output)
            )

        branch_header = header_index("Branch rules")
        token_header = header_index("Token scope")
        self.assertLess(
            branch_header,
            token_header,
            "the 'Branch rules' header must precede the 'Token scope' "
            "header:\n{}".format(result.output),
        )
        self.assertGreater(
            first_headline_index(branch_findings[0]),
            branch_header,
            "'Branch rules' must come before the first branch finding "
            "block (headline {!r}):\n{}".format(
                _finding_headline(branch_findings[0]), result.output
            ),
        )
        self.assertGreater(
            first_headline_index(token_findings[0]),
            token_header,
            "'Token scope' must come before the first token finding "
            "block (headline {!r}):\n{}".format(
                _finding_headline(token_findings[0]), result.output
            ),
        )

    def test_blocked_gate_finding_lines_match_render_finding_block(self):
        """Every line of ``render_finding_block(finding)`` - computed in
        this test from the same fixture the seam returns - appears in the
        blocked output in report order: the block is reused, never
        re-derived (behaviour 6)."""
        branch_finding = self._blocked_branch_findings()[0]
        token_findings = self._blocked_token_findings()
        token_finding = token_findings[0]
        result = self._run_blocked_report(token_findings)
        lines = result.output.splitlines()

        expected = (
            cli.piguard.render_finding_block(branch_finding)
            + cli.piguard.render_finding_block(token_finding)
        )
        # The branch block reports before the token block, so a single
        # forward cursor pins both blocks' lines in report order without
        # pinning the surrounding whitespace.
        cursor = 0
        for block_line in expected:
            for index in range(cursor, len(lines)):
                if lines[index].lstrip() == block_line.lstrip():
                    cursor = index + 1
                    break
            else:
                self.fail(
                    "a line of the reused finding block is missing or out "
                    "of order: {!r}\n{}".format(block_line, result.output)
                )

    def test_no_report_line_exceeds_80_characters(self):
        """Every line of the sectioned report - from the 'Branch rules'
        header through the report's tail (the numbered "To fix" section when
        present, the trailing note) - is at most 80 characters (behaviour 6;
        re-pointed for behaviour 9 of plans/guard-finding-compact.md, whose
        new tail joins the report). The end anchor stays the last token
        block's lines: the 80-column bound self-derives from the blocks, the
        fix entries and the note render at the same width."""
        token_findings = self._blocked_token_findings()
        result = self._run_blocked_report(token_findings)
        lines = result.output.splitlines()

        start = None
        for index, line in enumerate(lines):
            if line == "Branch rules":
                start = index
                break
        if start is None:
            self.fail(
                "the blocked report has no 'Branch rules' header:\n{}".format(
                    result.output
                )
            )

        last_block = cli.piguard.render_finding_block(token_findings[-1])
        headline_index = None
        for index, line in enumerate(lines[start:], start):
            if line.lstrip() == last_block[0]:
                headline_index = index
                break
        if headline_index is None:
            self.fail(
                "no block for the last token finding (headline {!r}):\n{}".format(
                    last_block[0], result.output
                )
            )

        end = headline_index + len(last_block)
        offenders = [line for line in lines[start:end] if len(line) > 80]
        self.assertEqual(
            [],
            offenders,
            "report lines exceed 80 characters:\n{}".format(
                "\n".join(repr(line) for line in offenders)
            ),
        )

    def test_a_skipped_finding_is_shown_not_hidden(self):
        """A ``skipped`` finding is reported too - it is honest, not hidden
        (behaviour 6). The pinned headline is the marked form - ``lstrip``
        does not remove the glyph, so this pin fails while the
        implementation prints an unmarked headline."""
        token_findings = self._blocked_token_findings()
        skipped = token_findings[-1]
        self.assertEqual("skipped", skipped["status"])
        result = self._run_blocked_report(token_findings)

        headline = _finding_headline(skipped)
        self.assertTrue(
            any(
                line.lstrip().startswith(headline)
                for line in result.output.splitlines()
            ),
            "the skipped finding's block headline {!r} must be "
            "reported (the em-dash brief follows the mark, prefix and "
            "label):\n{}".format(headline, result.output),
        )

    def test_the_token_value_is_never_echoed(self):
        """Guard (already green while the one-line placeholder is in
        place): the ``GITHUB_TOKEN`` value in .env never appears in the
        blocked report (behaviour 6)."""
        result = self._run_blocked_report(self._blocked_token_findings())
        self.assertNotIn(self.GATE_TOKEN, result.output)

    # -- behaviour 7: a blocked gate prepares the ruleset (RED) ------------
    # needs_ruleset is true for the class's default blocked seams (five
    # branch warns, no token findings), so every blocked run below is a
    # run that must prepare TARGET/.github-ruleset.json.

    RULESET_NAME = ".github-ruleset.json"

    def _blocked_run_wiring(self, write_spy=None):
        """The blocked-run seams plus, optionally, a spy over
        ``piruleset.write_ruleset`` (recording ``force`` and returning the
        path, or raising the given exception)."""
        patchers = self._blocked_seams()
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        if write_spy is not None:
            spy_patcher = mock.patch.object(
                cli.piruleset, "write_ruleset", write_spy
            )
            spy_patcher.start()
            self.addCleanup(spy_patcher.stop)

    def _ruleset_path(self):
        return Path(self.target) / self.RULESET_NAME

    def test_blocked_gate_writes_the_ruleset_when_absent(self):
        """Blocked run, ruleset absent: the gate writes
        TARGET/.github-ruleset.json with the rendered five-rule ruleset
        byte-for-byte, prints the written path and the manual import
        steps, and still exits blocked (RED - the blocked path writes no
        file yet)."""
        self.write_env(GITHUB_TOKEN="ghp_test")
        self.assertFalse(self._ruleset_path().exists())
        self._spy_provision(invoke_real=True)
        self._blocked_run_wiring()

        result = self.invoke_allowing_exception(
            ["setup-repo", self.target, "--yes"]
        )

        self.assertEqual(
            0, len(self._provision_calls), result.output
        )
        self.assertEqual(
            cli.EXIT_GUARDS_BLOCKED,
            result.exit_code,
            "a blocked gate that prepared the ruleset still exits "
            "blocked, not success: exit {}:\n{}".format(
                result.exit_code, result.output
            ),
        )
        ruleset_path = self._ruleset_path()
        self.assertTrue(
            ruleset_path.is_file(),
            "the blocked gate must write the ruleset to {}:\n{}".format(
                ruleset_path, result.output
            ),
        )
        self.assertEqual(
            piruleset.render_ruleset_json(piruleset.build_ruleset()),
            ruleset_path.read_text(encoding="utf-8"),
            "the written ruleset is not the rendered five-rule ruleset",
        )
        # The ruleset print pattern, pinned (moved in from the outgoing
        # ruleset-write command in the behaviour-13 cycle): the written path
        # is named, and at least one import step (the "Import a ruleset" line
        # from piruleset.import_steps) is printed.
        self.assertIn(
            self.RULESET_NAME,
            result.output,
            "the blocked report must name the written ruleset path "
            "{}:\n{}".format(ruleset_path, result.output),
        )
        self.assertIn(
            "Import a",
            result.output,
            "the blocked report must carry the import steps for the "
            "prepared ruleset (import_steps):\n{}".format(result.output),
        )

    def test_blocked_gate_never_overwrites_an_existing_ruleset(self):
        """Blocked run with TARGET/.github-ruleset.json pre-existing:
        force is never passed true, the file's bytes stay untouched, the
        report names the file as already prepared, and the run still
        exits blocked (RED - the gate never names the file yet)."""
        self.write_env(GITHUB_TOKEN="ghp_test")
        sentinel = "sentinel-do-not-touch"
        self._ruleset_path().write_text(sentinel, encoding="utf-8")
        self._spy_provision(invoke_real=True)
        force_kwargs = []

        def write_spy(path, text, force=False):
            # Mirrors the real write_ruleset over an existing file, so a
            # gate that checks existence itself and a gate that calls
            # write_ruleset and catches the RulesetError both run; force
            # is recorded either way.
            force_kwargs.append(force)
            raise piruleset.RulesetError(
                "refusing to overwrite {path}: an existing file is "
                "present; pass --force to overwrite it".format(path=path)
            )

        self._blocked_run_wiring(write_spy=write_spy)

        result = self.invoke_allowing_exception(
            ["setup-repo", self.target, "--yes"]
        )

        self.assertEqual(
            0, len(self._provision_calls), result.output
        )
        self.assertEqual(
            cli.EXIT_GUARDS_BLOCKED,
            result.exit_code,
            "an already-prepared ruleset never masks the block: "
            "exit {}:\n{}".format(result.exit_code, result.output),
        )
        self.assertEqual(
            sentinel,
            self._ruleset_path().read_text(encoding="utf-8"),
            "the existing ruleset file must be left untouched",
        )
        self.assertEqual([], force_kwargs)
        # The report names the file as already prepared: the path appears
        # alongside an 'already' phrasing (the existing command has no
        # equivalent - a write always claimed success - so the gate's
        # own line is pinned here).
        self.assertIn(
            self.RULESET_NAME,
            result.output,
            "the blocked report must name the existing ruleset path:\n{}".format(
                result.output
            ),
        )
        self.assertIn(
            "already",
            result.output.lower(),
            "the blocked report must say the ruleset is already "
            "prepared (not claim to have written it):\n{}".format(
                result.output
            ),
        )

    def test_blocked_gate_ruleset_error_is_reported_and_still_blocked(self):
        """Blocked run where the ruleset write fails: the failure is
        named in the report and the run still exits blocked - a
        RulesetError is never masked into success (pass-now guard:
        nothing is written yet, so no error occurs yet)."""
        self.write_env(GITHUB_TOKEN="ghp_test")
        self._spy_provision(invoke_real=True)

        def write_spy(path, text, force=False):
            raise piruleset.RulesetError(
                "cannot write ruleset to {}: its parent directory "
                "does not exist".format(path)
            )

        self._blocked_run_wiring(write_spy=write_spy)

        result = self.invoke_allowing_exception(
            ["setup-repo", self.target, "--yes"]
        )

        self.assertEqual(
            0, len(self._provision_calls), result.output
        )
        self.assertEqual(
            cli.EXIT_GUARDS_BLOCKED,
            result.exit_code,
            "a ruleset write failure must never be masked into "
            "success: exit {}:\n{}".format(result.exit_code, result.output),
        )
        # The failure is reported, not swallowed: the report names the
        # ruleset path and carries a clear could-not-write phrasing.
        self.assertIn(
            self.RULESET_NAME,
            result.output,
            "the blocked report must name the ruleset path the write "
            "failed on:\n{}".format(result.output),
        )
        self.assertIn(
            "could not write",
            result.output.lower(),
            "the blocked report must say the ruleset could not be "
            "written:\n{}".format(result.output),
        )

    # -- behaviour 8: a blocked gate prints the token recipe (RED) ---------
    # needs_token_recipe is true for the class's default token fixtures (the
    # administration fail), and the class's blocked seams resolve the
    # repository to (OWNER, REPO), so the blocked runs below are runs that
    # must print the pre-filled creation URL and the ordered UI steps - the
    # same substance the outgoing token-recipe command prints (moved in here
    # in the behaviour-13 cycle).

    def test_blocked_gate_prints_the_recipe_when_a_token_finding_fails(self):
        """Blocked run with a token ``fail``: the gate prints the exact
        pre-filled creation URL for the resolved owner/repo and every line
        of ``recipe_steps`` in order, and still exits blocked (RED - the
        blocked path prints no recipe yet, so the URL and steps are
        absent)."""
        from anvilkit.pi import pitokenrecipe

        url = pitokenrecipe.build_recipe_url(self.OWNER, self.REPO)
        steps = pitokenrecipe.recipe_steps(self.OWNER, self.REPO, url)
        result = self._run_blocked_report(self._blocked_token_findings())

        self.assertEqual(
            cli.EXIT_GUARDS_BLOCKED,
            result.exit_code,
            "a blocked gate that printed the recipe still exits "
            "blocked: exit {}:\n{}".format(result.exit_code, result.output),
        )
        lines = result.output.splitlines()
        url_index = None
        for index, line in enumerate(lines):
            if line.lstrip() == url:
                url_index = index
                break
        self.assertIsNotNone(
            url_index,
            "the blocked report has no line carrying the pre-filled "
            "creation URL {!r}:\n{}".format(url, result.output),
        )
        # The same lstrip-both-sides cursor the behaviour-6 block test
        # uses: every step line appears after the URL line, in order.
        cursor = url_index
        for step in steps:
            for index in range(cursor, len(lines)):
                if lines[index].lstrip() == step.lstrip():
                    cursor = index + 1
                    break
            else:
                self.fail(
                    "a recipe step line is missing or out of order: "
                    "{!r}\n{}".format(step, result.output)
                )

    def test_no_recipe_when_no_token_finding_fails(self):
        """Blocked run whose token findings are ``skipped`` only (the
        constant workflows-withheld finding): the branch warns still block,
        but with no token ``fail`` the gate prints no recipe at all -
        neither the pre-filled URL nor any step line (pass-now guard)."""
        from anvilkit.pi import pitokenrecipe

        url = pitokenrecipe.build_recipe_url(self.OWNER, self.REPO)
        steps = pitokenrecipe.recipe_steps(self.OWNER, self.REPO, url)
        result = self._run_blocked_report(
            [cli.piguard.workflows_withheld_finding()[0]]
        )

        self.assertEqual(
            cli.EXIT_GUARDS_BLOCKED,
            result.exit_code,
            "skipped-only token findings still block via the branch "
            "warns: exit {}:\n{}".format(result.exit_code, result.output),
        )
        self.assertNotIn(
            url,
            result.output,
            "no token fail means no recipe: the pre-filled URL {!r} must "
            "not be printed:\n{}".format(url, result.output),
        )
        for step in steps:
            self.assertNotIn(
                step,
                result.output,
                "no token fail means no recipe: the step line {!r} must "
                "not be printed:\n{}".format(step, result.output),
            )

    def test_recipe_error_is_reported_and_still_blocked(self):
        """Blocked run where ``build_recipe_url`` raises
        ``TokenRecipeError``: the failure is reported in the blocked output
        and the run still exits blocked - the recipe error never masks the
        block (red now, for the wrong reason: the blocked path attempts no
        recipe, so the 'could not build' line is absent; the exit-9 half
        already holds)."""
        from anvilkit.pi import pitokenrecipe

        patcher = mock.patch.object(
            cli.pitokenrecipe,
            "build_recipe_url",
            side_effect=pitokenrecipe.TokenRecipeError(
                "refusing to build a recipe URL without an owner: "
                "target_name is the resource owner and is never guessed"
            ),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        result = self._run_blocked_report(self._blocked_token_findings())

        self.assertEqual(
            cli.EXIT_GUARDS_BLOCKED,
            result.exit_code,
            "a recipe build failure must never be masked into "
            "success: exit {}:\n{}".format(result.exit_code, result.output),
        )
        # The same could-not phrasing the behaviour-7 ruleset error pins
        # ("could not write"): a clear what-happened line, not the raw
        # exception text.
        self.assertIn(
            "could not build the token recipe",
            result.output.lower(),
            "the blocked report must say the token recipe could not be "
            "built:\n{}".format(result.output),
        )

    # -- behaviour 9: a blocked gate exits 9 (PIN) --------------------------
    # The code was implemented in behaviour 4's green (the blocked path
    # already raises EXIT_GUARDS_BLOCKED); these boundary pins tighten the
    # earlier `!= 0` and `not in (2, 3)` pins to the exact code, pin the
    # re-run-setup-repo message, and pin the non-reuse of 9.

    def test_blocked_gate_exits_exactly_nine(self):
        """A blocked run exits ``EXIT_GUARDS_BLOCKED`` and that constant
        is literally 9 - a new failure class: nothing was provisioned and
        nothing is wrong with Anvil, so neither 5 (provisioning failed
        part-way) nor 1 (internal) (behaviour 9). Tightens the existing
        ``!= 0`` / ``not in (2, 3)`` pins to the exact code."""
        self.write_env(GITHUB_TOKEN="ghp_test")
        self._spy_provision(invoke_real=True)
        for patcher in self._blocked_seams():
            patcher.start()
            self.addCleanup(patcher.stop)

        result = self.invoke_allowing_exception(
            ["setup-repo", self.target, "--yes"]
        )

        self.assertEqual(0, len(self._provision_calls), result.output)
        self.assertEqual(
            9,
            cli.EXIT_GUARDS_BLOCKED,
            "EXIT_GUARDS_BLOCKED is literally 9, got {}".format(
                cli.EXIT_GUARDS_BLOCKED
            ),
        )
        self.assertEqual(
            cli.EXIT_GUARDS_BLOCKED,
            result.exit_code,
            "a blocked gate exits exactly 9: exit {}:\n{}".format(
                result.exit_code, result.output
            ),
        )

    def test_blocked_gate_message_names_re_running_setup_repo(self):
        """The last line a blocked run prints - the ``⛔`` line after the
        last prepared fix - tells the junior to fix GitHub and re-run
        ``setup-repo``: the line carries both (behaviour 9)."""
        result = self._run_blocked_report(self._blocked_token_findings())

        lines = [line for line in result.output.splitlines() if line.strip()]
        trailing = lines[-1]
        self.assertTrue(
            trailing.lstrip().startswith("⛔"),
            "the last line of a blocked run is the ⛔ re-run line, "
            "got {!r}:\n{}".format(trailing, result.output),
        )
        message = trailing.lower()
        self.assertIn(
            "setup-repo",
            message,
            "the blocked report must name setup-repo as the command "
            "to re-run:\n{}".format(result.output),
        )
        self.assertIn(
            "re-run",
            message,
            "the blocked report must tell the junior to re-run after "
            "fixing GitHub:\n{}".format(result.output),
        )

    def test_exit_nine_is_not_reused_by_any_other_command(self):
        """The blocked gate's code is its own failure class: no other
        ``EXIT_*`` constant in cli carries the value 9 (behaviour 9)."""
        self.assertEqual(9, cli.EXIT_GUARDS_BLOCKED)
        colliding = sorted(
            name
            for name, value in vars(cli).items()
            if name.startswith("EXIT_")
            and name != "EXIT_GUARDS_BLOCKED"
            and value == 9
        )
        self.assertEqual(
            [],
            colliding,
            "exit code 9 is reused by: {}".format(colliding),
        )

    # -- behaviour 11: non-interactive and --yes ---------------------------
    # A blocked run must never ask a question it will then discard: the gate
    # sits after _resolve_github_token (a stored token is reused without
    # prompting - the store lookup precedes the interactivity guard) and
    # before _resolve_frontier / _resolve_oxylabs. _prompt_traps booby-traps
    # every question function those resolvers use (prompts.confirm,
    # prompts.ask_required, prompts.choose, plus the low-level readers), so
    # any prompt asked on a blocked run fails the test loudly.

    def _prompt_traps(self):
        """Patcher over every question function a blocked run must not
        reach: ``prompts.confirm``, ``prompts.ask``, ``prompts.ask_required``,
        ``prompts.ask_port`` and ``prompts.choose`` (the seams
        ``_resolve_github_token``, ``_resolve_frontier`` and
        ``_resolve_oxylabs`` call), plus the low-level ``_read_line`` /
        ``_read_confirmation`` readers, so any read of stdin fails the test.
        Patched on ``cli.prompts`` - the same module object cli imports, so
        the traps arm the real call path."""
        boom = AssertionError("prompt asked on a blocked run")
        return (
            mock.patch.object(cli.prompts, "confirm", side_effect=boom),
            mock.patch.object(cli.prompts, "ask", side_effect=boom),
            mock.patch.object(cli.prompts, "ask_required", side_effect=boom),
            mock.patch.object(cli.prompts, "ask_port", side_effect=boom),
            mock.patch.object(cli.prompts, "choose", side_effect=boom),
            mock.patch.object(cli.prompts, "_read_line", side_effect=boom),
            mock.patch.object(
                cli.prompts, "_read_confirmation", side_effect=boom
            ),
        )

    def test_blocked_gate_with_yes_prints_fixes_and_exits_nine_no_prompt(
        self,
    ):
        """Blocked run with ``--yes`` (token stored in .env, so no token
        prompt is needed): the report headers, the prepared ruleset fix
        (the written path named plus an import step) and the exit 9 all
        print, with no prompt asked and provision never called
        (behaviour 11)."""
        self.write_env(GITHUB_TOKEN=self.GATE_TOKEN)
        self._spy_provision(invoke_real=True)
        for patcher in self._blocked_seams():
            patcher.start()
            self.addCleanup(patcher.stop)
        for patcher in self._prompt_traps():
            patcher.start()
            self.addCleanup(patcher.stop)

        result = self.invoke_allowing_exception(
            ["setup-repo", self.target, "--yes"]
        )

        self.assertEqual(
            cli.EXIT_GUARDS_BLOCKED,
            result.exit_code,
            "a blocked gate under --yes exits 9: exit {}:\n{}".format(
                result.exit_code, result.output
            ),
        )
        self.assertIn(
            "Branch rules",
            result.output,
            "the blocked report must carry the 'Branch rules' "
            "header:\n{}".format(result.output),
        )
        self.assertIn(
            "Token scope",
            result.output,
            "the blocked report must carry the 'Token scope' "
            "header:\n{}".format(result.output),
        )
        # The prepared fix: the class's default blocked seams trigger
        # needs_ruleset (branch warns, no token fail), so the written path
        # is named and at least one manual import step is printed.
        self.assertIn(
            self.RULESET_NAME,
            result.output,
            "the blocked report must name the prepared ruleset "
            "path:\n{}".format(result.output),
        )
        self.assertIn(
            "Import a",
            result.output,
            "the blocked report must carry the ruleset import "
            "steps:\n{}".format(result.output),
        )
        self.assertEqual(0, len(self._provision_calls), result.output)
        self.assertNotIn(self.GATE_TOKEN, result.output)

    def test_blocked_gate_non_interactive_no_yes_exits_nine(self):
        """Blocked run with no ``--yes`` and stdin genuinely closed
        (``input=""`` - the CI runner's EOF; CliRunner's stdin is not a
        tty, so the real ``_is_interactive`` seam resolves non-interactive
        itself, unpatched): the stored token is reused without the token
        prompt (its lookup precedes the interactivity guard), the gate
        blocks, and the run ends with the report and the prepared fixes at
        exit 9 - not usage 2, not missing-value 6, no prompt asked,
        provision never called (behaviour 11, the CI story)."""
        self.write_env(GITHUB_TOKEN=self.GATE_TOKEN)
        self._spy_provision(invoke_real=True)
        for patcher in self._blocked_seams():
            patcher.start()
            self.addCleanup(patcher.stop)
        for patcher in self._prompt_traps():
            patcher.start()
            self.addCleanup(patcher.stop)

        result = self.invoke_allowing_exception(
            ["setup-repo", self.target], input=""
        )

        self.assertNotIn(
            result.exit_code,
            (cli.EXIT_USAGE, cli.EXIT_CONFIG, cli.EXIT_PROMPT),
            "a blocked gate on a closed stdin is not a usage, config or "
            "missing-value error: exit {}:\n{}".format(
                result.exit_code, result.output
            ),
        )
        self.assertEqual(
            cli.EXIT_GUARDS_BLOCKED,
            result.exit_code,
            "a blocked gate on a closed stdin exits 9: exit "
            "{}:\n{}".format(result.exit_code, result.output),
        )
        # The stored-token branch of _resolve_github_token is the one that
        # ran - reused without prompting, before any interactivity decision.
        self.assertIn(
            "Reusing existing GITHUB_TOKEN from .env",
            result.output,
            "the stored token must be reused without prompting:\n{}".format(
                result.output
            ),
        )
        self.assertIn(
            "Branch rules",
            result.output,
            "the blocked report must carry the 'Branch rules' "
            "header:\n{}".format(result.output),
        )
        self.assertIn(
            "Token scope",
            result.output,
            "the blocked report must carry the 'Token scope' "
            "header:\n{}".format(result.output),
        )
        self.assertIn(
            self.RULESET_NAME,
            result.output,
            "the blocked report must name the prepared ruleset "
            "path:\n{}".format(result.output),
        )
        self.assertEqual(0, len(self._provision_calls), result.output)
        self.assertNotIn(self.GATE_TOKEN, result.output)

    def test_yes_does_not_auto_import_anything(self):
        """Blocked run with ``--yes`` and both fixes triggered (a token
        ``fail`` earns the recipe): ``--yes`` auto-imports nothing. The run
        makes zero HTTP calls - every GitHub call the gate can make is a
        GET (the read-only probes, all kept offline by the class's seams),
        and anvilkit/pi/piguard.py exposes no write-to-GitHub function at
        all - no import/create seam exists to arm - so the opener itself
        (``urllib.request.urlopen``) is booby-trapped instead: any HTTP
        request fails the test. The ruleset is written only as a local
        file, the token recipe is only printed, the run still exits 9, and
        the token value is not echoed (behaviour 11's Error clause)."""
        from anvilkit.pi import pitokenrecipe

        self.write_env(GITHUB_TOKEN=self.GATE_TOKEN)
        self._spy_provision(invoke_real=True)
        for patcher in self._blocked_seams_with_token_findings(
            self._blocked_token_findings()
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        boom = AssertionError(
            "--yes auto-imported something: the gate made an HTTP request"
        )
        opener_patcher = mock.patch.object(
            cli.piguard.urllib.request, "urlopen", side_effect=boom
        )
        opener_patcher.start()
        self.addCleanup(opener_patcher.stop)

        result = self.invoke_allowing_exception(
            ["setup-repo", self.target, "--yes"]
        )

        self.assertEqual(
            cli.EXIT_GUARDS_BLOCKED,
            result.exit_code,
            "--yes changes nothing about the gate's refusal to import: "
            "exit {}:\n{}".format(result.exit_code, result.output),
        )
        self.assertEqual(0, len(self._provision_calls), result.output)
        # The only write the run makes is the local ruleset file, with the
        # rendered five-rule content.
        ruleset_path = self._ruleset_path()
        self.assertTrue(
            ruleset_path.is_file(),
            "the blocked gate must write the ruleset to {}:\n{}".format(
                ruleset_path, result.output
            ),
        )
        self.assertEqual(
            piruleset.render_ruleset_json(piruleset.build_ruleset()),
            ruleset_path.read_text(encoding="utf-8"),
        )
        # The recipe is printed, not executed: the pre-filled URL as its
        # own line, then the ordered UI steps.
        url = pitokenrecipe.build_recipe_url(self.OWNER, self.REPO)
        self.assertIn(
            url,
            result.output,
            "the blocked report must print the pre-filled creation "
            "URL:\n{}".format(result.output),
        )
        steps = pitokenrecipe.recipe_steps(self.OWNER, self.REPO, url)
        self.assertIn(
            steps[0],
            result.output,
            "the blocked report must print the token recipe steps:\n{}".format(
                result.output
            ),
        )
        self.assertNotIn(self.GATE_TOKEN, result.output)

    # -- behaviour 12: --dry-run and a blocked gate (RED) ------------------
    # --dry-run is the module's global promise that nothing is written.
    # The blocked gate's _prepare_gate_ruleset ignores shared.dry_run
    # today and writes TARGET/.github-ruleset.json unconditionally, so the
    # first two tests below are the reds; the recipe test is a pass-now
    # guard - printing is not writing, and the recipe is only echoed.

    def _run_dry_run_blocked_gate(self):
        """A ``--dry-run setup-repo`` run with both fixes triggered: the
        branch warns (``needs_ruleset``) plus a token ``fail``
        (``needs_token_recipe``), the token stored in .env, provision
        spied with the real provision underneath. Returns the runner
        result."""
        self.write_env(GITHUB_TOKEN=self.GATE_TOKEN)
        self._spy_provision(invoke_real=True)
        for patcher in self._blocked_seams_with_token_findings(
            self._blocked_token_findings()
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        return self.invoke_allowing_exception(
            ["--dry-run", "setup-repo", self.target, "--yes"]
        )

    def test_dry_run_blocked_gate_writes_nothing(self):
        """``--dry-run setup-repo`` with a blocked gate and both fixes
        triggered writes nothing into the target: the recursive
        before/after snapshot is identical - no ``.github-ruleset.json``,
        nothing else either - provision is never reached, and the exit is
        still 9 (behaviour 12, RED: the gate writes the ruleset
        unconditionally today)."""
        before = self._target_snapshot()

        result = self._run_dry_run_blocked_gate()

        self.assertEqual(
            cli.EXIT_GUARDS_BLOCKED,
            result.exit_code,
            "a dry-run blocked gate still exits 9: exit {}:\n{}".format(
                result.exit_code, result.output
            ),
        )
        self.assertEqual(0, len(self._provision_calls), result.output)
        after = self._target_snapshot()
        self.assertEqual(
            before,
            after,
            "--dry-run must leave the target byte-for-byte unchanged; "
            "files that appeared: {}".format(
                sorted(set(after) - set(before))
            ),
        )
        self.assertFalse(
            self._ruleset_path().is_file(),
            "--dry-run must not create the ruleset at {}:\n{}".format(
                self._ruleset_path(), result.output
            ),
        )

    def test_dry_run_blocked_gate_announces_the_ruleset_path(self):
        """``--dry-run setup-repo`` with a blocked gate announces the
        ruleset path it *would* write: a line of the output carries both
        the path and the file's dry-run announcement phrasing 'would'
        ('would write', 'would store', 'would create', 'would merge'),
        and the output never claims the file was written (behaviour 12,
        RED: today the gate writes and announces 'Wrote the ruleset
        to')."""
        result = self._run_dry_run_blocked_gate()

        self.assertEqual(
            cli.EXIT_GUARDS_BLOCKED,
            result.exit_code,
            "a dry-run blocked gate still exits 9: exit {}:\n{}".format(
                result.exit_code, result.output
            ),
        )
        announced = [
            line
            for line in result.output.splitlines()
            if "would" in line.lower() and self.RULESET_NAME in line
        ]
        self.assertNotEqual(
            [],
            announced,
            "--dry-run must announce the ruleset path it would write "
            "({}): no line carries both 'would' and the path:\n{}".format(
                self._ruleset_path(), result.output
            ),
        )
        self.assertNotIn(
            "wrote the ruleset",
            result.output.lower(),
            "--dry-run must not claim to have written the ruleset:\n{}".format(
                result.output
            ),
        )

    def test_dry_run_blocked_gate_still_prints_the_recipe(self):
        """``--dry-run setup-repo`` with a blocked gate and a token
        ``fail`` still prints the token recipe: the pre-filled creation
        URL as its own line, then every ``recipe_steps`` line in order -
        printing is not writing, so the module's --dry-run rule (no
        writes) does not suppress it (behaviour 12; pass-now guard: the
        recipe is only echoed and already prints under --dry-run)."""
        from anvilkit.pi import pitokenrecipe

        result = self._run_dry_run_blocked_gate()

        self.assertEqual(
            cli.EXIT_GUARDS_BLOCKED,
            result.exit_code,
            "a dry-run blocked gate still exits 9: exit {}:\n{}".format(
                result.exit_code, result.output
            ),
        )
        url = pitokenrecipe.build_recipe_url(self.OWNER, self.REPO)
        steps = pitokenrecipe.recipe_steps(self.OWNER, self.REPO, url)
        lines = result.output.splitlines()
        url_index = None
        for index, line in enumerate(lines):
            if line.lstrip() == url:
                url_index = index
                break
        self.assertIsNotNone(
            url_index,
            "the dry-run blocked report must still print the pre-filled "
            "creation URL {!r}:\n{}".format(url, result.output),
        )
        # The same lstrip-both-sides cursor the behaviour-8 test uses:
        # every step line appears after the URL line, in order.
        cursor = url_index
        for step in steps:
            for index in range(cursor, len(lines)):
                if lines[index].lstrip() == step.lstrip():
                    cursor = index + 1
                    break
            else:
                self.fail(
                    "a recipe step line is missing or out of order under "
                    "--dry-run: {!r}\n{}".format(step, result.output)
                )

    # -- behaviour 9 of plans/guard-finding-compact.md: the report's new
    # tail (numbered fixes, then the note) is printed by the shared
    # _echo_guard_report, so the blocked gate's report carries it too.

    def test_blocked_gate_report_ends_with_fixes_then_note_before_the_prepared_fixes(
        self,
    ):
        """A blocked run's report - the part _echo_guard_report prints -
        ends with the numbered "To fix" section (the real
        ``render_fixes`` output for the branch findings plus the token
        findings, in one sequence) followed by a blank line and
        ``BYPASS_NOTE``; the gate's own prepared fixes (the ruleset import
        steps, the re-run line) still come AFTER the report, so the new
        tail does not swallow them (behaviour 9; behaviour 10's territory
        re-pinned only where the tail touched it)."""
        branch_findings = self._blocked_branch_findings()
        token_findings = self._blocked_token_findings()
        result = self._run_blocked_report(token_findings)
        lines = result.output.splitlines()

        fixes = cli.piguard.render_fixes(branch_findings + token_findings)
        self.assertGreaterEqual(
            len(fixes),
            2,
            "the blocked fixture (five branch warns plus a token fail) "
            "must earn a numbered section:\n{}".format(result.output),
        )

        # The tail starts right after the last token finding block: a
        # blank line, then the "To fix" header, then every entry in order.
        last_block = cli.piguard.render_finding_block(token_findings[-1])
        block_end = lines.index(last_block[-1])
        self.assertEqual(
            "",
            lines[block_end + 1],
            "a blank line must separate the token blocks from the "
            "'To fix' section:\n{}".format(result.output),
        )
        self.assertEqual(
            "To fix",
            lines[block_end + 2],
            "the numbered section's header must follow the last token "
            "block:\n{}".format(result.output),
        )
        cursor = block_end + 3
        for fix_line in fixes[1:]:
            for index in range(cursor, len(lines)):
                if lines[index] == fix_line:
                    cursor = index + 1
                    break
            else:
                self.fail(
                    "a numbered fix entry is missing or out of order: "
                    "{!r}\n{}".format(fix_line, result.output)
                )
        # ...then a blank line and the note.
        self.assertEqual(
            "",
            lines[cursor],
            "a blank line must separate the numbered fixes from the "
            "note:\n{}".format(result.output),
        )
        self.assertEqual(
            cli.piguard.BYPASS_NOTE,
            lines[cursor + 1],
            "the note must follow the numbered fixes:\n{}".format(
                result.output
            ),
        )
        # The gate's own prepared fixes still follow the report
        # (behaviour 10): the ruleset import steps and the final re-run
        # line come after the note, not before it.
        after_note = lines[cursor + 2:]
        self.assertTrue(
            any("Import a" in line for line in after_note),
            "the prepared ruleset's import steps must still be printed "
            "after the report:\n{}".format(result.output),
        )
        self.assertTrue(
            any(line.lstrip().startswith("⛔") for line in after_note),
            "the final re-run line must still be the last thing a "
            "blocked run prints:\n{}".format(result.output),
        )


class TestGuardReportFixesAndNote(CliCase):
    """The report prints the numbered fixes last, then the note
    (behaviour 9 of plans/guard-finding-compact.md).

    The seam is ``cli._echo_guard_report`` itself, driven with a real
    ``Context`` whose ``echo`` is captured - the same capture the resolver
    tests use - so the pins assert what the report prints, not what a
    command happens to add around it. The blocks and the fix entries are
    computed through the real ``render_finding_block`` / ``render_fixes``
    (never re-derived); only the approved sample's exact words and the
    tail shape are pinned verbatim.
    """

    def _shared_with_captured_echo(self):
        """A ``Context`` pointing at the test project whose ``echo``
        collects its lines; returns ``(shared, lines)``."""
        shared = cli.Context(
            dry_run=False, verbose=False, no_color=False, assume_yes=True
        )
        lines = []
        patcher = mock.patch.object(
            cli.typer, "echo", side_effect=lambda msg="": lines.append(str(msg))
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return shared, lines

    def _warn_fail_findings(self):
        """The warn/fail fixture: the real ``check_all`` over the empty
        rules (five branch warns with the sample's UI-label remedies) plus
        a token warn and a token fail with short sample-shaped remedies -
        enough of both sections that the one fix sequence spans them."""
        branch = cli.piguard.check_all([])
        token = [
            token_finding(
                "target_access",
                "warn",
                danger="cannot see the target repository",
                remedy="recreate the token with access to iar3-r8/anvil only",
            ),
            token_finding(
                "classic_token",
                "fail",
                danger="a classic token reaches every repository",
                remedy="recreate it as a fine-grained token, iar3-r8/anvil only",
            ),
        ]
        return branch, token

    def test_warn_fail_report_ends_with_the_numbered_fixes_then_the_note(self):
        """Branch blocks, token blocks, a blank line, the numbered
        "To fix" section (the real ``render_fixes`` of branch plus token),
        a blank line, the note - and the note is the LAST line (behaviour
        9's Then clause)."""
        branch, token = self._warn_fail_findings()
        shared, lines = self._shared_with_captured_echo()
        cli._echo_guard_report(shared, branch, token)

        fixes = cli.piguard.render_fixes(branch + token)
        self.assertGreaterEqual(
            len(fixes), 2, "the fixture must earn a numbered section"
        )
        # The section follows both sections' blocks: its header comes
        # after the last token block's headline.
        last_block = cli.piguard.render_finding_block(token[-1])
        self.assertIn(
            "To fix",
            lines,
            "the report must print the numbered 'To fix' section when "
            "findings carry warn or fail:\n{}".format("\n".join(lines)),
        )
        self.assertIn(
            last_block[0],
            lines,
            "the last token finding block is missing:\n{}".format(
                "\n".join(lines)
            ),
        )
        self.assertGreater(
            lines.index("To fix"),
            lines.index(last_block[0]),
            "the 'To fix' section must come after every finding block:\n"
            "{}".format("\n".join(lines)),
        )
        # Its entries appear in order, self-derived from the seam.
        cursor = lines.index("To fix") + 1
        for fix_line in fixes[1:]:
            for index in range(cursor, len(lines)):
                if lines[index] == fix_line:
                    cursor = index + 1
                    break
            else:
                self.fail(
                    "a numbered fix entry is missing or out of order: "
                    "{!r}\n{}".format(fix_line, "\n".join(lines))
                )
        # Then a blank line and the note, which is the last line.
        self.assertEqual(
            "",
            lines[cursor],
            "a blank line must separate the numbered fixes from the "
            "note:\n{}".format("\n".join(lines)),
        )
        self.assertEqual(
            cli.piguard.BYPASS_NOTE,
            lines[-1],
            "the note must be the report's last line:\n{}".format(
                "\n".join(lines)
            ),
        )
        self.assertEqual(
            cursor + 1,
            len(lines) - 1,
            "nothing may follow the note:\n{}".format("\n".join(lines)),
        )

    def test_warn_fail_report_numbers_the_fixes_across_both_sections_in_one_sequence(
        self,
    ):
        """The branch warn and the token warn/fail share one numbered
        sequence: the branch entries keep the sample's exact words at
        their combined numbers, and the token entry is numbered after
        every branch entry - per-section numbering (a token entry
        restarting at 1) would fail this pin (behaviour 9's 'numbered
        across both sections in one sequence')."""
        branch, token = self._warn_fail_findings()
        shared, lines = self._shared_with_captured_echo()
        cli._echo_guard_report(shared, branch, token)

        # One exact entry from the branch section, at its combined number.
        self.assertIn(
            '1. non_fast_forward: turn on "Block force pushes" for main',
            lines,
            "the first branch fix must open the single sequence at 1 "
            "with the sample's words:\n{}".format("\n".join(lines)),
        )
        self.assertIn(
            '2. deletion: turn on "Restrict deletions" for main',
            lines,
            "the branch deletion fix must keep the sample's words at its "
            "combined number:\n{}".format("\n".join(lines)),
        )
        # One exact entry from the token section, numbered AFTER the five
        # branch warns - the proof the sequence does not restart.
        self.assertIn(
            "6. target_access: recreate the token with access to "
            "iar3-r8/anvil only",
            lines,
            "the token fix must be numbered in the one sequence that "
            "continues the branch numbers (not restarted at 1):\n{}".format(
                "\n".join(lines)
            ),
        )

    def test_all_passed_report_has_no_to_fix_section_but_still_ends_with_the_note(
        self,
    ):
        """An all-passed run (no warn, no fail) prints the headers and
        every block, NO "To fix" line, NO numbered entry - and STILL
        ends with the blank line plus the note (behaviour 9's Error
        clause)."""
        branch = cli.piguard.check_all(five_rule_branch_rules())
        token = [
            token_finding("target_access", "passed"),
            token_finding("administration", "passed"),
            token_finding("classic_token", "passed"),
            cli.piguard.workflows_withheld_finding()[0],
            token_finding("named_repo", "passed"),
        ]
        shared, lines = self._shared_with_captured_echo()
        cli._echo_guard_report(shared, branch, token)

        self.assertIn("Branch rules", lines)
        self.assertIn("Token scope", lines)
        for finding in branch + token:
            # The headline anchor is a prefix: the compact block's headline
            # carries the em-dash brief after the label, and only the
            # mark, prefix and label are stable (the suite's convention).
            headline = _finding_headline(finding)
            self.assertTrue(
                any(line.startswith(headline) for line in lines),
                "no block headline {!r} in the report:\n{}".format(
                    headline, "\n".join(lines)
                ),
            )
        self.assertNotIn("To fix", lines)
        numbered = [line for line in lines if line[:1].isdigit()]
        self.assertEqual(
            [],
            numbered,
            "an all-passed run prints no numbered entry:\n{}".format(
                "\n".join(lines)
            ),
        )
        last_block = cli.piguard.render_finding_block(token[-1])
        self.assertEqual(
            last_block[-1],
            lines[-3],
            "the last token block must end the findings, followed by the "
            "blank line and the note and nothing else:\n{}".format(
                "\n".join(lines)
            ),
        )
        self.assertEqual("", lines[-2])
        self.assertEqual(cli.piguard.BYPASS_NOTE, lines[-1])

    def test_empty_findings_print_the_headers_and_the_note_and_nothing_else(self):
        """Empty findings lists: the two headers and the note, nothing
        else - byte-for-byte (behaviour 9's Error clause)."""
        shared, lines = self._shared_with_captured_echo()
        cli._echo_guard_report(shared, [], [])

        self.assertEqual(
            ["Branch rules", "", "Token scope", "", cli.piguard.BYPASS_NOTE],
            lines,
            "empty findings must print the headers and the note and "
            "nothing else:\n{}".format("\n".join(lines)),
        )

    def test_the_note_appears_exactly_once_in_the_report(self):
        """The note is the single surviving caveat: with warn/fail
        findings it appears EXACTLY ONCE in the whole output - the
        per-finding caveat left in the earlier cycles (behaviour 9's
        premise over behaviour 8)."""
        branch, token = self._warn_fail_findings()
        shared, lines = self._shared_with_captured_echo()
        cli._echo_guard_report(shared, branch, token)

        self.assertEqual(
            1,
            lines.count(cli.piguard.BYPASS_NOTE),
            "the bypass note must appear exactly once:\n{}".format(
                "\n".join(lines)
            ),
        )


class TestGuardReportCrossSiteConsistency(CliCase):
    """All three call sites print the same compact report
    (behaviour 10 of plans/guard-finding-compact.md).

    Behaviour 9 routed the three sites through the shared
    ``cli._echo_guard_report``, so the pins here are cross-site
    consistency: the SAME finding fixture driven through ``doctor``,
    ``verify-guards`` and a blocked ``setup-repo`` must yield the
    IDENTICAL block text for every finding, every report line within
    80 columns, the "To fix" section only when a warn or fail is
    present, and each command's own invariants (the gate's exit 9 and
    its prepared ruleset and token recipe AFTER the note,
    verify-guards' ``summarize`` exit, doctor's unchanged exit)
    holding through the report's new tail. The renderer itself is not
    re-pinned here - cycles 4-9 own its substance; these pins assert
    that the three SITES agree.

    The gate site can only be driven with a fixture that blocks it -
    a blocked run has a warn or fail by construction - so the
    all-passed fixture's cross-site pin covers the two sites that also
    print an all-passed report (doctor and verify-guards); the gate's
    "To fix" positive is the behaviour-9 gate pin, and its negative is
    unexpressible (a clean gate prints no report at all).
    """

    OWNER = "iar3-r8"
    REPO = "Anvil"
    TOKEN = "ghp_crosssite_token"

    # -- the shared fixtures --------------------------------------------------

    def warn_fail_branch_findings(self):
        """The branch fixture: the real ``check_all`` over no rules -
        the five warns with the sample's UI-label remedies."""
        return cli.piguard.check_all([])

    def all_passed_branch_findings(self):
        return cli.piguard.check_all(five_rule_branch_rules())

    def warn_fail_token_findings(self):
        """A warn, a fail and the constant workflows-withheld skip, so the
        shared fixture exercises one-line warn/fail blocks, the
        two-line skipped block, and a "To fix" sequence that spans both
        sections."""
        return [
            token_finding(
                "target_access",
                "warn",
                danger="cannot see the target repository",
                remedy="recreate the token with access to iar3-r8/anvil only",
            ),
            token_finding(
                "administration",
                "fail",
                danger="the token can delete or reconfigure the repository",
                remedy="recreate the token without the Administration permission",
            ),
            cli.piguard.workflows_withheld_finding()[0],
            token_finding(
                "named_repo",
                "warn",
                danger="also reaches someorg/other",
                remedy="recreate the token with access to iar3-r8/anvil only",
            ),
        ]

    def all_passed_token_findings(self):
        return [
            token_finding("target_access", "passed"),
            token_finding("administration", "passed"),
            token_finding("classic_token", "passed"),
            cli.piguard.workflows_withheld_finding()[0],
            token_finding("named_repo", "passed"),
        ]

    # -- seams and command drivers ---------------------------------------------

    def _start_guard_seams(self, branch_findings, token_findings):
        """The four piguard seams replaced, so every command runs offline
        on exactly the fixture this test wants reported - the same
        objects the run reports on, so the expected blocks are never
        re-derived."""
        patchers = (
            mock.patch.object(
                cli.piguard,
                "resolve_repository",
                return_value=(self.OWNER, self.REPO),
            ),
            mock.patch.object(
                cli.piguard,
                "fetch_branch_rules",
                return_value=(five_rule_branch_rules(), None),
            ),
            mock.patch.object(
                cli.piguard, "check_all", return_value=branch_findings
            ),
            mock.patch.object(
                cli.piguard, "check_token_all", return_value=token_findings
            ),
        )
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_gate(self, branch_findings, token_findings):
        """One blocked ``setup-repo`` run on the shared fixture (the
        fixture must block: warn or fail by construction)."""
        self.write_env(GITHUB_TOKEN=self.TOKEN)
        self._start_guard_seams(branch_findings, token_findings)
        target = tempfile.TemporaryDirectory()
        self.addCleanup(target.cleanup)
        return self.invoke_allowing_exception(
            ["setup-repo", target.name, "--yes"]
        )

    def run_verify(self, branch_findings, token_findings):
        self.write_env(GITHUB_TOKEN=self.TOKEN)
        self._start_guard_seams(branch_findings, token_findings)
        return self.invoke_allowing_exception(
            ["verify-guards", str(self.project), "--branch", "main"]
        )

    def run_doctor(self, branch_findings, token_findings):
        self.write_env(GITHUB_TOKEN=self.TOKEN)
        self._start_guard_seams(branch_findings, token_findings)
        # doctor probes the host tooling around the Guards section; patch
        # the three compose probes so the run stays offline.
        for patcher in (
            mock.patch.object(
                cli.compose, "docker_available", return_value=True
            ),
            mock.patch.object(
                cli.compose, "compose_v2_available", return_value=True
            ),
            mock.patch.object(
                cli.compose, "nvidia_available", return_value=True
            ),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        return self.invoke_allowing_exception(["doctor"])

    # -- extraction --------------------------------------------------------------

    def _extract_block(self, lines, finding, site, output):
        """The block a site printed for ``finding``: located by its
        headline, taken in order, and each line verified against the
        renderer's own output for the same finding (the locator's
        discipline, as in the existing gate pin) - so a site that
        reordered, dropped or altered a line fails here rather than
        comparing garbage to garbage. Returns the site's lines,
        stripped, for the cross-site comparison."""
        expected = cli.piguard.render_finding_block(finding)
        headline = expected[0]
        for index, line in enumerate(lines):
            if line.lstrip() != headline.lstrip():
                continue
            block = lines[index:index + len(expected)]
            if len(block) < len(expected):
                self.fail(
                    "{} printed fewer lines than the block for {!r}:\n{}".format(
                        site, _finding_headline(finding), output
                    )
                )
            for got, want in zip(block, expected):
                self.assertEqual(
                    got.lstrip(),
                    want.lstrip(),
                    "{} printed a different line for the finding "
                    "{!r}:\n{}".format(site, _finding_headline(finding), output),
                )
            return [block_line.lstrip() for block_line in block]
        self.fail(
            "{} printed no block for the finding {!r}:\n{}".format(
                site, _finding_headline(finding), output
            )
        )

    def _report_range(self, lines, site, output):
        """``(start, end)`` of the report in a site's output: the
        'Branch rules' header through the note line, both inclusive -
        exactly the part ``_echo_guard_report`` prints, bounded so the
        gate's prepared fixes and the verify-guards/doctor trailing
        separators are excluded."""
        start = None
        for index, line in enumerate(lines):
            if line == "Branch rules":
                start = index
                break
        if start is None:
            self.fail(
                "{} output has no 'Branch rules' header:\n{}".format(
                    site, output
                )
            )
        end = None
        for index in range(len(lines) - 1, start - 1, -1):
            if lines[index] == cli.piguard.BYPASS_NOTE:
                end = index
                break
        if end is None:
            self.fail(
                "{} output has no note line closing the report:\n{}".format(
                    site, output
                )
            )
        return start, end

    # -- the cross-site consistency (behaviour 10's Then clause) ----------------

    def test_warn_fail_fixture_blocks_identical_in_all_three_sites(self):
        """The same warn/fail finding - driven through all three
        commands - yields the identical block text in each: same
        finding, same bytes, in doctor's Guards section, in
        verify-guards, and in the blocked gate."""
        branch = self.warn_fail_branch_findings()
        token = self.warn_fail_token_findings()
        gate = self.run_gate(branch, token)
        verify = self.run_verify(branch, token)
        doctor = self.run_doctor(branch, token)
        for finding in branch + token:
            gate_block = self._extract_block(
                gate.output.splitlines(), finding, "the blocked gate",
                gate.output,
            )
            verify_block = self._extract_block(
                verify.output.splitlines(), finding, "verify-guards",
                verify.output,
            )
            doctor_block = self._extract_block(
                doctor.output.splitlines(), finding, "doctor", doctor.output,
            )
            self.assertEqual(
                doctor_block,
                verify_block,
                "doctor and verify-guards printed different block text "
                "for {!r}\ndoctor: {!r}\nverify-guards: {!r}".format(
                    _finding_headline(finding), doctor_block, verify_block
                ),
            )
            self.assertEqual(
                verify_block,
                gate_block,
                "verify-guards and the blocked gate printed different "
                "block text for {!r}\nverify-guards: {!r}\ngate: "
                "{!r}".format(
                    _finding_headline(finding), verify_block, gate_block
                ),
            )

    def test_all_passed_fixture_blocks_identical_in_doctor_and_verify_guards(
        self,
    ):
        """The same all-passed finding yields the identical block text
        in doctor's Guards section and in verify-guards. The gate site
        is unexpressible here: an all-passed fixture is a clean gate,
        and a clean gate prints no report at all."""
        branch = self.all_passed_branch_findings()
        token = self.all_passed_token_findings()
        verify = self.run_verify(branch, token)
        doctor = self.run_doctor(branch, token)
        for finding in branch + token:
            doctor_block = self._extract_block(
                doctor.output.splitlines(), finding, "doctor", doctor.output,
            )
            verify_block = self._extract_block(
                verify.output.splitlines(), finding, "verify-guards",
                verify.output,
            )
            self.assertEqual(
                doctor_block,
                verify_block,
                "doctor and verify-guards printed different block text "
                "for {!r}\ndoctor: {!r}\nverify-guards: {!r}".format(
                    _finding_headline(finding), doctor_block, verify_block
                ),
            )

    # -- 80 columns across all three sites ---------------------------------------

    def test_doctor_guards_report_within_80_columns_with_fixes_and_note(self):
        """Every line of doctor's Guards report - both headers, every
        block, the "To fix" section and the note - is at most 80
        characters. Doctor had no per-site 80-column pin at all."""
        branch = self.warn_fail_branch_findings()
        token = self.warn_fail_token_findings()
        result = self.run_doctor(branch, token)
        lines = result.output.splitlines()
        start, end = self._report_range(lines, "doctor", result.output)
        offenders = [line for line in lines[start:end + 1] if len(line) > 80]
        self.assertEqual(
            [],
            offenders,
            "doctor's Guards report lines exceed 80 characters:\n{}".format(
                "\n".join(repr(line) for line in offenders)
            ),
        )

    def test_verify_guards_report_within_80_columns_with_fixes_and_note(
        self,
    ):
        """The existing verify-guards 80-column pin runs an all-passed
        report without a "To fix" tail; this one pins the warn/fail
        shape, where the numbered fixes and the note join the bound."""
        branch = self.warn_fail_branch_findings()
        token = self.warn_fail_token_findings()
        result = self.run_verify(branch, token)
        lines = result.output.splitlines()
        start, end = self._report_range(lines, "verify-guards", result.output)
        offenders = [line for line in lines[start:end + 1] if len(line) > 80]
        self.assertEqual(
            [],
            offenders,
            "verify-guards report lines exceed 80 characters:\n{}".format(
                "\n".join(repr(line) for line in offenders)
            ),
        )

    def test_blocked_gate_report_within_80_columns_with_fixes_and_note(
        self,
    ):
        """The existing gate 80-column pin ends at the last token
        block; this one spans the whole report, so the "To fix"
        section and the note that join the report's tail are within
        the bound too."""
        branch = self.warn_fail_branch_findings()
        token = self.warn_fail_token_findings()
        result = self.run_gate(branch, token)
        lines = result.output.splitlines()
        start, end = self._report_range(lines, "the blocked gate", result.output)
        offenders = [line for line in lines[start:end + 1] if len(line) > 80]
        self.assertEqual(
            [],
            offenders,
            "the blocked gate's report lines exceed 80 characters:\n{}".format(
                "\n".join(repr(line) for line in offenders)
            ),
        )

    # -- "To fix" iff warn/fail, per site ------------------------------------------

    def test_verify_guards_all_passed_prints_no_to_fix_section(self):
        """An all-passed verify-guards run prints no "To fix" line and
        no numbered entry anywhere in its report - pinned through the
        command's real output, not the shared function alone."""
        branch = self.all_passed_branch_findings()
        token = self.all_passed_token_findings()
        result = self.run_verify(branch, token)
        lines = result.output.splitlines()
        start, end = self._report_range(lines, "verify-guards", result.output)
        report = lines[start:end + 1]
        self.assertNotIn(
            "To fix",
            report,
            "an all-passed verify-guards report must print no 'To fix' "
            "section:\n{}".format(result.output),
        )
        numbered = [line for line in report if line[:1].isdigit()]
        self.assertEqual(
            [],
            numbered,
            "an all-passed verify-guards report prints no numbered "
            "entry:\n{}".format(result.output),
        )

    def test_doctor_all_passed_prints_no_to_fix_section(self):
        """An all-passed doctor run prints no "To fix" line and no
        numbered entry in its Guards report."""
        branch = self.all_passed_branch_findings()
        token = self.all_passed_token_findings()
        result = self.run_doctor(branch, token)
        lines = result.output.splitlines()
        start, end = self._report_range(lines, "doctor", result.output)
        report = lines[start:end + 1]
        self.assertNotIn(
            "To fix",
            report,
            "an all-passed doctor Guards report must print no 'To fix' "
            "section:\n{}".format(result.output),
        )
        numbered = [line for line in report if line[:1].isdigit()]
        self.assertEqual(
            [],
            numbered,
            "an all-passed doctor Guards report prints no numbered "
            "entry:\n{}".format(result.output),
        )

    def test_verify_guards_warn_fail_prints_to_fix_section(self):
        """A warn/fail verify-guards run prints the "To fix" section -
        the remedy no longer rides per finding, so the section is how a
        warn/fail report names its fixes (pinned per site, not through
        the shared function alone)."""
        branch = self.warn_fail_branch_findings()
        token = self.warn_fail_token_findings()
        result = self.run_verify(branch, token)
        lines = result.output.splitlines()
        start, end = self._report_range(lines, "verify-guards", result.output)
        self.assertIn(
            "To fix",
            lines[start:end + 1],
            "a warn/fail verify-guards report must print the 'To fix' "
            "section:\n{}".format(result.output),
        )

    def test_doctor_warn_fail_prints_to_fix_section(self):
        """A warn/fail doctor run prints the "To fix" section in its
        Guards report - doctor reports, and the fixes are part of the
        report (pinned per site)."""
        branch = self.warn_fail_branch_findings()
        token = self.warn_fail_token_findings()
        result = self.run_doctor(branch, token)
        lines = result.output.splitlines()
        start, end = self._report_range(lines, "doctor", result.output)
        self.assertIn(
            "To fix",
            lines[start:end + 1],
            "a warn/fail doctor Guards report must print the 'To fix' "
            "section:\n{}".format(result.output),
        )

    # -- the commands' own invariants through the new report tail -----------------

    def test_warn_fail_fixture_gate_nine_verify_summarize_doctor_zero(self):
        """The Error clause, one sweep on the shared warn/fail fixture:
        the blocked gate still exits 9, verify-guards still exits
        ``summarize`` of the findings it reported, and doctor's exit
        status is unaffected by the report."""
        branch = self.warn_fail_branch_findings()
        token = self.warn_fail_token_findings()
        gate = self.run_gate(branch, token)
        verify = self.run_verify(branch, token)
        doctor = self.run_doctor(branch, token)
        self.assertEqual(
            cli.EXIT_GUARDS_BLOCKED,
            gate.exit_code,
            "the blocked gate's exit changed with the compact report: "
            "exit {}\n{}".format(gate.exit_code, gate.output),
        )
        self.assertEqual(
            cli.piguard.summarize(branch + token),
            verify.exit_code,
            "verify-guards no longer exits summarize of its findings: "
            "exit {}\n{}".format(verify.exit_code, verify.output),
        )
        self.assertEqual(
            0,
            doctor.exit_code,
            "doctor's exit status changed with the compact report: "
            "exit {}\n{}".format(doctor.exit_code, doctor.output),
        )

    def test_blocked_gate_prints_ruleset_and_token_recipe_after_the_note(
        self,
    ):
        """The gate's prepared fixes follow the report's new tail: the
        prepared ruleset line and the token recipe URL both print
        AFTER the note (the existing recipe pin orders the steps after
        the URL but never pinned the URL after the report; the
        ruleset's import steps after the note are the behaviour-9
        pin)."""
        from anvilkit.pi import pitokenrecipe

        branch = self.warn_fail_branch_findings()
        token = self.warn_fail_token_findings()
        result = self.run_gate(branch, token)
        lines = result.output.splitlines()

        note_index = next(
            (index for index, line in enumerate(lines)
             if line == cli.piguard.BYPASS_NOTE),
            None,
        )
        self.assertIsNotNone(
            note_index,
            "the blocked report has no note line closing the report:\n{}".format(
                result.output
            ),
        )
        url = pitokenrecipe.build_recipe_url(self.OWNER, self.REPO)
        url_index = next(
            (index for index, line in enumerate(lines)
             if line.lstrip() == url),
            None,
        )
        self.assertIsNotNone(
            url_index,
            "the blocked report has no token recipe URL line {!r}:\n{}".format(
                url, result.output
            ),
        )
        ruleset_index = next(
            (index for index, line in enumerate(lines)
             if "Wrote the ruleset to" in line),
            None,
        )
        self.assertIsNotNone(
            ruleset_index,
            "the blocked report has no prepared-ruleset line:\n{}".format(
                result.output
            ),
        )
        self.assertGreater(
            ruleset_index,
            note_index,
            "the prepared ruleset must print AFTER the report (after "
            "the note), not before it:\n{}".format(result.output),
        )
        self.assertGreater(
            url_index,
            note_index,
            "the token recipe must print AFTER the report (after the "
            "note), not before it:\n{}".format(result.output),
        )


class TestGuardReportCompactLineCount(CliCase):
    """A clean report is at most 15 lines (behaviour 11 of
    plans/guard-finding-compact.md).

    The user's "the report is way too long" made measurable: the whole
    report - both headers, every block, the note - is counted in NON-BLANK
    lines. The plan's "Clean run - 14 non-blank lines" sample is the
    counting authority; the user's original "15" counted a blank line.
    The seam is the real ``cli._echo_guard_report``
    driven with a captured ``Context`` (the tightest seam - the line COUNT
    is a property of the report, so command-level noise is avoided) over
    the all-passed and all-failing fixtures.
    """

    # -- the fixtures (the sample's exact findings) ------------------------------

    def _clean_branch_findings(self):
        """Five branch passes - the real ``check_all`` over the five-rule
        ruleset (non_fast_forward, deletion, pull_request, update,
        file_path_restriction)."""
        return cli.piguard.check_all(five_rule_branch_rules())

    def _clean_token_findings(self):
        """Four token passes plus the constant workflows_withheld skip -
        the sample's exact clean findings (the em-dash briefs are the
        sample's words, set on the finding the way a probe would)."""
        findings = [
            token_finding("target_access", "passed"),
            token_finding("administration", "passed"),
            token_finding("classic_token", "passed"),
            cli.piguard.workflows_withheld_finding()[0],
            token_finding("named_repo", "passed"),
        ]
        briefs = {
            "target_access": "the token reaches iar3-r8/anvil",
            "administration": "Administration withheld (403)",
            "classic_token": "no classic OAuth scopes returned",
            "named_repo": "does not reach someorg/other (404)",
        }
        for finding in findings:
            if finding["check"] in briefs:
                finding["brief"] = briefs[finding["check"]]
        return findings

    def _all_failing_branch_findings(self):
        """Five branch warns - the real ``check_all`` over no rules (the
        sample's UI-label remedies)."""
        return cli.piguard.check_all([])

    def _all_failing_token_findings(self):
        """Four token fails plus the constant workflows_withheld skip -
        the same fixture as the clean run, every check failing (the
        em-dash briefs are the sample's blocked words, set the way a
        probe would)."""
        findings = [
            token_finding(
                "target_access",
                "fail",
                danger="cannot see iar3-r8/anvil, so nothing below is proof",
                remedy="recreate the token with access to iar3-r8/anvil only",
            ),
            token_finding(
                "administration",
                "fail",
                danger="the token can delete or reconfigure iar3-r8/anvil",
                remedy="recreate the token without the Administration permission",
            ),
            token_finding(
                "classic_token",
                "fail",
                danger="a classic token reaches every repo the owner can see",
                remedy="recreate it as a fine-grained token, iar3-r8/anvil only",
            ),
            cli.piguard.workflows_withheld_finding()[0],
            token_finding(
                "named_repo",
                "fail",
                danger="also reaches someorg/other, so a leak is not confined here",
                remedy="recreate the token with access to iar3-r8/anvil only",
            ),
        ]
        briefs = {
            "target_access": "cannot see iar3-r8/anvil, so nothing below is proof",
            "administration": "the token can delete or reconfigure iar3-r8/anvil",
            "classic_token": "a classic token reaches every repo the owner can see",
            "named_repo": "also reaches someorg/other, so a leak is not confined here",
        }
        for finding in findings:
            if finding["check"] in briefs:
                finding["brief"] = briefs[finding["check"]]
        return findings

    # -- the seam ------------------------------------------------------------------

    def _report_lines(self, branch, token):
        """Drive the real ``cli._echo_guard_report`` through a captured
        ``Context`` and return the report's lines - exactly the part the
        report prints, from 'Branch rules' through the note."""
        lines = []
        shared = cli.Context(
            dry_run=False, verbose=False, no_color=False, assume_yes=True
        )
        patcher = mock.patch.object(
            cli.typer, "echo", side_effect=lambda msg="": lines.append(str(msg))
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        cli._echo_guard_report(shared, branch, token)
        return lines

    @staticmethod
    def _non_blank(lines):
        return [line for line in lines if line]

    # -- the clean report ----------------------------------------------------------

    def test_clean_report_is_at_most_15_non_blank_lines(self):
        """The clean report - both headers, every block, the note - is at
        most 15 non-blank lines: the user's "way too long" complaint made
        measurable (behaviour 11's Then clause)."""
        branch = self._clean_branch_findings()
        token = self._clean_token_findings()
        lines = self._report_lines(branch, token)
        count = len(self._non_blank(lines))
        self.assertLessEqual(
            count,
            15,
            "the clean report must be at most 15 non-blank lines, got "
            "{}:\n{}".format(count, "\n".join(lines)),
        )

    def test_clean_report_is_exactly_14_non_blank_lines_as_documented(self):
        """The documented fixture (the plan's "Clean run" sample) is
        exactly 14 non-blank lines - the exact-equality anchor: two
        headers + nine one-line findings + the skip's headline + the
        how: line + the note. The user's original "15" counted a blank
        line; the at-most-15 bound is the contract, this pin documents
        the measurement (14 <= 15)."""
        branch = self._clean_branch_findings()
        token = self._clean_token_findings()
        lines = self._report_lines(branch, token)
        count = len(self._non_blank(lines))
        self.assertEqual(
            14,
            count,
            "the documented clean report must be exactly 14 non-blank "
            "lines, got {}:\n{}".format(count, "\n".join(lines)),
        )

    def test_clean_report_prints_no_to_fix_line(self):
        """A clean report (no warn, no fail) prints no "To fix" line - the
        property the 15 count relies on (the sample has none)."""
        branch = self._clean_branch_findings()
        token = self._clean_token_findings()
        lines = self._report_lines(branch, token)
        self.assertNotIn(
            "To fix",
            lines,
            "the clean report must print no 'To fix' line:\n{}".format(
                "\n".join(lines)
            ),
        )

    # -- the all-failing report (behaviour 11's Error clause) ---------------------

    def test_all_failing_report_is_longer_than_15_non_blank_lines(self):
        """The same fixture with every check failing is LONGER than the
        clean 15 (behaviour 11's Error clause)."""
        branch = self._all_failing_branch_findings()
        token = self._all_failing_token_findings()
        lines = self._report_lines(branch, token)
        count = len(self._non_blank(lines))
        self.assertGreater(
            count,
            15,
            "the all-failing report must be longer than the clean 15, "
            "got {}:\n{}".format(count, "\n".join(lines)),
        )

    def test_all_failing_report_decomposes_to_headers_findings_fixes_and_note(self):
        """The all-failing report is still "one line per finding plus the
        numbered fixes" (behaviour 11's Error clause), pinned as an exact
        non-blank decomposition:

          2  section headers            (Branch rules, Token scope)
        + 10 finding headlines          (5 branch + 5 token, the skip included)
        +  1 how: line                  (the skip's second line)
        +  1 "To fix"
        +  9 numbered entries           (one per warn/fail; the skip is not numbered)
        +  1 note
        +  2 within-width wraps          (the file_path_restriction warn headline
                                          is 85 chars and fix entry 5 is 94 chars;
                                          both exceed the 80-col bound and wrap to
                                          2 lines, per behaviours 4/5/7)
        = 26

        NOTE: the plan's task brief stated "9 finding lines" and a total of 23;
        that is short by 3 - it omits the skip's own headline (there are 10
        finding headlines, not 9) and ignores the two within-width wraps.
        The 26 measured here is the report a correct implementation actually
        prints, so the pin is set to that reachable value."""
        branch = self._all_failing_branch_findings()
        token = self._all_failing_token_findings()
        lines = self._report_lines(branch, token)
        count = len(self._non_blank(lines))
        expected = 2 + 10 + 1 + 1 + 9 + 1 + 2
        self.assertEqual(
            expected,
            count,
            "the all-failing report must decompose to {} non-blank lines "
            "(2 headers + 10 finding headlines + 1 how: line + 1 'To fix' + "
            "9 numbered entries + 1 note + 2 within-width wraps), got "
            "{}:\n{}".format(expected, count, "\n".join(lines)),
        )


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

    def run_doctor_with_guards(self, resolve_value, fetch_value, **kwargs):
        """``run_doctor`` with the piguard seams replaced, so the guard flow
        runs offline. ``fetch_value`` is the ``(rules, reason)`` pair.

        Returns ``(result, resolve_mock, fetch_mock)`` so a test can prove
        whether the fetch was reached.
        """
        started = []
        for patcher in self.probes(**kwargs):
            patcher.start()
            started.append(patcher)
        resolve = mock.patch.object(
            cli.piguard, "resolve_repository", return_value=resolve_value
        )
        fetch = mock.patch.object(
            cli.piguard, "fetch_branch_rules", return_value=fetch_value
        )
        resolve_mock = resolve.start()
        fetch_mock = fetch.start()
        started.extend((resolve, fetch))
        try:
            result = self.invoke_allowing_exception(["doctor"])
        finally:
            for patcher in started:
                patcher.stop()
        return result, resolve_mock, fetch_mock

    def guards_lines(self, result):
        """The Guards section of a doctor report, or fail saying it is absent."""
        lines = result.output.splitlines()
        try:
            start = lines.index("Guards")
        except ValueError:
            self.fail(
                "doctor output has no 'Guards' section:\n{}".format(result.output)
            )
        return lines[start:]

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

    def test_doctor_reports_a_guards_section_with_broken_guards(self):
        # An empty rules array: both history-rewrite rules and the review
        # rule are absent, so every guard is broken (behaviour 8).
        # Behaviour 19: findings render as blocks, not _report_line rows;
        # the broken guard's block headline carries the marked
        # "⚠️ warn:" prefix and the rule name.
        result, _, _ = self.run_doctor_with_guards(
            ("iar3-r8", "Anvil"), ([], None)
        )
        self.assertEqual(0, result.exit_code)
        for rule in ("non_fast_forward", "deletion", "pull_request"):
            headline = "⚠️ warn: {}".format(rule)
            matching = [
                candidate for candidate in self.guards_lines(result)
                if candidate.lstrip().startswith(headline)
            ]
            self.assertTrue(
                matching,
                "no Guards block headline {!r} for the {!r} rule:\n{}".format(
                    headline, rule, result.output
                ),
            )

    def test_doctor_exit_unchanged_with_broken_guards(self):
        # doctor never fails on what it diagnoses: broken guards still exit 0,
        # and a broken and a healthy guards read differently.
        broken, _, _ = self.run_doctor_with_guards(
            ("iar3-r8", "Anvil"), ([], None)
        )
        self.assertEqual(0, broken.exit_code)

        protected = [
            {"type": "non_fast_forward", "ruleset_source": "repository"},
            {"type": "deletion", "ruleset_source": "repository"},
            {
                "type": "pull_request",
                "ruleset_source": "repository",
                "parameters": {"required_approving_review_count": 1},
            },
        ]
        healthy, _, _ = self.run_doctor_with_guards(
            ("iar3-r8", "Anvil"), (protected, None)
        )
        self.assertEqual(0, healthy.exit_code)
        self.assertNotEqual(broken.output, healthy.output)

    def test_doctor_guards_skipped_when_repository_unresolvable(self):
        result, _, fetch = self.run_doctor_with_guards(None, ([], None))
        self.assertEqual(0, result.exit_code)
        self.assertEqual(0, fetch.call_count)
        guards = "\n".join(self.guards_lines(result))
        self.assertIn(
            "skipped",
            guards.lower(),
            "Guards section shows no skipped line:\n{}".format(guards),
        )
        # The reason the checks could not run - the origin remote is not a
        # resolvable GitHub repository - must be visible, not hidden.
        self.assertIn("origin", guards.lower())

    def test_doctor_guards_report_all_five_rules_through_check_all(self):
        # Behaviour 8: doctor's Guards section reports through the single
        # check_all seam, so a five-rule target reports all five rules - and
        # a sixth check added to check_all reaches doctor without an edit.
        from anvilkit.pi import piguard

        findings = piguard.check_all(five_rule_branch_rules())
        with mock.patch.object(
            cli.piguard, "check_all", return_value=findings
        ) as check_all_mock:
            result, _, _ = self.run_doctor_with_guards(
                ("iar3-r8", "Anvil"), (five_rule_branch_rules(), None)
            )
        # doctor never fails on what it diagnoses.
        self.assertEqual(0, result.exit_code)
        self.assertEqual(
            1,
            check_all_mock.call_count,
            "doctor's Guards section must report through the single "
            "check_all seam, so a check added there reaches doctor "
            "without an edit",
        )
        for rule in FIVE_RULE_NAMES:
            line = next(
                (candidate for candidate in self.guards_lines(result)
                 if rule in candidate),
                None,
            )
            self.assertIsNotNone(
                line,
                "no Guards report line for the {!r} rule:\n{}".format(
                    rule, result.output
                ),
            )


class TestDoctorGuardsTokenFindings(CliCase):
    """doctor's Guards section picks up the token findings (behaviour 15).

    The section reports through the same ``check_token_all`` seam
    verify-guards uses, after the branch-rule findings, and a token finding
    - even a ``fail`` - never changes doctor's own exit status.
    """

    OWNER = "iar3-r8"
    REPO = "Anvil"
    TOKEN = "ghp_doctor_token"

    def run_doctor_with_token_findings(self, token_findings, token=TOKEN):
        """``doctor`` with the compose probes and the piguard seams replaced,
        so the guard flow runs offline. Returns ``(result, token_all_mock)``.
        """
        # Patcher objects, not their .start() mocks: stopping a MagicMock is
        # a no-op, and a leaked env.get patch poisons every later test in the
        # suite (it would answer every key with the token).
        docker = mock.patch.object(
            cli.compose, "docker_available", return_value=True
        )
        compose = mock.patch.object(
            cli.compose, "compose_v2_available", return_value=True
        )
        nvidia = mock.patch.object(
            cli.compose, "nvidia_available", return_value=True
        )
        resolve = mock.patch.object(
            cli.piguard,
            "resolve_repository",
            return_value=(self.OWNER, self.REPO),
        )
        fetch = mock.patch.object(
            cli.piguard,
            "fetch_branch_rules",
            return_value=(five_rule_branch_rules(), None),
        )
        token_all = mock.patch.object(
            cli.piguard, "check_token_all", return_value=token_findings
        )
        env_get = mock.patch.object(cli.env, "get", return_value=token)
        docker.start()
        compose.start()
        nvidia.start()
        resolve.start()
        fetch.start()
        token_all_mock = token_all.start()
        env_get.start()
        try:
            result = self.invoke_allowing_exception(["doctor"])
        finally:
            for patcher in (docker, compose, nvidia, resolve, fetch, token_all, env_get):
                patcher.stop()
        return result, token_all_mock

    def guards_section(self, result):
        """The Guards section of a doctor report, or fail saying it is absent."""
        lines = result.output.splitlines()
        try:
            start = lines.index("Guards")
        except ValueError:
            self.fail(
                "doctor output has no 'Guards' section:\n{}".format(result.output)
            )
        return lines[start:]

    def branch_findings(self):
        from anvilkit.pi import piguard

        return piguard.check_all(five_rule_branch_rules())

    def test_guards_reports_token_findings_after_the_branch_findings(self):
        # The token findings flow through the same check_token_all seam, so
        # a probe added there reaches doctor with no edit at the call site -
        # and they report after the branch-rule findings, as verify-guards
        # reports them.
        token = [
            token_finding(
                "target_access", "skipped", reason="no GITHUB_TOKEN in .env"
            ),
            token_finding(
                "administration",
                "warn",
                danger="the repository could be deleted or reconfigured",
                remedy="doc/external/github/rest-api-endpoints-for-actions-permissions.md",
            ),
            token_finding(
                "named_repo", "skipped", reason="no --other-repo was supplied"
            ),
        ]
        result, token_all = self.run_doctor_with_token_findings(token)
        self.assertEqual(0, result.exit_code)
        self.assertTrue(
            token_all.called,
            "doctor's Guards section never reached check_token_all, so a "
            "probe added there would not reach doctor",
        )
        assert_findings_reported_branch_then_token(
            self.guards_section(result), self.branch_findings(), token, result.output
        )

    def test_fail_token_finding_does_not_change_doctors_exit_status(self):
        # doctor never fails on what it diagnoses: a fail finding is
        # reported, and doctor still exits 0.
        token = [
            token_finding(
                "administration",
                "fail",
                danger="the repository could be deleted or reconfigured",
                remedy="doc/external/github/rest-api-endpoints-for-actions-permissions.md",
            ),
        ]
        result, token_all = self.run_doctor_with_token_findings(token)
        self.assertEqual(0, result.exit_code)
        self.assertTrue(
            token_all.called,
            "doctor's Guards section never reached check_token_all",
        )
        self.assertIn("fail:", result.output)

    def test_guards_has_branch_rules_header(self):
        # Behaviour 19: the Guards section has a "Branch rules" header
        # before the branch finding blocks.
        token = [
            token_finding(
                "target_access", "skipped", reason="no GITHUB_TOKEN in .env"
            ),
        ]
        result, _ = self.run_doctor_with_token_findings(token)
        section = self.guards_section(result)
        self.assertTrue(
            "Branch rules" in section,
            "no 'Branch rules' header in the Guards section:\n{}".format(
                result.output
            ),
        )

    def test_guards_has_token_scope_header(self):
        # Behaviour 19: the Guards section has a "Token scope" header
        # before the token finding blocks.
        token = [
            token_finding(
                "target_access", "skipped", reason="no GITHUB_TOKEN in .env"
            ),
        ]
        result, _ = self.run_doctor_with_token_findings(token)
        section = self.guards_section(result)
        self.assertTrue(
            "Token scope" in section,
            "no 'Token scope' header in the Guards section:\n{}".format(
                result.output
            ),
        )

    def test_token_finding_blocks_present_in_guards(self):
        # Behaviour 19: each token finding's block headline appears in
        # the Guards section, and doctor still exits 0.
        token = [
            token_finding(
                "target_access", "skipped", reason="no GITHUB_TOKEN in .env"
            ),
            token_finding(
                "administration",
                "warn",
                danger="the repository could be deleted or reconfigured",
                remedy="doc/external/github/rest-api-endpoints-for-actions-permissions.md",
            ),
        ]
        result, _ = self.run_doctor_with_token_findings(token)
        section = self.guards_section(result)
        for finding in token:
            headline = _finding_headline(finding)
            self.assertTrue(
                any(line.startswith(headline) for line in section),
                "no token finding block headline {!r} in the Guards "
                "section:\n{}".format(headline, result.output),
            )
        self.assertEqual(
            0,
            result.exit_code,
            "doctor must still exit 0 with token finding blocks",
        )


class TestVerifyGuards(CliCase):
    """``verify-guards`` reports through the single check_all seam."""

    def run_verify_guards_with_check_all(self, check_all_return_value):
        """verify-guards with the piguard seams replaced, so the guard flow
        runs offline. Returns ``(result, check_all_mock)``.
        """
        started = []
        resolve = mock.patch.object(
            cli.piguard,
            "resolve_repository",
            return_value=("iar3-r8", "Anvil"),
        )
        fetch = mock.patch.object(
            cli.piguard,
            "fetch_branch_rules",
            return_value=(five_rule_branch_rules(), None),
        )
        check_all = mock.patch.object(
            cli.piguard,
            "check_all",
            return_value=check_all_return_value,
        )
        resolve.start()
        fetch.start()
        check_all_mock = check_all.start()
        started.extend((resolve, fetch, check_all))
        try:
            result = self.invoke_allowing_exception(
                ["verify-guards", str(self.project), "--branch", "main"]
            )
        finally:
            for patcher in started:
                patcher.stop()
        return result, check_all_mock

    def test_reports_all_five_rules_through_check_all(self):
        # Behaviour 8: verify-guards reports through the single check_all
        # seam, so a five-rule target reports all five rules - and a sixth
        # check added to check_all reaches verify-guards without an edit.
        from anvilkit.pi import piguard

        findings = piguard.check_all(five_rule_branch_rules())
        result, check_all_mock = self.run_verify_guards_with_check_all(
            findings
        )

        self.assertEqual(
            1,
            check_all_mock.call_count,
            "verify-guards must report through the single check_all seam, "
            "so a check added there reaches verify-guards without an edit",
        )
        for rule in FIVE_RULE_NAMES:
            line = next(
                (candidate for candidate in result.output.splitlines()
                 if rule in candidate),
                None,
            )
            self.assertIsNotNone(
                line,
                "no report line for the {!r} rule:\n{}".format(
                    rule, result.output
                ),
            )
        # The report prints one block per check_all finding, via
        # render_finding_block. The block's headline (status prefix + label)
        # is the stable anchor: the detail and remedy lines are wrapped at
        # 80 columns and may span multiple lines, so only the headline is
        # searched. Counted per finding rather than as a report total:
        # behaviour 15 adds the token findings to the same report, so a
        # total would be invalidated by the wiring it was meant to guard.
        report_lines = result.output.splitlines()
        for finding in findings:
            headline = _finding_headline(finding)
            self.assertEqual(
                1,
                sum(1 for candidate in report_lines
                    if candidate.startswith(headline)),
                "the report must print exactly one block for the finding "
                "{!r} (headline {!r}):\n{}".format(
                    finding, headline, result.output
                ),
            )
        # No fail finding among the five passed rules: exit status unchanged.
        self.assertEqual(0, result.exit_code)


class TestVerifyGuardsTokenFindings(CliCase):
    """``verify-guards`` gains ``--other-repo`` and the token findings.

    Behaviour 15 of plans/verify-guards-token.md: the branch-rule findings
    report first, then the token findings through the single
    ``check_token_all`` seam, and the exit status is the ``summarize`` of
    all of them - the first live path for a non-zero verify-guards.
    """

    OWNER = "iar3-r8"
    REPO = "Anvil"
    TOKEN = "ghp_test_token"

    def run_verify_guards_with_token_findings(
        self, token_findings, other_repo=None, token=TOKEN
    ):
        """verify-guards with the piguard seams and the .env token replaced,
        so the whole flow runs offline. ``other_repo=None`` invokes without
        the flag. Returns ``(result, token_all_mock, env_get_mock)``.
        """
        resolve = mock.patch.object(
            cli.piguard,
            "resolve_repository",
            return_value=(self.OWNER, self.REPO),
        )
        fetch = mock.patch.object(
            cli.piguard,
            "fetch_branch_rules",
            return_value=(five_rule_branch_rules(), None),
        )
        token_all = mock.patch.object(
            cli.piguard, "check_token_all", return_value=token_findings
        )
        env_get = mock.patch.object(cli.env, "get", return_value=token)
        resolve.start()
        fetch.start()
        token_all_mock = token_all.start()
        env_get_mock = env_get.start()
        try:
            argv = ["verify-guards", str(self.project), "--branch", "main"]
            if other_repo is not None:
                argv.extend(["--other-repo", other_repo])
            result = self.invoke_allowing_exception(argv)
        finally:
            for patcher in (resolve, fetch, token_all, env_get):
                patcher.stop()
        return result, token_all_mock, env_get_mock

    @staticmethod
    def call_arg(mocked, name, index):
        """One call argument by name, falling back to its positional slot, so
        the pin holds whether the CLI passes it by keyword or position."""
        args, kwargs = mocked.call_args
        if name in kwargs:
            return kwargs[name]
        if len(args) > index:
            return args[index]
        return mock.DEFAULT

    def branch_findings(self):
        from anvilkit.pi import piguard

        return piguard.check_all(five_rule_branch_rules())

    def test_other_repo_option_is_accepted(self):
        # A missing option is a click usage error (exit 2, "No such option");
        # the flag must be accepted and reach check_token_all instead.
        result, token_all, _ = self.run_verify_guards_with_token_findings(
            [
                token_finding(
                    "named_repo", "skipped",
                    reason="the named repository was not reached",
                )
            ],
            other_repo="someorg/other",
        )
        self.assertNotIn("No such option", result.output)
        self.assertNotEqual(2, result.exit_code)
        self.assertTrue(
            token_all.called,
            "verify-guards never reached check_token_all, so --other-repo "
            "cannot reach the named-repo probe",
        )

    def test_reports_branch_findings_then_token_findings_and_exits_summarize_all(self):
        from anvilkit.pi import piguard

        branch = self.branch_findings()
        token = [
            token_finding(
                "target_access", "skipped", reason="no GITHUB_TOKEN in .env"
            ),
            token_finding(
                "administration",
                "warn",
                danger="the repository could be deleted or reconfigured",
                remedy="doc/external/github/rest-api-endpoints-for-actions-permissions.md",
            ),
            token_finding(
                "named_repo", "skipped", reason="no --other-repo was supplied"
            ),
        ]
        result, token_all, _ = self.run_verify_guards_with_token_findings(token)
        self.assertTrue(
            token_all.called, "verify-guards never reached check_token_all"
        )
        self.assertEqual(
            piguard.summarize(branch + token),
            result.exit_code,
            "the exit status must be the summarize of all findings, branch "
            "and token:\n{}".format(result.output),
        )
        assert_findings_reported_branch_then_token(
            result.output.splitlines(), branch, token, result.output
        )

    def test_check_token_all_receives_resolved_repo_token_and_raw_other_repo(self):
        result, token_all, env_get = self.run_verify_guards_with_token_findings(
            [
                token_finding(
                    "named_repo", "skipped",
                    reason="the named repository was not reached",
                )
            ],
            other_repo="someorg/other",
        )
        self.assertTrue(
            token_all.called, "verify-guards never reached check_token_all"
        )
        self.assertEqual(self.OWNER, self.call_arg(token_all, "owner", 0))
        self.assertEqual(self.REPO, self.call_arg(token_all, "repo", 1))
        self.assertEqual(self.TOKEN, self.call_arg(token_all, "token", 2))
        self.assertEqual(
            "someorg/other",
            self.call_arg(token_all, "other_repo", 3),
            "the raw --other-repo value reaches check_token_all unchanged",
        )
        self.assertEqual(1, env_get.call_count)

    def test_other_repo_absent_passes_none_to_check_token_all(self):
        result, token_all, _ = self.run_verify_guards_with_token_findings(
            [
                token_finding(
                    "named_repo", "skipped", reason="no --other-repo was supplied"
                )
            ]
        )
        self.assertTrue(
            token_all.called, "verify-guards never reached check_token_all"
        )
        self.assertIsNone(
            self.call_arg(token_all, "other_repo", 3),
            "an absent --other-repo must reach check_token_all as None, so "
            "the named-repo probe emits behaviour 6's skip rather than "
            "guessing",
        )

    def test_malformed_other_repo_is_a_skipped_finding_not_a_crash(self):
        # The probe owns the format check; at the CLI level a malformed
        # value must run to completion, report the skipped named-repo
        # finding and exit per summarize - the CLI does not re-validate it.
        from anvilkit.pi import piguard

        branch = self.branch_findings()
        token = [
            token_finding(
                check, "skipped", reason="no GITHUB_TOKEN in .env"
            )
            for check in ("target_access", "administration", "classic_token")
        ] + [
            token_finding(
                "workflows_withheld", "skipped",
                reason="the workflows permission has no read level",
            ),
            token_finding(
                "named_repo", "skipped", reason="not-a-path is not OWNER/REPO"
            ),
        ]
        result, token_all, _ = self.run_verify_guards_with_token_findings(
            token, other_repo="not-a-path"
        )
        self.assertTrue(
            token_all.called, "verify-guards never reached check_token_all"
        )
        self.assertEqual(
            "not-a-path",
            self.call_arg(token_all, "other_repo", 3),
            "the raw --other-repo value reaches the probe; the CLI does not "
            "re-validate the format",
        )
        self.assertEqual(
            piguard.summarize(branch + token),
            result.exit_code,
            "a malformed --other-repo must exit per summarize, not crash",
        )
        self.assertIn("named_repo", result.output)

    def test_missing_token_still_runs_and_reaches_check_token_all(self):
        # behaviour 7 at the CLI level: no token in .env still runs, the
        # probes skip inside check_token_all, and the exit is summarize's.
        skips = [
            token_finding(
                check, "skipped", reason="no GITHUB_TOKEN in .env"
            )
            for check in (
                "target_access",
                "administration",
                "classic_token",
                "workflows_withheld",
                "named_repo",
            )
        ]
        result, token_all, _ = self.run_verify_guards_with_token_findings(
            skips, token=None
        )
        self.assertTrue(
            token_all.called, "verify-guards never reached check_token_all"
        )
        self.assertIsNone(
            self.call_arg(token_all, "token", 2),
            "a missing .env token reaches check_token_all as None, so the "
            "probes skip instead of issuing an unauthenticated request",
        )
        self.assertEqual(0, result.exit_code)

    def test_fail_token_finding_makes_verify_guards_exit_nonzero(self):
        # The first live path for a non-zero verify-guards: a fail finding
        # from the token probes exits 1 through summarize.
        token = [
            token_finding(
                "target_access", "skipped", reason="no GITHUB_TOKEN in .env"
            ),
            token_finding(
                "administration",
                "fail",
                danger="the repository could be deleted or reconfigured",
                remedy="doc/external/github/rest-api-endpoints-for-actions-permissions.md",
            ),
            token_finding(
                "named_repo", "skipped", reason="no --other-repo was supplied"
            ),
        ]
        result, token_all, _ = self.run_verify_guards_with_token_findings(token)
        self.assertTrue(
            token_all.called, "verify-guards never reached check_token_all"
        )
        self.assertEqual(1, result.exit_code)
        self.assertIn("fail:", result.output)

    def test_verify_guards_still_exits_summarize_not_nine(self):
        # Behaviour 9 of plans/setup-repo-guards.md (pin): the gate is a
        # SIBLING of summarize, not a change to it - verify-guards exits
        # 0 on warn/skipped-only findings and 1 on a fail (the 0/1
        # contract itself is already pinned by
        # test_reports_all_five_rules_through_check_all and
        # test_fail_token_finding_makes_verify_guards_exit_nonzero); what
        # this pin adds is the negative: a blocked verify-guards is 0 or
        # 1, never the setup-repo gate's code.
        warn = [
            token_finding(
                "administration",
                "warn",
                danger="the repository could be deleted or reconfigured",
                remedy=(
                    "doc/external/github/rest-api-endpoints-for-actions-"
                    "permissions.md"
                ),
            ),
            token_finding(
                "named_repo", "skipped", reason="no --other-repo was supplied"
            ),
        ]
        result, _token_all, _ = self.run_verify_guards_with_token_findings(
            warn
        )
        self.assertEqual(
            0,
            result.exit_code,
            "warn/skipped-only findings exit 0 through summarize:\n{}".format(
                result.output
            ),
        )
        self.assertNotEqual(
            cli.EXIT_GUARDS_BLOCKED,
            result.exit_code,
            "verify-guards never exits the setup-repo gate's code: "
            "exit {}:\n{}".format(result.exit_code, result.output),
        )

        fail = [
            token_finding(
                "administration",
                "fail",
                danger="the repository could be deleted or reconfigured",
                remedy=(
                    "doc/external/github/rest-api-endpoints-for-actions-"
                    "permissions.md"
                ),
            ),
            token_finding(
                "named_repo", "skipped", reason="no --other-repo was supplied"
            ),
        ]
        result, _token_all, _ = self.run_verify_guards_with_token_findings(
            fail
        )
        self.assertEqual(
            1,
            result.exit_code,
            "a fail finding exits 1 through summarize:\n{}".format(
                result.output
            ),
        )
        self.assertNotEqual(
            cli.EXIT_GUARDS_BLOCKED,
            result.exit_code,
            "a failing verify-guards exits 1, never the setup-repo "
            "gate's code: exit {}:\n{}".format(
                result.exit_code, result.output
            ),
        )

    def test_report_has_branch_rules_header_before_first_branch_finding(self):
        # Behaviour 19: the report has a "Branch rules" section header
        # before the first branch finding block.
        token = [
            token_finding(
                "target_access", "skipped", reason="no GITHUB_TOKEN in .env"
            ),
        ]
        result, _, _ = self.run_verify_guards_with_token_findings(token)
        lines = result.output.splitlines()
        header_index = next(
            (index for index, line in enumerate(lines)
             if line == "Branch rules"),
            None,
        )
        self.assertIsNotNone(
            header_index,
            "no 'Branch rules' header in the report:\n{}".format(result.output),
        )
        branch = self.branch_findings()
        first_headline = _finding_headline(branch[0])
        first_index = next(
            (index for index, line in enumerate(lines)
             if line.startswith(first_headline)),
            None,
        )
        self.assertIsNotNone(
            first_index,
            "no branch finding block in the report:\n{}".format(result.output),
        )
        self.assertGreater(
            first_index,
            header_index,
            "'Branch rules' header must precede the first branch finding "
            "block:\n{}".format(result.output),
        )

    def test_report_has_token_scope_header_before_first_token_finding(self):
        # Behaviour 19: the report has a "Token scope" section header
        # before the first token finding block.
        token = [
            token_finding(
                "target_access", "skipped", reason="no GITHUB_TOKEN in .env"
            ),
        ]
        result, _, _ = self.run_verify_guards_with_token_findings(token)
        lines = result.output.splitlines()
        header_index = next(
            (index for index, line in enumerate(lines)
             if line == "Token scope"),
            None,
        )
        self.assertIsNotNone(
            header_index,
            "no 'Token scope' header in the report:\n{}".format(result.output),
        )
        first_headline = _finding_headline(token[0])
        first_index = next(
            (index for index, line in enumerate(lines)
             if line.startswith(first_headline)),
            None,
        )
        self.assertIsNotNone(
            first_index,
            "no token finding block in the report:\n{}".format(result.output),
        )
        self.assertGreater(
            first_index,
            header_index,
            "'Token scope' header must precede the first token finding "
            "block:\n{}".format(result.output),
        )

    def test_no_report_line_exceeds_80_characters(self):
        # Behaviour 19: the report is 80 columns wide. The harness's
        # target path is a short TemporaryDirectory path, so the metadata
        # lines (target/branch/repository) are well under 80; the
        # _SEPARATOR is 60 dashes. Every line must be at most 80.
        token = [
            token_finding(
                "target_access", "skipped", reason="no GITHUB_TOKEN in .env"
            ),
        ]
        result, _, _ = self.run_verify_guards_with_token_findings(token)
        for line in result.output.splitlines():
            self.assertLessEqual(
                len(line),
                80,
                "a report line exceeds 80 characters ({} chars): {!r}"
                "\n---\n{}".format(len(line), line, result.output),
            )

    def test_fail_token_finding_has_no_per_finding_fix_line(self):
        # Behaviour 19: the per-finding "fix:" line convention is removed -
        # the report carries no line beginning "fix:" anywhere. This used
        # to pin "the remedy rides on a fix: line" (the old convention);
        # it now pins the removal of that convention - the remedy is
        # collected in the report's "To fix" section instead (behaviour 7).
        remedy_text = "recreate the token"
        token = [
            token_finding(
                "administration",
                "fail",
                danger="the repository could be deleted or reconfigured",
                remedy="{}; see "
                "doc/external/github/rest-api-endpoints-for-actions-permissions.md".format(
                    remedy_text
                ),
            ),
        ]
        result, _, _ = self.run_verify_guards_with_token_findings(token)
        lines = result.output.splitlines()
        fix_lines = [
            line for line in lines if line.lstrip().startswith("fix:")
        ]
        self.assertEqual(
            [],
            fix_lines,
            "the report must carry no per-finding 'fix:' line:\n"
            "fix lines: {!r}\n{}".format(fix_lines, result.output),
        )


class TestVerifyGuardsDocstringCorrection(CliCase):
    """Behaviour 16: the verify-guards help text is corrected now that
    ``fail`` findings are emittable - it names which probes emit ``fail``
    and cites the host-driver token location the probes protect."""

    def help_text(self):
        result = self.invoke(["verify-guards", "--help"])
        self.assertEqual(0, result.exit_code)
        return result.output

    def test_help_no_longer_claims_the_command_emits_no_fail(self):
        self.assertNotIn(
            "emits none of",
            self.help_text(),
            "the help text still claims verify-guards emits no fail finding",
        )

    def test_help_names_the_probes_that_can_emit_fail(self):
        text = self.help_text().lower()
        self.assertIn(
            "administration",
            text,
            "the help text must name the administration probe as a "
            "fail emitter",
        )
        self.assertIn(
            "classic",
            text,
            "the help text must name the classic-token probe as a "
            "fail emitter",
        )

    def test_help_cites_the_host_driver_token_location(self):
        text = self.help_text().lower()
        self.assertIn(
            "host driver",
            text,
            "the help text must cite where the protected token lives",
        )
        self.assertIn(
            "agent cannot read",
            text,
            "the help text must say the agent cannot read the token",
        )


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

    # -- stress (Behaviour 17 red, run() entry-point mirror) -------------------
    #
    # ``run()`` calls the app with ``standalone_mode=False``: a ``typer.Exit(7)``
    # or ``typer.Exit(8)`` raised inside ``stress`` must surface as the
    # function's return value, not as a traceback. ``CliRunner`` cannot see
    # that gap, so these mirrors exist. While the subcommand is missing, click
    # raises ``UsageError`` and ``run()`` returns 2 - every mirror below
    # therefore guards on the registered commands first.

    def _stress_run(self, argv, **patch_returns):
        _require_stress_subcommand(self.id())
        defaults = dict(
            status=stress_ok(),
            check_model_available=stress_available(available=["org/alpha"]),
            warm_up=warmup_ok(),
            run_stress=clean_report(),
            log_path=lambda *a, **k: Path(str(self.project / "logs" / "stress.log")),
        )
        defaults.update(patch_returns)
        with mock.patch.object(
            cli.health, "check_gateway", return_value=defaults.pop("status")
        ), mock.patch.object(cli, "check_model_available", return_value=defaults.pop("check_model_available")), \
             mock.patch.object(cli, "warm_up", return_value=defaults.pop("warm_up")), \
             mock.patch.object(cli, "run_stress", return_value=defaults.pop("run_stress")), \
             mock.patch.object(cli, "log_path", side_effect=defaults.pop("log_path")):
            return self.run_cli(argv)

    def test_stress_clean_run_exits_zero(self):
        self.write_env(LLM_PORT="8000")
        code, _ = self._stress_run(["stress", "org/alpha"])
        self.assertEqual(cli.EXIT_OK, code)

    def test_stress_clean_run_does_not_print_a_traceback(self):
        self.write_env(LLM_PORT="8000")
        _, output = self._stress_run(["stress", "org/alpha"])
        self.assertNotIn("Traceback", output)

    def test_stress_failing_run_exits_with_the_failures_code(self):
        """EXIT_STRESS_FAILURES is the literal 8 - the constant does not exist yet."""
        self.write_env(LLM_PORT="8000")
        code, _ = self._stress_run(
            ["stress", "org/alpha"],
            run_stress=failing_report(),
        )
        self.assertEqual(8, code)

    def test_stress_failing_run_does_not_print_a_traceback(self):
        self.write_env(LLM_PORT="8000")
        _, output = self._stress_run(
            ["stress", "org/alpha"],
            run_stress=failing_report(),
        )
        self.assertNotIn("Traceback", output)

    def test_stress_missing_argument_exits_with_the_usage_code(self):
        """Must be earned from the real command - 'No such command' would also exit 2."""
        self.write_env(LLM_PORT="8000")
        code, _ = self._stress_run(
            ["stress"], status=stress_gateway_with_models()
        )
        self.assertEqual(cli.EXIT_USAGE, code)

    def test_stress_missing_argument_lists_the_registry(self):
        self.write_env(LLM_PORT="8000")
        _, output = self._stress_run(
            ["stress"], status=stress_gateway_with_models()
        )
        self.assertIn("org/alpha", output)

    def test_stress_missing_argument_does_not_print_a_traceback(self):
        self.write_env(LLM_PORT="8000")
        _, output = self._stress_run(
            ["stress"], status=stress_gateway_with_models()
        )
        self.assertNotIn("Traceback", output)

    def test_stress_warmup_failure_exits_with_the_unavailable_code(self):
        """EXIT_STRESS_UNAVAILABLE is the literal 7 - the constant does not exist yet."""
        self.write_env(LLM_PORT="8000")
        code, _ = self._stress_run(
            ["stress", "org/alpha"],
            warm_up=warmup_failed(),
        )
        self.assertEqual(7, code)

    def test_stress_warmup_failure_does_not_print_a_traceback(self):
        self.write_env(LLM_PORT="8000")
        _, output = self._stress_run(
            ["stress", "org/alpha"],
            warm_up=warmup_failed(),
        )
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
# _resolve_github_token  (Behavior 9 — persisting is a no-op when unchanged)
# ---------------------------------------------------------------------------


class TestResolveGithubTokenPersistNoopUnchanged(CliCase):
    """B9: persisting is a no-op when the value is unchanged.

    The contract, per plans/skip-github-token-prompt.md §4/B9:

    * input: ``.env`` already holds ``GITHUB_TOKEN=ghp_same`` and the
      resolved value is ``ghp_same`` — reachable via B2 with a matching
      flag, i.e. ``_resolve_github_token`` called with
      ``token="ghp_same"`` against a store already holding ``ghp_same``,
    * ``env.set_value`` is NOT called — asserted with
      ``mock.patch.object(cli.env, "set_value")`` and ``assert_not_called``,
    * the return value is still ``"ghp_same"``,
    * ``.env`` is byte-for-byte unchanged: the existing lines, their
      ordering and the other keys all survive (no read-modify-rewrite),
    * the persist notice ``⚡ Token accepted and persisted to .env`` is NOT
      echoed — the no-op returns before the echo
      (``anvilkit/cli.py:812-813``).

    Contract-lock note: B2's green cycle already built the
    unchanged-early-return into ``_persist_github_token``, so this test is
    expected to be green from the start, pinning the guard against a future
    rewrite (like B1/B4/B6's committed locks).
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

    def test_unchanged_flag_token_is_not_rewritten_to_env(self):
        """Flag value == stored value -> returned, no ``set_value``, file untouched.

        ``.env`` holds ``GITHUB_TOKEN=ghp_same`` plus other keys; passing
        the matching ``token="ghp_same"`` through the B2 flag path must
        leave the file byte-for-byte identical and echo no persist notice.
        """
        self.write_env(
            GITHUB_TOKEN="ghp_same",
            LLM_PORT="8000",
            OXYLABS_USERNAME="oxu",
        )
        content_before = self.env_path().read_bytes()
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
        echo_patcher, lines = self._capture_echo()
        with mock.patch.object(cli.env, "set_value") as set_value:
            with trap_confirm as prompts_confirm, trap_ask as ask_required:
                with echo_patcher:
                    result = cli._resolve_github_token(
                        ctx, "ghp_same", no_github=False
                    )

        # (a) the flag value is still returned
        self.assertEqual("ghp_same", result)
        # (b) no write happened at all
        set_value.assert_not_called()
        # (c) no prompt of any kind was reached
        prompts_confirm.assert_not_called()
        ask_required.assert_not_called()
        # (d) the file is byte-for-byte unchanged: every line, its ordering
        #     and the other keys survive
        self.assertEqual(content_before, self.env_path().read_bytes())
        values = cli.env.read(self.env_path())
        self.assertEqual(
            {
                "GITHUB_TOKEN": "ghp_same",
                "LLM_PORT": "8000",
                "OXYLABS_USERNAME": "oxu",
            },
            values,
        )
        # (e) the persist notice is not echoed — the no-op returns before it
        output = "\n".join(lines)
        self.assertNotIn(self.PERSIST_NOTICE, output)


# ---------------------------------------------------------------------------
# _resolve_github_token  (Behavior 10 — --dry-run writes nothing)
# ---------------------------------------------------------------------------


class TestResolveGithubTokenDryRunWritesNothing(CliCase):
    """B10: ``--dry-run`` writes nothing.

    The contract, per plans/skip-github-token-prompt.md §4/B10:

    * input: ``shared.dry_run=True``, a resolved non-empty token, and
      ``.env`` either absent or holding a *different* value (the
      different-value case is chosen because a missing dry-run guard
      would actually write there),
    * output: ``.env`` unchanged on disk — the assertion is on the
      file's content, not just on the mock,
    * echoes ``would store GITHUB_TOKEN in <env_path>``;
    * the token value is never echoed.

    The persist helper is reached through the public
    ``_resolve_github_token`` path — ``token="ghp_flag"`` with
    ``dry_run=True`` — so the test exercises the real seam.

    Contract-lock note: B2's green cycle already built the dry-run
    guard into ``_persist_github_token``
    (``anvilkit/cli.py:808-810``), so this test is expected to be green
    from the start, pinning the guard against a future rewrite (like
    B1/B4/B6/B9's committed locks).
    """

    PERSIST_NOTICE = "⚡ Token accepted and persisted to .env"
    TOKEN = "ghp_flag"

    def _make_context(self, assume_yes=False):
        """Build a minimal Context with ``dry_run=True`` pointing at the test project."""
        return cli.Context(
            dry_run=True,
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

    def _resolve_dry_run(self, token):
        """Run ``_resolve_github_token`` through the flag path with ``dry_run=True``.

        Returns ``(result, set_value, prompts_confirm, ask_required, lines)``.
        """
        ctx = self._make_context(assume_yes=False)
        trap_confirm = mock.patch.object(
            cli.prompts,
            "confirm",
            side_effect=AssertionError(
                "_resolve_github_token must not prompt when the flag is given"
            ),
        )
        trap_ask = mock.patch.object(
            cli.prompts,
            "ask_required",
            side_effect=AssertionError(
                "_resolve_github_token must not ask for a token when the flag is given"
            ),
        )
        echo_patcher, lines = self._capture_echo()
        with mock.patch.object(cli.env, "set_value") as set_value:
            with trap_confirm as prompts_confirm, trap_ask as ask_required:
                with echo_patcher:
                    result = cli._resolve_github_token(ctx, token, no_github=False)
        return result, set_value, prompts_confirm, ask_required, lines

    def test_dry_run_flag_token_writes_nothing_when_stored_value_differs(self):
        """``token="ghp_flag"`` + a *different* stored value -> echo only, file unchanged.

        The different stored value is what makes this test bite: a missing
        dry-run guard would write here, and the byte comparison catches it.
        """
        self.write_env(GITHUB_TOKEN="ghp_stored", LLM_PORT="8000")
        content_before = self.env_path().read_bytes()
        ctx = self._make_context()

        (
            result,
            set_value,
            prompts_confirm,
            ask_required,
            lines,
        ) = self._resolve_dry_run(self.TOKEN)

        # (a) the flag value is still returned
        self.assertEqual(self.TOKEN, result)
        # (b) no write happened at all
        set_value.assert_not_called()
        # (c) no prompt of any kind was reached
        prompts_confirm.assert_not_called()
        ask_required.assert_not_called()
        # (d) the file content is unchanged on disk — a missing dry-run guard
        #     would have rewritten it with the different flag value
        self.assertEqual(content_before, self.env_path().read_bytes())
        values = cli.env.read(self.env_path())
        self.assertEqual("ghp_stored", values.get("GITHUB_TOKEN"))
        self.assertEqual("8000", values.get("LLM_PORT"))
        # (e) the would-store line is echoed, naming the key and the path
        output = "\n".join(lines)
        self.assertIn("would store", output)
        self.assertIn("GITHUB_TOKEN", output)
        self.assertIn(str(ctx.env_path), output)
        # (f) the persist notice is not echoed, and neither is the secret
        self.assertNotIn(self.PERSIST_NOTICE, output)
        self.assertNotIn(self.TOKEN, output)

    def test_dry_run_flag_token_creates_no_file_when_env_absent(self):
        """``token="ghp_flag"`` + no ``.env`` -> the file is never created."""
        self.assertFalse(self.env_path().exists())
        ctx = self._make_context()

        (
            result,
            set_value,
            prompts_confirm,
            ask_required,
            lines,
        ) = self._resolve_dry_run(self.TOKEN)

        # (a) the flag value is still returned
        self.assertEqual(self.TOKEN, result)
        # (b) no write happened at all
        set_value.assert_not_called()
        # (c) no prompt of any kind was reached
        prompts_confirm.assert_not_called()
        ask_required.assert_not_called()
        # (d) the file was never created — asserted on the disk, not the mock
        self.assertFalse(self.env_path().exists())
        # (e) the would-store line is echoed, naming the key and the path
        output = "\n".join(lines)
        self.assertIn("would store", output)
        self.assertIn("GITHUB_TOKEN", output)
        self.assertIn(str(ctx.env_path), output)
        # (f) the persist notice is not echoed, and neither is the secret
        self.assertNotIn(self.PERSIST_NOTICE, output)
        self.assertNotIn(self.TOKEN, output)


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


# ---------------------------------------------------------------------------
# _persist_github_token  (Behavior 11 — writing GITHUB_TOKEN disturbs no other key)
# ---------------------------------------------------------------------------


class TestResolveGithubTokenWriteDoesNotDisturbOtherKeys(CliCase):
    """B11: writing ``GITHUB_TOKEN`` disturbs no other key.

    The contract, per plans/skip-github-token-prompt.md §4/B11:

    * input: ``.env`` containing ``ANTHROPIC_API_KEY``, ``OXYLABS_USERNAME``,
      ``OXYLABS_PASSWORD``, ``LLM_PORT``, a comment line and a section
      heading,
    * action: persist a GitHub token through the real seam —
      ``_resolve_github_token`` with ``token="ghp_new"`` — covering both the
      append-a-new-key case and the replace-an-existing-entry case,
    * output: every other key and its value, the comments and the original
      ordering are intact in the file, and ``GITHUB_TOKEN`` is appended or
      replaced in place.

    Assertions are on the actual file content — parsed values via
    ``cli.env.read`` plus raw text for ordering, comments and in-place
    position — not on a mock of ``env.set_value``.

    Regression sibling of
    ``test_set_value_preserves_anthropic_api_key_and_github_token_when_setting_oxylabs``
    (``tests/test_env.py:269``), which asserts the mirror-image property at
    the store level. Here the property is locked one seam higher: through
    ``_persist_github_token`` as reached from ``_resolve_github_token``.

    Contract-lock note: ``env.set_value`` (``anvilkit/env.py:44``) is a
    purpose-built, tested store documented to match the key exactly and
    preserve surrounding lines, comments and ordering, so this test is
    expected to be green from the start, pinning the property against a
    future rewrite (like the committed locks for B1/B4/B6/B9/B10).
    """

    PERSIST_NOTICE = "⚡ Token accepted and persisted to .env"
    TOKEN = "ghp_new"

    # The fixture is written as raw text rather than via ``write_env``
    # (which delegates to ``env.write`` and cannot express a plain comment
    # line), so the test owns its exact ordering, comment and heading.
    FIXTURE = (
        "# Anvil machine-specific secrets\n"
        "ANTHROPIC_API_KEY=sk-ant-abc123\n"
        "\n"
        "# --- Oxylabs proxy ---\n"
        "OXYLABS_USERNAME=oxuser\n"
        "OXYLABS_PASSWORD=oxpass\n"
        "\n"
        "# Networking\n"
        "LLM_PORT=8000\n"
    )

    EXPECTED_OTHERS = {
        "ANTHROPIC_API_KEY": "sk-ant-abc123",
        "OXYLABS_USERNAME": "oxuser",
        "OXYLABS_PASSWORD": "oxpass",
        "LLM_PORT": "8000",
    }

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

    def _write_fixture(self, extra_lines=()):
        """Write the fixture, optionally interleaving ``extra_lines`` before the last line."""
        lines = self.FIXTURE.splitlines()
        for extra in reversed(list(extra_lines)):
            lines.insert(2, extra)  # right after ANTHROPIC_API_KEY
        self.env_path().write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _resolve_with_flag(self):
        """Run ``_resolve_github_token`` through the flag path with a new token.

        Returns ``(result, prompts_confirm, ask_required, lines)``. The
        prompt seams are booby-trapped: the flag path must not prompt.
        """
        trap_confirm = mock.patch.object(
            cli.prompts,
            "confirm",
            side_effect=AssertionError(
                "_resolve_github_token must not prompt when the flag is given"
            ),
        )
        trap_ask = mock.patch.object(
            cli.prompts,
            "ask_required",
            side_effect=AssertionError(
                "_resolve_github_token must not ask for a token when the flag is given"
            ),
        )
        echo_patcher, lines = self._capture_echo()
        with trap_confirm as prompts_confirm, trap_ask as ask_required:
            with echo_patcher:
                result = cli._resolve_github_token(self._make_context(), self.TOKEN, no_github=False)
        return result, prompts_confirm, ask_required, lines

    def _assert_other_keys_intact(self):
        """Every other key and its value survives, plus the comments and heading."""
        values = cli.env.read(self.env_path())
        for key, value in self.EXPECTED_OTHERS.items():
            self.assertEqual(value, values.get(key))

        content = self.env_path().read_text(encoding="utf-8")
        # comment line and section heading survive byte-for-byte
        self.assertIn("# Anvil machine-specific secrets\n", content)
        self.assertIn("# --- Oxylabs proxy ---\n", content)
        self.assertIn("# Networking\n", content)

    def test_persist_new_token_appends_without_disturbing_other_keys(self):
        """``token="ghp_new"`` with no stored token -> ``GITHUB_TOKEN`` appended, everything else intact.

        The byte comparison is the decisive assertion: the resulting file
        must be exactly the original file plus the appended line, so any
        reordering, dropped line or value mutation fails.
        """
        self._write_fixture()
        content_before = self.env_path().read_text(encoding="utf-8")
        lines_before = content_before.splitlines()

        result, prompts_confirm, ask_required, lines = self._resolve_with_flag()

        # (a) the flag value is returned, no prompt of any kind
        self.assertEqual(self.TOKEN, result)
        prompts_confirm.assert_not_called()
        ask_required.assert_not_called()
        # (b) every other key/value, the comments and the heading are intact
        self._assert_other_keys_intact()
        # (c) the original ordering is intact and GITHUB_TOKEN is appended
        #     last — the file is byte-for-byte the original plus one line
        lines_after = self.env_path().read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines_before + ["GITHUB_TOKEN=" + self.TOKEN], lines_after)
        # (d) the store now answers for the new key with the new value
        self.assertEqual(self.TOKEN, cli.env.get(self.env_path(), cli.GITHUB_TOKEN_ENV))
        # (e) the persist notice is echoed; the secret never is
        output = "\n".join(lines)
        self.assertIn(self.PERSIST_NOTICE, output)
        self.assertNotIn(self.TOKEN, output)

    def test_persist_replaces_existing_token_in_place_without_disturbing_other_keys(self):
        """``token="ghp_new"`` over ``GITHUB_TOKEN=ghp_old`` -> replaced in place, everything else intact.

        The entry sits mid-file, between two unrelated keys: an in-place
        replace leaves its line index unchanged, while a rewrite that
        re-sorted or re-appended the key would move it and fail the
        line-by-line comparison.
        """
        self._write_fixture(extra_lines=("GITHUB_TOKEN=ghp_old",))
        lines_before = self.env_path().read_text(encoding="utf-8").splitlines()
        index_before = lines_before.index("GITHUB_TOKEN=ghp_old")

        result, prompts_confirm, ask_required, lines = self._resolve_with_flag()

        # (a) the flag value is returned, no prompt of any kind
        self.assertEqual(self.TOKEN, result)
        prompts_confirm.assert_not_called()
        ask_required.assert_not_called()
        # (b) every other key/value, the comments and the heading are intact
        self._assert_other_keys_intact()
        # (c) the replacement is in place: the old value is gone, the new
        #     one sits at exactly the same line index, and every other line
        #     is byte-for-byte unchanged
        content_after = self.env_path().read_text(encoding="utf-8")
        self.assertNotIn("ghp_old", content_after)
        lines_after = content_after.splitlines()
        self.assertEqual(len(lines_before), len(lines_after))
        self.assertEqual(
            "GITHUB_TOKEN=" + self.TOKEN, lines_after[index_before]
        )
        for position, (before, after) in enumerate(zip(lines_before, lines_after)):
            if position != index_before:
                self.assertEqual(before, after)
        # (d) the store now answers for the key with the new value, and no
        #     duplicate entry was left behind
        self.assertEqual(self.TOKEN, cli.env.get(self.env_path(), cli.GITHUB_TOKEN_ENV))
        self.assertEqual(
            1, sum(1 for line in lines_after if line.startswith("GITHUB_TOKEN="))
        )
        # (e) the persist notice is echoed; the secret never is
        output = "\n".join(lines)
        self.assertIn(self.PERSIST_NOTICE, output)
        self.assertNotIn(self.TOKEN, output)


# ---------------------------------------------------------------------------
# _resolve_github_token  (Behavior 12 — no ripple into render or provision)
# ---------------------------------------------------------------------------


class TestNoGithubRunNeverBlanksStoredRepoToken(CliCase):
    """B12: ``--no-github`` reaching provision as ``""`` must not blank a token the target repo already holds.

    ``_resolve_github_token`` now returns ``""`` from new code paths
    (``--no-github`` short-circuit, ``--yes`` / non-interactive with nothing
    stored) that could not produce it before the bugfix. This guard locks
    the downstream contract end-to-end: the real ``provision.setup_repo``
    (unmocked, as in ``TestNonInteractive.test_yes_setup_repo_reads_no_stdin``)
    merges an incoming ``GITHUB_PERSONAL_ACCESS_TOKEN=""`` into a target whose
    ``.roo/mcp.json`` already holds a non-empty one, and the stored value must
    survive — the A2 credential rule at ``anvilkit/provision.py:404-408``.

    Assertions are on the parsed structure of the deployed ``.roo/mcp.json``
    in the target, never on source text. The target is seeded with the
    same realistic github server entry shape as
    ``tests/test_provision_mcp_merge.py`` so the merge path (Anvil-owned
    server, dict env on both sides) is the one exercised.
    """

    STORED = "ghp_preexisting_in_repo"

    def setUp(self):
        super().setUp()
        self.write_env(LLM_PORT="8000")
        self._target = tempfile.TemporaryDirectory()
        self.target = Path(self._target.name)
        self.addCleanup(self._target.cleanup)
        self._seed_mcp_json()

    def _seed_mcp_json(self):
        roo = self.target / ".roo"
        roo.mkdir(parents=True)
        data = {
            "mcpServers": {
                "github": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                    "disabled": False,
                    "alwaysAllow": [],
                    "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": self.STORED},
                }
            }
        }
        (roo / "mcp.json").write_text(
            json.dumps(data, indent=4), encoding="utf-8"
        )

    def test_no_github_run_keeps_the_stored_repo_token(self):
        """``setup-repo --no-github``: the empty incoming token must not blank the stored one.

        * arrange: a target repo whose ``.roo/mcp.json`` holds
          ``GITHUB_PERSONAL_ACCESS_TOKEN=ghp_preexisting_in_repo``;
        * act: ``setup-repo <target> --yes --no-github`` through the real
          entry path, with the real provision performing the writes;
        * assert: exit 0 and the stored token still present in the merged
          ``.roo/mcp.json`` in the target.
        """
        result = self.invoke(
            ["setup-repo", str(self.target), "--yes", "--no-github"]
        )
        self.assertEqual(0, result.exit_code, result.output)

        deployed = json.loads(
            (self.target / ".roo" / "mcp.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            self.STORED,
            deployed["mcpServers"]["github"]["env"][
                "GITHUB_PERSONAL_ACCESS_TOKEN"
            ],
        )


# ---------------------------------------------------------------------------
# smoke-test subcommand (behaviour 18 of plans/smoke-test.md)
# ---------------------------------------------------------------------------
#
# Seam contract pinned here (the green step must satisfy exactly this):
#
# 1. ``anvilkit.smoke.run_smoke_test(repo_path, llm_port, docker_runner,
#    runner, *, fix=False, dry_run=False, check_gateway, read_models) ->
#    (report_text, exit_code)`` where report_text is ``format_report`` of
#    exactly six ``LayerResult``s named, in order, the six ``LAYER_NAMES``
#    (sub-checks folded into their parent layer's verdict) and exit_code is
#    ``summarize`` of those six. ``docker_runner(argv) -> (exit_code,
#    stdout, stderr)``; ``runner(invocation)`` is the six-key pidriver
#    result dict; ``check_gateway(port)`` / ``read_models(path)`` are the
#    production health/config functions in the real command, fakes here.
# 2. A ``smoke-test`` subcommand with ``--repo`` (default cwd),
#    ``--llm-port`` (resolved via ``Context.resolve_port``), ``--fix`` and
#    ``--dry-run``; it prints the report to stdout and exits with the
#    orchestrator's exit code.
# 3. CLI testability: ``cli._docker_runner_factory()`` and
#    ``cli._pidriver_runner_factory()`` are the only two seams the command
#    calls to obtain its runners; cli.py constructs no docker argv and
#    makes no HTTP call itself -- all docker/HTTP happens through the
#    factories' products.
#
# Nothing here touches the real docker daemon, the network, or $HOME.


def _require_run_smoke_test():
    """Return the behaviour-18 orchestrator, or fail naming what is missing."""
    check = getattr(smoke, "run_smoke_test", None)
    if check is None:
        raise AssertionError(
            "anvilkit.smoke does not define "
            "run_smoke_test(repo_path, llm_port, docker_runner, runner, "
            "*, fix=False, dry_run=False, check_gateway, read_models) yet "
            "(behaviour 18 of plans/smoke-test.md)"
        )
    return check


def _scripted_docker(script):
    """A fake ``docker_runner``: scripted ``(exit_code, stdout, stderr)``
    per argv key, recording every argv it is handed (list-form only)."""
    remaining = {key: list(vals) for key, vals in script.items()}
    calls = []

    def runner(argv):
        calls.append(list(argv))
        key = (argv[1], argv[2] if len(argv) > 2 else "")
        if key not in remaining or not remaining[key]:
            raise AssertionError(
                "scripted docker runner exhausted for %r" % (list(argv),)
            )
        return remaining[key].pop(0)

    runner.calls = calls
    return runner


def _docker_result(exit_code, stdout="", stderr=""):
    return (exit_code, stdout, stderr)


def _pidriver_result(exit_code=0, stdout="", stderr="", timed_out=False):
    """A six-key pidriver result dict, the shape tests/test_smoke.py pins."""
    return {
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "wall_time_s": 1.0,
        "timed_out": timed_out,
        "evidence": [],
    }


def _recording_pidriver(result):
    """A fake pidriver runner returning ``result``, recording every
    invocation dict it is handed."""
    invocations = []

    def runner(invocation):
        invocations.append(invocation)
        return result

    runner.invocations = invocations
    return runner


# The one JSONL record the pass-case stream carries: one valid event is
# all ``check_coder_run`` requires (judged on the stream existing).
_PASS_STREAM = '{"type": "agent_start"}\n'


class SmokeTestFakes:
    """Installs the behaviour-18 fakes on ``cli`` and hands them out.

    Every collaborator is a recorder; nothing real is spawned or fetched.
    The production ``check_gateway`` / ``read_models`` stand-ins default to
    an online gateway whose single hot model carries the coder id the
    real ``read_models`` returns for the temp project's config.yaml.
    """

    def __init__(self):
        self.docker = _scripted_docker({})
        self.runner = _recording_pidriver(_pidriver_result())
        self.gateway_ports = []
        self.models_paths = []

        coder = cli.config.read_models(cli.REPO_ROOT / "config.yaml")
        self.topology = coder

        def check_gateway(port):
            self.gateway_ports.append(port)
            from anvilkit import health

            return health.GatewayStatus(
                port=port,
                online=True,
                models=[health.ModelStatus(coder.coder_id, True)],
            )

        def read_models(path):
            self.models_paths.append(str(path))
            return coder

        self.check_gateway = check_gateway
        self.read_models = read_models

    @contextlib.contextmanager
    def install(self, case):
        # create=True: the factories do not exist yet (behaviour 18 is red);
        # the command's missing registration is what the tests name, not an
        # AttributeError from the patch itself.
        with mock.patch.object(
            cli, "_docker_runner_factory",
            create=True, return_value=self.docker
        ), mock.patch.object(
            cli, "_pidriver_runner_factory",
            create=True, return_value=self.runner
        ), mock.patch.object(
            cli.health, "check_gateway", self.check_gateway
        ), mock.patch.object(
            cli.config, "read_models", self.read_models
        ):
            yield

    @property
    def docker_argv(self):
        return self.docker.calls


class TestSmokeTestSubcommandRegistered(CliCase):
    """The smoke-test command exists and its options are spelled as pinned."""

    def test_orchestrator_guard(self):
        # The behaviour-18 orchestrator the command must call.
        _require_run_smoke_test()

    def test_smoke_test_help_names_the_command_and_every_option(self):
        result = self.invoke_allowing_exception(["smoke-test", "--help"])
        self.assertEqual(
            0,
            result.exit_code,
            "smoke-test --help must exit 0 with its usage text; got exit %s "
            "(command not registered yet, behaviour 18 of plans/smoke-test.md)"
            % result.exit_code,
        )
        for token in (
            "smoke-test", "--repo", "--fix", "--llm-port",
            "--dry-run", "--dump-events",
        ):
            self.assertIn(
                token,
                result.output,
                "smoke-test --help must name %r (behaviour 18/22 of "
                "plans/smoke-test.md); got: %s" % (token, result.output),
            )


class TestSmokeTestAllOk(CliCase):
    """Every layer passes: exit 0 and the six report names, in order."""

    def _invoke_all_ok(self, repo=None):
        fakes = SmokeTestFakes()
        script = {
            ("version", "--format"): [
                _docker_result(0, "27.1.1", "")
            ],
            ("image", "inspect"): [
                _docker_result(0, "[...]", "")
            ],
            ("network", "inspect"): [
                _docker_result(0, "[...]", "")
            ],
            ("ps", "--filter"): [
                _docker_result(0, "llama-swap-service\n", "")
            ],
            ("volume", "inspect"): [
                _docker_result(0, "[...]", "")
            ],
            ("run", "--rm"): [
                _docker_result(
                    0,
                    '{"providers": {"local": {"models": '
                    '[{"id": "%s"}]}}}' % fakes.topology.coder_id,
                    "",
                )
            ],
        }
        fakes.docker = _scripted_docker(script)
        fakes.runner = _recording_pidriver(
            _pidriver_result(stdout=_PASS_STREAM)
        )
        argv = ["smoke-test"]
        if repo is not None:
            argv += ["--repo", str(repo)]
        with fakes.install(self):
            result = self.invoke(argv)
        return result, fakes

    def _write_prompt(self, repo):
        (Path(repo) / ".pi" / "roles").mkdir(parents=True)
        (Path(repo) / ".pi" / "roles" / "coder.md").write_text(
            "## Coder\nYou write and modify code.\n"
        )

    def test_all_layers_ok_exits_zero(self):
        self._write_prompt(self.project)
        result, _ = self._invoke_all_ok(repo=self.project)
        self.assertEqual(
            0, result.exit_code, result.output
        )

    def test_all_layers_ok_prints_header_and_all_six_layers_in_order(self):
        self._write_prompt(self.project)
        result, _ = self._invoke_all_ok(repo=self.project)
        self.assertEqual(0, result.exit_code, result.output)
        self.assertIn(
            smoke.HEADER,
            result.output,
            "the report must carry the stable header; got: %s" % result.output,
        )
        positions = []
        for name in LAYER_NAMES:
            # The report line for a layer is "glyph <name>: detail"; the
            # "\n<name>:" anchor cannot hit detail text of an earlier layer.
            anchor = "\n%s:" % name
            positions.append(result.output.find(anchor) + 1
                             if anchor in result.output
                             else -1)
        self.assertTrue(
            all(position >= 0 for position in positions),
            "the report must name every layer in LAYER_NAMES %s; "
            "missing positions for %s; got: %s"
            % (LAYER_NAMES, [LAYER_NAMES[i] for i, p in enumerate(positions)
                             if p < 0], result.output),
        )
        self.assertEqual(
            positions, sorted(positions),
            "the six layers must appear in LAYER_NAMES order %s; got "
            "positions %s in: %s" % (LAYER_NAMES, positions, result.output),
        )

    def test_passing_run_reaches_the_pidriver_seam(self):
        self._write_prompt(self.project)
        result, fakes = self._invoke_all_ok(repo=self.project)
        self.assertEqual(0, result.exit_code, result.output)
        self.assertEqual(1, len(fakes.runner.invocations))


class TestSmokeTestExitCodes(CliCase):
    """summarize's classes: docker-class failure exits 4, run-class exits 1."""

    def test_docker_daemon_failure_exits_docker_class(self):
        fakes = SmokeTestFakes()
        fakes.docker = _scripted_docker(
            {("version", "--format"): [_docker_result(1, "", "cannot connect")]})
        self._write_prompt()
        with fakes.install(self):
            result = self.invoke(["smoke-test"])
        self.assertEqual(
            cli.EXIT_DOCKER,
            result.exit_code,
            "a docker-class layer failure must exit 4; got %s: %s"
            % (result.exit_code, result.output),
        )

    def test_agent_level_run_failure_exits_internal_class(self):
        # Everything before the run passes; the run itself exits non-zero
        # WITH output, so the driver returns (agent data) rather than
        # raising DriverError, and layer 5 fails.
        fakes = SmokeTestFakes()
        script = {
            ("version", "--format"): [_docker_result(0, "27.1.1", "")],
            ("image", "inspect"): [_docker_result(0, "[...]", "")],
            ("network", "inspect"): [_docker_result(0, "[...]", "")],
            ("ps", "--filter"): [_docker_result(0, "llama-swap-service\n", "")],
            ("volume", "inspect"): [_docker_result(0, "[...]", "")],
            ("run", "--rm"): [
                _docker_result(
                    0,
                    '{"providers": {"local": {"models": '
                    '[{"id": "%s"}]}}}' % fakes.topology.coder_id,
                    "",
                )
            ],
        }
        fakes.docker = _scripted_docker(script)
        fakes.runner = _recording_pidriver(
            _pidriver_result(exit_code=1, stdout="pi: some agent error")
        )
        self._write_prompt()
        with fakes.install(self):
            result = self.invoke(
                ["smoke-test", "--repo", str(self.project)]
            )
        self.assertEqual(
            cli.EXIT_ERROR,
            result.exit_code,
            "a failed run with layers 1-4 ok must exit 1; got %s: %s"
            % (result.exit_code, result.output),
        )

    def _write_prompt(self):
        (self.project / ".pi" / "roles").mkdir(parents=True)
        (self.project / ".pi" / "roles" / "coder.md").write_text(
            "## Coder\nYou write and modify code.\n"
        )


class TestSmokeTestRepoOption(CliCase):
    """--repo defaults to cwd and reaches the layers absolute."""

    def _fakes_all_ok(self, fakes):
        script = {
            ("version", "--format"): [_docker_result(0, "27.1.1", "")],
            ("image", "inspect"): [_docker_result(0, "[...]", "")],
            ("network", "inspect"): [_docker_result(0, "[...]", "")],
            ("ps", "--filter"): [_docker_result(0, "llama-swap-service\n", "")],
            ("volume", "inspect"): [_docker_result(0, "[...]", "")],
            ("run", "--rm"): [
                _docker_result(
                    0,
                    '{"providers": {"local": {"models": '
                    '[{"id": "%s"}]}}}' % fakes.topology.coder_id,
                    "",
                )
            ],
        }
        fakes.docker = _scripted_docker(script)
        fakes.runner = _recording_pidriver(_pidriver_result(stdout=_PASS_STREAM))

    def test_default_repo_cwd_reaches_the_run_absolutely(self):
        with self.runner.isolated_filesystem() as tmpdir:
            # The prompt must exist in the cwd repo for layer 4 to pass.
            (Path(tmpdir) / ".pi" / "roles").mkdir(parents=True)
            (Path(tmpdir) / ".pi" / "roles" / "coder.md").write_text(
                "## Coder\nYou write and modify code.\n"
            )
            fakes = SmokeTestFakes()
            self._fakes_all_ok(fakes)
            with fakes.install(self):
                result = self.invoke(["smoke-test"])
        self.assertEqual(0, result.exit_code, result.output)
        invocations = fakes.runner.invocations
        self.assertEqual(
            1, len(invocations),
            "the run layer must reach the pidriver seam once; got %s"
            % len(invocations),
        )
        self.assertEqual(
            Path(tmpdir).resolve(),
            Path(invocations[0]["cwd"]).resolve(),
            "the default --repo must be the working directory, absolute: "
            "cwd=%r tmpdir=%s"
            % (invocations[0]["cwd"], tmpdir),
        )

    def test_relative_repo_reaches_the_run_absolutely(self):
        sub = self.project / "sub"
        (sub / ".pi" / "roles").mkdir(parents=True)
        (sub / ".pi" / "roles" / "coder.md").write_text(
            "## Coder\nYou write and modify code.\n"
        )
        fakes = SmokeTestFakes()
        self._fakes_all_ok(fakes)
        with fakes.install(self):
            # The repo is passed relative, resolved against the project cwd.
            old_cwd = os.getcwd()
            try:
                os.chdir(str(self.project))
                result = self.invoke(["smoke-test", "--repo", "sub"])
            finally:
                os.chdir(old_cwd)
        self.assertEqual(0, result.exit_code, result.output)
        invocations = fakes.runner.invocations
        self.assertEqual(1, len(invocations))
        self.assertEqual(
            sub.resolve(),
            Path(invocations[0]["cwd"]).resolve(),
            "a relative --repo must reach the run absolute: cwd=%r sub=%s"
            % (invocations[0]["cwd"], sub),
        )


class TestSmokeTestLlmPort(CliCase):
    """--llm-port resolves through the existing precedence and reaches the
    gateway probe."""

    def test_flag_port_reaches_check_gateway(self):
        # 18080 cannot be the env value (no .env in the temp project) nor
        # the anvil.yaml default, so only the flag can produce it.
        fakes = SmokeTestFakes()
        script = {
            ("version", "--format"): [_docker_result(0, "27.1.1", "")],
            ("image", "inspect"): [_docker_result(0, "[...]", "")],
            ("network", "inspect"): [_docker_result(0, "[...]", "")],
            ("ps", "--filter"): [_docker_result(0, "llama-swap-service\n", "")],
            ("volume", "inspect"): [_docker_result(0, "[...]", "")],
            ("run", "--rm"): [
                _docker_result(
                    0,
                    '{"providers": {"local": {"models": '
                    '[{"id": "%s"}]}}}' % fakes.topology.coder_id,
                    "",
                )
            ],
        }
        fakes.docker = _scripted_docker(script)
        fakes.runner = _recording_pidriver(_pidriver_result(stdout=_PASS_STREAM))
        (self.project / ".pi" / "roles").mkdir(parents=True)
        (self.project / ".pi" / "roles" / "coder.md").write_text(
            "## Coder\nYou write and modify code.\n"
        )
        with fakes.install(self):
            result = self.invoke(
                ["smoke-test", "--llm-port", "18080", "--repo", str(self.project)]
            )
        self.assertEqual(0, result.exit_code, result.output)
        self.assertEqual(
            [18080],
            fakes.gateway_ports,
            "the --llm-port flag must reach the gateway probe as 18080; "
            "got %s" % fakes.gateway_ports,
        )


class TestSmokeTestFix(CliCase):
    """--fix chowns the volume exactly once on a permission failure;
    without --fix nothing is spawned and the layer fails."""

    def _docker_with_permission(self, fakes, with_retry_pass):
        read_argv_prefix = ["docker", "run", "--rm", "-v"]
        models_read = _docker_result(1, "", "cat: /models.json: Permission denied")
        retry = (
            [_docker_result(
                0,
                '{"providers": {"local": {"models": '
                '[{"id": "%s"}]}}}' % fakes.topology.coder_id,
                "",
            )]
            if with_retry_pass
            else [models_read]
        )
        script = {
            ("version", "--format"): [_docker_result(0, "27.1.1", "")],
            ("image", "inspect"): [_docker_result(0, "[...]", "")],
            ("network", "inspect"): [_docker_result(0, "[...]", "")],
            ("ps", "--filter"): [_docker_result(0, "llama-swap-service\n", "")],
            ("volume", "inspect"): [_docker_result(0, "[...]", "")],
            # With --fix and a retry, the ("run","--rm") key is consumed three
            # times in order: first read (permission fail), the chown (also
            # run --rm --user 0 ... chown ...), then the retried read.
            ("run", "--rm"): (
                [models_read, _docker_result(0, "", "")] + retry
                if with_retry_pass
                else [models_read]
            ),
        }
        return _scripted_docker(script)

    def test_fix_permission_failure_chowns_once_and_recovers(self):
        fakes = SmokeTestFakes()
        fakes.docker = self._docker_with_permission(fakes, with_retry_pass=True)
        fakes.runner = _recording_pidriver(_pidriver_result(stdout=_PASS_STREAM))
        (self.project / ".pi" / "roles").mkdir(parents=True)
        (self.project / ".pi" / "roles" / "coder.md").write_text(
            "## Coder\nYou write and modify code.\n"
        )
        with fakes.install(self):
            result = self.invoke(
                ["smoke-test", "--repo", str(self.project), "--fix"]
            )
        self.assertEqual(0, result.exit_code, result.output)
        # The pinned chown argv is
        #   ['docker','run','--rm','-v','<vol>:<home>','--user','0',tag,
        #    'chown','-R','1001:1001',<home>]
        # so the chown verb sits at index 8, not index 2 (see
        # tests/test_smoke.py::test_repair_fix_permission_fail_chown_argv_is_
        # exactly_the_pinned_one for the authoritative shape).
        chowns = [
            argv
            for argv in fakes.docker_argv
            if len(argv) >= 10 and argv[8] == "chown"
        ]
        self.assertEqual(
            1,
            len(chowns),
            "--fix on a permission failure must spawn exactly one chown "
            "argv; got %s in %s" % (chowns, fakes.docker_argv),
        )
        self.assertIn("--user", chowns[0])
        self.assertIn("0", chowns[0])
        self.assertIn("chown", chowns[0])
        self.assertIn("-R", chowns[0])
        self.assertIn("1001:1001", chowns[0])

    def test_without_fix_no_chown_and_the_layer_fails(self):
        fakes = SmokeTestFakes()
        fakes.docker = self._docker_with_permission(fakes, with_retry_pass=False)
        with fakes.install(self):
            result = self.invoke(["smoke-test"])
        self.assertEqual(
            cli.EXIT_DOCKER,
            result.exit_code,
            "without --fix a permission failure must fail the "
            "sandbox-agent-volume layer and exit 4; got %s: %s"
            % (result.exit_code, result.output),
        )
        # Same corrected filter as the --fix test: in the pinned chown argv
        # the chown verb sits at index 8, not index 2.
        chowns = [
            argv
            for argv in fakes.docker_argv
            if len(argv) >= 10 and argv[8] == "chown"
        ]
        self.assertEqual(
            0,
            len(chowns),
            "without --fix nothing is spawned; got %s in %s"
            % (chowns, fakes.docker_argv),
        )


class TestSmokeTestDryRun(CliCase):
    """--dry-run prints what it would check and spawns nothing."""

    def test_dry_run_exits_zero_spawns_nothing_and_names_all_layers(self):
        fakes = SmokeTestFakes()
        # The docker script is EMPTY: any call to it fails the test loudly.
        fakes.docker = _scripted_docker({})
        fakes.runner = _recording_pidriver(_pidriver_result(stdout=_PASS_STREAM))
        with fakes.install(self):
            result = self.invoke(["--dry-run", "smoke-test"])
        self.assertEqual(0, result.exit_code, result.output)
        self.assertEqual(
            [], fakes.docker_argv,
            "--dry-run must not run any docker argv; got %s" % fakes.docker_argv,
        )
        self.assertEqual(
            [], fakes.runner.invocations,
            "--dry-run must not reach the pidriver seam; got %s"
            % fakes.runner.invocations,
        )
        self.assertEqual(
            [], fakes.gateway_ports,
            "--dry-run must not call check_gateway; got %s" % fakes.gateway_ports,
        )
        self.assertEqual(
            [], fakes.models_paths,
            "--dry-run must not call read_models; got %s" % fakes.models_paths,
        )
        for name in LAYER_NAMES:
            self.assertIn(
                name,
                result.output,
                "--dry-run must still name every layer it would check; "
                "missing %r in: %s" % (name, result.output),
            )
        self.assertIn(
            "dry run",
            result.output.lower(),
            "--dry-run output must carry a dry-run marker; got: %s"
            % result.output,
        )


class TestSmokeTestDockerArgvShape(CliCase):
    """cli.py constructs no docker argv: every argv the docker seam receives
    is list-form with 'docker' first."""

    def test_every_docker_argv_is_list_form_starting_with_docker(self):
        fakes = SmokeTestFakes()
        script = {
            ("version", "--format"): [_docker_result(1, "", "daemon down")],
        }
        fakes.docker = _scripted_docker(script)
        with fakes.install(self):
            result = self.invoke(["smoke-test"])
        self.assertEqual(cli.EXIT_DOCKER, result.exit_code, result.output)
        self.assertTrue(fakes.docker_argv, "the docker seam must be called")
        for argv in fakes.docker_argv:
            self.assertIsInstance(
                argv,
                list,
                "every docker argv must be list-form, not a string: %r" % (argv,),
            )
            self.assertEqual(
                "docker",
                argv[0],
                "every docker argv must start with 'docker' (built by the "
                "smoke checks, not hand-built in cli): %r" % (argv,),
            )


class TestSmokeTestMissingRepo(CliCase):
    """"--repo" naming a nonexistent path, or a file, is a usage error:
    exit 2 naming the path, no docker spawn and no HTTP call, and no layer
    report (behaviour 19 of plans/smoke-test.md)."""

    def _fakes_all_ok(self, fakes):
        # The script lets every layer reach its natural verdict, so the red
        # state (no --repo validation yet) runs the layers to completion and
        # exits with a layer-report code instead of tripping the docker fake;
        # the green state consumes none of it.
        script = {
            ("version", "--format"): [_docker_result(0, "27.1.1", "")],
            ("image", "inspect"): [_docker_result(0, "[...]", "")],
            ("network", "inspect"): [_docker_result(0, "[...]", "")],
            ("ps", "--filter"): [_docker_result(0, "llama-swap-service\n", "")],
            ("volume", "inspect"): [_docker_result(0, "[...]", "")],
            ("run", "--rm"): [
                _docker_result(
                    0,
                    '{"providers": {"local": {"models": '
                    '[{"id": "%s"}]}}}' % fakes.topology.coder_id,
                    "",
                )
            ],
        }
        fakes.docker = _scripted_docker(script)
        fakes.runner = _recording_pidriver(_pidriver_result(stdout=_PASS_STREAM))

    def test_nonexistent_repo_exits_usage(self):
        missing = str(self.project / "no-such-dir")
        fakes = SmokeTestFakes()
        self._fakes_all_ok(fakes)
        with fakes.install(self):
            result = self.invoke(["smoke-test", "--repo", missing])
        self.assertEqual(
            cli.EXIT_USAGE,
            result.exit_code,
            "a nonexistent --repo must exit 2 (usage); got %s: %s"
            % (result.exit_code, result.output),
        )

    def test_nonexistent_repo_message_names_the_path(self):
        missing = str(self.project / "no-such-dir")
        fakes = SmokeTestFakes()
        self._fakes_all_ok(fakes)
        with fakes.install(self):
            result = self.invoke(["smoke-test", "--repo", missing])
        self.assertIn(
            missing,
            result.output,
            "the usage message must name the path %s; got: %s"
            % (missing, result.output),
        )

    def test_nonexistent_repo_spawns_nothing(self):
        missing = str(self.project / "no-such-dir")
        fakes = SmokeTestFakes()
        self._fakes_all_ok(fakes)
        with fakes.install(self):
            self.invoke(["smoke-test", "--repo", missing])
        self.assertEqual(
            [], fakes.docker_argv,
            "a nonexistent --repo must not run any docker argv; got %s"
            % fakes.docker_argv,
        )
        self.assertEqual(
            [], fakes.runner.invocations,
            "a nonexistent --repo must not reach the pidriver seam; got %s"
            % fakes.runner.invocations,
        )
        self.assertEqual(
            [], fakes.gateway_ports,
            "a nonexistent --repo must not call check_gateway; got %s"
            % fakes.gateway_ports,
        )
        self.assertEqual(
            [], fakes.models_paths,
            "a nonexistent --repo must not call read_models; got %s"
            % fakes.models_paths,
        )

    def test_repo_that_is_a_file_exits_usage_and_names_it(self):
        afile = self.project / "afile"
        afile.write_text("not a repo\n", encoding="utf-8")
        fakes = SmokeTestFakes()
        self._fakes_all_ok(fakes)
        with fakes.install(self):
            result = self.invoke(["smoke-test", "--repo", str(afile)])
        self.assertEqual(
            cli.EXIT_USAGE,
            result.exit_code,
            "a --repo naming a file must exit 2 (usage); got %s: %s"
            % (result.exit_code, result.output),
        )
        self.assertIn(
            str(afile),
            result.output,
            "the usage message must name the path %s; got: %s"
            % (afile, result.output),
        )

    def test_repo_that_is_a_file_spawns_nothing(self):
        afile = self.project / "afile"
        afile.write_text("not a repo\n", encoding="utf-8")
        fakes = SmokeTestFakes()
        self._fakes_all_ok(fakes)
        with fakes.install(self):
            self.invoke(["smoke-test", "--repo", str(afile)])
        self.assertEqual(
            [], fakes.docker_argv,
            "a --repo naming a file must not run any docker argv; got %s"
            % fakes.docker_argv,
        )
        self.assertEqual(
            [], fakes.runner.invocations,
            "a --repo naming a file must not reach the pidriver seam; got %s"
            % fakes.runner.invocations,
        )
        self.assertEqual(
            [], fakes.gateway_ports,
            "a --repo naming a file must not call check_gateway; got %s"
            % fakes.gateway_ports,
        )
        self.assertEqual(
            [], fakes.models_paths,
            "a --repo naming a file must not call read_models; got %s"
            % fakes.models_paths,
        )

    def test_missing_repo_output_is_not_a_layer_report(self):
        missing = str(self.project / "no-such-dir")
        fakes = SmokeTestFakes()
        self._fakes_all_ok(fakes)
        with fakes.install(self):
            result = self.invoke(["smoke-test", "--repo", missing])
        self.assertNotIn(
            smoke.HEADER,
            result.output,
            "a missing --repo must fail before any layer runs, so the "
            "output must not carry the report header %r; got: %s"
            % (smoke.HEADER, result.output),
        )


def _model_tokens(argv):
    """Every token immediately following a ``--model`` token in ``argv``.

    ``pirole.role_argv`` is the only source of ``--model`` tokens in a
    composed driver argv (the sandbox prefix ends at the image tag), so the
    list is exactly the model ids the composed invocations would send to Pi.
    """
    return [
        argv[i + 1]
        for i, token in enumerate(argv[:-1])
        if token == "--model"
    ]


class TestSmokeTestResolvesCoderModelId(CliCase):
    """The command resolves the coder id from config.yaml (behaviour 21).

    The user never named a model; the ``--model`` token in every composed
    driver invocation must come from ``matrix.vars.coder`` of the repo's
    ``config.yaml`` (``read_models`` -> ``ModelTopology.coder_id``), never
    from the unit-test placeholder ids the standalone checks default to.
    ``SmokeTestFakes.topology`` is built from the real repo-root
    ``config.yaml``, so ``fakes.topology.coder_id`` carries a slash and is
    a real model name, not the placeholder.
    """

    def _invoke_all_ok(self):
        """The TestSmokeTestAllOk recipe: every layer passes, one run."""
        fakes = SmokeTestFakes()
        script = {
            ("version", "--format"): [_docker_result(0, "27.1.1", "")],
            ("image", "inspect"): [_docker_result(0, "[...]", "")],
            ("network", "inspect"): [_docker_result(0, "[...]", "")],
            ("ps", "--filter"): [_docker_result(0, "llama-swap-service\n", "")],
            ("volume", "inspect"): [_docker_result(0, "[...]", "")],
            ("run", "--rm"): [
                _docker_result(
                    0,
                    '{"providers": {"local": {"models": '
                    '[{"id": "%s"}]}}}' % fakes.topology.coder_id,
                    "",
                )
            ],
        }
        fakes.docker = _scripted_docker(script)
        fakes.runner = _recording_pidriver(_pidriver_result(stdout=_PASS_STREAM))
        (self.project / ".pi" / "roles").mkdir(parents=True)
        (self.project / ".pi" / "roles" / "coder.md").write_text(
            "## Coder\nYou write and modify code.\n"
        )
        with fakes.install(self):
            result = self.invoke(["smoke-test", "--repo", str(self.project)])
        return result, fakes

    def _invoke_gateway_fail(self):
        """Layers 1 ok, layer 2's container check fails, the run-class
        layers drive the pidriver seam for the failure-paths proof."""
        fakes = SmokeTestFakes()
        script = {
            ("version", "--format"): [_docker_result(0, "27.1.1", "")],
            ("image", "inspect"): [_docker_result(0, "[...]", "")],
            ("network", "inspect"): [_docker_result(0, "[...]", "")],
            # empty ps output: no line equals the gateway container name,
            # so check_gateway_container fails and layer 2 folds to failed.
            ("ps", "--filter"): [_docker_result(0, "", "")],
        }
        fakes.docker = _scripted_docker(script)
        # Non-zero exit with EMPTY stdout: the driver's own DriverError
        # rule fires for the bad-image-tag probe (the failure path is
        # proved); the missing-prompt probe raises RoleError before the
        # runner is invoked.
        fakes.runner = _recording_pidriver(
            _pidriver_result(exit_code=125, stdout="", stderr="no such tag")
        )
        with fakes.install(self):
            result = self.invoke(["smoke-test", "--repo", str(self.project)])
        return result, fakes

    def test_all_ok_run_uses_the_config_coder_id_not_the_placeholder(self):
        result, fakes = self._invoke_all_ok()
        self.assertEqual(0, result.exit_code, result.output)
        expected = fakes.topology.coder_id
        self.assertTrue(
            "/" in expected,
            "the fakes must expose a real slash-carrying coder id from "
            "config.yaml, not a placeholder; got %r" % expected,
        )
        self.assertEqual(
            1,
            len(fakes.runner.invocations),
            "a healthy stack must drive the pidriver seam exactly once "
            "(the layer-5 run; the failure paths are skipped); got %s"
            % fakes.runner.invocations,
        )
        argv = fakes.runner.invocations[0]["argv"]
        tokens = _model_tokens(argv)
        self.assertEqual(
            [expected],
            tokens,
            "the layer-5 --model token must be the topology's coder id %r "
            "(matrix.vars.coder from config.yaml); got %r in argv %s"
            % (expected, tokens, argv),
        )
        self.assertNotEqual(
            ["coder-model"],
            tokens,
            "the unit-test placeholder id leaked into the composed "
            "argv; got %r" % (argv,),
        )

    def test_failure_path_probes_also_use_the_config_coder_id(self):
        result, fakes = self._invoke_gateway_fail()
        self.assertEqual(
            cli.EXIT_DOCKER,
            result.exit_code,
            "a layer-2 (docker-class) failure must exit 4; got %s: %s"
            % (result.exit_code, result.output),
        )
        self.assertTrue(
            fakes.runner.invocations,
            "the layer-6 failure-path proof must drive the pidriver seam "
            "(the bad-image-tag probe); got no invocations",
        )
        expected = fakes.topology.coder_id
        for invocation in fakes.runner.invocations:
            argv = invocation["argv"]
            tokens = _model_tokens(argv)
            self.assertEqual(
                [expected],
                tokens,
                "every failure-path --model token must be the topology's "
                "coder id %r; got %r in argv %s" % (expected, tokens, argv),
            )

    def test_placeholder_coder_model_never_appears_in_any_argv(self):
        _result, fakes = self._invoke_all_ok()
        self.assertTrue(
            fakes.runner.invocations,
            "the all-ok scenario must drive the pidriver seam; got none",
        )
        for invocation in fakes.runner.invocations:
            argv = invocation["argv"]
            self.assertNotIn(
                "coder-model",
                argv,
                "the unit-test placeholder id leaked into the composed "
                "driver argv; got %s" % (argv,),
            )

    def test_orchestrator_resolves_the_coder_id_from_read_models(self):
        # Pins run_smoke_test itself, not just the CLI wiring: the
        # orchestrator must read the topology once and compose every
        # driver --model token from topology.coder_id.
        fakes = SmokeTestFakes()
        script = {
            ("version", "--format"): [_docker_result(0, "27.1.1", "")],
            ("image", "inspect"): [_docker_result(0, "[...]", "")],
            ("network", "inspect"): [_docker_result(0, "[...]", "")],
            ("ps", "--filter"): [_docker_result(0, "", "")],
        }
        docker_runner = _scripted_docker(script)
        runner = _recording_pidriver(
            _pidriver_result(exit_code=125, stdout="", stderr="no such tag")
        )
        _report, exit_code = smoke.run_smoke_test(
            str(self.project),
            fakes.topology.gateway_port,
            docker_runner,
            runner,
            check_gateway=fakes.check_gateway,
            read_models=fakes.read_models,
        )
        self.assertEqual(
            cli.EXIT_DOCKER,
            exit_code,
            "a layer-2 (docker-class) failure must exit 4; got %s"
            % exit_code,
        )
        self.assertTrue(
            runner.invocations,
            "the layer-6 failure-path proof must drive the pidriver "
            "seam; got no invocations",
        )
        expected = fakes.topology.coder_id
        for invocation in runner.invocations:
            argv = invocation["argv"]
            tokens = _model_tokens(argv)
            self.assertEqual(
                [expected],
                tokens,
                "the orchestrator must compose the --model token from "
                "the topology's coder id %r (read once via read_models); "
                "got %r in argv %s" % (expected, tokens, argv),
            )


# ---------------------------------------------------------------------------
# smoke-test --dump-events  (behaviour 22 of plans/smoke-test.md)
# ---------------------------------------------------------------------------

# The one unique JSONL line the pass-case dump stream carries: the dump
# must reproduce it VERBATIM, never re-serialised.
_DUMPER_STREAM_LINE = (
    '{"type": "agent_start", "trace": "behaviour-22-verbatim-pin"}'
)


class TestSmokeTestDumpEvents(CliCase):
    """Behaviour 22 (b): ``anvil smoke-test --dump-events`` appends the
    run's full raw JSONL stream to the report, verbatim, under a line
    containing the ``coder-run events`` marker — only when the layer-5
    run check ran and passed."""

    DUMP_EVENTS_MARKER = "coder-run events"

    def _invoke(self, fakes, extra_argv, docker_script, stream, repo=None):
        fakes.docker = _scripted_docker(docker_script)
        fakes.runner = _recording_pidriver(
            _pidriver_result(stdout=stream)
        )
        argv = ["smoke-test"] + list(extra_argv)
        if repo is not None:
            argv += ["--repo", str(repo)]
        with fakes.install(self):
            result = self.invoke(argv)
        return result, fakes

    def _all_ok_docker_script(self, fakes):
        return {
            ("version", "--format"): [_docker_result(0, "27.1.1", "")],
            ("image", "inspect"): [_docker_result(0, "[...]", "")],
            ("network", "inspect"): [_docker_result(0, "[...]", "")],
            ("ps", "--filter"): [_docker_result(0, "llama-swap-service\n", "")],
            ("volume", "inspect"): [_docker_result(0, "[...]", "")],
            ("run", "--rm"): [
                _docker_result(
                    0,
                    '{"providers": {"local": {"models": '
                    '[{"id": "%s"}]}}}' % fakes.topology.coder_id,
                    "",
                )
            ],
        }

    def _write_prompt(self, repo=None):
        base = repo if repo is not None else self.project
        (Path(base) / ".pi" / "roles").mkdir(parents=True)
        (Path(base) / ".pi" / "roles" / "coder.md").write_text(
            "## Coder\nYou write and modify code.\n"
        )

    def test_dump_events_all_ok_appends_the_raw_stream_verbatim(self):
        # Arrange: an all-ok stack, the run stream carrying the unique
        # line plus one more record.
        fakes = SmokeTestFakes()
        self._write_prompt()
        stream = _DUMPER_STREAM_LINE + "\n" + '{"type": "message", "id": "m1"}\n'
        result, _fakes = self._invoke(
            fakes,
            ["--dump-events"],
            self._all_ok_docker_script(fakes),
            stream,
        )

        # Assert: exit 0, the marker, and every non-empty stream line
        # VERBATIM in the report.
        self.assertEqual(0, result.exit_code, result.output)
        self.assertIn(
            self.DUMP_EVENTS_MARKER,
            result.output,
            "--dump-events on a passed layer-5 run must append the "
            "section under a line containing %r; got: %s"
            % (self.DUMP_EVENTS_MARKER, result.output),
        )
        self.assertIn(
            _DUMPER_STREAM_LINE,
            result.output,
            "the run's raw stdout must be appended verbatim (the unique "
            "line must appear exactly as emitted); got: %s" % result.output,
        )
        self.assertIn(
            '{"type": "message", "id": "m1"}',
            result.output,
            "every non-empty stream line must be appended verbatim; "
            "got: %s" % result.output,
        )

    def test_without_dump_events_no_marker_and_no_raw_stream_line(self):
        # Arrange: the same all-ok stack, the flag absent.
        fakes = SmokeTestFakes()
        self._write_prompt()
        result, _ = self._invoke(
            fakes,
            [],
            self._all_ok_docker_script(fakes),
            _DUMPER_STREAM_LINE + "\n",
        )

        # Assert: exit 0; the compact counts stay in the layer-5 detail
        # (which already names the record count) but the raw stream line
        # and the marker are absent.
        self.assertEqual(0, result.exit_code, result.output)
        self.assertNotIn(
            self.DUMP_EVENTS_MARKER,
            result.output,
            "without --dump-events no dump section may appear; got: %s"
            % result.output,
        )
        self.assertNotIn(
            _DUMPER_STREAM_LINE,
            result.output,
            "without --dump-events the raw stream line must not be in "
            "the output (only the compact counts); got: %s" % result.output,
        )

    def test_dump_events_layer1_failing_exits_four_without_marker(self):
        # Arrange: the docker daemon is down — layer 1 fails, so layer 5
        # is skipped and the run never happens; --dump-events has
        # nothing to dump and must not turn the failure into a
        # traceback.
        fakes = SmokeTestFakes()
        fakes.docker = _scripted_docker(
            {("version", "--format"): [_docker_result(1, "", "cannot connect")]}
        )
        self._write_prompt()
        with fakes.install(self):
            result = self.invoke(
                ["smoke-test", "--dump-events", "--repo", str(self.project)]
            )

        # Assert: the docker-class exit, no marker, no stream line, no
        # traceback.
        self.assertEqual(
            cli.EXIT_DOCKER,
            result.exit_code,
            "a docker-class layer failure with --dump-events must still "
            "exit 4; got %s: %s" % (result.exit_code, result.output),
        )
        self.assertNotIn(
            self.DUMP_EVENTS_MARKER,
            result.output,
            "a skipped layer-5 run must not append the dump section; "
            "got: %s" % result.output,
        )
        self.assertNotIn(_DUMPER_STREAM_LINE, result.output)
        self.assertNotIn(
            "Traceback",
            result.output,
            "a layer-1 failure with --dump-events must not print a "
            "traceback; got: %s" % result.output,
        )

    def test_dry_run_with_dump_events_exits_zero_without_marker(self):
        # Arrange: --dry-run returns before any run, so --dump-events has
        # no run to dump; the docker script is EMPTY (any call fails the
        # test loudly).
        fakes = SmokeTestFakes()
        fakes.docker = _scripted_docker({})
        fakes.runner = _recording_pidriver(
            _pidriver_result(stdout=_DUMPER_STREAM_LINE + "\n")
        )
        with fakes.install(self):
            result = self.invoke(
                ["smoke-test", "--dry-run", "--dump-events",
                 "--repo", str(self.project)]
            )

        # Assert: exit 0, no run reached the seam, no marker, no
        # stream line.
        self.assertEqual(0, result.exit_code, result.output)
        self.assertEqual(
            [], fakes.runner.invocations,
            "--dry-run must not reach the pidriver seam; got %s"
            % fakes.runner.invocations,
        )
        self.assertNotIn(
            self.DUMP_EVENTS_MARKER,
            result.output,
            "--dry-run --dump-events must append nothing; got: %s"
            % result.output,
        )
        self.assertNotIn(_DUMPER_STREAM_LINE, result.output)


# ---------------------------------------------------------------------------
# _collect_guard_findings  (behaviour 3 of plans/setup-repo-guards.md — the
# resolve → fetch → check_all → check_token_all flow verify-guards and
# doctor's Guards section each duplicate today, extracted once)
# ---------------------------------------------------------------------------


def _require_collect_guard_findings():
    """Return the behaviour-3 helper, or fail naming what is missing."""
    helper = getattr(cli, "_collect_guard_findings", None)
    if not callable(helper):
        raise AssertionError(
            "anvilkit.cli does not define a callable "
            "_collect_guard_findings(target, token, branch, other_repo=None, "
            'noun="target") '
            "yet (behaviour 3 of plans/setup-repo-guards.md)"
        )
    return helper


def _call_arg(mocked, name, index):
    """One call argument by name, falling back to its positional slot, so
    the pin holds whether the helper passes it by keyword or position."""
    args, kwargs = mocked.call_args
    if name in kwargs:
        return kwargs[name]
    if len(args) > index:
        return args[index]
    return mock.DEFAULT


class TestCollectGuardFindings(CliCase):
    """The shared guard flow: resolve → fetch → check_all → check_token_all.

    Behaviour 3 of plans/setup-repo-guards.md: verify-guards and doctor's
    Guards section each duplicate this flow today; the helper must return
    ``(branch_findings, token_findings, repository)`` reproducing, for every
    input, exactly what both call sites do now, so the green step can rewire
    them with byte-for-byte unchanged output.
    """

    OWNER = "iar3-r8"
    REPO = "Anvil"
    TOKEN = "ghp_collect_token"

    def run_collect(
        self,
        target,
        token,
        branch,
        other_repo=None,
        noun="target",
        repository=None,
        rules=None,
        fetch_reason=None,
        branch_findings=None,
        token_findings=None,
    ):
        """``_collect_guard_findings`` with the four piguard seams replaced,
        so the flow runs offline. Returns ``result`` plus a dict of the seam
        mocks (``resolve``, ``fetch``, ``check_all``, ``token_all``) for
        call-argument assertions.
        """
        collect = _require_collect_guard_findings()
        resolve_patcher = mock.patch.object(
            cli.piguard, "resolve_repository", return_value=repository
        )
        fetch_patcher = mock.patch.object(
            cli.piguard,
            "fetch_branch_rules",
            return_value=(rules, fetch_reason),
        )
        check_all_patcher = mock.patch.object(
            cli.piguard, "check_all", return_value=branch_findings
        )
        token_all_patcher = mock.patch.object(
            cli.piguard, "check_token_all", return_value=token_findings
        )
        resolve = resolve_patcher.start()
        fetch = fetch_patcher.start()
        check_all = check_all_patcher.start()
        token_all = token_all_patcher.start()
        try:
            result = collect(
                target,
                token,
                branch,
                other_repo=other_repo,
                noun=noun,
            )
        finally:
            for patcher in (
                resolve_patcher,
                fetch_patcher,
                check_all_patcher,
                token_all_patcher,
            ):
                patcher.stop()
        return result, {
            "resolve": resolve,
            "fetch": fetch,
            "check_all": check_all,
            "token_all": token_all,
        }

    def test_resolvable_target_collects_branch_and_token_findings(self):
        # The full flow: resolve → fetch → check_all → check_token_all,
        # returning the exact objects the seams produced, not copies.
        from anvilkit.pi import piguard

        branch = piguard.check_all(five_rule_branch_rules())
        token = [
            token_finding("target_access", "passed"),
            token_finding(
                "named_repo", "skipped", reason="no --other-repo was supplied"
            ),
        ]
        target = self.project
        rules = five_rule_branch_rules()
        (branch_out, token_out, repository), seams = self.run_collect(
            target,
            self.TOKEN,
            "main",
            repository=(self.OWNER, self.REPO),
            rules=rules,
            branch_findings=branch,
            token_findings=token,
        )
        # check_all receives exactly the rules fetch returned: the flow is
        # resolve -> fetch -> check_all(fetched rules), not a re-fetch or a
        # guess.
        check_all_args, check_all_kwargs = seams["check_all"].call_args
        self.assertIs(
            rules,
            check_all_kwargs.get("rules", check_all_args[0]),
            "check_all must run on the exact rules fetch_branch_rules "
            "returned",
        )
        self.assertIs(
            branch,
            branch_out,
            "the branch findings must be the exact objects check_all "
            "returned, so the call sites' summarize and rendering are "
            "unchanged",
        )
        self.assertIs(
            token,
            token_out,
            "the token findings must be the exact objects check_token_all "
            "returned",
        )
        self.assertEqual(
            (self.OWNER, self.REPO),
            repository,
            "the third return element must be the repository resolve "
            "returned",
        )
        # The flow drives the seams with the resolved identity:
        # fetch_branch_rules(owner, repo, branch, token).
        self.assertEqual(
            self.OWNER, _call_arg(seams["fetch"], "owner", 0)
        )
        self.assertEqual(
            self.REPO, _call_arg(seams["fetch"], "repo", 1)
        )
        self.assertEqual(
            "main", _call_arg(seams["fetch"], "branch", 2)
        )
        self.assertEqual(
            self.TOKEN, _call_arg(seams["fetch"], "token", 3)
        )
        # check_all is the single seam for the branch rules.
        self.assertEqual(
            1,
            seams["check_all"].call_count,
            "the branch rules must be reported through the single check_all "
            "seam",
        )
        # check_token_all receives the resolved identity, the token, and
        # other_repo=None by default (matching doctor's call site).
        self.assertEqual(
            self.OWNER, _call_arg(seams["token_all"], "owner", 0)
        )
        self.assertEqual(
            self.REPO, _call_arg(seams["token_all"], "repo", 1)
        )
        self.assertEqual(
            self.TOKEN, _call_arg(seams["token_all"], "token", 2)
        )
        self.assertIsNone(
            _call_arg(seams["token_all"], "other_repo", 3),
            "other_repo must default to None, so the named-repo probe emits "
            "its skip rather than guessing (the call sites' default)",
        )

    def test_other_repo_is_forwarded_to_check_token_all(self):
        # --other-repo's raw value reaches check_token_all unchanged, as it
        # does at verify-guards today: the CLI never re-validates it.
        from anvilkit.pi import piguard

        branch = piguard.check_all(five_rule_branch_rules())
        token = [
            token_finding(
                "named_repo", "skipped",
                reason="the named repository was not reached",
            )
        ]
        (_branch_out, _token_out, _repository), seams = self.run_collect(
            self.project,
            self.TOKEN,
            "main",
            other_repo="someorg/other",
            repository=(self.OWNER, self.REPO),
            rules=five_rule_branch_rules(),
            branch_findings=branch,
            token_findings=token,
        )
        self.assertEqual(
            "someorg/other",
            _call_arg(seams["token_all"], "other_repo", 3),
            "the raw other_repo value must reach check_token_all unchanged",
        )

    def test_unresolvable_target_yields_four_skips_and_no_token_findings(
        self,
    ):
        # No resolvable repository: four skipped branch findings carrying
        # the same reason verify_guards builds today (it names the target
        # path), no token findings at all, and none of fetch/check_all/
        # check_token_all is called — a probe without an identity would be
        # a guess.
        from anvilkit.pi import piguard

        target = self.project
        reason = (
            "owner/repo could not be resolved from the origin remote of "
            "{}: the target has no origin, or its remote is not a GitHub "
            "repository, and the identity is never guessed".format(target)
        )
        (branch_out, token_out, repository), seams = self.run_collect(
            target, self.TOKEN, "main", repository=None
        )
        self.assertEqual(
            piguard.skipped_findings(reason),
            branch_out,
            "the branch findings must be skipped_findings of the exact "
            "reason verify_guards builds (it names the target path)",
        )
        self.assertEqual(
            4,
            len(branch_out),
            "one skipped finding per defined branch check is expected",
        )
        for finding in branch_out:
            self.assertEqual("skipped", finding["status"])
        self.assertIn(str(target), branch_out[0]["reason"])
        self.assertEqual(
            [],
            token_out,
            "no token findings without a resolvable repository - the token "
            "probes never run",
        )
        self.assertIsNone(repository)
        self.assertFalse(
            seams["fetch"].called,
            "fetch_branch_rules must not run without a resolvable "
            "repository",
        )
        self.assertFalse(
            seams["check_all"].called,
            "check_all must not run without a resolvable repository",
        )
        self.assertFalse(
            seams["token_all"].called,
            "check_token_all must not run without a resolvable repository",
        )

    def test_doctor_noun_keeps_the_project_wording(self):
        # doctor's _report_guards builds the same unresolvable-target reason
        # but says "the project" where verify_guards says "the target". With
        # noun="project" the helper must reproduce doctor's exact reason, so
        # the extraction leaves doctor's output byte-for-byte unchanged.
        from anvilkit.pi import piguard

        target = self.project
        reason = (
            "owner/repo could not be resolved from the origin remote of "
            "{}: the project has no origin, or its remote is not a GitHub "
            "repository, and the identity is never guessed".format(target)
        )
        (branch_out, token_out, repository), seams = self.run_collect(
            target, self.TOKEN, "main", noun="project", repository=None
        )
        self.assertEqual(
            piguard.skipped_findings(reason),
            branch_out,
            "the branch findings must be skipped_findings of the exact "
            'reason doctor builds (the noun "project" replaces "target")',
        )
        self.assertIn("the project has no origin", branch_out[0]["reason"])
        self.assertNotIn(
            "the target has no origin",
            branch_out[0]["reason"],
            'with noun="project" the "target" wording must be gone, not '
            "appended",
        )
        self.assertEqual(
            [],
            token_out,
            "no token findings without a resolvable repository - the token "
            "probes never run",
        )
        self.assertIsNone(repository)
        self.assertFalse(
            seams["fetch"].called,
            "fetch_branch_rules must not run without a resolvable "
            "repository",
        )
        self.assertFalse(
            seams["check_all"].called,
            "check_all must not run without a resolvable repository",
        )
        self.assertFalse(
            seams["token_all"].called,
            "check_token_all must not run without a resolvable repository",
        )

    def test_fetch_failure_yields_skipped_findings(self):
        # The repository resolves but the fetch fails: four skipped branch
        # findings carrying the fetch reason, and check_all never runs. The
        # token probes DO still run - verified against today's code: both
        # call sites assign token_findings outside the rules if/else (the
        # verify_guards and _report_guards ``else`` branches both reach
        # check_token_all), so the helper must do the same.
        from anvilkit.pi import piguard

        fetch_reason = "the fetch reason"
        token = [
            token_finding("target_access", "passed"),
            token_finding(
                "named_repo", "skipped", reason="no --other-repo was supplied"
            ),
        ]
        (branch_out, token_out, repository), seams = self.run_collect(
            self.project,
            self.TOKEN,
            "main",
            repository=(self.OWNER, self.REPO),
            rules=None,
            fetch_reason=fetch_reason,
            token_findings=token,
        )
        self.assertEqual(
            piguard.skipped_findings(fetch_reason),
            branch_out,
            "a failed fetch must yield skipped_findings of the fetch reason",
        )
        self.assertEqual(
            4,
            len(branch_out),
            "one skipped finding per defined branch check is expected",
        )
        for finding in branch_out:
            self.assertEqual("skipped", finding["status"])
        self.assertFalse(
            seams["check_all"].called,
            "a failed fetch must not reach check_all",
        )
        self.assertIs(
            token,
            token_out,
            "the token findings must still come from check_token_all when "
            "the fetch fails, as both call sites do today",
        )
        self.assertTrue(
            seams["token_all"].called,
            "the token probes run whenever the repository resolves, even "
            "when the branch-rules fetch fails",
        )
        self.assertEqual(
            (self.OWNER, self.REPO),
            repository,
            "the repository is returned even when the fetch fails",
        )