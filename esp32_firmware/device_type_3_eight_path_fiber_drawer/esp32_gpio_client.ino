/* ============================================================
   ESP32-S3 Ethernet GPIO Client — Device Type 3: 8 Path Fiber Drawer
   ------------------------------------------------------------
   Waveshare ESP32-S3-ETH firmware for card type 3 (see
   raspberry_pi_server/device_types.py, layout "fiber_drawer_8path").
   Reads 8 analog voltage inputs (fiber optical power, via an ADS7828
   8-channel I2C ADC + external voltage dividers — see below) and 8
   digital fault inputs, and publishes them over MQTT to a Raspberry Pi
   broker. Uses DHCP for IP assignment.

   This file is derived from esp32_firmware/_template/ — the networking,
   MQTT, and discovery code below is identical across every device type.
   Unlike device types 1 and 2, the channel-reading logic here is NOT the
   simple GPIO_PINS/IS_ANALOG pattern — the 8 voltage channels come from
   an external I2C ADC chip, not native ESP32 ADC pins, since this board
   doesn't have 8 safe native ADC-capable pins available. See
   docs/fiber_drawer_8path_schematic.md for the full hardware design and
   docs/OPEN_ITEMS.md for what's still unverified about that hardware.

   HARDWARE: each voltage input requires an external resistor divider
   (R1=75k ohm, R2=10k ohm, giving a divide-by-8.5 recovery factor) plus a
   2.7V Zener protection diode and 0.1uF filter cap, feeding one channel
   of an ADS7828 8-channel I2C ADC (address 0x48, A0/A1 tied to GND). The
   ADS7828's internal 2.5V reference is used, so the divider targets a
   safe max of ~2.35V at 20V input rather than the 3.3V range used by
   device type 2's native-ADC approach. See the schematic doc for the
   complete circuit.

   Written for ESP32 Arduino core v3.x (unified Network API) and
   the Waveshare ESP32-S3-ETH board, which uses an onboard W5500
   Ethernet chip over SPI (not the RMII/LAN8720 hardware found on
   boards like the Olimex ESP32-POE).

   REQUIRED LIBRARIES (Arduino IDE > Tools > Manage Libraries):
     - PubSubClient   by Nick O'Leary
     - ArduinoJson    by Benoit Blanchon
     (Wire.h ships with the ESP32 core, no separate install needed)

   BOARD SETUP (Arduino IDE):
     Tools > Board > esp32 > "ESP32S3 Dev Module"
     Tools > USB CDC On Boot > Enabled   (needed for Serial Monitor
                                           over this board's USB-C port)
   ============================================================ */

#include <ETH.h>
#include <ESPmDNS.h>
#include <SPI.h>
#include <Wire.h>
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

// --- Digital fault inputs (8 total, one per fiber path) ---
// Direct native GPIO reads, no ADC involved. See docs/fiber_drawer_8path_schematic.md
// for the full pin table and protection circuit (series resistor + pulldown).
const uint8_t FAULT_PINS[8] = {
  15, 16, 17, 18, 21, 38, 39, 40
};

// --- I2C bus to the ADS7828 8-channel ADC (the 8 voltage inputs) ---
// Chosen from the same safe-pin pool as everything else on this board.
const uint8_t I2C_SDA_PIN = 1;
const uint8_t I2C_SCL_PIN = 2;
const uint8_t ADS7828_I2C_ADDR = 0x48;   // A1=A0=GND on the schematic

// ADS7828 command bytes for single-ended channels 0-7, with internal
// 2.5V reference kept continuously on (PD1=1, PD0=1 on every command —
// per the datasheet, any command with PD1=0 turns the reference back
// off). Channel bit ordering here is NOT plain binary 0-7 — it follows
// the datasheet's own single-ended channel table, verified against TI's
// datasheet, the Linux kernel ads7828 driver, and a working example
// before use, since getting this table wrong silently reads the wrong
// channel rather than erroring.
const uint8_t ADS7828_CH_CMD[8] = {
  0x8C, 0xCC, 0x9C, 0xDC, 0xAC, 0xEC, 0xBC, 0xFC
};

// ADS7828's internal reference voltage (fixed by the chip, not
// adjustable) and this board's divider recovery factor: R1=75k, R2=10k
// -> (R1+R2)/R2 = 8.5. Per this project's convention, mW = recovered
// source voltage directly (1:1).
const float ADS7828_VREF = 2.5;
const float DIVIDER_RECOVERY_FACTOR = 8.5;

