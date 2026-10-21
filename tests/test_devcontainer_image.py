"""Tests for the devcontainer image ``.devcontainer/Dockerfile`` (behaviour 3
of ``plans/pi-bakeoff-devcontainer.md``).

The Dockerfile is data under test: the assertions read its text and pin the
one ``RUN`` first-physical-line that must carry the bake-off globals —
``npm install -g``, ``--ignore-scripts``, and the two exact pins
``@earendil-works/pi-coding-agent@1.3.0`` and ``pi-ultrawork@1.2.0`` (the same
pins ``docker/Dockerfile.bakeoff`` carries) — and the ordering that line must
satisfy: it appears before ``USER vscode``, because the ``vscode`` user (uid
1000) cannot write to the image's global npm root, so the install must run as
root.

This test deliberately pins no npm root path: the root differs per image (the
Interface facts table of the plan), so asserting one would couple the test to
an implementation detail it does not own.

Like ``tests/test_bakeoff_image.py``, only each ``RUN`` instruction's first
physical line is read (``tests/test_bakeoff_image.py:40``,
``docker/Dockerfile.bakeoff:26-27``), so the whole install must sit on that
one line — a first line ending in a backslash does not count.

``TestTemplateDevcontainerMirror`` (behaviour 4 of the same plan) pins the
same line in ``templates/devcontainer/Dockerfile`` and asserts it is byte
identical to the devcontainer line, so a half-applied mirror cannot land.
"""

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEVCONTAINER_DOCKERFILE = REPO_ROOT / ".devcontainer" / "Dockerfile"
TEMPLATES_DOCKERFILE = REPO_ROOT / "templates" / "devcontainer" / "Dockerfile"

NPM_INSTALL = "npm install -g"
IGNORE_SCRIPTS = "--ignore-scripts"
PI_AGENT_PACKAGE = "@earendil-works/pi-coding-agent"
PI_AGENT_VERSION = "1.3.0"
PI_AGENT_PIN = PI_AGENT_PACKAGE + "@" + PI_AGENT_VERSION
ULTRAWORK_PACKAGE = "pi-ultrawork"
ULTRAWORK_VERSION = "1.2.0"
ULTRAWORK_PIN = ULTRAWORK_PACKAGE + "@" + ULTRAWORK_VERSION


def _instruction_lines(text, instruction):
    """Stripped lines that begin with the given Dockerfile instruction
    (instruction name matched case-insensitively, argument kept verbatim).
    Because only lines that *begin* with the instruction match, these are
    first physical lines — continuation lines are excluded."""
    pattern = re.compile(r"^" + re.escape(instruction) + r"\b", re.IGNORECASE)
    return [line.strip() for line in text.splitlines() if pattern.match(line.strip())]


def _npm_install_run_lines(text):
    """First physical lines of every ``RUN`` instruction that runs an
    ``npm install``."""
    return [
        line
        for line in _instruction_lines(text, "RUN")
        if re.search(r"\bnpm\s+install\b", line)
    ]


def _npm_install_g_run_lines(text):
    """First physical lines of every ``RUN`` instruction that runs
    ``npm install -g`` — the install line the two Dockerfiles must mirror."""
    return [line for line in _npm_install_run_lines(text) if NPM_INSTALL in line]


class DevcontainerImageCase(unittest.TestCase):
    """Shared access to the devcontainer Dockerfile text, guarded so a missing
    file reports itself instead of leaking a bare ``FileNotFoundError``."""

    @property
    def text(self):
        if not DEVCONTAINER_DOCKERFILE.is_file():
            self.fail(".devcontainer/Dockerfile does not exist")
        return DEVCONTAINER_DOCKERFILE.read_text(encoding="utf-8")


