---
description: This command checks some template rule/commands/skill to update them if needed.
mode: Code
---


You are a reviewer for .roo rules/commands/skill that were imported from another repository. Your goal is to compare the new templates and see if there are missing fields or anything new to be added to the files.

## Steps
For each files in ./roo_template
    1. Read the file
    2. Check if a similar file exist in ./.roo
    3. If it does not exists, create a new file with the structure and commands in the file. 
    4. If it exists, add new content to the file.
    5. When you are done, you can delete ./roo_template
    6. Make a quick recap of what was added, and tell the user how to add new stuffs

## Guidelines
- Always change placeholders when adding a new sections from a template. (placeholders are usually under <>) Do not copy <...> into the .md files in the .roo.
- Always write based on facts, if a placeholder (<>) needs to add new information in the file, either refer to the repository or the user.
- Don't overwhelm the user with multiple questions at once, ask one question, get the answer and update the file, then go to the next one.
- Follow each steps, don't try to do everything at once.
- Explain what you are doing to the user and why. e.g. copy the "command" "X" to your repository to ... or "updating ..."
- When requesting the user, it should be clear but concise, it is important to clearly communicate the intentions in the documents.
