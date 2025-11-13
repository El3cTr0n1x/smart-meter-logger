import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import datetime
import os  

# --- Configuration  ---
LIVE_DB = 'campus_energy_multi.db'
DEMO_DB = 'demo_database.db'
DB_NAME = '' # We will set this now

# If we're running locally (where the live DB exists), use it.
# If not (e.g., on Streamlit Cloud), fall back to the demo DB.
if os.path.exists(LIVE_DB):
    DB_NAME = LIVE_DB
    st.set_page_config(page_title="Campus Energy (LIVE)", layout="wide")
else:
    DB_NAME = DEMO_DB
    st.set_page_config(page_title="Campus Energy (Demo)", layout="wide")
# --- End of configuration ---


# --- Database Connection & Caching ---

@st.cache_resource
def get_db_connection():
    """Establishes a connection to the SQLite database."""
    return sqlite3.connect(DB_NAME, check_same_thread=False)

@st.cache_data(ttl=300) # Cache data for 5 minutes
def run_query(query, params=None):
    """Fetches data from the DB and returns a Pandas DataFrame."""
    conn = get_db_connection()
    try:
        if params:
            df = pd.read_sql_query(query, conn, params=params)
        else:
            df = pd.read_sql_query(query, conn)
        return df
    except Exception as e:
        st.error(f"Database query failed: {e}")
        return pd.DataFrame()

# --- Analytics Queries ---

def get_meter_hierarchy():
    """Fetches the meter tree structure."""
    return run_query("SELECT * FROM meter_hierarchy")

# KPI Queries
def get_kpi_metrics(meter_ids):
    if not meter_ids:
        return {}
    id_tuple = tuple(meter_ids)
    if len(id_tuple) == 1:
        id_tuple = f"({id_tuple[0]})"
        
    query = f"""
    SELECT
        SUM(CASE WHEN DATE(timestamp) = DATE('now', 'localtime') THEN energy_wh_interval ELSE 0 END) / 1000 AS today_kwh,
        SUM(CASE WHEN STRFTIME('%Y-%W', timestamp) = STRFTIME('%Y-%W', 'now', 'localtime') THEN energy_wh_interval ELSE 0 END) / 1000 AS week_kwh,
        SUM(CASE WHEN STRFTIME('%Y-%m', timestamp) = STRFTIME('%Y-%m', 'now', 'localtime') THEN energy_wh_interval ELSE 0 END) / 1000 AS month_kwh
    FROM meter_readings
    WHERE meter_id IN {id_tuple};
    """
    df = run_query(query)
    if not df.empty:
        return df.to_dict('records')[0]
    return {}

def get_total_consumption_by_meter(meter_ids):
    if not meter_ids: return pd.DataFrame()
    id_tuple = tuple(meter_ids)
    if len(id_tuple) == 1: id_tuple = f"({id_tuple[0]})"
    query = f"""
    SELECT 
        h.lab_name,
        SUM(r.energy_wh_interval) / 1000 AS "Total Consumption (kWh)"
    FROM meter_readings r
    JOIN meter_hierarchy h ON r.meter_id = h.meter_id
    WHERE r.meter_id IN {id_tuple}
    GROUP BY h.lab_name
    ORDER BY "Total Consumption (kWh)" DESC;
    """
    return run_query(query)

def get_consumption_by_weekday(meter_ids):
    if not meter_ids: return pd.DataFrame()
    id_tuple = tuple(meter_ids)
    if len(id_tuple) == 1: id_tuple = f"({id_tuple[0]})"
    query = f"""
    SELECT 
        h.lab_name,
        STRFTIME('%w', r.timestamp) AS weekday_num,
        CASE STRFTIME('%w', r.timestamp)
            WHEN '0' THEN 'Sun' WHEN '1' THEN 'Mon' WHEN '2' THEN 'Tue'
            WHEN '3' THEN 'Wed' WHEN '4' THEN 'Thu' WHEN '5' THEN 'Fri'
            WHEN '6' THEN 'Sat'
        END AS "Day of Week",
        SUM(r.energy_wh_interval) / 1000 AS "Total (kWh)"
    FROM meter_readings r
    JOIN meter_hierarchy h ON r.meter_id = h.meter_id
    WHERE r.meter_id IN {id_tuple}
    GROUP BY h.lab_name, "Day of Week"
    ORDER BY h.lab_name, weekday_num;
    """
    return run_query(query)

