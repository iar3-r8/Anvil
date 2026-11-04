"""Tests for ``anvilkit.pi.pidriver`` - the absolute two-flag argv pin.

plans/pi-role-prompts.md, behaviour 18 (pidriver-forwards-both-flags):
given a sandbox run argv and a two-flag role argv, when ``pidriver``
composes them, the child argv carries ``--append-system-prompt <shared>``
then ``--append-system-prompt <role>`` in that order, exactly as
``pirole.role_argv`` would emit - both after the image tag, neither
dropped nor reordered - and the injected runner is invoked exactly once.

The existing suite (tests/test_pidriver.py) computes its expected vector
from the LIVE production functions (``pisandbox.run_argv(...) +
pirole.role_argv(definition, ...)``), so it moved with the behaviour-17
change and still pins composition and ordering, but not the ABSOLUTE
argv that reaches the child process: a driver regression that drops the
shared flag (e.g. by building its own four-key definition dict by hand)
would be invisible to those tests, because both sides of their equality
move together. This file pins the absolute vector end-to-end and pins
the two flags as an absolute pair - the shared path
(``.pi/roles/shared-agents.md``) as the value after the FIRST
``--append-system-prompt``, the role's path (``.pi/roles/<role>.md``) as
the value after the SECOND - so a missing, duplicated or reordered
shared flag fails here instead of shipping.

No test spawns ``pi`` or Docker: ``run_role`` takes process execution as
an injected runner callable (the same seam tests/test_pidriver.py uses -
one invocation dict in: ``argv``, ``cwd``, ``stdin``, ``timeout_s``,
optional ``env``; exactly six result keys out), and every test supplies
a fake that records its invocation and returns a canned result.

The ``pidriver`` import is deferred into each test: if the module is
missing, each test fails at its import step (ModuleNotFoundError)
rather than breaking collection of the whole file.
"""

import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit.pi import pirole as pirole
from anvilkit.pi import pisandbox as pisandbox

# Pinned inputs - the same values tests/test_pidriver.py uses, so the
# absolute vector here and the relative composition vector there
# describe the same run.
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

# The shared prompt layer: the chain root every role extends, the same
# file for all four roles (anvilkit/pi/pirole.py, resolve()).
SHARED_PROMPT_PATH = ".pi/roles/shared-agents.md"

# The append flag under test. The replace flag ``--system-prompt`` is a
# different token, so scanning for this one cannot match it.
FLAG = "--append-system-prompt"


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


def _resolve(role: str) -> Dict[str, str]:
    """The live role table's five-key definition for ``role``."""
    return pirole.resolve(role, CODER_MODEL_ID, FRONTIER_MODEL_ID)


def _role_prompt_path(role: str) -> str:
    """The role's own prompt path, as the live table shapes it."""
    return ".pi/roles/{}.md".format(role)


def _append_flag_positions(argv: List[str]) -> List[int]:
    """The indices of every ``--append-system-prompt`` token, in order."""
    return [i for i, token in enumerate(argv) if token == FLAG]


