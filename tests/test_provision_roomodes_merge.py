"""RED tests for the ``_merge_roomodes()`` merge in ``anvilkit/provision.py``.

Written before the implementation (TDD) for behaviours 9, 10, 11 and 12
of ``plans/package-registry-context.md`` (section 3, Group C).

Behaviour 13 of the same plan — ``setup_repo`` must merge ``.roomodes``
instead of overwriting it — is covered end-to-end by
``Behaviour13SetupRepoWiringTests``. It reuses the ``ProvisionCase``
harness from ``tests/test_provision.py`` and the ``_provision_fresh``
helper from ``tests/test_provision_mcp_merge.py`` (no duplicated
machinery) and captures report lines with a list-append echo callback,
as the behaviour 6 wiring tests do.

The helper does not exist yet. The module imports it once at top level
inside a guarded ``try/except ImportError`` and binds ``None`` in the red
state; the shared ``_merge()`` wrapper then asserts the binding is not
``None`` before calling — including inside the error-path tests, so a
red-state failure is an ``AssertionError`` ("not implemented"), never a
``TypeError`` from calling ``None``. The moment the helper lands, every
test proceeds to its real assertions unchanged.

Design under test (plan §2.3): *decide with the parser, emit as text.*
Slugs already present are discovered by parsing the existing file with
``anvilkit.yamlio.loads()``; the APPENDED content is the template's own
bytes verbatim — no YAML re-serialization of anything. The result
therefore starts with the existing text byte-for-byte (plus a trailing
newline if the existing text lacked one), followed by the missing
template blocks. "Unchanged" is signalled by returning ``None``, the
``_merge_gitignore`` convention.

Template block fixtures come from the real
``templates/roo_template/.roomodes`` (three modes: docs-manager,
qna-tester, tdd-manager; 2-space item indent; ``>-`` folded scalars and
nested ``groups`` lists). Template files are data and may be asserted on
directly (plan §4, precedent PR #12); the module under test is never
asserted on by its source text.
"""

import re
import sys
import unittest
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import provision  # noqa: E402
from tests.test_provision import ProvisionCase  # noqa: E402
from tests.test_provision_mcp_merge import _provision_fresh  # noqa: E402

try:
    from anvilkit.provision import _merge_roomodes  # noqa: E402
except ImportError:  # red state: helper not implemented yet
    _merge_roomodes = None

# The source argument used in error-message assertions, so a test proves the
# helper names the offending file without ever touching a real path.
SOURCE = "repo/.roomodes"

# The real template: 3 modes, 2-space item indent, folded scalars, nested
# groups. Read once at import time; it is committed data, not a fixture to
# maintain.
TEMPLATE_TEXT = (REPO_ROOT / "templates" / "roo_template" / ".roomodes").read_text(
    encoding="utf-8"
)


def _merge(existing_text, template_text, source=SOURCE):
    # type: (str, str, str) -> Optional[str]
    """Invoke ``_merge_roomodes``, asserting the red state first.

    While the helper is missing the module-level guard bound ``None`` and
    this assertion makes the test FAIL — for the expected reason — instead
    of crashing with a ``TypeError`` from calling ``None``. Once the helper
    exists the guard is a no-op and the call is unchanged.
    """
    assert (
        _merge_roomodes is not None
    ), "_merge_roomodes is not implemented in anvilkit.provision (red state)"

    return _merge_roomodes(existing_text, template_text, source)


def _extract_block(template_text, slug):
    # type: (str, str) -> str
    """Return the raw text of one mode block from template text.

    A block begins at its ``- slug: <slug>`` line and runs until the next
    line at that same indentation beginning with ``- ``, or end of text —
    the split the helper must perform (plan §2.3). Extracting the expected
    substring this way pins the exact template bytes a verbatim-append
    assertion must find, without re-parsing the block as YAML.
    """
    lines = template_text.split("\n")
    start = None
    for index, line in enumerate(lines):
        if re.match(r"^\s*- slug:\s*{}\s*$".format(re.escape(slug)), line):
            start = index
            break
    if start is None:
        raise AssertionError("slug {!r} not found in template text".format(slug))
    indent = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith(indent + "- "):
            end = index
            break
    return "\n".join(lines[start:end])


