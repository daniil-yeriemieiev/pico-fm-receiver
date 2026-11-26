"""
Main Application Module for the Pico W FM Radio Receiver (v1.1.0).

Integrates the Si4703 FM tuner, SH1106 OLED display, EC11 rotary encoder,
multi-function pushbutton, and temporary session storage using a multi-rate
non-blocking superloop with hardware interrupts.

Controls (Normal Mode):
    - Rotate: Adjust frequency (88.0-108.0 MHz) or volume (0-15).
    - Single click: Toggle encoder between frequency and volume mode.
    - Press & hold: Hardware seek to the next strong station.
    - Double click: Enter the Auto-Scan station menu.

Controls (Auto-Scan Menu Mode):
    - Single click: Start or stop band auto-scan.
    - Rotate: Scroll through discovered stations.
    - Press & hold: Tune to the selected station and exit to normal mode.
    - Double click: Exit back to normal mode.
"""

import time
from machine import Pin, I2C  # type: ignore

from fm_tuner import FmTuner
from sh1106 import SH1106_I2C
from rotary_irq_rp2 import RotaryIRQ
from multi_button import MultiFunctionButton
from radio_ui import RadioUI
from station_store import StationStore

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
DEFAULT_VOLUME = 5

# Multi-rate superloop timings (ms)
LOOP_DELAY_MS = 5
RADIO_POLL_MS = 30
UI_REFRESH_MS = 100
UI_MIN_FRAME_MS = 50
TUNE_SETTLE_MS = 120

# RDS & Auto-Scan settings
AUTOSCAN_RDS_WAIT_MS = 4700
RT_SCROLL_MS = 250
RT_WINDOW_CHARS = 10
SESSION_FILE = "autoscan_tmp.csv"

encoder_rotated = False  # set in IRQ, cleared in loop


def on_encoder_change():
    """
    Lightweight hardware interrupt callback for rotary encoder rotation.

    Sets a global flag processed inside the main superloop without performing
    any I2C transactions or memory allocation in IRQ context.
    """
    global encoder_rotated
    encoder_rotated = True


def log(tag, message):
    """
    Print a timestamped log message to the serial terminal.

    :param str tag: Short subsystem label (e.g. ``INIT``, ``TUNE``, ``SCAN``).
    :param str message: Human-readable event description.
    """
    print(f"[{time.ticks_ms():>8} ms] [{tag}] {message}")


def sync_encoder(encoder, value, min_val, max_val, range_mode):
    """
    Reconfigure the encoder range and clear any pending rotation flag.

    :param RotaryIRQ encoder: Active rotary encoder instance.
    :param int value: New encoder counter value.
    :param int min_val: Lower range bound.
    :param int max_val: Upper range bound.
    :param int range_mode: ``RotaryIRQ.RANGE_WRAP`` or ``RANGE_BOUNDED``.
    """
    global encoder_rotated
    encoder.set(value=value, min_val=min_val, max_val=max_val, range_mode=range_mode)
    encoder_rotated = False


