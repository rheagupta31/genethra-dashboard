"""
Reusable UI components for the dashboard, styled to match the wireframe's
design tokens.
"""

import streamlit as st
import pandas as pd
import altair as alt

import baseline as bl
from formatting import score_trend_insight

BAND_COLORS = {
    "High": {"bg": "#e3f3e9", "text": "#3c8a5b", "dot": "#3c8a5b"},
    "Moderate": {"bg": "#fbf0dd", "text": "#8a5c0c", "dot": "#c17f11"},
    "Low": {"bg": "#fbe6e9", "text": "#8f2d3a", "dot": "#d1495b"},
}

# All six composite scores are on a 0-100 scale.
SCORE_UNIT = "%"

TREND_ARROWS = {"improving": "▲", "stable": "●", "declining": "▼"}
TREND_COLORS = {"improving": "#3c8a5b", "stable": "#96a3a7", "declining": "#d1495b"}


def confidence_badge(band: str, score: float, caveat: str = None) -> str:
    c = BAND_COLORS[band]
    caveat_html = f'<div style="font-size:10.5px;color:{c["text"]};opacity:.85;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{caveat}</div>' if caveat else ""
    return f"""
    <div style="display:inline-flex;flex-direction:column;background:{c['bg']};
                border-radius:999px;padding:4px 10px;margin-top:6px;">
        <div style="display:flex;align-items:center;gap:5px;">
            <span style="width:7px;height:7px;border-radius:50%;background:{c['dot']};display:inline-block;"></span>
            <span style="font-size:11px;font-weight:700;color:{c['text']};">{band} confidence ({score}%)</span>
        </div>
        {caveat_html}
    </div>
    """


