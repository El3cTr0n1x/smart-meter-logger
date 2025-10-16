#!/usr/bin/env python3
"""
dump.py — CH340-safe Modbus register scanner

Fixes:
- Adds delay between requests (prevents I/O error)
- Auto-reconnects if port resets
- Cleanly handles serial exceptions
"""

import csv, os, time, glob, serial, struct, itertools
from datetime import datetime

BAUDRATE = 9600
SLAVE_ID = 1
SCAN_START = 0x0000
SCAN_END = 0x0040
SCALES = [1.0, 0.1, 0.01, 0.001]
ALL_ORDERS = ["".join(p) for p in itertools.permutations("ABCD")]

LOG_DIR = "log_files"
os.makedirs(LOG_DIR, exist_ok=True)

def find_port():
    ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/tty.usbserial*")
    return ports[0] if ports else None

def calc_crc(data):
    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) else (crc >> 1)
    return crc.to_bytes(2, "little")

def build_poll_frame(slave, start, qty, func=0x03):
    frame = bytes([slave, func, (start>>8)&0xFF, start&0xFF, (qty>>8)&0xFF, qty&0xFF])
    return frame + calc_crc(frame)

def validate_response(frame, slave, func):
    return len(frame) >= 5 and calc_crc(frame[:-2]) == frame[-2:] and frame[0] == slave and frame[1] == func

def reorder_words(raw4, order="ABCD"):
    mapping = {"A":0,"B":1,"C":2,"D":3}
    return bytes([raw4[mapping[c]] for c in order])

def decode_float(payload, offset, order="ABCD"):
    chunk = payload[offset:offset+4]
    if len(chunk) != 4:
        return None
    try:
        return struct.unpack(">f", reorder_words(chunk, order))[0]
    except:
        return None

def read_full_response(ser, slave, func, timeout=1.0):
    buf = bytearray()
    end_time = time.time() + timeout
    while time.time() < end_time:
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

def looks_reasonable(val):
    return (
        180 <= val <= 260 or
        45 <= val <= 55 or
        0 <= val <= 10 or
        -5000 <= val <= 5000 or
        0 <= val <= 1.2
    )

def open_serial():
    port = find_port()
    if not port:
        print("[ERROR] No USB port found.")
        return None
    try:
        s = serial.Serial(port, BAUDRATE, timeout=1)
        print(f"[OK] Connected to {port} at {BAUDRATE} baud")
        return s
    except Exception as e:
        print(f"[ERROR] Could not open serial port: {e}")
        return None

def main():
    fname = os.path.join(LOG_DIR, f"meter_dump_clean_{datetime.now():%Y-%m-%d_%H-%M-%S}.csv")
    with open(fname, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp","func","reg","order","scale","value"])

    ser = open_serial()
    if not ser:
        return

    try:
        for func in (0x03, 0x04):
            print(f"[SCAN] Function code 0x{func:X}")
            for reg in range(SCAN_START, SCAN_END, 2):
                frame = build_poll_frame(SLAVE_ID, reg, 2, func)
                try:
                    ser.write(frame)
                    time.sleep(0.2)
                    raw = read_full_response(ser, SLAVE_ID, func, timeout=0.5)
                    if not raw or not validate_response(raw, SLAVE_ID, func):
                        continue
                    payload = raw[3:-2]
                    best = None
                    for order in ALL_ORDERS:
                        val = decode_float(payload, 0, order)
                        if val is None:
                            continue
                        for scale in SCALES:
                            v = val * scale
                            if looks_reasonable(v):
                                best = (order, scale, v)
                                break
                        if best:
                            break
                    if best:
                        order, scale, v = best
                        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        print(f"[FOUND] func=0x{func:X}, reg=0x{reg:X}, order={order}, scale={scale}, val={v}")
                        with open(fname, "a", newline="") as f:
                            csv.writer(f).writerow([ts, func, hex(reg), order, scale, v])
                    time.sleep(0.2)
                except serial.SerialException:
                    print("[WARN] Serial I/O error, reconnecting...")
                    ser.close()
                    time.sleep(1)
                    ser = open_serial()
                    if not ser:
                        return
    except KeyboardInterrupt:
        print("[STOP] Interrupted by user.")
    finally:
        if ser and ser.is_open:
            ser.close()
        print(f"[DONE] Clean dump saved → {fname}")

if __name__ == "__main__":
    main()
