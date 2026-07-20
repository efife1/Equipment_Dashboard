# 2 Path Fiber Drawer — Expansion Board Schematic

Detailed net-by-net wiring for the carrier/expansion PCB that the
Waveshare ESP32-S3-ETH plugs into. Same carrier-board concept as the
other two device types — see `fiber_drawer_8path_schematic.md` for the
full mounting/power explanation. This board reads its 2 voltage channels
through the ESP32's own native ADC pins (no external ADC chip needed at
this channel count, unlike the 8 Path version).

## 1. Power section

Identical pattern to the other two boards:

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
- Nothing else on this board needs a separate power rail — the ESP32's
  native ADC pins read the dividers directly, no external chip involved.

## 2. Per-channel voltage divider + protection (x2, identical circuit)

One per fiber path, feeding directly into the ESP32's own ADC pin (no
external ADC chip — this is the key difference from the 8 Path version):

```
Screw terminal (fiber sensor output, 0-20V) [SIG]
        |
        R1 (56k ohm, 1%)
        |
        +------------------> ESP32 GPIO (native ADC pin, see table below)
        |
        +---[3.3V Zener, cathode up]---> GND   (protection clamp)
        |
        +---[0.1uF ceramic cap]--------> GND   (noise filter)
        |
        R2 (10k ohm, 1%)
        |
        GND
```

- Divider ratio: R2/(R1+R2) = 10/66 = 0.1515. At 20V input, the ESP32
  pin sees 3.03V — safely under the pin's 3.3V absolute maximum.
- Recovery factor (firmware multiplies the reading by this to recover the
  original 0-20V-range value): (R1+R2)/R2 = 6.6.
- Note these resistor values (56k/10k) differ from the 8 Path version's
  (75k/10k) — the 8 Path board's ADS7828 uses a 2.5V internal reference
  instead of the ESP32's 3.3V, so its divider targets a lower safe
  maximum. Don't mix these two boards' resistor values up.

## 3. Fault digital input (x2, identical circuit)

```
Screw terminal (fault signal, assumed 3.3V logic) [SIG]
        |
        R (1k ohm, series protection)
        |
        +------------------> ESP32 GPIO (see table below)
        |
        R (10k ohm, pulldown)
        |
        GND
```

Same assumption as the 8 Path version: fault source is 3.3V logic,
active-high. If your actual fault source differs, this needs adjusting —
see the note in `fiber_drawer_8path_schematic.md` Section 4.

## 4. ESP32 GPIO pin assignment

Matches the firmware in
`esp32_firmware/device_type_2_two_path_fiber_drawer/esp32_gpio_client.ino`:

| Path | Voltage (analog, native ADC) | Fault (digital) |
|---|---|---|
| 1 | GPIO1 | GPIO15 |
| 2 | GPIO2 | GPIO16 |

## 5. Screw terminal summary

- 1x 2-position: DC power in (DC_IN+, DC_IN-)
- 1x 3-position: 2x fiber voltage signals + 1 shared GND
- 1x 3-position: 2x fault signals + 1 shared GND

## Open items to verify before fabrication

Same as the other two device types — see `docs/OPEN_ITEMS.md` for the
full list. The VBUS/3V3/GND header pin verification item applies here
too; this board has no device-specific open items beyond that one, since
its divider design and channel count were already settled and confirmed
earlier in this project.
