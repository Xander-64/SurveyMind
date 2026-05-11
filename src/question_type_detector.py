from __future__ import annotations

import re

import pandas as pd
from pandas.api.types import is_numeric_dtype


QUESTION_TYPE_NUMERIC = "numeric question"
QUESTION_TYPE_SCALE = "scale question"
QUESTION_TYPE_SINGLE = "single-choice question"
QUESTION_TYPE_MULTIPLE = "multiple-choice question"
QUESTION_TYPE_OPEN = "open-ended text question"
QUESTION_TYPE_UNKNOWN = "unknown"

# Common survey exports often separate multi-select options with punctuation,
# line breaks, or locale-specific delimiters.
MULTI_CHOICE_PATTERN = re.compile(r"[,;；，、/\|\s]+")
EXPLICIT_MULTI_CHOICE_PATTERN = re.compile(r"[,;；，、/\|\n]")
METADATA_COLUMN_PATTERN = re.compile(r"(时间|编号|id)", re.IGNORECASE)
MULTI_CHOICE_DELIMITER = ";"


def normalize_multi_choice_response(value: object) -> str:
    """Normalize messy multi-choice separators into a single delimiter."""
    if value is None:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass

    text = str(value).strip()
    if not text:
        return ""

    parts = [part.strip() for part in MULTI_CHOICE_PATTERN.split(text)]
    return MULTI_CHOICE_DELIMITER.join(part for part in parts if part)


def split_multi_choice_response(value: object) -> list[str]:
    """Split one multi-choice response into clean option labels."""
    normalized = normalize_multi_choice_response(value)
    if not normalized:
        return []
    return [part.strip() for part in normalized.split(MULTI_CHOICE_DELIMITER) if part.strip()]


def get_question_type_options() -> list[str]:
    """Return the supported question type labels for UI controls."""
    return [
        QUESTION_TYPE_NUMERIC,
        QUESTION_TYPE_SCALE,
        QUESTION_TYPE_SINGLE,
        QUESTION_TYPE_MULTIPLE,
        QUESTION_TYPE_OPEN,
        QUESTION_TYPE_UNKNOWN,
    ]


def _has_multi_choice_delimiter(value: str) -> bool:
    """Check whether one response contains a likely multi-select separator."""
    text = value.strip()
    if not text:
        return False
    if EXPLICIT_MULTI_CHOICE_PATTERN.search(text):
        return True

    parts = [part for part in text.split() if part]
    return 2 <= len(parts) <= 6 and len(text) <= 30 and all(len(part) <= 20 for part in parts)


def _is_metadata_column(column_name: str | None) -> bool:
    """Identify technical metadata fields that should not drive survey analysis."""
    return bool(column_name and METADATA_COLUMN_PATTERN.search(str(column_name)))


def _coerce_numeric_like_values(series: pd.Series) -> pd.Series:
    """Coerce plain numeric values and score text like "5分" to numbers."""
    numeric_values = pd.to_numeric(series, errors="coerce")
    extracted_scores = series.astype("string").str.extract(r"^\s*([-+]?\d+(?:\.\d+)?)\s*分?\s*$", expand=False)
    extracted_numeric_values = pd.to_numeric(extracted_scores, errors="coerce")
    return numeric_values.fillna(extracted_numeric_values)


def _is_scale_question(series: pd.Series) -> bool:
    """Identify Likert-style numeric items such as 1-5, 1-7, or 1-10 scales."""
    numeric_values = _coerce_numeric_like_values(series.dropna()).dropna()
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


def detect_question_type(
    series: pd.Series,
    multi_choice_threshold: float = 0.15,
    column_name: str | None = None,
) -> str:
    """Infer a questionnaire-style column type using lightweight rules."""
    try:
        if _is_metadata_column(column_name):
            return QUESTION_TYPE_UNKNOWN

        normalized = series.replace(r"^\s*$", pd.NA, regex=True)
        missing_ratio = normalized.isna().mean()
        if missing_ratio >= 0.8:
            return QUESTION_TYPE_UNKNOWN

        non_null = normalized.dropna()
        if non_null.empty:
            return QUESTION_TYPE_UNKNOWN

        cleaned = non_null.astype(str).str.strip()
        cleaned = cleaned[cleaned != ""]
        if cleaned.empty:
            return QUESTION_TYPE_UNKNOWN

        sample_size = len(cleaned)
        unique_count = cleaned.nunique()
        unique_ratio = unique_count / max(sample_size, 1)
        average_length = cleaned.str.len().mean()
        has_delimiter = cleaned.apply(_has_multi_choice_delimiter)
        delimiter_count = int(has_delimiter.sum())
        delimiter_ratio = delimiter_count / max(sample_size, 1)

        # Multiple-choice detection comes first because survey exports often
        # store selected options together in one text cell.
        if delimiter_count >= 2 and delimiter_ratio >= multi_choice_threshold:
            return QUESTION_TYPE_MULTIPLE

        numeric_values = _coerce_numeric_like_values(cleaned)
        numeric_ratio = numeric_values.notna().mean()
        if numeric_ratio >= 0.6:
            numeric_cleaned = numeric_values.dropna()
            unique_numeric_count = numeric_cleaned.nunique()
            integer_ratio = ((numeric_cleaned - numeric_cleaned.round()).abs() < 1e-9).mean()
            if unique_numeric_count <= 10 and integer_ratio >= 0.8:
                return QUESTION_TYPE_SCALE
            return QUESTION_TYPE_NUMERIC

        if is_numeric_dtype(series):
            if _is_scale_question(series):
                return QUESTION_TYPE_SCALE
            return QUESTION_TYPE_NUMERIC

        if (average_length >= 40 and unique_count >= 8) or (average_length >= 25 and unique_ratio >= 0.6):
            return QUESTION_TYPE_OPEN

        low_cardinality_limit = min(15, max(6, int(sample_size * 0.1)))
        if unique_count <= low_cardinality_limit and average_length < 35:
            return QUESTION_TYPE_SINGLE

        if unique_count <= 25:
            return QUESTION_TYPE_SINGLE

        return QUESTION_TYPE_OPEN
    except Exception:
        return QUESTION_TYPE_UNKNOWN


def detect_question_types(
    df: pd.DataFrame,
    multi_choice_threshold: float = 0.15,
) -> dict[str, str]:
    """Detect question types for analyzable columns in a dataset."""
    detected_types: dict[str, str] = {}
    for column in df.columns:
        question_type = detect_question_type(
            df[column],
            multi_choice_threshold=multi_choice_threshold,
            column_name=column,
        )
        if question_type != QUESTION_TYPE_UNKNOWN:
            detected_types[column] = question_type
    return detected_types


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
