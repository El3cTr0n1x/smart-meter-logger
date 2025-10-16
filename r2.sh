#!/bin/bash
# runner.sh - Run main logger and analyzer in a loop

# Ensure venv is active
source venv/bin/activate

DURATION=${1:-60}
INTERVAL=${2:-5}

echo "[RUNNER] Starting smart meter logging loop with duration=$DURATION, interval=$INTERVAL..."

while true; do
    echo "[RUNNER] Starting logging cycle..."
    python3 main.py $DURATION $INTERVAL

    echo "[RUNNER] Logging finished. Running analyzer..."
    python3 analyzer.py

    echo "[RUNNER] Cycle complete. Restarting..."
done
