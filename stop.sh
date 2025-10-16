#!/bin/bash

# A script to stop the logger.

echo "--- Stopping Smart Meter Automation ---"

# Go to the script's own directory
SCRIPT_DIR=$(dirname "$(realpath "$0")")
cd "$SCRIPT_DIR"

# --- Stop the Logger ---
echo "Stopping the main.py logger process..."
# FIX: Be specific about which python process to kill
pkill -f "venv/bin/python3 main.py"
echo "✅ Logger stopped."
