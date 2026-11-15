#!/usr/bin/env bash
# Upload the code and the built data to a private S3 bucket.
#
# Run from the repository root, after the pipeline has built the data:
#   deploy/aws/upload.sh BUCKET
#
# Uploads
#   s3://BUCKET/app.tar.gz        server/, web/ and requirements.txt of the current commit
#   s3://BUCKET/server.sh         the script the machine runs at start
#   s3://BUCKET/data/fire.duckdb  the map database
#   s3://BUCKET/data/events/      fires as single events (if built)
#
# Raw CSV and intermediate Parquet stay on this computer: the server does not read them.
set -euo pipefail

BUCKET="${1:?usage: deploy/aws/upload.sh BUCKET}"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

[ -f data/fire.duckdb ] || { echo "data/fire.duckdb is missing. Run the pipeline first."; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git archive --format=tar.gz -o "$TMP/app.tar.gz" HEAD server web requirements.txt

aws s3 cp "$TMP/app.tar.gz" "s3://$BUCKET/app.tar.gz"
aws s3 cp deploy/aws/server.sh "s3://$BUCKET/server.sh"
aws s3 cp data/fire.duckdb "s3://$BUCKET/data/fire.duckdb"
if [ -d data/events ]; then
  aws s3 sync data/events "s3://$BUCKET/data/events" --delete
else
  echo "data/events is missing: the Fires panel will be empty."
fi
aws s3 ls "s3://$BUCKET" --recursive --human-readable
