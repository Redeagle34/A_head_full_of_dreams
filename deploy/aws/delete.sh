#!/usr/bin/env bash
# Remove everything deploy/aws/create.sh made. Asks before it starts.
#
#   deploy/aws/delete.sh
#
# The data and the code stay on this computer; only the copy on AWS is removed.
set -uo pipefail
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
. deploy/aws/common.sh

read -r -p "Delete the machine $NAME, its addresses and its key? Type yes: " answer
[ "$answer" = yes ] || exit 1

step() { echo "$1"; shift; "$@" >/dev/null 2>&1 || echo "    not there, or could not be removed: check the Lightsail console"; }
step "https address" aws lightsail --region "$CDN_REGION" delete-distribution --distribution-name "$NAME"
step "fixed address: detach" aws lightsail detach-static-ip --static-ip-name "$IP_NAME"
step "fixed address: release" aws lightsail release-static-ip --static-ip-name "$IP_NAME"
step "machine" aws lightsail delete-instance --instance-name "$NAME"
step "key pair" aws lightsail delete-key-pair --key-pair-name "$KEY_NAME"
rm -f "$KEY_FILE" "$KNOWN_HOSTS"

echo "Left in the account (should be empty):"
aws lightsail get-instances --query "instances[?name=='$NAME'].name" --output text
aws lightsail get-static-ips --query "staticIps[?name=='$IP_NAME'].name" --output text
aws lightsail --region "$CDN_REGION" get-distributions --query "distributions[?name=='$NAME'].name" --output text
