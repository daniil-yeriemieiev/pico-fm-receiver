References
==========

Datasheets
----------

* `Raspberry Pi Pico W <https://datasheets.raspberrypi.com/picow/pico-w-datasheet.pdf>`_
* `RP2040 <https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf>`_
* `Si4702/03-C19 <https://download.mikroe.com/documents/datasheets/Si4703_datasheet.pdf>`_
* `AN230, Si4700/01/02/03 Programming Guide <https://cdn.sparkfun.com/datasheets/BreakoutBoards/Si4703_ProgrammingGuide.pdf>`_
* `ALPS EC11 <https://www.tme.com/Document/947fff760d3e8051ff1d91b3169c392a/ALPS-EC11.pdf>`_
* `SH1106 <https://www.elecrow.com/download/SH1106%20datasheet.pdf>`_

Third-party code
----------------

* ``rotary.py``, ``rotary_irq_rp2.py``: Mike Teachman and Eric Moyer,
  `micropython-rotary <https://github.com/miketeachman/micropython-rotary>`_,
  MIT licence. Changes: reST docstrings, ``reset()`` resets to ``min_val``.
* ``sh1106.py``, ``gpio_devices.py``: Tomas Fryza, Shujen Chen et al.,
  `micropython-course-labs <https://gitlab.fekt.vut.cz/fryza/micropython-course-labs>`_,
  MIT licence.
* ``fm_tuner.py``: written by the team. Register map and start-up
  sequence follow AN230. The 2-wire reset follows the SparkFun Si4703
  library (MIT) and
  `si4703-RDS <https://github.com/tshaddack/si4703-RDS>`_ by Thomas
  Shaddack (MIT).

Course material
---------------

* `HOWTO_Sphinx.md <https://gitlab.fekt.vut.cz/fryza/micropython-course-labs/-/blob/main/docs/HOWTO_Sphinx.md>`_
