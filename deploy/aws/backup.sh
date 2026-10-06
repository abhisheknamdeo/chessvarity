#!/usr/bin/env bash
# Nightly logical backup of the app database to S3 (kept 30 days by the bucket's lifecycle rule).
# Runs from dukesmateai-backup.timer via run-with-secret.sh, which provides the PG* connection variables.
set -euo pipefail
stamp=$(date -u +%Y-%m-%dT%H%M%SZ)
pg_dump --format=custom --no-owner | aws s3 cp - "s3://${BACKUP_BUCKET}/backups/dukesmateai-${stamp}.dump" \
  --region "$AWS_REGION" --sse AES256 --only-show-errors
echo "Backup written: s3://${BACKUP_BUCKET}/backups/dukesmateai-${stamp}.dump"