class RunRoleFlagsTestCase(unittest.TestCase):
    """Shared deferred import of the ``pidriver`` module, plus the
    argv-capture and pair/order helpers every test class below reuses.

    The import happens inside each test, not at module top level: if
    the module is missing, each test fails at its import step
    (ModuleNotFoundError) rather than breaking collection of the whole
    file.
    """

    def _import_pidriver(self):
        from anvilkit.pi import pidriver as pidriver

        return pidriver

    def _capture_argv(
        self,
        role: str,
        env: Optional[Dict[str, str]] = None,
        definition: Optional[Dict[str, str]] = None,
    ) -> List[str]:
        """Arrange a recording fake runner, act through ``run_role``,
        and return the single recorded argv.

        ``definition`` defaults to the live table's definition for
        ``role``; a test that injects a mangled definition passes it
        explicitly.
        """
        pidriver = self._import_pidriver()
        resolved = definition if definition is not None else _resolve(role)
        fake = FakeRunner()
        kwargs: Dict[str, Any] = {}
        if env is not None:
            kwargs["env"] = env
        pidriver.run_role(
            definition=resolved,
            repo_path=REPO_PATH,
            tag=TAG,
            session_id=SESSION_ID,
            task=TASK,
            runner=fake,
            **kwargs,
        )
        # The existing contract: exactly one runner invocation, so a
        # zero-invocation drift cannot pass a pin silently.
        self.assertEqual(
            1,
            len(fake.calls),
            "the role %r must reach the runner exactly once; got %d "
            "calls" % (role, len(fake.calls)),
        )
        argv = fake.calls[0]["argv"]
        self.assertIsInstance(
            argv,
            list,
            "argv must be a list of tokens for subprocess, never a "
            "string; got: %r" % (argv,),
        )
        for token in argv:
            self.assertIsInstance(token, str)
        return argv

    def _assert_pair_and_order(self, role: str, argv: List[str]) -> None:
        """Assert the two ``--append-system-prompt`` tokens are a
        correctly ordered absolute pair: the value after the FIRST is
        the shared chain root, the value after the SECOND is the role's
        own path, and both flags land after the image tag.

        This is the absolute pin the relative composition tests lack:
        even a driver that rebuilt its definition dict by hand - and so
        kept a plausible token order around the missing flag - fails
        here on the shared value or the count.
        """
        positions = _append_flag_positions(argv)
        self.assertEqual(
            2,
            len(positions),
            "the role %r's child argv must carry exactly two "
            "--append-system-prompt flags (the shared layer and the "
            "role layer); got %d; argv: %r" % (role, len(positions), argv),
        )
        first, second = positions
        self.assertLess(
            first,
            second,
            "the shared flag must precede the role flag, so the role "
            "layer lands last; got positions %r; argv: %r"
            % ((first, second), argv),
        )
        self.assertEqual(
            SHARED_PROMPT_PATH,
            argv[first + 1],
            "the value after the FIRST --append-system-prompt must be "
            "the shared chain root %r; got: %r"
            % (SHARED_PROMPT_PATH, argv[first + 1]),
        )
        self.assertEqual(
            _role_prompt_path(role),
            argv[second + 1],
            "the value after the SECOND --append-system-prompt must be "
            "the role %r's own path %r; got: %r"
            % (role, _role_prompt_path(role), argv[second + 1]),
        )
        # Both flags belong to the role argv, which is appended after
        # the container argv that ends at the image tag.
        tag_index = argv.index(TAG)
        self.assertGreater(
            first,
            tag_index,
            "both append flags must land after the image tag %r; the "
            "first flag sits at index %d, the tag at %d; argv: %r"
            % (TAG, first, tag_index, argv),
        )


