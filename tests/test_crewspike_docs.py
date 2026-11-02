"""Tests for the pi-crew spike boundary files (batch A of
``plans/pi-crew-spike.md``).

Four files are data under test, read exactly as committed:

- ``docker/Dockerfile.crewspike`` — the spike image: same base and apt set as
  the bake-off image, one ``npm install -g --ignore-scripts`` line pinning
  both packages, the ``anvilkit/`` copy, a non-root user with its agent home
  created and chowned, and the fixture working directory; plus the safety
  properties that hold by absence: no credential ``ENV`` key, no host
  ``~/.pi/agent`` path, no ``docker.sock``.
- ``docker-compose.yml`` — the new ``pi-crewspike`` service in profile
  ``crewspike``, with its build block, command, gateway env, the
  read-only ``config.yaml`` bind, the ``./results`` bind and the named
  volume at the agent home; and the guarantee that every pre-existing
  service is unchanged and unprofiled.
- ``doc/external/pi-crew/postinstall-mjs.md`` — the saved postinstall source
  page, with its source URL in the header; the recommendation page states
  the ``--ignore-scripts`` verdict for it.
- ``doc/pi-crew-spike/README.md`` and ``doc/pi-crew-spike/recommendation.md``
  — the reproduce recipe as literal lines, the artifact layout, the three
  unknowns with headings, the recorded-run verdicts in the two run-dependent
  sections (measured facts only, no invented numbers), and the back-link to
  the intake issue.

The Dockerfile, the two spike doc pages and (in part) the Compose service do
not exist yet; until they are added the guards below report the missing file
with an explicit message instead of leaking a bare ``FileNotFoundError``.
"""

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import yamlio  # noqa: E402

CREWSPIKE_DOCKERFILE_PATH = REPO_ROOT / "docker" / "Dockerfile.crewspike"
BAKEOFF_DOCKERFILE = REPO_ROOT / "docker" / "Dockerfile.bakeoff"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
POSTINSTALL_DOC = REPO_ROOT / "doc" / "external" / "pi-crew" / "postinstall-mjs.md"
SPIKE_README = REPO_ROOT / "doc" / "pi-crew-spike" / "README.md"
RECOMMENDATION = REPO_ROOT / "doc" / "pi-crew-spike" / "recommendation.md"

BASE_IMAGE = "node:24-bookworm-slim"
PI_AGENT_PIN = "@earendil-works/pi-coding-agent@1.3.0"
CREW_PIN = "pi-crew@0.11.57"
NPM_INSTALL = "npm install -g --ignore-scripts"
CREDENTIAL_MARKERS = ("TOKEN", "KEY", "SECRET")

# Pinned verbatim from the committed docker-compose.yml: the service names
# that must survive the change untouched.
EXISTING_SERVICES = ("coder_qdrant", "llama-swap", "pi-bakeoff")

SPIKE_PROFILE = "crewspike"
CREWSPIKE_SERVICE = "pi-crewspike"
CREWSPIKE_DOCKERFILE = "docker/Dockerfile.crewspike"
CREWSPIKE_COMMAND = ["python3", "-m", "anvilkit.pi.picrew"]
CREWSPIKE_ENV = {
    "PI_GATEWAY_HOST": "llama-swap",
    "PI_GATEWAY_PORT": "8080",
    "PI_CREW_BROKER": "0",
}

REPRODUCE_COMMANDS = (
    "docker compose --profile coder up -d",
    "mkdir -p ./results && chmod 777 ./results",
    "docker compose --profile crewspike run --rm pi-crewspike",
)
ARTIFACT_NAMES = ("record.json", ".crew/", "./results/")

# The recorded-run marker, retired: the two run-dependent sections of the
# recommendation page carried this line (not a verdict) until the recorded
# run; the re-anchored tests pin its absence now that the verdicts landed.
RECORDED_RUN_MARKER = "not been performed"
BACK_LINK = "iar3-r8/anvil#84"


# ---------------------------------------------------------------------------
# Shared text helpers (same conventions as tests/test_bakeoff_image.py)
# ---------------------------------------------------------------------------


