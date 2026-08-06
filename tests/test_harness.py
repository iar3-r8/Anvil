"""Step 0 harness proof, plus the step 10 cutover entrypoint.

These tests exist to prove the discovery mechanism, the repo-root resolution and
the anvilkit import path all work before any of them are trusted by real tests.

A deliberately failing placeholder was used to confirm the runner reports RED,
then removed. These remaining assertions guard the environment contract itself.

``TestEntryPointScript`` covers the cutover: ``anvil`` is now a bash bootstrap
that execs into ``anvilkit.cli``. It is asserted structurally - that the shell
delegates rather than deciding - because the behaviour it delegates *to* is
already covered by ``test_cli.py``, and re-running the real script here would be
slow and would touch the network on a cold venv.
"""

import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BOOTSTRAP = REPO_ROOT / "scripts" / "bootstrap.sh"
ENTRYPOINT = REPO_ROOT / "anvil"


class TestHarness(unittest.TestCase):
    def test_repo_root_resolves_to_the_anvil_checkout(self):
        self.assertTrue((REPO_ROOT / "docker-compose.yml").is_file())
        self.assertTrue((REPO_ROOT / "requirements.txt").is_file())

    def test_interpreter_is_python_38_or_newer(self):
        self.assertGreaterEqual(
            sys.version_info[:2],
            (3, 8),
            "Anvil targets Python 3.8+; the bootstrap must not select an older interpreter",
        )

    def test_anvilkit_package_is_importable(self):
        import anvilkit

        self.assertTrue(Path(anvilkit.__file__).is_file())

    def test_pyyaml_is_available_in_the_environment(self):
        import yaml

        self.assertTrue(hasattr(yaml, "safe_load"))

    def test_cli_dependencies_are_available(self):
        import click
        import typer

        self.assertTrue(hasattr(typer, "Typer"))
        self.assertTrue(hasattr(click, "prompt"))


class TestEntryPointScript(unittest.TestCase):
    """``anvil`` must delegate, not decide (step 10 cutover)."""

    def script(self) -> str:
        return ENTRYPOINT.read_text(encoding="utf-8")

    def test_the_entrypoint_exists_and_is_executable(self):
        import os

        self.assertTrue(ENTRYPOINT.is_file())
        self.assertTrue(os.access(str(ENTRYPOINT), os.X_OK))

    def test_it_execs_into_the_python_cli(self):
        # exec, not a plain call, so signals and exit codes pass through - a
        # Ctrl-C during './anvil logs' must reach docker, not just the wrapper.
        self.assertIn("exec", self.script())
        self.assertIn("anvilkit.cli", self.script())

    def test_it_delegates_environment_setup_to_the_bootstrap(self):
        self.assertIn("bootstrap.sh", self.script())

    def test_it_contains_no_business_logic(self):
        """The 465-line original is gone; this file must stay a launcher.

        Asserted by size rather than by content: any real behaviour reappearing
        here would blow well past this budget, and a byte cap cannot be argued
        with the way a subjective review can.
        """
        self.assertLess(
            len(self.script().splitlines()),
            60,
            "anvil is a bootstrap; behaviour belongs in anvilkit/",
        )

    def test_the_obsolete_shell_tests_are_gone(self):
        # Their coverage moved to test_render.py; keeping them would re-introduce
        # assertions against generator source text.
        self.assertFalse((REPO_ROOT / "tests" / "test_context_window.sh").exists())
        self.assertFalse((REPO_ROOT / "tests" / "test_frontier_model.sh").exists())


class TestBootstrapPythonPath(unittest.TestCase):
    """``--python-path`` reports the interpreter without provisioning anything.

    ``anvil doctor`` depends on this: a command that diagnoses a broken
    environment must never silently repair it, or the diagnosis is worthless.
    """

    def run_bootstrap(self, *args):
        result = subprocess.run(
            [str(BOOTSTRAP)] + list(args),
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        return result

    def test_python_path_is_supported(self):
        result = self.run_bootstrap("--python-path")
        self.assertEqual(0, result.returncode, result.stderr)

    def test_python_path_prints_a_usable_interpreter(self):
        result = self.run_bootstrap("--python-path")
        reported = result.stdout.strip()
        self.assertTrue(Path(reported).exists(), reported)

    def test_the_reported_interpreter_is_new_enough(self):
        reported = self.run_bootstrap("--python-path").stdout.strip()
        probe = subprocess.run(
            [reported, "-c", "import sys; print('{}.{}'.format(*sys.version_info[:2]))"],
            capture_output=True,
            text=True,
        )
        major, minor = (int(part) for part in probe.stdout.strip().split("."))
        self.assertGreaterEqual((major, minor), (3, 8))

    def test_python_path_installs_nothing(self):
        # No pip run, so it is safe offline and cannot mutate the venv.
        result = self.run_bootstrap("--python-path")
        self.assertNotIn("Installing", result.stderr)
        self.assertNotIn("Provisioning", result.stderr)


if __name__ == "__main__":
    unittest.main()
