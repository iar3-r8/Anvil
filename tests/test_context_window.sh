#!/usr/bin/env bash
# Test: Context window extraction from config.yaml matches template injection
# Ensures the coder model's --max-model-len value stays synchronized
#
# Usage: ./tests/test_context_window.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PASSED=0
FAILED=0

pass() {
    echo "  ✅ PASS: $1"
    PASSED=$((PASSED + 1))
}

fail() {
    echo "  ❌ FAIL: $1"
    FAILED=$((FAILED + 1))
}

echo "============================================================"
echo "Context Window Synchronization Tests"
echo "============================================================"
echo ""

# ---- Test 1: config.yaml has max-model-len for coder model ----
echo "[Test 1] config.yaml has --max-model-len for coder model"
if grep -A50 '^  "Qwen/Qwen3.6-35B-A3B-FP8":' config.yaml | grep -q -- '--max-model-len'; then
    pass "coder model has --max-model-len defined"
else
    fail "coder model missing --max-model-len in config.yaml"
fi

# ---- Test 2: Extracted value equals 262144 ----
echo "[Test 2] Extracted context window equals 262144"
EXTRACTED=$(grep -A50 '^  "Qwen/Qwen3.6-35B-A3B-FP8":' config.yaml \
    | grep -- '--max-model-len' \
    | awk '{print $NF}' \
    | head -1)

if [ "$EXTRACTED" = "262144" ]; then
    pass "extracted value is $EXTRACTED"
else
    fail "expected 262144, got '$EXTRACTED'"
fi

# ---- Test 3: Template contains placeholder ----
echo "[Test 3] Template uses CONTEXT_WINDOW placeholder"
TEMPLATE=$(cat templates/zoo-code-settings.json.template)

if [[ "$TEMPLATE" == *'${CONTEXT_WINDOW}'* ]]; then
    pass "template contains \${CONTEXT_WINDOW} placeholder"
else
    fail "template missing \${CONTEXT_WINDOW} placeholder"
fi

# ---- Test 4: Template does NOT contain hardcoded value ----
echo "[Test 4] Template has no hardcoded context window number"
if [[ "$TEMPLATE" == *'"contextWindow": ${CONTEXT_WINDOW}'* ]]; then
    pass "template uses placeholder, not hardcoded number"
else
    fail "template may have hardcoded context window value"
fi

# ---- Test 5: anvil script uses extraction command ----
echo "[Test 5] anvil script contains extraction logic"
ANVIL=$(cat "$REPO_ROOT/anvil")

if echo "$ANVIL" | grep -q 'grep.*Qwen/Qwen3\.6-35B-A3B-FP8.*max-model-len'; then
    pass "anvil contains extraction grep pattern"
else
    fail "anvil missing extraction grep pattern"
fi

# ---- Test 6: anvil script passes to sed ----
echo "[Test 6] anvil script passes context_window to sed replacement"
if echo "$ANVIL" | grep -q 's/.*CONTEXT_WINDOW.*context_window'; then
    pass "anvil has sed replacement for CONTEXT_WINDOW"
else
    fail "anvil missing sed replacement"
fi

# ---- Test 7: Full pipeline simulation ----
echo "[Test 7] Full pipeline: extraction -> template substitution"
CONTEXT_WINDOW=$(grep -A50 '^  "Qwen/Qwen3.6-35B-A3B-FP8":' config.yaml \
    | grep -- '--max-model-len' \
    | awk '{print $NF}' \
    | head -1)

if [ -z "$CONTEXT_WINDOW" ]; then
    fail "extraction returned empty"
elif [ "$CONTEXT_WINDOW" != "262144" ]; then
    fail "extraction returned '$CONTEXT_WINDOW' instead of 262144"
else
    # Simulate sed substitution
    SUBSTITUTED=$(sed "s/\${CONTEXT_WINDOW}/${CONTEXT_WINDOW}/g" \
        templates/zoo-code-settings.json.template)

    if [[ "$SUBSTITUTED" == *'"contextWindow": 262144'* ]]; then
        pass "substitution produces correct value (262144)"
    else
        fail "substitution did not produce expected result"
    fi

    if [[ "$SUBSTITUTED" != *'${CONTEXT_WINDOW}'* ]]; then
        pass "placeholder fully replaced (no \${CONTEXT_WINDOW} remaining)"
    else
        fail "placeholder not fully replaced"
    fi
fi

# ---- Summary ----
echo ""
echo "============================================================"
echo "Results: $PASSED passed, $FAILED failed"
echo "============================================================"

if [ "$FAILED" -gt 0 ]; then
    exit 1
fi

exit 0
