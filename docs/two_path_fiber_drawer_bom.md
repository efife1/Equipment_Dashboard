# 2 Path Fiber Drawer — Bill of Materials

Quantities are per single expansion board (one 2 Path Fiber Drawer unit).

| # | Part | Qty | Approx unit cost | Notes |
|---|------|-----|------|-------|
| 1 | Waveshare ESP32-S3-ETH | 1 | $15-20 | The board this project already targets |
| 2 | Resistor, 56k ohm, 1%, 0805 or THT | 2 | $0.05 | Divider R1 (one per voltage channel) |
| 3 | Resistor, 10k ohm, 1%, 0805 or THT | 2 | $0.05 | Divider R2 (one per voltage channel) |
| 4 | Zener diode, 3.3V, e.g. BZX55C3V3 | 2 | $0.10 | Analog input overvoltage clamp |
| 5 | Ceramic capacitor, 0.1uF, 0805 or THT | 2 | $0.05 | Noise filter, one per voltage channel |
| 6 | Resistor, 1k ohm, 0805 or THT | 2 | $0.05 | Fault input series protection |
| 7 | Resistor, 10k ohm, 0805 or THT | 2 | $0.05 | Fault input pulldowns |
| 8 | Schottky diode, e.g. SS34 | 1 | $0.20 | Reverse-polarity protection on DC input |
| 9 | 5V buck regulator module, e.g. Pololu D24V5F5 (or equivalent fixed-5V, >=500mA module) | 1 | $5-8 | Steps down DC input to 5V for the Waveshare board's VBUS |
| 10 | 2-position 5.08mm pluggable screw terminal block | 1 | $0.50 | DC power input |
| 11 | 3-position 5.08mm pluggable screw terminal block | 2 | $0.75-1 each | One for voltage signals + GND, one for fault signals + GND |
| 12 | 2x20 pin female header socket, 2.54mm pitch, "short" Pico-compatible style | 2 | $1-2 each | Carrier board sockets the Waveshare board plugs into |
| 13 | PCB (2-layer, custom fab) | 1 | $5-15 (per board, at typical small-batch fab pricing) | See PCB design doc for outline/stackup |

**Estimated total per unit (excluding the Waveshare board and PCB fab
minimums): roughly $10-15 in passives/connectors** — no ADC chip needed
at this channel count, so this is meaningfully cheaper than the 8 Path
version's BOM despite the very similar circuit design.

## Sourcing notes

Same sourcing notes as the 8 Path Fiber Drawer's BOM
(`fiber_drawer_8path_bom.md`) apply here — any pin-compatible 5.08mm
pluggable terminal blocks and any fixed-5V buck module rated >=500mA
work equally well. Use 1% tolerance resistors for the divider (R1/R2) —
tolerance matters there since it directly affects reading accuracy;
5% is fine for the fault-input resistors, where exact values matter far
less.
