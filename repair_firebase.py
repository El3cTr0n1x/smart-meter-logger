#!/usr/bin/env python3
"""
repair_firebase.py (v1.1 - Fixed Data Types)

- [FIX] Converts Firebase's datetime objects into strings
  (e.g., '2025-11-10 14:30:00.123') before querying SQLite.
- This fixes the 'unsupported type' binding error.
"""

import sqlite3
import os
import sys
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# --- CONFIGURATION ---
LOG_DIR = "log_files"
DB_FILE = os.path.join(LOG_DIR, "smart_meter.db")
SERVICE_ACCOUNT_KEY = "service-account-key.json"
COLLECTION_NAME = "readings_5min_avg"

def log_runtime(msg):
    """Prints a message with a timestamp."""
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}")

def repair_firebase_data():
    """Finds and fixes all corrupted documents in the Firebase collection."""

    # --- 1. Connect to Firebase ---
    log_runtime(f"Connecting to Firebase with key: {SERVICE_ACCOUNT_KEY}")
    if not os.path.exists(SERVICE_ACCOUNT_KEY):
        log_runtime(f"❌ ERROR: Firebase service account key not found.")
        sys.exit(1)
    try:
        cred = credentials.Certificate(SERVICE_ACCOUNT_KEY)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db_firebase = firestore.client()
        collection_ref = db_firebase.collection(COLLECTION_NAME)
        log_runtime("✅ Firebase connection established.")
    except Exception as e:
        log_runtime(f"❌ FAILED TO INITIALIZE FIREBASE: {e}")
        sys.exit(1)

    # --- 2. Connect to Local SQLite DB ---
    log_runtime(f"Connecting to local database at {DB_FILE}...")
    if not os.path.exists(DB_FILE):
        log_runtime(f"❌ ERROR: Local database file not found.")
        sys.exit(1)

    con_sqlite = None
    try:
        con_sqlite = sqlite3.connect(DB_FILE)
        con_sqlite.row_factory = sqlite3.Row
        cur_sqlite = con_sqlite.cursor()
        log_runtime("✅ Local SQLite DB connection established.")
    except sqlite3.Error as e:
        log_runtime(f"❌ FAILED TO CONNECT TO SQLITE: {e}")
        sys.exit(1)

    # --- 3. Fetch all documents from Firebase ---
    try:
        log_runtime(f"Fetching all documents from '{COLLECTION_NAME}' collection...")
        docs = collection_ref.stream()

        fixed_count = 0
        skipped_count = 0

        for doc in docs:
            doc_id = doc.id
            data = doc.to_dict()

            start_time = data.get('interval_start_time')
            end_time = data.get('interval_end_time')

            if not start_time or not end_time:
                log_runtime(f"⚠️ Skipping doc {doc_id}: Missing timestamps.")
                skipped_count += 1
                continue

            # --- THIS IS THE FIX ---
            # Convert Firebase's Python datetime objects into the exact
            # string format we use in the SQLite database.
            try:
                start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            except Exception as e:
                log_runtime(f"⚠️ Skipping doc {doc_id}: Could not parse timestamp. Error: {e}")
                skipped_count += 1
                continue
            # --- END OF FIX ---

            # --- 4. Query local DB for the correct data ---
            sql_query = """
                SELECT SUM(energy_wh_interval) AS correct_total
                FROM readings
                WHERE timestamp >= ? AND timestamp <= ?
            """

            # Now we pass the correctly formatted strings to the query
            cur_sqlite.execute(sql_query, (start_time_str, end_time_str))
            result = cur_sqlite.fetchone()

            if result and result['correct_total'] is not None:
                correct_total_wh = round(result['correct_total'], 5)
                old_total_wh = data.get('total_energy_wh', 'N/A')

                # 5. Update the Firebase document
                log_runtime(f"Fixing doc {doc_id}: Old value={old_total_wh}, New value={correct_total_wh}")
                doc.reference.update({'total_energy_wh': correct_total_wh})
                fixed_count += 1
            else:
                log_runtime(f"ℹ️ Skipping doc {doc_id}: No local data found for this timeframe.")
                skipped_count += 1

        print("\n--- Repair Complete ---")
        print(f"✅ Successfully processed and updated {fixed_count} documents.")
        print(f"ℹ️ Skipped {skipped_count} documents (no local data or missing timestamps).")

    except Exception as e:
        log_runtime(f"\nAn error occurred during the repair: {e}")
    finally:
        if con_sqlite:
            con_sqlite.close()
            log_runtime("Local database connection closed.")

if __name__ == "__main__":
    repair_firebase_data()
