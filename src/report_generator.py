from __future__ import annotations

from typing import Any

import pandas as pd

from src.i18n import t, translate_question_type, translate_scale_level
from src.question_type_detector import (
    QUESTION_TYPE_MULTIPLE,
    QUESTION_TYPE_NUMERIC,
    QUESTION_TYPE_OPEN,
    QUESTION_TYPE_SCALE,
    QUESTION_TYPE_SINGLE,
)


def _question_type_counts(question_types: dict[str, str]) -> dict[str, int]:
    counts = pd.Series(question_types).value_counts()
    return {
        QUESTION_TYPE_NUMERIC: int(counts.get(QUESTION_TYPE_NUMERIC, 0)),
        QUESTION_TYPE_SCALE: int(counts.get(QUESTION_TYPE_SCALE, 0)),
        QUESTION_TYPE_SINGLE: int(counts.get(QUESTION_TYPE_SINGLE, 0)),
        QUESTION_TYPE_MULTIPLE: int(counts.get(QUESTION_TYPE_MULTIPLE, 0)),
        QUESTION_TYPE_OPEN: int(counts.get(QUESTION_TYPE_OPEN, 0)),
    }


def _bullet(text: str) -> str:
    return f"- {text}"


def _numbered(items: list[str]) -> str:
    return "\n\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))


def _format_dataset_overview(df: pd.DataFrame, language: str) -> str:
    duplicate_rows = int(df.duplicated().sum())
    average_missing = df.isna().mean().mean() * 100
    if language == "en":
        lines = [
            _bullet(f"Rows: {len(df)}"),
            _bullet(f"Columns: {len(df.columns)}"),
            _bullet(f"Duplicate rows: {duplicate_rows}"),
            _bullet(f"Average missing value ratio: {average_missing:.2f}%"),
        ]
    else:
        lines = [
            _bullet(f"样本行数：{len(df)}"),
            _bullet(f"字段数量：{len(df.columns)}"),
            _bullet(f"重复行数：{duplicate_rows}"),
            _bullet(f"平均缺失值比例：{average_missing:.2f}%"),
        ]
    return "\n".join(lines)


def _format_data_quality_summary(df: pd.DataFrame, question_types: dict[str, str], language: str) -> str:
    missing_rates = df.isna().mean().sort_values(ascending=False)
    complete_columns = int((missing_rates == 0).sum())
    top_missing = missing_rates.head(min(3, len(missing_rates)))
    high_missing = missing_rates[missing_rates > 0.1]

    lines: list[str] = []
    if language == "en":
        lines.append(_bullet(f"{complete_columns} columns have no missing values."))
        if not top_missing.empty and float(top_missing.iloc[0]) > 0:
            formatted = ", ".join(f"`{column}` ({rate * 100:.2f}%)" for column, rate in top_missing.items())
            lines.append(_bullet(f"The highest missingness appears in {formatted}."))
        if not high_missing.empty:
            flagged = ", ".join(f"`{column}`" for column in high_missing.index[:5])
            lines.append(_bullet(f"Columns above 10% missing responses include {flagged}."))
    else:
        lines.append(_bullet(f"共有 {complete_columns} 个字段没有缺失值。"))
        if not top_missing.empty and float(top_missing.iloc[0]) > 0:
            formatted = "、".join(f"`{column}`（{rate * 100:.2f}%）" for column, rate in top_missing.items())
            lines.append(_bullet(f"缺失率较高的字段包括 {formatted}。"))
        if not high_missing.empty:
            flagged = "、".join(f"`{column}`" for column in high_missing.index[:5])
            lines.append(_bullet(f"缺失率超过 10% 的字段有 {flagged}。"))

    numeric_like_columns = [
        column
        for column, q_type in question_types.items()
        if q_type in {QUESTION_TYPE_NUMERIC, QUESTION_TYPE_SCALE} and missing_rates.get(column, 0) > 0
    ]
    if numeric_like_columns:
        preview = ", ".join(f"`{column}`" for column in numeric_like_columns[:3])
        lines.append(
            _bullet(
                f"Numeric or scale fields with missing values include {preview}."
                if language == "en"
                else f"存在缺失值的数值题或量表题字段包括 {preview}。"
            )
        )

    return "\n".join(lines)


