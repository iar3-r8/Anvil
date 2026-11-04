"""Tests for ``anvilkit.pi.piprompt.source_for`` - the public surface of
the role source map.

``plans/pi-role-prompts.md``, behaviour 8 (role-source-map): given a role
name, when ``piprompt.source_for(name)``, then ``architect`` ->
``rules-architect/instructions.xml``, ``tester`` ->
``rules-qna-tester/instructions.xml``, ``docs`` ->
``rules-docs-manager/guidelines.xml``, ``tdd-manager`` ->
``rules-tdd-manager/instructions.xml``; ``coder`` has no XML source and
carries the literal one-liner. Error: any other name raises
``PromptError`` naming it and listing the six known names - the five
roles plus ``shared-agents`` (the chain root, which has no source file
of its own, so it is refused by ``source_for`` too).

Pinned seam for this cycle::

    source_for(name: str) -> str

Pin choice: the returned value for the four XML roles is pinned as the
plan writes it - the path string relative to ``templates/roo_template/``
(e.g. ``rules-architect/instructions.xml``), not an absolute ``Path`` -
so the map stays a pure name -> relative-path table and ``coder``
(returning the one-liner string) keeps the same return type. The
one-liner is pinned verbatim, not as a sentinel: behaviour 10 already
pins the coder body as exactly ``You write and modify code.``, and
behaviour 8 says the map points at that literal (no XML source).

Each mapped source must additionally exist as a tracked file under
``templates/roo_template/``: a map entry pointing at a phantom path is
drift the existence tests catch.

RED expectation (this commit): ``source_for`` does not exist yet. The
module ``anvilkit.pi.piprompt`` DOES exist (behaviours 4-7 are green),
so it is imported at module top level - the file therefore collects with
no import/collection/syntax error, and every test fails at the call site
with ``AttributeError: module 'anvilkit.pi.piprompt' has no attribute
'source_for'``: a clean per-test AttributeError is the right red reason,
not a collection error.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit.pi import piprompt  # noqa: E402

# The four roles whose body is built from a tracked XML source, keyed by
# role name to the plan's map value: the path string relative to
# templates/roo_template/ exactly as behaviour 8 writes it.
XML_ROLE_SOURCES = {
    "architect": "rules-architect/instructions.xml",
    "tester": "rules-qna-tester/instructions.xml",
    "docs": "rules-docs-manager/guidelines.xml",
    "tdd-manager": "rules-tdd-manager/instructions.xml",
}

# The five roles source_for serves: the four XML roles plus the coder.
ROLE_NAMES = ("architect", "tester", "docs", "tdd-manager", "coder")

# The six known names the plan's error line names: the five roles plus
# the chain root, which has no source file of its own.
KNOWN_NAMES = ROLE_NAMES + ("shared-agents",)

# Behaviour 10: the coder body is exactly this one-liner, and behaviour
# 8 says the map points at that literal (no XML source).
CODER_ONE_LINER = "You write and modify code."


class RoleSourceMapCase(unittest.TestCase):
    """Behaviour 8: source_for maps each role to its tracked source, the
    coder to the literal one-liner, and any other name to a PromptError
    naming it and listing the six known names."""

    def test_source_for_architect_returns_rules_architect_instructions_xml(
        self,
    ) -> None:
        self.assertEqual(
            piprompt.source_for("architect"),
            "rules-architect/instructions.xml",
            "source_for('architect') must return the relative path "
            "string 'rules-architect/instructions.xml' exactly as the "
            "plan writes it (relative to templates/roo_template/)",
        )

    def test_source_for_tester_returns_rules_qna_tester_instructions_xml(
        self,
    ) -> None:
        self.assertEqual(
            piprompt.source_for("tester"),
            "rules-qna-tester/instructions.xml",
            "source_for('tester') must return the relative path string "
            "'rules-qna-tester/instructions.xml' exactly as the plan "
            "writes it (relative to templates/roo_template/)",
        )

    def test_source_for_docs_returns_rules_docs_manager_guidelines_xml(
        self,
    ) -> None:
        self.assertEqual(
            piprompt.source_for("docs"),
            "rules-docs-manager/guidelines.xml",
            "source_for('docs') must return the relative path string "
            "'rules-docs-manager/guidelines.xml' exactly as the plan "
            "writes it (relative to templates/roo_template/)",
        )

    def test_source_for_tdd_manager_returns_rules_tdd_manager_instructions_xml(
        self,
    ) -> None:
        self.assertEqual(
            piprompt.source_for("tdd-manager"),
            "rules-tdd-manager/instructions.xml",
            "source_for('tdd-manager') must return the relative path "
            "string 'rules-tdd-manager/instructions.xml' exactly as the "
            "plan writes it (relative to templates/roo_template/)",
        )

    def test_source_for_coder_returns_literal_one_liner(self) -> None:
        # The coder has no XML source: the map points at the one-liner
        # itself, pinned verbatim (behaviour 10's body).
        self.assertEqual(
            piprompt.source_for("coder"),
            CODER_ONE_LINER,
            "source_for('coder') must return the literal one-liner %r "
            "(the coder has no XML source)" % CODER_ONE_LINER,
        )

    def test_source_for_architect_source_exists_under_roo_template(
        self,
    ) -> None:
        self._assert_source_exists("architect")

    def test_source_for_tester_source_exists_under_roo_template(
        self,
    ) -> None:
        self._assert_source_exists("tester")

    def test_source_for_docs_source_exists_under_roo_template(self) -> None:
        self._assert_source_exists("docs")

    def test_source_for_tdd_manager_source_exists_under_roo_template(
        self,
    ) -> None:
        self._assert_source_exists("tdd-manager")

    def test_source_for_unknown_name_raises_prompt_error_naming_it(self) -> None:
        with self.assertRaises(piprompt.PromptError) as ctx:
            piprompt.source_for("definitely-not-a-role")
        self.assertIn(
            "definitely-not-a-role",
            str(ctx.exception),
            "the PromptError for an unknown role must name the "
            "offending name (got: %r)" % str(ctx.exception),
        )

    def test_source_for_unknown_name_error_lists_all_five_roles_and_shared_agents(
        self,
    ) -> None:
        # Anti-vacuity: the "lists the known names" assertion checks all
        # six names individually - the five roles plus shared-agents -
        # not just one, so a message that lists only some of them fails
        # here naming exactly which one is missing.
        with self.assertRaises(piprompt.PromptError) as ctx:
            piprompt.source_for("definitely-not-a-role")
        message = str(ctx.exception)
        for known in KNOWN_NAMES:
            self.assertIn(
                known,
                message,
                "the PromptError for an unknown role must list the six "
                "known names, but %r is missing from %r" % (known, message),
            )

    def test_source_for_shared_agents_raises_prompt_error_naming_it(self) -> None:
        # The chain root has no source file of its own: it is refused,
        # not mapped.
        with self.assertRaises(piprompt.PromptError) as ctx:
            piprompt.source_for("shared-agents")
        self.assertIn(
            "shared-agents",
            str(ctx.exception),
            "the PromptError for shared-agents must name it (got: %r)"
            % str(ctx.exception),
        )

    def _assert_source_exists(self, role: str) -> None:
        """The source ``source_for(role)`` returns is a tracked file
        under ``templates/roo_template/``: a phantom path is map drift."""
        source = piprompt.source_for(role)
        path = REPO_ROOT / "templates" / "roo_template" / source
        self.assertTrue(
            path.is_file(),
            "the source source_for(%r) returns, %s, is missing under "
            "templates/roo_template/: the map must point at tracked "
            "files, not phantom paths" % (role, source),
        )


if __name__ == "__main__":
    unittest.main()
