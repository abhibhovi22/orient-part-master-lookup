import io
import os
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Model Part Consumption & Stock Lookup",
    page_icon="🔍",
    layout="wide",
)

# -----------------------------------------------------------------------------
# FILE PATH RESOLUTION (Local & Cloud Compatible)
# -----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else r"C:\Users\91924\Coding"

INVENTORY_FILE_PATH = os.path.join(BASE_DIR, "CurrentInventory_oelkarnataka31.csv")
PART_MASTER_FILE_PATH = os.path.join(BASE_DIR, "PartModelMaster_oelkarnataka31.csv")

# Fallback check
if not os.path.exists(INVENTORY_FILE_PATH):
    INVENTORY_FILE_PATH = r"C:\Users\91924\Coding\CurrentInventory_oelkarnataka31.csv"
if not os.path.exists(PART_MASTER_FILE_PATH):
    PART_MASTER_FILE_PATH = r"C:\Users\91924\Coding\PartModelMaster_oelkarnataka31.csv"


# -----------------------------------------------------------------------------
# DATA LOADING & PREPROCESSING (Cached for speed)
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner="Loading Master Data & Current Inventory...")
def load_and_preprocess_data(inv_path, pm_path):
    # 1. Load Inventory CSV
    df_inv = pd.read_csv(inv_path, low_memory=False, encoding="utf-8", encoding_errors="replace")
    df_inv["PART_CLEAN"] = (
        df_inv["PART_NO"].astype(str).str.strip().str.rstrip("'").str.strip()
    )

    # Aggregate inventory by clean part number
    inv_agg = (
        df_inv.groupby("PART_CLEAN", as_index=False)
        .agg({
            "GOOD_STOCK": "sum",
            "ENGG_GOOD_STOCK": "sum",
            "TOTAL_GOOD_STOCK": "sum",
            "DEFECTIVE_STOCK": "sum",
            "ENGG_DEFECTIVE_STOCK": "sum",
            "LOCATION_OFFICE": lambda x: ", ".join(x.dropna().astype(str).unique()),
            "COMPANY_NAME": lambda x: ", ".join(x.dropna().astype(str).unique()),
        })
    )

    # 2. Load Part Model Master CSV
    df_pm = pd.read_csv(pm_path, low_memory=False, encoding="utf-8", encoding_errors="replace")
    df_pm["PART_CLEAN"] = (
        df_pm["PART"].astype(str).str.strip().str.rstrip("'").str.strip()
    )
    df_pm["MAPPED_MODEL_STR"] = df_pm["MAPPED_MODEL"].astype(str).str.strip()
    df_pm["MODEL_DESCRIPTION_STR"] = df_pm["MODEL_DESCRIPTION"].astype(str).str.strip()

    # Pre-build searchable display strings
    models_df = (
        df_pm[["MAPPED_MODEL_STR", "MODEL_DESCRIPTION_STR", "PRODUCT", "BRAND"]]
        .drop_duplicates(subset=["MAPPED_MODEL_STR"])
        .sort_values(by="MODEL_DESCRIPTION_STR")
    )
    models_df["SEARCH_LABEL"] = (
        models_df["MAPPED_MODEL_STR"] + " — " + models_df["MODEL_DESCRIPTION_STR"]
    )

    return inv_agg, df_pm, models_df


try:
    inv_agg, df_pm, models_df = load_and_preprocess_data(
        INVENTORY_FILE_PATH, PART_MASTER_FILE_PATH
    )
except Exception as e:
    st.error(f"Error loading files: {e}")
    st.info(f"Looking in: {BASE_DIR}. Please make sure both CSV files exist.")
    st.stop()

# -----------------------------------------------------------------------------
# SIDEBAR CONTROLS
# -----------------------------------------------------------------------------
st.title("Orient Electric — Model Part Consumption Lookup")
st.caption("Look up consumable Bill of Materials (BOM) and live stock availability by model.")

with st.sidebar:
    st.header("Search Filters")
    filter_stock = st.radio(
        "Filter by Availability:",
        options=["All Parts", "In Stock Only (Good Stock > 0)", "Out of Stock Only"],
        index=0,
    )
    st.markdown("---")
    if st.button("🔄 Reload Inventory Data"):
        st.cache_data.clear()
        st.rerun()

# -----------------------------------------------------------------------------
# MODEL SEARCH & SELECTION
# -----------------------------------------------------------------------------
search_options = ["-- Select a Model --"] + models_df["SEARCH_LABEL"].tolist()

selected_option = st.selectbox(
    "Type Model Code or Model Description:",
    options=search_options,
    index=0,
    help="Start typing any part of the model number or fan name.",
)

if not selected_option or selected_option == "-- Select a Model --":
    st.info("👆 Please select or search for a model above to view parts and stock.")
    st.stop()

