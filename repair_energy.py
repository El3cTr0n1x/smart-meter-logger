#!/usr/bin/env python3
"""
repair_energy.py (One-Time-Use Script)

This script repairs the smart_meter.db database.
It finds all rows where the 'energy_wh_interval' column is NULL
and retroactively calculates the correct value based on the
'active_power_w1' reading from that same row.

This "rescues" all old data that was logged before v9.1 of main.py.
"""

import sqlite3
import os
import sys

# --- CONFIGURATION ---
LOG_DIR = "log_files"
DB_FILE = os.path.join(LOG_DIR, "smart_meter.db")
# This MUST match the INTERVAL in your main.py (which is 5 seconds)
INTERVAL_SECONDS = 5.0

def repair_energy_data():
    """
    Connects to the DB, finds all rows with NULL energy,
    and calculates the correct energy value from the power.
    """
    if not os.path.exists(DB_FILE):
        print(f"Error: Database file not found at {DB_FILE}")
        sys.exit(1)

    print(f"Connecting to database at {DB_FILE}...")
    con = None
    try:
        con = sqlite3.connect(DB_FILE)
        # Use a "row factory" to get rows as dictionaries (easier to work with)
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # 1. Find all rows that need to be fixed
        # We select rows where 'energy_wh_interval' is NULL
        # AND 'active_power_w1' is NOT NULL (so we can do the math)
        cur.execute("""
            SELECT timestamp, active_power_w1 
            FROM readings 
            WHERE energy_wh_interval IS NULL 
            AND active_power_w1 IS NOT NULL
        """)
        
        rows_to_fix = cur.fetchall()

        if not rows_to_fix:
            print("✅ No rows found with missing energy data. Database is already clean!")
            con.close()
            return

        print(f"Found {len(rows_to_fix)} rows with missing 'energy_wh_interval' data.")
        print("Beginning repair process...")
        
        fixed_count = 0
        interval_in_hours = INTERVAL_SECONDS / 3600.0
        updates_to_make = []

        # 2. Calculate the new energy value for each row
        for row in rows_to_fix:
            power_w = row['active_power_w1']
            
            # This is the same calculation from main.py
            energy_wh = power_w * interval_in_hours
            
            # We'll store all our updates in a list
            updates_to_make.append( (round(energy_wh, 5), row['timestamp']) )

        # 3. Apply all updates to the database at once
        # This is much faster than updating one row at a time
        print(f"Calculating complete. Applying {len(updates_to_make)} updates to the database...")
        sql_update = "UPDATE readings SET energy_wh_interval = ? WHERE timestamp = ?"
        
        cur.executemany(sql_update, updates_to_make)
        
        # 4. Commit all changes
        con.commit()
        fixed_count = cur.rowcount

        print("\n--- Repair Complete ---")
        print(f"✅ Successfully calculated and updated {fixed_count} rows.")
        print("Your database's historical energy data is now fully populated.")

    except sqlite3.Error as e:
        print(f"\nAn error occurred: {e}")
        if con:
            con.rollback() # Roll back any changes if an error occurred
    finally:
        if con:
            con.close()
            print("Database connection closed.")

if __name__ == "__main__":
    repair_energy_data()
