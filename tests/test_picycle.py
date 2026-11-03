"""Tests for ``anvilkit.pi.picycle`` - the red/green cycle loop.

``plans/pi-phase9-redgreen.md``, behaviour 8
(red-step-commits-once-on-genuine-red): given a tester delegation whose
suite run classifies ``red``, ``picycle.red_step(...)`` run with a fake
runner and a fake git seam commits EXACTLY ONCE, in the red format,
naming the behaviour and the plan. Error: a ``reason_mismatch`` commits
nothing and returns the mismatch for re-delegation.

``plans/pi-phase9-redgreen.md``, behaviour 9
(wrong-kind-of-red-is-not-committed): given a tester delegation whose
suite run classifies ``wrong_kind``, ``picycle.red_step(...)`` commits
nothing - no add, no commit - and returns the verbatim error output for
re-delegation to the tester. Error: none - this is the documented
re-delegation path, not a failure of the loop.

``anvilkit/pi/picycle.py`` does NOT exist yet. The import happens inside
each test (``_picycle``) rather than at module top level, so while the
module does not exist the tests fail at the import step
(``ModuleNotFoundError``) instead of breaking collection of the file.

The plan does NOT pin ``red_step``'s parameters (the same situation as
behaviours 5-7, where the signature was a proposed convention). The
signature and result shape below are a PROPOSED CONVENTION, flagged for
the coder to confirm:

PROPOSED signature (mirrors the plan's Given/When)::

    red_step(repo_path, scope, behaviour, number, plan_slug,
             reason, runner, git, issue=None) -> dict

- ``repo_path``: the repository path the git seam runs in (the ``git -C``
  path of ``picommit.commit_argv``);
- ``scope`` / ``behaviour`` / ``number`` / ``plan_slug`` / ``issue``:
  handed to ``picommit.red_message`` and the git seam verbatim - the
  same cycle identity a red commit is built from;
- ``reason``: the stated expected-failure reason, handed to
  ``piverdict.classify`` verbatim;
- ``runner``: the injected tester-role delegation, ``pidriver``-shaped -
  a callable invoked with the cycle's delegation context, whose result
  dict carries the suite run's ``unittest.TestResult`` (key ``"result"``)
  and the changed file paths of the delegation (key ``"changed_paths"``);
- ``git``: the injected git seam - a callable receiving an argv list
  (built by ``picommit``, never a shell string) and invoked for each git
  mutation. The plan's Assumptions pin the seam's existence and
  injectability, not its arity: this test proposes it takes exactly the
  one argv list.

PROPOSED result shape (flagged for confirmation). On a genuine red::

    {"verdict": "red", "committed": True, "message": <red message str>}

On a ``reason_mismatch`` (commits nothing, returns the mismatch for
re-delegation)::

    {"verdict": "reason_mismatch",
     "redelegate": "tester",
     "failure_text": <verbatim traceback text of the failure entry>}

The ``"redelegate"`` field is the distinguishable marker a caller uses to
re-delegate; ``"failure_text"`` carries the failure's traceback text
verbatim so the re-delegation is informed by it.

On a ``wrong_kind`` (commits nothing, returns the error for
re-delegation, behaviour 9)::

    {"verdict": "wrong_kind",
     "redelegate": "tester",
     "error_text": <verbatim traceback text of the first error entry>}

The ``"redelegate": "tester"`` marker is pinned for consistency with the
mismatch shape (the plan says "returned for re-delegation to the
tester"). ``"error_text"`` is a PROPOSED key name, flagged for
confirmation: the mismatch path uses ``"failure_text"`` for a failure
entry, so ``"error_text"`` is the consistent pairing for an error entry
- the failure and error texts are carried under distinct keys, never
shared.
"""

import importlib
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The inputs of behaviour 8, each a module constant so the expected
# message and argv below are reproducible by eye. The plan file is
# plans/pi-phase9-redgreen.md, hence plan slug "pi-phase9-redgreen";
# the issue is #56 per the plan header. The reason is this red step's
# stated expected-failure reason: the picycle module import.
REPO = "/workspace/repo"
SCOPE = "pi"
BEHAVIOUR = "red-step-commits-once-on-genuine-red"
NUMBER = 8
PLAN_SLUG = "pi-phase9-redgreen"
ISSUE = 56
REASON = "No module named 'anvilkit.pi.picycle'"

