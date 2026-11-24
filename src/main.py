"""Pico W FM radio: Si4703 tuner, SH1106 OLED and EC11 encoder.

Rotate to tune, click to seek, double click to auto-scan,
hold and rotate to change the volume.
"""

import time
from machine import Pin, I2C  # type: ignore

from fm_tuner import FmTuner
from sh1106 import SH1106_I2C
from rotary_irq_rp2 import RotaryIRQ
from gpio_devices import Button

# Si4703 tuner (I2C1)
RADIO_I2C_ID = 1
PIN_RADIO_SDA = 26
PIN_RADIO_SCL = 27
PIN_RADIO_RST = 16
RADIO_I2C_FREQ = 400_000

# SH1106 display (I2C0); True shares the tuner bus
OLED_SHARED_I2C = False
OLED_I2C_ID = 0
PIN_OLED_SDA = 4
PIN_OLED_SCL = 5
OLED_I2C_FREQ = 400_000

# EC11 encoder
PIN_ENC_CLK = 14
PIN_ENC_DT = 15
PIN_ENC_SW = 13

# Frequencies are scaled by 10 (883 = 88.3 MHz)
FM_MIN_SCALED = 880
FM_MAX_SCALED = 1080
DEFAULT_FREQ_SCALED = 883
VOL_MIN = 0
VOL_MAX = 15
DEFAULT_VOLUME = 10

LOOP_DELAY_MS = 20
DEBOUNCE_MS = 25
DOUBLE_CLICK_MS = 350  # max gap between two clicks
HOLD_THRESHOLD_MS = 400  # hold time for volume mode

AUTOSCAN_RDS_WAIT_MS = 4700  # max RDS wait per station
RT_SCROLL_MS = 250  # RadioText scroll step
RT_WINDOW_CHARS = 11  # visible RadioText characters
RT_X = 40  # RadioText window left edge

encoder_rotated = False  # set in IRQ, cleared in loop


def on_encoder_change():
    """Set a flag when the encoder rotates."""
    global encoder_rotated
    encoder_rotated = True


class MultiFunctionButton(Button):
    """Button with single click, double click and hold detection."""

    EVENT_NONE = 0
    EVENT_SINGLE_CLICK = 1
    EVENT_DOUBLE_CLICK = 2

    def __init__(self, pin_number):
        """Initialize button state for the given pin."""
        super().__init__(pin_number)
        self._last_raw = self.is_pressed()
        self._stable_pressed = self._last_raw
        self._last_debounce_ms = time.ticks_ms()
        self._press_start_ms = 0
        self._last_release_ms = 0
        self._click_count = 0
        self.is_holding = False

    def update(self):
        """Poll the button and return a click event.

        Call once per loop. The hold state is in ``is_holding``.
        """
        now = time.ticks_ms()
        raw_pressed = self.is_pressed()
        event = self.EVENT_NONE

        if raw_pressed != self._last_raw:
            self._last_raw = raw_pressed
            self._last_debounce_ms = now

        if time.ticks_diff(now, self._last_debounce_ms) >= DEBOUNCE_MS:
            if raw_pressed != self._stable_pressed:
                self._stable_pressed = raw_pressed

                if self._stable_pressed:
                    self._press_start_ms = now
                elif self.is_holding:
                    self.is_holding = False
                    self._click_count = 0
                else:
                    self._click_count += 1
                    self._last_release_ms = now
                    if self._click_count == 2:
                        self._click_count = 0
                        event = self.EVENT_DOUBLE_CLICK

        # Enter hold state
        if self._stable_pressed and not self.is_holding:
            if time.ticks_diff(now, self._press_start_ms) >= HOLD_THRESHOLD_MS:
                self.is_holding = True
                self._click_count = 0

        # Double-click window expired
        if (self._click_count == 1 and not self._stable_pressed
                and time.ticks_diff(now, self._last_release_ms) >= DOUBLE_CLICK_MS):
            self._click_count = 0
            event = self.EVENT_SINGLE_CLICK

        return event


