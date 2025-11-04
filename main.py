#!/usr/bin/env python3
"""
main.py — Smart Meter Logger (v9.1 - Calculate Energy)

- STOPS reading the broken 'energy_kwh' register (56).
- Manually calculates 'energy_wh' (Watt-hours) for each
  interval based on the stable 'active_power_w1' reading.
- This calculated value is now the source of truth.
"""

import serial
import struct
import time
import glob
import os
import signal
import sqlite3
import json
import paho.mqtt.client as mqtt
from datetime import datetime

# --- CONFIGURATION ---
LOG_DIR = "log_files"
DB_FILE = os.path.join(LOG_DIR, "smart_meter.db")
SLAVE_ID = 1
BAUD_RATE = 9600
TIMEOUT = 1.0
INTERVAL = 5 # 5 seconds

# --- METER IDENTIFICATION ---
METER_ID = "ECE-F1-001"
BUILDING = "ECE"
FLOOR = "1"

# Modbus register map (addresses and data types)
REGISTERS = {
    # -------------------------------------------------------------------------
    # --- NEW (v9.1) ---
    # We are GIVING UP on energy_kwh.
    # We will read the other (working) values and calculate energy.
    # -------------------------------------------------------------------------
    "voltage_v1":       {"addr": 6,  "word_order": "ABCD", "unpack": ">f", "scale": 1.0},
    "current_a1":       {"addr": 8,  "word_order": "ABCD", "unpack": ">f", "scale": 1.0},
    "active_power_w1":  {"addr": 10, "word_order": "ABCD", "unpack": ">f", "scale": -1000.0},
    "power_factor_pf1": {"addr": 34, "word_order": "ABCD", "unpack": ">f", "scale": 1.0},
    "frequency_hz":     {"addr": 54, "word_order": "ABCD", "unpack": ">f", "scale": 1.0},
    # "energy_kwh" register (56) is REMOVED.
}

# Define which registers to read in contiguous blocks
READ_BLOCKS = [
    (6, 6),   # Reads registers 6 through 11 (V, I, W)
    (34, 2),  # Reads registers 34 through 35 (PF)
    (54, 2)   # Reads registers 54 through 55 (Hz) - No longer reading 56/57
]

# --- MQTT CONFIGURATION ---
MQTT_BROKER_HOST = "localhost"
MQTT_BROKER_PORT = 1883
MQTT_TOPIC = "pes/campus/energy/meter/reading"
mqtt_client = None

# --- UTILITY FUNCTIONS ---
def log_runtime(msg):
    """Prints a message with a timestamp."""
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}")

def calc_crc(data):
    """Calculates the CRC-16 checksum for a Modbus frame."""
    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc.to_bytes(2, "little")

def build_poll_frame(slave, start, qty):
    """Builds a Modbus RTU frame for reading holding registers."""
    frame = bytes([slave, 3, (start >> 8) & 0xFF, start & 0xFF, (qty >> 8) & 0xFF, qty & 0xFF])
    return frame + calc_crc(frame)

def validate_response(frame, slave, func):
    """Validates a Modbus response frame."""
    return len(frame) >= 5 and calc_crc(frame[:-2]) == frame[-2:] and frame[0] == slave and frame[1] == func

def reorder_words(raw4_bytes, order="ABCD"):
    """Reorders the bytes of a 4-byte float value."""
    mapping = {"A": 0, "B": 1, "C": 2, "D": 3}
    return bytes([raw4_bytes[mapping[c]] for c in order])

