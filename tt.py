import serial
import time

ser = serial.Serial(
    port='/dev/ttyUSB0',     # <-- This is correct for your setup
    baudrate=9600,           # Adjust if your device uses a different baud rate
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=1                # 1-second read timeout
)

print("Connected to /dev/ttyUSB0")

try:
    while True:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            print(f"Received: {line}")
        else:
            time.sleep(0.1)
except KeyboardInterrupt:
    print("Exiting...")
finally:
    ser.close()
