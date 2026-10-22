"""
Tests for how readings are described in words.

The wording carries clinical weight. "Higher than usual" is good news for HRV and
bad news for resting heart rate, and a component that gets that backwards would
reassure someone it should be alerting.
"""

import pytest

import formatting as fmt
import baseline as bl


def _marker(key, label, higher_is_better, current, mean, sd):
    baseline = bl.Baseline(mean=mean, sd=sd, n=20)
    return {
        "key": key,
        "label": label,
        "unit": "bpm",
        "precision": 0,
        "higher_is_better": higher_is_better,
        "current": current,
        "baseline": baseline,
        "deviation": bl.classify(current, baseline),
    }


# --- status ----------------------------------------------------------------

def test_status_word_is_always_present():
    # Status must never be carried by colour alone, so every state needs a word.
    for deviation in [
        None,
        bl.classify(100, bl.Baseline(100, 10, 20)),
        bl.classify(115, bl.Baseline(100, 10, 20)),
        bl.classify(75, bl.Baseline(100, 10, 20)),
    ]:
        assert fmt.status_word(deviation).strip()


def test_status_word_distinguishes_direction_and_severity():
    baseline = bl.Baseline(100, 10, 20)
    assert fmt.status_word(bl.classify(100, baseline)) == "In range"
    assert fmt.status_word(bl.classify(112, baseline)) == "Above range"
    assert fmt.status_word(bl.classify(88, baseline)) == "Below range"
    assert "well" in fmt.status_word(bl.classify(125, baseline)).lower()


def test_no_baseline_has_its_own_status():
    assert fmt.status_word(None) == "No range yet"


def test_status_colour_falls_back_to_neutral_without_a_baseline():
    assert fmt.status_color(None) == fmt.NEUTRAL


# --- deviation phrasing ----------------------------------------------------

def test_deviation_phrase_reports_sd_units():
    baseline = bl.Baseline(100, 10, 20)
    assert "1.5 SD above" in fmt.deviation_phrase(bl.classify(115, baseline))
    assert "1.5 SD below" in fmt.deviation_phrase(bl.classify(85, baseline))


def test_deviation_phrase_handles_sitting_on_the_baseline():
    baseline = bl.Baseline(100, 10, 20)
    assert "at your baseline" in fmt.deviation_phrase(bl.classify(100, baseline))


def test_deviation_phrase_without_baseline_says_so():
    assert "not enough" in fmt.deviation_phrase(None).lower()


# --- interpretation --------------------------------------------------------

def test_high_hrv_reads_as_favourable():
    marker = _marker("hrv_sdnn", "HRV SDNN", True, 90, 70, 10)
    assert "favourable" in fmt.interpretation(marker)


def test_high_resting_hr_does_not_read_as_favourable():
    marker = _marker("resting_hr", "Resting HR", False, 70, 56, 4)
    text = fmt.interpretation(marker)
    assert "favourable" not in text
    assert "higher than usual" in text


def test_low_hrv_does_not_read_as_favourable():
    marker = _marker("hrv_sdnn", "HRV SDNN", True, 45, 70, 10)
    text = fmt.interpretation(marker)
    assert "favourable" not in text
    assert "lower than usual" in text


def test_low_resting_hr_reads_as_favourable():
    marker = _marker("resting_hr", "Resting HR", False, 46, 56, 4)
    assert "favourable" in fmt.interpretation(marker)


def test_interpretation_never_diagnoses_or_advises():
    # The product works under a wellness claim ceiling: describe the observation,
    # do not name a cause or tell someone what to do about it.
    banned = ["diagnos", "you should", "treat", "illness", "disease", "see a doctor"]
    cases = [
        _marker("hrv_sdnn", "HRV SDNN", True, 90, 70, 10),
        _marker("hrv_sdnn", "HRV SDNN", True, 45, 70, 10),
        _marker("resting_hr", "Resting HR", False, 70, 56, 4),
        _marker("resting_hr", "Resting HR", False, 56, 56, 4),
    ]
    for marker in cases:
        text = fmt.interpretation(marker).lower()
        for word in banned:
            assert word not in text, f"{word!r} appeared in {text!r}"


