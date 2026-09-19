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
