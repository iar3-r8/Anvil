# RTK — editions and licensing

Source: https://www.rtk-ai.app/docs/resources/editions/
Retrieved: 2026-10-19 (fetched by the tdd-manager via oxylabs `universal_scraper` during the RTK spike, [plans/rtk-spike.md](../../plans/rtk-spike.md); transcribed here, not re-fetched)

The three RTK downloads, their licences, what the Apache-2.0 (`rtk-oss`) edition leaves out, and the BUSL Additional Use Grant terms.

RTK ships as **three downloads**.

| Download | Binary | Licence | Contents |
| --- | --- | --- | --- |
| `rtk-<target>` | `rtk` | Apache-2.0 + BUSL-1.1 | Hook core, every command filter, **and** the compression engine |
| `rtk-oss-<target>` | `rtk` | Apache-2.0 only | Hook core and every command filter. No engine. |
| `rtk-proxy-<target>` | `rtk-proxy` | BUSL-1.1 | The RTK Proxy daemon. Never bundled with either `rtk`. |

The two `rtk` downloads install a binary with the **same name**, so hooks,
scripts and agent configuration work unchanged across editions. They cannot be
installed side by side.

Most people want the default `rtk` — the complete tool, free for production
use. Install the Apache-2.0 edition if your organisation requires that every
binary it runs carry an OSI-approved licence, or if you intend to redistribute
RTK as part of a commercial offering. Add `rtk-proxy` only if you want the
RTK Proxy daemon.

What the Apache-2.0 edition leaves out — same binary minus the compression
engine:

| Absent | What you lose |
| --- | --- |
| `rtk pipeline` | Inspecting, validating, explaining and benchmarking pipelines |
| `rtk methods` | Listing registered compression methods |
| `rtk tasks` | Listing and running delegation tasks |
| PostToolUse compression | Compressing the output of an agent's own `Read` and MCP tools |
| Pipeline files | A `pipeline.toml` on disk is inert, exactly as in a build predating the engine |

What stays is the part you use all day. The PreToolUse rewrite hook — the
mechanism that turns your agent's `git status` into `rtk git status` — is
Apache-2.0 and behaves identically. So does every command filter, `rtk init`,
`rtk gain`, `rtk discover`, `rtk session`, `rtk recall`, and `rtk llm-proxy`.

The practical difference: bash output is filtered exactly as in the full
edition; output your agent reads through its *own* file and MCP tools is not.

Installing the Apache-2.0 edition:
`curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | RTK_EDITION=oss sh`
or `brew install rtk-ai/tap/rtk-oss`; Debian/RPM packages published as
`rtk-oss`. The two editions cannot coexist — both install `/usr/bin/rtk`.
From source: `cargo build --release --no-default-features` removes
`rtk-engine` from the dependency graph entirely — no BUSL-licensed code is
compiled into the binary.

Licence terms:
- **Apache-2.0** covers the `rtk` CLI and its filters.
- **BUSL-1.1** covers the compression engine and the `rtk-proxy` daemon.

The BUSL Additional Use Grant permits **free production use**, including
running the daemon. What it does not permit is offering RTK — or a derivative
— to third parties as a commercial product or service. For resale, embedding
in a commercial offering, or any use the grant does not cover, contact
contact@rtk-ai.app. Licence files travel with every download: the `rtk`
archive carries `LICENSE` and `LICENSE-ENGINE`, the Apache-2.0 archive carries
`LICENSE` alone, and the daemon archive carries its own `LICENSE`.
