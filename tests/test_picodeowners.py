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


# ---------------------------------------------------------------------------
# Behaviour 13 of plans/file-path-codeowners-interactive.md: the
# self-approval step and its warning exist as text. ``last_push_step()``
# returns the extra walkthrough step naming "Require approval of the most
# recent reviewable push" (the UI rule) and ``require_last_push_approval``
# (the rulesets parameter); ``self_approval_warning(owner, repo_owner)``
# returns the one-line non-blocking advisory when the chosen owner is the
# repo owner, and None when the handles differ - the caller prints nothing.
# Neither function prompts, writes or raises. The rule facts are pinned to
# doc/external/github/about-protected-branches.md ("the most recent
# reviewable push must be approved by someone other than the person who
# pushed it") and doc/external/github/rest-api-endpoints-for-rules.md
# (the parameter name).
# ---------------------------------------------------------------------------

# The exact UI rule name and the rulesets parameter the step must name
# (doc/external/github/about-protected-branches.md;
# doc/external/github/rest-api-endpoints-for-rules.md).
_LAST_PUSH_RULE = "Require approval of the most recent reviewable push"
_LAST_PUSH_PARAM = "require_last_push_approval"

# The warning's pin tokens, all asserted on the single warning line:
# the owner named verbatim, "repo owner" (case-insensitive substring),
# "approve" and "own" as separate words (the approve-own-change idea;
# \bown\b does NOT match inside "owner"), "unless" (the option-off
# condition), and the option name itself.
_OWNER = "iar3-r8"
_REPO_OWNER = "repo owner"
_APPROVE = "approve"
_OWN_WORD = re.compile(r"\bown\b")
_OPTION_OFF = "unless"


class CodeownersPathTests(unittest.TestCase):
    """Behaviour 1 of plans/codeowners-flow-skip-existing-file.md: ``codeowners_path(target)`` -> ``target/.github/CODEOWNERS`` as a Path.

    The module imports fine (the other tests in this file prove it); each
    pin calls the attribute directly so the red state is a verbatim
    ``AttributeError`` - the builder does not exist yet. No test touches
    the network; pin 2's "no filesystem touch" is checked with a before/
    after listing of a temp base whose target subdir does not exist.
    """

    def _picodeowners(self):
        """Import anvilkit.pi.picodeowners, failing clearly if the module is absent."""
        try:
            from anvilkit.pi import picodeowners
        except ImportError:
            self.fail(_ABSENT)
        return picodeowners

    @staticmethod
    def _snapshot(root):
        """Every entry under ``root`` as a sorted list of relative path strings - a listing that ignores nothing."""
        import os

        entries = []
        for dirpath, dirnames, filenames in os.walk(str(root)):
            for name in dirnames + filenames:
                entries.append(
                    str((Path(dirpath) / name).relative_to(str(root)))
                )
        return sorted(entries)

    def test_codeowners_path_returns_the_joined_path_with_the_exact_components(self):
        """Pin 1: codeowners_path(target) == target / ".github" / "CODEOWNERS" as a Path, with the case-sensitive components pinned."""
        import tempfile

        picodeowners = self._picodeowners()

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)

            result = picodeowners.codeowners_path(target)

            self.assertIsInstance(
                result,
                Path,
                "codeowners_path must return a Path; got: "
                "{!r}".format(result),
            )
            self.assertEqual(
                result,
                target / ".github" / "CODEOWNERS",
                "codeowners_path must return target / .github / "
                "CODEOWNERS; got: {!r}".format(result),
            )
            self.assertEqual(
                list(result.parts[-2:]),
                [".github", "CODEOWNERS"],
                "the last two components must be exactly '.github' and the "
                "case-sensitive name 'CODEOWNERS' GitHub honours; got: "
                "{!r}".format(list(result.parts[-2:])),
            )

    def test_codeowners_path_is_pure_and_touches_nothing(self):
        """Pin 2: works on a target that does not exist and leaves the temp base listing unchanged - no exception, no write."""
        import tempfile

        picodeowners = self._picodeowners()

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "no-such-subdir"
            self.assertFalse(
                target.exists(),
                "the fixture must start with the target absent",
            )
            before = self._snapshot(Path(tmp))

            result = picodeowners.codeowners_path(target)

            self.assertIsInstance(result, Path)
            self.assertEqual(
                self._snapshot(Path(tmp)),
                before,
                "codeowners_path must not touch the filesystem: the temp "
                "base listing changed from {!r} to "
                "{!r}".format(before, self._snapshot(Path(tmp))),
            )

    def test_codeowners_path_is_deterministic(self):
        """Pin 3: two calls with the same target return equal paths."""
        import tempfile

        picodeowners = self._picodeowners()

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)

            first = picodeowners.codeowners_path(target)
            second = picodeowners.codeowners_path(target)

            self.assertEqual(
                first,
                second,
                "codeowners_path must be deterministic; got two different "
                "paths: {!r} vs {!r}".format(first, second),
            )

    def test_codeowners_path_joins_as_given_and_never_resolves(self):
        """Pin 4: a relative target yields a relative path with the given prefix parts verbatim; an absolute target yields an absolute path whose given prefix is preserved."""
        picodeowners = self._picodeowners()

        relative_target = Path("somewhere")
        relative_result = picodeowners.codeowners_path(relative_target)

        self.assertFalse(
            relative_result.is_absolute(),
            "a relative target must be joined as given and never resolved "
            "to absolute; got: {!r}".format(relative_result),
        )
        self.assertEqual(
            list(relative_result.parts),
            ["somewhere", ".github", "CODEOWNERS"],
            "the relative result's parts must be exactly the given "
            "prefix, '.github' and 'CODEOWNERS'; got: "
            "{!r}".format(list(relative_result.parts)),
        )

        absolute_target = Path("/definitely/not/real/abs-target")
        absolute_result = picodeowners.codeowners_path(absolute_target)

        self.assertTrue(
            absolute_result.is_absolute(),
            "an absolute target must stay absolute; got: "
            "{!r}".format(absolute_result),
        )
        self.assertTrue(
            str(absolute_result).startswith(str(absolute_target)),
            "the given absolute prefix must be preserved verbatim (never "
            "resolved or normalised away); got: {!r}".format(absolute_result),
        )


