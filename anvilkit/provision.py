"""Provisioning a target repository - the ``setup-repo`` orchestration.

Every value arrives pre-resolved in a :class:`RepoPlan`, so this module makes no
decisions about *what* to write and never prompts - that belongs to ``prompts``
and the CLI. It only performs filesystem work.

Constraints:

* templates are validated **before** anything is written, so a missing template
  cannot leave a repository half-provisioned;
* re-running refreshes ``roo_template/`` in place instead of nesting a copy
  inside the previous one;
* secrets are never echoed, only the paths they were written to.
"""

import json
import re
import shutil
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Union

from . import render
from . import yamlio

PathLike = Union[str, Path]

ROO_SUBDIRS = (".roo", ".roo/commands", ".roo/skills", ".roo/rules")
DEVCONTAINER_DIR = ".devcontainer"

_SEPARATOR = "-" * 70


class ProvisionError(Exception):
    """The target repository or the templates are unusable."""


class RepoPlan:
    """Every value needed to provision a repository, already resolved.

    Keeping resolution out of this module means ``setup_repo`` is a pure
    filesystem operation and therefore testable without any stdin at all.
    """

    def __init__(
        self,
        port: int,
        context_window: int,
        coder_model_id: str,
        embedder_model_id: Optional[str],
        local_profile_id: str,
        anthropic_profile_id: str,
        anthropic_api_key: str,
        anthropic_model_id: str,
        use_anthropic_for_frontier_modes: bool,
        github_token: str = "",
        oxylabs_username: str = "",
        oxylabs_password: str = "",
    ) -> None:
        self.port = port
        self.context_window = context_window
        self.coder_model_id = coder_model_id
        self.embedder_model_id = embedder_model_id
        self.local_profile_id = local_profile_id
        self.anthropic_profile_id = anthropic_profile_id
        self.anthropic_api_key = anthropic_api_key
        self.anthropic_model_id = anthropic_model_id
        self.use_anthropic_for_frontier_modes = use_anthropic_for_frontier_modes
        self.github_token = github_token
        self.oxylabs_username = oxylabs_username
        self.oxylabs_password = oxylabs_password


def setup_repo(
    target: Optional[PathLike],
    repo_plan: RepoPlan,
    templates_dir: Optional[PathLike] = None,
    dry_run: bool = False,
    echo: Optional[Callable[[str], None]] = None,
) -> str:
    """Provision ``target``, returning its resolved absolute path.

    Raises:
        ProvisionError: the target is missing, is not a directory, or a required
            template is absent. Nothing is written when validation fails.
    """
    report = echo or (lambda _message: None)

    resolved = _validate_target(target)
    templates = _Templates(templates_dir)
    templates.validate()

    report("📂 Verifying framework directory architectures...")
    _create_directories(resolved, dry_run, report)

    report("📝 Ensuring .gitignore protects sensitive files...")
    _merge_gitignore_step(resolved, templates, dry_run, report)

    report("� Deploying devcontainer configuration...")
    _copy_devcontainer(resolved, templates, dry_run, report)

    report("⚙️  Generating zoo-code-settings.json unified across a single proxy gate...")
    report("   ↳ 📐 Context window: {}".format(repo_plan.context_window))
    _write_zoo_settings(resolved, repo_plan, dry_run, report)

    report("⚙️  Processing MCP context mappings and injecting into workspace...")
    _write_mcp_settings(resolved, repo_plan, dry_run, report)

    report("💻 Verifying IDE configuration space...")
    _write_extensions(resolved, dry_run, report)

    report("🛠️  Deploying core orchestration instructions...")
    _install_rules_command(resolved, templates, dry_run, report)

    report("📦 Copying roo_template directory to repository root...")
    _copy_roo_template(resolved, templates, dry_run, report)

    report("🧩 Deploying mode definitions and rules...")
    _copy_root_roomodes(resolved, templates, dry_run, report)
    _deploy_mode_rules(resolved, templates, dry_run, report)

    _report_completion(resolved, report)

    return str(resolved)


