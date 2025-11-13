import sqlite3
import os
import random
from datetime import datetime, timedelta

# --- Configuration ---
OLD_DB_NAME = 'log_files/smart_meter.db'
NEW_DB_NAME = 'campus_energy_multi.db'

# --- Main Execution ---
def main():
    print(f"Starting database migration (FINAL v3 - SUBTRACTING 5.5 HOURS)...")
    if not os.path.exists(OLD_DB_NAME):
        print(f"Error: Old database '{OLD_DB_NAME}' not found.")
        return
    if os.path.exists(NEW_DB_NAME):
        print(f"Found existing '{NEW_DB_NAME}'. Deleting it to start fresh...")
        os.remove(NEW_DB_NAME)
    try:
        create_new_database()
        print(f"Reading data from '{OLD_DB_NAME}'...")
        old_data = read_old_data()
        if not old_data:
            print("No data found in the old database. Exiting.")
            return
        print(f"Read {len(old_data)} records from old database.")
        print("Correcting timestamps (subtracting 5.5h) and simulating meters...")
        new_readings = process_and_simulate(old_data)
        print(f"Generated {len(new_readings)} total records for 3 meters.")
        print(f"Writing all data to '{NEW_DB_NAME}'...")
        write_new_data(new_readings)
        print("\n✅ Success! Created '{NEW_DB_NAME}' with corrected 9-5 timestamps.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        if os.path.exists(NEW_DB_NAME):
            os.remove(NEW_DB_NAME)

# --- Database Functions ---
def create_new_database():
    print(f"Creating new database: '{NEW_DB_NAME}'")
    conn = sqlite3.connect(NEW_DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE meter_hierarchy (
            meter_id INTEGER PRIMARY KEY,
            block_name TEXT NOT NULL,
            lab_name TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE meter_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meter_id INTEGER NOT NULL,
            timestamp DATETIME NOT NULL,
            voltage REAL,
            current REAL,
            power REAL,
            energy_wh_interval REAL,
            energy_wh_total REAL,
            pf REAL,
            FOREIGN KEY (meter_id) REFERENCES meter_hierarchy (meter_id)
        )
    ''')
    hierarchy_data = [
        (1, 'Block A', 'Lab 1 (Original)'),
        (2, 'Block A', 'Lab 2 (Simulated 0.8x)'),
        (3, 'Block B', 'Lab 3 (Simulated 1.2x)')
    ]
    cursor.executemany('INSERT INTO meter_hierarchy VALUES (?, ?, ?)', hierarchy_data)
    conn.commit()
    conn.close()

def read_old_data():
    conn = sqlite3.connect(OLD_DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT timestamp, voltage_v1, current_a1, active_power_w1, energy_wh_interval 
        FROM readings 
        ORDER BY timestamp ASC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return rows

def write_new_data(new_readings):
    conn = sqlite3.connect(NEW_DB_NAME)
    cursor = conn.cursor()
    insert_query = '''
        INSERT INTO meter_readings 
        (meter_id, timestamp, voltage, current, power, energy_wh_interval, energy_wh_total, pf)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    '''
    cursor.executemany(insert_query, new_readings)
    conn.commit()
    conn.close()

# --- Data Processing Function  ---
def process_and_simulate(old_data):
    all_new_readings = []
    
    # This is the 5.5 hour offset we will subtract
    ist_offset = timedelta(hours=5, minutes=30)
    
    for row in old_data:
        ts_str, voltage_v1, current_a1, active_power_w1, energy_wh_interval_original = row
        
        # --- 1. Handle Timestamp  ---
        try:
            # Try parsing with microseconds
            dt_naive_bad = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S.%f')
        except ValueError:
            # Fallback to parsing without microseconds
            try:
                dt_naive_bad = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                print(f"Skipping bad timestamp: {ts_str}")
                continue # Skip this row if timestamp is unreadable
        
        dt_corrected = dt_naive_bad - ist_offset
        
        # Format it back to a string
        timestamp_str = dt_corrected.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        # ---  ---
        
        pf = round(random.uniform(0.85, 0.95), 2)
        
        # Meter 1 (Original)
        all_new_readings.append((
            1, timestamp_str, voltage_v1, current_a1, active_power_w1, 
            energy_wh_interval_original, None, pf
        ))
        
        # Meter 2 (Simulated 0.8x with Jitter)
        jitter_2 = random.uniform(0.95, 1.05) 
        current_2 = round(current_a1 * 0.8 * jitter_2, 2)
        power_2 = round(active_power_w1 * 0.8 * jitter_2, 2)
        energy_wh_interval_2 = round(energy_wh_interval_original * 0.8 * jitter_2, 4)
        all_new_readings.append((
            2, timestamp_str, voltage_v1, current_2, power_2, 
            energy_wh_interval_2, None, pf
        ))

        # Meter 3 (Simulated 1.2x with Jitter)
        jitter_3 = random.uniform(0.95, 1.05)
        current_3 = round(current_a1 * 1.2 * jitter_3, 2)
        power_3 = round(active_power_w1 * 1.2 * jitter_3, 2)
        energy_wh_interval_3 = round(energy_wh_interval_original * 1.2 * jitter_3, 4)
        all_new_readings.append((
            3, timestamp_str, voltage_v1, current_3, power_3, 
            energy_wh_interval_3, None, pf
        ))
    return all_new_readings

if __name__ == "__main__":
    main()
