"""RED tests for the ``_merge_extensions()`` pure helper in
``anvilkit/provision.py``.

Written before the implementation (TDD) for behaviour 14 of
``plans/package-registry-context.md`` (section 3, Group D): the merge of
``.vscode/extensions.json`` ``recommendations`` that preserves everything
else in the file.

The helper does not exist yet. The module imports it once at top level
inside a guarded ``try/except ImportError`` and binds ``None`` in the red
state; the shared ``_merge()`` wrapper then asserts the binding is not
``None`` before calling. While the helper is missing, every test therefore
FAILs on that assertion — "the helper does not exist yet", asserted —
rather than an ``ImportError`` crash. The moment the helper lands, every
test proceeds to its real assertions unchanged.

The rendered text for every fixture is produced by
``render.extensions_settings()`` (reading the real
``templates/extensions.json.template``); no rendered JSON is hand-written.
Per plan section 2.2, "preserved" means *value-preserved*, not
byte-preserved: assertions are on parsed structures and on key order,
never on raw bytes.

Return convention (like ``_merge_mcp_servers``, deliberately NOT the
``None`` "unchanged" convention of ``_merge_roomodes``): the helper always
returns the merged text. Detecting "unchanged" belongs to the
provisioning step, which compares before writing.

The step-level parts of the behaviour ledger (raising under ``dry_run``,
original on-disk bytes unchanged) are the provisioning step's concern and
are covered with the step once it is wired; the pure helper here is
required only to raise.
"""

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import provision, render  # noqa: E402
from tests.test_provision import ProvisionCase, plan  # noqa: E402
from tests.test_provision_mcp_merge import _provision_fresh  # noqa: E402

try:
    from anvilkit.provision import _merge_extensions  # noqa: E402
except ImportError:  # red state: helper not implemented yet
    _merge_extensions = None

# The source argument used in error-message assertions, so a test proves the
# helper names the offending file without ever touching a real path.
SOURCE = "repo/.vscode/extensions.json"

# The recommendation the current template renders, as stated by the
# behaviour ledger; asserted through the real renderer, never hard-coded
# into an expectation.
ZOO_CODE = "zoocodeorganization.zoo-code"


def _rendered() -> str:
    """Render ``.vscode/extensions.json`` via the real renderer."""
    return render.extensions_settings()


def _existing(data) -> str:
    """Build an existing-file fixture as a JSON string."""
    return json.dumps(data, indent=4)


def _merge(existing_text, rendered_text, source=SOURCE):
    """Invoke ``_merge_extensions``, asserting the red state first.

    While the helper is missing the module-level guard bound ``None`` and
    this assertion makes the test FAIL — for the expected reason — instead
    of crashing with an ``ImportError`` or a ``TypeError`` from calling
    ``None``. Once the helper exists the guard is a no-op and the call is
    unchanged.
    """
    assert (
        _merge_extensions is not None
    ), "_merge_extensions is not implemented in anvilkit.provision (red state)"

    return _merge_extensions(existing_text, rendered_text, source)


def _recommendations(merged_text) -> list:
    return json.loads(merged_text)["recommendations"]


class Behaviour14MergeTests(unittest.TestCase):
    """Behaviour 14 (core): merge ``recommendations``, preserve the rest.

    Existing entries keep their order, rendered entries missing from the
    existing file are appended after them, and every other top-level key
    survives in place.
    """

    def setUp(self):
        self.existing_text = _existing(
            {
                "recommendations": ["ms-python.python"],
                "unwantedRecommendations": ["x"],
            }
        )
        self.rendered_text = _rendered()
        # Sanity of the fixture itself: the rendered text is what the
        # ledger says it is, read through the real renderer.
        rendered = json.loads(self.rendered_text)
        self.assertEqual(
            rendered["recommendations"],
            [ZOO_CODE],
            "Test fixture precondition: the template must recommend "
            "only zoocodeorganization.zoo-code",
        )

    def test_recommendations_existing_first_appended_after(self):
        result = _merge(self.existing_text, self.rendered_text)
        self.assertEqual(
            _recommendations(result),
            ["ms-python.python", ZOO_CODE],
            "Existing recommendations must come first; missing rendered "
            "ones must be appended after them",
        )

    def test_unwanted_recommendations_preserved(self):
        result = _merge(self.existing_text, self.rendered_text)
        parsed = json.loads(result)
        self.assertEqual(
            parsed.get("unwantedRecommendations"),
            ["x"],
            "unwantedRecommendations must survive the merge untouched",
        )

    def test_unwanted_recommendations_survive_in_place(self):
        # "In place": key order of the existing file is preserved (the
        # merge re-emits with json.dumps, so insertion order is the order).
        result = _merge(self.existing_text, self.rendered_text)
        self.assertEqual(
            list(json.loads(result).keys()),
            ["recommendations", "unwantedRecommendations"],
            "Other top-level keys must survive in place, not be moved",
        )

    def test_existing_recommendation_order_preserved(self):
        existing_text = _existing(
            {
                "recommendations": [
                    "editorconfig.editorconfig",
                    "esbenp.prettier-vscode",
                ],
            }
        )
        result = _merge(existing_text, self.rendered_text)
        self.assertEqual(
            _recommendations(result),
            [
                "editorconfig.editorconfig",
                "esbenp.prettier-vscode",
                ZOO_CODE,
            ],
            "The existing order of recommendations must be preserved, "
            "with rendered ones appended after",
        )


