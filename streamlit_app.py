import os
import json
import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timedelta
from streamlit_javascript import st_javascript
from io import BytesIO

# --- Page Header ---
st.set_page_config(page_title="PFTracker", layout="wide")

st.markdown("""
    <h1 style='font-size: 42px; margin-bottom: 0;'>PFTracker</h1>
    <p style='font-size: 16px; color: #AAA; margin-top: 4px;'>
        This page shows how many parties in Final Fantasy XIV are still looking for at least one job from a selected group at different times of the day.
    </p>
    <p style='font-size: 14px; color: #AAA; margin-top: 0.5em;'>
        For example, if "WHM" and "SGE" are selected in a group, the graph will show how many parties are still looking for either of these jobs at the specified timeframe.
    </p>
""", unsafe_allow_html=True)

# Job color codes
JOB_COLORS = {
    "VPR": "#108210", "MNK": "#D69C00", "DRG": "#4164CD", "BLM": "#A579D6",
    "SAM": "#E46D04", "RPR": "#965A90", "NIN": "#FC92E1", "PCT": "#FC92E1",
    "RDM": "#E87B7B", "SMN": "#2D9B78", "DNC": "#E2B0AF", "BRD": "#91BA5E",
    "MCH": "#6EE1D6", "GNB": "#796D30", "PLD": "#A8D2E6", "DRK": "#D126CC",
    "WAR": "#CF2621", "AST": "#FFE74A", "WHM": "#FFF0DC", "SGE": "#80A0F0",
    "SCH": "#8657FF"
}

ROLES = {
    "Tanks": ["PLD", "WAR", "DRK", "GNB"],
    "Healers": ["WHM", "SCH", "AST", "SGE"],
    "Melee": ["MNK", "DRG", "NIN", "SAM", "RPR", "VPR"],
    "Ranged": ["BRD", "MCH", "DNC"],
    "Caster": ["BLM", "SMN", "RDM", "PCT"]
}

def blend_colors(hex_list):
    rgb_list = []
    for hex_code in hex_list:
        hex_code = hex_code.lstrip('#')
        rgb = tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4))
        rgb_list.append(rgb)
    r = int(sum(c[0] for c in rgb_list) / len(rgb_list)) if rgb_list else 170
    g = int(sum(c[1] for c in rgb_list) / len(rgb_list)) if rgb_list else 170
    b = int(sum(c[2] for c in rgb_list) / len(rgb_list)) if rgb_list else 170
    return f"#{r:02X}{g:02X}{b:02X}"

@st.cache_data(show_spinner="Downloading data from GitHub...")
def load_data(tz_offset_min, cache_key):
    repo = "Rinn-K/PFTracker"
    branch = "main"
    folder = "exports"

    api_url = f"https://api.github.com/repos/{repo}/contents/{folder}?ref={branch}"
    response = requests.get(api_url)
    response.raise_for_status()

    files = response.json()
    csv_urls = [
        f"https://raw.githubusercontent.com/{repo}/{branch}/{folder}/{f['name']}"
        for f in files if f['name'].endswith(".csv.gz")
    ]

    all_dfs = []
    for url in sorted(csv_urls):
        gz_data = requests.get(url).content
        df = pd.read_csv(BytesIO(gz_data), compression="gzip", parse_dates=["Timestamp"])
        df["Timestamp Rounded"] = df["Timestamp"].dt.floor("15min")
        all_dfs.append(df)

    if all_dfs:
        df_all = pd.concat(all_dfs).drop_duplicates(subset=["Timestamp", "ID"])
        df_all["Timestamp Rounded"] = df_all["Timestamp Rounded"] + pd.to_timedelta(-tz_offset_min, unit="m")
        return df_all.sort_values("Timestamp Rounded")
    return pd.DataFrame()

# --- Get timezone offset before loading data ---
tz_offset_min = st_javascript("new Date().getTimezoneOffset();") or 0

# --- Create a cache key that updates every 15 minutes ---
now = datetime.utcnow()
rounded_15 = now - timedelta(minutes=now.minute % 15,
                             seconds=now.second,
                             microseconds=now.microsecond)
cache_key = rounded_15.strftime('%Y-%m-%d-%H-%M')

# --- Load data ---
df = load_data(tz_offset_min, cache_key)

def extract_combat_jobs(df):
    jobs = set()
    for party_json in df["Party (JSON)"]:
        try:
            slots = json.loads(party_json)
            for slot in slots:
                for j in slot.get("job", "").split():
                    if j in JOB_COLORS:
                        jobs.add(j.strip())
        except Exception:
            continue
    return sorted(jobs)

