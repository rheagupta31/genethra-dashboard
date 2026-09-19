"""
Data layer for the Genethra dashboard.

Patient identity and today's biomarker readings come from Tristan's real
export, One_Minute_Synthetic_TimeSeries.csv (5 patients, 30 days, one row
per minute). As of this file, every biomarker in that export is constant
per patient across all 43,200 minutes — only the timestamp changes. So
"today's" reading below is real, but there is no real day-to-day or
intraday variation yet to compute a personal baseline from.

Trend, alert, and biomarker-history generation logic below is Ore's —
ported from his merge onto this file's real patient data instead of his
original 3 fictional personas. Two corrections were made to his
SCORE_SIGNALS mapping in the process; see the comment above it.

Placeholder variation is layered on top so the baseline/trend/alert
features have something to work with, and it is labeled everywhere it
appears — PLACEHOLDER_NOTE below. When Tristan's export starts carrying
real variation, get_biomarker_series() and get_intraday_series() are the
only two functions that need to change.
"""

import math
import random
import zlib
from functools import lru_cache
from pathlib import Path

import pandas as pd

import baseline as bl

PLACEHOLDER_NOTE = (
    "Simulated variation — Tristan's export does not yet vary over time, "
    "so day-to-day and intraday history here is generated around today's "
    "real reading, not observed."
)

CSV_PATH = Path(__file__).parent / "One_Minute_Synthetic_TimeSeries.csv"


def _stable_hash(text: str) -> int:
    # Deterministic across runs, unlike Python's hash() which is salted
    # per-process — needed so every session shows the same numbers.
    return zlib.crc32(text.encode()) % 10000


# ---------------------------------------------------------------------------
# Patient identity — real, from Tristan's export
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load():
    df = pd.read_csv(CSV_PATH)
    # Export labels this column Celsius but the values (95.6-98.3) are
    # actually Fahrenheit. Left as-is here — the app displays this signal
    # in Fahrenheit, so no conversion is needed; the column name itself is
    # just the CSV's literal header text, kept so pandas indexing matches.
    return df


@lru_cache(maxsize=1)
def _demographics():
    return _load().groupby("ID").first()


def get_persona(persona_id: int) -> dict:
    row = _demographics().loc[persona_id]
    return {
        "ID": persona_id,
        "Age": int(row["Age"]),
        "Sex": row["Sex"],
        "Height": row["Height"],
        "Body Mass": row["Body Mass"],
        "BMI Value": row["BMI Value"],
        "BMI Category": row["BMI Category"],
        "Resting Heart Rate (bpm)": row["Resting Heart Rate (bpm)"],
        "Heart Rate (bpm)": row["Heart Rate (bpm)"],
        "HRV SDNN (ms)": row["HRV SDNN (ms)"],
        "Basal Energy Burned (kcal)": row["Basal Energy Burned (kcal)"],
        "Respiratory Rate (breaths/min)": row["Respiratory Rate (breaths/min)"],
        "Oxygen Saturation (%)": row["Oxygen Saturation (%)"],
        "Body Temperature (celsius)": row["Body Temperature (celsius)"],
        "Blood Pressure (mmHg)": row["Blood Pressure (mmHg)"],
        "Blood Pressure Category": row["Blood Pressure Category"],
    }


PERSONAS = [get_persona(pid) for pid in sorted(_demographics().index)]


def get_days_collected(persona_id: int) -> int:
    """Real fact from the export: 30 days span Sept 1-30, 2026."""
    return 30


# ---------------------------------------------------------------------------
# Composite scores
# ---------------------------------------------------------------------------

COMPOSITE_SCORES = [
    "Recovery", "Stress", "Readiness",
    "Sleep Quality", "Cardiovascular Load", "Circadian Stability",
]

IN_SCOPE_SCORES = {"Cardiovascular Load", "Sleep Quality"}

CONFIDENCE_WEIGHTS = {
    "data_completeness": 0.30,
    "sensor_signal_quality": 0.25,
    "temporal_recency": 0.20,
    "cross_device_consistency": 0.15,
    "historical_baseline_depth": 0.10,
}


def calculate_confidence(components: dict) -> tuple[float, str]:
    score = sum(components.get(k, 0) * w for k, w in CONFIDENCE_WEIGHTS.items())
    if score >= 85:
        band = "High"
    elif score >= 60:
        band = "Moderate"
    else:
        band = "Low"
    return round(score, 1), band


