Testing
=======

Hardware tests are in the ``tests/`` folder. They run on the Pico W
(MicroPico, "Run current file") and are not uploaded to the device
permanently. Upload ``lib/*.py`` first.

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - Test
     - What it checks
   * - ``test_fm.py``
     - Chip ID 0x1242, band edges and clamping, tuning time below
       300 ms, seek across the band with an RSSI table, 20 s of RDS
       listening, volume and mute, longest ``poll`` / ``seek_update``
       call below 20 ms. Prints PASS / FAIL for every check.
   * - ``test_encoder.py``
     - Rotary encoder rotation and button.
   * - ``test_enc_with_fm.py``
     - First integration test of encoder and tuner.
   * - ``test_enc_tune.py``
     - The encoder tunes the radio 150 ms after the last step while
       ``poll()`` runs every 30 ms; prints frequency, RSSI, RDS counters,
       PI and station name twice per second.
   * - ``test_rds_diag.py``
     - 30 s on one station: RSSI, number of RDS groups, groups with
       errors, PI and name. Used to compare reception with and without
       headphones. Expected on a good station: about 11 groups per second.

RadioText and the RDS decoder were also checked on a PC with a simulated
register interface: complete text, partial text (hidden), change of the
A/B flag, a bad block D and version B groups.
