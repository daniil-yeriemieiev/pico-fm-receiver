# Pico W FM Radio Receiver with Digital Tuning and RDS

A digital FM radio receiver prototype built on the Raspberry Pi Pico W using MicroPython. The system integrates an Si4703 FM tuner, an SH1106 OLED display, and an EC11 rotary encoder with an integrated pushbutton to provide manual tuning, hardware station seeking, non-blocking band auto-scanning, volume control, and live RDS decoding (station name and scrolling RadioText).

---

## Team Members and Contributions

- **Daniil Yeriemieiev** — System architecture, rotary encoder integration and interrupt handling, main application logic ([`boot.py`](/src/boot.py), [`main.py`](/src/main.py)), integration testing, and Sphinx/repository documentation.
- **Maxim Sudakov** — Custom MicroPython driver development for the Si4703 FM tuner ([`fm_tuner.py`](/lib/fm_tuner.py)), I2C communication debugging, and RDS decoding.
- **Gleb Dulesov** — Hardware assembly on the DFRobot Pico Gravity Board, OLED UI design and verification, component testing, and presentation materials.

---

## Features and Operating Instructions

### Controls (EC11 Rotary Encoder + Pushbutton)
- **Rotate Knob:** Manually tunes the frequency across the 88.0–108.0 MHz band in 100 kHz increments (wraps around at band edges).
- **Single Click (`SW`):** Triggers a non-blocking hardware seek upward to the next strong FM station.
- **Double Click (`SW`):** Starts or stops the **Auto-Scan** routine. During auto-scan, the tuner sweeps from 88.0 to 108.0 MHz, waits briefly at each detected station to capture its RDS name, and prints a formatted table to the serial terminal:
  ```text
  +------+-------------+----------+
  | RSSI |  Frequency  | RDS      |
  +------+-------------+----------+
  |   34 |    88.3 MHz | KISSFM   |
  +------+-------------+----------+
  ```
  When the sweep finishes (or is cancelled by a second double-click), the radio automatically returns to the previously tuned frequency.
- **Press, Hold, and Rotate (`SW`):** Enters volume adjustment mode (0 to 15). Setting the volume to `0` mutes the audio output and displays a crossed-out speaker icon. Releasing the button returns the encoder to frequency tuning.

### OLED Display Layout (9-Zone Grid)

The 128x64 screen is divided into 3 rows and 3 columns (Row.Column). Drawing is done by `RadioUI.render()` in [`main.py`](/src/main.py); coordinates are in pixels (`x`, `y` = top-left corner, 8x8 px per character).

```text
 x:  0          40                          127
y=0  +------+----------------------------------+
     | 1.1  |  1.2 - 1.3                       |   Row 1  (y 0-19)
     | RSSI |  RadioText marquee (11 chars)    |
y=20 +------+----------------------------------+
     | 2.1  |  2.2 - 2.3                       |   Row 2  (y 21-41)
     | 88.3 |  Station name (PS, 8 chars)      |
y=42 +------+----------------------------------+
     | 3.1  |  3.2 - 3.3                       |   Row 3  (y 43-63)
     | icon |  Volume bar + number             |
y=63 +------+----------------------------------+
```

| Grid Zone | Function | Position (px) | Description |
| :--- | :--- | :--- | :--- |
| **1.1** | Signal Strength | icon `x=2, y=4` (11x11); value `x=18, y=6` | 4-bar signal strength icon + numeric RSSI value in dBµV. |
| **1.2 – 1.3** | RDS RadioText | `x=40, y=6`, 11 characters | Decoded RDS RadioText (group 2A/2B) as a scrolling marquee (step 250 ms). It appears only after the whole text was received; empty until then. Shows `SCANNING..` during Auto-Scan. |
| **2.1** | Active Frequency | `x=0, y=28` | Current tuned frequency in MHz (e.g., ` 88.3`). |
| **2.2 – 2.3** | RDS Station Name | `x=50, y=28`, up to 9 characters | Decoded RDS PS name (max. 8 characters), `SEEKING..` during a seek, or `NO RDS`. |
| **3.1** | Audio Icon | `x=4, y=48` (14x12) | Speaker icon with sound waves, or crossed-out speaker icon when volume is `0`. |
| **3.2 – 3.3** | Volume Indicator | bar `x=50, y=50` (48x8); value `x=104, y=50` | Horizontal progress bar + numeric volume level (`0`–`15`). Underlined (`y=59`) while holding the button in volume mode. |

