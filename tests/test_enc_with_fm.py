"""
FM Tuner and Rotary Encoder Integration Test Module

This script verifies the combined functionality of the colleague's custom 
FmTuner driver (fm_tuner.py) and the EC11 rotary encoder (rotary_irq_rp2_2.py) 
on the Raspberry Pi Pico W, without using a display. The encoder values are 
mapped directly to the European FM band (87.5 MHz to 108.0 MHz, scaled by 10).
"""

import time
from rotary_irq_rp2_2 import RotaryIRQ
from fm_tuner import FmTuner

# Hardware configuration constants for Encoder
PIN_ENC_CLK = 14
PIN_ENC_DT = 15

# Hardware configuration constants for FmTuner (I2C and Reset pins)
I2C_ID = 0
PIN_I2C_SDA = 4
PIN_I2C_SCL = 5
PIN_RST = 12

# FM Band constraints scaled by 10 for integer encoder (87.5 MHz - 108.0 MHz)
FM_MIN_SCALED = 875
FM_MAX_SCALED = 1080
DEFAULT_FREQ_SCALED = 1014  # 101.4 MHz
DEFAULT_VOLUME = 10

# Global flag for communication between IRQ context and the main loop
encoder_needs_update = False

def on_encoder_change():
    """Ultra-lightweight callback for encoder rotation."""
    global encoder_needs_update
    encoder_needs_update = True

def main():
    global encoder_needs_update
    
    print("Initializing FM Tuner and Rotary Encoder...")
    
    # 1. Initialize colleague's FmTuner driver
    # FmTuner handles its own I2C instantiation internally via _hw_reset()
    radio = FmTuner(i2c_id=I2C_ID, sda=PIN_I2C_SDA, scl=PIN_I2C_SCL, rst=PIN_RST, freq=400000)
    
    start_freq_mhz = DEFAULT_FREQ_SCALED / 10.0
    print(f"Powering up radio and tuning to {start_freq_mhz:.1f} MHz...")
    radio.start(volume=DEFAULT_VOLUME, frequency=start_freq_mhz)
    
    # 2. Initialize EC11 Encoder mapped to FM band limits
    encoder = RotaryIRQ(
        pin_num_clk=PIN_ENC_CLK, 
        pin_num_dt=PIN_ENC_DT, 
        min_val=FM_MIN_SCALED, 
        max_val=FM_MAX_SCALED, 
        incr=1,
        reverse=False, 
        range_mode=RotaryIRQ.RANGE_WRAP,
        pull_up=True 
    )
    encoder.set(value=DEFAULT_FREQ_SCALED)
    encoder.add_listener(on_encoder_change)
    
    print("✅ Hardware is ready.")
    print(f"Current Frequency: {start_freq_mhz:.1f} MHz | Volume: {DEFAULT_VOLUME}/15")
    print("Turn the knob to tune the radio. Press Ctrl+C to exit.")
    
    try:
        while True:
            # Handle frequency changes triggered by encoder rotation
            if encoder_needs_update:
                encoder_needs_update = False
                
                # Read scaled integer from encoder and convert to MHz float
                scaled_val = encoder.value()
                target_mhz = scaled_val / 10.0
                
                print(f"Tuning to {target_mhz:.1f} MHz...")
                tuned_freq = radio.tune(target_mhz)
                
                if tuned_freq is not None:
                    print(f"--> Successfully tuned to {tuned_freq:.1f} MHz | RSSI: {radio.rssi} | Stereo: {radio.stereo}")
                else:
                    print("--> Tuning timeout or failed.")
                    
            # Periodic radio status polling (decodes RDS and updates RSSI/stereo)
            radio.poll()
            
            # Small delay to keep the superloop responsive and non-blocking
            time.sleep_ms(30)
            
    except KeyboardInterrupt:
        print("\nStopping the test...")
        encoder.remove_listener(on_encoder_change)
        encoder.close()
        radio.power_off()
        print("✅ Radio powered off, pins released. Program terminated.")

if __name__ == "__main__":
    main()