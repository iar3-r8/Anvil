# RTK — overview

Source: https://www.rtk-ai.app/docs/
Retrieved: 2026-10-19 (fetched by the tdd-manager via oxylabs `universal_scraper` during the RTK spike, [plans/rtk-spike.md](../../plans/rtk-spike.md); transcribed here, not re-fetched)

What RTK is, how its PreToolUse hook rewrites commands, what "savings" measure, and the two optional layers (the engine and the RTK Proxy).

RTK is a CLI proxy that sits between your AI assistant and your development
tools. It filters command output before it reaches the LLM, keeping only what
matters and discarding boilerplate, progress bars, and noise. Result: fewer
bash output bytes reaching the LLM per command, without changing how you work.
You run `git status` as usual — RTK's hook intercepts it, filters the output,
and the LLM sees a compact 3-line summary instead of 40 lines.

How it works:

    Your AI assistant runs:  git status
    ↓
    Hook intercepts (PreToolUse)
    ↓
    rtk git status  (transparent rewrite)
    ↓
    Raw output: 40 lines     →     Filtered: 3 lines
    ↓
    LLM sees the compact output

Zero config changes to your workflow. The hook handles everything
automatically.

What the savings mean: RTK reduces **bash output bytes** — the output a shell
command sends back before your agent reads it. That is not the same as
reducing your bill by the same amount. Bash output is one contributor to input
tokens, alongside your prompt, the system prompt and conversation history.
Input tokens are in turn only part of the bill, which also counts output
tokens. The reduction dilutes at every step.

What RTK optimizes: dozens of commands across all major ecosystems — Git,
Cargo/Rust, JavaScript, Python, Go, Ruby, .NET, Docker/Kubernetes, and more.

Measure your savings: `rtk gain` (total savings across all sessions),
`rtk gain --daily`, `rtk gain --weekly`.

Analyze your usage: `rtk discover` (find commands that ran without RTK),
`rtk session` (RTK adoption rate per Claude Code session).

Go further: two optional layers sit on top of the hooks, neither changes
anything until you opt in:
- **The engine** — everything RTK does is expressed in one composable
  `pipeline.toml`: which commands get rewritten, what happens to a tool's
  output, what the proxy compresses. With no pipeline file you are on
  `rtk:default` and nothing changes.
- **The RTK Proxy** — a local daemon that runs the pipeline on the API traffic
  itself, one layer above bash output. Ships as its own download.
