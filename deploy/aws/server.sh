#!/usr/bin/env bash
# Install or update the server on the EC2 machine (Amazon Linux 2023). Run as root.
#
#   server.sh BUCKET REGION
#
# The machine runs it once at first start (deploy/aws/create.sh passes it as user data).
# To publish a new version: run deploy/aws/upload.sh again, then on the machine
#   sudo /opt/fire/server.sh BUCKET REGION
#
# What it does
#   1. downloads the code and the data from the bucket into /opt/fire
#   2. reads the secrets from SSM Parameter Store (/fire/...) into /opt/fire/app/.env
#   3. installs the Python packages and (re)starts the service on port 8080
set -euo pipefail

BUCKET="${1:?usage: server.sh BUCKET REGION}"
REGION="${2:?usage: server.sh BUCKET REGION}"
HOME_DIR=/opt/fire
APP="$HOME_DIR/app"

dnf install -y -q python3.12 python3.12-pip tar gzip
id fire >/dev/null 2>&1 || useradd --system --home-dir "$HOME_DIR" --shell /sbin/nologin fire
mkdir -p "$APP"

# 1. code and data
aws s3 cp "s3://$BUCKET/server.sh" "$HOME_DIR/server.sh" --region "$REGION" && chmod +x "$HOME_DIR/server.sh"
aws s3 cp "s3://$BUCKET/app.tar.gz" /tmp/app.tar.gz --region "$REGION"
rm -rf "$APP/server" "$APP/web"
tar -xzf /tmp/app.tar.gz -C "$APP"
aws s3 sync "s3://$BUCKET/data" "$APP/data" --delete --region "$REGION"

# 2. secrets (each is optional; a missing one only switches its feature off)
param() {
  aws ssm get-parameter --name "/fire/$1" --with-decryption --region "$REGION" \
    --query Parameter.Value --output text 2>/dev/null || true
}
umask 077
: > "$APP/.env"
for name in FIRMS_MAP_KEY EE_PROJECT; do
  value="$(param "$name")"
  [ -n "$value" ] && echo "$name=$value" >> "$APP/.env"
done
key="$(param EE_SERVICE_ACCOUNT_KEY_JSON)"
if [ -n "$key" ]; then
  printf '%s' "$key" > "$HOME_DIR/ee-key.json"
  echo "EE_SERVICE_ACCOUNT_KEY=$HOME_DIR/ee-key.json" >> "$APP/.env"
fi
umask 022

# 3. packages and service
[ -d "$HOME_DIR/venv" ] || python3.12 -m venv "$HOME_DIR/venv"
"$HOME_DIR/venv/bin/pip" install -q --upgrade pip
"$HOME_DIR/venv/bin/pip" install -q -r "$APP/requirements.txt" earthengine-api
chown -R fire:fire "$HOME_DIR"

cat > /etc/systemd/system/fire.service <<EOF
[Unit]
Description=Fire map server
After=network-online.target
Wants=network-online.target

[Service]
User=fire
WorkingDirectory=$APP
ExecStart=$HOME_DIR/venv/bin/python -m uvicorn server.main:app --host 0.0.0.0 --port 8080 --workers 2
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable fire.service
systemctl restart fire.service
sleep 5
curl -fsS http://localhost:8080/api/meta >/dev/null && echo "server answers on port 8080"
