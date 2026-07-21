# Talent Pack Decoder — Bill of Materials

Quantities are per single expansion board (one Talent Pack Decoder unit).
This is the simplest of the three boards — fully digital, no analog
components, no external ADC chip.

| # | Part | Qty | Approx unit cost | Notes |
|---|------|-----|------|-------|
| 1 | Waveshare ESP32-S3-ETH | 1 | $15-20 | The board this project already targets |
| 2 | Resistor, 2.2k ohm, 0805 or THT | 15 | $0.05 | Series resistor, one per LED tap input (clamp circuit) |
| 3 | Zener diode, 3.3V, e.g. BZX55C3V3 | 15 | $0.10 | Shunt overvoltage clamp, one per LED tap input |
| 4 | Resistor, 100k ohm, 0805 or THT | 15 | $0.05 | Pulldown, one per LED tap input (clamp circuit) |
| 5 | Schottky diode, e.g. SS34 | 1 | $0.20 | Reverse-polarity protection on DC input |
| 6 | 5V buck regulator module, e.g. Pololu D24V5F5 (or equivalent fixed-5V, >=500mA module) | 1 | $5-8 | Steps down DC input to 5V for the Waveshare board's VBUS |
| 7 | 2-position 5.08mm pluggable screw terminal block | 1 | $0.50 | DC power input |
| 8 | 6-position 5.08mm pluggable screw terminal block | 3 | $1-1.50 each | One per decoder (5 signals + shared GND) |
| 9 | 2x20 pin female header socket, 2.54mm pitch, "short" Pico-compatible style | 2 | $1-2 each | Carrier board sockets the Waveshare board plugs into |
| 10 | PCB (2-layer, custom fab) | 1 | $5-15 (per board, at typical small-batch fab pricing) | See PCB design doc for outline/stackup |

**Estimated total per unit (excluding the Waveshare board and PCB fab
minimums): roughly $12-18 in passives/connectors/zeners** — still
cheaper than the two Fiber Drawer boards since there's no ADC chip or
precision divider resistors, though slightly more than the original
1k-only design given the added zener and pulldown per channel.

## Sourcing notes

- Resistors: any reputable passive supplier (Digi-Key, Mouser, LCSC), 5%
  tolerance is plenty for the series and pulldown resistors here (no
  precision needed — unlike the Fiber Drawer boards' divider resistors,
  which are 1%).
- Zener diodes: same 3.3V part family as used on the 2 Path Fiber
  Drawer's analog inputs (`BZX55C3V3` or equivalent) — worth ordering in
  one combined batch across boards if building multiple units at once.
- Screw terminals and buck regulator: same sourcing notes as the 8 Path
  Fiber Drawer's BOM (`fiber_drawer_8path_bom.md`) — any pin-compatible
  5.08mm pluggable terminal block and any fixed-5V buck module rated
  >=500mA work equally well.
