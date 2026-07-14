from __future__ import annotations

from typing import Any

import pandas as pd

from src.field_semantics import (
    FIELD_ROLE_BOOLEAN,
    FIELD_ROLE_CATEGORICAL,
    FIELD_ROLE_MULTI_VALUE,
    FIELD_ROLE_NUMERIC,
    FieldProfile,
)


CHART_TIME_TREND = "time_trend"
CHART_CORRELATION_HEATMAP = "correlation_heatmap"
CHART_GROUPED_BOX = "grouped_box"
CHART_NUMERIC_HISTOGRAM = "numeric_histogram"
CHART_CATEGORICAL_BAR = "categorical_bar"


def recommend_charts(
    df: pd.DataFrame,
    semantics: dict[str, FieldProfile],
    overview: dict[str, Any],
    max_charts: int = 4,
) -> list[dict[str, Any]]:
    """Pick chart specs that match the detected field roles and findings."""
    specs: list[dict[str, Any]] = []

    numeric_columns = [c for c, p in semantics.items() if p.role == FIELD_ROLE_NUMERIC]

    time_trends = overview.get("time_trends") or {}
    for column, trend in time_trends.items():
        if isinstance(trend, pd.DataFrame) and len(trend) >= 2:
            specs.append({"kind": CHART_TIME_TREND, "column": column})
            break

    correlations = overview.get("correlations")
    if isinstance(correlations, pd.DataFrame) and not correlations.empty and len(numeric_columns) >= 2:
        specs.append({"kind": CHART_CORRELATION_HEATMAP, "columns": numeric_columns[:10]})

    group_differences = overview.get("group_differences")
    if isinstance(group_differences, pd.DataFrame) and not group_differences.empty:
        top = group_differences.iloc[0]
        specs.append(
            {
                "kind": CHART_GROUPED_BOX,
                "numeric_column": top["metric_field"],
                "group_column": top["group_field"],
            }
        )

    numeric_summary = overview.get("numeric_summary")
    if isinstance(numeric_summary, pd.DataFrame) and not numeric_summary.empty:
        spread = (numeric_summary["std"] / numeric_summary["mean"].abs().replace(0, 1)).abs()
        specs.append({"kind": CHART_NUMERIC_HISTOGRAM, "column": spread.sort_values(ascending=False).index[0]})

    categorical_candidates = [
        (column, profile)
        for column, profile in semantics.items()
        if profile.role in {FIELD_ROLE_CATEGORICAL, FIELD_ROLE_BOOLEAN, FIELD_ROLE_MULTI_VALUE}
        and 2 <= profile.unique_count <= 15
    ]
    if categorical_candidates:
        column, profile = max(categorical_candidates, key=lambda item: item[1].unique_count)
        specs.append(
            {
                "kind": CHART_CATEGORICAL_BAR,
                "column": column,
                "is_multi_value": profile.role == FIELD_ROLE_MULTI_VALUE,
            }
        )

    return specs[:max_charts]
