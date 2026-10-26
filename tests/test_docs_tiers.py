"""Tests for behaviour 18 ("docs_cover_both_tiers") of
``plans/vllm-tier-setups.md``.

The file under test is ``doc/1-setting-up-backend.md``. Behaviour 18 is a
docs-only behaviour: the guide must carry a "Low Tier" and a "High Tier"
hardware section beside the existing "Mid Tier" one, each naming the
``config.yaml`` change that tier needs (``--tensor-parallel-size 1`` for
low, ``--tensor-parallel-size 8`` for high), and the flag table under
"Running without prompts" must carry a ``--tier NAME`` row.

Per the plan's error clause, every assertion here is structural — headings,
the per-section ``--tensor-parallel-size`` flag, and the table row — never
on prose, so the green step can word the sections freely.

The idiom follows ``tests/test_harvest_command.py``: a plain
``unittest.TestCase`` that reads the repo file once in ``setUp`` and asserts
on key phrases and structure, never on raw bytes.
"""

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DOC_PATH = REPO_ROOT / "doc" / "1-setting-up-backend.md"

_HEADING = re.compile(r"^(#{1,6})\s+")


def _heading_level(line):
    """The level (1-6) of a markdown heading line, or None for any other
    line."""
    match = _HEADING.match(line)
    return len(match.group(1)) if match else None


def _section_lines(lines, phrase):
    """The lines of the first markdown section whose heading contains
    *phrase*.

    The section runs from the line after that heading to the next heading of
    the same or higher level, so a ``####`` section ends at the next
    ``####``, ``###``, ``##`` or ``#``. Returns ``None`` when no heading
    contains *phrase*.
    """
    start = None
    for index, line in enumerate(lines):
        if _heading_level(line) is not None and phrase in line:
            start = index
            break
    if start is None:
        return None
    level = _heading_level(lines[start])
    end = len(lines)
    for index in range(start + 1, len(lines)):
        next_level = _heading_level(lines[index])
        if next_level is not None and next_level <= level:
            end = index
            break
    return lines[start + 1:end]


def _table_first_cells(lines):
    """The first cell of every markdown table row in *lines*, backticks
    stripped, separator rows omitted."""
    cells = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        first = stripped.lstrip("|").split("|", 1)[0].strip().strip("`")
        if re.fullmatch(r":?-+:?", first):
            continue
        cells.append(first)
    return cells


class DocsTiersTestCase(unittest.TestCase):
    """Shared loading for ``doc/1-setting-up-backend.md``; a missing file
    fails at load time with the path named."""

    def setUp(self):
        self.assertTrue(
            DOC_PATH.is_file(),
            "doc file does not exist or is not a regular file: %s"
            % DOC_PATH,
        )
        self.text = DOC_PATH.read_text(encoding="utf-8")
        self.lines = self.text.splitlines()


class TestTierHeadings(DocsTiersTestCase):
    """The document carries a Low Tier and a High Tier hardware section
    heading beside the existing Mid Tier one — all three in one document."""

    def test_doc_carries_a_mid_tier_heading(self):
        self.assertTrue(
            any(
                "Mid Tier" in line
                for line in self.lines
                if _heading_level(line) is not None
            ),
            "no markdown heading containing 'Mid Tier' in %s" % DOC_PATH,
        )

    def test_doc_carries_a_low_tier_heading(self):
        self.assertTrue(
            any(
                "Low Tier" in line
                for line in self.lines
                if _heading_level(line) is not None
            ),
            "no markdown heading containing 'Low Tier' in %s" % DOC_PATH,
        )

    def test_doc_carries_a_high_tier_heading(self):
        self.assertTrue(
            any(
                "High Tier" in line
                for line in self.lines
                if _heading_level(line) is not None
            ),
            "no markdown heading containing 'High Tier' in %s" % DOC_PATH,
        )


class TestTierSectionConfigChange(DocsTiersTestCase):
    """Each new tier section states the ``config.yaml`` change that tier
    needs: ``--tensor-parallel-size 1`` for low, ``--tensor-parallel-size
    8`` for high. The fragment is asserted within the section only, so the
    flag must live in the right tier, not merely somewhere in the file."""

    def test_low_tier_section_states_tensor_parallel_size_1(self):
        section = _section_lines(self.lines, "Low Tier")
        self.assertIsNotNone(
            section,
            "no 'Low Tier' section to inspect in %s" % DOC_PATH,
        )
        self.assertIn(
            "--tensor-parallel-size 1",
            "\n".join(section),
            "the 'Low Tier' section does not state '--tensor-parallel-size "
            "1' (the config.yaml change the low tier needs)",
        )

    def test_high_tier_section_states_tensor_parallel_size_8(self):
        section = _section_lines(self.lines, "High Tier")
        self.assertIsNotNone(
            section,
            "no 'High Tier' section to inspect in %s" % DOC_PATH,
        )
        self.assertIn(
            "--tensor-parallel-size 8",
            "\n".join(section),
            "the 'High Tier' section does not state "
            "'--tensor-parallel-size 8' (the config.yaml change the high "
            "tier needs)",
        )


class TestFlagTableTierRow(DocsTiersTestCase):
    """The flag table carries a ``--tier NAME`` row: a table row whose
    first cell is the ``--tier`` flag."""

    def test_flag_table_carries_a_tier_row(self):
        first_cells = _table_first_cells(self.lines)
        self.assertTrue(
            any(cell.startswith("--tier") for cell in first_cells),
            "no table row whose first cell is the '--tier' flag; table "
            "first cells seen: %r" % first_cells,
        )
