from pathlib import Path

import pandas as pd
import pytest

from src.dataset_mode import (
    DATASET_MODE_GENERAL,
    DATASET_MODE_MIXED,
    DATASET_MODE_SURVEY,
    derive_analysis_types,
    derive_question_types,
    detect_dataset_mode,
)
from src.field_semantics import detect_field_semantics
from src.question_type_detector import (
    QUESTION_TYPE_MULTIPLE,
    QUESTION_TYPE_OPEN,
    QUESTION_TYPE_SCALE,
    QUESTION_TYPE_SINGLE,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def general_df():
    return pd.read_csv(DATA_DIR / "sample_general.csv")


@pytest.fixture(scope="module")
def survey_df():
    return pd.read_csv(DATA_DIR / "sample_survey.csv")


@pytest.fixture(scope="module")
def mixed_df():
    return pd.read_csv(DATA_DIR / "sample_mixed.csv")


def test_general_dataset_detected(general_df):
    semantics = detect_field_semantics(general_df)
    result = detect_dataset_mode(general_df, semantics)
    assert result.mode == DATASET_MODE_GENERAL


def test_survey_dataset_detected(survey_df):
    semantics = detect_field_semantics(survey_df)
    result = detect_dataset_mode(survey_df, semantics)
    assert result.mode == DATASET_MODE_SURVEY


def test_mixed_dataset_detected(mixed_df):
    semantics = detect_field_semantics(mixed_df)
    result = detect_dataset_mode(mixed_df, semantics)
    assert result.mode == DATASET_MODE_MIXED


def test_mode_detection_reports_signals(general_df):
    semantics = detect_field_semantics(general_df)
    result = detect_dataset_mode(general_df, semantics)
    assert result.signals, "mode detection should expose its evidence"


def test_derived_question_types_exclude_metadata_columns(general_df):
    semantics = detect_field_semantics(general_df)
    question_types = derive_question_types(general_df, semantics)
    assert "order_id" not in question_types
    assert "order_date" not in question_types


def test_general_analysis_types_never_use_scale(mixed_df):
    semantics = detect_field_semantics(mixed_df)
    analysis_types = derive_analysis_types(semantics)
    assert QUESTION_TYPE_SCALE not in analysis_types.values()


def test_survey_derivation_matches_survey_expectations(survey_df):
    semantics = detect_field_semantics(survey_df)
    question_types = derive_question_types(survey_df, semantics)
    assert question_types["gender"] == QUESTION_TYPE_SINGLE
    assert question_types["preferred_activities"] == QUESTION_TYPE_MULTIPLE
    assert question_types["open_feedback"] == QUESTION_TYPE_OPEN
    # Fixed misjudgment: slash-separated frequency categories are single-choice.
    assert question_types["fitness_frequency"] == QUESTION_TYPE_SINGLE


def test_mixed_derivation_keeps_scales(mixed_df):
    semantics = detect_field_semantics(mixed_df)
    question_types = derive_question_types(mixed_df, semantics)
    assert question_types["satisfaction_score"] == QUESTION_TYPE_SCALE
    assert question_types["used_features"] == QUESTION_TYPE_MULTIPLE
    assert "customer_id" not in question_types
