import google.generativeai as genai
import pandas as pd
import sqlite3
import os

# --- Configuration ---
DB_NAME = 'campus_energy_multi.db'
DEMO_DB = 'demo_data_v2.db' 

def get_db_path():
    """Auto-selects the correct DB (Live vs Demo)."""
    if os.path.exists(DB_NAME):
        return DB_NAME
    return DEMO_DB

def init_gemini(api_key):
    """Configures the Gemini API."""
    genai.configure(api_key=api_key)

def ask_database(user_question, api_key, chat_history=[]):
    """
    The core logic:
    1. Constructs a prompt with Schema + Chat History.
    2. Gets SQL back from Gemini.
    3. Runs SQL on local DB.
    """
    if not api_key:
        return None, "⚠️ Please enter a valid Google API Key in the sidebar."

    try:
        init_gemini(api_key)
        
        # 1. Format History for Context
        # We only send the last 3 exchanges to keep the prompt clean
        history_text = ""
        recent_history = chat_history[-6:] # Last 3 User + 3 Assistant messages
        
        for msg in recent_history:
            role = "User" if msg["role"] == "user" else "Assistant (SQL)"
            # If it's an assistant message, we care about the SQL it wrote, not the text response
            content = msg["content"]
            if "sql" in msg:
                content = f"Generated SQL: {msg['sql']}"
            history_text += f"{role}: {content}\n"

        # 2. Define the Schema and Prompt
        schema_context = """
        You are an expert SQL Data Analyst for a University Smart Meter project.
        Your job is to translate English questions into SQL queries for a SQLite database.
        
        The database has two tables:
        
        Table 1: meter_hierarchy (Maps IDs to locations)
        - meter_id (INTEGER)
        - block_name (TEXT) - e.g., 'Block A', 'Block B'
        - lab_name (TEXT) - e.g., 'Lab 1 (Original)', 'Lab 2 (Simulated)'
        
        Table 2: meter_readings (The sensor data)
        - meter_id (INTEGER) - Foreign Key
        - timestamp (DATETIME) - Format: 'YYYY-MM-DD HH:MM:SS' (e.g., '2025-11-17 14:30:00')
        - voltage (REAL) - In Volts
        - current (REAL) - In Amps
        - power (REAL) - In Watts (Active Power)
        - energy_wh_total (REAL) - Cumulative Energy Counter (Odometer style) in Watt-Hours
        - pf (REAL) - Power Factor
        
        IMPORTANT SQL RULES:
        1. Return ONLY the raw SQL query. Do not wrap it in markdown (```sql). Start directly with SELECT.
        2. **Context Awareness:** Use the "Conversation History" to understand "it", "that lab", or "compare them".
        3. **Time Filtering:** - 9am-5pm: `CAST(STRFTIME('%H', timestamp) AS INTEGER) BETWEEN 9 AND 17`
           - Date match: `DATE(timestamp) = '2025-11-13'`
        4. **Joins:** Always JOIN `meter_readings` with `meter_hierarchy` to return `lab_name`.
        5. **Limits:** If the user asks for "data" without specific aggregations, LIMIT to 50 rows.
        """
        
        model = genai.GenerativeModel('gemini-2.5-pro')
        
        full_prompt = f"""
        {schema_context}

        --- CONVERSATION HISTORY ---
        {history_text}
        
        --- CURRENT REQUEST ---
        User Question: {user_question}
        
        SQL Query:
        """
        
        response = model.generate_content(full_prompt)
        sql_query = response.text.strip().replace("```sql", "").replace("```", "").strip()
        
        # 3. Execute SQL
        conn = sqlite3.connect(get_db_path())
        conn.execute("PRAGMA journal_mode=WAL;")
        
        try:
            result_df = pd.read_sql_query(sql_query, conn)
            conn.close()
            
            if result_df.empty:
                return result_df, f"Query executed successfully but returned no data.\n\n**SQL Generated:**\n`{sql_query}`"
                
            return result_df, sql_query
            
        except Exception as db_err:
            conn.close()
            return None, f"Database Error: {db_err}\n\n**Bad SQL:** `{sql_query}`"

    except Exception as e:
        return None, f"API Error: {e}"
