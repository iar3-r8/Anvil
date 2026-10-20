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

from pathlib import Path

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
