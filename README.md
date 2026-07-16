# ESP32 → Raspberry Pi GPIO Monitor (MQTT)

Multiple ESP32-Ethernet units each monitor 12 GPIO inputs and report their
state over MQTT (DHCP-assigned IPs) to a Raspberry Pi, which runs the MQTT
broker plus a small web dashboard/API.

```
[ESP32 #1] --Ethernet/DHCP--\
[ESP32 #2] --Ethernet/DHCP---> MQTT (Mosquitto on Pi) --> Flask dashboard/API
[ESP32 #N] --Ethernet/DHCP--/
```

## 1. Raspberry Pi setup

### Quick install (recommended)

The installer pulls the project straight from GitHub, so you don't need to
copy files onto the Pi by hand:
```bash
git clone https://github.com/efife1/Equipment_Dashboard.git
cd Equipment_Dashboard/raspberry_pi_server
sudo ./install.sh
```

This one script handles everything:
- Installs Mosquitto (MQTT broker) and starts it
- Installs Avahi and advertises the broker via mDNS (`_mqtt._tcp`) so ESP32
  units find it automatically
- Deploys the server code to `/opt/gpio-monitor`
- Creates a Python virtual environment and installs dependencies
- Installs a **systemd service** (`gpio-server`) so the server starts
  automatically on boot and restarts itself if it ever crashes
- Prints the dashboard URL when done

**Deploying updates later:** push your changes to GitHub, then just re-run
`sudo ./install.sh` on the Pi — it pulls the latest commit and restarts the
service. Your commissioning registry (`registry.json`) isn't tracked by git,
so it survives updates untouched.

> **Note:** `install.sh` assumes the repo keeps these server files in a
> `raspberry_pi_server/` subfolder, matching this project's layout. If your
> repo's structure is different, edit the `REPO_SUBDIR` variable near the
> top of `install.sh` to match (set it to `""` if the files sit at the repo
> root instead).

Once installed, manage it with:
```bash
sudo systemctl status gpio-server     # check status
sudo journalctl -u gpio-server -f     # live logs
sudo systemctl restart gpio-server    # restart
```

### Manual install (if you'd rather do it step by step)

Install the MQTT broker:
```bash
sudo apt update
sudo apt install -y mosquitto mosquitto-clients
sudo systemctl enable --now mosquitto
```

Advertise the broker on the network via mDNS so ESP32 units can find it
automatically (Raspberry Pi OS ships with Avahi already running, so this is
just adding a service definition):
```bash
cd raspberry_pi_server
sudo cp mqtt.service /etc/avahi/services/mqtt.service
sudo systemctl restart avahi-daemon
```

Verify it's visible on the network from another machine:
```bash
avahi-browse -r _mqtt._tcp      # Linux
dns-sd -B _mqtt._tcp            # macOS
```

Install Python dependencies and run the server:
```bash
pip install -r requirements.txt
python3 gpio_server.py
```
Run it manually like this whenever you want, or set it up as a persistent
service yourself — `gpio-server.service` (included) is the same systemd unit
the installer uses, if you want to install it by hand instead.

- Dashboard: `http://<pi-ip>:8080`
- Raw JSON:  `http://<pi-ip>:8080/api/devices`

The server needs no per-device configuration — any ESP32 that publishes to
`gpio/<device_id>/status` shows up automatically.

## 2. ESP32 client setup

