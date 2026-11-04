"""Tests for the deterministic token estimate of
``anvilkit.pi.piprompt.estimate_tokens``.

``plans/pi-role-prompts.md``, behaviour 15
(token-estimate-is-deterministic): given any prompt text, when
``piprompt.estimate_tokens(text)`` is called, then the result is
``ceil(len(text.encode("utf-8")) / 3)`` — deterministic, and deliberately
conservative (an over-estimate; it is an approximation, not a measurement).
Error: empty text yields 0, never a division error.

This is the seam the budget check of behaviour 16
(``piprompt.budget_report``) will consume: it divides and compares the
estimate against the window, so the estimate must be an exact ``int``
and must not shrink as the text grows.

Behaviours 4-12 are green: ``all_documents``, ``role_document`` and
``shared_document`` already exist in the module. This file pins the
estimate alone.

Pinned seam for this cycle::

    estimate_tokens(text: str) -> int

RED expectation (this commit): ``estimate_tokens`` does not exist in
``anvilkit.pi.piprompt`` yet, so every test in this file fails with
``AttributeError: module 'anvilkit.pi.piprompt' has no attribute
'estimate_tokens'``: a clean per-test AttributeError is the right red
reason for a missing function (no collection, import or syntax error —
the module imports fine, it simply does not define the seam yet).
"""

import math
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit.pi import piprompt  # noqa: E402


def _expected(text: str) -> int:
    """The formula behaviour 15 pins: ceil(UTF-8 bytes / 3).

    Every expected value in this file is derived from the formula, not
    hardcoded, so the test pins the formula itself rather than one
    instance of it.
    """
    return math.ceil(len(text.encode("utf-8")) / 3)


class EstimateTokensEmptyTest(unittest.TestCase):
    """Empty text yields 0, never a division error."""

    def test_estimate_tokens_empty_string_returns_zero(self) -> None:
        # Arrange: the shortest possible input — the division-by-N on a
        # zero-byte text is the trap the behaviour names explicitly.
        text = ""

        # Act: the call must complete without raising ZeroDivisionError
        # (or any other error).
        result = piprompt.estimate_tokens(text)

        # Assert: exactly 0, and an int — 0.0 would be a float leak.
        self.assertEqual(result, 0)
        self.assertIsInstance(result, int)


class EstimateTokensFormulaTest(unittest.TestCase):
    """The estimate is ceil(UTF-8 bytes / 3), on encoded bytes."""

    def test_estimate_tokens_ascii_strings_match_ceil_utf8_bytes_over_3(self) -> None:
        # Arrange: three ASCII strings of different lengths; the 7-byte
        # one is NOT a multiple of 3, so it pins the ceiling (7/3 = 2.33
        # must round up to 3, not down to 2).
        texts = (
            "a",              # 1 byte -> ceil(1/3) = 1
            "abcd",           # 4 bytes -> ceil(4/3) = 2
            "abcdefgh",       # 8 bytes -> ceil(8/3) = 3 (ceiling case)
        )

        for text in texts:
            with self.subTest(text=text):
                # Act.
                result = piprompt.estimate_tokens(text)

                # Assert: the value equals the formula computed in the
                # test, so a wrong divisor or a floor instead of a
                # ceiling fails here.
                self.assertEqual(result, _expected(text))

    def test_estimate_tokens_multibyte_utf8_uses_encoded_bytes_not_chars(self) -> None:
        # Arrange: text with multi-byte UTF-8 characters (em-dashes are
        # 3 bytes each). The character count is deliberately NOT what
        # the formula runs on — if it did, the estimate would be
        # smaller than the byte-based one, and the budget check would
        # under-estimate the role's real payload.
        text = "red/green cycle kept honest — the asset being migrated"
        byte_count = len(text.encode("utf-8"))
        char_count = len(text)

        # Guard the test itself: this string must actually exercise the
        # multi-byte path, or the assertion below is vacuous.
        self.assertGreater(byte_count, char_count,
                           "test string must contain multi-byte characters")

        # Act.
        result = piprompt.estimate_tokens(text)

        # Assert: the estimate is computed on the UTF-8 encoding length,
        # not the character count.
        self.assertEqual(result, math.ceil(byte_count / 3))


class EstimateTokensDeterminismTest(unittest.TestCase):
    """Two calls on the same text return the same int."""

    def test_estimate_tokens_same_text_same_result(self) -> None:
        # Arrange: arbitrary non-trivial prompt text.
        text = "You are the Q&A Tester. Translate the behaviour into tests."

        # Act: two independent calls.
        first = piprompt.estimate_tokens(text)
        second = piprompt.estimate_tokens(text)

        # Assert: identical results — a time-, state- or hash-seed-
        # dependent estimate would make the budget report unrepeatable.
        self.assertEqual(first, second)


class EstimateTokensMonotonicTest(unittest.TestCase):
    """A strictly longer text yields an estimate >= the shorter's."""

    def test_estimate_tokens_longer_text_estimate_not_smaller(self) -> None:
        # Arrange: two texts where the longer has strictly more UTF-8
        # bytes.
        shorter = "abc"
        longer = "abcdef"
        self.assertGreater(len(longer.encode("utf-8")),
                           len(shorter.encode("utf-8")))

        # Act.
        shorter_estimate = piprompt.estimate_tokens(shorter)
        longer_estimate = piprompt.estimate_tokens(longer)

        # Assert: monotonic direction only. An estimate that shrinks as
        # the text grows would be unsound for a budget check; the ratio
        # between the two is deliberately NOT pinned.
        self.assertGreaterEqual(longer_estimate, shorter_estimate)


class EstimateTokensTypeTest(unittest.TestCase):
    """The estimate is an int: budget arithmetic divides and compares."""

    def test_estimate_tokens_returns_int(self) -> None:
        # Arrange.
        text = "the token estimate is an approximation, not a measurement"

        # Act.
        result = piprompt.estimate_tokens(text)

        # Assert: exactly int. A float would silently drift in the
        # budget arithmetic of behaviour 16; a bool (an int subclass)
        # would be wrong in every other way.
        self.assertIsInstance(result, int)
        self.assertNotIsInstance(result, bool)


if __name__ == "__main__":
    unittest.main()
