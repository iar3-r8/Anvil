"""Tests for the provisioned ``brainstorm-feature.md`` template command.

This module is the home for every behaviour of
``plans/brainstorm-feature-command.md`` that is verified against the
*content* of
``templates/roo_template/commands/brainstorm-feature.md``. It reuses the
frontmatter loader and path constants from
``tests/test_template_commands.py`` rather than redefining them (plan
§Assumptions): every assertion is on the parsed frontmatter structure, never
on raw bytes, so the green step has latitude in the prose.
"""

import unittest

from tests.test_template_commands import (
    COMMANDS_DIR,
    REPO_ROOT,
    load_template_command,
)

#: Behaviour 1 target (plan §Behaviors 1): the new Architect-mode command
#: file, which does not exist yet — creating it is the green step.
BRAINSTORM_COMMAND_PATH = COMMANDS_DIR / "brainstorm-feature.md"


class BrainstormCommandTestCase(unittest.TestCase):
    """Shared loading for the brainstorm-feature command file.

    ``setUp`` asserts the file exists as a regular file and parses it once,
    so every test asserts on the parsed frontmatter and body, and a missing
    or malformed document surfaces at load time naming the path. Later
    behaviours subclass this pointed at the same file and assert on
    ``self.body``.
    """

    command_path = BRAINSTORM_COMMAND_PATH

    def setUp(self):
        self.assertTrue(
            self.command_path.is_file(),
            "command file does not exist or is not a regular file: %s"
            % self.command_path,
        )
        self.frontmatter, self.body = load_template_command(self.command_path)


# --------------------------------------------------------------------------- #
# Behaviour 1 — the command file exists with valid frontmatter
# --------------------------------------------------------------------------- #


class B1FrontmatterTests(BrainstormCommandTestCase):
    """Behaviour 1 (plans/brainstorm-feature-command.md): the command file
    exists with valid frontmatter.

    Expected red reason: ``templates/roo_template/commands/brainstorm-feature.md``
    does not exist yet, so every test fails in ``setUp`` with the
    file-not-found assertion. That is the intended failure mode — the green
    step creates the file, nothing else.
    """

    def test_command_file_is_a_regular_file(self):
        # B1 output: the path is a file, not a directory or a missing path.
        # setUp already asserted this; the explicit test keeps the
        # requirement named in the suite.
        self.assertTrue(
            self.command_path.is_file(),
            "command file does not exist or is not a regular file: %s"
            % self.command_path,
        )

    def test_frontmatter_is_a_mapping(self):
        # B1: the parsed frontmatter is a YAML mapping, not a scalar or a
        # list. The loader would have raised for anything else.
        self.assertIsInstance(
            self.frontmatter,
            dict,
            "frontmatter of %s is not a mapping" % self.command_path,
        )

    def test_frontmatter_has_non_empty_description(self):
        # B1: frontmatter carries a non-empty ``description`` string.
        description = self.frontmatter.get("description")
        self.assertIsInstance(
            description,
            str,
            "frontmatter of %s has no 'description' string" % self.command_path,
        )
        self.assertTrue(
            description.strip(),
            "frontmatter 'description' of %s is empty" % self.command_path,
        )

    def test_frontmatter_mode_is_architect(self):
        # B1: the command runs in Architect mode (the plan's three-phase
        # brainstorming is a planning, not an implementation, session).
        self.assertEqual(
            self.frontmatter.get("mode"),
            "Architect",
            "frontmatter 'mode' of %s is not 'Architect'" % self.command_path,
        )


if __name__ == "__main__":
    unittest.main()
