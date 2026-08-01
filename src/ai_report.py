from __future__ import annotations

from typing import Any

import pandas as pd

from src.dataset_mode import DATASET_MODE_GENERAL, DATASET_MODE_MIXED, DATASET_MODE_SURVEY
from src.llm_client import call_llm, is_llm_configured


AI_STATUS_OK = "ok"
AI_STATUS_NOT_CONFIGURED = "not_configured"
AI_STATUS_FAILED = "failed"


_GROUNDING_RULES = {
    "en": (
        "Strict rules: Only use the computed statistics provided below. "
        "Never invent, estimate, or extrapolate numbers that are not in the input. "
        "Every numeric claim must match a number given to you. "
        "If the provided statistics are not enough to answer something, say "
        "\"The current data is not sufficient to draw further conclusions.\" "
        "Do not pretend to have read the raw data."
    ),
    "zh-CN": (
        "严格规则：只能使用下方提供的已计算统计结果。"
        "禁止编造、估算或推断输入中不存在的数字，所有数字结论必须与提供的数值一致。"
        "如果提供的统计信息不足以回答某个问题，必须明确说明“根据当前数据无法进一步判断”。"
        "不得假装已经读取了原始数据。"
    ),
}

_PERSONAS = {
    DATASET_MODE_GENERAL: {
        "en": (
            "You are a senior general-purpose data analyst. Write a concise markdown report with sections: "
            "Dataset Overview, Fields and Distributions, Data Quality, Variable Relationships, "
            "Key Findings, Suggested Next Analyses, Limitations."
        ),
        "zh-CN": (
            "你是一名资深的通用数据分析师。请用 Markdown 输出简洁的分析报告，章节包括："
            "数据集概览、字段与分布、数据质量、变量关系、主要发现、后续分析建议、分析限制。"
        ),
    },
    DATASET_MODE_SURVEY: {
        "en": (
            "You are a senior survey analyst. Write a concise markdown report covering question types, "
            "scale scores, single/multiple-choice distributions, open-text volume, key findings, "
            "recommendations, and limitations."
        ),
        "zh-CN": (
            "你是一名资深的问卷分析师。请用 Markdown 输出简洁的问卷分析报告，"
            "覆盖题型构成、量表得分、单选/多选分布、开放题情况、主要发现、分析建议与局限性。"
        ),
    },
    DATASET_MODE_MIXED: {
        "en": (
            "You are a senior analyst working on a mixed dataset that combines survey responses with "
            "general business fields. Write a concise markdown report: first cover the general table "
            "(overview, quality, relationships), then the survey-specific portions (scales, choices, "
            "open text), then combined key findings, suggestions, and limitations."
        ),
        "zh-CN": (
            "你是一名同时精通问卷与业务数据的混合数据分析师。请用 Markdown 输出简洁报告："
            "先分析通用表格部分（概览、质量、变量关系），再分析问卷部分（量表、选择题、开放题），"
            "最后给出综合的主要发现、后续建议与分析限制。"
        ),
    },
}


def get_persona_prompt(mode: str, language: str) -> str:
    persona = _PERSONAS.get(mode, _PERSONAS[DATASET_MODE_GENERAL])
    text = persona.get(language, persona["en"])
    rules = _GROUNDING_RULES.get(language, _GROUNDING_RULES["en"])
    return f"{text}\n\n{rules}"


def _frame_digest(frame: pd.DataFrame, max_rows: int = 10) -> str:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return "(none)"
    return frame.head(max_rows).to_string()


def build_analysis_digest(
    df: pd.DataFrame,
    mode: str,
    overview: dict[str, Any],
    descriptive_results: dict[str, Any] | None = None,
    question_types: dict[str, str] | None = None,
) -> str:
    """Assemble the locally computed statistics that ground the AI narrative.

    Everything in this digest comes from pandas/scipy computations; the LLM
    is only allowed to restate and interpret these numbers.
    """
    quality = overview.get("quality", {})
    sections: list[str] = [
        f"dataset_mode: {mode}",
        f"shape: {overview.get('shape')}",
        f"duplicate_rows: {quality.get('duplicate_rows')}",
        f"overall_missing_pct: {quality.get('overall_missing_pct')}",
        f"id_candidates: {overview.get('id_candidates')}",
        "",
        "## field roles",
        _frame_digest(overview.get("field_role_table"), max_rows=40),
        "",
        "## numeric summary",
        _frame_digest(overview.get("numeric_summary"), max_rows=15),
        "",
        "## datetime summary",
        _frame_digest(overview.get("datetime_summary")),
        "",
        "## correlations (pearson)",
        _frame_digest(overview.get("correlations")),
        "",
        "## group differences (ANOVA)",
        _frame_digest(overview.get("group_differences")),
    ]

    categorical_summary = overview.get("categorical_summary") or {}
    if categorical_summary:
        sections.append("")
        sections.append("## categorical top values")
        for column, frame in list(categorical_summary.items())[:8]:
            sections.append(f"### {column}")
            sections.append(_frame_digest(frame, max_rows=5))

    if mode in {DATASET_MODE_SURVEY, DATASET_MODE_MIXED} and descriptive_results:
        sections.append("")
        sections.append("## survey question types")
        sections.append(str(question_types or {}))
        sections.append("## scale summary")
        sections.append(_frame_digest(descriptive_results.get("scale_summary")))

    high_missing = quality.get("high_missing")
    if isinstance(high_missing, pd.Series) and len(high_missing) > 0:
        sections.append("")
        sections.append("## columns above 10% missing")
        sections.append(high_missing.head(10).to_string())

    return "\n".join(sections)


def generate_ai_report(
    df: pd.DataFrame,
    mode: str,
    language: str,
    overview: dict[str, Any],
    descriptive_results: dict[str, Any] | None = None,
    question_types: dict[str, str] | None = None,
) -> dict[str, str]:
    """Generate the LLM narrative for the given mode; degrade gracefully."""
    if not is_llm_configured():
        return {"status": AI_STATUS_NOT_CONFIGURED, "content": ""}

    digest = build_analysis_digest(df, mode, overview, descriptive_results, question_types)
    system_prompt = get_persona_prompt(mode, language)
    user_prompt = (
        ("Computed statistics for the uploaded dataset:\n\n" if language == "en" else "以下是当前数据集的本地计算结果：\n\n")
        + digest
    )

    content = call_llm(system_prompt, user_prompt)
    if content is None:
        return {"status": AI_STATUS_FAILED, "content": ""}
    return {"status": AI_STATUS_OK, "content": content}
