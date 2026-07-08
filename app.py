from __future__ import annotations

import html
import re
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile

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
from src.llm_client import ask_llm, is_llm_configured
from src.preprocessing import is_metadata_column, preprocess_input_dataframe

# Load .env so LLM_API_KEY etc. are available (optional convenience dependency).
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass
from src.question_type_detector import (
    QUESTION_TYPE_EMPTY,
    QUESTION_TYPE_MULTIPLE,
    QUESTION_TYPE_NUMERIC,
    QUESTION_TYPE_OPEN,
    QUESTION_TYPE_SCALE,
    QUESTION_TYPE_SINGLE,
    detect_question_types,
    get_question_type_options,
    question_types_to_frame,
)
from src.report_generator import build_dataset_summary, build_llm_prompt, generate_markdown_report
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


SUPPORTED_UPLOAD_SUFFIXES = {".csv", ".xlsx", ".xls"}


@st.cache_data
def get_demo_data():
    return preprocess_input_dataframe(load_demo_dataset())


@st.cache_data
def get_uploaded_data(file_bytes: bytes, filename: str):
    # Loading (incl. the tolerant-CSV fallback) and cleaning both live in src/
    # so the API layer produces byte-identical results to the Streamlit app.
    return preprocess_input_dataframe(load_uploaded_dataset(file_bytes, filename))


def get_upload_error_message(exc: Exception) -> str:
    if isinstance(exc, pd.errors.EmptyDataError):
        return "The uploaded file is empty. Please upload a non-empty CSV or Excel file."
    if isinstance(exc, ValueError) and "No usable survey columns remain" in str(exc):
        return "No usable survey columns remain after preprocessing. Please upload a file with survey response columns."
    if isinstance(exc, ValueError) and "Unsupported file type" in str(exc):
        return "Unsupported file type. Please upload a CSV or Excel file."
    if isinstance(exc, (BadZipFile, UnicodeDecodeError, OSError, ValueError, ImportError)):
        return "The uploaded file appears to be corrupted or unreadable. Please upload a valid CSV or Excel file."
    return "Something went wrong while reading the uploaded file. Please try another file."


def load_active_dataset(uploaded_file):
    try:
        if uploaded_file is None:
            return get_demo_data(), True

        suffix = Path(uploaded_file.name).suffix.lower()
        if suffix not in SUPPORTED_UPLOAD_SUFFIXES:
            st.error("Unsupported file type. Please upload a CSV or Excel file.")
            return None, False

        file_bytes = uploaded_file.getvalue()
        if not file_bytes:
            st.error("The uploaded file is empty. Please upload a non-empty CSV or Excel file.")
            return None, False
        return get_uploaded_data(file_bytes, uploaded_file.name), False
    except Exception as exc:
        st.error(get_upload_error_message(exc))
        return None, False


def get_language() -> str:
    return st.session_state.get("language", DEFAULT_LANGUAGE)


def has_display_data(data) -> bool:
    if data is None:
        return False
    if isinstance(data, (pd.DataFrame, pd.Series)):
        return not data.empty
    if isinstance(data, dict):
        return bool(data)
    if isinstance(data, (list, tuple, set, str)):
        return len(data) > 0
    return True


def render_dataframe_or_warning(data, empty_message: str, error_message: str | None = None) -> bool:
    if not has_display_data(data):
        st.warning(empty_message)
        return False

    try:
        st.dataframe(data, use_container_width=True)
        return True
    except Exception:
        st.warning(error_message or empty_message)
        return False


def render_plotly_chart_safely(build_figure, empty_message: str, error_message: str, chart_key: str) -> bool:
    try:
        fig = build_figure()
    except Exception:
        st.warning(error_message)
        return False

    if fig is None:
        st.warning(empty_message)
        return False

    try:
        st.plotly_chart(fig, use_container_width=True, key=chart_key)
        return True
    except Exception:
        st.warning(error_message)
        return False


