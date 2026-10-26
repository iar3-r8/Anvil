"""Tests for anvilkit.tiers - mapping a tier id to a GPU slot plan.

Written before the implementation (TDD, ``plans/vllm-tier-setups.md``,
behaviour 3: "tier_plan_is_strict", with the behaviour 1 "tier_table"
assertions folded in, since behaviour 1 has no dedicated cycle).

The production module ``anvilkit.tiers`` does not exist yet, so every test
loads it through ``_tiers``, which fails with a clear assertion instead of
letting a collection-time ImportError mask the reason the suite is red.

Attribute names the tests target where the plan leaves them open:

* each entry of ``tiers.TIERS`` exposes ``id``, ``label`` and ``coder_slots``;
* a valid ``tiers.plan(...)`` call returns an object exposing ``coder_slots``;
* the single exception type is ``tiers.TierError``.
"""

import importlib
import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TIER_IDS = ["low", "mid", "high"]


class TiersTestCase(unittest.TestCase):
    def _tiers(self):
        """Import anvilkit.tiers, failing clearly if the module is absent."""
        spec = importlib.util.find_spec("anvilkit.tiers")
        self.assertIsNotNone(
            spec,
            "anvilkit.tiers cannot be imported; the tier plan module has not "
            "been implemented yet",
        )
        return importlib.import_module("anvilkit.tiers")


class TestTierTable(TiersTestCase):
    """Behaviour 1 folded into the behaviour 3 cycle."""

    def test_tiers_is_an_ordered_sequence_of_exactly_three_entries(self):
        tiers = self._tiers()
        self.assertIsInstance(tiers.TIERS, (list, tuple))
        self.assertEqual(len(tiers.TIERS), 3)

    def test_tiers_ids_are_low_mid_high_in_that_order(self):
        tiers = self._tiers()
        self.assertEqual([entry.id for entry in tiers.TIERS], TIER_IDS)

    def test_tiers_labels_name_the_gpu_count_and_vram_from_the_issue(self):
        tiers = self._tiers()
        by_id = {entry.id: entry for entry in tiers.TIERS}
        # Issue: low is 1 GPU / 40 GB; mid is 2 GPUs; high is 8 GPUs / 320 GB.
        self.assertIn("1 GPU", by_id["low"].label)
        self.assertIn("40 GB", by_id["low"].label)
        self.assertIn("2 GPU", by_id["mid"].label)
        self.assertIn("8 GPU", by_id["high"].label)
        self.assertIn("320 GB", by_id["high"].label)

    def test_tiers_coder_slots_match_the_slot_plan(self):
        tiers = self._tiers()
        by_id = {entry.id: entry for entry in tiers.TIERS}
        # Low reuses one device id for everything (behaviour 5: "1 coder
        # slot"); mid is today's shipped default with coder on two GPUs
        # (behaviour 5: mid accepts exactly "1,2"); high writes four device
        # keys as 0/1/2/3, so its coder also spans two keys (behaviour 16).
        self.assertEqual(by_id["low"].coder_slots, 1)
        self.assertEqual(by_id["mid"].coder_slots, 2)
        self.assertEqual(by_id["high"].coder_slots, 2)


class TestPlanIsStrict(TiersTestCase):
    """Behaviour 3: an unknown or differently-cased id fails loudly."""

    def test_plan_unknown_id_raises_tier_error_listings_all_tiers(self):
        tiers = self._tiers()
        with self.assertRaises(tiers.TierError) as ctx:
            tiers.plan("bogus")
        message = str(ctx.exception)
        for tier_id in TIER_IDS:
            self.assertIn(tier_id, message)

    def test_plan_rejects_wrong_case_without_lowering(self):
        tiers = self._tiers()
        # "LOW" must not resolve to "low" - strictness is deliberate, so a
        # typo fails loudly rather than resolving silently.
        with self.assertRaises(tiers.TierError) as ctx:
            tiers.plan("LOW")
        message = str(ctx.exception)
        for tier_id in TIER_IDS:
            self.assertIn(tier_id, message)

    def test_plan_rejects_surrounding_whitespace_without_stripping(self):
        tiers = self._tiers()
        # " low " must not resolve to "low" - no stripping.
        with self.assertRaises(tiers.TierError) as ctx:
            tiers.plan(" low ")
        message = str(ctx.exception)
        for tier_id in TIER_IDS:
            self.assertIn(tier_id, message)

    def test_plan_valid_mid_returns_plan_exposing_coder_slots(self):
        tiers = self._tiers()
        plan = tiers.plan("mid")
        self.assertEqual(plan.coder_slots, 2)


