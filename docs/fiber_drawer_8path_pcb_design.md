# 8 Path Fiber Drawer — PCB Design Specification

This is a **schematic-level design specification**, not a routed PCB file.
It gives you everything needed to lay this out in KiCad (or any PCB CAD
tool) — component placement logic, board outline, mounting approach, and
connector positions — but the actual copper routing, via placement, and
DRC pass need to be done in real PCB CAD software. I don't have access to
run that kind of tool directly, so treat this as the brief you'd hand to
yourself (or a PCB designer) to lay it out.

## Board concept

A carrier/expansion board the Waveshare ESP32-S3-ETH plugs **into** —
mirroring how a Raspberry Pi Pico plugs into a Pico HAT. Two rows of
female 2.54mm header sockets on the carrier board receive the Waveshare
board's pin headers from above; all the divider circuits, the ADS7828,
screw terminals, and power section live on the carrier board around that
socket footprint.

## Assumed mounting footprint

Waveshare markets this board as "Pico header compatible." Assuming that
means the standard Raspberry Pi Pico form factor:
- Two 2x20 header rows (0.1"/2.54mm pitch within each row)
- **~17mm center-to-center spacing between the two rows** (standard Pico
  spec: 21mm board width, headers inset ~2mm from each edge)
- Board outline roughly 21mm x 51mm for the Waveshare board itself

**Verify this against the actual board or its official dimensional
drawing before finalizing your footprint** — this is inferred from the
"Pico compatible" marketing claim, not independently confirmed
pin-for-pin against a Waveshare-published drawing.

## Suggested carrier board outline

- Recommend a board roughly **100mm x 80mm** — enough room for the socket
  footprint in the center, the ADS7828 and its passives nearby, 8 divider
  circuits, the power section, and 3 screw terminal blocks around the
  edges, without cramming.
- 2-layer PCB is sufficient for this design's complexity (nothing here
  needs a 4-layer board — no high-speed signals, no dense BGA routing).
- Standard 1.6mm FR4, 1oz copper is fine.

## Placement guidance

- **Center**: the 2x20 female socket pair, oriented so the Waveshare
  board's USB-C port and RJ45 Ethernet jack overhang the board edge
  (accessible without obstruction) once plugged in — check the Waveshare
  board's actual header-to-edge dimensions to get this overhang right.
- **Near the sockets**: the ADS7828 (TSSOP-16, needs to be reasonably
  close to the ESP32's I2C pins with short traces) and its bypass/pullup
  passives.
- **One edge**: the 8-position voltage screw terminal + associated 8x
  divider circuits (R1/R2/Zener/cap per channel) — keep these physically
  grouped in a repeating row so the board reads clearly (channel 1's
  circuit next to channel 2's, etc.), and keep divider traces short and
  away from noisy digital lines (the I2C bus, Ethernet SPI) to protect
  signal integrity for the fluctuation-tracking feature.
- **Adjacent edge**: the 8-position fault screw terminal + associated
  8x fault input circuits (R series + pulldown per channel).
- **Remaining edge**: the power section — DC input screw terminal,
  Schottky diode, buck regulator module footprint.
- **Mounting holes**: 4x M3 holes near the corners, sized for standard M3
  standoffs, so the assembled board (with the Waveshare board plugged in)
  can be mounted inside an enclosure.

## Silkscreen / labeling

Worth investing in clear silkscreen labels given this board will be field
wired: label each screw terminal position with its path number (1-8) and
signal type (V for voltage, F for fault), and mark polarity/orientation
on the DC power input clearly — a mislabeled terminal block is a common
and entirely avoidable source of field-wiring mistakes.

## What's still needed before you can fabricate

1. **Schematic capture** in your PCB CAD tool, using the net list in
   `fiber_drawer_8path_schematic.md`.
2. **Footprint assignment** for every part (the ADS7828's TSSOP-16
   footprint, the screw terminals' exact footprint matching whichever
   specific part you buy, the female header sockets, etc.) — footprint
   libraries are tool-specific (KiCad has a large built-in library that
   covers most of this BOM already).
3. **Placement** following the guidance above, adjusted for whatever
   footprints you actually land on.
4. **Routing** — the actual copper traces. This design has no exotic
   requirements (no controlled impedance, no high-speed differential
   pairs), so it's a reasonably approachable routing job even for a first
   PCB project, but it still needs to be done in the CAD tool.
5. **DRC (design rule check)** against your fab's capabilities (minimum
   trace width/spacing, drill sizes) before ordering.
6. **Gerber export** and submission to a fab (JLCPCB, PCBWay, OSH Park,
   etc. are all common low-cost options for small runs).

If you have KiCad already, I can help translate the net list into KiCad's
schematic format more directly, or answer specific questions as you build
it out — just not produce the finished, routed board file directly.
