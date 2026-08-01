from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field

import pandas as pd
from pandas.api.types import is_bool_dtype, is_datetime64_any_dtype, is_numeric_dtype


FIELD_ROLE_NUMERIC = "numeric_metric"
FIELD_ROLE_CATEGORICAL = "categorical_dimension"
FIELD_ROLE_DATETIME = "datetime"
FIELD_ROLE_IDENTIFIER = "identifier"
FIELD_ROLE_BOOLEAN = "boolean"
FIELD_ROLE_FREE_TEXT = "free_text"
FIELD_ROLE_MULTI_VALUE = "multi_value"
FIELD_ROLE_EMPTY = "empty_or_constant"


def get_field_role_options() -> list[str]:
    """Return the supported generic field roles for UI controls."""
    return [
        FIELD_ROLE_NUMERIC,
        FIELD_ROLE_CATEGORICAL,
        FIELD_ROLE_DATETIME,
        FIELD_ROLE_IDENTIFIER,
        FIELD_ROLE_BOOLEAN,
        FIELD_ROLE_FREE_TEXT,
        FIELD_ROLE_MULTI_VALUE,
        FIELD_ROLE_EMPTY,
    ]


# Same delimiter family the survey pipeline splits on, so multi-value fields
# stay consistent between general and survey modes.
MULTI_VALUE_PATTERN = re.compile(r"[,;；，、/\|\n]")

ID_NAME_PATTERN = re.compile(r"(?<![a-z])id(?![a-z])", re.IGNORECASE)
ID_NAME_KEYWORDS = ("编号", "序号", "工号", "学号", "单号", "号码", "uuid")

DATETIME_NAME_KEYWORDS = (
    "date",
    "time",
    "timestamp",
    "created",
    "updated",
    "日期",
    "时间",
    "年月",
    "月份",
)

BOOLEAN_TOKENS = {
    "true",
    "false",
    "yes",
    "no",
    "y",
    "n",
    "t",
    "f",
    "0",
    "1",
    "0.0",
    "1.0",
    "是",
    "否",
    "有",
    "无",
}

SENTENCE_PUNCTUATION_PATTERN = re.compile(r"[。！？!?.]")


@dataclass
class FieldProfile:
    column: str
    role: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    non_null_count: int = 0
    unique_count: int = 0


def _has_id_name_hint(column_name: str) -> bool:
    lowered = column_name.strip().lower()
    return bool(ID_NAME_PATTERN.search(lowered)) or any(keyword in lowered for keyword in ID_NAME_KEYWORDS)


def _has_datetime_name_hint(column_name: str) -> bool:
    lowered = column_name.strip().lower()
    return any(keyword in lowered for keyword in DATETIME_NAME_KEYWORDS)


def _datetime_parse_ratio(cleaned: pd.Series) -> float:
    sample = cleaned.head(500)
    if sample.empty:
        return 0.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = pd.to_datetime(sample, errors="coerce")
    return float(parsed.notna().mean())


def _looks_like_datetime(cleaned: pd.Series, column_name: str) -> bool:
    if cleaned.empty:
        return False
    median_length = float(cleaned.str.len().median())
    name_hint = _has_datetime_name_hint(column_name)
    # Short numeric-looking strings such as "1990" parse as dates but are
    # almost never real datetime columns unless the name says so.
    if median_length < 6 and not name_hint:
        return False
    return _datetime_parse_ratio(cleaned) >= 0.9


def _is_boolean_values(cleaned: pd.Series) -> bool:
    unique_values = {str(value).strip().lower() for value in cleaned.unique()}
    return 1 <= len(unique_values) <= 2 and unique_values <= BOOLEAN_TOKENS


def _identifier_evidence(series: pd.Series, cleaned: pd.Series, column_name: str) -> list[str]:
    non_null = len(cleaned)
    if non_null == 0:
        return []
    unique_ratio = cleaned.nunique() / non_null
    name_hint = _has_id_name_hint(column_name)

    if name_hint and unique_ratio >= 0.9:
        return [f"name suggests id, unique_ratio={unique_ratio:.2f}"]

    if unique_ratio < 0.98:
        return []

    if is_numeric_dtype(series):
        numeric_values = pd.to_numeric(cleaned, errors="coerce").dropna()
        if numeric_values.empty:
            return []
        is_integer = bool(((numeric_values - numeric_values.round()).abs() < 1e-9).all())
        if not is_integer:
            return []
        span = float(numeric_values.max() - numeric_values.min()) + 1
        is_sequential = span <= non_null * 1.2
        if numeric_values.is_monotonic_increasing or is_sequential:
            return [f"unique sequential integers, unique_ratio={unique_ratio:.2f}"]
        return []

    average_length = float(cleaned.str.len().mean())
    space_free_ratio = float((~cleaned.str.contains(r"\s")).mean())
    if average_length <= 32 and space_free_ratio >= 0.9:
        return [f"unique short codes, unique_ratio={unique_ratio:.2f}"]
    return []


