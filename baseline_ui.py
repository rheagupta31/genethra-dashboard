"""
Baseline identification UI.

Ported from the Workflow 3 baseline branch into this app. Three pieces:

  render_signal_chart    a signal's daily readings drawn inside the shaded band
                         of that person's own normal range
  render_baseline_row    one signal as a card: reading, range, deviation, way in
  render_signal_detail   the drill down, with a 7/14/30 day window selector

The computation lives in baseline.py, which imports no Streamlit and is therefore
unit testable and portable to the server side unchanged. Wording and colour come
from formatting.py, so these components and the existing score cards cannot end
up describing the same reading two different ways.
"""

import altair as alt
import pandas as pd
import streamlit as st

import baseline as bl
import mock_data
from formatting import (
    IN_RANGE,
    LINE,
    MARKED,
    MUTED,
    NEUTRAL,
    TRACK,
    UNUSUAL,
    deviation_phrase,
    fmt,
    interpretation,
    status_color,
    status_word,
    trend_phrase,
)

"""
Per signal time series plotted against the personal baseline band.

This is the chart the workflow title is actually about. A line on its own says
"your resting heart rate was 58 today". The same line drawn inside a shaded band
of that person's own normal range says "58 is high for you", which is the claim
the product is built to make, and it makes it without needing a sentence.

Layers, back to front:
  1. the normal range band, mean plus or minus one SD
  2. the personal mean, dashed
  3. the reading line
  4. one point per day, coloured and sized by whether it sits inside the band
  5. today, drawn larger so the eye lands on it first

Altair ships with Streamlit, so this adds no dependency.
"""



# Legend order is fixed so the colours do not reshuffle between signals.
STATUS_ORDER = ["In range", "Outside range", "Well outside range"]
STATUS_COLORS = [IN_RANGE, UNUSUAL, MARKED]


def _status(value, baseline):
    """
    Per point status, using the same thresholds as the rest of the app.

    Without a baseline there is no "in range", so the tooltip says so rather
    than reporting a comparison that was never made.
    """
    deviation = bl.classify(value, baseline)
    if deviation is None:
        return "No range yet"
    if deviation.state == "in_range":
        return "In range"
    return "Well outside range" if deviation.magnitude == "marked" else "Outside range"


def _frame(marker):
    """
    One row per day.

    Day 0 is today and earlier days are negative, so the axis reads left to
    right as time passing without inventing calendar dates the mock data does
    not have.
    """
    series = marker["series"]
    baseline = marker["baseline"]
    n = len(series)

    rows = []
    for index, value in enumerate(series):
        z = bl.zscore(value, baseline) if baseline else None
        rows.append(
            {
                "day": index - (n - 1),
                "value": value,
                "status": _status(value, baseline),
                "z": round(z, 2) if z is not None else None,
                "is_today": index == n - 1,
            }
        )
    return pd.DataFrame(rows)