class Behaviour14EdgeTests(unittest.TestCase):
    """Behaviour 14 (edges): no duplication, empty file, missing key."""

    def setUp(self):
        self.rendered_text = _rendered()

    def test_already_present_entry_is_not_duplicated(self):
        existing_text = _existing(
            {
                "recommendations": [ZOO_CODE, "ms-python.python"],
                "unwantedRecommendations": ["x"],
            }
        )
        result = _merge(existing_text, self.rendered_text)
        self.assertEqual(
            _recommendations(result),
            [ZOO_CODE, "ms-python.python"],
            "An entry already present in recommendations must not be "
            "duplicated; its existing position must be kept",
        )
        parsed = json.loads(result)
        self.assertEqual(
            parsed.get("unwantedRecommendations"),
            ["x"],
            "unwantedRecommendations must survive the no-change merge too",
        )

    def test_empty_existing_returns_rendered_verbatim(self):
        result = _merge("", self.rendered_text)
        self.assertEqual(
            result,
            self.rendered_text,
            "Empty existing text must yield the rendered text verbatim",
        )

    def test_empty_existing_result_parses_to_rendered_structure(self):
        result = _merge("", self.rendered_text)
        self.assertEqual(
            json.loads(result),
            json.loads(self.rendered_text),
            "Parsed structure of first-run output must equal the rendered "
            "structure",
        )

    def test_missing_recommendations_key_is_created(self):
        existing_text = _existing({"unwantedRecommendations": ["x"]})
        result = _merge(existing_text, self.rendered_text)
        parsed = json.loads(result)
        self.assertEqual(
            parsed["recommendations"],
            [ZOO_CODE],
            "A missing recommendations key must be created with the "
            "rendered recommendations",
        )
        self.assertEqual(
            parsed.get("unwantedRecommendations"),
            ["x"],
            "Other top-level keys must survive when the key is created",
        )

    def test_missing_recommendations_key_among_other_keys(self):
        existing_text = _existing({"unwantedRecommendations": ["x"], "custom": 1})
        result = _merge(existing_text, self.rendered_text)
        parsed = json.loads(result)
        self.assertEqual(parsed["recommendations"], [ZOO_CODE])
        self.assertEqual(parsed.get("custom"), 1, "Other top-level key lost")


class Behaviour14ErrorTests(unittest.TestCase):
    """Behaviour 14 (errors): the pure helper raises ``ProvisionError``
    naming the ``source`` for unmergeable input.

    The dry-run and on-disk-bytes parts of the ledger item are the
    provisioning step's concern; the helper's contract is simply to raise,
    never a bare ``json.JSONDecodeError`` (one exception type per module).
    """

    def setUp(self):
        self.rendered_text = _rendered()

    def test_invalid_existing_json_raises_naming_source(self):
        with self.assertRaises(provision.ProvisionError) as ctx:
            _merge("not json at all", self.rendered_text)
        self.assertIn(
            SOURCE,
            str(ctx.exception),
            "ProvisionError must name the source: {}".format(ctx.exception),
        )

    def test_recommendations_not_a_list_raises_naming_source(self):
        existing_text = _existing({"recommendations": "ms-python.python"})
        with self.assertRaises(provision.ProvisionError) as ctx:
            _merge(existing_text, self.rendered_text)
        self.assertIn(
            SOURCE,
            str(ctx.exception),
            "ProvisionError must name the source: {}".format(ctx.exception),
        )

    def test_recommendations_not_a_list_as_mapping_raises(self):
        existing_text = _existing({"recommendations": {"ms-python.python": True}})
        with self.assertRaises(provision.ProvisionError) as ctx:
            _merge(existing_text, self.rendered_text)
        self.assertIn(
            SOURCE,
            str(ctx.exception),
            "ProvisionError must name the source: {}".format(ctx.exception),
        )

    def test_existing_top_level_not_a_mapping_raises(self):
        # A top-level JSON array parses fine but cannot be merged into;
        # the helper must fail with its own error type, not crash.
        with self.assertRaises(provision.ProvisionError) as ctx:
            _merge('["ms-python.python"]', self.rendered_text)
        self.assertIn(
            SOURCE,
            str(ctx.exception),
            "ProvisionError must name the source: {}".format(ctx.exception),
        )

    def test_invalid_rendered_json_raises_provision_error_naming_source(self):
        # Invalid rendered JSON is a pipeline bug, not user fault, but it
        # is still ProvisionError: one exception type per module keeps the
        # provisioning step's single ``except`` holding (precedent:
        # RenderedTextErrorSemanticsTests in test_provision_mcp_merge.py).
        existing_text = _existing({"recommendations": ["ms-python.python"]})
        with self.assertRaises(provision.ProvisionError) as ctx:
            _merge(existing_text, "definitely not json")
        self.assertIn(
            SOURCE,
            str(ctx.exception),
            "ProvisionError must name the source: {}".format(ctx.exception),
        )


