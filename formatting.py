"""
Shared presentation helpers for signals.

Kept in one module because the baseline row, the chart and the drill down all
have to describe the same reading, and three components inventing their own
wording is how a dashboard ends up saying "below range" in one place and
"slightly low" in another for the same number.
"""

# Palette. One green, one amber, one red, plus neutrals.
#
# Status is never carried by colour alone anywhere in the UI: every coloured
# element is paired with a word. Roughly one in twelve men has some degree of
# colour vision deficiency, and a health app that hides "your reading is unusual"
# in a hue is failing exactly the people it is meant to inform.
IN_RANGE = "#1a7f37"
UNUSUAL = "#b8860b"
MARKED = "#b42318"
NEUTRAL = "#8a8a8a"
MUTED = "#6b7280"
LINE = "#0b6bcb"
TRACK = "#eceff3"


def fmt(value, precision=0):
    """Format a reading at the precision the device actually reports."""
    if value is None:
        return "--"
    return f"{value:.{precision}f}"


def is_favourable(deviation, higher_is_better):
    """
    Whether an out of range reading points the good way for this signal.

    Being above your usual HRV and being above your usual resting heart rate are
    both "outside your range", and they are not the same news.
    """
    if deviation is None or deviation.state == "in_range":
        return False
    return (deviation.state == "above") == higher_is_better


def status_color(deviation, higher_is_better=None):
    """
    Colour for a deviation, neutral when there is nothing to compare to.

    Pass higher_is_better and a deviation in the favourable direction is coloured
    as in range. Amber on a reading that is good news reads as a warning about
    nothing, and a health app that cries wolf gets ignored on the day it matters.

    Omit it and the colour reflects deviation alone, which is the right default
    for any caller that does not know which way is good for the signal.
    """
    if deviation is None:
        return NEUTRAL
    if deviation.state == "in_range":
        return IN_RANGE
    if higher_is_better is not None and is_favourable(deviation, higher_is_better):
        return IN_RANGE
    return MARKED if deviation.magnitude == "marked" else UNUSUAL


def status_word(deviation, higher_is_better=None):
    """
    Short status label. Always rendered next to the colour, never instead of it.

    When the colour goes green for a favourable outlier the word has to say so
    too. Otherwise green versus amber becomes the only thing separating "you are
    unusually well recovered" from "your resting heart rate is up", and that
    distinction would be invisible to a colour blind reader.
    """
    if deviation is None:
        return "No range yet"
    if deviation.state == "in_range":
        return "In range"

    direction = "Above" if deviation.state == "above" else "Below"

    if higher_is_better is not None and is_favourable(deviation, higher_is_better):
        return f"{direction} range, favourable"

    return f"{direction} range" if deviation.magnitude == "unusual" else f"Well {direction.lower()} range"


def deviation_phrase(deviation, unit=""):
    """
    How far from normal, in the person's own standard deviations.

    SD units rather than raw units because that is what makes two signals
    comparable: two bpm and two hours are not the same size of event, but 1.5 SD
    in each case is.
    """
    if deviation is None:
        return "Not enough history to compare"
    magnitude = abs(deviation.z)
    if deviation.state == "in_range":
        if magnitude < 0.25:
            return "Right at your baseline"
        return f"{magnitude:.1f} SD from your baseline, within normal variation"
    direction = "above" if deviation.state == "above" else "below"
    return f"{magnitude:.1f} SD {direction} your baseline"


def interpretation(marker):
    """
    One sentence saying what the reading means for this person.

    Direction aware: a high resting heart rate and a high HRV are not the same
    news, so the wording depends on the signal rather than on the sign of z.

    Deliberately describes the observation and stops there. It does not diagnose,
    advise, or name a cause, which is the claim ceiling the product works under.
    """
    deviation = marker["deviation"]
    # Sentence form, so acronyms keep their capitals in prose.
    label = marker.get("phrase") or marker["label"]

    if deviation is None:
        return (
            f"Your {label} is being recorded, but there is not yet enough "
            f"history to say what is normal for you."
        )

    if deviation.state == "in_range":
        return f"Your {label} today is within your usual range."

    higher_is_better = marker["higher_is_better"]
    favourable = (deviation.state == "above") == higher_is_better
    direction = "higher" if deviation.state == "above" else "lower"

    if favourable:
        return (
            f"Your {label} is {direction} than your usual range, which is a "
            f"favourable direction for this signal."
        )

    strength = "well outside" if deviation.magnitude == "marked" else "outside"
    return (
        f"Your {label} is {direction} than usual and sits {strength} your "
        f"normal range. Worth watching rather than acting on by itself."
    )


