"""Tests for metadata (identifier/timestamp) column detection in app.py."""
from __future__ import annotations

import warnings

import pytest

# Importing app.py runs Streamlit module-level code; suppress the "no runtime"
# warnings so the import stays quiet during testing.
warnings.filterwarnings("ignore")
app = pytest.importorskip("app")


@pytest.mark.parametrize(
    "name",
    ["UserID", "StudentID", "RespondentID", "student_id", "Respondent ID", "id", "样本编号", "提交时间"],
)
def test_identifier_columns_are_metadata(name):
    assert app.is_metadata_column(name) is True


@pytest.mark.parametrize("name", ["satisfaction_score", "gender", "valid", "monthly_allowance"])
def test_survey_columns_are_not_metadata(name):
    assert app.is_metadata_column(name) is False