class _Templates:
    """Locates the template files and verifies they all exist up front."""

    def __init__(self, templates_dir: Optional[PathLike] = None) -> None:
        base = Path(templates_dir) if templates_dir else _default_templates_dir()
        self.base = base
        self.zoo = base / "zoo-code-settings.json.template"
        self.mcp = base / "mcp.json.template"
        self.extensions = base / "extensions.json.template"
        self.rules_command = base / "update_roo_rules.md"
        self.gitignore = base / ".gitignore.template"
        self.roo_template = base / "roo_template"
        self.devcontainer = base / "devcontainer"

    def validate(self) -> None:
        """Check every template before any file is written.

        Fail-fast ordering is deliberate, so a half-provisioned repository is
        impossible.
        """
        required_files = (
            ("Core settings template", self.zoo),
            ("MCP context template file", self.mcp),
            ("Extensions template file", self.extensions),
            ("Roo rules command file", self.rules_command),
            ("Gitignore template", self.gitignore),
        )

        for description, path in required_files:
            if not path.is_file():
                raise ProvisionError(
                    "{} not found at '{}'.".format(description, path)
                )

        if not self.roo_template.is_dir():
            raise ProvisionError(
                "Roo template directory not found at '{}'.".format(
                    self.roo_template
                )
            )

        if not self.devcontainer.is_dir():
            raise ProvisionError(
                "Devcontainer template directory not found at '{}'.".format(
                    self.devcontainer
                )
            )


def _default_templates_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "templates"


def _validate_target(target: Optional[PathLike]) -> Path:
    """Resolve and check the target directory, preserving anvil:284-293."""
    if target is None or str(target).strip() == "":
        raise ProvisionError(
            "Please provide the target repository directory path.\n"
            "Usage: ./anvil setup-repo /path/to/your/repo"
        )

    path = Path(target)

    if not path.exists():
        raise ProvisionError(
            "Target directory '{}' does not exist.".format(path)
        )

    if not path.is_dir():
        raise ProvisionError(
            "Target '{}' is not a directory.".format(path)
        )

    # Resolve natively to prevent relative-path leakage into generated files.
    return path.resolve()


def _create_directories(target: Path, dry_run: bool, report) -> None:
    for relative in ROO_SUBDIRS:
        directory = target / relative
        if directory.is_dir():
            continue

        report("   ↳ 📁 Creating missing directory: {}".format(relative))
        if not dry_run:
            directory.mkdir(parents=True, exist_ok=True)

    vscode = target / ".vscode"
    if not vscode.is_dir():
        report("   ↳ 📁 Creating missing directory: .vscode")
        if not dry_run:
            vscode.mkdir(parents=True, exist_ok=True)


# Canonical entries matching templates/.gitignore.template.
# These are the paths every Anvil-produced .gitignore must cover.
_GITIGNORE_ENTRIES = (
    ".env",
    "anvil.local.yaml",
    "zoo-code-settings.json",
    ".roo/mcp.json",
    ".venv/.anvil-requirements-stamp",
)


def _merge_gitignore(existing_text: str, template_text: str) -> Optional[str]:
    """Merge template entries into existing .gitignore content.

    A pure function with no filesystem access.

    Args:
        existing_text: Current .gitignore content (empty string if new).
        template_text: Content of the .gitignore.template file.

    Returns:
        The new .gitignore content string, or ``None`` if no changes are needed.
    """
    # Step 1: Parse template required entries (stripped, non-blank, non-comment).
    required_entries = []
    for line in template_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        required_entries.append(stripped)

    # Step 2: If existing text is empty (file doesn't exist or is zero bytes).
    if not existing_text:
        header = _gitignore_header()
        entries_lines = "\n".join(required_entries)
        return header + "\n" + entries_lines + "\n"

    # Step 3: Parse existing entries.
    existing_entries = set()
    for line in existing_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        existing_entries.add(stripped)

    # Step 4: Collect missing entries.
    missing = []
    for entry in required_entries:
        if entry not in existing_entries:
            missing.append(entry)

    if not missing:
        return None  # File is unchanged.

    # Step 5: Build appended content.
    header = _gitignore_header()
    body = existing_text
    if not body.endswith("\n"):
        body += "\n"
    body += "\n" + header + "\n"
    body += "\n".join(missing) + "\n"
    return body


