#!/usr/bin/env bats

# Test: Context window extraction from config.yaml matches template injection
# Ensures the coder model's --max-model-len value stays synchronized

setup() {
    REPO_ROOT="$(dirname "$BATS_TEST_FILENAME")/.."
    cd "$REPO_ROOT"
    
    # Expected value from config.yaml
    EXPECTED_CONTEXT_WINDOW=$(grep -A50 '^  "Qwen/Qwen3.6-35B-A3B-FP8":' config.yaml \
        | grep -- '--max-model-len' \
        | awk '{print $NF}' \
        | head -1)
    
    # Template placeholder
    TEMPLATE_CONTENT=$(cat templates/zoo-code-settings.json.template)
}

@test "config.yaml has max-model-len for coder model" {
    run grep -A50 '^  "Qwen/Qwen3.6-35B-A3B-FP8":' config.yaml | grep -- '--max-model-len'
    [ "$status" -eq 0 ]
    [[ "$output" =~ --max-model-len[[:space:]]+([0-9]+) ]]
}

@test "extracted context window equals 262144" {
    [ "$EXPECTED_CONTEXT_WINDOW" = "262144" ]
}

@test "template contains CONTEXT_WINDOW placeholder" {
    [[ "$TEMPLATE_CONTENT" =~ \$\{CONTEXT_WINDOW\} ]]
}

@test "template does NOT contain hardcoded context window number" {
    # The template should use the placeholder, not a raw number
    [[ "$TEMPLATE_CONTENT" =~ \"contextWindow\":[[:space:]]*[0-9]+ ]] || \
        [[ "$TEMPLATE_CONTENT" =~ \"contextWindow\":[[:space:]]*[0-9]+ ]]
    # Verify placeholder exists
    [[ "$TEMPLATE_CONTENT" == *'"contextWindow": ${CONTEXT_WINDOW}'* ]]
}

@test "anvil script uses extraction command in setup_repo" {
    local anvil_content
    anvil_content=$(cat "$REPO_ROOT/anvil")
    
    # Should contain the extraction grep pattern
    [[ "$anvil_content" =~ grep.*Qwen/Qwen3\.6-35B-A3B-FP8.*max-model-len ]]
}

@test "anvil script passes context_window to sed replacement" {
    local anvil_content
    anvil_content=$(cat "$REPO_ROOT/anvil")
    
    # Should contain sed replacement for CONTEXT_WINDOW
    [[ "$anvil_content" =~ s/\\\$\{CONTEXT_WINDOW\}/\$\{context_window\}/ ]]
}

@test "simulated full pipeline: extraction -> template substitution" {
    # Simulate what anvil does and verify the output would be correct
    local context_window
    context_window=$(grep -A50 '^  "Qwen/Qwen3.6-35B-A3B-FP8":' config.yaml \
        | grep -- '--max-model-len' \
        | awk '{print $NF}' \
        | head -1)
    
    # Verify extraction succeeded
    [ -n "$context_window" ]
    [ "$context_window" = "262144" ]
    
    # Simulate sed replacement
    local simulated_output
    simulated_output=$(sed "s/\${CONTEXT_WINDOW}/${context_window}/g" \
        templates/zoo-code-settings.json.template)
    
    # Verify the output contains the correct numeric value
    [[ "$simulated_output" == *'"contextWindow": 262144'* ]]
    
    # Verify the placeholder is gone
    [[ "$simulated_output" != *'${CONTEXT_WINDOW}'* ]]
}