def setup_database():
    """Creates the SQLite database and table if they don't exist."""
    os.makedirs(LOG_DIR, exist_ok=True)
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    # --- NEW (v9.1) ---
    # Changed energy_kwh to energy_wh_interval
    cur.execute('''
        CREATE TABLE IF NOT EXISTS readings (
            timestamp TEXT PRIMARY KEY,
            meter_id TEXT,
            building TEXT,
            floor TEXT,
            voltage_v1 REAL,
            current_a1 REAL,
            active_power_w1 REAL,
            power_factor_pf1 REAL,
            frequency_hz REAL,
            energy_wh_interval REAL
        )
    ''')
    # Add new column, ignore if it fails (already exists)
    try: cur.execute("ALTER TABLE readings ADD COLUMN energy_wh_interval REAL;")
    except: pass
    
    # Try to drop the old, bad column (ignore if it fails)
    try: cur.execute("ALTER TABLE readings DROP COLUMN energy_kwh;")
    except: pass
    
    con.commit()
    con.close()
    log_runtime(f"Database initialized at '{DB_FILE}'")

# --- MQTT CALLBACKS (FIXED) ---
def on_connect(client, userdata, flags, rc, properties):
    """Callback for MQTT connection."""
    if rc == 0:
        log_runtime("✅ Connected to MQTT broker.")
    else:
        log_runtime(f"⚠️ Failed to connect to MQTT broker, return code {rc}")

def on_disconnect(client, userdata, flags, rc, properties):
    """Callback for MQTT disconnection (with 5 args)."""
    log_runtime(f" MQTT> Disconnected from broker with code {rc}")


# --- SIGNAL HANDLING for graceful shutdown ---
terminate = False
def handle_sig(sig, frame):
    """Handles SIGINT/SIGTERM for graceful shutdown."""
    global terminate
    log_runtime(f"Received signal {sig}, shutting down gracefully...")
    terminate = True

signal.signal(signal.SIGINT, handle_sig)
signal.signal(signal.SIGTERM, handle_sig)


