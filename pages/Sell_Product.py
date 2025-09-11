import streamlit as st
import pandas as pd
import os
from datetime import datetime
import socket
import io

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))

INVENTORY_FILE = os.path.join(PROJECT_ROOT, "inventory.xlsx")
ARCHIVE_FILE = os.path.join(PROJECT_ROOT, "archive_inventory.xlsx")
SALES_FILE = os.path.join(PROJECT_ROOT, "sales.xlsx")
AUDIT_FILE = os.path.join(PROJECT_ROOT, "auditlog.xlsx")

def load_inventory():
    if os.path.exists(INVENTORY_FILE):
        return pd.read_excel(INVENTORY_FILE)
    else:
        st.error(f"Inventory file not found at {INVENTORY_FILE}.")
        st.stop()

def load_archive():
    if os.path.exists(ARCHIVE_FILE):
        return pd.read_excel(ARCHIVE_FILE)
    else:
        inv = load_inventory()
        return pd.DataFrame(columns=inv.columns if not inv.empty else [])

def save_inventory(df):
    df.to_excel(INVENTORY_FILE, index=False)

def save_archive(df):
    df.to_excel(ARCHIVE_FILE, index=False)

def load_sales():
    if os.path.exists(SALES_FILE):
        return pd.read_excel(SALES_FILE)
    else:
        return pd.DataFrame(columns=["Timestamp", "BARCODE", "Product", "Quantity", "Price", "SoldBy", "Customer", "Type"])

def save_sales(df):
    df.to_excel(SALES_FILE, index=False)

def load_audit():
    if os.path.exists(AUDIT_FILE):
        return pd.read_excel(AUDIT_FILE)
    else:
        return pd.DataFrame(columns=[
            "Timestamp", "BARCODE", "Action", "Product", "Quantity", "User",
            "Details", "Client IP", "Qty Before", "Qty After"
        ])

def save_audit(df):
    df.to_excel(AUDIT_FILE, index=False)

def clean_barcode(val):
    if pd.isnull(val):
        return ""
    s = str(val).strip().replace('\u200b','').replace('\u00A0','')
    if s.endswith('.0'):
        s = s[:-2]
    return s

def get_client_ip():
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        return ip
    except Exception:
        return "Unknown"

df = load_inventory()
archive_df = load_archive()
sales_df = load_sales()
audit_df = load_audit()

if "Type" not in sales_df.columns:
    sales_df["Type"] = ""

df["BARCODE_CLEAN"] = df["BARCODE"].apply(clean_barcode)
if not archive_df.empty:
    archive_df["BARCODE_CLEAN"] = archive_df["BARCODE"].apply(clean_barcode)

st.set_page_config(page_title="Sell Product", layout="wide")
st.title("Inventory Sales & Returns")

