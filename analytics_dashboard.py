import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import datetime
import os
import time
import chatbot_logic 

# --- Configuration ---
LIVE_DB = 'campus_energy_multi.db'
DEMO_DB = 'demo_data_v2.db' 
DB_NAME = '' 

if os.path.exists(LIVE_DB):
    DB_NAME = LIVE_DB
    st.set_page_config(page_title="Campus Energy (LIVE)", layout="wide")
else:
    DB_NAME = DEMO_DB
    st.set_page_config(page_title="Campus Energy (Demo)", layout="wide")

# --- Database Connection ---
@st.cache_resource
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, timeout=10.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

@st.cache_data(ttl=2)
def run_query(query, params=None):
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

# --- Analytics Functions ---
def get_meter_hierarchy():
    return run_query("SELECT * FROM meter_hierarchy")

@st.cache_data(ttl=2)
def get_kpi_metrics(meter_ids):
    if not meter_ids: return {}
    id_tuple = tuple(meter_ids)
    if len(id_tuple) == 1: id_tuple = f"({id_tuple[0]})"
    query = f"""
    SELECT
        SUM(CASE WHEN STRFTIME('%Y-%m-%d', timestamp) = STRFTIME('%Y-%m-%d', 'now', 'localtime') THEN energy_wh_interval ELSE 0 END) / 1000 AS today_kwh,
        SUM(CASE WHEN STRFTIME('%Y-%W', timestamp) = STRFTIME('%Y-%W', 'now', 'localtime') THEN energy_wh_interval ELSE 0 END) / 1000 AS week_kwh,
        SUM(CASE WHEN STRFTIME('%Y-%m', timestamp) = STRFTIME('%Y-%m', 'now', 'localtime') THEN energy_wh_interval ELSE 0 END) / 1000 AS month_kwh
    FROM meter_readings
    WHERE meter_id IN {id_tuple};
    """
    df = run_query(query)
    if not df.empty: return df.to_dict('records')[0]
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

