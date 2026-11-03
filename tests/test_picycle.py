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

``plans/pi-phase9-redgreen.md``, behaviour 10
(run-cycle-commits-red-then-green): given a cycle whose red step is a
genuine red and whose subsequent code delegation runs the suite green,
``picycle.run_cycle(...)`` run with a fake runner and a fake git seam
commits exactly TWICE, in order - the red commit in the red format,
then the green commit in the green format (subject
``feat({scope}): {behaviour}`` for a feature), each naming the
behaviour and the plan. Error: none - this is the happy path.

``plans/pi-phase9-redgreen.md``, behaviour 11
(coder-test-file-edit-is-refused): given a coder report whose changed
paths include the cycle's test file, ``picycle.green_step(...)`` run
with a recording git seam commits nothing - zero git invocations - and
returns a test-change request carrying the coder's argument verbatim;
a changed test is a new red step, never an edit of the loop's own test.
The paired non-refusal test drives the same function with a coder
report whose changed paths do NOT include the cycle's test file and
pins that the green is then committed (one commit argv, green format,
one message element), so the refusal is testable in both directions.

Behaviours 8, 9, 10 and 11 have landed, so ``anvilkit/pi/picycle.py``
EXISTS and ``run_cycle`` and ``green_step`` do. The import still
happens inside each test (``_picycle``) rather than at module top
level: the landed behaviours landed one at a time behind this file,
and keeping the import inside the tests is what let this file stay
collected while they had not.

``plans/pi-phase9-redgreen.md``, behaviour 12
(two-failed-greens-halt): given one behaviour whose green attempt
fails twice in a row, the loop stops and returns a halt result
naming the behaviour, both failure outputs and the escalation
target. Error: a first failure re-delegates once - a second coder
delegation - and nothing is committed on either green attempt.

The manager-confirmed design (do not re-litigate): a green attempt
succeeds iff ``piverdict.classify(coder_result, reason)`` returns
``"green"`` - the same single judge the red step uses, with the same
non-empty ``reason`` - and any other verdict is a failed green
attempt. On the first failure the loop re-delegates the coder once;
a second failure halts it. A green attempt commits nothing - the
green commit happens only on a successful attempt.

The plan does NOT pin the halt result shape ("result shape NEW"), so
the shape below is a PROPOSED CONVENTION, flagged for confirmation::

    {"verdict": "halted",
     "behaviour": <the cycle's behaviour name>,
     "failure_outputs": [<attempt 1's failure/error text verbatim>,
                         <attempt 2's failure/error text verbatim>],
     "escalate_to": <the escalation target>}

- ``"failure_outputs"`` carries EACH attempt's text verbatim, in
  attempt order - for a failed attempt the text of its first failure
  entry, or first error entry when the run is a wrong-kind red, the
  same entry ``red_step`` carries on its re-delegation paths;
- ``"escalate_to"`` is FLAGGED: the plan says only "the escalation
  target". Its value is pinned to ``"architect"`` here, the manager's
  named escalation for a double green failure in
  ``.roo/rules-tdd-manager/instructions.xml`` ("a second failure
  makes the plan suspect — architect with both reports, or the
  intake"), chosen over the raw "or the intake" tail because it is a
  single, testable string.

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

# The inputs of behaviour 10 (run-cycle-commits-red-then-green), each a
# module constant so the expected argvs below are reproducible by eye.
# The cycle lands its own behaviour (strict TDD: this test IS the red,
# the run_cycle implementation is the green), so scope, behaviour and
# number are the cycle's own - behaviour 10 of the same plan, issue #56
# per the plan header.
CYCLE_SCOPE = "pi"
CYCLE_BEHAVIOUR = "run-cycle-commits-red-then-green"
CYCLE_NUMBER = 10
CYCLE_PLAN_SLUG = "pi-phase9-redgreen"
CYCLE_ISSUE = 56

# The stated expected-failure reason of the cycle's genuine red: this
# test's own expected failure - run_cycle does not exist yet.
CYCLE_REASON = (
    "module 'anvilkit.pi.picycle' has no attribute 'run_cycle'"
)

# The verbatim traceback text of the cycle's genuine red's single
# failure entry, in the shape ``TestResult.addFailure`` produces. It is
# deterministic by construction (a module constant, not a real run) and
# MUST contain the reason as a substring - that is behaviour 4's match
# rule, the one that makes this a genuine red rather than a mismatch.
CYCLE_RED_TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "./tests/test_picycle.py", line 1, in test_run_cycle\n'
    "    picycle.run_cycle(...)\n"
    "AttributeError: module 'anvilkit.pi.picycle' has no "
    "attribute 'run_cycle'\n"
)
assert CYCLE_REASON in CYCLE_RED_TRACEBACK

# The changed file paths of the cycle's coder delegation: the loop's
# implementation, as distinct from the tester delegation's test file.
CYCLE_CODE_CHANGED_PATHS = ["anvilkit/pi/picycle.py"]

# The inputs of behaviour 11 (coder-test-file-edit-is-refused), each a
# module constant so the expected argvs below are reproducible by eye.
# The cycle lands its own behaviour (strict TDD: this test IS the red,
# the green_step implementation is the green), so scope, behaviour and
# number are the cycle's own - behaviour 11 of the same plan, issue #56
# per the plan header.
GREEN_STEP_SCOPE = "pi"
GREEN_STEP_BEHAVIOUR = "coder-test-file-edit-is-refused"
GREEN_STEP_NUMBER = 11
GREEN_STEP_PLAN_SLUG = "pi-phase9-redgreen"
GREEN_STEP_ISSUE = 56
GREEN_STEP_KIND = "feature"

# The cycle's test file: the red step's changed_paths, the list the
# green step is handed as ``test_paths``. A coder report touching it is
# the refusal trigger; a changed test is a new red step, never an edit
# of the loop's own test.
GREEN_STEP_TEST_PATHS = ["tests/test_picycle.py"]

# The coder's changed paths when the refusal fires: the implementation
# plus the cycle's own test file - the test file's presence is what
# must be refused.
GREEN_STEP_REFUSAL_CHANGED_PATHS = [
    "anvilkit/pi/picycle.py",
    "tests/test_picycle.py",
]

# The coder's changed paths when no refusal fires: the implementation
# only, never the cycle's test file.
GREEN_STEP_CLEAN_CHANGED_PATHS = ["anvilkit/pi/picycle.py"]

# The coder's stated argument/justification, carried verbatim in the
# test-change request on refusal. Deterministic by construction (a
# module constant, not a real run).
GREEN_STEP_CODER_ARGUMENT = (
    "the red assertion is too narrow; widening it is part of the fix, "
    "so I adjusted the test alongside the implementation"
)

# The inputs of behaviour 12 (two-failed-greens-halt), each a module
# constant so the expected argvs and texts below are reproducible by
# eye. The cycle lands its own behaviour (strict TDD: this test IS the
# red, the re-judgement is the green), so scope, behaviour and number
# are the cycle's own - behaviour 12 of the same plan, issue #56 per
# the plan header.
HALT_SCOPE = "pi"
HALT_BEHAVIOUR = "two-failed-greens-halt"
HALT_NUMBER = 12
HALT_PLAN_SLUG = "pi-phase9-redgreen"
HALT_ISSUE = 56
HALT_KIND = "feature"

# The stated expected-failure reason of the halt cycle's genuine red:
# the missing re-judgement itself - run_cycle commits the green
# without classifying the coder's suite run.
HALT_REASON = (
    "run_cycle commits the green without classifying the coder's "
    "suite run"
)

# The verbatim traceback text of the halt cycle's genuine red's single
# failure entry, in the shape ``TestResult.addFailure`` produces. It is
# deterministic by construction (a module constant, not a real run) and
# MUST contain the reason as a substring - that is behaviour 4's match
# rule, the one that makes this a genuine red rather than a mismatch.
HALT_RED_TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "./tests/test_picycle.py", line 1, in test_run_cycle\n'
    "    picycle.run_cycle(...)\n"
    "AssertionError: run_cycle commits the green without classifying "
    "the coder's suite run\n"
)
assert HALT_REASON in HALT_RED_TRACEBACK

