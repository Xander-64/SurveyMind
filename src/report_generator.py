"""Backwards-compatible facade for the report layer.

The implementation moved to the ``src.report`` package; this module re-exports
every name the single-file version exposed (private helpers included) so existing
imports and tests keep working unchanged. New code should import from
``src.report`` directly.
"""
from __future__ import annotations

from src.report.common import (  # noqa: F401
    _bullet,
    _df_to_markdown_table,
    _find_numeric_outliers,
    _format_dataset_overview,
    _numbered,
    _to_python_scalar,
)
from src.report.llm_prompt import (  # noqa: F401
    build_dataset_summary,
    build_llm_prompt,
)
from src.report.survey import (  # noqa: F401
    _build_categorical_findings,
    _build_generic_recommendation,
    _build_group_comparison_text,
    _build_group_followup_recommendation,
    _build_imbalanced_recommendation,
    _build_key_findings,
    _build_limitations_text,
    _build_missingness_recommendation,
    _build_multiple_choice_findings,
    _build_multiple_choice_recommendation,
    _build_numeric_findings,
    _build_open_ended_recommendation,
    _build_open_text_findings,
    _build_recommendations,
    _build_scale_findings,
    _build_scale_recommendation,
    _format_data_quality_summary,
    _format_question_type_summary,
    _question_type_counts,
    generate_markdown_report,
)
from src.report.general import (  # noqa: F401
    _build_general_limitations,
    _build_general_report_sections,
    _format_field_role_summary,
    _format_general_quality,
    _format_variable_relations,
    generate_general_report,
)
from src.report.mixed import (  # noqa: F401
    generate_mixed_report,
)
from src.report.dispatch import (  # noqa: F401
    generate_report,
)

__all__ = [
    "build_dataset_summary",
    "build_llm_prompt",
    "generate_general_report",
    "generate_markdown_report",
    "generate_mixed_report",
    "generate_report",
]
