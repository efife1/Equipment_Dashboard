# Waveshare ESP32-S3-ETH — Full Pinout Reference

Board: ESP32-S3R8 (Xtensa dual-core, 8MB PSRAM, 16MB Flash), onboard W5500
Ethernet chip over SPI, USB-C, TF card slot, camera header, Pico-compatible
header. Source: Waveshare's official wiki and schematic.

## Already committed pins — do not reassign

These are wired to onboard hardware and used by this project's firmware.
Reassigning them will break Ethernet.

| Function              | GPIO |
|------------------------|------|
| Ethernet MISO           | 12   |
| Ethernet MOSI           | 11   |
| Ethernet SCLK           | 13   |
| Ethernet CS             | 14   |
| Ethernet RST            | 9    |
| Ethernet INT            | 10   |

## Currently used for the 12 monitored inputs (this project's firmware)

| GPIO | Notes                                        |
|------|-----------------------------------------------|
| 1    | Also camera VSYNC if you ever add a camera    |
| 2    | Also camera HREF                              |
| 4    | Also TF card CS                               |
| 5    | Also TF card MISO                             |
| 6    | Also TF card MOSI                             |
| 7    | Also TF card SCLK                             |
| 8    | Free / general purpose                        |
| 15   | Also camera D6                                |
| 16   | Free / general purpose                        |
| 17   | Free / general purpose                        |
| 18   | Also camera D7                                |
| 21   | Also the onboard WS2812 RGB LED signal pin    |

None of these conflict with each other or with Ethernet — the "also" notes
just mean: if you later add the onboard camera or TF card slot to this same
project, pick different signal pins for those, since they share these.

## Permanently unusable

| GPIO(s)   | Why                                                                 |
|-----------|----------------------------------------------------------------------|
| 33–37     | Reserved internally for PSRAM on this board's ESP32-S3R8 (confirmed in Waveshare's own FAQ) — do not use |
| 19, 20    | Native USB D-/D+ — used for the USB-C programming/serial port        |
| 0, 3, 45, 46 | Boot-strapping pins — can usually be used as inputs post-boot, but risky for anything that might be driven during power-up; this project avoids them |

## Full general-purpose GPIO list (Waveshare's own IO_Test demo)

These are the 25 pins Waveshare's own test firmware treats as safe,
general-purpose GPIO on this board:

```
0, 1, 2, 3, 15, 16, 17, 18, 21, 33, 34, 35, 36, 37,
38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48
```
(Note this list still includes 33–37 and the strapping pins — Waveshare's
demo exercises them for a basic LED-blink test, but per their own FAQ
33–37 aren't actually usable in practice since they're tied up internally.
Treat that list as "physically broken out," not "safe to build on.")

## Onboard peripheral pin maps (for reference, if you expand this project)

**TF/SD card (SPI):**
| Signal | GPIO |
|--------|------|
| CS     | 4    |
| MOSI   | 6    |
| MISO   | 5    |
| SCLK   | 7    |

**Camera header (DVP, e.g. OV5640):**
| Signal      | GPIO |
|-------------|------|
| VSYNC       | 1    |
| HREF        | 2    |
| XCLK        | 3    |
| PCLK        | 39   |
| SIOD (SDA)  | 48   |
| SIOC (SCL)  | 47   |
| D7          | 18   |
| D6          | 15   |
| D5          | 38   |
| D4          | 40   |
| D3          | 42   |
| D2          | 46   |
| D1          | 45   |
| D0          | 41   |

**Onboard WS2812 RGB LED:** GPIO21

## Power pins

| Pin  | Notes                                                           |
|------|-------------------------------------------------------------------|
| 3V3  | Regulated 3.3V output — logic level for all GPIO on this board    |
| 5V / VBUS | From USB-C, or from the PoE module if fitted (PoE variant only) |
| GND  | Multiple ground pins broken out on the headers                    |

All GPIO logic levels are **3.3V** — do not feed 5V signals directly into
any GPIO pin.

## Buttons / indicators (not user GPIO)

- **BOOT** button — hold BOOT, tap RESET, release BOOT to enter flashing mode
  (needed on this board since it uses native USB, which often doesn't
  auto-reset into bootloader mode)
- **RESET** button — hardware reset
- **ACT** and **LINK** LEDs — onboard indicators, not connected to any
  user-accessible GPIO

## Official references

- [Schematic (PDF)](https://files.waveshare.com/wiki/ESP32-S3-ETH/ESP32-S3-ETH-Schematic.pdf)
- [Waveshare wiki page](https://www.waveshare.com/wiki/ESP32-S3-ETH)
- [ESP32-S3 datasheet](https://files.waveshare.com/wiki/common/Esp32-s3_datasheet_en.pdf)
