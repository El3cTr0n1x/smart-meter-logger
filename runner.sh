#!/bin/bash

# A script to start the continuous logger and schedule daily analytics.

echo "--- Smart Meter Automation Runner ---"

# Go to the script's own directory to ensure paths are correct
SCRIPT_DIR=$(dirname "$(realpath "$0")")
cd "$SCRIPT_DIR"

# --- Step 1: Start the Logger in the Background ---
echo "[1/2] Stopping any existing logger process..."
# Be specific to avoid killing other python scripts
pkill -f "venv/bin/python3 main.py"

echo "[1/2] Starting the main.py logger in the background..."
# FIX: Use the specific Python from the virtual environment
nohup venv/bin/python3 main.py > log_files/runtime.log 2>&1 &

# Give it a moment to start up before checking
sleep 1

# Check if the process started successfully
if pgrep -f "venv/bin/python3 main.py" > /dev/null; then
    echo "      ✅ Logger started successfully."
else
    echo "      ❌ ERROR: Failed to start the logger. Check log_files/runtime.log for details."
    exit 1
fi

# The cron job setup can remain the same
echo "[2/2] Cron job setup is unchanged."
echo ""
echo "--- Setup Complete! ---"