def _template_slugs(template_text):
    # type: (str) -> List[str]
    return [
        match.group(1)
        for match in re.finditer(r"^\s*- slug:\s*(\S+)", template_text, re.M)
    ]


def _reindented_template(template_text, extra_spaces):
    # type: (str, int) -> str
    """Shift every indented line by ``extra_spaces`` further in.

    Turns the 2-space item indent of the real template into a 4-space one,
    producing a re-indented variant for which block boundaries must still
    be derived from the FIRST item's indentation, not a hard-coded value.
    """
    pad = " " * extra_spaces
    return "\n".join(
        pad + line if line.strip() else line for line in template_text.split("\n")
    )


# ---------------------------------------------------------------------------
# Fixtures for the existing-file side (hand-built YAML data)
# ---------------------------------------------------------------------------


def _existing_docs_manager_edited():
    """An existing ``.roomodes``: docs-manager with a user-edited fileRegex.

    The ``fileRegex`` line is the user edit the merge must preserve
    byte-for-byte; there is no qna-tester or tdd-manager block.
    """
    return (
        "customModes:\n"
        "  - slug: docs-manager\n"
        "    name: My Docs Mode\n"
        "    roleDefinition: >-\n"
        "      A heavily customised role. Mentions slug: not-a-mode inside\n"
        "      the folded scalar on purpose.\n"
        "    groups:\n"
        "      - read\n"
        "      - - edit\n"
        "        - fileRegex: (.*\\.(edited-user-regex-xyz)$)\n"
        "          description: User-edited regex, must survive byte-for-byte\n"
        "      - command\n"
    )


def _existing_all_three():
    """An existing ``.roomodes`` holding every template slug (with edits)."""
    return (
        "customModes:\n"
        "  - slug: docs-manager\n"
        "    name: Edited Docs Manager\n"
        "  - slug: qna-tester\n"
        "    name: Edited Q&A Tester\n"
        "  - slug: tdd-manager\n"
        "    name: Edited TDD Manager\n"
    )


def _existing_qna_only_block():
    """An existing ``.roomodes`` with a single (qna-tester) mode block."""
    return (
        "customModes:\n"
        "  - slug: qna-tester\n"
        "    name: Local Tester\n"
        "    roleDefinition: >-\n"
        "      A trimmed local version.\n"
        "    groups:\n"
        "      - read\n"
    )


def _existing_mapping_no_custommodes():
    """A mapping with other keys but no ``customModes`` at all."""
    return (
        "profile: anvil-user\n"
        "notes: hand-tuned file with other keys\n"
    )


def _existing_custommodes_null():
    """``customModes:`` present but null (nothing under the key)."""
    return "customModes:\n"


class RoomodesMergeBase(unittest.TestCase):
    """Shared red-state guard plus sanity pins on the real template data."""

    TEMPLATE = TEMPLATE_TEXT

    def setUp(self):
        # Sanity pins on the data file every behaviour leans on: if the
        # template's slug set changes, these fixtures must be revisited
        # deliberately, not discover the drift as a confusing failure.
        self.assertEqual(
            _template_slugs(self.TEMPLATE),
            ["docs-manager", "qna-tester", "tdd-manager"],
            "Template drift: slug set changed; update these fixtures deliberately",
        )
        self.assertTrue(
            self.TEMPLATE.rstrip("\n").endswith("- mcp"),
            "Template drift: tdd-manager block no longer ends with '- mcp'; "
            "update these fixtures deliberately",
        )


# ---------------------------------------------------------------------------
# Behaviour 9 — nothing to merge: the template text, byte-for-byte
# ---------------------------------------------------------------------------