# --- Visual theme ported from the Claude Design mockup -----------------------
# Colors, fonts, card styling, spacing, and the five question-type badge colors
# come from design/SurveyMind 数据分析界面.html. This only affects presentation;
# the analysis logic in src/ is untouched.
THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Albert+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {
  --sm-bg:#FAFBFC; --sm-surface:#FFFFFF; --sm-surface-3:#F1F4F8;
  --sm-ink:#1A1F29; --sm-ink-2:#4A5260; --sm-ink-3:#6B7280; --sm-muted:#8A92A0;
  --sm-accent:#3E5C99; --sm-accent-700:#2B4475;
  --sm-accent-soft:#ECF1F9; --sm-accent-line:#C2D1EA;
  --sm-line:#EAEDF1; --sm-line-2:#E0E4EA;
  --sm-r-md:12px; --sm-r-sm:6px;
  --sm-sh:0 1px 2px rgba(20,30,50,.04), 0 4px 10px -2px rgba(20,30,50,.05);
}

html, body, .stApp, [data-testid="stAppViewContainer"],
[data-testid="stMarkdownContainer"], .stMarkdown, button, input, textarea, select {
  font-family:'Albert Sans',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
}
.stApp { background:var(--sm-bg); color:var(--sm-ink); }
.block-container { padding-top:2.4rem; padding-bottom:3rem; }

h1, h2, h3 { color:var(--sm-ink); font-weight:700; letter-spacing:-0.01em; }
/* Accent rule on section headers for the design's structured feel */
[data-testid="stHeading"] h2 {
  border-left:3px solid var(--sm-accent);
  padding-left:12px; margin-top:.5rem;
}

code, pre, kbd, [data-testid="stCodeBlock"], .stCode {
  font-family:'IBM Plex Mono','SF Mono',ui-monospace,monospace;
}

/* Metric cards */
[data-testid="stMetric"] {
  background:var(--sm-surface); border:1px solid var(--sm-line);
  border-radius:var(--sm-r-md); padding:14px 18px; box-shadow:var(--sm-sh);
}
[data-testid="stMetricValue"] { color:var(--sm-accent); font-weight:700; }
[data-testid="stMetricLabel"] { color:var(--sm-ink-3); }

/* Sidebar as a clean white surface */
[data-testid="stSidebar"] {
  background:var(--sm-surface); border-right:1px solid var(--sm-line);
}

/* Expanders and tables as cards */
[data-testid="stExpander"] {
  border:1px solid var(--sm-line); border-radius:var(--sm-r-md);
  background:var(--sm-surface); box-shadow:var(--sm-sh);
}
[data-testid="stDataFrame"] {
  border:1px solid var(--sm-line); border-radius:var(--sm-r-md); overflow:hidden;
}

