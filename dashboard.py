#!/usr/bin/env python3
"""
dashboard.py (v2.0 - Calculate Energy)

- [NEW] Reads the calculated 'energy_wh_interval' column.
- [NEW] Calculates consumption by SUMMING 'energy_wh_interval'
  instead of 'diffing' the old 'energy_kwh' column.
- This is a more robust calculation method.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
import time
import os
from datetime import datetime

# --- CONFIGURATION ---
DB_FILE = "log_files/smart_meter.db"
REFRESH_INTERVAL_SECONDS = 15

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Live Smart Meter Dashboard",
    page_icon="⚡",
    layout="wide"
)

# --- DATA LOADING (Robust) ---
@st.cache_data(ttl=REFRESH_INTERVAL_SECONDS)
def load_data():
    """
    Loads all data from the SQLite database and cleans bad timestamps
    without deleting the original database file.
    """
    if not os.path.exists(DB_FILE):
        return pd.DataFrame()
    try:
        con = sqlite3.connect(DB_FILE)
        df = pd.read_sql_query("SELECT * FROM readings", con, index_col=None)
        con.close()

        if df.empty:
            return pd.DataFrame()

        df['timestamp'] = pd.to_datetime(
            df['timestamp'], 
            format='%Y-%m-%d %H:%M:%S.%f',
            errors='coerce'
        )

        df.dropna(subset=['timestamp'], inplace=True)
        df.set_index('timestamp', inplace=True)
        
        # --- NEW (v2.0) ---
        # Ensure our new energy column is numeric
        df['energy_wh_interval'] = pd.to_numeric(df['energy_wh_interval'], errors='coerce')
        
        # Drop old/bad energy_kwh column if it exists, to avoid confusion
        if 'energy_kwh' in df.columns:
            df = df.drop(columns=['energy_kwh'])
            
        df = df.loc[df.index.notna()]
        df.sort_index(inplace=True)
        return df
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        return pd.DataFrame()

# --- LOAD THE DATA ---
df = load_data()

# --- UI ---
st.title("⚡ Live Smart Meter Dashboard")

# --- NEW (v2.0) ---
# Updated check to look for our new energy column
if df.empty or 'energy_wh_interval' not in df.columns or df['energy_wh_interval'].isnull().all():
    st.warning(f"No valid data found in '{DB_FILE}'. Is the logger (`main.py`) running and logging correctly?")
else:
    # --- CALCULATIONS ---
    latest_data = df.iloc[-1]

    # --- NEW (v2.0) ---
    # We now sum the interval energy (in Wh) and convert to kWh by / 1000
    daily_units_wh = df['energy_wh_interval'].resample('D').sum().dropna()
    daily_units_kwh = (daily_units_wh / 1000).dropna()
    
    # Check if we have enough data to calculate consumption
    if not daily_units_kwh.empty:
        weekly_units_kwh = daily_units_kwh.resample('W-Mon').sum()
        monthly_units_kwh = daily_units_kwh.resample('ME').sum()

        st.header("Consumption Overview")
        col_d, col_w, col_m = st.columns(3)
        col_d.metric("Today's Consumption", f"{daily_units_kwh.iloc[-1]:.2f} kWh")
        col_w.metric("This Week's Total", f"{weekly_units_kwh.iloc[-1]:.2f} kWh")
        col_m.metric("This Month's Total", f"{monthly_units_kwh.iloc[-1]:.2f} kWh")
    else:
        st.header("Consumption Overview")
        st.info("Collecting initial data... Consumption totals will appear soon.")
        # Create empty series so the rest of the app doesn't crash
        daily_units_kwh = pd.Series()
        
    # --- TOP-LEVEL METRICS (LIVE READINGS) ---
    last_update_time_str = "Not available"
    if not df.empty and pd.notna(df.index[-1]):
        try:
            last_update_time_str = df.index[-1].strftime('%I:%M:%S %p')
        except AttributeError:
            last_update_time_str = "Invalid timestamp"
    st.header(f"Live Readings (Last updated: {last_update_time_str})")

    if latest_data is not None:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Voltage", f"{latest_data.voltage_v1:.1f} V" if pd.notna(latest_data.voltage_v1) else "N/A")
        col2.metric("Current", f"{latest_data.current_a1:.2f} A" if pd.notna(latest_data.current_a1) else "N/A")
        col3.metric("Power", f"{latest_data.active_power_w1:.0f} W" if pd.notna(latest_data.active_power_w1) else "N/A")
        col4.metric("Frequency", f"{latest_data.frequency_hz:.2f} Hz" if pd.notna(latest_data.frequency_hz) else "N/A")
    else:
        st.warning("No live data available to display.")

    st.markdown("---")
    
    # --- VISUALIZATIONS ---
    st.header("Detailed Analysis")

    # --- Daily Power Profile Section ---
    st.subheader("Daily Power Profile")
    available_dates_raw = df.index.normalize().unique()
    available_dates = [date for date in available_dates_raw if pd.notna(date)]

    if not available_dates:
        st.warning("No valid date data to display daily profile.")
    else:
        default_index = max(0, len(available_dates) - 1)
        selected_date = st.selectbox(
            "Select a date to inspect its power profile:",
            options=available_dates,
            format_func=lambda date: date.strftime('%A, %B %d, %Y'),
            index=default_index
        )
        if selected_date:
            daily_df_filtered = df[df.index.date == selected_date.date()]
            
            show_extra_charts = st.checkbox("Show Voltage and Power Factor charts for this day")
            
            if not daily_df_filtered.empty:
                daily_profile_fig = px.line(
                    daily_df_filtered.reset_index(),
                    x='timestamp',
                    y='active_power_w1',
                    title=f"Power Draw on {selected_date.strftime('%A, %B %d')}",
                    labels={'timestamp': 'Time', 'active_power_w1': 'Power (W)'},
                    hover_data=["voltage_v1", "current_a1", "power_factor_pf1"]
                )
                st.plotly_chart(daily_profile_fig, use_container_width=True)

                if show_extra_charts:
                    st.markdown("---")
                    
                    voltage_fig = px.line(
                        daily_df_filtered,
                        y='voltage_v1',
                        title=f"Voltage Profile on {selected_date.strftime('%A, %B %d')}",
                        labels={'timestamp': 'Time', 'voltage_v1': 'Voltage (V)'}
                    )
                    voltage_fig.update_traces(line_color='#FF6347')
                    st.plotly_chart(voltage_fig, use_container_width=True)

                    pf_fig = px.line(
                        daily_df_filtered,
                        y='power_factor_pf1',
                        title=f"Power Factor Profile on {selected_date.strftime('%A, %B %d')}",
                        labels={'timestamp': 'Time', 'power_factor_pf1': 'Power Factor'}
                    )
                    pf_fig.update_traces(line_color='#32CD32')
                    st.plotly_chart(pf_fig, use_container_width=True)

            else:
                st.info(f"No data available for {selected_date.strftime('%Y-%m-%d')}.")
        else:
            st.warning("Please select a valid date.")

    st.markdown("---")
    st.subheader("Historical Averages")

    # --- Average Hourly Consumption Chart ---
    hourly_avg = df.groupby(df.index.hour)['active_power_w1'].mean()
    hourly_avg.index.name = "Hour of Day"
    hourly_fig = px.bar(
        hourly_avg,
        title="Average Consumption by Hour of the Day (All Time)",
        labels={'value': 'Average Power (W)', 'Hour of Day': 'Hour'}
    )
    hourly_fig.update_xaxes(type='category')
    st.plotly_chart(hourly_fig, use_container_width=True)

    # --- Daily Energy History Chart ---
    st.subheader("Daily Energy Usage History")
    # --- NEW (v2.0) ---
    if not daily_units_kwh.empty:
        daily_units_to_plot = daily_units_kwh.reset_index()
        daily_units_to_plot.columns = ['Date', 'kWh']
        daily_units_to_plot['Date'] = daily_units_to_plot['Date'].dt.strftime('%Y-%m-%d')
        daily_fig = px.bar(
            daily_units_to_plot,
            x='Date',
            y='kWh',
            title="Total Units Consumed Per Day (kWh)"
        )
        daily_fig.update_xaxes(type='category')
        st.plotly_chart(daily_fig, use_container_width=True)
    else:
        st.info("Not enough data to display daily energy history.")

    # --- Raw Data Table ---
    st.markdown("---")
    st.subheader("Latest Raw Data")
    # --- NEW (v2.0) ---
    # Show the new energy column
    display_cols = [
        'voltage_v1', 'current_a1', 'active_power_w1', 
        'power_factor_pf1', 'frequency_hz', 'energy_wh_interval'
    ]
    # Filter columns that actually exist in the dataframe
    display_cols = [col for col in display_cols if col in df.columns]
    st.dataframe(df[display_cols].tail(50).sort_index(ascending=False))

    # --- AUTO-REFRESH MECHANISM ---
    time.sleep(REFRESH_INTERVAL_SECONDS)
    st.rerun()
