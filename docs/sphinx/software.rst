Software
========

Controls
--------

* **Rotate:** tune 88,0 to 108,0 MHz in 100 kHz steps (wraps at the edges).
* **Single click:** seek to the next strong station (non-blocking).
* **Double click:** start or stop the auto-scan. The found stations
  (RSSI, frequency, RDS name) are printed as a table to the serial
  terminal; afterwards the previous frequency is restored.
* **Hold and rotate:** volume 0 to 15 (0 mutes).

Modules
-------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - File
     - Purpose
   * - ``src/boot.py``
     - Holds the Si4703 in reset at power-up, enables garbage collection.
   * - ``src/main.py``
     - Superloop, button gestures (:class:`main.MultiFunctionButton`),
       OLED user interface (:class:`main.RadioUI`).
   * - ``lib/fm_tuner.py``
     - Si4703 driver :class:`fm_tuner.FmTuner`: tune, seek, RSSI,
       RDS station name and RadioText.
   * - ``lib/rotary.py``, ``lib/rotary_irq_rp2.py``
     - Rotary encoder driver (Mike Teachman, MIT).
   * - ``lib/sh1106.py``, ``lib/gpio_devices.py``
     - OLED and button classes from the course (T. Fryza, MIT).

Timing plan
-----------

The program is one non-blocking loop (``LOOP_DELAY_MS`` = 20 ms) with a
hardware interrupt for the encoder. ``asyncio`` is not used.

.. list-table::
   :header-rows: 1
   :widths: 20 20 20 40

   * - Activity
     - Mechanism
     - Interval
     - Task
   * - Encoder rotation
     - IRQ
     - on event
     - Sets the flag ``encoder_rotated``; no I2C call in the handler.
   * - Button
     - polling
     - 20 ms
     - Debounce 25 ms, double click window 350 ms, hold after 400 ms.
   * - Tuner and RDS
     - polling
     - 20 ms
     - ``radio.poll()``: RSSI, stereo, one RDS group (about 11,4 groups/s).
   * - Seek and auto-scan
     - state machine
     - 20 ms
     - ``radio.seek_update()``; up to 4700 ms per station for the RDS name.
   * - OLED
     - polling
     - 20 ms
     - Redraws the framebuffer; the RadioText marquee moves every 250 ms.

OLED layout
-----------

The 128x64 screen is divided into 3 rows and 3 columns (row.column).

.. list-table::
   :header-rows: 1
   :widths: 12 20 68

   * - Zone
     - Content
     - Position (pixels) and notes
   * - 1.1
     - Signal strength
     - Icon at x = 2, y = 4 (4 bars), RSSI value at x = 18, y = 6.
   * - 1.2 to 1.3
     - RadioText
     - x = 40, y = 6, 11 characters, scrolling. Shown after the whole
       text was received. "SCANNING.." during the auto-scan.
   * - 2.1
     - Frequency
     - x = 0, y = 28, in MHz.
   * - 2.2 to 2.3
     - Station name
     - x = 50, y = 28. RDS name (PS), "SEEKING.." or "NO RDS".
   * - 3.1
     - Speaker icon
     - x = 4, y = 48; crossed out when the volume is 0.
   * - 3.2 to 3.3
     - Volume
     - Bar at x = 50, y = 50 (48x8 pixels), value at x = 104, y = 50;
       underlined while the button is held.

RDS decoding
------------

:meth:`fm_tuner.FmTuner.poll` reads one RDS group per call. The decoder
uses the block error counters of the Si4703 and keeps:

* ``ps``: station name (8 characters), from groups 0A/0B; accepted after
  two identical complete readings.
* ``rt``: RadioText (up to 64 characters), from groups 2A/2B; published
  only when every character up to the end marker was received. A change
  of the A/B flag clears the text.
* ``pi``: programme identification code.