# ----- SALES & RETURNS -----
sales_col, details_col = st.columns([2, 1])
with sales_col:
    st.subheader("Sell Product / Process Return")
    barcode = st.text_input("Scan or enter product barcode")
    barcode_input = clean_barcode(barcode)

    # Try active inventory first, then archive
    product_row = df[df["BARCODE_CLEAN"] == barcode_input]
    product_source = "Inventory"
    if product_row.empty and not archive_df.empty:
        product_row = archive_df[archive_df["BARCODE_CLEAN"] == barcode_input]
        product_source = "Archive"

    if not product_row.empty:
        product = product_row.iloc[0]
        qty_before = int(product.get("QUANTITY", 0)) if product_source == "Inventory" else 0
        st.success(f"Product found in {product_source}: {product.get('MODEL','')} ({product.get('SIZE','')}, {product.get('F COLOUR','')})")
        st.write(f"Current Stock: {qty_before if product_source == 'Inventory' else 'Archived'}")
        qty_to_sell = st.number_input(
            "Quantity to Sell/Return", 
            min_value=1, 
            max_value=max(qty_before if product_source == "Inventory" else 9999, 1), 
            value=1, key="qty_to_sell"
        )
        default_price = float(product.get("RRP", 0))
        if default_price < 0.01:
            default_price = 0.01
        price = st.number_input("Sale Price", min_value=0.01, value=default_price)
        customer = st.text_input("Customer Name (optional)")
        sold_by = st.text_input("Sold By (staff name)")
        sale_type = st.selectbox("Transaction Type", ["Sale", "Return"])

        # Calculate total sold and returned for this barcode
        total_sold = sales_df[
            (sales_df["BARCODE"].astype(str) == barcode_input) & (sales_df["Type"] == "Sale")
        ]["Quantity"].sum()
        total_returned = sales_df[
            (sales_df["BARCODE"].astype(str) == barcode_input) & (sales_df["Type"] == "Return")
        ]["Quantity"].sum()
        net_sold = total_sold - total_returned

        if sale_type == "Return":
            st.info(f"Total previously sold: {total_sold}, Total previously returned: {total_returned}, Remaining eligible for return: {net_sold}")

        if st.button("Process Transaction"):
            if sale_type == "Sale":
                if product_source == "Inventory":
                    new_qty = qty_before - int(qty_to_sell)
                    if new_qty < 0:
                        st.error("Error: Not enough stock!")
                        st.stop()
                    # Update inventory
                    df.loc[df["BARCODE_CLEAN"] == barcode_input, "QUANTITY"] = new_qty
                    # If product is now sold out, move to archive
                    if new_qty == 0:
                        archive_row = df[df["BARCODE_CLEAN"] == barcode_input]
                        df = df[df["BARCODE_CLEAN"] != barcode_input]
                        save_inventory(df)
                        archive_df = pd.concat([archive_df, archive_row], ignore_index=True)
                        save_archive(archive_df)
                    else:
                        save_inventory(df)
                else:
                    st.error("Cannot sell archived product. Please restore it to active inventory first.")
                    st.stop()
            else:  # Return logic
                if qty_to_sell > net_sold:
                    st.error(f"Error: Cannot return {qty_to_sell} items. Only {net_sold} have been sold and not yet returned for this product.")
                    st.stop()
                if product_source == "Inventory":
                    new_qty = qty_before + int(qty_to_sell)
                    df.loc[df["BARCODE_CLEAN"] == barcode_input, "QUANTITY"] = new_qty
                    save_inventory(df)
                else:
                    # Archive: restore to inventory and remove from archive
                    # If barcode already exists in inventory, just update quantity
                    if not df[df["BARCODE_CLEAN"] == barcode_input].empty:
                        df.loc[df["BARCODE_CLEAN"] == barcode_input, "QUANTITY"] += int(qty_to_sell)
                        save_inventory(df)
                        # Remove from archive
                        archive_df = archive_df[archive_df["BARCODE_CLEAN"] != barcode_input]
                        save_archive(archive_df)
                    else:
                        # Move row from archive to inventory and set new quantity
                        archive_row = archive_df[archive_df["BARCODE_CLEAN"] == barcode_input].copy()
                        archive_row["QUANTITY"] = int(qty_to_sell)
                        df = pd.concat([df, archive_row], ignore_index=True)
                        save_inventory(df)
                        # Remove from archive
                        archive_df = archive_df[archive_df["BARCODE_CLEAN"] != barcode_input]
                        save_archive(archive_df)
                    new_qty = int(qty_to_sell)

            # Log sale/return
            sale_row = {
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "BARCODE": barcode_input,
                "Product": product.get("MODEL", ""),
                "Quantity": qty_to_sell,
                "Price": price,
                "SoldBy": sold_by,
                "Customer": customer,
                "Type": sale_type
            }
            sales_df = pd.concat([sales_df, pd.DataFrame([sale_row])], ignore_index=True)
            save_sales(sales_df)
            # Audit log
            audit_row = {
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "BARCODE": barcode_input,
                "Action": sale_type,
                "Product": product.get("MODEL", ""),
                "Quantity": qty_to_sell,
                "User": sold_by,
                "Details": f"{sale_type} to {customer} ({product_source})",
                "Client IP": get_client_ip(),
                "Qty Before": qty_before,
                "Qty After": new_qty
            }
            audit_df = pd.concat([audit_df, pd.DataFrame([audit_row])], ignore_index=True)
            save_audit(audit_df)
            st.success(f"{sale_type} processed: {qty_to_sell} units of {product.get('MODEL', '')}. Inventory updated.")
    elif barcode:
        st.error("Product not found in inventory or archive.")

with details_col:
    st.subheader("Product Details")
    if not product_row.empty:
        st.write(f"**Model:** {product.get('MODEL', '')}")
        st.write(f"**Size:** {product.get('SIZE', '')}")
        st.write(f"**Frame Colour:** {product.get('F COLOUR', '')}")
        st.write(f"**Manufacturer:** {product.get('MANUFACTURER', '')}")
        st.write(f"**Current Stock:** {product.get('QUANTITY', 0) if product_source == 'Inventory' else 'Archived'}")
        st.write(f"**RRP:** {product.get('RRP', 0)}")
        st.write(f"**FRAME NO.:** {product.get('FRAME NO.', '')}")
        st.write(f"**FRSTATUS:** {product.get('FRSTATUS', '')}")
        st.write(f"**LOCATION:** {product.get('LOCATION', '')}")

with st.expander("Sales History", expanded=False):
    # Show newest first
    st.dataframe(sales_df.sort_values(by="Timestamp", ascending=False).head(100), use_container_width=True)
    # --- Download button for sales history ---
    output = io.BytesIO()
    sales_df.to_excel(output, index=False)
    output.seek(0)
    st.download_button(
        label="⬇️ Download Sales History (Excel)",
        data=output,
        file_name="sales_history.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

with st.expander("Audit Log", expanded=False):
    # Show newest first
    st.dataframe(audit_df.sort_values(by="Timestamp", ascending=False).head(100), use_container_width=True)
    # --- Download button for audit log ---
    output_audit = io.BytesIO()
    audit_df.to_excel(output_audit, index=False)
    output_audit.seek(0)
    st.download_button(
        label="⬇️ Download Audit Log (Excel)",
        data=output_audit,
        file_name="audit_log.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
