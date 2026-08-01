"""Mode dispatch: pick the report structure for the active dataset mode."""
from __future__ import annotations

from typing import Any

import pandas as pd

from src.dataset_mode import DATASET_MODE_MIXED, DATASET_MODE_SURVEY
from src.field_semantics import FieldProfile
from src.report.survey import generate_markdown_report
from src.report.general import generate_general_report
from src.report.mixed import generate_mixed_report


def generate_report(
    df: pd.DataFrame,
    mode: str,
    language: str = "en",
    question_types: dict[str, str] | None = None,
    descriptive_results: dict[str, Any] | None = None,
    cross_analysis_result: dict[str, Any] | None = None,
    semantics: dict[str, FieldProfile] | None = None,
    overview: dict[str, Any] | None = None,
) -> str:
    """Dispatch to the report structure that matches the dataset mode."""
    if mode == DATASET_MODE_SURVEY and question_types is not None and descriptive_results is not None:
        return generate_markdown_report(df, question_types, descriptive_results, cross_analysis_result, language)
    if mode == DATASET_MODE_MIXED and question_types is not None and descriptive_results is not None:
        return generate_mixed_report(
            df,
            semantics or {},
            overview or {},
            question_types,
            descriptive_results,
            cross_analysis_result,
            language,
        )
    return generate_general_report(df, semantics or {}, overview or {}, language)
