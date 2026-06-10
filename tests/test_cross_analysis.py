"""Regression tests for cross-analysis (scale columns stored as text)."""
from __future__ import annotations

import pandas as pd

from src.cross_analysis import analyze_cross_relationship
from src.question_type_detector import QUESTION_TYPE_SCALE, QUESTION_TYPE_SINGLE


def test_scale_column_with_text_suffix_does_not_crash():
    # Real surveys often store Likert answers as "5分" / "4 points".
    # This used to raise TypeError in groupby().agg(); it must now work.
    df = pd.DataFrame(
        {
            "group": ["A", "A", "B", "B"],
            "score": ["5分", "4分", "3分", "5分"],
        }
    )
    question_types = {"group": QUESTION_TYPE_SINGLE, "score": QUESTION_TYPE_SCALE}

    result = analyze_cross_relationship(df, "group", "score", question_types, "en")

    assert result["analysis_type"] == "numeric_by_group"
    table = result["summary_table"]
    # Group A mean = (5+4)/2 = 4.5, Group B mean = (3+5)/2 = 4.0
    assert round(table.loc["A", "mean"], 1) == 4.5
    assert round(table.loc["B", "mean"], 1) == 4.0


def test_numeric_scale_column_still_works():
    df = pd.DataFrame(
        {
            "group": ["A", "A", "B", "B"],
            "score": [5, 4, 3, 5],
        }
    )
    question_types = {"group": QUESTION_TYPE_SINGLE, "score": QUESTION_TYPE_SCALE}
    result = analyze_cross_relationship(df, "group", "score", question_types, "en")
    assert result["analysis_type"] == "numeric_by_group"
    assert round(result["summary_table"].loc["A", "mean"], 1) == 4.5
