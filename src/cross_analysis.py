from __future__ import annotations

import pandas as pd

from src.i18n import t
from src.question_type_detector import (
    MULTI_CHOICE_PATTERN,
    QUESTION_TYPE_MULTIPLE,
    QUESTION_TYPE_NUMERIC,
    QUESTION_TYPE_OPEN,
    QUESTION_TYPE_SCALE,
)


def analyze_numeric_by_group(
    df: pd.DataFrame,
    group_col: str,
    target_col: str,
    language: str = "en",
) -> dict[str, object]:
    grouped = (
        df[[group_col, target_col]]
        .dropna()
        .groupby(group_col)[target_col]
        .agg(["count", "mean", "median", "std"])
        .round(2)
        .sort_values("mean", ascending=False)
    )

    interpretation = (
        "Not enough data to compare groups."
        if language == "en"
        else "当前可用数据不足，暂时无法稳定比较不同分组之间的差异。"
    )
    if len(grouped) >= 2:
        highest_group = grouped.index[0]
        lowest_group = grouped.index[-1]
        highest_mean = grouped.iloc[0]["mean"]
        lowest_mean = grouped.iloc[-1]["mean"]
        if language == "en":
            interpretation = (
                f"{highest_group} reports the highest average {target_col} ({highest_mean}), "
                f"while {lowest_group} reports the lowest ({lowest_mean})."
            )
        else:
            interpretation = (
                f"在 {target_col} 上，`{highest_group}` 组的平均值最高（{highest_mean}），"
                f"`{lowest_group}` 组的平均值最低（{lowest_mean}）。"
            )

    return {
        "analysis_type": "numeric_by_group",
        "summary_table": grouped,
        "interpretation": interpretation,
    }


def analyze_categorical_relationship(
    df: pd.DataFrame,
    group_col: str,
    target_col: str,
    question_types: dict[str, str],
    language: str = "en",
) -> dict[str, object]:
    working = df[[group_col, target_col]].dropna().copy()

    if question_types.get(group_col) == QUESTION_TYPE_MULTIPLE:
        working[group_col] = working[group_col].astype(str).str.split(MULTI_CHOICE_PATTERN)
        working = working.explode(group_col)
    if question_types.get(target_col) == QUESTION_TYPE_MULTIPLE:
        working[target_col] = working[target_col].astype(str).str.split(MULTI_CHOICE_PATTERN)
        working = working.explode(target_col)

    working[group_col] = working[group_col].astype(str).str.strip()
    working[target_col] = working[target_col].astype(str).str.strip()
    working = working[(working[group_col] != "") & (working[target_col] != "")]

    crosstab = pd.crosstab(working[group_col], working[target_col])
    row_pct = pd.crosstab(working[group_col], working[target_col], normalize="index").mul(100).round(2)
    col_pct = pd.crosstab(working[group_col], working[target_col], normalize="columns").mul(100).round(2)

    interpretation = (
        "Not enough data to generate a stable pattern."
        if language == "en"
        else "当前数据量有限，暂时无法形成稳定的分布模式判断。"
    )
    if not row_pct.empty:
        top_group = row_pct.max(axis=1).sort_values(ascending=False).index[0]
        top_target = row_pct.loc[top_group].idxmax()
        top_value = row_pct.loc[top_group].max()
        if language == "en":
            interpretation = (
                f"Within {top_group}, the most common {target_col} response is {top_target} "
                f"at {top_value:.1f}% of that group."
            )
        else:
            interpretation = (
                f"在 `{top_group}` 这一分组中，`{target_col}` 最常见的回答是 `{top_target}`，"
                f"占该组的 {top_value:.1f}%。"
            )

    return {
        "analysis_type": "categorical_crosstab",
        "crosstab_table": crosstab,
        "row_percentage_table": row_pct,
        "column_percentage_table": col_pct,
        "interpretation": interpretation,
    }


def analyze_cross_relationship(
    df: pd.DataFrame,
    group_col: str,
    target_col: str,
    question_types: dict[str, str],
    language: str = "en",
) -> dict[str, object]:
    group_type = question_types.get(group_col)
    target_type = question_types.get(target_col)

    if group_type == QUESTION_TYPE_OPEN or target_type == QUESTION_TYPE_OPEN:
        return {
            "analysis_type": "unsupported",
            "message_key": "cross_open_ended_warning",
            "message": t(language, "cross_open_ended_warning"),
        }

    if target_type in {QUESTION_TYPE_NUMERIC, QUESTION_TYPE_SCALE}:
        return analyze_numeric_by_group(df, group_col, target_col, language=language)

    return analyze_categorical_relationship(df, group_col, target_col, question_types, language=language)
