"""Generated bake-off fixture - the trivial red task for the Pi phase-1 bake-off.

The fixture is created at runtime, never committed, so every bake-off run starts
from a known-red state: one file to edit and one existing assertion to make
pass. The generated ``test_adder.py`` imports ``bakeoff_fixture.adder`` and runs
with the destination as cwd (namespace packages, so no ``__init__.py``), while
``TASK.md`` names only ``adder.py`` so a model cannot succeed by editing the
test instead of the fixture.

All generated content is a fixed byte string, so two runs into two fresh
destinations are byte-identical.
"""

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

_ADDER_PY = (
    '"""Bake-off fixture module.\n'
    '\n'
    'Deliberate bug: ``add`` subtracts instead of adding.\n'
    '"""\n'
    '\n'
    '\n'
    "def add(a, b):\n"
    '    """Add two numbers (currently broken)."""\n'
    "    return a - b\n"
)

_TEST_ADDER_PY = (
    '"""Bake-off fixture test: the one assertion that must be made to pass."""\n'
    "\n"
    "\n"
    "from bakeoff_fixture.adder import add\n"
    "\n"
    "\n"
    "def test_add():\n"
    "    assert add(2, 3) == 5\n"
)

_TASK_MD = (
    "# Bake-off task\n"
    "\n"
    "Edit `bakeoff_fixture/adder.py` so that `add(2, 3) == 5` passes.\n"
    "\n"
    "The function currently returns `a - b`; the correct change is\n"
    "`a - b` -> `a + b`.\n"
)

# Runner for the red/green check: executes the fixture's test module from
# the destination (cwd) and calls each ``test_`` function directly. The
# fixture's ``tests/`` has no ``__init__.py`` (namespace package) and its
# test is a plain function, so neither ``unittest`` discovery nor
# ``python -m tests.test_adder`` collects it. Any failure - assertion,
# missing file, unimportable module - ends in a non-zero exit with the
# traceback on stderr.
_CHECK_PY = (
    "from tests import test_adder\n"
    "for name in sorted(dir(test_adder)):\n"
    "    if name.startswith('test_'):\n"
    "        getattr(test_adder, name)()\n"
)


class FixtureError(Exception):
    """Any failure to write the bake-off fixture.

    A single exception type covers the only current failure - a destination
    that already contains ``bakeoff_fixture/`` - so callers need one ``except``.
    """


def write_fixture(dest: Path) -> None:
    """Write the generated fixture into ``dest``, creating it if missing.

    The destination must not already contain a ``bakeoff_fixture/`` directory:
    a pre-existing fixture is never overwritten, not even partially.

    Raises:
        FixtureError: ``dest/bakeoff_fixture`` already exists.
    """
    dest = Path(dest)
    if (dest / "bakeoff_fixture").exists():
        raise FixtureError(
            "Fixture already exists at {}; refusing to overwrite it".format(dest)
        )

    (dest / "bakeoff_fixture").mkdir(parents=True)
    (dest / "tests").mkdir(parents=True)
    (dest / "bakeoff_fixture" / "adder.py").write_text(
        _ADDER_PY, encoding="utf-8"
    )
    (dest / "tests" / "test_adder.py").write_text(_TEST_ADDER_PY, encoding="utf-8")
    (dest / "TASK.md").write_text(_TASK_MD, encoding="utf-8")


def assertion_passes(dest: Path) -> dict:
    """Run the fixture's own unittest in a subprocess and report the result.

    This is the red/green check for the bake-off host run: ``passed`` is
    ``True`` iff the fixture's single assertion exits cleanly. The fixture
    code never enters this process - it runs under the current interpreter
    with the destination as cwd, so ``bakeoff_fixture.adder`` resolves
    without an ``__init__.py`` or any path setup.

    The fixture's test file defines a plain ``test_add()`` function, which
    the ``unittest`` discovery runner never collects, so the subprocess
    executes the test module and calls each ``test_`` function directly:
    an assertion failure, a missing file or an import error all surface
    as a traceback on stderr with a non-zero exit, never as an exception
    to this caller.

    Returns:
        dict: ``{"passed": bool, "stderr": str}``.
    """
    dest = Path(dest)
    result = subprocess.run(
        [sys.executable, "-c", _CHECK_PY],
        cwd=str(dest),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return {"passed": result.returncode == 0, "stderr": result.stderr}


def digest_fixture(dest: Path) -> Dict[str, str]:
    """Map every regular file under ``dest`` to the sha256 hex of its bytes.

    Keys are the posix-style paths relative to ``dest`` (for example
    ``"bakeoff_fixture/adder.py"``). The walk does not assume the fixture's
    file set - it digests whatever is present, so a run that added or
    deleted files shows up in ``changed_files`` below.

    Args:
        dest: The fixture destination to digest.

    Returns:
        Dict[str, str]: relative posix path -> sha256 hexdigest.
    """
    dest = Path(dest)
    return {
        path.relative_to(dest).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(dest.rglob("*"))
        if path.is_file()
    }


def changed_files(before: Dict[str, str], dest: Path) -> List[str]:
    """Compare the current tree under ``dest`` to an earlier digest.

    A file whose content changed and a file that was absent from ``before``
    both appear as their relative posix path; a file present in ``before``
    but missing now appears as ``"deleted:"`` + relative path, so a run that
    deleted a fixture file cannot read as a clean result.

    Args:
        before: A mapping returned by :func:`digest_fixture`.
        dest: The fixture destination to inspect.

    Returns:
        List[str]: sorted list of changed, added and deleted files.
    """
    after = digest_fixture(dest)
    # A file present now that was added or rewritten appears as its
    # relative path; deletions are reported separately with the prefix.
    changed = [name for name in after if before.get(name) != after[name]]
    deleted = ["deleted:" + name for name in before if name not in after]
    return sorted(changed + deleted)
