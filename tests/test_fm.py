"""Si4703 FM tuner hardware test for Raspberry Pi Pico W.

Checks chip ID, band edges and tuning time, scans the band with seek,
then listens for RDS on the strongest station and steps the volume.
Also records the longest non-blocking call (``poll``, ``seek_update``)."""

import time
from fm_tuner import FmTuner

I2C_ID = 1
PIN_SDA = 2
PIN_SCL = 3
PIN_RST = 16

VOLUME = 5
RDS_LISTEN_S = 20
TUNE_LIMIT_MS = 300
CALL_LIMIT_MS = 20
POLL_MS = 30
SEEK_POLL_MS = 20
MAX_STATIONS = 60


class FmTest:
    """Sequence of hardware checks with summary."""

    def __init__(self):
        """Create tuner object and empty result lists."""
        self.radio = FmTuner(I2C_ID, PIN_SDA, PIN_SCL, PIN_RST)
        self.results = []
        self.tune_times = []
        self.worst_call = 0  # longest non-blocking call, ms

    def check(self, name, passed, detail=""):
        """Print and store one PASS or FAIL result."""
        self.results.append((name, passed))
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}  {detail}")

    def note_call(self, t0):
        """Remember the longest call duration so far."""
        ms = time.ticks_diff(time.ticks_ms(), t0)
        if ms > self.worst_call:
            self.worst_call = ms

    def timed_tune(self, mhz):
        """Tune and return frequency with duration."""
        t0 = time.ticks_ms()
        f = self.radio.tune(mhz)
        ms = time.ticks_diff(time.ticks_ms(), t0)
        self.tune_times.append(ms)
        return f, ms

    def timed_poll(self):
        """Poll the tuner and record call duration."""
        t0 = time.ticks_ms()
        self.radio.poll()
        self.note_call(t0)

    def seek_once(self):
        """Seek up without blocking, return frequency and duration."""
        t0 = time.ticks_ms()
        self.radio.seek_start(up=True)
        done = False
        while not done:
            t1 = time.ticks_ms()
            done = self.radio.seek_update()
            self.note_call(t1)
            if not done:
                time.sleep_ms(SEEK_POLL_MS)
        ms = time.ticks_diff(time.ticks_ms(), t0)
        if self.radio.seek_failed:
            return None, ms
        return self.radio.frequency, ms

    def test_start(self):
        """Start the tuner and check chip identification."""
        print("\n--- 1. Start-up ---")
        t0 = time.ticks_ms()
        try:
            self.radio.start(volume=VOLUME)
        except OSError as e:
            self.check("chip present", False, str(e))
            print("  check wiring: SDIO/SCLK/RST/SEN, 3V3, GND")
            return False
        dt = time.ticks_diff(time.ticks_ms(), t0)
        info = self.radio.chip_info()
        self.check("device ID", info["device_id"] == 0x1242,
                   f"{info['device_id']:#06x}, chip {info['chip_id']:#06x}, "
                   f"rev {info['rev']}, fw {info['firmware']}, start {dt} ms")
        self.check("RDS capable (Si4703)", self.radio.has_rds,
                   f"dev field = {info['dev']}")
        return True

    def test_band_edges(self):
        """Tune band edges, check clamping and tuning time."""
        print("\n--- 2. Band edges and clamping ---")
        cases = ((87.5, 87.5), (108.0, 108.0), (98.4, 98.4),
                 (80.0, 87.5), (120.0, 108.0))
        for want, expect in cases:
            f, ms = self.timed_tune(want)
            ok = f is not None and abs(f - expect) < 0.05
            self.check(f"tune {want:.1f} MHz", ok, f"-> {f} MHz in {ms} ms")
        worst = max(self.tune_times)
        self.check(f"tune time < {TUNE_LIMIT_MS} ms", worst < TUNE_LIMIT_MS,
                   f"worst {worst} ms")

    def test_scan(self):
        """Scan whole band by seeking, print RSSI table."""
        print("\n--- 3. Band scan (seek up) ---")
        self.radio.tune(self.radio.F_MIN)
        stations = []
        last = 0
        t_scan = time.ticks_ms()
        for _ in range(MAX_STATIONS):
            f, ms = self.seek_once()
            if f is None or f <= last:
                break  # nothing found or wrapped
            last = f
            time.sleep_ms(50)  # let RSSI settle
            self.radio.poll()
            stations.append((f, self.radio.rssi, self.radio.stereo, ms))
        total = time.ticks_diff(time.ticks_ms(), t_scan)
        print("  f/MHz   RSSI/dBuV  stereo  seek/ms")
        for f, rssi, stereo, ms in stations:
            text = "yes" if stereo else "no"
            print(f"  {f:5.1f}   {rssi:9d}  {text:>6}  {ms:7d}")
        self.check("seek finds stations", len(stations) > 0,
                   f"{len(stations)} stations, full scan {total} ms")
        return stations

    def test_rds(self, stations):
        """Listen for RDS on the strongest station."""
        print("\n--- 4. RDS ---")
        if len(stations) == 0:
            self.check("RDS station name", False, "no station to test")
            return
        best = stations[0]
        for s in stations:
            if s[1] > best[1]:
                best = s
        f, ms = self.timed_tune(best[0])
        print(f"  listening on {f:.1f} MHz for {RDS_LISTEN_S} s ...")
        r = self.radio
        shown = ""
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < RDS_LISTEN_S * 1000:
            self.timed_poll()
            if r.ps != shown:
                shown = r.ps
                print(f"  PS = '{shown}'")
            time.sleep_ms(POLL_MS)
        bad = 0
        if r.groups > 0:
            bad = 100 * r.bad_groups / r.groups
        pi = "n/a"
        if r.pi is not None:
            pi = f"{r.pi:#06x}"
        print(f"  PI {pi}, {r.groups} groups "
              f"({r.groups / RDS_LISTEN_S:.1f} /s), {bad:.1f} % with errors")
        self.check("RDS station name", bool(r.ps),
                   f"'{r.ps}' after {r.ps_time_ms} ms")

    def test_volume(self):
        """Step volume levels and test mute by ear."""
        print("\n--- 5. Volume and mute (listen) ---")
        for level in (2, 8, 15, VOLUME):
            self.radio.set_volume(level)
            print(f"  volume {level}")
            time.sleep_ms(1000)
        self.radio.mute(True)
        print("  muted")
        time.sleep_ms(1000)
        self.radio.mute(False)
        print("  unmuted")

    def summary(self):
        """Print number of passed checks and failures."""
        passed = 0
        for _, ok in self.results:
            if ok:
                passed += 1
        print(f"\n=== {passed} / {len(self.results)} checks passed ===")
        for name, ok in self.results:
            if not ok:
                print(f"  FAILED: {name}")

    def run(self):
        """Run all hardware tests in order."""
        if self.test_start():
            self.test_band_edges()
            stations = self.test_scan()
            self.test_rds(stations)
            self.test_volume()
            self.check(f"longest call < {CALL_LIMIT_MS} ms",
                       self.worst_call < CALL_LIMIT_MS,
                       f"poll/seek_update worst {self.worst_call} ms")
        self.summary()


def main():
    """Run the test and always power the chip down."""
    test = FmTest()
    try:
        test.run()
    except KeyboardInterrupt:
        print("Interrupted")
    test.radio.power_off()


main()
