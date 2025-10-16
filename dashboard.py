import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
import time
import os

# --- CONFIGURATION ---
DB_FILE = "log_files/smart_meter.db"
REFRESH_INTERVAL_SECONDS = 15

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Live Smart Meter Dashboard",
    page_icon="⚡",
    layout="wide"
)

# --- DATA LOADING ---
@st.cache_data(ttl=REFRESH_INTERVAL_SECONDS)
def load_data():
    """Loads all data from the SQLite database."""
    if not os.path.exists(DB_FILE):
        return pd.DataFrame()

    try:
        con = sqlite3.connect(DB_FILE)
        df = pd.read_sql_query(
            "SELECT * FROM readings",
            con,
            index_col='timestamp',
            parse_dates=['timestamp']
        )
        con.close()
        df.sort_index(inplace=True)
        return df
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        return pd.DataFrame()

# --- LOAD THE DATA ---
df = load_data()

# --- UI ---
st.title("⚡ Live Smart Meter Dashboard")

if df.empty:
    st.warning(f"No data found in '{DB_FILE}'. Is the logger (`main.py`) running?")
else:
    latest_data = df.iloc[-1]
    daily_units = df['energy_kwh'].resample('D').apply(lambda x: x.max() - x.min()).dropna()
    weekly_units = daily_units.resample('W-Mon').sum()
    monthly_units = daily_units.resample('ME').sum()

    # --- TOP-LEVEL METRICS ---
    st.header(f"Live Readings (Last updated: {latest_data.name.strftime('%I:%M:%S %p')})")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Voltage", f"{latest_data.voltage_v1:.1f} V")
    col2.metric("Current", f"{latest_data.current_a1:.2f} A")
    col3.metric("Power", f"{latest_data.active_power_w1:.0f} W")
    col4.metric("Frequency", f"{latest_data.frequency_hz:.2f} Hz")
    
    st.markdown("---")
    st.header("Consumption Overview")
    
    col_d, col_w, col_m = st.columns(3)
    col_d.metric("Today's Consumption", f"{daily_units.iloc[-1]:.2f} kWh" if not daily_units.empty else "N/A")
    col_w.metric("This Week's Total", f"{weekly_units.iloc[-1]:.2f} kWh" if not weekly_units.empty else "N/A")
    col_m.metric("This Month's Total", f"{monthly_units.iloc[-1]:.2f} kWh" if not monthly_units.empty else "N/A")

    # --- VISUALIZATIONS ---
    st.markdown("---")
    st.header("Detailed Analysis")

    st.subheader("Live Power Draw")
    live_fig = px.line(
        df.tail(1000),
        y='active_power_w1',
        title="Live Power Consumption (W)",
        labels={'timestamp': 'Time', 'active_power_w1': 'Power (W)'}
    )
    st.plotly_chart(live_fig, use_container_width=True)

    st.subheader("Average Consumption by Hour of the Day")
    hourly_avg = df.groupby(df.index.hour)['active_power_w1'].mean()
    hourly_avg.index.name = "Hour of Day"
    hourly_fig = px.bar(
        hourly_avg,
        labels={'value': 'Average Power (W)', 'Hour of Day': 'Hour'}
    )
    st.plotly_chart(hourly_fig, use_container_width=True)

    st.subheader("Daily Energy Usage History")
    
    daily_units_to_plot = daily_units.reset_index()
    daily_units_to_plot['timestamp'] = daily_units_to_plot['timestamp'].dt.strftime('%Y-%m-%d')
    daily_units_to_plot.rename(columns={'timestamp': 'Date', 'energy_kwh': 'kWh'}, inplace=True)

    daily_fig = px.bar(
        daily_units_to_plot,
        x='Date',
        y='kWh',
        title="Total Units Consumed Per Day (kWh)"
    )
    # --- THIS IS THE KEY FIX ---
    # Force the x-axis to be treated as a category, not a continuous timeline.
    daily_fig.update_xaxes(type='category')
    st.plotly_chart(daily_fig, use_container_width=True)

    # --- AUTO-REFRESH MECHANISM ---
    time.sleep(REFRESH_INTERVAL_SECONDS)
    st.rerun()