def _merge_mcp_servers(existing_text: str, rendered_text: str, source: str = ".roo/mcp.json") -> str:
    """Merge the freshly rendered ``.roo/mcp.json`` with the one on disk.

    A pure function with no filesystem access, following the
    ``_merge_gitignore`` shape. Ownership is decided by name (plan §2.4,
    A1 option 1): a server named in the rendered text is Anvil-owned and is
    refreshed wholesale, so a rotated token or a server added by a newer
    Anvil version arrives on every run; a server present only in the
    existing file is user-owned and survives untouched, in position.
    Nothing is ever removed, and every top-level key other than
    ``mcpServers`` survives, so a hand-tuned file is re-serialised
    (plan §2.2, A5) but never loses data.

    The one exception is credentials (A2): refreshing an Anvil-owned
    server whose ``env`` mapping carries an empty value for a key the
    user has already filled in must not silently disable the server —
    an empty incoming value therefore never blanks a non-empty stored
    one, while any non-empty incoming value always wins.

    Unlike ``_merge_gitignore`` the helper always returns the merged
    text; detecting "unchanged" is the provisioning step's job, which
    compares before writing.

    Raises:
        ProvisionError: either text is not valid JSON, or the existing
            file has a structure the merge cannot reconcile (top level
            not a mapping, ``mcpServers`` present but not a mapping).
            The offending file is named via ``source`` so the pure
            function never needs to touch a real path.
    """
    if not existing_text.strip():
        # First run: the provisioning step writes the rendered text
        # wholesale, so it comes back verbatim rather than
        # re-serialised.
        return rendered_text

    try:
        existing = json.loads(existing_text)
    except json.JSONDecodeError as exc:
        raise ProvisionError(
            "Existing {} is not valid JSON: {}".format(source, exc)
        ) from exc

    if not isinstance(existing, dict):
        raise ProvisionError(
            "Existing {} must be a JSON object at the top level, got {}."
            .format(source, type(existing).__name__)
        )

    try:
        rendered = json.loads(rendered_text)
    except json.JSONDecodeError as exc:
        # Invalid rendered output is an Anvil bug, not user fault, but it
        # is ProvisionError anyway: one exception type per module keeps
        # the provisioning step's single ``except`` holding.
        raise ProvisionError(
            "Rendered MCP settings for {} are not valid JSON: {}".format(
                source, exc
            )
        ) from exc

    if not isinstance(rendered, dict):
        raise ProvisionError(
            "Rendered MCP settings must be a JSON object at the top "
            "level, got {}.".format(type(rendered).__name__)
        )

    existing_servers = existing.get("mcpServers")
    if existing_servers is None:
        # An existing file with no mcpServers key gets it created; every
        # server then lands as an append, which is exactly what the loop
        # below does with an empty start.
        existing_servers = {}

    if not isinstance(existing_servers, dict):
        raise ProvisionError(
            "Existing {} has an 'mcpServers' entry that is not a JSON "
            "object.".format(source)
        )

    rendered_servers = rendered.get("mcpServers")
    if rendered_servers is None:
        rendered_servers = {}

    if not isinstance(rendered_servers, dict):
        raise ProvisionError(
            "Rendered MCP settings have an 'mcpServers' entry that is "
            "not a JSON object; Anvil's template has drifted."
        )

    merged_servers = {}
    for name, existing_entry in existing_servers.items():
        rendered_entry = rendered_servers.get(name)
        if rendered_entry is None:
            # User-owned: kept untouched, in its existing position.
            merged_servers[name] = existing_entry
            continue
        if not isinstance(rendered_entry, dict):
            raise ProvisionError(
                "Rendered MCP server '{}' is not a JSON object; Anvil's "
                "template has drifted.".format(name)
            )
        if not isinstance(existing_entry, dict):
            # Cannot be refreshed field by field, so it is replaced
            # wholesale; the A2 exception has nothing to apply to.
            merged_servers[name] = rendered_entry
            continue
        # Anvil-owned: refreshed wholesale, with the A2 exception for
        # stored credentials that would be blanked.
        merged_entry = dict(rendered_entry)
        incoming_env = rendered_entry.get("env")
        stored_env = existing_entry.get("env")
        if isinstance(incoming_env, dict) and isinstance(stored_env, dict):
            merged_env = dict(incoming_env)
            for key, incoming_value in incoming_env.items():
                stored_value = stored_env.get(key)
                if incoming_value == "" and stored_value not in ("", None):
                    merged_env[key] = stored_value
            merged_entry["env"] = merged_env
        merged_servers[name] = merged_entry

    for name, rendered_entry in rendered_servers.items():
        if name not in merged_servers:
            # A server this Anvil version owns but the repo predates:
            # appended after every existing entry, in rendered order.
            merged_servers[name] = rendered_entry

    merged = dict(existing)
    merged["mcpServers"] = merged_servers
    return json.dumps(merged, indent=4)


