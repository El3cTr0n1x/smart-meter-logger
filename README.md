# ⚡ Real-Time Smart Meter Logger & Live Dashboard

This project is a resilient, real-time energy monitoring system designed to log data from a Modbus-enabled smart meter, store it in a local SQLite database, and visualize the findings on an interactive web dashboard. It was developed to analyze and understand the detailed power consumption patterns of a university lab environment.

The system runs as a robust background service on Ubuntu Linux, capable of automatically recovering from power outages and system reboots, ensuring continuous and reliable data collection.



---

## Features

-   **Real-Time Logging:** Captures data at a configurable interval (currently 2 seconds) from a single-phase smart meter via the Modbus RTU protocol.
-   **Resilient Operation:** Runs as a `systemd` service, automatically restarting on boot or after a power failure, providing a true "set it and forget it" logging solution.
-   **Efficient Database Storage:** Uses a local SQLite database (`smart_meter.db`) for fast, reliable, and long-term storage of time-series data.
-   **Live Interactive Dashboard:** A web-based dashboard built with Streamlit that auto-refreshes to display:
    -   Live readings for Power, Voltage, Current, and Frequency.
    -   Key performance indicators (KPIs) for daily, weekly, and monthly energy consumption (kWh).
    -   Historical charts showing daily usage trends and average power draw by the hour.

---

## System Architecture

The project consists of two primary, independent components that communicate through the central database:

1.  **The Logger (`main.py`):** A persistent background `systemd` service that continuously polls the smart meter. It's responsible for handling the Modbus communication, decoding the data, and writing every new reading into the SQLite database.
2.  **The Database (`smart_meter.db`):** A single SQLite file that acts as the central data store. It decouples the logger from the dashboard, allowing either to be restarted without affecting the other.
3.  **The Dashboard (`dashboard.py`):** A Streamlit web application that reads data from the database. It performs on-the-fly analysis and visualization, providing an interactive, near-real-time view of the lab's energy consumption.

---

## Tech Stack

-   **Hardware:** Single-Phase Modbus Smart Meter, USB-to-RS485 Converter (CH340 chipset).
-   **Backend:** Python, `pyserial` for hardware communication, SQLite3 for data storage.
-   **Dashboard:** Streamlit, Pandas for data manipulation, Plotly for interactive charts.
-   **Deployment:** `systemd` on Ubuntu Linux for robust background service management.

---

## Getting Started

Follow these steps to set up and run the project on a new Ubuntu machine.

### 1. Prerequisites

Your user must have permission to access serial devices. Run this command, then **log out and log back in**.
```bash
sudo usermod -a -G $USER dialout
```

### 2. Clone & Setup

Clone this repository and set up the Python virtual environment.
```bash
git clone [https://github.com/El3cTr0n1x/smart-meter-logger.git](https://github.com/El3cTr0n1x/smart-meter-logger.git)
cd smart-meter-logger

# Create and activate the virtual environment
python3 -m venv venv
source venv/bin/activate

# Install all required libraries
pip install -r requirements.txt
```

### 3. Configure the Logger Service

The logger is designed to run as a `systemd` service for maximum reliability.

**a. Create the Service File:**
```bash
sudo nano /etc/systemd/system/smart-meter-logger.service
```

**b. Paste the following configuration.** The paths are already set for the user `mars`. If your username or project path is different, you must update them here.
```ini
[Unit]
Description=Smart Meter Logger Service
After=network.target

[Service]
User=mars
Group=dialout
WorkingDirectory=/home/mars/SMART_METER
ExecStart=/home/mars/SMART_METER/venv/bin/python3 /home/mars/SMART_METER/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**c. Enable and Start the Service:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable smart-meter-logger.service
sudo systemctl start smart-meter-logger.service
```

### 4. Verify the Logger

Check that the service is running correctly.
```bash
sudo systemctl status smart-meter-logger.service
```
You should see a green `active (running)` status. You can view its live output with:
```bash
journalctl -u smart-meter-logger.service -f
```

### 5. Launch the Dashboard

With the logger running in the background, you can now launch the Streamlit web app.
```bash
# Make sure your venv is active
source venv/bin/activate

# Run the dashboard
streamlit run dashboard.py
```
Your default web browser will open, and the dashboard will be available at **`http://localhost:8501`**.

---

## Legacy Scripts

This repository also contains older scripts from the initial development phase (e.g., `analyzer.py`, `dump.py`). These were used for CSV-based logging and initial meter discovery and are no longer part of the primary live-monitoring workflow.
