"""Tests for the Pi sandbox image ``docker/Dockerfile.sandbox`` (behaviours
1-5 of ``plans/pi-sandbox-image.md``).

The Dockerfile is data under test: the assertions read its text and pin the
instructions a correct image needs -- Pi's documented sandbox base, the apt
set the agent runs on (without ``git``), the exact-pinned npm install on one
``RUN``'s first physical line, a non-root user with a writable agent home --
plus the safety properties that must hold by absence: no host
``~/.pi/agent`` path, no ``docker.sock``, and no credential key on any
``ENV`` line. The base image and the ``bash ca-certificates ripgrep`` set
are Pi's own documented sandbox recipe
([`doc/external/pi-dev/containerization.md`](../doc/external/pi-dev/containerization.md)),
minus ``git``: the base image installs none either, so absence costs only
not adding it, and a nested ``git push`` inside a script then finds no
binary.

The file does not exist yet; until it is added every content and safety
test here fails from the missing-file guard in :attr:`SandboxImageCase.text`
with exactly ``docker/Dockerfile.sandbox does not exist`` -- never from a
bare ``FileNotFoundError`` leaking out.

The boundary pins in :class:`TestExistingImagesAndServicesUnchanged` assert
the *current* state of ``docker/Dockerfile.bakeoff`` and
``docker-compose.yml`` and pass already: they fail only if the sandbox work
clobbers the bake-off harness.
"""

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import yamlio  # noqa: E402

BAKEOFF_DOCKERFILE = REPO_ROOT / "docker" / "Dockerfile.bakeoff"
SANDBOX_DOCKERFILE = REPO_ROOT / "docker" / "Dockerfile.sandbox"
COMPOSE_YAML = REPO_ROOT / "docker-compose.yml"

BASE_IMAGE = "node:24-bookworm-slim"
APT_PACKAGES = ("bash", "ca-certificates", "ripgrep")
NPM_INSTALL = "npm install -g --ignore-scripts"
PI_AGENT_PACKAGE = "@earendil-works/pi-coding-agent"
PI_AGENT_VERSION = "1.3.0"
PI_AGENT_PIN = PI_AGENT_PACKAGE + "@" + PI_AGENT_VERSION
CREDENTIAL_MARKERS = ("TOKEN", "KEY", "SECRET")

BAKEOFF_APT_PACKAGES = ("git", "python3", "python3-yaml")
CODER_SERVICES = ("coder_qdrant", "llama-swap")
LLM_NETWORK = "llm-network"


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


def _last_user(text):
    """The user name the last ``USER`` instruction names (empty string if
    none, or if the last one is valueless)."""
    user_lines = _instruction_lines(text, "USER")
    if not user_lines:
        return ""
    parts = user_lines[-1].split(None, 1)
    if len(parts) < 2:
        return ""
    return parts[1].split(":", 1)[0].strip()


class SandboxImageCase(unittest.TestCase):
    """Shared access to the sandbox Dockerfile text, guarded so a missing
    file reports itself instead of leaking a bare ``FileNotFoundError``."""

    @property
    def text(self):
        if not SANDBOX_DOCKERFILE.is_file():
            self.fail("docker/Dockerfile.sandbox does not exist")
        return SANDBOX_DOCKERFILE.read_text(encoding="utf-8")