def render_signal_chart(marker, height=260, show_title=False, y_domain=None):
    """
    marker: a resolved signal dict from DataSource.get_biomarker()
    y_domain: optional fixed (min, max) for the y-axis. When given, used
        instead of scaling to whatever's currently visible — so switching
        between the 1/7/14/30 day windows doesn't visually rescale the
        chart each time, only the data on screen changes.
    """
    series = marker["series"]
    if not series:
        st.caption("No readings available for this signal.")
        return

    baseline = marker["baseline"]
    unit = marker["unit"]
    precision = marker["precision"]

    if show_title:
        st.markdown(f"**{marker['label']}**")

    df = _frame(marker)

    tooltip = [
        alt.Tooltip("day:Q", title="Days ago"),
        alt.Tooltip("value:Q", title=f"{marker['label']} ({unit})", format=f".{precision}f"),
        alt.Tooltip("status:N", title="Status"),
    ]
    if baseline is not None:
        tooltip.append(alt.Tooltip("z:Q", title="SD from baseline", format="+.2f"))

    if y_domain is not None:
        y_scale = alt.Scale(domain=list(y_domain), nice=False)
    else:
        # Fallback: scale from the data and the band together, so a band
        # sitting outside the observed range is never clipped off the top.
        values = list(series)
        if baseline is not None:
            low, high = bl.normal_range(baseline)
            values += [low, high]
        span = max(values) - min(values)
        pad = span * 0.12 if span else 1.0
        y_scale = alt.Scale(domain=[min(values) - pad, max(values) + pad], nice=False)

    layers = []

    if baseline is not None:
        low, high = bl.normal_range(baseline)
        band_df = pd.DataFrame(
            {"day": [df["day"].min(), df["day"].max()], "low": [low, low], "high": [high, high]}
        )
        layers.append(
            alt.Chart(band_df)
            .mark_area(color=IN_RANGE, opacity=0.13)
            .encode(
                x=alt.X("day:Q"),
                y=alt.Y("low:Q", scale=y_scale),
                y2=alt.Y2("high:Q"),
            )
        )
        layers.append(
            alt.Chart(pd.DataFrame({"mean": [baseline.mean]}))
            .mark_rule(color=IN_RANGE, strokeDash=[5, 4], strokeWidth=1.4, opacity=0.75)
            .encode(y=alt.Y("mean:Q", scale=y_scale))
        )

    layers.append(
        alt.Chart(df)
        .mark_line(color=LINE, strokeWidth=2, interpolate="monotone")
        .encode(
            x=alt.X(
                "day:Q",
                title="Days ago (0 = today)",
                axis=alt.Axis(tickMinStep=1, grid=False),
            ),
            y=alt.Y(
                "value:Q",
                title=f"{marker['label']} ({unit})",
                scale=y_scale,
            ),
        )
    )

    points = (
        alt.Chart(df)
        .mark_point(filled=True, stroke="white", strokeWidth=1)
        .encode(
            x=alt.X("day:Q"),
            y=alt.Y("value:Q", scale=y_scale),
            size=alt.Size(
                "is_today:N",
                scale=alt.Scale(domain=[False, True], range=[55, 190]),
                legend=None,
            ),
            tooltip=tooltip,
        )
    )

    if baseline is not None:
        points = points.encode(
            color=alt.Color(
                "status:N",
                title="Reading",
                scale=alt.Scale(domain=STATUS_ORDER, range=STATUS_COLORS),
                legend=alt.Legend(orient="bottom", direction="horizontal", titleLimit=0),
            )
        )
    else:
        # No baseline means there is no "in range" to colour against. Showing a
        # green "In range" legend to someone the app has just told has no range
        # would contradict itself on the same screen.
        points = points.encode(color=alt.value(NEUTRAL))

    layers.append(points)

    chart = (
        alt.layer(*layers)
        .properties(height=height)
        .configure_view(strokeWidth=0)
        .configure_axis(labelColor=MUTED, titleColor=MUTED, titleFontSize=11, labelFontSize=10)
        .configure_legend(labelColor=MUTED, titleColor=MUTED, labelFontSize=10, titleFontSize=10)
    )

    st.altair_chart(chart, use_container_width=True)

    if baseline is None:
        st.caption(
            f"Readings only. {marker['observed_days']} days collected, "
            f"{bl.RANGE_MIN_DAYS} needed before a personal range can be drawn."
        )
    else:
        low, high = bl.normal_range(baseline)
        st.caption(
            f"Shaded band is your normal range, {fmt(low, precision)} to "
            f"{fmt(high, precision)} {unit}, calculated from {baseline.n} days of "
            f"your own readings. Dashed line is your average."
        )


def _intraday_frame(marker):
    """
    One row per intraday point. Minutes-since-midnight are converted to an
    arbitrary reference timestamp so Altair can format the axis as clock
    time (12 AM, 6 AM, ...) instead of raw minute numbers.
    """
    minutes = marker["minutes"]
    values = marker["values"]
    reference = pd.Timestamp("2000-01-01")
    rows = []
    for i, (m, v) in enumerate(zip(minutes, values)):
        rows.append({
            "timestamp": reference + pd.to_timedelta(m, unit="m"),
            "value": v,
            "is_now": i == len(minutes) - 1,
        })
    return pd.DataFrame(rows)