def test_interpretation_without_baseline_explains_the_gap():
    marker = _marker("resting_hr", "Resting HR", False, 58, 56, 4)
    marker["baseline"] = None
    marker["deviation"] = None
    assert "not yet enough history" in fmt.interpretation(marker)


# --- supporting phrases ----------------------------------------------------

def test_stability_phrase_reports_both_numbers():
    assert fmt.stability_phrase((22, 30)) == "22 of the last 30 days inside your range"
    assert fmt.stability_phrase(None) is None


def test_trend_phrase_names_the_window():
    # An unqualified "rising" gets read as "rising right now", which is not what
    # a slope across a month says.
    assert "30 days" in fmt.trend_phrase("rising", 30)
    assert fmt.trend_phrase(None, 30) is None


@pytest.mark.parametrize("value,precision,expected", [(58.0, 0, "58"), (6.42, 1, "6.4")])
def test_fmt_respects_precision(value, precision, expected):
    assert fmt.fmt(value, precision) == expected


def test_fmt_handles_missing_value():
    assert fmt.fmt(None) == "--"


# --- favourable outliers ----------------------------------------------------
#
# A reading can be outside the person's range and still be good news. Colouring
# it amber warns about nothing, and an app that cries wolf gets ignored on the
# day it matters.

def _above(baseline_mean=100, sd=10, value=115):
    return bl.classify(value, bl.Baseline(baseline_mean, sd, 20))


def _below(baseline_mean=100, sd=10, value=85):
    return bl.classify(value, bl.Baseline(baseline_mean, sd, 20))


def test_high_reading_is_favourable_when_higher_is_better():
    assert fmt.is_favourable(_above(), higher_is_better=True) is True
    assert fmt.is_favourable(_above(), higher_is_better=False) is False


def test_low_reading_is_favourable_when_lower_is_better():
    assert fmt.is_favourable(_below(), higher_is_better=False) is True
    assert fmt.is_favourable(_below(), higher_is_better=True) is False


def test_in_range_is_never_called_a_favourable_outlier():
    in_range = bl.classify(100, bl.Baseline(100, 10, 20))
    assert fmt.is_favourable(in_range, higher_is_better=True) is False
    assert fmt.is_favourable(None, higher_is_better=True) is False


def test_favourable_outlier_is_coloured_as_in_range():
    # High HRV: outside the range, but not a problem.
    assert fmt.status_color(_above(), higher_is_better=True) == fmt.IN_RANGE
    # High resting heart rate: outside the range, and worth noticing.
    assert fmt.status_color(_above(), higher_is_better=False) == fmt.UNUSUAL


def test_marked_unfavourable_deviation_stays_red():
    marked = bl.classify(130, bl.Baseline(100, 10, 20))
    assert fmt.status_color(marked, higher_is_better=False) == fmt.MARKED


def test_colour_without_the_flag_is_unchanged():
    # Callers that do not know which way is good for a signal must keep the old
    # behaviour rather than silently treating every high reading as good news.
    assert fmt.status_color(_above()) == fmt.UNUSUAL
    assert fmt.status_color(_below()) == fmt.UNUSUAL


def test_favourable_word_says_so_rather_than_relying_on_the_colour():
    # Green versus amber must never be the only thing separating "unusually well
    # recovered" from "resting heart rate is up" — that is invisible to a colour
    # blind reader.
    word = fmt.status_word(_above(), higher_is_better=True)
    assert "favourable" in word
    assert "Above range" in word


def test_unfavourable_word_carries_no_reassurance():
    assert "favourable" not in fmt.status_word(_above(), higher_is_better=False)
    assert "favourable" not in fmt.status_word(_below(), higher_is_better=True)


def test_word_without_the_flag_is_unchanged():
    assert fmt.status_word(_above()) == "Above range"
    assert fmt.status_word(_below()) == "Below range"


def test_colour_and_word_never_disagree():
    # The invariant the whole module exists to hold: if it is green, the word
    # must not sound like a warning, and vice versa.
    for higher_is_better in (True, False):
        for deviation in (_above(), _below()):
            green = fmt.status_color(deviation, higher_is_better) == fmt.IN_RANGE
            reassuring = "favourable" in fmt.status_word(deviation, higher_is_better)
            assert green == reassuring
