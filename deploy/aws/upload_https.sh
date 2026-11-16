#!/usr/bin/env bash
# Publish without SSH, for networks that block port 22. Same content as upload.sh, sent over https.
#
#   deploy/aws/upload_https.sh
#
# 1. Puts the code, the built data and the secrets in a private S3 bucket (one file).
# 2. Prints one command. Paste it in the machine's browser terminal:
#    Lightsail console > the machine > "Connect using SSH".
#    It downloads the file through a link that works for one hour and runs server.sh.
# 3. Afterwards run:  deploy/aws/upload_https.sh done    (deletes the file, empties the https address)
#
# Only committed code is sent, as with upload.sh.
set -euo pipefail
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
. deploy/aws/common.sh
BUCKET="$NAME-deploy-$(aws sts get-caller-identity --query Account --output text)"
OBJECT="s3://$BUCKET/bundle.tar"

if [ "${1:-}" = done ]; then
  aws s3 rm "$OBJECT"
  if aws lightsail --region "$CDN_REGION" get-distributions --distribution-name "$NAME" >/dev/null 2>&1; then
    aws lightsail --region "$CDN_REGION" reset-distribution-cache --distribution-name "$NAME" >/dev/null
    echo "https address emptied of old answers"
  fi
  exit 0
fi

[ -f data/fire.duckdb ] || { echo "data/fire.duckdb is missing. Run the pipeline first."; exit 1; }
aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null ||
  aws s3api create-bucket --bucket "$BUCKET" --create-bucket-configuration "LocationConstraint=$REGION" >/dev/null

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git archive --format=tar.gz -o "$TMP/app.tar.gz" HEAD server web requirements.txt
cp deploy/aws/server.sh "$TMP/server.sh"
: > "$TMP/env"
if [ -f .env ]; then
  grep -E '^(FIRMS_MAP_KEY|EE_PROJECT)=.' .env > "$TMP/env" || true
  KEY_PATH="$(grep -E '^EE_SERVICE_ACCOUNT_KEY=.' .env | cut -d= -f2- || true)"
  [ -n "${KEY_PATH:-}" ] && [ -f "$KEY_PATH" ] && cp "$KEY_PATH" "$TMP/ee-key.json"
  CRED_PATH="$(grep -E '^EE_USER_CREDENTIALS=.' .env | cut -d= -f2- || true)"
  [ -n "${CRED_PATH:-}" ] && [ -f "$CRED_PATH" ] && cp "$CRED_PATH" "$TMP/ee-user-credentials"
fi
mkdir "$TMP/data"
ln -s "$PWD/data/fire.duckdb" "$TMP/data/fire.duckdb"
[ -d data/events ] && ln -s "$PWD/data/events" "$TMP/data/events"

echo "uploading (about $(du -shcL "$TMP" | tail -1 | cut -f1))"
tar -C "$TMP" -chf - . | aws s3 cp - "$OBJECT" --only-show-errors
URL="$(aws s3 presign "$OBJECT" --expires-in 3600)"

echo
echo "Paste this in the machine's browser terminal (the link works for one hour):"
echo
echo "curl -fsSL '$URL' -o /tmp/bundle.tar && rm -rf /tmp/fire-upload && mkdir -m 700 /tmp/fire-upload && tar -C /tmp/fire-upload -xf /tmp/bundle.tar && rm /tmp/bundle.tar && sudo bash /tmp/fire-upload/server.sh"
echo
echo "When it says \"server answers on port 80\", run: deploy/aws/upload_https.sh done"
