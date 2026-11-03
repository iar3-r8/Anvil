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
10 and 11 of ``plans/pi-phase9-redgreen.md`` are implemented here:
``red_step(repo_path, scope, behaviour, number, plan_slug, reason,
runner, git, issue=None)`` invokes the injected tester delegation
exactly once, classifies its suite run with
``piverdict.classify(result, reason)``, and on a genuine red
(``"red"``) stages the delegation's changed paths with
``picommit.add_argv`` and then commits with ``picommit.commit_argv`` in
the red message built by ``picommit.red_message`` - both through the
seam, in that order, so the red step owns the whole commit step and a
genuine red commits exactly once. On a ``"reason_mismatch"`` it does
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
a ``"red"`` verdict, runs ONE coder delegation (the same injected
``runner``, context keyed on ``"role": "coder"``) and commits the
green: the green message built by
``picommit.green_message(scope, behaviour, number, plan_slug, kind,
issue=issue)``, staged with ``picommit.add_argv`` on the coder
delegation's changed paths and then committed with
``picommit.commit_argv``, the same stage-then-commit order the red
step uses. A completed cycle commits exactly twice, in order - the
red commit in the red format, then the green commit in the green
format - and returns ``{"verdict": "green", "red": <the red step's
result dict verbatim>, "green": {"committed": True, "message": <the
green message>}}``. In this slice ``run_cycle`` does not re-judge the
coder's suite run: no ``piverdict.classify`` call on the coder's
result, no halt on a non-green coder run, no test-file-edit refusal,
no double-green halt, no failure-path zero-commit logic - the loop's
termination and failure handling are behaviours 12-14, which have not
landed yet; its green half stays inlined as behaviour 10 left it,
and a later behaviour reshapes it to delegate to ``green_step``. A
red step that returns anything but a genuine red (``"red"``) cannot
be committed green on and raises ``CycleError`` naming the verdict.
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
coder's justification. Otherwise it commits the green once - the
message built by ``picommit.green_message``, staged with
``picommit.add_argv`` on the coder's changed paths and then committed
with ``picommit.commit_argv``, the same builders and the same
stage-then-commit order ``run_cycle``'s inline green half uses, so
the format cannot drift from it - and returns ``{"verdict": "green",
"committed": True, "message": <the green message>}``.

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
    so a failure is fixable without reading the source.
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
    message>}``.

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
        return {"verdict": "red", "committed": True, "message": message}
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
    """Run one cycle: the red step, then one green commit.

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
    format. On a ``"red"`` verdict the cycle runs ONE coder delegation
    - the same injected ``runner``, invoked with the cycle's delegation
    context keyed on ``"role": "coder"`` - and commits the green: the
    message built by
    ``picommit.green_message(scope, behaviour, number, plan_slug,
    kind, issue=issue)``, staged with ``picommit.add_argv(repo_path,
    coder_changed_paths)`` on the coder delegation's changed paths and
    then committed with ``picommit.commit_argv(repo_path,
    green_message)`` - both through the seam, in that order, the same
    stage-then-commit order the red step uses. A completed cycle
    commits exactly twice, in order - the red commit precedes the
    green commit, and the red is never amended or squashed into its
    green. The result is
    ``{"verdict": "green", "red": <the red step's result dict
    verbatim>, "green": {"committed": True, "message": <the green
    message>}}``.

    In this slice the green step does NOT call
    ``piverdict.classify`` again: no re-judgement of the coder's suite
    run, no halt on a non-green coder run - the loop's termination and
    failure handling are behaviours 11-14, which have not landed yet.

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
    runner_result: Dict[str, Any] = runner(context)
    coder_changed_paths: List[str] = list(runner_result["changed_paths"])
    green_msg: str = picommit.green_message(
        scope, behaviour, number, plan_slug, kind, issue=issue
    )
    git(picommit.add_argv(repo_path, coder_changed_paths))
    git(picommit.commit_argv(repo_path, green_msg))
    return {
        "verdict": "green",
        "red": red_result,
        "green": {"committed": True, "message": green_msg},
    }


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
    caller's new red step is informed by the coder's justification.
    Otherwise it commits the green once: the message built by
    ``picommit.green_message(scope, behaviour, number, plan_slug,
    kind, issue=issue)``, staged with ``picommit.add_argv(repo_path,
    changed_paths)`` on the coder's changed paths and then committed
    with ``picommit.commit_argv(repo_path, message)`` - both through
    the seam, in that order, the same builders and the same
    stage-then-commit order ``run_cycle``'s inline green half uses, so
    the green format cannot drift from it. The result is
    ``{"verdict": "green", "committed": True, "message": <the green
    message>}``.
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
