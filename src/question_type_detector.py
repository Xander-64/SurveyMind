from __future__ import annotations

import re

import pandas as pd
from pandas.api.types import is_numeric_dtype

from src.preprocessing import is_metadata_column


QUESTION_TYPE_NUMERIC = "numeric question"
QUESTION_TYPE_SCALE = "scale question"
QUESTION_TYPE_SINGLE = "single-choice question"
QUESTION_TYPE_MULTIPLE = "multiple-choice question"
QUESTION_TYPE_OPEN = "open-ended text question"
# Entirely blank columns — kept as a visible type ("空白列") for the UI.
QUESTION_TYPE_EMPTY = "empty question"
# Metadata / unusable columns — detect_question_types drops these entirely.
QUESTION_TYPE_UNKNOWN = "unknown"

# Common survey exports often separate multi-select options with punctuation,
# line breaks, or locale-specific delimiters.
MULTI_CHOICE_PATTERN = re.compile(r"[,;；，、/\|\s]+")
EXPLICIT_MULTI_CHOICE_PATTERN = re.compile(r"[,;；，、/\|\n]")
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

# Column names that strongly suggest a rating / Likert scale. Used to relax the
# integer-ratio requirement so decimal scores (e.g. 1.1, 2.7) on a 1-5 range are
# still recognised as scale questions rather than free numeric measurements.
SCALE_NAME_KEYWORDS = (
    "satisfaction",
    "score",
    "rating",
    "scale",
    "likert",
    "agree",
    "满意",
    "评分",
    "打分",
    "量表",
    "评价",
    "认可",
)


def _column_name_suggests_scale(series: pd.Series) -> bool:
    """Return True when the column name hints at a rating / Likert scale."""
    name = str(getattr(series, "name", "") or "").lower()
    return any(keyword in name for keyword in SCALE_NAME_KEYWORDS)


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
    """Identify technical metadata fields that should not drive survey analysis.

    Delegates to the shared token-based check so camelCase IDs ("UserID") are
    caught while ordinary words containing "id" ("valid", "paid") are not.
    """
    return bool(column_name) and is_metadata_column(str(column_name))


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

    min_value = numeric_values.min()
    max_value = numeric_values.max()
    in_scale_range = (
        1 <= min_value <= max_value <= 5
        or 1 <= min_value <= max_value <= 7
        or 1 <= min_value <= max_value <= 10
    )
    if not in_scale_range:
        return False

    name_suggests_scale = _column_name_suggests_scale(series)

    # Decimal rating columns (e.g. a 1-5 satisfaction score stored as 1.1, 2.7)
    # have a low integer ratio but are clearly scales. When the column name hints
    # at a rating we accept the wider 1-10 range without the integer requirement.
    if name_suggests_scale:
        return numeric_values.nunique() >= 3

    unique_count = numeric_values.nunique()
    if unique_count < 3 or unique_count > 10:
        return False

    # Likert-style items are usually stored as integers even if the column
    # dtype is float because of missing values or spreadsheet imports.
    integer_ratio = ((numeric_values - numeric_values.round()).abs() < 1e-9).mean()
    return integer_ratio >= 0.8


# Column names that lean towards a count rather than a rating. Used only to
# reduce noise in the scale_candidate hint below — never to decide a type.
COUNT_NAME_KEYWORDS = (
    "次数", "个数", "数量", "人数", "天数", "频次", "件数", "笔数",
    "count", "number", "times", "qty", "num_", "_num",
)


def _column_name_suggests_count(column_name: str | None) -> bool:
    name = str(column_name or "").lower()
    if any(keyword in name for keyword in COUNT_NAME_KEYWORDS):
        return True
    # A trailing 数 usually marks a count ("孩子数", "兄弟姐妹数"), except where
    # it closes a scoring word ("分数", "度数").
    return name.endswith("数") and not name.endswith(("分数", "度数"))