def _instruction_lines(text, instruction):
    """Stripped lines that begin with the given Dockerfile instruction
    (instruction name matched case-insensitively, argument kept verbatim)."""
    pattern = re.compile(r"^" + re.escape(instruction) + r"\b", re.IGNORECASE)
    return [line.strip() for line in text.splitlines() if pattern.match(line.strip())]


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


def _apt_package_set(text):
    """The set of package names installed by every ``apt-get install`` in
    the text, line-continuation backslashes excluded."""
    packages = set()
    for segment in _apt_install_segments(text):
        for token in segment.split():
            token = token.strip().strip("\\").strip()
            if token:
                packages.add(token)
    return packages


def _npm_install_lines(text):
    return [
        line.strip() for line in text.splitlines() if re.search(r"\bnpm\s+install\b", line)
    ]


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


def _user_from_instructions(text):
    """The identity the container runs as: the last ``USER`` instruction."""
    user_lines = _instruction_lines(text, "USER")
    if not user_lines:
        return None
    parts = user_lines[-1].split(None, 1)
    value = parts[1].strip() if len(parts) > 1 else ""
    return value.split(":", 1)[0].strip() or None


def _markdown_sections(text):
    """The markdown sections of *text* as ``{"heading", "body"}`` dicts.

    Each heading line (any level) starts a section whose body runs until the
    next heading line; text before the first heading is dropped.
    """
    sections = []
    current = None
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            if current is not None:
                sections.append(current)
            current = {
                "heading": line.strip().lstrip("#").strip(),
                "body": [],
            }
        elif current is not None:
            current["body"].append(line)
    if current is not None:
        sections.append(current)
    for section in sections:
        section["body"] = "\n".join(section["body"])
    return sections


# ---------------------------------------------------------------------------
# Shared compose helpers (data-structure assertions, per yamlio convention)
# ---------------------------------------------------------------------------


def _services(compose):
    services = compose.get("services")
    return services if isinstance(services, dict) else {}


def _env_mapping(service):
    """The service environment as a ``{name: str(value)}`` mapping,
    normalising both the ``- KEY=VALUE`` list form and the ``KEY: VALUE``
    mapping form."""
    env = service.get("environment")
    if env is None:
        return {}
    if isinstance(env, dict):
        return {str(key): str(value) for key, value in env.items()}
    mapping = {}
    for item in env:
        item = str(item)
        if "=" in item:
            key, _, value = item.partition("=")
            mapping[key] = value
    return mapping


def _volume_entries(service):
    """The service volumes as ``{"source", "target", "read_only", "type"}``
    dicts, normalising both the long syntax and the short ``a:b[:ro]``
    string form."""
    entries = []
    for entry in service.get("volumes") or []:
        if isinstance(entry, dict):
            entries.append(
                {
                    "source": entry.get("source"),
                    "target": entry.get("target"),
                    "read_only": bool(entry.get("read_only")),
                    "type": entry.get("type", "bind"),
                }
            )
        else:
            parts = str(entry).split(":")
            if len(parts) >= 2:
                source, target = parts[0], parts[1]
                read_only = len(parts) >= 3 and parts[2] in ("ro", "read-only")
                entries.append(
                    {"source": source, "target": target, "read_only": read_only, "type": "bind"}
                )
    return entries


# ---------------------------------------------------------------------------
# Pin 1 — docker/Dockerfile.crewspike
# ---------------------------------------------------------------------------


class CrewSpikeDockerfileCase(unittest.TestCase):
    """Shared access to the spike Dockerfile text, guarded so a missing file
    reports itself instead of leaking a bare ``FileNotFoundError``."""

    @property
    def text(self):
        if not CREWSPIKE_DOCKERFILE_PATH.is_file():
            self.fail("docker/Dockerfile.crewspike does not exist")
        return CREWSPIKE_DOCKERFILE_PATH.read_text(encoding="utf-8")


