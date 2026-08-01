from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from src.field_semantics import (
    FIELD_ROLE_BOOLEAN,
    FIELD_ROLE_CATEGORICAL,
    FIELD_ROLE_DATETIME,
    FIELD_ROLE_EMPTY,
    FIELD_ROLE_FREE_TEXT,
    FIELD_ROLE_IDENTIFIER,
    FIELD_ROLE_MULTI_VALUE,
    FIELD_ROLE_NUMERIC,
    MULTI_VALUE_PATTERN,
    FieldProfile,
)


MAX_NUMERIC_COLUMNS = 10
MAX_CATEGORICAL_COLUMNS = 10
MAX_GROUP_PAIRS = 40
MIN_GROUP_SIZE = 5
CORRELATION_THRESHOLD = 0.3


def _columns_with_role(semantics: dict[str, FieldProfile], role: str) -> list[str]:
    return [column for column, profile in semantics.items() if profile.role == role]


def iqr_outlier_count(series: pd.Series) -> int:
    cleaned = pd.to_numeric(series.dropna(), errors="coerce").dropna()
    if cleaned.empty:
        return 0
    q1 = cleaned.quantile(0.25)
    q3 = cleaned.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return 0
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    return int(((cleaned < lower_bound) | (cleaned > upper_bound)).sum())


def summarize_numeric_fields(df: pd.DataFrame, numeric_columns: list[str]) -> pd.DataFrame:
    if not numeric_columns:
        return pd.DataFrame()

    rows: list[dict[str, float]] = []
    index: list[str] = []
    for column in numeric_columns:
        cleaned = pd.to_numeric(df[column], errors="coerce").dropna()
        if cleaned.empty:
            continue
        rows.append(
            {
                "count": float(cleaned.count()),
                "mean": round(float(cleaned.mean()), 2),
                "median": round(float(cleaned.median()), 2),
                "std": round(float(cleaned.std()), 2) if cleaned.count() > 1 else 0.0,
                "min": round(float(cleaned.min()), 2),
                "q1": round(float(cleaned.quantile(0.25)), 2),
                "q3": round(float(cleaned.quantile(0.75)), 2),
                "max": round(float(cleaned.max()), 2),
                "missing_pct": round(float(df[column].isna().mean() * 100), 2),
                "outliers": iqr_outlier_count(df[column]),
            }
        )
        index.append(column)

    return pd.DataFrame(rows, index=index)


def summarize_categorical_fields(
    df: pd.DataFrame,
    semantics: dict[str, FieldProfile],
    top_n: int = 10,
) -> dict[str, pd.DataFrame]:
    summaries: dict[str, pd.DataFrame] = {}
    for column, profile in semantics.items():
        if profile.role not in {FIELD_ROLE_CATEGORICAL, FIELD_ROLE_BOOLEAN, FIELD_ROLE_MULTI_VALUE}:
            continue
        series = df[column].dropna().astype(str).str.strip()
        series = series[series != ""]
        if profile.role == FIELD_ROLE_MULTI_VALUE:
            series = series.str.split(MULTI_VALUE_PATTERN).explode().astype(str).str.strip()
            series = series[series != ""]
        if series.empty:
            continue
        frequency = series.value_counts().head(top_n).rename_axis("value").reset_index(name="count")
        frequency["percentage"] = (frequency["count"] / len(series) * 100).round(2)
        summaries[column] = frequency
    return summaries


def summarize_datetime_fields(df: pd.DataFrame, datetime_columns: list[str]) -> pd.DataFrame:
    if not datetime_columns:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for column in datetime_columns:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed = pd.to_datetime(df[column], errors="coerce")
        parsed = parsed.dropna()
        if parsed.empty:
            continue
        rows.append(
            {
                "column_name": column,
                "earliest": parsed.min().strftime("%Y-%m-%d"),
                "latest": parsed.max().strftime("%Y-%m-%d"),
                "span_days": int((parsed.max() - parsed.min()).days),
                "valid_count": int(parsed.count()),
            }
        )
    return pd.DataFrame(rows)


def build_time_trends(df: pd.DataFrame, datetime_columns: list[str]) -> dict[str, pd.DataFrame]:
    """Monthly record counts per datetime column, used by trend charts."""
    trends: dict[str, pd.DataFrame] = {}
    for column in datetime_columns:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed = pd.to_datetime(df[column], errors="coerce")
        parsed = parsed.dropna()
        if parsed.empty or parsed.nunique() < 2:
            continue
        monthly = parsed.dt.to_period("M").value_counts().sort_index()
        trend = monthly.rename_axis("period").reset_index(name="count")
        trend["period"] = trend["period"].astype(str)
        trends[column] = trend
    return trends


