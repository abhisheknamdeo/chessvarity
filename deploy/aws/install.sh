#!/usr/bin/env bash
# Install or update Dukes Mate AI on the EC2 server. Run as root (through AWS Systems Manager):
#   install.sh <release directory>        e.g. /opt/dukesmateai/releases/20260928-101500
# Safe to run again: the first run installs system packages, later runs only switch releases.
set -euo pipefail
release=$(realpath "$1")
cd "$release"

if ! id dukesmateai >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/dukesmateai --create-home --shell /usr/sbin/nologin dukesmateai
fi

# One-time move from the old "dukes-king" layout (before the Dukes Mate AI rename): keep the server's settings,
# point them at the renamed AWS resources, and retire the old service. The old folders are removed by hand later.
if [ -f /etc/dukes-king/app.env ] && [ ! -f /etc/dukesmateai/app.env ]; then
  systemctl disable --now dukes-king.service dukes-king-backup.timer 2>/dev/null || true
  install -d /etc/dukesmateai
  sed -e 's|dukes-king-060622564501-us-east-2|s3-dukesmateai|g' -e 's|dukes-king-db[.]|dukesmateai-db.|'       -e 's|dukes-king/app-db|DukesMateAI/app-db|' -e 's|dukes-king/oauth|DukesMateAI/oauth|'       -e 's|/opt/dukes-king/|/opt/dukesmateai/|g' -e 's|/var/lib/dukes-king|/var/lib/dukesmateai|'       /etc/dukes-king/app.env > /etc/dukesmateai/app.env
  chgrp dukesmateai /etc/dukesmateai/app.env && chmod 640 /etc/dukesmateai/app.env
  rm -f /etc/systemd/system/dukes-king.service /etc/systemd/system/dukes-king-backup.service /etc/systemd/system/dukes-king-backup.timer
  systemctl daemon-reload
fi

if [ ! -x /opt/dukesmateai/venv/bin/python ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -q
  apt-get install -y -q stockfish caddy python3-venv unzip curl ca-certificates gnupg
  # pg_dump must be at least the server's major version (RDS PostgreSQL 18): use the PostgreSQL apt repository.
  install -d /usr/share/postgresql-common/pgdg
  curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
  echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt noble-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list
  apt-get update -q
  apt-get install -y -q postgresql-client-18
  python3 -m venv /opt/dukesmateai/venv
  curl -fsSL https://truststore.pki.rds.amazonaws.com/us-east-2/us-east-2-bundle.pem -o /opt/dukesmateai/rds-ca.pem
fi

if ! command -v aws >/dev/null 2>&1 || [ "$(command -v aws)" = /snap/bin/aws ]; then
  curl -fsSL https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o /tmp/awscliv2.zip
  unzip -q -o /tmp/awscliv2.zip -d /tmp && /tmp/aws/install --update && rm -rf /tmp/aws /tmp/awscliv2.zip
fi

/opt/dukesmateai/venv/bin/pip install -q --upgrade pip
/opt/dukesmateai/venv/bin/pip install -q -r deploy/aws/requirements.txt
/opt/dukesmateai/venv/bin/pip install -q --no-deps --force-reinstall .

install -d /opt/dukesmateai/bin /etc/dukesmateai
install -m 755 deploy/aws/run-with-secret.sh deploy/aws/backup.sh /opt/dukesmateai/bin/
install -m 644 deploy/aws/dukesmateai.service deploy/aws/dukesmateai-backup.service deploy/aws/dukesmateai-backup.timer /etc/systemd/system/
[ -f /etc/dukesmateai/app.env ] || install -m 640 -g dukesmateai deploy/aws/dukesmateai.env /etc/dukesmateai/app.env
# Settings added in newer releases are appended; values already on the server are never changed.
grep -E '^[A-Z][A-Z0-9_]*=' deploy/aws/dukesmateai.env | while IFS= read -r line; do
  grep -q "^${line%%=*}=" /etc/dukesmateai/app.env || echo "$line" >> /etc/dukesmateai/app.env
done
install -m 644 deploy/aws/Caddyfile /etc/caddy/Caddyfile  # the Caddyfile lives in the repository

ln -sfn "$release" /opt/dukesmateai/current
chown -R root:root "$release"
systemctl daemon-reload
systemctl enable --now dukesmateai-backup.timer caddy >/dev/null
systemctl enable dukesmateai >/dev/null
systemctl restart dukesmateai
systemctl reload caddy

# Keep the five newest releases.
ls -1dt /opt/dukesmateai/releases/*/ | tail -n +6 | xargs -r rm -rf
echo "Installed $(basename "$release")"