# --- MAIN APPLICATION ---
def main():
    """Main loop: Connects to meter, reads data, logs to SQLite, and publishes to MQTT."""
    global mqtt_client

    setup_database()
    ser = None
    reconnect_delay = 2.0

    # --- MQTT Client Setup ---
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"smart_meter_logger_{METER_ID}")
    mqtt_client.on_connect = on_connect
    mqtt_client.on_disconnect = on_disconnect
    try:
        mqtt_client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, 60)
        mqtt_client.loop_start() # Start MQTT network loop in background thread
    except Exception as e:
        log_runtime(f"⚠️ Could not connect to MQTT broker: {e}. MQTT publishing disabled.")
        mqtt_client = None

    # --- Main Loop ---
    while not terminate:
        cycle_start_time = time.time()

        # --- STEP 1: SERIAL CONNECTION ---
        if ser is None or not ser.is_open:
            log_runtime("Searching for serial device...")
            port_list = (glob.glob("/dev/ttyUSB*") + glob.glob("/dev/tty.usbserial*"))
            if not port_list:
                log_runtime(f"No device found. Retrying in {reconnect_delay * 2:.0f}s...")
                time.sleep(reconnect_delay * 2)
                continue
            try:
                port_name = port_list[0]
                ser = serial.Serial(port_name, BAUD_RATE, timeout=TIMEOUT)
                log_runtime(f"✅ Connection established with {port_name}.")
                reconnect_delay = 2.0
            except serial.SerialException as e:
                log_runtime(f"⚠️  Failed to connect: {e}. Retrying in {reconnect_delay:.0f}s...")
                ser = None
                time.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)
                continue

        # --- STEP 2: READ METER DATA ---
        try:
            timestamp = datetime.now()
            register_map = {}
            all_blocks_read_successfully = True

            for start, qty in READ_BLOCKS:
                try:
                    frame = build_poll_frame(SLAVE_ID, start, qty)
                    ser.reset_input_buffer()
                    ser.write(frame)
                    time.sleep(0.25)
                    response_buffer = bytearray()
                    expected_len = 5 + qty * 2
                    deadline = time.time() + TIMEOUT
                    while len(response_buffer) < expected_len and time.time() < deadline:
                        if ser.in_waiting:
                            response_buffer.extend(ser.read(ser.in_waiting))
                        time.sleep(0.01)
                    response = bytes(response_buffer)
                    if not (response and validate_response(response, SLAVE_ID, 0x03)):
                        raise IOError(f"Invalid or incomplete response for block at {start}")
                    payload = response[3:-2]
                    for i in range(qty):
                        register_map[start + i] = payload[i*2 : i*2+2]
                except (serial.SerialException, IOError) as e:
                    log_runtime(f"⚠️  Warning: Failed to read block at {start} ({e}). Skipping this cycle.")
                    all_blocks_read_successfully = False
                    break 

            # --- STEP 3 & 4: PROCESS, LOG LOCALLY, AND PUBLISH TO MQTT ---
            if all_blocks_read_successfully:
                row_values = {}
                for key, meta in REGISTERS.items():
                    addr = meta["addr"]
                    raw4 = register_map.get(addr, b'') + register_map.get(addr + 1, b'')
                    if len(raw4) == 4:
                        reordered = reorder_words(raw4, meta["word_order"])
                        unpack_format = meta["unpack"]
                        val = struct.unpack(unpack_format, reordered)[0]
                        row_values[key] = round(val * meta["scale"], 3)
                    else:
                        log_runtime(f"⚠️ Missing data for register {key} (addr {addr})")
                        row_values[key] = None # Mark as missing

                # Ensure all expected values were successfully decoded
                if all(v is not None for v in row_values.values()):
                    
                    timestamp_str_db = timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

                    # --- NEW (v9.1) Calculate energy ---
                    power_w = row_values.get('active_power_w1', 0)
                    interval_hours = INTERVAL / 3600.0
                    energy_wh_interval = power_w * interval_hours
                    row_values['energy_wh_interval'] = round(energy_wh_interval, 5)

                    # Prepare the complete data dictionary
                    full_data = row_values.copy()
                    full_data['timestamp'] = timestamp_str_db
                    full_data['meter_id'] = METER_ID
                    full_data['building'] = BUILDING
                    full_data['floor'] = FLOOR

                    # 3a. Log to SQLite
                    try:
                        con = sqlite3.connect(DB_FILE)
                        cur = con.cursor()
                        columns = ', '.join(full_data.keys())
                        placeholders = ':'+', :'.join(full_data.keys())
                        sql = f'INSERT OR REPLACE INTO readings ({columns}) VALUES ({placeholders})'
                        cur.execute(sql, full_data)
                        con.commit()
                        con.close()
                        log_runtime(f"✅ Logged to DB {METER_ID} at {timestamp_str_db}")
                    except sqlite3.Error as db_err:
                         log_runtime(f"⚠️ SQLite Error: {db_err}")

                    # 3b. Publish to MQTT
                    if mqtt_client and mqtt_client.is_connected():
                        mqtt_payload = row_values.copy()
                        mqtt_payload['timestamp'] = timestamp.isoformat()
                        mqtt_payload['meter_id'] = METER_ID
                        mqtt_payload['building'] = BUILDING
                        mqtt_payload['floor'] = FLOOR
                        payload_json = json.dumps(mqtt_payload)
                        result = mqtt_client.publish(MQTT_TOPIC, payload_json)
                        if result.rc != mqtt.MQTT_ERR_SUCCESS:
                             log_runtime(f"⚠️ Mqtt> Failed to send message: {mqtt.error_string(result.rc)}")

        except (serial.SerialException, IOError) as e:
            log_runtime(f"❌ Communication lost: {e}. Closing port and preparing to reconnect.")
            if ser: ser.close()
            ser = None
            time.sleep(5)
            continue
        except Exception as e:
            log_runtime(f"An unexpected error occurred: {e}")
            time.sleep(2) # Prevent rapid error loops

        # --- Wait for Next Interval ---
        time_spent = time.time() - cycle_start_time
        wait_time = max(0, INTERVAL - time_spent)
        for _ in range(int(wait_time / 0.1)):
            if terminate: break
            time.sleep(0.1)

    # --- Cleanup ---
    if ser and ser.is_open:
        ser.close()
    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        log_runtime("MQTT client disconnected.")
    log_runtime("Logger stopped.")


if __name__ == "__main__":
    main()