def _baseline_depth_score(days: int) -> float:
    return min(100.0, (days / 30) * 100)


def _cardiovascular_load(patient: dict) -> int:
    rhr = patient["Resting Heart Rate (bpm)"]
    hrv = patient["HRV SDNN (ms)"]
    bp_penalty = 15 if "Hypertension" in patient["Blood Pressure Category"] else 0
    load = (rhr - 50) * 0.8 - (hrv - 30) * 0.5 + bp_penalty + 40
    return int(max(0, min(100, load)))


def _recovery(patient: dict, cardio_load: int) -> int:
    hrv = patient["HRV SDNN (ms)"]
    value = 50 + (hrv - 40) * 0.8 - (cardio_load - 50) * 0.4
    return int(max(0, min(100, value)))


def _stress(patient: dict) -> int:
    hrv = patient["HRV SDNN (ms)"]
    rhr = patient["Resting Heart Rate (bpm)"]
    value = 50 - (hrv - 40) * 0.7 + (rhr - 60) * 0.6
    return int(max(0, min(100, value)))


def _readiness(recovery: int, sleep_quality: int) -> int:
    return int(max(0, min(100, recovery * 0.6 + sleep_quality * 0.4)))


def _sleep_quality(persona_id: int) -> int:
    # Not derived from any real signal — no sleep-stage data exists yet.
    rnd = random.Random(persona_id * 13)
    return rnd.randint(58, 92)


def _circadian_stability(persona_id: int) -> int:
    # Not derived from any real signal — no rhythm data exists yet.
    rnd = random.Random(persona_id * 29)
    return rnd.randint(55, 90)


def get_score_data(persona_id: int) -> dict:
    patient = get_persona(persona_id)
    days = get_days_collected(persona_id)

    cardio_load = _cardiovascular_load(patient)
    recovery = _recovery(patient, cardio_load)
    stress = _stress(patient)
    sleep_quality = _sleep_quality(persona_id)
    readiness = _readiness(recovery, sleep_quality)
    circadian = _circadian_stability(persona_id)

    values = {
        "Recovery": recovery,
        "Stress": stress,
        "Readiness": readiness,
        "Sleep Quality": sleep_quality,
        "Cardiovascular Load": cardio_load,
        "Circadian Stability": circadian,
    }

    data = {}
    for label, value in values.items():
        rnd = random.Random(persona_id * _stable_hash(label))
        confidence_components = {
            "data_completeness": rnd.randint(70, 100),
            "sensor_signal_quality": rnd.randint(70, 100),
            "temporal_recency": 100,
            "cross_device_consistency": rnd.randint(60, 100),
            "historical_baseline_depth": _baseline_depth_score(days),
        }
        conf_score, conf_band = calculate_confidence(confidence_components)
        data[label] = {
            "value": value,
            "confidence_score": conf_score,
            "confidence_band": conf_band,
            "days_of_baseline": days,
        }
    return data


# ---------------------------------------------------------------------------
# Composite score trend (Insights tab) — Ore's deterministic-direction
# generator. A pure random walk had two problems: it could drift away from
# the score printed on the card (chart disagreeing with its own number),
# and a 14-step walk clears a 3-point move by chance most of the time,
# which is what made the Alerts tab fire on noise. This version picks one
# direction per patient+metric and ramps to it, ending exactly on today's
# score.
# ---------------------------------------------------------------------------

TREND_DIRECTIONS = ["improving", "declining", "flat"]
TREND_DRIFT = 9.0  # points moved across the window when genuinely trending


def _trend_direction_for(persona_id: int, metric: str) -> str:
    rnd = random.Random(persona_id * _stable_hash("dir" + metric))
    return rnd.choice(TREND_DIRECTIONS)


def get_trend_data(persona_id: int, metric: str, days: int = 14) -> list[float]:
    """Daily values for a composite score, oldest first, today last."""
    scores = get_score_data(persona_id)
    current = float(scores[metric]["value"])
    direction = _trend_direction_for(persona_id, metric)
    drift = {"improving": TREND_DRIFT, "declining": -TREND_DRIFT, "flat": 0.0}[direction]
    start = current - drift

    rnd = random.Random(persona_id * _stable_hash(metric))
    series = []
    for day in range(days):
        progress = day / max(1, days - 1)
        value = start + drift * progress
        wobble = math.sin(day / 3.0) * 1.6 + rnd.uniform(-1.4, 1.4)
        series.append(round(max(0.0, min(100.0, value + wobble)), 1))

    series[-1] = current
    return series


