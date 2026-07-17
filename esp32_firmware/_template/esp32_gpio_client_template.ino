/* ============================================================
   ESP32-S3 Ethernet GPIO Client — TEMPLATE
   ------------------------------------------------------------
   Base firmware for the Waveshare ESP32-S3-ETH used by every device
   type in this project. The networking, MQTT, and broker-discovery code
   below (Ethernet/W5500 setup, DHCP, mDNS + DNS fallback, MQTT connect,
   state publishing) is IDENTICAL across every device type — none of it
   needs to change when creating a new one.

   TO CREATE A NEW DEVICE TYPE:
     1. Copy this whole esp32_firmware/_template/ folder to
        esp32_firmware/device_type_N_<name>/ (pick the next free N).
     2. Rename this file to esp32_gpio_client.ino.
     3. Edit ONLY the "GPIO_PINS" section below — set it to the pins
        this new device actually needs. NUM_GPIO is computed
        automatically from the array, so nothing else needs touching
        just to change the channel count.
     4. On the Pi side: decide whether this new type needs a custom card
        layout (like the Talent Pack Decoder) or can just use the
        built-in generic per-GPIO label grid (most simple types can).
        See esp32_firmware/_template/README.md for the full workflow,
        including the Pi-side steps.

   Written for ESP32 Arduino core v3.x (unified Network API) and
   the Waveshare ESP32-S3-ETH board, which uses an onboard W5500
   Ethernet chip over SPI (not the RMII/LAN8720 hardware found on
   boards like the Olimex ESP32-POE).

   REQUIRED LIBRARIES (Arduino IDE > Tools > Manage Libraries):
     - PubSubClient   by Nick O'Leary
     - ArduinoJson    by Benoit Blanchon

   BOARD SETUP (Arduino IDE):
     Tools > Board > esp32 > "ESP32S3 Dev Module"
     Tools > USB CDC On Boot > Enabled   (needed for Serial Monitor
                                           over this board's USB-C port)
   ============================================================ */

#include <ETH.h>
#include <ESPmDNS.h>
#include <SPI.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ================= USER CONFIG =================

// No broker IP needed anymore — the Pi is found automatically on the
// network via mDNS (it advertises itself as an "_mqtt._tcp" service).
// See raspberry_pi_server setup for the matching Avahi service file.
//
// If mDNS can't reach the Pi (e.g. it's on a different VLAN/subnet, since
// mDNS relies on multicast which usually doesn't cross routed boundaries),
// this falls back to a plain unicast DNS lookup of the hostname below,
// which routes fine across VLANs like any other DNS query. Set this to
// whatever hostname resolves to your Pi on your network (a DHCP
// reservation + matching DNS entry, or a router that auto-registers
// DHCP client hostnames — check your router's local DNS / "clients" page).
const char* MQTT_BROKER_HOSTNAME = "raspberrypi.lan";
const uint16_t DEFAULT_MQTT_PORT = 1883;   // used only for the DNS fallback path

// Friendly name for this unit. Leave blank ("") to auto-generate
// a unique ID from the MAC address instead (recommended for fleets).
const char* DEVICE_NAME = "";

// Publish at least this often, even with no change (heartbeat so
// the server can tell a live "all zero" unit from a dead one).
const unsigned long PUBLISH_INTERVAL_MS = 5000;

// --- Ethernet PHY config: Waveshare ESP32-S3-ETH (onboard W5500 over SPI) ---
// Pin assignments per Waveshare's official pinout for this board.
#define ETH_PHY_TYPE   ETH_PHY_W5500
#define ETH_PHY_ADDR   1
#define ETH_PHY_CS     14   // Ethernet chip-select
#define ETH_PHY_IRQ    10   // Ethernet interrupt
#define ETH_PHY_RST    9    // Ethernet reset
#define ETH_SPI_SCK    13
#define ETH_SPI_MISO   12
#define ETH_SPI_MOSI   11