def stability_phrase(in_range):
    """How steady a signal has been across the window, not just today."""
    if not in_range:
        return None
    inside, total = in_range
    return f"{inside} of the last {total} days inside your range"


def trend_phrase(trend, days):
    """
    Direction across the whole window.

    The window is named explicitly because a signal can be drifting up across a
    month while having dropped over the last three days, and an unqualified
    "rising" would be read as "rising right now".
    """
    if trend is None:
        return None
    words = {"rising": "Rising", "falling": "Falling", "stable": "Stable"}
    return f"{words[trend]} across {days} days"


def with_unit(value, unit):
    """Joins a formatted value and its unit. No space before a percent sign."""
    return f"{value}{unit}" if unit == "%" else f"{value} {unit}"


def score_trend_insight(metric, values, higher_is_better, direction):
    """
    Short insight under a composite score trend chart.

    direction comes from baseline.trend_direction(), the same rule the Alerts
    tab uses, so the chart text and the alerts cannot disagree.
    """
    n = len(values)
    first, last = values[0], values[-1]
    avg = sum(values) / n

    if abs(last - avg) < 1:
        vs_avg = f"in line with the {n}-day average of {avg:.0f}%"
    elif last > avg:
        vs_avg = f"above the {n}-day average of {avg:.0f}%"
    else:
        vs_avg = f"below the {n}-day average of {avg:.0f}%"

    if direction in ("rising", "falling"):
        verb = "risen" if direction == "rising" else "fallen"
        good = (direction == "rising") == higher_is_better
        meaning = (
            "This is a favourable direction for this score."
            if good
            else "This is an unfavourable direction and is listed on the Alerts tab."
        )
        return (
            f"{metric} has {verb} {abs(last - first):.0f} points over {n} days, "
            f"from {first:.0f}% to {last:.0f}%. {meaning}"
        )

    return (
        f"{metric} has held steady over {n} days, between {min(values):.0f}% and "
        f"{max(values):.0f}%. Today's {last:.0f}% is {vs_avg}."
    )


def signal_chart_insight(marker):
    """Short insight under a signal chart in the drill down."""
    series = marker["series"]
    baseline = marker["baseline"]
    unit = marker["unit"]
    p = marker["precision"]
    n = len(series)

    if baseline is None:
        return (
            f"{n} days recorded so far. A personal range appears once there is "
            f"enough history to measure how much this signal normally varies."
        )

    low_v, high_v = min(series), max(series)
    spread = (
        f"Over the last {n} days, readings ranged from {fmt(low_v, p)} to "
        f"{with_unit(fmt(high_v, p), unit)}"
    )
    inside, total = marker["in_range"]
    outside = total - inside
    spread += (
        ", all inside your normal range."
        if outside == 0
        else f", with {outside} of {total} days outside your normal range."
    )

    current = series[-1]
    if n > 1 and current == high_v and series.count(high_v) == 1:
        second = "Today's reading is the highest in this window."
    elif n > 1 and current == low_v and series.count(low_v) == 1:
        second = "Today's reading is the lowest in this window."
    elif marker["trend"] in ("rising", "falling"):
        second = f"The readings show a {marker['trend']} trend across this window."
    else:
        second = "There is no clear upward or downward trend across this window."

    return f"{spread} {second}"


def intraday_insight(marker, low, high):
    """Short insight under the 24-hour chart. low/high: the daily normal range."""
    values = marker["values"]
    unit = marker["unit"]
    p = marker["precision"]
    text = (
        f"Over the last 24 hours, readings ranged from {fmt(min(values), p)} to "
        f"{with_unit(fmt(max(values), p), unit)}."
    )
    if low is not None:
        share = sum(1 for v in values if low <= v <= high) / len(values) * 100
        text += f" {share:.0f}% of readings were inside your daily normal range."
    return text
