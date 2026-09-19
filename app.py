"""
Genethra — Front-End Health Insights Dashboard (skeleton)
Streamlit app constrained to a phone-width layout.

Data access is isolated to mock_data.py — swapping mocks for the real
API means editing that one file.
"""

import streamlit as st
from mock_data import (
    PERSONAS, get_persona, get_score_data, get_body_systems_data,
    get_trend_data, get_biomarkers, get_alerts, COMPOSITE_SCORES, HIGHER_IS_BETTER,
)
from mock_data import (
    get_baseline_markers, get_days_collected,
)
from components import score_card, body_system_tile, biomarker_card, trend_chart, alert_card
from baseline_ui import render_baseline_section, render_signal_detail

st.set_page_config(page_title="Genethra", layout="centered", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500&display=swap');

.stApp {
    background: #0b0d10;
}

[data-testid="stSidebar"], [data-testid="collapsedControl"] {
    display: none !important;
}
[data-testid="stAppViewContainer"] {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
}

.block-container {
    max-width: 430px;
    width: 100%;
    height: 85vh;
    margin: 0 auto;
    padding: 0 0 24px 0;
    background: #f4f7f8;
    border-radius: 40px;
    border: 10px solid #0a0a0a;
    box-shadow: 0 20px 48px rgba(15,25,28,.35);
    overflow-y: auto;
    overflow-x: hidden;
}
div[data-testid="stVerticalBlock"] > div:has(> div.element-container) {
    gap: 0.3rem;
}
div[data-testid="stHorizontalBlock"] {
    gap: 0.6rem;
}
div[data-testid="column"] {
    padding: 0 4px;
}
.stTabs [data-baseweb="tab-list"] {
    padding-left: 20px;
    padding-right: 20px;
    gap: 22px;
}
h1, h2, h3 { font-family: 'General Sans', sans-serif; }
</style>
""", unsafe_allow_html=True)

DRILL_KEY = "drill_signal"


def open_signal(signal_key):
    st.session_state[DRILL_KEY] = signal_key


def close_signal():
    st.session_state[DRILL_KEY] = None


def clear_drill_on_persona_change():
    """A drill down belongs to one patient. Switching patients closes it."""
    st.session_state[DRILL_KEY] = None


persona_labels = [f"Patient {p['ID']} — {p['Sex']}, {p['Age']}" for p in PERSONAS]
selected_label = st.selectbox(
    "Persona (synthetic)", persona_labels, label_visibility="collapsed",
    key="persona_pick", on_change=clear_drill_on_persona_change,
)
selected_id = int(selected_label.split(" ")[1])
persona = get_persona(selected_id)

st.markdown(f"""
<div style="padding:16px 20px 4px;">
    <div style="font-size:13.5px;color:#5c6b70;">Good morning,</div>
    <div style="font-family:'General Sans',sans-serif;font-size:20px;font-weight:700;color:#131b1f;">
        Patient {persona['ID']}
    </div>
    <div style="font-size:11.5px;color:#96a3a7;margin-top:2px;">
        {persona['Sex']} · Age {persona['Age']} · {persona['BMI Category']}
    </div>
</div>
""", unsafe_allow_html=True)

# ~20px gutters at 430px, matching the inset Rhea's own components use.
PHONE_GUTTER = [1, 18, 1]

drilled = st.session_state.get(DRILL_KEY)
if drilled:
    _, mid, _ = st.columns(PHONE_GUTTER)
    with mid:
        render_signal_detail(persona["ID"], drilled, on_back=close_signal)
    st.stop()

tab_home, tab_insights, tab_alerts, tab_baselines = st.tabs(
    ["Home", "Insights", "Alerts", "Baselines"]
)

with tab_home:
    scores = get_score_data(persona["ID"])

    st.markdown('<div style="padding:0 20px;"><h3 style="font-size:13px;color:#5c6b70;margin:14px 0 6px;">Composite scores</h3></div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    for i, label in enumerate(COMPOSITE_SCORES):
        with (col1 if i % 2 == 0 else col2):
            score_card(label, scores[label])

    st.markdown('<div style="padding:0 20px;"><h3 style="font-size:13px;color:#5c6b70;margin:14px 0 6px;">Body systems</h3></div>', unsafe_allow_html=True)

    systems = get_body_systems_data(persona["ID"])
    sys_col1, sys_col2 = st.columns(2)
    for i, (name, sdata) in enumerate(systems.items()):
        with (sys_col1 if i % 2 == 0 else sys_col2):
            body_system_tile(name, sdata["status"], sdata["in_scope"])

with tab_insights:
    st.markdown('<div style="padding:0 20px;"><h3 style="font-size:13px;color:#5c6b70;margin:14px 0 6px;">Trend — all composite scores</h3></div>', unsafe_allow_html=True)

    for metric in COMPOSITE_SCORES:
        trend = get_trend_data(persona["ID"], metric)
        trend_chart(metric, trend, higher_is_better=HIGHER_IS_BETTER[metric])

    st.markdown('<div style="padding:0 20px;"><h3 style="font-size:13px;color:#5c6b70;margin:18px 0 6px;">Biomarkers</h3></div>', unsafe_allow_html=True)

    biomarkers = get_biomarkers(persona["ID"])
    bio_col1, bio_col2 = st.columns(2)
    for i, b in enumerate(biomarkers):
        with (bio_col1 if i % 2 == 0 else bio_col2):
            biomarker_card(b["label"], b["value"], b["unit"])

with tab_alerts:
    alerts = get_alerts(persona["ID"])

    st.markdown('<div style="padding:0 20px;"><h3 style="font-size:13px;color:#5c6b70;margin:14px 0 10px;">Alerts</h3></div>', unsafe_allow_html=True)

    if not alerts:
        st.markdown("""
        <div style="padding:40px 32px;text-align:center;">
            <div style="font-size:13px;color:#96a3a7;">No alerts right now</div>
            <div style="font-size:11.5px;color:#96a3a7;margin-top:6px;">
                Nothing is trending in a concerning direction for this patient.
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        for a in alerts:
            alert_card(a["severity"], a["title"], a["description"])


with tab_baselines:
    _, mid, _ = st.columns(PHONE_GUTTER)
    with mid:
        markers = get_baseline_markers(persona["ID"])
        render_baseline_section(
            markers,
            baseline_days=get_days_collected(persona["ID"]),
            on_open=open_signal,
        )