class SelfApprovalTextTests(unittest.TestCase):
    """Behaviour 13: ``last_push_step()`` and ``self_approval_warning(owner, repo_owner)`` as display text.

    Both functions are pure text builders: the module holds no subprocess
    (so nothing prompts, executes or writes), the calls are side-effect
    free, and the differing/None cases return None without raising.
    """

    def _picodeowners(self):
        """Import anvilkit.pi.picodeowners, failing clearly if the module is absent."""
        try:
            from anvilkit.pi import picodeowners
        except ImportError:
            self.fail(_ABSENT)
        return picodeowners

    def _expect_none(self, picodeowners, owner, repo):
        """Assert ``self_approval_warning(owner, repo)`` returns None, raising a clear failure if it raises."""
        try:
            result = picodeowners.self_approval_warning(owner, repo)
        except Exception as exc:
            self.fail(
                "self_approval_warning({!r}, {!r}) raised {}; the "
                "differing-handles case must return None without "
                "raising".format(owner, repo, exc)
            )
        self.assertIs(
            result,
            None,
            "self_approval_warning({!r}, {!r}) must return None when the "
            "handles differ (the caller prints nothing); got: "
            "{!r}".format(owner, repo, result),
        )

    def test_last_push_step_names_the_rule_and_the_rulesets_parameter(self):
        """Pin 1: the step names "Require approval of the most recent reviewable push" and require_last_push_approval."""
        picodeowners = self._picodeowners()

        step = picodeowners.last_push_step()

        self.assertIsInstance(step, str, "last_push_step must return a str")
        self.assertIn(
            _LAST_PUSH_RULE,
            step,
            "the step must name the UI rule verbatim {!r} "
            "(doc/external/github/about-protected-branches.md); got: "
            "{!r}".format(_LAST_PUSH_RULE, step),
        )
        self.assertIn(
            _LAST_PUSH_PARAM,
            step,
            "the step must name the rulesets parameter {!r} "
            "(doc/external/github/rest-api-endpoints-for-rules.md); got: "
            "{!r}".format(_LAST_PUSH_PARAM, step),
        )

    def test_last_push_step_every_line_is_at_most_80_characters(self):
        """Pin 1: the step is display text; every line stays at most 80 characters."""
        picodeowners = self._picodeowners()

        step = picodeowners.last_push_step()

        for line in step.splitlines():
            self.assertLessEqual(
                len(line),
                80,
                "every line of the step must stay at most 80 characters; "
                "this line is {}: {!r}".format(len(line), line),
            )

    def test_self_approval_warning_for_the_repo_owner_is_one_line_naming_owner_and_option(self):
        """Pin 2: owner == repo_owner -> exactly one line, at most 80 chars, naming the owner, 'repo owner', approve + own, 'unless' and the option name."""
        picodeowners = self._picodeowners()

        warning = picodeowners.self_approval_warning(_OWNER, _OWNER)

        self.assertIsInstance(
            warning,
            str,
            "self_approval_warning must return a str when the owner is "
            "the repo owner",
        )
        self.assertNotIn(
            "\n",
            warning,
            "the warning is exactly one line (no \\n inside); got: "
            "{!r}".format(warning),
        )
        self.assertLessEqual(
            len(warning),
            80,
            "the one-line warning is display text and must stay at most "
            "80 characters; it is {}: {!r}".format(len(warning), warning),
        )
        self.assertIn(
            _OWNER,
            warning,
            "the warning must name the owner {!r} verbatim; got: "
            "{!r}".format(_OWNER, warning),
        )
        self.assertIn(
            _REPO_OWNER,
            warning.lower(),
            "the warning must say the owner is the repo owner (pin "
            "{!r}, case-insensitive); got: {!r}".format(_REPO_OWNER, warning),
        )
        self.assertIn(
            _APPROVE,
            warning.lower(),
            "the warning must carry the approve-own-change idea (pin "
            "{!r}); got: {!r}".format(_APPROVE, warning),
        )
        self.assertTrue(
            _OWN_WORD.search(warning),
            "the warning must carry the approve-own-change idea: {!r} as "
            "its own word (not merely inside 'owner') on the same line as "
            "'approve'; got: {!r}".format(_OWN_WORD.pattern, warning),
        )
        self.assertIn(
            _OPTION_OFF,
            warning.lower(),
            "the warning must reference the option being off (pin "
            "{!r}); got: {!r}".format(_OPTION_OFF, warning),
        )
        self.assertIn(
            _LAST_PUSH_PARAM,
            warning,
            "the warning must name the option {!r} it is weak without "
            "(doc/external/github/rest-api-endpoints-for-rules.md); got: "
            "{!r}".format(_LAST_PUSH_PARAM, warning),
        )

    def test_self_approval_warning_returns_none_when_handles_differ(self):
        """Pin 3: ('alice', 'bob') -> None, no raise - the caller prints nothing."""
        picodeowners = self._picodeowners()

        self._expect_none(picodeowners, "alice", "bob")

    def test_self_approval_warning_normalises_case_and_leading_at(self):
        """Pin 4: comparison is case-insensitive with @ stripped - both directions of ("@Alice", "alice") warn."""
        picodeowners = self._picodeowners()

        for owner, repo in (("@Alice", "alice"), ("alice", "@Alice")):
            with self.subTest(owner=owner, repo=repo):
                warning = picodeowners.self_approval_warning(owner, repo)
                self.assertIsInstance(
                    warning,
                    str,
                    "self_approval_warning({!r}, {!r}) must return the "
                    "warning: the comparison is case-insensitive with @ "
                    "stripped; got: {!r}".format(owner, repo, warning),
                )

    def test_self_approval_warning_team_handle_never_matches_a_user(self):
        """Pin 5: an @org/team handle is not a user identity - ('org/team', 'team') -> None, and an owner containing '/' never warns even on an exact match."""
        picodeowners = self._picodeowners()

        self._expect_none(picodeowners, "org/team", "team")
        self._expect_none(picodeowners, "@org/team", "@org/team")

    def test_neither_function_prompts_writes_or_raises(self):
        """Pin 6: the module imports no subprocess, and neither call writes a file in a temp cwd (no prompt, no write, no raise)."""
        import os
        import tempfile

        picodeowners = self._picodeowners()

        self.assertIsNone(
            getattr(picodeowners, "subprocess", None),
            "anvilkit.pi.picodeowners must never import subprocess: these "
            "functions prompt, write and execute nothing "
            "(behaviour 13's error clause)",
        )

        with tempfile.TemporaryDirectory() as temp_cwd:
            before = sorted(os.listdir(temp_cwd))
            original_cwd = os.getcwd()
            os.chdir(temp_cwd)
            try:
                picodeowners.last_push_step()
                picodeowners.self_approval_warning(_OWNER, _OWNER)
                picodeowners.self_approval_warning("alice", "bob")
            finally:
                os.chdir(original_cwd)
            after = sorted(os.listdir(temp_cwd))

        self.assertEqual(
            before,
            after,
            "last_push_step() and self_approval_warning(...) must write "
            "no file: the temp cwd listing changed from {!r} to "
            "{!r}".format(before, after),
        )