# The changed file paths of the halt cycle's coder delegation: the
# loop's implementation, as distinct from the tester delegation's test
# file.
HALT_CODE_CHANGED_PATHS = ["anvilkit/pi/picycle.py"]

# The verbatim traceback text of green attempt 1's single failure
# entry. It MUST contain the reason as a substring, so the attempt's
# re-judgement ``piverdict.classify(result, reason)`` yields ``"red"``
# - a non-green verdict, hence a FAILED green attempt (the
# manager-confirmed design: any verdict but ``"green"`` fails).
HALT_FIRST_FAILURE_TEXT = (
    "Traceback (most recent call last):\n"
    '  File "./tests/test_picycle.py", line 2, in test_run_cycle\n'
    "    picycle.run_cycle(...)\n"
    "AssertionError: run_cycle commits the green without classifying "
    "the coder's suite run\n"
)
assert HALT_REASON in HALT_FIRST_FAILURE_TEXT

# The verbatim traceback text of green attempt 2's single ERROR entry
# (a broken implementation arriving through ``TestResult.addError``):
# the attempt's re-judgement yields ``"wrong_kind"`` - a second,
# distinct non-green verdict, so the halt is pinned on two kinds of
# failed attempt, not one.
HALT_SECOND_ERROR_TEXT = (
    "Traceback (most recent call last):\n"
    '  File "./anvilkit/pi/picycle.py", line 1, in <module>\n'
    "    import anvilkit.pi.picycle\n"
    "ImportError: cannot import name 'rejudge' from 'anvilkit.pi'\n"
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


class CycleRunner:
    """The injected delegation seam for the cycle, keyed on the
    context's ``"role"`` field.

    The cycle's runner is invoked once per delegation: first call the
    tester role (the red step's suite run), second call the coder role
    (the green step's suite run). The record is a copy of each context,
    so the loop cannot mutate what the test asserts on; the tests also
    assert on the recorded ``"role"`` values to pin that the two
    delegations arrived in order, tester then coder.
    """

    def __init__(
        self,
        tester_result: unittest.TestResult,
        coder_result: unittest.TestResult,
        coder_changed_paths: List[str],
    ) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._results: Dict[str, Dict[str, Any]] = {
            "tester": {
                "result": tester_result,
                "changed_paths": list(CHANGED_PATHS),
            },
            "coder": {
                "result": coder_result,
                "changed_paths": list(coder_changed_paths),
            },
        }

    def __call__(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append(dict(context))
        canned = self._results[context["role"]]
        return {
            "result": canned["result"],
            "changed_paths": list(canned["changed_paths"]),
        }


class RunCycleCommitsRedThenGreenTestCase(unittest.TestCase):
    """Behaviour 10 (run-cycle-commits-red-then-green): a cycle whose
    red step is a genuine red and whose subsequent code delegation runs
    the suite green commits exactly TWICE, in order - the red commit in
    the red format, then the green commit in the green format (subject
    ``feat({scope}): {behaviour}`` for a feature), each naming the
    behaviour and the plan. Error: none - this is the happy path.

    The plan does NOT pin ``run_cycle``'s signature. The signature and
    result shape below are a PROPOSED CONVENTION, flagged for
    confirmation:

    PROPOSED signature (mirrors ``red_step`` plus the loop's needs)::

        run_cycle(repo_path, scope, behaviour, number, plan_slug,
                  reason, kind, runner, git, issue=None) -> dict

    - the first eight parameters are ``red_step``'s, minus ``reason``'s
      green role: ``reason`` is the red step's stated expected-failure
      reason, handed to the tester delegation and the classifier;
    - ``kind`` is the branch kind - ``"feature"`` or ``"bugfix"`` -
      needed to build the green subject (``picommit.green_message``);
    - ``runner`` is the injected delegation seam, invoked ONCE PER
      DELEGATION - first call the ``"tester"`` role (the red step),
      second call the ``"coder"`` role (the green step) - keyed on the
      context's ``"role"`` field, which ``red_step`` already sends;
    - ``git`` is the same seam ``red_step`` uses.

    PROPOSED result shape (flagged for confirmation). On the happy
    path the returned dict carries the loop's terminal verdict and the
    two commits' info::

        {"verdict": "green",
         "red": <the red step's red_step result dict>,
         "green": {"committed": True, "message": <the green message>}}

    ``"red"`` is exactly what ``red_step`` returns on a genuine red
    (``{"verdict": "red", "committed": True, "message": ...}``);
    ``"green"`` carries the green commit's message the same way.

    The import happens inside the test (``_picycle``) rather than at
    module top level; ``anvilkit/pi/picycle.py`` exists (behaviours 8-9
    landed) but ``run_cycle`` does not, so the test fails on the
    attribute lookup (``AttributeError``) instead of breaking
    collection of the file.
    """

    def _picycle(self):
        """Import ``anvilkit.pi.picycle``."""
        return importlib.import_module("anvilkit.pi.picycle")

    def test_run_cycle_genuine_red_then_green_commits_twice_in_order(
        self,
    ) -> None:
        # Arrange: a cycle whose red step is a genuine red (one failure
        # whose text contains the reason, no errors) and whose green
        # step is a pass (no failures, no errors) - with a role-keyed
        # delegation seam and a recording git seam.
        runner = CycleRunner(
            _suite_result(CYCLE_RED_TRACEBACK),
            unittest.TestResult(),
            CYCLE_CODE_CHANGED_PATHS,
        )
        git = FakeGit()

        # Act
        picycle = self._picycle()
        result = picycle.run_cycle(
            REPO,
            CYCLE_SCOPE,
            CYCLE_BEHAVIOUR,
            CYCLE_NUMBER,
            CYCLE_PLAN_SLUG,
            CYCLE_REASON,
            kind="feature",
            runner=runner,
            git=git,
            issue=CYCLE_ISSUE,
        )

        # Assert: the loop's terminal verdict is green.
        self.assertEqual(
            "green",
            result.get("verdict"),
            "the cycle's terminal verdict must be 'green'; got: %r"
            % (result,),
        )

        # Assert: the delegation seam was invoked twice, in order -
        # tester first (the red step), coder second (the green step) -
        # keyed on the context's "role" field.
        self.assertEqual(
            ["tester", "coder"],
            [call.get("role") for call in runner.calls],
            "the cycle must delegate to the tester then the coder, in "
            "that order; got: %r" % (runner.calls,),
        )

        # Assert: EXACTLY TWO of the argvs the fake git recorded are
        # commit argvs (the picommit.commit_argv shape). "Exactly two
        # commits" means exactly two COMMIT argvs, not exactly two seam
        # invocations - each step stages before it commits, so two add
        # argvs are expected alongside.
        commit_argv = [
            argv
            for argv in git.calls
            if argv[:5] == ["git", "-C", REPO, "commit", "-m"]
        ]
        self.assertEqual(
            2,
            len(commit_argv),
            "a completed cycle records exactly two commit argvs; got %d: "
            "%r" % (len(commit_argv), git.calls),
        )

        # Assert: a staging argv precedes EACH commit, in the
        # picommit.add_argv shape - the red step stages the tester's
        # changed paths, the green step stages the coder's.
        self.assertEqual(
            [
                ["git", "-C", REPO, "add", "--"] + list(CHANGED_PATHS),
                ["git", "-C", REPO, "add", "--"] + list(CYCLE_CODE_CHANGED_PATHS),
            ],
            [
                argv
                for argv in git.calls
                if argv[:5] == ["git", "-C", REPO, "add", "--"]
            ],
            "each step must stage its own changed paths before its "
            "commit; got: %r" % (git.calls,),
        )

        # Assert: the red commit argv PRECEDES the green commit argv -
        # a red is never amended or squashed into its green, so the
        # order in history is fixed.
        self.assertLess(
            git.calls.index(commit_argv[0]),
            git.calls.index(commit_argv[1]),
            "the red commit argv must precede the green commit argv; "
            "got: %r" % (git.calls,),
        )

        # Assert: no argv carries an amend or no-verify token - the
        # red is never rewritten.
        for argv in git.calls:
            self.assertNotIn("--amend", argv)
            self.assertNotIn("--no-verify", argv)

        # Assert: each commit argv carries exactly one message element
        # after -m - one element, byte-identical, never split.
        for argv in commit_argv:
            self.assertEqual(
                1,
                len(argv) - 5,
                "each commit argv carries exactly one message element "
                "after -m; got: %r" % (argv,),
            )

        # Assert: the FIRST commit's message is the red format - the
        # red subject, the plan file, the behaviour and the Refs
        # trailer.
        red_message = commit_argv[0][5]
        self.assertEqual(
            "test(%s): cover %s, failing" % (CYCLE_SCOPE, CYCLE_BEHAVIOUR),
            red_message.splitlines()[0],
            "the first commit must open with the red subject; got: %r"
            % red_message,
        )
        self.assertIn(
            "plans/%s.md" % CYCLE_PLAN_SLUG,
            red_message,
            "the red message must cite the plan file; got: %r"
            % red_message,
        )
        self.assertIn(
            CYCLE_BEHAVIOUR,
            red_message,
            "the red message must name the behaviour; got: %r"
            % red_message,
        )
        self.assertIn(
            "Refs #%d" % CYCLE_ISSUE,
            red_message,
            "the red message must carry the Refs trailer; got: %r"
            % red_message,
        )

        # Assert: the SECOND commit's message is the green format - the
        # feat subject for a feature, the body ending Green., the plan
        # file and the Refs trailer, and never the word "failing" - it
        # is what keeps the red distinct from its green in history.
        green_message = commit_argv[1][5]
        self.assertEqual(
            "feat(%s): %s" % (CYCLE_SCOPE, CYCLE_BEHAVIOUR),
            green_message.splitlines()[0],
            "the second commit must open with the green feature "
            "subject; got: %r" % green_message,
        )
        self.assertIn(
            "plans/%s.md" % CYCLE_PLAN_SLUG,
            green_message,
            "the green message must cite the plan file; got: %r"
            % green_message,
        )
        self.assertIn(
            CYCLE_BEHAVIOUR,
            green_message,
            "the green message must name the behaviour; got: %r"
            % green_message,
        )
        self.assertIn(
            "Refs #%d" % CYCLE_ISSUE,
            green_message,
            "the green message must carry the Refs trailer; got: %r"
            % green_message,
        )
        self.assertEqual(
            "Behaviour %d of plans/%s.md. Green."
            % (CYCLE_NUMBER, CYCLE_PLAN_SLUG),
            green_message.splitlines()[2],
            "the green message's body must read 'Behaviour %d of "
            "plans/%s.md. Green.'; got: %r"
            % (CYCLE_NUMBER, CYCLE_PLAN_SLUG, green_message),
        )
        self.assertNotIn(
            "failing",
            green_message,
            "'failing' must never appear in a green message; got: %r"
            % green_message,
        )

        # Assert: the returned dict carries each commit's info under
        # the proposed keys - "red" is the red step's own result,
        # "green" carries the green message the same way.
        self.assertEqual(
            "red",
            result.get("red", {}).get("verdict"),
            "the result's 'red' must carry the red step's verdict; "
            "got: %r" % (result,),
        )
        self.assertEqual(
            green_message,
            result.get("green", {}).get("message"),
            "the result's 'green' must carry the green commit's "
            "message; got: %r" % (result,),
        )


class CoderTestFileEditIsRefusedTestCase(unittest.TestCase):
    """Behaviour 11 (coder-test-file-edit-is-refused): a coder report
    whose changed paths include the cycle's test file produces ZERO git
    invocations - nothing is committed - and the result is a
    test-change request carrying the coder's argument verbatim. Error:
    the test file is never edited by the loop; a changed test is a new
    red step.

    The paired non-refusal test is part of the same behaviour's
    observable contract: a refusal with no non-refusal test would be
    untestable in one direction only, so the refusal is pinned to fire
    on the test file, not on any path.

    The plan does NOT pin ``green_step``'s signature (the same
    situation as behaviours 8-10). The signature, report keys and
    result shape below are a PROPOSED CONVENTION, flagged for
    confirmation:

    PROPOSED signature (mirrors the plan's When, plus the refusal's
    needs)::

        green_step(repo_path, scope, behaviour, number, plan_slug,
                   kind, report, test_paths, git, issue=None) -> dict

    - ``repo_path`` / ``scope`` / ``behaviour`` / ``number`` /
      ``plan_slug`` / ``kind`` / ``git`` / ``issue`` mean the same as
      in ``run_cycle``'s confirmed green half (``kind`` and ``issue``
      feed ``picommit.green_message``);
    - ``report`` is the coder delegation's result dict. The keys this
      test reads are PROPOSED, mirroring the ``red_step`` report
      convention: ``"changed_paths"`` - the list of paths the coder
      touched, and ``"argument"`` - the coder's stated
      argument/justification, a string;
    - ``test_paths`` is the list of test files the cycle owns - the
      red step's ``changed_paths`` - handed in so the green step can
      refuse without re-deriving them.

    PROPOSED matching rule (flagged for confirmation): a changed path
    is a refusal trigger if it EQUALS any entry of ``test_paths`` -
    exact path comparison, no prefix matching invented.

    PROPOSED result shape (flagged for confirmation). On a refusal
    (nothing committed)::

        {"verdict": "test_change_requested", "argument": <verbatim>}

    On a clean green (the refusal does not fire)::

        {"verdict": "green", "committed": True, "message": <the green
        message>}

    The import happens inside the test (``_picycle``) rather than at
    module top level; ``anvilkit/pi/picycle.py`` exists (behaviours
    8-10 landed) but ``green_step`` does not, so the tests fail on the
    attribute lookup (``AttributeError``) instead of breaking
    collection of the file.
    """

    def _picycle(self):
        """Import ``anvilkit.pi.picycle``."""
        return importlib.import_module("anvilkit.pi.picycle")

    def _run_green_step(
        self,
        picycle: Any,
        report: Dict[str, Any],
        test_paths: List[str],
        git: FakeGit,
    ) -> Dict[str, Any]:
        """Drive ``green_step`` on the proposed signature."""
        return picycle.green_step(
            REPO,
            GREEN_STEP_SCOPE,
            GREEN_STEP_BEHAVIOUR,
            GREEN_STEP_NUMBER,
            GREEN_STEP_PLAN_SLUG,
            GREEN_STEP_KIND,
            report,
            test_paths,
            git,
            issue=GREEN_STEP_ISSUE,
        )

    def test_green_step_test_file_changed_commits_nothing_and_returns_argument(
        self,
    ) -> None:
        # Arrange: a coder report whose changed paths include the
        # cycle's test file (the red step's changed_paths, passed as
        # test_paths), with a recording git seam.
        report: Dict[str, Any] = {
            "changed_paths": list(GREEN_STEP_REFUSAL_CHANGED_PATHS),
            "argument": GREEN_STEP_CODER_ARGUMENT,
        }
        git = FakeGit()

        # Act
        picycle = self._picycle()
        result = self._run_green_step(
            picycle, report, list(GREEN_STEP_TEST_PATHS), git
        )

        # Assert: NOTHING is committed - zero git invocations, no add,
        # no commit; the test file is never edited by the loop and a
        # changed test is a new red step.
        self.assertEqual(
            0,
            len(git.calls),
            "a coder report that touched the cycle's test file commits "
            "nothing - no add, no commit; got %d git calls: %r"
            % (len(git.calls), git.calls),
        )

        # Assert: the result is a test-change request (proposed shape,
        # flagged): the distinguishable verdict marker, carrying the
        # coder's argument VERBATIM so the caller's new red step is
        # informed by the coder's justification.
        self.assertEqual(
            "test_change_requested",
            result.get("verdict"),
            "the result must carry the test-change-request verdict "
            "marker; got: %r" % (result,),
        )
        self.assertEqual(
            GREEN_STEP_CODER_ARGUMENT,
            result.get("argument"),
            "the result must carry the coder's argument verbatim; got: "
            "%r" % (result,),
        )

    def test_green_step_code_only_change_commits_green(
        self,
    ) -> None:
        # Arrange: a coder report whose changed paths do NOT include
        # the cycle's test file - the refusal must not over-fire on any
        # path, only on the test file.
        report: Dict[str, Any] = {
            "changed_paths": list(GREEN_STEP_CLEAN_CHANGED_PATHS),
            "argument": GREEN_STEP_CODER_ARGUMENT,
        }
        git = FakeGit()

        # Act
        picycle = self._picycle()
        result = self._run_green_step(
            picycle, report, list(GREEN_STEP_TEST_PATHS), git
        )

        # Assert: the green IS committed - exactly one commit argv, a
        # staging argv preceding it, in the picommit stage-then-commit
        # order the red step uses.
        commit_argv = [
            argv
            for argv in git.calls
            if argv[:5] == ["git", "-C", REPO, "commit", "-m"]
        ]
        self.assertEqual(
            1,
            len(commit_argv),
            "a coder report that did not touch the test file commits "
            "exactly once; got %d commit argvs: %r"
            % (len(commit_argv), git.calls),
        )
        self.assertIn(
            ["git", "-C", REPO, "add", "--"] + list(GREEN_STEP_CLEAN_CHANGED_PATHS),
            git.calls[:-1],
            "a staging argv must precede the commit argv; got: %r"
            % (git.calls,),
        )
        self.assertIs(
            git.calls[-1],
            commit_argv[0],
            "the commit argv must be the last recorded git call; "
            "got: %r" % (git.calls,),
        )

        # Assert: no amend or no-verify token, and exactly one message
        # element after -m - one element, byte-identical, never split.
        argv = commit_argv[0]
        self.assertNotIn("--amend", argv)
        self.assertNotIn("--no-verify", argv)
        self.assertEqual(
            1,
            len(argv) - 5,
            "the commit argv carries exactly one message element after "
            "-m; got: %r" % (argv,),
        )

        # Assert: the message is in the green format - the feat subject
        # for a feature, the body ending Green., the plan file, the
        # behaviour, the Refs trailer, and never the word "failing".
        message = argv[5]
        self.assertEqual(
            "feat(%s): %s" % (GREEN_STEP_SCOPE, GREEN_STEP_BEHAVIOUR),
            message.splitlines()[0],
            "the commit must open with the green feature subject; "
            "got: %r" % message,
        )
        self.assertIn(
            "plans/%s.md" % GREEN_STEP_PLAN_SLUG,
            message,
            "the green message must cite the plan file; got: %r" % message,
        )
        self.assertIn(
            GREEN_STEP_BEHAVIOUR,
            message,
            "the green message must name the behaviour; got: %r" % message,
        )
        self.assertIn(
            "Refs #%d" % GREEN_STEP_ISSUE,
            message,
            "the green message must carry the Refs trailer; got: %r"
            % message,
        )
        self.assertEqual(
            "Behaviour %d of plans/%s.md. Green."
            % (GREEN_STEP_NUMBER, GREEN_STEP_PLAN_SLUG),
            message.splitlines()[2],
            "the green message's body must read 'Behaviour %d of "
            "plans/%s.md. Green.'; got: %r"
            % (GREEN_STEP_NUMBER, GREEN_STEP_PLAN_SLUG, message),
        )
        self.assertNotIn(
            "failing",
            message,
            "'failing' must never appear in a green message; got: %r"
            % message,
        )

        # Assert: the result carries the green commit's info under the
        # proposed keys (flagged).
        self.assertEqual(
            "green",
            result.get("verdict"),
            "a clean green step must carry the green verdict; got: %r"
            % (result,),
        )
        self.assertEqual(
            message,
            result.get("message"),
            "the result must carry the green commit's message; got: %r"
            % (result,),
        )


class QueuedCycleRunner:
    """The delegation seam for the double-green halt, with the coder's
    attempts served from a queue.

    ``CycleRunner`` keys on the context's ``"role"`` field with one
    canned result per role, which fits the happy path's single coder
    delegation. A re-delegating green half is invoked ONCE PER GREEN
    ATTEMPT - first coder call attempt 1, second attempt 2 - so the
    coder role is served in order from a queue of pinned
    ``TestResult``s instead: each coder call pops the next attempt's
    suite run, and the re-delegation (if the loop lands it) is observed
    as a second coder call with a different canned result. The tester
    role keeps one canned result, exactly as ``CycleRunner``. The
    record is a copy of each context, so the loop cannot mutate what
    the test asserts on; the tests also assert on the recorded
    ``"role"`` values to pin the order, tester then coder, then coder.
    """

    def __init__(
        self,
        tester_result: unittest.TestResult,
        coder_results: List[unittest.TestResult],
        coder_changed_paths: List[str],
    ) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._tester: Dict[str, Any] = {
            "result": tester_result,
            "changed_paths": list(CHANGED_PATHS),
        }
        self._coder_results: List[unittest.TestResult] = list(coder_results)
        self._coder_changed_paths: List[str] = list(coder_changed_paths)

    def __call__(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append(dict(context))
        role: str = context["role"]
        if role == "tester":
            return {
                "result": self._tester["result"],
                "changed_paths": list(self._tester["changed_paths"]),
            }
        if role == "coder":
            result: unittest.TestResult = self._coder_results.pop(0)
            return {
                "result": result,
                "changed_paths": list(self._coder_changed_paths),
            }
        raise AssertionError("unexpected delegation role %r" % (role,))


class TwoFailedGreensHaltTestCase(unittest.TestCase):
    """Behaviour 12 (two-failed-greens-halt): a cycle whose green
    attempt fails twice in a row stops the loop and returns a halt
    result naming the behaviour, both failure outputs and the
    escalation target. Error: a first failure re-delegates once - a
    second coder delegation - and nothing is committed on either green
    attempt.

    Manager-CONFIRMED design (do not re-litigate): a green attempt
    succeeds iff ``piverdict.classify(coder_result, reason)`` returns
    ``"green"`` - the same single judge the red step uses, with the
    same non-empty ``reason`` - and any other verdict is a failed
    green attempt. On the first failure the loop re-delegates the
    coder once; a second failure halts it. On a green attempt NOTHING
    is committed - the green commit happens only on a successful
    (first or second) attempt.

    RESULT SHAPE: the plan pins the contents (names the behaviour,
    carries both failure outputs verbatim, names the escalation
    target) but not the shape ("result shape NEW"). The shape below is
    a PROPOSED CONVENTION, flagged for confirmation::

        {"verdict": "halted",
         "behaviour": <the cycle's behaviour name>,
         "failure_outputs": [<attempt 1's failure/error text verbatim>,
                             <attempt 2's failure/error text verbatim>],
         "escalate_to": <the escalation target>}

    - ``"failure_outputs"`` carries each attempt's text VERBATIM, in
      attempt order - for a failed attempt the text of its first
      failure entry, or first error entry when the run is a wrong-kind
      red, the same entry ``red_step`` carries on its re-delegation
      paths;
    - ``"escalate_to"`` is FLAGGED: the plan says only "the
      escalation target". Its value is pinned to ``"architect"`` here
      - the manager's named escalation for a double green failure in
      ``.roo/rules-tdd-manager/instructions.xml`` ("a second failure
      makes the plan suspect — architect with both reports, or the
      intake"), chosen over the raw "or the intake" tail because it is
      a single, testable string.
    """

    def _picycle(self):
        """Import ``anvilkit.pi.picycle``."""
        return importlib.import_module("anvilkit.pi.picycle")

    def _run_cycle(
        self,
        picycle: Any,
        runner: QueuedCycleRunner,
        git: FakeGit,
    ) -> Dict[str, Any]:
        """Drive ``run_cycle`` on the confirmed signature, for the
        halt cycle's own identity."""
        return picycle.run_cycle(
            REPO,
            HALT_SCOPE,
            HALT_BEHAVIOUR,
            HALT_NUMBER,
            HALT_PLAN_SLUG,
            HALT_REASON,
            kind=HALT_KIND,
            runner=runner,
            git=git,
            issue=HALT_ISSUE,
        )

    def _error_result(self, traceback_text: str) -> unittest.TestResult:
        """A real ``TestResult`` carrying exactly one error entry and no
        failures - the givens of a wrong-kind run, the same seam
        ``WrongKindIsNotCommittedTestCase`` uses. A sentinel stands in
        for the errored test."""
        result = unittest.TestResult()
        errored_test = object()
        result.errors.append((errored_test, traceback_text))
        return result

    def test_second_failed_green_halts_with_both_outputs(self) -> None:
        # Arrange: a cycle whose red step is a genuine red, whose green
        # attempt 1 is a failed assertion the re-judgement classifies
        # "red" (one failure whose text contains the reason) and whose
        # re-delegated attempt 2 is a wrong-kind run (one error entry)
        # - two consecutive failed greens, of two distinct kinds - with
        # the queue-based delegation seam and a recording git seam.
        runner = QueuedCycleRunner(
            _suite_result(HALT_RED_TRACEBACK),
            [
                _suite_result(HALT_FIRST_FAILURE_TEXT),
                self._error_result(HALT_SECOND_ERROR_TEXT),
            ],
            HALT_CODE_CHANGED_PATHS,
        )
        git = FakeGit()

        # Act
        picycle = self._picycle()
        result = self._run_cycle(picycle, runner, git)

        # Assert: the loop re-delegated the coder once after the first
        # failed green attempt - THREE delegations in order, tester
        # (the red step) then coder (attempt 1) then coder (attempt 2).
        self.assertEqual(
            3,
            len(runner.calls),
            "a first failed green attempt must be re-judged by "
            "classify and re-delegate the coder once, for three "
            "delegations; got %d (the loop re-judges no green "
            "attempt): %r" % (len(runner.calls), runner.calls),
        )
        self.assertEqual(
            ["tester", "coder", "coder"],
            [call.get("role") for call in runner.calls],
            "the delegations must be tester, then coder attempt 1, "
            "then coder attempt 2, in that order; got: %r"
            % (runner.calls,),
        )

        # Assert: EXACTLY ONE commit argv - the RED commit - and no
        # green commit: nothing is committed on either green attempt.
        # The single commit argv is red format, so a green commit
        # cannot have been made.
        commit_argv = [
            argv
            for argv in git.calls
            if argv[:5] == ["git", "-C", REPO, "commit", "-m"]
        ]
        self.assertEqual(
            1,
            len(commit_argv),
            "nothing is committed on a green attempt; a double green "
            "failure records exactly the red commit, no green commit; "
            "got %d commit argvs: %r" % (len(commit_argv), git.calls),
        )
        red_message = commit_argv[0][5]
        self.assertEqual(
            "test(%s): cover %s, failing" % (HALT_SCOPE, HALT_BEHAVIOUR),
            red_message.splitlines()[0],
            "the only commit must be the red commit in the red "
            "subject; got: %r" % red_message,
        )
        for argv in git.calls:
            self.assertNotIn("--amend", argv)
            self.assertNotIn("--no-verify", argv)

        # Assert: the returned result is the halt (proposed shape,
        # flagged): the distinguishable verdict marker, the
        # behaviour's name, both failure outputs VERBATIM in attempt
        # order, and the escalation target.
        self.assertEqual(
            "halted",
            result.get("verdict"),
            "the loop must return the halt verdict after a second "
            "failed green attempt; got: %r" % (result,),
        )
        self.assertEqual(
            HALT_BEHAVIOUR,
            result.get("behaviour"),
            "the halt result must name the behaviour; got: %r" % (result,),
        )
        self.assertEqual(
            [HALT_FIRST_FAILURE_TEXT, HALT_SECOND_ERROR_TEXT],
            result.get("failure_outputs"),
            "the halt result must carry both failure outputs verbatim, "
            "in attempt order; got: %r" % (result.get("failure_outputs",)),
        )
        self.assertEqual(
            "architect",
            result.get("escalate_to"),
            "the halt result must name the escalation target "
            "(flagged choice: 'architect', the manager's named "
            "escalation for a double green failure); got: %r"
            % (result.get("escalate_to",),),
        )

    def test_first_failed_green_redelegates_and_commits_on_second(
        self,
    ) -> None:
        # Arrange: a cycle whose red step is a genuine red, whose green
        # attempt 1 is a failed assertion (the re-judgement classifies
        # it "red", a failed attempt) and whose re-delegated attempt 2
        # runs the suite green (no failures, no errors) - the Error
        # clause: one re-delegation, then the green lands.
        runner = QueuedCycleRunner(
            _suite_result(HALT_RED_TRACEBACK),
            [
                _suite_result(HALT_FIRST_FAILURE_TEXT),
                unittest.TestResult(),
            ],
            HALT_CODE_CHANGED_PATHS,
        )
        git = FakeGit()

        # Act
        picycle = self._picycle()
        result = self._run_cycle(picycle, runner, git)

        # Assert: the loop re-delegated the coder once - THREE
        # delegations in order, tester then coder then coder.
        self.assertEqual(
            3,
            len(runner.calls),
            "a first failed green attempt must be re-judged by "
            "classify and re-delegate the coder once, for three "
            "delegations; got %d (the loop re-judges no green "
            "attempt): %r" % (len(runner.calls), runner.calls),
        )
        self.assertEqual(
            ["tester", "coder", "coder"],
            [call.get("role") for call in runner.calls],
            "the delegations must be tester, then coder attempt 1, "
            "then coder attempt 2, in that order; got: %r"
            % (runner.calls,),
        )

        # Assert: EXACTLY TWO commit argvs - the red commit first, then
        # ONE green commit; a staging argv precedes each, in the
        # stage-then-commit order the red step uses.
        commit_argv = [
            argv
            for argv in git.calls
            if argv[:5] == ["git", "-C", REPO, "commit", "-m"]
        ]
        self.assertEqual(
            2,
            len(commit_argv),
            "a green attempt that passes on the second delegation "
            "commits exactly twice - the red commit, then one green "
            "commit; got %d commit argvs: %r"
            % (len(commit_argv), git.calls),
        )
        self.assertEqual(
            [
                ["git", "-C", REPO, "add", "--"] + list(CHANGED_PATHS),
                ["git", "-C", REPO, "add", "--"] + list(HALT_CODE_CHANGED_PATHS),
            ],
            [
                argv
                for argv in git.calls
                if argv[:5] == ["git", "-C", REPO, "add", "--"]
            ],
            "each step must stage its own changed paths before its "
            "commit; got: %r" % (git.calls,),
        )
        self.assertLess(
            git.calls.index(commit_argv[0]),
            git.calls.index(commit_argv[1]),
            "the red commit argv must precede the green commit argv; "
            "got: %r" % (git.calls,),
        )
        for argv in git.calls:
            self.assertNotIn("--amend", argv)
            self.assertNotIn("--no-verify", argv)
        for argv in commit_argv:
            self.assertEqual(
                1,
                len(argv) - 5,
                "each commit argv carries exactly one message element "
                "after -m; got: %r" % (argv,),
            )

        # Assert: the first commit is the red format, the second the
        # green format - the feat subject for a feature, the plan file,
        # the behaviour, the Refs trailer, and never the word
        # "failing".
        red_message = commit_argv[0][5]
        self.assertEqual(
            "test(%s): cover %s, failing" % (HALT_SCOPE, HALT_BEHAVIOUR),
            red_message.splitlines()[0],
            "the first commit must open with the red subject; got: %r"
            % red_message,
        )
        self.assertIn(
            "Refs #%d" % HALT_ISSUE,
            red_message,
            "the red message must carry the Refs trailer; got: %r"
            % red_message,
        )
        green_message = commit_argv[1][5]
        self.assertEqual(
            "feat(%s): %s" % (HALT_SCOPE, HALT_BEHAVIOUR),
            green_message.splitlines()[0],
            "the second commit must open with the green feature "
            "subject; got: %r" % green_message,
        )
        self.assertIn(
            "plans/%s.md" % HALT_PLAN_SLUG,
            green_message,
            "the green message must cite the plan file; got: %r"
            % green_message,
        )
        self.assertIn(
            HALT_BEHAVIOUR,
            green_message,
            "the green message must name the behaviour; got: %r"
            % green_message,
        )
        self.assertIn(
            "Refs #%d" % HALT_ISSUE,
            green_message,
            "the green message must carry the Refs trailer; got: %r"
            % green_message,
        )
        self.assertNotIn(
            "failing",
            green_message,
            "'failing' must never appear in a green message; got: %r"
            % green_message,
        )

        # Assert: the returned result is the normal completed-cycle
        # shape - the terminal verdict green.
        self.assertEqual(
            "green",
            result.get("verdict"),
            "a green attempt that passes on the second delegation "
            "returns the completed-cycle verdict; got: %r" % (result,),
        )


if __name__ == "__main__":
    unittest.main()
