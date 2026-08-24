"""Anvil implementation package.

The ``anvil`` entrypoint is a thin bootstrap that provisions a managed virtual
environment and then delegates here. All behaviour lives in focused modules:

    yamlio     - the only module permitted to import ``yaml``
    env        - safe ``.env`` read/write
    config     - load and validate ``anvil.yaml``
    render     - emit config.yaml / zoo-code-settings.json / mcp.json
    compose    - docker compose invocation
    health     - gateway and model status probing
    stress     - concurrent-load measurement against a live gateway
    prompts    - interactive input, always bypassable by flags
    provision  - setup-repo orchestration
    cli        - typer wiring
"""

__version__ = "2.0.0-dev"

MIN_PYTHON = (3, 8)
