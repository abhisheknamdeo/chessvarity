#!/usr/bin/env bash
# One-time: create the app's own database user and make it the owner of the app database (and of a separate
# database for running the test suite). Uses the RDS-managed admin secret; run as root on the EC2 server:
#   bootstrap-db.sh <rds admin secret ARN>
set -euo pipefail
source /etc/dukesmateai/app.env
admin=$(aws secretsmanager get-secret-value --region "$AWS_REGION" --secret-id "$1" --query SecretString --output text)
app=$(aws secretsmanager get-secret-value --region "$AWS_REGION" --secret-id "$DB_SECRET_ID" --query SecretString --output text)
field() { /opt/dukesmateai/venv/bin/python -c "import json,sys; print(json.loads(sys.argv[1])[sys.argv[2]])" "$1" "$2"; }

export PGHOST=$DB_HOST PGPORT=$DB_PORT PGSSLMODE=verify-full PGSSLROOTCERT=$DB_SSLROOTCERT PGDATABASE=postgres
export PGUSER=$(field "$admin" username) PGPASSWORD=$(field "$admin" password)
APP_USER=$(field "$app" username) APP_PW=$(field "$app" password) APP_DB=$(field "$app" dbname)

psql -v ON_ERROR_STOP=1 -q -v u="$APP_USER" -v pw="$APP_PW" -v db="$APP_DB" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN', :'u') WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'u') \gexec
SELECT format('ALTER ROLE %I PASSWORD %L', :'u', :'pw') \gexec
SELECT format('GRANT %I TO CURRENT_USER', :'u') \gexec
SELECT format('ALTER DATABASE %I OWNER TO %I', :'db', :'u') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'db' || '_test', :'u')
  WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db' || '_test') \gexec
SQL
# The public schema belongs to pg_database_owner, so the app user can create its tables there.
echo "Database user ready."
