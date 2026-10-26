"""Tests for the sandbox internal network declared in docker-compose.yml.

``plans/pi-sandbox-image.md``, the Pi sandbox image: the compose file must
declare the internal network the sandbox container rides on, and the
``docker run --network`` token ``anvilkit.pi.pisandbox.run_argv`` emits must be
that same declared name. Asserting both sides in one cycle is what stops the
run side and the compose side drifting apart.

The explicit ``name:`` is what keeps an out-of-Compose ``docker run
--network sandbox-internal`` resolvable: without it, Compose project-prefixes
the real network name, exactly the problem ``llm-network`` already works
around. ``internal: true`` is the property that removes the default route
and drops traffic to other networks (doc/external/docker/
network-create-internal.md), so the sandbox gets no egress while
``llama-swap`` keeps its egress for model pulls on ``llm-network``.

No test in this file touches Docker or the network: the compose file is read
as data via ``anvilkit.yamlio.load`` and ``run_argv`` is a pure argv builder.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit.pi import pisandbox  # noqa: E402
from anvilkit import yamlio  # noqa: E402

COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
REPO_PATH = "/tmp/anvil-sandbox"
TAG = "anvil/sandbox:latest"
NETWORK_KEY = "sandbox-internal"
LLM_NETWORK = "llm-network"
LLAMA_SWAP = "llama-swap"


class SandboxInternalNetworkCase(unittest.TestCase):
    """Shared access to ``docker-compose.yml`` via ``anvilkit.yamlio``."""

    @property
    def data(self):
        try:
            return yamlio.load(COMPOSE_FILE)
        except yamlio.YamlError as exc:
            self.fail("could not parse docker-compose.yml: {}".format(exc))

    @property
    def networks(self):
        networks = self.data.get("networks")
        self.assertIsInstance(
            networks,
            dict,
            "docker-compose.yml has no top-level 'networks:'",
        )
        return networks

    def network(self):
        if NETWORK_KEY not in self.networks:
            self.fail(
                "networks.{} not declared in docker-compose.yml".format(
                    NETWORK_KEY
                )
            )
        entry = self.networks[NETWORK_KEY]
        self.assertIsInstance(
            entry,
            dict,
            "networks.{} must be a mapping, got: {!r}".format(
                NETWORK_KEY, entry
            ),
        )
        return entry

    @property
    def services(self):
        services = self.data.get("services")
        self.assertIsInstance(
            services,
            dict,
            "docker-compose.yml has no top-level 'services:'",
        )
        return services


class SandboxNetworkDeclarationTests(SandboxInternalNetworkCase):
    """The compose side: the internal network is declared with its pinned shape."""

    def test_sandbox_internal_network_carries_internal_true(self):
        self.assertIs(
            self.network().get("internal"),
            True,
            "networks.{} must carry internal: true - the property that "
            "removes the default route and drops traffic to other "
            "networks; got: {!r}".format(NETWORK_KEY, self.network()),
        )

    def test_sandbox_internal_network_declares_an_explicit_name(self):
        self.assertEqual(
            self.network().get("name"),
            NETWORK_KEY,
            "networks.{} must declare an explicit name: {} - without it "
            "Compose project-prefixes the real network and the out-of-"
            "Compose `docker run --network` would not resolve it, as "
            "llm-network already shows; got: {!r}".format(
                NETWORK_KEY, NETWORK_KEY, self.network()
            ),
        )


class LlamaSwapNetworkMembershipTests(SandboxInternalNetworkCase):
    """llama-swap keeps its egress while the sandbox gets none."""

    def test_llama_swap_lists_both_sandbox_internal_and_llm_network(self):
        service = self.services.get(LLAMA_SWAP)
        self.assertIsInstance(
            service,
            dict,
            "service '{}' not defined in docker-compose.yml".format(
                LLAMA_SWAP
            ),
        )
        networks = service.get("networks")
        self.assertIsInstance(
            networks,
            list,
            "service '{}' networks must be a list, got: {!r}".format(
                LLAMA_SWAP, networks
            ),
        )
        self.assertIn(
            NETWORK_KEY,
            networks,
            "service '{}' must list both {} and {} (the sandbox needs a "
            "peer on the internal network); got: {!r}".format(
                LLAMA_SWAP, NETWORK_KEY, LLM_NETWORK, networks
            ),
        )
        self.assertIn(
            LLM_NETWORK,
            networks,
            "service '{}' must keep {} so it retains egress for model "
            "pulls; got: {!r}".format(LLAMA_SWAP, LLM_NETWORK, networks),
        )


class RunArgvNetworkTokenTests(SandboxInternalNetworkCase):
    """The run side: run_argv's --network token equals the declared name."""

    def test_run_argv_network_token_equals_the_declared_network_name(self):
        argv = pisandbox.run_argv(REPO_PATH, TAG)
        self.assertIn(
            "--network",
            argv,
            "run_argv({!r}) must emit --network; got: {!r}".format(
                REPO_PATH, argv
            ),
        )
        token = argv[argv.index("--network") + 1]
        declared = self.network().get("name")
        self.assertEqual(
            token,
            declared,
            "the --network token {!r} emitted by run_argv must equal "
            "networks.{}.name in docker-compose.yml; got declared "
            "name: {!r}".format(token, NETWORK_KEY, declared),
        )


if __name__ == "__main__":
    unittest.main()
