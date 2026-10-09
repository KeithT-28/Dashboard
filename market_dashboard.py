import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import date
import io

# -----------------------------
# Personal Markets Dashboard
# -----------------------------
st.set_page_config(page_title="Personal Markets Dashboard", layout="wide")
st.title("Personal Markets Dashboard")
st.caption("A modular workspace for bond yields, FX rates, and any time-series data you add.")

DATA_FILE = Path("market_data.csv")

DEFAULT_SERIES = {
    "US 3M Treasury Yield": "DGS3MO",
    "US 6M Treasury Yield": "DGS6MO",
    "US 1Y Treasury Yield": "DGS1",
    "US 2Y Treasury Yield": "DGS2",
    "US 5Y Treasury Yield": "DGS5",
    "US 10Y Treasury Yield": "DGS10",
    "US 30Y Treasury Yield": "DGS30",
}

def load_saved_data():
    if DATA_FILE.exists():
        try:
            df = pd.read_csv(DATA_FILE, parse_dates=["Date"])
            required = {"Date", "Instrument", "Value", "Unit"}
            if required.issubset(df.columns):
                return df
        except Exception:
            pass
    return pd.DataFrame(columns=["Date", "Instrument", "Value", "Unit"])

def save_data(df):
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    df.to_csv(DATA_FILE, index=False)

def get_fred_data():
    url = (
        "https://fred.stlouisfed.org/graph/fredgraph.csv"
        "?id=" + ",".join(DEFAULT_SERIES.values())
    )
    raw = pd.read_csv(url, na_values=".")
    raw = raw.rename(columns={
        "observation_date": "Date",
        **{v: k for k, v in DEFAULT_SERIES.items()}
    })
    raw["Date"] = pd.to_datetime(raw["Date"])
    return raw.sort_values("Date")

if "saved_data" not in st.session_state:
    st.session_state.saved_data = load_saved_data()

# Sidebar controls
st.sidebar.header("Dashboard settings")
st.sidebar.write("Choose a data source and instruments to view.")

source = st.sidebar.radio(
    "Data source",
    ["Built-in US Treasury yields (FRED)", "My saved / uploaded data", "Combine both"],
    index=0
)

st.sidebar.caption(
    "FRED yields are daily constant-maturity Treasury rates. "
    "They are not live executable bond quotes."
)

# Fetch FRED only when needed
fred_long = pd.DataFrame(columns=["Date", "Instrument", "Value", "Unit"])
if source in ["Built-in US Treasury yields (FRED)", "Combine both"]:
    with st.spinner("Loading US Treasury yields from FRED..."):
        try:
            fred_wide = get_fred_data()
            fred_long = fred_wide.melt(
                id_vars=["Date"],
                var_name="Instrument",
                value_name="Value"
            ).dropna()
            fred_long["Unit"] = "%"
        except Exception as e:
            st.warning(f"Could not load FRED data right now: {e}")

saved = st.session_state.saved_data.copy()
if not saved.empty:
    saved["Date"] = pd.to_datetime(saved["Date"], errors="coerce")
    saved["Value"] = pd.to_numeric(saved["Value"], errors="coerce")
    saved = saved.dropna(subset=["Date", "Value"])

if source == "Built-in US Treasury yields (FRED)":
    data = fred_long.copy()
elif source == "My saved / uploaded data":
    data = saved.copy()
else:
    data = pd.concat([fred_long, saved], ignore_index=True)

# Data entry and upload tabs
tab_view, tab_add, tab_upload, tab_manage = st.tabs(
    ["Dashboard", "Add a data point", "Upload CSV", "Manage data"]
)

