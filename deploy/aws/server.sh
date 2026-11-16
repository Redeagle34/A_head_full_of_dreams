#!/usr/bin/env bash
# Install or update the server on the machine (Ubuntu 24.04). Run as root, on the machine.
# deploy/aws/upload.sh copies the files to /tmp/fire-upload and then runs this script.
#
# What it does
#   1. moves the code, the data and the secrets from /tmp/fire-upload into /opt/fire
#   2. installs the Python packages
#   3. (re)starts the service on port 80 and checks that it answers
set -euo pipefail

UPLOAD=/tmp/fire-upload
HOME_DIR=/opt/fire
APP="$HOME_DIR/app"

if ! python3 -c 'import venv, ensurepip' 2>/dev/null; then
  apt-get update -q
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3-venv
fi
id fire >/dev/null 2>&1 || useradd --system --home-dir "$HOME_DIR" --shell /usr/sbin/nologin fire
mkdir -p "$APP/data"

# 1. code, data, secrets
rm -rf "$APP/server" "$APP/web"
tar -xzf "$UPLOAD/app.tar.gz" -C "$APP"
mv -f "$UPLOAD/data/fire.duckdb" "$APP/data/fire.duckdb"
if [ -d "$UPLOAD/data/events" ]; then
  rm -rf "$APP/data/events"
  mv "$UPLOAD/data/events" "$APP/data/events"
fi
install -m 600 "$UPLOAD/env" "$APP/.env"
if [ -f "$UPLOAD/ee-key.json" ]; then
  install -m 600 "$UPLOAD/ee-key.json" "$HOME_DIR/ee-key.json"
  echo "EE_SERVICE_ACCOUNT_KEY=$HOME_DIR/ee-key.json" >> "$APP/.env"
fi
if [ -f "$UPLOAD/ee-user-credentials" ]; then
  install -d -m 700 "$HOME_DIR/.config" "$HOME_DIR/.config/earthengine"
  install -m 600 "$UPLOAD/ee-user-credentials" "$HOME_DIR/.config/earthengine/credentials"
fi
rm -rf "$UPLOAD"

# 2. packages
[ -d "$HOME_DIR/venv" ] || python3 -m venv "$HOME_DIR/venv"
"$HOME_DIR/venv/bin/pip" install -q --upgrade pip
"$HOME_DIR/venv/bin/pip" install -q -r "$APP/requirements.txt" earthengine-api
chown -R fire:fire "$HOME_DIR"

# 3. service
cat > /etc/systemd/system/fire.service <<UNIT
[Unit]
Description=Fire map server
After=network-online.target
Wants=network-online.target

[Service]
User=fire
WorkingDirectory=$APP
ExecStart=$HOME_DIR/venv/bin/python -m uvicorn server.main:app --host 0.0.0.0 --port 80 --workers 2
AmbientCapabilities=CAP_NET_BIND_SERVICE
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable -q fire.service
systemctl restart fire.service
for _ in $(seq 20); do
  if curl -fsS http://localhost/api/meta >/dev/null 2>&1; then echo "server answers on port 80"; exit 0; fi
  sleep 2
done
echo "the server does not answer. See: journalctl -u fire -n 50"
exit 1
