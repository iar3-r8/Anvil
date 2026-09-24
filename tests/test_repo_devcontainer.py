"""Tests for the provisioned devcontainer and the compose network.

The provisioned devcontainer (``templates/devcontainer/devcontainer.json``)
reaches the LLM stack through the host instead of joining the compose
network: ``--add-host=host.docker.internal:host-gateway`` and no
``--network`` argument. That is what lets the container-target Zoo Code
settings address the gateway and Qdrant at ``host.docker.internal`` plus the
host-mapped ports.

These tests load the *real* template file and ``docker-compose.yml`` — the
same way ``tests/test_repo_config.py`` loads the real ``config.yaml`` — so a
drift back to joining a compose network or to host networking is caught.
"""

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import yamlio  # noqa: E402


COMPOSE_YAML = REPO_ROOT / "docker-compose.yml"
TEMPLATE_DEVCONTAINER_JSON = REPO_ROOT / "templates" / "devcontainer" / "devcontainer.json"
NETWORK = "llm-network"
ADD_HOST_ARG = "--add-host=host.docker.internal:host-gateway"


def _load_devcontainer():
    return json.loads(TEMPLATE_DEVCONTAINER_JSON.read_text(encoding="utf-8"))


def _compose_service(name):
    """Return the named service from the real docker-compose.yml."""
    data = yamlio.load(COMPOSE_YAML)
    services = data.get("services") or {}
    assert name in services, "docker-compose.yml must define service {!r}".format(name)
    return services[name]


class TestTemplateDevcontainerUsesHostGatewayAddressing(unittest.TestCase):
    """The provisioned template devcontainer reaches the gateway via host-gateway."""

    def test_run_args_have_host_gateway_add_host(self):
        run_args = _load_devcontainer()["runArgs"]

        self.assertIn(ADD_HOST_ARG, run_args)

    def test_run_args_have_no_network_flag(self):
        """Any --network entry (host or bridge) would break host-gateway addressing."""
        run_args = _load_devcontainer()["runArgs"]

        self.assertFalse(
            any(arg.startswith("--network") for arg in run_args),
            "unexpected --network flag in runArgs: {}".format(run_args),
        )


class TestComposeServicesAreOnTheLlmNetwork(unittest.TestCase):
    """The gateway services talk to each other by name over llm-network;
    the devcontainer sandbox does not join that network and reaches the
    services via the host's published ports."""

    def test_llama_swap_is_on_the_network(self):
        self.assertIn(NETWORK, _compose_service("llama-swap").get("networks") or [])

    def test_qdrant_is_on_the_network(self):
        self.assertIn(NETWORK, _compose_service("coder_qdrant").get("networks") or [])

    def test_network_is_declared(self):
        data = yamlio.load(COMPOSE_YAML)

        self.assertIn(NETWORK, data.get("networks") or {})


if __name__ == "__main__":
    unittest.main()