class TestCrewSpikeDockerfileContent(CrewSpikeDockerfileCase):
    """The instructions the spike image must carry."""

    def test_dockerfile_crewspike_from_matches_bakeoff_base(self):
        text = self.text

        self.assertIn(
            "FROM " + BASE_IMAGE,
            text,
            "expected 'FROM %s' (the same base as the bake-off image); the "
            "FROM lines found: %r"
            % (BASE_IMAGE, _instruction_lines(text, "FROM")),
        )

    def test_dockerfile_crewspike_apt_set_identical_to_bakeoff(self):
        if not BAKEOFF_DOCKERFILE.is_file():
            self.fail("docker/Dockerfile.bakeoff does not exist (the model for the apt-set pin)")
        text = self.text

        spike = _apt_package_set(text)
        bakeoff = _apt_package_set(BAKEOFF_DOCKERFILE.read_text(encoding="utf-8"))
        self.assertTrue(spike, "no apt-get install command found in the spike image")
        self.assertEqual(
            spike,
            bakeoff,
            "the spike image's apt package set must be identical to the "
            "bake-off image's (%r); spike: %r, bakeoff: %r"
            % (sorted(bakeoff), sorted(spike), sorted(bakeoff)),
        )

    def test_dockerfile_crewspike_npm_line_is_single_and_ignores_scripts(self):
        npm_lines = _npm_install_lines(self.text)

        self.assertEqual(
            len(npm_lines),
            1,
            "exactly one npm install line is expected; got: %r" % npm_lines,
        )
        self.assertIn(
            NPM_INSTALL,
            npm_lines[0],
            "the npm install line must be '%s'; got: %r" % (NPM_INSTALL, npm_lines[0]),
        )

    def test_dockerfile_crewspike_npm_line_pins_pi_coding_agent_exactly(self):
        npm_lines = _npm_install_lines(self.text)

        self.assertIn(
            PI_AGENT_PIN,
            " ".join(npm_lines),
            "npm install must carry the exact pin %s; got: %r" % (PI_AGENT_PIN, npm_lines),
        )

    def test_dockerfile_crewspike_npm_line_pins_pi_crew_exactly(self):
        npm_lines = _npm_install_lines(self.text)

        self.assertIn(
            CREW_PIN,
            " ".join(npm_lines),
            "npm install must carry the exact pin %s; got: %r" % (CREW_PIN, npm_lines),
        )

    def test_dockerfile_crewspike_pins_are_exact_not_ranges_or_bare_names(self):
        text = self.text

        for package, version in (
            ("@earendil-works/pi-coding-agent", "1.3.0"),
            ("pi-crew", "0.11.57"),
        ):
            bare = re.findall(r"(?<![\w@-])" + re.escape(package) + r"(?!@)", text)
            self.assertEqual(
                bare,
                [],
                "%s appears without its exact version pin %s: %r"
                % (package, version, bare),
            )
            for match in re.finditer(re.escape(package) + r"@", text):
                suffix = text[match.end():]
                self.assertRegex(
                    suffix,
                    r"^%s(?![0-9A-Za-z._-])" % re.escape(version),
                    "%s must be pinned to exactly %s, found: %r"
                    % (package, version, suffix.split()[:2]),
                )

    def test_dockerfile_crewspike_instructions_appear_in_build_order(self):
        text = self.text
        lines = text.splitlines()

        def first_index(predicate):
            for index, line in enumerate(lines):
                if predicate(line.strip()):
                    return index
            return None

        from_idx = first_index(lambda l: l.upper().startswith("FROM "))
        npm_idx = first_index(lambda l: re.search(r"\bnpm\s+install\b", l))
        copy_idx = first_index(
            lambda l: l.upper().startswith("COPY") and "anvilkit/" in l
        )
        user_idx = first_index(lambda l: l.upper().startswith("USER "))
        workdir_idx = first_index(lambda l: l.upper().startswith("WORKDIR"))

        self.assertIsNotNone(from_idx, "no FROM instruction found")
        self.assertIsNotNone(npm_idx, "no npm install line found")
        self.assertIsNotNone(
            copy_idx, "no COPY line carrying anvilkit/ found"
        )
        self.assertIsNotNone(user_idx, "no USER instruction found")
        self.assertIsNotNone(workdir_idx, "no WORKDIR instruction found")
        self.assertLess(
            from_idx,
            npm_idx,
            "the npm install must come after FROM (got from=%r, npm=%r)"
            % (from_idx, npm_idx),
        )
        self.assertLess(
            npm_idx,
            copy_idx,
            "the anvilkit/ copy must come after the npm install (got npm=%r, "
            "copy=%r)" % (npm_idx, copy_idx),
        )
        self.assertLess(
            copy_idx,
            user_idx,
            "anvilkit/ must be copied before the user switch, or chowned on "
            "copy (got copy=%r, user=%r)" % (copy_idx, user_idx),
        )
        self.assertLess(
            user_idx,
            workdir_idx,
            "the user switch must precede the final WORKDIR (got user=%r, "
            "workdir=%r)" % (user_idx, workdir_idx),
        )

    def test_dockerfile_crewspike_runs_a_non_root_user(self):
        text = self.text

        user = _user_from_instructions(text)
        self.assertIsNotNone(
            user, "no USER instruction found; the image must run as non-root"
        )
        self.assertNotIn(
            user.lower(),
            ("", "root"),
            "the spike image must run as a non-root user, got USER %r" % user,
        )

    def test_dockerfile_crewspike_creates_user_like_bakeoff(self):
        text = self.text

        user = _user_from_instructions(text)
        self.assertIsNotNone(user, "no USER instruction found")
        run_lines = _instruction_lines(text, "RUN")
        creating = [line for line in run_lines if re.search(r"\buseradd\b|\busermod\b", line)]
        self.assertTrue(
            creating,
            "no RUN instruction creates the container user %r (the bake-off "
            "image's approach is a useradd line); RUN lines: %r"
            % (user, run_lines),
        )

    def test_dockerfile_crewspike_agent_home_created_and_chowned_to_user(self):
        text = self.text

        user = _user_from_instructions(text)
        self.assertIsNotNone(user, "no USER instruction found")
        agent_dir = "/home/%s/.pi/agent" % user

        run_lines = _instruction_lines(text, "RUN")
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
            "lands root-owned; got RUN lines: %r" % (agent_dir, run_lines),
        )
        chowning = [
            line for line in creating if re.search(r"\bchown\b", line) and user in line
        ]
        self.assertTrue(
            chowning,
            "no RUN instruction chowns %s to the container user %r; the "
            "copy-up must transfer the directory with the container user's "
            "ownership (created lines: %r)" % (agent_dir, user, creating),
        )

    def test_dockerfile_crewspike_workdir_is_workspace(self):
        workdir_lines = _instruction_lines(self.text, "WORKDIR")

        self.assertTrue(
            any(
                re.match(r"^WORKDIR\s+/workspace(\s|$)", line, re.IGNORECASE)
                for line in workdir_lines
            ),
            "expected 'WORKDIR /workspace' (the fixture cwd convention); "
            "got: %r" % workdir_lines,
        )


