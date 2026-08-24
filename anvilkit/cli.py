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
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import click
import typer

from . import compose, config, env, health, prompts, provision, render
from .compose import Compose, ComposeError
from .config import ConfigError
from .prompts import PromptError
from .provision import ProvisionError, RepoPlan
from .render import RenderError
from .stress import (
    DEFAULT_PROMPT,
    StressError,
    StressReport,
    WarmUpResult,
    check_model_available,
    concurrency_levels,
    format_report,
    format_report_json,
    log_path,
    run_stress,
    warm_up,
    write_log,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

# EXIT_USAGE uses click's own code (2) to avoid conflicting answers.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_CONFIG = 3
EXIT_DOCKER = 4
EXIT_PROVISION = 5
EXIT_PROMPT = 6
# Stress: 7 means no results were produced at all; 8 means the run finished
# and found failures, which is a successful measurement, so it gets its own
# code rather than reusing EXIT_ERROR.
EXIT_STRESS_UNAVAILABLE = 7
EXIT_STRESS_FAILURES = 8

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

# Section headings for .env, mapping keys to comment headings.
_ENV_SECTIONS = {
    "HF_HOME": "--- Host Storage Paths ---",
    "LLM_PORT": "--- Networking Ports ---",
    "LLM_DEVICE_ID_0": "--- GPU Device Allocation ---",
}

_DEFAULT_DATA_DIR = "./"
_DEFAULT_GPU_GENERIC = "0"
_DEFAULT_GPU_CODER = "0,1"
_DEFAULT_GPU_EMBEDDER = "2"

_UNSET_API_KEY = "to set"

ANTHROPIC_KEY_ENV = "ANTHROPIC_API_KEY"
GITHUB_TOKEN_ENV = "GITHUB_TOKEN"
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
    help="Anvil - manage the local llama-swap backend and provision repositories.",
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


def _fail(message: str, code: int) -> "typer.Exit":
    typer.echo(message, err=True)
    return typer.Exit(code)


def _compose_for(shared: Context, profile: str) -> Compose:
    return Compose(
        project_dir=shared.root,
        profile=profile,
        dry_run=shared.dry_run,
        echo=shared.echo,
    )


# ---------------------------------------------------------------------------
# .env bootstrap
# ---------------------------------------------------------------------------


class EnvAnswers:
    """The values the .env bootstrap needs, each overridable by a flag."""

    def __init__(
        self,
        llm_port: Optional[int] = None,
        hf_home: Optional[str] = None,
        data_dir: Optional[str] = None,
        gpu_generic: Optional[str] = None,
        gpu_coder: Optional[str] = None,
        gpu_embedder: Optional[str] = None,
    ) -> None:
        self.llm_port = llm_port
        self.hf_home = hf_home
        self.data_dir = data_dir
        self.gpu_generic = gpu_generic
        self.gpu_coder = gpu_coder
        self.gpu_embedder = gpu_embedder

    def fully_supplied(self) -> bool:
        """True when no question remains, so prompting can be skipped entirely."""
        return all(
            value is not None
            for value in (
                self.llm_port,
                self.hf_home,
                self.data_dir,
                self.gpu_generic,
                self.gpu_coder,
                self.gpu_embedder,
            )
        )


def _default_hf_home() -> str:
    """``$HOME/.cache/huggingface``."""
    return str(Path(os.path.expanduser("~")) / ".cache" / "huggingface")


def _split_coder_gpus(supplied: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Split ``--gpu-coder`` into the two device slots the compose file expects.

    A single id is applied to both slots, which is the natural reading of
    "--gpu-coder 5" and matches what a single-GPU host needs.
    """
    if supplied is None:
        return None, None

    parts = [part.strip() for part in str(supplied).split(",") if part.strip()]

    if not parts:
        raise typer.BadParameter("--gpu-coder needs at least one device id")

    if len(parts) == 1:
        return parts[0], parts[0]

    if len(parts) == 2:
        return parts[0], parts[1]

    raise typer.BadParameter(
        "--gpu-coder takes at most two device ids, got {}".format(len(parts))
    )


def _collect_env_values(
    shared: Context, answers: EnvAnswers, default_port: int
) -> List[Tuple[str, str]]:
    """Ask for (or derive) every .env value in the expected order."""
    interactive = shared.interactive()
    coder_gpu_0, coder_gpu_1 = _split_coder_gpus(answers.gpu_coder)

    hf_home = prompts.ask(
        "Enter Hugging Face cache directory",
        default=_default_hf_home(),
        supplied=answers.hf_home,
        assume_yes=shared.assume_yes,
        interactive=interactive,
    )

    data_dir = prompts.ask(
        "Enter local data storage directory",
        default=_DEFAULT_DATA_DIR,
        supplied=answers.data_dir,
        assume_yes=shared.assume_yes,
        interactive=interactive,
    )

    port = prompts.ask_port(
        "Enter main LLM port",
        default=default_port,
        supplied=answers.llm_port,
        assume_yes=shared.assume_yes,
        interactive=interactive,
    )

    generic_gpu = prompts.ask(
        "Enter Generic LLM GPU Device ID 1",
        default=_DEFAULT_GPU_GENERIC,
        supplied=answers.gpu_generic,
        assume_yes=shared.assume_yes,
        interactive=interactive,
    )

    default_coder_0, default_coder_1 = _DEFAULT_GPU_CODER.split(",")

    coder_0 = prompts.ask(
        "Enter Coder LLM GPU Device ID 1",
        default=default_coder_0,
        supplied=coder_gpu_0,
        assume_yes=shared.assume_yes,
        interactive=interactive,
    )

    coder_1 = prompts.ask(
        "Enter Coder LLM GPU Device ID 2",
        default=default_coder_1,
        supplied=coder_gpu_1,
        assume_yes=shared.assume_yes,
        interactive=interactive,
    )

    embedder_gpu = prompts.ask(
        "Enter Indexer GPU Device ID",
        default=_DEFAULT_GPU_EMBEDDER,
        supplied=answers.gpu_embedder,
        assume_yes=shared.assume_yes,
        interactive=interactive,
    )

    return [
        ("HF_HOME", hf_home),
        ("DATA_DIR", data_dir),
        (PORT_ENV, str(port)),
        ("LLM_DEVICE_ID_0", generic_gpu),
        ("LLM_DEVICE_ID_1", coder_0),
        ("LLM_DEVICE_ID_2", coder_1),
        ("INDEXER_STORAGE_DEVICE_ID", embedder_gpu),
    ]


def _bootstrap_env(shared: Context, answers: EnvAnswers) -> None:
    """Create ``.env`` interactively."""
    shared.echo("⚠️  Configuration file (.env) not found.")
    shared.echo("Let's set up your local Anvil backend environment variables now.")
    shared.echo(_SEPARATOR)

    values = _collect_env_values(shared, answers, shared.settings().default_port)

    if shared.dry_run:
        shared.echo("would write {}:".format(shared.env_path))
        for key, value in values:
            shared.echo("  {}={}".format(key, value))
        return

    env.write(shared.env_path, values, sections=_ENV_SECTIONS)

    shared.echo(_SEPARATOR)
    shared.echo("✅ Successfully generated your local .env configuration file!")
    shared.echo("")


def _ensure_env(shared: Context, answers: Optional[EnvAnswers] = None) -> None:
    """Run the bootstrap when ``.env`` is absent.

    Python does not need a pre-flight guard, but a fresh clone running
    './anvil up' with no .env would hand docker an unset ${LLM_PORT} and fail
    obscurely - so the convenience is kept, for the commands that actually need
    the file.
    """
    if shared.env_path.is_file():
        return

    _bootstrap_env(shared, answers or EnvAnswers())


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
    _ensure_env(shared)

    engine = _compose_for(shared, profile)
    shared.detail("profile: {}".format(profile))
    shared.detail("extra arguments: {}".format(" ".join(ctx.args) or "(none)"))

    try:
        code = getattr(engine, operation)(extra_args=ctx.args, **kwargs)
    except ComposeError as exc:
        raise _fail("❌ {}".format(exc), EXIT_DOCKER) from exc

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
        _ensure_env(shared)
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
        raise _fail("❌ {}".format(exc), EXIT_CONFIG) from exc


# ---------------------------------------------------------------------------
# test-model
# ---------------------------------------------------------------------------


def _report_available_models(shared: Context, port: int) -> "typer.Exit":
    """Explain which model ids ``test-model`` and ``stress`` would accept.

    A model id is long, case-sensitive and easy to mistype, so refusing with a
    bare "missing argument" would send the user to another command to find the
    answer. The registry is the authority, so it is quoted rather than
    config.yaml: llama-swap may be serving something the local file no longer
    describes.
    """
    lines = ["❌ Missing argument 'MODEL_NAME'."]

    status = health.check_gateway(port)

    if not status.online:
        lines.append(
            "   The gateway on port {} could not be reached, so the available "
            "models are unknown.".format(port)
        )
        if status.error:
            lines.append("   ↳ {}".format(status.error))
    elif not status.models:
        lines.append(
            "   The gateway on port {} has no registered models.".format(port)
        )
    else:
        lines.append("   Available models on port {}:".format(port))
        for model in status.models:
            lines.append("     - {}".format(model.id))

    return _fail("\n".join(lines), EXIT_USAGE)


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
        raise _fail("❌ {}".format(exc), EXIT_CONFIG) from exc

    # Checked here rather than by making the argument required, so the refusal
    # can name the ids that would have worked. It stays a usage error: no test
    # was run. It precedes --dry-run for the same reason.
    if model_name is None:
        raise _report_available_models(shared, port)

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

# Warm-up paces its retry attempts; the interval is deliberately short because
# a load in progress surfaces as a connection error within seconds, not a
# long hang.
_WARMUP_RETRY_INTERVAL = 5.0


def _stress_send(
    port: int,
    model_id: str,
    prompt: str,
    max_tokens: int,
    timeout: float,
) -> "Callable[[], 'health.ChatOutcome']":
    """The one-argument-free ``send`` that warm-up and the runner both call.

    Binds the gateway call so the stress module never learns the wire format
    or the port; ``chat_once`` already never raises for a failed request.
    """
    def send() -> "health.ChatOutcome":
        return health.chat_once(
            port=port,
            model_id=model_id,
            prompt=prompt,
            max_tokens=max_tokens,
            timeout=timeout,
        )

    return send


def _stamp_report(
    report: "StressReport",
    prompt: str,
    max_tokens: int,
    requests: int,
) -> None:
    """Fill the metadata fields the runner does not know.

    ``run_stress`` builds the report without the run's parameters, so the CLI
    stamps them in before rendering; the timestamp is the run's start, not the
    print time, so the report reads identically however late it is shown.
    """
    report.started_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    report.prompt = prompt
    report.max_tokens = max_tokens
    report.requests_per_level = requests
    clean = [
        level.concurrency
        for level in report.levels
        if level.failed == 0
    ]
    report.max_clean_concurrency = max(clean) if clean else None


def _any_level_failed(report: "StressReport") -> bool:
    return any(level.failed for level in report.levels)


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
        DEFAULT_PROMPT, "--prompt", help="Fixed prompt, identical for every request."
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

    try:
        port = shared.resolve_port(llm_port)
    except ConfigError as exc:
        raise _fail("❌ {}".format(exc), EXIT_CONFIG) from exc

    # Same reasoning as test-model: checked here so the refusal can list the
    # registry, and it precedes --dry-run for the same reason.
    if model_name is None:
        raise _report_available_models(shared, port)

    if shared.dry_run:
        # --dry-run precedes the probe: the probe itself is a network request,
        # so announcing the plan must not touch the gateway at all.
        body = health.build_chat_request(model_name, prompt, max_tokens)
        derived = log_path(shared.root, model_name, datetime.utcnow())
        shared.echo("Would stress {}:".format(model_name))
        shared.echo("  levels: {}".format(", ".join(str(l) for l in concurrency_levels(max_concurrency))))
        shared.echo("  requests per level: {}".format(requests))
        shared.echo("  gateway port: {}".format(port))
        shared.echo("  log file: {}".format(derived))
        shared.echo(health.format_request(port, body))
        return

    # --json must be pipeable, so nothing decorative may precede it.
    if not as_json:
        _banner(shared)

    status = health.check_gateway(port)
    availability = check_model_available(status, model_id=model_name)

    if availability.verdict == "unknown_model":
        lines = [
            "❌ Model {!r} is not registered on the gateway at port {}.".format(
                model_name, port
            )
        ]
        if availability.available:
            lines.append("   Available models:")
            for model_id in availability.available:
                lines.append("     - {}".format(model_id))
        else:
            lines.append(
                "   The registry on port {} is empty.".format(port)
            )
        raise _fail("\n".join(lines), EXIT_USAGE)

    if availability.verdict == "unreachable":
        # The gateway's own text is the diagnosis; paraphrase would lose it.
        raise _fail(
            "❌ The gateway on port {} could not be reached: {}".format(
                port, availability.reason or "no reason reported"
            ),
            EXIT_STRESS_UNAVAILABLE,
        )

    send = _stress_send(port, model_name, prompt, max_tokens, timeout)

    if no_warmup:
        warm_up_result = WarmUpResult(
            ok=True, attempts=0, elapsed_seconds=0.0, error=None
        )
    else:
        shared.detail(
            "warming up {} at http://localhost:{} (budget {}s)".format(
                model_name, port, warmup_timeout
            )
        )
        warm_up_result = warm_up(
            send=send,
            timeout=warmup_timeout,
            retry_interval=_WARMUP_RETRY_INTERVAL,
            sleep=time.sleep,
            now=time.monotonic,
        )
        if not warm_up_result.ok:
            raise _fail(
                "❌ Warm-up failed after {} attempt(s): {}".format(
                    warm_up_result.attempts,
                    warm_up_result.error or "no reason reported",
                ),
                EXIT_STRESS_UNAVAILABLE,
            )

    shared.detail(
        "measuring {} at http://localhost:{} ({} requests per level, timeout {}s)".format(
            model_name, port, requests, timeout
        )
    )
    report = run_stress(
        send=send,
        levels=concurrency_levels(max_concurrency),
        request_count=requests,
        warm_up_result=warm_up_result,
        model_id=model_name,
        port=port,
    )
    _stamp_report(report, prompt, max_tokens, requests)

    if as_json:
        shared.echo(format_report_json(report))
    else:
        shared.echo(format_report(report, use_color=shared.use_color))

    if not no_log_file:
        target = log_file if log_file is not None else log_path(
            shared.root, model_name, datetime.utcnow()
        )
        write_log(
            target,
            format_report(report, use_color=False),
            format_report_json(report),
        )
        shared.detail("log written to {}".format(target))

    if _any_level_failed(report):
        # A run that finished and found failures is a successful measurement;
        # its own code says "I learned something bad" rather than "I learned
        # nothing".
        raise typer.Exit(EXIT_STRESS_FAILURES)


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
        raise _fail(
            "❌ {} already exists; pass --force to regenerate it.".format(
                shared.env_path
            ),
            EXIT_USAGE,
        )

    answers = EnvAnswers(
        llm_port=llm_port,
        hf_home=hf_home,
        data_dir=data_dir,
        gpu_generic=gpu_generic,
        gpu_coder=gpu_coder,
        gpu_embedder=gpu_embedder,
    )

    try:
        _bootstrap_env(shared, answers)
    except ConfigError as exc:
        raise _fail("❌ {}".format(exc), EXIT_CONFIG) from exc
    except PromptError as exc:
        raise _fail("❌ {}".format(exc), EXIT_PROMPT) from exc


# ---------------------------------------------------------------------------
# setup-repo
# ---------------------------------------------------------------------------


def _resolve_github_token(
    shared: Context, token: Optional[str], no_github: bool
) -> str:
    """Decide the GitHub token."""
    if no_github:
        return ""

    if token is not None:
        # A flag-supplied value is authoritative; persist it so flag-less runs
        # are not prompted forever. An explicit empty string returns as-is and
        # never blanks a non-empty stored value.
        _persist_github_token(shared, token)
        return token

    # Consult the .env store before prompting: a non-empty stored token is
    # reused as-is so already-configured machines are not re-prompted. The
    # lookup sits before the --yes / non-interactive guard, matching
    # _resolve_oxylabs.
    stored = env.get(shared.env_path, GITHUB_TOKEN_ENV)
    if stored:
        # The value itself is never echoed.
        shared.echo("🔑 Reusing existing GITHUB_TOKEN from .env")
        return stored

    if shared.assume_yes or not shared.interactive():
        return ""

    wants_github = prompts.confirm(
        "❓ Do you use GitHub and want to map a personal repository token for the agent?",
        default=False,
        assume_yes=shared.assume_yes,
        interactive=shared.interactive(),
    )

    if not wants_github:
        shared.echo("⚠️  Skipping interactive GitHub integration token.")
        shared.echo("💡 Note: If you wish to set this up later, you must manually edit")
        shared.echo("   '.env' and populate GITHUB_TOKEN.")
        return ""

    resolved = prompts.ask_required(
        "🔑 Enter your GitHub Personal Access Token",
        assume_yes=shared.assume_yes,
        interactive=shared.interactive(),
        hide_input=True,
    )
    _persist_github_token(shared, resolved)
    return resolved


def _persist_github_token(shared: Context, token: str) -> None:
    """Store the token in .env, replacing any existing entry."""
    if not token:
        # --github-token "" reaches here via the flag path; treating an empty
        # value as a no-op is what keeps it from blanking a stored token.
        return

    if shared.dry_run:
        shared.echo("would store {} in {}".format(GITHUB_TOKEN_ENV, shared.env_path))
        return

    if env.get(shared.env_path, GITHUB_TOKEN_ENV) == token:
        return

    env.set_value(shared.env_path, GITHUB_TOKEN_ENV, token)
    # The value itself is never echoed.
    shared.echo("⚡ Token accepted and persisted to .env")


def _resolve_oxylabs(
    shared: Context,
    username: Optional[str],
    no_oxylabs: bool,
    password: Optional[str] = None,
) -> Tuple[str, str]:
    """Decide the Oxylabs credentials, returning (username, password)."""
    if no_oxylabs:
        return ("", "")

    if username is not None:
        return (username, password if password is not None else "")

    # Check .env for existing credentials.
    env_username = env.get(shared.env_path, "OXYLABS_USERNAME")
    env_password = env.get(shared.env_path, "OXYLABS_PASSWORD")
    if env_username and env_password:
        return (env_username, env_password)

    if shared.assume_yes or not shared.interactive():
        return ("", "")

    wants_oxylabs = prompts.confirm(
        "❓ Do you want to use Oxylabs web scraping for documentation lookups?\nSign up at https://dashboard.oxylabs.io/en/overview/scraper",
        default=False,
        assume_yes=shared.assume_yes,
        interactive=shared.interactive(),
    )

    if not wants_oxylabs:
        shared.echo("⚠️  Skipping Oxylabs web scraping setup.")
        shared.echo("💡 Note: If you wish to set this up later, you must manually edit")
        shared.echo("   '.env' and populate OXYLABS_USERNAME and OXYLABS_PASSWORD.")
        return ("", "")

    resolved_username = prompts.ask_required(
        "🔑 Enter your Oxylabs Username",
        assume_yes=shared.assume_yes,
        interactive=shared.interactive(),
        hide_input=False,
    )
    resolved_password = prompts.ask_required(
        "🔑 Enter your Oxylabs Password",
        assume_yes=shared.assume_yes,
        interactive=shared.interactive(),
        hide_input=True,
    )
    shared.echo("⚡ Credentials accepted and persisted to .env")
    env.set_value(shared.env_path, "OXYLABS_USERNAME", resolved_username)
    env.set_value(shared.env_path, "OXYLABS_PASSWORD", resolved_password)
    return (resolved_username, resolved_password)


class _Frontier:
    """The resolved architect-mode provider settings."""

    def __init__(self, api_key: str, model_id: str, use_anthropic: bool) -> None:
        self.api_key = api_key
        self.model_id = model_id
        self.use_anthropic = use_anthropic


def _resolve_frontier(
    shared: Context,
    settings: config.AnvilSettings,
    anthropic_key: Optional[str],
    no_anthropic: bool,
    want_anthropic: bool,
    anthropic_model: Optional[str],
) -> _Frontier:
    """Decide the architect provider."""
    declined = _Frontier(
        api_key=_UNSET_API_KEY,
        model_id=settings.default_anthropic_model,
        use_anthropic=False,
    )

    if no_anthropic:
        return declined

    # A supplied key, or an explicit --anthropic, is the consent itself.
    enabled = want_anthropic or anthropic_key is not None
    if not enabled:
        enabled = prompts.confirm(
            "❓ Do you want to use an Anthropic frontier model for architect and orchestrator modes?",
            default=False,
            assume_yes=shared.assume_yes,
            interactive=shared.interactive(),
        )

    if not enabled:
        shared.echo(
            "⚠️  Skipping frontier model setup - architect and orchestrator modes "
            "will use the local gateway."
        )
        shared.echo("💡 Note: If you wish to set this up later, edit")
        shared.echo("   'zoo-code-settings.json' and point modeApiConfigs.architect")
        shared.echo("   and modeApiConfigs.orchestrator at the '{}' id.".format(
            settings.anthropic_profile_id))
        return declined

    api_key = anthropic_key
    if api_key is None:
        # An existing key in .env is reused rather than re-requested.
        existing = env.get(shared.env_path, ANTHROPIC_KEY_ENV)
        if existing:
            shared.echo("🔑 Reusing existing {} from .env".format(ANTHROPIC_KEY_ENV))
            api_key = existing

    if api_key is None:
        api_key = prompts.ask_required(
            "🔑 Enter your Anthropic API Key",
            assume_yes=shared.assume_yes,
            interactive=shared.interactive(),
            hide_input=True,
        )

    _persist_anthropic_key(shared, api_key)

    model_id = prompts.choose(
        "Available Anthropic models",
        options=settings.anthropic_models,
        default=settings.default_anthropic_model,
        supplied=anthropic_model,
        assume_yes=shared.assume_yes,
        interactive=shared.interactive(),
    )

    return _Frontier(api_key=api_key, model_id=model_id, use_anthropic=True)


def _persist_anthropic_key(shared: Context, api_key: str) -> None:
    """Store the key in .env, replacing any existing entry."""
    if shared.dry_run:
        shared.echo("would store {} in {}".format(ANTHROPIC_KEY_ENV, shared.env_path))
        return

    if env.get(shared.env_path, ANTHROPIC_KEY_ENV) == api_key:
        return

    env.set_value(shared.env_path, ANTHROPIC_KEY_ENV, api_key)
    # The value itself is never echoed.
    shared.echo("⚡ Key accepted and persisted to .env")


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
        raise _fail("❌ {}".format(exc), EXIT_CONFIG) from exc

    shared.detail("gateway port: {}".format(port))
    shared.detail("coder model: {}".format(topology.coder_id))
    shared.detail("context window: {}".format(topology.coder_context_window))

    try:
        token = _resolve_github_token(shared, github_token, no_github)
        shared.echo("")
        frontier = _resolve_frontier(
            shared,
            settings,
            anthropic_key,
            no_anthropic,
            want_anthropic,
            anthropic_model,
        )
        shared.echo("")
        oxylabs_username, oxylabs_password = _resolve_oxylabs(
            shared, oxylabs_username, no_oxylabs, oxylabs_password
        )
        shared.echo("")
    except PromptError as exc:
        raise _fail("❌ {}".format(exc), EXIT_PROMPT) from exc

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
    )

    try:
        provision.setup_repo(
            path,
            repo_plan,
            dry_run=shared.dry_run,
            echo=shared.echo,
        )
    except ProvisionError as exc:
        raise _fail("❌ {}".format(exc), EXIT_PROVISION) from exc
    except RenderError as exc:
        raise _fail("❌ {}".format(exc), EXIT_CONFIG) from exc


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
    except KeyboardInterrupt:
        typer.echo("")
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(run())
