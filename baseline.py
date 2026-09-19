"""
Baseline identification and deviation detection.

This is the computation half of Workflow 3, "Baseline Identification and Trend
Analysis". It is deliberately free of Streamlit imports so it can be unit tested
without a browser, and so the same functions can move server side later without
being rewritten.

The core idea of the product is that a reading is interpreted against *that
person's own* history, not a population average. So every function here takes a
person's own observed series and derives their normal from it. Nothing in this
module knows about population reference ranges, and that is on purpose.

Two day-count thresholds are used, and they mean different things:

  BASELINE_MIN_DAYS (3)   72 hours of passive collection before the twin will
                          show *scores* at all. Anchored to the Digital Twin MVP
                          Architecture doc.

  RANGE_MIN_DAYS (7)      minimum history before the app will draw a personal
                          *range*. A range is a claim about how much someone
                          normally varies, and a standard deviation from three or
                          four points is not a usable estimate of that. A week
                          also captures at least one weekday/weekend cycle.

  BASELINE_MATURE_DAYS (30)
                          the rubric's own upper reference point, from the line
                          that "a score generated after 3 days is less reliable
                          than after 30".

BASELINE_MIN_DAYS and BASELINE_MATURE_DAYS come from the architecture doc.
RANGE_MIN_DAYS is a prototype decision and is flagged in the README as one to
confirm with Sima.
"""

import math
from collections import namedtuple

BASELINE_MIN_DAYS = 3
RANGE_MIN_DAYS = 7
BASELINE_MATURE_DAYS = 30

# How far from the personal mean, in standard deviations, before a reading is
# called a deviation rather than normal variation. One SD covers roughly 68% of
# a person's own readings, so anything outside it is unusual *for them*, which is
# the comparison the product is built on.
DEVIATION_SD = 1.0

# A second, wider threshold for readings that are not just unusual but notable.
MARKED_DEVIATION_SD = 2.0

# Minimum points needed before a trend direction is worth stating.
TREND_MIN_POINTS = 5

# Slope, in standard deviations per day, below which a trend is called stable.
# Expressed in SD units so it means the same thing for heart rate in bpm and
# sleep duration in hours.
TREND_FLAT_SD_PER_DAY = 0.02

# How many standard errors a fitted slope must clear before it is called a trend
# rather than noise. Two is roughly the 95% level.
#
# This matters more than it looks. Fit a straight line through a dozen noisy
# readings and you will almost always get a non zero slope, and calling that
# "your resting heart rate is rising" in a health app is exactly the kind of
# false alarm the confidence rubric exists to prevent. A slope has to be large
# relative to the scatter around it, not just non zero.
TREND_CONFIDENCE_SE = 2.0


Baseline = namedtuple("Baseline", "mean sd n")

Deviation = namedtuple("Deviation", "z state magnitude")


def mean(values):
    """Arithmetic mean. Returns None for an empty series."""
    values = list(values)
    if not values:
        return None
    return sum(values) / len(values)