selected_model_code = selected_option.split(" — ")[0].strip()
matched_model_rows = models_df[models_df["MAPPED_MODEL_STR"] == selected_model_code]

if matched_model_rows.empty:
    st.warning("Model metadata could not be found.")
    st.stop()

model_meta = matched_model_rows.iloc[0]

# Filter Part Master for the chosen model
matched_parts = df_pm[df_pm["MAPPED_MODEL_STR"] == selected_model_code].copy()

if matched_parts.empty:
    st.warning(f"No parts are mapped to model code {selected_model_code}.")
    st.stop()

# Join with Inventory
merged = pd.merge(
    matched_parts,
    inv_agg,
    on="PART_CLEAN",
    how="left",
)

# Fill Stock Nulls
merged["GOOD_STOCK"] = merged["GOOD_STOCK"].fillna(0).astype(int)
merged["ENGG_GOOD_STOCK"] = merged["ENGG_GOOD_STOCK"].fillna(0).astype(int)
merged["TOTAL_GOOD_STOCK"] = merged["TOTAL_GOOD_STOCK"].fillna(0).astype(int)
merged["DEFECTIVE_STOCK"] = merged["DEFECTIVE_STOCK"].fillna(0).astype(int)
merged["LOCATION_OFFICE"] = merged["LOCATION_OFFICE"].fillna("Not in Stock")
merged["STOCK_STATUS"] = merged["TOTAL_GOOD_STOCK"].apply(
    lambda qty: "In Stock" if qty > 0 else "Out of Stock"
)

# Apply Sidebar Filter
if filter_stock == "In Stock Only (Good Stock > 0)":
    display_df = merged[merged["TOTAL_GOOD_STOCK"] > 0].copy()
elif filter_stock == "Out of Stock Only":
    display_df = merged[merged["TOTAL_GOOD_STOCK"] == 0].copy()
else:
    display_df = merged.copy()

# -----------------------------------------------------------------------------
# KPI METRICS
# -----------------------------------------------------------------------------
total_mapped = len(merged)
in_stock_count = (merged["TOTAL_GOOD_STOCK"] > 0).sum()
out_of_stock_count = total_mapped - in_stock_count
total_units = merged["TOTAL_GOOD_STOCK"].sum()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Mapped Parts", total_mapped)
col2.metric("Parts Available", in_stock_count, delta=f"{(in_stock_count/total_mapped*100):.0f}% Match" if total_mapped else None)
col3.metric("Parts Out of Stock", out_of_stock_count)
col4.metric("Total Good Stock (Units)", total_units)

st.markdown("---")

# -----------------------------------------------------------------------------
# RESULTS TABLE
# -----------------------------------------------------------------------------
cols_to_show = [
    "PART_CLEAN",
    "DESCRIPTION",
    "MAX_USED_QTY",
    "TOTAL_GOOD_STOCK",
    "GOOD_STOCK",
    "ENGG_GOOD_STOCK",
    "DEFECTIVE_STOCK",
    "STOCK_STATUS",
    "LOCATION_OFFICE",
    "STATUS",
]

col_renames = {
    "PART_CLEAN": "Part No",
    "DESCRIPTION": "Part Description",
    "MAX_USED_QTY": "Max Qty",
    "TOTAL_GOOD_STOCK": "Total Good Stock",
    "GOOD_STOCK": "Branch Good Stock",
    "ENGG_GOOD_STOCK": "Engg Good Stock",
    "DEFECTIVE_STOCK": "Defective Stock",
    "STOCK_STATUS": "Availability",
    "LOCATION_OFFICE": "Location / ASC",
    "STATUS": "Master Status",
}

final_table = display_df[cols_to_show].rename(columns=col_renames)

st.subheader(f"Parts for Model: {model_meta['MODEL_DESCRIPTION_STR']} ({selected_model_code})")

def highlight_stock(val):
    if val == "In Stock":
        return "background-color: #d4edda; color: #155724; font-weight: bold;"
    elif val == "Out of Stock":
        return "background-color: #f8d7da; color: #721c24;"
    return ""

st.dataframe(
    final_table.style.map(highlight_stock, subset=["Availability"]),
    use_container_width=True,
    hide_index=True,
)

# -----------------------------------------------------------------------------
# EXCEL DOWNLOAD
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# EXCEL DOWNLOAD
# -----------------------------------------------------------------------------
output = io.BytesIO()
with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
    final_table.to_excel(writer, index=False, sheet_name="Model_Parts")
excel_data = output.getvalue()

st.download_button(
    label="📥 Download Part List as Excel",
    data=excel_data,
    file_name=f"Parts_{selected_model_code}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
    label="📥 Download Part List as Excel",
    data=excel_data,
    file_name=f"Parts_{selected_model_code}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