def score_card(label: str, data: dict | None):
    if data is None:
        st.markdown(f"""
        <div style="background:#f8fafb;border:1px dashed #dde4e6;border-radius:14px;
                    padding:14px;margin-bottom:10px;height:156px;overflow:hidden;
                    display:flex;flex-direction:column;justify-content:center;">
            <div style="font-size:11px;font-weight:700;color:#96a3a7;text-transform:uppercase;
                        letter-spacing:.04em;">{label}</div>
            <div style="font-size:12px;color:#96a3a7;margin-top:6px;line-height:1.4;">
                Awaiting inputs — not in this sprint's scope
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    caveat = None
    if data["confidence_band"] == "Moderate":
        caveat = f"Based on {data['days_of_baseline']} days of baseline data"
    elif data["confidence_band"] == "Low":
        caveat = f"Preliminary — only {data['days_of_baseline']} days of baseline collected"

    badge_html = confidence_badge(data["confidence_band"], data["confidence_score"], caveat)

    st.markdown(f"""
    <div style="background:#ffffff;border:1px solid #dde4e6;border-radius:14px;
                padding:14px;margin-bottom:10px;box-shadow:0 1px 2px rgba(15,25,28,.05);
                height:156px;overflow:hidden;display:flex;flex-direction:column;justify-content:space-between;">
        <div>
            <div style="font-size:11px;font-weight:700;color:#5c6b70;text-transform:uppercase;
                        letter-spacing:.04em;">{label}</div>
            <div style="font-family:monospace;font-size:26px;font-weight:700;color:#131b1f;
                        margin-top:4px;">{data['value']}<span style="font-size:15px;
                        font-weight:600;color:#5c6b70;margin-left:1px;">{SCORE_UNIT}</span></div>
        </div>
        {badge_html}
    </div>
    """, unsafe_allow_html=True)


def insight_note(text: str, inset: bool = True):
    """One or two lines of insight shown under a chart."""
    margin = "4px 20px 14px" if inset else "4px 0 14px"
    st.markdown(f"""
    <div style="margin:{margin};padding:8px 10px;background:#eef4f6;
                border-left:3px solid #0b6bcb;border-radius:6px;
                font-size:11.5px;line-height:1.45;color:#3d4a4f;">{text}</div>
    """, unsafe_allow_html=True)


def day_axis(n, title="Day"):
    """
    Numbered day axis for charts that plot one point per day at x = 1..n.
    Every day gets a tick and a gridline, so each point sits on its number.
    Day n is today.
    """
    # Up to 14 days every number fits. Beyond that, label day 1, every fifth
    # day and today, but keep a gridline on every day.
    label_expr = "datum.label"
    if n > 14:
        label_expr = (f"datum.value == 1 || datum.value % 5 == 0 || "
                      f"datum.value == {n} ? datum.label : ''")
    return alt.Axis(values=list(range(1, n + 1)), format="d", grid=True,
                    gridColor="#eef2f3", labelAngle=0, labelOverlap=False,
                    labelExpr=label_expr, title=title, titleFontWeight="normal")


def trend_chart(metric: str, values: list[float], higher_is_better: bool = True):
    n = len(values)
    df = pd.DataFrame({
        "DayNum": list(range(1, n + 1)),
        "Day": [f"Day {i}" + (" (today)" if i == n else "") for i in range(1, n + 1)],
        "Value": values,
    })
    mean_val = sum(values) / n
    delta = values[-1] - values[0]

    if abs(delta) < 0.5:
        color, arrow = "#96a3a7", "●"
    else:
        arrow = "▲" if delta > 0 else "▼"
        moved_good = (higher_is_better and delta > 0) or (not higher_is_better and delta < 0)
        color = "#3c8a5b" if moved_good else "#d1495b"

    st.markdown(f"""
    <div style="padding:0 20px;display:flex;justify-content:space-between;
                align-items:baseline;margin-top:12px;">
        <div style="font-size:12.5px;font-weight:600;color:#131b1f;">{metric}</div>
        <div style="font-size:11px;font-weight:700;color:{color};">
            {arrow} {abs(delta):.1f} pts over {n} days
        </div>
    </div>
    """, unsafe_allow_html=True)

    mean_rule = alt.Chart(pd.DataFrame({"y": [mean_val]})).mark_rule(
        color="#c17f11", strokeDash=[4, 3], size=1
    ).encode(y="y:Q")

    x_enc = alt.X("DayNum:Q", axis=day_axis(n, title=None),
                  scale=alt.Scale(domain=[1, n], nice=False, padding=10))
    line = alt.Chart(df).mark_line(color=color, strokeWidth=2).encode(
        x=x_enc,
        y=alt.Y("Value:Q", title=None, scale=alt.Scale(zero=False)),
    )
    points = alt.Chart(df).mark_circle(color=color, size=40).encode(
        x=x_enc,
        y="Value:Q",
        tooltip=[alt.Tooltip("Day:N", title="Day"), alt.Tooltip("Value:Q", title=f"{metric} (%)", format=".1f")],
    )

    chart = (mean_rule + line + points).properties(height=130).configure_view(
        strokeWidth=0
    ).configure_axis(gridColor="#eef2f3", domainColor="#dde4e6", labelColor="#96a3a7", labelFontSize=9)

    st.altair_chart(chart, use_container_width=True)

    direction = bl.trend_direction(values, baseline=bl.compute_baseline(values))
    insight_note(score_trend_insight(metric, values, higher_is_better, direction))


def alert_card(severity: str, title: str, description: str):
    colors = {
        "high": {"bg": "#fbe6e9", "text": "#8f2d3a", "dot": "#d1495b"},
        "moderate": {"bg": "#fbf0dd", "text": "#8a5c0c", "dot": "#c17f11"},
    }
    c = colors.get(severity, colors["moderate"])
    st.markdown(f"""
    <div style="background:{c['bg']};border-radius:14px;padding:14px;margin:0 20px 10px;">
        <div style="display:flex;align-items:center;gap:6px;">
            <span style="width:8px;height:8px;border-radius:50%;background:{c['dot']};display:inline-block;"></span>
            <span style="font-size:12.5px;font-weight:700;color:{c['text']};">{title}</span>
        </div>
        <div style="font-size:11.5px;color:{c['text']};opacity:.85;margin-top:4px;line-height:1.4;">{description}</div>
    </div>
    """, unsafe_allow_html=True)


def biomarker_card(label: str, value, unit: str):
    st.markdown(f"""
    <div style="background:#ffffff;border:1px solid #dde4e6;border-radius:14px;
                padding:13px;margin-bottom:10px;box-shadow:0 1px 2px rgba(15,25,28,.05);">
        <div style="font-size:11px;font-weight:600;color:#5c6b70;">{label}</div>
        <div style="display:flex;align-items:baseline;gap:4px;margin-top:5px;">
            <span style="font-family:monospace;font-size:17px;font-weight:700;color:#131b1f;">{value}</span>
            <span style="font-size:10.5px;color:#5c6b70;">{unit}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)


def body_system_tile(name: str, status: str, in_scope: bool):
    arrow = TREND_ARROWS[status]
    if in_scope:
        color = TREND_COLORS[status]
        opacity = "1"
        note = '<div style="font-size:9.5px;margin-top:2px;">&nbsp;</div>'
    else:
        color = "#b7c0c3"
        opacity = "0.85"
        note = '<div style="font-size:9.5px;color:#96a3a7;margin-top:2px;">Future tier</div>'
    st.markdown(f"""
    <div style="background:#ffffff;border:1px solid #dde4e6;border-radius:14px;
                padding:12px;text-align:center;opacity:{opacity};min-height:92px;
                display:flex;flex-direction:column;justify-content:center;margin-bottom:10px;">
        <div style="font-size:11.5px;font-weight:600;color:#131b1f;">{name}</div>
        <div style="font-size:16px;font-weight:700;color:{color};margin-top:6px;">
            {arrow} {status.capitalize()}
        </div>
        {note}
    </div>
    """, unsafe_allow_html=True)
