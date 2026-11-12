# MIT License (MIT)
# Copyright (c) 2022 Mike Teachman
# https://opensource.org/licenses/MIT

# Platform-independent MicroPython code for the rotary encoder module
# Annotated for Sphinx documentation by project team

"""
Platform-independent MicroPython code for the rotary encoder module.
This module contains the core state machine logic for debouncing and tracking
quadrature encoder signals.
"""

import micropython # type: ignore
from micropython import const # type: ignore

_DIR_CW = const(0x10)  # Clockwise step
_DIR_CCW = const(0x20)  # Counter-clockwise step

# Rotary Encoder States
_R_START = const(0x0)
_R_CW_1 = const(0x1)
_R_CW_2 = const(0x2)
_R_CW_3 = const(0x3)
_R_CCW_1 = const(0x4)
_R_CCW_2 = const(0x5)
_R_CCW_3 = const(0x6)
_R_ILLEGAL = const(0x7)

_transition_table = [
    # |------------- NEXT STATE -------------|            |CURRENT STATE|
    # CLK/DT    CLK/DT     CLK/DT    CLK/DT
    #   00        01         10        11
    [_R_START, _R_CCW_1, _R_CW_1,  _R_START],             # _R_START
    [_R_CW_2,  _R_START, _R_CW_1,  _R_START],             # _R_CW_1
    [_R_CW_2,  _R_CW_3,  _R_CW_1,  _R_START],             # _R_CW_2
    [_R_CW_2,  _R_CW_3,  _R_START, _R_START | _DIR_CW],   # _R_CW_3
    [_R_CCW_2, _R_CCW_1, _R_START, _R_START],             # _R_CCW_1
    [_R_CCW_2, _R_CCW_1, _R_CCW_3, _R_START],             # _R_CCW_2
    [_R_CCW_2, _R_START, _R_CCW_3, _R_START | _DIR_CCW],  # _R_CCW_3
    [_R_START, _R_START, _R_START, _R_START]]             # _R_ILLEGAL

_transition_table_half_step = [
    [_R_CW_3,            _R_CW_2,  _R_CW_1,  _R_START],
    [_R_CW_3 | _DIR_CCW, _R_START, _R_CW_1,  _R_START],
    [_R_CW_3 | _DIR_CW,  _R_CW_2,  _R_START, _R_START],
    [_R_CW_3,            _R_CCW_2, _R_CCW_1, _R_START],
    [_R_CW_3,            _R_CW_2,  _R_CCW_1, _R_START | _DIR_CW],
    [_R_CW_3,            _R_CCW_2, _R_CW_3,  _R_START | _DIR_CCW],
    [_R_START,           _R_START, _R_START, _R_START],
    [_R_START,           _R_START, _R_START, _R_START]]

_STATE_MASK = const(0x07)
_DIR_MASK = const(0x30)


