"""Tests for anvilkit.piruleset - the importable GitHub ruleset builder.

Written before the implementation (TDD, ``plans/ruleset-write.md``,
behaviour 1: "build_ruleset"). Behaviours 2-8 land in later cycles as
further tests in the same file.

``build_ruleset()`` must return the five-rule ruleset reproducing issue
#50's main-branch guard, freshly built on every call so a caller that
mutates the result cannot poison the next call. The shape mirrors the
exported-ruleset key set pinned by the golden shape reference
``doc/external/github/ruleset-recipes-branch-sample.json``:
``name``, ``target``, ``source_type``, ``enforcement``, ``conditions``,
``rules``, ``bypass_actors``.

The production module ``anvilkit.piruleset`` does not exist yet, so this
file imports it at module level and the suite fails with an ImportError
until the green step adds it.

Citations for the interface facts asserted here:

- ``conditions.ref_name.include`` accepts ``~DEFAULT_BRANCH``; ``exclude``
  is a sibling array - ``doc/external/github/rest-api-endpoints-for-rules.md``.
- ``enforcement`` is required, one of ``disabled`` | ``active`` |
  ``evaluate``; ``target`` defaults to ``branch`` - same page.
- ``update`` takes ``parameters.update_allows_fetch_and_merge`` (boolean,
  required); ``non_fast_forward`` and ``deletion`` take no parameters;
  ``file_path_restriction`` takes ``parameters.restricted_file_paths``
  (array of strings, required); the five ``pull_request`` parameters are
  exactly as pinned in :data:`expected_ruleset` - same page.
- ``fnmatch``'s ``*`` does not cross ``/``, so the ``**`` in
  ``".github/workflows/**"`` is load-bearing -
  ``doc/external/github/creating-rulesets-for-a-repository.md``.
"""

import sys
import unittest
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import piruleset  # noqa: E402


def expected_ruleset() -> Dict[str, Any]:
    """The pinned ruleset shape, freshly built per call.

    Returned by a function rather than a module-level constant so a test
    that mutates its own copy cannot poison the expectation another test
    is about to compare against.
    """
    return {
        "name": "Anvil main guard",
        "target": "branch",
        "source_type": "Repository",
        "enforcement": "active",
        "conditions": {
            "ref_name": {
                "include": ["~DEFAULT_BRANCH"],
                "exclude": [],
            }
        },
        "bypass_actors": [],
        "rules": [
            {"type": "non_fast_forward"},
            {"type": "deletion"},
            {
                "type": "update",
                "parameters": {"update_allows_fetch_and_merge": True},
            },
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": 1,
                    "require_code_owner_review": False,
                    "require_last_push_approval": True,
                    "dismiss_stale_reviews_on_push": True,
                    "required_review_thread_resolution": False,
                },
            },
            {
                "type": "file_path_restriction",
                "parameters": {
                    "restricted_file_paths": [".github/workflows/**"]
                },
            },
        ],
    }


class BuildRulesetStructureTests(unittest.TestCase):
    """Behaviour 1: the full five-rule structure, defaults only."""

    def test_build_ruleset_returns_a_dict(self) -> None:
        self.assertIsInstance(piruleset.build_ruleset(), dict)

    def test_build_ruleset_pins_name_to_a_non_empty_string(self) -> None:
        name = piruleset.build_ruleset()["name"]
        self.assertIsInstance(name, str)
        self.assertTrue(name, "ruleset name must be a non-empty string")

    def test_build_ruleset_matches_the_pinned_full_structure(self) -> None:
        # Dict equality on the rules list pins both the five rule types
        # and their order, not just the types.
        self.assertEqual(piruleset.build_ruleset(), expected_ruleset())

    def test_build_ruleset_pins_the_five_rule_types_in_order(self) -> None:
        rules = piruleset.build_ruleset()["rules"]
        self.assertEqual(
            [rule["type"] for rule in rules],
            [
                "non_fast_forward",
                "deletion",
                "update",
                "pull_request",
                "file_path_restriction",
            ],
        )


class BuildRulesetFreshnessTests(unittest.TestCase):
    """Behaviour 1, error path: fresh per call, no shared mutable state."""

    def test_build_ruleset_is_fresh_per_call_and_not_shared_by_reference(
        self,
    ) -> None:
        first = piruleset.build_ruleset()
        second = piruleset.build_ruleset()

        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertIsNot(first["rules"], second["rules"])

        # Mutating the first result - top-level, the rules list and a rule's
        # parameters - must not touch the second one.
        first["name"] = "mutated"
        first["rules"].append({"type": "bogus"})
        first["rules"][0]["type"] = "mutated"
        first["rules"][2]["parameters"]["update_allows_fetch_and_merge"] = False

        self.assertEqual(second, expected_ruleset())


if __name__ == "__main__":
    unittest.main()
