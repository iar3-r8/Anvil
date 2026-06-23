---
description: Pull and execute GitHub tasks with collaborative planning
---

Pulls a specific task from GitHub, collaboratively plans the approach, then executes it step by step.

**Usage:**
- Provide the GitHub issue number after the command: `/github-task-executor <issue-number>`
- The workflow will fetch the issue, plan the approach together, then execute it

**Example:**
```
/github-task-executor 123
```

**Behavior:**
- Fetches the specified GitHub issue using GitHub CLI
- Parses the task structure (Context, Goal, Scope, Definition of Done)
- **Collaboratively plans the implementation approach with user input**
- Creates a todo list based on the agreed approach and Definition of Done
- Executes each task item systematically
- Provides progress updates and completion status

**Prerequisites:**
- github mcp must be accessible

**Workflow Steps:**

1. **Fetch GitHub Issue from mcp server**

2. **Parse Task Structure**
   - Extract Context, Goal, Scope sections
   - Parse Definition of Done checklist
   - Identify Solutions to explore

3. **Collaborative Planning Phase** ⭐
   - Present the parsed task to the user for review
   - Ask clarifying questions about requirements and approach
   - Brainstorm implementation strategies together
   - Discuss potential challenges and edge cases
   - Agree on the technical approach before proceeding
   - Get explicit user confirmation on the planned approach

4. **Create Execution Plan**
   - Convert Definition of Done items to todo list
   - Incorporate insights from collaborative planning
   - Prioritize tasks based on dependencies and agreements
   - Set initial status for all items to "pending"

5. **Execute Tasks**
   - Work through todo items sequentially
   - Mark items as "in_progress" when starting
   - Mark items as "completed" when finished
   - Handle errors and provide rollback options


**Collaborative Planning Guidelines:**
- Always present the parsed task clearly before asking questions
- Ask at least 2-3 clarifying questions about requirements and approach
- Encourage discussion of multiple implementation strategies
- Identify potential risks, dependencies, or edge cases early
- Never proceed to execution without explicit user agreement
- Document the agreed approach in the planning summary

**Task Execution Guidelines:**
- Always read existing files before making changes
- Use minimal, focused edits following existing code style
- Test changes when possible
- Add regression tests for bug fixes
- Update documentation when relevant
- **Ensure all tests pass with pytest before completing any task**

**Error Handling:**
- If issue doesn't exist, provide clear error message
- If task format is invalid, prompt for manual parsing
- If execution fails, provide rollback steps
- Always preserve original code state

**Output:**
- Real-time progress updates
- Completion summary with changes made
- Links to modified files/commits
- Updated GitHub issue status

**Automatic Features:**
- Detects file paths mentioned in Scope section
- Automatically reads relevant files before editing
- Validates completion of each Definition of Done item
- Provides copy-pastable commands for manual verification
- **Run tests to verify all tests pass before task completion**
