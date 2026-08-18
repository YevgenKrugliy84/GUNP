#!/usr/bin/env bash
# One-time setup: creates the `gunp` PostgreSQL role and `gunp` database,
# using DB_PASSWORD from the project's .env file (same one gunp.service
# reads via EnvironmentFile) so the password lives in exactly one place.
# Must be run with sudo (needs to act as the `postgres` system/DB user).
# Idempotent: safe to re-run.
set -euo pipefail

ENV_FILE="/home/poweredge/projects/чат фінал майже/чат фінал майже/GUNP/gunp_django/.env"
# shellcheck disable=SC1090
source "$ENV_FILE"

DB_NAME="${DB_NAME:-gunp}"
DB_USER="${DB_USER:-gunp}"
: "${DB_PASSWORD:?DB_PASSWORD must be set in $ENV_FILE}"

sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$DB_USER') THEN
      CREATE ROLE $DB_USER WITH LOGIN CREATEDB PASSWORD '$DB_PASSWORD';
   ELSE
      ALTER ROLE $DB_USER WITH CREATEDB PASSWORD '$DB_PASSWORD';
   END IF;
END
\$\$;

SELECT 'CREATE DATABASE $DB_NAME OWNER $DB_USER'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')\gexec

GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
SQL

echo "Done: role and database '$DB_NAME' ready."