# ---------------------------------------------------------------------------
# Behaviour 15 — setup_repo merges .vscode/extensions.json instead of
# overwriting it (plan §3, Group D, item 15)
# ---------------------------------------------------------------------------


class Behaviour15SetupRepoWiringTests(ProvisionCase):
    """Behaviour 15: ``setup_repo`` merges ``.vscode/extensions.json``.

    End-to-end through the real entry path, mirroring the behaviour 6
    (``.roo/mcp.json``) and behaviour 13 (``.roomodes``) wiring tests:
    the target is provisioned once, the deployed file is modified by
    hand, and a second ``setup_repo`` run must reconcile with the
    rendered output via ``_merge_extensions`` and report the outcome
    distinctly from a first-run injection. The merge helper's own
    semantics are proven at the unit level in the behaviour 14 classes
    above; this class proves the *wiring*.

    RED state (written before the rewire): ``_write_extensions`` still
    calls ``_write`` and overwrites the file wholesale on every run, so

    * a hand-added recommendation is gone after the second run;
    * a no-change second run reports ``Injected`` and rewrites the
      bytes instead of reporting ``Skipped ... (already up to date)``;
    * a merging second run reports ``Injected`` instead of ``Merged``;
    * a malformed existing file is silently clobbered instead of
      raising ``ProvisionError`` (behaviour 7 precedent).

    The first-run golden and the dry-run locks pass in the red state
    too: they lock what the rewire must not change (the first-run line
    stays the ``_write`` injection line, so the existing tests keep
    passing).
    """

    HAND_ADDED = "ms-python.python"

    def _extensions_report_lines(self, messages):
        """The report lines emitted by the extensions step for one run."""
        marker = ".vscode/extensions.json"
        return [line for line in messages if marker in line]

    def _hand_add_recommendation(self, name):
        """Hand-add a recommendation to the deployed extensions.json."""
        path = self.target / ".vscode" / "extensions.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        recommendations = list(data.get("recommendations") or [])
        if name not in recommendations:
            recommendations.append(name)
        data["recommendations"] = recommendations
        path.write_text(json.dumps(data, indent=4), encoding="utf-8")
        return path

    def _provision_with_fresh_messages(self, **kwargs):
        """Provision with a fresh per-run message list, returned for asserts."""
        return _provision_fresh(self.target, **kwargs)

    def test_second_run_preserves_hand_added_recommendation(self):
        # B15 core: provision, add a recommendation by hand, provision again.
        self._provision_with_fresh_messages()
        self._hand_add_recommendation(self.HAND_ADDED)
        self._provision_with_fresh_messages()

        recommendations = self.read_json(
            ".vscode/extensions.json"
        )["recommendations"]
        self.assertIn(
            self.HAND_ADDED,
            recommendations,
            "The hand-added recommendation must survive a second "
            "setup_repo run (merge, not overwrite): "
            "{}".format(recommendations),
        )
        self.assertIn(
            ZOO_CODE,
            recommendations,
            "The Anvil recommendation must still be present after the "
            "second run: {}".format(recommendations),
        )
        self.assertEqual(
            len(recommendations),
            len(set(recommendations)),
            "Every recommendation must appear exactly once: "
            "{}".format(recommendations),
        )

    def test_first_run_output_matches_render_extensions_settings(self):
        # Lock: the first run must still produce exactly what the renderer
        # produces (parse and compare), unchanged from today.
        self._provision_with_fresh_messages()

        on_disk = self.read_json(".vscode/extensions.json")
        expected = json.loads(render.extensions_settings())
        self.assertEqual(
            on_disk,
            expected,
            "First-run output must be semantically identical to "
            "render.extensions_settings()",
        )

    def test_second_run_without_changes_reports_skipped_and_leaves_bytes_unchanged(self):
        # B15 edge: a no-change second run reports skipped/"already up to
        # date" and leaves the file bytes unchanged (bytes, not mtime).
        self._provision_with_fresh_messages()
        path = self.target / ".vscode" / "extensions.json"
        before = path.read_bytes()

        second_messages = self._provision_with_fresh_messages()
        second_lines = self._extensions_report_lines(second_messages)
        self.assertTrue(
            second_lines, "Second run must report on the extensions step"
        )
        self.assertTrue(
            any("Skipped" in line or "up to date" in line for line in second_lines),
            "A no-change second run must report the extensions step as "
            "skipped (already up to date): {}".format(second_lines),
        )
        self.assertFalse(
            any("Merged" in line or "Injected" in line for line in second_lines),
            "A no-change second run must not report a merge or an "
            "injection: {}".format(second_lines),
        )
        self.assertEqual(
            path.read_bytes(),
            before,
            "A no-change second run must not rewrite the file's bytes",
        )

    def test_second_run_report_says_merged_and_differs_from_first_run(self):
        # B15 edge: the file holds only the hand-added recommendation, so
        # the second run adds the Anvil recommendation and must report
        # "Merged", distinct from the first-run line.
        first_messages = self._provision_with_fresh_messages()
        path = self.target / ".vscode" / "extensions.json"
        path.write_text(
            json.dumps({"recommendations": [self.HAND_ADDED]}, indent=4),
            encoding="utf-8",
        )
        second_messages = self._provision_with_fresh_messages()

        first_lines = self._extensions_report_lines(first_messages)
        second_lines = self._extensions_report_lines(second_messages)
        self.assertTrue(
            first_lines, "First run must report on the extensions step"
        )
        self.assertTrue(
            any("Injected" in line for line in first_lines),
            "A first run on a fresh repo must keep reporting the "
            "extensions step as injected: {}".format(first_lines),
        )
        self.assertTrue(
            second_lines, "Second run must report on the extensions step"
        )
        self.assertTrue(
            any("Merged" in line for line in second_lines),
            "A second run that merges must say 'Merged', distinct from "
            "the first-run line: {}".format(second_lines),
        )
        self.assertNotEqual(
            first_lines,
            second_lines,
            "The extensions step report must differ between an injection "
            "and a merge",
        )
        recommendations = self.read_json(
            ".vscode/extensions.json"
        )["recommendations"]
        self.assertEqual(
            recommendations,
            [self.HAND_ADDED, ZOO_CODE],
            "The hand-added entry must survive with its position "
            "(existing first); the Anvil recommendation is appended "
            "after: {}".format(recommendations),
        )

    def _seed_extensions_json(self, content):
        """Hand-write the target's .vscode/extensions.json and return its path."""
        path = self.target / ".vscode" / "extensions.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_invalid_json_existing_file_raises_provision_error_naming_path(self):
        # B15 edge (behaviour 7 precedent at the wiring level): a
        # malformed existing file must fail cleanly, not be clobbered.
        path = self._seed_extensions_json("not json at all")
        before = path.read_bytes()

        with self.assertRaises(provision.ProvisionError) as ctx:
            self._provision_with_fresh_messages()

        self.assertIn(
            str(path),
            str(ctx.exception),
            "ProvisionError must name the offending path: {}".format(
                ctx.exception
            ),
        )
        self.assertEqual(
            path.read_bytes(),
            before,
            "The original bytes on disk must be unchanged after the error",
        )

    def test_invalid_json_error_is_raised_under_dry_run(self):
        # B15 edge: a dry run must surface the same fault and must not
        # hide it (validation before the dry_run check, B7 precedent).
        path = self._seed_extensions_json("not json at all")
        before = path.read_bytes()

        with self.assertRaises(provision.ProvisionError) as ctx:
            self._provision_with_fresh_messages(dry_run=True)

        self.assertIn(
            str(path),
            str(ctx.exception),
            "A dry run must surface the same fault: {}".format(ctx.exception),
        )
        self.assertEqual(
            path.read_bytes(),
            before,
            "A dry run must not modify the file while reporting the fault",
        )

    def test_dry_run_on_fresh_target_writes_no_extensions_json(self):
        self._provision_with_fresh_messages(dry_run=True)
        self.assertFalse(
            (self.target / ".vscode" / "extensions.json").exists(),
            "A dry run on a fresh repo must not create "
            ".vscode/extensions.json",
        )

    def test_dry_run_over_existing_file_changes_no_bytes(self):
        self._provision_with_fresh_messages()
        path = self._hand_add_recommendation(self.HAND_ADDED)
        before = path.read_bytes()

        self._provision_with_fresh_messages(dry_run=True)

        self.assertEqual(
            path.read_bytes(),
            before,
            "A dry run must not modify an existing .vscode/extensions.json",
        )


if __name__ == "__main__":
    unittest.main()