def _format_question_type_summary(question_types: dict[str, str], language: str) -> str:
    counts = _question_type_counts(question_types)
    grouped_columns: dict[str, list[str]] = {}
    for column, question_type in question_types.items():
        grouped_columns.setdefault(question_type, []).append(column)

    ordered_types = [
        QUESTION_TYPE_NUMERIC,
        QUESTION_TYPE_SCALE,
        QUESTION_TYPE_SINGLE,
        QUESTION_TYPE_MULTIPLE,
        QUESTION_TYPE_OPEN,
    ]

    lines = []
    for question_type in ordered_types:
        examples = ", ".join(f"`{column}`" for column in grouped_columns.get(question_type, [])[:3])
        label = translate_question_type(language, question_type)
        count = counts[question_type]
        if language == "en":
            detail = f"{label}: {count}"
            if examples:
                detail += f" (examples: {examples})"
        else:
            detail = f"{label}：{count}"
            if examples:
                detail += f"（示例字段：{examples}）"
        lines.append(_bullet(detail))

    return "\n".join(lines)


def _find_numeric_outliers(series: pd.Series) -> int:
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


def _build_numeric_findings(df: pd.DataFrame, numeric_summary: pd.DataFrame, language: str) -> list[str]:
    if numeric_summary.empty:
        return []

    findings: list[str] = []
    top_mean_column = numeric_summary["mean"].sort_values(ascending=False).index[0]
    top_std_column = numeric_summary["std"].fillna(0).sort_values(ascending=False).index[0]
    numeric_missing = df[numeric_summary.index].isna().mean().sort_values(ascending=False)
    top_missing_column = numeric_missing.index[0]

    if language == "en":
        findings.append(
            _bullet(
                f"`{top_mean_column}` has the highest mean among numeric questions at {numeric_summary.loc[top_mean_column, 'mean']:.2f}."
            )
        )
        findings.append(
            _bullet(
                f"`{top_std_column}` shows the widest spread, with a standard deviation of {numeric_summary.loc[top_std_column, 'std']:.2f}."
            )
        )
        findings.append(
            _bullet(
                f"`{top_missing_column}` has the highest missing rate among numeric questions at {numeric_missing.iloc[0] * 100:.2f}%."
            )
        )
    else:
        findings.append(
            _bullet(
                f"在数值题中，`{top_mean_column}` 的平均值最高，为 {numeric_summary.loc[top_mean_column, 'mean']:.2f}。"
            )
        )
        findings.append(
            _bullet(
                f"`{top_std_column}` 的离散程度最大，标准差为 {numeric_summary.loc[top_std_column, 'std']:.2f}。"
            )
        )
        findings.append(
            _bullet(
                f"在数值题中，`{top_missing_column}` 的缺失率最高，为 {numeric_missing.iloc[0] * 100:.2f}%。"
            )
        )

    outlier_notes = []
    for column in numeric_summary.index:
        outlier_count = _find_numeric_outliers(df[column])
        if outlier_count > 0:
            outlier_notes.append((column, outlier_count))

    if outlier_notes:
        column, count = sorted(outlier_notes, key=lambda item: item[1], reverse=True)[0]
        findings.append(
            _bullet(
                f"`{column}` shows possible outliers based on the 1.5×IQR rule, with {count} flagged responses."
                if language == "en"
                else f"基于 1.5×IQR 规则，`{column}` 可能存在异常值，共识别出 {count} 个可疑回答。"
            )
        )

    return findings