class TestDevcontainerNpmGlobals(DevcontainerImageCase):
    """The pinned npm globals the devcontainer image must carry as root."""

    def test_npm_install_run_first_line_carries_both_pinned_globals(self):
        npm_lines = _npm_install_run_lines(self.text)

        self.assertTrue(
            npm_lines,
            "no RUN instruction installs the npm globals; the devcontainer "
            "must bake @earendil-works/pi-coding-agent and pi-ultrawork "
            "(behaviour 3 of plans/pi-bakeoff-devcontainer.md)",
        )
        self.assertTrue(
            any(
                NPM_INSTALL in line
                and IGNORE_SCRIPTS in line
                and PI_AGENT_PIN in line
                and ULTRAWORK_PIN in line
                and not line.rstrip().endswith("\\")
                for line in npm_lines
            ),
            "expected one RUN first physical line containing %s, %s, %s and "
            "%s, all on that single line (a first line ending in a "
            "backslash does not count, because only first physical lines "
            "are read); got: %r"
            % (NPM_INSTALL, IGNORE_SCRIPTS, PI_AGENT_PIN, ULTRAWORK_PIN, npm_lines),
        )

    def test_npm_install_run_precedes_user_vscode(self):
        npm_line = None
        user_line = None
        for index, raw in enumerate(self.text.splitlines()):
            stripped = raw.strip()
            if (
                npm_line is None
                and re.match(r"^RUN\b", stripped, re.IGNORECASE)
                and re.search(r"\bnpm\s+install\b", stripped)
            ):
                npm_line = index
            if user_line is None and re.match(
                r"^USER\s+vscode\b", stripped, re.IGNORECASE
            ):
                user_line = index

        self.assertIsNotNone(
            user_line,
            "no 'USER vscode' instruction found in .devcontainer/Dockerfile",
        )
        self.assertIsNotNone(
            npm_line,
            "no RUN npm install first line found in .devcontainer/Dockerfile",
        )
        self.assertLess(
            npm_line,
            user_line,
            "the npm install RUN (line %d) must appear before 'USER vscode' "
            "(line %d): the vscode user is uid 1000 and cannot write to the "
            "global npm root, so the globals must be installed as root"
            % (npm_line + 1, user_line + 1),
        )

    def test_package_pins_are_exact_not_bare_or_latest(self):
        for package, version in (
            (PI_AGENT_PACKAGE, PI_AGENT_VERSION),
            (ULTRAWORK_PACKAGE, ULTRAWORK_VERSION),
        ):
            bare = re.findall(
                r"(?<![\w@-])" + re.escape(package) + r"(?!@)", self.text
            )
            self.assertEqual(
                bare,
                [],
                "%s appears without a version pin (a bare name or @latest "
                "is not allowed); expected exactly %s@%s"
                % (package, package, version),
            )
            for match in re.finditer(re.escape(package) + r"@", self.text):
                suffix = self.text[match.end():]
                self.assertRegex(
                    suffix,
                    r"^%s(?![0-9A-Za-z._-])" % re.escape(version),
                    "%s must be pinned to exactly %s, found: %r"
                    % (package, version, suffix.split()[:2]),
                )


class TestTemplateDevcontainerMirror(DevcontainerImageCase):
    """Behaviour 4: the provisioned template mirrors the devcontainer's
    npm-install line, byte for byte."""

    @property
    def template_text(self):
        if not TEMPLATES_DOCKERFILE.is_file():
            self.fail("templates/devcontainer/Dockerfile does not exist")
        return TEMPLATES_DOCKERFILE.read_text(encoding="utf-8")

    def test_template_npm_install_run_first_line_carries_both_pinned_globals(self):
        npm_lines = _npm_install_g_run_lines(self.template_text)

        self.assertTrue(
            npm_lines,
            "no RUN npm install -g first line found in "
            "templates/devcontainer/Dockerfile; the provisioned template must "
            "mirror the devcontainer install line (behaviour 4 of "
            "plans/pi-bakeoff-devcontainer.md)",
        )
        self.assertTrue(
            any(
                IGNORE_SCRIPTS in line
                and PI_AGENT_PIN in line
                and ULTRAWORK_PIN in line
                and not line.rstrip().endswith("\\")
                for line in npm_lines
            ),
            "expected the RUN first physical line in templates/devcontainer/"
            "Dockerfile to contain %s, %s and %s, all on that single line (a "
            "first line ending in a backslash does not count); got: %r"
            % (IGNORE_SCRIPTS, PI_AGENT_PIN, ULTRAWORK_PIN, npm_lines),
        )

    def test_template_npm_install_line_identical_to_devcontainer(self):
        template_lines = _npm_install_g_run_lines(self.template_text)
        devcontainer_lines = _npm_install_g_run_lines(self.text)

        self.assertTrue(
            devcontainer_lines,
            "no RUN npm install -g first line found in .devcontainer/Dockerfile",
        )
        self.assertTrue(
            template_lines,
            "no RUN npm install -g first line found in "
            "templates/devcontainer/Dockerfile",
        )
        self.assertEqual(
            template_lines[0],
            devcontainer_lines[0],
            "the npm install line diverged between the two Dockerfiles: "
            "templates/devcontainer/Dockerfile has %r, .devcontainer/Dockerfile "
            "has %r" % (template_lines[0], devcontainer_lines[0]),
        )

    def test_template_npm_install_run_precedes_user_vscode(self):
        npm_line = None
        user_line = None
        for index, raw in enumerate(self.template_text.splitlines()):
            stripped = raw.strip()
            if (
                npm_line is None
                and re.match(r"^RUN\b", stripped, re.IGNORECASE)
                and NPM_INSTALL in stripped
            ):
                npm_line = index
            if user_line is None and re.match(
                r"^USER\s+vscode\b", stripped, re.IGNORECASE
            ):
                user_line = index

        self.assertIsNotNone(
            user_line,
            "no 'USER vscode' instruction found in templates/devcontainer/Dockerfile",
        )
        self.assertIsNotNone(
            npm_line,
            "no RUN npm install -g first line found in "
            "templates/devcontainer/Dockerfile",
        )
        self.assertLess(
            npm_line,
            user_line,
            "the npm install RUN (line %d) must appear before 'USER vscode' "
            "(line %d) in templates/devcontainer/Dockerfile, mirroring "
            ".devcontainer/Dockerfile" % (npm_line + 1, user_line + 1),
        )


if __name__ == "__main__":
    unittest.main()
