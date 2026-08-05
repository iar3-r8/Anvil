#!/usr/bin/env bash
# Test: Anthropic frontier model placeholder substitution in zoo-code-settings.json template
# Verifies that the template contains the correct placeholders and sed substitution works
# for both accepted and declined paths.
#
# Usage: ./tests/test_frontier_model.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

TEMPLATE="$REPO_ROOT/templates/zoo-code-settings.json.template"
LOCAL_PROFILE_ID="4aj3zc43616"

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
echo "Frontier Model Substitution Tests"
echo "============================================================"
echo ""

# ---- Test 1: Template contains LOCAL_PROFILE_ID placeholder ----
echo "[Test 1] Template contains \${LOCAL_PROFILE_ID} placeholder"
if grep -q '\${LOCAL_PROFILE_ID}' "$TEMPLATE"; then
    pass "template contains \${LOCAL_PROFILE_ID}"
else
    fail "template missing \${LOCAL_PROFILE_ID} placeholder"
fi

# ---- Test 2: Template contains ANTHROPIC_API_KEY placeholder ----
echo "[Test 2] Template contains \${ANTHROPIC_API_KEY} placeholder"
if grep -q '\${ANTHROPIC_API_KEY}' "$TEMPLATE"; then
    pass "template contains \${ANTHROPIC_API_KEY}"
else
    fail "template missing \${ANTHROPIC_API_KEY} placeholder"
fi

# ---- Test 3: Template contains ANTHROPIC_MODEL_ID placeholder ----
echo "[Test 3] Template contains \${ANTHROPIC_MODEL_ID} placeholder"
if grep -q '\${ANTHROPIC_MODEL_ID}' "$TEMPLATE"; then
    pass "template contains \${ANTHROPIC_MODEL_ID}"
else
    fail "template missing \${ANTHROPIC_MODEL_ID} placeholder"
fi

# ---- Test 4: Template contains ARCHITECT_PROFILE_ID placeholder ----
echo "[Test 4] Template contains \${ARCHITECT_PROFILE_ID} placeholder"
if grep -q '\${ARCHITECT_PROFILE_ID}' "$TEMPLATE"; then
    pass "template contains \${ARCHITECT_PROFILE_ID}"
else
    fail "template missing \${ARCHITECT_PROFILE_ID} placeholder"
fi

# ---- Test 5: Template contains anthropic provider profile block ----
echo "[Test 5] Template contains 'anthropic' provider profile block"
if grep -q '"anthropic"' "$TEMPLATE"; then
    pass "template contains 'anthropic' profile entry"
else
    fail "template missing 'anthropic' profile block"
fi

# ---- Test 6: Template contains apiProvider: anthropic ----
echo "[Test 6] Template has 'apiProvider': 'anthropic' inside anthropic block"
if grep -q '"apiProvider": "anthropic"' "$TEMPLATE"; then
    pass "template has apiProvider: anthropic"
else
    fail "template missing apiProvider: anthropic"
fi

# ---- Test 7: Accepted path — sed substitutes anthropic_profile into architect ----
echo "[Test 7] Accepted path: architect profile resolves to 'anthropic_profile'"
ACCEPTED_OUTPUT=$(sed \
    -e "s|\${LLM_PORT}|8000|g" \
    -e "s|\${CONTEXT_WINDOW}|262144|g" \
    -e "s|\${LOCAL_PROFILE_ID}|${LOCAL_PROFILE_ID}|g" \
    -e "s|\${ANTHROPIC_API_KEY}|sk-ant-test-key|g" \
    -e "s|\${ANTHROPIC_MODEL_ID}|claude-opus-5|g" \
    -e "s|\${ARCHITECT_PROFILE_ID}|anthropic_profile|g" \
    "$TEMPLATE")

if echo "$ACCEPTED_OUTPUT" | grep -q '"architect": "anthropic_profile"'; then
    pass "architect mode bound to 'anthropic_profile' on accepted path"
else
    fail "architect mode not bound to 'anthropic_profile' on accepted path"
fi

