from __future__ import annotations

import html
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile

import pandas as pd
import streamlit as st

from src.ai_report import AI_STATUS_FAILED, AI_STATUS_NOT_CONFIGURED, AI_STATUS_OK, generate_ai_report
from src.analysis_suggestions import generate_analysis_suggestions
from src.chart_recommender import (
    CHART_CATEGORICAL_BAR,
    CHART_CORRELATION_HEATMAP,
    CHART_GROUPED_BOX,
    CHART_NUMERIC_HISTOGRAM,
    CHART_TIME_TREND,
    recommend_charts,
)
from src.cross_analysis import analyze_cross_relationship
from src.data_loader import DEFAULT_DEMO_PATH, load_demo_dataset, load_uploaded_dataset
from src.dataset_mode import (
    DATASET_MODE_MIXED,
    DATASET_MODE_OPTIONS,
    DATASET_MODE_SURVEY,
    derive_analysis_types,
    derive_question_types,
    detect_dataset_mode,
)
from src.descriptive_analysis import generate_descriptive_results
from src.field_semantics import (
    apply_role_overrides,
    detect_field_semantics,
    field_semantics_to_frame,
    get_field_role_options,
)
from src.general_overview import build_overview_findings, generate_general_overview
from src.i18n import (
    DEFAULT_LANGUAGE,
    LANGUAGE_OPTIONS,
    get_language_label,
    t,
    translate_dataset_mode,
    translate_field_role,
    translate_question_type,
    translate_scale_level,
)
from src.llm_client import is_llm_configured
from src.preprocessing import soft_clean_dataframe

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
    get_question_type_options,
    question_types_to_frame,
)
from src.report import generate_report
from src.visualization import (
    build_categorical_bar_chart,
    build_correlation_heatmap,
    build_crosstab_chart,
    build_grouped_box_plot,
    build_numeric_histogram,
    build_scale_bar_chart,
    build_time_trend_chart,
)


if "language" not in st.session_state:
    st.session_state["language"] = DEFAULT_LANGUAGE

st.set_page_config(page_title=t(st.session_state["language"], "page_title"), page_icon="📊", layout="wide")


SUPPORTED_UPLOAD_SUFFIXES = {".csv", ".xlsx", ".xls"}


# The strict survey preprocessing (which drops ID/timestamp columns) lives in
# src/preprocessing.py and still powers the five legacy API screens unchanged.
# The platform keeps every column via the shared lenient cleaner: field
# semantics assigns identifier/datetime roles instead of dropping the data.
def preprocess_input_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    return soft_clean_dataframe(df)


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
    if isinstance(exc, ValueError) and "No usable data columns remain" in str(exc):
        return "No usable data columns remain after preprocessing. Please upload a file that contains at least one non-empty column."
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


def render_mode_selector(mode_result, language: str, dataset_key: str) -> str:
    st.header(t(language, "section_mode_detection"))
    st.markdown(
        t(
            language,
            "mode_detected_caption",
            mode=translate_dataset_mode(language, mode_result.mode),
            survey_score=mode_result.survey_score,
            general_score=mode_result.general_score,
        )
    )
    if mode_result.signals:
        with st.expander(t(language, "mode_signals_label"), expanded=False):
            for signal in mode_result.signals:
                st.markdown(f"- {signal}")

    state_key = f"dataset_mode_override::{dataset_key}"
    if state_key not in st.session_state:
        st.session_state[state_key] = mode_result.mode
    if st.session_state[state_key] not in DATASET_MODE_OPTIONS:
        st.session_state[state_key] = mode_result.mode

    return st.radio(
        t(language, "mode_override_label"),
        options=DATASET_MODE_OPTIONS,
        horizontal=True,
        format_func=lambda value: translate_dataset_mode(language, value),
        key=state_key,
    )


