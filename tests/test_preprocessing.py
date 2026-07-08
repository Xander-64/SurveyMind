"""Equivalence tests: the API layer and the Streamlit app must clean data identically.

Both import preprocess_input_dataframe from src.preprocessing; these tests pin
that contract so the two entry points can never drift apart.
"""
from __future__ import annotations

import warnings

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.data_loader import load_uploaded_dataset
from src.preprocessing import is_metadata_column, preprocess_input_dataframe

warnings.filterwarnings("ignore")
app = pytest.importorskip("app")


def test_app_reuses_src_preprocessing_functions():
    # app.py must re-export the src/ implementations, not keep its own copies.
    assert app.preprocess_input_dataframe is preprocess_input_dataframe
    assert app.is_metadata_column is is_metadata_column


def test_streamlit_and_api_cleaning_produce_identical_frames():
    raw = pd.DataFrame(
        {
            "UserID": [1, 2, 3],
            "提交时间": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "gender": ["Male", "Female", " "],
            "score": [5, 4, 3],
            "blank": [None, None, None],
        }
    )

    via_api = preprocess_input_dataframe(raw)
    via_app = app.preprocess_input_dataframe(raw)

    assert_frame_equal(via_api, via_app)
    # Metadata and all-null columns dropped; whitespace-only value became NA.
    assert list(via_api.columns) == ["gender", "score"]
    assert pd.isna(via_api.loc[2, "gender"])


def test_tolerant_csv_fallback_lives_in_data_loader():
    # A ragged CSV (extra field on one row) must load via the python-engine
    # fallback instead of raising ParserError — for every entry point.
    ragged_csv = b"a,b\n1,2\n3,4,5\n6,7\n"
    df = load_uploaded_dataset(ragged_csv, "messy.csv")
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 2  # the bad row is skipped