def main():
    """
    Initialize hardware peripherals and execute the main radio superloop.
    """
    global encoder_rotated

    log("INIT", "Starting Pico W FM Radio Receiver (v1.1.0)...")

    # Clean up any leftover temporary file from an ungraceful previous reset
    store = StationStore(SESSION_FILE)
    if store.cleanup():
        log("STORE", f"Removed stale session file '{SESSION_FILE}'")

    radio = FmTuner(
        i2c_id=RADIO_I2C_ID,
        sda=PIN_RADIO_SDA,
        scl=PIN_RADIO_SCL,
        rst=PIN_RADIO_RST,
        freq=RADIO_I2C_FREQ,
    )
    start_mhz = DEFAULT_FREQ_SCALED / 10.0
    radio.start(volume=0, frequency=start_mhz)
    radio.set_volume(DEFAULT_VOLUME)
    log("INIT", f"Si4703 ready at {radio.frequency:.1f} MHz, volume {radio.volume}/{VOL_MAX}")

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
    ui = RadioUI(oled, vol_max=VOL_MAX, rt_scroll_ms=RT_SCROLL_MS, rt_window_chars=RT_WINDOW_CHARS)
    log("INIT", "SH1106 OLED initialized")

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
    sync_encoder(encoder, DEFAULT_FREQ_SCALED, FM_MIN_SCALED, FM_MAX_SCALED, RotaryIRQ.RANGE_WRAP)
    encoder.add_listener(on_encoder_change)

    # Pin base class rejects extra arguments
    button = MultiFunctionButton(PIN_ENC_SW)
    log("INIT", "EC11 encoder and MultiFunctionButton ready")

    # Application state
    control_mode = RadioUI.MODE_FREQ
    in_scan_menu = False
    manual_seek_active = False
    pending_freq_mhz = None
    last_tune_input_ms = 0

    # Auto-scan state
    autoscan_stage = "IDLE"  # IDLE, SEEKING or WAIT_RDS
    autoscan_rds_t0 = 0
    autoscan_pre_freq = start_mhz
    stations = []
    selected_idx = 0

    # Periodic task timers and log deduplication
    last_poll_ms = time.ticks_ms()
    last_ui_ms = 0
    ui_dirty = True
    last_logged_ps = ""
    last_logged_rt = ""

    def apply_normal_encoder():
        """Configure encoder bounds according to the active normal control mode."""
        if control_mode == RadioUI.MODE_VOL:
            sync_encoder(encoder, radio.volume, VOL_MIN, VOL_MAX, RotaryIRQ.RANGE_BOUNDED)
        else:
            freq_scaled = min(max(round(radio.frequency * 10), FM_MIN_SCALED), FM_MAX_SCALED)
            sync_encoder(encoder, freq_scaled, FM_MIN_SCALED, FM_MAX_SCALED, RotaryIRQ.RANGE_WRAP)

    def apply_menu_encoder():
        """Configure encoder bounds for scrolling the auto-scan station list."""
        max_idx = max(0, len(stations) - 1)
        idx = min(max(selected_idx, 0), max_idx)
        sync_encoder(encoder, idx, 0, max_idx, RotaryIRQ.RANGE_BOUNDED)

    def flush_pending_tune():
        """Execute any deferred frequency tune immediately."""
        nonlocal pending_freq_mhz, last_logged_ps, last_logged_rt, ui_dirty
        if pending_freq_mhz is not None:
            target = pending_freq_mhz
            pending_freq_mhz = None
            tuned = radio.tune(target)
            last_logged_ps = ""
            last_logged_rt = ""
            ui_dirty = True
            if tuned is not None:
                log("TUNE", f"{tuned:.1f} MHz | RSSI: {radio.rssi} | Stereo: {radio.stereo}")
            else:
                log("TUNE", f"Timeout tuning to {target:.1f} MHz")

    try:
        while True:
            now = time.ticks_ms()
            btn_event = button.update()

            # ------------------------------------------------------------
            # 1. BUTTON GESTURES
            # ------------------------------------------------------------
            if not in_scan_menu:
                # Normal Mode: 1 click toggles FREQ / VOL
                if btn_event == MultiFunctionButton.EVENT_SINGLE_CLICK:
                    flush_pending_tune()
                    control_mode = (
                        RadioUI.MODE_VOL if control_mode == RadioUI.MODE_FREQ
                        else RadioUI.MODE_FREQ
                    )
                    apply_normal_encoder()
                    mode_name = "VOLUME" if control_mode == RadioUI.MODE_VOL else "FREQUENCY"
                    log("MODE", f"Encoder switched to {mode_name}")
                    ui_dirty = True

                # Normal Mode: Hold triggers hardware seek
                elif btn_event == MultiFunctionButton.EVENT_HOLD:
                    flush_pending_tune()
                    if not radio.seeking:
                        log("SEEK", "Searching for next strong station...")
                        radio.seek_start(up=True)
                        manual_seek_active = True
                        ui_dirty = True

                # Normal Mode: Double click enters Auto-Scan menu
                elif btn_event == MultiFunctionButton.EVENT_DOUBLE_CLICK:
                    flush_pending_tune()
                    if manual_seek_active:
                        radio.seek_stop()
                        manual_seek_active = False
                    in_scan_menu = True
                    stations = store.load()
                    selected_idx = min(selected_idx, max(0, len(stations) - 1))
                    apply_menu_encoder()
                    log("MODE", f"Entered Auto-Scan menu ({len(stations)} stations cached)")
                    ui_dirty = True

            else:
                # Auto-Scan Menu: Double click exits to Normal Mode
                if btn_event == MultiFunctionButton.EVENT_DOUBLE_CLICK:
                    if autoscan_stage != "IDLE":
                        radio.seek_stop()
                        autoscan_stage = "IDLE"
                        radio.tune(autoscan_pre_freq)
                        log("SCAN", "Aborted on menu exit; restored previous frequency")
                    in_scan_menu = False
                    apply_normal_encoder()
                    log("MODE", "Exited Auto-Scan menu to Normal mode")
                    ui_dirty = True

                # Auto-Scan Menu: 1 click starts (or stops) Auto-Scan
                elif btn_event == MultiFunctionButton.EVENT_SINGLE_CLICK:
                    if autoscan_stage == "IDLE":
                        autoscan_pre_freq = radio.frequency
                        store.clear()
                        stations = []
                        selected_idx = 0
                        log("STORE", f"Reset temporary file '{SESSION_FILE}'")
                        log("SCAN", "Starting band auto-scan (88.0 - 108.0 MHz)...")
                        radio.tune(FM_MIN_SCALED / 10.0)
                        radio.seek_start(up=True)
                        autoscan_stage = "SEEKING"
                        ui_dirty = True
                    else:
                        radio.seek_stop()
                        autoscan_stage = "IDLE"
                        radio.tune(autoscan_pre_freq)
                        stations = store.load()
                        selected_idx = min(selected_idx, max(0, len(stations) - 1))
                        apply_menu_encoder()
                        log("SCAN", f"Stopped by user ({len(stations)} stations found)")
                        ui_dirty = True

                # Auto-Scan Menu: Hold tunes to selected station and exits
                elif btn_event == MultiFunctionButton.EVENT_HOLD:
                    if autoscan_stage == "IDLE" and stations:
                        _, sel_freq, sel_rds = stations[selected_idx]
                        in_scan_menu = False
                        control_mode = RadioUI.MODE_FREQ
                        radio.tune(sel_freq)
                        last_logged_ps = ""
                        last_logged_rt = ""
                        apply_normal_encoder()
                        log("SCAN", f"Selected {sel_freq:.1f} MHz ({sel_rds}), exiting menu")
                        ui_dirty = True

            # ------------------------------------------------------------
            # 2. ENCODER ROTATION
            # ------------------------------------------------------------
            if encoder_rotated:
                encoder_rotated = False
                val = encoder.value()

                if in_scan_menu:
                    if autoscan_stage == "IDLE" and stations:
                        selected_idx = min(max(val, 0), len(stations) - 1)
                        ui_dirty = True
                elif control_mode == RadioUI.MODE_VOL:
                    radio.set_volume(val)
                    radio.mute(val == 0)
                    log("VOL", f"Volume set to {val}/{VOL_MAX}" + (" (MUTED)" if val == 0 else ""))
                    ui_dirty = True
                elif not radio.seeking:
                    # Defer blocking tune until rapid rotation settles
                    pending_freq_mhz = val / 10.0
                    last_tune_input_ms = now
                    ui_dirty = True

            # Execute deferred tune once encoder stops moving
            if (pending_freq_mhz is not None
                    and time.ticks_diff(now, last_tune_input_ms) >= TUNE_SETTLE_MS):
                flush_pending_tune()

            # ------------------------------------------------------------
            # 3. RADIO POLLING, MANUAL SEEK & AUTO-SCAN FSM (every 30 ms)
            # ------------------------------------------------------------
            if time.ticks_diff(now, last_poll_ms) >= RADIO_POLL_MS:
                last_poll_ms = now

                if manual_seek_active:
                    if radio.seek_update():
                        manual_seek_active = False
                        if radio.seek_failed:
                            log("SEEK", "No station found")
                        else:
                            if radio.frequency < (FM_MIN_SCALED / 10.0):
                                radio.tune(FM_MIN_SCALED / 10.0)
                            log("SEEK", f"Found {radio.frequency:.1f} MHz (RSSI: {radio.rssi})")
                        last_logged_ps = ""
                        last_logged_rt = ""
                        if not in_scan_menu and control_mode == RadioUI.MODE_FREQ:
                            apply_normal_encoder()
                        ui_dirty = True

                elif autoscan_stage == "SEEKING":
                    if radio.seek_update():
                        freq = radio.frequency
                        duplicate = any(abs(s[1] - freq) < 0.05 for s in stations)
                        if radio.seek_failed or duplicate or freq < (FM_MIN_SCALED / 10.0):
                            autoscan_stage = "IDLE"
                            radio.tune(autoscan_pre_freq)
                            stations = store.load()
                            selected_idx = 0
                            apply_menu_encoder()
                            log("SCAN", f"Completed. Found {len(stations)} stations.")
                        else:
                            autoscan_stage = "WAIT_RDS"
                            autoscan_rds_t0 = now
                        ui_dirty = True

                elif autoscan_stage == "WAIT_RDS":
                    radio.poll()
                    elapsed = time.ticks_diff(now, autoscan_rds_t0)
                    if radio.ps or elapsed >= AUTOSCAN_RDS_WAIT_MS:
                        rds_str = radio.ps if radio.ps else "---"
                        store.add(radio.rssi, radio.frequency, rds_str)
                        stations.append((radio.rssi, radio.frequency, rds_str))
                        selected_idx = len(stations) - 1
                        log("SCAN", f"Station #{len(stations)}: {radio.frequency:5.1f} MHz | RSSI {radio.rssi:>2} | RDS: {rds_str}")
                        radio.seek_start(up=True)
                        autoscan_stage = "SEEKING"
                        ui_dirty = True

                else:
                    radio.poll()
                    if radio.ps and radio.ps != last_logged_ps:
                        last_logged_ps = radio.ps
                        log("RDS", f"PS: '{radio.ps}'")
                        ui_dirty = True
                    if radio.rt and radio.rt != last_logged_rt:
                        last_logged_rt = radio.rt
                        log("RDS", f"RT: '{radio.rt}'")
                        ui_dirty = True

            # ------------------------------------------------------------
            # 4. THROTTLED OLED REFRESH
            # ------------------------------------------------------------
            since_ui = time.ticks_diff(now, last_ui_ms)
            if since_ui >= UI_REFRESH_MS or (ui_dirty and since_ui >= UI_MIN_FRAME_MS):
                last_ui_ms = now
                ui_dirty = False
                if in_scan_menu:
                    ui.render_scan_menu(
                        stations=stations,
                        selected_idx=selected_idx,
                        scanning=(autoscan_stage != "IDLE"),
                        scan_freq=radio.frequency,
                    )
                else:
                    disp_freq = pending_freq_mhz if pending_freq_mhz is not None else radio.frequency
                    ui.render_normal(radio, disp_freq, control_mode)

            time.sleep_ms(LOOP_DELAY_MS)

    except KeyboardInterrupt:
        log("EXIT", "Shutdown requested by user")
    finally:
        encoder.remove_listener(on_encoder_change)
        encoder.close()
        oled.poweroff()
        radio.power_off()
        if store.cleanup():
            log("STORE", f"Deleted temporary session file '{SESSION_FILE}'")
        log("EXIT", "Hardware powered down cleanly")


if __name__ == "__main__":
    main()