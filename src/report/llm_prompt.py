"""Structured dataset summary and prompt builder for LLM-based reporting."""
from __future__ import annotations

from typing import Any
import json

from pandas.api.types import is_numeric_dtype
import pandas as pd

from src.report.common import _to_python_scalar


def build_dataset_summary(df: pd.DataFrame) -> dict[str, Any]:
    """Build a compact structured summary for LLM-based report generation."""
    dataset_summary: dict[str, Any] = {
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "average_missing_ratio": round(float(df.isna().mean().mean()), 4) if len(df.columns) else 0.0,
        "columns": {},
    }

    for column in df.columns:
        series = df[column]
        non_null_count = int(series.notna().sum())
        missing_count = int(series.isna().sum())

        column_summary: dict[str, Any] = {
            "dtype": str(series.dtype),
            "non_null_count": non_null_count,
            "missing_count": missing_count,
        }

        coerced_numeric = pd.to_numeric(series, errors="coerce")
        numeric_series = coerced_numeric.dropna()
        numeric_ratio = len(numeric_series) / non_null_count if non_null_count else 0

        if is_numeric_dtype(series) or numeric_ratio >= 0.9:
            column_summary["data_kind"] = "numeric"
            column_summary.update(
                {
                    "mean": round(float(numeric_series.mean()), 4) if not numeric_series.empty else None,
                    "median": round(float(numeric_series.median()), 4) if not numeric_series.empty else None,
                    "std": round(float(numeric_series.std()), 4) if not numeric_series.empty else None,
                    "min": round(float(numeric_series.min()), 4) if not numeric_series.empty else None,
                    "max": round(float(numeric_series.max()), 4) if not numeric_series.empty else None,
                }
            )
        else:
            top_values = series.dropna().astype(str).value_counts().head(10)
            column_summary["data_kind"] = "categorical"
            column_summary["top_values"] = [
                {
                    "value": str(index),
                    "count": int(count),
                }
                for index, count in top_values.items()
            ]

        dataset_summary["columns"][str(column)] = column_summary

    return dataset_summary


def build_llm_prompt(summary: dict[str, Any]) -> str:
    """Create a Chinese prompt that constrains the local model to interpretation only."""
    summary_json = json.dumps(summary, ensure_ascii=False, indent=2, default=_to_python_scalar)
    return f"""你是一名中文问卷分析师。请基于下面给出的结构化统计摘要，生成一份中文 Markdown 问卷分析报告。

严格要求：
1. 只能使用提供的统计摘要进行解释，不得编造任何数据。
2. 不要重新计算原始数据，不要假装看过原始问卷或样本明细。
3. 如果某列只有缺失情况或高频值信息，就只按这些信息解读。
4. 不要做因果推断、群体动机推断或超出数据证据的结论。
5. 如果信息不足，请直接说明“根据当前统计摘要无法进一步判断”。
6. 输出语言必须是中文。

请按以下结构输出：
- # 问卷分析报告
- ## 整体概览
- ## 逐字段分析
- ## 数据质量提醒
- ## 总结建议

写作要求：
- 语气专业、克制、清晰。
- 可以指出分布集中、缺失较多、均值高低、波动大小等现象。
- 建议部分必须建立在已提供统计摘要之上，不能引入不存在的数据结论。

以下是结构化统计摘要：
```json
{summary_json}
```"""
