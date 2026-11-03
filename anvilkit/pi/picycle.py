"""The red/green cycle: delegate, judge, commit.

One job: run one step of the red/green cycle - delegate to the tester
role, judge the suite run with ``piverdict.classify``, and commit on a
genuine red - and nothing else. This module is the only one of the
three (``piverdict`` decides, ``picommit`` builds) that invokes a git
mutation, and it does so only through the injected git seam: it
performs no subprocess itself, no Docker and no git of its own, so the
loop is testable with no repository and no commits (the plan's
Assumptions pin the seam's existence and injectability). The message it
commits is built by ``picommit``; the verdict it acts on is decided by
``piverdict``.

House discipline, as ``anvilkit.pi.piverdict`` and
``anvilkit.pi.picommit`` use it: one behaviour lands per red/green
cycle, and the docstring says which ones have landed. Behaviours 8, 9,
10, 11, 12, 13 and 14 of ``plans/pi-phase9-redgreen.md`` are
implemented here:
``red_step(repo_path, scope, behaviour, number, plan_slug, reason,
runner, git, issue=None)`` invokes the injected tester delegation
exactly once, classifies its suite run with
``piverdict.classify(result, reason)``, and on a genuine red
(``"red"``) stages the delegation's changed paths with
``picommit.add_argv`` and then commits with ``picommit.commit_argv`` in
the red message built by ``picommit.red_message`` - both through the
seam, in that order, so the red step owns the whole commit step and a
genuine red commits exactly once - and its ``"red"`` verdict result
carries the delegation's changed paths under ``"changed_paths"``
(behaviour 13 added the key, additively: those paths ARE the cycle's
test files, so ``run_cycle`` derives its ``test_paths`` from the red
result without a new parameter). On a ``"reason_mismatch"`` it does
nothing - no add, no commit - and returns the mismatch for
re-delegation, carrying the failure's traceback text verbatim. On a
``"wrong_kind"`` it does the same for the error - no add, no commit; a
broken test must never be committed - and returns the error's
traceback text verbatim for re-delegation to the tester. A ``"green"``
verdict is not a behaviour of ``red_step`` in this slice (behaviours
10-14 own the loop) and raises ``CycleError`` naming the verdict.
``run_cycle(repo_path, scope, behaviour, number, plan_slug, reason,
kind, runner, git, issue=None)`` is the happy path of the loop: it
delegates the RED half to ``red_step`` verbatim - a single commit
path, so the red format can never drift from ``red_step``'s - and, on
a ``"red"`` verdict, judges each green attempt with the same single
judge the red step uses: a green attempt succeeds iff
``piverdict.classify`` of the coder delegation's suite run (the same
non-empty ``reason``) returns ``"green"``. On a successful attempt it
routes the green commit through :func:`green_step` - one check, one
place: the coder delegation's result dict is handed over as the
``report`` and the red step's changed paths
(``red_result["changed_paths"]``) as ``test_paths``. Behaviour 13
(driver-side enforcement) landed: if the coder touched the cycle's
test file, ``green_step`` refuses - nothing is committed on the green
half, zero seam invocations of its own - and ``run_cycle`` returns
THAT refusal dict unchanged as the whole cycle result, the coder's
argument verbatim the cycle's terminal answer; otherwise
``green_step`` commits the green once and ``run_cycle`` returns the
completed-cycle shape with ``green_step``'s dict under ``"green"``.
Behaviour 12
(two-failed-greens-halt) landed: a failed attempt - any verdict but
``"green"`` - commits nothing, zero git calls, and carries its
failure text verbatim (the first failure entry's text, or the first
error entry's text for a wrong-kind run - the same entry
``red_step`` carries on its re-delegation paths); on the first
failure the loop re-delegates the coder ONCE with the same context
and judges attempt 2, and a second failed attempt halts it, still
with nothing committed on either green attempt, returning
``{"verdict": "halted", "behaviour": <the behaviour>,
"failure_outputs": [<attempt 1 text>, <attempt 2 text>],
"escalate_to": "architect"}`` - both texts verbatim in attempt order
and the escalation target the manager's loop-control rule names for
a second green failure. A completed cycle commits exactly twice, in
order - the red commit in the red format, then the green commit in the
green format - and returns ``{"verdict": "green", "red": <the
red step's result dict verbatim>, "green": <green_step's result
dict, ``{"verdict": "green", "committed": True, "message": <the
green message>}``>}}``. A red step
that returns anything but a genuine red (``"red"``) cannot
be committed green on and raises ``CycleError`` naming the verdict.
``ship(targeted_result, full_suite_result) -> bool`` is the ship
gate - behaviour 14
(targeted-in-loop-full-suite-before-ship) landed: it is PURE, deciding
over the two given suite runs with no runner, no git and no
delegation - "the loop itself ran only the targeted file" is a
property of the loop's running, and ``ship`` takes exactly those two
results. A run is green iff its ``errors`` AND ``failures`` are both
empty - the same criterion ``piverdict.classify``'s ``"green"``
branch uses, so "green" has one meaning in the module. Both green
returns ``True``. The refusal is a raise, not a return value, and the
targeted run is checked FIRST - a red targeted means the loop never
went green, you cannot ship what the loop has not proven, and its
``CycleError`` names ``"targeted"`` and carries the targeted run's
failure text verbatim - and only then the full suite, whose
``CycleError`` names ``"full"`` and carries the full-suite run's
failure text verbatim: a green targeted file is not a green branch.
When both are red the targeted one is raised (it is checked first).
The failure text is the module's verbatim entry - the first
``errors[0][1]`` if any, else ``failures[0][1]`` - built by
:func:`_failure_text`, which ``ship`` shares with the green half.
``green_step(repo_path, scope, behaviour, number, plan_slug, kind,
report, test_paths, git, issue=None)`` is the standalone green step
- behaviour 11 (coder-test-file-edit-is-refused) landed: it inspects
``report["changed_paths"]`` and, if any of them EQUALS an entry of
``test_paths`` - the cycle's test files, exact string comparison, no
prefix matching - commits nothing, zero seam invocations, and returns
the test-change refusal ``{"verdict": "test_change_requested",
"argument": <verbatim>}``: the test file is never edited by the
loop, a changed test is a new red step, and the coder's argument is
carried verbatim so the caller's new red step is informed by the
coder's justification. It reads ``report["argument"]`` only on that
refusal path. Otherwise it commits the green once - the message built
by ``picommit.green_message``, staged with ``picommit.add_argv`` on
the coder's changed paths and then committed with
``picommit.commit_argv``, the same builders and the same
stage-then-commit order the red step uses, so the green format cannot
drift from it - and returns ``{"verdict": "green", "committed": True,
"message": <the green message>}``. Behaviour 13 made this step the
driver's enforcement point too: ``run_cycle`` routes its green commit
through here, so the check and the commit live in exactly one place -
there is no second inline stage+commit in ``run_cycle``.

Stdlib only. One exception type: ``CycleError``.
"""

