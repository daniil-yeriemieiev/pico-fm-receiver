# MIT License (MIT)
# Copyright (c) 2020 Mike Teachman
# Copyright (c) 2021 Eric Moyer
# https://opensource.org/licenses/MIT

# Platform-specific MicroPython code for the rotary encoder module
# Raspberry Pi Pico implementation
# Annotated for Sphinx documentation by project team

"""
Platform-specific MicroPython code for the rotary encoder module.
This module provides the hardware-specific implementation for the Raspberry Pi Pico (RP2040)
using hardware interrupts (IRQ).
"""

from machine import Pin # type: ignore
from rotary import Rotary

IRQ_RISING_FALLING = Pin.IRQ_RISING | Pin.IRQ_FALLING


class RotaryIRQ(Rotary):
    """
    Rotary Encoder class for Raspberry Pi Pico using hardware interrupts.
    Inherits from the platform-independent Rotary class.
    """

    def __init__(
        self,
        pin_num_clk,
        pin_num_dt,
        min_val=0,
        max_val=10,
        incr=1,
        reverse=False,
        range_mode=Rotary.RANGE_UNBOUNDED,
        pull_up=False,
        half_step=False,
        invert=False
    ):
        """
        Initialize the hardware-specific rotary encoder.

        :param int pin_num_clk: GPIO pin connected to encoder CLK pin.
        :param int pin_num_dt: GPIO pin connected to encoder DT pin.
        :param int min_val: Minimum value in the encoder range. Also the starting value. Default is 0.
        :param int max_val: Maximum value in the encoder range (not used when range_mode = RANGE_UNBOUNDED). Default is 10.
        :param int incr: Amount count changes with each encoder click. Default is 1.
        :param bool reverse: Reverse count direction. Default is False.
        :param int range_mode: Count behavior at min_val and max_val. 
                               Options: Rotary.RANGE_UNBOUNDED (default), Rotary.RANGE_WRAP, Rotary.RANGE_BOUNDED.
        :param bool pull_up: Enable internal pull-up resistors. Use when rotary encoder hardware lacks them. Default is False.
        :param bool half_step: Enable half-step mode. Default is False.
        :param bool invert: Invert the CLK and DT signals. Use when encoder resting value is CLK, DT = 00. Default is False.
        """
        super().__init__(min_val, max_val, incr, reverse, range_mode, half_step, invert)

        if pull_up:
            self._pin_clk = Pin(pin_num_clk, Pin.IN, Pin.PULL_UP)
            self._pin_dt = Pin(pin_num_dt, Pin.IN, Pin.PULL_UP)
        else:
            self._pin_clk = Pin(pin_num_clk, Pin.IN)
            self._pin_dt = Pin(pin_num_dt, Pin.IN)

        self._hal_enable_irq()

    def _enable_clk_irq(self):
        """Enable hardware interrupt for the CLK pin."""
        self._pin_clk.irq(self._process_rotary_pins, IRQ_RISING_FALLING)

    def _enable_dt_irq(self):
        """Enable hardware interrupt for the DT pin."""
        self._pin_dt.irq(self._process_rotary_pins, IRQ_RISING_FALLING)

    def _disable_clk_irq(self):
        """Disable hardware interrupt for the CLK pin."""
        self._pin_clk.irq(None, 0)

    def _disable_dt_irq(self):
        """Disable hardware interrupt for the DT pin."""
        self._pin_dt.irq(None, 0)

    def _hal_get_clk_value(self):
        """
        Get the current digital value of the CLK pin.
        
        :return: 1 if pin is HIGH, 0 if LOW.
        :rtype: int
        """
        return self._pin_clk.value()

    def _hal_get_dt_value(self):
        """
        Get the current digital value of the DT pin.
        
        :return: 1 if pin is HIGH, 0 if LOW.
        :rtype: int
        """
        return self._pin_dt.value()

    def _hal_enable_irq(self):
        """Enable interrupts for both CLK and DT pins."""
        self._enable_clk_irq()
        self._enable_dt_irq()

    def _hal_disable_irq(self):
        """Disable interrupts for both CLK and DT pins."""
        self._disable_clk_irq()
        self._disable_dt_irq()

    def _hal_close(self):
        """Deactivate microcontroller pins used to read encoder."""
        self._hal_disable_irq()