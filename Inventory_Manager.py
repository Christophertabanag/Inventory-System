import streamlit as st
import pandas as pd
import numpy as np
import os
from datetime import datetime
import random
import barcode
from barcode.writer import ImageWriter
import io

# --- Custom CSS for green buttons and narrower textfields ---
st.markdown("""
    <style>
    div.stButton > button:first-child {
        background-color: #27ae60;
        color: white;
        font-weight: bold;
        border-radius: 6px;
        border: none;
        height: 38px;
        min-width: 170px;
        margin-bottom: 3px;
    }
    input[type="text"], textarea {
        max-width: 180px;
    }
    [data-baseweb="select"] {
        max-width: 180px;
    }
    div[data-testid="stNumberInput"] {
        max-width: 180px;
    }
    </style>
    """, unsafe_allow_html=True)

def clean_nans(df):
    df = df.replace([np.nan, pd.NA, 'nan'], '', regex=True)
    return df

def force_all_columns_to_string(df):
    for col in df.columns:
        df[col] = df[col].astype(str)
    return df

def clean_barcode(val):
    if pd.isnull(val):
        return ""
    s = str(val).strip().replace('\u200b','').replace('\u00A0','')
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
        else:
            return str(int(round(f)))
    except ValueError:
        return s

def format_price(val):
    try:
        f = float(str(val).replace("$", "").strip())
        return f"${f:.2f}"
    except Exception:
        return f"${val}.00"

def format_rrp(val):
    # For backward compatibility
    return format_price(val)

INVENTORY_FOLDER = os.path.join(os.path.dirname(__file__), "Inventory")
inventory_files = [f for f in os.listdir(INVENTORY_FOLDER) if f.lower().endswith(('.xlsx', '.csv'))]
if not inventory_files:
    st.error("No inventory files found in the 'Inventory' folder.")
    st.stop()
selected_file = inventory_files[0]
if len(inventory_files) > 1:
    selected_file = st.selectbox("Select inventory file to use:", inventory_files)
INVENTORY_FILE = os.path.join(INVENTORY_FOLDER, selected_file)
ARCHIVE_FILE = os.path.join(INVENTORY_FOLDER, "archive_inventory.xlsx")

st.set_page_config(page_title="Inventory Manager", layout="wide")

# --- New fields and dropdowns as per your requirements ---
NEW_FIELDS = [
    "BARCODE", "QUANTITY", "MANUFACTURER", "MODEL", "FCOLOUR", "SIZE", "SUPPLIER",
    "FRAME TYPE", "TEMPLE", "DEPTH", "DIAG", "RRP", "EXCOSTPRICE", "COSTPRICE",
    "TAXPC", "FRSTATUS", "AVAILFROM", "NOTE"
]
SIZE_OPTIONS = [f"{i:02d}_{j:02d}" for i in range(100) for j in range(100)]
FRAME_TYPE_OPTIONS = ["Mens", "Womens", "Unisex", "Kids"]
TAXPC_OPTIONS = [f"GST {i}%" for i in range(1, 21)]
FRSTATUS_OPTIONS = ["CONSIGNMENT OWNED", "PRACTICE OWNED"]

# --- Old fields for backward compatibility ---
VISIBLE_FIELDS = [
    "BARCODE", "AVAILABILITY", "FRAMENUM", "SIZE", "MANUFACTURER", "MODEL", "PHOTO", "RRP",
    "LOCATION", "PKEY", "F COLOUR", "F GROUP", "SUPPLIER", "QUANTITY", "F TYPE", "TEMPLE", "DEPTH", "DIAG",
    "BASECURVE", "EXCOSTPR", "COST PRICE", "TAXPC", "FRSTATUS", "AVAIL FROM", "NOTE"
]
FREE_TEXT_FIELDS = [
    "PKEY", "F COLOUR", "F GROUP", "BASECURVE"
]
F_TYPE_OPTIONS = ["MEN", "WOMEN", "KIDS", "UNISEX"]
OLD_FRSTATUS_OPTIONS = ["CONSIGNMENT OWNED", "PRACTICE OWNED"]
OLD_TAXPC_OPTIONS = [f"GST {i}%" for i in range(1, 21)]
OLD_SIZE_OPTIONS = [f"{i:02d}-{j:02d}" for i in range(100) for j in range(100)]

