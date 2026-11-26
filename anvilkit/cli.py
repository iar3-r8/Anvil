"""The Anvil command line: subcommand dispatch, flags and exit codes.

Design rules for this module:

* **it decides, it does not do.** Resolving values (flags, ``.env``, YAML,
  prompts) happens here; the work happens in ``compose``, ``health``, ``stress``,
  ``provision`` and ``render``. That keeps this file readable and keeps those
  modules testable without a CLI.
* **every failure class gets its own exit code**, so a caller can react to
  whether the problem was configuration, docker, provisioning, or a missing
  interactive value.
* **nothing is written or executed under ``--dry-run``**, so parity with the
  shell version can be checked without containers.

Interactivity is decided in exactly one place, :func:`_is_interactive`, and passed
down. Together with ``--yes`` this makes Anvil scriptable.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import click
import typer

from . import (
    compose,
    config,
    credentials,
    env,
    envsetup,
    health,
    modelreport,
    prompts,
    provision,
    render,
    smoke,
    stress,
    stressreport,
)
from .cliexit import (
    EXIT_CONFIG,
    EXIT_DOCKER,
    EXIT_ERROR,
    EXIT_GUARDS_BLOCKED,
    EXIT_OK,
    EXIT_PROVISION,
    EXIT_PROMPT,
    EXIT_STRESS_FAILURES,
    EXIT_STRESS_UNAVAILABLE,
    EXIT_USAGE,
    fail,
)
from .compose import Compose, ComposeError
from .pi import pibakeoff, piguardgate
from .config import ConfigError
from .pi import (
    picodeowners,
    piguard,
    pigithub,
    pilaunch,
    pirole,
    pitokenrecipe,
    piruleset,
    piprofile,
    pirun,
    runlog,
)
from .pi import piprofileflow
from .pi.piprofile import ProfileError
from .prompts import PromptError
from .provision import ProvisionError, RepoPlan
from .render import RenderError
# Only StressError remains from-imported from the stress module: run() maps
# it to EXIT_STRESS_UNAVAILABLE. The stress functions themselves are no longer
# cli globals - the stress handler delegates its report logic to stressreport,
# which imports the stress module qualified (plans/cli-segmentation.md
# behaviour 5), so the suite patches stress.<name>, not cli.<name>.
from .stress import StressError

REPO_ROOT = Path(__file__).resolve().parent.parent

# The exit vocabulary lives in ``cliexit`` (plans/cli-segmentation.md
# behaviour 1); the names are imported above so ``cli.EXIT_*`` keeps
# resolving for the tests and downstream callers.
# ``_fail`` is the historical name for ``cliexit.fail`` — kept as an alias
# for the ~20 pre-segmentation call sites.
_fail = fail

ENV_FILENAME = ".env"
SETTINGS_FILENAME = "anvil.yaml"
LOCAL_SETTINGS_FILENAME = "anvil.local.yaml"
MODELS_FILENAME = "config.yaml"
BANNER = r"""
                      _ _
     /\              (_) |
    /  \   _ ____   ___| |
   / /\ \ | '_ \ \ / / | |
  / ____ \| | | \ V /| | |
 /_/    \_\_| |_|\_/ |_|_|

