# Pico W FM receiver: Si4703 tuner module

Branch `feat/fm-tuner`: Si4703 FM tuner driver and its hardware test.

## Files
- `lib/fm_tuner.py`: class `FmTuner` (tune, seek, RSSI, stereo, RDS station name, volume, mute).
- `tests/test_fm.py`: hardware test with a PASS/FAIL table.

## Wiring (HW-322 / Si4703)
| Si4703 | Pico W |
|---|---|
| SDIO / SCLK | GP2 / GP3 (I2C1, 400 kHz, address 0x10) |
| RST | GP16 |
| SEN | 3V3 |
| 3V3 / GND | 3V3(OUT) / GND |

Audio and antenna: wired headphones in the module's 3,5 mm jack.

## Usage
```python
radio = FmTuner(1, 2, 3, 16)
radio.start(volume=5)          # raises OSError if chip is missing
radio.tune(98.4)               # blocking, under 100 ms
radio.seek_start()             # non-blocking seek, then call
radio.seek_update()            # every 20-50 ms until it returns True
radio.poll()                   # every 30 ms: RSSI, stereo, RDS
print(radio.frequency, radio.rssi, radio.ps)
```
No `asyncio`*

## Test
1. `lib/fm_tuner.py` -> `/lib` on the Pico.
2. Run `tests/test_fm.py`


## Third-party code
Register map and start-up sequence follow Silicon Labs AN230. The 2-wire reset procedure follows the SparkFun Si4703 library (MIT).
1. FM receiver - *88-108 MHz*
2. Auto-scan function - internal RPI button
3. OLED Display - show RDS, Freq., RSSI
4. Button used for auto-scan (multiple functions for diff inputs i.e. 1/2/3 clicks)
5. Potenciometr - for choosing the frequency 
6. Modules: FM receiver, display, encoder(potenciometr), antenna
7. RDS display - station/chanel name displayed on OLED screen

TO-DO
1. Block schemata
2. Readme
3. Work distribution
4. Setting deadline

## Third-Party Code

This project utilizes the following open-source drivers and libraries. We are grateful to the original authors for their work.

- **SH1106 OLED Display Driver**
  - **Authors:** 
    - Shujen Chen et al. (Raspberry Pi Pico Interfacing and Programming with MicroPython)
    - MicroPython SH1106 OLED driver contributors
    - Tomas Fryza
  - **Files:** [`sh1106.py`](https://gitlab.fekt.vut.cz/fryza/micropython-course-labs/-/blob/main/examples/_modules/sh1106.py)
  - **Repository:** [micropython-course-labs](https://gitlab.fekt.vut.cz/fryza/micropython-course-labs)
  - **License:** MIT License

- **GPIO Devices (LED, Button)**
  - **Author:** Tomas Fryza
  - **Files:** [`gpio_devices.py`](https://gitlab.fekt.vut.cz/fryza/micropython-course-labs/-/blob/main/examples/_modules/gpio_devices.py)
  - **Repository:** [micropython-course-labs](https://gitlab.fekt.vut.cz/fryza/micropython-course-labs)
  - **License:** MIT License

- **EC11 Rotary Encoder Driver**
  - **Author:** Mike Teachman (`miketeachman`)
  - **Files:** [`rotary_irq_rp2.py`](https://github.com/miketeachman/micropython-rotary/blob/master/rotary_irq_rp2.py), [`rotary.py`](https://github.com/miketeachman/micropython-rotary/blob/master/rotary.py)
  - **Repository:** [micropython-rotary](https://github.com/miketeachman/micropython-rotary)
  - **License:** MIT License

- **Si4703 FM Radio Tuner Driver**
  - **Author:** Thomas Shaddack (`tshaddack`)
  - **Files:** [`si4703rds.py`](https://github.com/tshaddack/si4703-RDS/blob/master/si4703rds.py), and internal dependencies ([`_libsi4703.py`](https://github.com/tshaddack/si4703-RDS/blob/master/_libsi4703.py), [`_rds_tmc_events.py`](https://github.com/tshaddack/si4703-RDS/blob/master/_rds_tmc_events.py), [`_rdslists.py`](https://github.com/tshaddack/si4703-RDS/blob/master/_rdslists.py))
  - **Repository:** [si4703-RDS](https://github.com/tshaddack/si4703-RDS)
  - **License:** MIT License
  - **Modifications:** The original `_libsi4703.py` was written for Raspberry Pi (Linux). We removed `smbus` and `RPi.GPIO` dependencies and refactored the I2C communication to use MicroPython's native `machine.I2C` and `machine.Pin` classes for compatibility with the Pico W.
