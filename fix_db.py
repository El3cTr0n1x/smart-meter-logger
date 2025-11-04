#!/usr/bin/env python3
"""
fix_db.py (One-Time-Use Script)

This script repairs the smart_meter.db database.
It finds all rows with a corrupted '-m-' timestamp
and replaces it with the correct '-10-'.
"""

import sqlite3
import os
import sys

# --- CONFIGURATION ---
LOG_DIR = "log_files"
DB_FILE = os.path.join(LOG_DIR, "smart_meter.db")

def repair_database():
    """
    Connects to the DB, finds all corrupted rows,
    and attempts to fix them.
    """
    if not os.path.exists(DB_FILE):
        print(f"Error: Database file not found at {DB_FILE}")
        sys.exit(1)

    print(f"Connecting to database at {DB_FILE}...")
    con = None
    try:
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()

        # 1. Find all corrupted rows
        cur.execute("SELECT timestamp FROM readings WHERE timestamp LIKE '%-m-%'")
        # .fetchall() is safe here since it's a one-time script
        corrupted_rows = cur.fetchall() 

        if not corrupted_rows:
            print("✅ No corrupted timestamps found. Database is already clean!")
            con.close()
            return

        print(f"Found {len(corrupted_rows)} rows with a corrupted '-m-' timestamp.")
        
        fixed_count = 0
        deleted_count = 0

        # 2. Loop through each bad row and fix it
        for row in corrupted_rows:
            old_ts = row[0]
            new_ts = old_ts.replace('-m-', '-10-')

            try:
                # 3. Check if a GOOD row with this timestamp already exists
                # (from data logged *after* we fixed main.py)
                cur.execute("SELECT 1 FROM readings WHERE timestamp = ?", (new_ts,))
                exists = cur.fetchone()

                if exists:
                    # 4. If it exists, the old row is a duplicate. Delete it.
                    cur.execute("DELETE FROM readings WHERE timestamp = ?", (old_ts,))
                    deleted_count += 1
                else:
                    # 5. If it doesn't exist, we can safely UPDATE the old row's key
                    cur.execute("UPDATE readings SET timestamp = ? WHERE timestamp = ?", (new_ts, old_ts))
                    fixed_count += 1

            except sqlite3.Error as e:
                print(f"  [Warning] Could not process {old_ts}: {e}. Skipping.")

        # 6. Commit all changes to the database
        con.commit()
        
        print("\n--- Repair Complete ---")
        print(f"✅ Fixed (updated) {fixed_count} rows.")
        print(f"🗑️  Deleted {deleted_count} duplicate rows.")
        print("Your database is now clean.")

    except sqlite3.Error as e:
        print(f"\nAn error occurred: {e}")
        if con:
            con.rollback() # Roll back any changes if an error occurred
    finally:
        if con:
            con.close()
            print("Database connection closed.")

if __name__ == "__main__":
    repair_database()