def _merge_extensions(
    existing_text: str, rendered_text: str, source: str = ".vscode/extensions.json"
) -> str:
    """Merge the freshly rendered ``.vscode/extensions.json`` with the one on disk.

    A pure function with no filesystem access, following the
    ``_merge_mcp_servers`` shape and its always-returns-merged-text
    convention: detecting "unchanged" belongs to the provisioning step,
    which compares before writing.

    ``recommendations`` is the only key Anvil claims: existing entries keep
    their order and value, and a rendered recommendation missing from the
    existing list is appended after them. Everything else in the file
    (``unwantedRecommendations`` and any future VS Code key) survives
    in place, so a hand-tuned file is re-serialised but never loses data
    and never reorders the developer's own keys.

    Raises:
        ProvisionError: either text is not valid JSON, the existing file
            has a structure the merge cannot reconcile (top level not a
            mapping, or ``recommendations`` present but not a list of
            strings), or the rendered output has drifted (its
            ``recommendations`` is not a list). The offending file is
            named via ``source`` so the pure function never needs to
            touch a real path.
    """
    if not existing_text.strip():
        # First run: the provisioning step writes the rendered text
        # wholesale, so it comes back verbatim rather than
        # re-serialised.
        return rendered_text

    try:
        existing = json.loads(existing_text)
    except json.JSONDecodeError as exc:
        raise ProvisionError(
            "Existing {} is not valid JSON: {}".format(source, exc)
        ) from exc

    if not isinstance(existing, dict):
        raise ProvisionError(
            "Existing {} must be a JSON object at the top level, got {}."
            .format(source, type(existing).__name__)
        )

    try:
        rendered = json.loads(rendered_text)
    except json.JSONDecodeError as exc:
        # Invalid rendered output is an Anvil bug, not user fault, but it
        # is ProvisionError anyway: one exception type per module keeps
        # the provisioning step's single ``except`` holding.
        raise ProvisionError(
            "Rendered extension settings for {} are not valid JSON: {}".format(
                source, exc
            )
        ) from exc

    if not isinstance(rendered, dict):
        raise ProvisionError(
            "Rendered extension settings must be a JSON object at the "
            "top level, got {}.".format(type(rendered).__name__)
        )

    existing_recs = existing.get("recommendations")
    if existing_recs is not None:
        if not isinstance(existing_recs, list) or not all(
            isinstance(entry, str) for entry in existing_recs
        ):
            raise ProvisionError(
                "Existing {} has a 'recommendations' entry that is not "
                "a list of strings.".format(source)
            )
    else:
        existing_recs = []

    rendered_recs = rendered.get("recommendations")
    if rendered_recs is None:
        rendered_recs = []
    if not isinstance(rendered_recs, list):
        raise ProvisionError(
            "Rendered extension settings have a 'recommendations' entry "
            "that is not a list; Anvil's template has drifted."
        )

    merged_recs = list(existing_recs)
    for entry in rendered_recs:
        if entry not in merged_recs:
            # A recommendation this Anvil version owns but the repo
            # predates: appended after every existing entry, in rendered
            # order.
            merged_recs.append(entry)

    merged = dict(existing)
    merged["recommendations"] = merged_recs
    return json.dumps(merged, indent=4)


