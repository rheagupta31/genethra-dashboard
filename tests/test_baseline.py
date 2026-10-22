"""
Tests for baseline identification and deviation detection.

These cover the claims the UI makes out loud. If the app tells someone their
resting heart rate is "1.4 SD above your baseline", that number has to be right,
and it has to be computed from a baseline that excluded the reading being judged.
"""

import math

import pytest

import baseline as bl


# --- basic statistics -------------------------------------------------------

def test_mean_of_empty_series_is_none():
    assert bl.mean([]) is None


def test_stdev_uses_sample_denominator():
    # A person's history is a sample of their physiology, not the whole of it,
    # so ddof=1. Population sd of this series would be 2.0, sample sd is ~2.236.
    values = [2, 4, 4, 4, 5, 5, 7, 9]
    assert bl.stdev(values) == pytest.approx(2.13809, rel=1e-4)


def test_stdev_needs_two_points():
    assert bl.stdev([5]) is None
    assert bl.stdev([]) is None


# --- baseline construction --------------------------------------------------

def test_baseline_excludes_today():
    # Today is a wild outlier. If it leaked into the baseline it would drag the
    # mean toward itself and hide the very deviation the product exists to spot.
    history = [49.0, 51.0, 50.0, 52.0, 48.0, 50.0, 51.0, 49.0, 50.0, 50.0]
    baseline = bl.compute_baseline(history + [90.0])
    assert baseline is not None
    assert baseline.mean == pytest.approx(50.0)
    assert baseline.n == 10


def test_baseline_can_include_today_when_asked():
    history = [49.0, 51.0, 50.0, 52.0, 48.0, 50.0, 51.0, 49.0, 50.0, 50.0]
    baseline = bl.compute_baseline(history + [90.0], exclude_today=False)
    assert baseline.n == 11
    assert baseline.mean > 50.0


def test_baseline_refused_below_the_range_minimum():
    # Seven history points are needed, so a series of seven (six after today is
    # removed) is not enough and an eight point series is.
    assert bl.compute_baseline([60.0] * 6 + [61.0]) is None
    assert bl.compute_baseline([60.0, 61.0] * 3 + [62.0, 61.0]) is not None


def test_zero_variation_is_treated_as_no_baseline():
    # A zero width range would mark every future reading abnormal. Refuse it.
    assert bl.compute_baseline([60.0] * 12) is None


# --- deviation --------------------------------------------------------------

def _baseline(mean, sd, n=20):
    return bl.Baseline(mean=mean, sd=sd, n=n)


def test_zscore_is_in_the_persons_own_sd_units():
    assert bl.zscore(58, _baseline(56, 2.0)) == pytest.approx(1.0)
    assert bl.zscore(53, _baseline(56, 2.0)) == pytest.approx(-1.5)


def test_zscore_without_a_baseline_is_none():
    assert bl.zscore(58, None) is None
    assert bl.zscore(58, _baseline(56, 0)) is None


def test_classify_boundaries():
    baseline = _baseline(100, 10)

    # Just inside one SD is normal variation.
    inside = bl.classify(109.9, baseline)
    assert inside.state == "in_range" and inside.magnitude == "normal"

    # Exactly one SD is the first unusual reading.
    edge = bl.classify(110, baseline)
    assert edge.state == "above" and edge.magnitude == "unusual"

    # Two SD and beyond is marked.
    marked = bl.classify(120, baseline)
    assert marked.state == "above" and marked.magnitude == "marked"

    below = bl.classify(80, baseline)
    assert below.state == "below" and below.magnitude == "marked"


def test_classify_without_baseline_is_none():
    assert bl.classify(58, None) is None


def test_normal_range_is_mean_plus_minus_one_sd():
    low, high = bl.normal_range(_baseline(56, 2.0))
    assert (low, high) == pytest.approx((54.0, 58.0))


# --- stability and trend ----------------------------------------------------

def test_days_in_range_counts_readings_inside_the_band():
    baseline = _baseline(100, 10)
    series = [95, 105, 130, 99, 70]
    assert bl.days_in_range(series, baseline) == (3, 5)


def test_days_in_range_without_baseline_is_none():
    assert bl.days_in_range([1, 2, 3], None) is None


def test_trend_direction_reads_a_clear_slope():
    rising = [float(v) for v in range(20)]
    assert bl.trend_direction(rising) == "rising"
    assert bl.trend_direction(list(reversed(rising))) == "falling"


def test_trend_direction_calls_noise_stable():
    flat = [50.0, 50.4, 49.7, 50.1, 49.9, 50.2, 50.0, 49.8]
    assert bl.trend_direction(flat, baseline=_baseline(50, 0.25)) == "stable"


def test_trend_needs_enough_points():
    assert bl.trend_direction([1.0, 2.0, 3.0]) is None


def test_trend_slope_in_sd_units_is_unit_free():
    # The same relative drift must give the same answer whether the signal is
    # measured in bpm or in hours. That is the point of reporting in SD units.
    bpm = [60 + i for i in range(10)]
    hours = [6 + i * 0.1 for i in range(10)]
    assert bl.trend_slope(bpm, _baseline(60, 2.0)) == pytest.approx(
        bl.trend_slope(hours, _baseline(6, 0.2))
    )


# --- maturity ---------------------------------------------------------------

@pytest.mark.parametrize(
    "days,expected",
    [
        (0, "collecting"),
        (2, "collecting"),
        (3, "no_range"),
        (6, "no_range"),
        (7, "partial"),
        (29, "partial"),
        (30, "established"),
        (90, "established"),
    ],
)
def test_maturity_states(days, expected):
    state, label = bl.maturity(days)
    assert state == expected
    assert label


def test_thresholds_are_ordered():
    # The three day counts have to stay in this order or the UI starts
    # contradicting itself: scores before ranges, ranges before "established".
    assert bl.BASELINE_MIN_DAYS < bl.RANGE_MIN_DAYS < bl.BASELINE_MATURE_DAYS


def test_range_minimum_supports_a_sample_sd():
    # A standard deviation needs at least two points to exist at all, and the
    # product claims a week captures a full weekday cycle.
    assert bl.RANGE_MIN_DAYS >= 7
    assert bl.MARKED_DEVIATION_SD > bl.DEVIATION_SD
