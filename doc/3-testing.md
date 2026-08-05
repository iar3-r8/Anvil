# Testing

## Overview

This repository includes automated tests to verify the synchronization between `config.yaml` (the single source of truth) and the generated `zoo-code-settings.json` template injection.

## Running Tests

### Context Window Synchronization Test

Verifies that the coder model's `--max-model-len` value in `config.yaml` is correctly extracted and injected into the generated settings file.

```bash
./tests/test_context_window.sh
```

**Expected output:**
```
============================================================
Context Window Synchronization Tests
============================================================

[Test 1] config.yaml has --max-model-len for coder model
  ✅ PASS: coder model has --max-model-len defined
[Test 2] Extracted context window equals 262144
  ✅ PASS: extracted value is 262144
...
============================================================
Results: 8 passed, 0 failed
============================================================
```

**Exit codes:**
- `0` - All tests passed
- `1` - One or more tests failed

## What the Tests Verify

| Test | Purpose |
|------|---------|
| 1 | `config.yaml` has `--max-model-len` for the coder model |
| 2 | Extracted value equals expected 262144 |
| 3 | Template uses `${CONTEXT_WINDOW}` placeholder |
| 4 | Template has no hardcoded numeric value |
| 5 | `anvil` script contains the extraction grep pattern |
| 6 | `anvil` script passes value to sed replacement |
| 7 | Full pipeline produces correct substituted value |
| 8 | No placeholder remains after substitution |

### Frontier Model Substitution Test

Verifies that the optional Anthropic frontier model binding for architect mode is rendered correctly for both the accepted and declined paths.

```bash
./tests/test_frontier_model.sh
```

| Test | Purpose |
|------|---------|
| 1-4 | Template exposes the `${LOCAL_PROFILE_ID}`, `${ANTHROPIC_API_KEY}`, `${ANTHROPIC_MODEL_ID}` and `${ARCHITECT_PROFILE_ID}` placeholders |
| 5-6 | Template carries a dormant `anthropic` profile with `"apiProvider": "anthropic"` |
| 7 | Accepted path binds `modeApiConfigs.architect` to `anthropic_profile` |
| 8 | Declined path binds `modeApiConfigs.architect` to the local llama-swap profile id |
| 9-10 | `code`, `ask`, `debug` and `orchestrator` stay on the local profile id in both paths |
| 11 | Accepted path injects the API key and selected model id into the `anthropic` profile |
| 12-13 | No unexpanded placeholders remain in either rendered output |
| 14-15 | Both rendered outputs parse as valid JSON |

## CI Integration

To integrate into a CI pipeline, add the test steps:

```yaml
- name: Run context window tests
  run: ./tests/test_context_window.sh

- name: Run frontier model tests
  run: ./tests/test_frontier_model.sh
```

## When to Run

- Before committing changes to `config.yaml`
- After any modification to the `anvil` script's `setup_repo` function
- After changing `templates/zoo-code-settings.json.template` placeholders or provider profiles
- As part of CI/CD pipeline pre-deployment checks