import unittest
from typing import Any, Callable, Dict, List, Optional

from anvilkit.pi import picommit
from anvilkit.pi import piverdict


class CycleError(Exception):
    """A cycle step this module could not carry out.

    A single exception type covers every failure of the cycle step, so
    callers need only one ``except`` clause. It is raised for the only
    verdict ``red_step`` does not own in this slice: a ``"green"``
    classification is a verdict for the loop, which behaviours 10-14
    own, not for the red step, and acting on one here would skip a
    green the loop must verify. (A ``"wrong_kind"`` does not raise:
    it returns the verbatim error for re-delegation and commits
    nothing.) The message names ``"green"`` as the offending verdict,
    so a failure is fixable without reading the source. ``run_cycle``
    raises it for a red step whose verdict is not ``"red"`` - a
    non-genuine red cannot be committed green on. And the ship gate
    (:func:`ship`) raises it as its refusal of a non-green suite: a
    red targeted run (naming ``"targeted"``) or, the targeted run
    being green, a red full-suite run (naming ``"full"``) - the
    refusal IS the raise, and the offending run's failure text is
    carried verbatim in the message.
    """


def red_step(
    repo_path: str,
    scope: str,
    behaviour: str,
    number: int,
    plan_slug: str,
    reason: str,
    runner: Callable[[Dict[str, Any]], Dict[str, Any]],
    git: Callable[[List[str]], None],
    issue: Optional[int] = None,
) -> Dict[str, Any]:
    """Run one red step: delegate, judge, commit once on a genuine red.

    ``repo_path`` is the repository path the git seam runs in (the
    ``git -C`` path of ``picommit.commit_argv``); ``scope``,
    ``behaviour``, ``number``, ``plan_slug`` and ``issue`` are handed
    to ``picommit.red_message`` verbatim - the same cycle identity a
    red commit is built from; ``reason`` is the stated expected-failure
    reason, handed to ``piverdict.classify`` verbatim; ``runner`` is the
    injected tester-role delegation, invoked exactly once with the
    cycle's delegation context, whose result dict carries the suite
    run's ``unittest.TestResult`` (key ``"result"``) and the changed
    file paths of the delegation (key ``"changed_paths"``); ``git`` is
    the injected git seam - a callable receiving an argv list (built
    by ``picommit``, never a shell string) and invoked for each git
    mutation.

    Behaviour 8 (red-step-commits-once-on-genuine-red): the delegation
    runs exactly once; its suite run is classified with
    ``piverdict.classify(result, reason)``. On a genuine red (verdict
    ``"red"``) the step owns the whole commit step: it stages
    ``changed_paths`` with ``picommit.add_argv(repo_path,
    changed_paths)`` and then commits with
    ``picommit.commit_argv(repo_path, message)`` - both through the
    seam, in that order, staging preceding the commit, never the other
    way round - so a genuine red commits exactly once, in the red
    format, naming the behaviour and the plan. The message is built by
    ``picommit.red_message`` with ``assertion`` the stated ``reason``,
    the ``Refs`` trailer coming from ``issue``. The result is
    ``{"verdict": "red", "committed": True, "message": <the red
    message>, "changed_paths": <the delegation's changed paths>}``:
    behaviour 13 added ``"changed_paths"`` additively - the tester
    delegation's paths, which ARE the cycle's test files - so
    :func:`run_cycle` can derive its ``test_paths`` from the red
    result without a new parameter.

    Error: a ``"reason_mismatch"`` commits nothing - no add, no commit,
    zero seam invocations - and returns
    ``{"verdict": "reason_mismatch", "redelegate": "tester",
    "failure_text": <verbatim>}``, the ``"redelegate"`` marker the
    caller uses to re-delegate and ``"failure_text"`` the traceback
    text of the first failure entry, carried verbatim so the
    re-delegation is informed by it.

    Behaviour 9 (wrong-kind-of-red-is-not-committed): a
    ``"wrong_kind"`` commits nothing - no add, no commit, zero seam
    invocations; a broken test must never be committed - and returns
    ``{"verdict": "wrong_kind", "redelegate": "tester",
    "error_text": <verbatim>}``, ``"error_text"`` the traceback text of
    the first error entry, carried verbatim so the re-delegation is
    informed by it. A ``"green"`` verdict raises ``CycleError`` naming
    it: ``"green"`` is the only verdict for the loop, not for the red
    step in this slice.
    """
    context: Dict[str, Any] = {
        "role": "tester",
        "repo_path": repo_path,
        "scope": scope,
        "behaviour": behaviour,
        "number": number,
        "plan_slug": plan_slug,
        "reason": reason,
    }
    runner_result: Dict[str, Any] = runner(context)
    result: unittest.TestResult = runner_result["result"]
    changed_paths: List[str] = list(runner_result["changed_paths"])
    verdict: str = piverdict.classify(result, reason)
    if verdict == "red":
        message: str = picommit.red_message(
            scope, behaviour, number, plan_slug, reason, issue=issue
        )
        git(picommit.add_argv(repo_path, changed_paths))
        git(picommit.commit_argv(repo_path, message))
        return {
            "verdict": "red",
            "committed": True,
            "message": message,
            "changed_paths": changed_paths,
        }
    if verdict == "reason_mismatch":
        return {
            "verdict": "reason_mismatch",
            "redelegate": "tester",
            "failure_text": result.failures[0][1],
        }
    if verdict == "wrong_kind":
        return {
            "verdict": "wrong_kind",
            "redelegate": "tester",
            "error_text": result.errors[0][1],
        }
    raise CycleError(
        "red_step does not own the 'green' verdict, the only verdict "
        "it does not own; the loop (behaviours 10-14) does"
    )


