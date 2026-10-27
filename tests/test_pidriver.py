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
- ``timeout_s``: the wall-clock budget handed to the runner; tier-aware
  since behaviour 16 (review comment 2) - an explicit caller budget
  always wins, a local-tier default is unbounded (``None``) and a
  frontier-tier default is a finite cost kill-switch; see
  ``_check_invocation_seam``;
- the invocation's ``cwd`` value is not pinned by the plan (``docker run``
  does not depend on it); the tests pin its presence and string type only.

The ``pidriver`` import is deferred into each test so that, while
``anvilkit/pi/pidriver.py`` does not yet exist, the tests fail at the
import step (ModuleNotFoundError) instead of breaking collection of the
module.

Container-start-failure detection and the exit-status recording are later
behaviours in the same plan and are not asserted here; the driver's
whole-stream stdout capture is asserted here as well.
"""

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def _architect_definition() -> Dict[str, str]:
    """The frontier-tier role definition the tier-timeout tests build on."""
    return pirole.resolve("architect", CODER_MODEL_ID, FRONTIER_MODEL_ID)


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

    def _check_invocation_seam(
        self,
        invocation: Dict[str, Any],
        definition: Dict[str, str],
        caller_timeout_s: Optional[float] = None,
    ) -> None:
        """Assert the invocation carries the documented runner-seam keys.

        ``argv`` is asserted by the caller; this pins the rest of the
        invocation dict: ``cwd`` present as a string (its value is not
        pinned by the plan), ``stdin`` the seam's ``/dev/null``, and
        ``timeout_s`` tier-aware - behaviour 16 supersedes the single
        positive-float pin that assumed one 900.0 default:

        - an explicit caller budget always wins: the invocation carries
          that exact positive float, whichever tier the definition is;
        - a local-tier definition (coder/tester/docs) with no caller
          budget runs unbounded: the ``timeout_s`` key is present with
          the value ``None`` - the key must still be present, because
          the runner treats an absent key as a misuse and raises before
          spawn, so ``None`` is distinguishable from absence;
        - a frontier-tier definition (architect) with no caller budget
          gets a finite cost kill-switch: a positive finite float.
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
        if caller_timeout_s is not None:
            self.assertEqual(
                float(caller_timeout_s),
                invocation["timeout_s"],
                "an explicit caller budget always overrides the tier "
                "default; got: %r" % (invocation["timeout_s"],),
            )
            return
        if definition["tier"] == "local":
            self.assertIs(
                None,
                invocation["timeout_s"],
                "a local-tier run with no caller budget is unbounded - "
                "timeout_s must be present with value None (a long "
                "local-model turn must never be killed for thinking); "
                "got: %r" % (invocation["timeout_s"],),
            )
        else:
            self.assertIsInstance(
                invocation["timeout_s"],
                float,
                "a frontier-tier run with no caller budget must carry a "
                "finite cost kill-switch (a positive float); got: %r"
                % (invocation["timeout_s"],),
            )
            self.assertGreater(
                invocation["timeout_s"],
                0.0,
                "the frontier kill-switch must be a positive budget; got: "
                "%r" % (invocation["timeout_s"],),
            )
            self.assertTrue(
                math.isfinite(invocation["timeout_s"]),
                "the frontier kill-switch must be finite - a frontier run "
                "must be cut off when it loops; got: %r"
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
        # followed by the role argv, token for token. The definition is
        # local-tier and no caller budget is passed, so the seam pin
        # expects the unbounded (None) timeout.
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
        self._check_invocation_seam(invocation, definition)

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
        # Assert: local-tier definition, no caller budget, so the seam
        # pin expects the unbounded (None) timeout.
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
        self._check_invocation_seam(invocation, definition)
        for token in invocation["argv"]:
            self.assertNotEqual(
                "-e",
                token,
                "no env mapping was passed, so no -e token may appear; "
                "got: %r" % (invocation["argv"],),
            )


# The canned capture stream: 5000 JSONL lines, then one non-JSON final
# line with no trailing LF. The exact newline count and the unterminated
# last line are what the whole-capture pin asserts on: a driver that
# strips the final line, splits the stream, or re-encodes the bytes
# changes at least one of them.
JSONL_LINE_COUNT = 5000
FINAL_NON_JSON_LINE = "plain text, not json"


def _whole_jsonl_stream() -> str:
    """The 5001-line stream the capture tests hand to the fake runner.

    5000 JSONL lines (built with ``json.dumps`` so the JSON is valid by
    construction) followed by one deliberately non-JSON final line. The
    lines are joined with LF and no trailing LF is appended, so the last
    line is unterminated exactly as a drained pipe can end.
    """
    lines: List[str] = [
        json.dumps({"type": "message", "index": i})
        for i in range(JSONL_LINE_COUNT)
    ]
    lines.append(FINAL_NON_JSON_LINE)
    return "\n".join(lines)


class TestRunRoleCapturesStdoutWhole(RunRoleTestCase):
    """The driver captures the runner's stdout whole.

    The runner's six-key result dict is the driver's return value: the
    captured stdout passes through byte-for-byte, unsplit and unparsed.
    The tests assert on the captured bytes and on the result dict's
    shape; they do not interpret the stream, since interpreting the
    JSONL is a later phase of the plan.
    """

    def _invoke_with_stdout(self, stdout: str, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Arrange an injected runner returning the given stdout, act, and
        return the driver's result."""
        pidriver = self._import_pidriver()
        fake = FakeRunner()
        fake._result["stdout"] = stdout
        kwargs: Dict[str, Any] = {}
        if env is not None:
            kwargs["env"] = env
        return pidriver.run_role(
            definition=_coder_definition(),
            repo_path=REPO_PATH,
            tag=TAG,
            session_id=SESSION_ID,
            task=TASK,
            runner=fake,
            **kwargs,
        )

    def test_run_role_with_whole_jsonl_stdout_is_byte_identical(self):
        # Arrange: a runner whose canned result carries the whole stream.
        stream = _whole_jsonl_stream()
        fake = FakeRunner()
        fake._result["stdout"] = stream
        # Act.
        result = self._invoke_with_stdout(stream)
        # Assert: the result carries the runner's stdout byte-for-byte -
        # equal as strings, and even the same object, so no copy, strip,
        # split or re-encode happened on the way through the driver.
        self.assertEqual(
            stream,
            result["stdout"],
            "the driver's result must carry the runner's stdout "
            "byte-for-byte; first and last bytes: %r ... %r"
            % (result["stdout"][:60], result["stdout"][-60:]),
        )
        self.assertIs(
            fake._result["stdout"],
            result["stdout"],
            "the driver must pass the runner's stdout object through "
            "without copying or re-encoding it",
        )

    def test_run_role_with_whole_jsonl_stdout_is_unsplit_and_unparsed(self):
        # Arrange / Act: the same whole stream through the driver.
        stream = _whole_jsonl_stream()
        result = self._invoke_with_stdout(stream, env=dict(ENV))
        # Assert: the capture is still one string (never a list of lines),
        # with exactly the 5000 newlines the 5001-line stream carries, the
        # final line present and unterminated, and the non-JSON line
        # verbatim - the byte facts that change if the driver strips,
        # splits or re-encodes.
        self.assertIsInstance(
            result["stdout"],
            str,
            "the captured stdout must be one string, never split into a "
            "list of lines; got: %r" % type(result["stdout"]).__name__,
        )
        self.assertEqual(
            JSONL_LINE_COUNT,
            result["stdout"].count("\n"),
            "the stream's 5001 lines carry exactly 5000 newlines (the "
            "final line has no trailing LF); got %d newlines"
            % result["stdout"].count("\n"),
        )
        self.assertEqual(
            JSONL_LINE_COUNT + 1,
            len(result["stdout"].split("\n")),
            "splitting the capture on LF must yield 5001 lines; got %d"
            % len(result["stdout"].split("\n")),
        )
        self.assertTrue(
            result["stdout"].endswith(FINAL_NON_JSON_LINE),
            "the final (non-JSON) line must survive at the end of the "
            "capture; got: %r" % result["stdout"][-60:],
        )
        self.assertFalse(
            result["stdout"].endswith("\n"),
            "the runner's stream has no trailing LF, and the driver must "
            "not add or strip one",
        )

    def test_run_role_result_carries_all_six_runner_keys_verbatim(self):
        # Arrange: the canned result carries non-default values in every
        # key except stdout, so any key the driver fails to pass through
        # shows up as a mismatch.
        pidriver = self._import_pidriver()
        fake = FakeRunner()
        fake._result = {
            "exit_code": 3,
            "stdout": _whole_jsonl_stream(),
            "stderr": "a note on stderr",
            "wall_time_s": 12.5,
            "timed_out": False,
            "evidence": "",
        }
        # Act.
        result = pidriver.run_role(
            definition=_coder_definition(),
            repo_path=REPO_PATH,
            tag=TAG,
            session_id=SESSION_ID,
            task=TASK,
            runner=fake,
            env=dict(ENV),
        )
        # Assert: the six-key dict comes back whole, key for key.
        self.assertEqual(
            set(fake._result),
            set(result),
            "the result must carry exactly the runner's six keys; got: %r"
            % sorted(result),
        )
        for key, value in fake._result.items():
            self.assertEqual(
                value,
                result[key],
                "result key %r must carry the runner's value verbatim; "
                "got: %r" % (key, result[key]),
            )

    def test_run_role_with_mangled_runner_stdout_tracks_the_runner(self):
        # Arrange: the runner's stdout is the stream with its final line
        # stripped - the one mangling mode the byte-identity pin must
        # catch, because it changes both the newline count and the tail.
        stream = _whole_jsonl_stream()
        mangled = stream.rsplit("\n", 1)[0]
        # Anti-vacuity first: each of the three mangling modes the pin
        # guards against is distinguishable from the whole stream, so an
        # identity assertion on it cannot pass silently for a mangled
        # capture.
        self.assertNotEqual(
            mangled,
            stream,
            "stripping the final line must change the bytes, or the "
            "byte-identity pin would be vacuous",
        )
        self.assertNotEqual(
            stream + "\n",
            stream,
            "re-encoding with a trailing LF must change the bytes, or "
            "the byte-identity pin would be vacuous",
        )
        self.assertNotIsInstance(
            stream.split("\n"),
            str,
            "splitting the stream yields a list, not a string, so the "
            "unsplit assertion cannot be vacuous",
        )
        # Act: the mangled runner output goes through the driver.
        result = self._invoke_with_stdout(mangled)
        # Assert: the pin tracks the runner's actual output, not a
        # constant - the mangled bytes come back verbatim, which is what
        # makes a driver that re-derived, repaired or normalised the
        # stream fail the byte-identity assertion in this class.
        self.assertEqual(
            mangled,
            result["stdout"],
            "the driver must return the runner's stdout as it is, "
            "mangled or not; got: %r ... %r"
            % (result["stdout"][:60], result["stdout"][-60:]),
        )
        self.assertFalse(
            result["stdout"].endswith(FINAL_NON_JSON_LINE),
            "the final line was stripped by the runner in this test, and "
            "the driver must not resurrect it",
        )


# The canned six-key runner results for the exit-status scenarios: a
# failed agent turn (exit 1 with a non-empty stream), a clean run (exit
# 0), and a run the driver killed at the deadline (``timed_out`` True and
# ``exit_code`` -9, the subprocess negative-signal form for the SIGKILL
# the runner's kill path reaps - anvilkit/pi/pibakeoff.py:494). Each
# scenario's (exit_code, timed_out) pair is pairwise distinct from the
# other two, which is what makes the scenario tests below able to catch
# a driver that drops one of the fields, hardcodes a constant for it, or
# conflates the agent's exit with its own status.
NONZERO_EXIT_RESULT: Dict[str, Any] = {
    "exit_code": 1,
    "stdout": '{"type": "message", "text": "agent turn finished with a failure"}\n',
    "stderr": "a diagnostic on stderr",
    "wall_time_s": 3.5,
    "timed_out": False,
    "evidence": "",
}
ZERO_EXIT_RESULT: Dict[str, Any] = {
    "exit_code": 0,
    "stdout": '{"type": "message", "text": "agent turn finished cleanly"}\n',
    "stderr": "",
    "wall_time_s": 2.0,
    "timed_out": False,
    "evidence": "",
}
TIMED_OUT_RESULT: Dict[str, Any] = {
    "exit_code": -9,
    "stdout": '{"type": "message", "text": "partial work before the kill"}',
    "stderr": "",
    "wall_time_s": 30.0,
    "timed_out": True,
    "evidence": "killed after the 30.0s budget",
}


class TestRunRoleRecordsExitStatus(RunRoleTestCase):
    """The driver records the agent's exit status as data, separately.

    The runner's result is the driver's return value: ``exit_code`` and
    ``timed_out`` pass through exactly as the runner reported them, the
    agent's own outcome (the captured stream) stays in its own field, and
    a non-zero agent exit with captured output is a result to be
    returned, never an exception to be raised - a non-zero agent exit is
    data, not a driver failure.
    """

    def _invoke(self, runner_result: Dict[str, Any]) -> Dict[str, Any]:
        """Arrange an injected runner returning the canned six-key result,
        act, and return the driver's result."""
        pidriver = self._import_pidriver()
        fake = FakeRunner()
        fake._result = dict(runner_result)
        return pidriver.run_role(
            definition=_coder_definition(),
            repo_path=REPO_PATH,
            tag=TAG,
            session_id=SESSION_ID,
            task=TASK,
            runner=fake,
        )

    def _assert_pairwise_distinct(
        self, scenario: Dict[str, Any], *others: Dict[str, Any]
    ) -> None:
        """Anti-vacuity: the scenario's (exit_code, timed_out) pair must
        differ from each other scenario's, so a driver that drops one of
        the two fields or hardcodes a constant for it cannot pass every
        scenario test."""
        pair = (scenario["exit_code"], scenario["timed_out"])
        for other in others:
            self.assertNotEqual(
                (other["exit_code"], other["timed_out"]),
                pair,
                "the scenarios' (exit_code, timed_out) pairs must be "
                "pairwise distinct, or the exit-status pin could pass a "
                "driver that drops or hardcodes one of the two fields",
            )

    def test_run_role_with_nonzero_exit_and_output_returns_result_not_raised(self):
        # Arrange: the agent's turn exits 1 with a non-empty stream.
        self._assert_pairwise_distinct(
            NONZERO_EXIT_RESULT, ZERO_EXIT_RESULT, TIMED_OUT_RESULT
        )
        self.assertNotEqual(
            0,
            NONZERO_EXIT_RESULT["exit_code"],
            "the scenario must be a genuinely non-zero exit, or a driver "
            "that raises on non-zero exit would never be exercised",
        )
        self.assertTrue(
            NONZERO_EXIT_RESULT["stdout"],
            "the scenario must carry output alongside the non-zero exit, "
            "or the reported-not-raised rule would be untested",
        )
        # Act: a driver that treats a non-zero agent exit as its own
        # failure raises here and the test fails; a compliant driver
        # returns the result dict.
        result = self._invoke(NONZERO_EXIT_RESULT)
        # Assert: a dict comes back (nothing was raised) carrying the
        # agent's exit status and its own outcome as separate fields.
        self.assertIsInstance(
            result,
            dict,
            "a non-zero agent exit with output must be reported as a "
            "result dict, never raised; got: %r" % type(result).__name__,
        )
        self.assertEqual(
            NONZERO_EXIT_RESULT["exit_code"],
            result["exit_code"],
            "the result must carry the agent's own exit code verbatim, "
            "not a driver-normalised value; got: %r" % result.get("exit_code"),
        )
        self.assertIs(
            False,
            result["timed_out"],
            "the run did not time out, so the result's timed_out field "
            "must be False; got: %r" % result.get("timed_out"),
        )
        self.assertIs(
            NONZERO_EXIT_RESULT["stdout"],
            result["stdout"],
            "the agent's own outcome must pass through in its own "
            "stdout field, uncorrupted by the exit status",
        )

    def test_run_role_with_zero_exit_returns_zero_exit_code_not_timed_out(self):
        # Arrange: a clean agent turn.
        self._assert_pairwise_distinct(
            ZERO_EXIT_RESULT, NONZERO_EXIT_RESULT, TIMED_OUT_RESULT
        )
        self.assertEqual(
            0,
            ZERO_EXIT_RESULT["exit_code"],
            "the scenario must be a zero exit, or the scenario pair would "
            "not be distinct from the non-zero one",
        )
        # Act.
        result = self._invoke(ZERO_EXIT_RESULT)
        # Assert: the zero exit comes through as data in its own field.
        self.assertEqual(
            0,
            result["exit_code"],
            "the result must carry the runner's zero exit code verbatim; "
            "got: %r" % result.get("exit_code"),
        )
        self.assertIs(
            False,
            result["timed_out"],
            "the run did not time out, so the result's timed_out field "
            "must be False; got: %r" % result.get("timed_out"),
        )
        self.assertIs(
            ZERO_EXIT_RESULT["stdout"],
            result["stdout"],
            "the agent's own outcome must pass through in its own "
            "stdout field; got: %r" % result.get("stdout"),
        )

    def test_run_role_with_timed_out_run_returns_timed_out_flag_and_kill_exit_code(self):
        # Arrange: the run was killed at the deadline - the runner
        # reports timed_out True and the -9 SIGKILL exit code.
        self._assert_pairwise_distinct(
            TIMED_OUT_RESULT, NONZERO_EXIT_RESULT, ZERO_EXIT_RESULT
        )
        self.assertTrue(
            TIMED_OUT_RESULT["timed_out"],
            "the scenario must be a timed-out run, or a driver that drops "
            "the timed_out field would never be exercised",
        )
        self.assertNotEqual(
            0,
            TIMED_OUT_RESULT["exit_code"],
            "the killed run carries a non-zero exit code, so a driver "
            "that raises on non-zero exit would be exercised here too",
        )
        # Act: the killed run is still data, not a driver failure.
        result = self._invoke(TIMED_OUT_RESULT)
        # Assert: the timeout flag and the kill exit code pass through
        # separately from the partial stream the agent produced before
        # the kill.
        self.assertIsInstance(result, dict)
        self.assertIs(
            True,
            result["timed_out"],
            "a timed-out run must come back with the timed_out field "
            "True, not dropped or forced to False; got: %r"
            % result.get("timed_out"),
        )
        self.assertEqual(
            -9,
            result["exit_code"],
            "the killed run must carry the runner's -9 SIGKILL exit code "
            "verbatim (anvilkit/pi/pibakeoff.py:494); got: %r"
            % result.get("exit_code"),
        )
        self.assertIs(
            TIMED_OUT_RESULT["stdout"],
            result["stdout"],
            "the partial stream captured before the kill must survive in "
            "its own stdout field, separate from the status fields",
        )
        self.assertEqual(
            TIMED_OUT_RESULT["evidence"],
            result["evidence"],
            "the runner's evidence string must pass through verbatim; "
            "got: %r" % result.get("evidence"),
        )


# The canned six-key runner results for the container-start-failure
# boundary: the failure shape is a non-zero exit with **empty** stdout
# and a stderr that names the image (the shape a docker image pull
# failure takes: the container never reached the pi process), while the
# two "not a driver failure" shapes pair the same non-zero exit with
# captured output, or pair empty output with a zero exit. The trio pins
# the distinguishing axis: what separates a driver error from recorded
# agent data is the (exit_code, stdout-empty) pair, never the exit code
# alone.
CONTAINER_START_FAILURE_RESULT: Dict[str, Any] = {
    "exit_code": 125,
    "stdout": "",
    "stderr": "docker: Error response from daemon: pull access denied for %s, repository does not exist" % TAG,
    "wall_time_s": 0.4,
    "timed_out": False,
    "evidence": "",
}
ZERO_EXIT_EMPTY_RESULT: Dict[str, Any] = {
    "exit_code": 0,
    "stdout": "",
    "stderr": "",
    "wall_time_s": 1.0,
    "timed_out": False,
    "evidence": "",
}


class TestRunRoleContainerStartFailure(RunRoleTestCase):
    """The driver names a container that could not start.

    A non-zero exit with empty stdout means the pi process never ran:
    the container start itself failed, and the driver raises
    ``DriverError`` naming the image tag and quoting the stderr. The
    boundary is the (exit_code, stdout-empty) pair, so the two adjacent
    shapes are pinned as non-errors: a non-zero exit *with* captured
    output is a recorded agent failure (returned as data, never raised),
    and a zero exit with empty output is a clean run.
    """

    def _run_with_result(
        self, runner_result: Dict[str, Any]
    ) -> "tuple":
        """Arrange an injected runner returning the canned six-key result;
        return ``(pidriver, fake, kwargs)`` so the test can act with or
        without expecting a raise."""
        pidriver = self._import_pidriver()
        fake = FakeRunner()
        fake._result = dict(runner_result)
        kwargs: Dict[str, Any] = {
            "definition": _coder_definition(),
            "repo_path": REPO_PATH,
            "tag": TAG,
            "session_id": SESSION_ID,
            "task": TASK,
            "runner": fake,
        }
        return pidriver, fake, kwargs

    def _assert_failure_shape(
        self,
        scenario: Dict[str, Any],
        *others: Dict[str, Any],
    ) -> None:
        """Anti-vacuity: the start-failure scenario's (exit_code,
        stdout-empty) pair must differ from each adjacent scenario's, so
        a driver keyed on the exit code alone - or on the empty stdout
        alone - cannot pass the boundary in both directions."""
        pair = (
            scenario["exit_code"] != 0,
            scenario["stdout"] == "",
        )
        for other in others:
            self.assertNotEqual(
                (other["exit_code"] != 0, other["stdout"] == ""),
                pair,
                "the container-start-failure scenario must be the only "
                "one pairing a non-zero exit with empty stdout, or the "
                "boundary could be satisfied by a driver keyed on one "
                "of the two fields alone",
            )

    def test_run_role_with_nonzero_exit_and_empty_stdout_raises_driver_error(self):
        # Arrange: the container never started - non-zero exit, empty
        # stdout, stderr naming the image.
        self._assert_failure_shape(
            CONTAINER_START_FAILURE_RESULT,
            NONZERO_EXIT_RESULT,
            ZERO_EXIT_EMPTY_RESULT,
        )
        self.assertNotEqual(
            0,
            CONTAINER_START_FAILURE_RESULT["exit_code"],
            "the scenario must carry a non-zero exit, or a driver that "
            "raises only on non-zero exits would never be exercised",
        )
        self.assertEqual(
            "",
            CONTAINER_START_FAILURE_RESULT["stdout"],
            "the scenario must carry empty stdout, or the empty-stdout "
            "half of the start-failure rule would be untested",
        )
        self.assertTrue(
            CONTAINER_START_FAILURE_RESULT["stderr"],
            "the scenario must carry stderr to quote, or the error's "
            "stderr quoting would be untested",
        )
        self.assertIn(
            TAG,
            CONTAINER_START_FAILURE_RESULT["stderr"],
            "the scenario's stderr must name the image, as a real image "
            "pull failure does",
        )
        pidriver, fake, kwargs = self._run_with_result(
            CONTAINER_START_FAILURE_RESULT
        )
        # Act / Assert: nothing is returned - DriverError is raised.
        with self.assertRaises(pidriver.DriverError):
            pidriver.run_role(**kwargs)
        # The start was still attempted: exactly one runner invocation.
        self.assertEqual(
            1,
            len(fake.calls),
            "the start attempt must still reach the runner exactly once; "
            "got %d calls" % len(fake.calls),
        )

    def test_run_role_driver_error_names_image_tag_and_quotes_stderr(self):
        # Arrange: the same start-failure shape.
        pidriver, fake, kwargs = self._run_with_result(
            CONTAINER_START_FAILURE_RESULT
        )
        # Act / Assert: the raised DriverError's message names the image
        # tag and quotes the stderr, so the operator can see which image
        # failed and why.
        with self.assertRaises(pidriver.DriverError) as ctx:
            pidriver.run_role(**kwargs)
        message = str(ctx.exception)
        self.assertIn(
            TAG,
            message,
            "the DriverError message must name the image tag %r; got: "
            "%r" % (TAG, message),
        )
        self.assertIn(
            CONTAINER_START_FAILURE_RESULT["stderr"],
            message,
            "the DriverError message must quote the runner's stderr; "
            "got: %r" % message,
        )

    def test_run_role_with_nonzero_exit_and_nonempty_stdout_returns_result_not_driver_error(self):
        # Arrange: a non-zero agent exit *with* captured output - the
        # recorded-agent-failure shape, one field away from the start
        # failure.
        self._assert_failure_shape(
            NONZERO_EXIT_RESULT,
            CONTAINER_START_FAILURE_RESULT,
            ZERO_EXIT_EMPTY_RESULT,
        )
        self.assertNotEqual(
            0,
            NONZERO_EXIT_RESULT["exit_code"],
            "the scenario must share the start-failure scenario's "
            "non-zero exit, or the two would not be one field apart",
        )
        self.assertTrue(
            NONZERO_EXIT_RESULT["stdout"],
            "the scenario must carry output, or it would be the start-"
            "failure shape, not the recorded-agent-failure shape",
        )
        pidriver, fake, kwargs = self._run_with_result(NONZERO_EXIT_RESULT)
        # Act: a driver that raises on any non-zero exit would raise
        # here; the compliant driver returns the result dict.
        result = pidriver.run_role(**kwargs)
        # Assert: a dict comes back (no DriverError) carrying the agent's
        # exit code and output verbatim.
        self.assertIsInstance(
            result,
            dict,
            "a non-zero agent exit with output must be returned as a "
            "result dict, never raised; got: %r"
            % type(result).__name__,
        )
        self.assertEqual(
            NONZERO_EXIT_RESULT["exit_code"],
            result["exit_code"],
            "the result must carry the agent's exit code verbatim; got: "
            "%r" % result.get("exit_code"),
        )
        self.assertIs(
            NONZERO_EXIT_RESULT["stdout"],
            result["stdout"],
            "the agent's output must pass through in its own stdout "
            "field; got: %r" % result.get("stdout"),
        )

    def test_run_role_with_zero_exit_and_empty_stdout_returns_result_not_driver_error(self):
        # Arrange: a clean run that produced no output - the empty-stdout
        # shape paired with a zero exit, the other side of the boundary.
        self._assert_failure_shape(
            ZERO_EXIT_EMPTY_RESULT,
            CONTAINER_START_FAILURE_RESULT,
            NONZERO_EXIT_RESULT,
        )
        self.assertEqual(
            0,
            ZERO_EXIT_EMPTY_RESULT["exit_code"],
            "the scenario must pair the start-failure scenario's empty "
            "stdout with a zero exit, or the two would not be one field "
            "apart",
        )
        pidriver, fake, kwargs = self._run_with_result(ZERO_EXIT_EMPTY_RESULT)
        # Act: a driver keyed on empty stdout alone would raise here;
        # the compliant driver returns the result dict.
        result = pidriver.run_role(**kwargs)
        # Assert: the zero exit and the empty stream come back as data.
        self.assertIsInstance(
            result,
            dict,
            "a zero-exit run must be returned as a result dict, never "
            "raised; got: %r" % type(result).__name__,
        )
        self.assertEqual(
            0,
            result["exit_code"],
            "the result must carry the runner's zero exit code verbatim; "
            "got: %r" % result.get("exit_code"),
        )
        self.assertEqual(
            "",
            result["stdout"],
            "the empty stream must pass through verbatim; got: %r"
            % result.get("stdout"),
        )


# The prompt-file existence check: with the check enabled, a repo whose
# ``.pi/roles/<role>.md`` is absent must fail before any container starts -
# no runner invocation - with pirole's RoleError naming the absolute path
# of the missing file. That error is a role-definition failure, distinct
# from DriverError, which a container that could not start raises only
# after a runner invocation. A repo where the prompt file exists passes
# the check and reaches the runner: the check is about existence, not
# about the driver refusing valid repos. The fake repos are tempfile
# directories, so no test touches a real repo.
def _make_fake_repo(tmp_dir: str, layout: str) -> str:
    """Create a fake repo under ``tmp_dir`` with the given ``.pi`` layout.

    ``layout`` is one of ``"empty"`` (a bare repo, no ``.pi`` at all),
    ``"roles_dir"`` (``.pi/roles`` exists but carries no ``coder.md``) or
    ``"prompt_file"`` (``.pi/roles/coder.md`` exists). The returned repo
    path is absolute, so the prompt file's expected absolute path is the
    repo path joined with the definition's ``prompt_path``.
    """
    repo = Path(tmp_dir) / "repo"
    repo.mkdir(parents=True)
    roles_dir: Optional[Path] = None
    if layout in ("roles_dir", "prompt_file"):
        roles_dir = repo / ".pi" / "roles"
        roles_dir.mkdir(parents=True)
    if layout == "prompt_file":
        assert roles_dir is not None
        (roles_dir / "coder.md").write_text(
            "a coder prompt\n", encoding="utf-8"
        )
    return str(repo)


class TestRunRoleMissingPromptFile(RunRoleTestCase):
    """A missing prompt file is named before any container starts.

    With the existence check enabled (``check_prompt_file=True``), a repo
    lacking the role's prompt file produces no result and no runner
    invocation: the failure is raised as pirole's ``RoleError`` naming
    the absolute path of the missing file, a role-definition failure
    distinct from ``DriverError`` (which a container that could not
    start raises after a runner invocation). A repo where the prompt
    file exists passes the check and proceeds to the runner.
    """

    def test_run_role_with_missing_prompt_file_raises_role_error_without_runner_invocation(self):
        # Arrange: a bare repo - no .pi directory at all.
        definition = _coder_definition()
        fake = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_fake_repo(tmp, "empty")
            self.assertFalse(
                (Path(repo) / definition["prompt_path"]).is_file(),
                "the repo must be missing the prompt file, or the "
                "missing-file rule would be untested",
            )
            pidriver = self._import_pidriver()
            # Act / Assert: nothing is returned - RoleError is raised.
            with self.assertRaises(pirole.RoleError):
                pidriver.run_role(
                    definition=definition,
                    repo_path=repo,
                    tag=TAG,
                    session_id=SESSION_ID,
                    task=TASK,
                    runner=fake,
                    check_prompt_file=True,
                )
            # A missing prompt file must fail before any container start:
            # the runner is invoked zero times.
            self.assertEqual(
                0,
                len(fake.calls),
                "a missing prompt file must fail before any container "
                "start, so the runner must be invoked zero times; got %d "
                "calls" % len(fake.calls),
            )

    def test_run_role_with_roles_dir_but_no_prompt_file_raises_role_error_without_runner_invocation(self):
        # Arrange: the .pi/roles directory exists, but coder.md does not -
        # the absence is the file, not its directory.
        definition = _coder_definition()
        fake = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_fake_repo(tmp, "roles_dir")
            self.assertTrue(
                (Path(repo) / ".pi" / "roles").is_dir(),
                "the .pi/roles directory must exist, or this would be the "
                "no-directory case, not the no-file case",
            )
            self.assertFalse(
                (Path(repo) / definition["prompt_path"]).is_file(),
                "the repo must be missing the prompt file, or the "
                "missing-file rule would be untested",
            )
            pidriver = self._import_pidriver()
            # Act / Assert: the same rule applies - RoleError, no runner.
            with self.assertRaises(pirole.RoleError):
                pidriver.run_role(
                    definition=definition,
                    repo_path=repo,
                    tag=TAG,
                    session_id=SESSION_ID,
                    task=TASK,
                    runner=fake,
                    check_prompt_file=True,
                )
            self.assertEqual(
                0,
                len(fake.calls),
                "a missing prompt file must fail before any container "
                "start, so the runner must be invoked zero times; got %d "
                "calls" % len(fake.calls),
            )

    def test_run_role_with_missing_prompt_file_error_names_absolute_path(self):
        # Arrange: a bare repo; the expected path is the repo path joined
        # with the definition's prompt path.
        definition = _coder_definition()
        fake = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_fake_repo(tmp, "empty")
            expected_path = str(Path(repo) / definition["prompt_path"])
            pidriver = self._import_pidriver()
            # Act / Assert: the raised RoleError's message names the
            # absolute path, so the operator knows exactly which file to
            # create.
            with self.assertRaises(pirole.RoleError) as ctx:
                pidriver.run_role(
                    definition=definition,
                    repo_path=repo,
                    tag=TAG,
                    session_id=SESSION_ID,
                    task=TASK,
                    runner=fake,
                    check_prompt_file=True,
                )
            message = str(ctx.exception)
            self.assertIn(
                expected_path,
                message,
                "the RoleError message must name the absolute path of "
                "the missing prompt file %r; got: %r"
                % (expected_path, message),
            )
            self.assertNotIsInstance(
                ctx.exception,
                pidriver.DriverError,
                "a missing prompt file is a role-definition failure, not "
                "a container-start failure, so the error must not be a "
                "DriverError; got: %r" % type(ctx.exception).__name__,
            )

    def test_run_role_with_existing_prompt_file_proceeds_to_runner(self):
        # Arrange: a repo carrying .pi/roles/coder.md - the boundary that
        # the check is about existence, not about the driver refusing
        # valid repos.
        definition = _coder_definition()
        fake = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_fake_repo(tmp, "prompt_file")
            self.assertTrue(
                (Path(repo) / definition["prompt_path"]).is_file(),
                "the repo must carry the prompt file, or the "
                "existing-file boundary would be untested",
            )
            pidriver = self._import_pidriver()
            # Act: the check passes, and the driver proceeds to the
            # runner as it does for any valid repo.
            result = pidriver.run_role(
                definition=definition,
                repo_path=repo,
                tag=TAG,
                session_id=SESSION_ID,
                task=TASK,
                runner=fake,
                check_prompt_file=True,
            )
            # Assert: no RoleError, exactly one runner invocation, and a
            # result dict comes back.
            self.assertEqual(
                1,
                len(fake.calls),
                "an existing prompt file must reach the runner exactly "
                "once; got %d calls" % len(fake.calls),
            )
            self.assertIsInstance(
                result,
                dict,
                "a run whose prompt file exists must return the runner's "
                "result dict, never an error; got: %r"
                % type(result).__name__,
            )


# The tier-aware default timeout: behaviour 16 supersedes the single
# 900.0 default. With no caller budget, a local-tier definition
# (coder/tester/docs) must run unbounded - the invocation carries
# ``timeout_s`` present with value ``None`` (the runner supports it since
# behaviour 15, and treats an *absent* key as a misuse that raises before
# spawn, so ``None`` is distinguishable from absence) - while a
# frontier-tier definition (architect) must carry a finite cost
# kill-switch, the driver's ``_FRONTIER_KILL_SWITCH_S`` (3600.0). An
# explicit caller budget always overrides the tier default, whichever
# tier it is.
class TestRunRoleTimeoutTierAware(RunRoleTestCase):
    """The driver's default timeout is tier-aware.

    plans/pi-phase6-single-role.md, behaviour 16 (review comment 2,
    user-confirmed design): a long local-model turn must never be killed
    for thinking, a frontier run must be cut off when it loops, and an
    explicit caller ``timeout_s`` always wins over the tier default.
    """

    def _invoke_and_return_invocation(
        self,
        definition: Dict[str, str],
        caller_timeout_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Arrange a fake runner, act with or without a caller budget,
        and return the single recorded invocation dict."""
        pidriver = self._import_pidriver()
        fake = FakeRunner()
        kwargs: Dict[str, Any] = {}
        if caller_timeout_s is not None:
            kwargs["timeout_s"] = caller_timeout_s
        pidriver.run_role(
            definition=definition,
            repo_path=REPO_PATH,
            tag=TAG,
            session_id=SESSION_ID,
            task=TASK,
            runner=fake,
            **kwargs,
        )
        self.assertEqual(
            1,
            len(fake.calls),
            "the driver must invoke the runner exactly once; got %d calls"
            % len(fake.calls),
        )
        return fake.calls[0]

    def test_run_role_local_tier_without_caller_budget_carries_unbounded_timeout_s(self):
        # Arrange: the local-tier definition, no caller budget.
        definition = _coder_definition()
        self.assertEqual(
            "local",
            definition["tier"],
            "the scenario must be a local-tier definition, or the "
            "local-tier unbounded rule would be untested; got: %r"
            % definition.get("tier"),
        )
        # Act.
        invocation = self._invoke_and_return_invocation(definition)
        # Assert: the ``timeout_s`` key is present in the invocation -
        # the runner requires the key and raises before spawn on an
        # absent one (the absent-key misuse pin in
        # tests/test_pibakeoff.py stays green) - and its value is
        # ``None``, so the local run is unbounded and the None is
        # distinguishable from absence.
        self.assertIn(
            "timeout_s",
            invocation,
            "the invocation dict must carry timeout_s per the runner "
            "seam - an absent key is the misuse the runner rejects "
            "before spawn; got keys: %r" % sorted(invocation),
        )
        self.assertIs(
            None,
            invocation["timeout_s"],
            "a local-tier run with no caller budget must be unbounded - "
            "timeout_s must be present with value None, so a long "
            "local-model turn is never killed for thinking; got: %r"
            % (invocation["timeout_s"],),
        )

    def test_run_role_frontier_tier_without_caller_budget_carries_finite_kill_switch(self):
        # Arrange: the frontier-tier definition, no caller budget.
        definition = _architect_definition()
        self.assertEqual(
            "frontier",
            definition["tier"],
            "the scenario must be a frontier-tier definition, or the "
            "frontier kill-switch rule would be untested; got: %r"
            % definition.get("tier"),
        )
        pidriver = self._import_pidriver()
        # The driver's frontier cost kill-switch (3600.0, behaviour 16),
        # imported from the module rather than hardcoded so the test
        # names the driver's own constant. The getattr with a 3600.0
        # fallback keeps this RED step honest: the driver still holds
        # the single 900.0 default and no such constant, so the failure
        # must be the budget assertion (900.0 != 3600.0), not an
        # AttributeError at the import step - and the explicit 3600.0
        # pin below means the fallback can never mask a wrong or
        # renamed constant once the green lands it.
        expected = getattr(pidriver, "_FRONTIER_KILL_SWITCH_S", 3600.0)
        self.assertEqual(
            3600.0,
            expected,
            "the driver's frontier kill-switch must be 3600.0 (plans/"
            "pi-phase6-single-role.md, behaviour 16); got: %r" % (expected,),
        )
        # Act.
        invocation = self._invoke_and_return_invocation(definition)
        # Assert: a positive finite float equal to the driver constant -
        # a frontier run must be cut off when it loops, and the budget
        # must be finite, never unbounded like the local tier.
        self.assertIsInstance(
            invocation["timeout_s"],
            float,
            "a frontier-tier run with no caller budget must carry the "
            "finite cost kill-switch as a float; got: %r"
            % (invocation["timeout_s"],),
        )
        self.assertGreater(
            invocation["timeout_s"],
            0.0,
            "the frontier kill-switch must be a positive budget; got: %r"
            % (invocation["timeout_s"],),
        )
        self.assertTrue(
            math.isfinite(invocation["timeout_s"]),
            "the frontier kill-switch must be finite - a frontier run "
            "must be cut off when it loops; got: %r"
            % (invocation["timeout_s"],),
        )
        self.assertEqual(
            expected,
            invocation["timeout_s"],
            "the frontier tier's default must be the driver's "
            "_FRONTIER_KILL_SWITCH_S; got: %r" % (invocation["timeout_s"],),
        )

    def test_run_role_local_tier_with_explicit_budget_overrides_tier_default(self):
        # Arrange: the local-tier definition, an explicit caller budget.
        definition = _coder_definition()
        self.assertEqual(
            "local",
            definition["tier"],
            "the scenario must be a local-tier definition, or the "
            "caller-budget-override rule would be untested for the local "
            "tier; got: %r" % definition.get("tier"),
        )
        # Act: the explicit budget must reach the runner verbatim, not
        # the unbounded local default.
        invocation = self._invoke_and_return_invocation(definition, 123.5)
        # Assert: the exact caller value wins.
        self.assertEqual(
            123.5,
            invocation["timeout_s"],
            "an explicit caller budget must override the tier default "
            "for the local tier; got: %r" % (invocation["timeout_s"],),
        )

    def test_run_role_frontier_tier_with_explicit_budget_overrides_tier_default(self):
        # Arrange: the frontier-tier definition, an explicit caller budget.
        definition = _architect_definition()
        self.assertEqual(
            "frontier",
            definition["tier"],
            "the scenario must be a frontier-tier definition, or the "
            "caller-budget-override rule would be untested for the "
            "frontier tier; got: %r" % definition.get("tier"),
        )
        # Act: the explicit budget must reach the runner verbatim, not
        # the kill-switch default.
        invocation = self._invoke_and_return_invocation(definition, 123.5)
        # Assert: the exact caller value wins.
        self.assertEqual(
            123.5,
            invocation["timeout_s"],
            "an explicit caller budget must override the tier default "
            "for the frontier tier; got: %r" % (invocation["timeout_s"],),
        )
