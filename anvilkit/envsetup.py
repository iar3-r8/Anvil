"""The init command's .env bootstrap: the section table, the defaults, and the ask-or-default collection that writes the install's .env."""

import os
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Tuple

import typer

from . import env, prompts

if TYPE_CHECKING:  # typing only: never imported at runtime, so the import
    # direction stays one-way (no family module imports cli)
    from .cli import Context

# cli.py keeps its own copy of the separator for its report commands; the
# value must stay byte-identical to it.
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

PORT_ENV = "LLM_PORT"


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
    shared: "Context", answers: EnvAnswers, default_port: int
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


def bootstrap_env(shared: "Context", answers: EnvAnswers) -> None:
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


def ensure_env(shared: "Context", answers: Optional[EnvAnswers] = None) -> None:
    """Run the bootstrap when ``.env`` is absent.

    Python does not need a pre-flight guard, but a fresh clone running
    './anvil up' with no .env would hand docker an unset ${LLM_PORT} and fail
    obscurely - so the convenience is kept, for the commands that actually need
    the file.
    """
    if shared.env_path.is_file():
        return

    bootstrap_env(shared, answers or EnvAnswers())
