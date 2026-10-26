"""Tests for anvilkit.pi.pisandbox - the sandbox build/run argv builders.

Written before the implementation (TDD, ``plans/pi-sandbox-image.md``:
behaviour 6 "build argv", behaviour 7 "run argv", behaviour 8 "environment
allowlist").

The production module ``anvilkit.pi.pisandbox`` does not exist yet, so every
test loads it through :meth:`PisandboxTestCase._pisandbox`, which fails
with a clear assertion instead of letting a collection-time ImportError
mask the reason the suite is red.

Pinned names (they must match what already exists):

- the landed ``docker/Dockerfile.sandbox`` user is ``sandbox`` at uid 1001,
  so the run argv carries ``--user 1001`` and the container agent home is
  ``/home/sandbox/.pi/agent``;
- the internal network is ``sandbox-internal`` (the compose-side pin that
  the run-side ``--network`` token must not drift from);
- the named volume is ``sandbox-agent`` -- stable across runs, and named
  after the existing ``pi-bakeoff-agent`` volume in ``docker-compose.yml``.

The run argv ends at the image tag: the ``pi`` invocation itself (model,
prompt, tools) is a later capability and out of scope for these tests.
Each allowed env name is emitted as two tokens, ``-e`` then ``NAME=VALUE``.
"""

import importlib
import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


REPO_PATH = "/home/u/project"
TAG = "anvil/sandbox:latest"
AGENT_HOME = "/home/sandbox/.pi/agent"
NAMED_VOLUME = "sandbox-agent"
INTERNAL_NETWORK = "sandbox-internal"
ALLOWED_ENV_NAMES = ("PI_GATEWAY_HOST", "PI_GATEWAY_PORT", "PI_CODING_AGENT_DIR")
ALLOWED_ENV_VALUES = {
    "PI_GATEWAY_HOST": "llama-swap",
    "PI_GATEWAY_PORT": "8080",
    "PI_CODING_AGENT_DIR": AGENT_HOME,
}


class PisandboxTestCase(unittest.TestCase):
    """Shared module access and argv-shape helpers."""

    def _pisandbox(self):
        """Import anvilkit.pi.pisandbox, failing clearly if the module is absent."""
        spec = importlib.util.find_spec("anvilkit.pi.pisandbox")
        self.assertIsNotNone(
            spec,
            "anvilkit.pi.pisandbox cannot be imported; the sandbox argv "
            "builders have not been implemented yet",
        )
        return importlib.import_module("anvilkit.pi.pisandbox")

    def _assert_token_discipline(self, argv):
        """The no-shell-reparse rule: a list of str, no space in any token."""
        self.assertIsInstance(
            argv,
            list,
            "argv builders must return a list of tokens, never a string, "
            "so no shell re-parses the result",
        )
        for token in argv:
            self.assertIsInstance(
                token,
                str,
                "every argv element must be a str token",
            )
            self.assertNotIn(
                " ",
                token,
                "no token may contain a space; each element is passed "
                "separately and never shell-split",
            )

    def _flag_values(self, argv, flag):
        """Values immediately following each occurrence of *flag* in *argv*."""
        return [
            argv[i + 1]
            for i, token in enumerate(argv)
            if token == flag and i + 1 < len(argv)
        ]


class TestSandboxError(PisandboxTestCase):
    """The module's single exception type, importable by name."""

    def test_sandbox_error_is_an_exception_type(self):
        pisandbox = self._pisandbox()
        self.assertTrue(
            isinstance(pisandbox.SandboxError, type)
            and issubclass(pisandbox.SandboxError, BaseException),
            "anvilkit.pi.pisandbox must expose SandboxError as an exception "
            "type (the module's one exception type, per repo convention)",
        )