class TestCoderIdsBroadcast(TiersTestCase):
    """Behaviour 4: one supplied coder id fills every coder slot of the plan."""

    def _split_coder_ids(self):
        """The split_coder_ids callable, failing clearly if unimplemented."""
        tiers = self._tiers()
        self.assertTrue(
            hasattr(tiers, "split_coder_ids"),
            "anvilkit.tiers.split_coder_ids has not been implemented yet "
            "(behaviour 4: coder_ids_broadcast in plans/vllm-tier-setups.md)",
        )
        return tiers.split_coder_ids

    def test_one_id_fills_every_coder_slot_of_every_tier(self):
        tiers = self._tiers()
        split_coder_ids = self._split_coder_ids()
        for tier in tiers.TIERS:
            with self.subTest(tier=tier.id):
                plan = tiers.plan(tier.id)
                ids = split_coder_ids(plan, "5")
                self.assertIsInstance(ids, (tuple, list))
                self.assertEqual(("5",) * plan.coder_slots, tuple(ids))

    def test_one_id_fills_the_single_coder_slot_of_the_low_tier(self):
        tiers = self._tiers()
        split_coder_ids = self._split_coder_ids()
        plan = tiers.plan("low")
        self.assertEqual(("5",), tuple(split_coder_ids(plan, "5")))

    def test_split_coder_ids_rejects_an_empty_string(self):
        tiers = self._tiers()
        split_coder_ids = self._split_coder_ids()
        plan = tiers.plan("low")
        with self.assertRaises(tiers.TierError):
            split_coder_ids(plan, "")

    def test_split_coder_ids_rejects_a_whitespace_only_string(self):
        tiers = self._tiers()
        split_coder_ids = self._split_coder_ids()
        plan = tiers.plan("low")
        with self.assertRaises(tiers.TierError):
            split_coder_ids(plan, "   ")


class TestCoderIdsRejectOverflow(TiersTestCase):
    """Behaviour 5: more coder ids than the tier has slots fails loudly.

    ``split_coder_ids`` must not silently broadcast or drop ids when the user
    names more GPUs than the tier's coder model spans. The rejection names the
    tier and its coder-slot count so the user sees what to change.
    """

    def test_low_tier_rejects_two_coder_ids_naming_the_tier_and_slot_count(self):
        tiers = self._tiers()
        plan = tiers.plan("low")
        with self.assertRaises(tiers.TierError) as ctx:
            tiers.split_coder_ids(plan, "1,2")
        message = str(ctx.exception)
        # The error must name the tier and its coder-slot count.
        self.assertIn(plan.id, message)
        self.assertIn(str(plan.coder_slots), message)

    def test_mid_tier_rejects_three_coder_ids_naming_the_tier_and_slot_count(self):
        tiers = self._tiers()
        plan = tiers.plan("mid")
        with self.assertRaises(tiers.TierError) as ctx:
            tiers.split_coder_ids(plan, "1,2,3")
        message = str(ctx.exception)
        self.assertIn(plan.id, message)
        self.assertIn(str(plan.coder_slots), message)

    def test_mid_tier_accepts_exactly_two_coder_ids(self):
        tiers = self._tiers()
        plan = tiers.plan("mid")
        # Exactly as many ids as slots is the accepted path, not overflow.
        self.assertEqual(("1", "2"), tuple(tiers.split_coder_ids(plan, "1,2")))


