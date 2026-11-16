"""Tests for anvilkit.pi.picodeowners - the CODEOWNERS body builder
(behaviour 1 of plans/file-path-interactive-free-plan.md) and the
walkthrough steps builder (behaviour 2).

Every test imports the module through a guarded ``try``/``except
ImportError`` inside the test method and fails with a clear assertion
message instead of letting a collection-time ImportError mask the reason
the suite is red. The module now exists and behaviours 1-2 are
implemented; the behaviour-3 tests fail on a guarded fetch of the
not-yet-implemented ``wants_walkthrough`` attribute for the same reason.

The ``walkthrough_steps`` pins assert substance, not full strings: each
step is display text for a human following the saved pages
``doc/external/github/about-code-owners.md`` (the ``/.github/`` owner line,
the write-access requirement, the public/private availability caveat) and
``doc/external/github/available-rules-for-rulesets.md`` (the UI label
"Require review from Code Owners"). Display tokens are matched
case-insensitively as substrings within a single step (same-step pairing,
so the pin cannot pass on two unrelated steps that share one word); the
body's owner line is data, not display text, and is matched exactly.

The ``/.github/`` owner line is GitHub's own "most secure method" - it owns
the CODEOWNERS file itself: the saved page
``doc/external/github/about-code-owners.md``, section "CODEOWNERS and branch
protection" ("The most secure method is to define a CODEOWNERS file in the
`.github` directory of the repository and define the repository owner as the
owner of either the CODEOWNERS file (`/.github/CODEOWNERS @owner_username`)
or the whole directory (`/.github/ @owner_username`)").

No test writes a file or makes a network call: ``codeowners_body`` is a pure
string builder; the observable surface of it is exactly what it returns.
"""

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The exact owner line the body must carry (GitHub's "most secure method":
# owning the CODEOWNERS file itself, via the whole ``.github/`` directory).
OWNER_LINE = "/.github/ @iar3-r8"

# Minimal honest tokens for the edit-me comment, matched as substrings of the
# lowercased body: the comment must tell the reader the handle is an EDIT to
# be made, and that the real owners need WRITE access.
_EDIT = "edit"
_WRITE = "write"

_ABSENT = (
    "anvilkit/pi/picodeowners.py does not exist yet - "
    "behaviour 1 of plans/file-path-interactive-free-plan.md"
)


class CodeownersBodyTests(unittest.TestCase):
    """Behaviour 1: codeowners_body(owner) -> the CODEOWNERS text."""

    def test_codeowners_body_names_the_owner_line(self):
        """The body contains the exact ``/.github/ @iar3-r8`` owner line."""
        try:
            from anvilkit.pi import picodeowners
        except ImportError:
            self.fail(_ABSENT)

        body = picodeowners.codeowners_body("iar3-r8")

        self.assertIsInstance(body, str, "codeowners_body must return a str")
        lines = body.splitlines()
        self.assertIn(
            OWNER_LINE,
            lines,
            "the body must contain the exact owner line {!r}; got lines: "
            "{!r}".format(OWNER_LINE, lines),
        )

    def test_codeowners_body_carries_the_edit_me_comment(self):
        """The body tells the reader the handle must be edited to real write-access owners."""
        try:
            from anvilkit.pi import picodeowners
        except ImportError:
            self.fail(_ABSENT)

        body = picodeowners.codeowners_body("iar3-r8")
        lowered = body.lower()

        self.assertIn(
            _EDIT,
            lowered,
            "the body must carry a comment naming that the handle must be "
            "EDITed to real owners; got: {!r}".format(body),
        )
        self.assertIn(
            _WRITE,
            lowered,
            "the body must name that the real owners need WRITE access; "
            "got: {!r}".format(body),
        )

    def test_codeowners_body_is_deterministic(self):
        """Two calls with the same owner return the identical string."""
        try:
            from anvilkit.pi import picodeowners
        except ImportError:
            self.fail(_ABSENT)

        first = picodeowners.codeowners_body("iar3-r8")
        second = picodeowners.codeowners_body("iar3-r8")

        self.assertEqual(
            first,
            second,
            "codeowners_body must be deterministic; got two different "
            "strings: {!r} vs {!r}".format(first, second),
        )

    def test_codeowners_body_empty_owner_raises_codeowners_error(self):
        """An empty or whitespace-only owner raises CodeownersError, never a guess."""
        try:
            from anvilkit.pi import picodeowners
        except ImportError:
            self.fail(_ABSENT)
        codeowners_error = getattr(picodeowners, "CodeownersError", None)
        self.assertTrue(
            isinstance(codeowners_error, type)
            and issubclass(codeowners_error, Exception),
            "anvilkit.pi.picodeowners.CodeownersError is not an exception "
            "type; the module's single exception type (behaviour 1's error "
            "path) has not been implemented yet",
        )

        for owner in ("", "   "):
            with self.assertRaises(
                codeowners_error,
                msg="codeowners_body({!r}) must raise CodeownersError; the "
                "handle is never guessed".format(owner),
            ):
                picodeowners.codeowners_body(owner)

    def test_codeowners_body_owner_is_used_verbatim(self):
        """The owner handle appears verbatim: no quoting, escaping or case-folding."""
        try:
            from anvilkit.pi import picodeowners
        except ImportError:
            self.fail(_ABSENT)

        owner = "Some-Handle-123"

        body = picodeowners.codeowners_body(owner)

        self.assertIn(
            "@" + owner,
            body,
            "the owner must appear verbatim as @{!r} (no quoting, no "
            "shell-escaping, no case-folding); got: {!r}".format(owner, body),
        )


# Word-boundary match for "Pro" in the availability caveat, so "proper" or
# "protection" in some other step cannot satisfy the plan-tier assertion
# (doc/external/github/about-code-owners.md: "GitHub Pro, GitHub Team,
# GitHub Enterprise Cloud, and GitHub Enterprise Server").
_PRO = re.compile(r"\bpro\b", re.IGNORECASE)


class WalkthroughStepsTestCase(unittest.TestCase):
    """Shared guarded imports and fetchers for behaviour 2's pins."""

    def _picodeowners(self):
        """Import anvilkit.pi.picodeowners, failing clearly if the module is absent."""
        try:
            from anvilkit.pi import picodeowners
        except ImportError:
            self.fail(_ABSENT)
        return picodeowners

    def _get_walkthrough_steps(self):
        """Fetch ``anvilkit.pi.picodeowners.walkthrough_steps``, failing clearly if absent."""
        picodeowners = self._picodeowners()
        steps = getattr(picodeowners, "walkthrough_steps", None)
        self.assertTrue(
            callable(steps),
            "anvilkit.pi.picodeowners.walkthrough_steps is not callable; "
            "behaviour 2 of plans/file-path-interactive-free-plan.md has "
            "not been implemented yet (the module imports fine; only the "
            "function is missing)",
        )
        return steps

    def _steps(self, owner="iar3-r8", repo="anvil", branch="main"):
        """The walkthrough steps for ``owner``/``repo``/``branch`` with behaviour 1's body."""
        picodeowners = self._picodeowners()
        walkthrough_steps = self._get_walkthrough_steps()
        body = picodeowners.codeowners_body(owner)
        return walkthrough_steps(owner, repo, branch, body)

    @staticmethod
    def _first_index(steps, needle):
        """The index of the first step containing ``needle`` (case-insensitive)."""
        wanted = needle.lower()
        for index, step in enumerate(steps):
            if wanted in step.lower():
                return index
        raise AssertionError(
            "no step mentions {!r}; steps: {!r}".format(needle, steps)
        )

    @staticmethod
    def _step_with(steps, *needles):
        """The first step containing every ``needle`` (case-insensitive).

        The same-step pairing keeps the pin from passing on two unrelated
        steps that happen to share one word; raises AssertionError when no
        single step carries them all.
        """
        for step in steps:
            lowered = step.lower()
            if all(needle.lower() in lowered for needle in needles):
                return step
        raise AssertionError(
            "no single step mentions all of {!r}; steps: {!r}".format(
                needles, steps
            )
        )


class WalkthroughStepsTests(WalkthroughStepsTestCase):
    """Behaviour 2: ``walkthrough_steps(owner, repo, branch, body)`` -> the ordered six steps.

    The steps are display text for a human, built by the module from its
    inputs; the assertions pin substance and order, not the full string of
    every step.
    """

    def test_walkthrough_steps_returns_exactly_six_strings(self):
        steps = self._steps()

        self.assertIsInstance(
            steps, list, "walkthrough_steps must return a list"
        )
        self.assertEqual(
            len(steps),
            6,
            "the walkthrough must have exactly six steps; got {}: "
            "{!r}".format(len(steps), steps),
        )
        for step in steps:
            self.assertIsInstance(step, str, "each step must be a str")

    def test_walkthrough_steps_are_in_the_contracts_order(self):
        steps = self._steps()

        # One token per contract step, each first-mentioned by its own step:
        # create the file, write access, commit to the base branch, the
        # ruleset option, re-run verify-guards, the availability caveat.
        order = (
            self._first_index(steps, ".github/CODEOWNERS"),
            self._first_index(steps, "write access"),
            self._first_index(steps, "commit"),
            self._first_index(steps, "Require review from Code Owners"),
            self._first_index(steps, "verify-guards"),
            self._first_index(steps, "private"),
        )
        self.assertTrue(
            all(a < b for a, b in zip(order, order[1:])),
            "the six steps must appear in the contract's order, one token "
            "per step, each before the next; got order {!r} for steps: "
            "{!r}".format(order, steps),
        )

    def test_walkthrough_steps_create_step_names_the_file_and_embeds_the_body(self):
        steps = self._steps()
        first = steps[0]

        self.assertIn(
            ".github/CODEOWNERS",
            first,
            "the first step must name the file at .github/CODEOWNERS; got: "
            + first,
        )
        self.assertIn(
            OWNER_LINE,
            first,
            "the create step must embed behaviour 1's body - its exact "
            "owner line {!r} is data, matched verbatim; got: {}".format(
                OWNER_LINE, first
            ),
        )

    def test_walkthrough_steps_write_access_step_names_the_handle_forms(self):
        steps = self._steps()

        self._step_with(steps, "write access", "@user", "team")

    def test_walkthrough_steps_commit_step_uses_the_branch_verbatim(self):
        steps = self._steps(branch="main")

        self._step_with(steps, "commit", "main")

        release_steps = self._steps(branch="release")

        self._step_with(release_steps, "commit", "release")

    def test_walkthrough_steps_ruleset_step_names_the_code_owner_option_and_save(self):
        # The UI label is GitHub's, verbatim, per
        # doc/external/github/available-rules-for-rulesets.md.
        steps = self._steps()

        self._step_with(steps, "Require review from Code Owners", "Save")

    def test_walkthrough_steps_ruleset_step_names_the_repository(self):
        # The repo is named verbatim in the ruleset step - the step that
        # points at the repository's rulesets settings - for the default
        # repo and for a non-default one.
        steps = self._steps(repo="anvil")

        self._step_with(steps, "ruleset", "anvil")

        other = self._steps(repo="other-repo")

        self._step_with(other, "ruleset", "other-repo")

    def test_walkthrough_steps_verify_guards_step_says_the_warn_stays(self):
        # The load-bearing honesty pin: the walkthrough is a review-gate
        # mitigation, and check_file_paths verifies the push rule only, so
        # the file_paths warn persists after the walkthrough (the plan's
        # scope section, user decision 2).
        steps = self._steps()

        self._step_with(steps, "verify-guards", "warn", "stays")

    def test_walkthrough_steps_availability_step_names_the_free_plan_caveat(self):
        # doc/external/github/about-code-owners.md: code owners work in
        # public repositories on GitHub Free; a private repository needs
        # Pro, Team, Enterprise Cloud or Enterprise Server.
        steps = self._steps()

        for step in steps:
            lowered = step.lower()
            if (
                "public" in lowered
                and "free" in lowered
                and "private" in lowered
                and "team" in lowered
                and "enterprise" in lowered
                and _PRO.search(step)
            ):
                return
        self.fail(
            "a step must record that code owners work in public repos on "
            "GitHub Free and a private repo needs Pro/Team/Enterprise "
            "(doc/external/github/about-code-owners.md); steps: "
            "{!r}".format(steps),
        )

    def test_walkthrough_steps_empty_branch_raises_codeowners_error(self):
        picodeowners = self._picodeowners()
        walkthrough_steps = self._get_walkthrough_steps()
        body = picodeowners.codeowners_body("iar3-r8")

        for branch in ("", "   "):
            with self.assertRaises(
                picodeowners.CodeownersError,
                msg="walkthrough_steps must raise CodeownersError for an "
                "empty or whitespace-only branch {!r}; the base branch is "
                "never guessed".format(branch),
            ):
                walkthrough_steps("iar3-r8", "anvil", branch, body)

    def test_walkthrough_steps_happy_path_returns_without_raising(self):
        # No other exception type leaves the module: a valid
        # owner/repo/branch returns the steps, nothing raised.
        steps = self._steps(owner="octodemo", repo="other-repo", branch="release")

        self.assertIsInstance(steps, list, "walkthrough_steps must return a list")
        self.assertEqual(
            len(steps),
            6,
            "the walkthrough must have exactly six steps; got {}: "
            "{!r}".format(len(steps), steps),
        )


class WantsWalkthroughTestCase(unittest.TestCase):
   """Shared guarded imports and a finding builder for behaviour 3's pins."""

   def _picodeowners(self):
       """Import anvilkit.pi.picodeowners, failing clearly if the module is absent."""
       try:
           from anvilkit.pi import picodeowners
       except ImportError:
           self.fail(_ABSENT)
       return picodeowners

   def _get_wants_walkthrough(self):
       """Fetch ``anvilkit.pi.picodeowners.wants_walkthrough``, failing clearly if absent."""
       picodeowners = self._picodeowners()
       wants = getattr(picodeowners, "wants_walkthrough", None)
       self.assertTrue(
           callable(wants),
           "anvilkit.pi.picodeowners.wants_walkthrough is not callable; "
           "behaviour 3 of plans/file-path-interactive-free-plan.md has "
           "not been implemented yet (the module imports fine; only the "
           "function is missing)",
       )
       return wants

   @staticmethod
   def _finding(status, check, rule=None, **extra):
       """One finding in the shape ``piguard.check_all`` produces.

       ``piguard.check_file_paths`` emits exactly these keys for a warn
       (``anvilkit/pi/piguard.py``): ``status``, ``check``, ``rule``,
       ``brief``, ``danger``, ``source``, ``remedy``. ``extra`` overrides
       any of them so a pin can vary one key at a time.
       """
       finding = {
           "status": status,
           "check": check,
           "rule": rule,
           "brief": "a push can change .github/workflows/**, what CI runs",
           "danger": "the file-path restriction rule is not active",
           "source": None,
           "remedy": "turn on the file-path restriction rule",
       }
       finding.update(extra)
       return finding


class WantsWalkthroughTests(WantsWalkthroughTestCase):
   """Behaviour 3: ``wants_walkthrough(findings)`` -> the once-per-run warn predicate.

   The predicate is True iff at least one finding has ``check ==
   "file_paths"`` and ``status == "warn"``: True once for the single such
   finding, never once per finding; False for a passed, skipped or absent
   ``file_paths`` finding, and False for an empty list. A non-dict element
   or a finding missing ``check``/``status`` is ignored, never a crash.
   Pure: no network, no file, no state between calls.
   """

   def test_wants_walkthrough_true_for_a_warn_file_paths_finding(self):
       wants = self._get_wants_walkthrough()
       findings = [
           self._finding("warn", "file_paths", "file_path_restriction"),
       ]

       self.assertIs(
           wants(findings),
           True,
           "a single warn file_paths finding must yield True",
       )

   def test_wants_walkthrough_true_when_other_findings_are_present(self):
       # The guard report carries up to five branch findings plus the
       # token findings; the warn must be seen among them.
       wants = self._get_wants_walkthrough()
       findings = [
           self._finding(
               "passed",
               "history_rewrite",
               "non_fast_forward",
               brief="force pushes blocked",
               danger="",
               remedy="nothing to do",
           ),
           self._finding(
               "passed",
               "review",
               "pull_request",
               brief="review required (1 required approval)",
               danger="",
               remedy="nothing to do",
           ),
           self._finding(
               "passed",
               "update_restriction",
               "non_fast_forward",
               brief="fast-forward only",
               danger="",
               remedy="nothing to do",
           ),
           self._finding(
               "skipped",
               "file_paths",
               "file_path_restriction",
               brief="api.github.com was unreachable",
               danger="",
           ),
           self._finding("warn", "file_paths", "file_path_restriction"),
       ]

       self.assertIs(
           wants(findings),
           True,
           "the warn file_paths finding must be seen among the other "
           "branch findings",
       )

   def test_wants_walkthrough_false_for_a_passed_file_paths_finding(self):
       wants = self._get_wants_walkthrough()
       findings = [
           self._finding(
               "passed",
               "file_paths",
               "file_path_restriction",
               brief="listed paths protected (.github/workflows/**)",
               danger="",
               remedy="nothing to do - the listed paths are protected",
           ),
       ]

       self.assertIs(
           wants(findings),
           False,
           "a passed file_paths finding must not trigger the walkthrough",
       )

   def test_wants_walkthrough_false_for_a_skipped_file_paths_finding(self):
       wants = self._get_wants_walkthrough()
       findings = [
           self._finding(
               "skipped",
               "file_paths",
               "file_path_restriction",
               brief="api.github.com was unreachable",
               danger="",
           ),
       ]

       self.assertIs(
           wants(findings),
           False,
           "a skipped file_paths finding must not trigger the walkthrough",
       )

   def test_wants_walkthrough_false_when_file_paths_is_absent(self):
       wants = self._get_wants_walkthrough()
       findings = [
           self._finding(
               "warn",
               "history_rewrite",
               "deletion",
               brief="branch deletion not blocked",
               danger="main can be force-deleted",
               remedy="turn on the deletion protection rule",
           ),
           self._finding(
               "passed",
               "review",
               "pull_request",
               brief="review required (1 required approval)",
               danger="",
               remedy="nothing to do",
           ),
           self._finding(
               "passed",
               "update_restriction",
               "non_fast_forward",
               brief="fast-forward only",
               danger="",
               remedy="nothing to do",
           ),
       ]

       self.assertIs(
           wants(findings),
           False,
           "other warns must not trigger the walkthrough when the "
           "file_paths check is absent",
       )

   def test_wants_walkthrough_false_for_an_empty_list(self):
       wants = self._get_wants_walkthrough()

       self.assertIs(
           wants([]),
           False,
           "an empty findings list must yield False",
       )

   def test_wants_walkthrough_ignores_non_dict_elements(self):
       # A malformed element is ignored, never a crash: the real warn
       # among the garbage still yields True.
       wants = self._get_wants_walkthrough()
       findings = [
           "garbage",
           None,
           42,
           self._finding("warn", "file_paths", "file_path_restriction"),
       ]

       self.assertIs(
           wants(findings),
           True,
           "non-dict elements must be ignored and the real warn still "
           "seen; a crash would mean the contract is unmet",
       )

   def test_wants_walkthrough_false_for_only_malformed_elements(self):
       wants = self._get_wants_walkthrough()

       self.assertIs(
           wants(["garbage", None, 42]),
           False,
           "a list of only malformed elements must yield False, not "
           "raise",
       )

   def test_wants_walkthrough_ignores_findings_missing_check_or_status(self):
       # A dict finding without ``check`` or without ``status`` is
       # ignored: no KeyError, no TypeError.
       wants = self._get_wants_walkthrough()

       missing_check = {
           "status": "warn",
           "rule": "file_path_restriction",
           "brief": "a push can change .github/workflows/**, what CI runs",
       }
       missing_status = {
           "check": "file_paths",
           "rule": "file_path_restriction",
           "brief": "a push can change .github/workflows/**, what CI runs",
       }

       self.assertIs(
           wants([missing_check, missing_status]),
           False,
           "findings missing check or status must be ignored; a KeyError "
           "or TypeError here would break the contract",
       )

       self.assertIs(
           wants(
               [
                   missing_check,
                   missing_status,
                   self._finding("warn", "file_paths", "file_path_restriction"),
               ]
           ),
           True,
           "malformed findings must not hide a real warn file_paths "
           "finding",
       )

   def test_wants_walkthrough_is_pure_and_deterministic(self):
       # Once-per-run is at the cli layer (behaviour 4); this predicate
       # is a pure function of its argument: two calls with the same list
       # return the same answer, and neither call mutates the list.
       wants = self._get_wants_walkthrough()
       findings = [
           self._finding("warn", "file_paths", "file_path_restriction"),
       ]
       original = [dict(finding) for finding in findings]

       first = wants(findings)
       second = wants(findings)

       self.assertIs(first, True, "the first call must see the warn")
       self.assertIs(
           second,
           True,
           "a second call with the same list must return the same answer: "
           "the predicate is pure, not a stateful asked-once flag",
       )
       self.assertEqual(
           findings,
           original,
           "the predicate must not mutate the findings list",
       )


# ---------------------------------------------------------------------------
# Behaviour 11 of plans/file-path-codeowners-interactive.md: the body
# accepts the handles the user gave. The same function, the same name, one
# argument - the argument is now a string that may hold several
# whitespace-separated handles, each with or without a leading ``@``. Every
# handle is normalised to exactly one leading ``@``; order is preserved;
# each handle is used verbatim otherwise. A single handle returns today's
# one-handle line unchanged, so behaviour 1 of
# plans/file-path-interactive-free-plan.md stays green at the new boundary
# (its pins in CodeownersBodyTests above are untouched).
# ---------------------------------------------------------------------------


class MultipleOwnersBodyTests(unittest.TestCase):
    """Behaviour 11: ``codeowners_body(owners)`` with several handles in one string."""

    def _picodeowners(self):
        """Import anvilkit.pi.picodeowners, failing clearly if the module is absent."""
        try:
            from anvilkit.pi import picodeowners
        except ImportError:
            self.fail(_ABSENT)
        return picodeowners

    def test_codeowners_body_mixed_handles_gives_the_exact_normalised_owner_line(self):
        """Pin 1: "@alice bob @org/team" -> the exact owner line "/.github/ @alice @bob @org/team"."""
        picodeowners = self._picodeowners()

        body = picodeowners.codeowners_body("@alice bob @org/team")

        self.assertIn(
            "/.github/ @alice @bob @org/team",
            body.splitlines(),
            "behaviour 11: the owner line must be exactly "
            "'/.github/ @alice @bob @org/team' - every handle normalised "
            "to exactly one leading @, order preserved, used verbatim "
            "otherwise; got lines: {!r}".format(body.splitlines()),
        )

    def test_codeowners_body_double_space_and_mixed_at_normalises_to_single_spaces(self):
        """Pin 2a: "alice  @bob" (double space, mixed @) -> the exact owner line "/.github/ @alice @bob"."""
        picodeowners = self._picodeowners()

        body = picodeowners.codeowners_body("alice  @bob")

        self.assertIn(
            "/.github/ @alice @bob",
            body.splitlines(),
            "handles are split on whitespace and re-joined with single "
            "spaces, each with exactly one leading @; got lines: "
            "{!r}".format(body.splitlines()),
        )

    def test_codeowners_body_double_leading_at_normalises_to_exactly_one_at(self):
        """Pin 2b: "@@weird" -> leading @@ collapses to exactly one @ -> the exact owner line "/.github/ @weird"."""
        picodeowners = self._picodeowners()

        body = picodeowners.codeowners_body("@@weird")

        self.assertIn(
            "/.github/ @weird",
            body.splitlines(),
            "a leading @@ must normalise to exactly one leading @; got "
            "lines: {!r}".format(body.splitlines()),
        )

    def test_codeowners_body_lone_at_handle_raises_codeowners_error(self):
        """Pin 3a: a handle that is only "@" is empty after stripping the optional leading @ -> raises."""
        picodeowners = self._picodeowners()

        with self.assertRaises(
            picodeowners.CodeownersError,
            msg="codeowners_body('@') must raise CodeownersError: a handle "
            "that is only @ is empty after stripping the optional leading "
            "@, and the handle is never guessed",
        ):
            picodeowners.codeowners_body("@")

    def test_codeowners_body_trailing_lone_at_handle_raises_codeowners_error(self):
        """Pin 3b: "alice @" carries a handle that is only "@" -> raises."""
        picodeowners = self._picodeowners()

        with self.assertRaises(
            picodeowners.CodeownersError,
            msg="codeowners_body('alice @') must raise CodeownersError: the "
            "second token is a lone @, empty after stripping the optional "
            "leading @, and the handle is never guessed",
        ):
            picodeowners.codeowners_body("alice @")

    def test_codeowners_body_empty_or_whitespace_only_still_raises_codeowners_error(self):
        """Pin 4: empty or whitespace-only still raises (behaviour 1's error path, re-affirmed for the multi form)."""
        picodeowners = self._picodeowners()

        for owners in ("", "   "):
            with self.assertRaises(
                picodeowners.CodeownersError,
                msg="codeowners_body({!r}) must raise CodeownersError; the "
                "handle is never guessed".format(owners),
            ):
                picodeowners.codeowners_body(owners)

    def test_codeowners_body_preserves_handle_order_without_sorting(self):
        """Pin 5: "zeta alpha" -> the exact owner line "/.github/ @zeta @alpha" (order preserved, no sorting)."""
        picodeowners = self._picodeowners()

        body = picodeowners.codeowners_body("zeta alpha")

        self.assertIn(
            "/.github/ @zeta @alpha",
            body.splitlines(),
            "handles must keep the order the user gave, never sorted; got "
            "lines: {!r}".format(body.splitlines()),
        )

    def test_codeowners_body_single_handle_is_behaviour_1s_body_unchanged(self):
        """Pin 6: a single handle returns exactly what behaviour 1 pins - the same owner line, the same edit-me comment."""
        picodeowners = self._picodeowners()

        body = picodeowners.codeowners_body("iar3-r8")

        self.assertIn(
            OWNER_LINE,
            body.splitlines(),
            "behaviour 1's exact owner line {!r} must be unchanged at the "
            "new boundary; got lines: {!r}".format(
                OWNER_LINE, body.splitlines()
            ),
        )
        lowered = body.lower()
        self.assertIn(
            _EDIT,
            lowered,
            "the edit-me comment must be unchanged at the new boundary; "
            "got: {!r}".format(body),
        )
        self.assertIn(
            _WRITE,
            lowered,
            "the write-access comment must be unchanged at the new "
            "boundary; got: {!r}".format(body),
        )

    def test_codeowners_body_handles_reach_the_file_content_only_and_write_nothing(self):
        """Pin 7: no handle is ever substituted into anything executable - it reaches the FILE content only.

        The honest form, in three parts: the module holds no subprocess
        (it never imports one, so no handle can be substituted into
        anything executable); a call writes no file (the listing of a
        temp cwd is unchanged before and after the call); and the user's
        handles reach the returned file content as their normalised
        tokens - the owner line's tokens are exactly
        ``['/.github/', '@alice', '@bob', '@org/team']``, so each handle
        is data in the text, not an execution.
        """
        import os
        import tempfile

        picodeowners = self._picodeowners()

        self.assertIsNone(
            getattr(picodeowners, "subprocess", None),
            "anvilkit.pi.picodeowners must never import subprocess: a "
            "handle that could be substituted into an executable is not "
            "file content (behaviour 11's error clause)",
        )

        owners = "@alice bob @org/team"
        with tempfile.TemporaryDirectory() as temp_cwd:
            before = sorted(os.listdir(temp_cwd))
            original_cwd = os.getcwd()
            os.chdir(temp_cwd)
            try:
                body = picodeowners.codeowners_body(owners)
            finally:
                os.chdir(original_cwd)
            after = sorted(os.listdir(temp_cwd))

        self.assertEqual(
            before,
            after,
            "codeowners_body({!r}) must write no file: the temp cwd "
            "listing changed from {!r} to {!r}".format(owners, before, after),
        )

        content = [
            line
            for line in body.splitlines()
            if line and not line.lstrip().startswith("#")
        ]
        self.assertEqual(
            len(content),
            1,
            "the body must carry exactly one owner line; got: "
            "{!r}".format(content),
        )
        self.assertEqual(
            content[0].split(),
            ["/.github/", "@alice", "@bob", "@org/team"],
            "the user's handles must reach the file content as their "
            "normalised tokens, order preserved; the owner line's tokens "
            "are: {!r}".format(content[0].split()),
        )


# ---------------------------------------------------------------------------
# Behaviour 12 of plans/file-path-codeowners-interactive.md: the git
# commands are built, never run. ``commit_commands()`` takes no arguments
# (the path is fixed at .github/CODEOWNERS and the commit message is fixed
# text) and returns the three command strings in order. The strings are
# display text for the user to run: the module runs no subprocess and
# imports none, and nothing the user typed reaches any of them (the
# handles go into the file content via behaviour 11, never into a command).
# ---------------------------------------------------------------------------


class CommitCommandsTests(unittest.TestCase):
    """Behaviour 12: ``commit_commands()`` -> the three git command strings, built never run."""

    def _picodeowners(self):
        """Import anvilkit.pi.picodeowners, failing clearly if the module is absent."""
        try:
            from anvilkit.pi import picodeowners
        except ImportError:
            self.fail(_ABSENT)
        return picodeowners

    def test_commit_commands_returns_the_three_git_commands_in_order(self):
        """Pin 1: commit_commands() returns exactly three strings, pinned exactly, in order."""
        picodeowners = self._picodeowners()

        commands = picodeowners.commit_commands()

        self.assertIsInstance(
            commands,
            list,
            "commit_commands must return a list",
        )
        self.assertEqual(
            len(commands),
            3,
            "commit_commands must return exactly three commands; got {}: "
            "{!r}".format(len(commands), commands),
        )
        for command in commands:
            self.assertIsInstance(
                command,
                str,
                "each command must be a str; got {!r}".format(command),
            )
        self.assertEqual(
            commands,
            [
                "git add .github/CODEOWNERS",
                'git commit -m "Add CODEOWNERS for the review gate"',
                "git push",
            ],
            "behaviour 12: the three commands must be exactly the fixed "
            "strings, in order; got: {!r}".format(commands),
        )

    def test_commit_commands_every_string_is_at_most_80_characters(self):
        """Pin 2: every command is display text shown to the user and stays at most 80 characters."""
        picodeowners = self._picodeowners()

        commands = picodeowners.commit_commands()

        for command in commands:
            self.assertLessEqual(
                len(command),
                80,
                "every command is display text for the user and must stay "
                "at most 80 characters; {!r} is {} characters".format(
                    command, len(command)
                ),
            )

    def test_commit_commands_takes_no_parameters_so_no_user_input_is_interpolated(self):
        """Pin 3: the function takes no parameters, so nothing the user typed can be interpolated into a command."""
        import inspect

        picodeowners = self._picodeowners()

        parameters = inspect.signature(picodeowners.commit_commands).parameters

        self.assertEqual(
            len(parameters),
            0,
            "commit_commands must take no parameters: the path and the "
            "commit message are fixed text, so nothing the user typed can "
            "reach any command; got parameters {!r}".format(list(parameters)),
        )

    def test_commit_commands_never_run_no_subprocess_and_no_side_effect(self):
        """Pin 4: the module runs no subprocess and imports none; a call produces no side effect."""
        import os
        import tempfile

        picodeowners = self._picodeowners()

        self.assertIsNone(
            getattr(picodeowners, "subprocess", None),
            "anvilkit.pi.picodeowners must run no subprocess and import "
            "none: the command strings are display text for the user to "
            "run (behaviour 12's error clause)",
        )

        with tempfile.TemporaryDirectory() as temp_cwd:
            before = sorted(os.listdir(temp_cwd))
            original_cwd = os.getcwd()
            os.chdir(temp_cwd)
            try:
                picodeowners.commit_commands()
            finally:
                os.chdir(original_cwd)
            after = sorted(os.listdir(temp_cwd))

        self.assertEqual(
            before,
            after,
            "commit_commands() must produce no side effect: the temp cwd "
            "listing changed from {!r} to {!r}".format(before, after),
        )

    def test_commit_commands_is_deterministic(self):
        """Pin 5: two calls return equal lists."""
        picodeowners = self._picodeowners()

        first = picodeowners.commit_commands()
        second = picodeowners.commit_commands()

        self.assertEqual(
            first,
            second,
            "commit_commands must be deterministic; got two different "
            "lists: {!r} vs {!r}".format(first, second),
        )


if __name__ == "__main__":
    unittest.main()