BODY_SYSTEMS = ["Cardiovascular", "Autonomic", "Sleep / Circadian", "Metabolic"]

SYSTEM_STATUS_POOL = ["improving", "stable", "declining"]


# Which composite score(s) a body system's status is derived from, where
# one exists. Cardiovascular Load's own signals (resting_hr, hrv_sdnn) span
# both the Cardiovascular and Autonomic system tags in BIOMARKER_META, so
# this mapping is a reasonable-but-imperfect simplification, not a precise
# taxonomy — same caveat as SCORE_SIGNALS above. Autonomic and Metabolic
# have no composite score that maps to them, so they're left out here
# entirely rather than forcing a link that doesn't exist; their status
# stays randomly generated, same as before.
SYSTEM_SCORES = {
    "Cardiovascular": ["Cardiovascular Load"],
    "Sleep / Circadian": ["Sleep Quality", "Circadian Stability"],
}


def _system_status_from_scores(persona_id: int, score_labels: list[str]):
    """
    Derives 'improving' / 'stable' / 'declining' from the real trend
    direction of the composite score(s) a system maps to — the same
    statistical test get_alerts() uses, not just the raw first-to-last
    delta. Adjusted for HIGHER_IS_BETTER so 'improving' always means
    favorable, not just 'the number went up'. Returns None when no score
    maps to this system, so the caller falls back to random.
    """
    if not score_labels:
        return None

    votes = []
    for label in score_labels:
        trend = get_trend_data(persona_id, label)
        direction = bl.trend_direction(trend, baseline=bl.compute_baseline(trend))
        good = HIGHER_IS_BETTER[label]
        if direction == "rising":
            votes.append(1 if good else -1)
        elif direction == "falling":
            votes.append(-1 if good else 1)
        else:
            votes.append(0)

    avg = sum(votes) / len(votes)
    if avg > 0.25:
        return "improving"
    if avg < -0.25:
        return "declining"
    return "stable"


def get_body_systems_data(persona_id: int) -> dict:
    # "In scope" is derived from BIOMARKER_META, not hand-maintained — a
    # system is ready if at least one working signal is tagged to it. This
    # was previously a hardcoded tuple that said only Cardiovascular and
    # Sleep/Circadian were ready, which had drifted out of sync with the
    # Baselines tab: Autonomic (HRV, Respiratory Rate) and Metabolic (Body
    # Temperature) already had working signals, while Sleep/Circadian had
    # none. Deriving it here means the two tabs can't disagree again.
    #
    # Status is the same idea applied to the Insights tab: where a
    # composite score maps to a system (see SYSTEM_SCORES), status comes
    # from that score's real trend, not an independent random draw — this
    # is exactly what was previously letting Home say "declining" while
    # Insights showed the same area clearly improving.
    systems_with_signals = {meta["system"] for meta in BIOMARKER_META.values()}
    rnd = random.Random(persona_id * 51)
    result = {}
    for system in BODY_SYSTEMS:
        derived = _system_status_from_scores(persona_id, SYSTEM_SCORES.get(system, []))
        status = derived if derived is not None else rnd.choice(SYSTEM_STATUS_POOL)
        result[system] = {
            "status": status,
            "in_scope": system in systems_with_signals,
        }
    return result


HIGHER_IS_BETTER = {
    "Recovery": True,
    "Stress": False,
    "Readiness": True,
    "Sleep Quality": True,
    "Cardiovascular Load": False,
    "Circadian Stability": True,
}