def render_intraday_chart(marker, height=260, y_domain=None):
    """
    Last 24 hours at whatever resolution mock_data generated, plotted
    against the same personal range the daily view uses (a range isn't
    recomputed from a single day — it's the existing 30-day baseline,
    viewed at finer time resolution).

    y_domain: optional fixed (min, max) for the y-axis — see
        render_signal_chart's docstring for why.
    """
    baseline = marker["baseline"]
    unit = marker["unit"]
    precision = marker["precision"]

    df = _intraday_frame(marker)

    if y_domain is not None:
        y_scale = alt.Scale(domain=list(y_domain), nice=False)
    else:
        values = list(marker["values"])
        if baseline is not None:
            low, high = bl.normal_range(baseline)
            values += [low, high]
        span = max(values) - min(values)
        pad = span * 0.15 if span else 1.0
        y_scale = alt.Scale(domain=[min(values) - pad, max(values) + pad], nice=False)

    layers = []

    if baseline is not None:
        low, high = bl.normal_range(baseline)
        band_df = pd.DataFrame({
            "timestamp": [df["timestamp"].min(), df["timestamp"].max()],
            "low": [low, low], "high": [high, high],
        })
        layers.append(
            alt.Chart(band_df).mark_area(color=IN_RANGE, opacity=0.13).encode(
                x=alt.X("timestamp:T"),
                y=alt.Y("low:Q", scale=y_scale),
                y2=alt.Y2("high:Q"),
            )
        )
        layers.append(
            alt.Chart(pd.DataFrame({"mean": [baseline.mean]}))
            .mark_rule(color=IN_RANGE, strokeDash=[5, 4], strokeWidth=1.4, opacity=0.75)
            .encode(y=alt.Y("mean:Q", scale=y_scale))
        )

    layers.append(
        alt.Chart(df).mark_line(color=LINE, strokeWidth=1.8, interpolate="monotone").encode(
            x=alt.X("timestamp:T", title="Time of day",
                     axis=alt.Axis(format="%I %p", grid=False, tickCount=6)),
            y=alt.Y("value:Q", title=f"{marker['label']} ({unit})", scale=y_scale),
            tooltip=[
                alt.Tooltip("timestamp:T", title="Time", format="%I:%M %p"),
                alt.Tooltip("value:Q", title=f"{marker['label']} ({unit})", format=f".{precision}f"),
            ],
        )
    )

    now_point = alt.Chart(df[df["is_now"]]).mark_point(
        filled=True, color=LINE, size=100, stroke="white", strokeWidth=1.5
    ).encode(x="timestamp:T", y=alt.Y("value:Q", scale=y_scale))
    layers.append(now_point)

    chart = (
        alt.layer(*layers)
        .properties(height=height)
        .configure_view(strokeWidth=0)
        .configure_axis(labelColor=MUTED, titleColor=MUTED, titleFontSize=11, labelFontSize=10)
    )

    st.altair_chart(chart, use_container_width=True)
    st.caption(mock_data.PLACEHOLDER_NOTE)


"""
Baseline range display.

Shows a signal's reading against that person's own normal range, how far outside
it sits, and how much history the range is built on.

Why a range and not just an average: an average cannot tell you whether today is
unusual. A resting heart rate two beats above average is nothing for someone who
swings four beats day to day and notable for someone who swings one. The range is
what makes "compared to your own baseline" mean anything.

The range is the person's mean plus or minus one standard deviation, computed
from their own observed series in `services/baseline.py`. Nothing here reads a
precomputed baseline out of a data file, and nothing here falls back to a
population average: the whole premise of the product is the personal baseline, so
a population comparison would mislead in exactly the moment a user is most likely
to trust it.

Each row is also the entry point to the signal drill down.
"""




def _position(value, low, high):
    """Position of a value along the track as a percentage, clamped."""
    if high <= low:
        return 50.0
    return max(0.0, min(100.0, (value - low) / (high - low) * 100))


def _track_bounds(marker):
    """
    Visible span of the track.

    Wide enough to show the band with room around it, and always wide enough to
    keep today's marker on screen even when the reading is far outside the range.
    """
    baseline = marker["baseline"]
    current = marker["current"]
    pad = 3.2 * baseline.sd
    low = min(baseline.mean - pad, current - 0.6 * baseline.sd)
    high = max(baseline.mean + pad, current + 0.6 * baseline.sd)
    return low, high