# ---------------------------------------------------------------------------
# Behaviour 17 of plans/file-path-codeowners-interactive.md: the write
# seam. ``write_codeowners(path, body)`` is the ONLY function in the
# module that writes: it writes ``body`` UTF-8 verbatim to the full
# target path (e.g. ``target/.github/CODEOWNERS``), creates the parent
# directory if absent, and returns the path. An existing file is never
# clobbered; a directory at the path or an unwritable parent raises
# ``CodeownersError`` and leaves nothing partial; no other exception
# type leaves the module. The seam follows the
# ``anvilkit/pi/piruleset.py::write_ruleset`` precedent (one exception
# type per module). The fake target is a temp dir: no test touches the
# network, the real Docker daemon or $HOME, and the only tree the
# function may touch is the given target.
# ---------------------------------------------------------------------------

# A body carrying non-ASCII text so the UTF-8 pin is load-bearing: the
# em dash encodes to three UTF-8 bytes (b"\xe2\x80\x94"), so a write in
# any other encoding cannot match the pinned bytes.
_WRITE_BODY = (
    "# CODEOWNERS \u2014 pre-filled; edit the handle below to the real\n"
    "# owners, who need explicit write access to the repository.\n"
    "/.github/ @iar3-r8\n"
)


class WriteCodeownersTests(unittest.TestCase):
    """Behaviour 17: ``write_codeowners(path, body)`` -> the body UTF-8 verbatim at ``path``, the parent created if absent, ``path`` returned."""

    def _picodeowners(self):
        """Import anvilkit.pi.picodeowners, failing clearly if the module is absent."""
        try:
            from anvilkit.pi import picodeowners
        except ImportError:
            self.fail(_ABSENT)
        return picodeowners

    @staticmethod
    def _snapshot(root):
        """Every entry under ``root`` as a sorted list of relative path strings - a listing that ignores nothing."""
        import os

        entries = []
        for dirpath, dirnames, filenames in os.walk(str(root)):
            for name in dirnames + filenames:
                entries.append(
                    str((Path(dirpath) / name).relative_to(str(root)))
                )
        return sorted(entries)

    def test_write_codeowners_writes_verbatim_utf8_creates_parent_returns_path(self):
        """Pin 1: parent absent -> the file exists with exactly body.encode("utf-8"), the parent dir is created, and the returned value is the path as a Path."""
        import tempfile

        picodeowners = self._picodeowners()

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            path = target / ".github" / "CODEOWNERS"
            self.assertFalse(
                path.parent.exists(),
                "the fixture must start with the parent dir absent",
            )

            result = picodeowners.write_codeowners(path, _WRITE_BODY)

            self.assertIsInstance(
                result,
                Path,
                "write_codeowners must return the path as a Path; got: "
                "{!r}".format(result),
            )
            self.assertEqual(
                result,
                path,
                "write_codeowners must return the exact path it wrote to; "
                "got: {!r}".format(result),
            )
            self.assertTrue(
                path.is_file(),
                "the CODEOWNERS file must exist at the full target path "
                "{!r}".format(path),
            )
            self.assertEqual(
                path.read_bytes(),
                _WRITE_BODY.encode("utf-8"),
                "the file must hold the body UTF-8 verbatim, byte for "
                "byte; got: {!r}".format(path.read_bytes()),
            )

    def test_write_codeowners_never_clobbers_an_existing_file(self):
        """Pin 2: a pre-existing file at the path is never clobbered - CodeownersError names the path, and the original bytes survive the failed call unchanged."""
        import tempfile

        picodeowners = self._picodeowners()

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            path = target / ".github" / "CODEOWNERS"
            original = b"pre-existing bytes that must survive\n"
            path.parent.mkdir(parents=True)
            path.write_bytes(original)

            with self.assertRaises(
                picodeowners.CodeownersError,
                msg="an existing file at the path must raise "
                "CodeownersError; it is never clobbered",
            ) as ctx:
                picodeowners.write_codeowners(path, _WRITE_BODY)

            self.assertIn(
                str(path),
                str(ctx.exception),
                "the CodeownersError must name the path {!r}; message: "
                "{!r}".format(str(path), str(ctx.exception)),
            )
            self.assertEqual(
                path.read_bytes(),
                original,
                "the existing file's bytes must be untouched after the "
                "failed call; got: {!r}".format(path.read_bytes()),
            )

    def test_write_codeowners_raises_when_the_path_is_a_directory(self):
        """Pin 3: a directory at the path raises CodeownersError and leaves nothing partial - the directory is still a directory and no file is created."""
        import tempfile

        picodeowners = self._picodeowners()

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            path = target / ".github" / "CODEOWNERS"
            path.mkdir(parents=True)

            with self.assertRaises(
                picodeowners.CodeownersError,
                msg="a directory at the path must raise CodeownersError; "
                "a write to a directory must never silently succeed",
            ):
                picodeowners.write_codeowners(path, _WRITE_BODY)

            self.assertTrue(
                path.is_dir(),
                "nothing partial: the path must still be a directory "
                "after the failed call",
            )
            self.assertFalse(
                path.is_file(),
                "nothing partial: no file may be created at the path",
            )
            self.assertEqual(
                self._snapshot(target),
                [".github", ".github/CODEOWNERS"],
                "nothing partial: the failed call must add no entries "
                "under the target; got: {!r}".format(self._snapshot(target)),
            )

    def test_write_codeowners_raises_when_the_parent_cannot_be_created(self):
        """Pin 4: an unwritable parent raises CodeownersError and leaves nothing partial.

        Root-independent construction: the path's grandparent
        (``target/blocker``) is a regular file, so its parent
        (``target/blocker/sub``) can never be created - the filesystem
        refuses to make a directory under a file (NotADirectoryError)
        regardless of privileges. A chmod 0o500 on the parent would be
        ignored when the suite runs as root, making the test
        non-deterministic in CI; this construction is not.
        """
        import tempfile

        picodeowners = self._picodeowners()

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            blocker = target / "blocker"
            blocker_bytes = b"i am a file, not a directory"
            blocker.write_bytes(blocker_bytes)
            path = target / "blocker" / "sub" / "CODEOWNERS"

            with self.assertRaises(
                picodeowners.CodeownersError,
                msg="an unwritable parent (a file where a directory is "
                "needed) must raise CodeownersError; no other exception "
                "type may leave the module",
            ):
                picodeowners.write_codeowners(path, _WRITE_BODY)

            self.assertFalse(
                (target / "blocker" / "sub").exists(),
                "nothing partial: the un-creatable parent dir must not "
                "exist after the failed call",
            )
            self.assertFalse(
                path.exists(),
                "nothing partial: no file may exist at the path",
            )
            self.assertEqual(
                blocker.read_bytes(),
                blocker_bytes,
                "the blocking file must be untouched after the failed "
                "call; got: {!r}".format(blocker.read_bytes()),
            )

    def test_write_codeowners_touches_only_the_given_target_tree(self):
        """Pin 5: the only thing touched is the given target tree - the new entries under target are exactly the parent dir + the file (only the file if the parent pre-existed), and a sentinel tree outside the target is unchanged."""
        import tempfile

        picodeowners = self._picodeowners()

        with tempfile.TemporaryDirectory() as tmp_target, \
             tempfile.TemporaryDirectory() as tmp_sentinel:
            target = Path(tmp_target)
            sentinel = Path(tmp_sentinel)
            (sentinel / "sentinel-file").write_bytes(b"untouched")
            sentinel_before = self._snapshot(sentinel)

            path = target / ".github" / "CODEOWNERS"
            before = self._snapshot(target)

            picodeowners.write_codeowners(path, _WRITE_BODY)

            after = self._snapshot(target)
            new_entries = [entry for entry in after if entry not in before]
            self.assertEqual(
                new_entries,
                [".github", ".github/CODEOWNERS"],
                "the only new entries under the target must be exactly "
                "the parent dir and the file; got: {!r}".format(
                    new_entries
                ),
            )
            self.assertEqual(
                after,
                [".github", ".github/CODEOWNERS"],
                "the target tree after the write must be exactly the "
                "parent dir and the file; got: {!r}".format(after),
            )
            self.assertEqual(
                self._snapshot(sentinel),
                sentinel_before,
                "nothing outside the target tree may be touched: the "
                "sentinel listing changed from {!r} to "
                "{!r}".format(sentinel_before, self._snapshot(sentinel)),
            )

        # The at-most-parent pin: with the parent dir pre-existing, the
        # write adds exactly one entry - the file.
        with tempfile.TemporaryDirectory() as tmp_target:
            target = Path(tmp_target)
            (target / ".github").mkdir()
            before = self._snapshot(target)

            picodeowners.write_codeowners(
                target / ".github" / "CODEOWNERS", _WRITE_BODY
            )

            new_entries = [
                entry
                for entry in self._snapshot(target)
                if entry not in before
            ]
            self.assertEqual(
                new_entries,
                [".github/CODEOWNERS"],
                "with the parent dir pre-existing, the write may create "
                "at most its file - no other entry; got: "
                "{!r}".format(new_entries),
            )

    def test_write_codeowners_only_codeowners_error_leaves_the_module(self):
        """Pin 6: in every error case the raised exception is specifically CodeownersError - not OSError, FileNotFoundError, IsADirectoryError or PermissionError leaking out."""
        import tempfile

        picodeowners = self._picodeowners()

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            cases = {}

            clobber = target / ".github" / "CODEOWNERS"
            clobber.parent.mkdir(parents=True)
            clobber.write_bytes(b"original")
            cases["clobber"] = lambda: picodeowners.write_codeowners(
                clobber, _WRITE_BODY
            )

            directory = target / "asis" / "CODEOWNERS"
            directory.mkdir(parents=True)
            cases["directory"] = lambda: picodeowners.write_codeowners(
                directory, _WRITE_BODY
            )

            blocker = target / "blocker"
            blocker.write_bytes(b"file")
            blocked = target / "blocker" / "sub" / "CODEOWNERS"
            cases["unwritable-parent"] = (
                lambda: picodeowners.write_codeowners(blocked, _WRITE_BODY)
            )

            for name, fn in cases.items():
                with self.subTest(case=name):
                    try:
                        fn()
                    except picodeowners.CodeownersError:
                        # The one and only exception type the module
                        # may raise.
                        pass
                    except Exception as exc:
                        self.fail(
                            "case {!r}: a non-CodeownersError leaked out "
                            "of the module: {!r} ({}); only "
                            "CodeownersError may leave the "
                            "module".format(name, exc, type(exc).__name__)
                        )
                    else:
                        self.fail(
                            "case {!r}: no exception raised; the error "
                            "path must raise CodeownersError".format(name)
                        )


if __name__ == "__main__":
    unittest.main()