def run_cycle(
    repo_path: str,
    scope: str,
    behaviour: str,
    number: int,
    plan_slug: str,
    reason: str,
    kind: str,
    runner: Callable[[Dict[str, Any]], Dict[str, Any]],
    git: Callable[[List[str]], None],
    issue: Optional[int] = None,
) -> Dict[str, Any]:
    """Run one cycle: the red step, then the judged green step.

    ``repo_path``, ``scope``, ``behaviour``, ``number``, ``plan_slug``,
    ``reason``, ``runner`` and ``git`` mean the same as in
    :func:`red_step`; ``kind`` is the branch kind - ``"feature"`` or
    ``"bugfix"`` - handed to ``picommit.green_message`` to pick the
    green subject prefix.

    Behaviour 10 (run-cycle-commits-red-then-green): the RED half
    delegates verbatim to :func:`red_step` - a single commit path, so
    the red format can never drift from ``red_step``'s - so the
    delegation seam is invoked once with the tester role, the suite run
    is classified, and a genuine red commits exactly once in the red
    format. On a ``"red"`` verdict the cycle delegates the coder
    (the same injected ``runner``, context keyed on ``"role":
    "coder"``) and judges the attempt's suite run with
    ``piverdict.classify`` - the same single judge the red step uses,
    the same non-empty ``reason``: a green attempt succeeds iff its
    verdict is ``"green"``. On a successful attempt the cycle routes
    the green commit through :func:`green_step` - behaviour 13
    (driver-side enforcement): one check, one place, no second inline
    stage+commit - passing the coder delegation's result dict as the
    ``report`` and the red step's changed paths
    (``red_result["changed_paths"]``) as ``test_paths``. If
    :func:`green_step` refuses (the coder touched the cycle's test
    file) the cycle commits nothing on the green half and returns
    THAT refusal dict unchanged as the whole cycle result - the
    coder's argument is the cycle's terminal answer. Otherwise
    :func:`green_step` commits the green once and the cycle returns
    ``{"verdict": "green", "red": <the red step's result dict
    verbatim>, "green": <green_step's result dict,
    ``{"verdict": "green", "committed": True, "message": <the green
    message>}``>}}``. A completed cycle commits exactly twice,
    in order - the red commit precedes the green commit, and the red
    is never amended or squashed into its green.

    Behaviour 12 (two-failed-greens-halt): a failed attempt - any
    verdict but ``"green"`` - commits nothing on that attempt, zero
    seam invocations, and captures its failure text verbatim: the
    first failure entry's text, or the first error entry's text for a
    wrong-kind run - the same entry :func:`red_step` carries on its
    re-delegation paths. On the first failure the cycle re-delegates
    the coder ONCE with the same context and judges attempt 2; a
    second failed attempt halts it - still with nothing committed on
    either green attempt, the only recorded commit the red's - and
    returns
    ``{"verdict": "halted", "behaviour": <the behaviour>,
    "failure_outputs": [<attempt 1's text>, <attempt 2's text>],
    "escalate_to": "architect"}``, both texts verbatim in attempt
    order and ``escalate_to`` the escalation target the manager's
    loop-control rule names for a second green failure.

    Error: a red step that returns a verdict other than ``"red"``
    (``"reason_mismatch"`` or ``"wrong_kind"``) cannot be committed
    green on - a re-delegation is owed to the tester before any green
    - and raises ``CycleError`` naming the verdict.
    """
    red_result: Dict[str, Any] = red_step(
        repo_path,
        scope,
        behaviour,
        number,
        plan_slug,
        reason,
        runner=runner,
        git=git,
        issue=issue,
    )
    if red_result.get("verdict") != "red":
        raise CycleError(
            "run_cycle cannot commit a green on a red step that "
            "returned %r; the re-delegation is owed to the tester "
            "before any green" % (red_result.get("verdict"),)
        )
    context: Dict[str, Any] = {
        "role": "coder",
        "repo_path": repo_path,
        "scope": scope,
        "behaviour": behaviour,
        "number": number,
        "plan_slug": plan_slug,
        "reason": reason,
    }
    failure_outputs: List[str] = []
    for _attempt in (1, 2):
        runner_result: Dict[str, Any] = runner(context)
        attempt_result: unittest.TestResult = runner_result["result"]
        if piverdict.classify(attempt_result, reason) == "green":
            green_result: Dict[str, Any] = green_step(
                repo_path,
                scope,
                behaviour,
                number,
                plan_slug,
                kind,
                report=runner_result,
                test_paths=red_result["changed_paths"],
                git=git,
                issue=issue,
            )
            if green_result.get("verdict") == "test_change_requested":
                return green_result
            return {
                "verdict": "green",
                "red": red_result,
                "green": green_result,
            }
        failure_outputs.append(_failure_text(attempt_result))
    return {
        "verdict": "halted",
        "behaviour": behaviour,
        "failure_outputs": failure_outputs,
        "escalate_to": "architect",
    }


