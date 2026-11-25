"""Generate the launch-time role documents into a target repository.

One concern only (``plans/pi-phase12-launch-gen.md``, behaviour 5): turn the
stored profile record plus the six shared ``piprompt`` documents into the
seven files ``<repo>/.pi/roles/`` holds at run start. The six generic
documents come from ``piprompt.all_documents`` and ``project.md`` from
``piproject.project_document`` for the record ``piprofile.load_profile``
returns; all seven land on disk through the existing ``render.role_prompts``
seam, byte-for-byte, so a successful call leaves a repo that passes
``smoke.check_role_prompt``.

Generation is a pure build step: it reads the profile store, assembles the
stem-to-text mapping, and hands it to the write seam. Nothing here opens a
container, touches anything outside ``<repo>/.pi/roles/`` or re-reads disk
after the write.

The function returns the resolved stem-to-text mapping it wrote, so a run
log can archive exactly what was used without re-reading disk.

Stdlib only. One exception type: ``LaunchError``, the module's single
failure point for the error paths its later behaviours raise; nothing in
behaviour 5 raises it yet.
"""

from typing import Dict, Union
from pathlib import Path

from anvilkit import render
from anvilkit.pi import piprofile
from anvilkit.pi import piproject
from anvilkit.pi import piprompt


class LaunchError(Exception):
    """The role documents cannot be generated into the target repository.

    A single exception type will cover every refusal this module raises, so
    callers need only one ``except`` clause. The wrapping of the underlying
    ``RenderError``, ``ProfileError`` and ``ProjectError`` arrives with the
    error-path behaviour; no code in this module raises it yet.
    """


def generate(
    repo_path: Union[str, Path],
    root: Union[str, Path],
    profile_name: str,
) -> Dict[str, str]:
    """Write the seven launch-time role documents into ``<repo>/.pi/roles/``.

    The record stored under ``profile_name`` in ``<root>/profiles.yaml`` is
    loaded through ``piprofile.load_profile``; the document set is the six
    ``piprompt.all_documents()`` stems plus ``project.md`` built from that
    record by ``piproject.project_document``. All seven are written through
    ``render.role_prompts`` with no bytes added or dropped, overwriting any
    file already at the path — a hand edit is a build artifact.

    Returns the seven-entry stem-to-text mapping that was written, so the
    caller can archive the resolved text without re-reading disk.
    """
    record = piprofile.load_profile(root, profile_name)
    documents = dict(piprompt.all_documents())
    documents["project"] = piproject.project_document(record)
    render.role_prompts(repo_path, documents)
    return documents