def _build_scale_findings(scale_summary: pd.DataFrame, language: str) -> list[str]:
    if scale_summary.empty:
        return []

    findings: list[str] = []
    top_scale_column = scale_summary["mean"].sort_values(ascending=False).index[0]
    top_scale_level = translate_scale_level(language, scale_summary.loc[top_scale_column, "interpretation"])

    if language == "en":
        findings.append(
            _bullet(
                f"`{top_scale_column}` has the highest average among scale questions at {scale_summary.loc[top_scale_column, 'mean']:.2f}, which is {top_scale_level}."
            )
        )
    else:
        findings.append(
            _bullet(
                f"在量表题中，`{top_scale_column}` 的平均分最高，为 {scale_summary.loc[top_scale_column, 'mean']:.2f}，整体水平为 {top_scale_level}。"
            )
        )

    for column in scale_summary.index[:3]:
        level = translate_scale_level(language, scale_summary.loc[column, "interpretation"])
        if language == "en":
            findings.append(
                _bullet(
                    f"`{column}` has a mean of {scale_summary.loc[column, 'mean']:.2f}, a median of {scale_summary.loc[column, 'median']:.2f}, and an overall interpretation of {level}."
                )
            )
        else:
            findings.append(
                _bullet(
                    f"`{column}` 的平均分为 {scale_summary.loc[column, 'mean']:.2f}，中位数为 {scale_summary.loc[column, 'median']:.2f}，整体可解释为 {level}。"
                )
            )

    return findings


def _build_categorical_findings(
    question_types: dict[str, str],
    categorical_summary: dict[str, pd.DataFrame],
    language: str,
) -> list[str]:
    findings: list[str] = []

    single_choice_columns = [
        column for column, q_type in question_types.items() if q_type == QUESTION_TYPE_SINGLE and column in categorical_summary
    ]

    for column in single_choice_columns[:5]:
        summary = categorical_summary[column]
        if summary.empty:
            continue
        top_row = summary.iloc[0]
        findings.append(
            _bullet(
                f"`{column}` is led by `{top_row['response']}` at {top_row['percentage']:.2f}%."
                if language == "en"
                else f"`{column}` 当前最集中的选项是 `{top_row['response']}`，占比 {top_row['percentage']:.2f}%。"
            )
        )
        if float(top_row["percentage"]) > 70:
            findings.append(
                _bullet(
                    f"`{column}` is highly imbalanced because its top category exceeds 70% of responses."
                    if language == "en"
                    else f"`{column}` 呈现出较强的集中分布，因为最高选项占比已经超过 70%。"
                )
            )

    return findings


def _build_multiple_choice_findings(
    question_types: dict[str, str],
    categorical_summary: dict[str, pd.DataFrame],
    language: str,
) -> list[str]:
    findings: list[str] = []

    for column, q_type in question_types.items():
        if q_type != QUESTION_TYPE_MULTIPLE:
            continue
        summary = categorical_summary.get(column)
        if summary is None or summary.empty:
            continue

        top_options = summary.head(3)
        formatted = ", ".join(
            f"`{row.response}` ({row.percentage:.2f}%)" for row in top_options.itertuples(index=False)
        )
        findings.append(
            _bullet(
                f"For multiple-choice question `{column}`, the most selected options are {formatted}."
                if language == "en"
                else f"对于多选题 `{column}`，当前被选择最多的选项包括 {formatted}。"
            )
        )

    return findings


def _build_open_text_findings(df: pd.DataFrame, question_types: dict[str, str], language: str) -> list[str]:
    findings: list[str] = []

    for column, q_type in question_types.items():
        if q_type != QUESTION_TYPE_OPEN:
            continue
        valid_count = int(df[column].dropna().astype(str).str.strip().ne("").sum())
        findings.append(
            _bullet(
                f"`{column}` contains {valid_count} valid open-ended responses. A future LLM workflow can summarize themes from this text field."
                if language == "en"
                else f"`{column}` 共包含 {valid_count} 条有效开放题回答。后续可以通过 LLM 工作流对这些文本进行主题归纳。"
            )
        )

    return findings


