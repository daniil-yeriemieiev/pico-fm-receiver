Software
========

Controls
--------

**Normal mode:**

* **Rotate:** tune 88,0 to 108,0 MHz (100 kHz steps, wrap-around) or
  adjust volume (0 to 15; 0 mutes). Rapid rotation defers the blocking
  ``tune()`` call by 120 ms so no encoder steps are dropped.
* **Single click:** toggle encoder control between frequency and volume.
* **Press and hold:** seek to the next strong station (non-blocking).
* **Double click:** open the Auto-Scan station menu.

**Auto-Scan menu:**

* **Single click:** start or stop a full-band auto-scan. Results are
  written to a temporary session file (``autoscan_tmp.csv``), which is
  deleted automatically when the program exits.
* **Rotate:** scroll through discovered stations.
* **Press and hold:** tune to the highlighted station and return to
  normal mode.
* **Double click:** exit back to normal mode (aborts an active scan).

Modules
-------

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - File
     - Purpose
   * - ``src/boot.py``
     - Holds the Si4703 in reset at power-up, enables garbage collection.
   * - ``src/main.py``
     - Configuration constants, serial logging, and multi-rate superloop.
   * - ``src/multi_button.py``
     - Gesture recognition (:class:`multi_button.MultiFunctionButton`):
       single click, double click, and hold.
   * - ``src/radio_ui.py``
     - OLED renderer (:class:`radio_ui.RadioUI`): 3x3 normal view and
       scrollable Auto-Scan table.
   * - ``src/station_store.py``
     - Session-only CSV cache (:class:`station_store.StationStore`) for
       auto-scan results.
   * - ``lib/fm_tuner.py``
     - Si4703 driver :class:`fm_tuner.FmTuner`: tune, seek, RSSI,
       RDS station name and RadioText.
   * - ``lib/rotary.py``, ``lib/rotary_irq_rp2.py``
     - Rotary encoder driver (Mike Teachman, MIT).
   * - ``lib/sh1106.py``, ``lib/gpio_devices.py``
     - OLED and button classes from the course (T. Fryza, MIT).

Timing plan
-----------

The program uses a multi-rate non-blocking superloop
(``LOOP_DELAY_MS`` = 5 ms) with a hardware interrupt for the encoder.
``asyncio`` is not used.

.. list-table::
   :header-rows: 1
   :widths: 20 18 20 42

   * - Activity
     - Mechanism
     - Interval
     - Task
   * - Encoder rotation
     - IRQ
     - on event
     - Sets ``encoder_rotated``; no I2C call in the handler.
   * - Button
     - polling
     - 5 ms
     - Debounce 15 ms, double click window 400 ms, hold after 600 ms.
   * - Deferred tune
     - settle timer
     - 120 ms
     - Calls ``radio.tune()`` once rapid rotation stops.
   * - Tuner and RDS
     - polling
     - 30 ms
     - ``radio.poll()`` / ``radio.seek_update()``; up to 4700 ms per
       station for RDS PS during auto-scan.
   * - OLED
     - throttled poll
     - 100 ms (50 ms min)
     - Redraws the framebuffer; the RadioText marquee moves every 250 ms.

OLED layout
-----------

In normal mode, the 128x64 screen is divided into 3 rows and 3 columns
(row.column). In Auto-Scan mode, the full screen displays a 5-row
scrollable table (``RS | FREQ | RDS``) with an inverted highlight bar.

.. list-table::
   :header-rows: 1
   :widths: 12 20 68

   * - Zone
     - Content
     - Position (pixels) and notes
   * - 1.1
     - Signal strength
     - Dynamic 0 to 4 bar icon at x = 2, y = 4; RSSI at x = 18, y = 6.
   * - 1.2 to 1.3
     - Station name
     - x = 44, y = 6. RDS PS (up to 8 chars), "SEEKING.." or "NO RDS".
   * - 2.1
     - Frequency
     - x = 0, y = 28, in MHz; underlined (y = 37) in frequency mode.
   * - 2.2 to 2.3
     - RadioText
     - x = 44, y = 28, 10 characters, scrolling (250 ms step). Shown
       after the complete text is received.
   * - 3.1
     - Speaker icon
     - Dynamic icon at x = 2, y = 48: crossed out at 0, 1 to 3 waves
       scaling with volume.
   * - 3.2 to 3.3
     - Volume
     - Bar at x = 44, y = 50 (56x8 px), value at x = 106, y = 50;
       underlined (y = 59) in volume mode.

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