// Number of samples averaged per analog reading, and how much a reading
// has to move before it's worth publishing immediately rather than
// waiting for the next heartbeat — same rationale as device type 2.
const uint8_t ANALOG_SAMPLES = 8;
const float ANALOG_CHANGE_THRESHOLD = 0.02;

// Channel order in the published "gpio" array: Path1 voltage, Path1
// fault, Path2 voltage, Path2 fault, ... Path8 voltage, Path8 fault —
// the dashboard assumes this exact order (FD_CHANNELS_PER_PATH in
// gpio_server.py), so don't reorder without updating that too.
const uint8_t NUM_GPIO = 16;

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
// float, not int: voltage channels store fractional mW readings, fault
// channels store whole 0/1 values (which fit fine in a float too).
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

// Reads one ADS7828 channel: sends the command byte, waits briefly for
// the conversion, reads back the 12-bit result (first byte's low nibble
// is the high 4 bits, second byte is the low 8 bits — per the datasheet's
// read sequence), converts to volts against the 2.5V internal reference,
// then applies the divider recovery factor to get back the original
// 0-20V-range source value.
float readADS7828Channel(uint8_t ch) {
  Wire.beginTransmission(ADS7828_I2C_ADDR);
  Wire.write(ADS7828_CH_CMD[ch]);
  Wire.endTransmission();
  delay(2);   // conservative margin over the chip's ~20us conversion time

  Wire.requestFrom((int)ADS7828_I2C_ADDR, 2);
  if (Wire.available() < 2) {
    Serial.println("ADS7828 read failed (no response on I2C bus)");
    return NAN;
  }
  uint8_t hi = Wire.read();
  uint8_t lo = Wire.read();
  uint16_t raw = ((uint16_t)(hi & 0x0F) << 8) | lo;

  float voltsAtChip = raw * ADS7828_VREF / 4095.0;
  return voltsAtChip * DIVIDER_RECOVERY_FACTOR;
}

// Averages several readings of one channel to smooth out noise — same
// rationale as device type 2's readAnalogChannel().
float readADS7828ChannelAveraged(uint8_t ch) {
  float sum = 0;
  for (uint8_t i = 0; i < ANALOG_SAMPLES; i++) {
    float v = readADS7828Channel(ch);
    if (!isnan(v)) sum += v;
    delay(2);
  }
  return sum / ANALOG_SAMPLES;
}

void publishStates(bool force) {
  bool changed = force;
  float newValues[16];

  for (uint8_t p = 0; p < 8; p++) {
    newValues[p * 2]     = readADS7828ChannelAveraged(p);       // voltage
    newValues[p * 2 + 1] = (float)digitalRead(FAULT_PINS[p]);   // fault
  }

  for (int i = 0; i < NUM_GPIO; i++) {
    bool isVoltage = (i % 2 == 0);
    if (isVoltage) {
      if (fabs(newValues[i] - lastStates[i]) > ANALOG_CHANGE_THRESHOLD) changed = true;
    } else {
      if (newValues[i] != lastStates[i]) changed = true;
    }
    lastStates[i] = newValues[i];
  }
  if (!changed) return;

  JsonDocument doc;
  doc["device_id"] = deviceId;
  doc["mac"] = ETH.macAddress();       // used by the Pi to look up equipment name
  doc["ip"] = ETH.localIP().toString();
  JsonArray arr = doc["gpio"].to<JsonArray>();
  for (int i = 0; i < NUM_GPIO; i++) {
    if (i % 2 == 0) {
      arr.add(roundf(lastStates[i] * 100) / 100.0);   // voltage, 2 decimal places
    } else {
      arr.add((int)lastStates[i]);                    // fault, 0/1
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

  for (uint8_t i = 0; i < 8; i++) {
    pinMode(FAULT_PINS[i], INPUT);
  }
  for (int i = 0; i < NUM_GPIO; i++) {
    lastStates[i] = -1;  // force the first read to always publish
  }

  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  // The ADS7828's internal reference needs a settling delay the first
  // time it's turned on. Since every command byte we send keeps PD1=1,
  // the reference starts powering up after the very first Stop
  // condition — send one throwaway read here so real readings later
  // aren't the first ones taken right after power-up.
  readADS7828Channel(0);
  delay(50);

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