class RadioUI:
    """OLED user interface on a 3x3 zone grid."""

    def __init__(self, oled):
        """Store the display and reset the marquee state."""
        self.oled = oled
        self._scroll_pos = 0
        self._last_scroll_ms = time.ticks_ms()
        self._last_rds_text = ""

    def _draw_rssi_icon(self, x, y, rssi):
        """Draw a four-bar signal strength icon."""
        # x, y, width, height, minimum RSSI
        bars = [
            (0, 8, 2, 3, 5),
            (3, 6, 2, 5, 15),
            (6, 3, 2, 8, 25),
            (9, 0, 2, 11, 38),
        ]
        for bx, by, bw, bh, threshold in bars:
            if rssi >= threshold:
                self.oled.fill_rect(x + bx, y + by, bw, bh, 1)
            else:
                self.oled.rect(x + bx, y + by, bw, bh, 1)

    def _draw_speaker_icon(self, x, y, muted):
        """Draw a speaker icon, crossed out when muted."""
        self.oled.fill_rect(x, y + 3, 3, 6, 1)
        self.oled.vline(x + 3, y + 2, 8, 1)
        self.oled.vline(x + 4, y + 1, 10, 1)
        self.oled.vline(x + 5, y, 12, 1)

        if muted:
            self.oled.line(x + 8, y + 3, x + 13, y + 8, 1)
            self.oled.line(x + 8, y + 8, x + 13, y + 3, 1)
        else:
            self.oled.vline(x + 8, y + 3, 6, 1)
            self.oled.vline(x + 11, y + 1, 10, 1)

    def _get_visible_rt(self, rt_text):
        """Return the visible part of the scrolling RadioText."""
        if rt_text != self._last_rds_text:
            self._last_rds_text = rt_text
            self._scroll_pos = 0
            self._last_scroll_ms = time.ticks_ms()

        if len(rt_text) <= RT_WINDOW_CHARS:
            return rt_text

        now = time.ticks_ms()
        padded = rt_text + "   "
        if time.ticks_diff(now, self._last_scroll_ms) >= RT_SCROLL_MS:
            self._last_scroll_ms = now
            self._scroll_pos = (self._scroll_pos + 1) % len(padded)

        doubled = padded + padded
        return doubled[self._scroll_pos:self._scroll_pos + RT_WINDOW_CHARS]

    def render(self, radio, autoscan_active, holding_volume):
        """Draw all display zones and refresh the screen."""
        self.oled.fill(0)

        # Row 1: signal strength and RadioText
        self._draw_rssi_icon(2, 4, radio.rssi)
        self.oled.text(f"{radio.rssi:>2}", 18, 6)
        rt_raw = "SCANNING.." if autoscan_active else radio.rt
        self.oled.text(self._get_visible_rt(rt_raw), RT_X, 6)

        # Row 2: frequency and station name
        self.oled.text(f"{radio.frequency:5.1f}", 0, 28)
        if radio.seeking:
            rds_raw = "SEEKING.."
        elif radio.ps:
            rds_raw = radio.ps
        else:
            rds_raw = "NO RDS"
        self.oled.text(rds_raw, 50, 28)

        # Row 3: speaker icon and volume
        self._draw_speaker_icon(4, 48, muted=(radio.volume == 0))
        bar_x, bar_y, bar_w, bar_h = 50, 50, 48, 8
        self.oled.rect(bar_x, bar_y, bar_w, bar_h, 1)
        fill_w = int((bar_w - 4) * radio.volume / VOL_MAX)
        if fill_w > 0:
            self.oled.fill_rect(bar_x + 2, bar_y + 2, fill_w, bar_h - 4, 1)
        self.oled.text(f"{radio.volume:>2}", 104, 50)
        if holding_volume:
            self.oled.hline(104, 59, 16, 1)

        self.oled.show()


