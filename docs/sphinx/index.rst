Pico W FM Radio Receiver
========================

Digital FM radio receiver on a Raspberry Pi Pico W (MicroPython).
An Si4703 tuner is controlled with an EC11 rotary encoder and its
pushbutton, and an SH1106 OLED display shows the frequency, signal
strength, RDS station name and scrolling RadioText.
Headphones in the 3,5 mm jack of the tuner module are the audio output
and also the FM antenna.

Project for the DE2 course, VUT FEKT, 2026.

Source code: `GitHub repository <https://github.com/daniil-yeriemieiev/pico-fm-receiver>`_.

Team
----

* **Daniil Yeriemieiev**: system architecture, encoder, main application
  (``boot.py``, ``main.py``), integration tests, documentation.
* **Maxim Sudakov**: Si4703 driver ``fm_tuner.py``, I2C debugging, RDS.
* **Gleb Dulesov**: hardware assembly, OLED UI design, component tests,
  presentation materials.

.. toctree::
   :maxdepth: 2
   :caption: Contents

   hardware
   software
   testing
   api
   references
