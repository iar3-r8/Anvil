---
description: Pull roo rules/commands/modes from another repository into our templates, and file a GitHub issue for the shortlist
mode: Architect
---

## Harvest Roo Templates

Read the roo configuration of another repository, report what our templates lack, and — after the user confirms — file a single GitHub issue for the shortlist.

## Inventory

Read the roo configuration of the other repository from these locations:

- `.roomodes` — agent modes
- `.roo/rules/` — shared always-on rules
- `.roo/rules-*/` — per-mode rules
- `.roo/commands/` — chat commands
- `.roo/skills/` — skills

If a listed source is absent in the other repo, note it as absent and continue — absence of a source is not a finding.
