"""Boundary pins for ``plans/pi-role-prompts.md`` behaviours 1-3.

These are coverage-only boundary pins: they assert the *current* repository
state on which the generated-prompts decision rests, before
``anvilkit/pi/piprompt.py`` exists. They are expected to PASS on arrival
(same precedent as ``tests/test_rules_mirror.py`` and
``tests/test_pirole.py``); there is no honest red for them - the invariants
already hold. They import nothing from ``anvilkit.pi.piprompt`` on purpose:
the pins must not depend on the module they pin the seam for.

1. ``rule-sources-tracked`` - the four rule XMLs and the three
   ``rules/*.md`` shared files under ``templates/roo_template/`` each exist,
   are non-empty, and (for the XMLs) parse as well-formed. A missing or
   empty source fails naming the path; no skip (all are tracked).
2. ``coder-window-readable`` - ``anvilkit.config.read_models`` in strict
   mode reads the repository ``config.yaml`` and returns the coder id
   ``Qwen/Qwen3.8-27B-FP8`` with a context window of ``262144``; and a
   config whose coder ``cmd`` has no ``--max-model-len`` raises
   ``ConfigError`` in strict mode rather than reporting the built-in
   default as if it had been read.
3. ``pi-roles-dir-committable`` - no ``.gitignore`` pattern matches
   ``.pi`` / ``.pi/roles`` (re-includes and comments do not count), so the
   generated ``.pi/roles/*.md`` prompts can be committed.

Stdlib only, plus ``anvilkit.config`` for behaviour 2. Python 3.8 floor.
"""

import fnmatch
import sys
import tempfile
import unittest
import xml.etree.ElementTree
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit.config import (
    DEFAULT_CONTEXT_WINDOW,
    ConfigError,
    read_models,
)

TEMPLATE_ROOT = REPO_ROOT / "templates" / "roo_template"

# Behaviour 1: the seven tracked sources the generator will read. (relative
# path, human label, is-xml).
RULE_SOURCES = [
    ("rules-architect/instructions.xml", "architect instructions", True),
    ("rules-qna-tester/instructions.xml", "qna-tester instructions", True),
    ("rules-tdd-manager/instructions.xml", "tdd-manager instructions", True),
    ("rules-docs-manager/guidelines.xml", "docs-manager guidelines", True),
    ("rules/AGENTS.md", "shared AGENTS rules", False),
    ("rules/architecture.md", "shared architecture rules", False),
    ("rules/coding-guidelines.md", "shared coding-guidelines rules", False),
]

EXPECTED_CODER_ID = "Qwen/Qwen3.8-27B-FP8"
EXPECTED_CODER_WINDOW = 262144

# Behaviour 3: the paths under which the generated prompts would live,
# relative to the repository root.
PI_ROLE_PATHS = [
    ".pi",
    ".pi/",
    ".pi/roles",
    ".pi/roles/",
    ".pi/roles/coder.md",
]


def _require_source(rel):
    """Return the source path, failing (naming the path) if it is missing
    or empty. No skip: every source is tracked and must exist."""
    path = TEMPLATE_ROOT / rel
    if not path.is_file():
        raise AssertionError(
            "tracked rule source is missing: templates/roo_template/%s" % rel
        )
    if path.stat().st_size == 0:
        raise AssertionError(
            "tracked rule source is empty: templates/roo_template/%s" % rel
        )
    return path


def _parse_rule_xml(rel):
    """Parse one rule XML, failing (naming the path) if it is missing,
    empty, or not well-formed."""
    path = _require_source(rel)
    try:
        xml.etree.ElementTree.fromstring(path.read_bytes())
    except xml.etree.ElementTree.ParseError as exc:
        raise AssertionError(
            "rule XML is not well-formed: templates/roo_template/%s (%s)"
            % (rel, exc)
        )


def _scan_gitignore(lines):
    """Return the (pattern, line-number) pairs among ``lines`` that would
    ignore one of ``PI_ROLE_PATHS``.

    Blank lines and ``#`` comments are skipped; a re-include entry
    (``!foo``) re-includes, so it must not count as a match.
    """
    offenders = []
    for line_number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        if any(fnmatch.fnmatch(candidate, line) for candidate in PI_ROLE_PATHS):
            offenders.append((line, line_number))
    return offenders


