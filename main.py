#!/usr/bin/env python3
"""
main.py — Smart Meter Logger

- This script reads REAL data from Meter 1.
- It then uses that data to generate LIVE SIMULATED data
  for Meters 2 and 3 in real-time.
- This makes the dashboard appear as if all 3 meters are live.
- Includes WAL mode fix for SQLite concurrency.
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
import random

# --- CONFIGURATION ---
DB_NAME = "campus_energy_multi.db" 
SLAVE_ID = 1 # The physical meter we are reading from
BAUD_RATE = 9600
TIMEOUT = 1.0
INTERVAL = 5 # 5 seconds

# --- MQTT CONFIGURATION ---
MQTT_BROKER_HOST = "localhost"
MQTT_BROKER_PORT = 1883
MQTT_TOPIC = "pes/campus/energy/meter/reading"
MQTT_METER_ID = "ECE-F1-001_DEV" # Changed ID to avoid collision
BUILDING = "ECE"
FLOOR = "1"
mqtt_client = None

# Modbus register map 
REGISTERS = {
    "voltage_v1":       {"addr": 6,  "word_order": "ABCD", "unpack": ">f", "scale": 1.0},
    "current_a1":       {"addr": 8,  "word_order": "ABCD", "unpack": ">f", "scale": 1.0},
    "active_power_w1":  {"addr": 10, "word_order": "ABCD", "unpack": ">f", "scale": -1000.0},
    "power_factor_pf1": {"addr": 34, "word_order": "ABCD", "unpack": ">f", "scale": 1.0},
    "frequency_hz":     {"addr": 54, "word_order": "ABCD", "unpack": ">f", "scale": 1.0},
}

READ_BLOCKS = [
    (6, 6),   # Reads registers 6 through 11 (V, I, W)
    (34, 2),  # Reads registers 34 through 35 (PF)
    (54, 2)   # Reads registers 54 through 55 (Hz)
]


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

# --- DATABASE SETUP (WITH WAL MODE) ---
def setup_database():
    """
    Checks if the new database and tables exist.
    *** NEW: Enables WAL mode for better concurrency ***
    """
    try:
        # Connect with a timeout, just in case
        conn = sqlite3.connect(DB_NAME, timeout=10.0)
        cursor = conn.cursor()
        
        # Enable Write-Ahead Logging (WAL) mode
        cursor.execute("PRAGMA journal_mode=WAL;")

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meter_readings'")
        if cursor.fetchone() is None:
            log_runtime(f"Error: Table 'meter_readings' not found in '{DB_NAME}'.")
            log_runtime("Please run 'create_sim_database.py' first.")
            conn.close()
            return False
            
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meter_hierarchy'")
        if cursor.fetchone() is None:
            log_runtime(f"Error: Table 'meter_hierarchy' not found in '{DB_NAME}'.")
            log_runtime("Please run 'create_sim_database.py' first.")
            conn.close()
            return False
            
        log_runtime(f"✅ Successfully connected to local database '{DB_NAME}'. (WAL mode enabled)")
        conn.close()
        return True
    except Exception as e:
        log_runtime(f"⚠️ Error checking local database: {e}")
        return False

# --- Helper function for live simulation ---
def simulate_reading(base_data, scale_factor):
    """Takes a real data dict and returns a scaled/jittered simulated dict."""
    sim_data = base_data.copy()
    jitter = random.uniform(0.95, 1.05) 
    
    sim_data['current_a1'] = round(base_data.get('current_a1', 0) * scale_factor * jitter, 2)
    sim_data['active_power_w1'] = round(base_data.get('active_power_w1', 0) * scale_factor * jitter, 2)
    sim_data['energy_wh_interval'] = round(base_data.get('energy_wh_interval', 0) * scale_factor * jitter, 5)
    
    pf_jitter = random.uniform(0.98, 1.02)
    sim_data['power_factor_pf1'] = round(base_data.get('power_factor_pf1', 0) * pf_jitter, 3)
    
    return sim_data

# --- DATABASE LOGGING (WITH TIMEOUT FIX) ---
def log_to_local_db(data, meter_id):
    """
    Logs a single data dictionary to the new 'meter_readings' table.
    """
    try:
        # Wait up to 10 seconds if the database is locked
        conn = sqlite3.connect(DB_NAME, timeout=10.0)
        
        cur = conn.cursor()
        
        cur.execute('''
            INSERT INTO meter_readings 
            (meter_id, timestamp, voltage, current, power, energy_wh_interval, pf)
            VALUES (?, datetime('now', 'localtime'), ?, ?, ?, ?, ?)
        ''', (
            meter_id, 
            data.get('voltage_v1'), 
            data.get('current_a1'), 
            data.get('active_power_w1'), 
            data.get('energy_wh_interval'),
            data.get('power_factor_pf1')
        ))
        conn.commit()
        conn.close()
    except sqlite3.Error as db_err:
         log_runtime(f"⚠️ SQLite Error for meter {meter_id}: {db_err}")

# --- MQTT CALLBACKS (Fixed to v2) ---
def on_connect(client, userdata, flags, rc, properties):
    if rc == 0:
        log_runtime("✅ Connected to MQTT broker.")
    else:
        log_runtime(f"⚠️ Failed to connect to MQTT broker, return code {rc}")

def on_disconnect(client, userdata, flags, rc, properties):
    if rc != 0:
        log_runtime(f" MQTT> Unexpectedly disconnected from broker with code {rc}")

# --- SIGNAL HANDLING ---
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

    if not setup_database():
        log_runtime("Database setup failed. Exiting.")
        return
        
    ser = None
    reconnect_delay = 2.0

    # --- MQTT Client Setup (Fixed to v2) ---
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"smart_meter_logger_{MQTT_METER_ID}")
    mqtt_client.on_connect = on_connect
    mqtt_client.on_disconnect = on_disconnect
    try:
        mqtt_client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, 60)
        mqtt_client.loop_start() 
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

            # --- STEP 3 & 4: PROCESS, LOG, & SIMULATE ---
            if all_blocks_read_successfully:
                real_data = {}
                for key, meta in REGISTERS.items():
                    addr = meta["addr"]
                    raw4 = register_map.get(addr, b'') + register_map.get(addr + 1, b'')
                    if len(raw4) == 4:
                        reordered = reorder_words(raw4, meta["word_order"])
                        unpack_format = meta["unpack"]
                        val = struct.unpack(unpack_format, reordered)[0]
                        real_data[key] = round(val * meta["scale"], 3)
                    else:
                        log_runtime(f"⚠️ Missing data for register {key} (addr {addr})")
                        real_data[key] = None # Mark as missing

                if all(v is not None for v in real_data.values()):
                    
                    # Calculate energy for the real meter
                    power_w = real_data.get('active_power_w1', 0)
                    interval_hours = INTERVAL / 3600.0
                    energy_wh_interval = power_w * interval_hours
                    real_data['energy_wh_interval'] = round(energy_wh_interval, 5)

                    # --- Live Simulation Logic ---
                    # 1. Log the real data for Meter 1
                    log_to_local_db(real_data, 1)
                    
                    # 2. Simulate and log for Meter 2
                    sim_data_2 = simulate_reading(real_data, 0.8)
                    log_to_local_db(sim_data_2, 2)
                    
                    # 3. Simulate and log for Meter 3
                    sim_data_3 = simulate_reading(real_data, 1.2)
                    log_to_local_db(sim_data_3, 3)
                    
                    log_runtime(f"✅ Logged real data for Meter 1 and simulated data for Meters 2 & 3.")
                    # ---------------------------

                    # --- PUBLISH TO MQTT ---
                    if mqtt_client and mqtt_client.is_connected():
                        mqtt_payload = real_data.copy()
                        mqtt_payload['timestamp'] = timestamp.isoformat()
                        mqtt_payload['meter_id'] = MQTT_METER_ID
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
            time.sleep(2)

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
