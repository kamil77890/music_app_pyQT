#!/usr/bin/env bash
set -euo pipefail

MUSIC_DIR="${MUSIC_LIBRARY_PATH:-/srv/music}"
MEDIA_GROUP="${MUSIC_LIBRARY_GROUP:-media}"
REAL_USER="${SUDO_USER:-${USER:-}}"

if [ -z "$REAL_USER" ]; then
  echo "ERROR: cannot determine real user (SUDO_USER/USER is empty)"
  exit 1
fi

sudo groupadd -f "$MEDIA_GROUP"
sudo usermod -aG "$MEDIA_GROUP" "$REAL_USER" || true
sudo usermod -aG "$MEDIA_GROUP" jellyfin || true

sudo mkdir -p "$MUSIC_DIR"
sudo chown -R "$REAL_USER:$MEDIA_GROUP" "$MUSIC_DIR"
sudo find "$MUSIC_DIR" -type d -exec chmod 2775 {} \;
sudo find "$MUSIC_DIR" -type f -exec chmod 664 {} \;

echo "Permissions fixed for $MUSIC_DIR"
echo "You may need to log out and log back in for group changes to apply."