def render_baseline_row(marker, on_open=None, key_prefix=""):
    """
    One signal as a card: reading, personal range, deviation, and a way in.

    marker: a resolved signal dict from DataSource.get_biomarker()
    on_open: callback taking the signal key, wired to the drill down. Omit it to
        render the card read only.
    """
    label = marker["label"]
    current = marker["current"]
    unit = marker["unit"]
    precision = marker["precision"]
    baseline = marker["baseline"]
    deviation = marker["deviation"]

    higher_is_better = marker["higher_is_better"]
    color = status_color(deviation, higher_is_better)
    word = status_word(deviation, higher_is_better)

    synthetic_badge = (
        f"<span style='font-size:0.62rem;color:#b8860b;background:#b8860b1a;"
        f"border-radius:4px;padding:1px 5px;margin-left:6px;font-weight:600;'>"
        f"SIMULATED</span>"
        if marker.get("fully_synthetic") else ""
    )

    with st.container(border=True):
        # Header: signal on the left, today's reading on the right.
        st.markdown(
            f"""
            <div style="display:flex;align-items:baseline;justify-content:space-between;">
              <span style="font-size:0.74rem;color:{MUTED};text-transform:uppercase;
                           letter-spacing:0.05em;font-weight:600;">{label}{synthetic_badge}</span>
              <span style="font-size:1.25rem;font-weight:700;color:{color};">
                {fmt(current, precision)}<span style="font-size:0.78rem;font-weight:500;
                color:{MUTED};margin-left:3px;">{unit}</span>
              </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if baseline is None:
            # No usable range yet. Say so plainly and draw an empty track rather
            # than a band the data cannot support.
            st.markdown(
                f"<div style='height:9px;border-radius:5px;background:{TRACK};"
                f"margin:9px 0 6px 0;'></div>"
                f"<div style='font-size:0.74rem;color:{MUTED};'>"
                f"{word} &nbsp;&middot;&nbsp; {marker['observed_days']} of "
                f"{bl.RANGE_MIN_DAYS} days needed</div>",
                unsafe_allow_html=True,
            )
        else:
            low, high = bl.normal_range(baseline)
            t_low, t_high = _track_bounds(marker)

            band_left = _position(low, t_low, t_high)
            band_width = _position(high, t_low, t_high) - band_left
            mean_pos = _position(baseline.mean, t_low, t_high)
            marker_pos = _position(current, t_low, t_high)

            # Endpoint labels sit under the band edges, not the track edges.
            # Clamped a little inside so a label never clips at the card border.
            label_left = min(max(band_left, 5.0), 95.0)
            label_right = min(max(band_left + band_width, 5.0), 95.0)

            st.markdown(
                f"""
                <div style="position:relative;height:9px;border-radius:5px;
                            background:{TRACK};margin:11px 0 5px 0;">
                  <div style="position:absolute;left:{band_left:.1f}%;
                              width:{band_width:.1f}%;top:0;bottom:0;
                              background:{IN_RANGE}2e;border-radius:5px;"></div>
                  <div style="position:absolute;left:{mean_pos:.1f}%;top:1px;bottom:1px;
                              width:1px;background:{IN_RANGE};opacity:0.55;"></div>
                  <div style="position:absolute;left:{marker_pos:.1f}%;top:-4px;
                              width:3px;height:17px;background:{color};
                              border-radius:2px;transform:translateX(-1.5px);
                              box-shadow:0 0 0 2px #fff;"></div>
                </div>
                <div style="position:relative;height:13px;
                            font-size:0.68rem;color:{MUTED};">
                  <span style="position:absolute;left:{label_left:.1f}%;
                               transform:translateX(-50%);">{fmt(low, precision)}</span>
                  <span style="position:absolute;left:{label_right:.1f}%;
                               transform:translateX(-50%);">{fmt(high, precision)}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Status is always a word next to the colour, never the colour alone.
            st.markdown(
                f"<div style='margin-top:7px;font-size:0.75rem;'>"
                f"<span style='background:{color}1a;color:{color};"
                f"border:1px solid {color}55;border-radius:999px;padding:1px 8px;"
                f"font-weight:600;'>{word}</span>"
                f"<span style='color:{MUTED};margin-left:7px;'>"
                f"{deviation_phrase(deviation, unit)}</span></div>",
                unsafe_allow_html=True,
            )

        if on_open is not None:
            st.button(
                f"Open {label} detail",
                key=f"{key_prefix}open_{marker['key']}",
                use_container_width=True,
                on_click=on_open,
                args=(marker["key"],),
            )


def render_baseline_section(markers, baseline_days, on_open=None, key_prefix=""):
    """
    Every signal as a baseline row.

    markers: dict of resolved signal dicts from DataSource.get_biomarkers()
    """
    state, label = bl.maturity(baseline_days)

    st.markdown("#### Your baselines")
    st.caption(label)

    # Explained once here rather than repeated under every row.
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:7px;font-size:0.7rem;"
        f"color:{MUTED};margin:0 0 10px 0;'>"
        f"<span style='display:inline-block;width:24px;height:8px;border-radius:4px;"
        f"background:{IN_RANGE}2e;flex:none;'></span>"
        f"Shaded band is your normal range, one SD either side of your own average"
        f"</div>",
        unsafe_allow_html=True,
    )

    if state == "partial":
        st.caption("Ranges will tighten as more of your history is collected.")

    for marker in markers.values():
        render_baseline_row(marker, on_open=on_open, key_prefix=key_prefix)