# Daily History Query 
def get_daily_usage_history(meter_ids):
    if not meter_ids: return pd.DataFrame()
    id_tuple = tuple(meter_ids)
    if len(id_tuple) == 1: id_tuple = f"({id_tuple[0]})"
    query = f"""
    SELECT 
        DATE(r.timestamp) AS "Date",
        SUM(r.energy_wh_interval) / 1000 AS "Total Units Consumed (kWh)"
    FROM meter_readings r
    WHERE r.meter_id IN {id_tuple}
    GROUP BY "Date"
    ORDER BY "Date" ASC;
    """
    return run_query(query)

def get_consumption_by_hour(meter_ids):
    if not meter_ids: return pd.DataFrame()
    id_tuple = tuple(meter_ids)
    if len(id_tuple) == 1: id_tuple = f"({id_tuple[0]})"
    query = f"""
    SELECT 
        h.lab_name,
        STRFTIME('%H', r.timestamp) AS "Hour of Day",
        AVG(r.power) AS "Average Power (W)"
    FROM meter_readings r
    JOIN meter_hierarchy h ON r.meter_id = h.meter_id
    WHERE r.meter_id IN {id_tuple}
    GROUP BY h.lab_name, "Hour of Day"
    ORDER BY h.lab_name, "Hour of Day" ASC;
    """
    return run_query(query)

def get_latest_readings(meter_ids):
    if not meter_ids: return pd.DataFrame()
    id_tuple = tuple(meter_ids)
    if len(id_tuple) == 1: id_tuple = f"({id_tuple[0]})"
    query = f"""
    SELECT 
        h.lab_name, r.power, r.voltage, r.current, r.pf,
        MAX(r.timestamp) AS "Last Reading"
    FROM meter_readings r
    JOIN meter_hierarchy h ON r.meter_id = h.meter_id
    WHERE r.meter_id IN {id_tuple}
    GROUP BY h.lab_name
    ORDER BY "Last Reading" DESC;
    """
    return run_query(query)

# Detailed Day Profile Query
def get_power_for_day(meter_ids, selected_date):
    if not meter_ids: return pd.DataFrame()
    id_tuple = tuple(meter_ids)
    if len(id_tuple) == 1: id_tuple = f"({id_tuple[0]})"
    
    query = f"""
    SELECT 
        r.timestamp,
        h.lab_name,
        r.power
    FROM meter_readings r
    JOIN meter_hierarchy h ON r.meter_id = h.meter_id
    WHERE r.meter_id IN {id_tuple} AND DATE(r.timestamp) = ?
    ORDER BY r.timestamp ASC;
    """
    return run_query(query, params=(selected_date,))


# --- Streamlit Dashboard UI ---

# We check DB_NAME to show a 'LIVE' or 'DEMO' title
if DB_NAME == LIVE_DB:
    st.title("⚡ Campus Smart Meter Dashboard (LIVE)")
    st.caption("Multi-meter analytics with live data and detailed breakdown.")
else:
    st.title("⚡ Campus Smart Meter Dashboard (DEMO)")
    st.caption("Showing a static data snapshot for demonstration.")


# --- 1. Load Data ---
hierarchy_df = get_meter_hierarchy()

# --- 2. Sidebar / Hierarchy Selector ---
st.sidebar.title("Meter Selector")
st.sidebar.markdown("Select meters to analyze:")
selected_meters = []
for index, row in hierarchy_df.iterrows():
    label = f"{row['block_name']} - {row['lab_name']}"
    if st.sidebar.checkbox(label, value=True, key=f"meter_{row['meter_id']}"):
        selected_meters.append(row['meter_id'])

if not selected_meters:
    st.warning("Please select at least one meter from the sidebar to view analytics.")
    st.stop()

# --- 3. Main Page Tabs ---
tab_overview, tab_analytics, tab_detail, tab_raw_data = st.tabs(
    ["Overview", "Historical Analytics", "Detailed Day Analysis", "Raw Data"]
)