class TestCrewSpikeDockerfileSafety(CrewSpikeDockerfileCase):
    """The safety properties the spike image must hold by absence."""

    def test_dockerfile_crewspike_env_lines_have_no_credential_keys(self):
        env_lines = _instruction_lines(self.text, "ENV")
        offending = [line for line in env_lines if _env_key_is_credential_like(line)]

        self.assertEqual(
            offending,
            [],
            "no ENV line may carry a key containing TOKEN, KEY or SECRET: %r"
            % offending,
        )

    def test_dockerfile_crewspike_does_not_reference_host_pi_agent_home(self):
        self.assertNotIn(
            "~/.pi/agent",
            self.text,
            "the spike image must not reference the host agent home "
            "~/.pi/agent (it carries credentials and sessions)",
        )

    def test_dockerfile_crewspike_does_not_reference_docker_socket(self):
        self.assertNotIn(
            "docker.sock",
            self.text,
            "the spike image must not reference the docker socket",
        )


# ---------------------------------------------------------------------------
# Pin 2 — docker-compose.yml: the pi-crewspike service
# ---------------------------------------------------------------------------


class ComposeCase(unittest.TestCase):
    """Shared access to the committed docker-compose.yml as parsed data,
    with the spike service extracted or reported missing."""

    @property
    def compose(self):
        try:
            return yamlio.load(COMPOSE_FILE)
        except yamlio.YamlError as exc:
            self.fail("docker-compose.yml could not be loaded: %s" % exc)

    @property
    def crewspike_service(self):
        services = _services(self.compose)
        if CREWSPIKE_SERVICE not in services:
            self.fail(
                "docker-compose.yml has no %s service (services present: %r)"
                % (CREWSPIKE_SERVICE, sorted(services))
            )
        return services[CREWSPIKE_SERVICE]


