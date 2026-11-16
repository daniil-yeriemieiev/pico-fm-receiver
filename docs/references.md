# Documentation & References

This document contains reference materials, hardware datasheets, and software guides used in the Pico W FM Radio Receiver project.

## Hardware Datasheets

| Component | Document Name | Direct Link |
|---|---|---|
| Raspberry Pi Pico W | Pico W Datasheet | [Pico W Datasheet PDF](https://datasheets.raspberrypi.com/picow/pico-w-datasheet.pdf) |
| RP2040 (MCU) | RP2040 Datasheet | [RP2040 Datasheet PDF](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf) |
| Si4703 / HW-322 | Si4702/03-C19 Datasheet | [Si4703 datasheet PDF](https://download.mikroe.com/documents/datasheets/Si4703_datasheet.pdf) |
| Si4703 / HW-322 | AN230: Si4700/01/02/03 Programming Guide | [AN230 PDF](https://cdn.sparkfun.com/datasheets/BreakoutBoards/Si4703_ProgrammingGuide.pdf) |
| EC11 Rotary Encoder | ALPS EC11 Series Datasheet | [ALPS EC11 PDF](https://www.tme.com/Document/947fff760d3e8051ff1d91b3169c392a/ALPS-EC11.pdf) |
| SH1106 OLED Display | SH1106 Datasheet | [SH1106 PDF](https://www.elecrow.com/download/SH1106%20datasheet.pdf) |

---

## Third-Party Software & Course Materials

- **SH1106 OLED Display Driver:** Pre-written driver library provided in the university course repository.
  - Authors:
    - Shujen Chen et al.
    - MicroPython SH1106 contributors
    - Tomas Fryza
  - Source Code: [`sh1106.py`](https://gitlab.fekt.vut.cz/fryza/micropython-course-labs/-/blob/main/examples/_modules/sh1106.py)
  - Repository: [micropython-course-labs](https://gitlab.fekt.vut.cz/fryza/micropython-course-labs) | License: MIT

- **GPIO Devices Driver:** Pre-written class library for basic GPIO components (LEDs, Buttons) from the university course.
  - Author: Tomas Fryza
  - Source Code: [`gpio_devices.py`](https://gitlab.fekt.vut.cz/fryza/micropython-course-labs/-/blob/main/examples/_modules/gpio_devices.py)
  - Repository: [micropython-course-labs](https://gitlab.fekt.vut.cz/fryza/micropython-course-labs) | License: MIT

- **EC11 Rotary Encoder Driver:** Interrupt-based rotary encoder library for MicroPython.
  - Author: Mike Teachman (`miketeachman`)
  - Source Code: [`rotary_irq_rp2.py`](https://github.com/miketeachman/micropython-rotary/blob/master/rotary_irq_rp2.py) and [`rotary.py`](https://github.com/miketeachman/micropython-rotary/blob/master/rotary.py)
  - Repository: [micropython-rotary](https://github.com/miketeachman/micropython-rotary) | License: MIT

- **Si4703 FM Tuner Driver:** Custom MicroPython I2C driver for the Si4703 FM receiver with RDS support, written specifically for the Raspberry Pi Pico W.
  - Author: Maxim Sudakov
  - Source Code: [`lib/fm_tuner.py`](../lib/fm_tuner.py)
  - References & Inspiration: The register map and start-up sequence follow the Silicon Labs AN230 Programming Guide. The 2-wire reset procedure and general architectural logic were inspired by the SparkFun Si4703 library (MIT) and Thomas Shaddack's [si4703-RDS](https://github.com/tshaddack/si4703-RDS) repository.

- **Sphinx Documentation Guide:** A practical guide written by our instructor in the lab repository for setting up, structuring, and generating the project documentation.
  - Guide: [`HOWTO_Sphinx.md`](https://gitlab.fekt.vut.cz/fryza/micropython-course-labs/-/blob/main/docs/HOWTO_Sphinx.md)