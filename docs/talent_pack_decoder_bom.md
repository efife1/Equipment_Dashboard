# Talent Pack Decoder — Bill of Materials

Quantities are per single expansion board (one Talent Pack Decoder unit).
This is the simplest of the three boards — fully digital, no analog
components, no external ADC chip.

| # | Part | Qty | Approx unit cost | Notes |
|---|------|-----|------|-------|
| 1 | Waveshare ESP32-S3-ETH | 1 | $15-20 | The board this project already targets |
| 2 | Resistor, 1k ohm, 0805 or THT | 15 | $0.05 | Series protection on each LED tap input |
| 3 | Schottky diode, e.g. SS34 | 1 | $0.20 | Reverse-polarity protection on DC input |
| 4 | 5V buck regulator module, e.g. Pololu D24V5F5 (or equivalent fixed-5V, >=500mA module) | 1 | $5-8 | Steps down DC input to 5V for the Waveshare board's VBUS |
| 5 | 2-position 5.08mm pluggable screw terminal block | 1 | $0.50 | DC power input |
| 6 | 6-position 5.08mm pluggable screw terminal block | 3 | $1-1.50 each | One per decoder (5 signals + shared GND) |
| 7 | 2x20 pin female header socket, 2.54mm pitch, "short" Pico-compatible style | 2 | $1-2 each | Carrier board sockets the Waveshare board plugs into |
| 8 | PCB (2-layer, custom fab) | 1 | $5-15 (per board, at typical small-batch fab pricing) | See PCB design doc for outline/stackup |

**Estimated total per unit (excluding the Waveshare board and PCB fab
minimums): roughly $10-15 in passives/connectors, plus the board and fab
cost** — noticeably cheaper than the two Fiber Drawer boards since there's
no ADC chip, no precision resistors, and no Zener diodes needed here.

## Sourcing notes

- Resistors: any reputable passive supplier (Digi-Key, Mouser, LCSC), 5%
  tolerance is plenty for a simple series protection resistor (no
  precision needed here, unlike the Fiber Drawer boards' divider
  resistors).
- Screw terminals and buck regulator: same sourcing notes as the 8 Path
  Fiber Drawer's BOM (`fiber_drawer_8path_bom.md`) — any pin-compatible
  5.08mm pluggable terminal block and any fixed-5V buck module rated
  >=500mA work equally well.
