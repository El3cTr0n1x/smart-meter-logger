# Smart Meter Test Project

A practical toolkit for polling a Modbus-capable smart meter over USB/RS485, logging register data into CSV, and performing daily analysis with summaries and plots.

## Project layout

smart-meter-test/
├── main.py          # Primary logger (auto-detect port, logs to master CSV)
├── dump.py          # Register explorer (scans registers, word orders, scaling)
├── analyzer.py      # Analyzer (daily summaries, anomalies, plots per meter/day)
├── config.json      # Config file (registers, slave IDs, logging settings)
├── requirements.txt # Python dependencies
├── runner.sh        # Wrapper: runs main.py, then analyzer.py automatically
├── log_files/       # Generated CSV logs + plots
│   ├── meter_log_master.csv   # Master log (all meters, all dates)
│   ├── daily_summary.csv      # Auto-generated daily summary
│   ├── anomalies.csv          # Auto-detected anomalies
│   └── plots/                 # Auto-saved plots (PNG)
└── venv/            # Virtual environment (not checked in)



## Requirements

- Python 3.8+ (tested on Python 3.10, macOS/Linux/Windows)
- Virtual environment recommended

Python Packages

pyserial (serial comms)
pymodbus (Modbus helper, optional)
pandas (data analysis)
matplotlib (plots)
jupyter (optional, for notebooks)

Create a .txt file(requirements.txt) and paste the above packages in that file, these will be installed later.

Install inside venv:

python -m venv venv
source venv/bin/activate      # macOS / Linux
.\venv\Scripts\activate       # Windows

pip install -r requirements.txt


# System-level (for USB–RS485)

macOS
brew install libusb

Linux (Debian/Ubuntu)
sudo apt update
sudo apt install libusb-1.0-0

Windows

Use Zadig to install a WinUSB/libusb driver for your USB–serial adapter:
Download Zadig.
Plug in your meter cable.
Options → List All Devices.
Choose your device; pick WinUSB/libusb and install.
For CH340/CP210x/FTDI adapters, ensure the driver is installed.

# Configuration

main.py and dump.py auto-detect ports:

macOS: /dev/tty.usbserial*, /dev/tty.SLAB*
Linux: /dev/ttyUSB*
Windows: COM*

If auto-detect fails, edit find_port() in scripts or hardcode your port.

Default Modbus unit ID: SLAVE_ID = 1

Registers & settings are defined in config.json:

{
  "slave_ids": [1],
  "interval": 5,
  "duration": 60,
  "word_order": "ABCD",
  "scale": 1.0,
  "registers": {
    "voltage_v1":        { "addr": 30, "type": "float32", "scale": 1.0 },
    "current_a1":        { "addr": 40, "type": "float32", "scale": 1.0 },
    "active_power_w1":   { "addr": 50, "type": "float32", "scale": 1.0 },
    "reactive_power_var1": { "addr": 60, "type": "float32", "scale": 1.0 },
    "power_factor_pf1":  { "addr": 70, "type": "float32", "scale": 1.0 },
    "frequency_hz":      { "addr": 80, "type": "float32", "scale": 1.0 },
    "energy_kwh":        { "addr": 100, "type": "float32", "scale": 0.001 }
  }
}


# How to run

All run from project root with venv active.

1. Log real-time data

Starts logging and appends to log_files/meter_log_master.csv:

python main.py

Console output:

2025-09-28 11:21:17 | V=227.43 V | f=50.01 Hz | I=2.27 A | P=710.9 W | E=1.28 kWh

2. Dump registers (debug)

Explores raw registers, word orders, and scaling:

python dump.py

Output: log_files/meter_dump_*.csv.

3. Analyze logs

Generates daily summaries + plots (auto for all dates, all meters):

python analyzer.py

Daily summary → log_files/daily_summary.csv
Plots → log_files/plots/plot_<date>_meter<meter_id>.png

Sample summary:

=== DAILY SUMMARY ===
              voltage_avg  current_avg  power_avg  freq_avg  energy_total
date       meter_id
2025-09-24 1        227.3        2.27     591.8     50.02          0.023

4. Run everything automatically

./runner.sh

Starts logger (main.py)
Runs analyzer after logging finishes
Outputs CSVs + plots in log_files/


# Output format

main.py CSV(meter_log_master.csv):
timestamp,date,meter_id,voltage_v1,frequency_hz,current_a1,active_power_w1,total_energy_kwh,delta_energy_kwh

dump.py CSV
timestamp,func,reg,order,scale,value

analyzer.py Summary (daily_summary.csv)
date,meter_id,voltage_avg,voltage_min,voltage_max,current_avg,power_avg,freq_avg,energy_total delta_energy_total


# Troubleshooting

No serial port found → check cable/driver.

macOS: ls /dev/tty.*
Linux: ls /dev/ttyUSB*
Windows: Device Manager → Ports

Device busy → close other serial programs (Arduino IDE, screen, etc.).

Import error (pandas/matplotlib) → install in the active venv.

libusb errors → install system package (see above).

# Recommended workflow

Run dump.py once to explore registers/word orders.
Run main.py to log data into the master CSV.
Run analyzer.py to generate plots & summaries.
Expand config.json when adding new meters or registers.
