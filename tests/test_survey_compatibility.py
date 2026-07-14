"""Regression tests: the original survey pipeline must keep working."""

from pathlib import Path

import pandas as pd
import pytest

from src.cross_analysis import analyze_cross_relationship
from src.descriptive_analysis import generate_descriptive_results
from src.question_type_detector import (
    QUESTION_TYPE_NUMERIC,
    QUESTION_TYPE_OPEN,
    QUESTION_TYPE_SINGLE,
    detect_question_types,
    get_question_type_options,
)
from src.report_generator import generate_markdown_report

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def survey_df():
    return pd.read_csv(DATA_DIR / "sample_survey.csv")


def test_legacy_detector_still_works(survey_df):
    question_types = detect_question_types(survey_df)
    valid_types = set(get_question_type_options())
    assert set(question_types.keys()) == set(survey_df.columns)
    assert set(question_types.values()) <= valid_types
    assert question_types["gender"] == QUESTION_TYPE_SINGLE
    assert question_types["monthly_allowance"] == QUESTION_TYPE_NUMERIC
    assert question_types["open_feedback"] == QUESTION_TYPE_OPEN


def test_descriptive_results_structure(survey_df):
    question_types = detect_question_types(survey_df)
    results = generate_descriptive_results(survey_df, question_types)
    for key in ("numeric_summary", "scale_summary", "categorical_summary", "sample_profile"):
        assert key in results


def test_cross_analysis_still_works(survey_df):
    question_types = detect_question_types(survey_df)
    result = analyze_cross_relationship(survey_df, "gender", "monthly_allowance", question_types, language="zh-CN")
    assert result["analysis_type"] == "numeric_by_group"
    assert not result["summary_table"].empty


def test_survey_markdown_report_generation(survey_df):
    question_types = detect_question_types(survey_df)
    results = generate_descriptive_results(survey_df, question_types)
    for language in ("en", "zh-CN"):
        report = generate_markdown_report(survey_df, question_types, results, None, language=language)
        assert isinstance(report, str) and len(report) > 200