"""

_SEPARATOR = "-" * 60

# The credential resolution lives in ``credentials`` (plans/cli-segmentation.md
# behaviour 3); the env-key name is re-exposed so ``cli.GITHUB_TOKEN_ENV``
# keeps resolving for the tests.
GITHUB_TOKEN_ENV = credentials.GITHUB_TOKEN_ENV
PORT_ENV = "LLM_PORT"


class Context:
    """Global options plus the paths every command works from.

    Carried on typer's context object so each subcommand receives one value
    rather than five, and so tests can see exactly what was resolved.
    """

    def __init__(
        self,
        dry_run: bool = False,
        verbose: bool = False,
        no_color: bool = False,
        assume_yes: bool = False,
    ) -> None:
        self.dry_run = dry_run
        self.verbose = verbose
        self.no_color = no_color
        self.assume_yes = assume_yes
        self.root = REPO_ROOT

    @property
    def env_path(self) -> Path:
        return self.root / ENV_FILENAME

    @property
    def settings_path(self) -> Path:
        return self.root / SETTINGS_FILENAME

    @property
    def local_settings_path(self) -> Path:
        return self.root / LOCAL_SETTINGS_FILENAME

    @property
    def models_path(self) -> Path:
        return self.root / MODELS_FILENAME

    @property
    def use_color(self) -> bool:
        return not self.no_color

    def echo(self, message: str = "") -> None:
        typer.echo(message)

    def detail(self, message: str) -> None:
        """Emit only under ``--verbose``."""
        if self.verbose:
            typer.echo(message)

    def interactive(self) -> bool:
        return _is_interactive()

    def settings(self) -> config.AnvilSettings:
        return config.read_settings(self.settings_path, self.local_settings_path)

    def resolve_port(self, port_flag: Optional[int]) -> int:
        return config.resolve_port(
            port_flag,
            env.get(self.env_path, PORT_ENV),
            self.settings().default_port,
        )


def _is_interactive() -> bool:
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def _in_venv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

# Extra args are refused at the group level so an unknown command is a usage
# error rather than being swallowed as an argument.
app = typer.Typer(
    help=(
        "Anvil - manage the local llama-swap backend and provision repositories.\n"
        "Run 'anvil <command> --help' for detailed help on a command."
    ),
    no_args_is_help=True,
    add_completion=False,
)

_PASSTHROUGH = {"allow_extra_args": True, "ignore_unknown_options": True}


@app.callback()
def main(
    ctx: typer.Context,
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print what would be written or executed, then stop."
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Explain each step."),
    no_color: bool = typer.Option(
        False, "--no-color", help="Suppress ANSI colour in output."
    ),
) -> None:
    """Resolve the global options before any subcommand runs."""
    ctx.obj = Context(dry_run=dry_run, verbose=verbose, no_color=no_color)


def _context(ctx: typer.Context, assume_yes: bool = False) -> Context:
    shared = ctx.obj if isinstance(ctx.obj, Context) else Context()
    if assume_yes:
        shared.assume_yes = True
    return shared


def _banner(shared: Context) -> None:
    shared.echo(BANNER)


def _compose_for(shared: Context, profile: str) -> Compose:
    return Compose(
        project_dir=shared.root,
        profile=profile,
        dry_run=shared.dry_run,
        echo=shared.echo,
    )


# ---------------------------------------------------------------------------
# Container lifecycle commands
# ---------------------------------------------------------------------------


def _run_compose_command(
    ctx: typer.Context,
    shared: Context,
    profile: str,
    announcement: str,
    operation: str,
    **kwargs,
) -> None:
    """Shared body of up/build/restart/logs/down.

    Every one of them announces itself, ensures ``.env`` exists, then delegates -
    with ``ctx.args`` forwarded so user arguments reach docker untouched.
    """
    _banner(shared)
    shared.echo(announcement)
    envsetup.ensure_env(shared)

    engine = _compose_for(shared, profile)
    shared.detail("profile: {}".format(profile))
    shared.detail("extra arguments: {}".format(" ".join(ctx.args) or "(none)"))

    try:
        code = getattr(engine, operation)(extra_args=ctx.args, **kwargs)
    except ComposeError as exc:
        raise fail("❌ {}".format(exc), EXIT_DOCKER) from exc

    if code != 0:
        # docker's own status is the truth about docker; do not relabel it.
        raise typer.Exit(code)


@app.command(context_settings=_PASSTHROUGH)
def up(
    ctx: typer.Context,
    profile: str = typer.Option(compose.DEFAULT_PROFILE, "--profile"),
    assume_yes: bool = typer.Option(False, "--yes", "-y", help="Never prompt."),
) -> None:
    """Start the Llama-Swap router and dependencies."""
    shared = _context(ctx, assume_yes)
    _run_compose_command(
        ctx,
        shared,
        profile,
        "Starting the Anvil local backend cluster via Llama-Swap...",
        "up",
    )


@app.command(context_settings=_PASSTHROUGH)
def build(
    ctx: typer.Context,
    profile: str = typer.Option(compose.DEFAULT_PROFILE, "--profile"),
    assume_yes: bool = typer.Option(False, "--yes", "-y", help="Never prompt."),
) -> None:
    """Force build/rebuild of custom configurations."""
    shared = _context(ctx, assume_yes)
    _run_compose_command(
        ctx, shared, profile, "Rebuilding container configurations...", "build"
    )


@app.command(context_settings=_PASSTHROUGH)
def restart(
    ctx: typer.Context,
    profile: str = typer.Option(compose.DEFAULT_PROFILE, "--profile"),
    assume_yes: bool = typer.Option(False, "--yes", "-y", help="Never prompt."),
) -> None:
    """Quickly cycle the core proxy daemon."""
    shared = _context(ctx, assume_yes)
    _run_compose_command(
        ctx, shared, profile, "Bouncing the llama-swap manager container...", "restart"
    )


@app.command(context_settings=_PASSTHROUGH)
def logs(
    ctx: typer.Context,
    follow: bool = typer.Option(
        True, "--follow/--no-follow", help="Keep streaming (the default, as in bash)."
    ),
    profile: str = typer.Option(compose.DEFAULT_PROFILE, "--profile"),
    assume_yes: bool = typer.Option(False, "--yes", "-y", help="Never prompt."),
) -> None:
    """Stream dynamic engine controller outputs."""
    shared = _context(ctx, assume_yes)
    _run_compose_command(
        ctx,
        shared,
        profile,
        "Streaming logs from your llama-swap orchestration engine...",
        "logs",
        follow=follow,
    )


@app.command(context_settings=_PASSTHROUGH)
def down(
    ctx: typer.Context,
    keep_orphans: bool = typer.Option(
        False,
        "--keep-orphans",
        help="Leave on-demand vLLM containers running instead of sweeping them.",
    ),
    profile: str = typer.Option(compose.DEFAULT_PROFILE, "--profile"),
    assume_yes: bool = typer.Option(False, "--yes", "-y", help="Never prompt."),
) -> None:
    """Stop all runtime services and child model processes."""
    shared = _context(ctx, assume_yes)

    if not keep_orphans:
        shared.detail("orphaned vLLM containers will be purged after shutdown")

    _run_compose_command(
        ctx,
        shared,
        profile,
        "🛑 Destroying active containers and runtime allocations...",
        "down",
        purge_orphans=not keep_orphans,
    )


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@app.command()
def status(
    ctx: typer.Context,
    as_json: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of the table."
    ),
    llm_port: Optional[int] = typer.Option(
        None, "--llm-port", min=1, max=65535, help="Override the gateway port."
    ),
    timeout: float = typer.Option(
        health.DEFAULT_TIMEOUT, "--timeout", help="Seconds to wait for the gateway."
    ),
    assume_yes: bool = typer.Option(False, "--yes", "-y", help="Never prompt."),
) -> None:
    """Verify active engine routing layers and API backends."""
    shared = _context(ctx, assume_yes)

    try:
        # --json must be pipeable, so nothing decorative may precede it: no
        # banner, no 'docker compose ps' table.
        if as_json:
            port = shared.resolve_port(llm_port)
            shared.echo(health.format_json(health.check_gateway(port, timeout)))
            return

        _banner(shared)
        envsetup.ensure_env(shared)
        port = shared.resolve_port(llm_port)

        shared.echo("Llama-Swap Daemon & Infrastructure Status:")
        shared.echo(_SEPARATOR)

        engine = _compose_for(shared, compose.DEFAULT_PROFILE)
        try:
            engine.ps()
        except ComposeError as exc:
            # A missing docker must not hide the gateway report: the gateway can
            # be up while the local CLI is broken.
            shared.echo("⚠️  {}".format(exc))

        shared.echo("")
        shared.echo("Dynamic Model Routing Health Checks:")
        shared.echo(_SEPARATOR)

        shared.detail("probing http://localhost:{} (timeout {}s)".format(port, timeout))

        gateway = health.check_gateway(port, timeout)
        shared.echo(health.format_status(gateway, use_color=shared.use_color))
    except ConfigError as exc:
        raise fail("❌ {}".format(exc), EXIT_CONFIG) from exc


# ---------------------------------------------------------------------------
# test-model
# ---------------------------------------------------------------------------
#
# The model-state reporting the test-model and stress handlers share (the
# available-id list, the empty-registry wording, the unknown-model usage
# error) moved to modelreport in plans/cli-segmentation.md behaviour 6; only
# the handler stays here.
@app.command(name="test-model")
def test_model(
    ctx: typer.Context,
    model_name: Optional[str] = typer.Argument(
        None,
        metavar="MODEL_NAME",
        help="The model id to exercise, as it appears in 'anvil status'.",
    ),
    prompt: str = typer.Option(
        health.DEFAULT_PROBE_PROMPT, "--prompt", help="The prompt to send."
    ),
    max_tokens: int = typer.Option(
        health.DEFAULT_MAX_TOKENS, "--max-tokens", min=1, help="Reply token ceiling."
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of the report."
    ),
    llm_port: Optional[int] = typer.Option(
        None, "--llm-port", min=1, max=65535, help="Override the gateway port."
    ),
    timeout: float = typer.Option(
        health.DEFAULT_GENERATION_TIMEOUT,
        "--timeout",
        help="Seconds to wait for the completion. A cold model must load first.",
    ),
    assume_yes: bool = typer.Option(False, "--yes", "-y", help="Never prompt."),
) -> None:
    """Send one prompt to a model and report whether it answered.

    'status' only reports what the gateway has registered and loaded, which does
    not prove the worker behind a model can still generate. This does.
    """
    shared = _context(ctx, assume_yes)

    try:
        port = shared.resolve_port(llm_port)
    except ConfigError as exc:
        raise fail("❌ {}".format(exc), EXIT_CONFIG) from exc

    # Checked here rather than by making the argument required, so the refusal
    # can name the ids that would have worked. It stays a usage error: no test
    # was run. It precedes --dry-run for the same reason.
    if model_name is None:
        raise modelreport.report_available_models(shared, port)

    if shared.dry_run:
        body = health.build_chat_request(model_name, prompt, max_tokens)
        shared.echo(
            health.format_request_json(port, body)
            if as_json
            else health.format_request(port, body)
        )
        return

    # --json must be pipeable, so nothing decorative may precede it.
    if not as_json:
        _banner(shared)
        shared.detail(
            "prompting {} at http://localhost:{} (timeout {}s)".format(
                model_name, port, timeout
            )
        )

    result = health.test_model(
        port=port,
        model_id=model_name,
        prompt=prompt,
        max_tokens=max_tokens,
        timeout=timeout,
    )

    shared.echo(
        health.format_model_test_json(result)
        if as_json
        else health.format_model_test(result, use_color=shared.use_color)
    )

    if not result.ok:
        # A model that cannot answer is a failure of the thing being measured,
        # not of Anvil, so it takes the generic error code rather than one of
        # the configuration or docker codes.
        raise typer.Exit(EXIT_ERROR)


# ---------------------------------------------------------------------------
# stress
# ---------------------------------------------------------------------------
#
# The report logic (warm-up pacing, the per-attempt and per-level printing,
# the report stamping) moved to stressreport in plans/cli-segmentation.md
# behaviour 5; only the handler and its flags stay here.
# ``_WARMUP_RETRY_INTERVAL`` keeps resolving on the cli namespace - the
# value lives in stressreport and the alias tracks it, so a reader of cli.py
# sees the same number the moved code paces with.
_WARMUP_RETRY_INTERVAL = stressreport._WARMUP_RETRY_INTERVAL


@app.command()
def stress(
    ctx: typer.Context,
    model_name: Optional[str] = typer.Argument(
        None,
        metavar="MODEL_NAME",
        help="The model id to stress, as it appears in 'anvil status'.",
    ),
    max_concurrency: int = typer.Option(
        16, "--max-concurrency", min=1, help="Highest concurrency level; the ramp is derived from it."
    ),
    requests: int = typer.Option(
        20, "--requests", min=1, help="Requests sent at each level."
    ),
    prompt: str = typer.Option(
        stress.DEFAULT_PROMPT, "--prompt", help="Fixed prompt, identical for every request."
    ),
    max_tokens: int = typer.Option(
        128, "--max-tokens", min=1, help="Reply token ceiling, identical for every request."
    ),
    timeout: float = typer.Option(
        120.0, "--timeout", help="Seconds per measured request."
    ),
    warmup_timeout: float = typer.Option(
        600.0,
        "--warmup-timeout",
        help="Total seconds allowed for a cold model to come up before measuring.",
    ),
    no_warmup: bool = typer.Option(
        False, "--no-warmup", help="Skip warm-up; skews level 1 for a cold model."
    ),
    log_file: Optional[Path] = typer.Option(
        None, "--log-file", help="Override the derived log path."
    ),
    no_log_file: bool = typer.Option(
        False, "--no-log-file", help="Print the report but write no log."
    ),
    llm_port: Optional[int] = typer.Option(
        None, "--llm-port", min=1, max=65535, help="Override the gateway port."
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Emit only the JSON summary; nothing decorative precedes it."
    ),
    assume_yes: bool = typer.Option(False, "--yes", "-y", help="Never prompt."),
) -> None:
    """Ramp a model from one concurrent request to the maximum and report where it breaks.

    'status' and 'test-model' prove the model answers at all; this proves it
    still answers under load, which is the question hardware sizing needs.
    """
    shared = _context(ctx, assume_yes)

    # The report logic raises its own ``typer.Exit`` on the failure paths; it
    # only returns once a run has finished, with the code this handler turns
    # back into the exit both entry paths surface: click's standalone mode
    # discards a *returned* ``typer.Exit``, so it must be raised, and run()
    # (standalone_mode=False) maps the raised code onto its return value.
    code = stressreport.run_stress_command(
        shared,
        _banner,
        modelreport.report_available_models,
        model_name,
        max_concurrency,
        requests,
        prompt,
        max_tokens,
        timeout,
        warmup_timeout,
        no_warmup,
        log_file,
        no_log_file,
        llm_port,
        as_json,
    )
    raise typer.Exit(code)


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


@app.command()
def init(
    ctx: typer.Context,
    force: bool = typer.Option(
        False, "--force", help="Regenerate .env even if it already exists."
    ),
    llm_port: Optional[int] = typer.Option(None, "--llm-port", min=1, max=65535),
    hf_home: Optional[str] = typer.Option(None, "--hf-home"),
    data_dir: Optional[str] = typer.Option(None, "--data-dir"),
    gpu_generic: Optional[str] = typer.Option(None, "--gpu-generic"),
    gpu_coder: Optional[str] = typer.Option(
        None, "--gpu-coder", help="One or two comma-separated device ids."
    ),
    gpu_embedder: Optional[str] = typer.Option(None, "--gpu-embedder"),
    assume_yes: bool = typer.Option(
        False, "--yes", "-y", help="Accept every default without prompting."
    ),
) -> None:
    """Create the .env configuration file."""
    shared = _context(ctx, assume_yes)
    _banner(shared)

    if shared.env_path.is_file() and not force:
        # Bash never faced this: its bootstrap was guarded by '[ ! -f .env ]', so
        # it could only ever create. As an explicit command, refusing protects a
        # hand-tuned .env from a mistyped command.
        raise fail(
            "❌ {} already exists; pass --force to regenerate it.".format(
                shared.env_path
            ),
            EXIT_USAGE,
        )

    answers = envsetup.EnvAnswers(
        llm_port=llm_port,
        hf_home=hf_home,
        data_dir=data_dir,
        gpu_generic=gpu_generic,
        gpu_coder=gpu_coder,
        gpu_embedder=gpu_embedder,
    )

    try:
        envsetup.bootstrap_env(shared, answers)
    except ConfigError as exc:
        raise fail("❌ {}".format(exc), EXIT_CONFIG) from exc
    except PromptError as exc:
        raise fail("❌ {}".format(exc), EXIT_PROMPT) from exc


# ---------------------------------------------------------------------------
# setup-repo
# ---------------------------------------------------------------------------


# The credential resolution lives in ``credentials`` (plans/cli-segmentation.md
# behaviour 3); the private names are re-exposed as same-name aliases so the
# direct ``cli._resolve_github_token(...)`` / ``cli._resolve_oxylabs(...)`` test
# calls keep resolving. The CLI itself calls the public names qualified.
_resolve_github_token = credentials.resolve_github_token
_resolve_oxylabs = credentials.resolve_oxylabs

# The guard-gate flow lives in ``piguardgate`` (plans/cli-segmentation.md
# behaviour 4); the same-name aliases keep the direct ``cli.<name>`` test
# calls resolving. The CLI itself calls the public names qualified.
# There is no alias for ``_free_plan_followup``: the test patch sites
# retarget to ``cli.piguardgate.free_plan_followup`` because the internal
# call now resolves in the new module's globals.
_ask_free_plan = piguardgate.ask_free_plan
_codeowners_flow = piguardgate.codeowners_flow
_collect_guard_findings = piguardgate.collect_guard_findings
_echo_guard_report = piguardgate.echo_guard_report


@app.command(name="setup-repo")
def setup_repo(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="Target repository directory."),
    llm_port: Optional[int] = typer.Option(None, "--llm-port", min=1, max=65535),
    github_token: Optional[str] = typer.Option(None, "--github-token"),
    no_github: bool = typer.Option(
        False, "--no-github", help="Skip GitHub integration entirely."
    ),
    anthropic_key: Optional[str] = typer.Option(None, "--anthropic-key"),
    want_anthropic: bool = typer.Option(
        False,
        "--anthropic",
        help="Use Anthropic for architect and orchestrator modes, taking the key from .env.",
    ),
    no_anthropic: bool = typer.Option(
        False, "--no-anthropic", help="Keep architect and orchestrator modes on the local gateway."
    ),
    anthropic_model: Optional[str] = typer.Option(
        None, "--anthropic-model", help="Any model id, including an unlisted one."
    ),
    oxylabs_username: Optional[str] = typer.Option(
        None, "--oxylabs-username"
    ),
    oxylabs_password: Optional[str] = typer.Option(
        None, "--oxylabs-password"
    ),
    no_oxylabs: bool = typer.Option(
        False, "--no-oxylabs", help="Skip Oxylabs documentation scraping entirely."
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help="Record the provisioning under this profile name in the Anvil "
        "profile store. There is no default: a missing name is asked "
        "interactively, or must be supplied here when non-interactive.",
    ),
    container: bool = typer.Option(
        False,
        "--container",
        help="Render Zoo Code URLs for a dev container reaching the host via "
        "host.docker.internal (host-mapped LLM_PORT) instead of localhost.",
    ),
    assume_yes: bool = typer.Option(
        False, "--yes", "-y", help="Accept every default without prompting."
    ),
) -> None:
    """Inject template configs, .roo frameworks, VS Code options and rules."""
    shared = _context(ctx, assume_yes)
    _banner(shared)

    try:
        settings = shared.settings()
        topology = config.read_models(shared.models_path)
        port = shared.resolve_port(llm_port)
    except ConfigError as exc:
        raise fail("❌ {}".format(exc), EXIT_CONFIG) from exc

    shared.detail("gateway port: {}".format(port))
    shared.detail("coder model: {}".format(topology.coder_id))
    shared.detail("context window: {}".format(topology.coder_context_window))

    try:
        token, repository = piguardgate.guard_gate(
            shared, path, github_token, no_github
        )
        frontier = credentials.resolve_frontier(
            shared,
            settings,
            anthropic_key,
            no_anthropic,
            want_anthropic,
            anthropic_model,
        )
        shared.echo("")
        oxylabs_username, oxylabs_password = credentials.resolve_oxylabs(
            shared, oxylabs_username, no_oxylabs, oxylabs_password
        )
        shared.echo("")
    except PromptError as exc:
        raise fail("❌ {}".format(exc), EXIT_PROMPT) from exc

    # Behaviour 21 (superseding behaviour 15's basename default): the
    # profile name is resolved BEFORE anything is provisioned, and only on
    # the path that records (the gate ran, i.e. not --no-github).
    # --profile returns its name without prompting; with no flag there
    # is NO default, so --yes or a non-interactive run cannot answer
    # the question and fails on the prompt code (6) naming
    # --profile NAME as the fix, before provisioning. The resolved name
    # is validated against the store's charset rule up front, so an
    # invalid name is a usage error that stops the run before
    # provisioning - an invalid name can no longer reach save_profile.
    # A skipped gate (--no-github) has no identity to record, so no
    # name is resolved.
    profile_name: Optional[str] = None
    if not no_github:
        try:
            profile_name = piprofileflow.resolve_profile_name(shared, profile)
        except PromptError as exc:
            raise fail("❌ {}".format(exc), EXIT_PROMPT) from exc

    repo_plan = RepoPlan(
        port=port,
        context_window=topology.coder_context_window,
        coder_model_id=topology.coder_id,
        embedder_model_id=topology.embedder_id,
        local_profile_id=settings.local_profile_id,
        anthropic_profile_id=settings.anthropic_profile_id,
        anthropic_api_key=frontier.api_key,
        anthropic_model_id=frontier.model_id,
        use_anthropic_for_frontier_modes=frontier.use_anthropic,
        github_token=token,
        oxylabs_username=oxylabs_username,
        oxylabs_password=oxylabs_password,
        container_target=container,
    )

    try:
        provision.setup_repo(
            path,
            repo_plan,
            dry_run=shared.dry_run,
            echo=shared.echo,
        )
    except ProvisionError as exc:
        raise fail("❌ {}".format(exc), EXIT_PROVISION) from exc
    except RenderError as exc:
        raise fail("❌ {}".format(exc), EXIT_CONFIG) from exc

    if profile_name is not None:
        piprofileflow.announce_or_record_profile(shared, path, profile_name, repository)


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


def _mark(ok: bool) -> str:
    return "✅" if ok else "❌"


def _report_line(label: str, value: str) -> str:
    return "  {:<22} {}".format(label + ":", value)


@app.command()
def doctor(ctx: typer.Context) -> None:
    """Report the interpreter, virtualenv, docker, compose and GPU tooling.

    Deliberately never fails on what it diagnoses: a broken host is exactly when
    this command is needed, so a missing docker is a finding, not an error. It
    also never writes anything, including the .env bootstrap.
    """
    shared = _context(ctx)

    shared.echo("Anvil environment report")
    shared.echo(_SEPARATOR)

    shared.echo("Python")
    shared.echo(_report_line("interpreter", sys.executable))
    shared.echo(
        _report_line("version", "{}.{}.{}".format(*sys.version_info[:3]))
    )
    shared.echo(
        _report_line(
            "venv", "{} {}".format(_mark(_in_venv()), sys.prefix if _in_venv() else "not in a venv")
        )
    )

    shared.echo("")
    shared.echo("Container tooling")
    docker_ok = compose.docker_available()
    compose_ok = compose.compose_v2_available()
    nvidia_ok = compose.nvidia_available()

    shared.echo(
        _report_line(
            "docker",
            "{} {}".format(
                _mark(docker_ok),
                "daemon responding" if docker_ok else "not available",
            ),
        )
    )
    shared.echo(
        _report_line(
            "compose v2",
            "{} {}".format(
                _mark(compose_ok),
                "plugin installed" if compose_ok else "'docker compose' not available",
            ),
        )
    )
    shared.echo(
        _report_line(
            "nvidia",
            "{} {}".format(
                _mark(nvidia_ok),
                "nvidia-smi responding" if nvidia_ok else "no GPU tooling detected",
            ),
        )
    )

    shared.echo("")
    shared.echo("Configuration")
    for label, path in (
        (ENV_FILENAME, shared.env_path),
        (SETTINGS_FILENAME, shared.settings_path),
        (MODELS_FILENAME, shared.models_path),
    ):
        present = path.is_file()
        shared.echo(
            _report_line(
                label, "{} {}".format(_mark(present), path if present else "missing")
            )
        )

    _report_config_health(shared)
    piguardgate.report_guards(shared)

    shared.echo(_SEPARATOR)


def _report_config_health(shared: Context) -> None:
    """Try to parse the configuration, reporting rather than raising."""
    if shared.settings_path.is_file():
        try:
            settings = shared.settings()
            shared.echo(
                _report_line(
                    "default port", "{} {}".format(_mark(True), settings.default_port)
                )
            )
        except ConfigError as exc:
            shared.echo(
                _report_line(
                    SETTINGS_FILENAME + " parse", "{} {}".format(_mark(False), exc)
                )
            )

    if shared.models_path.is_file():
        try:
            topology = config.read_models(shared.models_path)
            shared.echo(
                _report_line(
                    "coder model", "{} {}".format(_mark(True), topology.coder_id)
                )
            )
            shared.echo(
                _report_line(
                    "context window",
                    "{} {}".format(_mark(True), topology.coder_context_window),
                )
            )
        except ConfigError as exc:
            shared.echo(
                _report_line(
                    MODELS_FILENAME + " parse", "{} {}".format(_mark(False), exc)
                )
            )


# ---------------------------------------------------------------------------
# verify-guards
# ---------------------------------------------------------------------------


@app.command(name="verify-guards")
def verify_guards(
    ctx: typer.Context,
    target: Path = typer.Argument(
        Path("."),
        metavar="TARGET",
        help="Target repository directory; defaults to the current directory.",
    ),
    branch: str = typer.Option(
        "main", "--branch", help="The branch whose rules are checked."
    ),
    other_repo: Optional[str] = typer.Option(
        None,
        "--other-repo",
        help=(
            "OWNER/REPO: probe whether the token reaches a named other "
            "repository; the value is the raw OWNER/REPO and is never "
            "guessed, so a malformed value surfaces as a skipped finding."
        ),
    ),
) -> None:
    """Check the GitHub branch rules of the target repository and report the guards.

    The agent cannot read it: the token lives on the host driver, outside the
    container. The target's owner/repo is resolved from its origin remote,
    and the rules for ``--branch`` are fetched read-only from the GitHub API
    - a token is used from .env when present, and a missing token is an
    unauthenticated attempt, not a skip: the endpoint allows that on public
    repositories. Anything that could not run is reported as a skipped
    finding, never a pass. After the branch-rule findings, the token-scope
    findings from ``check_token_all`` print, and the exit status is the
    ``summarize`` of all of them, so a ``fail`` exits non-zero. The token is
    read once from .env and passed to the probes; it is never printed. The
    administration probe emits ``fail`` when the repository's
    actions-permissions endpoint is readable - the grant that could delete
    the repository - and the classic-token probe emits ``fail`` when a
    classic OAuth scope is returned, which reaches every repository the
    owner can see.
    """
    shared = _context(ctx)

    token = env.get(shared.env_path, GITHUB_TOKEN_ENV)

    findings, token_findings, repository = piguardgate.collect_guard_findings(
        target, token, branch, other_repo=other_repo
    )

    shared.echo("Guards report")
    shared.echo(_SEPARATOR)
    shared.echo(_report_line("target", str(target)))
    shared.echo(_report_line("branch", branch))
    if repository is not None:
        shared.echo(
            _report_line("repository", "{}/{}".format(repository[0], repository[1]))
        )
    else:
        shared.echo(_report_line("repository", "not resolvable from origin"))
    # Behaviour 19: the findings print as wrapped blocks - a status-
    # prefixed headline, the finding's substance at 80 columns, and an
    # indented fix:/see: line - under a section header per source, so
    # branch and token findings no longer run together as unbroken
    # lines and no report line exceeds 80 characters.
    shared.echo("")
    piguardgate.echo_guard_report(shared, findings, token_findings)
    piguardgate.free_plan_followup(
        shared, findings, repository, branch, target
    )
    shared.echo(_SEPARATOR)

    raise typer.Exit(piguard.summarize(findings + token_findings))
# ---------------------------------------------------------------------------
# smoke-test
# ---------------------------------------------------------------------------


def _docker_runner_factory() -> Callable[[List[str]], Tuple[int, str, str]]:
    """The production docker seam: one list-form argv in, the three-tuple out.

    ``cli.py`` constructs no docker argv and never invokes docker itself; the
    ``smoke`` checks build every argv and this factory's product runs it - a
    list-form ``subprocess.run`` (never a string, never ``shell=True``) with
    stdout and stderr captured, returning ``(exit_code, stdout, stderr)``. A
    missing docker binary surfaces as ``FileNotFoundError``, which the checks
    already turn into a "not on PATH" failure rather than a traceback.
    """
    def docker_runner(argv: List[str]) -> Tuple[int, str, str]:
        completed = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout = completed.stdout.decode("utf-8", "replace")
        stderr = completed.stderr.decode("utf-8", "replace")
        return (completed.returncode, stdout, stderr)

    return docker_runner


def _pidriver_runner_factory() -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """The production pidriver seam: one invocation dict in, six-key result out.

    Returns the module's own :func:`anvilkit.pi.pibakeoff.subprocess_runner` -
    the same runner every other driver-backed command uses - so the six-key
    result shape (``exit_code``, ``stdout``, ``stderr``, ``wall_time_s``,
    ``timed_out``, ``evidence``) is the one pinned in ``anvilkit/pi/
    pibakeoff.py`` and never re-implemented here.
    """
    return pibakeoff.subprocess_runner


def _pirun_git_factory() -> Callable[[List[str]], None]:
    """The production git seam for ``pi run``: one list-form argv in, nothing out.

    Follows :func:`_pidriver_runner_factory`'s factory pattern: a module-level
    private factory returning the production callable. The argv is executed
    verbatim through list-form ``subprocess`` - no ``shell=True``, so no
    argument is ever re-parsed by a shell. On a non-zero exit it raises
    ``pirun.RunError`` naming the command and the exit code, so the run
    never believes a git step that failed (behaviour 9's pin arrives with
    the push execution; until then the seam simply must not swallow a
    failure).
    """

    def git(argv: List[str]) -> None:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise pirun.RunError(
                "git exited {}: {}".format(
                    completed.returncode, " ".join(argv)
                )
            )

    return git


@app.command(name="smoke-test")
def smoke_test(
    ctx: typer.Context,
    repo: Optional[Path] = typer.Option(
        None, "--repo", help="Target repository; defaults to the current "
                             "working directory."
    ),
    llm_port: Optional[int] = typer.Option(
        None, "--llm-port", min=1, max=65535, help="Override the gateway port."
    ),
    fix: bool = typer.Option(
        False, "--fix",
        help="Chown the agent volume on a models.json permission failure and "
             "retry the read once.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Print what each layer would check; spawn no process and make "
             "no HTTP call.",
    ),
    dump_events: bool = typer.Option(
        False, "--dump-events",
        help="Append the layer-5 run's raw JSONL event stream to the report, "
             "verbatim, when that run check ran and passed.",
    ),
) -> None:
    """Prove the single-role stack: docker, gateway, agent volume, prompt, one real run, failure paths.

    Runs the six smoke layers against ``--repo`` and exits with ``summarize``'
    code: 0 when every layer passes, 4 when a docker-class layer (1-4)
    fails, 1 when only the run-class layers (5-6) fail. ``--dry-run`` names
    every layer without spawning or probing.
    """
    shared = _context(ctx)

    # --repo defaults to the working directory, resolved at call time (not
    # import time) so the default tracks where the operator actually stands.
    target = repo if repo is not None else Path.cwd()

    # A mistyped path is a usage error before anything else runs - layers,
    # docker, HTTP - regardless of --dry-run, so the failure cannot be
    # mistaken for a layer report (behaviour 19).
    if not target.is_dir():
        raise fail(
            "❌ --repo names no existing directory: {}".format(target),
            EXIT_USAGE,
        )

    # The global --dry-run (set before the subcommand) and the local one are
    # the same intent: name what would be checked, then stop.
    dry = dry_run or shared.dry_run

    try:
        port = shared.resolve_port(llm_port)
    except ConfigError as exc:
        raise fail("❌ {}".format(exc), EXIT_CONFIG) from exc

    docker_runner = _docker_runner_factory()
    runner = _pidriver_runner_factory()

    report, exit_code = smoke.run_smoke_test(
        str(target),
        port,
        docker_runner,
        runner,
        fix=fix,
        dry_run=dry,
        check_gateway=health.check_gateway,
        read_models=config.read_models,
        dump_events=dump_events,
    )

    typer.echo(report, nl=False)
    raise typer.Exit(exit_code)


# ---------------------------------------------------------------------------
# profile sub-app
# ---------------------------------------------------------------------------

# A flat CLI grows a sub-group the moment one command family carries more
# than one verb; ``profile`` is that family. The commands here are
# read-only and need no shared Context (no port, no compose), so they stay
# standalone: no global callback, no prompts, no ``--yes``.
profile_app = typer.Typer(
    help="Inspect the profiles recorded in the ~/.anvil profile store.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(profile_app, name="profile")


@profile_app.command(name="list")
def profile_list() -> None:
    """List every saved profile, one line per name with its absolute path.

    A read is a read: it never writes, and it prints only the record's own
    fields - never a resolved token, so a token value is never echoed.
    A record whose path has vanished still lists, with its stored path:
    ``profile_path`` does no existence check (behaviour 19), so ``list``
    stays a working discovery tool while ``show`` keeps behaviour 10's
    refusal.
    """
    root = piprofileflow.profile_root()
    names = piprofile.list_profiles(root)
    if not names:
        typer.echo("No profiles are saved.")
        return
    for name in names:
        typer.echo("{}\t{}".format(name, piprofile.profile_path(root, name)))


@profile_app.command(name="show")
def profile_show(
    name: str = typer.Argument(..., help="The profile name to show."),
) -> None:
    """Print one profile's record: path, owner, repo, base, the ``token_env``
    key name, and the project block's values, verbatim.

    Prints the ``token_env`` KEY name, never a token value: it reads only
    the record's own fields and never resolves a token or reads a .env. A
    name the store does not hold exits on the usage code with the store's
    own message (behaviour 9); a record whose path has vanished raises
    ``ProfileError`` untouched, for the entry point to map.
    """
    root = piprofileflow.profile_root()
    try:
        record = piprofile.load_profile(root, name)
    except ProfileError as exc:
        if name not in piprofile.list_profiles(root):
            # Behaviour 9: the store does not hold this name - a typo the
            # operator can fix from the message, which names the known
            # profiles, or says none are saved.
            raise fail(str(exc), EXIT_USAGE) from exc
        # The name IS held: a vanished path (behaviour 10) or a malformed
        # store - a controlled failure the entry point maps to its own
        # code, so the ProfileError propagates untouched.
        raise
    typer.echo("name: {}".format(name))
    typer.echo("path: {}".format(record["path"]))
    typer.echo("owner: {}".format(record["owner"]))
    typer.echo("repo: {}".format(record["repo"]))
    typer.echo("base: {}".format(record["base"]))
    typer.echo("token_env: {}".format(record["token_env"]))
    project = record.get("project")
    for key, value in (project or {}).items():
        typer.echo("project.{}: {}".format(key, value))


# ---------------------------------------------------------------------------
# pi sub-app
# ---------------------------------------------------------------------------

# The ``pi`` family grows one verb at a time (``run`` first); like
# ``profile`` it is standalone: no global callback, no shared Context,
# because nothing here needs a port or a compose project.
pi_app = typer.Typer(
    help="Drive a Pi run for a recorded profile.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(pi_app, name="pi")


@pi_app.command(name="run")
def pi_run(
    ctx: typer.Context,
    profile: str = typer.Argument(..., help="The profile name to run."),
    issue: int = typer.Argument(..., help="The GitHub issue number to run."),
) -> None:
    """Run one Pi cycle for ``profile`` against issue number ``issue``.

    The profile gate runs first: the store is loaded and a record that
    cannot load - an unknown name, or a held name whose path has vanished
    - fails on the usage code with the store's own message, before any run
    seam is touched. After the gate, the run phase resolves the GitHub
    token (the home ``.env``'s value under the record's ``token_env`` key,
    falling back to the install ``.env``'s ``GITHUB_TOKEN``), reads the
    issue host-side with it, and - when the read succeeded - calls
    ``pigithub.run`` with the plan-pinned parameter mapping. The token
    reaches only the ``token`` parameter of ``pigithub.read_issue`` and
    ``pigithub.run`` (behaviour 8): never stdout, the archive, or any
    other argument. An empty token does not stop the run: a line
    containing ``unauthenticated`` is printed and the run proceeds. When
    the host-side read fails, the read's reason is reported and
    ``pigithub.run`` is called zero times.

    When ``run`` returns, the command executes the result's
    ``push_argv`` (behaviour 9): only when it is truthy - the
    ``opened`` shape carries it, while ``halted`` and ``intake_failed``
    carry ``None`` and a falsy argv is never executed - verbatim, as a
    list-form subprocess, through the behaviour-8 git seam. A non-zero
    push exit is reported as ``push failed: <reason>`` and exits
    ``EXIT_ERROR`` (1), never 0 and never an outcome code.

    The command exits on the run's own outcome code (behaviour 10):
    ``opened`` is 10, ``halted`` is 11 and the pre-read-failure path
    (``intake_failed``) is 12 - never 0. A push failure still exits
    ``EXIT_ERROR`` (1) and precedes the outcome code: the push block
    raises before the outcome exit is reached.

    The archive (behaviour 11) is opened BEFORE ``pigithub.run`` and
    lands outside the target repository - under
    ``~/.anvil/runs/<profile>/<run-id>/``, computed at call time so a
    test-redirected ``$HOME`` is seen - carrying the ``meta.json``
    (the intake, one session per ``pirole.ROLES`` and the live
    ``anvilkit.__version__``) and, after the run, the generated role
    documents archived verbatim under ``prompts/``. A run id that
    already has an archive is a reported failure - exit 1 - before
    anything runs: no ``pigithub.run``, no subprocess. The run is
    finished on the terminal its status maps to: ``opened`` ships,
    ``halted`` halts; a failed push (exit 1) and a failed intake read
    (exit 12) exit before the finish.

    Under ``--dry-run`` (behaviour 12) the command performs the
    read-only issue read and then stops: it names the profile, the
    derived branch, the archive path that would be written and the
    seams it does not invoke, then exits 0. An unknown profile still
    exits 2 first and a failed read still exits 12.
    """
    shared = _context(ctx)
    root = piprofileflow.profile_root()
    try:
        record = piprofile.load_profile(root, profile)
    except ProfileError as exc:
        raise fail(str(exc), EXIT_USAGE) from exc

    # The token resolves after the gate (behaviour 8). Both env paths are
    # computed at call time: the home root is ``profile_root()`` and the
    # install env is ``REPO_ROOT / .env`` - ``REPO_ROOT`` read from the
    # module global, never captured at import, so a test-redirected root
    # is seen.
    token = piprofile.resolve_token(
        record,
        home_env=root / ".env",
        install_env=REPO_ROOT / ENV_FILENAME,
    )
    if not token:
        typer.echo(
            "no GitHub token resolved - the run proceeds unauthenticated"
        )

    # The derivation needs the payload, so the issue is read host-side
    # first; ``pigithub.run`` re-reads the intake internally by design.
    # The real seam returns ``(issue, reason)`` - the unpack writes the
    # real tuple's shape, and the derivation helpers are defensive for
    # any payload ``read_issue`` can return. The payload is held in
    # ``payload`` so it does not shadow the CLI's ``issue`` number, which
    # ``branch_for`` and the ``run`` call below need as an int.
    payload, reason = pigithub.read_issue(
        record["owner"], record["repo"], issue, token=token
    )
    if payload is None:
        # The read's reason is the report: stdout for the reason (a human
        # reads it there), stderr for the failure line, and the
        # ``intake_failed`` outcome code 12 - the run is never called.
        typer.echo("intake failed: {}".format(reason))
        raise fail("intake failed: {}".format(reason), 12)

    kind = pirun.kind_for(payload)
    branch = pirun.branch_for(kind, issue)

    if shared.dry_run:
        # The dry-run stop (behaviour 12): the read-only read already
        # happened, so the announcement names the REAL derived branch;
        # the run-id dir is generated locally by ``new_run_id`` - no
        # file is written and ``~/.anvil/runs`` is never created. Every
        # loop seam below - the run cycle, the push and the archive -
        # is named, not invoked; a command that returns None exits 0.
        would_be = Path.home() / ".anvil" / "runs" / profile / runlog.new_run_id()
        typer.echo(
            "dry run: profile {prof}, branch {branch}; would write "
            "archive {archive}; not invoked: the run cycle, the push, "
            "the archive".format(
                prof=profile, branch=branch, archive=would_be
            )
        )
        return

    fields = pirun.pr_fields_for(payload)
    title = fields["title"]
    # ``example`` is the issue body verbatim, or the literal when the body
    # is missing, null or blank - the plan's blank-check rule, applied to
    # the raw body rather than ``pr_fields_for``'s placeholder, so a blank
    # body is reported as the literal and never as the placeholder text.
    raw_body = payload.get("body") if isinstance(payload, dict) else None
    example = (
        raw_body
        if isinstance(raw_body, str) and raw_body.strip()
        else "see the intake issue body"
    )
    # The archive (behaviour 11) is opened BEFORE the run, so a run
    # that dies mid-way leaves a readable record (runlog behaviour 6),
    # and it lands outside the target: the root is
    # ``~/.anvil/runs/<profile>`` - ``Path.home()`` consulted at call
    # time, never the record's path - so the run dir is
    # ``~/.anvil/runs/<profile>/<run-id>/``. The intake carries the
    # issue number and the title the host-side read returned (the
    # same defensive derivation as the ``pr_fields_for`` title above),
    # one session per ``pirole.ROLES``, and the ``started_at`` an
    # ISO-8601 UTC string at call time. A run id whose archive
    # already exists is refused here - the run never reaches
    # ``pigithub.run`` or the subprocess, and a past run is never
    # overwritten.
    archive_root = Path.home() / ".anvil" / "runs" / profile
    run_id = runlog.new_run_id()
    try:
        run_dir = runlog.start_run(
            archive_root,
            run_id,
            intake={"issue": issue, "text": title},
            sessions={
                role: runlog.session_id(run_id, role) for role in pirole.ROLES
            },
            started_at=datetime.now(timezone.utc).isoformat(),
        )
    except runlog.RunLogError as exc:
        raise fail("run archive: {}".format(exc), EXIT_ERROR) from exc

    result = pigithub.run(
        record["owner"],
        record["repo"],
        issue,
        record["path"],
        "origin",
        branch,
        title,
        record["base"],
        title,
        (),
        "covered by the repository's existing test suite",
        example,
        record["repo"],
        title,
        "issue-{}".format(issue),
        "issue {}: {}".format(issue, title),
        kind,
        _pidriver_runner_factory(),
        _pirun_git_factory(),
        token=token,
        profile_name=profile,
        profile_root=str(root),
    )

    # The push runs only when the result carries a truthy ``push_argv`` -
    # the ``opened`` shape does; ``halted`` and ``intake_failed`` carry
    # ``None`` and a falsy argv is never executed (behaviour 9). It goes
    # through the behaviour-8 git seam, so the same list-form subprocess
    # discipline and the same non-zero -> ``RunError`` translation cover
    # the caller's push as the cycle's driver git.
    push = result.get("push_argv") if isinstance(result, dict) else None
    if push:
        try:
            _pirun_git_factory()(push)
        except pirun.RunError as exc:
            raise fail(
                "push failed: {}".format(exc), EXIT_ERROR
            ) from exc

    status = result.get("status") if isinstance(result, dict) else None

    # The archive completion (behaviour 11): the role documents the
    # cycle generated are archived verbatim under the run dir - the
    # result's ``documents`` map is the generation seam's return,
    # surfaced by the cycle seam (behaviour 21) - and the writer
    # refuses an empty mapping, so it is called only when the map is
    # non-empty. The run is then finished on the terminal its status
    # maps to: ``opened`` ships, ``halted`` halts. A failed push has
    # already exited 1 and a failed intake read already exited 12, so
    # only the two outcome statuses reach here.
    documents = result.get("documents") if isinstance(result, dict) else None
    if isinstance(documents, dict) and documents:
        runlog.write_prompts(run_dir, documents)
    runlog.finish_run(
        run_dir,
        "shipped" if status == "opened" else "halted",
        datetime.now(timezone.utc).isoformat(),
    )

    # The outcome exit (behaviour 10): the command ends on the run's own
    # outcome code - 10 for ``opened``, 11 for ``halted`` - never 0. The
    # push phase has already run (or was skipped on a falsy ``push_argv``)
    # and a push failure has already exited 1, so by here the outcome is
    # final. The line is the human-readable report of what happened; the
    # non-zero exit is the designed per-outcome code, not an error.
    raise fail(
        "run finished: {}".format(status), pirun.exit_code_for(status)
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run() -> int:
    """Invoke the CLI, mapping any escaped exception to an exit code.

    Replaces the bare ``set -e`` at anvil:4, which made every failure - a missing
    file, a bad port, an absent docker - indistinguishable to a caller.

    ``standalone_mode=False`` is what lets the exit code be chosen here rather
    than by click, but it changes two behaviours that must be handled explicitly:

    * click **returns** the command's value instead of exiting, so a ``typer.Exit``
      raised inside a subcommand surfaces as a return value that would otherwise
      be silently discarded - every failure then looked like success;
    * click **raises** ``UsageError`` instead of printing usage and exiting 2, so
      an unknown command produced a traceback rather than a help message.

    Both were real defects, caught by ``TestRunEntryPoint`` only because it
    exercises this function; ``CliRunner`` uses standalone mode and cannot see them.
    """
    try:
        result = app(standalone_mode=False)
        # In non-standalone mode a returned int is the intended exit code.
        return int(result) if isinstance(result, int) else EXIT_OK
    except click.UsageError as exc:
        # Reproduce what standalone mode would have printed, then use our code.
        if exc.ctx is not None:
            typer.echo(exc.ctx.get_usage(), err=True)
        typer.echo("Error: {}".format(exc.format_message()), err=True)
        return EXIT_USAGE
    except click.ClickException as exc:
        exc.show()
        return EXIT_USAGE
    except SystemExit as exc:
        return int(exc.code or 0)
    except typer.Exit as exc:
        return int(exc.exit_code)
    except typer.Abort:
        typer.echo("Aborted.", err=True)
        return EXIT_ERROR
    except ConfigError as exc:
        typer.echo("❌ {}".format(exc), err=True)
        return EXIT_CONFIG
    except ComposeError as exc:
        typer.echo("❌ {}".format(exc), err=True)
        return EXIT_DOCKER
    except ProvisionError as exc:
        typer.echo("❌ {}".format(exc), err=True)
        return EXIT_PROVISION
    except PromptError as exc:
        typer.echo("❌ {}".format(exc), err=True)
        return EXIT_PROMPT
    except StressError as exc:
        typer.echo("❌ {}".format(exc), err=True)
        return EXIT_STRESS_UNAVAILABLE
    except RenderError as exc:
        typer.echo("❌ {}".format(exc), err=True)
        return EXIT_CONFIG
    except ProfileError as exc:
        typer.echo("❌ {}".format(exc), err=True)
        return EXIT_CONFIG
    except KeyboardInterrupt:
        typer.echo("")
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(run())
