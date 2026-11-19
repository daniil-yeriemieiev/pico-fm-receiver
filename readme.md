# Pico W FM Radio Receiver with Digital Tuning and RDS

A digital FM radio receiver prototype built on the Raspberry Pi Pico W using MicroPython. The system integrates an Si4703 FM tuner, an SH1106 OLED display, and an EC11 rotary encoder with an integrated pushbutton to provide manual tuning, hardware station seeking, non-blocking band auto-scanning, volume control, and live RDS decoding.

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

The 128x64 screen is divided into 3 rows and 3 columns (Row.Column):

| Grid Zone | Function | Description |
| :--- | :--- | :--- |
| **1.1** | Signal Strength | 4-bar signal strength icon + numeric RSSI value. |
| **1.2 – 1.3** | Auto-Scan Status | Displays `SCAN: ON` during band sweep or `SCAN:OFF` in normal mode. |
| **2.1** | Active Frequency | Current tuned frequency in MHz (e.g., `88.3`). |
| **2.2 – 2.3** | RDS Station Name | Displays decoded RDS PS name, `SEEKING..`, or `NO RDS`. Automatically scrolls as a marquee if text exceeds 9 characters. |
| **3.1** | Audio Icon | Speaker icon with sound waves, or crossed-out speaker icon when volume is `0`. |
| **3.2 – 3.3** | Volume Indicator | Horizontal progress bar + numeric volume level (`0`–`15`). Underlined while holding the button in volume mode. |

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
| **Seek / Auto-Scan** | Non-blocking FSM | Every 20 ms | Calls `radio.seek_update()` without blocking the UI; waits up to 1800 ms per station for RDS PS during auto-scan. |
| **OLED Refresh** | Superloop Render | Every 20 ms | Updates the 9-zone framebuffer and shifts the RDS marquee every 250 ms. |

---

## Software Modules and Class APIs

### 1. `boot.py`
Executes automatically on power-up before `main.py`.
- **`setup_environment()`**: Pulls `PIN_RADIO_RST` (`GP16`) low immediately to keep the Si4703 silent and prevent audio pops at boot, then enables and runs garbage collection (`gc.collect()`).

### 2. `main.py`
Main application entry point containing hardware constants, UI rendering, button gesture logic, and the superloop.
- **`MultiFunctionButton(Button)`**: Extends `gpio_devices.Button` with `update()` to return `EVENT_NONE`, `EVENT_SINGLE_CLICK`, or `EVENT_DOUBLE_CLICK`, while exposing the `is_holding` boolean state.
- **`RadioUI`**: Manages the 9-zone SH1106 display layout. Key method: `render(radio, autoscan_active, holding_volume)`.

### 3. `fm_tuner.py` (`FmTuner`)
Custom native MicroPython driver for the Si4703 FM receiver.
- **`start(volume=5, frequency=None)`**: Performs 2-wire I2C hardware reset, verifies chip ID, powers up oscillator, configures European band (87.5–108.0 MHz, 100 kHz, 50 us de-emphasis), and enables RDS.
- **`tune(mhz, timeout_ms=500)`**: Tunes to the specified frequency in MHz (blocking for < 100 ms).
- **`seek_start(up=True)` / `seek_update()`**: Non-blocking hardware seek across the band.
- **`poll()`**: Updates `rssi`, `stereo`, and decodes RDS Programme Service (`ps`) with block error rate (BLER) validation.
- **`set_volume(level)` / `mute(on=True)` / `power_off()`**: Audio and power management.

### 4. `rotary.py` & `rotary_irq_rp2.py` (`Rotary`, `RotaryIRQ`)
Quadrature state machine and RP2040 hardware interrupt driver for the EC11 encoder.
- **`RotaryIRQ(...)`**: Configures `CLK` and `DT` pins with `Pin.IRQ_RISING | Pin.IRQ_FALLING`.
- **`value()` / `set(...)` / `reset()`**: Reads or dynamically reconfigures the encoder counter, bounds (`min_val`, `max_val`), and mode (`RANGE_WRAP`, `RANGE_BOUNDED`, `RANGE_UNBOUNDED`).
- **`add_listener(l)` / `remove_listener(l)` / `close()`**: Manages IRQ callbacks and disables interrupts cleanly on exit.

### 5. `gpio_devices.py` (`Button`)
Reusable GPIO abstraction from the VUT FEKT MicroPython course.
- **`is_pressed()` / `is_released()` / `was_pressed(debounce_ms=20)`**: Active-low button reading and software debouncing.

### 6. `sh1106.py` (`SH1106_I2C`)
I2C OLED driver inheriting from `framebuf.FrameBuffer`.
- **`show()` / `fill()` / `text()` / `rect()` / `fill_rect()` / `poweroff()`**: Framebuffer drawing and display refresh over I2C.

---

## Setup and Running

### Uploading to Raspberry Pi Pico W
1. Flash the latest **MicroPython** firmware onto the Raspberry Pi Pico W.
2. Open the project in **VS Code** with the **MicroPico** extension (or **Thonny**).
3. Upload the driver files (`fm_tuner.py`, `gpio_devices.py`, `rotary.py`, `rotary_irq_rp2.py`, `sh1106.py`) and application scripts (`boot.py`, `main.py`) to the root directory of the Pico W.
4. Verify the pin constants at the top of `main.py` match your wiring on the Gravity Board.
5. Reset the board or run `main.py` via the REPL.

### Building Sphinx Documentation Locally
1. Install Sphinx and the Read the Docs theme:
   ```bash
   pip install sphinx sphinx-rtd-theme
   ```
2. Build the HTML documentation from the `docs/` directory:
   ```bash
   cd docs
   sphinx-build -b html . _build/html
   ```
3. Open `docs/_build/html/index.html` in a web browser.

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

## Presentation Materials

- **Project Poster (A3):** Coming soon
- **Demonstration Video (1–2 min):** Coming soon
