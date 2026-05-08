from __future__ import annotations

import pandas as pd

from src.question_type_detector import (
    MULTI_CHOICE_PATTERN,
    QUESTION_TYPE_MULTIPLE,
    QUESTION_TYPE_NUMERIC,
    QUESTION_TYPE_OPEN,
    QUESTION_TYPE_SCALE,
    QUESTION_TYPE_SINGLE,
)


def split_multi_choice_series(series: pd.Series) -> pd.Series:
    """Split delimited multi-select responses into a long-format series."""
    cleaned = series.dropna().astype(str).str.strip()
    if cleaned.empty:
        return pd.Series(dtype="object")

    exploded = (
        cleaned.str.split(MULTI_CHOICE_PATTERN)
        .explode()
        .astype(str)
        .str.strip()
    )
    return exploded[exploded != ""]


def summarize_numeric_questions(df: pd.DataFrame, question_types: dict[str, str]) -> pd.DataFrame:
    numeric_columns = [col for col, q_type in question_types.items() if q_type == QUESTION_TYPE_NUMERIC]
    if not numeric_columns:
        return pd.DataFrame()

    summary = df[numeric_columns].describe(percentiles=[0.25, 0.5, 0.75]).T
    summary = summary.rename(columns={"50%": "median", "25%": "q1", "75%": "q3"})
    ordered_columns = ["count", "mean", "median", "std", "min", "q1", "q3", "max"]
    return summary[ordered_columns].round(2)


def interpret_scale_mean(mean_value: float) -> str:
    """Convert an average score into a simple low / medium / high interpretation."""
    if mean_value < 2.5:
        return "low"
    if mean_value <= 3.5:
        return "moderate"
    return "high"


def coerce_scale_scores(series: pd.Series) -> pd.Series:
    """Convert Likert-style responses such as "5分" into numeric scores."""
    extracted_scores = series.astype("string").str.extract(r"([-+]?\d+(?:\.\d+)?)", expand=False)
    return pd.to_numeric(extracted_scores, errors="coerce")


def summarize_scale_questions(df: pd.DataFrame, question_types: dict[str, str]) -> pd.DataFrame:
    scale_columns = [col for col, q_type in question_types.items() if q_type == QUESTION_TYPE_SCALE]
    if not scale_columns:
        return pd.DataFrame()

    rows: list[dict[str, float | str]] = []
    row_index: list[str] = []
    for column in scale_columns:
        cleaned = coerce_scale_scores(df[column]).dropna()
        if cleaned.empty:
            continue

        rows.append(
            {
                "count": float(cleaned.count()),
                "mean": cleaned.mean(),
                "median": cleaned.median(),
                "std": cleaned.std(),
                "interpretation": interpret_scale_mean(cleaned.mean()),
            }
        )
        row_index.append(column)

    if not rows:
        return pd.DataFrame()

    summary = pd.DataFrame(rows, index=row_index)
    numeric_columns = ["count", "mean", "median", "std"]
    summary[numeric_columns] = summary[numeric_columns].round(2)
    return summary


def summarize_scale_distribution(series: pd.Series) -> pd.DataFrame:
    cleaned = coerce_scale_scores(series).dropna()
    if cleaned.empty:
        return pd.DataFrame(columns=["score", "count", "percentage"])

    rounded_scores = cleaned.round().astype(int)
    distribution = rounded_scores.value_counts().sort_index().rename_axis("score").reset_index(name="count")
    distribution["percentage"] = (distribution["count"] / distribution["count"].sum() * 100).round(2)
    return distribution


def summarize_scale_distributions(
    df: pd.DataFrame, question_types: dict[str, str]
) -> dict[str, pd.DataFrame]:
    distributions: dict[str, pd.DataFrame] = {}
    for column, q_type in question_types.items():
        if q_type == QUESTION_TYPE_SCALE:
            distributions[column] = summarize_scale_distribution(df[column])
    return distributions


def summarize_categorical_question(series: pd.Series, question_type: str) -> pd.DataFrame:
    if question_type == QUESTION_TYPE_MULTIPLE:
        values = split_multi_choice_series(series)
        total = max(len(values), 1)
        frequency = values.value_counts().rename_axis("response").reset_index(name="count")
    else:
        values = series.fillna("Missing").astype(str)
        total = max(len(values), 1)
        frequency = values.value_counts().rename_axis("response").reset_index(name="count")

    frequency["percentage"] = (frequency["count"] / total * 100).round(2)
    return frequency


def summarize_categorical_questions(
    df: pd.DataFrame, question_types: dict[str, str]
) -> dict[str, pd.DataFrame]:
    summaries: dict[str, pd.DataFrame] = {}
    for column, q_type in question_types.items():
        if q_type in {QUESTION_TYPE_SINGLE, QUESTION_TYPE_MULTIPLE}:
            summaries[column] = summarize_categorical_question(df[column], q_type)
    return summaries


def build_sample_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Create a compact respondent profile summary for common survey dimensions."""
    profile_columns = [
        column
        for column in ["gender", "grade", "major_type", "fitness_goal", "bookkeeping_habit"]
        if column in df.columns
    ]

    rows: list[dict[str, str | int | float]] = []
    for column in profile_columns:
        counts = df[column].fillna("Missing").astype(str).value_counts(normalize=True).mul(100).round(2)
        if counts.empty:
            continue
        top_response = counts.index[0]
        rows.append(
            {
                "column_name": column,
                "top_response": top_response,
                "top_response_pct": counts.iloc[0],
                "distinct_responses": int(df[column].nunique(dropna=True)),
            }
        )

    return pd.DataFrame(rows)


def generate_descriptive_results(df: pd.DataFrame, question_types: dict[str, str]) -> dict[str, object]:
    """Bundle descriptive outputs used across the app and report generator."""
    return {
        "numeric_summary": summarize_numeric_questions(df, question_types),
        "scale_summary": summarize_scale_questions(df, question_types),
        "scale_distributions": summarize_scale_distributions(df, question_types),
        "categorical_summary": summarize_categorical_questions(df, question_types),
        "sample_profile": build_sample_profile(df),
        "question_counts": pd.Series(question_types).value_counts().rename_axis("question_type").reset_index(name="count"),
    }
