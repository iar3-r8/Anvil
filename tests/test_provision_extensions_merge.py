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


if __name__ == "__main__":
    unittest.main()
