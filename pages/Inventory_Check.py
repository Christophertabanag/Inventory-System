import streamlit as st
import pandas as pd
import os
from datetime import datetime
import io

# Paths (parent directory for inventory files)
MAIN_INVENTORY = os.path.join(os.path.dirname(__file__), "..", "inventory.xlsx")
SECONDARY_INVENTORY = os.path.join(os.path.dirname(__file__), "..", "secondary_inventory.xlsx")
UNFOUND_BARCODES = os.path.join(os.path.dirname(__file__), "..", "unfound_barcodes.xlsx")

def clean_barcode(val):
    if pd.isnull(val):
        return ""
    s = str(val).strip().replace('\u200b','').replace('\u00A0','')
    if '.' in s:
        int_part, dec_part = s.split('.', 1)
        if dec_part == '0':
            s = int_part
    return s

def ensure_inventory_files(main_file, secondary_file, unfound_file):
    main_df = pd.read_excel(main_file)
    # Secondary inventory
    if not os.path.exists(secondary_file):
        empty_df = pd.DataFrame(columns=main_df.columns)
        empty_df.to_excel(secondary_file, index=False)
    secondary_df = pd.read_excel(secondary_file)
    # Unfound barcodes
    if not os.path.exists(unfound_file):
        unfound_df = pd.DataFrame(columns=["BARCODE", "Timestamp"])
        unfound_df.to_excel(unfound_file, index=False)
    unfound_df = pd.read_excel(unfound_file)
    return main_df, secondary_df, unfound_df

def add_to_secondary(result, secondary_df):
    secondary_df["BARCODE_CLEAN"] = secondary_df["BARCODE"].apply(clean_barcode)
    search_barcode_clean = result.iloc[0]["BARCODE_CLEAN"]
    if not secondary_df[secondary_df["BARCODE_CLEAN"] == search_barcode_clean].empty:
        st.warning("Product already exists in secondary inventory!")
    else:
        secondary_df = pd.concat([result.drop(columns=["BARCODE_CLEAN"], errors="ignore"), secondary_df], ignore_index=True)
        secondary_df.to_excel(SECONDARY_INVENTORY, index=False)
        st.success("Product added to secondary inventory!")
    return secondary_df

def remove_from_secondary(search_barcode_clean, secondary_df):
    secondary_df["BARCODE_CLEAN"] = secondary_df["BARCODE"].apply(clean_barcode)
    secondary_df = secondary_df[secondary_df["BARCODE_CLEAN"] != search_barcode_clean]
    secondary_df.to_excel(SECONDARY_INVENTORY, index=False)
    st.success("Product removed from secondary inventory!")
    return secondary_df

def add_to_unfound(search_barcode_clean, unfound_df):
    if not unfound_df[unfound_df["BARCODE"].astype(str).apply(clean_barcode) == search_barcode_clean].empty:
        st.info("Barcode already in unfound list.")
    else:
        new_row = {"BARCODE": search_barcode_clean, "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        unfound_df = pd.concat([pd.DataFrame([new_row]), unfound_df], ignore_index=True)
        unfound_df.to_excel(UNFOUND_BARCODES, index=False)
        st.success("Barcode added to unfound barcodes list!")
    return unfound_df

def delete_unfound_barcode(barcode_to_delete, unfound_df):
    clean_barcodes = unfound_df["BARCODE"].astype(str).apply(clean_barcode)
    new_unfound_df = unfound_df[clean_barcodes != barcode_to_delete]
    new_unfound_df.to_excel(UNFOUND_BARCODES, index=False)
    st.success(f"Deleted barcode: {barcode_to_delete}")
    return new_unfound_df

st.title("Inventory Check / Product Transfer")

main_df, secondary_df, unfound_df = ensure_inventory_files(MAIN_INVENTORY, SECONDARY_INVENTORY, UNFOUND_BARCODES)

search_barcode = st.text_input("Scan or enter barcode")
search_barcode_clean = clean_barcode(search_barcode)

main_df["BARCODE_CLEAN"] = main_df["BARCODE"].apply(clean_barcode)
result = main_df[main_df["BARCODE_CLEAN"] == search_barcode_clean]
product_row = result.iloc[0] if not result.empty else None

if search_barcode:
    if not result.empty:
        st.success("Product found!")
        st.write("**Product Details:**")
        st.write(result.drop(columns=["BARCODE_CLEAN"], errors="ignore"))
    else:
        st.warning("Product not found in main inventory.")
        # Option to add to unfound barcodes
        if st.button("Add barcode to unfound barcodes list"):
            unfound_df = add_to_unfound(search_barcode_clean, unfound_df)

if product_row is not None:
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Add Product to Secondary Inventory"):
            secondary_df = add_to_secondary(result, secondary_df)
    with col2:
        if st.button("Remove Product from Secondary Inventory"):
            secondary_df = remove_from_secondary(search_barcode_clean, secondary_df)

st.markdown("---")
st.subheader("Secondary Inventory Preview")
st.dataframe(secondary_df.drop(columns=["BARCODE_CLEAN"], errors="ignore"), use_container_width=True)  

st.markdown("---")
st.subheader("Unfound Barcodes List")

# Show table first
st.dataframe(unfound_df, use_container_width=True)

# Show per-row delete buttons below the table
if not unfound_df.empty:
    st.write("Delete a barcode from the unfound list:")
    for idx, row in unfound_df.iterrows():
        barcode_cleaned = clean_barcode(row["BARCODE"])
        cols = st.columns([2,1])
        with cols[0]:
            st.write(f'{row["BARCODE"]} ({row["Timestamp"]})')
        with cols[1]:
            if st.button(f"Delete", key=f"delete_unfound_{idx}"):
                unfound_df = delete_unfound_barcode(barcode_cleaned, unfound_df)
                # No rerun; UI updates on next interaction

    buffer = io.BytesIO()
    unfound_df.to_excel(buffer, index=False, engine='openpyxl')
    buffer.seek(0)
    st.download_button(
        label="Download Unfound Barcodes as Excel",
        data=buffer,
        file_name="unfound_barcodes.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.write("No unfound barcodes.")