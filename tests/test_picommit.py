"""Tests for ``anvilkit.pi.picommit`` - the red/green commit message and
git argv builder.

``plans/pi-phase9-redgreen.md``, behaviour 5 (red-message-format): given
a scope, behaviour name, number, plan slug, assertion and issue number,
``picommit.red_message(...)`` builds - it never executes - the red commit
message in the format pinned by the plan's interface-facts:

    subject ``test({scope}): cover {behaviour}, failing``
    blank line
    body ``Behaviour {n} of plans/{task-slug}.md; fails: {assertion}.``
    blank line
    ``Refs #{issue}`` trailer (omitted entirely when there is no issue)

Error: an empty scope or behaviour raises ``CommitError`` naming the
offending field.

``plans/pi-phase9-redgreen.md``, behaviour 6 (green-message-format):
given the same inputs as behaviour 5 plus the branch kind,
``picommit.green_message(...)`` builds - it never executes - the green
commit message in the house format (``.roo/rules-tdd-manager/
instructions.xml``, green_format):

    subject ``feat({scope}): {behaviour}`` for a feature,
            ``fix({scope}): {behaviour}`` for a bugfix
    blank line
    body ``Behaviour {n} of plans/{task-slug}.md. Green.``
    blank line
    ``Refs #{issue}`` trailer (omitted entirely when there is no issue)

The trailer follows the same rule as the red: an intake reference as
a trailer, omitted when the intake had no issue; a bugfix uses
``fix`` for the green. The body line ends ``Green.``; the message as
a whole ends with the trailer when one is present.

Error: an unknown branch kind raises ``CommitError`` naming it; and
"failing" never appears in a green message, since it is what keeps
the red distinct from its green in history.

**Signature, confirmed by the manager:**

    green_message(scope, behaviour, number, plan_slug, kind,
                  issue=None) -> str

with ``kind`` the branch kind, ``"feature"`` or ``"bugfix"`` (the
plan's own header and the ``feat(``/``fix(`` subjects pin the two
values, though not the parameter name), mirroring behaviour 5's
signature plus the ``kind`` before the trailing ``issue``.

``anvilkit/pi/picommit.py`` now exists (behaviour 5 landed), so the
behaviour-6 class imports it normally at module top level. The
behaviour-5 classes keep the lazy ``_picommit()`` import from the
original red step; they are unchanged and still pass.
"""

import importlib
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
   sys.path.insert(0, str(REPO_ROOT))

from anvilkit.pi import picommit  # noqa: E402  (module exists: B5 landed)

# The inputs of behaviour 5, each a module constant so the expected
# message below is reproducible by eye. The plan file is
# plans/pi-phase9-redgreen.md, hence plan slug "pi-phase9-redgreen";
# the issue is #56 per the plan header. The assertion is the actual
# failing assertion of this red step: the module import.
SCOPE = "pi"
BEHAVIOUR = "red-message-format"
NUMBER = 5
PLAN_SLUG = "pi-phase9-redgreen"
ASSERTION = "No module named 'anvilkit.pi.picommit'"
ISSUE = 56

# The inputs of behaviour 6, each a module constant so the expected
# message below is reproducible by eye. The scope, plan slug and issue
# are the same as behaviour 5's; the branch kind is the new input.
# "feature" and "bugfix" are the plan's two pinned branch-kind values.
GREEN_BEHAVIOUR = "green-message-format"
GREEN_NUMBER = 6
KIND_FEATURE = "feature"
KIND_BUGFIX = "bugfix"
# A kind the plan does not pin - the error rule must name it.
KIND_UNKNOWN = "hotfix"


