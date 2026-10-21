"""Tests for the bake-off image ``docker/Dockerfile.bakeoff`` (behaviour 2 of
``plans/pi-phase1b-docker.md``).

The Dockerfile is data under test: the assertions read its text and pin the
instructions a correct image needs -- the documented Pi sandbox base, the
apt packages the driver runs on, the exact-pinned npm installs, the
``anvilkit/`` copy, a non-root user and the fixture working directory -- plus
the safety properties that must hold by absence: no host ``~/.pi/agent``
path, no ``docker.sock``, and no credential key on any ``ENV`` line. The
base image and the ``bash ca-certificates git ripgrep`` set are Pi's own
documented sandbox base ([`doc/external/pi-dev/containerization.md`](../doc/external/pi-dev/containerization.md)),
which also carries the Node >= 22.19 that pi-coding-agent 1.3.0's
``engines`` field requires.

The file does not exist yet; until it is added every test here fails from
the missing-file guard in :attr:`BakeoffImageCase.text` with exactly
``docker/Dockerfile.bakeoff does not exist`` -- never from a bare
``FileNotFoundError`` leaking out.
"""

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BAKEOFF_DOCKERFILE = REPO_ROOT / "docker" / "Dockerfile.bakeoff"

BASE_IMAGE = "node:24-bookworm-slim"
APT_PACKAGES = ("python3", "python3-yaml", "bash", "ca-certificates", "git", "ripgrep")
NPM_INSTALL = "npm install -g --ignore-scripts"
PI_AGENT_PIN = "@earendil-works/pi-coding-agent@1.3.0"
ULTRAWORK_PIN = "pi-ultrawork@1.2.0"
CREDENTIAL_MARKERS = ("TOKEN", "KEY", "SECRET")


def _instruction_lines(text, instruction):
    """Stripped lines that begin with the given Dockerfile instruction
    (instruction name matched case-insensitively, argument kept verbatim)."""
    pattern = re.compile(r"^" + re.escape(instruction) + r"\b", re.IGNORECASE)
    return [line.strip() for line in text.splitlines() if pattern.match(line.strip())]


def _is_from_base(line, base_image):
    """True if *line* is a FROM instruction whose image is exactly
    *base_image* (an ``AS alias`` after the image is allowed)."""
    parts = line.split(None, 1)
    if len(parts) != 2 or parts[0].upper() != "FROM":
        return False
    image = parts[1].split(None, 1)[0]
    return image == base_image


def _apt_install_segments(text):
    """Package lists of every ``apt-get install`` command in the text.

    Handles the common ``RUN apt-get update && apt-get install -y ...``
    form: each ``apt-get install`` occurrence contributes the remainder of
    its command (up to the next ``&&``), with leading flags stripped.
    """
    segments = []
    for line in text.splitlines():
        for match in re.finditer(r"apt-get\s+install\b", line):
            tail = line[match.end():].split("&&", 1)[0]
            tail = re.sub(r"^(\s+-\S+)+", "", tail)
            segments.append(tail)
    return segments


def _word_present(text, name):
    """True if *name* appears as a standalone word (not fused into a
    longer word or a hyphenated neighbour such as ``git-lfs``)."""
    return re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", text) is not None


def _npm_install_lines(text):
    return [line.strip() for line in text.splitlines() if re.search(r"\bnpm\s+install\b", line)]


def _env_key_is_credential_like(line):
    """True if the key(s) on this ``ENV`` instruction look like a
    credential: any key containing ``TOKEN``, ``KEY`` or ``SECRET``."""
    parts = line.split(None, 1)
    if len(parts) != 2:
        return False
    rest = parts[1]
    keys = re.findall(r"([A-Za-z_][A-Za-z0-9_.\-]*)\s*=", rest)
    if not keys:
        first = rest.split()
        keys = [first[0]] if first else []
    return any(
        any(marker in key.upper() for marker in CREDENTIAL_MARKERS) for key in keys
    )


class BakeoffImageCase(unittest.TestCase):
    """Shared access to the bake-off Dockerfile text, guarded so a missing
    file reports itself instead of leaking a bare ``FileNotFoundError``."""

    @property
    def text(self):
        if not BAKEOFF_DOCKERFILE.is_file():
            self.fail("docker/Dockerfile.bakeoff does not exist")
        return BAKEOFF_DOCKERFILE.read_text(encoding="utf-8")


