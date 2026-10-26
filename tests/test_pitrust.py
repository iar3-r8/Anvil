"""Tests for anvilkit.pi.pitrust - the project ``.pi/`` fixture writer.

Written before the implementation (TDD, ``plans/pi-phase2-approval.md``,
behaviour 5: "project ``.pi/`` fixture").

The production module ``anvilkit.pi.pitrust`` does not exist yet, so every
test loads it through ``_pitrust``, which fails with a clear assertion
instead of letting a collection-time ImportError mask the reason the
suite is red.
"""

import importlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The complete generated file set, relative to ``dest``.
EXPECTED_FILES = [
    ".pi/APPEND_SYSTEM.md",
    ".pi/mcp.json",
    ".pi/settings.json",
]

# The tests own these values; the module takes them as arguments and must
# never hardcode them. The command must not be resolvable on PATH.
MARKER = "ANVIL-PHASE2-MARKER"
UNREACHABLE_COMMAND = "anvil-nonexistent-mcp-server"


class PitrustTestCase(unittest.TestCase):
    def _pitrust(self):
        """Import anvilkit.pi.pitrust, failing clearly if the module is absent."""
        spec = importlib.util.find_spec("anvilkit.pi.pitrust")
        self.assertIsNotNone(
            spec,
            "anvilkit.pi.pitrust cannot be imported; the project .pi/ fixture "
            "writer has not been implemented yet",
        )
        return importlib.import_module("anvilkit.pi.pitrust")

    def _fresh_dest(self):
        """A fresh, existing destination directory in a temp tree."""
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        dest = Path(tmp_dir.name) / "dest"
        dest.mkdir()
        return dest

    @staticmethod
    def _pi_files(dest):
        """All files under ``dest`` as a ``{relative posix path: bytes}`` map."""
        pi = dest / ".pi"
        if not pi.is_dir():
            return {}
        return {
            path.relative_to(dest).as_posix(): path.read_bytes()
            for path in sorted(pi.rglob("*"))
            if path.is_file()
        }


class TestWriteProject(PitrustTestCase):
    def test_write_project_creates_the_three_files(self):
        pitrust = self._pitrust()
        dest = self._fresh_dest()
        pitrust.write_project(dest, MARKER, UNREACHABLE_COMMAND)
        for name in EXPECTED_FILES:
            self.assertTrue(
                (dest / name).is_file(), "missing generated file: " + name
            )

    def test_write_project_file_set_is_exactly_three_files(self):
        pitrust = self._pitrust()
        dest = self._fresh_dest()
        pitrust.write_project(dest, MARKER, UNREACHABLE_COMMAND)
        files = sorted(
            path.relative_to(dest).as_posix()
            for path in dest.rglob("*")
            if path.is_file()
        )
        self.assertEqual(files, EXPECTED_FILES)

    def test_write_project_settings_json_is_valid_inert_json(self):
        pitrust = self._pitrust()
        dest = self._fresh_dest()
        pitrust.write_project(dest, MARKER, UNREACHABLE_COMMAND)
        text = (dest / ".pi" / "settings.json").read_text(encoding="utf-8")
        parsed = json.loads(text)
        self.assertIsInstance(
            parsed, dict, "settings.json must parse to a JSON object"
        )

    def test_write_project_append_system_contains_the_marker(self):
        pitrust = self._pitrust()
        dest = self._fresh_dest()
        pitrust.write_project(dest, MARKER, UNREACHABLE_COMMAND)
        text = (dest / ".pi" / "APPEND_SYSTEM.md").read_text(encoding="utf-8")
        self.assertIn(
            MARKER,
            text,
            "APPEND_SYSTEM.md must instruct the model to include the marker "
            "token verbatim in its reply",
        )

    def test_write_project_mcp_json_has_one_stdio_server_with_the_command(self):
        pitrust = self._pitrust()
        dest = self._fresh_dest()
        pitrust.write_project(dest, MARKER, UNREACHABLE_COMMAND)
        parsed = json.loads((dest / ".pi" / "mcp.json").read_text(encoding="utf-8"))
        self.assertIn("mcpServers", parsed, "mcp.json must carry an mcpServers map")
        servers = parsed["mcpServers"]
        self.assertIsInstance(servers, dict)
        self.assertEqual(
            len(servers),
            1,
            "mcp.json must carry exactly one mcpServers entry",
        )
        only_entry = next(iter(servers.values()))
        self.assertIsInstance(only_entry, dict)
        self.assertEqual(
            only_entry.get("command"),
            UNREACHABLE_COMMAND,
            "the single mcpServers entry's command must equal the "
            "unreachable command passed to write_project",
        )
        # A stdio entry: command is a single executable, never a shell
        # string. Pin it as a non-empty string with no shell metacharacters.
        command = only_entry["command"]
        self.assertIsInstance(command, str)
        self.assertGreaterEqual(len(command), 1)
        for metachar in (";", "&", "|", ">", "<", "(", ")", "$", "`", "\n", " "):
            self.assertNotIn(
                metachar,
                command,
                "command must be a single executable, not a shell string",
            )

    def test_write_project_is_byte_identical_across_two_writes(self):
        pitrust = self._pitrust()
        first = self._fresh_dest()
        second = self._fresh_dest()
        pitrust.write_project(first, MARKER, UNREACHABLE_COMMAND)
        pitrust.write_project(second, MARKER, UNREACHABLE_COMMAND)
        self.assertEqual(
            self._pi_files(first),
            self._pi_files(second),
            "two fresh writes with identical arguments must be byte-identical",
        )

    def test_write_project_leaves_unrelated_dest_files_untouched(self):
        pitrust = self._pitrust()
        dest = self._fresh_dest()
        pre_existing = dest / "unrelated.txt"
        pre_existing.write_text("keep me\n", encoding="utf-8")
        pitrust.write_project(dest, MARKER, UNREACHABLE_COMMAND)
        self.assertEqual(
            pre_existing.read_text(encoding="utf-8"),
            "keep me\n",
            "a successful write must not touch unrelated files in dest",
        )
        # And the generated set is still exactly the three files, so the
        # unrelated file is not swallowed into the fixture.
        files = sorted(
            path.relative_to(dest).as_posix()
            for path in dest.rglob("*")
            if path.is_file()
        )
        self.assertEqual(files, EXPECTED_FILES + ["unrelated.txt"])


