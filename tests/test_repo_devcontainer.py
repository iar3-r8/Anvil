"""Tests for the repo-level devcontainer and compose wiring (llm-network).

The devcontainer sandbox joins the gateway's own bridge network
(``llm-network``) instead of running with ``--network=host``.  That is what
lets the provisioned Zoo Code settings address the LLM by container name
(``llama-swap-service:8080``) rather than by ``localhost`` plus the host-side
``LLM_PORT`` mapping.

These tests load the *real* ``.devcontainer/devcontainer.json`` and
``docker-compose.yml`` — the same way ``tests/test_repo_config.py`` loads the
real ``config.yaml`` — so a drift back to host networking is caught.

Container names are asserted from ``docker-compose.yml`` itself (the single
source of truth for ``container_name``), never duplicated by hand here: the
test fails the moment compose and the renderer disagree.
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
    """Both gateway services sit on llm-network, so names resolve across it."""

    def test_llama_swap_is_on_the_network(self):
        self.assertIn(NETWORK, _compose_service("llama-swap").get("networks") or [])

    def test_qdrant_is_on_the_network(self):
        self.assertIn(NETWORK, _compose_service("coder_qdrant").get("networks") or [])

    def test_network_is_declared(self):
        data = yamlio.load(COMPOSE_YAML)

        self.assertIn(NETWORK, data.get("networks") or {})


class TestContainerNamesMatchTheRenderedTargets(unittest.TestCase):
    """The names the renderer emits must exist in docker-compose.yml.

    render.zoo_code_settings(container_target=True) points at
    ``llama-swap-service:8080`` and ``coder_qdrant-service:6333``; if compose
    ever renames a container, this test fails before the sandbox silently
    loses its LLM.
    """

    def test_llama_swap_container_name(self):
        self.assertEqual(
            _compose_service("llama-swap")["container_name"], "llama-swap-service"
        )

    def test_qdrant_container_name(self):
        self.assertEqual(
            _compose_service("coder_qdrant")["container_name"], "coder_qdrant-service"
        )

    def test_llama_swap_exposes_its_internal_gateway_port(self):
        """The container-name URL hardcodes 8080; compose must keep it."""
        ports = _compose_service("llama-swap").get("ports") or []

        self.assertTrue(
            any("8080" in str(p) for p in ports),
            "llama-swap must keep its 8080 port mapping: {}".format(ports),
        )


if __name__ == "__main__":
    unittest.main()