def render_field_roles(df, semantics, language: str, dataset_key: str):
    st.header(t(language, "section_field_roles"))
    st.write(t(language, "field_roles_desc"))

    role_options = get_field_role_options()

    if st.button(t(language, "reset_field_roles")):
        for column, profile in semantics.items():
            st.session_state[f"field_role_override::{dataset_key}::{column}"] = profile.role

    overrides: dict[str, str] = {}
    with st.expander(t(language, "manual_role_override"), expanded=False):
        override_columns = st.columns(2)
        for index, (column, profile) in enumerate(semantics.items()):
            state_key = f"field_role_override::{dataset_key}::{column}"
            if state_key not in st.session_state or st.session_state[state_key] not in role_options:
                st.session_state[state_key] = profile.role if profile.role in role_options else role_options[0]
            with override_columns[index % 2]:
                overrides[column] = st.selectbox(
                    label=column,
                    options=role_options,
                    key=state_key,
                    format_func=lambda value: translate_field_role(language, value),
                    help=t(language, "detected_as_help", question_type=translate_field_role(language, profile.role)),
                )

    active_semantics = apply_role_overrides(semantics, overrides)

    display_frame = field_semantics_to_frame(semantics, {column: p.role for column, p in active_semantics.items()})
    display_frame["detected_role"] = display_frame["detected_role"].map(lambda value: translate_field_role(language, value))
    display_frame["active_role"] = display_frame["active_role"].map(lambda value: translate_field_role(language, value))
    display_frame = display_frame.rename(
        columns={
            "column_name": t(language, "column_name_label"),
            "detected_role": t(language, "detected_role_label"),
            "active_role": t(language, "active_role_label"),
            "evidence": t(language, "evidence_label"),
        }
    )
    render_dataframe_or_warning(display_frame, "Field role results are unavailable.")
    return active_semantics


def render_general_overview_section(df, overview, semantics, language: str):
    st.header(t(language, "section_data_overview"))

    quality = overview.get("quality", {})
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(t(language, "metric_rows"), overview["shape"][0])
    col2.metric(t(language, "metric_columns"), overview["shape"][1])
    col3.metric(t(language, "metric_missing_ratio"), f"{quality.get('overall_missing_pct', 0):.2f}%")
    col4.metric(t(language, "metric_duplicates"), quality.get("duplicate_rows", 0))

    st.write(f"**{t(language, 'first_five_rows')}**")
    render_dataframe_or_warning(overview.get("preview"), "Dataset preview is unavailable.")

    tab_fields, tab_numeric, tab_categorical, tab_datetime, tab_relations, tab_quality = st.tabs(
        [
            t(language, "overview_tab_fields"),
            t(language, "overview_tab_numeric"),
            t(language, "overview_tab_categorical"),
            t(language, "overview_tab_datetime"),
            t(language, "overview_tab_relations"),
            t(language, "overview_tab_quality"),
        ]
    )

    with tab_fields:
        role_table = overview.get("field_role_table")
        if has_display_data(role_table):
            localized = role_table.copy()
            localized["role"] = localized["role"].map(lambda value: translate_field_role(language, value))
            render_dataframe_or_warning(localized, "Field table is unavailable.")
        else:
            st.warning("Field table is unavailable.")

    with tab_numeric:
        render_dataframe_or_warning(overview.get("numeric_summary"), t(language, "no_numeric_fields"))

    with tab_categorical:
        categorical_summary = overview.get("categorical_summary") or {}
        if not categorical_summary:
            st.warning(t(language, "no_categorical_fields"))
        else:
            selected_column = st.selectbox(
                t(language, "choose_categorical_field"),
                list(categorical_summary.keys()),
                key="overview_categorical_column",
            )
            render_dataframe_or_warning(categorical_summary.get(selected_column), t(language, "no_categorical_fields"))

    with tab_datetime:
        render_dataframe_or_warning(overview.get("datetime_summary"), t(language, "no_datetime_fields"))

    with tab_relations:
        correlations = overview.get("correlations")
        group_differences = overview.get("group_differences")
        shown = False
        if has_display_data(correlations):
            st.write(f"**{t(language, 'correlations_title')}**")
            render_dataframe_or_warning(correlations, t(language, "no_relations"))
            shown = True
        if has_display_data(group_differences):
            st.write(f"**{t(language, 'group_differences_title')}**")
            render_dataframe_or_warning(group_differences, t(language, "no_relations"))
            shown = True
        if not shown:
            st.info(t(language, "no_relations"))

    with tab_quality:
        high_missing = quality.get("high_missing")
        if isinstance(high_missing, pd.Series) and len(high_missing) > 0:
            missing_frame = (high_missing * 100).round(2).rename_axis(t(language, "column_name_label")).reset_index(
                name=t(language, "metric_missing_ratio")
            )
            render_dataframe_or_warning(missing_frame, "Missing-value details are unavailable.")
        unusable = quality.get("unusable_columns") or []
        if unusable:
            st.warning(", ".join(f"`{column}`" for column in unusable))

    try:
        findings = build_overview_findings(df, overview, language)
    except Exception:
        findings = []
    if findings:
        st.write(f"**{t(language, 'overview_findings_title')}**")
        st.markdown("\n".join(f"- {finding}" for finding in findings))


