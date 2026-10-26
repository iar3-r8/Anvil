"""Tests for anvilkit.pi.pifixture - the bake-off fixture generator.

Written before the implementation (TDD, ``plans/pi-phase1-bakeoff.md``,
behaviours 1-3: "fixture written", "fixture starts red and turns
green", and "fixture change detection").

The fixture is GENERATED at runtime - every bake-off run must start
known-red - so nothing is committed under ``tests/fixtures`` for it.

The production module ``anvilkit.pi.pifixture`` does not exist yet, so every
test loads it through ``_pifixture``, which fails with a clear assertion
instead of letting a collection-time ImportError mask the reason the
suite is red.
"""

import ast
import hashlib
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
        """Import anvilkit.pi.pifixture, failing clearly if the module is absent."""
        spec = importlib.util.find_spec("anvilkit.pi.pifixture")
        self.assertIsNotNone(
            spec,
            "anvilkit.pi.pifixture cannot be imported; the fixture generator "
            "has not been implemented yet",
        )
        return importlib.import_module("anvilkit.pi.pifixture")

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


class TestAssertionPasses(PifixtureTestCase):
    """Behaviour 2: the fixture starts red and turns green.

    The pinned result shape is a ``dict`` carrying at least:

    - ``"passed"``: a ``bool`` - ``False`` while the fixture is red,
      ``True`` once ``adder.py`` returns ``a + b``;
    - ``"stderr"``: a ``str`` - the subprocess's captured stderr, which
      must carry the interpreter's failure output whenever the check
      fails.

    The fixture's test file imports ``bakeoff_fixture.adder`` with no
    ``__init__.py`` and no path setup, so the subprocess can only
    resolve it with the destination itself as cwd. A check that ran
    from the repo root would stay red forever and fail the green test
    below.
    """

    def _pifixture_with_assertion_passes(self):
        """Import the module and assert behaviour 2's entry point exists."""
        pifixture = self._pifixture()
        self.assertTrue(
            callable(getattr(pifixture, "assertion_passes", None)),
            "anvilkit.pi.pifixture.assertion_passes is not callable; the "
            "red/green check has not been implemented yet",
        )
        return pifixture

    def test_assertion_passes_fresh_fixture_returns_false(self):
        pifixture = self._pifixture_with_assertion_passes()
        dest = self._fresh_dest()
        pifixture.write_fixture(dest)
        result = pifixture.assertion_passes(dest)
        self.assertIsInstance(result, dict)
        self.assertIs(result["passed"], False)
        self.assertIsInstance(result["stderr"], str)
        # The red result must carry the interpreter's failure output,
        # not an empty string.
        self.assertNotEqual(result["stderr"], "")

    def test_assertion_passes_fixed_adder_returns_true(self):
        pifixture = self._pifixture_with_assertion_passes()
        dest = self._fresh_dest()
        pifixture.write_fixture(dest)
        (dest / "bakeoff_fixture" / "adder.py").write_text(
            "def add(a, b):\n    return a + b\n", encoding="utf-8"
        )
        result = pifixture.assertion_passes(dest)
        self.assertIsInstance(result, dict)
        self.assertIs(result["passed"], True)
        self.assertIsInstance(result["stderr"], str)

    def test_assertion_passes_absent_adder_returns_false_with_stderr(self):
        pifixture = self._pifixture_with_assertion_passes()
        dest = self._fresh_dest()
        pifixture.write_fixture(dest)
        (dest / "bakeoff_fixture" / "adder.py").unlink()
        # Must not raise: the import failure is reported, not escaped.
        result = pifixture.assertion_passes(dest)
        self.assertIsInstance(result, dict)
        self.assertIs(result["passed"], False)
        self.assertIsInstance(result["stderr"], str)
        self.assertNotEqual(result["stderr"], "")
        self.assertIn("adder", result["stderr"])

    def test_assertion_passes_unimportable_adder_returns_false_with_stderr(self):
        pifixture = self._pifixture_with_assertion_passes()
        dest = self._fresh_dest()
        pifixture.write_fixture(dest)
        # Module-level raise: importing adder in the test process would
        # escape as RuntimeError and fail this test. It must instead
        # surface in the captured stderr.
        (dest / "bakeoff_fixture" / "adder.py").write_text(
            'raise RuntimeError("adder poison 42")\n', encoding="utf-8"
        )
        result = pifixture.assertion_passes(dest)
        self.assertIsInstance(result, dict)
        self.assertIs(result["passed"], False)
        self.assertIn("adder poison 42", result["stderr"])

    def test_assertion_passes_never_imports_fixture_into_test_process(self):
        pifixture = self._pifixture_with_assertion_passes()
        dest = self._fresh_dest()
        pifixture.write_fixture(dest)
        pifixture.assertion_passes(dest)
        # The fixture's code must have run in a subprocess, never in this
        # one: no fixture module may be in sys.modules ...
        for name in ("bakeoff_fixture", "bakeoff_fixture.adder", "test_adder"):
            self.assertNotIn(name, sys.modules)
        # ... and the destination must not have been added to this
        # process's sys.path.
        dest_resolved = dest.resolve()
        for entry in sys.path:
            if entry:
                self.assertNotEqual(Path(entry).resolve(), dest_resolved)


