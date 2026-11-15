#!/usr/bin/env bash
# Remove everything deploy/aws/create.sh made. Asks before it starts.
#
#   deploy/aws/delete.sh BUCKET
#
# The CloudFront distribution is only switched off here: AWS needs about 15 minutes before
# it can be deleted. The last line printed is the command that deletes it.
set -uo pipefail

BUCKET="${1:?usage: deploy/aws/delete.sh BUCKET}"
REGION="${AWS_REGION:-$(aws configure get region)}"
NAME=fire-map
export AWS_DEFAULT_REGION="$REGION" AWS_PAGER=""

read -r -p "Delete the machine, the bucket $BUCKET with its files, and the role? Type yes: " answer
[ "$answer" = yes ] || exit 1

INSTANCES="$(aws ec2 describe-instances --filters "Name=tag:Name,Values=$NAME" \
  "Name=instance-state-name,Values=pending,running,stopping,stopped" \
  --query 'Reservations[].Instances[].InstanceId' --output text)"
if [ -n "$INSTANCES" ]; then
  aws ec2 terminate-instances --instance-ids $INSTANCES >/dev/null
  aws ec2 wait instance-terminated --instance-ids $INSTANCES
fi
GROUP="$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$NAME" \
  --query 'SecurityGroups[0].GroupId' --output text)"
[ "$GROUP" != None ] && aws ec2 delete-security-group --group-id "$GROUP"

aws iam remove-role-from-instance-profile --instance-profile-name "$NAME-server" --role-name "$NAME-server"
aws iam delete-instance-profile --instance-profile-name "$NAME-server"
aws iam detach-role-policy --role-name "$NAME-server" \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam delete-role-policy --role-name "$NAME-server" --policy-name read-bucket-and-secrets
aws iam delete-role --role-name "$NAME-server"

aws s3 rb "s3://$BUCKET" --force

ID="$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?Comment=='$NAME'].Id | [0]" --output text)"
if [ "$ID" != None ] && [ -n "$ID" ]; then
  TMP="$(mktemp)"
  ETAG="$(aws cloudfront get-distribution-config --id "$ID" --query ETag --output text)"
  aws cloudfront get-distribution-config --id "$ID" --query DistributionConfig \
    | sed 's/"Enabled": true/"Enabled": false/' > "$TMP"
  aws cloudfront update-distribution --id "$ID" --if-match "$ETAG" \
    --distribution-config "file://$TMP" >/dev/null
  rm -f "$TMP"
  echo "CloudFront $ID is switching off. In about 15 minutes run:"
  echo "  aws cloudfront delete-distribution --id $ID --if-match \$(aws cloudfront get-distribution-config --id $ID --query ETag --output text)"
fi