def _failure_text(result: unittest.TestResult) -> str:
    """Capture a non-green suite run's failure text, verbatim.

    A non-green run carries at least one of the two kinds the judge
    keeps apart: a wrong-kind run (``errors`` non-empty) or a
    genuine-red run (``errors`` empty, ``failures`` non-empty). This
    mirrors ``piverdict.classify``'s priority - an error outranks a
    failure - and returns the module's one verbatim entry: the first
    error entry's traceback text for a wrong-kind run, else the first
    failure entry's traceback text. The callers hand the text on
    verbatim: :func:`run_cycle`'s halt result, and :func:`ship`'s
    ``CycleError`` messages, carry what the suite run produced,
    unaltered.
    """
    if result.errors:
        return result.errors[0][1]
    return result.failures[0][1]


def ship(
    targeted_result: unittest.TestResult,
    full_suite_result: unittest.TestResult,
) -> bool:
    """Decide whether the cycle may ship: both runs green, or refuse.

    ``targeted_result`` is the suite run of the targeted file - the
    file the loop ran in the cycle - and ``full_suite_result`` is the
    suite run of the whole suite; each is the object a ``unittest``
    run produces, the same two lists ``piverdict.classify`` reads.

    Behaviour 14 (targeted-in-loop-full-suite-before-ship): the gate
    is PURE - it decides over the two given results and never acts: no
    runner, no git, no delegation. "The loop itself ran only the
    targeted file" is a property of the loop's running, and this
    function takes exactly those two results, no cycle identity.

    The green criterion is the module's one: a run is green iff its
    ``errors`` AND ``failures`` are both empty - the same test
    ``piverdict.classify``'s ``"green"`` branch makes, so "green" has
    one meaning in the module. Both runs green returns ``True``.

    Otherwise the refusal IS the raise - a ``CycleError``, not a
    return value - and the targeted run is checked FIRST: a red
    targeted means the loop never went green, and you cannot ship
    what the loop has not proven, so its message names ``"targeted"``
    and carries the targeted run's failure text verbatim (the
    module's entry - first error, else first failure - via
    :func:`_failure_text`). Only then is the full suite checked, and
    its message names ``"full"`` and carries the full-suite run's
    failure text verbatim: a green targeted file is not a green
    branch. When both runs are red the targeted one is raised, since
    it is checked first.
    """
    if targeted_result.errors or targeted_result.failures:
        raise CycleError(
            "the targeted suite is not green; the loop never went "
            "green and it cannot ship what it has not proven:\n%s"
            % _failure_text(targeted_result)
        )
    if full_suite_result.errors or full_suite_result.failures:
        raise CycleError(
            "the full suite is not green; a green targeted file is "
            "not a green branch:\n%s"
            % _failure_text(full_suite_result)
        )
    return True


