#!/usr/bin/env python3
"""
analyzer.py — Smart Meter Data Analyzer (v2.0 - Automated Daily Analysis)

Features:
- Auto-detects yesterday's log file for automated daily runs (e.g., via cron)
- Generates date-stamped reports (summary, anomalies, plots) to prevent overwrites
- New '--consolidate' mode to merge all daily logs into a master CSV file
- Proper datetime handling and robust error checking
- Colored terminal output for clarity
"""

import pandas as pd
import matplotlib.pyplot as plt
import argparse
import os
import glob
from datetime import datetime, timedelta

LOG_DIR = "log_files"
PLOT_DIR = os.path.join(LOG_DIR, "plots")
os.makedirs(PLOT_DIR, exist_ok=True)

# ----------------- COLOR HELPERS -----------------
def c(text, color):
    """Add ANSI color for clean, readable terminal output."""
    colors = {
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "cyan": "\033[96m",
        "reset": "\033[0m"
    }
    return f"{colors.get(color, '')}{text}{colors['reset']}"

# ----------------- LOAD & PROCESS DATA -----------------
def load_and_process_data(filename):
    """Loads a single CSV, parsing dates and cleaning columns."""
    try:
        df = pd.read_csv(filename, on_bad_lines="skip")
        df.columns = [col.strip().lower() for col in df.columns]
        
        # Ensure timestamp is the primary datetime column and index
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)

        # Drop rows where critical numeric values are missing
        numeric_cols = ["voltage_v1", "current_a1", "active_power_w1", "power_factor_pf1", "frequency_hz", "energy_kwh"]
        df.dropna(subset=[col for col in numeric_cols if col in df.columns], inplace=True)
        
        if df.empty:
            raise ValueError("No valid data rows found after cleaning.")
            
        return df

    except Exception as e:
        print(c(f"[ERROR] Could not read or process {filename}: {e}", "red"))
        return None

# ----------------- ANALYTICS -----------------
def generate_summary(df):
    """Computes mean/min/max for key numeric columns."""
    numeric_cols = df.select_dtypes(include='number').columns
    summary = df[numeric_cols].agg(['mean', 'min', 'max']).round(3).T
    
    # Calculate total energy consumption for the day
    if "energy_kwh" in df.columns and not df["energy_kwh"].empty:
        energy_used = df["energy_kwh"].iloc[-1] - df["energy_kwh"].iloc[0]
        summary.loc['energy_kwh', 'total_usage'] = round(energy_used, 3)
        
    return summary

def detect_anomalies(df):
    """Identifies voltage or frequency readings outside normal ranges."""
    anomalies = []
    if "voltage_v1" in df.columns:
        voltage_anomalies = df[(df["voltage_v1"] < 200) | (df["voltage_v1"] > 250)]
        for idx, row in voltage_anomalies.iterrows():
            anomalies.append([idx, "voltage_v1", row["voltage_v1"], "Voltage out of 200-250V range"])
            
    if "frequency_hz" in df.columns:
        freq_anomalies = df[(df["frequency_hz"] < 49.5) | (df["frequency_hz"] > 50.5)]
        for idx, row in freq_anomalies.iterrows():
            anomalies.append([idx, "frequency_hz", row["frequency_hz"], "Frequency out of 49.5-50.5Hz range"])
            
    return pd.DataFrame(anomalies, columns=["timestamp", "metric", "value", "issue"])

# ----------------- PLOTTING -----------------
def plot_metrics(df, date_str):
    """Generates and saves plots for each metric."""
    metrics_to_plot = [c for c in df.columns if c not in ("date", "meter_id")]
    for col in metrics_to_plot:
        plt.figure(figsize=(12, 5))
        df[col].plot(linewidth=1.5, title=f"{col.replace('_', ' ').title()} on {date_str}")
        plt.xlabel("Time")
        plt.ylabel(col)
        plt.grid(True, which='both', linestyle='--', linewidth=0.5)
        plt.tight_layout()
        fname = os.path.join(PLOT_DIR, f"{date_str}_{col}.png")
        plt.savefig(fname)
        plt.close()
    print(c(f"[PLOT] Saved {len(metrics_to_plot)} plots to {PLOT_DIR}/", "green"))

# ----------------- LOG CONSOLIDATION -----------------
def consolidate_logs():
    """Finds all daily logs, merges them, and saves to a master file."""
    print(c("\n[CONSOLIDATE] Merging all daily logs into a master file...", "cyan"))
    log_files = sorted(glob.glob(os.path.join(LOG_DIR, "meter_log_*.csv")))
    if not log_files:
        print(c("[WARN] No daily log files found to consolidate.", "yellow"))
        return

    master_df = pd.concat([pd.read_csv(f) for f in log_files], ignore_index=True)
    master_df.drop_duplicates(subset=["timestamp"], inplace=True)
    master_df.sort_values(by="timestamp", inplace=True)
    
    output_file = os.path.join(LOG_DIR, "meter_log_master.csv")
    master_df.to_csv(output_file, index=False)
    print(c(f"[OK] Consolidated {len(log_files)} files into {output_file}", "green"))

# ----------------- MAIN -----------------
def main():
    parser = argparse.ArgumentParser(description="Analyze Smart Meter CSV Logs")
    parser.add_argument(
        "--date",
        help="Target date (YYYY-MM-DD). Defaults to yesterday."
    )
    parser.add_argument(
        "--consolidate",
        action="store_true",
        help="Consolidate all daily logs into one master file and exit."
    )
    args = parser.parse_args()

    if args.consolidate:
        consolidate_logs()
        return

    # Determine target date: use provided date or default to yesterday
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(c("[ERROR] Invalid date format. Please use YYYY-MM-DD.", "red"))
            return
    else:
        target_date = datetime.now().date() - timedelta(days=1)
    
    date_str = target_date.strftime("%Y-%m-%d")
    log_filename = os.path.join(LOG_DIR, f"meter_log_{date_str}.csv")

    print(c(f"\nAnalyzing data for {date_str} from {log_filename}", "cyan"))

    if not os.path.exists(log_filename):
        print(c(f"[ERROR] Log file not found: {log_filename}", "red"))
        return

    df = load_and_process_data(log_filename)
    if df is None:
        return

    # --- Generate Summary ---
    summary = generate_summary(df)
    print(c("\n=== DAILY SUMMARY ===", "cyan"))
    print(summary)
    summary_fname = os.path.join(LOG_DIR, f"summary_{date_str}.csv")
    summary.to_csv(summary_fname)
    print(c(f"[OK] Exported summary -> {summary_fname}", "green"))
    
    # --- Detect Anomalies ---
    anomalies = detect_anomalies(df)
    if not anomalies.empty:
        print(c("\n=== ANOMALIES DETECTED ===", "red"))
        print(anomalies)
        anomalies_fname = os.path.join(LOG_DIR, f"anomalies_{date_str}.csv")
        anomalies.to_csv(anomalies_fname, index=False)
        print(c(f"[WARN] Exported anomalies -> {anomalies_fname}", "yellow"))
    else:
        print(c("\nNo anomalies detected ✅", "green"))
        
    # --- Generate Plots ---
    plot_metrics(df, date_str)

if __name__ == "__main__":
    main()