---

## Hardware Inventory and Wiring

### Components
- **Microcontroller:** Raspberry Pi Pico W (RP2040, 3.3 V logic)
- **Expansion Board:** DFRobot Pico Gravity Board
- **FM Tuner:** Si4703 FM Receiver Breakout Board (I2C, 3.3 V)
- **Display:** 1.3" SH1106 OLED Display (128x64, I2C, 3.3 V)
- **Input:** EC11 Rotary Encoder with integrated pushbutton (`SW`)
- **Audio Output:** Standard 3.5 mm headphones (also serves as the FM antenna)

### Pinout and Bus Allocation

The Si4703 and SH1106 are placed on separate I2C buses to prevent the Si4703 2-wire hardware reset sequence (which temporarily toggles SDA as a digital output) from interfering with the OLED display.

| Component | Module Pin | Pico W GPIO | Bus / Interface | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **SH1106 OLED** | SDA | `GP4` | `I2C0` | 400 kHz, addr `0x3C` |
| **SH1106 OLED** | SCL | `GP5` | `I2C0` | 400 kHz |
| **Si4703 Tuner** | SDIO (SDA) | `GP26` (or `GP2`) | `I2C1` | 400 kHz, addr `0x10` |
| **Si4703 Tuner** | SCLK (SCL) | `GP27` (or `GP3`) | `I2C1` | 400 kHz |
| **Si4703 Tuner** | RST | `GP16` | Digital Out | Held low in `boot.py` to prevent power-up pop |
| **EC11 Encoder** | CLK | `GP14` | Digital In (IRQ) | Internal pull-up enabled |
| **EC11 Encoder** | DT | `GP15` | Digital In (IRQ) | Internal pull-up enabled |
| **EC11 Encoder** | SW (Button) | `GP13` | Digital In | Active-low, internal pull-up enabled |

### Hardware Assumptions and Limitations
- **3.3 V Logic Only:** All peripherals operate at 3.3 V supplied by the Pico W / Gravity Board.
- **Audio Output:** Audio is routed directly from the Si4703 3.5 mm jack to headphones or a powered external amplifier. Speakers are never driven from Pico GPIO pins.
- **Single-Tuner Architecture:** The Si4703 has a single RF front-end; therefore, during Auto-Scan, live audio playback is paused while the tuner sweeps the band.
- **RDS Reception:** RDS decoding depends on antenna orientation (headphone cable) and local signal strength.

---

## System Architecture

### Block Diagram

![Schematic](/docs/images/schematic.jpg)

### Timing and Concurrency Plan

The application uses a **Superloop with Hardware Interrupts** (`LOOP_DELAY_MS = 20 ms`), avoiding `uasyncio` overhead since all local hardware operations are short and deterministic:

| Activity | Mechanism | Interval / Latency | Responsibility |
| :--- | :--- | :--- | :--- |
| **Encoder Rotation** | Hardware IRQ (`Pin.irq`) | Immediate (< 50 us) | Updates quadrature state machine and sets `encoder_rotated = True` flag. No I2C or memory allocation in IRQ context. |
| **Button Gestures** | Superloop Polling | Every 20 ms | Software debounce (25 ms), distinguishes single-click, double-click (350 ms window), and hold (400 ms threshold). |
| **Tuner & RDS Poll** | Superloop Polling | Every 20 ms | Calls `radio.poll()` to read RSSI, stereo flag, and decode incoming RDS groups (~11.4 groups/sec). |
| **Seek / Auto-Scan** | Non-blocking FSM | Every 20 ms | Calls `radio.seek_update()` without blocking the UI; waits up to 4700 ms per station for RDS PS during auto-scan. |
| **OLED Refresh** | Superloop Render | Every 20 ms | Updates the 9-zone framebuffer and shifts the RadioText marquee every 250 ms. |

