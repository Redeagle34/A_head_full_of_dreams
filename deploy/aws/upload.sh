#!/usr/bin/env bash
# Copy the code, the built data and the secrets to the machine and (re)start the server.
#
# Run from the repository, after the pipeline has built the data and after create.sh:
#   deploy/aws/upload.sh
# Run it again to publish a new version of the code or the data.
#
# Copies
#   server/, web/, requirements.txt   of the current commit (uncommitted changes are not sent)
#   data/fire.duckdb                  the map database
#   data/events/                      fires one by one (if built)
#   FIRMS_MAP_KEY, EE_PROJECT         from .env
#   the Earth Engine key file         if EE_SERVICE_ACCOUNT_KEY in .env points to one
#
# Raw CSV and intermediate Parquet stay on this computer: the server does not read them.
# A server cannot use the browser sign-in of Earth Engine: without a service-account key
# the Landsat pictures answer "not available" and everything else works.
set -euo pipefail
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
. deploy/aws/common.sh

[ -f data/fire.duckdb ] || { echo "data/fire.duckdb is missing. Run the pipeline first."; exit 1; }
[ -f "$KEY_FILE" ] || { echo "$KEY_FILE is missing. Run deploy/aws/create.sh first."; exit 1; }
IP="$(machine_ip)"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git archive --format=tar.gz -o "$TMP/app.tar.gz" HEAD server web requirements.txt
cp deploy/aws/server.sh "$TMP/server.sh"
: > "$TMP/env"
if [ -f .env ]; then
  grep -E '^(FIRMS_MAP_KEY|EE_PROJECT)=.' .env > "$TMP/env" || true
  KEY_PATH="$(grep -E '^EE_SERVICE_ACCOUNT_KEY=.' .env | cut -d= -f2- || true)"
  [ -n "${KEY_PATH:-}" ] && [ -f "$KEY_PATH" ] && cp "$KEY_PATH" "$TMP/ee-key.json"
  # When service-account keys are blocked: an Earth Engine user sign-in limited to the
  # earthengine scope (see README). Copied to the server user's ~/.config/earthengine.
  CRED_PATH="$(grep -E '^EE_USER_CREDENTIALS=.' .env | cut -d= -f2- || true)"
  [ -n "${CRED_PATH:-}" ] && [ -f "$CRED_PATH" ] && cp "$CRED_PATH" "$TMP/ee-user-credentials"
fi
DATA=(fire.duckdb)
if [ -d data/events ]; then DATA+=(events); else echo "data/events is missing: the Fires panel will be empty."; fi

echo "copying to $IP (about $(du -shcL "${DATA[@]/#/data/}" | tail -1 | cut -f1))"
on_machine "rm -rf /tmp/fire-upload && mkdir -p -m 700 /tmp/fire-upload/data"
tar -C "$TMP" -cf - . | on_machine "tar -C /tmp/fire-upload -xf -"
tar -C data -chf - "${DATA[@]}" | on_machine "tar -C /tmp/fire-upload/data -xf -"
on_machine "sudo bash /tmp/fire-upload/server.sh"

# Answers are kept by the https address for a day: empty it so the new version shows.
if aws lightsail --region "$CDN_REGION" get-distributions --distribution-name "$NAME" >/dev/null 2>&1; then
  aws lightsail --region "$CDN_REGION" reset-distribution-cache --distribution-name "$NAME" >/dev/null
  echo "https address emptied of old answers"
fi