# --- Tab 1: Overview ---
with tab_overview:
    st.header("Consumption Overview")
    
    # KPI Metrics
    kpi_data = get_kpi_metrics(selected_meters)
    kpi_cols = st.columns(3)
    kpi_cols[0].metric("Today's Consumption", f"{kpi_data.get('today_kwh', 0):.2f} kWh")
    kpi_cols[1].metric("This Week's Total", f"{kpi_data.get('week_kwh', 0):.2f} kWh")
    kpi_cols[2].metric("This Month's Total", f"{kpi_data.get('month_kwh', 0):.2f} kWh")

    st.markdown("---")
    
    st.header("Live Status")
    # Display latest readings in columns
    latest_df = get_latest_readings(selected_meters)

    if not latest_df.empty:
        cols = st.columns(len(latest_df))
        for i, (index, row) in enumerate(latest_df.iterrows()):
            with cols[i]:
                st.metric(
                    label=f"{row['lab_name']} Power",
                    value=f"{row['power']:.2f} W"
                )
                st.caption(f"PF: {row['pf']:.2f} | V: {row['voltage']:.1f} V")
                st.caption(f"Last read: {row['Last Reading']}")
    else:
        st.info("No live data found for selected meters.")

    st.markdown("---")

    # Total Consumption Pie Chart
    st.header("Total Consumption Breakdown")
    total_kwh_df = get_total_consumption_by_meter(selected_meters)

    if not total_kwh_df.empty:
        fig = px.pie(
            total_kwh_df, 
            names='lab_name', 
            values='Total Consumption (kWh)', 
            title="Total Energy Consumption (kWh) by Meter"
        )
        st.plotly_chart(fig, use_container_width=True)


# --- Tab 2: Historical Analytics ---
with tab_analytics:
    st.header("Consumption Analytics")

    # NEW: Daily Energy Usage History (from your screenshot)
    st.subheader("Daily Energy Usage History (All Selected Meters)")
    daily_history_df = get_daily_usage_history(selected_meters)
    if not daily_history_df.empty:
        daily_history_df['Date'] = pd.to_datetime(daily_history_df['Date'])
        fig_daily_history = px.bar(
            daily_history_df,
            x="Date",
            y="Total Units Consumed (kWh)",
            title="Total Energy Per Day"
        )
        st.plotly_chart(fig_daily_history, use_container_width=True)
    else:
        st.info("No daily history data to display.")

    st.markdown("---")

    # Weekday Analysis
    st.subheader("Which day of the week consumes the most energy?")
    weekday_df = get_consumption_by_weekday(selected_meters)

    if not weekday_df.empty:
        fig_weekday = px.bar(
            weekday_df,
            x="Day of Week",
            y="Total (kWh)",
            color="lab_name",
            barmode="group",
            title="Total Consumption by Day of Week",
            category_orders={"Day of Week": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]}
        )
        st.plotly_chart(fig_weekday, use_container_width=True)

    st.markdown("---")

    # Hourly "Efficiency" Analysis
    st.subheader("What time of day are labs most active?")
    hourly_df = get_consumption_by_hour(selected_meters)
    
    if not hourly_df.empty:
        fig_hourly = px.line(
            hourly_df,
            x="Hour of Day",
            y="Average Power (W)",
            color="lab_name",
            title="Average Power Consumption by Hour",
            markers=True
        )
        st.plotly_chart(fig_hourly, use_container_width=True)


# --- Tab 3: Detailed Day Analysis  ---
with tab_detail:
    st.header("Detailed Day Analysis")
    st.markdown("Select a date to inspect the detailed power profile for that day.")
    
    # Date picker
    selected_date = st.date_input("Select a date", datetime.date.today())
    
    if selected_date:
        day_power_df = get_power_for_day(selected_meters, selected_date)
        
        if not day_power_df.empty:
            
            # 1. Convert timestamp strings to datetime objects
            day_power_df['timestamp'] = pd.to_datetime(day_power_df['timestamp'], format='mixed')
            
            # 2. Manually add 5.5 hours to shift from UTC (in DB) to IST (for display)
            day_power_df['timestamp'] = day_power_df['timestamp'] + pd.to_timedelta('05:30:00')
            # ----------------------------------------
            
            fig_day_power = px.line(
                day_power_df,
                x="timestamp",
                y="power",
                color="lab_name",
                title=f"Power Draw on {selected_date.strftime('%B %d, %Y')}",
                labels={"power": "Power (W)", "timestamp": "Time (IST)"} # Label the axis as IST
            )
            
            
            fig_day_power.update_traces(marker=None)
            st.plotly_chart(fig_day_power, use_container_width=True)
        else:
            st.warning(f"No data found for the selected meters on {selected_date}.")


# --- Tab 4: Raw Data ---
with tab_raw_data:
    st.header("Raw Data Inspector")
    st.markdown("Showing the first 1,000 rows from the database.")
    
    raw_df = run_query("""
        SELECT r.*, h.block_name, h.lab_name 
        FROM meter_readings r
        JOIN meter_hierarchy h ON r.meter_id = h.meter_id
        ORDER BY r.timestamp DESC
        LIMIT 1000
    """)
    st.dataframe(raw_df)
