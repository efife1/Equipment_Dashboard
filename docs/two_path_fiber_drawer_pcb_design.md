# 2 Path Fiber Drawer — PCB Design Specification

Schematic-level design specification, not a routed PCB file — same
caveat as the other two device types: actual copper routing and DRC need
real PCB CAD software.

## Board concept

Same carrier-board concept as the other two device types: the Waveshare
ESP32-S3-ETH plugs into two rows of female 2.54mm header sockets, with
the divider circuits, screw terminals, and power section on the carrier
board around that footprint. Simpler than the 8 Path board (no ADC chip),
more analog-sensitive than the Talent Pack Decoder board (2 precision
divider circuits to route carefully).

## Assumed mounting footprint

Same assumption as the other two boards — standard Raspberry Pi Pico
header spacing. **Verify against the actual board before finalizing your
footprint** — see `docs/OPEN_ITEMS.md`.

## Suggested carrier board outline

- Recommend roughly **70mm x 60mm** — the smallest of the three boards,
  with only 2 channels' worth of divider circuitry and 3 screw terminal
  blocks to fit.
- 2-layer PCB is sufficient.
- Standard 1.6mm FR4, 1oz copper.

## Placement guidance

- **Center**: the 2x20 female socket pair, same orientation
  considerations as the other two boards (USB-C/Ethernet jack overhang).
- **One edge**: the 2 voltage divider circuits (R1/R2/Zener/cap per
  channel) + their 3-position screw terminal — keep these traces short
  and away from the power section's switching regulator to protect
  reading accuracy for the reference/delta fluctuation tracking.
- **Adjacent edge**: the 2 fault input circuits + their 3-position screw
  terminal.
- **Remaining edge**: the power section (DC input screw terminal,
  Schottky diode, buck regulator module footprint) — keep this
  reasonably separated from the divider circuits given switching
  regulators are a noise source, even though this design doesn't have
  especially tight noise requirements at only 2 channels.
- **Mounting holes**: 4x M3 holes near the corners for standoffs.

## Silkscreen / labeling

Label the 4 voltage/fault terminal positions clearly with path number and
signal type (e.g. "P1 Voltage", "P1 Fault", "P2 Voltage", "P2 Fault") —
fewer terminals than the other two boards, but still worth labeling
explicitly to avoid field-wiring mix-ups.

## What's still needed before you can fabricate

Same remaining steps as the other two boards: schematic capture using the
net list in `two_path_fiber_drawer_schematic.md`, footprint assignment,
placement, routing, DRC, and Gerber export/fab submission. This is a
reasonable middle-difficulty board between the other two — simpler than
the 8 Path version (no ADC chip, no I2C bus to route), but has real
analog signals to keep clean, unlike the Talent Pack Decoder board.
