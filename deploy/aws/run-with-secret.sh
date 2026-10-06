#!/usr/bin/env bash
# Builds DATABASE_URL from Secrets Manager (never written to disk), then runs the given command.
#   run-with-secret.sh uvicorn ...        (the service)
#   run-with-secret.sh pg_dump ...        (backups; also exports PG* variables)
set -euo pipefail

secret=$(aws secretsmanager get-secret-value --region "$AWS_REGION" --secret-id "$DB_SECRET_ID" \
  --query SecretString --output text)

eval "$(SECRET="$secret" /opt/dukesmateai/venv/bin/python - <<'EOF'
import json, os, shlex
from urllib.parse import quote
s = json.loads(os.environ["SECRET"])
host, port, ca = os.environ["DB_HOST"], os.environ["DB_PORT"], os.environ["DB_SSLROOTCERT"]
url = (f"postgresql://{quote(s['username'], safe='')}:{quote(s['password'], safe='')}@{host}:{port}/"
       f"{quote(s['dbname'], safe='')}?sslmode=verify-full&sslrootcert={quote(ca)}")
for k, v in {"DATABASE_URL": url, "PGHOST": host, "PGPORT": port, "PGUSER": s["username"],
             "PGPASSWORD": s["password"], "PGDATABASE": s["dbname"], "PGSSLMODE": "verify-full",
             "PGSSLROOTCERT": ca}.items():
    print(f"export {k}={shlex.quote(v)}")
EOF
)"
unset secret

# Optional: Google / Apple sign-in keys, stored as {"CHESSCOACH_GOOGLE_CLIENT_ID": "...", ...} in their own secret.
if [ -n "${OAUTH_SECRET_ID:-}" ]; then
  if oauth=$(aws secretsmanager get-secret-value --region "$AWS_REGION" --secret-id "$OAUTH_SECRET_ID"       --query SecretString --output text 2>/dev/null); then
    eval "$(SECRET="$oauth" /opt/dukesmateai/venv/bin/python - <<'EOF'
import json, os, shlex
for k, v in json.loads(os.environ["SECRET"]).items():
    if k.startswith("CHESSCOACH_"):
        print(f"export {k}={shlex.quote(str(v))}")
EOF
)"
  fi
  unset oauth
fi
exec "$@"
