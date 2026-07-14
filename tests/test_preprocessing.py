"""Contract tests for the two cleaning entry points.

The FastAPI backend uses src/preprocessing.preprocess_input_dataframe, which
drops metadata (ID/timestamp) columns — that behavior powers the deployed
service and must not change.

The Streamlit platform intentionally diverges: it keeps every column and lets
field-semantics detection assign identifier/datetime roles, so general
datasets keep their primary keys and date columns for trend analysis.
"""
from __future__ import annotations

import warnings

import pandas as pd
import pytest

from src.data_loader import load_uploaded_dataset
from src.preprocessing import preprocess_input_dataframe

warnings.filterwarnings("ignore")
app = pytest.importorskip("app")


def _raw_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "UserID": [1, 2, 3],
            "提交时间": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "gender": ["Male", "Female", " "],
            "score": [5, 4, 3],
            "blank": [None, None, None],
        }
    )


def test_api_cleaning_still_drops_metadata_columns():
    # Deployed-backend behavior: metadata and all-null columns dropped,
    # whitespace-only values become NA.
    via_api = preprocess_input_dataframe(_raw_frame())
    assert list(via_api.columns) == ["gender", "score"]
    assert pd.isna(via_api.loc[2, "gender"])


def test_streamlit_keeps_metadata_columns_for_role_analysis():
    # Platform behavior: ID/timestamp columns survive cleaning so that
    # field-semantics detection can assign identifier/datetime roles.
    via_app = app.preprocess_input_dataframe(_raw_frame())
    assert list(via_app.columns) == ["UserID", "提交时间", "gender", "score"]
    assert pd.isna(via_app.loc[2, "gender"])

    from src.field_semantics import FIELD_ROLE_DATETIME, FIELD_ROLE_IDENTIFIER, detect_field_semantics

    semantics = detect_field_semantics(via_app)
    assert semantics["UserID"].role == FIELD_ROLE_IDENTIFIER
    assert semantics["提交时间"].role == FIELD_ROLE_DATETIME


def test_tolerant_csv_fallback_lives_in_data_loader():
    # A ragged CSV (extra field on one row) must load via the python-engine
    # fallback instead of raising ParserError — for every entry point.
    ragged_csv = b"a,b\n1,2\n3,4,5\n6,7\n"
    df = load_uploaded_dataset(ragged_csv, "messy.csv")
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 2  # the bad row is skipped
