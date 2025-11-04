#!/usr/bin/env python3
"""
main.py — Smart Meter Logger (v6.2 - CSV Logger Build)

- Logs to daily rotating CSV files in log_files/
- Prints live, formatted data to the terminal.
- Stable Modbus decoding with register map.
- Handles graceful shutdown and auto-reconnect.
"""

import csv
import serial
import time
import struct
import glob
import os
import json
import signal
import argparse
from datetime import datetime

LOG_DIR = "log_files"
os.makedirs(LOG_DIR, exist_ok=True)
RUNTIME_LOG = os.path.join(LOG_DIR, "runtime.log")

# --- DEFAULT CONFIG (from config.json or default) ---
DEFAULT_CONFIG = {
    "slave_ids": [1],
    "interval": 5,
    "word_order": "ABCD",
    "registers": {
        "voltage_v1":       {"addr": 6,  "type": "float32", "scale": 1.0},
        "current_a1":       {"addr": 8,  "type": "float32", "scale": 1.0},
        "active_power_w1":  {"addr": 10, "type": "float32", "scale": -1000.0},
        "power_factor_pf1": {"addr": 34, "type": "float32", "scale": 1.0},
        "frequency_hz":     {"addr": 54, "type": "float32", "scale": 1.0},
        "energy_kwh":       {"addr": 56, "type": "float32", "scale": 0.01}
    },
    "serial": {"baudrate": 9600, "timeout": 1.0}
}

# --- UTILITIES ---
def c(txt, color):
    """Utility for color-coding terminal output."""
    colors = {"g":"\033[92m","y":"\033[93m","r":"\033[91m","c":"\033[96m","reset":"\033[0m"}
    return f"{colors.get(color,'')}{txt}{colors['reset']}"

