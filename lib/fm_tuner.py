"""Si4703 FM tuner driver for MicroPython (Raspberry Pi Pico W).

Tuning, seeking, RSSI / stereo status and RDS Programme Service
(station name) decoding with error checking.

Lab style: no ``asyncio``. Timing uses ``time.sleep_ms`` and
``time.ticks_ms`` / ``time.ticks_diff``. Tuning is short and blocking
(under 100 ms), seeking is non-blocking (``seek_start`` + ``seek_update``).

Register map and start-up sequence follow Silicon Labs AN230
(Si4700/01/02/03 Programming Guide) and the Si4702/03-C19 datasheet.
The 2-wire reset procedure follows the SparkFun Si4703 library (MIT),
as also used in ``_libsi4703.py``.
"""

import time
from machine import Pin, I2C

# Register addresses
_DEVICEID = 0x00
_CHIPID = 0x01
_POWERCFG = 0x02
_CHANNEL = 0x03
_SYSCONFIG1 = 0x04
_SYSCONFIG2 = 0x05
_SYSCONFIG3 = 0x06
_TEST1 = 0x07
_STATUSRSSI = 0x0A
_READCHAN = 0x0B
_RDSA = 0x0C
_RDSD = 0x0F

# POWERCFG bits and masks
_DMUTE = 0x4000
_RDSM = 0x0800
_SEEKUP = 0x0200
_SEEK = 0x0100
_DISABLE = 0x0040
_ENABLE = 0x0001
_NOT_DMUTE = 0xBFFF
_NOT_SEEK = 0xFEFF
_NOT_SEEK_DIR = 0xF9FF  # SKMODE=0 (wrap), SEEKUP=0
# CHANNEL bits and masks
_TUNE = 0x8000
_NOT_TUNE = 0x7FFF
# SYSCONFIG1 bits and masks
_RDS = 0x1000
_DE = 0x0800
_NOT_RDS = 0xEFFF
# SYSCONFIG3 bits
_RDSPRF = 0x0200
# STATUSRSSI bits
_RDSR = 0x8000
_STC = 0x4000
_SFBL = 0x2000
_ST = 0x0100

_DEVICE_ID_SI470X = 0x1242
_DEV_SI4703 = 9


def _char(code):
    """Return printable ASCII character or question mark."""
    if 32 <= code < 127:
        return chr(code)
    return "?"


