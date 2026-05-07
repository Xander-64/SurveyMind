from __future__ import annotations

import pandas as pd
import streamlit as st

from src.cross_analysis import analyze_cross_relationship
from src.data_loader import DEFAULT_DEMO_PATH, get_dataset_overview, load_demo_dataset, load_uploaded_dataset
from src.descriptive_analysis import generate_descriptive_results
from src.i18n import (
    DEFAULT_LANGUAGE,
    LANGUAGE_OPTIONS,
    get_language_label,
    t,
    translate_question_type,
    translate_scale_level,
)
from src.question_type_detector import (
    QUESTION_TYPE_NUMERIC,
    QUESTION_TYPE_OPEN,
    QUESTION_TYPE_SCALE,
    detect_question_types,
    get_question_type_options,
    question_types_to_frame,
)
from src.report_generator import generate_markdown_report
from src.visualization import (
    build_categorical_bar_chart,
    build_crosstab_chart,
    build_grouped_box_plot,
    build_numeric_histogram,
    build_scale_bar_chart,
)


if "language" not in st.session_state:
    st.session_state["language"] = DEFAULT_LANGUAGE

st.set_page_config(page_title=t(st.session_state["language"], "page_title"), page_icon="📊", layout="wide")


@st.cache_data
def get_demo_data():
    return load_demo_dataset()


@st.cache_data
def get_uploaded_data(file_bytes: bytes, filename: str):
    return load_uploaded_dataset(file_bytes, filename)


def load_active_dataset(uploaded_file):
    if uploaded_file is None:
        return get_demo_data(), True
    return get_uploaded_data(uploaded_file.getvalue(), uploaded_file.name), False


def get_language() -> str:
    return st.session_state.get("language", DEFAULT_LANGUAGE)


def render_sidebar() -> str:
    language = get_language()
    with st.sidebar:
        st.header(t(language, "sidebar_settings"))
        st.selectbox(
            label=t(language, "sidebar_language"),
            options=LANGUAGE_OPTIONS,
            format_func=get_language_label,
            key="language",
            help=t(language, "sidebar_language_help"),
        )
    return get_language()


def localize_question_type_frame(
    detected_question_types: dict[str, str],
    active_question_types: dict[str, str],
    language: str,
) -> pd.DataFrame:
    frame = question_types_to_frame(detected_question_types, active_question_types).copy()
    frame["detected_type"] = frame["detected_type"].map(lambda value: translate_question_type(language, value))
    frame["active_type"] = frame["active_type"].map(lambda value: translate_question_type(language, value))
    return frame.rename(
        columns={
            "column_name": t(language, "column_name_label"),
            "detected_type": t(language, "detected_type_label"),
            "active_type": t(language, "active_type_label"),
        }
    )


def localize_scale_summary(scale_summary: pd.DataFrame, language: str) -> pd.DataFrame:
    if scale_summary.empty:
        return scale_summary

    localized = scale_summary.copy()
    localized["interpretation"] = localized["interpretation"].map(lambda value: translate_scale_level(language, value))
    return localized.rename(columns={"interpretation": t(language, "label_interpretation")})


def render_intro(language: str):
    st.title(t(language, "app_title"))
    st.subheader(t(language, "app_subtitle"))
    st.write(t(language, "app_intro"))


def render_data_upload(language: str):
    st.header(t(language, "section_data_upload"))
    return st.file_uploader(
        t(language, "upload_label"),
        type=["csv", "xlsx", "xls"],
        help=t(language, "upload_help"),
    )


def render_data_overview(df, language: str):
    st.header(t(language, "section_data_overview"))
    overview = get_dataset_overview(df)

    col1, col2, col3 = st.columns(3)
    col1.metric(t(language, "metric_rows"), overview["shape"][0])
    col2.metric(t(language, "metric_columns"), overview["shape"][1])
    col3.metric(t(language, "metric_missing_ratio"), f"{df.isna().mean().mean() * 100:.2f}%")

    st.write(f"**{t(language, 'first_five_rows')}**")
    st.dataframe(overview["preview"], use_container_width=True)

    meta_col1, meta_col2 = st.columns([1, 2])
    with meta_col1:
        st.write(f"**{t(language, 'column_names')}**")
        st.dataframe({t(language, "column_name_label"): overview["columns"]}, use_container_width=True)
    with meta_col2:
        st.write(f"**{t(language, 'column_metadata')}**")
        st.dataframe(overview["overview_table"], use_container_width=True)


