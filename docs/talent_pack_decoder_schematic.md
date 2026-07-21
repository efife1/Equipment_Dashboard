# Talent Pack Decoder — Expansion Board Schematic

Detailed net-by-net wiring for the carrier/expansion PCB that the
Waveshare ESP32-S3-ETH plugs into. Same carrier-board concept as the
8 Path Fiber Drawer's board (see `fiber_drawer_8path_schematic.md`) — a
board the Waveshare board plugs into, with screw terminals and a
dedicated power input around the edges. Fully digital, no ADC chip and
no precision analog components — but every input does carry its own
overvoltage clamp circuit (see Section 2), since the real LED tap
voltage was never confirmed on hardware.

## 1. Power section

Identical to the other two device types' expansion boards:

```
DC power screw terminal (7-24V)
  DC_IN+ ---[SS34 Schottky, cathode toward regulator]---> VIN (buck regulator)
  DC_IN- ----------------------------------------------> GND (common ground)

5V buck regulator (e.g. Pololu D24V5F5, fixed 5V/500mA, 3-pin VIN/GND/VOUT)
  VOUT (5V) ---> Waveshare header pin VBUS
  GND        ---> Waveshare header pin GND (any GND pin on the header)
```

- The Schottky diode protects against reverse-polarity DC input.
- Do not power via both USB-C and this VBUS feed simultaneously unless
  you've confirmed the Waveshare board's power-path circuitry allows it.
- This board has no other components that need power — the 15 signal
  inputs are simple voltage-sense taps into the ESP32's own GPIO pins,
  nothing else on this board draws current.

## 2. Signal inputs (x15, one per LED tap) — clamp protection circuit

**RESOLVED (see `docs/OPEN_ITEMS.md`):** the actual LED tap voltage was
never confirmed on real hardware. Rather than block fabrication on that
measurement, each input uses a clamp instead of a plain series resistor
or a fixed divider. A clamp doesn't need the real voltage known in
advance — it passes real signals through close to unattenuated (useful
since these are digital on/off reads, not analog values needing
resolution) and only limits current once the voltage approaches the
design ceiling. This differs from the Fiber Drawer boards' dividers,
which are sized for a specific *known* source voltage — the Talent Pack
Decoder's source voltage was unknown, so a divider ratio picked for a
worst case would have under-driven the GPIO if the real voltage turned
out lower (e.g. 5V logic through a divider sized for 24V could fail to
register as a digital HIGH at all).

```
Screw terminal (LED tap signal) [SIG]
        |
        R1 (2.2k ohm, series)
        |
        +------------------> ESP32 GPIO (see pin table below)
        |
        +---[3.3V Zener, cathode up]---> GND   (shunt clamp)
        |
        R2 (100k ohm, pulldown)
        |
        GND
```

- **Design ceiling: 24V worst case.** At clamp, current through R1 is
  ~9-10mA — comfortably within a small SOT-23 zener's rating (300mW+
  parts handle this easily).
- **Pulldown (R2, 100k):** unlike the earlier no-pulldown design, this
  version includes one — it gives a clean, defined LOW when a tap is at
  0V or disconnected, and 100k is high enough not to meaningfully load
  the LED circuit's own node during normal sensing.
- **No further hardware verification required before fabrication** — the
  clamp works across the full range of plausible tap voltages (3.3V,
  5V, 12V logic, etc.) up to the 24V ceiling, so this design doesn't
  depend on knowing the exact real-world value.

## 3. ESP32 GPIO pin assignment

Matches the firmware in
`esp32_firmware/device_type_1_talent_pack_decoder/esp32_gpio_client.ino`:

| Decoder | On-Air | Prod | Error/Manual A | Error/Manual B | Call |
|---|---|---|---|---|---|
| 1 | GPIO1 | GPIO2 | GPIO15 | GPIO16 | GPIO17 |
| 2 | GPIO18 | GPIO21 | GPIO38 | GPIO39 | GPIO40 |
| 3 | GPIO41 | GPIO42 | GPIO47 | GPIO48 | GPIO43 |

GPIO44 is unused (spare).

## 4. Screw terminal summary

- 1x 2-position: DC power in (DC_IN+, DC_IN-)
- 3x 6-position: one per decoder (5 signal taps + 1 shared GND each), or
  a single larger 16-position block (15 signals + 1 shared GND) if you'd
  rather not split it by decoder — either works electrically, the
  per-decoder split just keeps field wiring visually organized to match
  the dashboard card's 3-decoder layout.

## Open items to verify before fabrication

- VBUS/3V3/GND exact physical pin positions on the Waveshare header
  (assumed standard Pico pinout, not independently confirmed) — same
  item as the other two device types, see `docs/OPEN_ITEMS.md`.
- The LED tap voltage item is **resolved** as of this revision — see
  Section 2's clamp circuit. No hardware measurement needed before
  fabrication.
