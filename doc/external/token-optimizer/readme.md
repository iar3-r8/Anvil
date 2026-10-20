# token-optimizer — README

Source: https://github.com/alexgreensh/token-optimizer (README.md, main)
Retrieved: 2026-10-20 (fetched by the tdd-manager via the GitHub MCP during the RTK spike, [plans/rtk-spike.md](../../plans/rtk-spike.md); transcribed here, not re-fetched)

What token-optimizer is, its eight compression surfaces, session continuity and quality scoring, its positioning against RTK and Headroom, and its licence.

Cut the tokens your AI coding assistant wastes, keep your work alive across
sessions and compactions, and show where every dollar went on a live dashboard.
Most of it runs automatically: install it, run the audit once, and the hooks do
the rest.

Why not just use Headroom or RTK? They compress command output, which covers
15-25% of your context. Token Optimizer covers that plus the other 75%:
bloated configs, unused skills, stale memory, compaction loss, model
misrouting, behavioral waste. Every saving is cache-safe and measured.

Works on: Claude Code, Codex, OpenCode, OpenClaw, Hermes, GitHub Copilot, Pi,
Cursor, Google Antigravity (beta), Grok Build (beta). (No Cline / Roo Code.)
Badge claims: zero dependencies, zero telemetry, Python 3.9+, macOS/Linux/
Windows, license PolyForm Noncommercial.

Runs automatically: Smart Compaction (checkpoints before auto-compact, restore
after), Session Continuity (cross-session hints, cold-resume, checkpoint
scoring), Active Compression (9 features on by default: delta diffs,
skeletons, bash/search compression, lean-output nudges, quality nudges, loop
detection, activity mode, decision extraction), Quality Scoring (7 signals,
grades S-F), Session Database (SQLite, 15 tables, zero network), Progressive
Disclosure (large outputs archived, expand on demand), Context Intel Digest,
Model Routing Nudges.

On request: /token-optimizer (full audit), /token-coach (30-day trends),
quick, route, doctor, savings, report, dashboard, memory-review, expand,
resume-lean.

Compression coverage table (status: supported / partial / not supported):

| Compression surface | Token Optimizer | Headroom | RTK | Boost |
|---|---|---|---|---|
| Bash / command output (git, tests, lint, build, logs) | 113 commands across 25 pattern families, credential-safe; 564 to 115 tokens on a pytest run | SmartCrusher, CodeCompressor, Kompress-v2 | 100+ filters | Command-aware filters |
| Search / grep output | Top hits plus a count; 500 lines to 20 | no | no | — |
| Tabular / JSON output (jq, yq, csvtool, mlr) | Value-preserving columnar | SmartCrusher | no | — |
| File re-reads, delta mode | Diff only; 2,000-token re-read to ~50 | no | no | — |
| File re-reads, structure map | Skeleton of signatures and imports; 720KB to 250 tokens | no | no | — |
| Large tool results (over 4K chars) | Archived to disk, expandable on demand | no | no | — |
| Model output verbosity | Lean-output nudge, cache-safe (savings estimated, not metered) | no | no | no |
| Structural context (configs, skills, MCP, memory) | Per-component audit, each source scored | no | no | no |

Differentiators beyond compression: session continuity survives compaction
(checkpoint + restore); structural waste audit (CLAUDE.md, skills, MCP,
memory); model routing and behavioral coaching (12 detectors); 30-day trend
analysis; 7-signal context quality scoring; loop and spin detection; measures
whether compression helped (local before/after tokens, dollar savings);
fleet-level cross-agent analysis.

Claims on mechanics: hook-wired, fires automatically; full original recoverable
(raw archived, `expand` retrieves, failures never compressed); custom TOML
filters (command-filters.toml); 137 TOKEN_OPTIMIZER_* controls; cache-safe
(never modifies existing context prefix); zero baseline context overhead
(external process, no context injection); zero runtime dependencies (pure
stdlib Python/TypeScript); zero telemetry (nothing leaves the machine);
signed and checksum-verified install (CHECKSUMS.sha256 per release).
Multi-platform row: Claude Code, VS Code, Codex, OpenClaw, OpenCode, Hermes,
Copilot, Cursor, Antigravity; Cowork experimental.

Reported 30-day savings (author's own machine, 1,698 sessions): about $1,396
API-equivalent and 59.6M tokens never sent (~28% of workload), split into
$126 logged actions (metered), $1,124 repeat reads avoided (estimated),
$146 other estimates (estimated). Methodology in BENCHMARK.md.

Active Compression features (all on by default, toggleable): Delta Mode
(re-reads return only what changed, ~20% on re-reads; disable
TOKEN_OPTIMIZER_READ_CACHE_DELTA=0), Structure Map (unchanged code-file
re-reads return a structural skeleton, ~30%; disable
TOKEN_OPTIMIZER_READ_CACHE_MODE=shadow), First-Read Skeleton (v5.12: target
file always served in full on first read; savings come from periphery
skeletons), Bash Output Compression (~10%; 564-token pytest output to 115
tokens; disable TOKEN_OPTIMIZER_BASH_COMPRESS=0), Search Result Compression
(part of bash compression), Lean-Output Nudges (estimated 10-15%, not
counterfactually measured; trigger TOKEN_OPTIMIZER_VERBOSITY_MIN_FILL,
default 25), Quality Nudges (inline note when quality drops; disable
TOKEN_OPTIMIZER_QUALITY_NUDGES=0), Loop Detection (fires at confidence
>=0.7, session cap 2; also edit-compile-fail and inline-script-repeat
detectors).

PreToolUse hooks intercept every Read and Bash call before it enters context;
PostToolUse hooks archive the full original to disk and log a compression
event to SQLite. Nothing is lost, everything retrievable.

Session database: per-session DB (~/.claude/token-optimizer/snapshots/
session-store/<session>.db, 8 tables, WAL, 50MB cap) and trends DB
(snapshots/trends.db, 7 tables). All local, zero network.

Progressive disclosure: large tool results (>4KB) archived to disk, replaced
with preview + retrieval pointer; `expand <key>` retrieves; `expand --search`
full-text search; TOKEN_OPTIMIZER_ARCHIVE_EXEMPT_TOOLS allowlist for
documented large-payload MCP tools.

Smart Compaction: progressive checkpoints at 20/35/50/65/80% fill and quality
drops; context intel digest after compaction (heuristic, <30ms, no LLM call);
decision extraction (capped 10/session) injected as CRITICAL DECISIONS.

Quality scoring: Resource Health (context fill, compaction depth, waste
tokens) + Session Efficiency (stale reads, bloated results, decision density,
agent efficiency); letter grades S(90-100) A(80-89) B(70-79) C(55-69)
D(40-54) F(0-39).

Claude-desktop status bar: a "mod" (Claude Code 2.1.287+, Anthropic mods
feature) drawing quality grade, context fill, cache countdown and usage
limits above the prompt; "VS Code is not supported."

License section (README): **PolyForm Noncommercial 1.0.0**, plus a written
small business permission. Personal / hobby / research / education: full
source, runs locally, no purchase. Small business (fewer than 5 people AND
under $20k/month revenue, whole company): no-cost internal commercial use.
Larger company / commercial use: contact the author; terms scale with company
size.