def compute_correlations(
    df: pd.DataFrame,
    numeric_columns: list[str],
    threshold: float = CORRELATION_THRESHOLD,
    top_n: int = 10,
) -> pd.DataFrame:
    usable = numeric_columns[:MAX_NUMERIC_COLUMNS]
    if len(usable) < 2:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for i, column_a in enumerate(usable):
        for column_b in usable[i + 1 :]:
            paired = df[[column_a, column_b]].apply(pd.to_numeric, errors="coerce").dropna()
            if len(paired) < 3 or paired[column_a].nunique() < 2 or paired[column_b].nunique() < 2:
                continue
            try:
                r_value, p_value = stats.pearsonr(paired[column_a], paired[column_b])
            except Exception:
                continue
            if np.isnan(r_value) or abs(r_value) < threshold:
                continue
            rows.append(
                {
                    "field_1": column_a,
                    "field_2": column_b,
                    "pearson_r": round(float(r_value), 3),
                    "p_value": round(float(p_value), 4),
                    "n": int(len(paired)),
                }
            )

    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    return result.reindex(result["pearson_r"].abs().sort_values(ascending=False).index).head(top_n).reset_index(drop=True)


def compute_group_differences(
    df: pd.DataFrame,
    categorical_columns: list[str],
    numeric_columns: list[str],
    top_n: int = 5,
) -> pd.DataFrame:
    """Scan categorical × numeric pairs for notable mean gaps (with ANOVA p)."""
    rows: list[dict[str, Any]] = []
    pair_count = 0
    for group_column in categorical_columns[:MAX_CATEGORICAL_COLUMNS]:
        group_values = df[group_column].dropna().astype(str).str.strip()
        group_cardinality = group_values.nunique()
        if group_cardinality < 2 or group_cardinality > 10:
            continue
        for metric_column in numeric_columns[:MAX_NUMERIC_COLUMNS]:
            if pair_count >= MAX_GROUP_PAIRS:
                break
            pair_count += 1

            working = df[[group_column, metric_column]].copy()
            working[metric_column] = pd.to_numeric(working[metric_column], errors="coerce")
            working = working.dropna()
            if working.empty:
                continue
            working[group_column] = working[group_column].astype(str).str.strip()

            group_sizes = working.groupby(group_column)[metric_column].count()
            valid_groups = group_sizes[group_sizes >= MIN_GROUP_SIZE].index
            if len(valid_groups) < 2:
                continue
            working = working[working[group_column].isin(valid_groups)]

            means = working.groupby(group_column)[metric_column].mean().sort_values(ascending=False)
            overall_std = float(working[metric_column].std())
            if overall_std == 0 or np.isnan(overall_std):
                continue
            gap = float(means.iloc[0] - means.iloc[-1])
            effect = gap / overall_std

            samples = [group_data.values for _, group_data in working.groupby(group_column)[metric_column]]
            try:
                _, p_value = stats.f_oneway(*samples)
            except Exception:
                p_value = float("nan")

            rows.append(
                {
                    "group_field": group_column,
                    "metric_field": metric_column,
                    "top_group": means.index[0],
                    "top_mean": round(float(means.iloc[0]), 2),
                    "bottom_group": means.index[-1],
                    "bottom_mean": round(float(means.iloc[-1]), 2),
                    "effect_size": round(effect, 2),
                    "p_value": round(float(p_value), 4) if not np.isnan(p_value) else None,
                }
            )

    if not rows:
        return pd.DataFrame()
    return (
        pd.DataFrame(rows)
        .sort_values("effect_size", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )


def assess_data_quality(df: pd.DataFrame, semantics: dict[str, FieldProfile]) -> dict[str, Any]:
    missing_rates = df.isna().mean()
    high_missing = missing_rates[missing_rates > 0.1].sort_values(ascending=False)
    return {
        "duplicate_rows": int(df.duplicated().sum()),
        "overall_missing_pct": round(float(missing_rates.mean() * 100), 2),
        "high_missing": high_missing,
        "unusable_columns": _columns_with_role(semantics, FIELD_ROLE_EMPTY),
    }


def build_field_role_table(df: pd.DataFrame, semantics: dict[str, FieldProfile]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "column_name": list(semantics.keys()),
            "role": [profile.role for profile in semantics.values()],
            "dtype": [str(df[column].dtype) for column in semantics.keys()],
            "non_null": [profile.non_null_count for profile in semantics.values()],
            "unique": [profile.unique_count for profile in semantics.values()],
            "missing_pct": [round(float(df[column].isna().mean() * 100), 2) for column in semantics.keys()],
        }
    )


def generate_general_overview(df: pd.DataFrame, semantics: dict[str, FieldProfile]) -> dict[str, Any]:
    """Bundle the mode-agnostic data overview used across UI and reports."""
    numeric_columns = _columns_with_role(semantics, FIELD_ROLE_NUMERIC)
    categorical_columns = _columns_with_role(semantics, FIELD_ROLE_CATEGORICAL) + _columns_with_role(
        semantics, FIELD_ROLE_BOOLEAN
    )
    datetime_columns = _columns_with_role(semantics, FIELD_ROLE_DATETIME)

    numeric_summary = summarize_numeric_fields(df, numeric_columns)
    return {
        "shape": df.shape,
        "preview": df.head(),
        "field_role_table": build_field_role_table(df, semantics),
        "quality": assess_data_quality(df, semantics),
        "id_candidates": _columns_with_role(semantics, FIELD_ROLE_IDENTIFIER),
        "free_text_columns": _columns_with_role(semantics, FIELD_ROLE_FREE_TEXT),
        "numeric_summary": numeric_summary,
        "categorical_summary": summarize_categorical_fields(df, semantics),
        "datetime_summary": summarize_datetime_fields(df, datetime_columns),
        "time_trends": build_time_trends(df, datetime_columns),
        "correlations": compute_correlations(df, numeric_columns),
        "group_differences": compute_group_differences(df, categorical_columns, numeric_columns),
    }