class Behaviour9NothingToMergeTests(RoomodesMergeBase):
    """Behaviour 9: empty (or whitespace-only) existing text → the template
    text unchanged, byte-for-byte.

    First-run semantics: nothing to preserve, so the merge is the identity
    on the template — not even a trailing-newline normalisation.
    """

    def test_empty_existing_returns_template_verbatim(self):
        result = _merge("", self.TEMPLATE)
        self.assertEqual(
            result,
            self.TEMPLATE,
            "Empty existing text must yield the template text byte-for-byte",
        )

    def test_whitespace_only_existing_returns_template_verbatim(self):
        result = _merge("   \n\t  \n", self.TEMPLATE)
        self.assertEqual(
            result,
            self.TEMPLATE,
            "Whitespace-only existing text must be treated as empty "
            "(template text verbatim, byte-for-byte)",
        )


# ---------------------------------------------------------------------------
# Behaviour 10 — missing slugs appended; present slugs never touched
# ---------------------------------------------------------------------------


class Behaviour10MissingSlugsAppendedTests(RoomodesMergeBase):
    """Behaviour 10: present slugs are preserved byte-for-byte as a prefix;
    only the missing template blocks are appended."""

    def setUp(self):
        self.existing_text = _existing_docs_manager_edited()
        self.user_edit = "        - fileRegex: (.*\\.(edited-user-regex-xyz)$)"
        self.assertNotIn("qna-tester", self.existing_text)
        self.assertNotIn("tdd-manager", self.existing_text)

    def test_result_starts_with_existing_text_byte_for_byte(self):
        self.assertTrue(self.existing_text.endswith("\n"))
        result = _merge(self.existing_text, self.TEMPLATE)
        self.assertTrue(
            result.startswith(self.existing_text),
            "The existing text (ending in a newline) must be a prefix of the "
            "result, byte-for-byte — the user edit must be untouched",
        )

    def test_user_edited_fileregex_survives_in_result(self):
        result = _merge(self.existing_text, self.TEMPLATE)
        self.assertIn(
            self.user_edit,
            result,
            "The user-edited fileRegex line must survive verbatim",
        )

    def test_appended_region_contains_only_the_missing_blocks(self):
        result = _merge(self.existing_text, self.TEMPLATE)
        appended = result[len(self.existing_text):]
        self.assertIn("- slug: qna-tester", appended)
        self.assertIn("- slug: tdd-manager", appended)
        self.assertNotIn(
            "- slug: docs-manager",
            appended,
            "A present slug must not be re-appended",
        )

    def test_each_slug_line_appears_exactly_once(self):
        result = _merge(self.existing_text, self.TEMPLATE)
        for slug in ("docs-manager", "qna-tester", "tdd-manager"):
            found = re.findall(r"^\s*- slug:\s*{}\s*$".format(re.escape(slug)), result, re.M)
            self.assertEqual(
                len(found),
                1,
                "The {} slug line must appear exactly once in the merged "
                "result".format(slug),
            )

    def test_every_slug_already_present_returns_none(self):
        # The template itself, re-merged into the template: idempotent,
        # nothing to write (the _merge_gitignore None convention).
        result = _merge(self.TEMPLATE, self.TEMPLATE)
        self.assertIsNone(
            result,
            "When every template slug is already present the helper must "
            "return None ('unchanged, write nothing')",
        )

    def test_handbuilt_all_slugs_present_returns_none(self):
        result = _merge(_existing_all_three(), self.TEMPLATE)
        self.assertIsNone(
            result,
            "Every slug present (in edited form) → None, no re-append",
        )

    def test_missing_trailing_newline_inserted_before_append(self):
        existing_no_newline = _existing_qna_only_block().rstrip("\n")
        self.assertFalse(existing_no_newline.endswith("\n"))
        result = _merge(existing_no_newline, self.TEMPLATE)
        self.assertTrue(
            result.startswith(existing_no_newline + "\n"),
            "Without a trailing newline, the result must insert one before "
            "the appended block so no line is glued together",
        )
        appended = result[len(existing_no_newline) + 1:]
        self.assertIn("- slug: docs-manager", appended)
        self.assertIn("- slug: tdd-manager", appended)
        self.assertNotIn(
            "- slug: qna-tester",
            appended,
            "The present slug must not be re-appended",
        )


