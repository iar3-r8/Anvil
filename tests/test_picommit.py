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

The production module does not exist yet, so every test imports it
lazily through ``_picommit()`` (an ``importlib.import_module`` inside
the test, the same idiom as ``tests/test_piverdict.py``'s behaviour-1
class). While the module is missing the file collects and each test
fails at the import step with
``ModuleNotFoundError: No module named 'anvilkit.pi.picommit'`` - the
right kind of red for this step.

**Proposed signature - NOT plan-pinned.** The plan names the function
and its inputs but pins no parameter list or order (behaviours 5/6).
This test file is written against the proposed convention:

    red_message(scope, behaviour, number, plan_slug, assertion,
                issue=None) -> str

with the parameters in the order the plan's "Given" clause lists them,
and ``issue=None`` meaning "no issue" (trailer omitted). The coder is
free to confirm or adjust the signature - if adjusted, this file must
be updated to match and re-run.
"""

import importlib
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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


if __name__ == "__main__":
    unittest.main()