class TestComposeCrewSpikeService(ComposeCase):
    """The fields the new service must carry."""

    def test_compose_pi_crewspike_service_is_present(self):
        self.assertIn(CREWSPIKE_SERVICE, _services(self.compose))

    def test_compose_pi_crewspike_profile_is_crewspike(self):
        service = self.crewspike_service

        self.assertEqual(
            service.get("profiles"),
            [SPIKE_PROFILE],
            "the pi-crewspike service must sit in profile %r "
            "(matching the file's existing list style); got: %r"
            % (SPIKE_PROFILE, service.get("profiles")),
        )

    def test_compose_pi_crewspike_builds_the_crewspike_dockerfile(self):
        service = self.crewspike_service
        build = service.get("build")

        self.assertIsInstance(
            build,
            dict,
            "the pi-crewspike service must carry a build block (the "
            "pi-bakeoff service's style); got: %r" % build,
        )
        self.assertEqual(
            build.get("dockerfile"),
            CREWSPIKE_DOCKERFILE,
            "the build block must point at %s; got: %r"
            % (CREWSPIKE_DOCKERFILE, build.get("dockerfile")),
        )
        self.assertEqual(
            build.get("context"),
            ".",
            "the build context must be the repo root (the pi-bakeoff "
            "service's style); got: %r" % build.get("context"),
        )

    def test_compose_pi_crewspike_command_drives_the_picrew_module(self):
        service = self.crewspike_service

        self.assertEqual(
            service.get("command"),
            CREWSPIKE_COMMAND,
            "the pi-crewspike service must command %r (the file's argv "
            "list style); got: %r" % (CREWSPIKE_COMMAND, service.get("command")),
        )

    def test_compose_pi_crewspike_env_points_at_gateway_with_broker_off(self):
        env = _env_mapping(self.crewspike_service)

        for key, value in CREWSPIKE_ENV.items():
            self.assertEqual(
                env.get(key),
                value,
                "the pi-crewspike service must set %s=%r; environment: %r"
                % (key, value, env),
            )

    def test_compose_pi_crewspike_mounts_config_read_only(self):
        entries = _volume_entries(self.crewspike_service)
        config = [e for e in entries if e["source"] in ("./config.yaml", "config.yaml")]

        self.assertTrue(
            config,
            "the pi-crewspike service must bind-mount ./config.yaml; "
            "volumes: %r" % entries,
        )
        self.assertTrue(
            all(e["read_only"] for e in config),
            "the ./config.yaml mount must be read-only (the existing "
            "services' -ro form); volumes: %r" % entries,
        )

    def test_compose_pi_crewspike_mounts_results_bind(self):
        entries = _volume_entries(self.crewspike_service)
        results = [e for e in entries if e["source"] in ("./results", "results")]

        self.assertTrue(
            results,
            "the pi-crewspike service must bind-mount ./results; volumes: %r"
            % entries,
        )

    def test_compose_pi_crewspike_volume_target_matches_dockerfile_agent_home(self):
        if not CREWSPIKE_DOCKERFILE_PATH.is_file():
            self.fail(
                "docker/Dockerfile.crewspike does not exist (needed to learn "
                "the agent home the named volume must target)"
            )
        dockerfile = CREWSPIKE_DOCKERFILE_PATH.read_text(encoding="utf-8")
        match = re.search(r"/(?:home/[^/\s]+|root)/\.pi/agent", dockerfile)
        if match is None:
            self.fail(
                "docker/Dockerfile.crewspike carries no container agent home "
                "path like /home/<user>/.pi/agent to match the volume target against"
            )
        agent_home = match.group(0)

        entries = _volume_entries(self.crewspike_service)
        named = [
            e
            for e in entries
            if e["type"] == "volume" and not str(e["source"]).startswith((".", "/"))
        ]
        self.assertTrue(
            named,
            "the pi-crewspike service must carry a named (type: volume) "
            "mount; volumes: %r" % entries,
        )
        self.assertTrue(
            any(e["target"] == agent_home for e in named),
            "the named volume must target the agent home the Dockerfile "
            "creates and chowns (%s); named volume targets: %r"
            % (agent_home, [e["target"] for e in named]),
        )


