"""Survey schema: JSON round-trip, question-type vocabulary, derived lookups."""
import json
from pathlib import Path

import pytest

from src.question_type_detector import (
    QUESTION_TYPE_EMPTY,
    QUESTION_TYPE_SCALE,
    QUESTION_TYPE_UNKNOWN,
    get_question_type_options,
)
from src.survey_gen.schema import (
    GENERATABLE_QUESTION_TYPES,
    SCHEMA_VERSION,
    QUESTION_SOURCE_GENERATED,
    Survey,
    localized,
    text_in,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "surveys"


@pytest.fixture(scope="module")
def golden_payload():
    return json.loads((FIXTURES / "golden_survey.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def golden(golden_payload):
    return Survey.from_dict(golden_payload)


def test_generatable_types_are_a_subset_of_the_detector_vocabulary():
    """The generate -> analyse loop breaks the moment these drift apart."""
    assert set(GENERATABLE_QUESTION_TYPES) <= set(get_question_type_options())


def test_detector_only_outcomes_are_not_generatable():
    assert QUESTION_TYPE_EMPTY not in GENERATABLE_QUESTION_TYPES
    assert QUESTION_TYPE_UNKNOWN not in GENERATABLE_QUESTION_TYPES


def test_schema_has_no_slot_for_claiming_a_validated_scale(golden):
    """Structural defence against the model citing an instrument it did not use."""
    for question in golden.all_questions():
        assert question.source == QUESTION_SOURCE_GENERATED


def test_round_trip_is_lossless(golden_payload):
    survey = Survey.from_dict(golden_payload)
    assert survey.to_dict() == golden_payload


def test_round_trip_is_stable_across_two_passes(golden):
    once = Survey.from_dict(golden.to_dict())
    twice = Survey.from_dict(once.to_dict())
    assert once == twice


def test_unknown_keys_are_dropped_rather_than_raising(golden_payload):
    payload = json.loads(json.dumps(golden_payload))
    payload["some_future_field"] = {"added": "by a newer version"}
    payload["sections"][0]["questions"][0]["future_question_field"] = 1
    survey = Survey.from_dict(payload)
    assert survey.survey_id == golden_payload["survey_id"]


def test_golden_declares_the_current_schema_version(golden):
    assert golden.schema_version == SCHEMA_VERSION


def test_construct_membership_is_derived_not_stored(golden):
    """Construct carries no question list: a second copy would drift."""
    assert not hasattr(golden.constructs[0], "question_ids")
    service = golden.questions_for_construct("c_service")
    assert [q.question_id for q in service] == ["Q02", "Q03", "Q04", "Q05"]
    assert all(q.question_type == QUESTION_TYPE_SCALE for q in service)


def test_question_lookup_and_iteration_agree(golden):
    questions = golden.all_questions()
    assert len(questions) == 13
    assert golden.question_by_id("Q10").code == "attn_check"
    assert golden.question_by_id("nope") is None
    assert [section.section_id for section, _ in golden.iter_questions()][:2] == ["S1", "S2"]


def test_response_metadata_spec_is_reserved_but_disabled(golden):
    spec = golden.response_metadata_spec
    assert spec.enabled is False
    assert spec.collected_by is None
    assert spec.source_mappings == {}
    for name in (
        "duration_total_seconds",
        "per_question_dwell",
        "dropout_position",
        "option_order_seed",
        "per_question_option_order",
    ):
        assert name in spec.fields


def test_localized_helpers():
    value = localized("中文", "English")
    assert text_in(value, "zh-CN") == "中文"
    assert text_in(value, "en") == "English"
    assert text_in(value, "fr") == "English"
    assert text_in(None, "en") == ""