def is_scale_candidate(series: pd.Series, column_name: str | None = None) -> bool:
    """Flag a numeric column that *might* be a 0-10 style scale.

    This is a hint, never a verdict: the question type is untouched and the
    column stays a numeric question. The detector deliberately does not widen
    its own range check, because a count of children on 0-4 and a five-point
    item on 0-4 are identical in their values — see
    docs/detection-benchmark.md. Widening to catch the scale catches every
    count with it.

    The asymmetry is what settles it. A scale read as numeric only loses
    information; the mean stays a legitimate statistic. A count read as a scale
    propagates into the report and AI layers, where "3.2 purchases on average"
    is narrated as "an average rating of 3.2" — confidently wrong, and the
    hardest kind of error for a reader to catch.

    So the ambiguity is surfaced instead of guessed at, and the person who
    knows the answer decides. Same philosophy as the declared/detected
    authority chain: never silently side with one reading.
    """
    if _is_metadata_column(column_name):
        return False
    values = _coerce_numeric_like_values(series.dropna()).dropna()
    if values.empty:
        return False
    # Already recognised as a scale: nothing to offer.
    if _is_scale_question(series):
        return False
    if _column_name_suggests_count(column_name):
        return False

    integer_ratio = ((values - values.round()).abs() < 1e-9).mean()
    if integer_ratio < 0.99:
        return False

    minimum, maximum = values.min(), values.max()
    if not (0 <= minimum and maximum <= 10):
        return False

    # Contiguous: a rating scale uses its whole range, a sparse set of integers
    # is something else.
    observed = set(int(value) for value in values.unique())
    expected = set(range(int(minimum), int(maximum) + 1))
    if observed != expected:
        return False

    return len(expected) >= 3


def detect_scale_candidates(df: pd.DataFrame) -> dict[str, bool]:
    """Per-column scale hints for the whole frame. Types are unaffected."""
    return {
        column: is_scale_candidate(df[column], column_name=column)
        for column in df.columns
    }


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
        non_null = normalized.dropna()
        # Entirely blank columns keep the dedicated EMPTY type (visible in the
        # UI); mostly-missing columns are unusable and dropped as UNKNOWN.
        if non_null.empty:
            return QUESTION_TYPE_EMPTY
        if normalized.isna().mean() >= 0.8:
            return QUESTION_TYPE_UNKNOWN

        cleaned = non_null.astype(str).str.strip()
        cleaned = cleaned[cleaned != ""]
        if cleaned.empty:
            return QUESTION_TYPE_EMPTY

        sample_size = len(cleaned)
        unique_count = cleaned.nunique()
        unique_ratio = unique_count / max(sample_size, 1)
        average_length = cleaned.str.len().mean()
        has_delimiter = cleaned.apply(_has_multi_choice_delimiter)
        delimiter_count = int(has_delimiter.sum())
        delimiter_ratio = delimiter_count / max(sample_size, 1)

        # Multiple-choice detection comes first because survey exports often
        # store selected options together in one text cell.
        #
        # A genuine multi-select compresses cardinality: a few atomic options
        # combine into many full-value strings, so splitting on the delimiters
        # yields *fewer* distinct tokens than distinct full values. Ordinal
        # labels such as "1-2 times/week" do the opposite (splitting invents
        # fragments like "week"), so only treat the column as multiple-choice
        # when splitting does not increase the distinct count.
        if delimiter_count >= 2 and delimiter_ratio >= multi_choice_threshold:
            tokens = cleaned.str.split(MULTI_CHOICE_PATTERN).explode().str.strip()
            tokens = tokens[tokens != ""]
            if tokens.nunique() <= unique_count:
                return QUESTION_TYPE_MULTIPLE

        numeric_values = _coerce_numeric_like_values(cleaned)
        numeric_ratio = numeric_values.notna().mean()
        if numeric_ratio >= 0.6:
            # _is_scale_question owns all scale rules (1-5/1-7/1-10 range,
            # integer ratio, decimal ratings via column-name keywords, "5分").
            if _is_scale_question(series):
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