with tab_add:
    st.subheader("Add a data point manually")
    st.write("Use this for FX rates, gold, equity indices, policy rates, or any value you want to track.")
    with st.form("add_point_form", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        instrument = c1.text_input("Instrument name", placeholder="e.g. USD/JPY")
        obs_date = c2.date_input("Observation date", value=date.today())
        value = c3.number_input("Value", value=0.0, format="%.6f")
        unit = c4.text_input("Unit", placeholder="e.g. FX rate, %, USD")
        submitted = st.form_submit_button("Save data point")
        if submitted:
            if not instrument.strip():
                st.error("Please enter an instrument name.")
            else:
                new_row = pd.DataFrame([{
                    "Date": pd.Timestamp(obs_date),
                    "Instrument": instrument.strip(),
                    "Value": float(value),
                    "Unit": unit.strip() or "value"
                }])
                current = st.session_state.saved_data.copy()
                current["Date"] = pd.to_datetime(current["Date"], errors="coerce")
                current = pd.concat([current, new_row], ignore_index=True)
                current = current.drop_duplicates(
                    subset=["Date", "Instrument"], keep="last"
                ).sort_values(["Instrument", "Date"])
                st.session_state.saved_data = current
                save_data(current)
                st.success(f"Saved {instrument} for {obs_date}.")

with tab_upload:
    st.subheader("Upload your own CSV")
    st.write("Expected columns: `Date`, `Instrument`, `Value`; optional column: `Unit`.")
    st.code(
        "Date,Instrument,Value,Unit\n"
        "2026-10-08,USD/JPY,153.25,JPY per USD\n"
        "2026-10-08,EUR/USD,1.1630,USD per EUR\n"
        "2026-10-08,Gold,3975.50,USD per oz",
        language="csv"
    )
    uploaded = st.file_uploader("Choose a CSV file", type=["csv"])
    if uploaded is not None:
        try:
            incoming = pd.read_csv(uploaded)
            incoming.columns = [c.strip() for c in incoming.columns]
            if not {"Date", "Instrument", "Value"}.issubset(incoming.columns):
                st.error("CSV must contain Date, Instrument, and Value columns.")
            else:
                if "Unit" not in incoming.columns:
                    incoming["Unit"] = "value"
                incoming["Date"] = pd.to_datetime(incoming["Date"], errors="coerce")
                incoming["Value"] = pd.to_numeric(incoming["Value"], errors="coerce")
                incoming = incoming.dropna(subset=["Date", "Instrument", "Value"])
                incoming["Instrument"] = incoming["Instrument"].astype(str).str.strip()
                incoming["Unit"] = incoming["Unit"].fillna("value").astype(str)
                st.write("Preview:", incoming.head(10))
                if st.button("Import CSV data"):
                    current = st.session_state.saved_data.copy()
                    current["Date"] = pd.to_datetime(current["Date"], errors="coerce")
                    combined = pd.concat([current, incoming], ignore_index=True)
                    combined = combined.drop_duplicates(
                        subset=["Date", "Instrument"], keep="last"
                    ).sort_values(["Instrument", "Date"])
                    st.session_state.saved_data = combined
                    save_data(combined)
                    st.success(f"Imported {len(incoming)} rows.")
        except Exception as e:
            st.error(f"Could not read CSV: {e}")

with tab_manage:
    st.subheader("Manage saved data")
    current = st.session_state.saved_data.copy()
    if current.empty:
        st.info("No manually added or uploaded data yet.")
    else:
        current["Date"] = pd.to_datetime(current["Date"], errors="coerce")
        st.dataframe(current.sort_values(["Date", "Instrument"], ascending=[False, True]),
                     use_container_width=True)
        csv_bytes = current.assign(
            Date=current["Date"].dt.strftime("%Y-%m-%d")
        ).to_csv(index=False).encode("utf-8")
        st.download_button("Download saved data as CSV", csv_bytes,
                           file_name="market_data.csv", mime="text/csv")
        if st.button("Delete all manually saved data", type="secondary"):
            st.session_state.saved_data = pd.DataFrame(
                columns=["Date", "Instrument", "Value", "Unit"]
            )
            if DATA_FILE.exists():
                DATA_FILE.unlink()
            st.rerun()

with tab_view:
    st.subheader("Market overview")

    if data.empty:
        st.info("No data to display yet. Load FRED data, add a data point, or upload a CSV.")
    else:
        data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
        data["Value"] = pd.to_numeric(data["Value"], errors="coerce")
        data = data.dropna(subset=["Date", "Value", "Instrument"])

        instruments = sorted(data["Instrument"].dropna().unique().tolist())
        selected = st.multiselect(
            "Select instruments to display",
            instruments,
            default=[x for x in [
                "US 3M Treasury Yield",
                "US 2Y Treasury Yield",
                "US 10Y Treasury Yield",
                "USD/JPY",
                "EUR/USD"
            ] if x in instruments][:3]
        )

        if selected:
            selected_data = data[data["Instrument"].isin(selected)].copy()
            latest_rows = (
                selected_data.sort_values("Date")
                .groupby("Instrument", as_index=False)
                .tail(1)
            )
            previous_rows = (
                selected_data.sort_values("Date")
                .groupby("Instrument")
                .nth(-2)
                .reset_index()
                if selected_data.groupby("Instrument").size().ge(2).any()
                else pd.DataFrame()
            )

            st.markdown("#### Latest readings")
            st.dataframe(
                latest_rows[["Date", "Instrument", "Value", "Unit"]]
                .sort_values("Instrument", ignore_index=True),
                use_container_width=True,
                hide_index=True
            )

            # Daily/last-observation changes
            changes = []
            for name in selected:
                series_df = selected_data[selected_data["Instrument"] == name].sort_values("Date")
                if len(series_df) >= 2:
                    last = series_df.iloc[-1]
                    prev = series_df.iloc[-2]
                    unit_value = str(last.get("Unit", "value"))
                    delta = last["Value"] - prev["Value"]
                    if unit_value == "%":
                        delta_text = f"{delta * 100:.1f} bp"
                    else:
                        delta_text = f"{delta:+.6f}"
                    changes.append({
                        "Instrument": name,
                        "Latest date": last["Date"].date(),
                        "Previous date": prev["Date"].date(),
                        "Change since previous observation": delta_text
                    })
            if changes:
                st.markdown("#### Change since previous available observation")
                st.dataframe(pd.DataFrame(changes), use_container_width=True, hide_index=True)

            st.markdown("#### Historical chart")
            chart_mode = st.radio(
                "Chart style",
                ["Separate lines (raw values)", "Indexed to 100"],
                horizontal=True
            )
            pivot = selected_data.pivot_table(
                index="Date", columns="Instrument", values="Value", aggfunc="last"
            ).sort_index()
            if chart_mode == "Indexed to 100":
                pivot = pivot[selected].copy()
                for col in pivot.columns:
                    first = pivot[col].dropna()
                    if len(first):
                        pivot[col] = pivot[col] / first.iloc[0] * 100
                st.caption("Indexed view compares percentage movement, not absolute price/yield levels.")
                st.line_chart(pivot, use_container_width=True)
            else:
                st.line_chart(pivot[selected], use_container_width=True)

            # Yield curve if the required instruments exist
            curve_names = [
                "US 3M Treasury Yield", "US 6M Treasury Yield",
                "US 1Y Treasury Yield", "US 2Y Treasury Yield",
                "US 5Y Treasury Yield", "US 10Y Treasury Yield",
                "US 30Y Treasury Yield"
            ]
            latest_by_name = (
                data.sort_values("Date").groupby("Instrument").tail(1)
                .set_index("Instrument")
            )
            available_curve = [x for x in curve_names if x in latest_by_name.index]
            if len(available_curve) >= 3:
                year_map = {
                    "US 3M Treasury Yield": 0.25,
                    "US 6M Treasury Yield": 0.5,
                    "US 1Y Treasury Yield": 1,
                    "US 2Y Treasury Yield": 2,
                    "US 5Y Treasury Yield": 5,
                    "US 10Y Treasury Yield": 10,
                    "US 30Y Treasury Yield": 30
                }
                curve = latest_by_name.loc[available_curve].copy()
                curve["Years"] = [year_map[x] for x in available_curve]
                curve = curve.sort_values("Years")
                st.markdown("#### Latest Treasury yield curve")
                fig, ax = plt.subplots(figsize=(10, 4))
                ax.plot(curve["Years"], curve["Value"], marker="o")
                ax.set_xlabel("Maturity (years)")
                ax.set_ylabel("Yield (%)")
                ax.set_title("US Treasury Constant-Maturity Yield Curve")
                ax.grid(True, alpha=0.3)
                st.pyplot(fig)
                plt.close(fig)

                if "US 2Y Treasury Yield" in latest_by_name.index and "US 10Y Treasury Yield" in latest_by_name.index:
                    spread = (
                        latest_by_name.loc["US 10Y Treasury Yield", "Value"]
                        - latest_by_name.loc["US 2Y Treasury Yield", "Value"]
                    )
                    st.metric("10Y − 2Y spread", f"{spread:.2f} percentage points",
                              f"{spread * 100:.0f} bp")

        st.caption(
            "Data notes: FRED Treasury series update on business days and may be delayed. "
            "Manually entered/uploaded observations are saved locally in market_data.csv "
            "in the folder where you run this app. Back up or download that CSV periodically."
        )

st.divider()
st.caption("This dashboard is for learning and monitoring, not investment advice or an execution-price feed.")
