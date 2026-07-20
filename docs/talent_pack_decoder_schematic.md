# Talent Pack Decoder — Expansion Board Schematic

Detailed net-by-net wiring for the carrier/expansion PCB that the
Waveshare ESP32-S3-ETH plugs into. Same carrier-board concept as the
8 Path Fiber Drawer's board (see `fiber_drawer_8path_schematic.md`) — a
board the Waveshare board plugs into, with screw terminals and a
dedicated power input around the edges — but simpler, since this device
is fully digital with no analog readings and no external ADC chip.

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

## 2. Signal inputs (x15, one per LED tap)

Each input is a direct voltage-sense tap — the ESP32 reads whatever
voltage is present at the node between a GPIO and the current-limiting
resistor on the Talent Pack Decoder's own LED circuit (see the very
first design discussion in this project for why this works: a
high-impedance ADC/digital input doesn't meaningfully load that node, so
tapping it doesn't disturb the LED's own operation).

```
Screw terminal (LED tap signal) [SIG]
        |
        R (1k ohm, series protection — optional but recommended for a
           field-wired board; limits fault current into the ESP32 pin
           without meaningfully affecting the voltage reading, since the
           ESP32's GPIO input impedance is very high)
        |
        ESP32 GPIO (see pin table below)
```

**No pulldown resistor** on these inputs, unlike the Fault inputs on the
Fiber Drawer boards — this preserves the original "just read whatever
voltage is present" sensing behavior this device type was built around.
Adding a pulldown would interfere with that if the Talent Pack Decoder's
own circuit doesn't actively drive the line to a defined level when idle.

**Open question carried over from the original design (see
`docs/OPEN_ITEMS.md`):** these taps were designed assuming the Talent
Pack Decoder's LED circuits run at 3.3V logic-compatible levels, since no
divider was ever built for this device type. If the actual voltage at
any of these tap points exceeds ~3.6V (the ESP32 GPIO's absolute
maximum), it will damage the pin — confirm the actual voltage with a
multimeter on real hardware before wiring this in, and add a divider
(same technique as the Fiber Drawer boards) for any tap that reads higher
than that.

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

Same as the other two device types — see `docs/OPEN_ITEMS.md`:
- VBUS/3V3/GND exact physical pin positions on the Waveshare header
  (assumed standard Pico pinout, not independently confirmed).
- **New for this device**: the actual LED tap voltage level on real
  Talent Pack Decoder hardware — confirm it's within 3.3V logic range
  before wiring, per the note in Section 2 above.
