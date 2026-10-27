"""Boundary pins for ``plans/pi-phase6-single-role.md`` behaviours 1-3.

These are the loop's home test module (``tests/test_pirole.py``). The batch
covers the three boundary pins that assert *today's* ``pisandbox`` / runner
contract before ``pirole`` / ``pidriver`` build on top of it, so nothing the
later behaviours add can quietly invalidate the seam:

1. ``sandbox-run-argv-unchanged`` - the run argv ends at the image tag and
   carries no ``pi`` token; the append point the driver relies on.
2. ``sandbox-refuses-credential-env`` - a credential-looking env name is
   refused with the credential reason, nothing is returned.
3. ``runner-seam-contract`` - ``subprocess_runner`` invoked with the
   invocation-dict contract returns exactly the six result keys with their
   documented types.

These pin existing, already-landed code (``anvilkit/pi/pisandbox.py`` and
``anvilkit/pi/pibakeoff.py``). A pin that cannot be red against the current
contract is still worth recording: it is the boundary the later behaviours
must not move. They are written against the documented public contract only -
no source text, no production change.

Documented runner contract, cited from
``anvilkit/pi/pibakeoff.py`` ``subprocess_runner`` (and mirrored in
``anvilkit/pi/piapproval.py``): one invocation dict in
(``argv`` list[str], ``cwd`` str, ``stdin`` str, ``timeout_s`` float, optional
``env`` dict) and exactly six result keys out -
``exit_code`` (int), ``stdout`` (str), ``stderr`` (str),
``wall_time_s`` (float), ``timed_out`` (bool), ``evidence`` (str).
"""

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit.pi import pibakeoff as pibakeoff
from anvilkit.pi import pisandbox as pisandbox

# Pinned inputs for the run-argv pin. The tag is the phase-6 sandbox tag;
# the env map is the full three-name allowlist the sandbox permits.
REPO_PATH = "/home/u/project"
TAG = "pi-sandbox"
ALLOWED_ENV = {
    "PI_GATEWAY_HOST": "llama-swap",
    "PI_GATEWAY_PORT": "8080",
    "PI_CODING_AGENT_DIR": "/home/sandbox/.pi/agent",
}

# The six runner-contract keys, pinned exactly: no more, no less.
RUNNER_RESULT_KEYS = {
    "exit_code",
    "stdout",
    "stderr",
    "wall_time_s",
    "timed_out",
    "evidence",
}


class PiRoleBoundaryPinTestCase(unittest.TestCase):
    """Shared per-test temp directory for the runner-seam pin."""

    def _tmpdir(self) -> Path:
        """A per-test temporary directory, cleaned up automatically."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)


class TestSandboxRunArgvUnchanged(PiRoleBoundaryPinTestCase):
    """Behaviour 1: the run argv ends at the tag and carries no ``pi`` token.

    Pins the append point the phase-6 driver relies on: ``run_argv`` builds
    the container command and stops at the image tag, so the driver can
    append the role argv immediately after it.
    """

    def test_run_argv_with_three_name_env_ends_at_tag_and_has_no_pi_token(self):
        # Arrange: a repo path, the sandbox tag, the full three-name env map.
        # Act.
        argv = pisandbox.run_argv(REPO_PATH, TAG, env=dict(ALLOWED_ENV))
        # Assert: a list of str tokens, the last token is the tag, and no
        # ``pi`` token appears anywhere in the vector.
        self.assertIsInstance(argv, list)
        for token in argv:
            self.assertIsInstance(token, str)
        self.assertEqual(
            TAG,
            argv[-1],
            "the run argv must end at the image tag so the driver can append "
            "the role argv after it; got tail: %r" % argv[-3:],
        )
        self.assertNotIn(
            "pi",
            argv,
            "no ``pi`` token may appear in the run argv; the pi invocation "
            "is the driver's job, not part of this argv; got: %r" % (argv,),
        )


class TestSandboxRefusesCredentialEnv(PiRoleBoundaryPinTestCase):
    """Behaviour 2: a credential-looking env name is refused, nothing returned.

    ``ANTHROPIC_API_KEY`` matches the ``KEY`` credential marker and must be
    refused with the credential reason before it can reach the container,
    where every process can read any variable passed in.
    """

    def test_run_argv_credential_env_is_refused_with_sandbox_error(self):
        # Arrange: an env map carrying a credential-looking name.
        credential_env = {"ANTHROPIC_API_KEY": "x"}
        # Act / Assert: nothing is returned; a SandboxError is raised that
        # names the credential reason and the offending env name.
        with self.assertRaises(pisandbox.SandboxError) as ctx:
            pisandbox.run_argv(REPO_PATH, TAG, env=credential_env)
        message = str(ctx.exception)
        self.assertIn(
            "ANTHROPIC_API_KEY",
            message,
            "the refusal must name the offending env name; got: %r" % message,
        )
        self.assertTrue(
            "credential" in message.lower(),
            "the refusal must state the credential reason (values passed in "
            "are readable by every process inside); got: %r" % message,
        )


class TestRunnerSeamContract(PiRoleBoundaryPinTestCase):
    """Behaviour 3: ``subprocess_runner`` honours the invocation-dict contract.

    A trivial argv (the repo's own interpreter printing a known line) is
    invoked with the documented invocation dict; the result must be exactly
    the six runner-contract keys with their documented types, and on this
    trivial success the documented success-path values hold.
    """

    def test_subprocess_runner_trivial_argv_returns_six_keys_with_documented_types(self):
        # Arrange: a trivial argv via sys.executable, and the documented
        # invocation dict.
        cwd = self._tmpdir()
        argv = [sys.executable, "-c", "print('ok')"]
        spec = {
            "argv": argv,
            "cwd": str(cwd),
            "stdin": "/dev/null",
            "timeout_s": 10.0,
        }
        # Act.
        result = pibakeoff.subprocess_runner(spec)
        # Assert: exactly the six runner-contract keys, no more, no less.
        self.assertIsInstance(result, dict)
        self.assertEqual(
            RUNNER_RESULT_KEYS,
            set(result),
            "the runner must return exactly the six runner-contract keys, "
            "no more, no less; got: %r" % (sorted(result),),
        )
        # Each key carries its documented type.
        self.assertIsInstance(result["exit_code"], int)
        self.assertNotIsInstance(result["exit_code"], bool)
        self.assertIsInstance(result["stdout"], str)
        self.assertIsInstance(result["stderr"], str)
        self.assertIsInstance(result["wall_time_s"], float)
        self.assertIs(type(result["timed_out"]), bool)
        self.assertIsInstance(result["evidence"], str)
        # The documented success path for this trivial, non-blocked run.
        self.assertEqual(
            0,
            result["exit_code"],
            "a trivial successful child must report exit code 0; got: %r"
            % result["exit_code"],
        )
        self.assertIs(
            result["timed_out"],
            False,
            "a run that completes inside the budget is not timed out; got: %r"
            % result["timed_out"],
        )
        self.assertEqual(
            "",
            result["evidence"],
            "evidence is empty unless the run was blocked; got: %r"
            % result["evidence"],
        )
        self.assertEqual(
            "ok\n",
            result["stdout"],
            "the runner must capture the child's stdout verbatim; got: %r"
            % result["stdout"],
        )
        self.assertGreaterEqual(result["wall_time_s"], 0.0)


if __name__ == "__main__":
    unittest.main()
