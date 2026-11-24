"""
Multi-Function Button Handler Module.

Extends :class:`gpio_devices.Button` with non-blocking software debouncing
and gesture recognition for single click, double click, and press-and-hold.
"""

import time
from gpio_devices import Button


class MultiFunctionButton(Button):
    """
    Button controller supporting single click, double click, and hold events.

    Inherits active-low GPIO handling from :class:`gpio_devices.Button`.
    """

    EVENT_NONE = 0
    EVENT_SINGLE_CLICK = 1
    EVENT_DOUBLE_CLICK = 2
    EVENT_HOLD = 3

    def __init__(self, pin_number, debounce_ms=15, double_click_ms=400, hold_threshold_ms=600):
        """
        Initialize the multi-function button state machine.

        :param int pin_number: GPIO pin connected to the button.
        :param int debounce_ms: Software debounce interval in milliseconds.
        :param int double_click_ms: Max gap between two clicks in milliseconds.
        :param int hold_threshold_ms: Press duration to trigger hold in milliseconds.
        """
        super().__init__(pin_number)
        self._debounce_ms = debounce_ms
        self._double_click_ms = double_click_ms
        self._hold_threshold_ms = hold_threshold_ms

        self._last_raw = self.is_pressed()
        self._stable_pressed = self._last_raw
        self._last_debounce_ms = time.ticks_ms()
        self._press_start_ms = 0
        self._last_release_ms = 0
        self._click_count = 0
        self._hold_fired = False

    def update(self):
        """
        Poll the button and resolve the latest user gesture.

        Should be called frequently (every 5-10 ms) inside the main superloop
        so rapid double clicks are captured reliably.

        :return: One of ``EVENT_NONE``, ``EVENT_SINGLE_CLICK``,
                 ``EVENT_DOUBLE_CLICK``, or ``EVENT_HOLD``.
        :rtype: int
        """
        now = time.ticks_ms()
        raw_pressed = self.is_pressed()
        event = self.EVENT_NONE

        if raw_pressed != self._last_raw:
            self._last_raw = raw_pressed
            self._last_debounce_ms = now

        if time.ticks_diff(now, self._last_debounce_ms) >= self._debounce_ms:
            if raw_pressed != self._stable_pressed:
                self._stable_pressed = raw_pressed

                if self._stable_pressed:
                    self._press_start_ms = now
                    self._hold_fired = False
                elif self._hold_fired:
                    # Ignore release after a hold gesture
                    self._hold_fired = False
                    self._click_count = 0
                else:
                    self._click_count += 1
                    self._last_release_ms = now
                    if self._click_count == 2:
                        self._click_count = 0
                        event = self.EVENT_DOUBLE_CLICK

        # Trigger hold once when threshold is crossed
        if self._stable_pressed and not self._hold_fired:
            if time.ticks_diff(now, self._press_start_ms) >= self._hold_threshold_ms:
                self._hold_fired = True
                self._click_count = 0
                event = self.EVENT_HOLD

        # Confirm single click after double-click window expires
        if (self._click_count == 1 and not self._stable_pressed
                and time.ticks_diff(now, self._last_release_ms) >= self._double_click_ms):
            self._click_count = 0
            event = self.EVENT_SINGLE_CLICK

        return event