class TestAbsoluteVectorCoder(RunRoleFlagsTestCase):
    """The core pin: the coder's captured child argv, token by token, is
    the absolute composition ``pisandbox.run_argv(...) +
    pirole.role_argv(pirole.resolve("coder"), ...)``, and within it the
    two append flags are the absolute shared-before-role pair."""

    def test_run_role_coder_argv_is_absolute_run_argv_plus_role_argv_with_shared_pair(self):
        # Arrange: the expected vector, computed from the live
        # production functions on both sides - the container command
        # with the full env map, then the two-flag role argv built from
        # a FRESH resolve, so a driver that built its own definition
        # dict by hand cannot drift the two sides into agreement.
        expected = (
            pisandbox.run_argv(REPO_PATH, TAG, env=dict(ENV))
            + pirole.role_argv(_resolve("coder"), SESSION_ID, TASK)
        )
        # Anti-vacuity: the expected vector itself carries the
        # two-flag pair with distinct values, so the pair check below
        # is not asserting nothing, and the replace flag is absent
        # from the vector the role argv is pinned to emit.
        expected_positions = _append_flag_positions(expected)
        self.assertEqual(
            2,
            len(expected_positions),
            "the live role argv must carry exactly two append flags, "
            "or the pair pin would have nothing to check; argv: %r"
            % (expected,),
        )
        self.assertNotEqual(
            expected[expected_positions[0] + 1],
            expected[expected_positions[1] + 1],
            "the shared and role prompt paths must differ, or a "
            "dropped shared flag would be indistinguishable; argv: %r"
            % (expected,),
        )
        self.assertNotIn(
            "--system-prompt",
            expected,
            "the replace flag --system-prompt is never emitted; argv: "
            "%r" % (expected,),
        )
        # Act: the same role, session id and task the existing suite
        # uses, through the injected-runner seam.
        argv = self._capture_argv("coder", env=dict(ENV))
        # Assert: absolute token-for-token equality - this is what the
        # relative composition tests cannot catch when both sides of
        # their expected value move together.
        self.assertEqual(
            expected,
            argv,
            "argv must be exactly the run_argv container command "
            "followed by the role_argv pi invocation, token for "
            "token; got: %r" % (argv,),
        )
        # Assert: the absolute pair - shared immediately before role,
        # both after the image tag.
        self._assert_pair_and_order("coder", argv)


class TestFlagOrderCoder(RunRoleFlagsTestCase):
    """The order pin: of the two ``--append-system-prompt`` occurrences
    in the coder's child argv, the FIRST is the shared layer and the
    SECOND is the role layer - the role layer lands last."""

    def test_run_role_coder_first_append_flag_is_shared_second_is_role(self):
        # Act: no env mapping, so the container argv is its shorter
        # form and the role argv - where the flags live - is isolated.
        argv = self._capture_argv("coder")
        # Assert: exactly two occurrences, first shared then role.
        positions = _append_flag_positions(argv)
        self.assertEqual(
            2,
            len(positions),
            "exactly two --append-system-prompt flags must appear, "
            "first the shared layer then the role layer; got %d; argv: "
            "%r" % (len(positions), argv),
        )
        first, second = positions
        self.assertLess(
            first,
            second,
            "the shared flag must occur before the role flag; got "
            "positions %r; argv: %r" % ((first, second), argv),
        )
        self.assertEqual(
            SHARED_PROMPT_PATH,
            argv[first + 1],
            "the value after the FIRST --append-system-prompt must be "
            "the shared chain root %r, never the role's path; got: %r"
            % (SHARED_PROMPT_PATH, argv[first + 1]),
        )
        self.assertEqual(
            _role_prompt_path("coder"),
            argv[second + 1],
            "the value after the SECOND --append-system-prompt must be "
            "the coder's own path %r, never the shared path; got: %r"
            % (_role_prompt_path("coder"), argv[second + 1]),
        )
        # Both flags sit in the role argv, after the image tag.
        tag_index = argv.index(TAG)
        self.assertGreater(
            first,
            tag_index,
            "both append flags must appear after the image tag %r; the "
            "first sits at index %d, the tag at %d; argv: %r"
            % (TAG, first, tag_index, argv),
        )


