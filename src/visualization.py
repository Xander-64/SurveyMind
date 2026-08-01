from __future__ import annotations

import pandas as pd
import plotly.express as px

from src.descriptive_analysis import summarize_categorical_question
from src.i18n import t


def build_categorical_bar_chart(
    df: pd.DataFrame,
    column: str,
    question_type: str,
    display_mode: str = "percentage",
    language: str = "en",
):
    summary = summarize_categorical_question(df[column], question_type)
    y_column = "percentage" if display_mode == "percentage" else "count"
    y_label = t(language, "label_percentage") if display_mode == "percentage" else t(language, "label_count")
    text_template = "%{text:.2f}%" if display_mode == "percentage" else "%{text}"
    fig = px.bar(
        summary,
        x="response",
        y=y_column,
        text=y_column,
        title=t(language, "plot_distribution_of", column=column),
        labels={"response": t(language, "label_response"), y_column: y_label},
        hover_data={"count": True, "percentage": True},
    )
    fig.update_traces(texttemplate=text_template, textposition="outside")
    fig.update_layout(xaxis_tickangle=-25, yaxis_title=y_label)
    return fig


def build_scale_bar_chart(
    distribution_df: pd.DataFrame,
    column: str,
    display_mode: str = "percentage",
    language: str = "en",
):
    if distribution_df.empty:
        return None

    y_column = "percentage" if display_mode == "percentage" else "count"
    y_label = t(language, "label_percentage") if display_mode == "percentage" else t(language, "label_count")
    text_template = "%{text:.2f}%" if display_mode == "percentage" else "%{text}"
    fig = px.bar(
        distribution_df,
        x="score",
        y=y_column,
        text=y_column,
        title=t(language, "plot_score_distribution", column=column),
        labels={"score": t(language, "label_score"), y_column: y_label},
        hover_data={"count": True, "percentage": True},
    )
    fig.update_traces(texttemplate=text_template, textposition="outside")
    fig.update_layout(yaxis_title=y_label)
    return fig


def build_numeric_histogram(df: pd.DataFrame, column: str, language: str = "en"):
    fig = px.histogram(
        df,
        x=column,
        nbins=20,
        title=t(language, "plot_histogram_of", column=column),
        labels={column: column},
    )
    fig.update_layout(bargap=0.08)
    return fig


def build_grouped_box_plot(df: pd.DataFrame, numeric_column: str, group_column: str, language: str = "en"):
    plot_df = df[[numeric_column, group_column]].dropna()
    fig = px.box(
        plot_df,
        x=group_column,
        y=numeric_column,
        points="outliers",
        title=t(language, "plot_boxplot_of", numeric_column=numeric_column, group_column=group_column),
        labels={group_column: group_column, numeric_column: numeric_column},
    )
    fig.update_layout(xaxis_tickangle=-20)
    return fig


def build_correlation_heatmap(df: pd.DataFrame, numeric_columns: list[str], language: str = "en"):
    usable = [column for column in numeric_columns if column in df.columns]
    if len(usable) < 2:
        return None

    corr_matrix = df[usable].apply(pd.to_numeric, errors="coerce").corr().round(2)
    if corr_matrix.empty:
        return None

    fig = px.imshow(
        corr_matrix,
        text_auto=True,
        aspect="auto",
        color_continuous_scale="RdBu",
        zmin=-1,
        zmax=1,
        title=t(language, "plot_correlation_heatmap"),
    )
    return fig


def build_time_trend_chart(trend_df: pd.DataFrame, column: str, language: str = "en"):
    if trend_df is None or trend_df.empty:
        return None

    fig = px.line(
        trend_df,
        x="period",
        y="count",
        markers=True,
        title=t(language, "plot_time_trend", column=column),
        labels={
            "period": t(language, "label_period"),
            "count": t(language, "label_record_count"),
        },
    )
    fig.update_layout(xaxis_tickangle=-30)
    return fig


def build_crosstab_chart(
    crosstab_df: pd.DataFrame,
    chart_type: str = "stacked",
    display_mode: str = "row_percentage",
    language: str = "en",
):
    if crosstab_df.empty:
        return None

    y_label = {
        "raw_count": t(language, "label_count"),
        "row_percentage": t(language, "label_row_percentage"),
        "column_percentage": t(language, "label_column_percentage"),
    }[display_mode]

    display_mode_label = {
        "raw_count": t(language, "cross_raw_count"),
        "row_percentage": t(language, "cross_row_percentage"),
        "column_percentage": t(language, "cross_column_percentage"),
    }[display_mode]

    if chart_type == "heatmap":
        fig = px.imshow(
            crosstab_df,
            text_auto=True,
            aspect="auto",
            color_continuous_scale="Blues",
            title=t(language, "plot_heatmap_title", mode=display_mode_label),
        )
        fig.update_layout(
            xaxis_title=t(language, "label_target_variable"),
            yaxis_title=t(language, "label_grouping_variable"),
        )
        return fig

    plot_df = crosstab_df.reset_index().rename(columns={crosstab_df.index.name or "index": "group"})
    melted = plot_df.melt(id_vars="group", var_name="target", value_name="value")
    fig = px.bar(
        melted,
        x="group",
        y="value",
        color="target",
        barmode="stack",
        title=t(language, "plot_stacked_title", mode=display_mode_label),
        labels={
            "group": t(language, "label_grouping_variable"),
            "value": y_label,
            "target": t(language, "label_target_variable"),
        },
    )
    fig.update_layout(xaxis_tickangle=-20, yaxis_title=y_label)
    return fig