# ---------------------------------------------------------------------------
# Behaviour 11 — an appended block is the template's bytes verbatim
# ---------------------------------------------------------------------------


class Behaviour11AppendedBlockVerbatimTests(RoomodesMergeBase):
    """Behaviour 11: the appended text is the template's own bytes.

    The tdd-manager block carries a ``>-`` folded scalar and nested
    ``groups`` entries: a YAML round-trip would reflow both, so finding the
    exact template substring in the result proves nothing was re-serialized.
    """

    def setUp(self):
        self.existing_text = _existing_docs_manager_edited()
        self.tdd_block = _extract_block(self.TEMPLATE, "tdd-manager")

    def test_tdd_manager_block_appears_verbatim_in_result(self):
        self.assertIn(">-\n", self.tdd_block, "fixture must exercise a folded scalar")
        self.assertIn("groups:", self.tdd_block, "fixture must exercise nested groups")
        result = _merge(self.existing_text, self.TEMPLATE)
        appended = result[len(self.existing_text):]
        self.assertIn(
            self.tdd_block.rstrip("\n"),
            appended,
            "The tdd-manager block must appear in the appended region as the "
            "template's own bytes — no YAML re-serialization allowed",
        )

    def test_qna_tester_block_appears_verbatim_in_result(self):
        qna_block = _extract_block(self.TEMPLATE, "qna-tester")
        result = _merge(self.existing_text, self.TEMPLATE)
        appended = result[len(self.existing_text):]
        self.assertIn(
            qna_block.rstrip("\n"),
            appended,
            "The qna-tester block must appear verbatim too",
        )

    def test_last_block_terminated_by_eof_extracted_completely(self):
        # The tdd-manager block ends at EOF, not at a next '- slug:' line:
        # the extraction must run it to the template's last line.
        last_template_line = self.TEMPLATE.rstrip("\n").split("\n")[-1]
        self.assertEqual(
            self.tdd_block.rstrip("\n").split("\n")[-1],
            last_template_line,
            "The last template block must run to the template's last line",
        )
        result = _merge(self.existing_text, self.TEMPLATE)
        self.assertTrue(
            result.rstrip("\n").endswith(last_template_line),
            "The merged result must end with the last line of the last "
            "template block (EOF-terminated block extracted completely)",
        )

    def test_reindented_template_block_boundaries_still_split(self):
        # 4-space item indent: boundaries must come from the FIRST item's
        # indentation, not a hard-coded two spaces.
        reindented = _reindented_template(self.TEMPLATE, 2)
        self.assertTrue(
            reindented.split("\n")[1].startswith("    - slug:"),
            "fixture: re-indent must shift the item indent to 4 spaces",
        )
        existing_text = (
            "customModes:\n"
            "    - slug: docs-manager\n"
            "      name: Indented Docs\n"
        )
        self.assertNotIn("qna-tester", existing_text)
        result = _merge(existing_text, reindented)
        self.assertTrue(
            result.startswith(existing_text),
            "Existing text must still be a byte-for-byte prefix",
        )
        appended = result[len(existing_text):]
        for slug in ("qna-tester", "tdd-manager"):
            block = _extract_block(reindented, slug)
            self.assertIn(
                block.rstrip("\n"),
                appended,
                "Re-indented (4-space) template: the {} block must still be "
                "split and appended verbatim".format(slug),
            )


# ---------------------------------------------------------------------------
# Behaviour 12 — structural edge cases and error paths
# ---------------------------------------------------------------------------