_ROOMODES_KEY_RE = re.compile(r"^( *)customModes:\s*$")
_ROOMODES_ITEM_RE = re.compile(r"^( *)- ")
_ROOMODES_SLUG_RE = re.compile(r"^( *)- slug:\s*(\S+)")


def _merge_roomodes(
    existing_text: str, template_text: str, source: str = ".roomodes"
) -> Optional[str]:
    """Merge the template's mode blocks into an existing ``.roomodes``.

    A pure function with no filesystem access, mirroring the
    ``_merge_gitignore`` shape and its ``None``-means-unchanged convention:
    the provisioning step writes nothing when ``None`` is returned.

    The decision is made with the parser, the emission as text. The slugs
    already present are discovered by parsing ``existing_text`` with
    ``yamlio.loads()`` — a textual scan is unsafe because ``slug:`` can
    legally appear inside a ``>-`` folded scalar — while the appended
    content is the template's own lines verbatim. A YAML round-trip is
    deliberately avoided: it would reflow the ``>-`` scalars and nested
    ``groups`` lists in a file developers hand-edit, and every existing
    byte must remain an exact prefix of the result.

    Args:
        existing_text: Current ``.roomodes`` content (empty if new).
        template_text: Content of the template ``.roomodes`` file.
        source: Name of the existing file, named in error messages.

    Returns:
        The merged content, or ``None`` when every template slug is already
        present. Empty or whitespace-only ``existing_text`` yields the
        template text verbatim, byte-for-byte.

    Raises:
        ProvisionError: the existing text is not a valid YAML mapping
            (naming ``source``), or the template has drifted (no
            ``customModes:`` key, or a block with no parseable slug).
    """
    if not existing_text.strip():
        # First run: nothing to preserve, so the merge is the identity on
        # the template — not even a trailing-newline normalisation.
        return template_text

    try:
        # yamlio.loads also raises YamlError when the top level is not a
        # mapping, so one except covers both error families of the
        # existing file.
        existing = yamlio.loads(existing_text)
    except yamlio.YamlError as exc:
        raise ProvisionError(
            "Existing {} is not a valid YAML mapping: {}".format(source, exc)
        ) from exc

    key_indent, blocks = _roomodes_template_blocks(template_text, source)

    present = set()
    custom_modes = existing.get("customModes")
    if isinstance(custom_modes, list):
        for entry in custom_modes:
            if isinstance(entry, dict):
                slug = entry.get("slug")
                if isinstance(slug, str) and slug.strip():
                    present.add(slug)

    missing = [text for slug, text in blocks if slug not in present]
    if not missing:
        return None

    body = existing_text
    if not body.endswith("\n"):
        # Insert one newline so no appended line is glued onto the last
        # existing line.
        body += "\n"
    if "customModes" not in existing:
        # The key itself is missing, so it is created at the template's
        # top-level key indentation; when the key is present (even null)
        # the blocks simply land under it and no second key line is
        # emitted.
        body += "{}customModes:\n".format(key_indent)
    for block in missing:
        body += block
    return body


