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
        background-color: #27ae60 !important;
        color: white !important;
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
    # Always return barcode as a whole number string with no decimal
    if pd.isnull(val) or val == "":
        return ""
    s = str(val).strip().replace('\u200b','').replace('\u00A0','')
    try:
        f = float(s)
        s = str(int(f))
    except ValueError:
        pass
    return s

def format_rrp(val):
    # Always show price as $123.45
    try:
        f = float(str(val).replace("$", "").strip())
        return f"${f:.2f}"
    except Exception:
        return "$0.00"

INVENTORY_FOLDER = os.path.join(os.path.dirname(__file__), "Inventory")
inventory_files = [f for f in os.listdir(INVENTORY_FOLDER) if f.lower().endswith(('.xlsx', '.csv'))]

if not inventory_files:
    st.error("No inventory files found in the 'Inventory' folder.")
    st.stop()

selected_file = inventory_files[0]
if len(inventory_files) > 1:
    selected_file = st.selectbox("Select inventory file to use:", inventory_files)

INVENTORY_FILE = os.path.join(INVENTORY_FOLDER, selected_file)
ARCHIVE_FOLDER = INVENTORY_FOLDER
ARCHIVE_FILE = os.path.join(ARCHIVE_FOLDER, "archive_inventory.xlsx")

st.set_page_config(page_title="Inventory Manager", layout="wide")

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
        df.rename(columns={"FRAME NO.": "FRAMENUM"}, inplace=True)
        # Clean barcode column as whole number string
        if "BARCODE" in df.columns:
            df["BARCODE"] = df["BARCODE"].map(clean_barcode)
            cols = list(df.columns)
            cols.insert(0, cols.pop(cols.index("BARCODE")))
            df = df[cols]
        # Clean RRP column
        if "RRP" in df.columns:
            df["RRP"] = df["RRP"].apply(lambda x: str(x).replace("$", "").strip())
        # Add GSTSTAT column if missing, set all past products to "Inc. GST"
        if "GSTSTAT" not in df.columns:
            # Place GSTSTAT beside RRP
            cols = list(df.columns)
            if "RRP" in cols:
                rrp_index = cols.index("RRP")
                cols.insert(rrp_index + 1, "GSTSTAT")
            else:
                cols.append("GSTSTAT")
            df["GSTSTAT"] = "Inc. GST"
            df = df.reindex(columns=cols)
        else:
            df["GSTSTAT"] = df["GSTSTAT"].replace('', 'Inc. GST')
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
            cols = list(df.columns)
            cols.insert(0, cols.pop(cols.index("BARCODE")))
            df = df[cols]
        if "RRP" in df.columns:
            df["RRP"] = df["RRP"].apply(lambda x: str(x).replace("$", "").strip())
        # GSTSTAT for archive too
        if "GSTSTAT" not in df.columns:
            cols = list(df.columns)
            if "RRP" in cols:
                rrp_index = cols.index("RRP")
                cols.insert(rrp_index + 1, "GSTSTAT")
            else:
                cols.append("GSTSTAT")
            df["GSTSTAT"] = "Inc. GST"
            df = df.reindex(columns=cols)
        else:
            df["GSTSTAT"] = df["GSTSTAT"].replace('', 'Inc. GST')
        return df
    else:
        return pd.DataFrame()

def generate_unique_barcode(df):
    # Always generate and return as whole number string
    while True:
        barcode_val = str(random.randint(100000, 999999))  # 6 digits
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
    if header == "F TYPE":
        return "MEN"
    if header == "RRP":
        return "120.00"
    if header == "EXCOSTPR":
        return "60.00"
    if header == "COST PRICE":
        return "70.00"
    if header == "TAXPC":
        return "GST 10%"
    if header == "AVAIL FROM":
        return datetime.now().date()
    if header == "FRSTATUS":
        return "PRACTICE OWNED"
    if header == "NOTE":
        return ""
    if header == "GSTSTAT":
        return "Inc. GST"
    return ""

