"""Questionnaire generation.

The generation side of the survey end-to-end pipeline: build a survey schema,
check it against methodology rules, and export it so the questionnaire can be
fielded on a third-party platform. Recovered responses come back through the
existing upload/analysis path — nothing here collects answers.

    schema      Survey / Section / Question dataclasses and JSON round-trip
    vocabulary  word lists backing the wording checks
    validator   methodology validator (pure rules, no IO, no LLM)
"""
from __future__ import annotations

from src.survey_gen.schema import (
    GENERATABLE_QUESTION_TYPES,
    SCHEMA_VERSION,
    Construct,
    Option,
    Question,
    ResponseMetadataSpec,
    ScaleSpec,
    Section,
    Survey,
    localized,
)
from src.survey_gen.validator import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    ValidationIssue,
    validate_survey,
)

__all__ = [
    "Construct",
    "GENERATABLE_QUESTION_TYPES",
    "Option",
    "Question",
    "ResponseMetadataSpec",
    "SCHEMA_VERSION",
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "ScaleSpec",
    "Section",
    "Survey",
    "ValidationIssue",
    "localized",
    "validate_survey",
]
