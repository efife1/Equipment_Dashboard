#!/usr/bin/env bash
# ============================================================
# ESP32 GPIO Monitor — Raspberry Pi installer (GitHub edition)
# ------------------------------------------------------------
# Pulls the latest code straight from GitHub and sets up:
#   - Mosquitto MQTT broker
#   - Avahi mDNS advertisement (_mqtt._tcp) so ESP32 units find
#     this Pi automatically, with no IP hardcoded anywhere
#   - Python virtual environment + dependencies
#   - A systemd service so the server starts on boot and
#     restarts automatically if it ever crashes
#
# Usage:
#   git clone https://github.com/efife1/Equipment_Dashboard.git
#   cd Equipment_Dashboard/raspberry_pi_server
#   sudo ./install.sh
#
# Re-running this script later pulls the latest commit and
# updates the running service in place — handy for deploying
# updates to the fleet's server without doing it by hand.
# ============================================================

set -euo pipefail

REPO_URL="https://github.com/efife1/Equipment_Dashboard.git"
REPO_BRANCH="main"

# Path *within the repo* where gpio_server.py etc. live.
# Set to "" if your repo keeps them at the repo root instead of
# in a subfolder.
REPO_SUBDIR="raspberry_pi_server"

INSTALL_DIR="/opt/gpio-monitor"
SERVICE_NAME="gpio-server"
INSTALL_USER="${SUDO_USER:-$USER}"

if [ "$EUID" -ne 0 ]; then
  echo "This installer needs root privileges (it installs packages and a"
  echo "systemd service). Please re-run it with sudo:"
  echo "  sudo ./install.sh"
  exit 1
fi

echo "==> Installing for user: $INSTALL_USER"
echo

echo "==> [1/7] Installing system packages (git, mosquitto, avahi, python3-venv)..."
apt-get update -qq
apt-get install -y git mosquitto mosquitto-clients avahi-daemon python3-venv python3-pip
systemctl enable --now mosquitto

echo
echo "==> [2/7] Fetching code from GitHub ($REPO_URL, branch $REPO_BRANCH)..."
if [ -d "$INSTALL_DIR/.git" ]; then
  echo "Existing install found at $INSTALL_DIR — pulling latest changes..."
  git -C "$INSTALL_DIR" fetch --quiet origin "$REPO_BRANCH"
  git -C "$INSTALL_DIR" reset --quiet --hard "origin/$REPO_BRANCH"
else
  rm -rf "$INSTALL_DIR"
  git clone --quiet --branch "$REPO_BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi
chown -R "$INSTALL_USER":"$INSTALL_USER" "$INSTALL_DIR"

SRC_DIR="$INSTALL_DIR"
if [ -n "$REPO_SUBDIR" ]; then
  SRC_DIR="$INSTALL_DIR/$REPO_SUBDIR"
fi

if [ ! -f "$SRC_DIR/gpio_server.py" ]; then
  echo
  echo "ERROR: couldn't find gpio_server.py at:"
  echo "  $SRC_DIR"
  echo "Edit REPO_SUBDIR near the top of this script to match where the"
  echo "server files actually live in your repo, then run this again."
  exit 1
fi

echo
echo "==> [3/7] Advertising the MQTT broker via mDNS (_mqtt._tcp)..."
cp "$SRC_DIR/mqtt.service" /etc/avahi/services/mqtt.service
systemctl restart avahi-daemon

echo
echo "==> [4/7] Creating Python virtual environment and installing dependencies..."
sudo -u "$INSTALL_USER" python3 -m venv "$SRC_DIR/venv"
sudo -u "$INSTALL_USER" "$SRC_DIR/venv/bin/pip" install --quiet --upgrade pip
sudo -u "$INSTALL_USER" "$SRC_DIR/venv/bin/pip" install --quiet -r "$SRC_DIR/requirements.txt"

echo
echo "==> [5/7] Installing systemd service ($SERVICE_NAME)..."
sed -e "s/__INSTALL_USER__/$INSTALL_USER/" \
    -e "s#/opt/gpio-monitor#$SRC_DIR#g" \
    "$SRC_DIR/gpio-server.service" > "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo
echo "==> [6/7] Verifying the service started..."
sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
  echo "Service is running."
else
  echo "WARNING: service did not start cleanly. Check details with:"
  echo "  sudo journalctl -u $SERVICE_NAME -n 50"
fi

echo
echo "==> [7/7] Done."
PI_IP="$(hostname -I | awk '{print $1}')"

echo
echo "============================================================"
echo " Install complete — deployed from $REPO_URL @ $REPO_BRANCH"
echo "============================================================"
echo " Dashboard:      http://${PI_IP}:8080"
echo " Commission UI:  http://${PI_IP}:8080/commission"
echo " Raw JSON API:   http://${PI_IP}:8080/api/devices"
echo
echo " Verify mDNS advertisement from another machine with:"
echo "   avahi-browse -r _mqtt._tcp      (Linux)"
echo "   dns-sd -B _mqtt._tcp            (macOS)"
echo
echo " To deploy an update later: pull your changes to GitHub, then"
echo " just re-run this script — it re-clones and restarts the service."
echo
echo " Useful commands:"
echo "   sudo systemctl status $SERVICE_NAME    # check status"
echo "   sudo journalctl -u $SERVICE_NAME -f    # live logs"
echo "   sudo systemctl restart $SERVICE_NAME   # restart"
echo "============================================================"
