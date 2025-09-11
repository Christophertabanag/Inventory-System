import streamlit as st
import pandas as pd
import os
import barcode
from barcode.writer import ImageWriter
import io
import base64
from collections import OrderedDict
import tempfile
from fpdf import FPDF
import json

# --- CONFIGURATION ---
INVENTORY_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "inventory.xlsx")
)
DEFAULT_LABEL_WIDTH = 300
DEFAULT_LABEL_HEIGHT = 150
DEFAULT_FONT_SIZE = 16
DEFAULT_BARCODE_WIDTH = 220
DEFAULT_MARGIN = 8
BARCODE_TYPES = ["code128", "ean13", "ean8", "upc", "isbn13"]
TEMPLATE_FILE = os.path.join(os.path.dirname(__file__), "templates.json")

# --- Persistent Template Save/Load ---
def save_templates_to_disk(templates):
    with open(TEMPLATE_FILE, "w") as f:
        json.dump(templates, f)

def load_templates_from_disk():
    if os.path.exists(TEMPLATE_FILE):
        with open(TEMPLATE_FILE, "r") as f:
            return json.load(f)
    return {}

FIELD_LABELS = OrderedDict([
    ("BARCODE", "Barcode Number"),
    ("RRP", "Price"),
    ("FRAME NO.", "Framecode"),
    ("MODEL", "Model"),
    ("MANUFACTURER", "Manufacturer"),
    ("F COLOUR", "Frame Colour"),
    ("SIZE", "Size"),
])

# --- Early Template Load ---
if "saved_templates" not in st.session_state:
    st.session_state["saved_templates"] = load_templates_from_disk()

field_order_default = list(FIELD_LABELS.keys())
for k, v in [
    ("label_width", DEFAULT_LABEL_WIDTH),
    ("label_height", DEFAULT_LABEL_HEIGHT),
    ("font_size", DEFAULT_FONT_SIZE),
    ("barcode_type", "code128"),
    ("barcode_width", DEFAULT_BARCODE_WIDTH),
    ("margin", DEFAULT_MARGIN),
    ("orientation", "Landscape"),
    ("inc_gst_text", "Inc GST"),
    ("field_order", field_order_default)
]:
    if k not in st.session_state:
        st.session_state[k] = v

# --- Restore product selection after template load ---
if "template_to_load" in st.session_state:
    t = st.session_state["saved_templates"][st.session_state["template_to_load"]]
    st.session_state.label_width = t["width"]
    st.session_state.label_height = t["height"]
    st.session_state.font_size = t["font_size"]
    st.session_state.barcode_type = t["barcode_type"]
    st.session_state.barcode_width = t["barcode_width"]
    st.session_state.margin = t["margin"]
    st.session_state.orientation = t["orientation"]
    st.session_state.inc_gst_text = t["inc_gst_text"]
    st.session_state.field_order = t["field_order"]
    del st.session_state["template_to_load"]
    # Restore selection if present
    if "restore_selected_idx" in st.session_state:
        st.session_state["selected_idx"] = st.session_state.pop("restore_selected_idx")
    if "restore_selected_indices" in st.session_state:
        st.session_state["selected_indices"] = st.session_state.pop("restore_selected_indices")

@st.cache_data
def load_inventory():
    if os.path.exists(INVENTORY_FILE):
        df = pd.read_excel(INVENTORY_FILE)
        if len(df) == 0:
            st.error("Inventory is empty.")
            st.stop()
        return df
    st.error("No inventory.xlsx found in the parent directory of pages/. Please place 'inventory.xlsx' in '/Users/christopherallantabanag/Desktop/barcode_project'.")
    st.stop()

df = load_inventory()

def clean_barcode(val):
    if pd.isnull(val):
        return ""
    s = str(val).strip().replace('\u200b', '').replace('\u00A0', '')
    if '.' in s:
        int_part, dec_part = s.split('.', 1)
        if dec_part == '0':
            s = int_part
    return s

def format_price(val):
    try:
        return f"${float(val):.2f}"
    except:
        return str(val)

def barcode_image_base64(code, barcode_type, width):
    code = str(code)
    try:
        BARCODE = barcode.get_barcode_class(barcode_type)
        my_code = BARCODE(code, writer=ImageWriter())
        buffer = io.BytesIO()
        options = {"write_text": False, "module_width": 0.2}
        my_code.write(buffer, options=options)
        buffer.seek(0)
        img_bytes = buffer.getvalue()
        img_b64 = base64.b64encode(img_bytes).decode()
        return img_b64
    except Exception as e:
        st.warning(f"Error generating barcode: {e}")
        return ""

def get_field(product, col):
    val = product.get(col, "")
    if col == "BARCODE":
        return clean_barcode(val)
    if col == "RRP":
        return format_price(val)
    return str(val) if pd.notnull(val) else ""

