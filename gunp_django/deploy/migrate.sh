#!/usr/bin/env bash
# Runs `manage.py migrate` using the project's venv. No sudo needed.
set -euo pipefail
PROJECT_DIR="/home/poweredge/projects/чат фінал майже/чат фінал майже/GUNP/gunp_django"
VENV="/home/poweredge/projects/чат фінал майже/чат фінал майже/GUNP/gunp_django_venv"
cd "$PROJECT_DIR"
"$VENV/bin/python3" manage.py migrate