def load_inventory():
    if os.path.exists(INVENTORY_FILE):
        if INVENTORY_FILE.lower().endswith('.xlsx'):
            df = pd.read_excel(INVENTORY_FILE)
        else:
            df = pd.read_csv(INVENTORY_FILE)
        df = force_all_columns_to_string(df)
        # Rename old frame number
        df.rename(columns={"FRAME NO.": "FRAMENUM"}, inplace=True)
        if "BARCODE" in df.columns:
            df["BARCODE"] = df["BARCODE"].map(clean_barcode)
        # Clean all price columns
        for pricefield in ["RRP", "EXCOSTPRICE", "COSTPRICE", "EXCOSTPR", "COST PRICE"]:
            if pricefield in df.columns:
                df[pricefield] = df[pricefield].apply(lambda x: str(x).replace("$", "").strip())
        # Move BARCODE to first column
        if "BARCODE" in df.columns:
            cols = list(df.columns)
            cols.insert(0, cols.pop(cols.index("BARCODE")))
            df = df[cols]
        return df
    else:
        st.error(f"Inventory file '{INVENTORY_FILE}' not found.")
        st.stop()

def load_archive_inventory():
    if os.path.exists(ARCHIVE_FILE):
        df = pd.read_excel(ARCHIVE_FILE)
        df = force_all_columns_to_string(df)
        df.rename(columns={"FRAME NO.": "FRAMENUM"}, inplace=True)
        if "BARCODE" in df.columns:
            df["BARCODE"] = df["BARCODE"].map(clean_barcode)
        for pricefield in ["RRP", "EXCOSTPRICE", "COSTPRICE", "EXCOSTPR", "COST PRICE"]:
            if pricefield in df.columns:
                df[pricefield] = df[pricefield].apply(lambda x: str(x).replace("$", "").strip())
        if "BARCODE" in df.columns:
            cols = list(df.columns)
            cols.insert(0, cols.pop(cols.index("BARCODE")))
            df = df[cols]
        return df
    else:
        return pd.DataFrame()

def generate_unique_barcode(df):
    while True:
        barcode_val = str(random.randint(1, 11000))
        barcode_val_clean = clean_barcode(barcode_val)
        if "BARCODE" not in df.columns or barcode_val_clean not in df["BARCODE"].map(clean_barcode).values:
            return barcode_val_clean

def generate_framecode(supplier, df):
    prefix = supplier[:3].upper()
    frame_col = "FRAMENUM"
    if frame_col not in df.columns:
        return prefix + "000001"
    framecodes = df[frame_col].dropna().astype(str)
    matching = framecodes[framecodes.str.startswith(prefix)]
    nums = matching.str[len(prefix):].str.extract(r'(\d{6})')[0].dropna()
    if not nums.empty:
        max_num = int(nums.max())
        next_num = max_num + 1
    else:
        next_num = 1
    return f"{prefix}{next_num:06d}"

def generate_barcode_image(code):
    try:
        CODE128 = barcode.get_barcode_class('code128')
        code = str(code)
        if not code:
            st.error("Barcode value cannot be empty.")
            return None
        my_code = CODE128(code, writer=ImageWriter())
        buffer = io.BytesIO()
        my_code.write(buffer, options={"write_text": False})
        buffer.seek(0)
        return buffer
    except Exception as e:
        st.error(f"Error generating barcode image: {e}")
        return None

