"""Tests for anvilkit.pi.piprofile — the ``~/.anvil/profiles.yaml`` store.

Written before the implementation (TDD, ``plans/pi-phase13-profiles.md``).
This file covers behaviour 1 ("name-charset") and behaviour 2
("token-env-derivation"); the later behaviours (``save_profile``,
``load_profile``, ``list_profiles``, ``resolve_token``) will be added here
as separate test classes as they are implemented.

The production module is imported inside each test body rather than at
collection time, so the file always collects cleanly. While behaviour 2 is
unimplemented, its expected red failure is an ``AttributeError`` naming
``token_env_for`` — not a collection error in this file.
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


# Behaviour 2: the same names that pass behaviour 1, paired with the exact
# environment variable each must derive to.
EXPECTED_TOKEN_ENV = {
    "project-x": "GITHUB_TOKEN_PROJECT_X",
    "api.v2": "GITHUB_TOKEN_API_V2",
    "web_ui": "GITHUB_TOKEN_WEB_UI",
    "A9": "GITHUB_TOKEN_A9",
}

# One invalid name per way of failing behaviour 1.
INVALID_TOKEN_ENV_NAMES = [
    "",
    "my project!",
    "-project",
    ".hidden",
    "2cool",
]

#: The charset a failure message must quote so the operator can fix the
#: name without reading the source.
ALLOWED_CHARSET = "[A-Za-z0-9._-]"


class TokenEnvDerivationTestCase(unittest.TestCase):
    """Behaviour 2: token-env-derivation."""

    def _module(self):
        """Import anvilkit.pi.piprofile, named in any red failure.

        The module exists (behaviour 1), so the import succeeds and a missing
        ``token_env_for`` surfaces as an ``AttributeError`` naming the
        function, not as a collection error.
        """
        return importlib.import_module("anvilkit.pi.piprofile")

    def test_token_env_for_derives_expected_env_name(self):
        module = self._module()
        for name, expected in EXPECTED_TOKEN_ENV.items():
            with self.subTest(name=name):
                self.assertEqual(module.token_env_for(name), expected)

    def test_token_env_for_deterministic_across_calls(self):
        module = self._module()
        for name in EXPECTED_TOKEN_ENV:
            with self.subTest(name=name):
                self.assertEqual(
                    module.token_env_for(name),
                    module.token_env_for(name),
                )

    def test_token_env_for_invalid_name_raises_profile_error(self):
        module = self._module()
        for name in INVALID_TOKEN_ENV_NAMES:
            with self.subTest(name=name):
                # A raise, not a silently sanitised string, is the contract:
                # assertRaises fails if token_env_for returns anything.
                self.assertRaises(module.ProfileError, module.token_env_for, name)

    def test_token_env_for_error_message_names_name_and_charset(self):
        module = self._module()
        for name in INVALID_TOKEN_ENV_NAMES:
            with self.subTest(name=name):
                with self.assertRaises(module.ProfileError) as ctx:
                    module.token_env_for(name)
                message = str(ctx.exception)
                if name:
                    self.assertIn(name, message)
                self.assertIn(ALLOWED_CHARSET, message)