def build_overview_findings(df: pd.DataFrame, overview: dict[str, Any], language: str = "en") -> list[str]:
    """Turn computed overview results into short human-readable findings."""
    findings: list[str] = []
    is_en = language == "en"

    rows, columns = overview["shape"]
    quality = overview["quality"]
    findings.append(
        f"The dataset has {rows} rows and {columns} columns; average missing ratio is {quality['overall_missing_pct']:.2f}%."
        if is_en
        else f"数据集共有 {rows} 行、{columns} 个字段，平均缺失值比例为 {quality['overall_missing_pct']:.2f}%。"
    )

    if quality["duplicate_rows"] > 0:
        findings.append(
            f"{quality['duplicate_rows']} duplicate row(s) were found and may need de-duplication."
            if is_en
            else f"检测到 {quality['duplicate_rows']} 行完全重复的数据，建议确认是否需要去重。"
        )

    high_missing = quality["high_missing"]
    if len(high_missing) > 0:
        formatted = (
            ", ".join(f"`{column}` ({rate * 100:.1f}%)" for column, rate in high_missing.head(3).items())
            if is_en
            else "、".join(f"`{column}`（{rate * 100:.1f}%）" for column, rate in high_missing.head(3).items())
        )
        findings.append(
            f"Columns with more than 10% missing values: {formatted}."
            if is_en
            else f"缺失率超过 10% 的字段：{formatted}。"
        )

    id_candidates = overview["id_candidates"]
    if id_candidates:
        formatted = ", ".join(f"`{column}`" for column in id_candidates[:3])
        findings.append(
            f"Likely identifier column(s): {formatted}; they are excluded from statistical analysis."
            if is_en
            else f"识别出可能的 ID 字段：{formatted}，这些字段已从统计分析中排除。"
        )

    datetime_summary = overview["datetime_summary"]
    if isinstance(datetime_summary, pd.DataFrame) and not datetime_summary.empty:
        first = datetime_summary.iloc[0]
        findings.append(
            f"`{first['column_name']}` covers {first['earliest']} to {first['latest']} ({first['span_days']} days)."
            if is_en
            else f"`{first['column_name']}` 覆盖 {first['earliest']} 至 {first['latest']}，跨度 {first['span_days']} 天。"
        )

    numeric_summary = overview["numeric_summary"]
    if isinstance(numeric_summary, pd.DataFrame) and not numeric_summary.empty:
        outlier_columns = numeric_summary[numeric_summary["outliers"] > 0]
        if not outlier_columns.empty:
            top = outlier_columns["outliers"].sort_values(ascending=False)
            findings.append(
                f"`{top.index[0]}` shows {int(top.iloc[0])} possible outlier(s) by the 1.5×IQR rule."
                if is_en
                else f"按 1.5×IQR 规则，`{top.index[0]}` 存在 {int(top.iloc[0])} 个可能的异常值。"
            )

    correlations = overview["correlations"]
    if isinstance(correlations, pd.DataFrame) and not correlations.empty:
        top = correlations.iloc[0]
        findings.append(
            f"`{top['field_1']}` and `{top['field_2']}` show the strongest correlation (r={top['pearson_r']:.2f}, n={int(top['n'])})."
            if is_en
            else f"`{top['field_1']}` 与 `{top['field_2']}` 的相关性最强（r={top['pearson_r']:.2f}，样本量 {int(top['n'])}）。"
        )

    group_differences = overview["group_differences"]
    if isinstance(group_differences, pd.DataFrame) and not group_differences.empty:
        top = group_differences.iloc[0]
        p_text = (
            f", ANOVA p={top['p_value']:.4f}" if top["p_value"] is not None else ""
        ) if is_en else (
            f"，ANOVA p={top['p_value']:.4f}" if top["p_value"] is not None else ""
        )
        findings.append(
            (
                f"`{top['metric_field']}` differs across `{top['group_field']}`: "
                f"`{top['top_group']}` averages {top['top_mean']} vs `{top['bottom_group']}` at {top['bottom_mean']}{p_text}."
            )
            if is_en
            else (
                f"`{top['metric_field']}` 在不同 `{top['group_field']}` 之间存在差异："
                f"`{top['top_group']}` 平均 {top['top_mean']}，`{top['bottom_group']}` 平均 {top['bottom_mean']}{p_text}。"
            )
        )

    return findings