def main():
    """Run the radio application loop."""
    global encoder_rotated

    print("Initializing FM Radio Receiver...")

    radio = FmTuner(
        i2c_id=RADIO_I2C_ID,
        sda=PIN_RADIO_SDA,
        scl=PIN_RADIO_SCL,
        rst=PIN_RADIO_RST,
        freq=RADIO_I2C_FREQ,
    )
    start_mhz = DEFAULT_FREQ_SCALED / 10.0
    radio.start(volume=DEFAULT_VOLUME, frequency=start_mhz)

    if OLED_SHARED_I2C:
        oled_i2c = radio.i2c
    else:
        oled_i2c = I2C(
            OLED_I2C_ID,
            sda=Pin(PIN_OLED_SDA),
            scl=Pin(PIN_OLED_SCL),
            freq=OLED_I2C_FREQ,
        )
    oled = SH1106_I2C(oled_i2c)
    ui = RadioUI(oled)

    encoder = RotaryIRQ(
        pin_num_clk=PIN_ENC_CLK,
        pin_num_dt=PIN_ENC_DT,
        min_val=FM_MIN_SCALED,
        max_val=FM_MAX_SCALED,
        incr=1,
        reverse=True,
        range_mode=RotaryIRQ.RANGE_WRAP,
        pull_up=True,
    )
    encoder.set(value=DEFAULT_FREQ_SCALED)
    encoder.add_listener(on_encoder_change)

    button = MultiFunctionButton(PIN_ENC_SW)

    was_holding = False
    manual_seek_active = False

    autoscan_active = False
    autoscan_stage = "IDLE"  # IDLE, SEEKING or WAIT_RDS
    autoscan_rds_t0 = 0
    autoscan_pre_freq = start_mhz
    scanned_freqs = []

    print(f"System ready. Tuned to {radio.frequency:.1f} MHz.")

    try:
        while True:
            btn_event = button.update()

            # Switch encoder between frequency and volume
            if button.is_holding and not was_holding:
                was_holding = True
                encoder_rotated = False
                encoder.set(
                    value=radio.volume,
                    min_val=VOL_MIN,
                    max_val=VOL_MAX,
                    range_mode=RotaryIRQ.RANGE_BOUNDED,
                )
            elif not button.is_holding and was_holding:
                was_holding = False
                encoder_rotated = False
                current_scaled = min(
                    max(round(radio.frequency * 10), FM_MIN_SCALED),
                    FM_MAX_SCALED,
                )
                encoder.set(
                    value=current_scaled,
                    min_val=FM_MIN_SCALED,
                    max_val=FM_MAX_SCALED,
                    range_mode=RotaryIRQ.RANGE_WRAP,
                )

            # Single click: seek next station
            if btn_event == MultiFunctionButton.EVENT_SINGLE_CLICK:
                if not autoscan_active and not radio.seeking:
                    print("[SEEK] Searching for next strong station...")
                    radio.seek_start(up=True)
                    manual_seek_active = True

            # Double click: start or stop auto-scan
            elif btn_event == MultiFunctionButton.EVENT_DOUBLE_CLICK:
                autoscan_active = not autoscan_active
                if autoscan_active:
                    autoscan_pre_freq = radio.frequency
                    scanned_freqs.clear()
                    print("\nStarting Auto-Scan (88.0 - 108.0 MHz)...")
                    print("+------+-------------+----------+")
                    print("| RSSI |  Frequency  | RDS      |")
                    print("+------+-------------+----------+")
                    radio.tune(FM_MIN_SCALED / 10.0)
                    radio.seek_start(up=True)
                    autoscan_stage = "SEEKING"
                else:
                    print("+------+-------------+----------+")
                    print("[AUTOSCAN] Stopped by user.")
                    autoscan_stage = "IDLE"
                    radio.tune(autoscan_pre_freq)
                    encoder.set(value=round(radio.frequency * 10))

            # Encoder rotation
            if encoder_rotated:
                encoder_rotated = False
                val = encoder.value()

                if button.is_holding:
                    radio.set_volume(val)
                    radio.mute(val == 0)
                elif not autoscan_active and not radio.seeking:
                    radio.tune(val / 10.0)

            # Manual seek progress
            if manual_seek_active:
                if radio.seek_update():
                    manual_seek_active = False
                    if radio.seek_failed:
                        print("[SEEK] No station found.")
                    else:
                        # Hardware wraps to 87.5 MHz
                        if radio.frequency < (FM_MIN_SCALED / 10.0):
                            radio.tune(FM_MIN_SCALED / 10.0)
                        print(f"[SEEK] Tuned to {radio.frequency:.1f} MHz (RSSI: {radio.rssi})")
                    encoder.set(value=round(radio.frequency * 10))

            # Auto-scan state machine
            if autoscan_active:
                if autoscan_stage == "SEEKING":
                    if radio.seek_update():
                        freq = radio.frequency
                        # Stop on failure or repeated station
                        if radio.seek_failed or freq in scanned_freqs or freq < (FM_MIN_SCALED / 10.0):
                            print("+------+-------------+----------+")
                            print(f"[AUTOSCAN] Completed. Found {len(scanned_freqs)} stations.")
                            autoscan_active = False
                            autoscan_stage = "IDLE"
                            radio.tune(autoscan_pre_freq)
                            encoder.set(value=round(radio.frequency * 10))
                        else:
                            scanned_freqs.append(freq)
                            autoscan_stage = "WAIT_RDS"
                            autoscan_rds_t0 = time.ticks_ms()

                elif autoscan_stage == "WAIT_RDS":
                    radio.poll()
                    elapsed = time.ticks_diff(time.ticks_ms(), autoscan_rds_t0)
                    # Log when PS is decoded or time is up
                    if radio.ps or elapsed >= AUTOSCAN_RDS_WAIT_MS:
                        rds_str = radio.ps if radio.ps else "---"
                        print(f"| {radio.rssi:>4} | {radio.frequency:>7.1f} MHz | {rds_str:<8} |")
                        radio.seek_start(up=True)
                        autoscan_stage = "SEEKING"
            else:
                radio.poll()

            ui.render(
                radio=radio,
                autoscan_active=autoscan_active,
                holding_volume=button.is_holding,
            )

            time.sleep_ms(LOOP_DELAY_MS)

    except KeyboardInterrupt:
        print("\nShutting down...")
        encoder.remove_listener(on_encoder_change)
        encoder.close()
        oled.poweroff()
        radio.power_off()
        print("Hardware safely powered down.")


if __name__ == "__main__":
    main()