def _roomodes_template_blocks(
    template_text: str, source: str
) -> Tuple[str, List[Tuple[str, str]]]:
    """Split template text into per-mode blocks, verbatim.

    Returns ``(key_indent, blocks)`` where each block is a
    ``(slug, block_text)`` pair and ``block_text`` is the template's own
    lines from its ``- slug:`` line to the next item at the same
    indentation, or end of text.

    The item indentation is taken from the FIRST item found, never
    hard-coded, so a re-indented template still splits on its own
    boundaries.

    Raises:
        ProvisionError: the template has drifted — no ``customModes:``
            key, no items under it, or an item line carrying no
            parseable slug.
    """
    lines = template_text.split("\n")

    key_indent = None
    key_index = None
    for index, line in enumerate(lines):
        match = _ROOMODES_KEY_RE.match(line)
        if match:
            key_index = index
            key_indent = match.group(1)
            break

    if key_index is None:
        raise ProvisionError(
            "Template {} has drifted: no 'customModes:' key found.".format(
                source
            )
        )

    item_indent = None
    for line in lines[key_index + 1:]:
        if not line.strip():
            continue
        match = _ROOMODES_ITEM_RE.match(line)
        if match:
            item_indent = len(match.group(1))
        break

    blocks = []
    current = None  # type: Optional[Tuple[str, List[str]]]
    for line in lines[key_index + 1:]:
        if item_indent is not None and line.startswith(" " * item_indent + "- "):
            # An item line: it opens a new block, and its slug must be
            # parseable on the same line.
            match = _ROOMODES_SLUG_RE.match(line)
            if match is None:
                raise ProvisionError(
                    "Template {} has drifted: a mode block under "
                    "'customModes' has no parseable slug.".format(source)
                )
            if current is not None:
                blocks.append((current[0], "\n".join(current[1])))
            current = (match.group(2), [line])
        elif current is not None:
            # Continuation lines (deeper-indented content, blank lines
            # between blocks) belong to the open block, verbatim.
            current[1].append(line)

    if current is not None:
        blocks.append((current[0], "\n".join(current[1])))

    if not blocks:
        raise ProvisionError(
            "Template {} has drifted: 'customModes' defines no mode "
            "blocks.".format(source)
        )

    return key_indent, blocks


def _gitignore_header() -> str:
    """Return the Anvil .gitignore header comment block."""
    return (
        "# Anvil-managed entries — do not edit manually.\n"
        "# Setup-repo appends missing entries below this marker.\n"
    )


def _merge_gitignore_step(
    target: Path,
    templates: "_Templates",
    dry_run: bool,
    report,
) -> None:
    """Ensure the target .gitignore contains all required entries.

    Reads the template, merges with any existing file, and writes if changed.
    """
    # Build template content from canonical entries.
    # The actual template file is validated to exist by _Templates.validate(),
    # but the content here is deterministic and does not depend on which
    # templates_dir is passed (important for tests that use mini templates).
    header_lines = _gitignore_header().rstrip("\n")
    template_content = header_lines + "\n\n" + "\n".join(_GITIGNORE_ENTRIES) + "\n"

    gitignore_path = target / ".gitignore"

    # Check if path is a directory.
    if gitignore_path.is_dir():
        raise ProvisionError(
            "Target contains a directory named '.gitignore' at {}.".format(gitignore_path)
        )

    file_existed = gitignore_path.exists()
    existing_content = ""

    if file_existed:
        # Read existing content.
        try:
            existing_content = gitignore_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise ProvisionError(
                "Target .gitignore at {} could not be read as UTF-8.".format(
                    gitignore_path
                )
            )
        result = _merge_gitignore(existing_content, template_content)
        if result is None:
            report(
                "   ↳ ⏭️  Skipped .gitignore (already up to date)"
            )
            return
        new_content = result
    else:
        new_content = _merge_gitignore("", template_content)

    if dry_run:
        report("   ↳ ⏭️  Dry-run: would create {}".format(gitignore_path))
        return

    render.write_text(gitignore_path, new_content)

    if file_existed:
        report(
            "   ↳ ✅ Appended: {}".format(gitignore_path)
        )
    else:
        report(
            "   ↳ ✅ Created: {}".format(gitignore_path)
        )


