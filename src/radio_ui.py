"""
OLED Graphical User Interface Module for the SH1106 Display.

Provides two display views for the 128x64 monochrome OLED:
    1. **Normal Mode (3x3 Grid):** Dynamic RSSI icon + value, RDS station name (PS),
       active frequency, scrolling RDS RadioText (RT), dynamic speaker icon, and
       volume slider with active control mode underline.
    2. **Auto-Scan Menu Mode:** Full-screen scrollable station table
       (``RSSI | FREQ | RDS``) with inverted-color selection highlight.
"""

import time


class RadioUI:
    """
    Display renderer for the SH1106 128x64 OLED screen.
    """

    MODE_FREQ = 0
    MODE_VOL = 1

    def __init__(self, oled, vol_max=15, rt_scroll_ms=250, rt_window_chars=10):
        """
        Initialize the OLED user interface manager.

        :param SH1106_I2C oled: Initialized SH1106 display driver instance.
        :param int vol_max: Maximum audio volume level.
        :param int rt_scroll_ms: Scroll step interval for RadioText in ms.
        :param int rt_window_chars: Visible character width of the RadioText window.
        """
        self.oled = oled
        self._vol_max = vol_max
        self._rt_scroll_ms = rt_scroll_ms
        self._rt_window_chars = rt_window_chars

        self._scroll_pos = 0
        self._last_scroll_ms = time.ticks_ms()
        self._last_rt_text = ""
        self._menu_top = 0

    def _draw_rssi_icon(self, x, y, rssi):
        """
        Draw a dynamic signal strength icon whose bar count scales with RSSI.

        :param int x: Left X coordinate.
        :param int y: Top Y coordinate.
        :param int rssi: Current RSSI reading from the tuner.
        """
        # x_off, y_off, width, height, minimum RSSI
        bars = [
            (0, 8, 2, 3, 5),
            (3, 6, 2, 5, 15),
            (6, 3, 2, 8, 25),
            (9, 0, 2, 11, 38),
        ]
        for bx, by, bw, bh, threshold in bars:
            if rssi >= threshold:
                self.oled.fill_rect(x + bx, y + by, bw, bh, 1)

    def _draw_speaker_icon(self, x, y, volume):
        """
        Draw a dynamic speaker icon whose wave count scales with volume.

        Draws a crossed-out icon when volume is 0, and 1 to 3 sound waves
        for low, medium, and high volume levels.

        :param int x: Left X coordinate.
        :param int y: Top Y coordinate.
        :param int volume: Current audio volume level (0 to ``vol_max``).
        """
        # Speaker body and cone
        self.oled.fill_rect(x, y + 3, 3, 6, 1)
        self.oled.vline(x + 3, y + 2, 8, 1)
        self.oled.vline(x + 4, y + 1, 10, 1)
        self.oled.vline(x + 5, y, 12, 1)

        if volume == 0:
            self.oled.line(x + 8, y + 3, x + 13, y + 8, 1)
            self.oled.line(x + 8, y + 8, x + 13, y + 3, 1)
        else:
            if volume >= 1:
                self.oled.vline(x + 8, y + 4, 4, 1)
            if volume >= 6:
                self.oled.vline(x + 11, y + 2, 8, 1)
            if volume >= 11:
                self.oled.vline(x + 14, y, 12, 1)

    def _get_visible_rt(self, rt_text):
        """
        Compute the currently visible marquee slice of the RDS RadioText string.

        :param str rt_text: Full RadioText message.
        :return: Substring fitting within ``_rt_window_chars``.
        :rtype: str
        """
        if rt_text != self._last_rt_text:
            self._last_rt_text = rt_text
            self._scroll_pos = 0
            self._last_scroll_ms = time.ticks_ms()

        if len(rt_text) <= self._rt_window_chars:
            return rt_text

        now = time.ticks_ms()
        padded = rt_text + "   "
        if time.ticks_diff(now, self._last_scroll_ms) >= self._rt_scroll_ms:
            self._last_scroll_ms = now
            self._scroll_pos = (self._scroll_pos + 1) % len(padded)

        doubled = padded + padded
        return doubled[self._scroll_pos:self._scroll_pos + self._rt_window_chars]

    def render_normal(self, radio, display_freq, control_mode):
        """
        Render the normal radio screen on a 3x3 logical grid.

        Layout:
            - **1.1**: Dynamic RSSI icon + numeric value.
            - **1.2-1.3**: Station name (RDS PS) or seek status.
            - **2.1**: Active frequency (underlined in frequency mode).
            - **2.2-2.3**: Scrolling RDS RadioText (RT).
            - **3.1**: Dynamic speaker / mute icon.
            - **3.2-3.3**: Volume bar + value (underlined in volume mode).

        :param FmTuner radio: Active FM tuner instance.
        :param float display_freq: Frequency in MHz to display (supports pending tune).
        :param int control_mode: Active encoder target (``MODE_FREQ`` or ``MODE_VOL``).
        """
        self.oled.fill(0)

        # Row 1: dynamic RSSI and station name (RDS PS)
        self._draw_rssi_icon(2, 4, radio.rssi)
        self.oled.text(f"{radio.rssi:>2}", 18, 6)
        if radio.seeking:
            ps_text = "SEEKING.."
        elif radio.ps:
            ps_text = radio.ps
        else:
            ps_text = "NO RDS"
        self.oled.text(ps_text, 44, 6)

        # Row 2: frequency and scrolling RadioText (RDS RT)
        self.oled.text(f"{display_freq:5.1f}", 0, 28)
        if control_mode == self.MODE_FREQ:
            self.oled.hline(0, 37, 40, 1)
        rt_text = "" if radio.seeking else radio.rt
        self.oled.text(self._get_visible_rt(rt_text), 44, 28)

        # Row 3: dynamic speaker icon and volume bar
        self._draw_speaker_icon(2, 48, radio.volume)
        bar_x, bar_y, bar_w, bar_h = 44, 50, 56, 8
        self.oled.rect(bar_x, bar_y, bar_w, bar_h, 1)
        fill_w = int((bar_w - 4) * radio.volume / self._vol_max)
        if fill_w > 0:
            self.oled.fill_rect(bar_x + 2, bar_y + 2, fill_w, bar_h - 4, 1)
        self.oled.text(f"{radio.volume:>2}", 106, 50)
        if control_mode == self.MODE_VOL:
            self.oled.hline(106, 59, 16, 1)

        self.oled.show()

    def render_scan_menu(self, stations, selected_idx, scanning, scan_freq):
        """
        Render the full-screen Auto-Scan station table on the OLED display.

        Displays up to 5 stations at a time in ``RSSI | FREQ | RDS`` columns
        with an inverted highlight bar on the currently selected entry.

        :param list stations: List of ``(rssi, frequency, rds)`` tuples.
        :param int selected_idx: Currently highlighted index in ``stations``.
        :param bool scanning: True while band auto-scan is actively running.
        :param float scan_freq: Current tuner frequency shown during active scan.
        """
        self.oled.fill(0)

        # Header row
        if scanning:
            self.oled.text(f"SCAN {scan_freq:5.1f} [{len(stations)}]", 0, 1)
        else:
            self.oled.text("RS", 0, 1)
            self.oled.text("FREQ", 19, 1)
            self.oled.text("RDS", 63, 1)
            if stations:
                pos_str = f"{selected_idx + 1}/{len(stations)}"
                self.oled.text(pos_str, 128 - len(pos_str) * 8, 1)
        self.oled.hline(0, 10, 128, 1)

        # Empty state
        if not stations:
            if scanning:
                self.oled.text("Searching...", 16, 30)
            else:
                self.oled.text("No stations", 20, 22)
                self.oled.text("Click: Scan", 20, 36)
                self.oled.text("2xClick: Back", 12, 50)
            self.oled.show()
            return

        # Keep selected row inside the 5-row viewport
        visible_rows = 5
        if selected_idx < self._menu_top:
            self._menu_top = selected_idx
        elif selected_idx >= self._menu_top + visible_rows:
            self._menu_top = selected_idx - visible_rows + 1

        for row_i in range(visible_rows):
            idx = self._menu_top + row_i
            if idx >= len(stations):
                break
            rssi, freq, rds = stations[idx]
            y = 13 + row_i * 10
            if idx == selected_idx:
                self.oled.fill_rect(0, y - 1, 128, 10, 1)
                fg = 0
            else:
                fg = 1
            self.oled.text(f"{rssi:>2}", 0, y, fg)
            self.oled.text(f"{freq:5.1f}", 19, y, fg)
            self.oled.text(rds[:8], 63, y, fg)

        self.oled.show()