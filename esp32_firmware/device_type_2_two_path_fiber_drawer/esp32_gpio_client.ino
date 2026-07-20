/* ============================================================
   ESP32-S3 Ethernet GPIO Client — Device Type 2: 2 Path Fiber Drawer
   ------------------------------------------------------------
   Waveshare ESP32-S3-ETH firmware for card type 2 (see
   raspberry_pi_server/device_types.py, layout "fiber_drawer_2path").
   Reads 2 analog voltage inputs (fiber optical power, via an external
   voltage divider — see below) and 2 digital fault inputs, and publishes
   them over MQTT to a Raspberry Pi broker. Uses DHCP for IP assignment.

   This file is derived from esp32_firmware/_template/ — the networking,
   MQTT, and discovery code below is identical across every device type;
   only the GPIO_PINS/analog-reading section is specific to this card. See
   esp32_firmware/_template/README.md for how to create a new device type
   from scratch using this same base.

   HARDWARE: each voltage input requires an external resistor divider
   before the ESP32 pin — R1=56k ohm (source to ADC node), R2=10k ohm (ADC
   node to ground), giving a divide-by-6.6 ratio that brings a 0-20V
   source down to a safe 0-3.03V at the pin. A 3.3V Zener diode from the
   ADC node to ground and a 0.1uF ceramic cap across R2 are strongly
   recommended: the Zener clamps the pin if the source ever exceeds the
   expected 20V, and the cap filters noise that would otherwise show up as
   false fluctuations in the dashboard's reference/delta tracking. See
   docs/ for the full schematic.

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
#include <math.h>

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

// --- GPIO pins to monitor (4 total) ---
// Channel order: Path 1 voltage, Path 1 fault, Path 2 voltage, Path 2
// fault — the dashboard assumes this exact order (FD_CHANNELS_PER_PATH in
// gpio_server.py), so don't reorder these without updating that too.
//
// Chosen to avoid: the Ethernet SPI pins above (9-14), GPIO33-37 (reserved
// internally for PSRAM, not usable per Waveshare's own FAQ), the
// native-USB pins (19/20), and boot-strapping pins (0/3/45/46). The two
// voltage pins are also specifically within GPIO1-10 (ADC1), which avoids
// any WiFi-related ADC2 conflict entirely — not that it matters on this
// Ethernet-only board, but it's the more future-proof choice regardless.
const uint8_t GPIO_PINS[] = {
  1,    // Path 1 voltage (analog, via external divider)
  15,   // Path 1 fault (digital)
  2,    // Path 2 voltage (analog, via external divider)
  16,   // Path 2 fault (digital)
};
// true for channels read via analogReadMilliVolts() instead of
// digitalRead() — must stay the same length and order as GPIO_PINS above.
const bool IS_ANALOG[] = {
  true, false, true, false
};
// Computed automatically from the array above — never edit this directly,
// and never need to keep it in sync by hand when changing pin counts.
const uint8_t NUM_GPIO = sizeof(GPIO_PINS) / sizeof(GPIO_PINS[0]);

// --- Voltage divider recovery ---
// R1 = 56k ohm, R2 = 10k ohm -> ratio (R1+R2)/R2 = 6.6. The ADC reads the
// stepped-down voltage at the divider's midpoint; multiplying by this
// factor recovers the original 0-20V-range source value. Per this
// project's convention, mW = recovered source voltage directly (1:1).
const float DIVIDER_RECOVERY_FACTOR = 6.6;

// Number of ADC samples averaged per reading. Multiple samples smooth out
// electrical noise so small real fluctuations aren't drowned out by ADC
// jitter — important since the dashboard's "reference/delta" tracking
// depends on clean readings.
const uint8_t ANALOG_SAMPLES = 8;

// How much an analog reading has to change (in mW/volts) before it's
// treated as a real change worth publishing immediately, rather than
// waiting for the next heartbeat. Keeps small ADC jitter from spamming
// MQTT with publishes.
const float ANALOG_CHANGE_THRESHOLD = 0.02;

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
// float, not int: analog channels store fractional mW readings, digital
// channels store whole 0/1 values (which fit fine in a float too).
// Sized generously (up to 32 channels, matching this project's max card
// size) rather than exactly to NUM_GPIO — so reusing this firmware for a
// future device with a different channel count never requires touching
// this line, only GPIO_PINS above.
float lastStates[32];

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

// Reads one analog channel: averages several calibrated millivolt samples
// (using analogReadMilliVolts(), which corrects for the ESP32 ADC's known
// non-linearity, rather than raw analogRead() math) then applies the
// divider recovery factor to get back the original 0-20V-range value.
float readAnalogChannel(uint8_t pin) {
  uint32_t sumMv = 0;
  for (uint8_t i = 0; i < ANALOG_SAMPLES; i++) {
    sumMv += analogReadMilliVolts(pin);
    delay(2);
  }
  float voltsAtPin = (sumMv / (float)ANALOG_SAMPLES) / 1000.0;
  return voltsAtPin * DIVIDER_RECOVERY_FACTOR;
}

void publishStates(bool force) {
  bool changed = force;
  for (int i = 0; i < NUM_GPIO; i++) {
    float val = IS_ANALOG[i] ? readAnalogChannel(GPIO_PINS[i]) : (float)digitalRead(GPIO_PINS[i]);
    if (IS_ANALOG[i]) {
      if (fabs(val - lastStates[i]) > ANALOG_CHANGE_THRESHOLD) changed = true;
    } else {
      if (val != lastStates[i]) changed = true;
    }
    lastStates[i] = val;
  }
  if (!changed) return;

  JsonDocument doc;
  doc["device_id"] = deviceId;
  doc["mac"] = ETH.macAddress();       // used by the Pi to look up equipment name
  doc["ip"] = ETH.localIP().toString();
  JsonArray arr = doc["gpio"].to<JsonArray>();
  for (int i = 0; i < NUM_GPIO; i++) {
    if (IS_ANALOG[i]) {
      arr.add(roundf(lastStates[i] * 100) / 100.0);   // 2 decimal places
    } else {
      arr.add((int)lastStates[i]);
    }
  }

  char payload[512];
  size_t n = serializeJson(doc, payload);

  mqtt.publish(topicStatus.c_str(), (uint8_t*)payload, n, true); // retained
  Serial.print("Published: ");
  Serial.println(payload);
}

void setup() {
  Serial.begin(115200);

  for (int i = 0; i < NUM_GPIO; i++) {
    if (IS_ANALOG[i]) {
      // 11dB attenuation is required for the ADC to read the full 0-3.3V
      // range this circuit needs — without it, readings clip well below
      // the actual voltage present at the pin.
      analogSetPinAttenuation(GPIO_PINS[i], ADC_11db);
    } else {
      pinMode(GPIO_PINS[i], INPUT);
    }
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
