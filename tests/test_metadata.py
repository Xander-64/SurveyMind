"""Tests for metadata (identifier/timestamp) column-name detection.

is_metadata_column lives in src/preprocessing and powers the FastAPI backend's
strict cleaning. The Streamlit platform no longer drops these columns — it
assigns identifier/datetime field roles instead (see src/field_semantics.py) —
but the name-based detector itself must keep working for the API layer.
"""
from __future__ import annotations

import pytest

from src.preprocessing import is_metadata_column


@pytest.mark.parametrize(
    "name",
    ["UserID", "StudentID", "RespondentID", "student_id", "Respondent ID", "id", "样本编号", "提交时间"],
)
def test_identifier_columns_are_metadata(name):
    assert is_metadata_column(name) is True


@pytest.mark.parametrize("name", ["satisfaction_score", "gender", "valid", "monthly_allowance"])
def test_survey_columns_are_not_metadata(name):
    assert is_metadata_column(name) is False