def _build_key_findings(
    df: pd.DataFrame,
    question_types: dict[str, str],
    descriptive_results: dict[str, Any],
    language: str,
) -> str:
    numeric_summary = descriptive_results.get("numeric_summary", pd.DataFrame())
    scale_summary = descriptive_results.get("scale_summary", pd.DataFrame())
    categorical_summary = descriptive_results.get("categorical_summary", {})

    findings: list[str] = []
    findings.extend(_build_numeric_findings(df, numeric_summary, language))
    findings.extend(_build_scale_findings(scale_summary, language))
    findings.extend(_build_categorical_findings(question_types, categorical_summary, language))
    findings.extend(_build_multiple_choice_findings(question_types, categorical_summary, language))
    findings.extend(_build_open_text_findings(df, question_types, language))

    if not findings:
        return _bullet(t(language, "report_no_findings"))
    return "\n".join(findings)


def _build_group_comparison_text(cross_analysis_result: dict[str, Any] | None, language: str) -> str:
    if not cross_analysis_result:
        return _bullet(t(language, "report_no_cross_analysis"))

    if cross_analysis_result.get("analysis_type") == "unsupported":
        return _bullet(cross_analysis_result.get("message", t(language, "cross_open_ended_warning")))

    lines = [_bullet(cross_analysis_result.get("interpretation", ""))]
    if cross_analysis_result.get("analysis_type") == "numeric_by_group":
        summary_table = cross_analysis_result.get("summary_table", pd.DataFrame())
        if isinstance(summary_table, pd.DataFrame) and not summary_table.empty:
            top_group = summary_table.index[0]
            lines.append(
                _bullet(
                    f"The leading group in the selected comparison is `{top_group}`."
                    if language == "en"
                    else f"在当前比较中，表现最高的分组是 `{top_group}`。"
                )
            )
    elif cross_analysis_result.get("analysis_type") == "categorical_crosstab":
        crosstab_table = cross_analysis_result.get("crosstab_table", pd.DataFrame())
        if isinstance(crosstab_table, pd.DataFrame) and not crosstab_table.empty:
            lines.append(
                _bullet(
                    f"The selected cross-tab contains {crosstab_table.shape[0]} group categories and {crosstab_table.shape[1]} target categories."
                    if language == "en"
                    else f"本次交叉表共包含 {crosstab_table.shape[0]} 个分组类别和 {crosstab_table.shape[1]} 个目标类别。"
                )
            )
    return "\n".join(lines)


def _build_imbalanced_recommendation(column: str, top_row: pd.Series, language: str) -> str:
    option = top_row["response"]
    percentage = float(top_row["percentage"])
    if language == "en":
        return (
            f"`{column}` is strongly concentrated in `{option}` ({percentage:.2f}%). "
            "A distribution this concentrated can mean the sample is clustered around one subgroup, or that the current response options are not separating respondents clearly enough. "
            "Check whether the sample is sufficiently diverse and whether the wording or granularity of the options should be refined. "
            "A useful next step is to compare this question across demographic or behavioral variables to see whether the concentration is consistent across groups."
        )
    return (
        f"`{column}` 当前高度集中在 `{option}`，占比达到 {percentage:.2f}%。"
        " 这种过于集中的分布，可能意味着样本本身比较单一，也可能说明当前题目选项的区分度还不够强。"
        " 建议同时检查样本构成是否足够多样，以及选项设计是否需要进一步细化。"
        " 下一步可以把这道题与人口属性或行为变量做交叉分析，看看这种集中现象是否只出现在某些特定群体中。"
    )


