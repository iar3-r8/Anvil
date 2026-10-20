# token-optimizer — HOOKS

Source: https://github.com/alexgreensh/token-optimizer/blob/main/HOOKS.md
Retrieved: 2026-10-20 (fetched by the tdd-manager via the GitHub MCP during the RTK spike, [plans/rtk-spike.md](../../plans/rtk-spike.md); transcribed here, not re-fetched)

The hook execution model, the full hook inventory, and the security boundaries.

Execution model: host platform tool call -> hook event (PreToolUse,
PostToolUse, SessionStart, etc.) -> python-launcher.sh -> hooks/run.py
(stdlib-only dispatcher) -> consent check (fail-open) -> target script
(measure.py, read_cache.py, etc.) -> local file write (SQLite / JSON /
markdown). run.py always exits 0 (never blocks a tool call); 120-second
timeout per hook; subprocess isolation.

Hook inventory (event -> target script -> purpose): PreToolUse[Read] ->
read_cache.py (detect redundant file reads, serve structure maps);
PreToolUse[Bash] -> bash_hook.py (silent, no permission decision; bash output
compressed PostToolUse); PreToolUse[Agent|Task] -> checkpoint before
sub-agent fan-out; PreToolUse[mcp__.*] -> refetch_guard.py (deny exact
duplicate MCP call after a large result was archived); PreCompact (x3) ->
compaction instructions + checkpoint capture + read-cache clear;
SessionStart -> consolidated dispatcher (ensure-health, cache warm,
compact-restore, checkpoint pointer); StopFailure -> checkpoint on failure;
UserPromptSubmit -> continuity/verbosity/quality-cache work; PostToolUse ->
consolidated dispatcher (bash output compression, result archiving for Bash/
Read/Glob/Grep/Agent/mcp__.*, context-intel scoring, read-cache
invalidation, quality-cache update); Stop -> checkpoint + session-end flush +
keepwarm-arm; SessionEnd -> full session flush + dashboard regeneration;
PostCompact -> quality-cache re-warm; CwdChanged -> read-cache clear.

Security boundaries: no shell execution (list args, never shell=True; rejects
shell metacharacters; whitelist env vars; no hook approves a command); path
traversal protection; consent gate (fail-open); data isolation (hooks write
only to their own data directories). ensure-health writes to the host
settings.json: cleanupPeriodDays, subagentPromptCacheTtl (opt-in), daemon
config. Zero network calls in the shipped hook tree.

The hooks are registered in the host platform's hook system (Claude Code
settings.json hooks, per-adapter plugin dirs for the other platforms) — the
mechanism is the agent's hook API, not a rules file.
