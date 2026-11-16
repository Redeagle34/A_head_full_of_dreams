#!/usr/bin/env bash
# Create everything on AWS once: one Lightsail machine, a fixed address and an https address.
#
# Run from the repository, signed in to AWS (aws configure), after the pipeline:
#   deploy/aws/create.sh
#
# Creates (all named "fire-map", in us-east-1; see common.sh)
#   key pair         to reach the machine; the private key is saved in ~/.ssh/
#   machine          Ubuntu 24.04, 2 GB memory, 60 GB disk; ports 22 and 80 open
#   static IP        so the address survives a restart
#   distribution     the public https address (https://....cloudfront.net)
# and then runs deploy/aws/upload.sh.
#
# Cost while it exists: 12 USD a month for the machine and 2.50 USD for the distribution
# (AWS may waive part of it in the first months). Remove everything with deploy/aws/delete.sh.
#
# Safe to run again after a failure: steps already done are skipped.
set -euo pipefail
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
. deploy/aws/common.sh

[ -f data/fire.duckdb ] || { echo "data/fire.duckdb is missing. Run the pipeline first."; exit 1; }
exists() { "$@" >/dev/null 2>&1; }

echo "1/5 key pair"
if [ ! -s "$KEY_FILE" ]; then
  exists aws lightsail get-key-pair --key-pair-name "$KEY_NAME" && {
    echo "Key pair $KEY_NAME exists in AWS but $KEY_FILE is not on this computer. Run deploy/aws/delete.sh first."; exit 1; }
  mkdir -p -m 700 "$HOME/.ssh"
  (umask 077; aws lightsail create-key-pair --key-pair-name "$KEY_NAME" --query privateKeyBase64 --output text > "$KEY_FILE") || { rm -f "$KEY_FILE"; exit 1; }
fi

echo "2/5 machine"
if ! exists aws lightsail get-instance --instance-name "$NAME"; then
  aws lightsail create-instances --instance-names "$NAME" --availability-zone "$ZONE" \
    --blueprint-id "$BLUEPRINT" --bundle-id "$BUNDLE" --key-pair-name "$KEY_NAME" >/dev/null
fi
until [ "$(aws lightsail get-instance-state --instance-name "$NAME" --query state.name --output text)" = running ]; do sleep 5; done

echo "3/5 fixed address and ports"
if ! exists aws lightsail get-static-ip --static-ip-name "$IP_NAME"; then
  aws lightsail allocate-static-ip --static-ip-name "$IP_NAME" >/dev/null
fi
if [ "$(aws lightsail get-static-ip --static-ip-name "$IP_NAME" --query staticIp.isAttached --output text)" != True ]; then
  aws lightsail attach-static-ip --static-ip-name "$IP_NAME" --instance-name "$NAME" >/dev/null
  rm -f "$KNOWN_HOSTS"
fi
# 22: to copy files and look at logs. 80: the server; the https address reads from it.
aws lightsail put-instance-public-ports --instance-name "$NAME" --port-infos \
  fromPort=22,toPort=22,protocol=tcp fromPort=80,toPort=80,protocol=tcp >/dev/null
IP="$(machine_ip)"
echo "    $IP"
until on_machine true 2>/dev/null; do sleep 5; done

echo "4/5 code and data"
deploy/aws/upload.sh

echo "5/5 https address"
# The page, the 3D models and the answers of /api are kept for a day (an answer depends only
# on its query and the data changes only with upload.sh). Orbit data changes during the day.
if ! exists aws lightsail --region "$CDN_REGION" get-distributions --distribution-name "$NAME"; then
  aws lightsail --region "$CDN_REGION" create-distribution --distribution-name "$NAME" --bundle-id "$CDN_BUNDLE" \
    --origin "name=$NAME,regionName=$REGION,protocolPolicy=http-only" \
    --default-cache-behavior behavior=cache \
    --cache-behavior-settings '{
      "defaultTTL": 86400, "minimumTTL": 0, "maximumTTL": 86400,
      "allowedHTTPMethods": "GET,HEAD,OPTIONS,PUT,PATCH,POST,DELETE", "cachedHTTPMethods": "GET,HEAD",
      "forwardedCookies": {"option": "none"},
      "forwardedHeaders": {"option": "default"},
      "forwardedQueryStrings": {"option": true}
    }' \
    --cache-behaviors path=api/tle,behavior=dont-cache path=api/report,behavior=dont-cache >/dev/null
fi
DOMAIN="$(aws lightsail --region "$CDN_REGION" get-distributions --distribution-name "$NAME" --query 'distributions[0].domainName' --output text)"

echo
echo "Machine:  http://$IP   (works now)"
echo "Address:  https://$DOMAIN   (ready in about 10 minutes)"
echo "Shell:    ssh -i $KEY_FILE ubuntu@$IP"
