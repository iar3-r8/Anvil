"""Tests for anvilkit.piruleset - the importable GitHub ruleset builder.

Written before the implementation (TDD, ``plans/ruleset-write.md``).
This file currently pins behaviour 1 ("build_ruleset"), behaviour 2
("render_ruleset_json"), the behaviour 8 golden-fixture boundary
pin (batched with behaviour 2 per the plan's sequencing notes) and
behaviours 3+4 ("default_output_path" folded into
"write_ruleset" per the plan's sequencing note); the remaining
behaviours land in later cycles as further tests in the same file.

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

import json
import sys
import tempfile
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


class RenderRulesetJsonTests(unittest.TestCase):
    """Behaviour 2: render the ruleset dict to JSON."""

    def test_render_ruleset_json_ends_with_exactly_one_newline(self) -> None:
        rendered = piruleset.render_ruleset_json(piruleset.build_ruleset())

        self.assertIsInstance(rendered, str)
        self.assertTrue(
            rendered.endswith("\n"),
            "rendered JSON must end with exactly one trailing newline",
        )
        self.assertFalse(
            rendered.endswith("\n\n"),
            "rendered JSON must not end with two trailing newlines",
        )

    def test_render_ruleset_json_round_trips_to_the_input_dict(self) -> None:
        ruleset = piruleset.build_ruleset()

        rendered = piruleset.render_ruleset_json(ruleset)

        self.assertEqual(json.loads(rendered), ruleset)

    def test_render_ruleset_json_survives_quote_and_backslash_in_paths(
        self,
    ) -> None:
        # A quote or backslash in the data must not produce invalid JSON:
        # the renderer builds with json.dumps, never string substitution.
        ruleset = piruleset.build_ruleset()
        ruleset["rules"][4]["parameters"]["restricted_file_paths"] = [
            '.github/work"flows/**',
            "templates\\zoo\\settings/**",
        ]

        rendered = piruleset.render_ruleset_json(ruleset)

        self.assertEqual(json.loads(rendered), ruleset)


class GoldenRulesetFixtureTests(unittest.TestCase):
    """Behaviour 8: the golden fixture is a no-production-change pin.

    The comparison is on parsed structures, not raw bytes - key ordering
    and indentation are not part of the contract
    (``tests/fixtures/README.md``).
    """

    FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "golden_ruleset.json"

    def test_golden_fixture_parses_as_json_with_the_recipes_key_set(
        self,
    ) -> None:
        fixture = json.loads(self.FIXTURE_PATH.read_text(encoding="utf-8"))

        self.assertIsInstance(fixture, dict)
        self.assertEqual(
            set(fixture),
            {
                "name",
                "target",
                "source_type",
                "enforcement",
                "conditions",
                "rules",
                "bypass_actors",
            },
        )

    def test_golden_fixture_matches_the_rendered_output_structure(self) -> None:
        fixture = json.loads(self.FIXTURE_PATH.read_text(encoding="utf-8"))
        rendered = piruleset.render_ruleset_json(piruleset.build_ruleset())

        self.assertEqual(json.loads(rendered), fixture)


class WriteRulesetTests(unittest.TestCase):
    """Behaviours 3+4: default output path and writing the rendered text.

    Behaviour 3 ("default_output_path") has no non-obvious input, output,
    edge or error, so its assertion is folded into this class per the
    plan's sequencing note. Behaviour 5's clobber/force edge is tested in
    :class:`WriteRulesetClobberTests` below.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_default_output_path_is_the_target_slash_github_ruleset_json(
        self,
    ) -> None:
        # Behaviour 3, folded in: pure path join, no filesystem touch.
        self.assertEqual(
            piruleset.default_output_path(self.tmpdir),
            self.tmpdir / ".github-ruleset.json",
        )

    def test_write_ruleset_creates_the_file_verbatim_and_returns_the_path(
        self,
    ) -> None:
        text = piruleset.render_ruleset_json(piruleset.build_ruleset())
        output = self.tmpdir / ".github-ruleset.json"

        written = piruleset.write_ruleset(output, text)

        self.assertTrue(output.is_file())
        self.assertEqual(
            output.read_text(encoding="utf-8"),
            text,
            "the file must hold the text verbatim, UTF-8",
        )
        self.assertEqual(written, output)

    def test_write_ruleset_raises_ruleset_error_when_the_parent_is_missing(
        self,
    ) -> None:
        output = self.tmpdir / "nonexistent" / "sub" / "ruleset.json"

        with self.assertRaises(piruleset.RulesetError) as ctx:
            piruleset.write_ruleset(output, "{}\n")

        # The error names the absent directory.
        self.assertIn(str(output.parent), str(ctx.exception))
        # Nothing partial is left behind: no file at any level, and the
        # parent tree was never created.
        self.assertFalse(output.exists())
        self.assertFalse((self.tmpdir / "nonexistent").exists())


class WriteRulesetClobberTests(unittest.TestCase):
    """Behaviour 5: write_ruleset refuses to clobber an existing path.

    The plan (behaviour 5) pins that with an existing file at the output
    path and ``force=False`` the module's single error is raised naming
    the path and the ``--force`` flag, and the file's original bytes
    survive byte-identical; with ``force=True`` the same call
    overwrites; a path that exists but is a directory raises rather
    than silently succeeding.
    """

    SENTINEL = b"unrelated\n"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_write_ruleset_refuses_to_clobber_an_existing_file_when_force_is_false(
        self,
    ) -> None:
        path = self.tmpdir / ".github-ruleset.json"
        path.write_bytes(self.SENTINEL)
        text = "{}\n"

        with self.assertRaises(piruleset.RulesetError) as ctx:
            piruleset.write_ruleset(path, text)

        message = str(ctx.exception)
        # The error names the existing path and the --force flag.
        self.assertIn(str(path), message, "the error must name the existing path")
        self.assertIn(
            "force",
            message.lower(),
            "the error must mention the --force flag",
        )
        # The original bytes survive byte-identical.
        self.assertEqual(
            path.read_bytes(),
            self.SENTINEL,
            "the refused write must leave the original bytes untouched",
        )

    def test_write_ruleset_overwrites_the_existing_file_when_force_is_true(
        self,
    ) -> None:
        path = self.tmpdir / ".github-ruleset.json"
        path.write_bytes(self.SENTINEL)
        text = "{}\n"

        written = piruleset.write_ruleset(path, text, force=True)

        self.assertEqual(written, path)
        self.assertEqual(
            path.read_bytes(),
            text.encode("utf-8"),
            "with force=True the file must hold the new text",
        )

    def test_write_ruleset_raises_ruleset_error_when_path_is_a_directory(
        self,
    ) -> None:
        path = self.tmpdir / "ruleset-dir"
        path.mkdir()

        with self.assertRaises(piruleset.RulesetError):
            # force=False is picked deliberately: a write to a directory
            # must not silently succeed before the force flag is even in
            # play.
            piruleset.write_ruleset(path, "{}\n", force=False)


if __name__ == "__main__":
    unittest.main()
