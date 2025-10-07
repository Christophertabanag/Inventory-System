import streamlit as st
import pandas as pd
import os
from datetime import datetime
import random

# --- You may want to import or copy utility functions from your main file ---
# For example, if you use clean_barcode, force_all_columns_to_string, etc.,
# you can import them if you put them in a separate utils.py
# Or, for now, just copy those functions here.

def clean_barcode(val):
    if pd.isnull(val) or val == "":
        return ""
    s = str(val).strip().replace('\u200b','').replace('\u00A0','')
    try:
        f = float(s)
        s = str(int(f))
    except ValueError:
        pass
    return s

def force_all_columns_to_string(df):
    for col in df.columns:
        df[col] = df[col].astype(str)
    return df

def clean_nans(df):
    return df.replace([pd.NA, 'nan'], '', regex=True)

# --- Load inventory file (you may want to DRY this with a utils file!) ---
INVENTORY_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Inventory")
inventory_files = [f for f in os.listdir(INVENTORY_FOLDER) if f.lower().endswith(('.xlsx', '.csv'))]
selected_file = inventory_files[0]
if len(inventory_files) > 1:
    selected_file = st.selectbox("Select inventory file to use:", inventory_files)
INVENTORY_FILE = os.path.join(INVENTORY_FOLDER, selected_file)

def load_inventory():
    if os.path.exists(INVENTORY_FILE):
        if INVENTORY_FILE.lower().endswith('.xlsx'):
            df = pd.read_excel(INVENTORY_FILE)
        elif INVENTORY_FILE.lower().endswith('.csv'):
            df = pd.read_csv(INVENTORY_FILE)
        else:
            st.error("Unsupported inventory file type.")
            st.stop()
        df = force_all_columns_to_string(df)
        return df
    else:
        st.error(f"Inventory file '{INVENTORY_FILE}' not found.")
        st.stop()

df = load_inventory()
barcode_col = "BARCODE"

st.title("Stocktake")

st.write("Upload a file (CSV, Excel, or TXT) of scanned barcodes from your stock count.")
uploaded_file = st.file_uploader("Upload scanned barcodes", type=["csv", "xlsx", "txt"])
if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith(".csv"):
            scanned_df = pd.read_csv(uploaded_file)
        elif uploaded_file.name.endswith(".xlsx"):
            scanned_df = pd.read_excel(uploaded_file)
        elif uploaded_file.name.endswith(".txt"):
            scanned_df = pd.read_csv(uploaded_file, delimiter=None)
        else:
            st.error("❌ Unsupported file type.")
            scanned_df = None
    except Exception as e:
        st.error(f"❌ Error reading file: {e}")
        scanned_df = None

    if scanned_df is not None:
        scanned_df = force_all_columns_to_string(scanned_df)
        scanned_df[barcode_col] = scanned_df[barcode_col].map(clean_barcode)
        st.write("Preview of your uploaded file:")
        st.dataframe(clean_nans(scanned_df.head()), width='stretch')
        barcode_candidates = [
            col for col in scanned_df.columns
            if "barcode" in col.lower() or "ean" in col.lower() or "upc" in col.lower() or "code" in col.lower()
        ]
        if not barcode_candidates:
            barcode_candidates = scanned_df.columns.tolist()
        barcode_column = st.selectbox(
            "Select the column containing barcodes", barcode_candidates
        )
        inventory_barcodes = set(df[barcode_col].map(clean_barcode))
        scanned_barcodes = set(scanned_df[barcode_column].map(clean_barcode))
        matched = inventory_barcodes & scanned_barcodes
        missing = inventory_barcodes - scanned_barcodes
        unexpected = scanned_barcodes - inventory_barcodes
        st.success(f"✅ Matched items: {len(matched)}")
        st.warning(f"⚠️ Missing items: {len(missing)}")
        st.error(f"❌ Unexpected items: {len(unexpected)}")
        if matched:
            st.write("✅ Present items:")
            st.dataframe(clean_nans(df[df[barcode_col].map(clean_barcode).isin(matched)]), width='stretch')
        if missing:
            st.write("❌ Missing items:")
            st.dataframe(clean_nans(df[df[barcode_col].map(clean_barcode).isin(missing)]), width='stretch')
        if unexpected:
            st.write("⚠️ Unexpected items (not in system):")
            st.write(list(unexpected))