def get_alerts(persona_id: int) -> list[dict]:
    """
    Alerts for scores moving in an unfavourable direction.

    Uses baseline.trend_direction(), which requires a fitted slope to clear
    two standard errors (~95% confidence) before calling a series rising or
    falling — the same rule the trend chart itself uses, so the two views
    cannot disagree on screen the way a raw delta threshold allowed.
    """
    alerts = []

    for label in COMPOSITE_SCORES:
        trend = get_trend_data(persona_id, label)
        direction = bl.trend_direction(trend, baseline=bl.compute_baseline(trend))

        if direction not in ("rising", "falling"):
            continue

        good = HIGHER_IS_BETTER[label]
        moved_bad = (good and direction == "falling") or (not good and direction == "rising")
        if moved_bad:
            delta = trend[-1] - trend[0]
            alerts.append({
                "severity": "high" if abs(delta) > 6 else "moderate",
                "title": f"{label} trending {'down' if good else 'up'}",
                "description": f"{label} moved {abs(delta):.1f} points over the last {len(trend)} days, a change large enough to clear the noise threshold in the direction associated with declining status.",
            })

    systems = get_body_systems_data(persona_id)
    for name, sdata in systems.items():
        if sdata["status"] == "declining":
            alerts.append({
                "severity": "moderate",
                "title": f"{name} system declining",
                "description": f"The {name} system's trend indicator has moved to declining based on current inputs.",
            })

    return alerts


BIOMARKER_FIELDS = [
    ("Resting Heart Rate", "Resting Heart Rate (bpm)", "bpm"),
    ("Heart Rate", "Heart Rate (bpm)", "bpm"),
    ("HRV (SDNN)", "HRV SDNN (ms)", "ms"),
    ("Blood Pressure", "Blood Pressure (mmHg)", "mmHg"),
    ("Respiratory Rate", "Respiratory Rate (breaths/min)", "breaths/min"),
    ("Oxygen Saturation", "Oxygen Saturation (%)", "%"),
    ("Body Temperature", "Body Temperature (celsius)", "\u00b0F"),
    ("Basal Energy Burned", "Basal Energy Burned (kcal)", "kcal"),
    ("BMI", "BMI Value", "kg/m²"),
]


def get_biomarkers(persona_id: int) -> list[dict]:
    patient = get_persona(persona_id)
    out = []
    for label, key, unit in BIOMARKER_FIELDS:
        value = patient[key]
        if key == "Body Temperature (celsius)":
            value = round(value, 2)
        out.append({"label": label, "value": value, "unit": unit})
    return out


# ---------------------------------------------------------------------------
# Baseline signals — Ore's AR(1) generator, running on real patient data.
#
# Blood Pressure excluded (string, not a number). BMI and Basal Energy
# excluded (don't vary day to day). Heart Rate excluded (near-duplicate of
# Resting HR in this dataset).
# ---------------------------------------------------------------------------

BIOMARKER_META = {
    "resting_hr": {
        "field": "Resting Heart Rate (bpm)", "label": "Resting Heart Rate",
        "phrase": "resting heart rate", "unit": "bpm",
        "higher_is_better": False, "precision": 0, "system": "Cardiovascular",
    },
    "hrv_sdnn": {
        "field": "HRV SDNN (ms)", "label": "HRV (SDNN)",
        "phrase": "HRV", "unit": "ms",
        "higher_is_better": True, "precision": 0, "system": "Autonomic",
    },
    "respiratory_rate": {
        "field": "Respiratory Rate (breaths/min)", "label": "Respiratory Rate",
        "phrase": "respiratory rate", "unit": "breaths/min",
        "higher_is_better": False, "precision": 1, "system": "Autonomic",
    },
    "oxygen_saturation": {
        "field": "Oxygen Saturation (%)", "label": "Oxygen Saturation",
        "phrase": "oxygen saturation", "unit": "%",
        "higher_is_better": True, "precision": 1, "system": "Cardiovascular",
    },
    "body_temperature": {
        "field": "Body Temperature (celsius)", "label": "Body Temperature",
        "phrase": "body temperature", "unit": "\u00b0F",
        # Prototype convention, same as Ore's original — lower reads as
        # favourable. Worth confirming with Dr. Muhammad, same open item
        # he flagged.
        "higher_is_better": False, "precision": 1, "system": "Metabolic",
    },
    "sleep_duration": {
        # No "field" — unlike the five signals above, there is no real
        # column for this at all. The export's only sleep-related fields
        # (Sleep Analysis, Sleep State, Activity State) are categorical and
        # constant ("inBed" / "Awake" / "Sedentary" for every patient,
        # every minute) — nothing numeric to anchor even today's value to.
        # So this signal is FULLY invented: not just simulated history
        # around a real reading, but an invented reading too. Flagged via
        # fully_synthetic below, and called out separately in the UI.
        "field": None, "label": "Sleep Duration",
        "phrase": "sleep duration", "unit": "hrs",
        "higher_is_better": True, "precision": 1, "system": "Sleep / Circadian",
        "fully_synthetic": True,
    },
}

