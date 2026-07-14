from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.field_semantics import (
    FIELD_ROLE_BOOLEAN,
    FIELD_ROLE_CATEGORICAL,
    FIELD_ROLE_DATETIME,
    FIELD_ROLE_EMPTY,
    FIELD_ROLE_FREE_TEXT,
    FIELD_ROLE_IDENTIFIER,
    FIELD_ROLE_MULTI_VALUE,
    FIELD_ROLE_NUMERIC,
    FieldProfile,
)
from src.question_type_detector import (
    QUESTION_TYPE_MULTIPLE,
    QUESTION_TYPE_NUMERIC,
    QUESTION_TYPE_OPEN,
    QUESTION_TYPE_SCALE,
    QUESTION_TYPE_SINGLE,
    _is_scale_question,
)


DATASET_MODE_GENERAL = "general"
DATASET_MODE_SURVEY = "survey"
DATASET_MODE_MIXED = "mixed"

DATASET_MODE_OPTIONS = [DATASET_MODE_GENERAL, DATASET_MODE_SURVEY, DATASET_MODE_MIXED]

SURVEY_NAME_KEYWORDS = (
    "满意",
    "同意",
    "意愿",
    "程度",
    "评分",
    "评价",
    "推荐",
    "问卷",
    "satisf",
    "agree",
    "likert",
    "scale",
    "score",
    "rating",
    "recommend",
    "nps",
    "willingness",
    "opinion",
)

FEEDBACK_NAME_KEYWORDS = (
    "建议",
    "反馈",
    "意见",
    "评论",
    "看法",
    "原因",
    "feedback",
    "comment",
    "suggestion",
    "opinion",
    "reason",
    "review",
)

GENERAL_NAME_KEYWORDS = (
    "price",
    "amount",
    "sales",
    "revenue",
    "cost",
    "profit",
    "quantity",
    "qty",
    "salary",
    "income",
    "balance",
    "金额",
    "价格",
    "销量",
    "销售",
    "收入",
    "成本",
    "利润",
    "数量",
    "库存",
    "工资",
    "余额",
    "订单",
)


@dataclass
class ModeDetectionResult:
    mode: str
    survey_score: float
    general_score: float
    signals: list[str] = field(default_factory=list)


def _name_contains(column_name: str, keywords: tuple[str, ...]) -> bool:
    lowered = column_name.strip().lower()
    return any(keyword in lowered for keyword in keywords)


def detect_dataset_mode(df: pd.DataFrame, semantics: dict[str, FieldProfile]) -> ModeDetectionResult:
    """Score survey-style vs general-table evidence and pick a dataset mode."""
    survey_score = 0.0
    general_score = 0.0
    signals: list[str] = []

    for column, profile in semantics.items():
        role = profile.role
        if role == FIELD_ROLE_IDENTIFIER:
            general_score += 2
            signals.append(f"identifier column `{column}`")
        elif role == FIELD_ROLE_DATETIME:
            general_score += 2
            signals.append(f"datetime column `{column}`")
        elif role == FIELD_ROLE_BOOLEAN:
            general_score += 0.5
        elif role == FIELD_ROLE_NUMERIC:
            survey_name = _name_contains(column, SURVEY_NAME_KEYWORDS)
            if _is_scale_question(df[column]):
                if survey_name:
                    survey_score += 2
                    signals.append(f"Likert-style scale column `{column}`")
                else:
                    survey_score += 0.75
            elif survey_name:
                survey_score += 1
                signals.append(f"survey-style numeric column `{column}`")
            elif _name_contains(column, GENERAL_NAME_KEYWORDS):
                general_score += 1
                signals.append(f"business metric column `{column}`")
            else:
                general_score += 0.25
        elif role == FIELD_ROLE_MULTI_VALUE:
            survey_score += 2
            signals.append(f"multi-select style column `{column}`")
        elif role == FIELD_ROLE_FREE_TEXT:
            if _name_contains(column, FEEDBACK_NAME_KEYWORDS):
                survey_score += 2
                signals.append(f"open feedback column `{column}`")
            else:
                survey_score += 0.75
        elif role == FIELD_ROLE_CATEGORICAL:
            survey_score += 0.25

    if survey_score >= 3 and general_score >= 3:
        mode = DATASET_MODE_MIXED
    elif survey_score >= 2 and survey_score > general_score:
        mode = DATASET_MODE_SURVEY
    else:
        mode = DATASET_MODE_GENERAL

    return ModeDetectionResult(
        mode=mode,
        survey_score=round(survey_score, 2),
        general_score=round(general_score, 2),
        signals=signals[:8],
    )


# Columns with these roles carry table metadata rather than analyzable
# answers, so they never become questions or comparison variables.
METADATA_ROLES = {FIELD_ROLE_IDENTIFIER, FIELD_ROLE_DATETIME, FIELD_ROLE_EMPTY}


def derive_question_types(df: pd.DataFrame, semantics: dict[str, FieldProfile]) -> dict[str, str]:
    """Project field roles onto survey question types (survey/mixed modes)."""
    question_types: dict[str, str] = {}
    for column, profile in semantics.items():
        role = profile.role
        if role in METADATA_ROLES:
            continue
        if role == FIELD_ROLE_NUMERIC:
            question_types[column] = (
                QUESTION_TYPE_SCALE if _is_scale_question(df[column]) else QUESTION_TYPE_NUMERIC
            )
        elif role in {FIELD_ROLE_CATEGORICAL, FIELD_ROLE_BOOLEAN}:
            question_types[column] = QUESTION_TYPE_SINGLE
        elif role == FIELD_ROLE_MULTI_VALUE:
            question_types[column] = QUESTION_TYPE_MULTIPLE
        elif role == FIELD_ROLE_FREE_TEXT:
            question_types[column] = QUESTION_TYPE_OPEN
    return question_types


def derive_analysis_types(semantics: dict[str, FieldProfile]) -> dict[str, str]:
    """Map field roles to comparison-friendly types for general mode.

    General datasets never use the scale-question concept, so numeric columns
    stay numeric; the mapping only exists to drive the cross-analysis engine.
    """
    analysis_types: dict[str, str] = {}
    for column, profile in semantics.items():
        role = profile.role
        if role in METADATA_ROLES:
            continue
        if role == FIELD_ROLE_NUMERIC:
            analysis_types[column] = QUESTION_TYPE_NUMERIC
        elif role in {FIELD_ROLE_CATEGORICAL, FIELD_ROLE_BOOLEAN}:
            analysis_types[column] = QUESTION_TYPE_SINGLE
        elif role == FIELD_ROLE_MULTI_VALUE:
            analysis_types[column] = QUESTION_TYPE_MULTIPLE
        elif role == FIELD_ROLE_FREE_TEXT:
            analysis_types[column] = QUESTION_TYPE_OPEN
    return analysis_types