# ---- Test 8: Declined path — sed substitutes local profile id into architect ----
echo "[Test 8] Declined path: architect profile resolves to local profile id"
DECLINED_OUTPUT=$(sed \
    -e "s|\${LLM_PORT}|8000|g" \
    -e "s|\${CONTEXT_WINDOW}|262144|g" \
    -e "s|\${LOCAL_PROFILE_ID}|${LOCAL_PROFILE_ID}|g" \
    -e "s|\${ANTHROPIC_API_KEY}|to set|g" \
    -e "s|\${ANTHROPIC_MODEL_ID}|claude-opus-5|g" \
    -e "s|\${ARCHITECT_PROFILE_ID}|${LOCAL_PROFILE_ID}|g" \
    "$TEMPLATE")

if echo "$DECLINED_OUTPUT" | grep -q '"architect": "'"${LOCAL_PROFILE_ID}"'"'; then
    pass "architect mode bound to local profile id on declined path"
else
    fail "architect mode not bound to local profile id on declined path"
fi

# ---- Test 9: Declined path — code/ask/debug/orchestrator still use local id ----
echo "[Test 9] Declined path: code/ask/debug/orchestrator use local profile id"
for mode in code ask debug orchestrator; do
    if echo "$DECLINED_OUTPUT" | grep -q "\"${mode}\": \"${LOCAL_PROFILE_ID}\""; then
        pass "${mode} mode bound to local profile id"
    else
        fail "${mode} mode not bound to local profile id"
    fi
done

# ---- Test 10: Accepted path — code/ask/debug/orchestrator still use local id ----
echo "[Test 10] Accepted path: code/ask/debug/orchestrator still use local profile id"
for mode in code ask debug orchestrator; do
    if echo "$ACCEPTED_OUTPUT" | grep -q "\"${mode}\": \"${LOCAL_PROFILE_ID}\""; then
        pass "${mode} mode still bound to local profile id"
    else
        fail "${mode} mode incorrectly changed on accepted path"
    fi
done

# ---- Test 11: Accepted path — anthropic profile has key and model id ----
echo "[Test 11] Accepted path: anthropic profile has api key and model id"
if echo "$ACCEPTED_OUTPUT" | grep -q '"anthropicApiKey": "sk-ant-test-key"'; then
    pass "anthropic profile has api key"
else
    fail "anthropic profile missing api key"
fi

if echo "$ACCEPTED_OUTPUT" | grep -q '"apiModelId": "claude-opus-5"'; then
    pass "anthropic profile has model id"
else
    fail "anthropic profile missing model id"
fi

# ---- Test 11b: anvil offers the expected Anthropic model lineup ----
echo "[Test 11b] anvil script offers the expected Anthropic model lineup"
ANVIL_SRC=$(cat "$REPO_ROOT/anvil")
for model in claude-fable-5 claude-opus-5 claude-sonnet-5 claude-haiku-4-5; do
    if echo "$ANVIL_SRC" | grep -q "$model"; then
        pass "anvil offers ${model}"
    else
        fail "anvil missing ${model}"
    fi
done

if echo "$ANVIL_SRC" | grep -q 'DEFAULT_ANTHROPIC_MODEL="claude-opus-5"'; then
    pass "default model is claude-opus-5"
else
    fail "default model is not claude-opus-5"
fi

# ---- Test 12: No placeholders remain in accepted output ----
echo "[Test 12] No placeholders remain in accepted output"
REMAINING=$(echo "$ACCEPTED_OUTPUT" | grep -oE '\$\{[A-Z_]+\}' || true)
if [ -z "$REMAINING" ]; then
    pass "no unexpanded placeholders in accepted output"
else
    fail "placeholders remain: ${REMAINING}"
fi

# ---- Test 13: No placeholders remain in declined output ----
echo "[Test 13] No placeholders remain in declined output"
REMAINING=$(echo "$DECLINED_OUTPUT" | grep -oE '\$\{[A-Z_]+\}' || true)
if [ -z "$REMAINING" ]; then
    pass "no unexpanded placeholders in declined output"
else
    fail "placeholders remain: ${REMAINING}"
fi

# ---- Test 14: Output parses as valid JSON (basic check) ----
echo "[Test 14] Accepted output is valid JSON"
if echo "$ACCEPTED_OUTPUT" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
    pass "accepted output is valid JSON"
else
    fail "accepted output is NOT valid JSON"
fi

echo "[Test 15] Declined output is valid JSON"
if echo "$DECLINED_OUTPUT" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
    pass "declined output is valid JSON"
else
    fail "declined output is NOT valid JSON"
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