def _build_scale_recommendation(column: str, row: pd.Series, language: str) -> str:
    mean_value = float(row["mean"])
    level = row["interpretation"]
    if language == "en":
        if level == "high":
            return (
                f"`{column}` has a relatively high average score ({mean_value:.2f}). "
                "This suggests respondents already view this area positively, so the practical goal is to maintain that strength and understand what is working well. "
                "Compare the item across subgroups to see where the strongest ratings come from, and read it together with open-ended comments to identify the concrete experiences behind the positive score."
            )
        if level == "moderate":
            return (
                f"`{column}` has a moderate average score ({mean_value:.2f}). "
                "This usually means the topic is not failing badly, but it also is not a clear strength yet. "
                "A good next step is to look for subgroup differences instead of relying only on the overall mean, and to interpret the scale result together with open-ended responses for additional context."
            )
        return (
            f"`{column}` has a relatively low average score ({mean_value:.2f}). "
            "This is a signal that the topic may need priority attention in the next round of analysis or action planning. "
            "Use demographic or behavioral cross-analysis to locate the groups with the weakest scores, and interpret the rating together with open-ended responses so the improvement direction is more concrete."
        )

    if level == "high":
        return (
            f"`{column}` 的平均分相对较高（{mean_value:.2f}）。"
            " 这通常说明受访者对这一方面的评价整体较积极，后续重点更适合放在保持优势并理解优势来源。"
            " 建议进一步比较不同群体的评分差异，同时结合开放题内容，看看高分背后对应的是哪些具体体验或因素。"
        )
    if level == "moderate":
        return (
            f"`{column}` 的平均分处于中等水平（{mean_value:.2f}）。"
            " 这往往意味着该议题没有明显失衡，但也尚未形成稳定优势。"
            " 建议不要只看总体平均分，而是进一步比较不同群体之间的差异，并结合开放题回答理解中等评分背后的真实原因。"
        )
    return (
        f"`{column}` 的平均分相对较低（{mean_value:.2f}）。"
        " 这提示该议题更值得优先关注，并在后续分析或改进方案中放到前面。"
        " 建议结合人口属性或行为变量定位低分最集中的群体，再结合开放题内容理解受访者为何会给出较低评价。"
    )


def _build_multiple_choice_recommendation(column: str, summary: pd.DataFrame, language: str) -> str:
    top_options = summary.head(3)
    formatted = ", ".join(f"{row.response} ({row.percentage:.2f}%)" for row in top_options.itertuples(index=False))
    if language == "en":
        return (
            f"For the multiple-choice question `{column}`, the most selected options are {formatted}. "
            "These top 2-3 options are usually the best starting point because they capture the clearest respondent priorities or behaviors. "
            "Focus follow-up interpretation on those leading options first, and then compare option preferences across groups to see whether different student segments or user types are choosing differently."
        )
    return (
        f"对于多选题 `{column}`，当前最常被选择的选项包括 {formatted}。"
        " 这些排名靠前的 2 到 3 个选项，通常最能代表受访者当前最明确的偏好、需求或行为特征。"
        " 建议先围绕这些核心选项做重点解读，再进一步比较不同群体在选项偏好上的差异，看看是否存在明显的分层现象。"
    )


def _build_open_ended_recommendation(open_columns: list[str], language: str) -> str:
    joined = ", ".join(f"`{column}`" for column in open_columns[:3])
    if language == "en":
        return (
            f"Open-ended questions such as {joined} should be used as a second layer of interpretation on top of the structured results. "
            "A practical workflow is to combine text summarization, keyword extraction, and light manual coding so repeated concerns and recurring themes can be surfaced reliably. "
            "These text responses often explain why people selected certain ratings or options, so they are especially helpful when you want to turn survey findings into concrete recommendations."
        )
    return (
        f"像 {joined} 这样的开放题，适合放在结构化结果之后作为第二层解释材料。"
        " 一个比较实用的做法，是把文本摘要、关键词提取和轻量人工编码结合起来，这样更容易稳定地识别高频主题和重复问题。"
        " 开放题往往能解释受访者为什么给出某个分值或选择某个选项，因此它对把问卷结果转化为具体建议特别有帮助。"
    )


def _build_missingness_recommendation(high_missing: pd.Series, language: str) -> str:
    joined = ", ".join(f"`{column}` ({rate * 100:.2f}%)" for column, rate in high_missing.head(3).items())
    if language == "en":
        return (
            f"Columns with higher missingness, such as {joined}, deserve a separate review before the findings are used heavily. "
            "A higher missing rate may mean the question was hard to understand, easy to skip, or not relevant to part of the sample. "
            "Check the wording, answer options, and survey flow for those items, and consider whether cleaning rules or follow-up data collection are needed."
        )
    return (
        f"缺失率较高的字段，例如 {joined}，建议在正式使用结论前单独复查。"
        " 缺失率偏高往往意味着题目不好理解、容易被跳过，或者对部分样本相关性不强。"
        " 可以回头检查这些题目的表述、选项设计和问卷流程，同时评估是否需要补充清洗规则或后续补充采集。"
    )