class TestAbsoluteVectorOtherRoles(RunRoleFlagsTestCase):
    """The pair+order check repeated for two further roles, so a
    role-specific special case in the driver - one role hardwired to a
    hand-built definition, the rest composed through ``role_argv`` - is
    caught, not just the coder path.

    The two roles are named in the test names per the plan: architect
    (the only frontier-tier role, so a tier-keyed special case lands
    there) and tester (a local-tier role distinct from coder).
    """

    def test_run_role_architect_argv_is_absolute_run_argv_plus_role_argv_with_shared_pair(self):
        # Arrange: the live frontier-tier definition, expected from the
        # live functions on both sides.
        expected = (
            pisandbox.run_argv(REPO_PATH, TAG)
            + pirole.role_argv(_resolve("architect"), SESSION_ID, TASK)
        )
        self.assertEqual(
            2,
            len(_append_flag_positions(expected)),
            "the live architect role argv must carry the two-flag "
            "pair; argv: %r" % (expected,),
        )
        # Act.
        argv = self._capture_argv("architect")
        # Assert: absolute equality, then the absolute pair with the
        # architect's own path as the role layer.
        self.assertEqual(
            expected,
            argv,
            "the architect's argv must be exactly the run_argv "
            "container command followed by the role_argv pi "
            "invocation, token for token; got: %r" % (argv,),
        )
        self._assert_pair_and_order("architect", argv)

    def test_run_role_tester_argv_is_absolute_run_argv_plus_role_argv_with_shared_pair(self):
        # Arrange: the live local-tier definition, expected from the
        # live functions on both sides.
        expected = (
            pisandbox.run_argv(REPO_PATH, TAG)
            + pirole.role_argv(_resolve("tester"), SESSION_ID, TASK)
        )
        self.assertEqual(
            2,
            len(_append_flag_positions(expected)),
            "the live tester role argv must carry the two-flag pair; "
            "argv: %r" % (expected,),
        )
        # Act.
        argv = self._capture_argv("tester")
        # Assert: absolute equality, then the absolute pair with the
        # tester's own path as the role layer.
        self.assertEqual(
            expected,
            argv,
            "the tester's argv must be exactly the run_argv container "
            "command followed by the role_argv pi invocation, token "
            "for token; got: %r" % (argv,),
        )
        self._assert_pair_and_order("tester", argv)


class TestDriverErrorInheritance(RunRoleFlagsTestCase):
    """A definition-level failure surfaces as ``RoleError`` from the
    driver call.

    The driver's public surface makes this reachable without any fake
    beyond what the seam already carries: ``run_role`` takes the role
    definition as a parameter, so a definition whose
    ``shared_prompt_path`` is empty goes into the call and must come
    out as the ``RoleError`` that ``pirole.role_argv`` raises -
    inherited, not re-wrapped as ``DriverError`` - before any runner
    invocation, since the role argv is built before the runner runs.
    """

    def test_run_role_definition_with_empty_shared_path_raises_role_error(self):
        # Arrange: the live definition with its shared path emptied -
        # the exact shape a driver-internal hand-built four-key dict
        # would feed ``role_argv``.
        definition = _resolve("coder")
        definition["shared_prompt_path"] = ""
        self.assertEqual(
            "",
            definition["shared_prompt_path"],
            "the scenario must carry an empty shared path, or the "
            "inheritance rule would be untested; got: %r"
            % definition.get("shared_prompt_path"),
        )
        fake = FakeRunner()
        pidriver = self._import_pidriver()
        # Act / Assert: nothing is returned - RoleError is raised.
        with self.assertRaises(pirole.RoleError) as ctx:
            pidriver.run_role(
                definition=definition,
                repo_path=REPO_PATH,
                tag=TAG,
                session_id=SESSION_ID,
                task=TASK,
                runner=fake,
            )
        self.assertNotIsInstance(
            ctx.exception,
            pidriver.DriverError,
            "a definition-level failure is a role-definition failure, "
            "not a container-start failure, so the error must not be "
            "a DriverError; got: %r" % type(ctx.exception).__name__,
        )
        self.assertIn(
            "shared_prompt_path",
            str(ctx.exception),
            "the RoleError message must name the offending field; "
            "got: %r" % str(ctx.exception),
        )
        # The failure is decided before the container starts: the
        # runner is invoked zero times.
        self.assertEqual(
            0,
            len(fake.calls),
            "an empty shared path must fail before any container "
            "start, so the runner must be invoked zero times; got %d "
            "calls" % len(fake.calls),
        )


if __name__ == "__main__":
    unittest.main()
