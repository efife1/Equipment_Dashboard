# Adding a new device type

This folder holds one subfolder per physical device/card type, each a copy
of `_template/` with its `GPIO_PINS` customized. The networking, MQTT, and
broker-discovery code is identical across every device type — you're only
ever customizing which pins are read and (optionally) how the dashboard
displays them.

## Existing device types

| # | Name | Folder | Channels |
|---|------|--------|----------|
| 1 | Talent Pack Decoder | `device_type_1_talent_pack_decoder/` | 15 (3 decoders x 5) |
| 2 | 2 Path Fiber Drawer | `device_type_2_two_path_fiber_drawer/` | 4 (2 paths x 2, mixed analog/digital) |
| 3 | 8 Path Fiber Drawer | `device_type_3_eight_path_fiber_drawer/` | 16 (8 paths x 2, analog via external I2C ADC) |

## Steps to add a new one

### 1. Firmware

1. Copy `_template/` to `device_type_N_<short_name>/` (pick the next free N).
2. Rename `esp32_gpio_client_template.ino` inside it to `esp32_gpio_client.ino`.
3. Edit the `GPIO_PINS[]` array near the top — set it to whatever pins this
   device actually needs. `NUM_GPIO` is computed automatically from the
   array's size, so nothing else in the file needs touching just because
   the channel count changed.
4. Check `docs/ESP32-S3-ETH_Pinout.md` for which pins are safe to use on
   this board, and keep the Ethernet SPI pins (already `#define`'d near the
   top of the file) untouched — they're fixed by the board's hardware, not
   configurable.
5. **All-digital devices** (like the Talent Pack Decoder) can leave the
   template's channel-reading logic untouched. **If your device needs
   analog readings** (a varying voltage, not just on/off — like the Fiber
   Drawer's optical power sensors), use
   `device_type_2_two_path_fiber_drawer/esp32_gpio_client.ino` as your
   starting point instead of the plain template: it already has the
   `IS_ANALOG[]` array, calibrated `analogReadMilliVolts()` reading with
   sample averaging, and the ADC attenuation setup needed for accurate
   0–3.3V readings. Remember the ESP32's ADC pins can only read 0–3.3V —
   anything higher needs an external voltage divider (and likely a
   protection diode) before the signal reaches the pin; see that device
   type's section in the main README for a worked example.
6. Flash it to a unit and confirm in Serial Monitor that it gets a DHCP
   lease, finds the broker via mDNS, and connects to MQTT — all of that
   works identically to every other device type with zero code changes.

**Running out of native ADC pins?** `device_type_3_eight_path_fiber_drawer/`
is the reference example for reading analog channels through an external
I2C ADC (an ADS7828) instead of the ESP32's own ADC pins — useful any time
a device needs more analog channels than the board's ~7 safe native
ADC-capable pins can cover. Only 2 ESP32 pins (I2C SDA/SCL) are needed
regardless of how many channels the external ADC provides.

### 2. Raspberry Pi side

Decide whether this new type needs a **custom card layout** or can use the
**generic layout** that's already built in:

- **Generic layout (most cases):** no code changes needed at all. Go to
  `http://<pi-ip>:8080/device-types`, define a new type slot with a name,
  color, and a label for each GPIO channel. Commission a device with that
  MAC and pick the new type — done.

- **Custom layout (only if the generic per-GPIO label grid genuinely
  doesn't fit** — e.g. grouped sub-panels, live-editable per-group text
  fields, multi-pin combined indicators like the Talent Pack Decoder's
  2-way Error/Manual LED): this requires adding a bespoke renderer in
  `raspberry_pi_server/gpio_server.py`, following the same pattern as
  `talent_pack_decoder_view()` and the `layout == "talent_pack_decoder"`
  branch in the dashboard template. This is real code, not configuration —
  budget more time for it than the generic path.

Either way, the parts that never need to change for a new device type:
DHCP, mDNS/DNS broker discovery, MQTT connect/reconnect/Last-Will, the
commissioning registry, offline detection, and (for custom layouts that
want it) the live-save and event-logging infrastructure — all of that is
shared, generic, and already working.

## A known trade-off with this pattern

Because Arduino sketches don't have a clean way to share code between
`.ino` files without setting up a proper Arduino library, every device
type's networking/MQTT/discovery code is a **copy**, not a shared include.
That means if a bug is ever found in that shared logic (e.g. in
`discoverBroker()` or `mqttReconnect()`), it has to be fixed by hand in
every `device_type_N_.../esp32_gpio_client.ino` file individually — there's
no single place to patch once and have it apply everywhere.

This is fine at a handful of device types. If this project ever grows to
many device types that all need to be kept in lockstep, it's worth
refactoring the shared code into an actual Arduino library (a `.h`/`.cpp`
pair installed alongside the sketch) that every device type's `.ino`
includes rather than copies — a bigger change, but worth it past a certain
scale.
