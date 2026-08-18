#!/usr/bin/env bash
# Polls /healthz/ and alerts (via notify_failure.sh) only after 3 consecutive
# failures, to avoid paging on a single transient blip. Run every 5 minutes
# by check-gunp-health.timer.
set -uo pipefail

URL="http://10.111.16.6:8095/healthz/"
STATE_FILE="/tmp/gunp_health_failcount"
THRESHOLD=3
DEPLOY_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

CODE=$(curl -fsS -o /dev/null -w '%{http_code}' -m 10 "$URL" 2>/dev/null) || CODE="000"

if [ "$CODE" = "200" ]; then
    rm -f "$STATE_FILE"
    exit 0
fi

COUNT=1
if [ -f "$STATE_FILE" ]; then
    COUNT=$(($(cat "$STATE_FILE") + 1))
fi
echo "$COUNT" > "$STATE_FILE"

if [ "$COUNT" -ge "$THRESHOLD" ]; then
    bash "$DEPLOY_DIR/notify_failure.sh" "healthz (http_code=$CODE, $COUNT consecutive failures)"
    rm -f "$STATE_FILE"
fi
