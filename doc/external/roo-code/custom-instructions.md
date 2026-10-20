# Roo Code — custom instructions

Source: https://roocodeinc.github.io/Roo-Code/features/custom-instructions
Retrieved: 2026-10-19 (fetched by the tdd-manager via oxylabs `universal_scraper` during the RTK spike, [plans/rtk-spike.md](../../plans/rtk-spike.md); transcribed here, not re-fetched)

Where Roo Code reads custom instructions from, the rule loading order, and when the legacy files (`.roorules`, `.clinerules`) are used.

Instruction File Locations: global rules (applied across all projects) at
`~/.roo/rules/` and `~/.roo/rules-{modeSlug}/`; workspace rules (project-
specific) take precedence over global rules when they conflict:
- Preferred: `.roo/rules/` directory (read recursively, alphabetical order by
  filename)
- Fallback: single file `.roorules`
- Mode-specific preferred: `.roo/rules-{modeSlug}/` directory
- Mode-specific fallback: single file `.roorules-{modeSlug}`

**Rule Loading Order: 1. Global Rules (from `~/.roo/`), 2. Project Rules (from
`project/.roo/`) — take precedence over global rules when they conflict,
3. [Generic only] Legacy Files (workspace root `.roorules`, `.clinerules`) —
used only if no generic rules directory content was loaded.**

Within each level, mode-specific rules are loaded before general rules.

How Instructions are Combined — the system prompt section:

    ====
    USER'S CUSTOM INSTRUCTIONS
    ...
    Rules:
    # Rules from rules-{modeSlug} directories:
    [Contents of ALL files from ~/.roo/rules-{modeSlug}/ AND .roo/rules-{modeSlug}/ if they exist]
    # Rules from .roorules-{modeSlug}:
    [Contents of .roorules-{modeSlug} file if no mode-specific directories have files]
    # Rules from .rooignore:
    [.rooignore-related instructions if applicable]
    # Agent Rules Standard (AGENTS.md):
    [Contents of AGENTS.md or AGENT.md from workspace root if present and enabled]
    # Rules from rules directories:
    [Contents of ALL files from ~/.roo/rules/ AND .roo/rules/ if they exist]
    # Rules from .roorules:
    [Contents of .roorules file if no general rules directories have files]
    ====

Rule Interaction: mode-specific rules complement global rules rather than
replacing them. AGENTS.md: loaded by default, after mode-specific rules and
`.rooignore`, before generic rules; disabled via `roo-cline.useAgentRules`.
