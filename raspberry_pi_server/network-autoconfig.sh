#!/usr/bin/env bash
# ============================================================
# Network auto-config for the ESP32 GPIO Monitor
# ------------------------------------------------------------
# Run on the interface connecting to the ESP32 units. Detects
# whether a DHCP server already exists on that network:
#
#   - If one IS found: leaves the interface in normal DHCP-client
#     mode (the Pi just gets an address like any other device) and
#     makes sure this Pi is NOT also handing out addresses, so it
#     never becomes a second, conflicting DHCP server.
#
#   - If NONE is found: assigns this Pi a fixed fallback address
#     and has it start serving DHCP itself — but only on this one
#     interface/segment (e.g. an isolated switch with the ESP32
#     units and nothing else), never routed anywhere else.
#
# Safe to re-run any time (e.g. after moving the Pi to a different
# network) — it re-probes and reconfigures automatically. It's also
# re-triggered automatically on link changes via a NetworkManager
# dispatcher hook installed by install.sh, so replugging into a
# different network re-detects without a reboot.
#
# REQUIRES NetworkManager (the default on Raspberry Pi OS Bookworm
# and newer). If your Pi uses dhcpcd/ifupdown instead, this script
# will tell you and exit — see the README for a manual dnsmasq
# alternative in that case.
#
# EDIT THESE if you need the fallback address to avoid colliding
# with something specific on your network:
# ============================================================
FALLBACK_IP="192.168.1.99"
FALLBACK_CIDR="24"
# ============================================================

set -euo pipefail

IFACE="${1:-eth0}"
PROBE_TIMEOUT=8

log() { echo "[net-autoconfig] $*"; }

if [ "$EUID" -ne 0 ]; then
  echo "Run with sudo: sudo $0 $IFACE"
  exit 1
fi

if ! command -v nmcli >/dev/null 2>&1 || ! systemctl is-active --quiet NetworkManager; then
  log "NetworkManager not detected as the active network manager on this system."
  log "This script only supports NetworkManager (default on Raspberry Pi OS"
  log "Bookworm+). See the README for a manual dnsmasq-based alternative."
  exit 1
fi

if ! command -v nmap >/dev/null 2>&1; then
  log "Installing nmap (used to probe for an existing DHCP server)..."
  apt-get update -qq
  apt-get install -y nmap
fi

CONN_NAME="$(nmcli -t -f DEVICE,CONNECTION device status | awk -F: -v i="$IFACE" '$1==i{print $2}')"
if [ -z "$CONN_NAME" ] || [ "$CONN_NAME" = "--" ]; then
  log "No NetworkManager connection profile found for $IFACE yet — creating one."
  nmcli connection add type ethernet ifname "$IFACE" con-name "gpio-monitor-$IFACE" >/dev/null
  CONN_NAME="gpio-monitor-$IFACE"
fi

log "Probing $IFACE for an existing DHCP server (timeout ${PROBE_TIMEOUT}s)..."
PROBE_OUTPUT="$(timeout "$PROBE_TIMEOUT" nmap --script broadcast-dhcp-discover -e "$IFACE" 2>&1 || true)"

if echo "$PROBE_OUTPUT" | grep -qi "DHCPOFFER\|Server Identifier"; then
  log "Existing DHCP server found on $IFACE — using it normally, and making"
  log "sure this Pi is NOT also serving DHCP on this interface."
  nmcli connection modify "$CONN_NAME" ipv4.method auto
  nmcli connection up "$CONN_NAME" >/dev/null
else
  log "No DHCP server found on $IFACE."
  log "This Pi will use $FALLBACK_IP/$FALLBACK_CIDR as its own fixed address"
  log "on this interface and serve DHCP itself to other devices on this"
  log "segment only (nothing is routed or bridged beyond this interface)."
  nmcli connection modify "$CONN_NAME" \
    ipv4.method shared \
    ipv4.addresses "$FALLBACK_IP/$FALLBACK_CIDR"
  nmcli connection up "$CONN_NAME" >/dev/null
fi

log "Done. Current address on $IFACE:"
ip -4 addr show "$IFACE" | grep inet || log "(no address yet — check 'nmcli device status')"
