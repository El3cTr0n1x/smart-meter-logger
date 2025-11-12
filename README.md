# Smart Energy Meter Logger & Analytics Dashboard

This is a university project to log and analyze energy data from a physical smart meter. The system is designed to simulate a multi-meter campus environment for demonstration purposes.

The project consists of two main components:
1. **`main.py` (Logger):** A robust Python script that reads live data from a physical Modbus meter. It logs this data as "Meter 1" and simultaneously generates live, scaled, and jittered simulated data for "Meter 2" and "Meter 3".
2. **`analytics_dashboard.py` (Dashboard):** A Streamlit web application that reads directly from the local SQLite database. It displays live metrics, historical analytics (by weekday, by hour), and detailed power profiles for all three meters.

This architecture replaces a previous, more complex system that relied on Firebase and a separate Flask API.

---

## ⚡ Features

* **Live Data Logging:** Connects to any serial Modbus device to read registers.  
* **Robust Energy Calculation:** Manually calculates `energy_wh_interval` from `active_power` readings, bypassing faulty meter registers.  
* **Live Multi-Meter Simulation:** Reads from one real meter and generates live, realistic data for two additional simulated meters.  
* **Local-First Analytics:** All data is logged and read from a local `campus_energy_multi.db` SQLite database.  
* **Rich Analytics Dashboard:**
  * High-level KPI metrics (Today, This Week, This Month)
  * Total consumption breakdown by meter
  * Historical “Total Energy Per Day” bar chart
  * “Day of Week” and “Hour of Day” analysis to find peak usage
  * Detailed, zoomable power-draw graphs for any selected day

---

## 🧠 Technology Stack

* **Core:** Python 3  
* **Logger:** `pyserial`, `paho-mqtt`  
* **Database:** SQLite3  
* **Dashboard:** `streamlit`  
* **Analytics:** `pandas`  
* **Plotting:** `plotly`  

---

## 📁 Project Structure

```text
SMART_METER/
│
├── main.py                 # The live logger (reads from meter, simulates 2–3, logs to DB)
├── analytics_dashboard.py  # The Streamlit analytics dashboard
├── create_sim_database.py  # One-time script to build the DB from old data
├── requirements.txt        # Python dependencies for the project
│
├── .gitignore              # Ensures database files and logs are not committed
├── campus_energy_multi.db  # The analytics database (NOT tracked by Git)
└── log_files/              # Folder containing old 'smart_meter.db' (NOT tracked by Git)

---

## 🚀 How to Run

### 1. First-Time Setup

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/El3cTr0n1x/smart-meter-logger.git
   cd smart-meter-logger
   ```

2. **Create a Virtual Environment:**

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Create the Database:**

   * Place your original `smart_meter.db` inside the `log_files/` folder.
   * Run:

     ```bash
     python3 create_sim_database.py
     ```
   * This will generate `campus_energy_multi.db` with all historical and simulated data.

---

### 2. Running the Application

Run these two services in separate terminals.

**Terminal 1 – Logger (connects to meter):**

```bash
python3 main.py
```

*Shows connection logs and records data every 5 seconds.*

**Terminal 2 – Dashboard:**

```bash
streamlit run analytics_dashboard.py
```

*Opens a local analytics dashboard in your browser.*

---

*Updated: **2025-11-12** — Local-first analytics architecture.*

````

---

### ✅ `requirements.txt`

```text
# Python dependencies for the Smart Meter Logger & Analytics Dashboard

# --- For main.py (Logger) ---
pyserial       # For serial/Modbus communication
paho-mqtt      # For MQTT publishing

# --- For analytics_dashboard.py (Dashboard) ---
streamlit      # Web dashboard framework
pandas         # Data manipulation and analytics
plotly         # Interactive plotting

# --- For create_sim_database.py (Setup Script) ---
pytz           # Timezone conversion during DB creation
````

---

### ✅ Commands to commit and push

```bash
git add README.md requirements.txt
git commit -m "docs: update README and consolidate requirements"
git push origin main
```

---
