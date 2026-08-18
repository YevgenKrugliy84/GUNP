#!/usr/bin/env bash
# Installs the gunp systemd service and nginx site config, then starts both.
# Must be run with sudo. Run once after `git pull` + venv/requirements are in place.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

install -m 644 "$DEPLOY_DIR/gunp.service" /etc/systemd/system/gunp.service
install -m 644 "$DEPLOY_DIR/nginx_gunp.conf" /etc/nginx/sites-available/gunp
install -m 644 "$DEPLOY_DIR/logrotate_gunp" /etc/logrotate.d/gunp

ln -sf /etc/nginx/sites-available/gunp /etc/nginx/sites-enabled/gunp

nginx -t
logrotate -d /etc/logrotate.d/gunp

systemctl daemon-reload
systemctl enable --now gunp
systemctl reload nginx

echo "Done. gunp.service status:"
systemctl status gunp --no-pager --lines=5