VISIBLE_FIELDS = [
    "BARCODE", "LOCATION", "FRAMENUM", "PKEY", "MANUFACTURER", "MODEL", "SIZE",
    "F COLOUR", "F GROUP", "SUPPLIER", "QUANTITY", "F TYPE", "TEMPLE", "DEPTH", "DIAG",
    "BASECURVE", "RRP", "GSTSTAT", "EXCOSTPR", "COST PRICE", "TAXPC", "FRSTATUS", "AVAIL FROM", "NOTE"
]
FREE_TEXT_FIELDS = [
    "PKEY", "F COLOUR", "F GROUP", "BASECURVE"
]
F_TYPE_OPTIONS = ["MEN", "WOMEN", "KIDS", "UNISEX"]
FRSTATUS_OPTIONS = ["CONSIGNMENT OWNED", "PRACTICE OWNED"]
TAXPC_OPTIONS = [f"GST {i}%" for i in range(1, 21)]
SIZE_OPTIONS = [f"{i:02d}-{j:02d}" for i in range(100) for j in range(100)]

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

if barcode_col not in columns or framecode_col not in columns:
    st.error(f"Couldn't find '{barcode_col}' or '{framecode_col}' columns in your inventory file.")
    st.write("Found columns:", columns)
    st.stop()

headers = [h for h in columns if h.lower() != "timestamp"]

st.title("Inventory Manager")

st.markdown("#### Generate Unique Barcodes")
btn_col1, btn_col2 = st.columns(2)
with btn_col1:
    if st.button("Generate Barcode", key="generate_barcode_btn"):
        st.session_state["barcode"] = generate_unique_barcode(df)
        st.session_state["add_product_expanded"] = True
with btn_col2:
    supplier_val = st.text_input(
        "Enter Supplier for Framecode Generation",
        value=st.session_state.get("supplier_for_framecode", ""),
        key="supplier_for_framecode",
        on_change=None,
    )
    if st.button("Generate Framecode", key="generate_framecode_btn"):
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