---

## Software Modules and Class APIs

### 1. [`boot.py`](/src/boot.py)
Executes automatically on power-up before `main.py`.
- **`setup_environment()`**: Pulls `PIN_RADIO_RST` (`GP16`) low immediately to keep the Si4703 silent and prevent audio pops at boot, then enables and runs garbage collection (`gc.collect()`).

### 2. [`main.py`](/src/main.py)
Main application entry point containing hardware constants, UI rendering, button gesture logic, and the superloop.
- **`MultiFunctionButton(Button)`**: Extends `gpio_devices.Button` with `update()` to return `EVENT_NONE`, `EVENT_SINGLE_CLICK`, or `EVENT_DOUBLE_CLICK`, while exposing the `is_holding` boolean state.
- **`RadioUI`**: Manages the 9-zone SH1106 display layout. Key method: `render(radio, autoscan_active, holding_volume)`.

### 3. [`fm_tuner.py`](/lib/fm_tuner.py) (`FmTuner`)
Custom native MicroPython driver for the Si4703 FM receiver.
- **`start(volume=5, frequency=None)`**: Performs 2-wire I2C hardware reset, verifies chip ID, powers up oscillator, configures European band (87.5–108.0 MHz, 100 kHz, 50 us de-emphasis), and enables RDS.
- **`tune(mhz, timeout_ms=500)`**: Tunes to the specified frequency in MHz (blocking for < 100 ms).
- **`seek_start(up=True)` / `seek_update()`**: Non-blocking hardware seek across the band.
- **`poll()`**: Updates `rssi`, `stereo`, and decodes RDS with block error rate (BLER) validation: Programme Service name (`ps`, groups 0A/0B) and RadioText (`rt`, groups 2A/2B). `rt` is updated only when the complete text was received and is cleared when the station sends new text (A/B flag toggles) or when the tuner is retuned.
- **`set_volume(level)` / `mute(on=True)` / `power_off()`**: Audio and power management.

### 4. [`rotary.py`](/lib/rotary.py) & [`rotary_irq_rp2.py`](/lib/rotary_irq_rp2.py) (`Rotary`, `RotaryIRQ`)
Quadrature state machine and RP2040 hardware interrupt driver for the EC11 encoder.
- **`RotaryIRQ(...)`**: Configures `CLK` and `DT` pins with `Pin.IRQ_RISING | Pin.IRQ_FALLING`.
- **`value()` / `set(...)` / `reset()`**: Reads or dynamically reconfigures the encoder counter, bounds (`min_val`, `max_val`), and mode (`RANGE_WRAP`, `RANGE_BOUNDED`, `RANGE_UNBOUNDED`).
- **`add_listener(l)` / `remove_listener(l)` / `close()`**: Manages IRQ callbacks and disables interrupts cleanly on exit.

### 5. [`gpio_devices.py`](/lib/gpio_devices.py) (`Button`)
Reusable GPIO abstraction from the VUT FEKT MicroPython course.
- **`is_pressed()` / `is_released()` / `was_pressed(debounce_ms=20)`**: Active-low button reading and software debouncing.

### 6. [`sh1106.py`](/lib/sh1106.py) (`SH1106_I2C`)
I2C OLED driver inheriting from `framebuf.FrameBuffer`.
- **`show()` / `fill()` / `text()` / `rect()` / `fill_rect()` / `poweroff()`**: Framebuffer drawing and display refresh over I2C.

### 7. Hardware tests ([`tests/`](/tests))
Run on the Pico W with MicroPico ("Run current file"); they stay on the PC and are not uploaded to the device.
- [`test_fm.py`](/tests/test_fm.py): chip ID, band edges, tune/seek timing, 20 s RDS listening, volume and mute.
- [`test_encoder.py`](/tests/test_encoder.py): rotary encoder and button.
- [`test_enc_with_fm.py`](/tests/test_enc_with_fm.py): early encoder + tuner integration test.
- [`test_enc_tune.py`](/tests/test_enc_tune.py): encoder tunes the radio while `poll()` runs continuously.
- [`test_rds_diag.py`](/tests/test_rds_diag.py): RSSI and RDS group statistics on a fixed station.

