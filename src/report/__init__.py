"""Report layer.

Split out of the former single-file ``src/report_generator.py`` (1031 lines) so
each dataset mode owns its own module. Behaviour is unchanged — the split was
mechanical.

    common      formatting helpers shared by every structure
    llm_prompt  dataset summary + prompt builder for LLM reporting
    survey      questionnaire report
    general     general-dataset report
    mixed       general sections + survey sections
    dispatch    picks the structure for the active dataset mode
"""
from __future__ import annotations

from src.report.dispatch import generate_report
from src.report.general import generate_general_report
from src.report.llm_prompt import build_dataset_summary, build_llm_prompt
from src.report.mixed import generate_mixed_report
from src.report.survey import generate_markdown_report

__all__ = [
    "build_dataset_summary",
    "build_llm_prompt",
    "generate_general_report",
    "generate_markdown_report",
    "generate_mixed_report",
    "generate_report",
]
