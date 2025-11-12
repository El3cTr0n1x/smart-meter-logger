import sqlite3
import os
import datetime
import pytz
import random

# --- Configuration ---
OLD_DB_NAME = 'log_files/smart_meter.db'
NEW_DB_NAME = 'campus_energy_multi.db'
TIMEZONE_IST = pytz.timezone('Asia/Kolkata')
TIMEZONE_UTC = pytz.utc

# --- Main Execution ---

def main():
    """Main function to run the entire migration and simulation process."""
    
    print(f"Starting database migration and simulation...")

    # 1. Check if the old database exists
    if not os.path.exists(OLD_DB_NAME):
        print(f"Error: Old database '{OLD_DB_NAME}' not found.")
        print("Please place this script in the same directory as your database.")
        return

    # 2. Check and delete the new database if it already exists
    if os.path.exists(NEW_DB_NAME):
        print(f"Found existing '{NEW_DB_NAME}'. Deleting it to start fresh...")
        os.remove(NEW_DB_NAME)

    try:
        # 3. Create new database and tables
        create_new_database()

        # 4. Read data from the old database
        print(f"Reading data from '{OLD_DB_NAME}'...")
        old_data = read_old_data()
        if not old_data:
            print("No data found in the old database. Exiting.")
            return
        print(f"Read {len(old_data)} records from old database.")
        
        # 5. Process old data and simulate new data
        print("Processing data, converting timestamps, and simulating meters 2 & 3...")
        new_readings = process_and_simulate(old_data)
        print(f"Generated {len(new_readings)} total records for 3 meters.")

        # 6. Write the new data to the new database
        print(f"Writing all data to '{NEW_DB_NAME}'...")
        write_new_data(new_readings)

        print("\n✅ Success!")
        print(f"Created '{NEW_DB_NAME}' with 3 simulated meters and analytics-ready tables.")

    except Exception as e:
        print(f"\nAn error occurred: {e}")
        # Clean up the partial new DB if an error occurred
        if os.path.exists(NEW_DB_NAME):
            os.remove(NEW_DB_NAME)

# --- Database Functions ---

def create_new_database():
    """Creates the new SQLite file and the required table structures."""
    print(f"Creating new database: '{NEW_DB_NAME}'")
    conn = sqlite3.connect(NEW_DB_NAME)
    cursor = conn.cursor()

    # Table 1: Meter Hierarchy (The "Tree" Structure)
    cursor.execute('''
        CREATE TABLE meter_hierarchy (
            meter_id INTEGER PRIMARY KEY,
            block_name TEXT NOT NULL,
            lab_name TEXT NOT NULL
        )
    ''')
    print("Created table: 'meter_hierarchy'")

    # Table 2: Meter Readings (The Time-Series Data)
    # Using the new schema you defined
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
    print("Created table: 'meter_readings'")
    
    # Populate the hierarchy table
    hierarchy_data = [
        (1, 'Block A', 'Lab 1 (Original)'),
        (2, 'Block A', 'Lab 2 (Simulated 0.8x)'),
        (3, 'Block B', 'Lab 3 (Simulated 1.2x)')
    ]
    cursor.executemany('INSERT INTO meter_hierarchy VALUES (?, ?, ?)', hierarchy_data)
    print("Populated 'meter_hierarchy' table.")
    
    conn.commit()
    conn.close()

def read_old_data():
    """Reads all data from the old database."""
    print("Reading from old DB with corrected column names (voltage_v1, etc.)...")
    conn = sqlite3.connect(OLD_DB_NAME)
    cursor = conn.cursor()
    # Read the columns using the schema from your 'simulate_meters.py' script
    # This is the line we are fixing
    cursor.execute('''
        SELECT timestamp, voltage_v1, current_a1, active_power_w1, energy_wh_interval 
        FROM readings 
        ORDER BY timestamp ASC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return rows

def write_new_data(new_readings):
    """Writes all the processed and simulated data to the new database."""
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

# --- Data Processing Function ---

def process_and_simulate(old_data):
    """
    The core logic. Converts timestamps, simulates new meters,
    and calculates interval energy.
    
    *** UPDATED WITH RANDOM JITTER ***
    """
    all_new_readings = []
    
    # To calculate energy_wh_interval (current - last)
    last_energy_total = {1: None, 2: None, 3: None}

    for row in old_data:
        # 1. Unpack old data (based on our corrected schema)
        ts_str, voltage_v1, current_a1, active_power_w1, energy_wh_interval_original = row
        
        # --- 1. Handle Timestamp ---
        ist_timestamp_str = ts_str
        
        # --- 2. Simulate Missing Data ---
        # Simulate a realistic Power Factor (PF)
        pf = round(random.uniform(0.85, 0.95), 2)
        
        # --- 3. Generate Data for Meter 1 (Original) ---
        # We assume the 'energy_wh_interval' from the old DB is what we want to keep
        all_new_readings.append((
            1, ist_timestamp_str, voltage_v1, current_a1, active_power_w1, 
            energy_wh_interval_original, 
            None, # We don't have cumulative total energy, so we'll store None
            pf
        ))
        
        # --- 4. Generate Data for Meter 2 (Simulated 0.8x with Jitter) ---
        # Add random jitter between 0.95 and 1.05 (±5%)
        jitter_2 = random.uniform(0.95, 1.05) 
        current_2 = round(current_a1 * 0.8 * jitter_2, 2)
        power_2 = round(active_power_w1 * 0.8 * jitter_2, 2)
        energy_wh_interval_2 = round(energy_wh_interval_original * 0.8 * jitter_2, 4)

        all_new_readings.append((
            2, ist_timestamp_str, voltage_v1, current_2, power_2, 
            energy_wh_interval_2, None, pf
        ))

        # --- 5. Generate Data for Meter 3 (Simulated 1.2x with Jitter) ---
        jitter_3 = random.uniform(0.95, 1.05)
        current_3 = round(current_a1 * 1.2 * jitter_3, 2)
        power_3 = round(active_power_w1 * 1.2 * jitter_3, 2)
        energy_wh_interval_3 = round(energy_wh_interval_original * 1.2 * jitter_3, 4)
        
        all_new_readings.append((
            3, ist_timestamp_str, voltage_v1, current_3, power_3, 
            energy_wh_interval_3, None, pf
        ))

    return all_new_readings

if __name__ == "__main__":
    # This script needs 'pytz'
    # You might need to install it: pip install pytz
    main()