# --- SIDEBAR: LABEL DESIGNER ---
st.sidebar.title("Label Designer")

# The following widgets ONLY use the key argument, not value/default
label_width = st.sidebar.slider("Label width (px)", 120, 600, key="label_width")
label_height = st.sidebar.slider("Label height (px)", 80, 400, key="label_height")
font_size = st.sidebar.slider("Font size (pt)", 8, 32, key="font_size")
barcode_type = st.sidebar.selectbox("Barcode Type", BARCODE_TYPES, key="barcode_type")
barcode_width = st.sidebar.slider("Barcode width (px)", 80, 400, key="barcode_width")
margin = st.sidebar.slider("Label margin (px)", 0, 32, key="margin")
orientation = st.sidebar.radio("Label Orientation", ["Landscape", "Portrait"], key="orientation")
inc_gst_text = st.sidebar.text_input("Text under price", key="inc_gst_text")
st.sidebar.markdown("---")

field_order = st.sidebar.multiselect(
    "Field order and selection",
    options=list(FIELD_LABELS.keys()),
    format_func=lambda k: FIELD_LABELS[k],
    key="field_order"
)
if not field_order:
    st.sidebar.error("Select at least one field for your label.")

template_name = st.sidebar.text_input("Template name", key="template_name")
if st.sidebar.button("Save Template"):
    st.session_state.saved_templates[template_name] = dict(
        width=st.session_state.label_width,
        height=st.session_state.label_height,
        font_size=st.session_state.font_size,
        barcode_type=st.session_state.barcode_type,
        barcode_width=st.session_state.barcode_width,
        margin=st.session_state.margin,
        orientation=st.session_state.orientation,
        inc_gst_text=st.session_state.inc_gst_text,
        field_order=st.session_state.field_order.copy()
    )
    save_templates_to_disk(st.session_state.saved_templates)
    st.sidebar.success(f"Template '{template_name}' saved!")

load_choices = list(st.session_state.saved_templates.keys())
if load_choices:
    chosen_template = st.sidebar.selectbox("Load template", load_choices, key="chosen_template")
    if st.sidebar.button("Load Selected Template"):
        st.session_state["template_to_load"] = chosen_template
        # Save current selected_idx and selected_indices before rerun
        if "selected_idx" in st.session_state:
            st.session_state["restore_selected_idx"] = st.session_state["selected_idx"]
        if "selected_indices" in st.session_state:
            st.session_state["restore_selected_indices"] = st.session_state["selected_indices"]
        st.sidebar.success(f"Template '{chosen_template}' loaded!")
        st.rerun()

if st.sidebar.button("Reset to Default"):
    st.session_state.label_width = DEFAULT_LABEL_WIDTH
    st.session_state.label_height = DEFAULT_LABEL_HEIGHT
    st.session_state.font_size = DEFAULT_FONT_SIZE
    st.session_state.barcode_type = "code128"
    st.session_state.barcode_width = DEFAULT_BARCODE_WIDTH
    st.session_state.margin = DEFAULT_MARGIN
    st.session_state.orientation = "Landscape"
    st.session_state.inc_gst_text = "Inc GST"
    st.session_state.field_order = field_order_default
    st.sidebar.success("Reset to default settings.")
    st.rerun()

st.sidebar.markdown("---")
batch_mode = st.sidebar.checkbox("Batch Print (Multiple Labels)", False, key="batch_mode")

# --- MAIN PAGE: PRODUCT SELECTION ---
st.title("Barcode Label Designer & Printer")

# Selection widgets with restored state
if batch_mode:
    selected_indices_default = st.session_state.get("selected_indices", [])
    selected_indices = st.multiselect(
        "Select products for batch printing",
        options=df.index.tolist(),
        format_func=lambda i: f"{clean_barcode(df.loc[i]['BARCODE'])} - {df.loc[i]['MODEL']}",
        key="selected_indices"
    )
else:
    selected_idx_default = st.session_state.get("selected_idx", df.index.tolist()[0])
    selected_idx = st.selectbox(
        "Choose product",
        options=df.index.tolist(),
        format_func=lambda i: f"{clean_barcode(df.loc[i]['BARCODE'])} - {df.loc[i]['MODEL']}",
        key="selected_idx"
    )
    selected_indices = [selected_idx]