class Behaviour12StructuralEdgesTests(RoomodesMergeBase):
    """Behaviour 12: existing-file structural edges and both error families.

    Error family 1 — the existing file is unreadable as a YAML mapping
    (invalid YAML, or top level not a mapping): ``ProvisionError`` naming
    the source. Error family 2 — the TEMPLATE has drifted (no
    ``customModes`` key, or a block with no parseable slug):
    ``ProvisionError`` reporting template drift, by analogy with the
    ``${CONTEXT_WINDOW}`` drift check.
    """

    def test_mapping_without_custommodes_key_gets_key_and_all_blocks(self):
        existing_text = _existing_mapping_no_custommodes()
        result = _merge(existing_text, self.TEMPLATE)
        self.assertTrue(
            result.startswith(existing_text),
            "Existing text must be a byte-for-byte prefix",
        )
        appended = result[len(existing_text):]
        self.assertIn("customModes:", appended, "The key must be appended")
        for slug in _template_slugs(self.TEMPLATE):
            self.assertIn("- slug: {}".format(slug), appended)

    def test_null_custommodes_gets_blocks_under_existing_key_once(self):
        existing_text = _existing_custommodes_null()
        result = _merge(existing_text, self.TEMPLATE)
        self.assertEqual(
            result.count("customModes:"),
            1,
            "No second 'customModes:' line may be emitted: the blocks belong "
            "under the existing key",
        )
        for slug in _template_slugs(self.TEMPLATE):
            self.assertIn("- slug: {}".format(slug), result)

    def test_invalid_existing_yaml_raises_provision_error_naming_source(self):
        existing_text = (
            "customModes:\n"
            "  - slug: docs-manager\n"
            "    description: \"unterminated\n"
        )
        with self.assertRaises(provision.ProvisionError) as ctx:
            _merge(existing_text, self.TEMPLATE)
        self.assertIn(
            SOURCE,
            str(ctx.exception),
            "ProvisionError must name the source: {}".format(ctx.exception),
        )

    def test_existing_top_level_not_a_mapping_raises(self):
        with self.assertRaises(provision.ProvisionError) as ctx:
            _merge("- just\n- a\n- list\n", self.TEMPLATE)
        self.assertIn(
            SOURCE,
            str(ctx.exception),
            "ProvisionError must name the source: {}".format(ctx.exception),
        )

    def test_template_without_custommodes_key_raises_drift_error(self):
        drifted = "profile: something-else\nnotes: no customModes here\n"
        with self.assertRaises(provision.ProvisionError) as ctx:
            _merge(_existing_docs_manager_edited(), drifted)
        self.assertIn(
            SOURCE,
            str(ctx.exception),
            "Template-drift ProvisionError must name the source: {}".format(
                ctx.exception
            ),
        )

    def test_template_block_with_no_parseable_slug_raises_drift_error(self):
        drifted = (
            "customModes:\n"
            "  - slug: docs-manager\n"
            "    name: Fine\n"
            "  - slug:\n"
            "    name: Broken block, slug value missing\n"
        )
        with self.assertRaises(provision.ProvisionError) as ctx:
            _merge(_existing_docs_manager_edited(), drifted)
        self.assertIn(
            SOURCE,
            str(ctx.exception),
            "Template-drift ProvisionError must name the source: {}".format(
                ctx.exception
            ),
        )


# ---------------------------------------------------------------------------
# Behaviour 13 — setup_repo merges .roomodes instead of overwriting it
# ---------------------------------------------------------------------------