def render_suggestions_section(df, semantics, overview, language: str):
    st.header(t(language, "section_suggestions"))
    try:
        suggestions = generate_analysis_suggestions(df, semantics, overview, language)
    except Exception:
        suggestions = []
    if not suggestions:
        st.info(t(language, "no_data_insufficient"))
        return
    st.write(t(language, "suggestions_desc"))
    st.markdown("\n".join(f"{index}. {suggestion}" for index, suggestion in enumerate(suggestions, start=1)))


def render_recommended_charts_section(df, semantics, overview, language: str):
    st.header(t(language, "section_recommended_charts"))
    try:
        chart_specs = recommend_charts(df, semantics, overview)
    except Exception:
        chart_specs = []
    if not chart_specs:
        st.info(t(language, "no_recommended_charts"))
        return

    grid = st.columns(2)
    for index, spec in enumerate(chart_specs):
        kind = spec.get("kind")
        with grid[index % 2]:
            if kind == CHART_TIME_TREND:
                trend_df = (overview.get("time_trends") or {}).get(spec["column"])
                render_plotly_chart_safely(
                    lambda trend_df=trend_df, column=spec["column"]: build_time_trend_chart(trend_df, column, language=language),
                    t(language, "no_recommended_charts"),
                    "Time trend chart could not be displayed.",
                    f"recommended_chart::{index}::{spec['column']}",
                )
            elif kind == CHART_CORRELATION_HEATMAP:
                render_plotly_chart_safely(
                    lambda columns=spec["columns"]: build_correlation_heatmap(df, columns, language=language),
                    t(language, "no_recommended_charts"),
                    "Correlation heatmap could not be displayed.",
                    f"recommended_chart::{index}::correlation",
                )
            elif kind == CHART_GROUPED_BOX:
                render_plotly_chart_safely(
                    lambda numeric=spec["numeric_column"], group=spec["group_column"]: build_grouped_box_plot(
                        df, numeric, group, language=language
                    ),
                    t(language, "no_recommended_charts"),
                    "Box plot could not be displayed.",
                    f"recommended_chart::{index}::box",
                )
            elif kind == CHART_NUMERIC_HISTOGRAM:
                render_plotly_chart_safely(
                    lambda column=spec["column"]: build_numeric_histogram(df, column, language=language),
                    t(language, "no_recommended_charts"),
                    "Histogram could not be displayed.",
                    f"recommended_chart::{index}::{spec['column']}",
                )
            elif kind == CHART_CATEGORICAL_BAR:
                question_type = QUESTION_TYPE_MULTIPLE if spec.get("is_multi_value") else QUESTION_TYPE_SINGLE
                render_plotly_chart_safely(
                    lambda column=spec["column"], q_type=question_type: build_categorical_bar_chart(
                        df, column, q_type, language=language
                    ),
                    t(language, "no_recommended_charts"),
                    "Bar chart could not be displayed.",
                    f"recommended_chart::{index}::{spec['column']}",
                )


def render_ai_section(df, mode, language, overview, descriptive_results, question_types, dataset_key: str):
    st.header(t(language, "section_ai_insights"))
    persona_key = {
        "general": "ai_persona_general",
        "survey": "ai_persona_survey",
        "mixed": "ai_persona_mixed",
    }.get(mode, "ai_persona_general")
    st.caption(t(language, "ai_persona_caption", persona=t(language, persona_key)))

    if not is_llm_configured():
        st.info(t(language, "ai_not_configured"))
        return

    result_key = f"ai_report_result::{dataset_key}::{mode}::{language}"
    if st.button(t(language, "ai_generate_button")):
        with st.spinner(t(language, "ai_generating")):
            st.session_state[result_key] = generate_ai_report(
                df, mode, language, overview, descriptive_results, question_types
            )

    result = st.session_state.get(result_key)
    if not result:
        return
    if result.get("status") == AI_STATUS_OK:
        st.caption(t(language, "ai_grounding_note"))
        st.markdown(result.get("content", ""))
    elif result.get("status") == AI_STATUS_FAILED:
        st.warning(t(language, "ai_failed_notice"))
    elif result.get("status") == AI_STATUS_NOT_CONFIGURED:
        st.info(t(language, "ai_not_configured"))