// --- GPIO pins to monitor: CUSTOMIZE THIS SECTION FOR YOUR NEW DEVICE ---
// Replace the example pins below with whatever this device type actually
// needs. Order matters if you're building a card with a fixed per-group
// layout (like the Talent Pack Decoder's 5-per-decoder pattern) — the
// Pi-side card renderer for a custom layout will assume the same channel
// order you use here, so document and keep them in sync deliberately.
//
// PIN SAFETY on the Waveshare ESP32-S3-ETH — see docs/ESP32-S3-ETH_Pinout.md
// for the full breakdown, but in short, avoid:
//   - GPIO9-14 (used by the onboard Ethernet SPI, fixed by the board)
//   - GPIO33-37 (reserved internally for PSRAM, not usable at all)
//   - GPIO19-20 (native-USB D-/D+)
//   - GPIO0/3/45/46 (boot-strapping pins — risky, avoid unless necessary)
// That leaves roughly 16 safe general-purpose pins to work with:
//   Left header:  1, 2, 15, 16, 17, 18, 21
//   Right header: 38, 39, 40, 41, 42, 43, 44, 47, 48
const uint8_t GPIO_PINS[] = {
  1, 2, 4, 5, 6   // <-- EXAMPLE ONLY. Replace with your real pin list.
};
// Computed automatically from the array above — never edit this directly,
// and never need to keep it in sync by hand when changing pin counts.
const uint8_t NUM_GPIO = sizeof(GPIO_PINS) / sizeof(GPIO_PINS[0]);

// =================================================

static bool eth_connected = false;
String deviceId;
String topicStatus;
String topicLWT;

IPAddress brokerIP;
uint16_t brokerPort = 1883;

NetworkClient ethClient;
PubSubClient mqtt(ethClient);
SPIClass ethSPI(FSPI);   // dedicated SPI bus for the W5500

unsigned long lastPublish = 0;
// Sized generously (up to 32 channels, matching this project's max card
// size) rather than exactly to NUM_GPIO — so reusing this firmware for a
// future device with a different channel count never requires touching
// this line, only GPIO_PINS above.
int lastStates[32];

// WARNING: onEvent is called from a separate FreeRTOS task (thread)!
void onEvent(arduino_event_id_t event) {
  switch (event) {
    case ARDUINO_EVENT_ETH_START:
      Serial.println("ETH Started");
      // Hostname must be set here — after the interface starts but
      // before DHCP — so it's applied from this event handler thread.
      ETH.setHostname("esp32-gpio-client");
      break;
    case ARDUINO_EVENT_ETH_CONNECTED:
      Serial.println("ETH Connected (link up)");
      break;
    case ARDUINO_EVENT_ETH_GOT_IP:
      Serial.print("ETH got IP via DHCP: ");
      Serial.println(ETH.localIP());
      eth_connected = true;
      break;
    case ARDUINO_EVENT_ETH_DISCONNECTED:
      Serial.println("ETH Disconnected");
      eth_connected = false;
      break;
    case ARDUINO_EVENT_ETH_STOP:
      Serial.println("ETH Stopped");
      eth_connected = false;
      break;
    default:
      break;
  }
}

String macToId() {
  String mac = ETH.macAddress();   // e.g. "A1:B2:C3:D4:E5:F6"
  mac.replace(":", "");
  mac.toLowerCase();
  return "esp32-" + mac.substring(6);  // last 6 hex chars -> esp32-d4e5f6
}

// Searches the local network for a service advertising itself as
// "_mqtt._tcp" (the Raspberry Pi, via Avahi) and fills in brokerIP/brokerPort.
// Falls back to a plain DNS hostname lookup if mDNS finds nothing — this
// covers the Pi being on a different VLAN/subnet, since regular unicast DNS
// routes across those boundaries even though mDNS's multicast traffic
// typically doesn't.
// Returns true on success. Safe to call again later to pick up a new IP
// if the Pi's address ever changes (e.g. after a DHCP lease renewal).
bool discoverBroker() {
  Serial.println("Searching for MQTT broker via mDNS (_mqtt._tcp)...");
  int n = MDNS.queryService("mqtt", "tcp");
  if (n > 0) {
    brokerIP = MDNS.address(0);
    brokerPort = MDNS.port(0);
    Serial.print("Found broker via mDNS at ");
    Serial.print(brokerIP);
    Serial.print(":");
    Serial.println(brokerPort);
    return true;
  }
  Serial.println("mDNS discovery failed (expected if crossing a VLAN/subnet).");

  Serial.print("Trying DNS fallback hostname: ");
  Serial.println(MQTT_BROKER_HOSTNAME);
  IPAddress resolvedIP;
  if (Network.hostByName(MQTT_BROKER_HOSTNAME, resolvedIP) == 1) {
    brokerIP = resolvedIP;
    brokerPort = DEFAULT_MQTT_PORT;
    Serial.print("Found broker via DNS at ");
    Serial.println(brokerIP);
    return true;
  }

  Serial.println("DNS fallback also failed.");
  return false;
}

