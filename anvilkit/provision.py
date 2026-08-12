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

import shutil
from pathlib import Path
from typing import Callable, Optional, Union

from . import render

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
    content = render.mcp_settings(
        workspace_folder=str(target), github_token=repo_plan.github_token
    )
    _write(target / ".roo" / "mcp.json", content, dry_run, report)


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
    """Copy .roomodes from inside roo_template to the repo root."""
    source = templates.roo_template / ".roomodes"
    destination = target / ".roomodes"

    if source.is_file():
        if not dry_run:
            render.write_text(destination, source.read_text(encoding="utf-8"))
        report("   ↳ ✅ Deployed: {}".format(destination))
    else:
        report("   ↳ ⏭️  Skipped .roomodes (source not found at {})".format(source))


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