def _write_zoo_settings(
    target: Path, repo_plan: RepoPlan, dry_run: bool, report
) -> None:
    destination = target / "zoo-code-settings.json"

    content = render.zoo_code_settings(
        port=repo_plan.port,
        context_window=repo_plan.context_window,
        coder_model_id=repo_plan.coder_model_id,
        embedder_model_id=repo_plan.embedder_model_id,
        local_profile_id=repo_plan.local_profile_id,
        anthropic_profile_id=repo_plan.anthropic_profile_id,
        anthropic_api_key=repo_plan.anthropic_api_key,
        anthropic_model_id=repo_plan.anthropic_model_id,
        use_anthropic_for_frontier_modes=repo_plan.use_anthropic_for_frontier_modes,
    )

    if repo_plan.use_anthropic_for_frontier_modes:
        report(
            "   ↳ 🧠 Architect mode: {} (Anthropic)".format(
                repo_plan.anthropic_model_id
            )
        )
        report(
            "   ↳ 🧠 Orchestrator mode: {} (Anthropic)".format(
                repo_plan.anthropic_model_id
            )
        )
    else:
        report("   ↳ 🧠 Architect mode: local llama-swap gateway")
        report("   ↳ 🧠 Orchestrator mode: local llama-swap gateway")

    _write(destination, content, dry_run, report)


def _write_mcp_settings(
    target: Path, repo_plan: RepoPlan, dry_run: bool, report
) -> None:
    mcp_path = target / ".roo" / "mcp.json"
    rendered_text = render.mcp_settings(
        workspace_folder=str(target),
        github_token=repo_plan.github_token,
        oxylabs_username=repo_plan.oxylabs_username,
        oxylabs_password=repo_plan.oxylabs_password,
    )

    file_existed = mcp_path.exists()
    existing_text = ""
    if file_existed:
        try:
            existing_text = mcp_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise ProvisionError(
                "Existing MCP settings at {} could not be read as UTF-8."
                .format(mcp_path)
            )

    # Validation happens before the dry_run check, per the
    # _merge_gitignore_step precedent: a dry run must surface the same
    # fault, so a malformed existing file is never silently clobbered.
    merged_text = _merge_mcp_servers(
        existing_text, rendered_text, source=str(mcp_path)
    )

    if not file_existed:
        # First run: the file does not exist yet, so the rendered text is
        # written wholesale rather than merged.
        if not dry_run:
            render.write_text(mcp_path, rendered_text)
        report("   ↳ ✅ Injected: {}".format(mcp_path))
        return

    if merged_text == existing_text:
        report("   ↳ ⏭️  Skipped .roo/mcp.json (already up to date)")
        return

    if dry_run:
        report("   ↳ ⏭️  Dry-run: would merge {}".format(mcp_path))
        return

    render.write_text(mcp_path, merged_text)
    report("   ↳ ✅ Merged: {}".format(mcp_path))


def _write_extensions(target: Path, dry_run: bool, report) -> None:
    _write(
        target / ".vscode" / "extensions.json",
        render.extensions_settings(),
        dry_run,
        report,
    )


def _install_rules_command(
    target: Path, templates: _Templates, dry_run: bool, report
) -> None:
    destination = target / ".roo" / "commands" / "update_roo_rules.md"

    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(templates.rules_command), str(destination))

    report("   ↳ ✅ Injected: {}".format(destination))


def _copy_roo_template(
    target: Path, templates: _Templates, dry_run: bool, report
) -> None:
    destination = target / templates.roo_template.name

    if not dry_run:
        # Replace rather than copy-into: 'cp -r src dst' nests src inside dst
        # when dst already exists.
        if destination.exists():
            shutil.rmtree(str(destination))
        shutil.copytree(str(templates.roo_template), str(destination))

    report("   ↳ ✅ Copied: {}".format(destination))


def _write(destination: Path, content: str, dry_run: bool, report) -> None:
    if not dry_run:
        render.write_text(destination, content)

    report("   ↳ ✅ Injected: {}".format(destination))


