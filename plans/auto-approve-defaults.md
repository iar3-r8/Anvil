# Enable Auto-Approves by Default

## Intake
Direct instruction: when setting up the repo, the zoo code setting should enable all the auto-approves by default, and add destructive command guard.

## Behaviours

### Behaviour 1: All alwaysAllow* settings true ✅ done
- **Input**: render.zoo_code_settings() with any valid parameters
- **Output**: globalSettings has all 10 alwaysAllow* keys set to true
- **Settings**: alwaysAllowReadOnly, alwaysAllowReadOnlyOutsideWorkspace, alwaysAllowWrite, alwaysAllowWriteOutsideWorkspace, alwaysAllowWriteProtected, alwaysAllowMcp, alwaysAllowModeSwitch, alwaysAllowSubtasks, alwaysAllowExecute, alwaysAllowFollowupQuestions
- **Edge cases**: applies to both accepted (anthropic) and declined (local) render paths

### Behaviour 2: followupAutoApproveTimeoutMs 20000 ✅ done
- **Input**: render.zoo_code_settings() with any valid parameters
- **Output**: globalSettings.followupAutoApproveTimeoutMs is 20000 (was 60000)
- **Edge cases**: same timeout for both accepted and declined paths

### Behaviour 3: Deny destructive git commands ✅ done
- **Input**: render.zoo_code_settings() with any valid parameters
- **Output**: globalSettings.deniedCommands includes "git reset --hard" and "git push --force"
- **Edge cases**: existing allowedCommands remain unchanged; both accepted and declined paths
