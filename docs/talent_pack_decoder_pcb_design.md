# Talent Pack Decoder — PCB Design Specification

Schematic-level design specification, not a routed PCB file — same caveat
as the other two device types' PCB docs: actual copper routing and DRC
need real PCB CAD software (KiCad or similar).

## Board concept

Same carrier-board concept as the other two device types: a board the
Waveshare ESP32-S3-ETH plugs into (two rows of female 2.54mm header
sockets), with the power section and screw terminals built into the
carrier board around that socket footprint. This is the simplest of the
three boards to lay out — no ADC chip, no precision analog components, no
noise-sensitive traces to route carefully.

## Assumed mounting footprint

Same assumption as the other two boards — standard Raspberry Pi Pico
header spacing (2x20 rows, 0.1"/2.54mm pitch, ~17mm between rows) based
on Waveshare's "Pico header compatible" claim. **Verify against the
actual board before finalizing your footprint** — see `docs/OPEN_ITEMS.md`.

## Suggested carrier board outline

- Recommend roughly **100mm x 75mm** — slightly larger than the original
  estimate since each of the 15 channels now carries three components
  (series resistor, zener, pulldown) instead of one, but still smaller
  than the 8 Path Fiber Drawer's board since there's no ADC chip or I2C
  bus to route.
- 2-layer PCB is more than sufficient — this design has no
  noise-sensitive signals at all, unlike the two Fiber Drawer boards.
- Standard 1.6mm FR4, 1oz copper.

## Placement guidance

- **Center**: the 2x20 female socket pair, oriented so the Waveshare
  board's USB-C port and RJ45 Ethernet jack overhang the board edge once
  plugged in.
- **Three clusters around the edges**, one per decoder: 5 clamp circuits
  (series resistor + zener + pulldown each) + a 6-position screw
  terminal block, positioned so the physical layout roughly mirrors the
  dashboard card's 3-decoder left-to-right arrangement — makes field
  wiring easier to reason about at a glance ("decoder 2's terminal block
  is the middle one").
- **One edge**: the power section (DC input screw terminal, Schottky
  diode, buck regulator module footprint).
- **Mounting holes**: 4x M3 holes near the corners for standoffs.

## Silkscreen / labeling

Label each screw terminal position with its decoder number and signal
name (e.g. "D1 On-Air", "D1 Prod", "D1 Err/Man-A", "D1 Err/Man-B", "D1
Call") — with 15 nearly-identical-looking signal wires going to one
board, clear labeling matters even more here than on the Fiber Drawer
boards.

## What's still needed before you can fabricate

Same five remaining steps as the 8 Path Fiber Drawer's PCB doc: schematic
capture in your CAD tool using the net list in
`talent_pack_decoder_schematic.md`, footprint assignment, placement,
routing, DRC, and Gerber export/fab submission. This board is the least
technically demanding of the three to actually route, given the total
absence of analog/noise-sensitive signals — a reasonable first PCB
project if you're new to layout work.