def log_runtime(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line)
    try:
        with open(RUNTIME_LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

def calc_crc(data):
    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc.to_bytes(2, "little")

def build_poll_frame(slave, start, qty):
    frame = bytes([slave, 3, (start >> 8) & 0xFF, start & 0xFF, (qty >> 8) & 0xFF, qty & 0xFF])
    return frame + calc_crc(frame)

def validate_response(frame, slave, func):
    return len(frame) >= 5 and calc_crc(frame[:-2]) == frame[-2:] and frame[0] == slave and frame[1] == func

def reorder_words(raw4, order="ABCD"):
    mapping = {"A":0,"B":1,"C":2,"D":3}
    return bytes([raw4[mapping[c]] for c in order])

def read_full_response(ser, slave, func, timeout=1.0):
    buf = bytearray()
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if ser.in_waiting:
                buf.extend(ser.read(ser.in_waiting))
            else:
                time.sleep(0.01)
        except serial.SerialException:
            break
        if len(buf) >= 5:
            byte_count = buf[2]
            expected_len = 1 + 1 + 1 + byte_count + 2
            if len(buf) >= expected_len:
                return bytes(buf[:expected_len])
    return bytes(buf)

# --- SIGNAL HANDLING ---
terminate = False
def handle_sig(sig, frame):
    global terminate
    log_runtime(f"[SIGNAL] Received {sig}, shutting down gracefully...")
    terminate = True

signal.signal(signal.SIGINT, handle_sig)
signal.signal(signal.SIGTERM, handle_sig)

# --- CORE ---
def find_port():
    ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/tty.usbserial*")
    return ports[0] if ports else None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    debug = args.debug

    # Load config (simple version)
    cfg = DEFAULT_CONFIG.copy()
    
    SLAVE = cfg["slave_ids"][0]
    WORD_ORDER = cfg["word_order"]
    REGISTERS = cfg["registers"]
    INTERVAL = cfg["interval"]
    BAUD = cfg["serial"]["baudrate"]
    TIMEOUT = cfg["serial"]["timeout"]

    # These are the register blocks to read
    READ_BLOCKS = [
        (6, 6),   # Reads 6, 7, 8, 9, 10, 11 (V, I, W)
        (34, 2),  # Reads 34, 35 (PF)
        (54, 4)   # Reads 54, 55, 56, 57 (Hz, kWh)
    ]

    log_runtime(f"[START] Smart Meter Logger started (interval={INTERVAL}s)")
    current_day = datetime.now().strftime("%Y-%m-%d")
    fname = os.path.join(LOG_DIR, f"meter_log_{current_day}.csv")
    
    # Write CSV header if file is new
    if not os.path.exists(fname):
        with open(fname, "w", newline="") as f:
            csv.writer(f).writerow(["timestamp","date","meter_id"] + list(REGISTERS.keys()))

    ser = None
    
    def open_serial():
        port = find_port()
        if not port:
            log_runtime("[ERROR] No USB serial device found.")
            return None
        try:
            s = serial.Serial(port, BAUD, timeout=TIMEOUT)
            log_runtime(f"[OK] Connected to {port} at {BAUD} baud")
            return s
        except Exception as e:
            log_runtime(f"[ERROR] Could not open serial port: {e}")
            return None

    ser = open_serial()

    while not terminate:
        cycle_start_time = time.time()
        timestamp = datetime.now()
        date_str = timestamp.strftime("%Y-%m-%d")

        # --- Daily file rotation ---
        if date_str != current_day:
            current_day = date_str
            fname = os.path.join(LOG_DIR, f"meter_log_{current_day}.csv")
            if not os.path.exists(fname):
                with open(fname, "w", newline="") as f:
                    csv.writer(f).writerow(["timestamp","date","meter_id"] + list(REGISTERS.keys()))
                log_runtime(f"[NEW FILE] Started logging to {fname}")

        # --- Serial connection handling ---
        if ser is None or not ser.is_open:
            log_runtime("[WARN] Serial port not open — reconnecting...")
            ser = open_serial()
            if ser is None:
                time.sleep(5) # Wait before retrying
                continue
        
        # --- Read and Decode Data ---
        try:
            register_map = {}
            read_ok = True
            for start, qty in READ_BLOCKS:
                frame = build_poll_frame(SLAVE, start, qty)
                ser.reset_input_buffer()
                ser.write(frame)
                time.sleep(0.1)
                raw = read_full_response(ser, SLAVE, 0x03, timeout=TIMEOUT)
                
                if debug and raw:
                    print(c(f"[DEBUG] Frame ({start}, qty={qty}): {raw.hex()}", "y"))

                if not (raw and validate_response(raw, SLAVE, 0x03)):
                    log_runtime(f"[ERROR] Invalid or empty response for block at {start}")
                    read_ok = False
                    break
                
                payload = raw[3:-2]
                for i in range(qty):
                    register_map[start + i] = payload[i*2:i*2+2]
                time.sleep(0.05)
            
            if not read_ok:
                raise serial.SerialException("Incomplete data read from meter")

            # --- Decode values from the map ---
            row_values = {}
            for key, meta in REGISTERS.items():
                addr = meta["addr"]
                val = None
                if addr in register_map and (addr + 1) in register_map:
                    raw4 = register_map[addr] + register_map[addr + 1]
                    order = meta.get("word_order", WORD_ORDER)
                    try:
                        val = struct.unpack(">f", reorder_words(raw4, order))[0]
                        val *= meta.get("scale", 1.0)
                        row_values[key] = round(val, 3)
                    except (struct.error, IndexError) as e:
                        log_runtime(f"[ERROR] Could not decode {key}: {e}")
                        row_values[key] = ""
                else:
                    row_values[key] = ""

            # --- 1. Print to Terminal ---
            print(c(f"{timestamp.strftime('%H:%M:%S')} → " +
                    " | ".join(f"{k}={v}" for k, v in row_values.items()), "g"))

            # --- 2. Write to CSV ---
            if all(v != "" for v in row_values.values()):
                row = [timestamp.strftime("%Y-%m-%d %H:%M:%S"), date_str, SLAVE] + [row_values[k] for k in REGISTERS.keys()]
                with open(fname, "a", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(row)
                    f.flush()
                    os.fsync(f.fileno())

        except serial.SerialException as e:
            log_runtime(f"[ERROR] Serial I/O: {e}")
            if ser: ser.close()
            ser = None
        except Exception as e:
            log_runtime(f"[ERROR] Unexpected: {e}")

        # --- Interval wait ---
        time_spent = time.time() - cycle_start_time
        wait_time = max(0, INTERVAL - time_spent)
        for _ in range(int(wait_time / 0.1)):
             if terminate:
                 break
             time.sleep(0.1)
        if terminate:
            break

    try:
        if ser and ser.is_open:
            ser.close()
    except: pass
    log_runtime("[STOP] Smart Meter Logger stopped.")

if __name__ == "__main__":
    main()