def _multi_value_evidence(cleaned: pd.Series) -> list[str]:
    """Require real evidence before treating text as a multi-value field.

    A delimiter alone is not enough: sentences and addresses contain commas,
    and categories like "1-2 times/week" contain slashes. Genuine multi-select
    data splits into a small vocabulary of short tokens that repeat across
    rows, and produces more raw combinations than distinct tokens.
    """
    if cleaned.empty:
        return []

    delimiter_ratio = float(cleaned.str.contains(MULTI_VALUE_PATTERN).mean())
    if delimiter_ratio < 0.1:
        return []

    tokens = cleaned.str.split(MULTI_VALUE_PATTERN).explode().astype(str).str.strip()
    tokens = tokens[tokens != ""]
    if tokens.empty:
        return []

    token_vocabulary = int(tokens.nunique())
    average_token_length = float(tokens.str.len().mean())
    token_reuse = len(tokens) / max(token_vocabulary, 1)
    raw_combinations = int(cleaned.nunique())
    row_count = len(cleaned)
    vocabulary_limit = max(3, min(30, row_count // 2))

    if (
        token_vocabulary <= vocabulary_limit
        and average_token_length <= 25
        and token_reuse >= 2
        and raw_combinations > token_vocabulary
    ):
        return [
            f"delimiter_ratio={delimiter_ratio:.2f}",
            f"token_vocabulary={token_vocabulary}",
            f"token_reuse={token_reuse:.1f}",
            f"raw_combinations={raw_combinations}",
        ]
    return []


def _looks_like_free_text(cleaned: pd.Series) -> bool:
    if cleaned.empty:
        return False
    average_length = float(cleaned.str.len().mean())
    unique_ratio = cleaned.nunique() / len(cleaned)
    if average_length >= 30:
        return True
    if unique_ratio >= 0.6 and average_length >= 15:
        return True
    sentence_ratio = float(cleaned.str.contains(SENTENCE_PUNCTUATION_PATTERN).mean())
    if sentence_ratio >= 0.3 and average_length >= 20:
        return True
    if cleaned.nunique() > 50 and unique_ratio > 0.5:
        return True
    return False


def detect_field_profile(series: pd.Series, column_name: str) -> FieldProfile:
    """Classify one column into a generic field role with evidence."""
    non_null = series.dropna()
    non_null_count = int(len(non_null))
    unique_count = int(non_null.nunique())

    def profile(role: str, confidence: float, evidence: list[str]) -> FieldProfile:
        return FieldProfile(
            column=column_name,
            role=role,
            confidence=confidence,
            evidence=evidence,
            non_null_count=non_null_count,
            unique_count=unique_count,
        )

    if non_null_count == 0 or unique_count <= 1:
        return profile(FIELD_ROLE_EMPTY, 0.95, ["all missing" if non_null_count == 0 else "constant value"])

    if is_datetime64_any_dtype(series):
        return profile(FIELD_ROLE_DATETIME, 0.95, ["datetime dtype"])

    if is_bool_dtype(series):
        return profile(FIELD_ROLE_BOOLEAN, 0.95, ["boolean dtype"])

    cleaned = non_null.astype(str).str.strip()
    cleaned = cleaned[cleaned != ""]
    if cleaned.empty:
        return profile(FIELD_ROLE_EMPTY, 0.9, ["only blank strings"])

    if not is_numeric_dtype(series) and _looks_like_datetime(cleaned, column_name):
        return profile(FIELD_ROLE_DATETIME, 0.85, ["values parse as dates"])

    if _is_boolean_values(cleaned):
        return profile(FIELD_ROLE_BOOLEAN, 0.85, ["two-value yes/no style values"])

    identifier_evidence = _identifier_evidence(series, cleaned, column_name)
    if identifier_evidence:
        return profile(FIELD_ROLE_IDENTIFIER, 0.85, identifier_evidence)

    if is_numeric_dtype(series):
        return profile(FIELD_ROLE_NUMERIC, 0.9, ["numeric dtype"])

    multi_value_evidence = _multi_value_evidence(cleaned)
    if multi_value_evidence:
        return profile(FIELD_ROLE_MULTI_VALUE, 0.8, multi_value_evidence)

    if _looks_like_free_text(cleaned):
        return profile(FIELD_ROLE_FREE_TEXT, 0.75, ["long or highly unique text"])

    return profile(
        FIELD_ROLE_CATEGORICAL,
        0.8,
        [f"unique_count={unique_count} over {non_null_count} rows"],
    )


def detect_field_semantics(df: pd.DataFrame) -> dict[str, FieldProfile]:
    """Detect generic field roles for every column in a dataset."""
    return {str(column): detect_field_profile(df[column], str(column)) for column in df.columns}


def field_semantics_to_frame(
    semantics: dict[str, FieldProfile],
    active_roles: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Convert field profiles into a display-friendly DataFrame."""
    frame_data = {
        "column_name": [profile.column for profile in semantics.values()],
        "detected_role": [profile.role for profile in semantics.values()],
        "evidence": ["; ".join(profile.evidence) for profile in semantics.values()],
    }
    if active_roles is not None:
        frame_data["active_role"] = [active_roles.get(column, profile.role) for column, profile in semantics.items()]
    return pd.DataFrame(frame_data)


def apply_role_overrides(
    semantics: dict[str, FieldProfile],
    overrides: dict[str, str],
) -> dict[str, FieldProfile]:
    """Return a copy of the semantics with user-selected roles applied."""
    updated: dict[str, FieldProfile] = {}
    for column, profile in semantics.items():
        override_role = overrides.get(column)
        if override_role and override_role != profile.role:
            updated[column] = FieldProfile(
                column=profile.column,
                role=override_role,
                confidence=1.0,
                evidence=["manual override"],
                non_null_count=profile.non_null_count,
                unique_count=profile.unique_count,
            )
        else:
            updated[column] = profile
    return updated
