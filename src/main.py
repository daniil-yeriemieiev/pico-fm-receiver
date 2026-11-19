"""
Main Application Module for the Pico W FM Radio Receiver.

This module integrates the Si4703 FM tuner, SH1106 OLED display, and EC11
rotary encoder with pushbutton into a non-blocking superloop architecture.

Features:
    - Manual frequency tuning (88.0 to 108.0 MHz) via rotary encoder rotation.
    - Single click: automatic seek to the next strong station.
    - Double click: start/stop non-blocking band auto-scan with terminal table output.
    - Hold + rotate: adjust audio volume (0 to 15).
    - 9-zone OLED UI displaying RSSI icon/value, frequency, speaker/mute icon,
      auto-scan state, scrolling RDS text, and volume slider.
"""

import time
from machine import Pin, I2C  # type: ignore

from fm_tuner import FmTuner
from sh1106 import SH1106_I2C
from rotary_irq_rp2 import RotaryIRQ
from gpio_devices import Button

# ============================================================================
# HARDWARE PIN & BUS CONSTANTS
# ============================================================================
# I2C configuration for FM Tuner (Si4703)
RADIO_I2C_ID = 1
PIN_RADIO_SDA = 26
PIN_RADIO_SCL = 27
PIN_RADIO_RST = 16
RADIO_I2C_FREQ = 400_000

# I2C configuration for OLED Display (SH1106)
# Set OLED_SHARED_I2C = True if OLED is wired to the same I2C pins as the radio
OLED_SHARED_I2C = False
OLED_I2C_ID = 0
PIN_OLED_SDA = 4
PIN_OLED_SCL = 5
OLED_I2C_FREQ = 400_000

# Rotary Encoder (EC11) pins
PIN_ENC_CLK = 14
PIN_ENC_DT = 15
PIN_ENC_SW = 13

# ============================================================================
# RADIO & AUDIO CONSTANTS
# ============================================================================
FM_MIN_SCALED = 880        # 88.0 MHz (scaled by 10 for integer encoder)
FM_MAX_SCALED = 1080       # 108.0 MHz (scaled by 10 for integer encoder)
DEFAULT_FREQ_SCALED = 883  # 88.3 MHz initial frequency
VOL_MIN = 0
VOL_MAX = 15
DEFAULT_VOLUME = 10

# ============================================================================
# TIMING & UI CONSTANTS
# ============================================================================
LOOP_DELAY_MS = 20
DEBOUNCE_MS = 25
DOUBLE_CLICK_MS = 350      # Max interval between clicks for a double-click
HOLD_THRESHOLD_MS = 400    # Hold time required to enter volume adjustment mode

AUTOSCAN_RDS_WAIT_MS = 1800  # Max wait time per station to capture RDS during scan
RDS_SCROLL_MS = 250          # Marquee scroll step interval in ms
RDS_WINDOW_CHARS = 9         # Number of visible characters in zones 2.2-2.3

# ============================================================================
# GLOBAL IRQ FLAG
# ============================================================================
encoder_rotated = False


def on_encoder_change():
    """
    Lightweight hardware interrupt callback for rotary encoder rotation.

    Sets a global flag processed asynchronously inside the main superloop.
    """
    global encoder_rotated
    encoder_rotated = True