class Behaviour13SetupRepoWiringTests(ProvisionCase):
    """Behaviour 13: ``setup_repo`` merges ``.roomodes`` instead of overwriting it.

    End-to-end through the real entry path, mirroring the behaviour 6
    wiring tests for ``.roo/mcp.json``: the target is provisioned once,
    the deployed ``.roomodes`` is hand-edited (a ``fileRegex`` value), and
    a second ``setup_repo`` run must preserve the edit, keep every
    template slug, and report the merge distinctly from a first-run
    deployment. The merge helper's own semantics are already proven at
    the unit level in the behaviour 9-12 classes above; this class proves
    the wiring — that the step actually calls ``_merge_roomodes`` and
    reports deploy / merge / skip distinctly.
    """

    # A value no template line carries; replacing the first ``fileRegex``
    # line (the docs-manager one, per template file order) simulates a
    # developer hand-editing the deployed file.
    HAND_EDIT = "fileRegex: hand-edited-regex-xyz"

    def _roomodes_report_lines(self, messages):
        """The report lines emitted by the ``.roomodes`` step for one run."""
        marker = ".roomodes"
        return [line for line in messages if marker in line]

    def _hand_edit_first_fileregex(self):
        """Hand-edit the first ``fileRegex`` line of the deployed file."""
        path = self.target / ".roomodes"
        text = path.read_text(encoding="utf-8")
        edited, count = re.subn(
            r"fileRegex: .*$", self.HAND_EDIT, text, count=1, flags=re.M
        )
        self.assertEqual(
            count,
            1,
            "The deployed .roomodes must contain a fileRegex line to edit",
        )
        path.write_text(edited, encoding="utf-8")
        return path

    def test_second_run_preserves_hand_edit_and_keeps_all_template_slugs(self):
        _provision_fresh(self.target)
        path = self._hand_edit_first_fileregex()
        self.assertIn(
            self.HAND_EDIT,
            path.read_text(encoding="utf-8"),
            "sanity: the hand edit must be in place before the second run",
        )

        _provision_fresh(self.target)

        content = path.read_text(encoding="utf-8")
        self.assertIn(
            self.HAND_EDIT,
            content,
            "A hand edit to the deployed .roomodes must survive a second "
            "setup_repo run (merge, not overwrite)",
        )
        for slug in _template_slugs(TEMPLATE_TEXT):
            self.assertIn(
                "- slug: {}".format(slug),
                content,
                "Every template slug must still be present after the merge: "
                "{}".format(slug),
            )

    def test_second_run_report_says_merged_and_differs_from_first_run(self):
        first_messages = _provision_fresh(self.target)
        self._hand_edit_first_fileregex()
        second_messages = _provision_fresh(self.target)

        first_lines = self._roomodes_report_lines(first_messages)
        second_lines = self._roomodes_report_lines(second_messages)
        self.assertTrue(first_lines, "First run must report on the .roomodes step")
        self.assertTrue(
            any("Deployed" in line or "Injected" in line for line in first_lines),
            "A first run on a fresh repo must report the .roomodes step as "
            "deployed or injected: {}".format(first_lines),
        )
        self.assertTrue(second_lines, "Second run must report on the .roomodes step")
        self.assertTrue(
            any("Merged" in line for line in second_lines),
            "A second run that merges must say 'Merged', not merely "
            "'Deployed': {}".format(second_lines),
        )
        self.assertNotEqual(
            first_lines,
            second_lines,
            "The .roomodes step report must differ between a deploy and a merge",
        )

    def test_second_run_without_changes_reports_skipped_and_leaves_bytes_unchanged(self):
        _provision_fresh(self.target)
        path = self.target / ".roomodes"
        before = path.read_bytes()

        second_messages = _provision_fresh(self.target)
        second_lines = self._roomodes_report_lines(second_messages)
        self.assertTrue(second_lines, "Second run must report on the .roomodes step")
        self.assertTrue(
            any("Skipped" in line or "up to date" in line for line in second_lines),
            "A no-change second run must report the .roomodes step as skipped "
            "(already up to date): {}".format(second_lines),
        )
        self.assertFalse(
            any(
                "Merged" in line or "Injected" in line or "Deployed" in line
                for line in second_lines
            ),
            "A no-change second run must not report a merge or a deploy: "
            "{}".format(second_lines),
        )
        self.assertEqual(
            path.read_bytes(),
            before,
            "A no-change second run must not rewrite the file's bytes",
        )

    def test_dry_run_over_edited_existing_file_changes_no_bytes(self):
        # The fresh dry-run half of this edge ("creates no .roomodes") is
        # already locked by test_dry_run_does_not_write_roomodes in
        # tests/test_provision.py; here the dry run targets an EXISTING
        # edited file and must leave its bytes untouched.
        _provision_fresh(self.target)
        path = self._hand_edit_first_fileregex()
        before = path.read_bytes()

        _provision_fresh(self.target, dry_run=True)

        self.assertEqual(
            path.read_bytes(),
            before,
            "A dry run must not modify an edited .roomodes",
        )


if __name__ == "__main__":
    unittest.main()
