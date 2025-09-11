#!/bin/bash

# Activate your virtual environment
source venv/bin/activate

# Start the Flask server in the background
python barcode_server.py &

# Wait for Flask to start
sleep 3

# Start Streamlit apps on ports 8501 and 8502 in the background, suppressing auto-browser launch
streamlit run Inventory_Manager.py --server.port 8501 --server.headless true &

# Wait for Streamlit apps to start
sleep 5

# Open all desired pages in browser (each only once)
open "http://localhost:8501/"

wait