class TestBuildArgv(PisandboxTestCase):
    """build_argv: the docker build command, context at the repo root."""

    def test_build_argv_returns_exact_tokens_with_repo_root_context(self):
        pisandbox = self._pisandbox()
        argv = pisandbox.build_argv(TAG)
        self._assert_token_discipline(argv)
        self.assertEqual(
            argv,
            ["docker", "build", "-t", TAG, "-f", "docker/Dockerfile.sandbox", "."],
            "the build context must be the repo root, never the "
            "Dockerfile's directory",
        )

    def test_build_argv_returns_list_of_str_tokens_without_spaces(self):
        pisandbox = self._pisandbox()
        self._assert_token_discipline(pisandbox.build_argv(TAG))

    def test_build_argv_empty_tag_raises_sandbox_error_naming_the_field(self):
        pisandbox = self._pisandbox()
        with self.assertRaises(pisandbox.SandboxError) as ctx:
            pisandbox.build_argv("")
        self.assertIn(
            "tag",
            str(ctx.exception),
            "the refusal must name the offending field; got: %r"
            % str(ctx.exception),
        )

    def test_build_argv_whitespace_tag_raises_sandbox_error_naming_the_field(self):
        pisandbox = self._pisandbox()
        with self.assertRaises(pisandbox.SandboxError) as ctx:
            pisandbox.build_argv("   ")
        self.assertIn(
            "tag",
            str(ctx.exception),
            "the refusal must name the offending field; got: %r"
            % str(ctx.exception),
        )


class TestRunArgv(PisandboxTestCase):
    """run_argv: the docker run command, ending at the image tag."""

    def test_run_argv_carries_lifecycle_and_safety_tokens(self):
        pisandbox = self._pisandbox()
        argv = pisandbox.run_argv(REPO_PATH, TAG)
        self._assert_token_discipline(argv)
        self.assertEqual(
            argv[:2],
            ["docker", "run"],
            "the run argv is a docker run command",
        )
        self.assertIn("--rm", argv)
        self.assertEqual(
            self._flag_values(argv, "--network"),
            [INTERNAL_NETWORK],
            "the sandbox must ride only the internal network",
        )
        self.assertEqual(
            self._flag_values(argv, "--user"),
            ["1001"],
            "the container must run as the non-root uid of the image user",
        )
        self.assertEqual(
            self._flag_values(argv, "--cap-drop"),
            ["ALL"],
        )
        self.assertEqual(
            self._flag_values(argv, "--security-opt"),
            ["no-new-privileges"],
        )

    def test_run_argv_binds_repo_at_workspace_and_named_volume_at_agent_home(self):
        pisandbox = self._pisandbox()
        argv = pisandbox.run_argv(REPO_PATH, TAG)
        volumes = self._flag_values(argv, "-v")
        self.assertIn(
            REPO_PATH + ":/workspace",
            volumes,
            "the host repo must be bound at /workspace",
        )
        self.assertIn(
            NAMED_VOLUME + ":" + AGENT_HOME,
            volumes,
            "the container-local agent home must be a named volume, not a "
            "host bind",
        )
        self.assertEqual(
            len(volumes),
            2,
            "exactly the repo bind and the named agent volume, no other "
            "mounts; got: %r" % volumes,
        )

    def test_run_argv_final_element_is_the_image_tag(self):
        pisandbox = self._pisandbox()
        argv = pisandbox.run_argv(REPO_PATH, TAG)
        self.assertEqual(
            argv[-1],
            TAG,
            "the run argv ends at the image tag; the agent invocation is "
            "not part of it yet",
        )

    def test_run_argv_returns_list_of_str_tokens_without_spaces(self):
        pisandbox = self._pisandbox()
        self._assert_token_discipline(pisandbox.run_argv(REPO_PATH, TAG))

    def test_run_argv_empty_repo_path_raises_sandbox_error_naming_the_field(self):
        pisandbox = self._pisandbox()
        with self.assertRaises(pisandbox.SandboxError) as ctx:
            pisandbox.run_argv("", TAG)
        self.assertIn(
            "repo_path",
            str(ctx.exception),
            "the refusal must name the offending field; got: %r"
            % str(ctx.exception),
        )

    def test_run_argv_relative_repo_path_raises_sandbox_error_naming_the_field(self):
        pisandbox = self._pisandbox()
        with self.assertRaises(pisandbox.SandboxError) as ctx:
            pisandbox.run_argv("./project", TAG)
        self.assertIn(
            "repo_path",
            str(ctx.exception),
            "the refusal must name the offending field; got: %r"
            % str(ctx.exception),
        )

    def test_run_argv_repo_path_with_dot_pi_component_is_refused_naming_the_path(self):
        pisandbox = self._pisandbox()
        with self.assertRaises(pisandbox.SandboxError) as ctx:
            pisandbox.run_argv("/home/u/.pi/repo", TAG)
        self.assertIn(
            "/home/u/.pi/repo",
            str(ctx.exception),
            "a run that appears to need the host agent home is "
            "misconfigured and must be refused by name; got: %r"
            % str(ctx.exception),
        )

    def test_run_argv_repo_path_with_dot_pi_only_as_fragment_is_accepted(self):
        pisandbox = self._pisandbox()
        argv = pisandbox.run_argv("/home/u/pictures", TAG)
        self.assertIn(
            "/home/u/pictures:/workspace",
            self._flag_values(argv, "-v"),
            "the refusal is component-based; .pi inside a longer name "
            "must not trigger it",
        )