---

## Third-Party Code Attribution and Licenses

- **Si4703 FM Radio Tuner Driver ([`fm_tuner.py`](/lib/fm_tuner.py))**
  - **Author:** Custom project team implementation.
  - **References:** Register map and start-up sequence follow the Silicon Labs AN230 Programming Guide. The 2-wire reset procedure and architectural concepts were inspired by the SparkFun Si4703 library (MIT) and Thomas Shaddack's [si4703-RDS](https://github.com/tshaddack/si4703-RDS) repository (MIT).
- **Rotary Encoder Driver ([`rotary.py`](/lib/rotary.py), [`rotary_irq_rp2.py`](/lib/rotary_irq_rp2.py))**
  - **Author:** Mike Teachman, Eric Moyer.
  - **Repository:** [micropython-rotary](https://github.com/miketeachman/micropython-rotary)
  - **License:** MIT License.
  - **Modifications:** Added Sphinx reStructuredText docstrings and updated `reset()` to reset to `min_val` instead of hardcoded `0`.
- **SH1106 OLED Driver ([`sh1106.py`](/lib/sh1106.py)) & GPIO Devices ([`gpio_devices.py`](/lib/gpio_devices.py))**
  - **Author:** Tomas Fryza (VUT FEKT MicroPython Course), Shujen Chen et al.
  - **Source:** [VUT FEKT MicroPython Course Labs](https://gitlab.fekt.vut.cz/fryza/micropython-course-labs)
  - **License:** MIT License.

---

## References

### Hardware Datasheets

| Component | Document Name | Direct Link |
| :--- | :--- | :--- |
| Raspberry Pi Pico W | Pico W Datasheet | [Pico W Datasheet PDF](https://datasheets.raspberrypi.com/picow/pico-w-datasheet.pdf) |
| RP2040 (MCU) | RP2040 Datasheet | [RP2040 Datasheet PDF](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf) |
| Si4703 / HW-322 | Si4702/03-C19 Datasheet | [Si4703 datasheet PDF](https://download.mikroe.com/documents/datasheets/Si4703_datasheet.pdf) |
| Si4703 / HW-322 | AN230: Si4700/01/02/03 Programming Guide | [AN230 PDF](https://cdn.sparkfun.com/datasheets/BreakoutBoards/Si4703_ProgrammingGuide.pdf) |
| EC11 Rotary Encoder | ALPS EC11 Series Datasheet | [ALPS EC11 PDF](https://www.tme.com/Document/947fff760d3e8051ff1d91b3169c392a/ALPS-EC11.pdf) |
| SH1106 OLED Display | SH1106 Datasheet | [SH1106 PDF](https://www.elecrow.com/download/SH1106%20datasheet.pdf) |

### Course Materials

- **Sphinx Documentation Guide:** A practical guide written by our instructor in the lab repository for setting up, structuring, and generating the project documentation: [`HOWTO_Sphinx.md`](https://gitlab.fekt.vut.cz/fryza/micropython-course-labs/-/blob/main/docs/HOWTO_Sphinx.md).
- **Source files of the course drivers:** [`sh1106.py`](https://gitlab.fekt.vut.cz/fryza/micropython-course-labs/-/blob/main/examples/_modules/sh1106.py), [`gpio_devices.py`](https://gitlab.fekt.vut.cz/fryza/micropython-course-labs/-/blob/main/examples/_modules/gpio_devices.py).
- **Source files of the rotary encoder driver:** [`rotary_irq_rp2.py`](https://github.com/miketeachman/micropython-rotary/blob/master/rotary_irq_rp2.py), [`rotary.py`](https://github.com/miketeachman/micropython-rotary/blob/master/rotary.py).

---

## TO-DO

- **Project Poster (A3):** Coming soon
- **Demonstration Video (1–2 min):** Coming soon
