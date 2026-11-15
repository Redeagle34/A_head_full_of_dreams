#!/usr/bin/env bash
# Create everything on AWS once: bucket, permissions, one EC2 machine, CloudFront address.
#
# Run from the repository root, signed in to AWS (aws configure), after the pipeline:
#   deploy/aws/create.sh BUCKET
#
# BUCKET is a new, globally unique name, for example fire-map-<your-initials>-2026.
# The region is the one of `aws configure` (override with AWS_REGION).
#
# Creates (all named or tagged "fire-map")
#   S3 bucket, private           code and data (deploy/aws/upload.sh fills it)
#   IAM role fire-map-server     lets the machine read that bucket and the /fire/* secrets
#   security group               port 8080 open to CloudFront only
#   EC2 machine t3.small, 20 GB  runs deploy/aws/server.sh at first start
#   CloudFront distribution      the public https address
#
# Cost while running: about 17 USD a month for the machine and disk, plus traffic.
# Remove everything with deploy/aws/delete.sh BUCKET.
#
# Change here: INSTANCE_TYPE, DISK_GB.
set -euo pipefail

BUCKET="${1:?usage: deploy/aws/create.sh BUCKET}"
REGION="${AWS_REGION:-$(aws configure get region)}"
NAME=fire-map
INSTANCE_TYPE=t3.small
DISK_GB=20
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
export AWS_DEFAULT_REGION="$REGION" AWS_PAGER=""

echo "1/6 bucket $BUCKET in $REGION"
if [ "$REGION" = us-east-1 ]; then
  aws s3api create-bucket --bucket "$BUCKET" >/dev/null
else
  aws s3api create-bucket --bucket "$BUCKET" \
    --create-bucket-configuration "LocationConstraint=$REGION" >/dev/null
fi
aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

echo "2/6 upload code and data"
"$(dirname "$0")/upload.sh" "$BUCKET"

echo "3/6 role $NAME-server"
aws iam create-role --role-name "$NAME-server" --assume-role-policy-document '{
  "Version": "2012-10-17",
  "Statement": [{"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"}, "Action": "sts:AssumeRole"}]
}' >/dev/null
aws iam put-role-policy --role-name "$NAME-server" --policy-name read-bucket-and-secrets --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    {\"Effect\": \"Allow\", \"Action\": [\"s3:GetObject\", \"s3:ListBucket\"],
     \"Resource\": [\"arn:aws:s3:::$BUCKET\", \"arn:aws:s3:::$BUCKET/*\"]},
    {\"Effect\": \"Allow\", \"Action\": \"ssm:GetParameter\",
     \"Resource\": \"arn:aws:ssm:$REGION:$ACCOUNT:parameter/fire/*\"}
  ]
}"
# Lets you open a shell on the machine from the AWS console (Session Manager), without SSH keys.
aws iam attach-role-policy --role-name "$NAME-server" \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam create-instance-profile --instance-profile-name "$NAME-server" >/dev/null
aws iam add-role-to-instance-profile --instance-profile-name "$NAME-server" --role-name "$NAME-server"
sleep 15    # a new role needs a moment before EC2 accepts it

echo "4/6 security group"
VPC="$(aws ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text)"
GROUP="$(aws ec2 create-security-group --group-name "$NAME" --vpc-id "$VPC" \
  --description "Fire map: port 8080 from CloudFront only" --query GroupId --output text)"
PREFIX="$(aws ec2 describe-managed-prefix-lists \
  --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing \
  --query 'PrefixLists[0].PrefixListId' --output text)"
aws ec2 authorize-security-group-ingress --group-id "$GROUP" --ip-permissions \
  "IpProtocol=tcp,FromPort=8080,ToPort=8080,PrefixListIds=[{PrefixListId=$PREFIX}]" >/dev/null

echo "5/6 machine"
IMAGE="$(aws ssm get-parameter --query Parameter.Value --output text \
  --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64)"
USER_DATA="$(mktemp)"
cat > "$USER_DATA" <<EOF
#!/bin/bash
aws s3 cp s3://$BUCKET/server.sh /root/server.sh --region $REGION
bash /root/server.sh $BUCKET $REGION > /var/log/fire-install.log 2>&1
EOF
INSTANCE="$(aws ec2 run-instances --image-id "$IMAGE" --instance-type "$INSTANCE_TYPE" \
  --iam-instance-profile "Name=$NAME-server" --security-group-ids "$GROUP" \
  --block-device-mappings "DeviceName=/dev/xvda,Ebs={VolumeSize=$DISK_GB,VolumeType=gp3}" \
  --metadata-options HttpTokens=required \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" \
  --user-data "file://$USER_DATA" --query 'Instances[0].InstanceId' --output text)"
rm -f "$USER_DATA"
aws ec2 wait instance-running --instance-ids "$INSTANCE"
HOST="$(aws ec2 describe-instances --instance-ids "$INSTANCE" \
  --query 'Reservations[0].Instances[0].PublicDnsName' --output text)"

echo "6/6 CloudFront address"
# Managed policies: CachingDisabled for /api (answers depend on the query), CachingOptimized
# for the page and the 3D models, AllViewer to pass query strings to the server.
CONFIG="$(mktemp)"
cat > "$CONFIG" <<EOF
{
  "CallerReference": "$NAME-$(date +%s)",
  "Comment": "$NAME",
  "Enabled": true,
  "Origins": {"Quantity": 1, "Items": [{
    "Id": "server", "DomainName": "$HOST",
    "CustomOriginConfig": {"HTTPPort": 8080, "HTTPSPort": 443, "OriginProtocolPolicy": "http-only",
                           "OriginReadTimeout": 60}
  }]},
  "DefaultCacheBehavior": {
    "TargetOriginId": "server", "ViewerProtocolPolicy": "redirect-to-https", "Compress": true,
    "AllowedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]},
    "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6"
  },
  "CacheBehaviors": {"Quantity": 1, "Items": [{
    "PathPattern": "/api/*", "TargetOriginId": "server", "ViewerProtocolPolicy": "redirect-to-https",
    "Compress": true, "AllowedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]},
    "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
    "OriginRequestPolicyId": "216adef6-5c7f-47e4-b989-5492eafa07d3"
  }]}
}
EOF
DOMAIN="$(aws cloudfront create-distribution --distribution-config "file://$CONFIG" \
  --query Distribution.DomainName --output text)"
rm -f "$CONFIG"

echo
echo "Machine:  $INSTANCE ($HOST)"
echo "Address:  https://$DOMAIN   (ready in about 10 minutes)"
echo "Install log on the machine: /var/log/fire-install.log"
