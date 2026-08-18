#!/usr/bin/env bash
# Daily backup of the GUNP PostgreSQL database via pg_dump (custom format,
# compressed, safe to run against a live DB). Keeps 30 days.
# Runs as poweredge (see backup-gunp-db.service / .timer).
set -euo pipefail

PROJECT_DIR="/home/poweredge/projects/чат фінал майже/чат фінал майже/GUNP/gunp_django"
ENV_FILE="$PROJECT_DIR/.env"
BACKUP_DIR="$PROJECT_DIR/backups"
KEEP_DAYS=30

# shellcheck disable=SC1090
source "$ENV_FILE"
DB_NAME="${DB_NAME:-gunp}"
DB_USER="${DB_USER:-gunp}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$BACKUP_DIR/db-$TIMESTAMP.dump"

PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -Fc -f "$DEST" "$DB_NAME"

find "$BACKUP_DIR" -name 'db-*.dump' -mtime "+$KEEP_DAYS" -delete

echo "Backed up to $DEST"