class TestBakeoffImageContent(BakeoffImageCase):
    """The instructions the bake-off image must carry."""

    def test_from_instruction_is_documented_pi_sandbox_base(self):
        from_lines = _instruction_lines(self.text, "FROM")

        self.assertTrue(
            any(_is_from_base(line, BASE_IMAGE) for line in from_lines),
            "expected 'FROM %s' (Pi's documented sandbox base, which also "
            "carries the Node >= 22.19 pi-coding-agent 1.3.0 requires); "
            "got: %r" % (BASE_IMAGE, from_lines),
        )

    def test_apt_get_install_covers_python3_and_sandbox_packages(self):
        segments = _apt_install_segments(self.text)

        self.assertTrue(segments, "no apt-get install command found")
        blob = " ".join(segments)
        missing = [pkg for pkg in APT_PACKAGES if not _word_present(blob, pkg)]
        self.assertEqual(
            missing,
            [],
            "apt-get install is missing %r (found: %r)" % (missing, segments),
        )

    def test_npm_install_line_is_global_and_ignores_scripts(self):
        npm_lines = _npm_install_lines(self.text)

        self.assertTrue(npm_lines, "no npm install line found")
        self.assertTrue(
            any(NPM_INSTALL in line for line in npm_lines),
            "expected '%s'; got: %r" % (NPM_INSTALL, npm_lines),
        )
        bad = [
            line
            for line in npm_lines
            if "--ignore-scripts" not in line
            or not re.search(r"(^|\s)-g(\s|$)", line)
        ]
        self.assertEqual(
            bad, [], "npm install lines missing -g or --ignore-scripts: %r" % bad
        )

    def test_npm_install_pins_pi_coding_agent_exactly(self):
        npm_lines = _npm_install_lines(self.text)

        self.assertIn(
            PI_AGENT_PIN,
            " ".join(npm_lines),
            "npm install must carry the exact pin %s; got: %r"
            % (PI_AGENT_PIN, npm_lines),
        )

    def test_npm_install_pins_pi_ultrawork_exactly(self):
        npm_lines = _npm_install_lines(self.text)

        self.assertIn(
            ULTRAWORK_PIN,
            " ".join(npm_lines),
            "npm install must carry the exact pin %s; got: %r"
            % (ULTRAWORK_PIN, npm_lines),
        )

    def test_package_pins_are_exact_not_ranges_or_bare_names(self):
        for package, version in (
            ("@earendil-works/pi-coding-agent", "1.3.0"),
            ("pi-ultrawork", "1.2.0"),
        ):
            bare = re.findall(
                r"(?<![\w@-])" + re.escape(package) + r"(?!@)", self.text
            )
            self.assertEqual(
                bare,
                [],
                "%s appears without its exact version pin %s: %r"
                % (package, version, bare),
            )
            for match in re.finditer(re.escape(package) + r"@", self.text):
                suffix = self.text[match.end():]
                self.assertRegex(
                    suffix,
                    r"^%s(?![0-9A-Za-z._-])" % re.escape(version),
                    "%s must be pinned to exactly %s, found: %r"
                    % (package, version, suffix.split()[:2]),
                )

    def test_copy_instruction_copies_anvilkit(self):
        copy_lines = _instruction_lines(self.text, "COPY")

        self.assertTrue(
            any("anvilkit" in line for line in copy_lines),
            "no COPY line mentioning anvilkit; got: %r" % copy_lines,
        )

    def test_user_instruction_runs_a_non_root_user(self):
        user_lines = _instruction_lines(self.text, "USER")

        self.assertTrue(user_lines, "no USER instruction found")
        # The last USER instruction wins: that is the identity the
        # container actually runs as.
        parts = user_lines[-1].split(None, 1)
        value = parts[1].strip() if len(parts) > 1 else ""
        user = value.split(":", 1)[0].strip()
        self.assertNotIn(
            user.lower(),
            ("", "root"),
            "the bake-off image must run as a non-root user, got USER %r" % value,
        )

    def test_run_instruction_creates_agent_home_owned_by_container_user(self):
        user_lines = _instruction_lines(self.text, "USER")
        self.assertTrue(user_lines, "no USER instruction found")
        # The last USER instruction wins: that is the identity the
        # container actually runs as.
        parts = user_lines[-1].split(None, 1)
        user = parts[1].split(":", 1)[0].strip() if len(parts) > 1 else ""
        agent_dir = "/home/%s/.pi/agent" % user

        run_lines = _instruction_lines(self.text, "RUN")
        creating = [
            line
            for line in run_lines
            if agent_dir in line and re.search(r"\b(mkdir|chown)\b", line)
        ]
        self.assertTrue(
            creating,
            "no RUN instruction creates %s; the named volume is created "
            "empty, so without content at the agent home in the image "
            "Docker's first-mount copy-up never runs and the mountpoint "
            "lands root-owned (the container user cannot write "
            "models.json into it); got RUN lines: %r"
            % (agent_dir, run_lines),
        )
        chowning = [
            line for line in creating if re.search(r"\bchown\b", line) and user in line
        ]
        self.assertTrue(
            chowning,
            "no RUN instruction chowns %s to the container user %r; the "
            "copy-up must transfer the directory with the container "
            "user's ownership, so the driver can write into the volume "
            "(created lines: %r)" % (agent_dir, user, creating),
        )

    def test_workdir_is_workspace(self):
        workdir_lines = _instruction_lines(self.text, "WORKDIR")

        self.assertTrue(
            any(
                re.match(r"^WORKDIR\s+/workspace(\s|$)", line, re.IGNORECASE)
                for line in workdir_lines
            ),
            "expected 'WORKDIR /workspace' (the fixture cwd convention); "
            "got: %r" % workdir_lines,
        )


class TestBakeoffImageSafety(BakeoffImageCase):
    """The safety properties the bake-off image must hold by absence."""

    def test_text_does_not_reference_host_pi_agent_home(self):
        self.assertNotIn(
            "~/.pi/agent",
            self.text,
            "the bake-off image must not reference the host agent home "
            "~/.pi/agent (it carries credentials and sessions)",
        )

    def test_text_does_not_reference_docker_socket(self):
        self.assertNotIn(
            "docker.sock",
            self.text,
            "the bake-off image must not reference the docker socket",
        )

    def test_env_lines_have_no_credential_keys(self):
        env_lines = _instruction_lines(self.text, "ENV")
        offending = [line for line in env_lines if _env_key_is_credential_like(line)]

        self.assertEqual(
            offending,
            [],
            "no ENV line may carry a key containing TOKEN, KEY or SECRET: %r"
            % offending,
        )


if __name__ == "__main__":
    unittest.main()