def count_group_match(row, job_list):
    try:
        slots = json.loads(row["Party (JSON)"])
    except Exception:
        return 0

    if row["[One Player per Job]"] == 1:
        filled_jobs = {j for s in slots if s.get("filled", True) for j in s.get("job", "").split()}
        if all(job in filled_jobs for job in job_list):
            return 0

    unfilled_match = any(
        not s.get("filled", True) and any(j in job_list for j in s.get("job", "").split())
        for s in slots
    )
    return int(unfilled_match)

# --- Load and process data ---
if df.empty:
    st.warning("No data available in 'exports/'")
    st.stop()

# --- JS-based Timezone detection ---
df["Date"] = df["Timestamp Rounded"].dt.date

# --- Sidebar Filters ---
st.sidebar.header("Filters")

min_ts = df["Date"].min()
max_ts = df["Date"].max()
start_date = st.sidebar.date_input("Start date", min_ts, min_value=min_ts, max_value=max_ts)
end_date = st.sidebar.date_input("End date", max_ts, min_value=min_ts, max_value=max_ts)

df = df[(df["Date"] >= start_date) & (df["Date"] <= end_date)]

data_centres = sorted(df["Data Centre"].dropna().unique())
selected_dc = st.sidebar.selectbox("Data Centre", data_centres)
df = df[df["Data Centre"] == selected_dc]

all_duties = sorted(df["Duty"].dropna().unique())
duty_key = f"duties_{selected_dc}"
default_duties = st.session_state.get(duty_key, [])

selected_duties = st.sidebar.multiselect(
    "Duties",
    all_duties,
    default=default_duties,
    key=duty_key
)
df = df[df["Duty"].isin(selected_duties)]

tag_options = ["None", "[Practice]", "[Duty Completion]", "[Loot]"]
selected_tag = st.sidebar.radio("Tag filter", tag_options)
if selected_tag != "None":
    df = df[df[selected_tag] == 1]

# --- Job Groups ---
st.sidebar.header("Job Groups")
if "job_groups" not in st.session_state:
    st.session_state["job_groups"] = [["WHM", "SGE"]]

if st.sidebar.button("Add Group"):
    st.session_state["job_groups"].append([])

if st.sidebar.button("Remove Group") and st.session_state["job_groups"]:
    st.session_state["job_groups"].pop()

all_jobs = extract_combat_jobs(df)
job_groups = []

# Role buttons
st.sidebar.markdown("**Quick Add by Role**")
cols = st.sidebar.columns(5)
for role, btn in zip(ROLES, cols):
    if btn.button(role):
        st.session_state["job_groups"].append(ROLES[role][:])

# Group selectors
for i, group in enumerate(st.session_state["job_groups"]):
    valid_defaults = [j for j in group if j in all_jobs]
    selected = st.sidebar.multiselect(f"Group {i+1}", all_jobs, default=valid_defaults, key=f"group_{i}")
    st.session_state["job_groups"][i] = selected
    if selected:
        job_groups.append((f"Group {i+1}", selected))

# --- Plotting ---
if job_groups:
    df_plot = df[["Timestamp Rounded", "Party (JSON)", "[One Player per Job]"]].copy()
    for label, jobs in job_groups:
        df_plot[label] = df.apply(lambda row: count_group_match(row, jobs), axis=1)

    grouped = df_plot.groupby("Timestamp Rounded").sum().reset_index()

    fig = go.Figure()
    averages = {}

    for label, jobs in job_groups:
        color = blend_colors([JOB_COLORS.get(j, "#AAAAAA") for j in jobs])
        y_vals = grouped[label]
        fig.add_trace(go.Scatter(
            x=grouped["Timestamp Rounded"],
            y=y_vals,
            mode="lines",
            name=f"{label}: {', '.join(jobs)}",
            line=dict(color=color, width=2)
        ))
        averages[label] = y_vals.mean()

    fig.update_layout(
        hovermode="x unified",
        showlegend=True,
        legend_title_text="Job Groups",
        margin=dict(t=10)
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- Averages table ---
    st.subheader("Average listings per group (in time window)")
    for label, jobs in job_groups:
        color = blend_colors([JOB_COLORS.get(j, "#AAAAAA") for j in jobs])
        avg = round(averages[label], 2)
        st.markdown(f"<span style='color:{color}; font-weight:bold'>{label}</span>: {avg}", unsafe_allow_html=True)
else:
    st.info("Add at least one job group to visualize.")
