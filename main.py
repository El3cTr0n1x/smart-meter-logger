#!/usr/bin/env python3
"""
main.py — Smart Meter Logger (v7.1 - Resilient Build)

Logs smart meter data to an SQLite database with enhanced error handling.
- Handles intermittent hardware connection drops gracefully.
- Skips logging cycles on partial data reads instead of crashing.
- Structured for continuous, long-term operation as a background service.
"""

import serial
import struct
import time
import glob
import os
import signal
import sqlite3
from datetime import datetime

# --- CONFIGURATION ---
LOG_DIR = "log_files"
DB_FILE = os.path.join(LOG_DIR, "smart_meter.db")
SLAVE_ID = 1
BAUD_RATE = 9600
TIMEOUT = 1.0
INTERVAL = 2 # seconds

# Modbus register map (addresses and data types)
REGISTERS = {
    "voltage_v1":       {"addr": 6,  "word_order": "ABCD", "scale": 1.0},
    "current_a1":       {"addr": 8,  "word_order": "ABCD", "scale": 1.0},
    "active_power_w1":  {"addr": 10, "word_order": "ABCD", "scale": -1000.0},
    "power_factor_pf1": {"addr": 34, "word_order": "ABCD", "scale": 1.0},
    "frequency_hz":     {"addr": 54, "word_order": "ABCD", "scale": 1.0},
    "energy_kwh":       {"addr": 56, "word_order": "ABCD", "scale": 1.0}
}

# Define which registers to read in contiguous blocks
READ_BLOCKS = [
    (6, 6),   # Reads registers 6 through 11 (V, I, W)
    (34, 2),  # Reads registers 34 through 35 (PF)
    (54, 4)   # Reads registers 54 through 57 (Hz, kWh)
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

def setup_database():
    """Creates the SQLite database and table if they don't exist."""
    os.makedirs(LOG_DIR, exist_ok=True)
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS readings (
            timestamp TEXT PRIMARY KEY,
            voltage_v1 REAL,
            current_a1 REAL,
            active_power_w1 REAL,
            power_factor_pf1 REAL,
            frequency_hz REAL,
            energy_kwh REAL
        )
    ''')
    con.commit()
    con.close()
    log_runtime(f"Database initialized at '{DB_FILE}'")

# --- SIGNAL HANDLING for graceful shutdown ---
terminate = False
def handle_sig(sig, frame):
    global terminate
    log_runtime(f"Received signal {sig}, shutting down gracefully...")
    terminate = True

signal.signal(signal.SIGINT, handle_sig)
signal.signal(signal.SIGTERM, handle_sig)

# --- MAIN APPLICATION ---

def main():
    """Main loop for finding the serial port, reading data, and logging to the database."""
    setup_database()
    ser = None
    reconnect_delay = 2.0

    while not terminate:
        # --- STEP 1: ESTABLISH AND VERIFY CONNECTION ---
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
                reconnect_delay = 2.0 # Reset delay on successful connection
            except serial.SerialException as e:
                log_runtime(f"⚠️  Failed to connect: {e}. Retrying in {reconnect_delay:.0f}s...")
                ser = None # Ensure ser is None if connection fails
                time.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60) # Cap delay at 60s
                continue

        # --- STEP 2: TRY TO READ DATA FROM THE METER ---
        try:
            timestamp = datetime.now()
            register_map = {}
            # Read all data blocks
            for start, qty in READ_BLOCKS:
                frame = build_poll_frame(SLAVE_ID, start, qty)
                ser.reset_input_buffer()
                ser.write(frame)
                time.sleep(0.25)

                response = ser.read(5 + qty * 2) # Read expected response length

                if not (response and validate_response(response, SLAVE_ID, 0x03)):
                    raise IOError(f"Invalid response for block at {start}")
                
                payload = response[3:-2]
                for i in range(qty):
                    register_map[start + i] = payload[i*2 : i*2+2]
            
            # --- STEP 3: PROCESS AND LOG THE DATA ---
            # (This part is only reached if all blocks were read successfully)
            row_values = {}
            for key, meta in REGISTERS.items():
                addr = meta["addr"]
                raw4 = register_map.get(addr, b'') + register_map.get(addr + 1, b'')
                if len(raw4) == 4:
                    reordered = reorder_words(raw4, meta["word_order"])
                    val = struct.unpack(">f", reordered)[0]
                    row_values[key] = round(val * meta["scale"], 3)
            
            if len(row_values) == len(REGISTERS):
                row_values['timestamp'] = timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                
                con = sqlite3.connect(DB_FILE)
                cur = con.cursor()
                sql = f'INSERT OR REPLACE INTO readings ({", ".join(row_values.keys())}) VALUES (:{", :".join(row_values.keys())})'
                cur.execute(sql, row_values)
                con.commit()
                con.close()
                
                log_runtime(f"✅ Logged data point at {row_values['timestamp']}")

        except (serial.SerialException, IOError) as e:
            # This is the crucial fallback. A read error means the connection is likely lost.
            log_runtime(f"❌ Communication lost: {e}. Closing port and preparing to reconnect.")
            ser.close()
            ser = None # Setting ser to None triggers the reconnection logic in the next loop.
            time.sleep(5) # Wait a moment before trying to reconnect
            continue

        # --- Wait for the next 5-second interval ---
        time.sleep(max(0, INTERVAL - (time.time() % INTERVAL)))

    if ser and ser.is_open:
        ser.close()
    log_runtime("Logger stopped.")

if __name__ == "__main__":
    main()
