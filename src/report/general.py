"""The general-dataset report: field roles, quality, variable relationships."""
from __future__ import annotations

from typing import Any

import pandas as pd

from src.analysis_suggestions import generate_analysis_suggestions
from src.field_semantics import FieldProfile
from src.general_overview import build_overview_findings
from src.i18n import t, translate_field_role
from src.report.common import _bullet, _df_to_markdown_table, _format_dataset_overview, _numbered


def _format_field_role_summary(semantics: dict[str, FieldProfile], language: str) -> str:
    grouped: dict[str, list[str]] = {}
    for column, profile in semantics.items():
        grouped.setdefault(profile.role, []).append(column)

    lines: list[str] = []
    for role, columns in grouped.items():
        examples = ", ".join(f"`{column}`" for column in columns[:4])
        label = translate_field_role(language, role)
        if language == "en":
            lines.append(_bullet(f"{label}: {len(columns)} (examples: {examples})"))
        else:
            lines.append(_bullet(f"{label}：{len(columns)} 个（示例字段：{examples}）"))
    return "\n".join(lines)


def _format_general_quality(df: pd.DataFrame, overview: dict[str, Any], language: str) -> str:
    quality = overview.get("quality", {})
    is_en = language == "en"
    lines = [
        _bullet(
            f"Duplicate rows: {quality.get('duplicate_rows', 0)}"
            if is_en
            else f"重复行数：{quality.get('duplicate_rows', 0)}"
        ),
        _bullet(
            f"Average missing ratio: {quality.get('overall_missing_pct', 0):.2f}%"
            if is_en
            else f"平均缺失值比例：{quality.get('overall_missing_pct', 0):.2f}%"
        ),
    ]

    high_missing = quality.get("high_missing")
    if isinstance(high_missing, pd.Series) and len(high_missing) > 0:
        formatted = (
            ", ".join(f"`{column}` ({rate * 100:.1f}%)" for column, rate in high_missing.head(5).items())
            if is_en
            else "、".join(f"`{column}`（{rate * 100:.1f}%）" for column, rate in high_missing.head(5).items())
        )
        lines.append(
            _bullet(f"Columns above 10% missing: {formatted}" if is_en else f"缺失率超过 10% 的字段：{formatted}")
        )

    unusable = quality.get("unusable_columns") or []
    if unusable:
        formatted = ", ".join(f"`{column}`" for column in unusable[:5])
        lines.append(
            _bullet(
                f"Empty or constant columns excluded from analysis: {formatted}"
                if is_en
                else f"空白或取值恒定、已排除分析的字段：{formatted}"
            )
        )

    numeric_summary = overview.get("numeric_summary")
    if isinstance(numeric_summary, pd.DataFrame) and not numeric_summary.empty:
        flagged = numeric_summary[numeric_summary["outliers"] > 0]
        if not flagged.empty:
            formatted = (
                ", ".join(f"`{column}` ({int(count)})" for column, count in flagged["outliers"].head(3).items())
                if is_en
                else "、".join(f"`{column}`（{int(count)} 个）" for column, count in flagged["outliers"].head(3).items())
            )
            lines.append(
                _bullet(
                    f"Columns with 1.5×IQR outliers: {formatted}"
                    if is_en
                    else f"按 1.5×IQR 规则存在异常值的字段：{formatted}"
                )
            )

    return "\n".join(lines)