# The verbatim traceback text of the genuine red's single failure entry,
# in the shape ``TestResult.addFailure`` produces. It is deterministic by
# construction (a module constant, not a real run) and MUST contain the
# reason as a substring - that is behaviour 4's match rule, the one that
# makes this a genuine red rather than a mismatch.
GENUINE_RED_TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "./tests/test_picycle.py", line 5, in <module>\n'
    '    importlib.import_module("anvilkit.pi.picycle")\n'
    "ModuleNotFoundError: No module named 'anvilkit.pi.picycle'\n"
)
assert REASON in GENUINE_RED_TRACEBACK

# The verbatim traceback text of the mismatch's single failure entry: a
# genuine red whose failure text does NOT contain the reason (its
# assertion line is not the reason), so classify yields
# "reason_mismatch", never "red".
MISMATCH_TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "./tests/test_example.py", line 12, in test_example\n'
    "    self.assertEqual(1, 2)\n"
    "AssertionError: 1 != 2\n"
)
assert REASON not in MISMATCH_TRACEBACK

# The changed file paths of the delegation: the test file a red step
# writes.
CHANGED_PATHS = ["tests/test_picycle.py"]

# The verbatim traceback text of the wrong-kind run's single ERROR entry
# (an import failure arriving through ``TestResult.addError``), in the
# shape ``addError`` produces. It is deterministic by construction (a
# module constant, not a real run). The wrong-kind verdict does not
# depend on the reason - behaviour 3 outranks the reason check - so no
# substring constraint is needed here.
WRONG_KIND_ERROR_TEXT = (
    "Traceback (most recent call last):\n"
    '  File "./tests/test_new_module.py", line 1, in <module>\n'
    "    import anvilkit.pi.not_yet_written\n"
    "ModuleNotFoundError: No module named 'anvilkit.pi.not_yet_written'\n"
)


def _suite_result(traceback_text: str) -> unittest.TestResult:
    """A real ``TestResult`` carrying exactly one failure entry and no
    errors - the givens of a genuine red. The entry is the
    ``(test, traceback_text)`` tuple ``addFailure`` appends, built
    directly because ``addFailure`` renders its text from a live
    exception tuple and cannot inject a pinned one; the classifier reads
    exactly the two lists, so the list is the seam. A sentinel stands in
    for the failed test."""
    result = unittest.TestResult()
    failing_test = object()
    result.failures.append((failing_test, traceback_text))
    return result


