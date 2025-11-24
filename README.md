# Smart Energy Meter Logger & AI-Powered Dashboard

This project is a university-level implementation of a full-stack smart energy monitoring system. It logs live electrical data from a physical Modbus energy meter, simulates additional meters for scalability, stores all data locally in SQLite, and provides an interactive Streamlit dashboard for analytics. A built-in AI assistant (Gemini Text-to-SQL) enables natural-language querying of the database.

The system consists of three core components:
1. **`main.py` (Logger):** Reads real-time electrical parameters from a Modbus RTU meter, computes interval-based energy values, and logs everything into SQLite. It also generates simulated data for additional meters.
2. **`analytics_dashboard.py` (Dashboard):** A Streamlit UI that displays live metrics, historical trends, hourly and weekday analysis, and detailed time-series plots.
3. **`chatbot_logic.py` (AI Assistant):** Uses Google Gemini to translate natural-language questions into SQL queries, executes them locally, and returns results or visualizations.

---

## ⚡ Features

* **Live Modbus Logging:** Reads voltage, current, power, PF, and timestamps from a hardware energy meter using RS-485.
* **Accurate Energy Calculation:** Computes `energy_wh_interval` directly from power to bypass unreliable meter registers.
* **Multi-Meter Support:** Simulates two additional meters for campus-scale demonstration.
* **Local-First Database:** All data is stored and analyzed using SQLite (`campus_energy_multi.db`).
* **AI Assistant (Text-to-SQL):** Converts English questions into SQL and answers them with real data.
* **Interactive Analytics:**
  * KPI metrics for Today, This Week, and This Month  
  * Daily energy consumption charts  
  * Hour-of-day and day-of-week usage patterns  
  * Zoomable power-draw curves for any date  

---

## 🧠 Technology Stack

* **Language:** Python 3  
* **Logger:** `pyserial`, `paho-mqtt`  
* **Database:** SQLite3 (WAL mode enabled)  
* **Dashboard:** `streamlit`  
* **AI Assistant:** `google-generativeai`  
* **Analytics:** `pandas`  
* **Plotting:** `plotly`  

---

## 📁 Project Structure

```text
SMART_METER/
│
├── main.py                   # Logger (reads Modbus, simulates meters, writes to DB)
├── analytics_dashboard.py    # Streamlit dashboard
├── chatbot_logic.py          # Text-to-SQL AI assistant
├── create_sim_database.py    # Initializes or repairs the SQLite DB
│
├── campus_energy_multi.db    # Live energy database (not tracked by Git)
├── demo_data_v2.db           # Optional demo database
├── requirements.txt          # Python dependencies
└── .gitignore                # Excludes DBs, logs, and secrets

```
---

## 🚀 How to Run

### 1. First-Time Setup

1. **Clone the repository:**

```bash
git clone https://github.com/El3cTr0n1x/smart-meter-logger.git
cd smart-meter-logger
```


2. **Create a virtual environment:**

```bash
python3 -m venv venv
source venv/bin/activate
```

3. **Install dependencies:**

```bash
pip install -r requirements.txt
```

4. **Create or rebuild the database:**

* If you have an older smart_meter.db, place it inside log_files/ and run:

```bash
python3 create_sim_database.py
```

* This generates a fresh campus_energy_multi.db with real and simulated meter data.

---

### 2. Running the Application

**Terminal 1 – Logger:**

```bash
python3 main.py
```

**Terminal 2 – Dashboard:**

```bash
streamlit run analytics_dashboard.py
```

*The dashboard will open in your browser.*

---

### AI Assistant Setup

Create a Streamlit secrets file:

```bash
mkdir -p .streamlit
nano .streamlit/secrets.toml
```

Add your Gemini API key:

```bash
GOOGLE_API_KEY = "AIzaSyD...your_key_here"
```

Restart the dashboard after saving.

---

### 📈 Usage

Overview Tab: Live power readings, KPI summaries, and latest sensor values.

AI Assistant Tab: Ask natural-language questions such as:

"Which lab consumed the most energy yesterday?"

"Show voltage readings for Lab 1 today."

"Compare total cost for all labs this month."

Historical Analytics: Daily totals, hourly trends, and weekday patterns.

Detailed Analysis: View minute-level power data for any selected date.