def _format_variable_relations(overview: dict[str, Any], language: str) -> str:
    is_en = language == "en"
    lines: list[str] = []

    correlations = overview.get("correlations")
    if isinstance(correlations, pd.DataFrame) and not correlations.empty:
        for row in correlations.head(5).itertuples(index=False):
            lines.append(
                _bullet(
                    f"`{row.field_1}` vs `{row.field_2}`: r={row.pearson_r:.2f} (p={row.p_value:.4f}, n={row.n})"
                    if is_en
                    else f"`{row.field_1}` 与 `{row.field_2}`：r={row.pearson_r:.2f}（p={row.p_value:.4f}，n={row.n}）"
                )
            )

    group_differences = overview.get("group_differences")
    if isinstance(group_differences, pd.DataFrame) and not group_differences.empty:
        for row in group_differences.head(3).itertuples(index=False):
            p_text = f"p={row.p_value:.4f}" if row.p_value is not None else ("p unavailable" if is_en else "p 值不可用")
            lines.append(
                _bullet(
                    (
                        f"`{row.metric_field}` by `{row.group_field}`: `{row.top_group}` averages {row.top_mean} "
                        f"vs `{row.bottom_group}` at {row.bottom_mean} (ANOVA {p_text})"
                    )
                    if is_en
                    else (
                        f"按 `{row.group_field}` 分组的 `{row.metric_field}`：`{row.top_group}` 平均 {row.top_mean}，"
                        f"`{row.bottom_group}` 平均 {row.bottom_mean}（ANOVA {p_text}）"
                    )
                )
            )

    if not lines:
        lines.append(_bullet(t(language, "no_data_insufficient")))
    return "\n".join(lines)


def _build_general_limitations(df: pd.DataFrame, overview: dict[str, Any], language: str) -> str:
    is_en = language == "en"
    lines = [
        _bullet(
            "Field roles and the dataset mode are detected heuristically; review the detected roles before relying on the results."
            if is_en
            else "字段角色与数据模式由启发式规则识别，正式使用结论前建议先核对识别结果。"
        ),
        _bullet(
            "Correlations and group differences are descriptive and do not establish causality."
            if is_en
            else "相关性与分组差异均为描述性结果，不能直接作为因果关系的证据。"
        ),
    ]
    quality = overview.get("quality", {})
    if quality.get("duplicate_rows", 0) > 0 or quality.get("overall_missing_pct", 0) > 5:
        lines.append(
            _bullet(
                "Missing or duplicate data may bias the summary statistics above."
                if is_en
                else "缺失值或重复数据可能会对上述统计结果产生偏差。"
            )
        )
    correlations = overview.get("correlations")
    if not isinstance(correlations, pd.DataFrame) or correlations.empty:
        lines.append(
            _bullet(
                "No strong correlations were detected; with the current data no further relationship conclusions can be drawn."
                if is_en
                else "未检测到明显的相关关系；根据当前数据无法进一步判断变量之间的关联。"
            )
        )
    return "\n".join(lines)


def _build_general_report_sections(
    df: pd.DataFrame,
    semantics: dict[str, FieldProfile],
    overview: dict[str, Any],
    language: str,
) -> list[str]:
    findings = build_overview_findings(df, overview, language)
    suggestions = generate_analysis_suggestions(df, semantics, overview, language)

    numeric_table = _df_to_markdown_table(
        overview.get("numeric_summary", pd.DataFrame()),
        index_label=t(language, "label_field"),
    )
    fields_section = _format_field_role_summary(semantics, language)
    if numeric_table:
        fields_section = fields_section + "\n\n" + numeric_table

    return [
        f"## {t(language, 'report_dataset_overview')}",
        _format_dataset_overview(df, language),
        f"## {t(language, 'report_fields_distribution')}",
        fields_section,
        f"## {t(language, 'report_data_quality')}",
        _format_general_quality(df, overview, language),
        f"## {t(language, 'report_variable_relations')}",
        _format_variable_relations(overview, language),
        f"## {t(language, 'report_key_findings')}",
        "\n".join(_bullet(finding) for finding in findings) if findings else _bullet(t(language, "report_no_findings")),
        f"## {t(language, 'report_next_steps')}",
        _numbered(suggestions) if suggestions else _bullet(t(language, "no_data_insufficient")),
        f"## {t(language, 'report_analysis_limitations')}",
        _build_general_limitations(df, overview, language),
    ]


def generate_general_report(
    df: pd.DataFrame,
    semantics: dict[str, FieldProfile],
    overview: dict[str, Any],
    language: str = "en",
) -> str:
    """Create the report for a general (non-survey) dataset."""
    sections = [f"# {t(language, 'report_title_general')}"]
    sections.extend(_build_general_report_sections(df, semantics, overview, language))
    return "\n\n".join(sections).strip() + "\n"