"""
Signal drill down.

The list view answers "is this signal normal for me today". This view answers the
questions that follow: how far outside, for how long, how steady has it been, and
what does it feed into.

Navigation is a single key in `st.session_state`. Streamlit reruns the script on
every interaction, so the app renders either the list or this detail depending on
that key, and the back button clears it. That keeps the drill down to one piece
of state rather than a routing layer the prototype does not need.
"""



# Windows the user can look back over. "day1" is the newest addition — the
# only window that can show intraday movement, now that a 24-hour view is
# possible. 14 and 30 mirror the baseline windows the architecture doc
# refers to; 7 is the shortest window that can carry a range at all, so it
# is the floor rather than a design choice.
WINDOW_OPTIONS = ["day1", 7, 14, 30]
DEFAULT_WINDOW = 30


def _window_label(window):
    return "1 day" if window == "day1" else f"{window} days"


def _stat(label, value, sub=None, color=None):
    """One cell of the summary grid."""
    color = color or "#1f2328"
    sub_html = (
        f"<div style='font-size:0.66rem;color:{MUTED};margin-top:1px;'>{sub}</div>"
        if sub
        else ""
    )
    return (
        f"<div style='padding:9px 10px;background:#fafbfc;border:1px solid #eceff3;"
        f"border-radius:8px;'>"
        f"<div style='font-size:0.63rem;color:{MUTED};text-transform:uppercase;"
        f"letter-spacing:0.05em;font-weight:600;'>{label}</div>"
        f"<div style='font-size:0.98rem;font-weight:700;color:{color};"
        f"margin-top:2px;'>{value}</div>{sub_html}</div>"
    )


def _fixed_y_domain(persona_id, signal_key):
    """
    Y-axis domain for a signal, computed once from its full 30-day history
    and baseline band. Passed to whichever chart is being drawn (1/7/14/30
    day view) so the vertical scale stays put when switching between them
    — only the data on screen changes, not the zoom level.
    """
    full_series = mock_data.get_biomarker_series(
        persona_id, signal_key, days=mock_data.BASELINE_WINDOW_DAYS
    )
    baseline = bl.compute_baseline(full_series)
    values = list(full_series)
    if baseline is not None:
        low, high = bl.normal_range(baseline)
        values += [low, high]
    span = max(values) - min(values)
    pad = span * 0.15 if span else 1.0
    return (min(values) - pad, max(values) + pad)


