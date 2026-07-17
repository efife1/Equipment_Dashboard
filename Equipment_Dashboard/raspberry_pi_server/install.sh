#!/usr/bin/env bash
# ============================================================
# ESP32 GPIO Monitor — Raspberry Pi installer (GitHub edition)
# ------------------------------------------------------------
# Pulls the latest code straight from GitHub and sets up:
#   - Mosquitto MQTT broker (listening on all interfaces)
#   - Network auto-config: detects whether a DHCP server already
#     exists on the ESP32-facing interface. If so, leaves the Pi
#     as a normal DHCP client. If not, the Pi assigns itself a
#     fixed fallback address and serves DHCP itself to that
#     segment only — auto re-checked on every link change, so
#     moving the Pi to a different network needs no manual steps.
#   - Avahi mDNS advertisement (_mqtt._tcp) so ESP32 units find
#     this Pi automatically, with no IP hardcoded anywhere
#   - Python virtual environment + dependencies
#   - A systemd service so the server starts on boot and
#     restarts automatically if it ever crashes
#
# Usage:
#   git clone https://github.com/efife1/Equipment_Dashboard.git
#   cd Equipment_Dashboard/raspberry_pi_server
#   sudo bash install.sh
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

# The network interface connecting to the ESP32 units (usually the
# Pi's wired Ethernet port). Edit if yours is named differently
# (check with `ip link` — e.g. it may be "end0" on some Pi models).
TARGET_IFACE="eth0"

INSTALL_DIR="/opt/gpio-monitor"
SERVICE_NAME="gpio-server"
INSTALL_USER="${SUDO_USER:-$USER}"

if [ "$EUID" -ne 0 ]; then
  echo "This installer needs root privileges (it installs packages and a"
  echo "systemd service). Please re-run it with sudo:"
  echo "  sudo bash install.sh"
  exit 1
fi

echo "==> Installing for user: $INSTALL_USER"
echo "==> Target interface: $TARGET_IFACE (edit TARGET_IFACE at the top of"
echo "    this script if that's not the port your ESP32 units connect to)"
echo

echo "==> [1/9] Installing system packages (git, mosquitto, avahi, nmap, python3-venv)..."
apt-get update -qq
apt-get install -y git mosquitto mosquitto-clients avahi-daemon nmap python3-venv python3-pip
systemctl enable --now mosquitto

echo
echo "==> [2/9] Fetching code from GitHub ($REPO_URL, branch $REPO_BRANCH)..."
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
echo "==> [3/9] Configuring Mosquitto to listen on all interfaces..."
cat > /etc/mosquitto/conf.d/gpio-monitor.conf << 'EOF'
listener 1883 0.0.0.0
allow_anonymous true
EOF
systemctl restart mosquitto

echo
echo "==> [4/9] Setting up network auto-config for $TARGET_IFACE..."
cp "$SRC_DIR/network-autoconfig.sh" "$INSTALL_DIR/network-autoconfig.sh"
chmod +x "$INSTALL_DIR/network-autoconfig.sh"

sed "s/__TARGET_IFACE__/$TARGET_IFACE/" "$SRC_DIR/network-autoconfig.service" \
  > /etc/systemd/system/network-autoconfig.service
sed "s/__TARGET_IFACE__/$TARGET_IFACE/" "$SRC_DIR/99-gpio-monitor-autoconfig" \
  > /etc/NetworkManager/dispatcher.d/99-gpio-monitor-autoconfig
chmod +x /etc/NetworkManager/dispatcher.d/99-gpio-monitor-autoconfig

if command -v nmcli >/dev/null 2>&1 && systemctl is-active --quiet NetworkManager; then
  systemctl daemon-reload
  systemctl enable --now network-autoconfig.service
  echo "Running an initial DHCP-presence check on $TARGET_IFACE now..."
  "$INSTALL_DIR/network-autoconfig.sh" "$TARGET_IFACE" || \
    echo "WARNING: initial network auto-config check failed — see output above."
else
  echo "NetworkManager not detected as active — skipping network auto-config."
  echo "(Your Pi's network stack differs from what this feature supports;"
  echo "see the README for a manual DHCP fallback option if you need one.)"
fi

echo
echo "==> [5/9] Advertising the MQTT broker via mDNS (_mqtt._tcp)..."
cp "$SRC_DIR/mqtt.service" /etc/avahi/services/mqtt.service
systemctl restart avahi-daemon

echo
echo "==> [6/9] Creating Python virtual environment and installing dependencies..."
sudo -u "$INSTALL_USER" python3 -m venv "$SRC_DIR/venv"
sudo -u "$INSTALL_USER" "$SRC_DIR/venv/bin/pip" install --quiet --upgrade pip
sudo -u "$INSTALL_USER" "$SRC_DIR/venv/bin/pip" install --quiet -r "$SRC_DIR/requirements.txt"

echo
echo "==> [7/9] Installing systemd service ($SERVICE_NAME)..."
sed -e "s/__INSTALL_USER__/$INSTALL_USER/" \
    -e "s#/opt/gpio-monitor#$SRC_DIR#g" \
    "$SRC_DIR/gpio-server.service" > "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo
echo "==> [8/9] Verifying the service started..."
sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
  echo "Service is running."
else
  echo "WARNING: service did not start cleanly. Check details with:"
  echo "  sudo journalctl -u $SERVICE_NAME -n 50"
fi

echo
echo "==> [9/9] Done."
PI_IP="$(hostname -I | awk '{print $1}')"

echo
echo "============================================================"
echo " Install complete — deployed from $REPO_URL @ $REPO_BRANCH"
echo "============================================================"
echo " Dashboard:      http://${PI_IP}:8080"
echo " Commission UI:  http://${PI_IP}:8080/commission"
echo " Raw JSON API:   http://${PI_IP}:8080/api/devices"
echo
echo " Network auto-config log: /var/log/gpio-monitor-net.log"
echo " Re-check DHCP presence manually any time with:"
echo "   sudo $INSTALL_DIR/network-autoconfig.sh $TARGET_IFACE"
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