def render_question_detection(
    detected_question_types: dict[str, str],
    language: str,
    dataset_key: str = "default",
) -> dict[str, str]:
    st.header(t(language, "section_question_detection"))
    st.write(t(language, "question_detection_desc"))

    if not detected_question_types:
        st.warning("Question type detection did not return any columns to display.")
        return {}

    render_type_badges(detected_question_types, language)

    if st.button(t(language, "reset_overrides")):
        for column, detected_type in detected_question_types.items():
            st.session_state[f"question_type_override::{dataset_key}::{column}"] = detected_type

    question_type_options = get_question_type_options()
    active_question_types: dict[str, str] = {}

    with st.expander(t(language, "manual_override"), expanded=False):
        override_columns = st.columns(2)
        for index, (column, detected_type) in enumerate(detected_question_types.items()):
            state_key = f"question_type_override::{dataset_key}::{column}"
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


def render_report(
    df,
    mode,
    question_types,
    descriptive_results,
    cross_analysis_result,
    semantics,
    overview,
    language: str,
):
    st.header(t(language, "section_report"))

    try:
        report_markdown = generate_report(
            df,
            mode,
            language=language,
            question_types=question_types,
            descriptive_results=descriptive_results,
            cross_analysis_result=cross_analysis_result,
            semantics=semantics,
            overview=overview,
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
        dataset_key = "demo"
    else:
        st.caption(t(language, "using_upload_caption", filename=uploaded_file.name))
        dataset_key = f"{uploaded_file.name}::{df.shape[0]}x{df.shape[1]}"

    semantics = detect_field_semantics(df)
    mode_result = detect_dataset_mode(df, semantics)

    try:
        mode = render_mode_selector(mode_result, language, dataset_key)
    except Exception:
        st.warning("Dataset mode selector could not be displayed. Using the detected mode.")
        mode = mode_result.mode

    try:
        semantics = render_field_roles(df, semantics, language, dataset_key)
    except Exception:
        st.warning("Field role display could not be rendered. Using detected roles.")

    try:
        overview = generate_general_overview(df, semantics)
    except Exception:
        st.warning("Data overview could not be computed.")
        overview = {"shape": df.shape, "quality": {}, "preview": df.head()}

    try:
        render_general_overview_section(df, overview, semantics, language)
    except Exception:
        st.warning("Data overview could not be displayed.")

    try:
        render_suggestions_section(df, semantics, overview, language)
    except Exception:
        st.warning("Analysis suggestions could not be displayed.")

    try:
        render_recommended_charts_section(df, semantics, overview, language)
    except Exception:
        st.warning("Recommended charts could not be displayed.")

    question_types = None
    descriptive_results = None
    cross_analysis_result = None

    if mode in {DATASET_MODE_SURVEY, DATASET_MODE_MIXED}:
        detected_question_types = derive_question_types(df, semantics)
        try:
            question_types = render_question_detection(detected_question_types, language, dataset_key)
        except Exception:
            st.warning("Question type display could not be rendered. Using detected defaults.")
            question_types = detected_question_types

        try:
            descriptive_results = generate_descriptive_results(df, question_types)
        except Exception:
            st.warning("Descriptive statistics could not be computed.")
            descriptive_results = {}

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
    else:
        analysis_types = derive_analysis_types(semantics)
        try:
            cross_analysis_result = render_cross_analysis(df, analysis_types, language)
        except Exception:
            st.warning("Cross analysis section could not be displayed.")

    try:
        render_report(
            df,
            mode,
            question_types,
            descriptive_results,
            cross_analysis_result,
            semantics,
            overview,
            language,
        )
    except Exception:
        st.warning("Report section could not be displayed.")

    try:
        render_ai_section(df, mode, language, overview, descriptive_results, question_types, dataset_key)
    except Exception:
        st.warning("AI interpretation section could not be displayed.")


if __name__ == "__main__":
    main()