def render_question_detection(detected_question_types: dict[str, str], language: str) -> dict[str, str]:
    st.header(t(language, "section_question_detection"))
    st.write(t(language, "question_detection_desc"))

    if st.button(t(language, "reset_overrides")):
        for column, detected_type in detected_question_types.items():
            st.session_state[f"question_type_override::{column}"] = detected_type

    question_type_options = get_question_type_options()
    active_question_types: dict[str, str] = {}

    with st.expander(t(language, "manual_override"), expanded=False):
        override_columns = st.columns(2)
        for index, (column, detected_type) in enumerate(detected_question_types.items()):
            state_key = f"question_type_override::{column}"
            if state_key not in st.session_state:
                st.session_state[state_key] = detected_type

            with override_columns[index % 2]:
                active_question_types[column] = st.selectbox(
                    label=column,
                    options=question_type_options,
                    index=question_type_options.index(st.session_state[state_key]),
                    key=state_key,
                    format_func=lambda value: translate_question_type(language, value),
                    help=t(language, "detected_as_help", question_type=translate_question_type(language, detected_type)),
                )

    if not active_question_types:
        active_question_types = dict(detected_question_types)

    st.dataframe(
        localize_question_type_frame(detected_question_types, active_question_types, language),
        use_container_width=True,
    )
    return active_question_types


def render_descriptive_statistics(df, question_types, descriptive_results, language: str):
    st.header(t(language, "section_descriptive_stats"))

    numeric_summary = descriptive_results["numeric_summary"]
    scale_summary = descriptive_results["scale_summary"]
    scale_distributions = descriptive_results["scale_distributions"]
    categorical_summary = descriptive_results["categorical_summary"]
    sample_profile = descriptive_results["sample_profile"]

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            t(language, "tab_numeric"),
            t(language, "tab_scale"),
            t(language, "tab_categorical"),
            t(language, "tab_profile"),
        ]
    )

    with tab1:
        if numeric_summary.empty:
            st.info(t(language, "no_numeric"))
        else:
            st.dataframe(numeric_summary, use_container_width=True)

    with tab2:
        if scale_summary.empty:
            st.info(t(language, "no_scale"))
        else:
            st.dataframe(localize_scale_summary(scale_summary, language), use_container_width=True)
            selected_scale = st.selectbox(
                t(language, "choose_scale_question"),
                list(scale_summary.index),
                key="scale_summary_column",
            )
            distribution_df = scale_distributions[selected_scale]
            st.write(f"**{t(language, 'scale_distribution')}**")
            st.dataframe(distribution_df, use_container_width=True)
            fig = build_scale_bar_chart(distribution_df, selected_scale, display_mode="percentage", language=language)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)

    with tab3:
        if not categorical_summary:
            st.info(t(language, "no_categorical"))
        else:
            selected_column = st.selectbox(
                t(language, "choose_categorical_question"),
                list(categorical_summary.keys()),
                key="categorical_summary_column",
            )
            st.dataframe(categorical_summary[selected_column], use_container_width=True)

    with tab4:
        if sample_profile.empty:
            st.info(t(language, "no_profile"))
        else:
            st.dataframe(sample_profile, use_container_width=True)


def render_visualization_explorer(df, question_types, descriptive_results, language: str):
    st.header(t(language, "section_visualization"))

    numeric_columns = [col for col, q_type in question_types.items() if q_type == QUESTION_TYPE_NUMERIC]
    scale_columns = [col for col, q_type in question_types.items() if q_type == QUESTION_TYPE_SCALE]
    metric_columns = [col for col, q_type in question_types.items() if q_type in {QUESTION_TYPE_NUMERIC, QUESTION_TYPE_SCALE}]
    categorical_columns = [
        col for col, q_type in question_types.items() if q_type not in {QUESTION_TYPE_NUMERIC, QUESTION_TYPE_SCALE, QUESTION_TYPE_OPEN}
    ]

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            t(language, "chart_tab_categorical"),
            t(language, "chart_tab_scale"),
            t(language, "chart_tab_numeric"),
            t(language, "chart_tab_box"),
        ]
    )

    with tab1:
        if categorical_columns:
            column = st.selectbox(t(language, "categorical_variable"), categorical_columns, key="bar_chart_column")
            display_mode = st.radio(
                t(language, "display_mode"),
                options=["percentage", "count"],
                index=0,
                horizontal=True,
                format_func=lambda value: t(language, f"display_{value}"),
                key="categorical_display_mode",
            )
            fig = build_categorical_bar_chart(df, column, question_types[column], display_mode=display_mode, language=language)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(t(language, "no_categorical_chart"))

    with tab2:
        if scale_columns:
            column = st.selectbox(t(language, "scale_variable"), scale_columns, key="scale_chart_column")
            display_mode = st.radio(
                t(language, "display_mode"),
                options=["percentage", "count"],
                index=0,
                horizontal=True,
                format_func=lambda value: t(language, f"display_{value}"),
                key="scale_display_mode",
            )
            distribution_df = descriptive_results["scale_distributions"][column]
            fig = build_scale_bar_chart(distribution_df, column, display_mode=display_mode, language=language)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(t(language, "no_scale_chart"))

    with tab3:
        if numeric_columns:
            column = st.selectbox(t(language, "numeric_variable"), numeric_columns, key="histogram_column")
            fig = build_numeric_histogram(df, column, language=language)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(t(language, "no_numeric_chart"))

    with tab4:
        if metric_columns and categorical_columns:
            numeric_column = st.selectbox(
                t(language, "numeric_or_scale_variable"),
                metric_columns,
                key="box_numeric",
            )
            group_column = st.selectbox(t(language, "grouping_variable"), categorical_columns, key="box_group")
            fig = build_grouped_box_plot(df, numeric_column, group_column, language=language)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(t(language, "boxplot_requirement"))