class RedMessageFormatTestCase(unittest.TestCase):
    """Behaviour 5 (red-message-format): the built message has exactly
    the pinned line structure - subject, blank line, body, blank line,
    ``Refs #{issue}`` trailer - and a missing issue omits the trailer
    entirely (no blank-line-only tail). The import happens inside the
    tests (``_picommit``) rather than at module top level, so while
    ``anvilkit/pi/picommit.py`` does not exist the tests fail at the
    import step (``ModuleNotFoundError``) instead of breaking
    collection of the file.
    """

    def _picommit(self):
        """Import ``anvilkit.pi.picommit``."""
        return importlib.import_module("anvilkit.pi.picommit")

    def test_red_message_with_issue_has_full_trailer(self) -> None:
        # Arrange: the givens of behaviour 5, all six of them.
        # Act
        picommit = self._picommit()
        message = picommit.red_message(
            SCOPE, BEHAVIOUR, NUMBER, PLAN_SLUG, ASSERTION, ISSUE
        )

        # Assert: the exact line structure, pinned line by line.
        expected_lines = [
            "test(pi): cover red-message-format, failing",
            "",
            "Behaviour 5 of plans/pi-phase9-redgreen.md; fails: "
            "No module named 'anvilkit.pi.picommit'.",
            "",
            "Refs #56",
        ]
        self.assertEqual(
            message.splitlines(),
            expected_lines,
            "the red message must be subject, blank, body, blank, "
            "Refs trailer; got: %r" % message,
        )

    def test_red_message_without_issue_omits_trailer_entirely(self) -> None:
        # Arrange: the same givens with no issue - ``issue=None`` is
        # the proposed spelling of "missing" (see module docstring).
        # Act
        picommit = self._picommit()
        message = picommit.red_message(
            SCOPE, BEHAVIOUR, NUMBER, PLAN_SLUG, ASSERTION, None
        )

        # Assert: subject, blank, body - and nothing after it. A
        # blank-line-only tail would be a trailer stub, which the plan
        # forbids ("omits the trailer entirely").
        expected_lines = [
            "test(pi): cover red-message-format, failing",
            "",
            "Behaviour 5 of plans/pi-phase9-redgreen.md; fails: "
            "No module named 'anvilkit.pi.picommit'.",
        ]
        self.assertEqual(
            message.splitlines(),
            expected_lines,
            "without an issue the trailer and its blank line must be "
            "absent; got: %r" % message,
        )


class RedMessageValidationErrorTestCase(unittest.TestCase):
    """Behaviour 5's error rule: an empty scope or behaviour raises
    ``CommitError`` naming the offending field - a message built from
    an empty scope or behaviour would be malformed history. The import
    happens inside the tests for the same reason as in
    ``RedMessageFormatTestCase``: the module does not exist yet.
    """

    def _picommit(self):
        """Import ``anvilkit.pi.picommit``."""
        return importlib.import_module("anvilkit.pi.picommit")

    def test_red_message_empty_scope_raises_commit_error_naming_scope(
        self,
    ) -> None:
        # Arrange / Act
        picommit = self._picommit()

        # Assert
        with self.assertRaises(picommit.CommitError) as ctx:
            picommit.red_message(
                "", BEHAVIOUR, NUMBER, PLAN_SLUG, ASSERTION, ISSUE
            )
        message = str(ctx.exception)
        self.assertIn(
            "scope",
            message,
            "the error must name the empty scope; got: %r" % message,
        )

    def test_red_message_empty_behaviour_raises_commit_error_naming_behaviour(
        self,
    ) -> None:
        # Arrange / Act
        picommit = self._picommit()

        # Assert
        with self.assertRaises(picommit.CommitError) as ctx:
            picommit.red_message(
                SCOPE, "", NUMBER, PLAN_SLUG, ASSERTION, ISSUE
            )
        message = str(ctx.exception)
        self.assertIn(
            "behaviour",
            message,
            "the error must name the empty behaviour; got: %r"
            % message,
        )