class TestAssignSlots(TiersTestCase):
    """Behaviour 6: assign_slots, with the behaviour 2 (tier_plan) slot
    defaults folded in, since behaviour 2 has no dedicated cycle.

    Attribute names the tests target where the plan leaves them open:

    * ``tiers.assign(plan, generic, coder_ids, embedder)`` takes the tier
      plan, the answered generic id, the *already-split* coder tuple (exactly
      as returned by ``split_coder_ids``) and the answered embedder id;
    * it returns four ``(key, value)`` pairs in the order
      ``LLM_DEVICE_ID_0``, ``LLM_DEVICE_ID_1``, ``LLM_DEVICE_ID_2``,
      ``INDEXER_STORAGE_DEVICE_ID``;
    * the plan object exposes its slot defaults as ``default_generic``,
      ``default_coder`` and ``default_embedder``, as raw strings - the coder
      default feeds straight back into ``split_coder_ids``.
    """

    def _assign(self):
        """The assign callable, failing clearly if unimplemented."""
        tiers = self._tiers()
        self.assertTrue(
            hasattr(tiers, "assign"),
            "anvilkit.tiers.assign has not been implemented yet "
            "(behaviour 6: assign_slots in plans/vllm-tier-setups.md)",
        )
        return tiers.assign

    def _assert_plan_has_slot_defaults(self, plan):
        """Guard the plan's slot-default attributes with a clear failure."""
        for attr in ("default_generic", "default_coder", "default_embedder"):
            self.assertTrue(
                hasattr(plan, attr),
                "plan object is missing '{}' "
                "(behaviour 2: tier_plan in plans/vllm-tier-setups.md)".format(attr),
            )

    def test_mid_plan_defaults_match_todays_env_values(self):
        tiers = self._tiers()
        plan = tiers.plan("mid")
        self._assert_plan_has_slot_defaults(plan)
        # Mid is today's shipped default, so its slot defaults must be
        # identical to what init writes today: generic 0, coder 0,1,
        # embedder 2.
        self.assertEqual(plan.default_generic, "0")
        self.assertEqual(plan.default_coder, "0,1")
        self.assertEqual(plan.default_embedder, "2")

    def test_assign_mid_tier_returns_four_pairs_in_env_key_order(self):
        tiers = self._tiers()
        assign = self._assign()
        plan = tiers.plan("mid")
        # The coder argument is the split tuple, not the raw string -
        # split_coder_ids stays the single validation seam.
        coder_ids = tiers.split_coder_ids(plan, "0,1")
        pairs = assign(plan, "0", coder_ids, "2")
        self.assertEqual(
            [tuple(pair) for pair in pairs],
            [
                ("LLM_DEVICE_ID_0", "0"),
                ("LLM_DEVICE_ID_1", "0"),
                ("LLM_DEVICE_ID_2", "1"),
                ("INDEXER_STORAGE_DEVICE_ID", "2"),
            ],
        )

    def test_assign_high_tier_places_two_coder_ids_and_embedder(self):
        tiers = self._tiers()
        assign = self._assign()
        plan = tiers.plan("high")
        # High writes the four device keys as 0 / 1 / 2 / 3 (behaviour 16).
        coder_ids = tiers.split_coder_ids(plan, "1,2")
        pairs = assign(plan, "0", coder_ids, "3")
        self.assertEqual(
            [tuple(pair) for pair in pairs],
            [
                ("LLM_DEVICE_ID_0", "0"),
                ("LLM_DEVICE_ID_1", "1"),
                ("LLM_DEVICE_ID_2", "2"),
                ("INDEXER_STORAGE_DEVICE_ID", "3"),
            ],
        )

    def test_assign_low_tier_reuses_one_id_for_all_four_pairs(self):
        tiers = self._tiers()
        assign = self._assign()
        plan = tiers.plan("low")
        # The low tier has exactly one GPU to name, so a single id fills all
        # four pairs - a single-GPU host never names a device it does not
        # have.
        coder_ids = tiers.split_coder_ids(plan, "3")
        pairs = assign(plan, "3", coder_ids, "3")
        self.assertEqual(
            [tuple(pair) for pair in pairs],
            [
                ("LLM_DEVICE_ID_0", "3"),
                ("LLM_DEVICE_ID_1", "3"),
                ("LLM_DEVICE_ID_2", "3"),
                ("INDEXER_STORAGE_DEVICE_ID", "3"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
