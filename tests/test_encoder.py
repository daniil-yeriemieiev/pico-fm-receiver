"""
Encoder and Button Integration Test Module

This script verifies the functionality of the EC11 rotary encoder and its 
integrated SW button on the Raspberry Pi Pico W. It uses hardware interrupts 
for the encoder and a polling-based software debounce for the button via the 
gpio_devices.Button class. Pressing the button cycles the encoder's range mode 
through WRAP, BOUNDED, and UNBOUNDED states, handling out-of-bounds resets.
"""

import time
from rotary_irq_rp2 import RotaryIRQ
from gpio_devices import Button

# Hardware configuration constants
PIN_CLK = 14
PIN_DT = 15
PIN_SW = 16

MIN_VAL = 0
MAX_VAL = 10

# Global flag for communication between IRQ context and the main loop
encoder_needs_update = False

def on_encoder_change():
    """Ultra-lightweight callback for encoder rotation."""
    global encoder_needs_update
    encoder_needs_update = True

def main():
    global encoder_needs_update
    
    print("Initializing EC11 encoder and button...")
    
    # Modes configuration list for cycling
    modes = [RotaryIRQ.RANGE_WRAP, RotaryIRQ.RANGE_BOUNDED, RotaryIRQ.RANGE_UNBOUNDED]
    mode_names = ["WRAP (0-10 loop)", "BOUNDED (0-10 limits)", "UNBOUNDED (No limits)"]
    current_mode_idx = 0  # Start with WRAP
    
    # Initialize the encoder (CLK and DT) via IRQ
    encoder = RotaryIRQ(
        pin_num_clk=PIN_CLK, 
        pin_num_dt=PIN_DT, 
        min_val=MIN_VAL, 
        max_val=MAX_VAL, 
        reverse=False, 
        range_mode=modes[current_mode_idx],
        pull_up=True 
    )
    encoder.add_listener(on_encoder_change)
    
    # Initialize the button (SW) using the gpio_devices module
    button = Button(PIN_SW)
    
    print("Hardware is ready.")
    print(f"Current mode: {mode_names[current_mode_idx]}")
    print("Turn the knob to change values. Press the SW button to cycle modes.")
    print("Press Ctrl+C to exit.")
    
    try:
        while True:
            # 1. Handle encoder rotation (Event-driven via IRQ flag)
            if encoder_needs_update:
                encoder_needs_update = False
                print(f"Rotation! Current value: {encoder.value()}")
                
            # 2. Handle button press (Polling with software debounce)
            if button.was_pressed():
                # Cycle to the next mode index
                current_mode_idx = (current_mode_idx + 1) % len(modes)
                new_mode = modes[current_mode_idx]
                new_mode_name = mode_names[current_mode_idx]
                
                print(f"Button pressed! Switching to {new_mode_name}.")
                
                # Protect against out-of-bounds jumping when switching back to limited modes
                current_val = encoder.value()
                if new_mode != RotaryIRQ.RANGE_UNBOUNDED and (current_val < MIN_VAL or current_val > MAX_VAL):
                    print(f"--> Value {current_val} is out of bounds! Resetting to minimum ({MIN_VAL}).")
                    # set() can update both the value and the mode in one atomic operation
                    encoder.set(value=MIN_VAL, range_mode=new_mode)
                else:
                    encoder.set(range_mode=new_mode)
                    
                print(f"Current value: {encoder.value()}")
                    
            # Main loop sleeps to free up CPU (also acts as polling interval for the button)
            time.sleep(0.05) 
            
    except KeyboardInterrupt:
        # Clean up resources on exit
        print("\nStopping the test...")
        encoder.remove_listener(on_encoder_change)
        encoder.close()
        print("Pins released, interrupts disabled. Program terminated.")

if __name__ == "__main__":
    main()