def _build_group_followup_recommendation(cross_analysis_result: dict[str, Any] | None, language: str) -> str:
    if language == "en":
        if cross_analysis_result and cross_analysis_result.get("analysis_type") != "unsupported":
            return (
                "The current group comparison should be treated as a starting point rather than the final conclusion. "
                "Try repeating the comparison with other profile, demographic, or behavioral variables so you can distinguish broad averages from subgroup-specific patterns. "
                "This kind of follow-up is often the fastest way to turn a descriptive survey result into a more actionable insight."
            )
        return (
            "After the first round of descriptive analysis, the next useful step is to run targeted group comparisons on the most important outcome variables. "
            "This helps you see whether the overall pattern is stable or whether it changes across student profiles, usage behaviors, or other respondent segments. "
            "Even a simple cross-analysis can make the final report much more practical and easier to explain."
        )
    if cross_analysis_result and cross_analysis_result.get("analysis_type") != "unsupported":
        return (
            "当前的分组比较更适合作为下一步分析的起点，而不是最终结论。"
            " 建议继续把关键指标与更多画像变量、人口属性或行为变量做比较，这样更容易区分“总体平均”与“群体差异”。"
            " 这类追加分析通常能最快把描述性结果转化为更有行动价值的结论。"
        )
    return (
        "完成第一轮描述性统计之后，下一步最值得做的是围绕关键结果变量继续补充分组比较。"
        " 这样可以帮助你判断总体模式是否稳定，还是只集中出现在某些学生群体或行为类型中。"
        " 即使是相对简单的交叉分析，也往往能显著提升报告的解释力和实用性。"
    )


def _build_generic_recommendation(language: str) -> str:
    if language == "en":
        return (
            "When presenting the findings, focus on a small number of questions that are most relevant to the survey objective instead of trying to discuss every field equally. "
            "A good presentation pattern is to combine one descriptive chart, one group comparison, and one short interpretation paragraph for each priority theme. "
            "This keeps the analysis readable for non-technical audiences while still showing clear analytical reasoning."
        )
    return (
        "在展示分析结果时，建议优先围绕与调查目标最相关的少数几个核心题目展开，而不是平均讨论所有字段。"
        " 一个比较实用的呈现方式，是每个重点主题都配一张描述性图表、一组分组比较，再加上一段简短解释。"
        " 这样既能让非技术受众更容易读懂，也能保留清晰的数据分析逻辑。"
    )


def _build_recommendations(
    df: pd.DataFrame,
    question_types: dict[str, str],
    descriptive_results: dict[str, Any],
    cross_analysis_result: dict[str, Any] | None,
    language: str,
) -> str:
    scale_summary = descriptive_results.get("scale_summary", pd.DataFrame())
    categorical_summary = descriptive_results.get("categorical_summary", {})
    missing_rates = df.isna().mean()
    high_missing = missing_rates[missing_rates > 0.1]

    recommendations: list[str] = []

    imbalanced_candidates = []
    for column, q_type in question_types.items():
        if q_type != QUESTION_TYPE_SINGLE:
            continue
        summary = categorical_summary.get(column)
        if summary is None or summary.empty:
            continue
        top_row = summary.iloc[0]
        if float(top_row["percentage"]) > 70:
            imbalanced_candidates.append((column, top_row))
    if imbalanced_candidates:
        column, top_row = sorted(imbalanced_candidates, key=lambda item: float(item[1]["percentage"]), reverse=True)[0]
        recommendations.append(_build_imbalanced_recommendation(column, top_row, language))

    if not scale_summary.empty:
        scale_priority = scale_summary.copy()
        order_map = {"low": 0, "moderate": 1, "high": 2}
        scale_priority["priority"] = scale_priority["interpretation"].map(order_map)
        best_scale = scale_priority.sort_values(["priority", "mean"]).iloc[0]
        recommendations.append(_build_scale_recommendation(best_scale.name, best_scale, language))

    multiple_choice_columns = [
        column
        for column, q_type in question_types.items()
        if q_type == QUESTION_TYPE_MULTIPLE and column in categorical_summary and not categorical_summary[column].empty
    ]
    if multiple_choice_columns:
        column = multiple_choice_columns[0]
        recommendations.append(_build_multiple_choice_recommendation(column, categorical_summary[column], language))

    open_columns = [column for column, q_type in question_types.items() if q_type == QUESTION_TYPE_OPEN]
    if open_columns:
        recommendations.append(_build_open_ended_recommendation(open_columns, language))

    if not high_missing.empty:
        recommendations.append(_build_missingness_recommendation(high_missing, language))

    recommendations.append(_build_group_followup_recommendation(cross_analysis_result, language))

    while len(recommendations) < 3:
        recommendations.append(_build_generic_recommendation(language))

    return _numbered(recommendations[:4])


