"""The mixed report: general table sections followed by survey-specific ones."""
from __future__ import annotations

from typing import Any

import pandas as pd

from src.field_semantics import FieldProfile
from src.i18n import t
from src.report.survey import (
    _build_group_comparison_text,
    _build_key_findings,
    _format_question_type_summary,
)
from src.report.general import _build_general_report_sections


def generate_mixed_report(
    df: pd.DataFrame,
    semantics: dict[str, FieldProfile],
    overview: dict[str, Any],
    question_types: dict[str, str],
    descriptive_results: dict[str, Any],
    cross_analysis_result: dict[str, Any] | None = None,
    language: str = "en",
) -> str:
    """General sections first, then the survey-specific portions."""
    sections = [f"# {t(language, 'report_title_mixed')}"]
    sections.extend(_build_general_report_sections(df, semantics, overview, language))
    sections.extend(
        [
            f"## {t(language, 'question_type_summary_title')}",
            _format_question_type_summary(question_types, language),
            f"## {t(language, 'report_key_findings')} ({t(language, 'mode_survey')})",
            _build_key_findings(df, question_types, descriptive_results, language),
            f"## {t(language, 'report_group_findings')}",
            _build_group_comparison_text(cross_analysis_result, language),
        ]
    )
    return "\n\n".join(sections).strip() + "\n"
