"""
Tests for the merged data layer.

Two things these lock down. First, the demo must render identical numbers on
every run: the previous seeding used hash() on a string, which Python salts per
process, so confidence bands flipped between launches. Second, the biomarker
series has to satisfy the contract the baseline layer assumes, since a series
that is too short or padded past the days actually worn would produce a range
the data cannot support.
"""

import subprocess
import sys

import baseline as bl
import mock_data as m


# --- determinism ------------------------------------------------------------

def _in_fresh_process(expr):
    """Run an expression in a new interpreter, so hash randomisation applies."""
    out = subprocess.run(
        [sys.executable, "-c", f"import mock_data as m; print({expr})"],
        capture_output=True, text=True, cwd=".", check=True,
    )
    return out.stdout.strip()


def test_confidence_scores_identical_across_processes():
    expr = "[round(v['confidence_score'],3) for v in m.get_score_data(1).values()]"
    runs = {_in_fresh_process(expr) for _ in range(3)}
    assert len(runs) == 1, f"confidence varies between processes: {runs}"


def test_trend_series_identical_across_processes():
    runs = {_in_fresh_process("m.get_trend_data(2,'Recovery')") for _ in range(3)}
    assert len(runs) == 1, f"trend varies between processes: {runs}"


def test_biomarker_series_identical_across_processes():
    runs = {_in_fresh_process("m.get_biomarker_series(3,'hrv_sdnn')") for _ in range(3)}
    assert len(runs) == 1, f"series varies between processes: {runs}"


# --- series contract --------------------------------------------------------

def test_series_never_longer_than_days_worn():
    for pid in (1, 2, 3):
        worn = m.get_days_collected(pid)
        for key in m.BIOMARKER_META:
            series = m.get_biomarker_series(pid, key, days=365)
            assert len(series) <= worn


def test_last_reading_is_the_personas_current_value():
    for pid in (1, 2, 3):
        patient = m.get_persona(pid)
        for key, meta in m.BIOMARKER_META.items():
            series = m.get_biomarker_series(pid, key)
            expected = round(float(patient[meta["field"]]), meta["precision"])
            assert series[-1] == expected


def test_today_is_excluded_from_its_own_baseline():
    series = m.get_biomarker_series(1, "resting_hr")
    baseline = bl.compute_baseline(series)
    assert baseline.n == len(series) - 1


def test_every_signal_resolves_with_a_baseline():
    for pid in (1, 2, 3):
        for key in m.BIOMARKER_META:
            marker = m.get_biomarker(pid, key)
            assert marker["baseline"] is not None, f"{pid}/{key} has no baseline"
            assert marker["deviation"] is not None


def test_trend_series_ends_on_the_score_shown_on_the_card():
    """The chart's last point and the number above it must be the same day."""
    for pid in (1, 2, 3):
        scores = m.get_score_data(pid)
        for label in m.COMPOSITE_SCORES:
            assert m.get_trend_data(pid, label)[-1] == float(scores[label]["value"])


# --- alert gating -----------------------------------------------------------

def test_alerts_only_fire_on_statistically_real_trends():
    for pid in (1, 2, 3):
        for alert in m.get_alerts(pid):
            if "system" in alert["title"]:
                continue  # body system labels are categorical, not fitted
            label = alert["title"].rsplit(" trending", 1)[0]
            series = m.get_trend_data(pid, label)
            direction = bl.trend_direction(series, baseline=bl.compute_baseline(series))
            assert direction in ("rising", "falling")


def test_favourable_trends_never_raise_an_alert():
    for pid in (1, 2, 3):
        titles = [a["title"] for a in m.get_alerts(pid)]
        for label in m.COMPOSITE_SCORES:
            series = m.get_trend_data(pid, label)
            direction = bl.trend_direction(series, baseline=bl.compute_baseline(series))
            good = m.HIGHER_IS_BETTER[label]
            favourable = (good and direction == "rising") or (not good and direction == "falling")
            if favourable:
                assert not any(t.startswith(label) for t in titles), \
                    f"{label} moved favourably for patient {pid} but raised an alert"
