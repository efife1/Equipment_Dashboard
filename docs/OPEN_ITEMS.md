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

- [ ] **Confirm the actual LED tap voltage level** on real Talent Pack
      Decoder hardware. The original design assumed 3.3V logic-compatible
      signals since no divider was ever built for this device type — if
      any tap point actually reads higher than ~3.6V, it will damage the
      ESP32 GPIO pin. Verify with a multimeter before wiring in, and add
      a divider (same technique as the Fiber Drawer boards) for any tap
      that reads too high. See `talent_pack_decoder_schematic.md`.

## 8 Path Fiber Drawer specific

- [ ] **Verify the ADS7828 command byte configuration** against the
      datasheet's command byte table before trusting readings on real
      hardware — the firmware's command bytes were cross-referenced
      against TI's datasheet, the Linux kernel's ads7828 driver, and a
      working community example, but haven't been confirmed against an
      actual ADS7828 chip yet. See `fiber_drawer_8path_schematic.md`.

See each device type's `..._schematic.md`, `..._bom.md`, and
`..._pcb_design.md` for full context on every item above.

