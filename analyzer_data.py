import pandas as pd
import glob
import os
import json
from datetime import datetime

# --- CONFIGURATION ---
LOG_DIR = "log_files"
SPIKE_THRESHOLD = 0.15      # 15% jump in power between readings
VOLTAGE_SURGE_LIMIT = 230   # Voltage level to be considered a surge
WATT_UPPER_LIMIT = 20000    # A reasonable upper limit for power draw in Watts to filter out garbage data

def analyze_data():
    """
    Reads all daily logs, computes detailed analytics, and outputs summary files.
    """
    print("--- Starting Data Analysis ---")

    # --- 1. Load and Consolidate All Log Files ---
    log_files = sorted(glob.glob(os.path.join(LOG_DIR, "meter_log_*.csv")))
    if not log_files:
        print(f"❌ ERROR: No log files found in '{LOG_DIR}'. Exiting.")
        return

    print(f"✅ Found {len(log_files)} daily log files to process.")
    df = pd.concat([pd.read_csv(f) for f in log_files], ignore_index=True)
    
    # --- 2. Clean and Prepare Data ---
    df.drop_duplicates(subset=['timestamp'], inplace=True)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    initial_rows = len(df)
    df = df[df['active_power_w1'].between(0, WATT_UPPER_LIMIT)]
    filtered_rows = initial_rows - len(df)
    if filtered_rows > 0:
        print(f"⚠️  Filtered out {filtered_rows} rows with unrealistic power values (> {WATT_UPPER_LIMIT}W).")

    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)

    # --- 3. Feature Engineering (Create new columns for analysis) ---
    # NEW: Create a boolean column to flag voltage surges
    df['voltage_surge'] = df['voltage_v1'] > VOLTAGE_SURGE_LIMIT
    
    df['power_spike'] = df['active_power_w1'].pct_change() > SPIKE_THRESHOLD

    # --- 4. Compute Daily Statistics ---
    daily_summary = df.resample('D').agg(
        Units_kWh=('energy_kwh', lambda x: x.max() - x.min() if not x.empty else 0),
        Avg_Power_W=('active_power_w1', 'mean'),
        Peak_Power_W=('active_power_w1', 'max'),
        Avg_Voltage_V=('voltage_v1', 'mean'),
        Avg_Current_A=('current_a1', 'mean'),
        Avg_Power_Factor=('power_factor_pf1', 'mean'),
        Power_Spikes=('power_spike', 'sum'),
        Voltage_Surges=('voltage_surge', 'sum') # NEW: Count the number of voltage surges per day
    ).dropna()

    peak_times = df.resample('D')['active_power_w1'].idxmax().dt.strftime('%H:%M:%S')
    daily_summary['Peak_Time'] = peak_times
    
    # --- 5. Compute Weekly and Monthly Totals ---
    weekly_units = daily_summary['Units_kWh'].resample('W-Mon').sum()
    monthly_units = daily_summary['Units_kWh'].resample('ME').sum()

    # --- 6. Format and Print Console Output ---
    daily_summary_display = daily_summary.round(2)
    daily_summary_display['Power_Spikes'] = daily_summary_display['Power_Spikes'].astype(int)
    daily_summary_display['Voltage_Surges'] = daily_summary_display['Voltage_Surges'].astype(int) # NEW: Format new column
    
    print("\n=== ENERGY CONSUMPTION SUMMARY ===")
    # NEW: Added Voltage_Surges to the printout
    print(daily_summary_display[['Units_kWh', 'Avg_Power_W', 'Peak_Power_W', 'Peak_Time', 'Power_Spikes', 'Voltage_Surges']].to_string())
    
    # (Weekly and Monthly printouts remain the same)
    if not weekly_units.empty:
        latest_week = weekly_units.index[-1]
        print(f"\n=== WEEKLY TOTAL (Week {latest_week.isocalendar().week}) ===")
        print(f"{weekly_units.iloc[-1]:.2f} kWh")

    if not monthly_units.empty:
        latest_month = monthly_units.index[-1]
        print(f"\n=== MONTHLY TOTAL ({latest_month.strftime('%B %Y')}) ===")
        print(f"{monthly_units.iloc[-1]:.2f} kWh (so far)")

    # --- 7. Save Output Files ---
    # (Saving logic remains the same, the new column will be included automatically)
    summary_csv_path = os.path.join(LOG_DIR, "daily_summary.csv")
    daily_summary_display.to_csv(summary_csv_path)
    print(f"\n✅ Daily summary saved to '{summary_csv_path}'")
    
    weekly_dict = {key.strftime('%Y-%m-%d'): value for key, value in weekly_units.to_dict().items()}
    monthly_dict = {key.strftime('%Y-%m-%d'): value for key, value in monthly_units.to_dict().items()}

    output_json = {
        "last_updated": datetime.now().isoformat(),
        "daily_summary": daily_summary_display.reset_index().rename(columns={'timestamp': 'date'}).to_dict(orient='records'),
        "weekly_total_kWh": weekly_dict,
        "monthly_total_kWh": monthly_dict
    }
    for item in output_json['daily_summary']:
        item['date'] = item['date'].strftime('%Y-%m-%d')

    summary_json_path = os.path.join(LOG_DIR, "summary.json")
    with open(summary_json_path, 'w') as f:
        json.dump(output_json, f, indent=4)
    print(f"✅ Dashboard-ready JSON saved to '{summary_json_path}'")
    
    print("\n--- Analysis Complete ---")

if __name__ == "__main__":
    analyze_data()
