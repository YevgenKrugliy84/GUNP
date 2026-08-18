#!/usr/bin/env bash
# Runs when a monitored systemd unit fails (see OnFailure= in gunp.service).
# Always logs loudly to the journal (visible via `journalctl -p err`) and
# broadcasts to logged-in terminals. If GUNP_ALERT_WEBHOOK_URL is set in
# /etc/default/gunp-alerts (not committed — create it manually if/when a
# real notification channel, e.g. a Telegram/Slack webhook, is wired up),
# also POSTs a short message there.
set -uo pipefail

UNIT="${1:-unknown-unit}"
MESSAGE="GUNP ALERT: systemd unit '$UNIT' failed on $(hostname) at $(date -Is)"

logger -p daemon.err -t gunp-alert "$MESSAGE"
wall "$MESSAGE" 2>/dev/null || true

ENV_FILE="/etc/default/gunp-alerts"
if [ -f "$ENV_FILE" ]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
fi

if [ -n "${GUNP_ALERT_WEBHOOK_URL:-}" ]; then
    curl -fsS -m 10 -X POST -H 'Content-Type: application/json' \
        -d "{\"text\": \"$MESSAGE\"}" \
        "$GUNP_ALERT_WEBHOOK_URL" >/dev/null 2>&1 || \
        logger -p daemon.err -t gunp-alert "Failed to deliver webhook alert for $UNIT"
fi
