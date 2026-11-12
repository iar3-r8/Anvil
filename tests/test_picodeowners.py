"""Tests for anvilkit.pi.picodeowners - the CODEOWNERS body builder
(behaviour 1 of plans/file-path-interactive-free-plan.md).

Written before the implementation (TDD RED step). The production module
``anvilkit.pi.picodeowners`` does not exist yet, so every test imports it
through a guarded ``try``/``except ImportError`` inside the test method and
fails with a clear assertion message instead of letting a collection-time
ImportError mask the reason the suite is red.

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


if __name__ == "__main__":
    unittest.main()
