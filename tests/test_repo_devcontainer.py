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
DEVCONTAINER_JSON = REPO_ROOT / ".devcontainer" / "devcontainer.json"
NETWORK = "llm-network"


def _load_devcontainer():
    return json.loads(DEVCONTAINER_JSON.read_text(encoding="utf-8"))


def _compose_service(name):
    """Return the named service from the real docker-compose.yml."""
    data = yamlio.load(COMPOSE_YAML)
    services = data.get("services") or {}
    assert name in services, "docker-compose.yml must define service {!r}".format(name)
    return services[name]


class TestDevcontainerJoinsLlmNetwork(unittest.TestCase):
    """The sandbox container shares the gateway's bridge network."""

    def test_run_args_use_the_llm_network(self):
        run_args = _load_devcontainer()["runArgs"]

        self.assertIn("--network={}".format(NETWORK), run_args)

    def test_run_args_no_longer_use_host_networking(self):
        """--network=host would silently break the container-name URLs again."""
        run_args = _load_devcontainer()["runArgs"]

        self.assertNotIn("--network=host", run_args)


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