class TestRunArgvEnvAllowlist(PisandboxTestCase):
    """run_argv env mapping: exactly three names pass, named for a reason."""

    def test_run_argv_without_env_produces_no_env_tokens(self):
        pisandbox = self._pisandbox()
        argv = pisandbox.run_argv(REPO_PATH, TAG)
        self.assertNotIn(
            "-e",
            argv,
            "no env argument means an empty allowlist and no -e tokens",
        )

    def test_run_argv_allowed_env_names_pass_as_flag_then_name_equals_value(self):
        pisandbox = self._pisandbox()
        for name in ALLOWED_ENV_NAMES:
            with self.subTest(env_name=name):
                value = ALLOWED_ENV_VALUES[name]
                argv = pisandbox.run_argv(REPO_PATH, TAG, env={name: value})
                self._assert_token_discipline(argv)
                self.assertEqual(
                    self._flag_values(argv, "-e"),
                    [name + "=" + value],
                    "each allowed name passes as exactly one -e pair, "
                    "flag then NAME=VALUE",
                )

    def test_run_argv_all_three_allowed_names_pass_together(self):
        pisandbox = self._pisandbox()
        argv = pisandbox.run_argv(REPO_PATH, TAG, env=dict(ALLOWED_ENV_VALUES))
        self.assertEqual(
            self._flag_values(argv, "-e"),
            ["PI_GATEWAY_HOST=llama-swap", "PI_GATEWAY_PORT=8080",
             "PI_CODING_AGENT_DIR=" + AGENT_HOME],
            "exactly the three allowlisted names pass, each once",
        )

    def test_run_argv_disallowed_env_name_raises_sandbox_error_naming_it(self):
        pisandbox = self._pisandbox()
        for name in ("HOME", "PATH", "LLM_PORT"):
            with self.subTest(env_name=name):
                with self.assertRaises(pisandbox.SandboxError) as ctx:
                    pisandbox.run_argv(REPO_PATH, TAG, env={name: "x"})
                self.assertIn(
                    name,
                    str(ctx.exception),
                    "the refusal must name the offending env name; got: %r"
                    % str(ctx.exception),
                )

    def test_run_argv_credential_like_env_name_is_refused_with_credential_reason(self):
        pisandbox = self._pisandbox()
        for name, marker in (
            ("PI_GATEWAY_TOKEN", "TOKEN"),
            ("PI_CODING_API_KEY", "KEY"),
            ("ANTHROPIC_SECRET", "SECRET"),
        ):
            with self.subTest(env_name=name):
                with self.assertRaises(pisandbox.SandboxError) as ctx:
                    pisandbox.run_argv(REPO_PATH, TAG, env={name: "x"})
                message = str(ctx.exception)
                self.assertIn(
                    name,
                    message,
                    "the refusal must name the offending env name; got: %r"
                    % message,
                )
                self.assertTrue(
                    "credential" in message.lower() or marker in message,
                    "the refusal must state the credential reason (values "
                    "passed in are readable by every process inside); got: %r"
                    % message,
                )