class TestComposeExistingServicesUnchanged(ComposeCase):
    """The guarantee that the appended service is the only change."""

    def test_compose_preexisting_service_names_still_present(self):
        services = _services(self.compose)
        missing = [name for name in EXISTING_SERVICES if name not in services]

        self.assertEqual(
            missing,
            [],
            "pre-existing services must survive unchanged; missing: %r "
            "(present: %r)" % (missing, sorted(services)),
        )

    def test_compose_preexisting_services_gain_no_crewspike_profile(self):
        services = _services(self.compose)
        profiled = [
            name
            for name in EXISTING_SERVICES
            if name in services and SPIKE_PROFILE in (services[name].get("profiles") or [])
        ]

        self.assertEqual(
            profiled,
            [],
            "no pre-existing service may gain the %r profile: %r"
            % (SPIKE_PROFILE, profiled),
        )


# ---------------------------------------------------------------------------
# Pin 3 — the saved postinstall page and its recorded verdict
# ---------------------------------------------------------------------------


class TestPostinstallPageVerdict(unittest.TestCase):
    """The saved source page exists with its URL, and the recommendation
    names the verdict for it."""

    def test_postinstall_page_header_names_the_source_url(self):
        if not POSTINSTALL_DOC.is_file():
            self.fail("doc/external/pi-crew/postinstall-mjs.md does not exist")
        head = "\n".join(
            POSTINSTALL_DOC.read_text(encoding="utf-8").splitlines()[:10]
        )

        self.assertIn(
            "https://github.com/baphuongna/pi-crew",
            head,
            "the first lines of doc/external/pi-crew/postinstall-mjs.md must "
            "carry the source URL (github.com/baphuongna/pi-crew); head: %r"
            % head,
        )

    def test_recommendation_postinstall_section_names_the_ignore_scripts_verdict(self):
        if not RECOMMENDATION.is_file():
            self.fail("doc/pi-crew-spike/recommendation.md does not exist")
        text = RECOMMENDATION.read_text(encoding="utf-8")
        sections = _markdown_sections(text)
        postinstall = [
            s
            for s in sections
            if re.search(r"postinstall|ignore-scripts", s["heading"], re.IGNORECASE)
        ]

        self.assertTrue(
            postinstall,
            "doc/pi-crew-spike/recommendation.md must have a section heading "
            "naming the postinstall / --ignore-scripts decision; headings: %r"
            % [s["heading"] for s in sections],
        )
        body = "\n".join(s["body"] for s in postinstall)
        self.assertIn(
            "--ignore-scripts",
            body,
            "the postinstall section must name the literal flag "
            "--ignore-scripts in its verdict; body: %r" % body[:400],
        )
        self.assertTrue(
            re.search(r"\bkeep\b", body, re.IGNORECASE)
            or re.search(r"retained", body, re.IGNORECASE),
            "the postinstall verdict must state that the flag is kept "
            "(the word 'keep' or 'retained'); body: %r" % body[:400],
        )


# ---------------------------------------------------------------------------
# Pin 4 — doc/pi-crew-spike/README.md
# ---------------------------------------------------------------------------


class SpikeReadmeCase(unittest.TestCase):
    """Shared access to the spike README text, guarded so a missing file
    reports itself instead of leaking a bare ``FileNotFoundError``."""

    @property
    def text(self):
        if not SPIKE_README.is_file():
            self.fail("doc/pi-crew-spike/README.md does not exist")
        return SPIKE_README.read_text(encoding="utf-8")


