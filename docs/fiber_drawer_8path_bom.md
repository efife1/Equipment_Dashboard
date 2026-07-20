# 8 Path Fiber Drawer — Bill of Materials

Quantities are per single expansion board (one 8 Path Fiber Drawer unit).
Prices are rough single-unit estimates (2026) — expect them to drop
noticeably if you're building more than one unit at a time and buying
resistors/caps in the quantities they're actually sold in (reels/cut-tape
of 50-100+, not singles).

| # | Part | Qty | Approx unit cost | Notes |
|---|------|-----|------|-------|
| 1 | Waveshare ESP32-S3-ETH | 1 | $15-20 | The board this project already targets |
| 2 | ADS7828IPWR (TI, TSSOP-16) | 1 | $4-6 | 8-channel 12-bit I2C ADC |
| 3 | Resistor, 75k ohm, 1%, 0805 or THT | 8 | $0.05 | Divider R1 (one per channel) |
| 4 | Resistor, 10k ohm, 1%, 0805 or THT | 8 | $0.05 | Divider R2 (one per channel) |
| 5 | Zener diode, 2.7V, e.g. BZX55C2V7 | 8 | $0.10 | Analog input overvoltage clamp |
| 6 | Ceramic capacitor, 0.1uF, 0805 or THT | 9 | $0.05 | 8x noise filter (one per analog channel) + 1x ADS7828 VREF bypass |
| 7 | Resistor, 4.7k ohm, 0805 or THT | 2 | $0.05 | I2C SDA/SCL pull-ups |
| 8 | Resistor, 1k ohm, 0805 or THT | 8 | $0.05 | Fault input series protection |
| 9 | Resistor, 10k ohm, 0805 or THT | 8 | $0.05 | Fault input pulldowns (same value as R2 above, separate line for BOM clarity) |
| 10 | Schottky diode, e.g. SS34 | 1 | $0.20 | Reverse-polarity protection on DC input |
| 11 | 5V buck regulator module, e.g. Pololu D24V5F5 (or equivalent fixed-5V, >=500mA module) | 1 | $5-8 | Steps down DC input to 5V for the Waveshare board's VBUS |
| 12 | 2-position 5.08mm pluggable screw terminal block | 1 | $0.50 | DC power input |
| 13 | 9-position 5.08mm pluggable screw terminal block | 2 | $2-3 each | One for 8 voltage signals + GND, one for 8 fault signals + GND |
| 14 | 2x20 pin female header socket, 2.54mm pitch, "short" Pico-compatible style | 2 | $1-2 each | Carrier board sockets the Waveshare board plugs into |
| 15 | PCB (2-layer, custom fab) | 1 | $5-15 (per board, at typical small-batch fab pricing) | See PCB design doc for outline/stackup |

**Estimated total per unit (excluding the Waveshare board and PCB fab
minimums, which are usually cheaper per-unit at higher quantities):
roughly $20-30 in passives/connectors/ADC, plus the board and fab cost.**

## Sourcing notes

- Resistors/caps: any reputable passive supplier (Digi-Key, Mouser, LCSC)
  in 0805 SMD if you want a compact board, or through-hole if
  hand-assembling without SMD tools — values matter, package doesn't.
- ADS7828: available from Digi-Key/Mouser under TI's part number. Confirm
  you're ordering the **IPW** (TSSOP-16) or an equivalent package you can
  actually solder — TI also sells other package options for this part
  under related part numbers.
- Screw terminals: any 5.08mm pitch "pluggable" (2-piece: PCB header +
  removable plug) terminal block works — Phoenix Contact is the common
  reference brand, but there are many pin-compatible equivalents at lower
  cost.
- Buck regulator: the Pololu module referenced is a real, well-documented
  part that's simple to drop in (3 pins: VIN, GND, VOUT, no external
  components needed) — but any fixed 5V buck module rated for your input
  voltage range and at least 500mA works equally well.