void mqttReconnect() {
  while (!mqtt.connected()) {
    discoverBroker();               // pick up a new IP if the Pi's has changed
    mqtt.setServer(brokerIP, brokerPort);

    Serial.print("Connecting to MQTT broker...");
    // Last Will: if this unit drops off ungracefully, broker announces it
    if (mqtt.connect(deviceId.c_str(), topicLWT.c_str(), 1, true, "offline")) {
      Serial.println(" connected");
      mqtt.publish(topicLWT.c_str(), "online", true);
    } else {
      Serial.print(" failed, rc=");
      Serial.print(mqtt.state());
      Serial.println(" — retrying in 3s");
      delay(3000);
    }
  }
}

void publishStates(bool force) {
  bool changed = force;
  for (int i = 0; i < NUM_GPIO; i++) {
    int val = digitalRead(GPIO_PINS[i]);
    if (val != lastStates[i]) changed = true;
    lastStates[i] = val;
  }
  if (!changed) return;

  JsonDocument doc;
  doc["device_id"] = deviceId;
  doc["mac"] = ETH.macAddress();       // used by the Pi to look up equipment name
  doc["ip"] = ETH.localIP().toString();
  JsonArray arr = doc["gpio"].to<JsonArray>();
  for (int i = 0; i < NUM_GPIO; i++) arr.add(lastStates[i]);

  char payload[512];
  size_t n = serializeJson(doc, payload);

  mqtt.publish(topicStatus.c_str(), (uint8_t*)payload, n, true); // retained
  Serial.print("Published: ");
  Serial.println(payload);
}

void setup() {
  Serial.begin(115200);

  for (int i = 0; i < NUM_GPIO; i++) {
    pinMode(GPIO_PINS[i], INPUT);
    lastStates[i] = -1;  // force the first read to always publish
  }

  Network.onEvent(onEvent);
  ethSPI.begin(ETH_SPI_SCK, ETH_SPI_MISO, ETH_SPI_MOSI, ETH_PHY_CS);
  ETH.begin(ETH_PHY_TYPE, ETH_PHY_ADDR, ETH_PHY_CS, ETH_PHY_IRQ, ETH_PHY_RST,
            ethSPI);   // DHCP happens automatically

  Serial.println("Waiting for Ethernet link + DHCP lease...");
  while (!eth_connected) { delay(200); }

  deviceId = (strlen(DEVICE_NAME) > 0) ? String(DEVICE_NAME) : macToId();
  topicStatus = "gpio/" + deviceId + "/status";
  topicLWT    = "gpio/" + deviceId + "/lwt";

  Serial.print("Device ID: ");
  Serial.println(deviceId);

  MDNS.begin(deviceId.c_str());   // unique mDNS hostname per unit

  while (!discoverBroker()) {
    Serial.println("Retrying broker discovery in 5s...");
    delay(5000);
  }

  mqtt.setServer(brokerIP, brokerPort);
}

void loop() {
  if (!eth_connected) { delay(500); return; }
  if (!mqtt.connected()) mqttReconnect();
  mqtt.loop();

  unsigned long now = millis();
  if (now - lastPublish >= PUBLISH_INTERVAL_MS) {
    lastPublish = now;
    publishStates(true);    // heartbeat: publish regardless of change
  } else {
    publishStates(false);   // also publish immediately on any change
  }
}
