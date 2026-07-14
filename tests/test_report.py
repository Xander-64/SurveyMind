"""Tests for report robustness with degenerate data."""
from __future__ import annotations

import pandas as pd

from src.descriptive_analysis import generate_descriptive_results
from src.question_type_detector import (
    QUESTION_TYPE_EMPTY,
    QUESTION_TYPE_NUMERIC,
    detect_question_type,
)
from src.report_generator import _build_numeric_findings, generate_markdown_report


def test_all_null_column_is_empty_type():
    series = pd.Series([None, None, None, None])
    assert detect_question_type(series) == QUESTION_TYPE_EMPTY


def test_blank_string_column_is_empty_type():
    series = pd.Series(["", "  ", "\t", ""])
    assert detect_question_type(series) == QUESTION_TYPE_EMPTY


def test_constant_numeric_column_no_nan_std_finding():
    # Every column constant -> std is NaN. The report must not claim a
    # "widest spread" with std = nan.
    df = pd.DataFrame({"q1": [5, 5, 5, 5], "q2": [3, 3, 3, 3]})
    numeric_summary = df.describe().T.rename(columns={"50%": "median"})
    findings = _build_numeric_findings(df, numeric_summary, "en")
    joined = " ".join(findings).lower()
    assert "nan" not in joined
    assert "widest spread" not in joined  # no valid std -> skipped


def test_report_generation_with_degenerate_data_does_not_crash():
    df = pd.DataFrame({"score": [4, 4, 4], "blank": [None, None, None]})
    qt = {"score": QUESTION_TYPE_NUMERIC, "blank": QUESTION_TYPE_EMPTY}
    results = generate_descriptive_results(df, qt)
    report = generate_markdown_report(df, qt, results, None, "en")
    assert isinstance(report, str) and len(report) > 0