class FmTuner:
    """Si4703 FM receiver.

    Band 87,5-108 MHz, 100 kHz step, 50 us de-emphasis.

    :param i2c_id: I2C controller number (0 or 1).
    :param sda: GPIO number connected to SDIO.
    :param scl: GPIO number connected to SCLK.
    :param rst: GPIO number connected to RST.
    :param freq: I2C clock frequency in Hz.

    Typical use::

        radio = FmTuner(1, 2, 3, 16)
        radio.start(volume=5)
        radio.tune(98.4)
        while True:
            radio.poll()           # every 20-40 ms
            print(radio.ps, radio.rssi)
            time.sleep_ms(30)
    """

    ADDR = 0x10
    F_MIN = 87.5
    F_MAX = 108.0
    CHANNELS = 205
    SEEK_TIMEOUT_MS = 8000

    def __init__(self, i2c_id=1, sda=2, scl=3, rst=16, freq=400000):
        """Store pins, hold chip in reset."""
        self._i2c_id = i2c_id
        self._sda = sda
        self._scl = scl
        self._freq = freq
        self._rst = Pin(rst, Pin.OUT)
        self._rst.value(0)  # chip off, silent
        self.i2c = None
        self.reg = [0] * 16
        self.powered = False
        self.busy = False
        self.seeking = False
        self.seek_failed = False
        self.has_rds = False
        self.rssi = 0
        self.stereo = False
        self.frequency = self.F_MIN
        self.volume = 0
        self._seek_t0 = 0
        self._reset_rds()

    # ---------- low level ----------

    def _hw_reset(self):
        """Reset chip into 2-wire I2C mode."""
        sda = Pin(self._sda, Pin.OUT)
        sda.value(0)  # SDIO low selects 2-wire
        self._rst.value(0)
        time.sleep_ms(1)
        self._rst.value(1)  # bus mode latched here
        time.sleep_ms(1)
        self.i2c = I2C(self._i2c_id, sda=Pin(self._sda),
                       scl=Pin(self._scl), freq=self._freq)

    def _read(self, n=16):
        """Read registers starting at address 0x0A."""
        data = self.i2c.readfrom(self.ADDR, 2 * n)
        r = _STATUSRSSI
        for i in range(n):
            self.reg[r] = (data[2 * i] << 8) | data[2 * i + 1]
            r = (r + 1) & 0x0F

    def _write(self, last):
        """Write registers starting at address 0x02."""
        buf = []
        for r in range(_POWERCFG, last + 1):
            buf.append(self.reg[r] >> 8)
            buf.append(self.reg[r] & 0xFF)
        self.i2c.writeto(self.ADDR, bytes(buf))

    def _wait_stc(self, state, timeout_ms):
        """Wait until STC flag has given state."""
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < timeout_ms:
            self._read(1)
            if bool(self.reg[_STATUSRSSI] & _STC) == state:
                return True
            time.sleep_ms(5)
        return False

    def _update_status(self):
        """Decode RSSI, stereo and frequency from registers."""
        s =self.reg[_STATUSRSSI]
        self.rssi = s & 0xFF
        self.stereo = bool(s & _ST)
        self.frequency = (875 + (self.reg[_READCHAN] & 0x03FF)) / 10

    def _finish(self):
        """Refresh status and reset RDS after tuning."""
        self._read(2)
        self._update_status()
        self._reset_rds()
        self.busy = False

    def _reset_rds(self):
        """Clear all RDS decoder state variables."""
        self.ps = ""
        self.pi = None
        self.groups = 0
        self.bad_groups = 0
        self.ps_time_ms = None
        self._ps_buf = [" "] * 8
        self._ps_mask = 0
        self._ps_candidate = None
        self._last_group = None
        self._tuned_at = time.ticks_ms()

    # ---------- public API ----------

    def start(self, volume=5, frequency=None):
        """Reset, power up and configure the tuner.

        Takes about 0,6 s.

        :param volume: initial volume 0-15.
        :param frequency: optional frequency in MHz to tune after start.
        :raises OSError: chip not found or not an Si470x.
        """
        self._hw_reset()
        if self.ADDR not in self.i2c.scan():
            raise OSError("Si4703 not found at I2C 0x10")
        self._read(16)
        if self.reg[_DEVICEID] != _DEVICE_ID_SI470X:
            raise OSError(f"Unexpected device ID {self.reg[_DEVICEID]:#06x}")
        self.reg[_TEST1] = 0x8100  # enable crystal oscillator
        self._write(_TEST1)
        time.sleep_ms(500)  # oscillator settling (AN230)
        self.reg[_POWERCFG] = _DMUTE | _ENABLE
        self._write(_POWERCFG)
        time.sleep_ms(110)  # power-up time
        self.powered = True
        self._read(16)
        self.has_rds = ((self.reg[_CHIPID] >> 6) & 0x0F) == _DEV_SI4703
        self.volume = min(max(volume, 0), 15)
        self.reg[_POWERCFG] |= _RDSM  # verbose RDS error flags
        self.reg[_SYSCONFIG1] |= _RDS | _DE  # RDS on, 50 us
        # SEEKTH 0x19, SPACE 100 kHz (0x10), band 87.5-108 MHz
        self.reg[_SYSCONFIG2] = 0x1900 | 0x0010 | self.volume
        # SKSNR 4, SKCNT 8 (AN230 recommended)
        self.reg[_SYSCONFIG3] = ((self.reg[_SYSCONFIG3] & 0xFC00)
                                 | _RDSPRF | 0x0048)
        self._write(_SYSCONFIG3)
        if frequency is not None:
            self.tune(frequency)

    def tune(self, mhz, timeout_ms=500):
        """Tune to a frequency and wait.

        ``mhz`` is clamped to the band and rounded to 100 kHz.
        Blocks for the tuning time (typically under 100 ms).

        :return: tuned frequency in MHz, or ``None`` on timeout.
        """
        if self.seeking:
            return None
        chan = min(max(round((mhz - self.F_MIN) * 10), 0), self.CHANNELS)
        self.busy = True
        self.reg[_CHANNEL] = (self.reg[_CHANNEL] & 0x7C00) | _TUNE | chan
        self._write(_CHANNEL)
        ok = self._wait_stc(True, timeout_ms)
        self.reg[_CHANNEL] &= _NOT_TUNE
        self._write(_CHANNEL)
        self._wait_stc(False, 50)
        self._finish()
        return self.frequency if ok else None

    def seek_start(self, up=True):
        """Start a non-blocking seek without waiting.

        Seek wraps around the band edges and does not wait. Call :meth:`seek_update` repeatedly until it returns ``True``.

        :param up: seek direction.
        """
        if self.busy:
            return
        self.busy = True
        self.seeking = True
        self.seek_failed = False
        power = self.reg[_POWERCFG] & _NOT_SEEK_DIR
        if up:
            power |= _SEEKUP
        self.reg[_POWERCFG] = power | _SEEK
        self._write(_POWERCFG)
        self._seek_t0 = time.ticks_ms()

    def seek_update(self):
        """Check progress of the running seek.

        Call every 20-50 ms.

        :return: ``True`` when finished (or not seeking). Then read
            ``seek_failed`` and ``frequency``.
        """
        if not self.seeking:
            return True
        self._read(1)
        done = bool(self.reg[_STATUSRSSI] & _STC)
        elapsed = time.ticks_diff(time.ticks_ms(), self._seek_t0)
        if not done and elapsed < self.SEEK_TIMEOUT_MS:
            return False
        self.seek_failed = (not done) or bool(self.reg[_STATUSRSSI] & _SFBL)
        self.reg[_POWERCFG] &= _NOT_SEEK
        self._write(_POWERCFG)
        self._wait_stc(False, 50)
        self.seeking = False
        self._finish()
        return True

    def seek(self, up=True):
        """Seek and wait until it finishes.

        :return: found frequency in MHz, or ``None`` if nothing was found.
        """
        self.seek_start(up)
        while not self.seek_update():
            time.sleep_ms(5)
        if self.seek_failed:
            return None
        return self.frequency

    def poll(self):
        """Update status and decode one RDS group.

        Reads RSSI, stereo and one RDS group if ready. Call every 20-40 ms (RDS sends about 11,4 groups per second).

        :return: ``True`` if a new RDS group was processed.
        """
        if self.busy or self.i2c is None:
            return False
        self._read(6)
        self._update_status()
        if not self.reg[_STATUSRSSI] & _RDSR:
            return False
        group = tuple(self.reg[_RDSA:_RDSD + 1])
        if group == self._last_group:
            return False
        self._last_group = group
        self._decode_rds(group)
        return True

    def _decode_rds(self, group):
        """Decode station name from one RDS group."""
        a, b, _, d = group
        s = self.reg[_STATUSRSSI]
        rc = self.reg[_READCHAN]
        bler = ((s >> 9) & 3, (rc >> 14) & 3, (rc >> 12) & 3, (rc >> 10) & 3)
        self.groups += 1
        if 3 in bler:
            self.bad_groups += 1
        if bler[1] == 3:
            return  # group type unknown
        if bler[0] < 3:
            self.pi = a
        if (b >> 12) != 0 or bler[3] == 3:
            return  # not group 0A/0B
        seg = b & 0x03
        self._ps_buf[2 * seg] = _char(d >> 8)
        self._ps_buf[2 * seg + 1] = _char(d & 0xFF)
        self._ps_mask |= 1 << seg
        if self._ps_mask != 0x0F:
            return
        text = "".join(self._ps_buf)
        if text == self._ps_candidate:  # confirmed twice
            if not self.ps:
                self.ps_time_ms = time.ticks_diff(time.ticks_ms(),
                                                  self._tuned_at)
            self.ps = text.strip()
        self._ps_candidate = text
        self._ps_mask = 0

    def set_volume(self, level):
        """Set audio volume from 0 to 15."""
        self.volume = min(max(level, 0), 15)
        self.reg[_SYSCONFIG2] = (self.reg[_SYSCONFIG2] & 0xFFF0) | self.volume
        self._write(_SYSCONFIG2)

    def mute(self, on=True):
        """Mute or unmute the audio output."""
        if on:
            self.reg[_POWERCFG] &= _NOT_DMUTE
        else:
            self.reg[_POWERCFG] |= _DMUTE
        self._write(_POWERCFG)

    def chip_info(self):
        """Return chip identification values as dictionary."""
        cid = self.reg[_CHIPID]
        return {
            "device_id": self.reg[_DEVICEID],
            "chip_id": cid,
            "rev": cid >> 10,
            "dev": (cid >> 6) & 0x0F,
            "firmware": cid & 0x3F,
        }

    def power_off(self):
        """Power down chip and hold in reset."""
        if self.powered:
            self.reg[_SYSCONFIG1] &= _NOT_RDS
            self._write(_SYSCONFIG1)
            self.reg[_POWERCFG] = _DISABLE | _ENABLE
            self._write(_POWERCFG)
            self.powered = False
        self._rst.value(0)