class TestSpikeReadmeContent(SpikeReadmeCase):
    """The load-bearing reproduce facts ``doc/pi-crew-spike/README.md`` must
    state: the recipe as literal lines and the artifact layout."""

    def test_readme_pins_the_coder_up_command_as_a_literal_line(self):
        command = REPRODUCE_COMMANDS[0]
        lines = [line.strip() for line in self.text.splitlines()]

        self.assertIn(
            command,
            lines,
            "the reproduce recipe must carry the literal line %r; "
            "lines: %r" % (command, lines[:30]),
        )

    def test_readme_pins_the_results_setup_command_as_a_literal_line(self):
        command = REPRODUCE_COMMANDS[1]
        lines = [line.strip() for line in self.text.splitlines()]

        self.assertIn(
            command,
            lines,
            "the reproduce recipe must carry the literal line %r; "
            "lines: %r" % (command, lines[:30]),
        )

    def test_readme_pins_the_crewspike_run_command_as_a_literal_line(self):
        command = REPRODUCE_COMMANDS[2]
        lines = [line.strip() for line in self.text.splitlines()]

        self.assertIn(
            command,
            lines,
            "the reproduce recipe must carry the literal line %r; "
            "lines: %r" % (command, lines[:30]),
        )

    def test_readme_names_the_artifact_layout_under_results(self):
        text = self.text
        missing = [name for name in ARTIFACT_NAMES if name not in text]

        self.assertEqual(
            missing,
            [],
            "the artifact layout section must name %r under ./results/; "
            "missing: %r" % (ARTIFACT_NAMES, missing),
        )

    def test_readme_has_no_todo_or_pending_run_placeholder(self):
        text = self.text

        self.assertNotIn(
            "TODO",
            text.upper(),
            "the README is complete: the recipe is runnable today, so no "
            "TODO placeholder is allowed",
        )
        self.assertNotIn(
            "pending run",
            text.lower(),
            "the README is complete: the recipe is runnable today, so no "
            "'pending run' placeholder is allowed",
        )


# ---------------------------------------------------------------------------
# Pin 5 — doc/pi-crew-spike/recommendation.md
# ---------------------------------------------------------------------------


class RecommendationCase(unittest.TestCase):
    """Shared access to the recommendation page text, guarded so a missing
    file reports itself instead of leaking a bare ``FileNotFoundError``."""

    @property
    def text(self):
        if not RECOMMENDATION.is_file():
            self.fail("doc/pi-crew-spike/recommendation.md does not exist")
        return RECOMMENDATION.read_text(encoding="utf-8")

    def _sections_for(self, pattern):
        sections = _markdown_sections(self.text)
        return [s for s in sections if re.search(pattern, s["heading"], re.IGNORECASE)]


