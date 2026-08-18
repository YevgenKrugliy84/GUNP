#!/usr/bin/env bash
# Daily backup of db.sqlite3 using Python's sqlite3.backup() (safe to run
# while gunicorn is writing to the DB, unlike `cp`). Keeps 30 days.
# Runs as poweredge (see backup-gunp-db.service / .timer).
set -euo pipefail

PROJECT_DIR="/home/poweredge/projects/чат фінал майже/чат фінал майже/GUNP/gunp_django"
PYTHON="/home/poweredge/projects/чат фінал майже/чат фінал майже/GUNP/gunp_django_venv/bin/python3"
DB_FILE="$PROJECT_DIR/db.sqlite3"
BACKUP_DIR="$PROJECT_DIR/backups"
KEEP_DAYS=30

mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$BACKUP_DIR/db-$TIMESTAMP.sqlite3"

"$PYTHON" - "$DB_FILE" "$DEST" <<'PYEOF'
import sqlite3
import sys

src_path, dest_path = sys.argv[1], sys.argv[2]
src = sqlite3.connect(src_path)
dest = sqlite3.connect(dest_path)
with dest:
    src.backup(dest)
src.close()
dest.close()
PYEOF

gzip "$DEST"

find "$BACKUP_DIR" -name 'db-*.sqlite3.gz' -mtime "+$KEEP_DAYS" -delete

echo "Backed up to $DEST.gz"
