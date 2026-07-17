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
5. Flash it to a unit and confirm in Serial Monitor that it gets a DHCP
   lease, finds the broker via mDNS, and connects to MQTT — all of that
   works identically to every other device type with zero code changes.

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
