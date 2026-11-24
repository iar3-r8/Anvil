"""The model-state reporting shared by status and test-model.

One job: the available-id list, the empty-registry wording and the
unknown-model usage error that the ``test-model`` and ``stress`` handlers
surface when no model id was given. Moved out of ``cli.py`` in
plans/cli-segmentation.md behaviour 6; ``ConfigError`` still maps to exit 3
at the handler, not here.
"""

from typing import TYPE_CHECKING

import typer

from . import health
from .cliexit import EXIT_USAGE, fail

if TYPE_CHECKING:  # typing only: never imported at runtime, so the import
    # direction stays one-way (no family module imports cli)
    from .cli import Context


def report_available_models(shared: "Context", port: int) -> "typer.Exit":
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

    return fail("\n".join(lines), EXIT_USAGE)