class TestRecommendationUnknowns(RecommendationCase):
    """One section per unknown, with the right content in each."""

    def test_recommendation_has_a_heading_for_the_headless_team_load(self):
        matching = self._sections_for(r"team.*?(headless|load)|(headless|load).*?team")
        headings = [s["heading"] for s in _markdown_sections(self.text)]

        self.assertTrue(
            matching,
            "doc/pi-crew-spike/recommendation.md must have a heading naming "
            "the headless 'team' tool load unknown; headings: %r" % headings,
        )

    def test_recommendation_has_a_heading_for_the_postinstall_decision(self):
        matching = self._sections_for(r"postinstall|ignore-scripts")
        headings = [s["heading"] for s in _markdown_sections(self.text)]

        self.assertTrue(
            matching,
            "doc/pi-crew-spike/recommendation.md must have a heading naming "
            "the postinstall / --ignore-scripts decision; headings: %r" % headings,
        )

    def test_recommendation_has_a_heading_for_the_record_shape(self):
        matching = self._sections_for(r"record")
        headings = [s["heading"] for s in _markdown_sections(self.text)]

        self.assertTrue(
            matching,
            "doc/pi-crew-spike/recommendation.md must have a heading naming "
            "the per-run record shape unknown; headings: %r" % headings,
        )

    def test_recommendation_headless_team_section_carries_the_recorded_go_verdict(self):
        sections = self._sections_for(r"team.*?(headless|load)|(headless|load).*?team")
        self.assertTrue(sections, "no headless 'team' tool load section found")
        body = "\n".join(s["body"] for s in sections)

        self.assertIn(
            "**GO**",
            body,
            "the headless 'team' section must carry the recorded **GO** "
            "verdict (the recorded run shows the tool loaded and ran); "
            "body: %r" % body[:400],
        )
        self.assertNotIn(
            "NO-GO",
            body,
            "the headless 'team' verdict is the recorded GO; a NO-GO "
            "verdict must not appear in the same section; body: %r"
            % body[:400],
        )
        self.assertNotIn(
            RECORDED_RUN_MARKER,
            body,
            "the recorded-run marker line is retired once the verdict "
            "lands; the headless 'team' section must not still carry %r; "
            "body: %r" % (RECORDED_RUN_MARKER, body[:400]),
        )
        self.assertIn(
            "fast-fix",
            body,
            "the GO verdict must name the 3-task fast-fix workflow the "
            "crew ran; body: %r" % body[:400],
        )
        for task in ("01_explore", "02_execute", "03_verify"):
            self.assertIn(
                task,
                body,
                "the GO verdict must name the three fast-fix tasks that "
                "completed; %r is missing; body: %r" % (task, body[:400]),
            )
        self.assertTrue(
            re.search(r"delegat", body, re.IGNORECASE),
            "the GO verdict must state that the top-level model delegated "
            "to the team tool (its only executed tools were team actions "
            "run and summary, no direct read/edit); body: %r" % body[:400],
        )
        self.assertIn(
            "summary",
            body,
            "the GO verdict must name the team actions executed (run and "
            "summary); 'summary' is missing; body: %r" % body[:400],
        )
        self.assertIn(
            ".crew/",
            body,
            "the GO verdict must name the live .crew/ state tree the crew "
            "wrote; body: %r" % body[:400],
        )
        self.assertTrue(
            re.search(r"llamaswap", body, re.IGNORECASE),
            "the GO verdict must note that model routing hit the local "
            "gateway (the llamaswap coder model); body: %r" % body[:400],
        )

    def test_recommendation_record_section_carries_the_recorded_verdict(self):
        sections = self._sections_for(r"record")
        self.assertTrue(sections, "no per-run record section found")
        body = "\n".join(s["body"] for s in sections)

        self.assertIn(
            "**GO**",
            body,
            "the per-run record section must carry the recorded **GO** "
            "verdict; body: %r" % body[:400],
        )
        self.assertNotIn(
            "NO-GO",
            body,
            "the per-run record verdict is the recorded GO; a NO-GO "
            "verdict must not appear in the same section; body: %r"
            % body[:400],
        )
        self.assertNotIn(
            RECORDED_RUN_MARKER,
            body,
            "the recorded-run marker line is retired once the verdict "
            "lands; the per-run record section must not still carry %r; "
            "body: %r" % (RECORDED_RUN_MARKER, body[:400]),
        )
        for key in (
            "runId",
            "durationMs",
            "totalCost",
            "timestamp",
            "taskCount",
            "completedCount",
            "failedCount",
            "consistencyScore",
        ):
            self.assertIn(
                key,
                body,
                "the recorded verdict must name the metrics key %r from the "
                "team tool result's details.metrics; body: %r"
                % (key, body[:400]),
            )
        self.assertIn(
            ".crew/state/metrics/",
            body,
            "the recorded verdict must name the metrics JSONL location "
            ".crew/state/metrics/; body: %r" % body[:400],
        )
        self.assertIn(
            ".crew/state/runs/",
            body,
            "the recorded verdict must name .crew/state/runs/ (empty in "
            "the recorded run, so the record is not a single flat file); "
            "body: %r" % body[:400],
        )
        self.assertTrue(
            re.search(r"event[- ]stream", body, re.IGNORECASE),
            "the recorded verdict must state that the record lives embedded "
            "in the event-stream tool result, not in a single flat file; "
            "body: %r" % body[:400],
        )
        for figure in ("33,789", "253,086", "5.7", "1.9"):
            self.assertIn(
                figure,
                body,
                "the recorded overhead finding must carry the measured "
                "figure %r (the 3-task run's tokens and ms, and the "
                "package preflight's slower/costlier multipliers); body: %r"
                % (figure, body[:400]),
            )


class TestRecommendationBackLink(RecommendationCase):
    """The page closes the loop with the intake issue."""

    def test_recommendation_links_back_to_issue_84(self):
        self.assertIn(
            BACK_LINK,
            self.text,
            "doc/pi-crew-spike/recommendation.md must end with a back-link "
            "line naming %s" % BACK_LINK,
        )


if __name__ == "__main__":
    unittest.main()
