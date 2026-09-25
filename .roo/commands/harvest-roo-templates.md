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

## Filing the issue

Once the user confirms the shortlist, file exactly one issue for the whole harvest — a single GitHub issue covering all confirmed findings, never one issue per finding. File it with a single `mcp--github--create_issue` call, with owner="iar3-r8" and repo="anvil".

The issue body follows the task template from `templates/roo_template/commands/write-github-task.md`, with its four sections in order: `context`, `goal`, `scope`, and `definition of done`. Every `scope` bullet must name the concrete destination path of every adopted item — a specific file path under `templates/roo_template/`, never a directory.

If the MCP call returns an error, return it to the user and stop — do not retry, do not file a partial issue, and do not proceed past the failure.

## Mirror obligation

The four rule XMLs exist in two copies: the tracked, shipped copy under `templates/roo_template/` and the gitignored local copy under `.roo/`:

- `templates/roo_template/rules-tdd-manager/instructions.xml`
- `templates/roo_template/rules-architect/instructions.xml`
- `templates/roo_template/rules-qna-tester/instructions.xml`
- `templates/roo_template/rules-docs-manager/guidelines.xml`

Any adopted change to a rule XML must land in both copies. `tests/test_rules_mirror.py` asserts that the two copies stay byte-identical and goes red on a half-applied change: `.roo/*` is gitignored, so only the template side ever shows in a diff, and the mirror test is the only thing that catches a change applied to one side only.