# Plausible starting point for signals with no real reading to anchor to
# at all (BIOMARKER_META entries where "field" is None).
SYNTHETIC_ANCHOR_RANGES = {
    "sleep_duration": (6.5, 8.2),  # hours — typical adult range
}


def _anchor_value(persona_id: int, marker_key: str, meta: dict) -> float:
    """Today's reading for a signal. Real, from the export, when the
    signal has a field. Fully invented — a deterministic per-persona
    starting point, not derived from anything in the export — when it
    doesn't."""
    if meta["field"] is not None:
        return float(get_persona(persona_id)[meta["field"]])
    lo, hi = SYNTHETIC_ANCHOR_RANGES[marker_key]
    rnd = random.Random(persona_id * _stable_hash("anchor" + marker_key))
    return rnd.uniform(lo, hi)

# Typical within-person day-to-day variation. PROTOTYPE VALUES — should be
# replaced with dispersion measured from Tristan's real series once it
# carries real variation.
BIOMARKER_SIM_SD = {
    "resting_hr": 3.0,
    "hrv_sdnn": 7.0,
    "respiratory_rate": 0.8,
    "oxygen_saturation": 0.6,
    "body_temperature": 0.36,  # 0.2°C equivalent, scaled to °F (×9/5)
    "sleep_duration": 0.7,  # hours, night-to-night variation
}

# Minute-to-minute noise is smaller than day-to-day variation — expressed
# as a fraction of the daily SD rather than a separate constant per signal.
INTRADAY_SD_FRACTION = 0.3

SERIES_AUTOCORRELATION = 0.45
DEVIATION_RAMP_DAYS = 3

# The range shown as "your normal" is always computed from this fixed
# 30-day history, regardless of which window (1/7/14/30 days) is being
# viewed. Otherwise switching windows silently changes what "normal"
# means. The window selector only controls how much of the line is drawn.
BASELINE_WINDOW_DAYS = 30

# Which signals each composite score is actually computed from — not a
# published formula (none exists), and corrected from Ore's original
# mapping in two places: Circadian Stability had no entry here (it was
# listed as coming from body_temperature, but _circadian_stability() is
# pure random.randint and never reads it), and Cardiovascular Load's
# respiratory_rate was dropped (_cardiovascular_load() only reads resting
# HR, HRV, and blood pressure category).
SCORE_SIGNALS = {
    "Recovery": ["hrv_sdnn", "resting_hr"],
    "Stress": ["hrv_sdnn", "resting_hr"],
    "Readiness": ["hrv_sdnn", "resting_hr"],  # indirect, via Recovery
    "Cardiovascular Load": ["resting_hr", "hrv_sdnn"],
}


def _today_offset(persona_id: int, marker_key: str, sd: float) -> float:
    """How far today's reading sits from this person's simulated historical
    mean. Seeded so each persona has a stable mix of in-range and
    out-of-range signals."""
    rnd = random.Random(persona_id * _stable_hash("off" + marker_key))
    return rnd.uniform(-1.9, 1.9) * sd


@lru_cache(maxsize=None)
def _generate_full_series(persona_id: int, marker_key: str) -> tuple:
    """
    The full BASELINE_WINDOW_DAYS-day history for one signal, oldest first,
    today last. Cached and always generated at the same fixed length, so
    that get_biomarker_series() can slice any shorter window from the same
    underlying walk — guaranteeing the visible tail of a 7-day view and a
    30-day view are identical, not two different random draws.
    """
    meta = BIOMARKER_META[marker_key]
    sd = BIOMARKER_SIM_SD[marker_key]
    precision = meta["precision"]
    n = BASELINE_WINDOW_DAYS

    current = _anchor_value(persona_id, marker_key, meta)
    offset = _today_offset(persona_id, marker_key, sd)
    history_mean = current - offset
    ramp = min(DEVIATION_RAMP_DAYS, n)

    rnd = random.Random(persona_id * _stable_hash(marker_key))
    rho = SERIES_AUTOCORRELATION
    innovation = math.sqrt(1 - rho ** 2)

    deviate = rnd.gauss(0, 1)
    values = []
    for day in range(n):
        raw = history_mean + sd * deviate
        days_from_end = n - 1 - day
        if days_from_end < ramp:
            raw += offset * (ramp - days_from_end) / ramp
        values.append(round(raw, precision))
        deviate = rho * deviate + innovation * rnd.gauss(0, 1)

    values[-1] = round(current, precision)  # today is the real reading
    return tuple(values)


