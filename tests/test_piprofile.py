"""Tests for anvilkit.pi.piprofile — the ``~/.anvil/profiles.yaml`` store.

Written before the implementation (TDD, ``plans/pi-phase13-profiles.md``).
This file currently covers behaviour 1 only ("name-charset"); the later
behaviours (``token_env_for``, ``save_profile``, ``load_profile``,
``list_profiles``, ``resolve_token``) will be added here as separate test
classes as they are implemented.

The production module ``anvilkit.pi.piprofile`` does not exist yet, so each
test imports it inside the test body rather than at collection time. The
expected red failure is a ``ModuleNotFoundError`` (an ``ImportError``) naming
``anvilkit.pi.piprofile`` — or, once the module exists but the function does
not, an ``AttributeError`` naming ``valid_name`` — not a collection error in
this file.
"""

import importlib
import unittest

# The tests own these values; the module must derive its verdict from the
# name's characters, not from a hardcoded allowlist.
ACCEPTED_NAMES = [
    "project-x",
    "api.v2",
    "web_ui",
    "A9",
]

OUT_OF_CHARSET_NAMES = [
    "my project!",
    "my_project?",
]

LEADING_HYPHEN_NAMES = ["-project", "-"]
LEADING_DOT_NAMES = [".hidden", "."]
LEADING_DIGIT_NAMES = ["2cool", "0", "123"]


class ValidNameTestCase(unittest.TestCase):
    """Behaviour 1: name-charset."""

    def _valid_name(self):
        """Import anvilkit.pi.piprofile and return its ``valid_name``.

        Fails with a ModuleNotFoundError naming the missing module while the
        store is unimplemented, and with an AttributeError naming
        ``valid_name`` once the module exists without the function.
        """
        return importlib.import_module("anvilkit.pi.piprofile").valid_name

    def test_valid_name_accepts_charset_names_returns_true(self):
        valid_name = self._valid_name()
        for name in ACCEPTED_NAMES:
            with self.subTest(name=name):
                self.assertIs(valid_name(name), True)

    def test_valid_name_rejects_out_of_charset_character_returns_false(self):
        valid_name = self._valid_name()
        for name in OUT_OF_CHARSET_NAMES:
            with self.subTest(name=name):
                self.assertIs(valid_name(name), False)

    def test_valid_name_rejects_empty_string_returns_false(self):
        valid_name = self._valid_name()
        self.assertIs(valid_name(""), False)

    def test_valid_name_rejects_leading_hyphen_returns_false(self):
        valid_name = self._valid_name()
        for name in LEADING_HYPHEN_NAMES:
            with self.subTest(name=name):
                self.assertIs(valid_name(name), False)

    def test_valid_name_rejects_leading_dot_returns_false(self):
        valid_name = self._valid_name()
        for name in LEADING_DOT_NAMES:
            with self.subTest(name=name):
                self.assertIs(valid_name(name), False)

    def test_valid_name_rejects_leading_digit_returns_false(self):
        valid_name = self._valid_name()
        for name in LEADING_DIGIT_NAMES:
            with self.subTest(name=name):
                self.assertIs(valid_name(name), False)
