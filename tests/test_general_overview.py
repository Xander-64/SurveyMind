import pandas as pd
import pytest

from src.field_semantics import detect_field_semantics
from src.general_overview import (
    build_overview_findings,
    generate_general_overview,
    iqr_outlier_count,
)


@pytest.fixture()
def sample_df():
    base_x = [10, 12, 11, 15, 18, 20, 22, 25, 24, 30]
    x = base_x * 4
    y = [2 * value + 1 for value in x]
    z = ([10, 11, 9, 12, 10, 11, 12, 9, 10, 11] * 2) + ([50, 52, 49, 51, 50, 53, 48, 52, 51, 50] * 2)
    return pd.DataFrame(
        {
            "user_id": [f"U{i:03d}" for i in range(40)],
            "event_date": [f"2024-{month:02d}-10" for month in range(1, 9)] * 5,
            "group": ["A"] * 20 + ["B"] * 20,
            "x": x,
            "y": y,
            "z": z,
        }
    )


@pytest.fixture()
def overview(sample_df):
    semantics = detect_field_semantics(sample_df)
    return generate_general_overview(sample_df, semantics)


def test_numeric_summary_matches_pandas(sample_df, overview):
    summary = overview["numeric_summary"]
    assert round(float(sample_df["x"].mean()), 2) == summary.loc["x", "mean"]
    assert round(float(sample_df["x"].median()), 2) == summary.loc["x", "median"]
    assert round(float(sample_df["x"].std()), 2) == summary.loc["x", "std"]


def test_strong_correlation_detected(overview):
    correlations = overview["correlations"]
    assert not correlations.empty
    pair = correlations[
        ((correlations["field_1"] == "x") & (correlations["field_2"] == "y"))
        | ((correlations["field_1"] == "y") & (correlations["field_2"] == "x"))
    ]
    assert not pair.empty
    assert abs(float(pair.iloc[0]["pearson_r"])) >= 0.99


def test_group_difference_detected_with_p_value(overview):
    differences = overview["group_differences"]
    assert not differences.empty
    top = differences[differences["metric_field"] == "z"].iloc[0]
    assert top["top_group"] == "B"
    assert top["p_value"] is not None and top["p_value"] < 0.05


def test_id_candidates_and_datetime_summary(overview):
    assert "user_id" in overview["id_candidates"]
    datetime_summary = overview["datetime_summary"]
    assert not datetime_summary.empty
    assert datetime_summary.iloc[0]["column_name"] == "event_date"
    trend = overview["time_trends"]["event_date"]
    assert int(trend["count"].sum()) == 40


def test_duplicate_rows_counted(sample_df):
    duplicated = pd.concat([sample_df, sample_df.head(2)], ignore_index=True)
    semantics = detect_field_semantics(duplicated)
    overview = generate_general_overview(duplicated, semantics)
    assert overview["quality"]["duplicate_rows"] == 2


def test_iqr_outlier_count_flags_extremes():
    series = pd.Series([10, 11, 12, 10, 11, 12, 10, 11, 12, 500])
    assert iqr_outlier_count(series) >= 1


def test_overview_findings_bilingual(sample_df, overview):
    for language in ("en", "zh-CN"):
        findings = build_overview_findings(sample_df, overview, language)
        assert findings
        assert any("40" in finding for finding in findings)
