---
description: Build pull request descriptions following project guidelines
---

## Build Pull Request

**Usage:**
- Use this workflow to create pull request descriptions that follow the project's communication standards
- Focus on clear, concise explanations of changes with proper context

**Guidelines for Pull Request Content:**

### Structure
1. **Context**: Brief explanation of the problem or reason for changes
2. **Changes**: Bullet points of what was modified
3. **Optional**: Technical details if complex changes

### Content Rules
- **Keep it concise**: Use bullet points, avoid long paragraphs
- **Focus on what changed**: Don't include impact/results fields
- **Be specific**: Mention actual file paths (relative to root e.g. src/api/) and key modifications
- **High-level focus**: Focus on major changes, not every small detail or file
- **Use clear language**: Avoid jargon, explain technical concepts simply
- **GitHub format**: Structure for easy copy-paste into GitHub PR description

### Example Format:
```
### Context
[One sentence explaining the problem/reason for changes]

### Changes
- **Brief description**: What was changed
- **Another change**: What was modified
- **Testing**: What tests were added/updated
```

### What to Include
- Problem statement (why the change was needed)
- Specific files modified
- Key functionality changes
- Testing coverage added
- Documentation updates

### What to Exclude
- Impact statements ("fixes the workflow error...")
- Results ("all tests pass...")
- Long technical explanations
- Personal observations

**Execution:**
1. Ask user for context about the changes
2. Gather specific details about what was modified
3. Structure the content according to the guidelines above
4. Provide GitHub-compatible format for easy copy-paste
