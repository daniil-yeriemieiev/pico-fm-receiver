import time
from rotary_irq_rp2 import RotaryIRQ
from fm_tuner import FmTuner

# Constants for encoder pins
PIN_CLK = 14
PIN_DT = 15
PIN_SW = 16

MIN_VAL = 875
MAX_VAL = 1080

# Constants for FM tuner
I2C_ID = 0
PIN_SDA = 4
PIN_SCL = 5
PIN_RST = 12

VOLUME = 10
RDS_LISTEN_S = 20
TUNE_LIMIT_MS = 300
CALL_LIMIT_MS = 20
POLL_MS = 30
SEEK_POLL_MS = 20
MAX_STATIONS = 60

enc = RotaryIRQ(pin_num_clk=PIN_CLK, 
                pin_num_dt=PIN_DT, 
                min_val=MIN_VAL, 
                max_val=MAX_VAL, 
                reverse=False, 
                range_mode=RotaryIRQ.RANGE_WRAP)

tuner = FmTuner(I2C_ID, PIN_SDA, PIN_SCL, PIN_RST)

encoder_needs_update = False

def on_encoder_change():
    """Ultra-lightweight callback for encoder rotation."""
    global encoder_needs_update
    encoder_needs_update = True

try:
    tuner.start(volume=VOLUME, frequency=87.5)
    value = enc.value() / 10.0
    while True:
        if encoder_needs_update:
            encoder_needs_update = False
            # Read encoder value
            value = enc.value() / 10.0
            print(f"Encoder value: {value}")
            
        # Seek up to the next station
        tuner.seek_start(up=True)
        # Wait for the seek to complete
        while not tuner.seek_update():
            time.sleep_ms(SEEK_POLL_MS)
        # Print the tuned frequency and RSSI

        #HACK: Tune to the encoder value
        tuner.tune(value)  # Tune to the encoder value
        print(f"Tuned to {tuner.frequency:.1f} MHz with RSSI {tuner.rssi} dBuV")
        # Listen for RDS for a few seconds
        print(f"Listening for RDS for {RDS_LISTEN_S} seconds...")
        t0 = time.ticks_ms()
        while True:
            if time.ticks_diff(time.ticks_ms(), t0) > 20000:
                t0 = time.ticks_ms()
                tuner.poll()
                print(f"RDS groups: {tuner.groups}, bad: {tuner.bad_groups}, PI: {tuner.pi}, PS: {tuner.ps}", end="\r")
                time.sleep_ms(POLL_MS)
        
except KeyboardInterrupt:
    print("Exiting...")
    tuner.power_off()