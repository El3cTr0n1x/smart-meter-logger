#!/usr/bin/env python3
"""
app.py (v3.0 - Calculate Energy)

- Serves the main index.html file.
- API endpoints SUM the 'total_energy_wh' field
  from the 'readings_5min_avg' collection.
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta, timezone
from google.cloud.firestore_v1.base_query import FieldFilter

# --- CONFIGURATION ---
SERVICE_ACCOUNT_KEY = "service-account-key.json"

# --- INITIALIZE FLASK & CORS ---
app = Flask(__name__)
CORS(app) 

@app.route('/')
def serve_index():
    """Serves the index.html file from the current directory."""
    return send_from_directory('.', 'index.html')

# --- INITIALIZE FIREBASE ---
db = None
try:
    cred = credentials.Certificate(SERVICE_ACCOUNT_KEY)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    else:
        print(" Firebase app already initialized.")
    db = firestore.client()
    print("✅ Firebase connection established.")
except FileNotFoundError:
    print(f"❌ ERROR: Firebase service account key '{SERVICE_ACCOUNT_KEY}' not found.")
except Exception as e:
    print(f"❌ FAILED TO INITIALIZE FIREBASE: {e}")

def parse_required_dates():
    """Parses REQUIRED start_date and end_date from query args."""
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if not start_date_str or not end_date_str:
        raise ValueError("Missing required query parameters: 'start_date' and 'end_date' (YYYY-MM-DD)")

    try:
        start_dt_day = datetime.strptime(start_date_str, '%Y-%m-%d')
        start_dt_utc = start_dt_day.replace(tzinfo=timezone.utc)
        end_dt_day = datetime.strptime(end_date_str, '%Y-%m-%d')
        end_dt_utc = (end_dt_day + timedelta(days=1)).replace(tzinfo=timezone.utc)
        if start_dt_utc >= end_dt_utc:
            raise ValueError("Invalid date range: 'end_date' must be after 'start_date'")
        return start_dt_utc, end_dt_utc
    except ValueError as e:
        raise ValueError(f"Invalid date format or range: {e}. Use YYYY-MM-DD format.") from e

# --- API ENDPOINTS ---

@app.route('/api/aggregate/campus', methods=['GET'])
def get_campus_aggregate():
    """
    Calculates the total energy consumed across campus.
    Sums 'total_energy_wh' from the 'readings_5min_avg' collection.
    """
    if db is None:
        return jsonify({"error": "Firebase connection not available"}), 500
    try:
        start_dt, end_dt = parse_required_dates()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    try:
        readings_query = db.collection('readings_5min_avg')
        
        query = readings_query.where(filter=FieldFilter('timestamp', '>=', start_dt))
        query = query.where(filter=FieldFilter('timestamp', '<', end_dt))
        docs = query.stream()

        total_campus_energy_wh = 0
        latest_timestamp_in_range = None
        readings_processed = 0
        meters_found = set()

        for doc in docs:
            reading = doc.to_dict()
            energy_wh = reading.get('total_energy_wh') 
            if energy_wh is None or not isinstance(energy_wh, (int, float)):
                continue
            
            total_campus_energy_wh += energy_wh
            readings_processed += 1
            meter_id = reading.get('meter_id', 'unknown_meter')
            meters_found.add(meter_id)

            timestamp = reading.get('timestamp')
            if timestamp:
                ts_datetime = timestamp
                if isinstance(timestamp, str):
                    try: ts_datetime = datetime.fromisoformat(timestamp)
                    except ValueError: continue
                if latest_timestamp_in_range is None or ts_datetime > latest_timestamp_in_range:
                    latest_timestamp_in_range = ts_datetime

        last_updated_str = latest_timestamp_in_range.strftime('%Y-%m-%d %H:%M:%S') if latest_timestamp_in_range else "N/A"
        total_campus_energy_kwh = total_campus_energy_wh / 1000.0

        return jsonify({
            "scope": "campus",
            "time_range_start": start_dt.isoformat(),
            "time_range_end": end_dt.isoformat(),
            "total_energy_kwh": round(total_campus_energy_kwh, 2),
            "meters_found": len(meters_found),
            "readings_processed": readings_processed,
            "last_reading_in_range": last_updated_str
        })
    except Exception as e:
        print(f"❌ Error querying Firebase in /api/aggregate/campus: {e}")
        return jsonify({"error": "Failed to fetch campus aggregate data. Check server logs."}), 500

@app.route('/api/aggregate/building/<building_name>', methods=['GET'])
def get_building_aggregate(building_name):
    """
    Calculates the total energy for a specific building.
    Sums 'total_energy_wh' from the 'readings_5min_avg' collection.
    """
    if db is None:
        return jsonify({"error": "Firebase connection not available"}), 500
    try:
        start_dt, end_dt = parse_required_dates()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    try:
        readings_query = db.collection('readings_5min_avg')
        
        query = readings_query.where(filter=FieldFilter('building', '==', building_name))
        query = query.where(filter=FieldFilter('timestamp', '>=', start_dt))
        query = query.where(filter=FieldFilter('timestamp', '<', end_dt))
        docs = query.stream()

        total_building_energy_wh = 0
        latest_timestamp_in_range = None
        readings_processed = 0
        meters_found = set()

        for doc in docs:
            reading = doc.to_dict()
            energy_wh = reading.get('total_energy_wh')
            if energy_wh is None or not isinstance(energy_wh, (int, float)):
                continue

            total_building_energy_wh += energy_wh
            readings_processed += 1
            meter_id = reading.get('meter_id', 'unknown_meter')
            meters_found.add(meter_id)

            timestamp = reading.get('timestamp')
            if timestamp:
                ts_datetime = timestamp
                if isinstance(timestamp, str):
                    try: ts_datetime = datetime.fromisoformat(timestamp)
                    except ValueError: continue
                if latest_timestamp_in_range is None or ts_datetime > latest_timestamp_in_range:
                    latest_timestamp_in_range = ts_datetime

        last_updated_str = latest_timestamp_in_range.strftime('%Y-%m-%d %H:%M:%S') if latest_timestamp_in_range else "N/A"
        total_building_energy_kwh = total_building_energy_wh / 1000.0

        return jsonify({
            "scope": "building",
            "building_name": building_name,
            "time_range_start": start_dt.isoformat(),
            "time_range_end": end_dt.isoformat(),
            "total_energy_kwh": round(total_building_energy_kwh, 2),
            "meters_found": len(meters_found),
            "readings_processed": readings_processed,
            "last_reading_in_range": last_updated_str
        })
    except Exception as e:
        print(f"❌ Error querying Firebase in /api/aggregate/building/{building_name}: {e}")
        return jsonify({"error": f"Failed to fetch aggregate data for building '{building_name}'. Check server logs."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
