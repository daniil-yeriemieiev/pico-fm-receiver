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