class FakeRunner:
    """The injected tester-role delegation, ``pidriver``-shaped.

    Records every delegation context it is invoked with and returns a
    canned result dict carrying the pinned suite run (``"result"``) and
    the changed file paths (``"changed_paths"``), the proposed
    runner-result shape ``red_step`` reads. The record is a copy, so the
    loop cannot mutate what the test asserts on.
    """

    def __init__(self, result: unittest.TestResult) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._result: Dict[str, Any] = {
            "result": result,
            "changed_paths": list(CHANGED_PATHS),
        }

    def __call__(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append(dict(context))
        return dict(self._result)


class FakeGit:
    """The injected git seam.

    Records every argv list it is invoked with and returns ``None`` -
    the proposed seam contract: it receives the argv a git mutation is
    built with (a list, never a shell string) and performs the mutation.
    The record is a copy, so the loop cannot mutate what the test asserts
    on.
    """

    def __init__(self) -> None:
        self.calls: List[List[str]] = []

    def __call__(self, argv: List[str]) -> None:
        self.calls.append(list(argv))


class RedStepCommitsOnceOnGenuineRedTestCase(unittest.TestCase):
    """Behaviour 8 (red-step-commits-once-on-genuine-red): a tester
    delegation whose suite run classifies ``red`` produces exactly ONE
    commit, in the red format, naming the behaviour and the plan.

    CONFIRMED CONTRACT (manager, for B8's GREEN and everything after):
    ``red_step`` owns the whole commit step. On a genuine red it stages
    the changed paths with ``picommit.add_argv(repo, changed_paths)``
    and THEN commits with ``picommit.commit_argv(repo, message)`` - both
    through the injected git seam, in that order. "Exactly one commit"
    means exactly one COMMIT argv the seam recorded, not exactly one
    seam invocation. On a ``reason_mismatch`` it does nothing - no add,
    no commit. The signature and the result shapes in the module
    docstring are CONFIRMED as written.

    The import happens inside the test (``_picycle``) rather than at
    module top level, so while ``anvilkit/pi/picycle.py`` does not exist
    the test fails at the import step (``ModuleNotFoundError``) instead
    of breaking collection of the file.
    """

    def _picycle(self):
        """Import ``anvilkit.pi.picycle``."""
        return importlib.import_module("anvilkit.pi.picycle")

    def _run_red_step(self, picycle: Any, fake: FakeRunner, git: FakeGit) -> Dict[str, Any]:
        """Drive ``red_step`` on the proposed signature."""
        return picycle.red_step(
            REPO,
            SCOPE,
            BEHAVIOUR,
            NUMBER,
            PLAN_SLUG,
            REASON,
            runner=fake,
            git=git,
            issue=ISSUE,
        )

    def test_red_step_genuine_red_commits_exactly_once_in_red_format(
        self,
    ) -> None:
        # Arrange: a tester delegation whose suite run classifies red -
        # one failure whose text contains the reason, no errors - with a
        # recording git seam.
        fake = FakeRunner(_suite_result(GENUINE_RED_TRACEBACK))
        git = FakeGit()

        # Act
        picycle = self._picycle()
        self._run_red_step(picycle, fake, git)

        # Assert: the delegation ran exactly once.
        self.assertEqual(
            1,
            len(fake.calls),
            "red_step must run the tester delegation exactly once; "
            "got %d calls" % len(fake.calls),
        )

        # Assert: EXACTLY ONE of the argvs the fake git recorded is a
        # commit argv (the picommit.commit_argv shape). "Exactly one
        # commit" means exactly one commit argv, not exactly one seam
        # invocation - the confirmed contract has the red step own the
        # whole commit step, so it stages before it commits.
        commit_argv = [
            argv
            for argv in git.calls
            if argv[:5] == ["git", "-C", REPO, "commit", "-m"]
        ]
        self.assertEqual(
            1,
            len(commit_argv),
            "a genuine red records exactly one commit argv; got %d: %r"
            % (len(commit_argv), git.calls),
        )

        # Assert: that commit argv is the LAST recorded call - the
        # staging precedes it, never the other way round.
        self.assertIs(
            git.calls[-1],
            commit_argv[0],
            "the commit argv must be the last recorded git call; "
            "got: %r" % (git.calls,),
        )

        # Assert: a staging argv PRECEDES the commit - the
        # picommit.add_argv shape: git -C repo add -- <paths>, exactly
        # the delegation's changed paths.
        self.assertIn(
            ["git", "-C", REPO, "add", "--"] + list(CHANGED_PATHS),
            git.calls[:-1],
            "a staging argv must precede the commit argv; got: %r"
            % (git.calls,),
        )

        # Assert: the commit argv carries no amend and no no-verify
        # token, and exactly one message element after -m.
        argv = commit_argv[0]
        self.assertNotIn("--amend", argv)
        self.assertNotIn("--no-verify", argv)
        self.assertEqual(
            1,
            len(argv) - 5,
            "the commit argv carries exactly one message element after "
            "-m; got: %r" % (argv,),
        )

        # Assert: the message is ONE element, in the red format, naming
        # the behaviour and the plan, with the Refs trailer.
        message = argv[5]
        self.assertEqual(
            "test(%s): cover %s, failing" % (SCOPE, BEHAVIOUR),
            message.splitlines()[0],
            "the red message must open with the red subject; got: %r"
            % message,
        )
        self.assertIn(
            "plans/%s.md" % PLAN_SLUG,
            message,
            "the red message must cite the plan file; got: %r" % message,
        )
        self.assertIn(
            BEHAVIOUR,
            message,
            "the red message must name the behaviour; got: %r" % message,
        )
        self.assertIn(
            "Refs #%d" % ISSUE,
            message,
            "the red message must carry the Refs trailer; got: %r"
            % message,
        )

    def test_red_step_reason_mismatch_commits_nothing_and_returns_mismatch(
        self,
    ) -> None:
        # Arrange: the same genuine-red shape, but the failure text does
        # NOT contain the reason - classify yields reason_mismatch, never
        # red.
        fake = FakeRunner(_suite_result(MISMATCH_TRACEBACK))
        git = FakeGit()

        # Act
        picycle = self._picycle()
        result = self._run_red_step(picycle, fake, git)

        # Assert: the delegation ran, but nothing was committed.
        self.assertEqual(
            1,
            len(fake.calls),
            "red_step must run the tester delegation exactly once; "
            "got %d calls" % len(fake.calls),
        )
        self.assertEqual(
            0,
            len(git.calls),
            "a reason_mismatch commits nothing; got %d git calls: %r"
            % (len(git.calls), git.calls),
        )

        # Assert: the returned result is usable by a caller to
        # re-delegate - it carries the distinguishable verdict marker and
        # the verbatim failure text the re-delegation is informed by.
        self.assertEqual(
            "reason_mismatch",
            result.get("verdict"),
            "the result must carry the reason_mismatch verdict marker; "
            "got: %r" % (result,),
        )
        self.assertEqual(
            "tester",
            result.get("redelegate"),
            "the result must name the re-delegation target; got: %r"
            % (result,),
        )
        self.assertEqual(
            MISMATCH_TRACEBACK,
            result.get("failure_text"),
            "the result must carry the failure text verbatim for "
            "re-delegation; got: %r" % (result,),
        )


class WrongKindIsNotCommittedTestCase(unittest.TestCase):
    """Behaviour 9 (wrong-kind-of-red-is-not-committed): a tester
    delegation whose suite run classifies ``wrong_kind`` produces ZERO
    git invocations - no add, no commit - and returns the verbatim
    error output for re-delegation to the tester.

    A wrong-kind red must never be committed: committing a broken test
    (an import, collection or syntax error) poisons the history. Error:
    none - this is the documented re-delegation path, not a failure of
    the loop.

    CONFIRMED CONTRACT inherited from behaviour 8: ``red_step``'s
    signature and the runner/git seam shapes in this file's docstring.
    RESULT-SHAPE CHOICES FLAGGED for the coder: ``"redelegate":
    "tester"`` is pinned for consistency with the mismatch shape (the
    plan says the error output is "returned for re-delegation to the
    tester"); the key ``"error_text"`` is a PROPOSAL - the mismatch
    path carries its failure under ``"failure_text"``, so an error is
    carried under the consistently paired ``"error_text"`` and the two
    kinds of red never share a key.

    The import happens inside the test (``_picycle``) rather than at
    module top level, so the test fails at the import step
    (``ModuleNotFoundError``) instead of breaking collection of the
    file.
    """

    def _picycle(self):
        """Import ``anvilkit.pi.picycle``."""
        return importlib.import_module("anvilkit.pi.picycle")

    def _run_red_step(self, picycle: Any, fake: FakeRunner, git: FakeGit) -> Dict[str, Any]:
        """Drive ``red_step`` on the confirmed signature."""
        return picycle.red_step(
            REPO,
            SCOPE,
            BEHAVIOUR,
            NUMBER,
            PLAN_SLUG,
            REASON,
            runner=fake,
            git=git,
            issue=ISSUE,
        )

    def _wrong_kind_result(self) -> unittest.TestResult:
        """A real ``TestResult`` carrying exactly one error entry and no
        failures - the givens of a wrong-kind run (the clean case: an
        error outranks a failure, so the errors-only shape is what
        behaviour 3 pins). The entry is the ``(test, traceback_text)``
        tuple ``addError`` appends, built directly because ``addError``
        renders its text from a live exception tuple and cannot inject a
        pinned one; the classifier reads exactly the two lists, so the
        list is the seam. A sentinel stands in for the errored test."""
        result = unittest.TestResult()
        errored_test = object()
        result.errors.append((errored_test, WRONG_KIND_ERROR_TEXT))
        return result

    def test_red_step_wrong_kind_commits_nothing_and_returns_error(
        self,
    ) -> None:
        # Arrange: a tester delegation whose suite run classifies
        # wrong_kind - one error entry, no failures - with a recording
        # git seam.
        fake = FakeRunner(self._wrong_kind_result())
        git = FakeGit()

        # Act
        picycle = self._picycle()
        result = self._run_red_step(picycle, fake, git)

        # Assert: the delegation ran exactly once.
        self.assertEqual(
            1,
            len(fake.calls),
            "red_step must run the tester delegation exactly once; "
            "got %d calls" % len(fake.calls),
        )

        # Assert: ZERO git invocations - no add, no commit; a wrong-kind
        # red must never be committed.
        self.assertEqual(
            0,
            len(git.calls),
            "a wrong_kind commits nothing - no add, no commit; got %d "
            "git calls: %r" % (len(git.calls), git.calls),
        )

        # Assert: the returned result is usable by a caller to
        # re-delegate to the tester - it carries the distinguishable
        # verdict marker and the re-delegation target.
        self.assertEqual(
            "wrong_kind",
            result.get("verdict"),
            "the result must carry the wrong_kind verdict marker; got: "
            "%r" % (result,),
        )
        self.assertEqual(
            "tester",
            result.get("redelegate"),
            "the result must name the re-delegation target (consistency "
            "choice, pinned with the mismatch shape); got: %r" % (result,),
        )

        # Assert: the verbatim error text is carried for re-delegation
        # under the proposed "error_text" key - the error's traceback,
        # not the failure's, so "failure_text" is never reused for an
        # error.
        self.assertEqual(
            WRONG_KIND_ERROR_TEXT,
            result.get("error_text"),
            "the result must carry the error text verbatim for "
            "re-delegation (proposed key 'error_text', paired with the "
            "mismatch path's 'failure_text'); got: %r" % (result,),
        )


if __name__ == "__main__":
    unittest.main()
