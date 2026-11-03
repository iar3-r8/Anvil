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
cycle, and the docstring says which ones have landed. Behaviour 8 of
``plans/pi-phase9-redgreen.md`` is implemented here:
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
re-delegation, carrying the failure's traceback text verbatim. A
``"green"`` or ``"wrong_kind"`` verdict is not a behaviour of
``red_step`` in this slice (behaviours 9-14 own the loop) and raises
``CycleError`` naming the verdict. ``run_cycle`` and ``green_step``
have not landed yet.

Stdlib only. One exception type: ``CycleError``.
"""

import unittest
from typing import Any, Callable, Dict, List, Optional

from anvilkit.pi import picommit
from anvilkit.pi import piverdict


class CycleError(Exception):
    """A cycle step this module could not carry out.

    A single exception type covers every failure of the cycle step, so
    callers need only one ``except`` clause. Behaviour 8 raises it for
    a verdict ``red_step`` does not own in this slice: a ``"green"`` or
    ``"wrong_kind"`` classification is a verdict for the loop, which
    behaviours 9-14 own, not for the red step, and acting on one here
    would commit a wrong-kind red or skip a green the loop must
    verify. Every message names the offending verdict, so a failure is
    fixable without reading the source.
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
    re-delegation is informed by it. A ``"green"`` or ``"wrong_kind"``
    verdict raises ``CycleError`` naming the verdict: those are
    verdicts for the loop, not for the red step in this slice.
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
    raise CycleError(
        "red_step does not own verdict %r; the loop (behaviours 9-14) "
        "does" % verdict
    )