def _build_limitations_text(df: pd.DataFrame, question_types: dict[str, str], language: str) -> str:
    lines = [
        _bullet(
            "This report is rule-based and still depends on automatic or manually corrected question-type detection."
            if language == "en"
            else "当前报告仍然基于规则生成，并依赖自动识别或手动修正后的题型结果。"
        ),
        _bullet(
            "The findings are descriptive and should not be treated as evidence of causality or statistical significance."
            if language == "en"
            else "当前发现主要属于描述性分析，不应直接视为因果关系或统计显著性的证据。"
        ),
        _bullet(
            "Multiple-choice parsing assumes the uploaded data uses relatively consistent delimiters."
            if language == "en"
            else "多选题的拆分目前默认上传数据中的分隔符使用相对一致。"
        ),
    ]

    open_ended_count = sum(1 for q_type in question_types.values() if q_type == QUESTION_TYPE_OPEN)
    if open_ended_count:
        lines.append(
            _bullet(
                f"{open_ended_count} open-ended question(s) were detected, but full text-theme summarization is still a placeholder in this MVP."
                if language == "en"
                else f"本次共识别出 {open_ended_count} 道开放题，但更完整的文本主题归纳仍然是后续版本的预留能力。"
            )
        )

    duplicate_rows = int(df.duplicated().sum())
    if duplicate_rows > 0:
        lines.append(
            _bullet(
                f"{duplicate_rows} duplicate row(s) were detected and may affect interpretation if they reflect repeated submissions."
                if language == "en"
                else f"当前检测到 {duplicate_rows} 行重复数据，如果它们来自重复提交，可能会影响结果解释。"
            )
        )

    return "\n".join(lines)


def generate_markdown_report(
    df: pd.DataFrame,
    question_types: dict[str, str],
    descriptive_results: dict[str, Any],
    cross_analysis_result: dict[str, Any] | None = None,
    language: str = "en",
) -> str:
    """Create a bilingual, dataset-agnostic questionnaire analysis report."""
    sections = [
        f"# {t(language, 'report_title')}",
        f"## {t(language, 'report_dataset_overview')}",
        _format_dataset_overview(df, language),
        f"## {t(language, 'report_data_quality')}",
        _format_data_quality_summary(df, question_types, language),
        f"## {t(language, 'question_type_summary_title')}",
        _format_question_type_summary(question_types, language),
        f"## {t(language, 'report_key_findings')}",
        _build_key_findings(df, question_types, descriptive_results, language),
        f"## {t(language, 'report_group_findings')}",
        _build_group_comparison_text(cross_analysis_result, language),
        f"## {t(language, 'report_recommendations')}",
        _build_recommendations(df, question_types, descriptive_results, cross_analysis_result, language),
        f"## {t(language, 'report_limitations')}",
        _build_limitations_text(df, question_types, language),
    ]
    return "\n\n".join(sections).strip() + "\n"


def generate_llm_enhanced_report(_: dict[str, Any]) -> str:
    """Placeholder for a future LLM-powered reporting workflow."""
    raise NotImplementedError("LLM report generation is not enabled in this MVP.")
