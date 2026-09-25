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

## Comparison

The comparison is one-way against the baseline `templates/roo_template/`. It reports only what the other repository has and our templates lack. Anything that exists in `templates/roo_template/` but not in the other repository is out of scope, and the command never proposes removing or deleting it. A two-way diff was rejected because it would flag every anvil-specific rule as missing from the other repo and drown the signal.

## Classifying findings

Every finding is one of three classes:

- **New file** — a whole new file present in the other repository but absent from `templates/roo_template/`.
- **New section** — a new section within a file that exists on both sides.
- **Divergent wording** — an existing section whose text differs between the two sides.

Divergent wording is shown to the user for judgement and is never adopted, copied, overwritten or rewritten automatically: our templates carry deliberate local edits (the tdd-manager byte ceiling, the architect's package-registry step) that a silent rewrite would revert.

## Confirming the shortlist

Present the classified findings to the user as a shortlist. The user's explicit confirmation is a blocking gate: the command requires the user to confirm the shortlist before it files anything, and it never files the issue until the user confirms. The command stops at the shortlist and waits for the user's go-ahead rather than proceeding on the way past.

If the shortlist is empty — nothing worth importing — the command ends with a report and no issue is filed.
