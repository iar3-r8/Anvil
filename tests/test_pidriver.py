"""Tests for ``anvilkit.pi.pidriver`` - the single-role run driver.

``plans/pi-phase6-single-role.md``, behaviour 9: the driver composes the
container argv with the role argv and invokes the injected runner exactly
once. No test spawns ``pi`` or Docker: ``run_role`` takes process
execution as an **injected runner callable** (the same seam
``anvilkit.pi.pibakeoff`` and ``anvilkit.pi.piapproval`` use - one
invocation dict in: ``argv``, ``cwd``, ``stdin``, ``timeout_s``, optional
``env``; exactly six result keys out: ``exit_code``, ``stdout``,
``stderr``, ``wall_time_s``, ``timed_out``, ``evidence``), and every test
supplies a fake that records its invocation and returns a canned result.

Pinned signature::

    run_role(definition, repo_path, tag, session_id, task, runner,
             env=None, timeout_s=<driver default>)

- ``definition``: the role definition dict from ``pirole.resolve`` - the
  givens for this behaviour name no model ids, so the driver takes the
  already-resolved definition and never calls ``resolve`` itself;
- ``repo_path`` / ``tag`` / ``env``: handed to ``pisandbox.run_argv``
  verbatim (``env`` optional, mirroring ``run_argv``'s ``Optional``);
- ``session_id`` / ``task``: handed to ``pirole.role_argv`` verbatim;
- ``runner``: the injected process-execution seam, invoked exactly once;
- ``timeout_s``: the wall-clock budget handed to the runner; the driver
  owns the default, the tests never pin a specific value - only that the
  recorded invocation carries a positive float;
- the invocation's ``cwd`` value is not pinned by the plan (``docker run``
  does not depend on it); the tests pin its presence and string type only.

The ``pidriver`` import is deferred into each test so that, while
``anvilkit/pi/pidriver.py`` does not yet exist, the tests fail at the
import step (ModuleNotFoundError) instead of breaking collection of the
module.

Container-start-failure detection, stdout capture and the exit-status
recording are later behaviours in the same plan and are not asserted here.
"""

import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit.pi import pirole as pirole
from anvilkit.pi import pisandbox as pisandbox

# Pinned inputs. The tag is the phase-6 sandbox tag; the env map is the
# full three-name allowlist the sandbox permits; the session id follows
# the ``{run_id}-{role}`` shape the plan's assumptions pin.
REPO_PATH = "/home/u/project"
TAG = "pi-sandbox"
SESSION_ID = "20261027T140530Z-coder"
TASK = "Refactor the adder"
CODER_MODEL_ID = "llama-swapped-coder-72b"
FRONTIER_MODEL_ID = "claude-sonnet-4-5"
ENV = {
    "PI_GATEWAY_HOST": "llama-swap",
    "PI_GATEWAY_PORT": "8080",
    "PI_CODING_AGENT_DIR": "/home/sandbox/.pi/agent",
}


