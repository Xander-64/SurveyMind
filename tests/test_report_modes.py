from pathlib import Path

import pandas as pd
import pytest

import src.ai_report as ai_report
from src.ai_report import AI_STATUS_NOT_CONFIGURED, build_analysis_digest, generate_ai_report, get_persona_prompt
from src.dataset_mode import (
    DATASET_MODE_GENERAL,
    DATASET_MODE_MIXED,
    DATASET_MODE_SURVEY,
    derive_question_types,
)
from src.descriptive_analysis import generate_descriptive_results
from src.field_semantics import detect_field_semantics
from src.general_overview import generate_general_overview
from src.report_generator import generate_report

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

SURVEY_TERMS_ZH = ("单选题", "多选题", "量表题", "开放题", "问卷")


def build_context(filename):
    df = pd.read_csv(DATA_DIR / filename)
    semantics = detect_field_semantics(df)
    overview = generate_general_overview(df, semantics)
    return df, semantics, overview


@pytest.fixture(scope="module")
def general_context():
    return build_context("sample_general.csv")


@pytest.fixture(scope="module")
def survey_context():
    return build_context("sample_survey.csv")


@pytest.fixture(scope="module")
def mixed_context():
    return build_context("sample_mixed.csv")


def test_general_report_structure_and_no_survey_terms(general_context):
    df, semantics, overview = general_context
    report = generate_report(df, DATASET_MODE_GENERAL, language="zh-CN", semantics=semantics, overview=overview)
    for section in ("数据集概览", "字段与分布", "数据质量", "变量关系", "主要发现", "后续分析建议", "分析限制"):
        assert section in report
    for term in SURVEY_TERMS_ZH:
        assert term not in report, f"general report must not contain survey term {term}"


def test_general_report_english(general_context):
    df, semantics, overview = general_context
    report = generate_report(df, DATASET_MODE_GENERAL, language="en", semantics=semantics, overview=overview)
    for section in ("Dataset Overview", "Fields and Distributions", "Variable Relationships", "Limitations"):
        assert section in report
    assert "single-choice question" not in report


def test_survey_report_keeps_question_sections(survey_context):
    df, semantics, overview = survey_context
    question_types = derive_question_types(df, semantics)
    descriptive_results = generate_descriptive_results(df, question_types)
    report = generate_report(
        df,
        DATASET_MODE_SURVEY,
        language="zh-CN",
        question_types=question_types,
        descriptive_results=descriptive_results,
        semantics=semantics,
        overview=overview,
    )
    assert "题型识别概况" in report
    assert "SurveyMind 问卷分析报告" in report


def test_mixed_report_contains_both_layers(mixed_context):
    df, semantics, overview = mixed_context
    question_types = derive_question_types(df, semantics)
    descriptive_results = generate_descriptive_results(df, question_types)
    report = generate_report(
        df,
        DATASET_MODE_MIXED,
        language="zh-CN",
        question_types=question_types,
        descriptive_results=descriptive_results,
        semantics=semantics,
        overview=overview,
    )
    assert "字段与分布" in report
    assert "题型识别概况" in report


def test_ai_report_degrades_when_not_configured(general_context, monkeypatch):
    df, semantics, overview = general_context
    monkeypatch.setattr(ai_report, "is_llm_configured", lambda: False)
    result = generate_ai_report(df, DATASET_MODE_GENERAL, "zh-CN", overview)
    assert result["status"] == AI_STATUS_NOT_CONFIGURED


def test_ai_digest_contains_computed_numbers(general_context):
    df, semantics, overview = general_context
    digest = build_analysis_digest(df, DATASET_MODE_GENERAL, overview)
    computed_mean = overview["numeric_summary"].loc["total_amount", "mean"]
    assert str(computed_mean) in digest


def test_personas_switch_with_mode():
    general_zh = get_persona_prompt(DATASET_MODE_GENERAL, "zh-CN")
    survey_zh = get_persona_prompt(DATASET_MODE_SURVEY, "zh-CN")
    mixed_zh = get_persona_prompt(DATASET_MODE_MIXED, "zh-CN")
    assert "通用数据分析师" in general_zh
    assert "问卷分析师" in survey_zh
    assert "混合数据分析师" in mixed_zh
    for prompt in (general_zh, survey_zh, mixed_zh):
        assert "根据当前数据无法进一步判断" in prompt