class TestChangedFiles(PifixtureTestCase):
    """Behaviour 3: fixture change detection.

    The pinned digest shape from ``digest_fixture(dest)`` is a ``dict``
    mapping every file's posix-style path relative to ``dest`` (for
    example ``"bakeoff_fixture/adder.py"``) to the sha256 hexdigest of
    the file's bytes. ``changed_files(before, dest)`` compares the
    current tree to that digest and returns a sorted ``List[str]``:

    - a changed file appears as its relative path;
    - a file present in ``before`` but missing now appears as
      ``"deleted:" + relative path``, so a run that deleted the test
      cannot be mistaken for a clean result;
    - a file that did not exist in ``before`` appears as its relative
      path, because a run may add files and additions are changes;
    - an untouched tree returns ``[]``.
    """

    def _pifixture_with_changed_files(self):
        """Import the module and assert behaviour 3's entry points exist."""
        pifixture = self._pifixture()
        for name in ("digest_fixture", "changed_files"):
            self.assertTrue(
                callable(getattr(pifixture, name, None)),
                "anvilkit.pi.pifixture.%s is not callable; fixture change "
                "detection has not been implemented yet" % name,
            )
        return pifixture

    def test_digest_fixture_returns_relative_path_to_sha256_map(self):
        pifixture = self._pifixture_with_changed_files()
        dest = self._fresh_dest()
        pifixture.write_fixture(dest)
        digest = pifixture.digest_fixture(dest)
        self.assertIsInstance(digest, dict)
        self.assertEqual(
            set(digest),
            set(EXPECTED_FILES),
            "the digest must name exactly the fixture's files, relative "
            "to dest, with posix separators",
        )
        for name in EXPECTED_FILES:
            expected = hashlib.sha256(
                (dest / name).read_bytes()
            ).hexdigest()
            self.assertEqual(
                digest[name],
                expected,
                "digest of %s is not its sha256" % name,
            )

    def test_changed_files_untouched_fixture_returns_empty_list(self):
        pifixture = self._pifixture_with_changed_files()
        dest = self._fresh_dest()
        pifixture.write_fixture(dest)
        before = pifixture.digest_fixture(dest)
        self.assertEqual(pifixture.changed_files(before, dest), [])

    def test_changed_files_rewritten_adder_lists_only_that_file(self):
        pifixture = self._pifixture_with_changed_files()
        dest = self._fresh_dest()
        pifixture.write_fixture(dest)
        before = pifixture.digest_fixture(dest)
        (dest / "bakeoff_fixture" / "adder.py").write_text(
            "def add(a, b):\n    return a + b\n", encoding="utf-8"
        )
        self.assertEqual(
            pifixture.changed_files(before, dest),
            ["bakeoff_fixture/adder.py"],
        )

    def test_changed_files_deleted_test_file_lists_deleted_prefix(self):
        pifixture = self._pifixture_with_changed_files()
        dest = self._fresh_dest()
        pifixture.write_fixture(dest)
        before = pifixture.digest_fixture(dest)
        (dest / "tests" / "test_adder.py").unlink()
        self.assertEqual(
            pifixture.changed_files(before, dest),
            ["deleted:tests/test_adder.py"],
        )

    def test_changed_files_new_file_listed_by_relative_path(self):
        pifixture = self._pifixture_with_changed_files()
        dest = self._fresh_dest()
        pifixture.write_fixture(dest)
        before = pifixture.digest_fixture(dest)
        (dest / "bakeoff_fixture" / "helper.py").write_text(
            "def double(n):\n    return n * 2\n", encoding="utf-8"
        )
        self.assertEqual(
            pifixture.changed_files(before, dest),
            ["bakeoff_fixture/helper.py"],
        )

    def test_changed_files_mixed_mutations_are_sorted(self):
        pifixture = self._pifixture_with_changed_files()
        dest = self._fresh_dest()
        pifixture.write_fixture(dest)
        before = pifixture.digest_fixture(dest)
        (dest / "bakeoff_fixture" / "adder.py").write_text(
            "def add(a, b):\n    return a + b\n", encoding="utf-8"
        )
        (dest / "TASK.md").unlink()
        (dest / "notes.txt").write_text("scratch\n", encoding="utf-8")
        self.assertEqual(
            pifixture.changed_files(before, dest),
            ["bakeoff_fixture/adder.py", "deleted:TASK.md", "notes.txt"],
        )