class FakeRunner:
    """A runner that records every invocation and returns a canned result.

    The record is a copy, so the driver cannot mutate what the test
    asserts on; the canned result is the documented six-key runner
    contract, so a driver that passes it through is exercised on a
    shape the production runner really returns.
    """

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._result: Dict[str, Any] = {
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "wall_time_s": 0.25,
            "timed_out": False,
            "evidence": "",
        }

    def __call__(self, invocation: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append(dict(invocation))
        return dict(self._result)


def _coder_definition() -> Dict[str, str]:
    """The local-tier role definition the composition tests build on."""
    return pirole.resolve("coder", CODER_MODEL_ID, FRONTIER_MODEL_ID)


class RunRoleTestCase(unittest.TestCase):
    """Shared deferred import of the not-yet-existing ``pidriver`` module.

    The import happens inside each test, not at module top level, so that
    while ``anvilkit/pi/pidriver.py`` does not yet exist the tests fail
    at the import step (ModuleNotFoundError) instead of breaking
    collection.
    """

    def _import_pidriver(self):
        from anvilkit.pi import pidriver as pidriver

        return pidriver

    def _check_invocation_seam(self, invocation: Dict[str, Any]) -> None:
        """Assert the invocation carries the documented runner-seam keys.

        ``argv`` is asserted by the caller; this pins the rest of the
        invocation dict: ``cwd`` present as a string (its value is not
        pinned by the plan), ``stdin`` the seam's ``/dev/null``, and
        ``timeout_s`` a positive float.
        """
        self.assertIsInstance(invocation, dict)
        for key in ("argv", "cwd", "stdin", "timeout_s"):
            self.assertIn(
                key,
                invocation,
                "the invocation dict must carry %r per the runner seam; "
                "got keys: %r" % (key, sorted(invocation)),
            )
        self.assertIsInstance(
            invocation["argv"],
            list,
            "argv must be a list of tokens for subprocess, never a string; "
            "got: %r" % (invocation["argv"],),
        )
        for token in invocation["argv"]:
            self.assertIsInstance(token, str)
        self.assertIsInstance(
            invocation["cwd"],
            str,
            "cwd must be a string; got: %r" % (invocation["cwd"],),
        )
        self.assertEqual(
            "/dev/null",
            invocation["stdin"],
            "the runner seam reads stdin from /dev/null; got: %r"
            % (invocation["stdin"],),
        )
        self.assertIsInstance(
            invocation["timeout_s"],
            float,
            "timeout_s must be a float wall-clock budget; got: %r"
            % (invocation["timeout_s"],),
        )
        self.assertGreater(
            invocation["timeout_s"],
            0.0,
            "timeout_s must be a positive budget; got: %r"
            % (invocation["timeout_s"],),
        )


class TestRunRoleWithEnv(RunRoleTestCase):
    """The driver composes the container argv with the role argv.

    Given a role definition, repo path, tag, the full three-name env map,
    a session id and a task, ``run_role`` invokes the injected runner
    exactly once, and the recorded ``argv`` is exactly
    ``pisandbox.run_argv(...) + pirole.role_argv(...)`` - the container
    command up to the image tag, then the pi invocation.
    """

    def test_run_role_with_env_invokes_runner_exactly_once(self):
        # Arrange: the definition, the full env map, a fake runner.
        pidriver = self._import_pidriver()
        definition = _coder_definition()
        fake = FakeRunner()
        # Act.
        pidriver.run_role(
            definition=definition,
            repo_path=REPO_PATH,
            tag=TAG,
            session_id=SESSION_ID,
            task=TASK,
            runner=fake,
            env=dict(ENV),
        )
        # Assert: exactly one runner invocation.
        self.assertEqual(
            1,
            len(fake.calls),
            "the driver must invoke the runner exactly once; got %d calls"
            % len(fake.calls),
        )

    def test_run_role_with_env_argv_is_container_argv_plus_role_argv(self):
        # Arrange.
        pidriver = self._import_pidriver()
        definition = _coder_definition()
        fake = FakeRunner()
        # Act.
        pidriver.run_role(
            definition=definition,
            repo_path=REPO_PATH,
            tag=TAG,
            session_id=SESSION_ID,
            task=TASK,
            runner=fake,
            env=dict(ENV),
        )
        # Assert: the recorded argv is exactly the container argv
        # followed by the role argv, token for token.
        self.assertEqual(1, len(fake.calls))
        invocation = fake.calls[0]
        expected = (
            pisandbox.run_argv(REPO_PATH, TAG, env=dict(ENV))
            + pirole.role_argv(definition, SESSION_ID, TASK)
        )
        self.assertEqual(
            expected,
            invocation["argv"],
            "argv must be the run_argv container command followed by the "
            "role_argv pi invocation; got: %r" % (invocation["argv"],),
        )
        self._check_invocation_seam(invocation)

    def test_run_role_composed_argv_carries_tag_at_junction_before_pi(self):
        # Arrange.
        pidriver = self._import_pidriver()
        definition = _coder_definition()
        fake = FakeRunner()
        # Act.
        pidriver.run_role(
            definition=definition,
            repo_path=REPO_PATH,
            tag=TAG,
            session_id=SESSION_ID,
            task=TASK,
            runner=fake,
            env=dict(ENV),
        )
        # Assert: the junction between the two argvs is the image tag -
        # the token immediately before ``pi`` (the first role-argv token,
        # and the only ``pi`` token, since the container argv carries
        # none) is the tag.
        self.assertEqual(1, len(fake.calls))
        argv: List[str] = fake.calls[0]["argv"]
        self.assertEqual(
            1,
            argv.count("pi"),
            "exactly one 'pi' token may appear, at the head of the role "
            "argv; got: %r" % (argv,),
        )
        junction = argv.index("pi")
        self.assertGreater(
            junction,
            0,
            "the role argv must be appended after a non-empty container "
            "argv; got: %r" % (argv,),
        )
        self.assertEqual(
            TAG,
            argv[junction - 1],
            "the image tag must sit at the junction, immediately before "
            "the pi invocation; got: %r" % (argv[max(0, junction - 3) : junction + 2],),
        )


class TestRunRoleWithoutEnv(RunRoleTestCase):
    """The composition holds when no env mapping is passed in.

    ``run_argv`` with no env carries no ``-e`` tokens, so the expected
    composition is that shorter container argv plus the same role argv.
    """

    def test_run_role_without_env_invokes_runner_exactly_once(self):
        # Arrange.
        pidriver = self._import_pidriver()
        definition = _coder_definition()
        fake = FakeRunner()
        # Act: no env mapping is passed at all.
        pidriver.run_role(
            definition=definition,
            repo_path=REPO_PATH,
            tag=TAG,
            session_id=SESSION_ID,
            task=TASK,
            runner=fake,
        )
        # Assert.
        self.assertEqual(
            1,
            len(fake.calls),
            "the driver must invoke the runner exactly once; got %d calls"
            % len(fake.calls),
        )

    def test_run_role_without_env_argv_is_container_argv_plus_role_argv(self):
        # Arrange.
        pidriver = self._import_pidriver()
        definition = _coder_definition()
        fake = FakeRunner()
        # Act.
        pidriver.run_role(
            definition=definition,
            repo_path=REPO_PATH,
            tag=TAG,
            session_id=SESSION_ID,
            task=TASK,
            runner=fake,
        )
        # Assert.
        self.assertEqual(1, len(fake.calls))
        invocation = fake.calls[0]
        expected = (
            pisandbox.run_argv(REPO_PATH, TAG)
            + pirole.role_argv(definition, SESSION_ID, TASK)
        )
        self.assertEqual(
            expected,
            invocation["argv"],
            "argv must be the run_argv container command (no -e tokens "
            "when no env is passed) followed by the role_argv pi "
            "invocation; got: %r" % (invocation["argv"],),
        )
        self._check_invocation_seam(invocation)
        for token in invocation["argv"]:
            self.assertNotEqual(
                "-e",
                token,
                "no env mapping was passed, so no -e token may appear; "
                "got: %r" % (invocation["argv"],),
            )