def get_smart_default(header, df):
    if header in df.columns and not df[header].dropna().empty:
        recent = df[header].dropna().iloc[-1]
        if recent: return str(recent)
    if header in df.columns and not df[header].dropna().empty:
        most_common = df[header].dropna().mode()
        if not most_common.empty: return str(most_common.iloc[0])
    if header == "MANUFACTURER":
        return "Ray-Ban"
    if header == "SUPPLIER":
        return "Default Supplier"
    if header in ("F TYPE", "FRAME TYPE"):
        return "MEN"
    if header == "RRP":
        return "120.00"
    if header in ("EXCOSTPR", "EXCOSTPRICE"):
        return "60.00"
    if header in ("COST PRICE", "COSTPRICE"):
        return "70.00"
    if header == "TAXPC":
        return "GST 10%"
    if header in ("AVAIL FROM", "AVAILFROM"):
        return datetime.now().date()
    if header == "FRSTATUS":
        return "PRACTICE OWNED"
    if header == "NOTE":
        return ""
    return ""

if "add_product_expanded" not in st.session_state:
    st.session_state["add_product_expanded"] = False
if "barcode" not in st.session_state:
    st.session_state["barcode"] = ""
if "framecode" not in st.session_state:
    st.session_state["framecode"] = ""
if "edit_product_index" not in st.session_state:
    st.session_state["edit_product_index"] = None
if "edit_delete_expanded" not in st.session_state:
    st.session_state["edit_delete_expanded"] = False
if "pending_delete_index" not in st.session_state:
    st.session_state["pending_delete_index"] = None
if "pending_delete_confirmed" not in st.session_state:
    st.session_state["pending_delete_confirmed"] = False
if "supplier_for_framecode" not in st.session_state:
    st.session_state["supplier_for_framecode"] = ""
if "last_deleted_product" not in st.session_state:
    st.session_state["last_deleted_product"] = None

df = load_inventory()
archive_df = load_archive_inventory()
columns = list(df.columns)
barcode_col = "BARCODE"
framecode_col = "FRAMENUM"

headers = [h for h in columns if h.lower() != "timestamp"]

st.title("Inventory Manager")

st.markdown("#### Generate Unique Barcodes")
btn_col1, btn_col2 = st.columns(2)
with btn_col1:
    if st.button("Generate Barcode"):
        st.session_state["barcode"] = generate_unique_barcode(df)
        st.session_state["add_product_expanded"] = True
with btn_col2:
    supplier_val = st.text_input(
        "Enter Supplier for Framecode Generation",
        value=st.session_state.get("supplier_for_framecode", ""),
        key="supplier_for_framecode",
        on_change=None,
    )
    if st.button("Generate Framecode"):
        if st.session_state["supplier_for_framecode"]:
            st.session_state["framecode"] = generate_framecode(st.session_state["supplier_for_framecode"], df)
            st.session_state["add_product_expanded"] = True
        else:
            st.warning("⚠️ Please enter a supplier name first.")

if st.session_state["barcode"]:
    st.markdown("#### Barcode Image")
    img_buffer = generate_barcode_image(st.session_state["barcode"])
    if img_buffer:
        st.image(img_buffer, width=220)

