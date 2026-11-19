"""RDS diagnostic: print signal and RDS counters on a fixed station.

Run once without and once with headphones, compare the output.
Expected on a good station: about 11 groups/s, few bad groups.
Change STATION_MHZ to a strong local station."""

import time
from fm_tuner import FmTuner

I2C_ID = 0
PIN_SDA = 4
PIN_SCL = 5
PIN_RST = 12

STATION_MHZ = 98.4
VOLUME = 5
LISTEN_S = 30
POLL_MS = 30
PRINT_MS = 1000


def main():
    """Listen on one station and print RDS statistics."""
    radio = FmTuner(I2C_ID, PIN_SDA, PIN_SCL, PIN_RST)
    try:
        radio.start(volume=VOLUME)
    except OSError as e:
        print(f"Tuner error: {e}")
        return
    f = radio.tune(STATION_MHZ)
    print(f"tuned {f} MHz, RDS capable: {radio.has_rds}")
    print("  t/s  RSSI  ST  groups  bad  PI      PS")
    t0 = t_print = time.ticks_ms()
    try:
        while time.ticks_diff(time.ticks_ms(), t0) < LISTEN_S * 1000:
            now = time.ticks_ms()
            radio.poll()
            if time.ticks_diff(now, t_print) >= PRINT_MS:
                t_print = now
                secs = time.ticks_diff(now, t0) // 1000
                pi = f"{radio.pi:#06x}" if radio.pi is not None else "n/a   "
                print(f"  {secs:3d}  {radio.rssi:4d}  "
                      f"{'y' if radio.stereo else 'n'}  {radio.groups:6d}  "
                      f"{radio.bad_groups:3d}  {pi}  '{radio.ps}'")
            time.sleep_ms(POLL_MS)
    except KeyboardInterrupt:
        print("Interrupted")
    print(f"result: {radio.groups / LISTEN_S:.1f} groups/s, "
          f"{radio.bad_groups} bad, PS '{radio.ps}'")
    radio.power_off()


main()
