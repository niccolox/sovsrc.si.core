#!/usr/bin/env bash
# run_curl_examples.sh — Run all API curl examples for sovsrc.si.core
#
# Usage:
#   make run-server          # Start server in one terminal
#   ./run_curl_examples.sh   # Run this script in another terminal

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
JQ_AVAILABLE=true
command -v jq >/dev/null 2>&1 || JQ_AVAILABLE=false

echo "=== Sovereign Source API curl examples ==="
echo "Base URL: $BASE_URL"
echo ""

# Helper to run curl with nice formatting
run_curl() {
    local label="$1"
    local cmd="$2"
    echo "--- $label ---"
    echo "$ $cmd"
    if [ "$JQ_AVAILABLE" = true ]; then
        eval "$cmd" | jq .
    else
        eval "$cmd"
    fi
    echo ""
}

# 1. Get API Info
run_curl "1. Get API Info" "curl -s $BASE_URL/"

# 2. List All Content Units
run_curl "2. List All Content Units" "curl -s $BASE_URL/content"

# 3. Get Single Content Unit (c1)
run_curl "3. Get Single Content Unit (c1)" "curl -s $BASE_URL/content/c1"

# 4. Ingest New Content Unit
run_curl "4. Ingest New Content Unit" \
  'curl -s -X POST '"$BASE_URL"'/content \
  -H "Content-Type: application/json" \
  -d '"'"'{"text": "The speed of light is 299,792,458 m/s", "source_uri": "https://github.com/niccolox/sovsrc.llm/blob/main/licenses/SS-SIP-0.1.md", "license": "sovsrc-rewards-v1", "contributor_id": "alice", "metadata": {"domain": "physics", "quality_score": 0.95}}'"'"''

# 5. Attribute Model Output (with citations)
ATTRIBUTE_RESPONSE=$(curl -s -X POST "$BASE_URL/attribute" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is the speed of light?",
    "response": "Light travels at 299,792,458 m/s.",
    "citations": [
      {"content_unit_id": "c1", "influence_score": 0.8, "method": "exact_match"},
      {"content_unit_id": "c2", "influence_score": 0.2, "method": "semantic_similarity"}
    ]
  }')
echo "--- 5. Attribute Model Output ---"
echo "$ curl -X POST $BASE_URL/attribute ..."
if [ "$JQ_AVAILABLE" = true ]; then
    echo "$ATTRIBUTE_RESPONSE" | jq .
else
    echo "$ATTRIBUTE_RESPONSE"
fi
OUTPUT_ID=$(echo "$ATTRIBUTE_RESPONSE" | (jq -r .id 2>/dev/null || echo ""))
echo ""

# 6. Calculate Rewards for Model Output
if [ -n "$OUTPUT_ID" ] && [ "$OUTPUT_ID" != "null" ]; then
    run_curl "6. Calculate Rewards for Model Output" \
      "curl -s -X POST $BASE_URL/rewards/calculate -H \"Content-Type: application/json\" -d '{\"model_output_id\": \"$OUTPUT_ID\", \"pool_amount\": \"100\"}'"
else
    echo "--- 6. Calculate Rewards (skipped - no output_id) ---"
    echo ""
fi

# 7. View Reward Ledger (all events)
run_curl "7. View Reward Ledger (all events)" "curl -s $BASE_URL/rewards/ledger"

# 8. Get Contributor Earnings (alice)
run_curl "8. Get Contributor Earnings (alice)" "curl -s $BASE_URL/contributors/alice/earnings"

# 9. Run Hello World Demo (fixture)
run_curl "9. Run Hello World Demo (fixture)" "curl -s $BASE_URL/demo/hello-world"

# 10. Run Unified Training + Rewards Demo (may take 10-30s)
echo "--- 10. Run Unified Training + Rewards Demo (may take 10-30s) ---"
echo "$ curl $BASE_URL/demo/unified"
if [ "$JQ_AVAILABLE" = true ]; then
    curl -s "$BASE_URL/demo/unified" | jq .
else
    curl -s "$BASE_URL/demo/unified"
fi
echo ""

# 11. List Macbeth Content Units
if [ "$JQ_AVAILABLE" = true ]; then
    run_curl "11. List Macbeth Content Units" \
      "curl -s $BASE_URL/content | jq '.content_units[] | select(.id | startswith(\"macbeth\")) | {id, character: .metadata.character, license, text: .text[0:60]}'"
else
    run_curl "11. List Macbeth Content Units (requires jq)" "curl -s $BASE_URL/content"
fi

# 12. Get Macbeth Speech by ID
run_curl "12. Get Macbeth Speech (macbeth-speech-1)" "curl -s $BASE_URL/content/macbeth-speech-1"

# 13. Attribute Output Citing Macbeth Speeches
MACBETH_ATTRIBUTE=$(curl -s -X POST "$BASE_URL/attribute" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Quote a line about guilt from Macbeth",
    "response": "Methought I heard a voice cry Sleep no more! Macbeth does murder sleep.",
    "citations": [
      {"content_unit_id": "macbeth-speech-2", "influence_score": 0.7, "method": "exact_match"},
      {"content_unit_id": "macbeth-speech-10", "influence_score": 0.3, "method": "semantic_similarity"}
    ]
  }')
echo "--- 13. Attribute Output Citing Macbeth Speeches ---"
echo "$ curl -X POST $BASE_URL/attribute ..."
if [ "$JQ_AVAILABLE" = true ]; then
    echo "$MACBETH_ATTRIBUTE" | jq .
else
    echo "$MACBETH_ATTRIBUTE"
fi
MACBETH_OUTPUT_ID=$(echo "$MACBETH_ATTRIBUTE" | (jq -r .id 2>/dev/null || echo ""))
echo ""

# 14. Calculate Rewards for Macbeth Attribution
if [ -n "$MACBETH_OUTPUT_ID" ] && [ "$MACBETH_OUTPUT_ID" != "null" ]; then
    run_curl "14. Calculate Rewards for Macbeth Attribution" \
      "curl -s -X POST $BASE_URL/rewards/calculate -H \"Content-Type: application/json\" -d '{\"model_output_id\": \"$MACBETH_OUTPUT_ID\", \"pool_amount\": \"100\"}'"
else
    echo "--- 14. Calculate Rewards for Macbeth (skipped - no output_id) ---"
    echo ""
fi

# 15. Get Earnings for Macbeth Characters
for contributor in macbeth lady_macbeth banquo; do
    run_curl "15. Get Earnings for $contributor" "curl -s $BASE_URL/contributors/$contributor/earnings"
done

# 16. Filter Content by License
if [ "$JQ_AVAILABLE" = true ]; then
    run_curl "16a. Filter sovsrc-rewards-v1 content (full rewards)" \
      "curl -s $BASE_URL/content | jq '.content_units[] | select(.license == \"sovsrc-rewards-v1\") | {id, contributor_id, text: .text[0:80]}'"

    run_curl "16b. Filter public-domain content (no rewards)" \
      "curl -s $BASE_URL/content | jq '.content_units[] | select(.license == \"public-domain\") | {id, contributor_id, text: .text[0:80]}'"
else
    echo "--- 16. Filter by License (requires jq) ---"
    echo "Install jq to run these examples"
    echo ""
fi

echo "=== All examples completed ==="