class MultiFunctionButton(Button):
    """
    Extended button handler supporting single click, double click, and hold states.

    Inherits low-level pin initialization and active-low checks from
    :class:`gpio_devices.Button`.
    """

    EVENT_NONE = 0
    EVENT_SINGLE_CLICK = 1
    EVENT_DOUBLE_CLICK = 2

    def __init__(self, pin_number):
        """
        Initialize the multi-function button controller.

        :param int pin_number: GPIO pin connected to the encoder SW button.
        """
        super().__init__(pin_number)
        self._last_raw = self.is_pressed()
        self._stable_pressed = self._last_raw
        self._last_debounce_ms = time.ticks_ms()
        self._press_start_ms = 0
        self._last_release_ms = 0
        self._click_count = 0
        self.is_holding = False

    def update(self):
        """
        Poll the button state and resolve multi-click or hold gestures.

        Must be called once per main loop iteration.

        :return: Resolved click event (``EVENT_NONE``, ``EVENT_SINGLE_CLICK``,
                 or ``EVENT_DOUBLE_CLICK``). Hold status is exposed via the
                 :attr:`is_holding` boolean attribute.
        :rtype: int
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
                    # Button just pressed down
                    self._press_start_ms = now
                else:
                    # Button just released
                    if self.is_holding:
                        self.is_holding = False
                        self._click_count = 0
                    else:
                        self._click_count += 1
                        self._last_release_ms = now
                        if self._click_count == 2:
                            self._click_count = 0
                            event = self.EVENT_DOUBLE_CLICK

        # Detect transition into hold state
        if self._stable_pressed and not self.is_holding:
            if time.ticks_diff(now, self._press_start_ms) >= HOLD_THRESHOLD_MS:
                self.is_holding = True
                self._click_count = 0

        # Confirm single click if double-click window expires
        if (self._click_count == 1 and not self._stable_pressed
                and time.ticks_diff(now, self._last_release_ms) >= DOUBLE_CLICK_MS):
            self._click_count = 0
            event = self.EVENT_SINGLE_CLICK

        return event


class RadioUI:
    """
    Graphical user interface manager for the 128x64 SH1106 OLED display.

    Divides the screen into a 3x3 logical grid:
        - **1.1**: RSSI signal icon + numeric value.
        - **1.2-1.3**: Auto-scan status indicator.
        - **2.1**: Active frequency in MHz.
        - **2.2-2.3**: Station RDS name (with scrolling marquee if needed).
        - **3.1**: Speaker icon (crossed out when muted / volume is 0).
        - **3.2-3.3**: Volume progress bar and numeric level.
    """

    def __init__(self, oled):
        """
        Initialize the UI manager.

        :param SH1106_I2C oled: Initialized SH1106 display driver instance.
        """
        self.oled = oled
        self._scroll_pos = 0
        self._last_scroll_ms = time.ticks_ms()
        self._last_rds_text = ""

    def _draw_rssi_icon(self, x, y, rssi):
        """
        Draw a 4-bar signal / RSSI strength icon at (x, y).

        :param int x: Left X coordinate.
        :param int y: Top Y coordinate.
        :param int rssi: Current RSSI value (0-75+ dBuV).
        """
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
        """
        Draw a speaker horn icon at (x, y), crossed out if volume is 0.

        :param int x: Left X coordinate.
        :param int y: Top Y coordinate.
        :param bool muted: True if volume is 0, drawing a mute 'X'.
        """
        # Speaker body and cone
        self.oled.fill_rect(x, y + 3, 3, 6, 1)
        self.oled.vline(x + 3, y + 2, 8, 1)
        self.oled.vline(x + 4, y + 1, 10, 1)
        self.oled.vline(x + 5, y, 12, 1)

        if muted:
            # Draw 'X' next to the speaker cone
            self.oled.line(x + 8, y + 3, x + 13, y + 8, 1)
            self.oled.line(x + 8, y + 8, x + 13, y + 3, 1)
        else:
            # Draw sound waves
            self.oled.vline(x + 8, y + 3, 6, 1)
            self.oled.vline(x + 11, y + 1, 10, 1)

    def _get_visible_rds(self, rds_text):
        """
        Compute the current substring for the RDS display area with scrolling.

        :param str rds_text: Full RDS text to display.
        :return: Substring of max length ``RDS_WINDOW_CHARS``.
        :rtype: str
        """
        if rds_text != self._last_rds_text:
            self._last_rds_text = rds_text
            self._scroll_pos = 0
            self._last_scroll_ms = time.ticks_ms()

        if len(rds_text) <= RDS_WINDOW_CHARS:
            return rds_text

        now = time.ticks_ms()
        padded = rds_text + "   "
        if time.ticks_diff(now, self._last_scroll_ms) >= RDS_SCROLL_MS:
            self._last_scroll_ms = now
            self._scroll_pos = (self._scroll_pos + 1) % len(padded)

        doubled = padded + padded
        return doubled[self._scroll_pos:self._scroll_pos + RDS_WINDOW_CHARS]

    def render(self, radio, autoscan_active, holding_volume):
        """
        Render all 9 grid zones to the OLED framebuffer and refresh the screen.

        :param FmTuner radio: Active FM tuner instance.
        :param bool autoscan_active: Whether background auto-scan is running.
        :param bool holding_volume: Whether user is holding button for volume.
        """
        self.oled.fill(0)

        # --- ROW 1 (Y: 0..19) ---
        # Zone 1.1: RSSI icon + numeric value
        self._draw_rssi_icon(2, 4, radio.rssi)
        self.oled.text(f"{radio.rssi:>2}", 18, 6)

        # Zone 1.2-1.3: Auto-scan state
        scan_str = "SCAN: ON" if autoscan_active else "SCAN:OFF"
        self.oled.text(scan_str, 50, 6)

        # --- ROW 2 (Y: 21..41) ---
        # Zone 2.1: Active Frequency
        self.oled.text(f"{radio.frequency:5.1f}", 0, 28)

        # Zone 2.2-2.3: RDS Station Name
        if radio.seeking:
            rds_raw = "SEEKING.."
        elif radio.ps:
            rds_raw = radio.ps
        else:
            rds_raw = "NO RDS"
        visible_rds = self._get_visible_rds(rds_raw)
        self.oled.text(visible_rds, 50, 28)

        # --- ROW 3 (Y: 43..63) ---
        # Zone 3.1: Speaker icon (crossed out if volume == 0)
        self._draw_speaker_icon(4, 48, muted=(radio.volume == 0))

        # Zone 3.2-3.3: Volume slider + numeric value
        bar_x, bar_y, bar_w, bar_h = 50, 50, 48, 8
        self.oled.rect(bar_x, bar_y, bar_w, bar_h, 1)
        fill_w = int((bar_w - 4) * radio.volume / VOL_MAX)
        if fill_w > 0:
            self.oled.fill_rect(bar_x + 2, bar_y + 2, fill_w, bar_h - 4, 1)

        vol_label = f"{radio.volume:>2}"
        self.oled.text(vol_label, 104, 50)
        if holding_volume:
            # Highlight volume number when in hold-to-adjust-volume mode
            self.oled.hline(104, 59, 16, 1)

        self.oled.show()


def main():
    """
    Main application entry point and non-blocking superloop.
    """
    global encoder_rotated

    print("Initializing FM Radio Receiver...")

    # 1. Initialize FM Tuner (also sets up its I2C bus during _hw_reset)
    radio = FmTuner(
        i2c_id=RADIO_I2C_ID,
        sda=PIN_RADIO_SDA,
        scl=PIN_RADIO_SCL,
        rst=PIN_RADIO_RST,
        freq=RADIO_I2C_FREQ,
    )
    start_mhz = DEFAULT_FREQ_SCALED / 10.0
    radio.start(volume=DEFAULT_VOLUME, frequency=start_mhz)

    # 2. Initialize OLED Display
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

    # 3. Initialize Rotary Encoder & Multi-Function Button
    encoder = RotaryIRQ(
        pin_num_clk=PIN_ENC_CLK,
        pin_num_dt=PIN_ENC_DT,
        min_val=FM_MIN_SCALED,
        max_val=FM_MAX_SCALED,
        incr=1,
        reverse=False,
        range_mode=RotaryIRQ.RANGE_WRAP,
        pull_up=True,
    )
    encoder.set(value=DEFAULT_FREQ_SCALED)
    encoder.add_listener(on_encoder_change)

    button = MultiFunctionButton(PIN_ENC_SW)

    # State tracking variables
    was_holding = False
    manual_seek_active = False

    # Auto-scan state machine variables
    autoscan_active = False
    autoscan_stage = "IDLE"  # "SEEKING" or "WAIT_RDS"
    autoscan_rds_t0 = 0
    autoscan_pre_freq = start_mhz
    scanned_freqs = []

    print(f"System ready. Tuned to {radio.frequency:.1f} MHz.")

    try:
        while True:
            # ----------------------------------------------------------------
            # 1. PROCESS BUTTON GESTURES
            # ----------------------------------------------------------------
            btn_event = button.update()

            # Detect transition into/out of Hold mode (Volume vs Frequency)
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

            # Single click: Seek to the next strong station
            if btn_event == MultiFunctionButton.EVENT_SINGLE_CLICK:
                if not autoscan_active and not radio.seeking:
                    print("[SEEK] Searching for next strong station...")
                    radio.seek_start(up=True)
                    manual_seek_active = True

            # Double click: Start / Stop Auto-Scan
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

            # ----------------------------------------------------------------
            # 2. PROCESS ENCODER ROTATION
            # ----------------------------------------------------------------
            if encoder_rotated:
                encoder_rotated = False
                val = encoder.value()

                if button.is_holding:
                    # Volume adjustment mode
                    radio.set_volume(val)
                    radio.mute(val == 0)
                else:
                    # Manual frequency tuning mode (cancels active scan/seek)
                    if not autoscan_active and not radio.seeking:
                        target_mhz = val / 10.0
                        radio.tune(target_mhz)

            # ----------------------------------------------------------------
            # 3. PROCESS SINGLE-CLICK HARDWARE SEEK
            # ----------------------------------------------------------------
            if manual_seek_active:
                if radio.seek_update():
                    manual_seek_active = False
                    if radio.seek_failed:
                        print("[SEEK] No station found.")
                    else:
                        # Clamp to 88.0 MHz if hardware wrapped to 87.5 MHz
                        if radio.frequency < (FM_MIN_SCALED / 10.0):
                            radio.tune(FM_MIN_SCALED / 10.0)
                        print(f"[SEEK] Tuned to {radio.frequency:.1f} MHz (RSSI: {radio.rssi})")
                    encoder.set(value=round(radio.frequency * 10))

            # ----------------------------------------------------------------
            # 4. PROCESS NON-BLOCKING AUTO-SCAN STATE MACHINE
            # ----------------------------------------------------------------
            if autoscan_active:
                if autoscan_stage == "SEEKING":
                    if radio.seek_update():
                        freq = radio.frequency
                        # Stop scan if seek failed or wrapped back to an already logged station
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
                    # Log as soon as RDS PS is decoded, or when timeout expires
                    if radio.ps or elapsed >= AUTOSCAN_RDS_WAIT_MS:
                        rds_str = radio.ps if radio.ps else "---"
                        print(f"| {radio.rssi:>4} | {radio.frequency:>7.1f} MHz | {rds_str:<8} |")
                        radio.seek_start(up=True)
                        autoscan_stage = "SEEKING"
            else:
                # Normal operation: poll radio for RDS and RSSI updates
                radio.poll()

            # ----------------------------------------------------------------
            # 5. UPDATE OLED DISPLAY
            # ----------------------------------------------------------------
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