# --- Add Product Section (includes both NEW_FIELDS + legacy as fallback) ---
with st.expander("➕ Add a New Product", expanded=st.session_state["add_product_expanded"]):
    input_values = {}
    # Lay out new fields in 3 columns
    col1, col2, col3 = st.columns(3)
    with col1:
        input_values["BARCODE"] = st.text_input("BARCODE", value=st.session_state["barcode"])
        input_values["QUANTITY"] = st.number_input("QUANTITY", min_value=0, value=1)
        input_values["MANUFACTURER"] = st.text_input("MANUFACTURER")
        input_values["MODEL"] = st.text_input("MODEL")
        input_values["FCOLOUR"] = st.text_input("FCOLOUR")
        input_values["SIZE"] = st.selectbox("SIZE", SIZE_OPTIONS)
    with col2:
        input_values["SUPPLIER"] = st.text_input("SUPPLIER")
        input_values["FRAME TYPE"] = st.selectbox("FRAME TYPE", FRAME_TYPE_OPTIONS)
        input_values["TEMPLE"] = st.text_input("TEMPLE")
        input_values["DEPTH"] = st.text_input("DEPTH")
        input_values["DIAG"] = st.text_input("DIAG")
        input_values["RRP"] = st.text_input("RRP")
    with col3:
        input_values["EXCOSTPRICE"] = st.text_input("EXCOSTPRICE")
        input_values["COSTPRICE"] = st.text_input("COSTPRICE")
        input_values["TAXPC"] = st.selectbox("TAXPC", TAXPC_OPTIONS)
        input_values["FRSTATUS"] = st.selectbox("FRSTATUS", FRSTATUS_OPTIONS)
        input_values["AVAILFROM"] = st.date_input("AVAILFROM", value=datetime.now().date())
        input_values["NOTE"] = st.text_input("NOTE")

    # For legacy fields, fallback to old fields UI
    legacy_col1, legacy_col2, legacy_col3 = st.columns(3)
    with legacy_col1:
        input_values["AVAILABILITY"] = st.text_input("AVAILABILITY")
        input_values["FRAMENUM"] = st.text_input("FRAME NUMBER", value=st.session_state["framecode"])
        input_values["PHOTO"] = st.text_input("PHOTO")
        input_values["LOCATION"] = st.text_input("LOCATION")
    with legacy_col2:
        input_values["PKEY"] = st.text_input("PKEY")
        input_values["F COLOUR"] = st.text_input("F COLOUR")
        input_values["F GROUP"] = st.text_input("F GROUP")
        input_values["F TYPE"] = st.selectbox("F TYPE", F_TYPE_OPTIONS)
    with legacy_col3:
        input_values["BASECURVE"] = st.text_input("BASECURVE")
        input_values["EXCOSTPR"] = st.text_input("EXCOSTPR")
        input_values["COST PRICE"] = st.text_input("COST PRICE")
        input_values["AVAIL FROM"] = st.date_input("AVAIL FROM", value=datetime.now().date())

    with st.form(key="add_product_form"):
        st.markdown("Click 'Add Product' to submit the details above.")
        submit = st.form_submit_button("Add Product")
        if submit:
            # Validate both new and legacy required fields
            required_fields = ["BARCODE", "FRAMENUM"]
            missing = [field for field in required_fields if not input_values.get(field)]
            barcode_cleaned = clean_barcode(input_values.get("BARCODE", ""))
            framecode_cleaned = clean_barcode(input_values.get("FRAMENUM", ""))
            df_barcodes_cleaned = df["BARCODE"].map(clean_barcode)
            df_framecodes_cleaned = df["FRAMENUM"].map(clean_barcode) if "FRAMENUM" in df.columns else pd.Series([])
            if missing:
                st.warning(f"⚠️ {', '.join(missing)} are required.")
            elif barcode_cleaned in df_barcodes_cleaned.values:
                st.error("❌ This barcode already exists in inventory!")
            elif framecode_cleaned in df_framecodes_cleaned.values:
                st.error("❌ This framecode already exists in inventory!")
            else:
                new_row = {}
                # Add new fields
                for col in NEW_FIELDS:
                    val = input_values.get(col, "")
                    if col == "BARCODE":
                        val = clean_barcode(val)
                    if col in ["RRP", "EXCOSTPRICE", "COSTPRICE"]:
                        val = str(val).replace("$", "").strip()
                    if col == "AVAILFROM" and isinstance(val, (datetime, pd.Timestamp)):
                        val = val.strftime('%Y-%m-%d')
                    new_row[col] = val
                # Add legacy fields if present
                for col in VISIBLE_FIELDS:
                    if col not in NEW_FIELDS:
                        val = input_values.get(col, "")
                        if col == "BARCODE":
                            val = clean_barcode(val)
                        if col in ["RRP", "EXCOSTPR", "COST PRICE"]:
                            val = str(val).replace("$", "").strip()
                        if col in ["AVAIL FROM"] and isinstance(val, (datetime, pd.Timestamp)):
                            val = val.strftime('%Y-%m-%d')
                        new_row[col] = val
                if "Timestamp" in df.columns:
                    new_row["Timestamp"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                df = clean_nans(df)
                df = force_all_columns_to_string(df)
                df["BARCODE"] = df["BARCODE"].map(clean_barcode)
                for pricefield in ["RRP", "EXCOSTPRICE", "COSTPRICE", "EXCOSTPR", "COST PRICE"]:
                    if pricefield in df.columns:
                        df[pricefield] = df[pricefield].apply(lambda x: str(x).replace("$", "").strip())
                if INVENTORY_FILE.lower().endswith('.xlsx'):
                    df.to_excel(INVENTORY_FILE, index=False)
                else:
                    df.to_csv(INVENTORY_FILE, index=False)
                st.success(f"✅ Product added successfully!")
                st.session_state["barcode"] = ""
                st.session_state["framecode"] = ""
                st.session_state["add_product_expanded"] = False
                st.rerun()

# --- Display inventory table with formatted prices ---
st.markdown('### Current Inventory')
df_display = df.copy()
for pricefield in ["RRP", "EXCOSTPRICE", "COSTPRICE", "EXCOSTPR", "COST PRICE"]:
    if pricefield in df_display.columns:
        df_display[pricefield] = df_display[pricefield].apply(format_price)
st.dataframe(clean_nans(df_display), width='stretch')

download_date_str = datetime.now().strftime("%Y-%m-%d")
custom_download_name = f"fil-{selected_file.split('.')[0]}_{download_date_str}-downloaded"
st.download_button(
    label="🗂️ Download as CSV",
    data=clean_nans(df).to_csv(index=False).encode('utf-8'),
    file_name=f"{custom_download_name}.csv",
    mime="text/csv"
)
excel_buffer = io.BytesIO()
clean_nans(df).to_excel(excel_buffer, index=False)
excel_buffer.seek(0)
st.download_button(
    label="📄 Download as Excel",
    data=excel_buffer,
    file_name=f"{custom_download_name}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

if not archive_df.empty:
    st.markdown("### Archive Inventory")
    archive_df_display = archive_df.copy()
    for pricefield in ["RRP", "EXCOSTPRICE", "COSTPRICE", "EXCOSTPR", "COST PRICE"]:
        if pricefield in archive_df_display.columns:
            archive_df_display[pricefield] = archive_df_display[pricefield].apply(format_price)
    st.dataframe(clean_nans(archive_df_display), width='stretch')
    archive_download_name = f"fil-archive_{download_date_str}-downloaded"
    arch_col1, arch_col2 = st.columns([1, 1])
    with arch_col1:
        st.download_button(
            label="📄 Archive Excel",
            data=open(ARCHIVE_FILE, "rb").read(),
            file_name=f"{archive_download_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with arch_col2:
        archive_csv_bytes = clean_nans(archive_df).to_csv(index=False).encode('utf-8')
        st.download_button(
            label="🗂️ Archive CSV",
            data=archive_csv_bytes,
            file_name=f"{archive_download_name}.csv",
            mime="text/csv"
        )

# --- Edit/Delete section (legacy style but compatible with new fields) ---
with st.expander("✏️ Edit or 🗑 Delete Products", expanded=st.session_state["edit_delete_expanded"]):
    if len(df) > 0:
        selected_row = st.selectbox(
            "Select a product to edit or delete",
            options=df.index.tolist(),
            format_func=lambda i: f"{clean_barcode(df.at[i, barcode_col])} - {clean_barcode(df.at[i, framecode_col])}" if framecode_col in df.columns else f"{clean_barcode(df.at[i, barcode_col])}",
            key="selected_product"
        )
        if selected_row is not None:
            st.session_state["edit_product_index"] = selected_row
            product = df.loc[selected_row]
            edit_values = {}
            # Lay out editing fields in 3 columns for all new and legacy fields
            edit_headers = [col for col in NEW_FIELDS if col in df.columns] + [col for col in VISIBLE_FIELDS if col not in NEW_FIELDS and col in df.columns]
            edit_header_rows = [edit_headers[i:i+3] for i in range(0, len(edit_headers), 3)]
            for row in edit_header_rows:
                cols = st.columns(len(row))
                for idx, header in enumerate(row):
                    value = product[header] if header in product else ""
                    if header == "SIZE":
                        edit_values[header] = cols[idx].selectbox(header, SIZE_OPTIONS, index=SIZE_OPTIONS.index(str(value)) if str(value) in SIZE_OPTIONS else 0, key=f"edit_{header}_{selected_row}")
                    elif header == "FRAME TYPE":
                        edit_values[header] = cols[idx].selectbox(header, FRAME_TYPE_OPTIONS, index=FRAME_TYPE_OPTIONS.index(str(value)) if str(value) in FRAME_TYPE_OPTIONS else 0, key=f"edit_{header}_{selected_row}")
                    elif header == "TAXPC":
                        edit_values[header] = cols[idx].selectbox(header, TAXPC_OPTIONS, index=TAXPC_OPTIONS.index(str(value)) if str(value) in TAXPC_OPTIONS else 0, key=f"edit_{header}_{selected_row}")
                    elif header == "FRSTATUS":
                        edit_values[header] = cols[idx].selectbox(header, FRSTATUS_OPTIONS, index=FRSTATUS_OPTIONS.index(str(value)) if str(value) in FRSTATUS_OPTIONS else 0, key=f"edit_{header}_{selected_row}")
                    elif header in ["AVAILFROM", "AVAIL FROM"]:
                        try:
                            date_val = pd.to_datetime(value).date() if value else datetime.now().date()
                        except Exception:
                            date_val = datetime.now().date()
                        edit_values[header] = cols[idx].date_input(header, value=date_val, key=f"edit_{header}_{selected_row}")
                    elif header == "QUANTITY":
                        try:
                            default_qty = int(str(value)) if str(value).isdigit() else 1
                        except:
                            default_qty = 1
                        edit_values[header] = cols[idx].number_input(header, min_value=0, value=default_qty, key=f"edit_{header}_{selected_row}")
                    else:
                        edit_values[header] = cols[idx].text_input(header, value=str(value), key=f"edit_{header}_{selected_row}")
            with st.form(key=f"edit_form_{selected_row}"):
                col1, col2 = st.columns(2)
                submit_edit = col1.form_submit_button("Save Changes")
                submit_delete = col2.form_submit_button("Delete Product")
                if submit_edit:
                    # Clean and save edited values
                    for h in edit_headers:
                        if h in edit_values:
                            val = edit_values[h]
                            if h == "BARCODE":
                                val = clean_barcode(val)
                            if h in ["RRP", "EXCOSTPRICE", "COSTPRICE", "EXCOSTPR", "COST PRICE"]:
                                val = str(val).replace("$", "").strip()
                            if h in ["AVAILFROM", "AVAIL FROM"] and isinstance(val, (datetime, pd.Timestamp)):
                                val = val.strftime('%Y-%m-%d')
                            df.at[selected_row, h] = val
                        else:
                            df.at[selected_row, h] = ""
                    if "Timestamp" in df.columns:
                        df.at[selected_row, "Timestamp"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    df = clean_nans(df)
                    df = force_all_columns_to_string(df)
                    df["BARCODE"] = df["BARCODE"].map(clean_barcode)
                    for pricefield in ["RRP", "EXCOSTPRICE", "COSTPRICE", "EXCOSTPR", "COST PRICE"]:
                        if pricefield in df.columns:
                            df[pricefield] = df[pricefield].apply(lambda x: str(x).replace("$", "").strip())
                    if INVENTORY_FILE.lower().endswith('.xlsx'):
                        df.to_excel(INVENTORY_FILE, index=False)
                    else:
                        df.to_csv(INVENTORY_FILE, index=False)
                    st.success("✅ Product updated successfully!")
                    st.session_state["edit_delete_expanded"] = True
                    st.rerun()
                if submit_delete:
                    st.session_state["pending_delete_index"] = selected_row
    else:
        st.info("ℹ️ No products in inventory yet.")

if st.session_state.get("pending_delete_index") is not None:
    st.warning(f"⚠️ Are you sure you want to delete product with barcode '{clean_barcode(df.at[st.session_state['pending_delete_index'], barcode_col])}' and framecode '{clean_barcode(df.at[st.session_state['pending_delete_index'], framecode_col])}'?")
    confirm_col, cancel_col = st.columns(2)
    with confirm_col:
        if st.button("Confirm Delete", key="confirm_delete_btn"):
            df = df.drop(st.session_state["pending_delete_index"]).reset_index(drop=True)
            df = clean_nans(df)
            df = force_all_columns_to_string(df)
            df["BARCODE"] = df["BARCODE"].map(clean_barcode)
            for pricefield in ["RRP", "EXCOSTPRICE", "COSTPRICE", "EXCOSTPR", "COST PRICE"]:
                if pricefield in df.columns:
                    df[pricefield] = df[pricefield].apply(lambda x: str(x).replace("$", "").strip())
            if INVENTORY_FILE.lower().endswith('.xlsx'):
                df.to_excel(INVENTORY_FILE, index=False)
            else:
                df.to_csv(INVENTORY_FILE, index=False)
            st.success("✅ Product deleted successfully!")
            st.session_state["edit_product_index"] = None
            st.session_state["edit_delete_expanded"] = True
            st.session_state["pending_delete_index"] = None
            st.rerun()
    with cancel_col:
        if st.button("Cancel", key="cancel_delete_btn"):
            st.session_state["pending_delete_index"] = None

# --- Stock count uploader (unchanged) ---
with st.expander("📦 Stock Count"):
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

# --- Quick Stock Check (Scan Barcode) ---
with st.expander("🔍 Quick Stock Check (Scan Barcode)"):
    st.write("Place your cursor below, scan a barcode, and instantly see product details!")
    scanned_barcode = st.text_input("Scan Barcode", value="", key="stock_check_barcode_input")
    if scanned_barcode:
        cleaned_input = clean_barcode(scanned_barcode)
        matches = df[df[barcode_col].map(clean_barcode) == cleaned_input]
        if not matches.empty:
            matches = force_all_columns_to_string(matches)
            st.success("✅ Product found:")
            matches_display = matches.copy()
            for pricefield in ["RRP", "EXCOSTPRICE", "COSTPRICE", "EXCOSTPR", "COST PRICE"]:
                if pricefield in matches_display.columns:
                    matches_display[pricefield] = matches_display[pricefield].apply(format_price)
            st.dataframe(clean_nans(matches_display), width='stretch')
            product = matches.iloc[0]
            barcode_value = clean_barcode(product[barcode_col])
            barcode_img_buffer = generate_barcode_image(barcode_value)
            rrp = str(product.get("RRP", ""))
            rrp_display = format_price(rrp)
            framecode = str(product.get("FRAMENUM", ""))
            model = str(product.get("MODEL", "")) or str(product.get("MODEL", ""))
            manufact = str(product.get("MANUFACTURER", ""))
            fcolour = str(product.get("FCOLOUR", "")) or str(product.get("F COLOUR", ""))
            size = str(product.get("SIZE", "")) or str(product.get("SIZE", ""))
            st.markdown('<div class="print-label-block">', unsafe_allow_html=True)
            if barcode_img_buffer:
                st.image(barcode_img_buffer, width=220)
            st.markdown(f'<div class="print-label-barcode-num">{barcode_value}</div>', unsafe_allow_html=True)
            if rrp.strip() and rrp.strip() != "$.00" and rrp.strip() != "nan" and rrp.strip() != "":
                st.markdown(f'<div class="print-label-price">{rrp_display}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="print-label-gst">Inc GST</div>', unsafe_allow_html=True)
            st.markdown('<div class="print-label-details">', unsafe_allow_html=True)
            st.markdown(f'Framecode: {framecode}', unsafe_allow_html=True)
            st.markdown(f'Model: {model}', unsafe_allow_html=True)
            st.markdown(f'Manufacturer: {manufact}', unsafe_allow_html=True)
            st.markdown(f'Frame Colour: {fcolour}', unsafe_allow_html=True)
            st.markdown(f'Size: {size}', unsafe_allow_html=True)
            st.markdown('</div></div>', unsafe_allow_html=True)
        else:
            st.error("❌ Barcode not found in inventory.")
