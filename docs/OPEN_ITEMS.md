# Open items — revisit before fabricating any of the three expansion boards

Flagged during the hardware design passes (schematic/BOM/PCB docs for all
three device types) and set aside to keep moving on software. Come back
to these before ordering parts or submitting any board for fabrication.

## Applies to all three boards

- [ ] **Confirm VBUS/3V3/GND pin positions** on the Waveshare ESP32-S3-ETH's
      Pico-compatible header. Every board's power section assumes standard
      Raspberry Pi Pico pin assignments (VBUS pin 40, 3V3 pin 36) based on
      Waveshare's "Pico header compatible" marketing claim, but this hasn't
      been independently verified against Waveshare's own dimensional
      drawing or the physical board. Check with a multimeter or their
      official pinout diagram before finalizing any of the three
      footprints.

- [ ] **Actual PCB routing** for all three boards — schematics, BOMs, and
      placement/outline guidance are complete for each, but real trace
      routing and DRC need to happen in PCB CAD software (KiCad or
      similar). See each device type's `..._pcb_design.md` for its brief.

## Talent Pack Decoder specific

- [x] **LED tap voltage protection — RESOLVED (design decision).** Actual
      tap voltage was never confirmed on real hardware, so rather than
      wait on a measurement, all 15 channels now use a clamp instead of a
      divider: 2.2kΩ series resistor (tap → GPIO) + 3.3V shunt zener
      (GPIO node → GND) + 100kΩ pull-down (GPIO node → GND). Design
      ceiling is a conservative 24V worst case (~9-10mA through the
      series resistor at clamp, well within a small SOT-23 zener's
      rating). Unlike a divider, this doesn't require knowing the real
      voltage in advance — since these are digital on/off reads rather
      than analog values needing resolution, the clamp passes real
      signals through close to unattenuated and only engages if the
      voltage approaches the 24V ceiling. No further hardware
      verification needed before fabrication. Update
      `talent_pack_decoder_schematic.md` and `talent_pack_decoder_bom.md`
      with the per-channel resistor/zener/pull-down (15x each).

## 8 Path Fiber Drawer specific

- [ ] **Verify the ADS7828 command byte configuration** against the
      datasheet's command byte table before trusting readings on real
      hardware — the firmware's command bytes were cross-referenced
      against TI's datasheet, the Linux kernel's ads7828 driver, and a
      working community example, but haven't been confirmed against an
      actual ADS7828 chip yet. See `fiber_drawer_8path_schematic.md`.

See each device type's `..._schematic.md`, `..._bom.md`, and
`..._pcb_design.md` for full context on every item above.

