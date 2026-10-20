"""Tests for anvilkit.piargv - the bake-off invocation argv builder.

Written before the implementation (TDD, ``plans/pi-phase1-bakeoff.md``,
behaviour 4: "print invocation argv"). Only behaviour 4 is covered in
this module; behaviours 5-6 (json/ultrawork argv) and 7 (models
document) will land in later cycles as further classes in the same file.

The production module ``anvilkit.piargv`` does not exist yet, so every
test loads it through ``_piargv``, which fails with a clear assertion
instead of letting a collection-time ImportError mask the reason the
suite is red.
"""

import importlib
import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class PiargvTestCase(unittest.TestCase):
    def _piargv(self):
        """Import anvilkit.piargv, failing clearly if the module is absent."""
        spec = importlib.util.find_spec("anvilkit.piargv")
        self.assertIsNotNone(
            spec,
            "anvilkit.piargv cannot be imported; the bake-off argv "
            "builder has not been implemented yet",
        )
        return importlib.import_module("anvilkit.piargv")


class TestPrintArgv(PiargvTestCase):
    """Behaviour 4: print invocation argv.

    The pinned signature is ``print_argv(model_id, prompt)`` returning
    a ``List[str]``. The plan's "fixture path" input is intentionally
    NOT part of the signature: the argv carries no cwd or path token,
    and the host run recipe (behaviour 18) sets the subprocess cwd to
    the fixture directory separately, so baking a path into the argv
    would couple the builder to where the fixture happens to live.
    """

    def test_print_argv_returns_exact_token_list(self):
        piargv = self._piargv()
        argv = piargv.print_argv("llamaswap/coder", "Edit adder.py so add(2, 3) == 5")
        self.assertIsInstance(
            argv,
            list,
            "print_argv must return a list of tokens, never a string, "
            "so no shell re-parses it",
        )
        self.assertEqual(
            argv,
            [
                "pi",
                "-p",
                "--model",
                "llamaswap/coder",
                "--tools",
                "read,edit,write",
                "-a",
                "--no-session",
                "--",
                "Edit adder.py so add(2, 3) == 5",
            ],
        )

    def test_print_argv_prompt_is_final_element_after_double_dash(self):
        piargv = self._piargv()
        argv = piargv.print_argv("llamaswap/coder", "fix it")
        self.assertEqual(argv[-1], "fix it")
        self.assertEqual(argv[-2], "--")

    def test_print_argv_prompt_beginning_with_dash_is_included_as_is(self):
        # "--" already precedes the prompt, so a leading-dash prompt is
        # safe and must be passed through verbatim, not rejected.
        piargv = self._piargv()
        argv = piargv.print_argv("llamaswap/coder", "-p --mode json -- evil prompt")
        self.assertEqual(argv[-1], "-p --mode json -- evil prompt")
        self.assertNotIsInstance(argv, (str, bytes))

    def test_print_argv_empty_model_id_raises_argv_error(self):
        piargv = self._piargv()
        with self.assertRaises(piargv.ArgvError):
            piargv.print_argv("", "Edit adder.py so add(2, 3) == 5")

    def test_print_argv_whitespace_model_id_raises_argv_error(self):
        piargv = self._piargv()
        with self.assertRaises(piargv.ArgvError):
            piargv.print_argv("   ", "Edit adder.py so add(2, 3) == 5")

    def test_print_argv_empty_prompt_raises_argv_error(self):
        piargv = self._piargv()
        with self.assertRaises(piargv.ArgvError):
            piargv.print_argv("llamaswap/coder", "")


if __name__ == "__main__":
    unittest.main()