def render_signal_detail(persona_id, signal_key, on_back):
    """
    persona_id: whose signal this is
    signal_key: which signal
    on_back: callback that clears the drill down state
    """
    st.button("Back to baselines", key="drill_back", on_click=on_back)

    window_key = f"window_{signal_key}"
    if window_key not in st.session_state:
        st.session_state[window_key] = DEFAULT_WINDOW

    # key= alone drives this widget. Also passing index= (computed from a
    # value read from session_state just before the widget is created) is
    # a documented Streamlit anti-pattern — the two can fall out of sync by
    # one interaction, which is exactly the "click 1 day, see 7 days"
    # lag this was causing.
    st.radio(
        "Window",
        options=WINDOW_OPTIONS,
        format_func=_window_label,
        horizontal=True,
        key=window_key,
    )
    window = st.session_state[window_key]

    if window == "day1":
        _render_day1_detail(persona_id, signal_key)
    else:
        _render_daily_detail(persona_id, signal_key, window)


def _render_day1_detail(persona_id, signal_key):
    """
    24-hour intraday view. Headline and status still compare against the
    same daily personal range the 7/14/30 views use — a range isn't
    recomputed from a single day. What changes is time resolution: instead
    of one point per day, this shows the last 24 hours at 10-minute steps.
    """
    marker = mock_data.get_intraday_marker(persona_id, signal_key)
    label = marker["label"]
    unit = marker["unit"]
    precision = marker["precision"]
    baseline = marker["baseline"]
    deviation = bl.classify(marker["current"], baseline)
    color = status_color(deviation, marker["higher_is_better"])

    st.markdown(
        f"<div style='margin-top:6px;'>"
        f"<span style='font-size:0.66rem;color:{MUTED};text-transform:uppercase;"
        f"letter-spacing:0.05em;font-weight:600;background:#f1f3f5;"
        f"border-radius:4px;padding:2px 7px;'>{marker['system']}</span></div>"
        f"<div style='font-size:1.3rem;font-weight:700;margin-top:7px;'>{label}</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"<div style='display:flex;align-items:baseline;gap:8px;margin:2px 0 10px 0;'>"
        f"<span style='font-size:2.3rem;font-weight:700;line-height:1.05;"
        f"color:{color};'>{fmt(marker['current'], precision)}</span>"
        f"<span style='font-size:0.9rem;color:{MUTED};'>{unit}</span>"
        f"<span style='margin-left:auto;background:{color}1a;color:{color};"
        f"border:1px solid {color}55;border-radius:999px;padding:2px 10px;"
        f"font-size:0.75rem;font-weight:600;'>"
        f"{status_word(deviation, marker['higher_is_better'])}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    if baseline is None:
        st.info(
            f"No personal range yet — {bl.RANGE_MIN_DAYS} days needed before "
            f"a range can be calculated from your own readings."
        )
    else:
        low, high = bl.normal_range(baseline)
        inside = sum(1 for v in marker["values"] if low <= v <= high)
        total = len(marker["values"])
        beyond = (
            "beyond your usual range"
            if deviation.state != "in_range"
            else "within your usual range"
        )
        cells = [
            _stat("Your average", f"{fmt(baseline.mean, precision)} {unit}",
                  f"from {baseline.n} days"),
            _stat("Your normal range",
                  f"{fmt(low, precision)} to {fmt(high, precision)} {unit}",
                  "one SD either side"),
            _stat("Deviation", f"{deviation.z:+.2f} SD", beyond, color=color),
            _stat("Readings in range", f"{inside} of {total}", "across today"),
        ]
        st.markdown(
            "<div style='display:grid;grid-template-columns:1fr 1fr;gap:7px;"
            "margin-bottom:12px;'>" + "".join(cells) + "</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            f"Range is {fmt(low, precision)} to {fmt(high, precision)} {unit} — "
            f"a range isn't recalculated from one day, so this is the same "
            f"range the 7/14/30 day views use."
        )

    render_intraday_chart(marker, y_domain=_fixed_y_domain(persona_id, signal_key))

    if marker.get("fully_synthetic"):
        st.caption(
            "⚠ Fully simulated signal — unlike the other biomarkers here, "
            "there is no real reading behind this one at all, not even "
            "today's. The export has no numeric sleep or circadian data yet."
        )

    contributes = mock_data.get_signal_scores(signal_key)
    if contributes:
        st.caption(f"Contributes to: {', '.join(contributes)}")


def _render_daily_detail(persona_id, signal_key, window):
    marker = mock_data.get_biomarker(persona_id, signal_key, days=window)

    label = marker["label"]
    unit = marker["unit"]
    precision = marker["precision"]
    baseline = marker["baseline"]
    deviation = marker["deviation"]
    color = status_color(deviation, marker["higher_is_better"])

    st.markdown(
        f"<div style='margin-top:6px;'>"
        f"<span style='font-size:0.66rem;color:{MUTED};text-transform:uppercase;"
        f"letter-spacing:0.05em;font-weight:600;background:#f1f3f5;"
        f"border-radius:4px;padding:2px 7px;'>{marker['system']}</span></div>"
        f"<div style='font-size:1.3rem;font-weight:700;margin-top:7px;'>{label}</div>",
        unsafe_allow_html=True,
    )

    # Today's reading, given the space it deserves as the headline number.
    st.markdown(
        f"<div style='display:flex;align-items:baseline;gap:8px;margin:2px 0 10px 0;'>"
        f"<span style='font-size:2.3rem;font-weight:700;line-height:1.05;"
        f"color:{color};'>{fmt(marker['current'], precision)}</span>"
        f"<span style='font-size:0.9rem;color:{MUTED};'>{unit}</span>"
        f"<span style='margin-left:auto;background:{color}1a;color:{color};"
        f"border:1px solid {color}55;border-radius:999px;padding:2px 10px;"
        f"font-size:0.75rem;font-weight:600;'>"
        f"{status_word(deviation, marker['higher_is_better'])}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Summary grid. Two by two so it stays readable at phone width.
    if baseline is not None:
        low, high = bl.normal_range(baseline)
        inside, total = marker["in_range"]
        beyond = (
            "beyond your usual range"
            if deviation.state != "in_range"
            else "within your usual range"
        )
        cells = [
            _stat("Your average", f"{fmt(baseline.mean, precision)} {unit}",
                  f"from {baseline.n} days"),
            _stat("Your normal range",
                  f"{fmt(low, precision)} to {fmt(high, precision)} {unit}",
                  "one SD either side"),
            _stat("Deviation", f"{deviation.z:+.2f} SD", beyond, color=color),
            _stat("Days in range", f"{inside} of {total}",
                  trend_phrase(marker["trend"], marker["observed_days"])),
        ]
        st.markdown(
            "<div style='display:grid;grid-template-columns:1fr 1fr;gap:7px;"
            "margin-bottom:12px;'>" + "".join(cells) + "</div>",
            unsafe_allow_html=True,
        )
    else:
        st.info(
            f"No personal range yet. {marker['observed_days']} days of "
            f"{marker['phrase']} collected, {bl.RANGE_MIN_DAYS} needed before a "
            f"range can be calculated from your own readings."
        )

    render_signal_chart(marker, y_domain=_fixed_y_domain(persona_id, signal_key))

    if marker.get("fully_synthetic"):
        st.caption(
            "⚠ Fully simulated signal — unlike the other biomarkers here, "
            "there is no real reading behind this one at all, not even "
            "today's. The export has no numeric sleep or circadian data yet."
        )

    st.markdown(f"**What this means:** {interpretation(marker)}")

    contributes = mock_data.get_signal_scores(signal_key)
    if contributes:
        st.caption(f"Contributes to: {', '.join(contributes)}")

    with st.expander("How this baseline was calculated"):
        baseline_days_text = marker["baseline"].n if marker["baseline"] else mock_data.BASELINE_WINDOW_DAYS - 1
        st.markdown(
            f"""
Your baseline is calculated from **your own readings only**, never from a
population average.

- Readings used: the last **{baseline_days_text} days**, excluding today,
  so today's value is not folded into the range it is being judged against.
  This is fixed regardless of the window selected above — the window only
  changes how much history is drawn on the chart, not what counts as normal.
- Centre: the mean of those readings.
- Range: mean plus or minus **one standard deviation**, which covers roughly
  68% of your own readings. Anything outside it is unusual *for you*.
- Deviation is reported in standard deviations so signals with different units
  can be compared directly.
- A range is only drawn once there are at least **{bl.RANGE_MIN_DAYS} days** of
  history. Below that, a standard deviation is not a usable estimate of how much
  you actually vary.
"""
        )
