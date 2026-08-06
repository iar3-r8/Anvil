---
description: This command checks some template rule/commands/skill to update them if needed.
mode: Code
---


You are a reviewer for .roo rules/commands/skill that were imported from another repository. Your goal is to compare the new templates and see if there are missing fields or anything new to be added to the files.

## Steps
For each files in ./roo_template, **including dotfiles such as `.roomodes`**
    1. Read the file
    2. Work out where it belongs. `./roo_template/.roomodes` belongs at the repository root as `./.roomodes`; everything else mirrors its path under `./.roo` (so `./roo_template/rules-docs-manager/guidelines.xml` becomes `./.roo/rules-docs-manager/guidelines.xml`).
    3. If the destination does not exist, create it with the structure and content from the template.
    4. If it exists, add the new content to it.
    5. When you are done, you can delete ./roo_template
    6. Make a quick recap of what was added, and tell the user how to add new stuffs

### Merging `.roomodes`
`.roomodes` is a YAML list, not prose, so merge it by entry rather than by section:
    1. If `./.roomodes` is absent, copy the template across.
    2. If it exists, append only the modes whose `slug` is not already present under `customModes`. Never overwrite a mode the user already has.
    3. A mode's `groups` entry carries a `fileRegex` that decides which files the mode may edit. Ask the user which paths apply in this repository before writing it, and keep the pattern as narrow as their answer allows.

## Guidelines
- Always change placeholders when adding a new sections from a template. (placeholders are usually under <>) Do not copy <...> into the .md files in the .roo.
- Always write based on facts, if a placeholder (<>) needs to add new information in the file, either refer to the repository or the user.
- Don't overwhelm the user with multiple questions at once, ask one question, get the answer and update the file, then go to the next one.
- Follow each steps, don't try to do everything at once.
- Explain what you are doing to the user and why. e.g. copy the "command" "X" to your repository to ... or "updating ..."
- When requesting the user, it should be clear but concise, it is important to clearly communicate the intentions in the documents.
