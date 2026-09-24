"""Mirror parity guard for plans/cut-agent-context-cost.md, behaviour B1.

Every rule-file change in that plan is mirrored into the anvil repo's own
``.roo/`` tree, and the four XML rule files must stay **byte-identical**
between ``templates/roo_template/`` (shipped) and ``.roo/`` (local). Because
``.roo/*`` is gitignored, only the template side ever appears in a diff; this
module is the guard that turns "forgot to update the ``.roo/`` copy" into a
red test instead of silent drift.

This is byte-equality between two copies of the same data, not an assertion
on the source text of the thing under test, and it says nothing about
content. It is expected to PASS on arrival (coverage-only boundary pin, same
precedent as ``B18ArchitectDeploymentTests`` in
``tests/test_templates_rules.py``).

Edge behaviour, per the plan:

* ``.roo/`` absent -> **skip**, not fail (gitignored; absent on a fresh
  clone and in CI, same skip pattern as B20 in
  ``tests/test_templates_rules.py``).
* A template file absent -> **fail**; the templates are tracked and must
  exist, even when ``.roo/`` is not provisioned.
* Drift -> **fail** with a message naming the differing path and the byte
  count of both copies, so a reviewer sees which copy drifted.
"""

import unittest

from tests.test_templates_rules import REPO_ROOT

# The two trees being mirrored. The template side is the source of truth
# (tracked); the local side is what every behaviour in the plan must keep in
# sync.
TEMPLATE_ROOT = REPO_ROOT / "templates" / "roo_template"
LOCAL_ROOT = REPO_ROOT / ".roo"

# The four rule files that must stay in lockstep: (relative path, human
# label for the test name).
MIRROR_PAIRS = [
    ("rules-tdd-manager/instructions.xml", "tdd-manager instructions"),
    ("rules-architect/instructions.xml", "architect instructions"),
    ("rules-qna-tester/instructions.xml", "qna-tester instructions"),
    ("rules-docs-manager/guidelines.xml", "docs-manager guidelines"),
]


def _drift_message(rel, template_size, local_size):
    """Failure text naming the drifted path and the byte count of both
    copies, so a reviewer sees which copy drifted and by how much."""
    return (
        "mirror drift: .roo/%s is not byte-identical to "
        "templates/roo_template/%s (template %d bytes, local %d bytes)"
        % (rel, rel, template_size, local_size)
    )


class RulesMirrorTestCase(unittest.TestCase):
    """Each shipped rule XML is byte-identical to its local ``.roo/`` copy."""

    def setUp(self):
        # The template side is tracked and must exist, regardless of whether
        # .roo/ is provisioned; a missing template is a failure, not a skip.
        for rel, label in MIRROR_PAIRS:
            self.assertTrue(
                (TEMPLATE_ROOT / rel).is_file(),
                "tracked template file is missing: "
                "templates/roo_template/%s (%s)" % (rel, label),
            )
        # .roo/ is gitignored, so it is absent on a fresh clone and in CI;
        # skip cleanly in that case (B20 pattern in test_templates_rules.py).
        if not LOCAL_ROOT.is_dir():
            self.skipTest(
                "anvil repo local .roo/ directory not provisioned; "
                "nothing to check"
            )

    def _assert_mirror(self, rel):
        """Assert the local copy's bytes equal the template's bytes."""
        template_bytes = (TEMPLATE_ROOT / rel).read_bytes()
        local_bytes = (LOCAL_ROOT / rel).read_bytes()
        self.assertEqual(
            local_bytes,
            template_bytes,
            _drift_message(rel, len(template_bytes), len(local_bytes)),
        )

    # -- the four mirror pairs -- #

    def test_tdd_manager_instructions_are_byte_identical_to_local_copy(self):
        self._assert_mirror("rules-tdd-manager/instructions.xml")

    def test_architect_instructions_are_byte_identical_to_local_copy(self):
        self._assert_mirror("rules-architect/instructions.xml")

    def test_qna_tester_instructions_are_byte_identical_to_local_copy(self):
        self._assert_mirror("rules-qna-tester/instructions.xml")

    def test_docs_manager_guidelines_are_byte_identical_to_local_copy(self):
        self._assert_mirror("rules-docs-manager/guidelines.xml")

    # -- error behaviour: the drift message is diagnostic, not opaque -- #

    def test_drift_message_names_path_and_both_byte_counts(self):
        message = _drift_message("rules-architect/instructions.xml", 17900, 18000)
        for expected in (
            "rules-architect/instructions.xml",
            "17900",
            "18000",
        ):
            self.assertIn(
                expected,
                message,
                "drift message does not name %r: %r" % (expected, message),
            )


if __name__ == "__main__":
    unittest.main()