class GreenMessageFormatTestCase(unittest.TestCase):
    """Behaviour 6 (green-message-format): the built message has
    exactly the house line structure - ``feat``/``fix`` subject, blank
    line, body ending ``Green.``, blank line, ``Refs #{issue}``
    trailer - with the trailer omitted entirely when there is no
    issue, and "failing" never appearing, so a green stays distinct
    from its red in history. The module exists (behaviour 5 landed),
    so ``picommit`` is the top-level import; the red for this step is
    the missing ``green_message`` attribute.

    Written against the CONFIRMED signature (see module docstring):
    ``green_message(scope, behaviour, number, plan_slug, kind,
    issue=None) -> str``.

    The trailer rule is the same as the red's (behaviour 5): an intake
    reference as a trailer, omitted when the intake had no issue.
    The ``Refs #{issue}`` line sits after a blank line, exactly as the
    red builds it.
    """

    def _green_lines(self, subject_kind: str, issue=None) -> list:
        """The house line structure for one branch kind, with the
        trailer only when an issue is given."""
        lines = [
            "%s(pi): %s" % (subject_kind, GREEN_BEHAVIOUR),
            "",
            "Behaviour %d of plans/%s.md. Green."
            % (GREEN_NUMBER, PLAN_SLUG),
        ]
        if issue is not None:
            lines.append("")
            lines.append("Refs #%d" % issue)
        return lines

    def test_green_message_feature_subject_is_feat(self) -> None:
        # Arrange: the givens of behaviour 6 for a feature branch,
        # with the intake's issue number.
        # Act
        message = picommit.green_message(
            SCOPE, GREEN_BEHAVIOUR, GREEN_NUMBER, PLAN_SLUG,
            KIND_FEATURE, ISSUE,
        )

        # Assert: the exact house line structure for a feature,
        # trailer included - the body line ends "Green.", the message
        # as a whole ends with the trailer.
        self.assertEqual(
            message.splitlines(),
            self._green_lines("feat", ISSUE),
            "a feature's green message must be "
            "feat subject, blank, body ending Green., blank, "
            "Refs trailer; got: %r" % message,
        )
        self.assertTrue(
            message.splitlines()[2].endswith("Green."),
            "the green body line must end with 'Green.'; got: %r"
            % message,
        )
        self.assertNotIn(
            "failing",
            message,
            "'failing' must never appear in a green message; "
            "got: %r" % message,
        )

    def test_green_message_bugfix_subject_is_fix(self) -> None:
        # Arrange: the same givens for a bugfix branch, with the
        # intake's issue number.
        # Act
        message = picommit.green_message(
            SCOPE, GREEN_BEHAVIOUR, GREEN_NUMBER, PLAN_SLUG,
            KIND_BUGFIX, ISSUE,
        )

        # Assert: the exact house line structure for a bugfix,
        # trailer included.
        self.assertEqual(
            message.splitlines(),
            self._green_lines("fix", ISSUE),
            "a bugfix's green message must be "
            "fix subject, blank, body ending Green., blank, "
            "Refs trailer; got: %r" % message,
        )
        self.assertTrue(
            message.splitlines()[2].endswith("Green."),
            "the green body line must end with 'Green.'; got: %r"
            % message,
        )
        self.assertNotIn(
            "failing",
            message,
            "'failing' must never appear in a green message; "
            "got: %r" % message,
        )

    def test_green_message_never_contains_failing(self) -> None:
        # Arrange / Act: both branch kinds, since the rule is that a
        # green is never red-flavoured; each also built without an
        # issue, since the trailer rule must hold for the green as it
        # does for the red.
        feature = picommit.green_message(
            SCOPE, GREEN_BEHAVIOUR, GREEN_NUMBER, PLAN_SLUG,
            KIND_FEATURE, ISSUE,
        )
        bugfix = picommit.green_message(
            SCOPE, GREEN_BEHAVIOUR, GREEN_NUMBER, PLAN_SLUG,
            KIND_BUGFIX, ISSUE,
        )
        feature_no_issue = picommit.green_message(
            SCOPE, GREEN_BEHAVIOUR, GREEN_NUMBER, PLAN_SLUG,
            KIND_FEATURE, None,
        )

        # Assert: the red's load-bearing word is absent from the green.
        self.assertNotIn(
            "failing",
            feature,
            "'failing' must never appear in a green message; "
            "got: %r" % feature,
        )
        self.assertNotIn(
            "failing",
            bugfix,
            "'failing' must never appear in a green message; "
            "got: %r" % bugfix,
        )
        self.assertNotIn(
            "failing",
            feature_no_issue,
            "'failing' must never appear in a green message; "
            "got: %r" % feature_no_issue,
        )

        # Assert: the trailer is present when an issue is given -
        # exactly as the red builds it.
        self.assertEqual(
            feature.splitlines(),
            self._green_lines("feat", ISSUE),
            "with an issue the green message must end with the "
            "Refs trailer; got: %r" % feature,
        )

        # Assert: and absent entirely when there is no issue - no
        # trailer, no blank-line-only tail, mirroring behaviour 5.
        self.assertEqual(
            feature_no_issue.splitlines(),
            self._green_lines("feat", None),
            "without an issue the trailer and its blank line must be "
            "absent; got: %r" % feature_no_issue,
        )


class GreenMessageValidationErrorTestCase(unittest.TestCase):
    """Behaviour 6's error rule: an unknown branch kind raises
    ``CommitError`` naming the offending kind - a subject can only be
    ``feat`` or ``fix``, so any other kind is a build failure.
    ``picommit`` is the top-level import, as in the format class.
    """

    def test_green_message_unknown_kind_raises_commit_error_naming_kind(
        self,
    ) -> None:
        # Arrange / Act
        # Assert
        with self.assertRaises(picommit.CommitError) as ctx:
            picommit.green_message(
                SCOPE, GREEN_BEHAVIOUR, GREEN_NUMBER, PLAN_SLUG,
                KIND_UNKNOWN, ISSUE,
            )
        message = str(ctx.exception)
        self.assertIn(
            KIND_UNKNOWN,
            message,
            "the error must name the unknown branch kind; got: %r"
            % message,
        )


if __name__ == "__main__":
    unittest.main()