def green_step(
    repo_path: str,
    scope: str,
    behaviour: str,
    number: int,
    plan_slug: str,
    kind: str,
    report: Dict[str, Any],
    test_paths: List[str],
    git: Callable[[List[str]], None],
    issue: Optional[int] = None,
) -> Dict[str, Any]:
    """Run one green step: refuse a changed test file, else commit once.

    ``repo_path``, ``scope``, ``behaviour``, ``number``, ``plan_slug``,
    ``kind``, ``git`` and ``issue`` mean the same as in
    :func:`run_cycle`'s green half (``kind`` and ``issue`` feed
    ``picommit.green_message``); ``report`` is the coder delegation's
    result dict, whose ``"changed_paths"`` are the paths the coder
    touched and whose ``"argument"`` is the coder's stated
    justification, a string; ``test_paths`` is the list of test files
    the cycle owns - the red step's changed paths - handed in so the
    refusal is checked without re-deriving them.

    Behaviour 11 (coder-test-file-edit-is-refused): the step inspects
    ``report["changed_paths"]``; if any of them EQUALS an entry of
    ``test_paths`` - exact string comparison, no prefix matching - it
    commits nothing, zero seam invocations, and returns
    ``{"verdict": "test_change_requested", "argument": <verbatim>}``:
    the test file is never edited by the loop, a changed test is a new
    red step, and the coder's argument is carried verbatim so the
    caller's new red step is informed by the coder's justification. It
    reads ``report["argument"]`` only on that refusal path.
    Otherwise it commits the green once: the message built by
    ``picommit.green_message(scope, behaviour, number, plan_slug,
    kind, issue=issue)``, staged with ``picommit.add_argv(repo_path,
    changed_paths)`` on the coder's changed paths and then committed
    with ``picommit.commit_argv(repo_path, message)`` - both through
    the seam, in that order, the same builders and the same
    stage-then-commit order the red step uses. This step is the single
    implementation of the green commit: behaviour 13 made
    :func:`run_cycle` route its green commit through here, so the
    check and the commit live in one place and the green format
    cannot drift. The result is ``{"verdict": "green",
    "committed": True, "message": <the green message>}``.
    """
    changed_paths: List[str] = list(report["changed_paths"])
    for path in changed_paths:
        if path in test_paths:
            return {
                "verdict": "test_change_requested",
                "argument": report["argument"],
            }
    message: str = picommit.green_message(
        scope, behaviour, number, plan_slug, kind, issue=issue
    )
    git(picommit.add_argv(repo_path, changed_paths))
    git(picommit.commit_argv(repo_path, message))
    return {"verdict": "green", "committed": True, "message": message}