def _wrap(value, incr, lower_bound, upper_bound):
    """Internal helper to calculate wrapped values for RANGE_WRAP mode."""
    range = upper_bound - lower_bound + 1
    value = value + incr

    if value < lower_bound:
        value += range * ((lower_bound - value) // range + 1)

    return lower_bound + (value - lower_bound) % range


def _bound(value, incr, lower_bound, upper_bound):
    """Internal helper to calculate bounded values for RANGE_BOUNDED mode."""
    return min(upper_bound, max(lower_bound, value + incr))


def _trigger(rotary_instance):
    """Internal helper to trigger all registered callback functions."""
    for listener in rotary_instance._listener:
        listener()


class Rotary:
    """
    Platform-independent base class for the rotary encoder module.
    Handles state machine transitions, debouncing, and value calculation.
    """

    RANGE_UNBOUNDED = const(1)
    """Encoder has no bounds on the counting range."""
    
    RANGE_WRAP = const(2)
    """Encoder will count up to max_val then wrap to minimum value."""
    
    RANGE_BOUNDED = const(3)
    """Encoder will count up to max_val then stop."""

    def __init__(self, min_val, max_val, incr, reverse, range_mode, half_step, invert):
        """
        Initialize the rotary encoder logical state.
        
        :param int min_val: Minimum value in the encoder range.
        :param int max_val: Maximum value in the encoder range.
        :param int incr: Amount count changes with each step.
        :param bool reverse: Reverse the counting direction.
        :param int range_mode: Logic for handling boundaries (UNBOUNDED, WRAP, or BOUNDED).
        :param bool half_step: Enable half-step decoding logic.
        :param bool invert: Invert logic for CLK and DT signals.
        """
        self._min_val = min_val
        self._max_val = max_val
        self._incr = incr
        self._reverse = -1 if reverse else 1
        self._range_mode = range_mode
        self._value = min_val
        self._state = _R_START
        self._half_step = half_step
        self._invert = invert
        self._listener = []

    def set(self, value=None, min_val=None, max_val=None, incr=None, reverse=None, range_mode=None):
        """
        Set encoder value and internal configuration parameters.
        `None` indicates no change to the specific configuration parameter.

        Examples:
            - `set(min_val=0, max_val=59)`: Change encoder bounds (useful for minutes).
            - `set(value=6)`: Change encoder value to 6.

        :param int value: New value for the encoder.
        :param int min_val: New minimum boundary.
        :param int max_val: New maximum boundary.
        :param int incr: New increment step.
        :param bool reverse: New reverse flag.
        :param int range_mode: New range mode (UNBOUNDED, WRAP, BOUNDED).
        """
        # disable DT and CLK pin interrupts
        self._hal_disable_irq()

        if value is not None:
            self._value = value
        if min_val is not None:
            self._min_val = min_val
        if max_val is not None:
            self._max_val = max_val
        if incr is not None:
            self._incr = incr
        if reverse is not None:
            self._reverse = -1 if reverse else 1
        if range_mode is not None:
            self._range_mode = range_mode
        self._state = _R_START

        # enable DT and CLK pin interrupts
        self._hal_enable_irq()

    def value(self):
        """
        Return the current encoder value.

        :return: Current integer count of the encoder.
        :rtype: int
        """
        return self._value

    def reset(self):
        """
        Set encoder value to `min_val`.
        (Redundant with the addition of the `set()` method. Retained for backwards compatibility).
        """
        self._value = self._min_val

    def close(self):
        """Deactivate microcontroller pins used to read encoder."""
        self._hal_close()

    def add_listener(self, l):
        """
        Add a callback function that will be called on each change of encoder count.

        :param callable l: Callback function to execute.
        """
        self._listener.append(l)

    def remove_listener(self, l):
        """
        Remove a previously added callback function.

        :param callable l: Callback function to remove.
        :raises ValueError: If the listener is not currently installed.
        """
        if l not in self._listener:
            raise ValueError('{} is not an installed listener'.format(l))
        self._listener.remove(l)
        
    def _process_rotary_pins(self, pin):
        """Internal callback invoked by hardware interrupts to process pin state changes."""
        old_value = self._value
        clk_dt_pins = (self._hal_get_clk_value() <<
                       1) | self._hal_get_dt_value()
                       
        if self._invert:
            clk_dt_pins = ~clk_dt_pins & 0x03
            
        # Determine next state
        if self._half_step:
            self._state = _transition_table_half_step[self._state &
                                                      _STATE_MASK][clk_dt_pins]
        else:
            self._state = _transition_table[self._state &
                                            _STATE_MASK][clk_dt_pins]
        direction = self._state & _DIR_MASK

        incr = 0
        if direction == _DIR_CW:
            incr = self._incr
        elif direction == _DIR_CCW:
            incr = -self._incr

        incr *= self._reverse

        if self._range_mode == self.RANGE_WRAP:
            self._value = _wrap(
                self._value,
                incr,
                self._min_val,
                self._max_val)
        elif self._range_mode == self.RANGE_BOUNDED:
            self._value = _bound(
                self._value,
                incr,
                self._min_val,
                self._max_val)
        else:
            self._value = self._value + incr

        try:
            if old_value != self._value and len(self._listener) != 0:
                _trigger(self)
        except:
            pass