/* Primary buttons */
.stButton > button {
  background:var(--sm-accent); color:#fff; font-weight:600;
  border:1px solid var(--sm-accent); border-radius:var(--sm-r-sm);
}
.stButton > button:hover { background:var(--sm-accent-700); border-color:var(--sm-accent-700); color:#fff; }
.stDownloadButton > button {
  background:var(--sm-accent-soft); color:var(--sm-accent-700); font-weight:600;
  border:1px solid var(--sm-accent-line); border-radius:var(--sm-r-sm);
}
.stDownloadButton > button:hover { background:#E0E9F6; color:var(--sm-accent-700); }

/* Tabs accent */
.stTabs [data-baseweb="tab-list"] { gap:4px; }
.stTabs [aria-selected="true"] { color:var(--sm-accent); }

/* Question-type badges (five categories) */
.sm-badges { display:flex; flex-wrap:wrap; gap:8px; margin:.4rem 0 1rem; }
.sm-badge {
  display:inline-flex; align-items:center; gap:6px;
  font-size:12px; font-weight:600; padding:5px 11px;
  border-radius:7px; white-space:nowrap; line-height:1.5;
}
.sm-badge .sm-dot { width:6px; height:6px; border-radius:50%; flex:none; }
.sm-badge .sm-type { font-weight:500; opacity:.8; }
.sm-badge.num    { background:#E9EFFB; color:#2F569E; } .sm-badge.num    .sm-dot { background:#3E5C99; }
.sm-badge.scale  { background:#E0F0EA; color:#1C7355; } .sm-badge.scale  .sm-dot { background:#2A8C6A; }
.sm-badge.single { background:#ECE8FA; color:#5B45A8; } .sm-badge.single .sm-dot { background:#6B54BE; }
.sm-badge.multi  { background:#FBEFD9; color:#8A5A12; } .sm-badge.multi  .sm-dot { background:#C68A2E; }
.sm-badge.open   { background:#FAE7EC; color:#9C4763; } .sm-badge.open   .sm-dot { background:#BC5E78; }
.sm-badge.empty  { background:#F1F4F8; color:#6B7280; } .sm-badge.empty  .sm-dot { background:#A9B0BC; }
</style>
"""

# Maps each detected question type to its badge color class above.
QUESTION_TYPE_BADGE_CLASS = {
    QUESTION_TYPE_NUMERIC: "num",
    QUESTION_TYPE_SCALE: "scale",
    QUESTION_TYPE_SINGLE: "single",
    QUESTION_TYPE_MULTIPLE: "multi",
    QUESTION_TYPE_OPEN: "open",
    QUESTION_TYPE_EMPTY: "empty",
}


def inject_theme_css() -> None:
    """Apply the SurveyMind visual theme once per page render."""
    st.markdown(THEME_CSS, unsafe_allow_html=True)


def render_type_badges(detected_question_types: dict[str, str], language: str) -> None:
    """Show each column as a colored badge keyed to its detected question type."""
    badges = []
    for column, q_type in detected_question_types.items():
        css_class = QUESTION_TYPE_BADGE_CLASS.get(q_type, "empty")
        type_label = html.escape(translate_question_type(language, q_type))
        column_label = html.escape(str(column))
        badges.append(
            f'<span class="sm-badge {css_class}"><span class="sm-dot"></span>'
            f"{column_label}<span class=\"sm-type\"> · {type_label}</span></span>"
        )
    st.markdown(f'<div class="sm-badges">{"".join(badges)}</div>', unsafe_allow_html=True)


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

    if not isinstance(df, pd.DataFrame) or df.empty or df.shape[1] == 0:
        st.warning("No dataset is available to display.")
        return

    try:
        overview = get_dataset_overview(df)
    except Exception:
        st.warning("Data overview is unavailable for the current dataset.")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric(t(language, "metric_rows"), overview["shape"][0])
    col2.metric(t(language, "metric_columns"), overview["shape"][1])
    col3.metric(t(language, "metric_missing_ratio"), f"{df.isna().mean().mean() * 100:.2f}%")

    st.write(f"**{t(language, 'first_five_rows')}**")
    render_dataframe_or_warning(overview.get("preview"), "Dataset preview is unavailable.")

    meta_col1, meta_col2 = st.columns([1, 2])
    with meta_col1:
        st.write(f"**{t(language, 'column_names')}**")
        columns_frame = pd.DataFrame({t(language, "column_name_label"): overview.get("columns", [])})
        render_dataframe_or_warning(columns_frame, "Column names are unavailable.")
    with meta_col2:
        st.write(f"**{t(language, 'column_metadata')}**")
        render_dataframe_or_warning(overview.get("overview_table"), "Column metadata is unavailable.")


def render_question_detection(detected_question_types: dict[str, str], language: str) -> dict[str, str]:
    st.header(t(language, "section_question_detection"))
    st.write(t(language, "question_detection_desc"))

    if not detected_question_types:
        st.warning("Question type detection did not return any columns to display.")
        return {}

    render_type_badges(detected_question_types, language)

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

            selected_type = st.session_state[state_key]
            if selected_type not in question_type_options:
                selected_type = detected_type if detected_type in question_type_options else question_type_options[0]
                st.session_state[state_key] = selected_type

            with override_columns[index % 2]:
                active_question_types[column] = st.selectbox(
                    label=column,
                    options=question_type_options,
                    index=question_type_options.index(selected_type),
                    key=state_key,
                    format_func=lambda value: translate_question_type(language, value),
                    help=t(language, "detected_as_help", question_type=translate_question_type(language, detected_type)),
                )

    if not active_question_types:
        active_question_types = dict(detected_question_types)

    render_dataframe_or_warning(
        localize_question_type_frame(detected_question_types, active_question_types, language),
        "Question type results are unavailable.",
    )
    return active_question_types


def render_descriptive_statistics(df, question_types, descriptive_results, language: str):
    st.header(t(language, "section_descriptive_stats"))

    if not isinstance(descriptive_results, dict):
        st.warning("Descriptive statistics are unavailable.")
        return

    numeric_summary = descriptive_results.get("numeric_summary")
    scale_summary = descriptive_results.get("scale_summary")
    scale_distributions = descriptive_results.get("scale_distributions") or {}
    categorical_summary = descriptive_results.get("categorical_summary") or {}
    sample_profile = descriptive_results.get("sample_profile")

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            t(language, "tab_numeric"),
            t(language, "tab_scale"),
            t(language, "tab_categorical"),
            t(language, "tab_profile"),
        ]
    )

    with tab1:
        if not render_dataframe_or_warning(numeric_summary, t(language, "no_numeric"), "Numeric summary could not be displayed."):
            pass

    with tab2:
        if not has_display_data(scale_summary):
            st.warning(t(language, "no_scale"))
        else:
            localized_scale_summary = localize_scale_summary(scale_summary, language)
            render_dataframe_or_warning(
                localized_scale_summary,
                t(language, "no_scale"),
                "Scale summary could not be displayed.",
            )
            scale_options = list(scale_summary.index)
            if not scale_options:
                st.warning(t(language, "no_scale"))
            else:
                selected_scale = st.selectbox(
                    t(language, "choose_scale_question"),
                    scale_options,
                    key="scale_summary_column",
                )
                distribution_df = scale_distributions.get(selected_scale)
                if not has_display_data(distribution_df):
                    st.warning(t(language, "no_scale"))
                else:
                    st.write(f"**{t(language, 'scale_distribution')}**")
                    render_dataframe_or_warning(
                        distribution_df,
                        t(language, "no_scale"),
                        "Scale distribution could not be displayed.",
                    )
                    render_plotly_chart_safely(
                        lambda: build_scale_bar_chart(
                            distribution_df,
                            selected_scale,
                            display_mode="percentage",
                            language=language,
                        ),
                        t(language, "no_scale"),
                        "Scale chart could not be displayed.",
                        f"descriptive_scale_chart::{selected_scale}",
                    )

    with tab3:
        if not categorical_summary:
            st.warning(t(language, "no_categorical"))
        else:
            selected_column = st.selectbox(
                t(language, "choose_categorical_question"),
                list(categorical_summary.keys()),
                key="categorical_summary_column",
            )
            render_dataframe_or_warning(
                categorical_summary.get(selected_column),
                t(language, "no_categorical"),
                "Categorical summary could not be displayed.",
            )

    with tab4:
        render_dataframe_or_warning(sample_profile, t(language, "no_profile"), "Sample profile could not be displayed.")


def render_visualization_explorer(df, question_types, descriptive_results, language: str):
    st.header(t(language, "section_visualization"))

    if not question_types:
        st.warning("Visualization is unavailable because no question types were returned.")
        return

    scale_distributions = {}
    if isinstance(descriptive_results, dict):
        scale_distributions = descriptive_results.get("scale_distributions") or {}

    numeric_columns = [col for col, q_type in question_types.items() if q_type == QUESTION_TYPE_NUMERIC]
    scale_columns = [
        col
        for col, q_type in question_types.items()
        if q_type == QUESTION_TYPE_SCALE and has_display_data(scale_distributions.get(col))
    ]
    metric_columns = numeric_columns + scale_columns
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
            render_plotly_chart_safely(
                lambda: build_categorical_bar_chart(
                    df,
                    column,
                    question_types[column],
                    display_mode=display_mode,
                    language=language,
                ),
                t(language, "no_categorical_chart"),
                "Categorical chart could not be displayed.",
                f"visual_categorical_chart::{column}::{display_mode}",
            )
        else:
            st.warning(t(language, "no_categorical_chart"))

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
            distribution_df = scale_distributions.get(column)
            if not has_display_data(distribution_df):
                st.warning(t(language, "no_scale_chart"))
            else:
                render_plotly_chart_safely(
                    lambda: build_scale_bar_chart(
                        distribution_df,
                        column,
                        display_mode=display_mode,
                        language=language,
                    ),
                    t(language, "no_scale_chart"),
                    "Scale chart could not be displayed.",
                    f"visual_scale_chart::{column}::{display_mode}",
                )
        else:
            st.warning(t(language, "no_scale_chart"))

    with tab3:
        if numeric_columns:
            column = st.selectbox(t(language, "numeric_variable"), numeric_columns, key="histogram_column")
            render_plotly_chart_safely(
                lambda: build_numeric_histogram(df, column, language=language),
                t(language, "no_numeric_chart"),
                "Numeric chart could not be displayed.",
                f"visual_numeric_histogram::{column}",
            )
        else:
            st.warning(t(language, "no_numeric_chart"))

    with tab4:
        if metric_columns and categorical_columns:
            numeric_column = st.selectbox(
                t(language, "numeric_or_scale_variable"),
                metric_columns,
                key="box_numeric",
            )
            group_column = st.selectbox(t(language, "grouping_variable"), categorical_columns, key="box_group")
            render_plotly_chart_safely(
                lambda: build_grouped_box_plot(df, numeric_column, group_column, language=language),
                t(language, "boxplot_requirement"),
                "Box plot could not be displayed.",
                f"visual_box_plot::{numeric_column}::{group_column}",
            )
        else:
            st.warning(t(language, "boxplot_requirement"))


def render_cross_analysis(df, question_types, language: str):
    st.header(t(language, "section_cross_analysis"))
    group_options = [
        col for col, q_type in question_types.items() if q_type not in {QUESTION_TYPE_NUMERIC, QUESTION_TYPE_SCALE, QUESTION_TYPE_OPEN}
    ]
    target_options = [col for col, q_type in question_types.items() if q_type != QUESTION_TYPE_OPEN]

    if not group_options or len(target_options) < 2:
        st.warning(t(language, "cross_analysis_requirement"))
        return None

    col1, col2 = st.columns(2)
    with col1:
        group_col = st.selectbox(t(language, "grouping_variable"), group_options, key="cross_group")
    with col2:
        remaining_targets = [col for col in target_options if col != group_col]
        if not remaining_targets:
            st.warning(t(language, "cross_analysis_requirement"))
            return None
        target_col = st.selectbox(t(language, "target_variable"), remaining_targets, key="cross_target")

    result = analyze_cross_relationship(df, group_col, target_col, question_types, language=language)
    if not isinstance(result, dict) or not result.get("analysis_type"):
        st.warning("Cross analysis results are unavailable.")
        return None

    if result["analysis_type"] == "unsupported":
        st.warning(result.get("message", t(language, "cross_open_ended_warning")))
        return result

    if result["analysis_type"] == "numeric_by_group":
        st.write(f"**{t(language, 'grouped_summary_stats')}**")
        render_dataframe_or_warning(
            result.get("summary_table"),
            "Grouped summary data is unavailable.",
            "Grouped summary could not be displayed.",
        )
        interpretation = result.get("interpretation")
        if interpretation:
            st.info(interpretation)
        else:
            st.warning("Cross analysis interpretation is unavailable.")
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
            "raw_count": result.get("crosstab_table"),
            "row_percentage": result.get("row_percentage_table"),
            "column_percentage": result.get("column_percentage_table"),
        }
        mode_label = {
            "raw_count": t(language, "cross_raw_count"),
            "row_percentage": t(language, "cross_row_percentage"),
            "column_percentage": t(language, "cross_column_percentage"),
        }[display_mode]
        selected_table = table_lookup.get(display_mode)
        st.write(f"**{t(language, 'cross_table_title', mode=mode_label)}**")
        if render_dataframe_or_warning(
            selected_table,
            "Cross analysis table is unavailable.",
            "Cross analysis table could not be displayed.",
        ):
            chart_mode = st.radio(
                t(language, "cross_chart_type"),
                options=["stacked", "heatmap"],
                horizontal=True,
                format_func=lambda value: t(language, f"chart_type_{value}"),
            )
            render_plotly_chart_safely(
                lambda: build_crosstab_chart(
                    selected_table,
                    chart_type=chart_mode,
                    display_mode=display_mode,
                    language=language,
                ),
                "Cross analysis chart is unavailable.",
                "Cross analysis chart could not be displayed.",
                f"cross_chart::{target_col}::{display_mode}::{chart_mode}",
            )
        interpretation = result.get("interpretation")
        if interpretation:
            st.info(interpretation)
        else:
            st.warning("Cross analysis interpretation is unavailable.")

    return result


def render_report(df, question_types, descriptive_results, cross_analysis_result, language: str):
    st.header(t(language, "section_report"))

    try:
        report_markdown = generate_markdown_report(
            df,
            question_types,
            descriptive_results,
            cross_analysis_result,
            language=language,
        )
    except Exception:
        st.warning("Report content is unavailable.")
        return None

    if not isinstance(report_markdown, str) or not report_markdown.strip():
        st.warning("Report content is unavailable.")
        return None

    try:
        st.markdown(report_markdown)
        st.download_button(
            label=t(language, "download_report"),
            data=report_markdown,
            file_name=t(language, "download_report_filename"),
            mime="text/markdown",
        )
    except Exception:
        st.warning("Report display is unavailable.")
        return None

    return report_markdown


def render_ai_report(df: pd.DataFrame):
    st.header("8. AI 问卷分析报告")
    st.caption("调用云端 LLM API，基于 pandas 已计算好的结构化统计摘要生成中文报告。")

    if not is_llm_configured():
        st.info("尚未配置 LLM API key：请将项目根目录的 .env.example 复制为 .env 并填入你的 LLM_API_KEY。")
        return None

    dataset_signature = (tuple(df.columns), int(len(df)), int(df.isna().sum().sum()))
    if st.session_state.get("ai_report_signature") != dataset_signature:
        st.session_state["ai_report_signature"] = dataset_signature
        st.session_state.pop("ai_report_markdown", None)

    if st.button("生成 AI 分析报告", key="generate_ai_report"):
        with st.spinner("正在调用云端模型生成报告..."):
            try:
                summary = build_dataset_summary(df)
                prompt = build_llm_prompt(summary)
                st.session_state["ai_report_markdown"] = ask_llm(prompt)
            except Exception as exc:
                st.error(f"AI 报告生成失败：{exc}")

    report_markdown = st.session_state.get("ai_report_markdown", "")
    if not isinstance(report_markdown, str) or not report_markdown.strip():
        return None

    st.markdown(report_markdown)
    st.download_button(
        label="下载 AI Markdown 报告",
        data=report_markdown,
        file_name="surveymind_ai_report.md",
        mime="text/markdown",
        key="download_ai_report",
    )
    return report_markdown


def main():
    inject_theme_css()
    language = render_sidebar()
    render_intro(language)
    uploaded_file = render_data_upload(language)

    df, using_demo = load_active_dataset(uploaded_file)
    if df is None:
        return

    if using_demo:
        st.caption(t(language, "using_demo_caption", filename=DEFAULT_DEMO_PATH.name))
    else:
        st.caption(t(language, "using_upload_caption", filename=uploaded_file.name))

    try:
        render_data_overview(df, language)
    except Exception:
        st.warning("Data overview could not be displayed.")

    detected_question_types = detect_question_types(df)
    try:
        question_types = render_question_detection(detected_question_types, language)
    except Exception:
        st.warning("Question type display could not be rendered. Using detected defaults.")
        question_types = detected_question_types

    descriptive_results = generate_descriptive_results(df, question_types)

    try:
        render_descriptive_statistics(df, question_types, descriptive_results, language)
    except Exception:
        st.warning("Descriptive statistics could not be displayed.")

    try:
        render_visualization_explorer(df, question_types, descriptive_results, language)
    except Exception:
        st.warning("Visualization section could not be displayed.")

    try:
        cross_analysis_result = render_cross_analysis(df, question_types, language)
    except Exception:
        st.warning("Cross analysis section could not be displayed.")
        cross_analysis_result = None

    try:
        render_report(df, question_types, descriptive_results, cross_analysis_result, language)
    except Exception:
        st.warning("Report section could not be displayed.")

    try:
        render_ai_report(df)
    except Exception:
        st.warning("AI report section could not be displayed.")


if __name__ == "__main__":
    main()
