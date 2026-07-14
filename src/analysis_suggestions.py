from __future__ import annotations

import re
from typing import Any

import pandas as pd

from src.field_semantics import (
    FIELD_ROLE_BOOLEAN,
    FIELD_ROLE_CATEGORICAL,
    FIELD_ROLE_DATETIME,
    FIELD_ROLE_FREE_TEXT,
    FIELD_ROLE_MULTI_VALUE,
    FIELD_ROLE_NUMERIC,
    FieldProfile,
)


TARGET_NAME_PATTERN = re.compile(
    r"churn|流失|label|target|converted|purchased|survived|default|是否|退货|returned|离职|attrition",
    re.IGNORECASE,
)


def find_target_candidates(df: pd.DataFrame, semantics: dict[str, FieldProfile]) -> list[str]:
    """Columns that look like modeling targets (binary and/or target-like names)."""
    candidates: list[str] = []
    for column, profile in semantics.items():
        name_hit = bool(TARGET_NAME_PATTERN.search(column))
        is_binary = profile.role == FIELD_ROLE_BOOLEAN or (
            profile.role in {FIELD_ROLE_NUMERIC, FIELD_ROLE_CATEGORICAL} and profile.unique_count == 2
        )
        if name_hit and is_binary:
            candidates.insert(0, column)
        elif name_hit or (profile.role == FIELD_ROLE_BOOLEAN and is_binary):
            candidates.append(column)
    return candidates


def generate_analysis_suggestions(
    df: pd.DataFrame,
    semantics: dict[str, FieldProfile],
    overview: dict[str, Any],
    language: str = "en",
    max_suggestions: int = 5,
) -> list[str]:
    """Build 3-5 analysis suggestions grounded in the actual fields."""
    is_en = language == "en"
    suggestions: list[str] = []

    numeric_columns = [c for c, p in semantics.items() if p.role == FIELD_ROLE_NUMERIC]
    categorical_columns = [
        c
        for c, p in semantics.items()
        if p.role in {FIELD_ROLE_CATEGORICAL, FIELD_ROLE_BOOLEAN} and 2 <= p.unique_count <= 10
    ]
    datetime_columns = [c for c, p in semantics.items() if p.role == FIELD_ROLE_DATETIME]
    text_columns = [c for c, p in semantics.items() if p.role == FIELD_ROLE_FREE_TEXT]
    multi_columns = [c for c, p in semantics.items() if p.role == FIELD_ROLE_MULTI_VALUE]

    group_differences = overview.get("group_differences")
    if isinstance(group_differences, pd.DataFrame) and not group_differences.empty:
        top = group_differences.iloc[0]
        suggestions.append(
            f"Compare `{top['metric_field']}` across `{top['group_field']}` groups — the current gap looks notable."
            if is_en
            else f"比较不同 `{top['group_field']}` 之间的 `{top['metric_field']}` 差异——当前分组差距比较明显。"
        )
    elif categorical_columns and numeric_columns:
        suggestions.append(
            f"Compare `{numeric_columns[0]}` across `{categorical_columns[0]}` groups."
            if is_en
            else f"比较不同 `{categorical_columns[0]}` 之间的 `{numeric_columns[0]}` 差异。"
        )

    correlations = overview.get("correlations")
    if isinstance(correlations, pd.DataFrame) and not correlations.empty:
        top = correlations.iloc[0]
        suggestions.append(
            f"Explore the relationship between `{top['field_1']}` and `{top['field_2']}` (r={top['pearson_r']:.2f})."
            if is_en
            else f"进一步分析 `{top['field_1']}` 与 `{top['field_2']}` 的关系（r={top['pearson_r']:.2f}）。"
        )
    elif len(numeric_columns) >= 2:
        suggestions.append(
            f"Check whether `{numeric_columns[0]}` and `{numeric_columns[1]}` are related."
            if is_en
            else f"检查 `{numeric_columns[0]}` 与 `{numeric_columns[1]}` 之间是否存在关联。"
        )

    if datetime_columns:
        metric_hint = f" `{numeric_columns[0]}`" if numeric_columns else ""
        suggestions.append(
            f"Look at monthly trends over `{datetime_columns[0]}`{(' for' + metric_hint) if metric_hint else ''}."
            if is_en
            else f"查看按 `{datetime_columns[0]}` 汇总的每月变化趋势{('，重点关注' + metric_hint) if metric_hint else ''}。"
        )

    target_candidates = find_target_candidates(df, semantics)
    if target_candidates:
        suggestions.append(
            f"Check which variables are most related to `{target_candidates[0]}` (a likely target variable)."
            if is_en
            else f"检查哪些变量与 `{target_candidates[0]}`（疑似目标变量）关系最大。"
        )

    if text_columns:
        suggestions.append(
            f"Summarize the main themes in the free-text field `{text_columns[0]}`."
            if is_en
            else f"总结自由文本字段 `{text_columns[0]}` 中的主要主题。"
        )

    if multi_columns and len(suggestions) < max_suggestions:
        suggestions.append(
            f"Review which options are selected most often in `{multi_columns[0]}`."
            if is_en
            else f"查看多值字段 `{multi_columns[0]}` 中被选择最多的选项。"
        )

    quality = overview.get("quality", {})
    high_missing = quality.get("high_missing")
    if isinstance(high_missing, pd.Series) and len(high_missing) > 0 and len(suggestions) < max_suggestions:
        suggestions.append(
            f"Investigate why `{high_missing.index[0]}` has a high missing rate before deeper analysis."
            if is_en
            else f"在深入分析之前，先排查 `{high_missing.index[0]}` 缺失率偏高的原因。"
        )

    if len(suggestions) < 3 and numeric_columns:
        suggestions.append(
            f"Review the distribution and outliers of `{numeric_columns[0]}`."
            if is_en
            else f"检查 `{numeric_columns[0]}` 的分布形态和异常值。"
        )
    if len(suggestions) < 3 and categorical_columns:
        suggestions.append(
            f"Check whether the categories of `{categorical_columns[0]}` are balanced."
            if is_en
            else f"检查 `{categorical_columns[0]}` 的类别分布是否均衡。"
        )

    return suggestions[:max_suggestions]