class TestSandboxImageContent(SandboxImageCase):
    """The instructions the sandbox image must carry."""

    def test_from_instruction_is_documented_pi_sandbox_base(self):
        from_lines = _instruction_lines(self.text, "FROM")

        self.assertTrue(
            any(_is_from_base(line, BASE_IMAGE) for line in from_lines),
            "expected 'FROM %s' (Pi's documented sandbox base, which also "
            "carries the Node >= 22.19 pi-coding-agent 1.3.0 requires); "
            "got: %r" % (BASE_IMAGE, from_lines),
        )

    def test_apt_get_install_is_one_command_carrying_the_sandbox_set(self):
        segments = _apt_install_segments(self.text)

        self.assertEqual(
            len(segments),
            1,
            "expected exactly one apt-get install; got: %r" % segments,
        )
        missing = [pkg for pkg in APT_PACKAGES if not _word_present(segments[0], pkg)]
        self.assertEqual(
            missing,
            [],
            "apt-get install is missing %r (found: %r)" % (missing, segments),
        )

    def test_git_is_absent_as_a_standalone_word(self):
        text = self.text

        self.assertFalse(
            _word_present(text, "git"),
            "'git' appears as a standalone word in docker/Dockerfile.sandbox: "
            "the image must not install it — a nested 'git push' inside a "
            "script must find no binary, because the driver owns git; the "
            "base image installs none either, so absence costs only not "
            "adding it",
        )

    def test_npm_install_sits_on_one_run_first_physical_line(self):
        run_lines = _instruction_lines(self.text, "RUN")
        npm_runs = [line for line in run_lines if re.search(r"\bnpm\s+install\b", line)]

        self.assertEqual(
            len(npm_runs),
            1,
            "exactly one RUN first physical line may npm-install; "
            "got RUN lines: %r" % run_lines,
        )
        self.assertIn(
            NPM_INSTALL,
            npm_runs[0],
            "the npm install RUN first physical line must carry %r; "
            "got: %r" % (NPM_INSTALL, npm_runs[0]),
        )
        self.assertIn(
            PI_AGENT_PIN,
            npm_runs[0],
            "the npm install RUN first physical line must carry the "
            "exact pin %s; got: %r" % (PI_AGENT_PIN, npm_runs[0]),
        )

    def test_npm_install_line_is_global_and_ignores_scripts(self):
        npm_lines = _npm_install_lines(self.text)

        self.assertTrue(npm_lines, "no npm install line found")
        bad = [
            line
            for line in npm_lines
            if "--ignore-scripts" not in line
            or not re.search(r"(^|\s)-g(\s|$)", line)
        ]
        self.assertEqual(
            bad, [], "npm install lines missing -g or --ignore-scripts: %r" % bad
        )

    def test_package_pin_is_exact_not_bare_or_range(self):
        bare = re.findall(
            r"(?<![\w@-])" + re.escape(PI_AGENT_PACKAGE) + r"(?!@)", self.text
        )
        self.assertEqual(
            bare,
            [],
            "%s appears without its exact version pin %s: %r"
            % (PI_AGENT_PACKAGE, PI_AGENT_VERSION, bare),
        )
        for match in re.finditer(re.escape(PI_AGENT_PACKAGE) + r"@", self.text):
            suffix = self.text[match.end():]
            self.assertRegex(
                suffix,
                r"^%s(?![0-9A-Za-z._-])" % re.escape(PI_AGENT_VERSION),
                "%s must be pinned to exactly %s, found: %r"
                % (PI_AGENT_PACKAGE, PI_AGENT_VERSION, suffix.split()[:2]),
            )

    def test_user_instruction_runs_a_non_root_user(self):
        user_lines = _instruction_lines(self.text, "USER")

        self.assertTrue(user_lines, "no USER instruction found")
        # The last USER instruction wins: that is the identity the
        # container actually runs as.
        value = user_lines[-1].split(None, 1)[1] if " " in user_lines[-1] else ""
        user = value.split(":", 1)[0].strip()
        self.assertNotIn(
            user.lower(),
            ("", "root"),
            "the sandbox image must run as a non-root user, got USER %r" % user,
        )

    def test_run_instruction_creates_and_chowns_the_agent_home(self):
        user = _last_user(self.text)
        agent_dir = "/home/%s/.pi/agent" % user

        run_lines = _instruction_lines(self.text, "RUN")
        both = [
            line
            for line in run_lines
            if agent_dir in line
            and re.search(r"\bmkdir\b", line)
            and re.search(r"\bchown\b", line)
            and user in line
        ]
        self.assertTrue(
            both,
            "one RUN first physical line must both create and chown %s "
            "to the container user %r: the named volume is created empty, "
            "so without content at the agent home in the image Docker's "
            "first-mount copy-up never runs and the mountpoint lands "
            "root-owned (the container user cannot write into it); "
            "got RUN lines: %r" % (agent_dir, user, run_lines),
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


class TestSandboxImageSafety(SandboxImageCase):
    """The safety properties the sandbox image must hold by absence."""

    def test_text_does_not_reference_host_pi_agent_home(self):
        self.assertNotIn(
            "~/.pi/agent",
            self.text,
            "the sandbox image must not reference the host agent home "
            "~/.pi/agent (it carries credentials and sessions)",
        )

    def test_text_does_not_reference_docker_socket(self):
        self.assertNotIn(
            "docker.sock",
            self.text,
            "the sandbox image must not reference the docker socket",
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


class TestExistingImagesAndServicesUnchanged(unittest.TestCase):
    """Boundary pins: the sandbox work must leave the bake-off harness and
    the compose services it runs on untouched. These assert the current
    state and pass already; they fail only if a later change clobbers it."""

    @property
    def bakeoff_text(self):
        if not BAKEOFF_DOCKERFILE.is_file():
            self.fail("docker/Dockerfile.bakeoff does not exist")
        return BAKEOFF_DOCKERFILE.read_text(encoding="utf-8")

    @property
    def compose_data(self):
        try:
            return yamlio.load(COMPOSE_YAML)
        except yamlio.YamlError as exc:
            self.fail("could not parse docker-compose.yml: {}".format(exc))

    def test_bakeoff_dockerfile_still_installs_git_python_and_yaml(self):
        segments = _apt_install_segments(self.bakeoff_text)

        self.assertTrue(
            segments,
            "no apt-get install command found in docker/Dockerfile.bakeoff",
        )
        blob = " ".join(segments)
        missing = [pkg for pkg in BAKEOFF_APT_PACKAGES if not _word_present(blob, pkg)]
        self.assertEqual(
            missing,
            [],
            "docker/Dockerfile.bakeoff apt-get install is missing %r "
            "(found: %r); the bake-off harness needs all three"
            % (missing, segments),
        )

    def test_bakeoff_dockerfile_still_copies_anvilkit(self):
        copy_lines = _instruction_lines(self.bakeoff_text, "COPY")

        self.assertTrue(
            any("anvilkit" in line for line in copy_lines),
            "docker/Dockerfile.bakeoff must still carry COPY anvilkit/ "
            "(the harness source); got: %r" % copy_lines,
        )

    def test_llm_network_keeps_its_name(self):
        networks = self.compose_data.get("networks") or {}

        self.assertEqual(
            (networks.get(LLM_NETWORK) or {}).get("name"),
            LLM_NETWORK,
            "networks.{} must keep name: {}".format(LLM_NETWORK, LLM_NETWORK),
        )

    def test_coder_services_keep_the_coder_profile(self):
        services = self.compose_data.get("services")
        self.assertIsInstance(
            services, dict, "docker-compose.yml has no top-level 'services:'"
        )
        for name in CODER_SERVICES:
            svc = services.get(name)
            self.assertIsInstance(
                svc,
                dict,
                "existing service '{}' is missing from docker-compose.yml".format(name),
            )
            self.assertEqual(
                svc.get("profiles"),
                ["coder"],
                "service '{}' must still carry exactly profiles: "
                "[\"coder\"]".format(name),
            )


if __name__ == "__main__":
    unittest.main()