def render_cross_analysis(df, question_types, language: str):
    st.header(t(language, "section_cross_analysis"))
    group_options = [
        col for col, q_type in question_types.items() if q_type not in {QUESTION_TYPE_NUMERIC, QUESTION_TYPE_SCALE, QUESTION_TYPE_OPEN}
    ]
    target_options = [col for col, q_type in question_types.items() if q_type != QUESTION_TYPE_OPEN]

    if not group_options or len(target_options) < 2:
        st.info(t(language, "cross_analysis_requirement"))
        return None

    col1, col2 = st.columns(2)
    with col1:
        group_col = st.selectbox(t(language, "grouping_variable"), group_options, key="cross_group")
    with col2:
        remaining_targets = [col for col in target_options if col != group_col]
        target_col = st.selectbox(t(language, "target_variable"), remaining_targets, key="cross_target")

    result = analyze_cross_relationship(df, group_col, target_col, question_types, language=language)

    if result["analysis_type"] == "unsupported":
        st.warning(result.get("message", t(language, "cross_open_ended_warning")))
        return result

    if result["analysis_type"] == "numeric_by_group":
        st.write(f"**{t(language, 'grouped_summary_stats')}**")
        st.dataframe(result["summary_table"], use_container_width=True)
        st.info(result["interpretation"])
    else:
        display_mode = st.radio(
            t(language, "cross_display_mode"),
            options=["row_percentage", "raw_count", "column_percentage"],
            index=0,
            horizontal=True,
            format_func=lambda value: {
                "raw_count": t(language, "cross_raw_count"),
                "row_percentage": t(language, "cross_row_percentage"),
                "column_percentage": t(language, "cross_column_percentage"),
            }[value],
        )
        table_lookup = {
            "raw_count": result["crosstab_table"],
            "row_percentage": result["row_percentage_table"],
            "column_percentage": result["column_percentage_table"],
        }
        mode_label = {
            "raw_count": t(language, "cross_raw_count"),
            "row_percentage": t(language, "cross_row_percentage"),
            "column_percentage": t(language, "cross_column_percentage"),
        }[display_mode]
        st.write(f"**{t(language, 'cross_table_title', mode=mode_label)}**")
        st.dataframe(table_lookup[display_mode], use_container_width=True)
        chart_mode = st.radio(
            t(language, "cross_chart_type"),
            options=["stacked", "heatmap"],
            horizontal=True,
            format_func=lambda value: t(language, f"chart_type_{value}"),
        )
        fig = build_crosstab_chart(
            table_lookup[display_mode],
            chart_type=chart_mode,
            display_mode=display_mode,
            language=language,
        )
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        st.info(result["interpretation"])

    return result


def render_report(df, question_types, descriptive_results, cross_analysis_result, language: str):
    st.header(t(language, "section_report"))
    report_markdown = generate_markdown_report(
        df,
        question_types,
        descriptive_results,
        cross_analysis_result,
        language=language,
    )
    st.markdown(report_markdown)
    st.download_button(
        label=t(language, "download_report"),
        data=report_markdown,
        file_name=t(language, "download_report_filename"),
        mime="text/markdown",
    )
    return report_markdown


def main():
    language = render_sidebar()
    render_intro(language)
    uploaded_file = render_data_upload(language)
    df, using_demo = load_active_dataset(uploaded_file)

    if using_demo:
        st.caption(t(language, "using_demo_caption", filename=DEFAULT_DEMO_PATH.name))
    else:
        st.caption(t(language, "using_upload_caption", filename=uploaded_file.name))

    render_data_overview(df, language)
    detected_question_types = detect_question_types(df)
    question_types = render_question_detection(detected_question_types, language)
    descriptive_results = generate_descriptive_results(df, question_types)
    render_descriptive_statistics(df, question_types, descriptive_results, language)
    render_visualization_explorer(df, question_types, descriptive_results, language)
    cross_analysis_result = render_cross_analysis(df, question_types, language)
    render_report(df, question_types, descriptive_results, cross_analysis_result, language)


if __name__ == "__main__":
    main()
