#!/usr/bin/env bash
# ============================================================
# ESP32 GPIO Monitor — Raspberry Pi installer
# ------------------------------------------------------------
# Sets up everything needed to run the GPIO monitor server:
#   - Mosquitto MQTT broker
#   - Avahi mDNS advertisement (_mqtt._tcp) so ESP32 units find
#     this Pi automatically, with no IP hardcoded anywhere
#   - Python virtual environment + dependencies
#   - A systemd service so the server starts on boot and
#     restarts automatically if it ever crashes
#
# Usage:
#   chmod +x install.sh
#   ./install.sh
#
# Safe to re-run — every step is idempotent.
# ============================================================

set -euo pipefail

INSTALL_DIR="/opt/gpio-monitor"
SERVICE_NAME="gpio-server"
INSTALL_USER="${SUDO_USER:-$USER}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$EUID" -ne 0 ]; then
  echo "This installer needs root privileges (it installs packages and a"
  echo "systemd service). Please re-run it with sudo:"
  echo "  sudo ./install.sh"
  exit 1
fi

echo "==> Installing for user: $INSTALL_USER"
echo

echo "==> [1/6] Installing system packages (mosquitto, avahi, python3-venv)..."
apt-get update -qq
apt-get install -y mosquitto mosquitto-clients avahi-daemon python3-venv python3-pip
systemctl enable --now mosquitto

echo
echo "==> [2/6] Advertising the MQTT broker via mDNS (_mqtt._tcp)..."
cp "$SCRIPT_DIR/mqtt.service" /etc/avahi/services/mqtt.service
systemctl restart avahi-daemon

echo
echo "==> [3/6] Copying application files to $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/gpio_server.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/registry.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"
chown -R "$INSTALL_USER":"$INSTALL_USER" "$INSTALL_DIR"

echo
echo "==> [4/6] Creating Python virtual environment and installing dependencies..."
sudo -u "$INSTALL_USER" python3 -m venv "$INSTALL_DIR/venv"
sudo -u "$INSTALL_USER" "$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
sudo -u "$INSTALL_USER" "$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

echo
echo "==> [5/6] Installing systemd service ($SERVICE_NAME)..."
sed "s/__INSTALL_USER__/$INSTALL_USER/" "$SCRIPT_DIR/gpio-server.service" \
  > "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"

echo
echo "==> [6/6] Verifying the service started..."
sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
  echo "Service is running."
else
  echo "WARNING: service did not start cleanly. Check details with:"
  echo "  sudo journalctl -u $SERVICE_NAME -n 50"
fi

PI_IP="$(hostname -I | awk '{print $1}')"

echo
echo "============================================================"
echo " Install complete."
echo "============================================================"
echo " Dashboard:      http://${PI_IP}:8080"
echo " Commission UI:  http://${PI_IP}:8080/commission"
echo " Raw JSON API:   http://${PI_IP}:8080/api/devices"
echo
echo " Verify mDNS advertisement from another machine with:"
echo "   avahi-browse -r _mqtt._tcp      (Linux)"
echo "   dns-sd -B _mqtt._tcp            (macOS)"
echo
echo " Useful commands:"
echo "   sudo systemctl status $SERVICE_NAME    # check status"
echo "   sudo journalctl -u $SERVICE_NAME -f    # live logs"
echo "   sudo systemctl restart $SERVICE_NAME   # restart"
echo "============================================================"
