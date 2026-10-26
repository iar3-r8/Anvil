# docker network create — the `--internal` flag

Source URL: https://docs.docker.com/reference/cli/docker/network/create/
Fetched: 2026-10-26

Why this page is saved: issue #51 asks us to "decide deliberately whether the
container needs network access beyond the llama-swap gateway". This page is the
authority on what `--internal` actually does, and the answer constrains the
design: an internal network is isolated **as a network**, not per-container, so
"reach llama-swap but nothing else" means attaching the gateway to an internal
network — it is not a flag on the sandbox container alone.

## The load-bearing quote

> ### Network internal mode (--internal)
>
> Containers on an internal network may communicate between each other, but not
> with any other network, as no default route is configured and firewall rules
> are set up to drop all traffic to or from other networks. Communication with
> the gateway IP address (and thus appropriately configured host services) is
> possible, and the host may communicate with any container IP directly.
>
> By default, when you connect a container to an `overlay` network, Docker also
> connects a bridge network to it to provide external connectivity. If you want
> to create an externally isolated `overlay` network, you can specify the
> `--internal` option.

## What follows for the sandbox

- `--internal` is a **network-creation** option, not a `docker run` option. The
  options table lists it under `docker network create [OPTIONS] NETWORK`:
  `--internal` — "Restrict external access to the network".
- "no default route is configured and firewall rules are set up to drop all
  traffic to or from other networks" is the egress control: an agent inside
  cannot `curl | sh` from the internet, because there is no route off the
  network.
- Containers on the same internal network still reach each other, so a sandbox
  and llama-swap **both** attached to one internal network can talk while
  neither can reach the internet.
- Anvil's existing `llm-network` is **not** internal (`docker-compose.yml`
  declares it with no `internal:` key), so attaching the sandbox to it as-is
  grants full egress.

## Supporting fact from the bridge-driver page

Source URL: https://docs.docker.com/engine/network/drivers/bridge/

> **User-defined bridges provide automatic DNS resolution between containers.**
> […] On a user-defined bridge network, containers can resolve each other by
> name or alias.

So name resolution of `llama-swap` survives on a user-defined network; it is a
property of the user-defined bridge, not of external connectivity. The same page
confirms the default is the opposite of what a sandbox wants:

> Uses masquerading to give containers external network access.
