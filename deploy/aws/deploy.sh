#!/usr/bin/env bash
# Deploy the current working tree to the EC2 server. Run from the project root on your computer:
#   deploy/aws/deploy.sh
# Packs the app, uploads it to the private S3 bucket, and runs install.sh on the server through
# AWS Systems Manager (no SSH). Needs the AWS CLI signed in to the project (aws login).
set -euo pipefail
export MSYS_NO_PATHCONV=1
REGION=us-east-2
BUCKET=s3-dukesmateai
INSTANCE=$(aws ec2 describe-instances --region $REGION --filters Name=tag:Name,Values=DukesMateAI-web \
  Name=instance-state-name,Values=running --query "Reservations[0].Instances[0].InstanceId" --output text)
stamp=$(date -u +%Y%m%d-%H%M%S)
mkdir -p dist && tarball=dist/release-$stamp.tar.gz  # relative path: works with the Windows AWS CLI too

tar -czf "$tarball" --exclude=__pycache__ pyproject.toml uv.lock README.md NOTICE.md src tools tests deploy
aws s3 cp "$tarball" "s3://$BUCKET/releases/$stamp.tar.gz" --region $REGION --sse AES256 --only-show-errors && rm -f "$tarball"

dir=/opt/dukesmateai/releases/$stamp
cmd=$(aws ssm send-command --region $REGION --instance-ids "$INSTANCE" --document-name AWS-RunShellScript \
  --comment "Deploy Dukes Mate AI $stamp" --timeout-seconds 900 \
  --parameters "commands=[\"set -e\",\"mkdir -p $dir\",\"aws s3 cp s3://$BUCKET/releases/$stamp.tar.gz /tmp/release.tgz --region $REGION --only-show-errors || /usr/local/bin/aws s3 cp s3://$BUCKET/releases/$stamp.tar.gz /tmp/release.tgz --region $REGION --only-show-errors\",\"tar -xzf /tmp/release.tgz -C $dir && rm /tmp/release.tgz\",\"bash $dir/deploy/aws/install.sh $dir\",\"for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do curl -fsS -m 3 http://127.0.0.1:8000/api/health && exit 0; sleep 2; done; journalctl -u dukesmateai -n 30 --no-pager; exit 1\"]" \
  --query Command.CommandId --output text)
echo "Deploying $stamp (command $cmd)..."
aws ssm wait command-executed --region $REGION --command-id "$cmd" --instance-id "$INSTANCE" || true
aws ssm get-command-invocation --region $REGION --command-id "$cmd" --instance-id "$INSTANCE" \
  --query "[Status, StandardOutputContent, StandardErrorContent]" --output text
