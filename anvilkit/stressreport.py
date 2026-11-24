"""The stress command's report logic: the warm-up and level event printing and the report stamping that the stress handler delegates to."""

import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

import typer

from . import health, stress
from .cliexit import (
    EXIT_CONFIG,
    EXIT_OK,
    EXIT_STRESS_FAILURES,
    EXIT_STRESS_UNAVAILABLE,
    EXIT_USAGE,
    fail,
)
from .config import ConfigError

if TYPE_CHECKING:  # typing only: never imported at runtime, so the import
    # direction stays one-way (no family module imports cli)
    from .cli import Context


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
    report: "stress.StressReport",
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


def _any_level_failed(report: "stress.StressReport") -> bool:
    return any(level.failed for level in report.levels)


def _print_warmup_attempt(
    shared: "Context", attempt: "stress.WarmUpAttempt"
) -> None:
    """One indented line per failed warm-up attempt.

    ``will_retry`` is the engine's own decision, so the line promises another
    attempt only when one is really queued; a missing error reads as
    ``no reason reported`` rather than an empty field.
    """
    line = "  warm-up attempt {} failed after {:.1f}s: {}".format(
        attempt.attempt,
        attempt.elapsed_seconds,
        attempt.error or "no reason reported",
    )
    if attempt.will_retry:
        line += "; retrying in {:g}s".format(_WARMUP_RETRY_INTERVAL)
    shared.echo(line)


def _print_level_event(shared: "Context", event: "stress.LevelEvent") -> None:
    """The default one-line-per-level start and finish.

    The finish line is printed even for an all-failed level: zero successes
    is a finding, not a reason to stay silent.
    """
    if event.phase == "start":
        shared.echo(
            "Level {}: sending {} requests".format(event.concurrency, event.requests)
        )
    else:
        summary = event.summary
        if summary is None:
            # A finish always carries its summary; without one there is
            # nothing truthful to print.
            return
        shared.echo(
            "Level {}: {}/{} ok, {} failed".format(
                event.concurrency,
                summary.succeeded,
                event.requests,
                summary.failed,
            )
        )


def run_stress_command(
    shared: "Context",
    banner: Callable[["Context"], None],
    report_available_models: Callable[["Context", int], "typer.Exit"],
    model_name: Optional[str],
    max_concurrency: int,
    requests: int,
    prompt: str,
    max_tokens: int,
    timeout: float,
    warmup_timeout: float,
    no_warmup: bool,
    log_file: Optional[Path],
    no_log_file: bool,
    llm_port: Optional[int],
    as_json: bool,
) -> int:
    """Everything the ``stress`` handler does below flag parsing.

    ``banner`` and ``report_available_models`` are the two cli.py helpers the
    body reaches past its own module: cli.py stays the only importer of cli,
    and the handler keeps resolving them in its own namespace. Failure paths
    raise ``typer.Exit`` (usage, config or unavailable) exactly as the handler
    always has; only a finished run returns, with the exit code ``run()``
    surfaces.
    """
    try:
        port = shared.resolve_port(llm_port)
    except ConfigError as exc:
        raise fail("❌ {}".format(exc), EXIT_CONFIG) from exc

    # Same reasoning as test-model: checked here so the refusal can list the
    # registry, and it precedes --dry-run for the same reason.
    if model_name is None:
        raise report_available_models(shared, port)

    if shared.dry_run:
        # --dry-run precedes the probe: the probe itself is a network request,
        # so announcing the plan must not touch the gateway at all.
        body = health.build_chat_request(model_name, prompt, max_tokens)
        derived = stress.log_path(shared.root, model_name, datetime.utcnow())
        shared.echo("Would stress {}:".format(model_name))
        shared.echo("  levels: {}".format(", ".join(str(l) for l in stress.concurrency_levels(max_concurrency))))
        shared.echo("  requests per level: {}".format(requests))
        shared.echo("  gateway port: {}".format(port))
        shared.echo("  log file: {}".format(derived))
        shared.echo(health.format_request(port, body))
        return EXIT_OK

    # --json must be pipeable, so nothing decorative may precede it.
    if not as_json:
        banner(shared)

    status = health.check_gateway(port)
    availability = stress.check_model_available(status, model_id=model_name)

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
        raise fail("\n".join(lines), EXIT_USAGE)

    if availability.verdict == "unreachable":
        # The gateway's own text is the diagnosis; paraphrase would lose it.
        raise fail(
            "❌ The gateway on port {} could not be reached: {}".format(
                port, availability.reason or "no reason reported"
            ),
            EXIT_STRESS_UNAVAILABLE,
        )

    send = _stress_send(port, model_name, prompt, max_tokens, timeout)

    if no_warmup:
        warm_up_result = stress.WarmUpResult(
            ok=True, attempts=0, elapsed_seconds=0.0, error=None
        )
    else:
        shared.detail(
            "warming up {} at http://localhost:{} (budget {}s)".format(
                model_name, port, warmup_timeout
            )
        )
        if not as_json:
            shared.echo(
                "Warming up {} at http://localhost:{}\u2026".format(model_name, port)
            )
        # --json passes None rather than a quiet printer: with nothing that
        # could print, the JSON document being the first byte on stdout is
        # structural, not a discipline.
        warm_up_result = stress.warm_up(
            send=send,
            timeout=warmup_timeout,
            retry_interval=_WARMUP_RETRY_INTERVAL,
            sleep=time.sleep,
            now=time.monotonic,
            on_attempt=None if as_json else lambda a: _print_warmup_attempt(shared, a),
        )
        if not warm_up_result.ok:
            raise fail(
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
    report = stress.run_stress(
        send=send,
        levels=stress.concurrency_levels(max_concurrency),
        request_count=requests,
        warm_up_result=warm_up_result,
        model_id=model_name,
        port=port,
        on_level=None if as_json else lambda e: _print_level_event(shared, e),
    )
    _stamp_report(report, prompt, max_tokens, requests)

    if as_json:
        shared.echo(stress.format_report_json(report))
    else:
        shared.echo(stress.format_report(report, use_color=shared.use_color))

    if not no_log_file:
        target = log_file if log_file is not None else stress.log_path(
            shared.root, model_name, datetime.utcnow()
        )
        stress.write_log(
            target,
            stress.format_report(report, use_color=False),
            stress.format_report_json(report),
        )
        shared.detail("log written to {}".format(target))

    if _any_level_failed(report):
        # A run that finished and found failures is a successful measurement;
        # its own code says "I learned something bad" rather than "I learned
        # nothing".
        return EXIT_STRESS_FAILURES

    return EXIT_OK
