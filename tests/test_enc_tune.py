"""Encoder tunes the Si4703 FM tuner, RDS is polled continuously.

Turn the encoder: after it stands still for TUNE_DELAY_MS the tuner
tunes to the new frequency. ``poll()`` runs every POLL_MS all the time.
One status line is printed every PRINT_MS.
Pins are the ones used in the team's test on 2026-11-19."""

import time
from rotary_irq_rp2 import RotaryIRQ
from fm_tuner import FmTuner

PIN_CLK = 14
PIN_DT = 15
I2C_ID = 0
PIN_SDA = 4
PIN_SCL = 5
PIN_RST = 12

MIN_VAL = 875  # encoder value = frequency in 100 kHz
MAX_VAL = 1080
START_MHZ = 98.4
VOLUME = 8

LOOP_MS = 10
INPUT_MS = 20
TUNE_DELAY_MS = 150
POLL_MS = 30
PRINT_MS = 500


def due(now, last, interval):
    """Return True when interval has passed since last."""
    return time.ticks_diff(now, last) >= interval


def print_status(radio):
    """Print frequency, signal and RDS counters in one line."""
    ps = radio.ps if radio.ps else "--------"
    pi = f"{radio.pi:#06x}" if radio.pi is not None else "n/a"
    print(f"{radio.frequency:5.1f} MHz  RSSI {radio.rssi:2d}  "
          f"{'ST' if radio.stereo else 'MO'}  groups {radio.groups} "
          f"bad {radio.bad_groups}  PI {pi}  PS {ps}")


def main():
    """Run the encoder, tune and RDS loop."""
    enc = RotaryIRQ(pin_num_clk=PIN_CLK, pin_num_dt=PIN_DT,
                    min_val=MIN_VAL, max_val=MAX_VAL,
                    range_mode=RotaryIRQ.RANGE_BOUNDED)
    enc.set(value=round(START_MHZ * 10))
    radio = FmTuner(I2C_ID, PIN_SDA, PIN_SCL, PIN_RST)
    try:
        radio.start(volume=VOLUME, frequency=START_MHZ)
    except OSError as e:
        print(f"Tuner error: {e}")
        return
    last_value = enc.value()
    changed_at = None  # time of last encoder step
    t_input = t_poll = t_print = time.ticks_ms()
    try:
        while True:
            now = time.ticks_ms()
            if due(now, t_input, INPUT_MS):
                t_input = now
                value = enc.value()
                if value != last_value:
                    last_value = value
                    changed_at = now
            if changed_at is not None and due(now, changed_at, TUNE_DELAY_MS):
                changed_at = None
                radio.tune(last_value / 10)  # no seek needed
            if due(now, t_poll, POLL_MS):
                t_poll = now
                radio.poll()
            if due(now, t_print, PRINT_MS):
                t_print = now
                print_status(radio)
            time.sleep_ms(LOOP_MS)
    except KeyboardInterrupt:
        print("Interrupted")
    radio.power_off()


main()