class TestWriteProjectPreexistingPi(PitrustTestCase):
    def test_write_project_preexisting_empty_pi_raises_trust_error(self):
        pitrust = self._pitrust()
        dest = self._fresh_dest()
        (dest / ".pi").mkdir()
        with self.assertRaises(pitrust.TrustError):
            pitrust.write_project(dest, MARKER, UNREACHABLE_COMMAND)
        # The pre-existing .pi must remain empty: nothing written, never a
        # partial overwrite.
        self.assertEqual(
            sorted(
                path.relative_to(dest).as_posix()
                for path in dest.rglob("*")
                if path.is_file()
            ),
            [],
            "a pre-existing .pi must not be written into",
        )

    def test_write_project_preexisting_pi_names_the_path_in_the_error(self):
        pitrust = self._pitrust()
        dest = self._fresh_dest()
        pi_dir = dest / ".pi"
        pi_dir.mkdir()
        with self.assertRaises(pitrust.TrustError) as ctx:
            pitrust.write_project(dest, MARKER, UNREACHABLE_COMMAND)
        self.assertIn(
            str(pi_dir),
            str(ctx.exception),
            "TrustError must name the offending .pi path",
        )

    def test_write_project_preexisting_pi_with_files_is_never_overwritten(self):
        pitrust = self._pitrust()
        dest = self._fresh_dest()
        pi_dir = dest / ".pi"
        pi_dir.mkdir()
        original_settings = b'{"harmless": true}\n'
        (pi_dir / "settings.json").write_bytes(original_settings)
        with self.assertRaises(pitrust.TrustError):
            pitrust.write_project(dest, MARKER, UNREACHABLE_COMMAND)
        # The pre-existing content must be byte-for-byte untouched.
        self.assertEqual(
            (pi_dir / "settings.json").read_bytes(),
            original_settings,
            "a pre-existing .pi file must never be overwritten",
        )
        # And no other fixture file may have appeared.
        self.assertEqual(
            sorted(
                path.relative_to(dest).as_posix()
                for path in dest.rglob("*")
                if path.is_file()
            ),
            [".pi/settings.json"],
            "a refused write must not create any fixture file",
        )


class TestPitrustModuleShape(PitrustTestCase):
    def test_pitrust_exposes_trust_error_and_write_project(self):
        pitrust = self._pitrust()
        self.assertTrue(
            issubclass(getattr(pitrust, "TrustError", None), Exception),
            "anvilkit.pi.pitrust must define TrustError, the single refusal",
        )
        self.assertTrue(
            callable(getattr(pitrust, "write_project", None)),
            "anvilkit.pi.pitrust.write_project is not callable; the project "
            ".pi/ fixture writer has not been implemented yet",
        )


if __name__ == "__main__":
    unittest.main()