1. In Arduino IDE, install board support: **Boards Manager → esp32 (Espressif Systems)**, version 2.0.12+.
2. Install libraries: **PubSubClient** and **ArduinoJson** (Library Manager). (**ESPmDNS** and **SPI** ship with the ESP32 core, no separate install needed.)
3. Open `esp32_gpio_client/esp32_gpio_client.ino`.
4. Board settings — this firmware targets the **Waveshare ESP32-S3-ETH** (onboard W5500 Ethernet over SPI):
   - **Tools → Board → esp32 → "ESP32S3 Dev Module"** (not plain "ESP32 Dev Module" — picking the wrong one causes an upload error like `This chip is ESP32-S3, not ESP32`)
   - **Tools → USB CDC On Boot → Enabled** (needed for Serial Monitor over this board's USB-C port)
5. Edit the **USER CONFIG** section at the top:
   - `GPIO_PINS[12]` → defaults are 12 pins already verified free on this board (avoiding the Ethernet SPI pins, the internally-reserved PSRAM pins, USB pins, and boot-strapping pins) — only change these if you also need the onboard TF card or camera header, since those share some of the same pins.
   - No broker address needed — it's discovered automatically via mDNS (see below).
6. Upload — this same firmware/config works unmodified on every unit, since nothing device- or network-specific is hardcoded.
7. Open Serial Monitor (115200 baud) to confirm it gets a DHCP address, finds the broker, and connects to MQTT.

Repeat for each unit — no code changes needed between units beyond confirming
the board type; each one auto-generates a unique device ID from its MAC
address (or set `DEVICE_NAME` for a fixed human-readable name instead).

### GPIO pin availability

This firmware targets the **Waveshare ESP32-S3-ETH**, which uses an onboard
W5500 chip over SPI for Ethernet (not the RMII/LAN8720 hardware other ESP32
Ethernet boards use). Its SPI bus and control pins are fixed by the board:
MISO=12, MOSI=11, SCLK=13, CS=14, RST=9, INT=10.

The default `GPIO_PINS[12]` (1, 2, 4, 5, 6, 7, 8, 15, 16, 17, 18, 21) avoids
those, avoids GPIO33–37 (reserved internally for PSRAM on this board's
ESP32-S3R8 per Waveshare's own FAQ), avoids the native-USB pins (19/20), and
avoids boot-strapping pins (0/3/45/46). If you plan to also use this board's
onboard TF card slot (GPIO4–7) or camera header, pick different signal pins
for those, since they overlap with a few of the defaults above.

## 3. Network notes

- All units use **DHCP** — no static IP config needed on the ESP32 side.
- The Pi's MQTT broker is found via **mDNS/Zeroconf** (`_mqtt._tcp` service
  advertised by Avahi) — no IP hardcoded on the ESP32 side either. This
  means the firmware is identical across every unit and units are fully
  interchangeable; swap one in and it finds the network's broker on its own.
- If the Pi's DHCP lease changes IP later, each ESP32 re-runs discovery on
  every MQTT reconnect attempt, so it picks up the new address automatically
  without a reflash.
- **Crossing VLANs/subnets:** mDNS relies on multicast traffic reaching both
  devices, so it works cleanly on a flat LAN but typically won't cross
  routed boundaries on its own. The firmware automatically falls back to a
  plain unicast DNS lookup (`MQTT_BROKER_HOSTNAME`, default
  `raspberrypi.lan`) if mDNS finds nothing — unicast DNS routes across
  VLANs like any other query, no reflector needed. To make the fallback
  actually resolve, do one of:
  - Give the Pi a DHCP reservation and confirm your router auto-registers
    DHCP client hostnames in its local DNS (many consumer/prosumer routers
    do this — check its "clients" or "DHCP leases" page for a hostname you
    can query), or
  - Add a manual local DNS A record for `raspberrypi.lan` pointing at the
    Pi's reserved IP (pfSense/OPNsense, Pi-hole, or your DNS server's admin
    page), or
  - Set up an **mDNS reflector** instead if your router/L3 switch supports
    one (e.g. UniFi's "mDNS Gateway" toggle, or `avahi-daemon-reflect` on a
    Linux router) — then mDNS itself crosses VLANs and the DNS fallback
    never even gets used.
  Any one of these is enough; the firmware doesn't need to be touched
  either way once one is in place.
- For predictability, you can still set a **DHCP reservation** for each
  ESP32's MAC on your router if you want consistent IPs for troubleshooting
  — it's optional now, since neither side depends on a fixed address.

## 4. Commissioning devices (MAC → equipment name)

Each ESP32 now reports its full MAC address in every MQTT message. The Pi
keeps a persistent registry (`raspberry_pi_server/registry.json`, created
automatically) mapping MAC addresses to equipment names, so the dashboard
shows *"Compressor Panel 3"* instead of a bare device ID.

**To commission a new unit:**
1. Power it on and let it connect — it'll show up on the dashboard as
   *"unregistered"* along with its MAC address.
2. Click **"register it"** next to it (or go to `http://<pi-ip>:8080/commission`
   and enter the MAC manually — also printed in Serial Monitor on boot).
3. Fill in the equipment name, and optionally a location and notes.
4. Save — the dashboard updates immediately, and the mapping persists across
   server restarts.

You can also view/edit/delete existing entries at `/commission`, or pull the
whole registry as JSON from `/api/registry`.

## 5. How offline detection works

- Each ESP32 sets an MQTT **Last Will** message (`offline`) that the broker
  publishes automatically if the connection drops uncleanly.
- Each ESP32 also publishes a heartbeat at least every 5 seconds (configurable
  via `PUBLISH_INTERVAL_MS`), even with no GPIO changes.
- The Pi server also independently marks a device **stale** if it hasn't
  heard from it in `STALE_TIMEOUT_SEC` (default 30s) — a backstop in case a
  device loses power abruptly and the LWT doesn't arrive in time.