with st.expander("➕ Add a New Product", expanded=st.session_state["add_product_expanded"]):
    input_values = {}
    n_cols = 3
    visible_headers = [h for h in VISIBLE_FIELDS if h in headers]
    # Put GSTSTAT beside NOTE in the UI for adding
    if "GSTSTAT" in visible_headers and "NOTE" in visible_headers:
        visible_headers.remove("GSTSTAT")
        note_index = visible_headers.index("NOTE")
        visible_headers.insert(note_index + 1, "GSTSTAT")
    header_rows = [visible_headers[i:i+n_cols] for i in range(0, len(visible_headers), n_cols)]
    st.markdown("**Enter New Product Details:**")
    required_fields = [barcode_col, framecode_col]
    for row in header_rows:
        cols = st.columns(len(row), gap="small")
        for idx, header in enumerate(row):
            with cols[idx]:
                unique_key = f"textinput_{header}"
                smart_suggestion = get_smart_default(header, df)
                if header in [barcode_col, framecode_col]:
                    label = header
                else:
                    label = f"{header} <span class='required-label'>*</span>" if header in required_fields else header
                if header == barcode_col:
                    input_values[header] = st.text_input(
                        label, value=st.session_state["barcode"], key=unique_key, help="Unique product barcode"
                    )
                elif header == framecode_col:
                    input_values[header] = st.text_input(
                        label, value=st.session_state["framecode"], key=unique_key, help="Unique product frame code"
                    )
                elif header.upper() == "SUPPLIER":
                    input_values[header] = st.text_input(header, value=st.session_state.get("supplier_for_framecode", ""), key=unique_key)
                elif header.lower() == "model":
                    input_values[header] = st.text_input(header, value=smart_suggestion, key=unique_key)
                elif header.lower() == "size":
                    default_size = smart_suggestion if smart_suggestion in SIZE_OPTIONS else SIZE_OPTIONS[0]
                    input_values[header] = st.selectbox(header, SIZE_OPTIONS, index=SIZE_OPTIONS.index(default_size), key=unique_key)
                elif header.upper() in FREE_TEXT_FIELDS:
                    input_values[header] = st.text_input(header, value=smart_suggestion, key=unique_key)
                elif header.upper() == "MANUFACTURER":
                    input_values[header] = st.text_input(header, value=smart_suggestion, key=unique_key)
                elif header.upper() == "QUANTITY":
                    try:
                        default_qty = int(smart_suggestion) if smart_suggestion.isdigit() else 1
                    except:
                        default_qty = 1
                    input_values[header] = st.number_input(header, min_value=0, value=default_qty, key=unique_key)
                elif header.upper() == "F TYPE":
                    default_ftype = smart_suggestion if smart_suggestion in F_TYPE_OPTIONS else F_TYPE_OPTIONS[0]
                    input_values[header] = st.selectbox(header, F_TYPE_OPTIONS, index=F_TYPE_OPTIONS.index(default_ftype), key=unique_key)
                elif header.upper() == "FRSTATUS":
                    default_status = smart_suggestion if smart_suggestion in FRSTATUS_OPTIONS else FRSTATUS_OPTIONS[1]
                    input_values[header] = st.selectbox(header, FRSTATUS_OPTIONS, index=FRSTATUS_OPTIONS.index(default_status), key=unique_key)
                elif header.upper() in ["TEMPLE", "DEPTH", "DIAG", "EXCOSTPR", "COST PRICE"]:
                    input_values[header] = st.text_input(header, value=smart_suggestion, key=unique_key)
                elif header.upper() == "RRP":
                    input_values[header] = st.text_input(header, value=format_rrp(smart_suggestion), key=unique_key)
                elif header.upper() == "GSTSTAT":
                    input_values[header] = st.text_input(header, value=smart_suggestion or "Inc. GST", key=unique_key)
                elif header.upper() == "TAXPC":
                    default_tax = smart_suggestion if smart_suggestion in TAXPC_OPTIONS else TAXPC_OPTIONS[9]
                    input_values[header] = st.selectbox(header, TAXPC_OPTIONS, index=max(0, TAXPC_OPTIONS.index(default_tax)), key=unique_key)
                elif header.upper() == "AVAIL FROM":
                    date_val = datetime.now().date()
                    input_values[header] = st.date_input(header, value=date_val, key=unique_key)
                elif header.upper() == "NOTE":
                    input_values[header] = st.text_input(header, value=smart_suggestion, key=unique_key)
                else:
                    input_values[header] = st.text_input(header, value=smart_suggestion, key=unique_key)
    with st.form(key="add_product_form"):
        st.markdown("Click 'Add Product' to submit the details above.")
        submit = st.form_submit_button("Add Product")
        if submit:
            required_fields = [barcode_col, framecode_col]
            missing = [field for field in required_fields if field in visible_headers and not input_values.get(field)]
            barcode_cleaned = clean_barcode(input_values.get(barcode_col, ""))
            framecode_cleaned = clean_barcode(input_values.get(framecode_col, ""))
            df_barcodes_cleaned = df[barcode_col].map(clean_barcode)
            df_framecodes_cleaned = df[framecode_col].map(clean_barcode)
            if missing:
                st.warning(f"⚠️ {', '.join(missing)} are required.")
            elif barcode_cleaned in df_barcodes_cleaned.values:
                st.error("❌ This barcode already exists in inventory!")
            elif framecode_cleaned in df_framecodes_cleaned.values:
                st.error("❌ This framecode already exists in inventory!")
            else:
                new_row = {}
                for col in headers:
                    if col in input_values:
                        val = input_values[col]
                        if col == "AVAIL FROM" and isinstance(val, (datetime, pd.Timestamp)):
                            val = val.strftime('%Y-%m-%d')
                        if col == "BARCODE":
                            val = clean_barcode(val)
                        if col == "RRP":
                            val = format_rrp(val)
                        if col == "GSTSTAT":
                            val = val or "Inc. GST"
                        new_row[col] = val
                    else:
                        new_row[col] = ""
                if "Timestamp" in df.columns:
                    new_row["Timestamp"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                df = clean_nans(df)
                df = force_all_columns_to_string(df)
                df[barcode_col] = df[barcode_col].map(clean_barcode)
                if "RRP" in df.columns:
                    df["RRP"] = df["RRP"].apply(format_rrp)
                if "GSTSTAT" in df.columns:
                    df["GSTSTAT"] = df["GSTSTAT"].replace('', 'Inc. GST')
                if INVENTORY_FILE.lower().endswith('.xlsx'):
                    df.to_excel(INVENTORY_FILE, index=False)
                else:
                    df.to_csv(INVENTORY_FILE, index=False)
                st.success(f"✅ Product added successfully!")
                st.session_state["barcode"] = ""
                st.session_state["framecode"] = ""
                st.session_state["add_product_expanded"] = False
                st.rerun()

st.markdown('### Current Inventory')
df_display = df.copy()
if "RRP" in df_display.columns:
    df_display["RRP"] = df_display["RRP"].apply(format_rrp).astype(str)
if "BARCODE" in df_display.columns:
    df_display["BARCODE"] = df_display["BARCODE"].map(clean_barcode)
if "GSTSTAT" in df_display.columns:
    df_display["GSTSTAT"] = df_display["GSTSTAT"].replace('', 'Inc. GST')
st.dataframe(clean_nans(df_display), width='stretch')

download_date_str = datetime.now().strftime("%Y-%m-%d")
custom_download_name = f"fil-{selected_file.split('.')[0]}_{download_date_str}-downloaded"
excel_buffer = io.BytesIO()
df_display["RRP"] = df_display["RRP"].astype(str)
df_display["GSTSTAT"] = df_display["GSTSTAT"].astype(str)
clean_nans(df_display).to_excel(excel_buffer, index=False)
excel_buffer.seek(0)
st.download_button(
    label="📄 Download as Excel",
    data=excel_buffer,
    file_name=f"{custom_download_name}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
st.download_button(
    label="🗂️ Download as CSV",
    data=clean_nans(df_display).to_csv(index=False).encode('utf-8'),
    file_name=f"{custom_download_name}.csv",
    mime="text/csv"
)

if not archive_df.empty:
    st.markdown("### Archive Inventory")
    archive_df_display = archive_df.copy()
    if "RRP" in archive_df_display.columns:
        archive_df_display["RRP"] = archive_df_display["RRP"].apply(format_rrp).astype(str)
    if "BARCODE" in archive_df_display.columns:
        archive_df_display["BARCODE"] = archive_df_display["BARCODE"].map(clean_barcode)
    if "GSTSTAT" in archive_df_display.columns:
        archive_df_display["GSTSTAT"] = archive_df_display["GSTSTAT"].replace('', 'Inc. GST')
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
        archive_csv_bytes = clean_nans(archive_df_display).to_csv(index=False).encode('utf-8')
        st.download_button(
            label="🗂️ Archive CSV",
            data=archive_csv_bytes,
            file_name=f"{archive_download_name}.csv",
            mime="text/csv"
        )

with st.expander("✏️ Edit or 🗑 Delete Products", expanded=st.session_state["edit_delete_expanded"]):
    if len(df) > 0:
        selected_row = st.selectbox(
            "Select a product to edit or delete",
            options=df.index.tolist(),
            format_func=lambda i: f"{clean_barcode(df.at[i, barcode_col])} - {clean_barcode(df.at[i, framecode_col])}",
            key="selected_product"
        )
        if selected_row is not None:
            st.session_state["edit_product_index"] = selected_row
            product = df.loc[selected_row]
            edit_values = {}
            n_cols = 3
            visible_headers = [h for h in VISIBLE_FIELDS if h in headers]
            # Put GSTSTAT beside NOTE in the UI for editing
            if "GSTSTAT" in visible_headers and "NOTE" in visible_headers:
                visible_headers.remove("GSTSTAT")
                note_index = visible_headers.index("NOTE")
                visible_headers.insert(note_index + 1, "GSTSTAT")
            header_rows = [visible_headers[i:i+n_cols] for i in range(0, len(visible_headers), n_cols)]
            st.markdown("**Edit Product Details**")
            required_fields = [barcode_col, framecode_col]
            for row in header_rows:
                cols = st.columns(len(row), gap="small")
                for idx, header in enumerate(row):
                    value = product[header] if header in product else ""
                    show_value = clean_barcode(value) if header in [barcode_col, framecode_col] else value
                    unique_key = f"edit_textinput_{header}_{selected_row}"
                    smart_suggestion = get_smart_default(header, df)
                    if header in [barcode_col, framecode_col]:
                        label = header
                    else:
                        label = f"{header} <span class='required-label'>*</span>" if header in required_fields else header
                    if header == barcode_col or header == framecode_col:
                        edit_values[header] = st.text_input(label, value=str(show_value), key=unique_key)
                    elif header.upper() == "SUPPLIER":
                        edit_values[header] = st.text_input(header, value=str(show_value), key=unique_key)
                    elif header.lower() == "model":
                        edit_values[header] = st.text_input(header, value=str(show_value), key=unique_key)
                    elif header.lower() == "size":
                        default_size = str(show_value) if str(show_value) in SIZE_OPTIONS else SIZE_OPTIONS[0]
                        edit_values[header] = st.selectbox(header, SIZE_OPTIONS, index=SIZE_OPTIONS.index(default_size), key=unique_key)
                    elif header.upper() in FREE_TEXT_FIELDS:
                        edit_values[header] = st.text_input(header, value=str(show_value), key=unique_key)
                    elif header.upper() == "MANUFACTURER":
                        edit_values[header] = st.text_input(header, value=str(show_value), key=unique_key)
                    elif header.upper() == "QUANTITY":
                        try:
                            default_qty = int(str(show_value)) if str(show_value).isdigit() else 1
                        except:
                            default_qty = 1
                        edit_values[header] = st.number_input(header, min_value=0, value=default_qty, key=unique_key)
                    elif header.upper() == "F TYPE":
                        default_ftype = str(show_value) if str(show_value) in F_TYPE_OPTIONS else F_TYPE_OPTIONS[0]
                        edit_values[header] = st.selectbox(header, F_TYPE_OPTIONS, index=F_TYPE_OPTIONS.index(default_ftype), key=unique_key)
                    elif header.upper() == "FRSTATUS":
                        default_status = str(show_value) if str(show_value) in FRSTATUS_OPTIONS else FRSTATUS_OPTIONS[1]
                        edit_values[header] = st.selectbox(header, FRSTATUS_OPTIONS, index=FRSTATUS_OPTIONS.index(default_status), key=unique_key)
                    elif header.upper() in ["TEMPLE", "DEPTH", "DIAG", "EXCOSTPR", "COST PRICE"]:
                        edit_values[header] = st.text_input(header, value=str(show_value), key=unique_key)
                    elif header.upper() == "RRP":
                        edit_values[header] = st.text_input(header, value=format_rrp(show_value), key=unique_key)
                    elif header.upper() == "GSTSTAT":
                        edit_values[header] = st.text_input(header, value=str(show_value) or "Inc. GST", key=unique_key)
                    elif header.upper() == "TAXPC":
                        default_tax = str(show_value) if str(show_value) in TAXPC_OPTIONS else TAXPC_OPTIONS[9]
                        edit_values[header] = st.selectbox(header, TAXPC_OPTIONS, index=max(0, TAXPC_OPTIONS.index(default_tax)), key=unique_key)
                    elif header.upper() == "AVAIL FROM":
                        try:
                            if pd.isnull(show_value) or show_value == "":
                                date_val = datetime.now().date()
                            else:
                                date_val = pd.to_datetime(show_value).date()
                        except Exception:
                            date_val = datetime.now().date()
                        edit_values[header] = st.date_input(header, value=date_val, key=unique_key)
                    elif header.upper() == "NOTE":
                        edit_values[header] = st.text_input(header, value=str(show_value), key=unique_key)
                    else:
                        edit_values[header] = st.text_input(header, value=str(show_value), key=unique_key)
            with st.form(key=f"edit_form_{selected_row}"):
                col1, col2 = st.columns(2)
                submit_edit = col1.form_submit_button("Save Changes")
                submit_delete = col2.form_submit_button("Delete Product")
                if submit_edit:
                    if "AVAIL FROM" in edit_values and isinstance(edit_values["AVAIL FROM"], (datetime, pd.Timestamp)):
                        edit_values["AVAIL FROM"] = edit_values["AVAIL FROM"].strftime('%Y-%m-%d')
                    edit_barcode_cleaned = clean_barcode(edit_values[barcode_col])
                    edit_framecode_cleaned = clean_barcode(edit_values[framecode_col])
                    df_barcodes_cleaned = df[barcode_col].map(clean_barcode)
                    df_framecodes_cleaned = df[framecode_col].map(clean_barcode)
                    duplicate_barcode = (df_barcodes_cleaned == edit_barcode_cleaned) & (df.index != selected_row)
                    duplicate_framecode = (df_framecodes_cleaned == edit_framecode_cleaned) & (df.index != selected_row)
                    if duplicate_barcode.any():
                        st.error("❌ Another product with this barcode already exists!")
                    elif duplicate_framecode.any():
                        st.error("❌ Another product with this framecode already exists!")
                    else:
                        for h in headers:
                            if h in edit_values:
                                val = edit_values[h]
                                if h == "AVAIL FROM" and isinstance(val, (datetime, pd.Timestamp)):
                                    val = val.strftime('%Y-%m-%d')
                                if h == "BARCODE":
                                    val = clean_barcode(val)
                                if h == "RRP":
                                    val = format_rrp(val)
                                if h == "GSTSTAT":
                                    val = val or "Inc. GST"
                                df.at[selected_row, h] = val
                            else:
                                df.at[selected_row, h] = ""
                        if "Timestamp" in df.columns:
                            df.at[selected_row, "Timestamp"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        df = clean_nans(df)
                        df = force_all_columns_to_string(df)
                        df[barcode_col] = df[barcode_col].map(clean_barcode)
                        if "RRP" in df.columns:
                            df["RRP"] = df["RRP"].apply(format_rrp)
                        if "GSTSTAT" in df.columns:
                            df["GSTSTAT"] = df["GSTSTAT"].replace('', 'Inc. GST')
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
            df[barcode_col] = df[barcode_col].map(clean_barcode)
            if "RRP" in df.columns:
                df["RRP"] = df["RRP"].apply(format_rrp)
            if "GSTSTAT" in df.columns:
                df["GSTSTAT"] = df["GSTSTAT"].replace('', 'Inc. GST')
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
            if "RRP" in matches_display.columns:
                matches_display["RRP"] = matches_display["RRP"].apply(format_rrp)
            if "BARCODE" in matches_display.columns:
                matches_display["BARCODE"] = matches_display["BARCODE"].map(clean_barcode)
            if "GSTSTAT" in matches_display.columns:
                matches_display["GSTSTAT"] = matches_display["GSTSTAT"].replace('', 'Inc. GST')
            st.dataframe(clean_nans(matches_display), width='stretch')
            product = matches.iloc[0]
            barcode_value = clean_barcode(product[barcode_col])
            barcode_img_buffer = generate_barcode_image(barcode_value)
            rrp = str(product.get("RRP", ""))
            rrp_display = format_rrp(rrp)
            framecode = str(product.get("FRAMENUM", ""))
            model = str(product.get("MODEL", ""))
            manufact = str(product.get("MANUFACTURER", ""))
            fcolour = str(product.get("F COLOUR", ""))
            size = str(product.get("SIZE", ""))
            gststat = str(product.get("GSTSTAT", "Inc. GST"))
            st.markdown('<div class="print-label-block">', unsafe_allow_html=True)
            if barcode_img_buffer:
                st.image(barcode_img_buffer, width=220)
            st.markdown(f'<div class="print-label-barcode-num">{barcode_value}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="print-label-price">{rrp_display}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="print-label-gst">{gststat}</div>', unsafe_allow_html=True)
            st.markdown('<div class="print-label-details">', unsafe_allow_html=True)
            st.markdown(f'Framecode: {framecode}', unsafe_allow_html=True)
            st.markdown(f'Model: {model}', unsafe_allow_html=True)
            st.markdown(f'Manufacturer: {manufact}', unsafe_allow_html=True)
            st.markdown(f'Frame Colour: {fcolour}', unsafe_allow_html=True)
            st.markdown(f'Size: {size}', unsafe_allow_html=True)
            st.markdown('</div></div>', unsafe_allow_html=True)
        else:
            st.error("❌ Barcode not found in inventory.")