def get_recent_power_data(meter_ids, minutes=30):
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
    WHERE r.meter_id IN {id_tuple} 
    AND r.timestamp >= datetime('now', 'localtime', '-{minutes} minutes')
    ORDER BY r.timestamp ASC;
    """
    return run_query(query)

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

def get_cost_by_meter(meter_ids, cost_per_kwh):
    if not meter_ids: return pd.DataFrame()
    id_tuple = tuple(meter_ids)
    if len(id_tuple) == 1: id_tuple = f"({id_tuple[0]})"
    query = f"""
    SELECT 
        h.lab_name,
        (SUM(r.energy_wh_interval) / 1000) * ? AS "Total Cost (₹)"
    FROM meter_readings r
    JOIN meter_hierarchy h ON r.meter_id = h.meter_id
    WHERE r.meter_id IN {id_tuple}
    GROUP BY h.lab_name
    ORDER BY "Total Cost (₹)" DESC;
    """
    return run_query(query, params=(cost_per_kwh,))

def get_cost_by_day(meter_ids, cost_per_kwh):
    if not meter_ids: return pd.DataFrame()
    id_tuple = tuple(meter_ids)
    if len(id_tuple) == 1: id_tuple = f"({id_tuple[0]})"
    query = f"""
    SELECT 
        DATE(r.timestamp) AS "Date",
        (SUM(r.energy_wh_interval) / 1000) * ? AS "Daily Cost (₹)"
    FROM meter_readings r
    WHERE r.meter_id IN {id_tuple}
    GROUP BY "Date"
    ORDER BY "Date" ASC;
    """
    return run_query(query, params=(cost_per_kwh,))


# --- UI Layout ---
if DB_NAME == LIVE_DB:
    st.title("⚡ Campus Smart Meter Dashboard")
else:
    st.title("⚡ Campus Smart Meter Dashboard (DEMO)")

hierarchy_df = get_meter_hierarchy()

# Sidebar
st.sidebar.title("Controls")
if "GOOGLE_API_KEY" in st.secrets:
    gemini_api_key = st.secrets["GOOGLE_API_KEY"]
    st.sidebar.success("✅ API Key loaded")
else:
    gemini_api_key = st.sidebar.text_input("Google Gemini API Key", type="password")

st.sidebar.subheader("Cost Configuration")
cost_per_kwh = st.sidebar.number_input("Cost Per kWh (₹)", min_value=0.0, max_value=50.0, value=8.0, step=0.5)
st.sidebar.divider()
st.sidebar.markdown("Select meters to analyze:")
selected_meters = []
for index, row in hierarchy_df.iterrows():
    label = f"{row['block_name']} - {row['lab_name']}"
    if st.sidebar.checkbox(label, value=True, key=f"meter_{row['meter_id']}"):
        selected_meters.append(row['meter_id'])
if not selected_meters:
    st.warning("Please select at least one meter.")
    st.stop()

# Tabs
tab_overview, tab_analytics, tab_cost, tab_ai, tab_detail, tab_raw_data = st.tabs(
    ["Overview", "Historical Analytics", "Cost Analysis", "AI Assistant", "Detailed Day Analysis", "Raw Data"]
)

# --- Overview (Fragment) ---
@st.fragment(run_every=2)
def render_live_overview():
    st.header("Consumption Overview")
    kpi_data = get_kpi_metrics(selected_meters)
    kpi_cols = st.columns(3)
    kpi_cols[0].metric("Today's Consumption", f"{kpi_data.get('today_kwh', 0):.2f} kWh")
    kpi_cols[1].metric("This Week's Total", f"{kpi_data.get('week_kwh', 0):.2f} kWh")
    kpi_cols[2].metric("This Month's Total", f"{kpi_data.get('month_kwh', 0):.2f} kWh")
    st.markdown("---")
    st.header("Live Status")
    latest_df = get_latest_readings(selected_meters)
    if not latest_df.empty:
        cols = st.columns(len(latest_df))
        for i, (index, row) in enumerate(latest_df.iterrows()):
            with cols[i]:
                st.metric(label=f"{row['lab_name']} Power", value=f"{row['power']:.2f} W")
                st.caption(f"PF: {row['pf']:.2f} | V: {row['voltage']:.1f} V")
                st.caption(f"Last read: {row['Last Reading']}")

with tab_overview:
    render_live_overview()
    st.markdown("---")
    st.header("Total Consumption Breakdown")
    total_kwh_df = get_total_consumption_by_meter(selected_meters)
    if not total_kwh_df.empty:
        fig = px.pie(total_kwh_df, names='lab_name', values='Total Consumption (kWh)', title="Total Energy Consumption (kWh) by Meter")
        st.plotly_chart(fig, use_container_width=True) 

with tab_analytics:
    st.header("Consumption Analytics")
    st.subheader("Daily Energy Usage History")
    daily_history_df = get_daily_usage_history(selected_meters)
    if not daily_history_df.empty:
        daily_history_df['Date'] = pd.to_datetime(daily_history_df['Date'])
        st.plotly_chart(px.bar(daily_history_df, x="Date", y="Total Units Consumed (kWh)", title="Total Energy Per Day"), use_container_width=True)
    st.subheader("Hourly Efficiency Profile")
    hourly_df = get_consumption_by_hour(selected_meters)
    if not hourly_df.empty:
        st.plotly_chart(px.line(hourly_df, x="Hour of Day", y="Average Power (W)", color="lab_name", markers=True), use_container_width=True)

with tab_cost:
    st.header(f"Cost Analysis (at ₹{cost_per_kwh}/kWh)")
    st.subheader("Total Cost by Meter")
    cost_by_meter_df = get_cost_by_meter(selected_meters, cost_per_kwh)
    if not cost_by_meter_df.empty:
        total_cost = cost_by_meter_df["Total Cost (₹)"].sum()
        st.metric("Total Cost (Selected)", f"₹{total_cost:,.2f}")
        st.plotly_chart(px.pie(cost_by_meter_df, names='lab_name', values='Total Cost (₹)'), use_container_width=True)
    st.subheader("Daily Cost")
    cost_by_day_df = get_cost_by_day(selected_meters, cost_per_kwh)
    if not cost_by_day_df.empty:
        cost_by_day_df['Date'] = pd.to_datetime(cost_by_day_df['Date'])
        st.plotly_chart(px.bar(cost_by_day_df, x="Date", y="Daily Cost (₹)"), use_container_width=True) 
    else:
        st.info("No daily cost data to display.")

# --- AI Assistant (Context Aware + Auto Plotting) ---
with tab_ai:
    st.header("Ask Your Data")
    st.markdown("Examples: *Show me the power usage for Lab 1.* or *Compare all labs.*")
    
    if not gemini_api_key:
        st.warning("⚠️ Please enter your Google Gemini API Key.")
    else:
        if "messages" not in st.session_state:
            st.session_state.messages = []

        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if "dataframe" in message and message["dataframe"] is not None:
                    st.dataframe(message["dataframe"])
                if "chart" in message and message["chart"] is not None:
                    st.plotly_chart(message["chart"], use_container_width=True)
                if "sql" in message:
                    with st.expander("View SQL Query"):
                        st.code(message["sql"], language="sql")

        if prompt := st.chat_input("Ask a question..."):
            with st.chat_message("user"):
                st.markdown(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    # Pass session history to chatbot
                    result_df, sql_used = chatbot_logic.ask_database(prompt, gemini_api_key, st.session_state.messages)
                    
                    if result_df is not None and not result_df.empty:
                        st.dataframe(result_df)
                        
                        # --- AUTO-PLOTTING LOGIC ---
                        chart = None
                        try:
                            # 1. Time-Series Plot (Line Chart)
                            if 'timestamp' in result_df.columns:
                                result_df['timestamp'] = pd.to_datetime(result_df['timestamp'])
                                numeric_cols = result_df.select_dtypes(include=['number']).columns.tolist()
                                numeric_cols = [c for c in numeric_cols if 'id' not in c] # Exclude IDs
                                
                                if numeric_cols:
                                    chart = px.line(result_df, x='timestamp', y=numeric_cols, 
                                                  title="Time-Series Trend", markers=True)
                            
                            # 2. Categorical Comparison Plot (Bar Chart)
                            # If no timestamp, but we have text (e.g., lab_name) and numbers
                            elif result_df.select_dtypes(include=['object', 'string']).shape[1] > 0:
                                # Find the first text column (likely lab_name)
                                cat_col = result_df.select_dtypes(include=['object', 'string']).columns[0]
                                # Find the first numeric column (e.g., total_energy)
                                num_cols = result_df.select_dtypes(include=['number']).columns.tolist()
                                num_cols = [c for c in num_cols if 'id' not in c]
                                
                                if cat_col and num_cols:
                                    # Plot the first numeric metric against the category
                                    chart = px.bar(result_df, x=cat_col, y=num_cols[0],
                                                 title=f"Comparison by {cat_col}", color=cat_col)
                        except Exception as e:
                            st.warning(f"Could not generate chart: {e}")
                        # ---------------------------

                        with st.expander("View SQL Query"):
                            st.code(sql_used, language="sql")
                        response_text = "Here is the data you asked for."
                        
                        st.session_state.messages.append({
                            "role": "assistant", 
                            "content": response_text,
                            "dataframe": result_df,
                            "chart": chart,
                            "sql": sql_used
                        })
                    else:
                        st.error(sql_used) 
                        response_text = "I couldn't find any data for that query."
                        st.session_state.messages.append({"role": "assistant", "content": response_text})

with tab_detail:
    st.header("Detailed Day Analysis")
    view_mode = st.radio("View Mode:", ["Live Window (Last 30 mins)", "Full Day History"], horizontal=True)
    if view_mode == "Live Window (Last 30 mins)":
        @st.fragment(run_every=2)
        def render_live_chart():
            st.caption("Showing real-time data. Updates instantly.")
            day_power_df = get_recent_power_data(selected_meters, minutes=30)
            if not day_power_df.empty:
                day_power_df['timestamp'] = pd.to_datetime(day_power_df['timestamp'], format='mixed')
                fig = px.line(day_power_df, x="timestamp", y="power", color="lab_name", title="Live Power Draw (Last 30 Minutes)")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("No recent data found.")
        render_live_chart()
    else:
        st.caption("Select a date to see full history.")
        selected_date = st.date_input("Select Date", datetime.date.today())
        day_power_df = get_power_for_day(selected_meters, selected_date)
        if not day_power_df.empty:
            day_power_df['timestamp'] = pd.to_datetime(day_power_df['timestamp'], format='mixed')
            fig = px.line(day_power_df, x="timestamp", y="power", color="lab_name", title=f"Power Draw on {selected_date}")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(f"No data found for {selected_date}.")

with tab_raw_data:
    st.header("Raw Data Inspector")
    @st.fragment(run_every=5)
    def render_raw_data():
        raw_df = run_query("""SELECT r.*, h.block_name, h.lab_name FROM meter_readings r JOIN meter_hierarchy h ON r.meter_id = h.meter_id ORDER BY r.timestamp DESC LIMIT 100""")
        st.dataframe(raw_df)
    render_raw_data()
