from pathlib import Path

import pandas as pd
import pytest

from src.analysis_suggestions import find_target_candidates, generate_analysis_suggestions
from src.chart_recommender import (
    CHART_CATEGORICAL_BAR,
    CHART_CORRELATION_HEATMAP,
    CHART_GROUPED_BOX,
    CHART_NUMERIC_HISTOGRAM,
    CHART_TIME_TREND,
    recommend_charts,
)
from src.field_semantics import detect_field_semantics
from src.general_overview import generate_general_overview

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
VALID_CHART_KINDS = {
    CHART_TIME_TREND,
    CHART_CORRELATION_HEATMAP,
    CHART_GROUPED_BOX,
    CHART_NUMERIC_HISTOGRAM,
    CHART_CATEGORICAL_BAR,
}


@pytest.fixture(scope="module")
def general_setup():
    df = pd.read_csv(DATA_DIR / "sample_general.csv")
    semantics = detect_field_semantics(df)
    overview = generate_general_overview(df, semantics)
    return df, semantics, overview


def test_suggestions_are_dynamic_and_bounded(general_setup):
    df, semantics, overview = general_setup
    for language in ("en", "zh-CN"):
        suggestions = generate_analysis_suggestions(df, semantics, overview, language)
        assert 3 <= len(suggestions) <= 5
        joined = " ".join(suggestions)
        assert any(column in joined for column in df.columns), "suggestions must reference real fields"


def test_target_candidate_detected(general_setup):
    df, semantics, _ = general_setup
    assert "is_returned" in find_target_candidates(df, semantics)


def test_chart_recommendations_valid(general_setup):
    df, semantics, overview = general_setup
    specs = recommend_charts(df, semantics, overview)
    assert specs, "the general sample should produce chart recommendations"
    assert all(spec["kind"] in VALID_CHART_KINDS for spec in specs)
    kinds = {spec["kind"] for spec in specs}
    assert CHART_TIME_TREND in kinds, "a dataset with a date column should get a trend chart"
    time_spec = next(spec for spec in specs if spec["kind"] == CHART_TIME_TREND)
    assert time_spec["column"] == "order_date"
