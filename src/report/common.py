"""Formatting helpers shared by every report structure."""
from __future__ import annotations

from typing import Any

import pandas as pd


def _bullet(text: str) -> str:
    return f"- {text}"


def _numbered(items: list[str]) -> str:
    return "\n\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))


def _to_python_scalar(value: Any) -> Any:
    """Convert pandas / numpy scalars into JSON-friendly Python values."""
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            return value
    return value


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


def _df_to_markdown_table(frame: pd.DataFrame, index_label: str = "", max_rows: int = 15) -> str:
    """Render a DataFrame as a GitHub-style markdown table without extra deps."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return ""
    display = frame.head(max_rows)
    include_index = bool(index_label) or not isinstance(display.index, pd.RangeIndex)
    headers = ([index_label or ""] if include_index else []) + [str(col) for col in display.columns]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for index, row in display.iterrows():
        cells = ([str(index)] if include_index else []) + [str(value) for value in row.tolist()]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


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