def _copy_root_roomodes(
    target: Path, templates: "_Templates", dry_run: bool, report
) -> None:
    """Deploy .roomodes from roo_template, merging instead of overwriting.

    A first run deploys the template verbatim; a re-run merges the
    template's mode blocks into the existing file via
    ``_merge_roomodes`` so a developer's hand edits survive, and writes
    nothing when the merge reports the file already up to date.
    """
    source = templates.roo_template / ".roomodes"
    destination = target / ".roomodes"

    if not source.is_file():
        report("   ↳ ⏭️  Skipped .roomodes (source not found at {})".format(source))
        return

    template_text = source.read_text(encoding="utf-8")

    if not destination.exists():
        # First run: the template text is deployed wholesale, so the
        # result stays byte-identical to the pre-merge behaviour
        # (locked by test_roomodes_content_matches_template).
        if not dry_run:
            render.write_text(destination, template_text)
        report("   ↳ ✅ Deployed: {}".format(destination))
        return

    if destination.is_dir():
        raise ProvisionError(
            "Target contains a directory named '.roomodes' at {}.".format(
                destination
            )
        )

    try:
        existing_text = destination.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ProvisionError(
            "Existing .roomodes at {} could not be read as UTF-8.".format(
                destination
            )
        )

    # A template without a 'customModes:' key defines no mode blocks, so
    # there is nothing to merge; the merge helper would classify such a
    # template as drift and fail every re-provision of a repo that was
    # already set up, which is the destructive-re-run class this step
    # exists to eliminate.
    has_mode_blocks = any(
        _ROOMODES_KEY_RE.match(line) for line in template_text.split("\n")
    )
    if not has_mode_blocks:
        report("   ↳ ⏭️  Skipped .roomodes (already up to date)")
        return

    # Validation happens before the dry_run check, per the
    # _merge_gitignore_step and _write_mcp_settings precedent: a dry run
    # must surface the same fault, so a malformed existing file is never
    # silently clobbered.
    merged_text = _merge_roomodes(
        existing_text, template_text, source=str(destination)
    )
    if merged_text is None:
        # Every template slug is already present: nothing to write, even
        # under dry_run the report is the same.
        report("   ↳ ⏭️  Skipped .roomodes (already up to date)")
        return

    if dry_run:
        report("   ↳ ⏭️  Dry-run: would merge {}".format(destination))
        return

    render.write_text(destination, merged_text)
    report("   ↳ ✅ Merged: {}".format(destination))


def _deploy_mode_rules(
    target: Path, templates: "_Templates", dry_run: bool, report
) -> None:
    """Move rules-* directories from roo_template into .roo/.

    Template layout places mode-specific rule directories inside roo_template/
    (e.g. roo_template/rules-qna-tester/, roo_template/rules-docs-manager/) so
    they travel with the scaffold.  At provision time we move them into .roo/
    where Roo-Code resolves them.
    """
    roo_root = target / ".roo"
    if not dry_run:
        roo_root.mkdir(parents=True, exist_ok=True)

    for entry in sorted(templates.roo_template.iterdir()):
        if entry.is_dir() and entry.name.startswith("rules-"):
            destination = roo_root / entry.name
            if not dry_run:
                if destination.exists():
                    shutil.rmtree(str(destination))
                shutil.copytree(str(entry), str(destination))
            report("   ↳ ✅ Deployed: {}".format(destination))


def _copy_devcontainer(
    target: Path, templates: "_Templates", dry_run: bool, report
) -> None:
    """Copy devcontainer template to the target, skipping if one exists.

    If the target already has a ``.devcontainer`` directory (file or otherwise),
    provisioning skips it silently — overwriting a developer's own container
    config would be destructive.
    """
    destination = target / DEVCONTAINER_DIR
    if destination.exists():
        report("   ⏭️  Skipped devcontainer (target already has {})".format(destination))
        return

    if not dry_run:
        shutil.copytree(str(templates.devcontainer), str(destination))

    report("   ↳ ✅ Deployed: {}".format(destination))


def _report_completion(target: Path, report) -> None:
    report("")
    report("✨ Workspace setup complete for: {}".format(target))
    report(_SEPARATOR)
    report("👉 IMPORTANT NEXT STEP:")
    report("To update the various rules of the LLM model, open your Zoo chat")
    report(
        "interface with the LLM and instruct it to execute the command "
        "/update_roo_rules.md"
    )
    report(_SEPARATOR)