class RuleSourcesTrackedTestCase(unittest.TestCase):
    """Behaviour 1: the seven tracked rule sources exist, are non-empty,
    and each XML parses as well-formed."""

    def test_architect_instructions_exist_and_parse(self):
        _parse_rule_xml("rules-architect/instructions.xml")

    def test_qna_tester_instructions_exist_and_parse(self):
        _parse_rule_xml("rules-qna-tester/instructions.xml")

    def test_tdd_manager_instructions_exist_and_parse(self):
        _parse_rule_xml("rules-tdd-manager/instructions.xml")

    def test_docs_manager_guidelines_exist_and_parse(self):
        _parse_rule_xml("rules-docs-manager/guidelines.xml")

    def test_shared_agents_md_exists_and_non_empty(self):
        _require_source("rules/AGENTS.md")

    def test_shared_architecture_md_exists_and_non_empty(self):
        _require_source("rules/architecture.md")

    def test_shared_coding_guidelines_md_exists_and_non_empty(self):
        _require_source("rules/coding-guidelines.md")

    # -- error behaviour: the failure names the path; no skip -- #

    def test_require_source_failure_names_the_missing_path(self):
        with self.assertRaises(AssertionError) as ctx:
            _require_source("rules/does-not-exist.md")
        self.assertIn("rules/does-not-exist.md", str(ctx.exception))

    def test_parse_rule_xml_failure_names_the_malformed_path(self):
        with self.assertRaises(AssertionError) as ctx:
            _parse_rule_xml("rules/does-not-exist.xml")
        self.assertIn("rules/does-not-exist.xml", str(ctx.exception))


class CoderWindowReadableTestCase(unittest.TestCase):
    """Behaviour 2: the coder window the phase measures its budget against
    is READ from the repository config in strict mode, never defaulted."""

    def test_repository_config_reports_coder_id_and_window(self):
        topology = read_models(
            REPO_ROOT / "config.yaml", strict_context_window=True
        )
        self.assertEqual(EXPECTED_CODER_ID, topology.coder_id)
        self.assertEqual(EXPECTED_CODER_WINDOW, topology.coder_context_window)

    def test_strict_mode_raises_when_coder_max_model_len_is_missing(self):
        """A config whose coder cmd carries no ``--max-model-len`` raises
        ``ConfigError`` in strict mode - it must never report the built-in
        default as if it had been read."""
        config_text = (
            "matrix:\n"
            "  vars:\n"
            "    coder: %s\n"
            "models:\n"
            "  %s:\n"
            "    cmd: >\n"
            "      docker run --rm --network llm-network vllm/vllm-openai:latest\n"
            "        --model x\n"
            "        --port 8080\n"
            % (EXPECTED_CODER_ID, EXPECTED_CODER_ID)
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(config_text)
            with self.assertRaises(ConfigError):
                read_models(path, strict_context_window=True)

    def test_lenient_mode_defaults_when_coder_max_model_len_is_missing(self):
        """The strict raise above is what makes the strict read honest:
        without it, the same config silently yields the built-in default."""
        config_text = (
            "matrix:\n"
            "  vars:\n"
            "    coder: %s\n"
            "models:\n"
            "  %s:\n"
            "    cmd: >\n"
            "      docker run --rm --network llm-network vllm/vllm-openai:latest\n"
            "        --model x\n"
            "        --port 8080\n"
            % (EXPECTED_CODER_ID, EXPECTED_CODER_ID)
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(config_text)
            topology = read_models(path, strict_context_window=False)
            self.assertEqual(DEFAULT_CONTEXT_WINDOW, topology.coder_context_window)

    def test_strict_mode_error_names_coder_and_flag(self):
        config_text = (
            "matrix:\n"
            "  vars:\n"
            "    coder: %s\n"
            "models:\n"
            "  %s:\n"
            "    cmd: >\n"
            "      docker run --rm vllm/vllm-openai:latest\n"
            % (EXPECTED_CODER_ID, EXPECTED_CODER_ID)
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(config_text)
            with self.assertRaises(ConfigError) as ctx:
                read_models(path, strict_context_window=True)
        message = str(ctx.exception)
        self.assertIn(EXPECTED_CODER_ID, message)
        self.assertIn("--max-model-len", message)


class PiRolesDirCommittableTestCase(unittest.TestCase):
    """Behaviour 3: no ``.gitignore`` pattern ignores ``.pi/`` or
    ``.pi/roles/`` - the checked-in decision that the generated prompts are
    committed rests on this."""

    def test_gitignore_does_not_ignore_pi_roles_dir(self):
        lines = (REPO_ROOT / ".gitignore").read_text().splitlines()
        offenders = _scan_gitignore(lines)
        self.assertEqual(
            [],
            offenders,
            ".gitignore would ignore the generated prompts: %r" % (offenders,),
        )

    # -- error behaviour: a match fails naming the offending line -- #

    def test_scan_reports_offending_pattern_and_line_number(self):
        lines = [
            "# a comment that mentions .pi/",
            "",
            "!.pi/  # re-include, must not count",
            ".pi/roles/",
        ]
        offenders = _scan_gitignore(lines)
        self.assertEqual([(".pi/roles/", 4)], offenders)

    def test_scan_ignores_comments_blank_lines_and_re_includes(self):
        lines = [
            "# .pi/ in a comment never counts",
            "",
            "!/.pi/",
            "!.pi/roles/",
            "*.py",
        ]
        self.assertEqual([], _scan_gitignore(lines))


if __name__ == "__main__":
    unittest.main()