# --- LABEL HTML BUILDER ---
def build_label_html(product):
    barcode_value = get_field(product, "BARCODE")
    barcode_b64 = barcode_image_base64(barcode_value, barcode_type, barcode_width)
    details_html = ""
    for col in field_order:
        label = FIELD_LABELS[col]
        val = get_field(product, col)
        if col == "BARCODE":
            continue # barcode image shown above, number below
        if col == "RRP":
            details_html += f'<div style="font-size:{font_size*1.5}pt;font-weight:bold;color:#222;">{val}</div>'
            details_html += f'<div style="font-size:{font_size*0.8}pt;color:#666;">{inc_gst_text}</div>'
        else:
            details_html += f'<div style="margin-bottom:2px;"><span style="font-weight:bold;">{label}:</span> {val}</div>'

    label_block = f"""
    <div class="print-label-block" style="
        background:#fff;
        padding:{margin}px;
        border-radius:8px;
        width:{label_width}px;
        height:{label_height}px;
        display:flex;
        flex-direction:{'row' if orientation=='Landscape' else 'column'};
        align-items:flex-start;
        justify-content:flex-start;
        box-shadow:0 0 6px #eee;
        font-size:{font_size}pt;
        font-family:'Segoe UI',Arial,sans-serif;
        overflow:hidden;
        margin:16px auto;
    ">
        <div style="flex:0 0 auto;">
            <img src="data:image/png;base64,{barcode_b64}" width="{barcode_width}" style="margin-bottom:6px;" />
            <div style="font-size:{font_size}pt;letter-spacing:2px;margin-bottom:8px;">{barcode_value}</div>
        </div>
        <div style="flex:1 1 auto;padding-left:12px;">
            {details_html}
        </div>
    </div>
    """
    return label_block

# --- PREVIEW ---
st.subheader("Label Preview")
if not selected_indices:
    st.info("Select a product to preview the label.")
else:
    for idx in selected_indices:
        product = df.loc[idx]
        st.markdown(build_label_html(product), unsafe_allow_html=True)

# --- PRINT PREVIEW FUNCTION ---
def build_print_preview_html(products):
    labels_html = ""
    for product in products:
        labels_html += build_label_html(product)
    html = f"""
    <html>
    <head>
    <style>
    body {{ background:#fff; margin:0; padding:0; }}
    @media print {{
        body {{ margin:0; padding:0; }}
        .print-label-block {{
            box-shadow:none !important;
            border:none !important;
            margin:0 auto !important;
        }}
    }}
    </style>
    </head>
    <body>
    {labels_html}
    <script>
    window.onload = function() {{ window.print(); }};
    </script>
    </body>
    </html>
    """
    return html

if st.button("Print Preview"):
    products = [df.loc[i] for i in selected_indices]
    preview_html = build_print_preview_html(products)
    data_url = "data:text/html;base64," + base64.b64encode(preview_html.encode("utf-8")).decode()
    st.markdown(
        f'<a href="{data_url}" target="_blank"><button style="font-size:18px;padding:6px 20px;">Open Print Preview Tab</button></a>',
        unsafe_allow_html=True
    )

# --- PDF EXPORT ---
def make_pdf(products):
    pdf = FPDF(orientation="L" if orientation=="Landscape" else "P", unit="pt", format=[label_width, label_height])
    for product in products:
        pdf.add_page()
        barcode_value = get_field(product, "BARCODE")
        barcode_b64 = barcode_image_base64(barcode_value, barcode_type, barcode_width)
        barcode_bytes = base64.b64decode(barcode_b64)
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
            tmp_file.write(barcode_bytes)
            tmp_file.flush()
            pdf.image(tmp_file.name, x=margin, y=margin, w=barcode_width)
        y = margin + barcode_width + 10
        for col in field_order:
            label = FIELD_LABELS[col]
            val = get_field(product, col)
            if col == "BARCODE":
                pdf.set_y(y)
                pdf.set_font("Arial", size=int(font_size))
                pdf.set_x(margin)
                pdf.cell(0, 10, barcode_value, ln=1)
                y += 20
            elif col == "RRP":
                pdf.set_y(y)
                pdf.set_font("Arial", "B", size=int(font_size*1.5))
                pdf.set_x(margin)
                pdf.cell(0, 14, val, ln=1)  # Price on its own line
                y += 18
                pdf.set_font("Arial", size=int(font_size*0.8))
                pdf.set_x(margin)
                pdf.cell(0, 10, inc_gst_text, ln=1)  # Inc GST directly below
                y += 14
            else:
                pdf.set_y(y)
                pdf.set_font("Arial", size=int(font_size))
                pdf.set_x(margin)
                pdf.cell(0, 12, f"{label}: {val}", ln=1)
                y += 16
    return pdf.output(dest='S').encode('latin1')

if st.button("Export as PDF"):
    products = [df.loc[i] for i in selected_indices]
    pdf_bytes = make_pdf(products)
    # Dynamic filename: use barcode for single selection, batch for multiple
    if len(selected_indices) == 1:
        barcode_value = get_field(df.loc[selected_indices[0]], "BARCODE")
        pdf_filename = f"Barcode({barcode_value}).pdf"
    else:
        pdf_filename = "Barcode(batch).pdf"
    st.download_button(
        label="Download PDF",
        data=pdf_bytes,
        file_name=pdf_filename,
        mime="application/pdf"
    )

st.markdown("---")

with st.expander("Show inventory table"):
    st.dataframe(df, use_container_width=True)