def stdev(values):
    """
    Sample standard deviation, ddof=1.

    Sample rather than population because a person's observed history is a
    sample of their ongoing physiology, not the complete set of it. Returns None
    for fewer than two points, where spread is undefined rather than zero.
    """
    values = list(values)
    if len(values) < 2:
        return None
    avg = mean(values)
    variance = sum((v - avg) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def compute_baseline(series, exclude_today=True):
    """
    Derive a personal baseline from that person's own observed series.

    series: daily values, oldest first, last element is today.
    exclude_today: leave today's reading out of the baseline it is compared
        against. Including it would drag the baseline toward the value being
        judged, which flattens exactly the deviation the product exists to spot.

    Returns a Baseline(mean, sd, n), or None when there is not enough history to
    make an honest claim about the person's normal range.
    """
    values = list(series)
    if exclude_today and values:
        values = values[:-1]

    if len(values) < RANGE_MIN_DAYS:
        return None

    avg = mean(values)
    sd = stdev(values)

    # No observed variation at all. Real physiology always varies, so this means
    # the data is degenerate rather than that the person is perfectly steady.
    # A zero width range would read as "every reading is abnormal", so refuse to
    # draw one instead.
    if sd is None or sd <= 0:
        return None

    return Baseline(mean=avg, sd=sd, n=len(values))


def normal_range(baseline, sd_multiple=DEVIATION_SD):
    """The person's normal range as (low, high), mean plus or minus one SD."""
    if baseline is None:
        return None
    return (
        baseline.mean - sd_multiple * baseline.sd,
        baseline.mean + sd_multiple * baseline.sd,
    )


def zscore(value, baseline):
    """
    How far a reading sits from the person's own mean, in their own SDs.

    Reporting deviation in SD units rather than raw units is what makes two
    signals comparable. Two bpm above baseline and two hours above baseline are
    not the same size of event, but 1.5 SD in each case is.
    """
    if baseline is None or baseline.sd is None or baseline.sd <= 0:
        return None
    return (value - baseline.mean) / baseline.sd


def classify(value, baseline):
    """
    Classify a reading against the person's baseline.

    Returns a Deviation(z, state, magnitude) where state is one of
    "in_range", "above", "below", and magnitude is "normal", "unusual", or
    "marked". Returns None when there is no baseline to compare against.
    """
    z = zscore(value, baseline)
    if z is None:
        return None

    if abs(z) < DEVIATION_SD:
        return Deviation(z=z, state="in_range", magnitude="normal")

    magnitude = "marked" if abs(z) >= MARKED_DEVIATION_SD else "unusual"
    state = "above" if z > 0 else "below"
    return Deviation(z=z, state=state, magnitude=magnitude)


def days_in_range(series, baseline):
    """
    How many of the last N readings sat inside the person's normal range.

    Gives the drill down a stability measure: a signal can be in range today and
    still have been all over the place this month, and the single current
    reading cannot show that.
    """
    if baseline is None:
        return None
    low, high = normal_range(baseline)
    inside = sum(1 for v in series if low <= v <= high)
    return inside, len(series)


def _fit(values):
    """
    Least squares fit of value against day index.

    Returns (slope, standard_error) in raw units per day, or None when there are
    too few points to fit anything meaningful.
    """
    n = len(values)
    if n < TREND_MIN_POINTS:
        return None

    xs = list(range(n))
    x_mean = mean(xs)
    y_mean = mean(values)

    sxx = sum((x - x_mean) ** 2 for x in xs)
    if sxx == 0:
        return None

    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values)) / sxx
    intercept = y_mean - slope * x_mean

    residuals = [y - (intercept + slope * x) for x, y in zip(xs, values)]
    if n > 2:
        residual_variance = sum(r * r for r in residuals) / (n - 2)
        stderr = math.sqrt(residual_variance / sxx)
    else:
        stderr = 0.0

    return slope, stderr


def trend_slope(series, baseline=None):
    """
    Least squares slope of the series, in units per day.

    When a baseline is given the slope is returned in SD units per day instead,
    so the number is comparable across signals with different units.
    """
    fit = _fit(list(series))
    if fit is None:
        return None

    slope, _ = fit
    if baseline is not None and baseline.sd:
        return slope / baseline.sd
    return slope


def trend_direction(series, baseline=None):
    """
    "rising", "falling", or "stable" for a series.

    A slope is only reported as a direction when it clears two bars: a practical
    floor, so a drift too small to matter is not announced, and the statistical
    one above, so scatter is not mistaken for movement.

    Deliberately reports direction only, with no judgement about whether the
    direction is good. Whether rising is good depends on the signal, and that
    call belongs with the caller that knows which signal this is.

    Returns None when there are too few points to say anything.
    """
    values = list(series)
    fit = _fit(values)
    if fit is None:
        return None

    slope, stderr = fit

    if baseline is not None and baseline.sd:
        slope /= baseline.sd
        stderr /= baseline.sd
        floor = TREND_FLAT_SD_PER_DAY
    else:
        scale = abs(mean(values) or 1.0)
        floor = TREND_FLAT_SD_PER_DAY * scale

    threshold = max(floor, TREND_CONFIDENCE_SE * stderr)

    if abs(slope) < threshold:
        return "stable"
    return "rising" if slope > 0 else "falling"


def maturity(days):
    """
    How established a baseline is, as (state, label).

    States, in order: "collecting" (no scores yet), "no_range" (scores but not
    enough history for a personal range), "partial", "established".
    """
    if days < BASELINE_MIN_DAYS:
        return "collecting", f"Establishing baseline, day {days} of {BASELINE_MIN_DAYS}"
    if days < RANGE_MIN_DAYS:
        return "no_range", f"{days} days collected, {RANGE_MIN_DAYS} needed for a range"
    if days < BASELINE_MATURE_DAYS:
        return "partial", f"Partial baseline, {days} days of data"
    return "established", f"Established baseline, {days} days of data"
