from __future__ import annotations

import re

import pandas as pd
from pandas.api.types import is_numeric_dtype


QUESTION_TYPE_NUMERIC = "numeric question"
QUESTION_TYPE_SCALE = "scale question"
QUESTION_TYPE_SINGLE = "single-choice question"
QUESTION_TYPE_MULTIPLE = "multiple-choice question"
QUESTION_TYPE_OPEN = "open-ended text question"

# Common survey exports often separate multi-select options with punctuation,
# line breaks, or locale-specific delimiters.
MULTI_CHOICE_PATTERN = re.compile(r"[,;；，、/\|\n]")


def get_question_type_options() -> list[str]:
    """Return the supported question type labels for UI controls."""
    return [
        QUESTION_TYPE_NUMERIC,
        QUESTION_TYPE_SCALE,
        QUESTION_TYPE_SINGLE,
        QUESTION_TYPE_MULTIPLE,
        QUESTION_TYPE_OPEN,
    ]


def _has_multi_choice_delimiter(value: str) -> bool:
    """Check whether one response contains a likely multi-select separator."""
    return bool(MULTI_CHOICE_PATTERN.search(value))


def _is_scale_question(series: pd.Series) -> bool:
    """Identify Likert-style numeric items such as 1-5, 1-7, or 1-10 scales."""
    numeric_values = pd.to_numeric(series.dropna(), errors="coerce").dropna()
    if numeric_values.empty:
        return False

    unique_count = numeric_values.nunique()
    if unique_count < 3 or unique_count > 10:
        return False

    # Likert-style items are usually stored as integers even if the column
    # dtype is float because of missing values or spreadsheet imports.
    integer_ratio = ((numeric_values - numeric_values.round()).abs() < 1e-9).mean()
    if integer_ratio < 0.8:
        return False

    min_value = numeric_values.min()
    max_value = numeric_values.max()
    return (
        1 <= min_value <= max_value <= 5
        or 1 <= min_value <= max_value <= 7
        or 1 <= min_value <= max_value <= 10
    )


def detect_question_type(series: pd.Series, multi_choice_threshold: float = 0.15) -> str:
    """Infer a questionnaire-style column type using lightweight rules."""
    if is_numeric_dtype(series):
        if _is_scale_question(series):
            return QUESTION_TYPE_SCALE
        return QUESTION_TYPE_NUMERIC

    non_null = series.dropna()
    if non_null.empty:
        return QUESTION_TYPE_SINGLE

    cleaned = non_null.astype(str).str.strip()
    sample_size = len(cleaned)
    unique_count = cleaned.nunique()
    unique_ratio = unique_count / max(sample_size, 1)
    average_length = cleaned.str.len().mean()
    delimiter_ratio = cleaned.apply(_has_multi_choice_delimiter).mean()

    # Multiple-choice detection is intentionally checked before the
    # single-choice heuristics because many real survey exports store
    # multi-select answers as one delimited string per respondent.
    if delimiter_ratio >= multi_choice_threshold:
        return QUESTION_TYPE_MULTIPLE

    low_cardinality_limit = min(15, max(6, int(sample_size * 0.1)))
    if unique_count <= low_cardinality_limit and average_length < 35:
        return QUESTION_TYPE_SINGLE

    if (average_length >= 40 and unique_count >= 8) or (average_length >= 25 and unique_ratio >= 0.6):
        return QUESTION_TYPE_OPEN

    if unique_count <= 25:
        return QUESTION_TYPE_SINGLE

    return QUESTION_TYPE_OPEN


def detect_question_types(
    df: pd.DataFrame,
    multi_choice_threshold: float = 0.15,
) -> dict[str, str]:
    """Detect question types for all columns in a dataset."""
    return {
        column: detect_question_type(df[column], multi_choice_threshold=multi_choice_threshold)
        for column in df.columns
    }


def question_types_to_frame(
    detected_question_types: dict[str, str],
    active_question_types: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Convert question types into a display-friendly DataFrame."""
    frame_data = {
        "column_name": list(detected_question_types.keys()),
        "detected_type": list(detected_question_types.values()),
    }
    if active_question_types is not None:
        frame_data["active_type"] = [active_question_types[column] for column in detected_question_types]

    return pd.DataFrame(frame_data)
