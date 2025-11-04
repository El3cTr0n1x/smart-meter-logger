# Campus Energy Monitoring System (Full-Stack IoT Pipeline)

This project is a complete, end-to-end IoT data pipeline that reads real-time electrical data from a Modbus RTU smart meter, processes it, and serves it to two different live dashboards.

The system is designed for robust, 24/7 operation on a Linux server, with all components managed by `systemd`.

---

## 🏛️ Project Architecture

This system is built on a 3-tier architecture to decouple the logger, data aggregator, and web server.

1.  **Tier 1: Data Logging (`main.py`)**
    * A Python script reads 5 real-time parameters (Voltage, Current, Power, etc.) from a smart meter every 5 seconds via Modbus RTU.
    * It **calculates** energy consumption (in Watt-hours) from the stable Power (W) reading, as the meter's built-in energy register was found to be unreliable.
    * This data is sent to two places:
        1.  A local **SQLite database** (`smart_meter.db`) for high-resolution local analysis.
        2.  A local **MQTT broker** (Mosquitto) for real-time data streaming.

2.  **Tier 2: Aggregation & Storage (`firebase_bridge.py`)**
    * A separate Python service listens to the MQTT topic.
    * To solve Firebase's free-tier quota limits (20k writes/day), this script **aggregates 5-second readings into 5-minute averages**.
    * This one aggregated document (containing the *sum* of energy and *average* of power) is written to a **Firebase Firestore** collection.
    * **Result:** Database writes are reduced by **98%** (from ~17,280 to ~288 per day).

3.  **Tier 3: API & Frontend (`app.py`, `index.html`)**
    * A **Flask (Gunicorn) REST API** (`app.py`) queries the `readings_5min_avg` collection in Firebase.
    * It serves this data to a simple, auto-refreshing **HTML/JavaScript dashboard** (`index.html`) that displays the campus-wide energy totals.

---

## ✨ Features

* **Real-time Modbus Data:** Polls a smart meter for 5 electrical parameters every 5 seconds.
* **Calculated Energy:** Fixes unreliable hardware by calculating energy from power (`Energy = Power × Time`).
* **Dual Dashboards:**
    1.  **Local (Streamlit):** A high-resolution dashboard (`dashboard.py`) for live debugging, powered by the local SQLite DB.
    2.  **Cloud (Web):** A low-resolution, scalable dashboard (`index.html`) for public viewing, powered by Firebase.
* **Scalable Architecture:** Uses an MQTT broker to decouple the logger from the cloud services.
* **Cost Optimization:** Reduces Firebase writes by 98% through aggregation.
* **Robust Deployment:** All 3 core Python scripts (`main.py`, `firebase_bridge.py`, `app.py`) are managed as independent, auto-restarting `systemd` services for 24/7 uptime on a Linux server.

---

## 📁 Repository Structure
smart-meter-logger/ │ ├── main.py # (Service 1) The Modbus logger ├── firebase_bridge.py # (Service 2) The MQTT-to-Firebase aggregator ├── dashboard.py # The local Streamlit dashboard ├── fix_db.py # Utility to repair corrupted timestamps ├── requirements.txt # Python libraries for the logger │ ├── campus-dashboard-backend/ │ ├── app.py # (Service 3) The Flask API server │ ├── index.html # The public-facing web dashboard │ ├── requirements.txt # Python libraries for the API │ └── .gitignore # Ignores credentials and venv for the API │ ├── .gitignore # Main gitignore (ignores local DB, logs, venv, keys) └── README.md # This file

---

## 🛠️ Key Technologies

* **Languages:** Python (Flask, Pandas, Streamlit), SQL, HTML/JS
* **Platforms & Databases:** Linux, Firebase (Firestore), SQLite, MQTT
* **DevOps & Tools:** `systemd`, Gunicorn, Git
* **Protocols:** Modbus RTU
