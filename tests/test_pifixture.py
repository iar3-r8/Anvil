"""Tests for anvilkit.pifixture - the bake-off fixture generator.

Written before the implementation (TDD, ``plans/pi-phase1-bakeoff.md``,
behaviour 1, "fixture written").

The fixture is GENERATED at runtime - every bake-off run must start
known-red - so nothing is committed under ``tests/fixtures`` for it.
This module covers behaviour 1 only; later cycles add behaviours 2-3
here.

The production module ``anvilkit.pifixture`` does not exist yet, so every
test loads it through ``_pifixture``, which fails with a clear assertion
instead of letting a collection-time ImportError mask the reason the
suite is red.
"""

import ast
import importlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The complete generated file set, relative to the destination.
EXPECTED_FILES = [
    "TASK.md",
    "bakeoff_fixture/adder.py",
    "tests/test_adder.py",
]


class PifixtureTestCase(unittest.TestCase):
    def _pifixture(self):
        """Import anvilkit.pifixture, failing clearly if the module is absent."""
        spec = importlib.util.find_spec("anvilkit.pifixture")
        self.assertIsNotNone(
            spec,
            "anvilkit.pifixture cannot be imported; the fixture generator "
            "has not been implemented yet",
        )
        return importlib.import_module("anvilkit.pifixture")

    def _fresh_dest(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        return Path(tmp_dir.name)

    @staticmethod
    def _snapshot(root):
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }


class TestWriteFixture(PifixtureTestCase):
    def test_write_fixture_creates_missing_destination(self):
        pifixture = self._pifixture()
        dest = self._fresh_dest() / "nested" / "dest"
        self.assertFalse(dest.exists())
        pifixture.write_fixture(dest)
        for name in EXPECTED_FILES:
            self.assertTrue((dest / name).is_file(), "missing generated file: " + name)

    def test_write_fixture_adder_returns_a_minus_b(self):
        # The fixture's code must not be imported into the test process, so
        # the generated adder is executed in a subprocess instead. Three
        # argument pairs rule out a hardcoded return value.
        pifixture = self._pifixture()
        dest = self._fresh_dest()
        pifixture.write_fixture(dest)
        adder_path = dest / "bakeoff_fixture" / "adder.py"
        probe = (
            "import importlib.util, json, sys\n"
            "spec = importlib.util.spec_from_file_location('adder_fixture', sys.argv[1])\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(module)\n"
            "print(json.dumps([module.add(2, 3), module.add(1, 10), module.add(0, 0)]))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe, str(adder_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, "probe failed:\n" + result.stderr)
        self.assertEqual(json.loads(result.stdout), [-1, -9, 0])

    @staticmethod
    def _is_add_2_3_call(node):
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "add"
            and len(node.args) == 2
            and all(
                isinstance(arg, ast.Constant) and isinstance(arg.value, int)
                for arg in node.args
            )
            and [arg.value for arg in node.args] == [2, 3]
        )

    def test_write_fixture_test_file_has_exactly_one_assertion_add_2_3_eq_5(self):
        pifixture = self._pifixture()
        dest = self._fresh_dest()
        pifixture.write_fixture(dest)
        text = (dest / "tests" / "test_adder.py").read_text(encoding="utf-8")
        tree = ast.parse(text)
        assertions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                assertions.append(node.test)
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr.startswith("assert")
            ):
                assertions.append(node)
        self.assertEqual(
            len(assertions),
            1,
            "test_adder.py must contain exactly one assertion, found %d"
            % len(assertions),
        )
        expr = assertions[0]
        self.assertTrue(
            any(self._is_add_2_3_call(node) for node in ast.walk(expr)),
            "the single assertion must call add(2, 3)",
        )
        self.assertTrue(
            any(
                isinstance(node, ast.Constant) and node.value == 5
                for node in ast.walk(expr)
            ),
            "the single assertion must compare against 5",
        )

    def test_write_fixture_task_md_names_adder_and_the_change(self):
        pifixture = self._pifixture()
        dest = self._fresh_dest()
        pifixture.write_fixture(dest)
        task = (dest / "TASK.md").read_text(encoding="utf-8")
        # The task must name the file to edit ...
        self.assertIn("adder.py", task)
        # ... and state the one-line change explicitly ...
        self.assertIn("a - b", task)
        self.assertIn("a + b", task)
        # ... and must not point at the test, so no model can succeed by
        # editing the test instead of the fixture.
        self.assertNotIn("test_adder.py", task)

    def test_write_fixture_file_set_is_exactly_three_files(self):
        pifixture = self._pifixture()
        dest = self._fresh_dest()
        pifixture.write_fixture(dest)
        files = sorted(
            path.relative_to(dest).as_posix()
            for path in dest.rglob("*")
            if path.is_file()
        )
        self.assertEqual(files, EXPECTED_FILES)

    def test_write_fixture_existing_bakeoff_fixture_raises_fixture_error(self):
        pifixture = self._pifixture()
        dest = self._fresh_dest()
        existing = dest / "bakeoff_fixture"
        existing.mkdir()
        original = "def add(a, b):\n    return a + b\n"
        (existing / "adder.py").write_text(original, encoding="utf-8")
        with self.assertRaises(pifixture.FixtureError):
            pifixture.write_fixture(dest)
        # The pre-existing fixture must not have been touched or overwritten.
        self.assertEqual(
            (existing / "adder.py").read_text(encoding="utf-8"), original
        )
        self.assertEqual(
            sorted(
                path.relative_to(dest).as_posix()
                for path in dest.rglob("*")
                if path.is_file()
            ),
            ["bakeoff_fixture/adder.py"],
        )

    def test_write_fixture_is_byte_identical_across_two_runs(self):
        pifixture = self._pifixture()
        first = self._fresh_dest()
        second = self._fresh_dest()
        pifixture.write_fixture(first)
        pifixture.write_fixture(second)
        self.assertEqual(self._snapshot(first), self._snapshot(second))
