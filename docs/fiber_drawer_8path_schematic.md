# 8 Path Fiber Drawer — Expansion Board Schematic

Detailed net-by-net wiring for the carrier/expansion PCB that the Waveshare
ESP32-S3-ETH plugs into. See `fiber_drawer_8path_system_architecture` diagram
in the main conversation for the block-level overview this expands on.

## 1. Power section

```
DC power screw terminal (7-24V)
  DC_IN+ ---[SS34 Schottky, cathode toward regulator]---> VIN (buck regulator)
  DC_IN- ----------------------------------------------> GND (common ground)

5V buck regulator (e.g. Pololu D24V5F5, fixed 5V/500mA, 3-pin VIN/GND/VOUT)
  VOUT (5V) ---> Waveshare header pin VBUS
  GND        ---> Waveshare header pin GND (any GND pin on the header)
```

- The Schottky diode protects against reverse-polarity DC input; it's not
  optional — reversed polarity without it can damage the regulator and
  everything downstream.
- VBUS feed replaces/supplements the USB-C port's normal power path. Do
  not power via both USB-C and this VBUS feed simultaneously unless you've
  confirmed the Waveshare board's power-path circuitry allows it (check
  Waveshare's docs/schematic before doing this — assume "one power source
  at a time" unless proven otherwise).
- Everything else in this design (ADS7828, I2C pull-ups) draws its 3.3V
  from the Waveshare board's own onboard 3.3V regulator via its header's
  3V3 pin — no separate 3.3V regulator needed on this expansion board.

## 2. I2C ADC section (ADS7828)

```
ADS7828 (TSSOP-16)
  VCC   ---> Waveshare header 3V3 pin
  GND   ---> common ground
  A0    ---> GND  (address pin, low)
  A1    ---> GND  (address pin, low)   => I2C address 0x48
  SDA   ---> Waveshare header GPIO1  (also has 4.7k ohm pull-up to 3V3)
  SCL   ---> Waveshare header GPIO2  (also has 4.7k ohm pull-up to 3V3)
  VREF  ---> floating, with a 0.1uF ceramic bypass cap to GND
             (internal 2.5V reference is enabled in firmware via the
             command byte's power-down bits — see the ADS7828 datasheet's
             command byte table before writing the I2C driver code)
  CH0-CH7 ---> one per fiber path, see divider circuit below
```

## 3. Per-channel voltage divider + protection (x8, identical circuit)

One of these per fiber path (paths 1-8), each feeding one ADS7828 channel
(CH0 through CH7 respectively):

```
Screw terminal (fiber sensor output, 0-20V) [SIG]
        |
        R1 (75k ohm, 1%)
        |
        +------------------> ADS7828 CHn
        |
        +---[2.7V Zener, cathode up]---> GND   (protection clamp)
        |
        +---[0.1uF ceramic cap]--------> GND   (noise filter)
        |
        R2 (10k ohm, 1%)
        |
        GND
```

- Divider ratio: R2/(R1+R2) = 10/85 = 0.1176. At 20V input, ADS7828 sees
  2.353V — safely under the 2.5V internal reference full-scale, with
  margin.
- Recovery factor (firmware multiplies the ADS7828 reading by this to get
  back the original 0-20V-range value): (R1+R2)/R2 = 8.5.
- Per this project's convention, mW = recovered voltage directly (1:1).

## 4. Per-channel fault digital input (x8, identical circuit)

One per fiber path, direct to its own ESP32 GPIO (no ADC involved):

```
Screw terminal (fault signal, assumed 3.3V logic) [SIG]
        |
        R (1k ohm, series protection)
        |
        +------------------> ESP32 GPIO (see pin table below)
        |
        R (10k ohm, pulldown)
        |
        GND
```

- Assumes the fault source is already 3.3V logic and drives HIGH when
  active (pulldown keeps the input at a defined LOW when nothing's
  driving it). If your actual fault signal source is 5V logic or uses a
  different active state, this needs the same divider/protection
  treatment as the analog channels, or an inverted pull configuration —
  confirm against your actual fault signal source's datasheet before
  wiring it in.

## 5. ESP32 GPIO pin assignment

| Function | Pin |
|---|---|
| I2C SDA (to ADS7828) | GPIO1 |
| I2C SCL (to ADS7828) | GPIO2 |
| Fault 1 | GPIO15 |
| Fault 2 | GPIO16 |
| Fault 3 | GPIO17 |
| Fault 4 | GPIO18 |
| Fault 5 | GPIO21 |
| Fault 6 | GPIO38 |
| Fault 7 | GPIO39 |
| Fault 8 | GPIO40 |

6 safe GPIO pins remain unused (41, 42, 43, 44, 47, 48) — spare headroom
for a future revision.

## 6. Screw terminal summary

- 1x 2-position: DC power in (DC_IN+, DC_IN-)
- 1x 9-position: 8x fiber voltage signals + 1 shared GND
- 1x 9-position: 8x fault signals + 1 shared GND

## Open items to verify before fabrication

- **VBUS/3V3/GND exact physical pin positions** on the Waveshare board's
  Pico-compatible header — this document assumes standard Raspberry Pi
  Pico pin assignments (VBUS pin 40, 3V3 pin 36, multiple GND pins) since
  Waveshare markets this board as "Pico header compatible," but that
  hasn't been independently confirmed pin-for-pin against Waveshare's own
  dimensional/pinout drawing for this specific board. Check the board's
  silkscreen or official pinout diagram before finalizing your PCB
  footprint.
- **ADS7828 command byte configuration** for single-ended mode, internal
  reference, and always-on power mode needs to be written against the
  datasheet's command byte table (SD, C2, C1, C0, PD1, PD0 bits) — not
  included here since getting this wrong is a firmware bug, not a
  schematic error, and belongs in that implementation step.
