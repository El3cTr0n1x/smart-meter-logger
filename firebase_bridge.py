#!/usr/bin/env python3
"""
firebase_bridge.py (v4.0 - Calculate Energy)

- [NEW] Expects 'energy_wh_interval' from MQTT.
- [NEW] SUMS the energy for the 5-min batch and saves it
  as 'total_energy_wh'.
- This provides an accurate, aggregated energy value to Firebase.
"""

import paho.mqtt.client as mqtt
import firebase_admin
from firebase_admin import credentials, firestore
import json
from datetime import datetime
import time
import os
import signal
import threading

# --- FIREBASE CONFIGURATION ---
SERVICE_ACCOUNT_KEY = "service-account-key.json"
NEW_COLLECTION_NAME = "readings_5min_avg" 

# --- MQTT CONFIGURATION ---
MQTT_BROKER_HOST = "localhost"
MQTT_BROKER_PORT = 1883
MQTT_TOPIC = "pes/campus/energy/meter/reading"
CLIENT_ID = "firebase_bridge_001"

# --- BATCHING CONFIGURATION ---
BATCH_INTERVAL_SECONDS = 300 # 5 minutes
data_batch = []
data_batch_lock = threading.Lock()

# --- GLOBALS ---
db = None
readings_collection_ref = None
terminate = False
mqtt_client = None

def log_runtime(msg):
    """Prints a message with a timestamp."""
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}")

def setup_firebase():
    """Initializes the Firebase connection."""
    global db, readings_collection_ref
    if not os.path.exists(SERVICE_ACCOUNT_KEY):
        log_runtime(f"❌ ERROR: Firebase service account key '{SERVICE_ACCOUNT_KEY}' not found.")
        return False
    try:
        cred = credentials.Certificate(SERVICE_ACCOUNT_KEY)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        else:
            log_runtime(" Firebase app already initialized.")
        db = firestore.client()
        readings_collection_ref = db.collection(NEW_COLLECTION_NAME) 
        log_runtime(f"✅ Firebase connection established. Writing to collection '{NEW_COLLECTION_NAME}'")
        return True
    except Exception as e:
        log_runtime(f"❌ FAILED TO INITIALIZE FIREBASE: {e}")
        return False

def flush_batch_to_firestore():
    """
    Calculates the average of the batch and writes ONE document to Firestore.
    """
    global data_batch, readings_collection_ref, db
    
    if db is None:
        log_runtime("⚠️ Firebase not ready, cannot flush batch.")
        return

    with data_batch_lock:
        if not data_batch:
            log_runtime(" Batch is empty, nothing to flush.")
            return
        batch_to_write = data_batch.copy()
        data_batch.clear()

    if not batch_to_write:
        return

    try:
        # --- NEW (v4.0) Averaging and Summing Logic ---
        sums = {
            'voltage_v1': 0, 'current_a1': 0, 'active_power_w1': 0,
            'power_factor_pf1': 0, 'frequency_hz': 0,
            'energy_wh_interval': 0 # We will SUM this value
        }
        count = len(batch_to_write)
        
        for packet in batch_to_write:
            for key in sums:
                sums[key] += packet.get(key, 0)
        
        # Build the single aggregated document
        agg_data = {
            'timestamp': firestore.SERVER_TIMESTAMP, 
            'interval_start_time': batch_to_write[0].get('timestamp'),
            'interval_end_time': batch_to_write[-1].get('timestamp'),
            'meter_id': batch_to_write[0].get('meter_id'),
            'building': batch_to_write[0].get('building'),
            'floor': batch_to_write[0].get('floor'),
            
            # Calculate averages for instantaneous values
            'voltage_v1': round(sums['voltage_v1'] / count, 2),
            'current_a1': round(sums['current_a1'] / count, 3),
            'active_power_w1': round(sums['active_power_w1'] / count, 2),
            'power_factor_pf1': round(sums['power_factor_pf1'] / count, 3),
            'frequency_hz': round(sums['frequency_hz'] / count, 2),
            
            # --- NEW (v4.0) ---
            # Save the SUM of energy used in this batch
            'total_energy_wh': round(sums['energy_wh_interval'], 5), 
            'readings_in_batch': count
        }
        
        # Add the single document to the new collection
        readings_collection_ref.add(agg_data)
        
        log_runtime(f"✅ Flushed {count} readings as 1 aggregate doc to '{NEW_COLLECTION_NAME}'.")

    except Exception as e:
        log_runtime(f"❌ Error writing aggregate doc to Firebase: {e}")
        with data_batch_lock:
            data_batch.extend(batch_to_write)
        log_runtime(f"⚠️ Re-added {len(batch_to_write)} items to batch for next try.")


# --- MQTT CALLBACKS ---
def on_connect(client, userdata, flags, rc, properties):
    if rc == 0:
        log_runtime(f"✅ Connected to MQTT broker. Subscribing to '{MQTT_TOPIC}'...")
        client.subscribe(MQTT_TOPIC)
    else:
        log_runtime(f"❌ Failed to connect to MQTT broker, return code {rc}")

def on_disconnect(client, userdata, flags, rc, properties):
    if rc != 0:
        log_runtime(f"⚠️ MQTT Unexpectedly disconnected. Code: {rc}. Auto-reconnecting...")

def on_message(client, userdata, msg):
    global data_batch, db
    if db is None:
        log_runtime("⚠️ Received MQTT message, but Firebase is not connected. Message will be lost.")
        return
    try:
        payload_str = msg.payload.decode()
        data_packet = json.loads(payload_str)
        data_packet['timestamp'] = datetime.fromisoformat(data_packet['timestamp'])
        with data_batch_lock:
            data_batch.append(data_packet)
        meter = data_packet.get('meter_id', 'Unknown')
        log_runtime(f" Buffered message from {meter}. (Batch size: {len(data_batch)})")
    except Exception as e:
        log_runtime(f"⚠️ Error processing message: {e}")

# --- SIGNAL HANDLING ---
def handle_sig(sig, frame):
    global terminate
    log_runtime(f"Received signal {sig}, initiating shutdown...")
    terminate = True

# --- MAIN FUNCTION ---
def main():
    global mqtt_client, terminate
    if not setup_firebase():
        log_runtime("Exiting due to Firebase connection failure during startup.")
        return

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.on_disconnect = on_disconnect

    while not terminate:
        try:
            log_runtime(f"Attempting to connect to MQTT broker at {MQTT_BROKER_HOST}...")
            mqtt_client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, 60)
            mqtt_client.loop_start()
            log_runtime(" MQTT loop started in background thread.")
            break
        except Exception as e:
            log_runtime(f"❌ Error connecting: {e}. Retrying in 10s...")
            time.sleep(10)

    last_batch_write_time = time.time()
    while not terminate:
        try:
            current_time = time.time()
            if (current_time - last_batch_write_time) > BATCH_INTERVAL_SECONDS:
                log_runtime(" Batch interval reached, flushing data...")
                flush_batch_to_firestore()
                last_batch_write_time = current_time
            time.sleep(1)
        except Exception as e:
            log_runtime(f"❌ Error in main batching loop: {e}")
            time.sleep(5)

    log_runtime("Shutting down Firebase bridge...")
    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        log_runtime(" MQTT loop stopped.")
    
    log_runtime("Performing final data flush before exiting...")
    flush_batch_to_firestore()
    log_runtime("Firebase bridge stopped.")

if __name__ == "__main__":
    main()