def get_biomarker_series(persona_id: int, marker_key: str, days: int = 30) -> list[float]:
    """A window onto the signal's fixed 30-day history — a slice, not a
    fresh generation, so overlapping days show the same value regardless
    of which window is being viewed."""
    full = _generate_full_series(persona_id, marker_key)
    days = max(1, min(days, len(full)))
    return list(full[-days:])


def get_intraday_series(persona_id: int, marker_key: str, interval_minutes: int = 10):
    """Last 24 hours at `interval_minutes` resolution, ending at today's
    real reading. Placeholder minute-level noise with mild mean reversion
    so it doesn't wander over the simulated day. Returns
    (minutes_since_midnight, values)."""
    meta = BIOMARKER_META[marker_key]
    sd = BIOMARKER_SIM_SD[marker_key] * INTRADAY_SD_FRACTION
    precision = meta["precision"]
    real_value = _anchor_value(persona_id, marker_key, meta)
    rnd = random.Random(persona_id * 2000 + _stable_hash(marker_key))

    n = (24 * 60) // interval_minutes
    minutes = [i * interval_minutes for i in range(n)]
    values = []
    val = real_value
    for _ in range(n):
        val += rnd.uniform(-sd, sd)
        val += (real_value - val) * 0.05  # mild pull back toward today's real value
        values.append(round(val, precision))
    values[-1] = round(real_value, precision)  # "now" matches the real reading exactly
    return minutes, values


def get_biomarker(persona_id: int, marker_key: str, days: int = 30) -> dict:
    """One signal fully resolved: reading, baseline, deviation, trend.
    The baseline always comes from the fixed 30-day history regardless of
    `days` — see BASELINE_WINDOW_DAYS above. `days` only controls how much
    of the series is returned for plotting."""
    meta = BIOMARKER_META[marker_key]
    series = get_biomarker_series(persona_id, marker_key, days=days)
    full_series = get_biomarker_series(persona_id, marker_key, days=BASELINE_WINDOW_DAYS)
    baseline = bl.compute_baseline(full_series)
    current = series[-1]

    return {
        "key": marker_key,
        "label": meta["label"],
        "phrase": meta["phrase"],
        "system": meta["system"],
        "unit": meta["unit"],
        "precision": meta["precision"],
        "higher_is_better": meta["higher_is_better"],
        "fully_synthetic": meta.get("fully_synthetic", False),
        "current": current,
        "series": series,
        "observed_days": len(series),
        "baseline": baseline,
        "deviation": bl.classify(current, baseline),
        "trend": bl.trend_direction(series, baseline=baseline),
        "in_range": bl.days_in_range(series, baseline),
    }


def get_baseline_markers(persona_id: int, days: int = 30) -> dict:
    return {key: get_biomarker(persona_id, key, days=days) for key in BIOMARKER_META}


def get_intraday_marker(persona_id: int, marker_key: str, interval_minutes: int = 10) -> dict:
    """Same signal, last-24-hours view. The shaded band still comes from
    the fixed 30-day baseline — a range isn't recomputed from one day."""
    meta = BIOMARKER_META[marker_key]
    full_series = get_biomarker_series(persona_id, marker_key, days=BASELINE_WINDOW_DAYS)
    baseline = bl.compute_baseline(full_series)
    minutes, values = get_intraday_series(persona_id, marker_key, interval_minutes)

    return {
        "key": marker_key,
        "label": meta["label"],
        "phrase": meta["phrase"],
        "unit": meta["unit"],
        "precision": meta["precision"],
        "system": meta["system"],
        "higher_is_better": meta["higher_is_better"],
        "fully_synthetic": meta.get("fully_synthetic", False),
        "minutes": minutes,
        "values": values,
        "baseline": baseline,
        "current": values[-1],
    }


def get_signal_scores(signal_key: str) -> list[str]:
    """Composite scores a signal actually contributes to, so the drill
    down can say so. Circadian Stability deliberately has no entries
    pointing to it — see SCORE_SIGNALS comment above."""
    return [score for score, signals in SCORE_SIGNALS.items() if signal_key in signals]
