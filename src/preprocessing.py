"""Shared input-cleaning logic used by both the Streamlit app and the API layer.

Moved verbatim from app.py so that every entry point (Streamlit UI, FastAPI
backend, tests) cleans uploaded data with exactly the same rules.
"""
from __future__ import annotations

import re

import pandas as pd


METADATA_COLUMN_KEYWORDS = ("时间", "编号")
# Split on word separators and camelCase boundaries so that "UserID",
# "student_id", "Respondent ID" all normalize to a token list containing "id".
_CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z])(?=[A-Z])")
_WORD_SEPARATORS = re.compile(r"[\s_\-]+")


def _name_tokens(column_name: str) -> list[str]:
    spaced = _CAMEL_CASE_BOUNDARY.sub(" ", column_name.strip())
    return [token for token in _WORD_SEPARATORS.split(spaced.lower()) if token]


def is_metadata_column(column_name: str) -> bool:
    if any(keyword in column_name.strip() for keyword in METADATA_COLUMN_KEYWORDS):
        return True
    # Identifier columns (UserID, student_id, RespondentID, ...) carry no survey
    # signal and should be dropped before analysis.
    return "id" in _name_tokens(column_name)


def preprocess_input_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    cleaned_df = df.copy()
    cleaned_df.columns = [str(column).strip() if column is not None else "" for column in cleaned_df.columns]
    cleaned_df = cleaned_df.replace(r"^\s*$", pd.NA, regex=True)

    metadata_columns = [column for column in cleaned_df.columns if is_metadata_column(column)]
    if metadata_columns:
        cleaned_df = cleaned_df.drop(columns=metadata_columns, errors="ignore")

    cleaned_df = cleaned_df.dropna(axis=1, how="all")
    if cleaned_df.shape[1] == 0:
        raise ValueError("No usable survey columns remain after preprocessing.")

    return cleaned_df
